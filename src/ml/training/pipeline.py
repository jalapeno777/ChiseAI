"""End-to-end training data pipeline.

Provides TrainingPipeline class that orchestrates feature extraction,
batch processing, and outcome enrichment to create complete TrainingSample
objects ready for ML model training.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from market_analysis.signal_storage.interface import SignalStorageInterface
    from market_analysis.signal_storage.models import SignalWithOutcome

    from ml.training.extractor import ExtractedFeatures, FeatureExtractor
    from ml.training.schema import TrainingSample

logger = logging.getLogger(__name__)


@dataclass
class PipelineStats:
    """Statistics for pipeline processing.

    Attributes:
        total_signals: Total number of signals processed
        successful: Number of successfully processed signals
        failed: Number of failed signal processing
        skipped: Number of skipped signals (missing data)
        processing_time_ms: Total processing time in milliseconds
        batch_count: Number of batches processed
    """

    total_signals: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    processing_time_ms: float = 0.0
    batch_count: int = 0

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_signals == 0:
            return 0.0
        return (self.successful / self.total_signals) * 100.0

    @property
    def avg_time_per_signal_ms(self) -> float:
        """Calculate average processing time per signal."""
        if self.total_signals == 0:
            return 0.0
        return self.processing_time_ms / self.total_signals

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "total_signals": self.total_signals,
            "successful": self.successful,
            "failed": self.failed,
            "skipped": self.skipped,
            "success_rate_pct": round(self.success_rate, 2),
            "processing_time_ms": round(self.processing_time_ms, 2),
            "avg_time_per_signal_ms": round(self.avg_time_per_signal_ms, 2),
            "batch_count": self.batch_count,
        }


@dataclass
class PipelineConfig:
    """Configuration for training pipeline.

    Attributes:
        batch_size: Number of signals to process per batch
        max_concurrent: Maximum concurrent extraction operations
        cache_enabled: Whether to enable feature caching
        default_outcome_window: Default window for outcome calculation
        skip_on_missing_data: Whether to skip signals with missing data
        enrichment_enabled: Whether to enrich with outcome labels
    """

    batch_size: int = 100
    max_concurrent: int = 10
    cache_enabled: bool = True
    default_outcome_window: timedelta = field(
        default_factory=lambda: timedelta(hours=24)
    )
    skip_on_missing_data: bool = True
    enrichment_enabled: bool = True


class TrainingPipeline:
    """End-to-end pipeline from signals to training samples.

    Orchestrates feature extraction, batch processing, and outcome
    enrichment to create complete TrainingSample objects.

    Attributes:
        extractor: FeatureExtractor instance
        signal_storage: Signal storage interface
        config: Pipeline configuration
        stats: Pipeline statistics
    """

    def __init__(
        self,
        extractor: FeatureExtractor,
        signal_storage: SignalStorageInterface | None = None,
        config: PipelineConfig | None = None,
    ) -> None:
        """Initialize training pipeline.

        Args:
            extractor: Feature extractor instance
            signal_storage: Signal storage interface
            config: Optional pipeline configuration
        """
        self.extractor = extractor
        self.signal_storage = signal_storage
        self.config = config or PipelineConfig()
        self.stats = PipelineStats()
        self._semaphore: asyncio.Semaphore | None = None

    async def process_signal(
        self,
        signal_id: str,
        skip_enrichment: bool = False,
    ) -> TrainingSample | None:
        """Process single signal into training sample.

        Args:
            signal_id: Signal identifier
            skip_enrichment: Whether to skip outcome enrichment

        Returns:
            TrainingSample if successful, None otherwise
        """
        start_time = datetime.now()

        try:
            # Extract features
            features = await self.extractor.extract_features(signal_id)
            if features is None:
                logger.warning(f"Failed to extract features for signal: {signal_id}")
                self.stats.skipped += 1
                return None

            # Create training sample from features
            sample = self._create_sample_from_features(features)

            # Enrich with outcomes if enabled and not skipped
            if self.config.enrichment_enabled and not skip_enrichment:
                samples = await self.enrich_with_outcomes(
                    [sample],
                    self.config.default_outcome_window,
                )
                if samples:
                    sample = samples[0]

            self.stats.successful += 1
            return sample

        except Exception as e:
            logger.error(f"Failed to process signal {signal_id}: {e}")
            self.stats.failed += 1
            return None

        finally:
            self.stats.total_signals += 1
            elapsed = (datetime.now() - start_time).total_seconds() * 1000
            self.stats.processing_time_ms += elapsed

    async def process_batch(
        self,
        signal_ids: list[str],
        batch_size: int | None = None,
        show_progress: bool = False,
    ) -> list[TrainingSample]:
        """Process multiple signals efficiently.

        Args:
            signal_ids: List of signal identifiers
            batch_size: Override default batch size
            show_progress: Whether to log progress

        Returns:
            List of successfully processed TrainingSample objects
        """
        batch_size = batch_size or self.config.batch_size
        results: list[TrainingSample] = []

        # Initialize semaphore for concurrency control
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.config.max_concurrent)

        # Process in batches
        total_batches = (len(signal_ids) + batch_size - 1) // batch_size

        for batch_idx in range(total_batches):
            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(signal_ids))
            batch = signal_ids[start_idx:end_idx]

            if show_progress:
                logger.info(
                    f"Processing batch {batch_idx + 1}/{total_batches} "
                    f"({len(batch)} signals)"
                )

            # Process batch concurrently
            batch_results = await self._process_batch_concurrent(batch)
            results.extend(batch_results)

            self.stats.batch_count += 1

            if show_progress:
                logger.info(
                    f"Batch {batch_idx + 1} complete: "
                    f"{len(batch_results)}/{len(batch)} successful"
                )

        return results

    async def _process_batch_concurrent(
        self,
        signal_ids: list[str],
    ) -> list[TrainingSample]:
        """Process a batch of signals concurrently.

        Args:
            signal_ids: List of signal identifiers

        Returns:
            List of successfully processed TrainingSample objects
        """
        if self._semaphore is None:
            raise RuntimeError("Pipeline semaphore not initialized")
        semaphore = cast(asyncio.Semaphore, self._semaphore)

        async def process_with_semaphore(signal_id: str) -> TrainingSample | None:
            async with semaphore:
                return await self.process_signal(signal_id)

        # Create tasks for all signals
        tasks = [process_with_semaphore(sid) for sid in signal_ids]

        # Execute concurrently and collect results
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out failures and exceptions
        results: list[TrainingSample] = []
        for result in completed:
            if isinstance(result, Exception):
                logger.error(f"Signal processing error: {result}")
                self.stats.failed += 1
            elif result is not None:
                results.append(result)

        return results

    async def enrich_with_outcomes(
        self,
        samples: list[TrainingSample],
        outcome_window: timedelta | None = None,
    ) -> list[TrainingSample]:
        """Add outcome labels (win/loss, PnL) to samples.

        Args:
            samples: List of training samples to enrich
            outcome_window: Time window for outcome calculation

        Returns:
            List of enriched training samples
        """
        if self.signal_storage is None:
            logger.warning("Signal storage not configured, skipping enrichment")
            return samples

        outcome_window = outcome_window or self.config.default_outcome_window
        enriched: list[TrainingSample] = []

        for sample in samples:
            try:
                # Get outcome for this signal
                outcome = await self.signal_storage.get_outcome_by_signal_id(
                    sample.sample_id
                )

                if outcome is not None:
                    # Calculate PnL percentage
                    pnl_pct = self._calculate_pnl_percentage(sample, outcome)

                    # Update sample with outcome data
                    sample.outcome = 1 if outcome.is_win else 0
                    sample.pnl_percent = pnl_pct
                    sample.holding_period_minutes = int(outcome.duration_hours * 60)

                enriched.append(sample)

            except Exception as e:
                logger.warning(f"Failed to enrich sample {sample.sample_id}: {e}")
                enriched.append(sample)  # Keep sample even if enrichment fails

        return enriched

    def _create_sample_from_features(
        self, features: ExtractedFeatures
    ) -> TrainingSample:
        """Create TrainingSample from extracted features.

        Args:
            features: Extracted features

        Returns:
            TrainingSample instance
        """
        from ml.training.schema import TrainingSample

        # Calculate confidence bin
        confidence_bin = 0
        if features.confidence is not None:
            confidence_bin = min(int(features.confidence * 10), 10)

        # Calculate BB width if both bands available
        bb_width = None
        if (
            features.technical.bb_upper is not None
            and features.technical.bb_lower is not None
            and features.entry_price is not None
            and features.entry_price > 0
        ):
            bb_width = (
                (features.technical.bb_upper - features.technical.bb_lower)
                / features.entry_price
            ) * 100

        return TrainingSample(
            sample_id=features.signal_id,
            timestamp=features.timestamp,
            token=features.token,
            timeframe=features.timeframe,
            # Technical indicators
            rsi=features.technical.rsi,
            macd=features.technical.macd,
            macd_signal=features.technical.macd_signal,
            macd_histogram=features.technical.macd_histogram,
            bb_upper=features.technical.bb_upper,
            bb_lower=features.technical.bb_lower,
            bb_width=bb_width,
            atr=features.technical.atr,
            volume_sma=features.technical.volume_sma,
            # Trend and confluence
            trend_state=features.market.trend_state,
            confluence_score=features.market.confluence_score,
            confidence=features.confidence,
            direction=features.direction,
            # Price data
            entry_price=features.entry_price,
            price_change_24h=features.market.price_change_24h,
            volatility=features.market.volatility,
            # Confidence metadata
            predicted_prob=features.predicted_prob,
            confidence_bin=confidence_bin,
        )

    def _calculate_pnl_percentage(
        self,
        sample: TrainingSample,
        outcome: Any,
    ) -> float | None:
        """Calculate PnL percentage for a sample.

        Args:
            sample: Training sample
            outcome: Outcome record

        Returns:
            PnL percentage or None
        """
        if sample.entry_price is None or sample.entry_price == 0:
            return None

        # Calculate percentage change
        if hasattr(outcome, "exit_price") and outcome.exit_price is not None:
            pnl_pct = (
                (outcome.exit_price - sample.entry_price) / sample.entry_price
            ) * 100

            # Adjust sign based on direction
            if sample.direction == "short":
                pnl_pct = -pnl_pct

            return round(pnl_pct, 4)

        # Fallback to outcome PnL if available
        if hasattr(outcome, "pnl") and outcome.pnl is not None:
            return round(outcome.pnl, 4)

        return None

    async def process_query_results(
        self,
        signals_with_outcomes: list[SignalWithOutcome],
        batch_size: int | None = None,
    ) -> list[TrainingSample]:
        """Process signals already queried with outcomes.

        Args:
            signals_with_outcomes: List of SignalWithOutcome from storage query
            batch_size: Override default batch size

        Returns:
            List of TrainingSample objects
        """
        samples: list[TrainingSample] = []

        for swo in signals_with_outcomes:
            try:
                # Extract features from signal
                features = self.extractor._extract_from_signal(swo.signal)

                # Create sample
                sample = self._create_sample_from_features(features)

                # Add outcome data if available
                if swo.outcome is not None:
                    sample.outcome = 1 if swo.outcome.is_win else 0
                    sample.pnl_percent = self._calculate_pnl_percentage(
                        sample, swo.outcome
                    )
                    sample.holding_period_minutes = int(swo.outcome.duration_hours * 60)

                samples.append(sample)
                self.stats.successful += 1

            except Exception as e:
                logger.error(f"Failed to process signal {swo.signal.signal_id}: {e}")
                self.stats.failed += 1

        self.stats.total_signals += len(signals_with_outcomes)
        return samples

    def get_stats(self) -> PipelineStats:
        """Get current pipeline statistics.

        Returns:
            PipelineStats with current processing statistics
        """
        return self.stats

    def reset_stats(self) -> None:
        """Reset pipeline statistics."""
        self.stats = PipelineStats()

    async def process_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        token: str | None = None,
        batch_size: int | None = None,
    ) -> list[TrainingSample]:
        """Process all signals within a date range.

        Args:
            start_date: Start date (inclusive)
            end_date: End date (inclusive)
            token: Optional token filter
            batch_size: Override default batch size

        Returns:
            List of TrainingSample objects
        """
        if self.signal_storage is None:
            logger.error("Signal storage not configured")
            return []

        # Convert to timestamps
        start_ts = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        # Query signals with outcomes
        signals_with_outcomes = await self.signal_storage.query_signals_with_outcomes(
            token=token,
            start_time=start_ts,
            end_time=end_ts,
            resolved_only=True,
            limit=10000,  # Large limit for batch processing
        )

        logger.info(f"Found {len(signals_with_outcomes)} signals in date range")

        # Process signals
        return await self.process_query_results(
            signals_with_outcomes,
            batch_size=batch_size,
        )
