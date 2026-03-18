"""Training integration with model registry for ChiseAI.

This module provides integration between the training pipeline and model registry,
enabling automatic registration of trained models with full lineage tracking.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from ml.model_registry.artifact_linker import ArtifactLinker, TrainingArtifact
from ml.model_registry.registry import ModelRegistry, ModelStatus

logger = logging.getLogger(__name__)


class TrainingCallback(Protocol):
    """Protocol for training callbacks."""
    
    def on_training_complete(
        self,
        model_id: str,
        model_path: str,
        metrics: Dict[str, float],
        hyperparameters: Dict[str, Any],
    ) -> None:
        """Called when training completes."""
        ...


@dataclass
class TrainingConfig:
    """Configuration for training integration."""
    
    auto_register: bool = True
    auto_promote_to_challenger: bool = False
    validation_threshold: float = 0.0
    required_metrics: List[str] = None
    tags: List[str] = None
    
    def __post_init__(self):
        if self.required_metrics is None:
            self.required_metrics = []
        if self.tags is None:
            self.tags = []


class TrainingIntegration:
    """Integrates training pipeline with model registry."""
    
    def __init__(self, registry: ModelRegistry, config: Optional[TrainingConfig] = None):
        """Initialize training integration.
        
        Args:
            registry: Model registry instance
            config: Training integration configuration
        """
        self.registry = registry
        self.config = config or TrainingConfig()
        self.linker = ArtifactLinker(registry)
        self._callbacks: List[TrainingCallback] = []
        
    def register_callback(self, callback: TrainingCallback) -> None:
        """Register a training callback."""
        self._callbacks.append(callback)
        
    def on_training_complete(
        self,
        model_id: str,
        model_path: str,
        metrics: Dict[str, float],
        hyperparameters: Dict[str, Any],
        training_metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Handle training completion and register model.
        
        Args:
            model_id: Model identifier
            model_path: Path to trained model
            metrics: Training metrics
            hyperparameters: Model hyperparameters
            training_metadata: Additional training metadata
            
        Returns:
            Version ID if registered, None otherwise
        """
        if not self.config.auto_register:
            logger.info(f"Auto-registration disabled, skipping model {model_id}")
            return None
            
        # Validate required metrics
        if self.config.required_metrics:
            missing = set(self.config.required_metrics) - set(metrics.keys())
            if missing:
                logger.error(f"Missing required metrics: {missing}")
                return None
                
        # Check validation threshold
        if self.config.validation_threshold > 0:
            primary_metric = metrics.get("accuracy", metrics.get("loss", 0))
            if isinstance(primary_metric, (int, float)):
                if primary_metric < self.config.validation_threshold:
                    logger.warning(f"Model {model_id} failed validation threshold")
                    return None
        
        # Create training artifact
        artifact = TrainingArtifact(
            model_path=model_path,
            metrics=metrics,
            hyperparameters=hyperparameters,
            training_metadata=training_metadata or {},
        )
        
        # Register with model registry
        try:
            version = self.linker.link_training_run(
                model_id=model_id,
                artifact=artifact,
                tags=self.config.tags,
            )
            
            # Auto-promote to challenger if configured
            if self.config.auto_promote_to_challenger:
                self.registry.promote_to_challenger(version.version_id)
                logger.info(f"Auto-promoted {version.version_id} to challenger")
            
            # Call callbacks
            for callback in self._callbacks:
                try:
                    callback.on_training_complete(
                        model_id=model_id,
                        model_path=model_path,
                        metrics=metrics,
                        hyperparameters=hyperparameters,
                    )
                except Exception as e:
                    logger.error(f"Callback error: {e}")
            
            logger.info(f"Successfully registered training run for {model_id}")
            return version.version_id
            
        except Exception as e:
            logger.error(f"Failed to register training run: {e}")
            return None
    
    def validate_and_promote(
        self,
        version_id: str,
        validation_metrics: Dict[str, float],
        promotion_criteria: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Validate model and promote if criteria met.
        
        Args:
            version_id: Model version ID
            validation_metrics: Validation metrics
            promotion_criteria: Optional promotion criteria
            
        Returns:
            True if promoted, False otherwise
        """
        try:
            # Update with validation results
            self.linker.update_with_validation(version_id, validation_metrics)
            
            # Check promotion criteria
            if promotion_criteria:
                if self._meets_criteria(validation_metrics, promotion_criteria):
                    self.registry.promote_to_challenger(version_id)
                    logger.info(f"Promoted {version_id} to challenger")
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Validation and promotion failed: {e}")
            return False
    
    def _meets_criteria(
        self,
        metrics: Dict[str, float],
        criteria: Dict[str, Any],
    ) -> bool:
        """Check if metrics meet promotion criteria."""
        for metric, threshold in criteria.items():
            if metric not in metrics:
                return False
            if metrics[metric] < threshold:
                return False
        return True
    
    def get_training_summary(self, model_id: str) -> Dict[str, Any]:
        """Get training summary for a model.
        
        Args:
            model_id: Model identifier
            
        Returns:
            Training summary with lineage information
        """
        versions = self.registry.list_versions(model_id)
        
        summary = {
            "model_id": model_id,
            "total_versions": len(versions),
            "training_runs": [],
        }
        
        for version in versions:
            lineage = self.linker.get_training_lineage(version.version_id)
            summary["training_runs"].append(lineage)
        
        return summary
    
    def cleanup_old_versions(
        self,
        model_id: str,
        keep_last_n: int = 5,
    ) -> List[str]:
        """Clean up old model versions, keeping only the last N.
        
        Args:
            model_id: Model identifier
            keep_last_n: Number of recent versions to keep
            
        Returns:
            List of deleted version IDs
        """
        versions = self.registry.list_versions(model_id)
        
        # Sort by creation date (newest first)
        sorted_versions = sorted(
            versions,
            key=lambda v: v.created_at or datetime.min,
            reverse=True,
        )
        
        # Keep only the last N versions
        to_delete = sorted_versions[keep_last_n:]
        deleted = []
        
        for version in to_delete:
            try:
                self.registry.delete_version(version.version_id)
                deleted.append(version.version_id)
                logger.info(f"Deleted old version {version.version_id}")
            except Exception as e:
                logger.error(f"Failed to delete {version.version_id}: {e}")
        
        return deleted
