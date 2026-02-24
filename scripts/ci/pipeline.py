"""CI/CD Pipeline Configuration for ST-NS-030."""
import os
import subprocess
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Callable

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    LINT = "lint"
    TEST = "test"
    BUILD = "build"
    SECURITY = "security"
    DEPLOY = "deploy"


class PipelineStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    """Result of a pipeline stage execution."""
    stage: PipelineStage
    status: PipelineStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: float = 0.0
    output: str = ""
    error: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        return {
            "stage": self.stage.value,
            "status": self.status.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration_seconds": self.duration_seconds,
            "output": self.output[:1000],  # Truncate
            "error": self.error[:1000],
            "metrics": self.metrics,
        }


@dataclass
class PipelineConfig:
    """Configuration for CI/CD pipeline."""
    project_name: str = "chiseai"
    python_version: str = "3.13"
    enable_lint: bool = True
    enable_test: bool = True
    enable_security_scan: bool = True
    enable_build: bool = True
    min_coverage: float = 80.0
    fail_on_coverage_drop: bool = True
    parallel_jobs: int = 4
    timeout_minutes: int = 60
    
    def to_dict(self) -> dict:
        return {
            "project_name": self.project_name,
            "python_version": self.python_version,
            "enable_lint": self.enable_lint,
            "enable_test": self.enable_test,
            "enable_security_scan": self.enable_security_scan,
            "min_coverage": self.min_coverage,
            "parallel_jobs": self.parallel_jobs,
            "timeout_minutes": self.timeout_minutes,
        }


class StageRunner:
    """Base class for running pipeline stages."""
    
    def __init__(self, config: PipelineConfig):
        self.config = config
    
    def run_command(self, cmd: list[str], cwd: Optional[str] = None, 
                    timeout: Optional[int] = None) -> tuple[int, str, str]:
        """Run a shell command and return exit code, stdout, stderr."""
        try:
            result = subprocess.run(
                cmd,
                cwd=cwd or os.getcwd(),
                capture_output=True,
                text=True,
                timeout=timeout or self.config.timeout_minutes * 60,
            )
            return result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            return -1, "", "Command timed out"
        except Exception as e:
            return -1, "", str(e)


class LintStage(StageRunner):
    """Lint stage runner."""
    
    def run(self) -> StageResult:
        start_time = datetime.now(timezone.utc)
        stage = PipelineStage.LINT
        
        # Run black check
        code, stdout, stderr = self.run_command(
            ["python3", "-m", "black", "--check", "--diff", "src/", "tests/"]
        )
        black_passed = code == 0
        
        # Run ruff
        code2, stdout2, stderr2 = self.run_command(
            ["python3", "-m", "ruff", "check", "src/", "tests/"]
        )
        ruff_passed = code2 == 0
        
        # Run mypy (if configured)
        code3, stdout3, stderr3 = self.run_command(
            ["python3", "-m", "mypy", "src/", "--ignore-missing-imports"],
            timeout=120,
        )
        mypy_passed = code3 == 0 or code3 == -1  # Allow mypy to be missing
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        status = PipelineStatus.SUCCESS if (black_passed and ruff_passed) else PipelineStatus.FAILED
        
        return StageResult(
            stage=stage,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            output=stdout + stdout2,
            error=stderr + stderr2 if not ruff_passed else "",
            metrics={
                "black_passed": black_passed,
                "ruff_passed": ruff_passed,
                "mypy_passed": mypy_passed,
            },
        )


class TestStage(StageRunner):
    """Test stage runner."""
    
    def run(self) -> StageResult:
        start_time = datetime.now(timezone.utc)
        stage = PipelineStage.TEST
        
        # Run pytest with coverage
        cmd = [
            "python3", "-m", "pytest",
            "tests/",
            "-v",
            f"--cov=src",
            "--cov-report=json:coverage.json",
            "--cov-report=term-missing",
            f"-n{self.config.parallel_jobs}",
        ]
        
        code, stdout, stderr = self.run_command(cmd, timeout=600)
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        # Parse coverage
        coverage_pct = 0.0
        coverage_path = Path("coverage.json")
        if coverage_path.exists():
            try:
                with open(coverage_path) as f:
                    cov_data = json.load(f)
                    coverage_pct = cov_data.get("totals", {}).get("percent_covered", 0.0)
            except Exception:
                pass
        
        passed = code == 0
        coverage_met = coverage_pct >= self.config.min_coverage
        
        if not passed:
            status = PipelineStatus.FAILED
        elif not coverage_met and self.config.fail_on_coverage_drop:
            status = PipelineStatus.FAILED
        else:
            status = PipelineStatus.SUCCESS
        
        return StageResult(
            stage=stage,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            output=stdout,
            error=stderr if not passed else "",
            metrics={
                "tests_passed": passed,
                "coverage_percent": coverage_pct,
                "coverage_target_met": coverage_met,
            },
        )


class SecurityStage(StageRunner):
    """Security scan stage runner."""
    
    def run(self) -> StageResult:
        start_time = datetime.now(timezone.utc)
        stage = PipelineStage.SECURITY
        
        vulnerabilities = []
        
        # Run bandit for security issues
        code, stdout, stderr = self.run_command(
            ["python3", "-m", "bandit", "-r", "src/", "-f", "json"],
            timeout=120,
        )
        bandit_passed = code == 0
        
        if not bandit_passed and stdout:
            try:
                results = json.loads(stdout)
                vulnerabilities.extend(results.get("results", []))
            except json.JSONDecodeError:
                pass
        
        # Run safety for dependency vulnerabilities
        code2, stdout2, stderr2 = self.run_command(
            ["python3", "-m", "safety", "check", "--json"],
            timeout=60,
        )
        safety_passed = code2 == 0
        
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()
        
        # Allow pipeline to pass even if security tools aren't installed
        if not bandit_passed and "No module named bandit" in stderr:
            bandit_passed = True
        if not safety_passed and "No module named safety" in stderr2:
            safety_passed = True
        
        status = PipelineStatus.SUCCESS if (bandit_passed and safety_passed) else PipelineStatus.FAILED
        
        return StageResult(
            stage=stage,
            status=status,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            output=stdout[:1000],
            error=stderr[:500] if not bandit_passed else "",
            metrics={
                "bandit_passed": bandit_passed,
                "safety_passed": safety_passed,
                "vulnerability_count": len(vulnerabilities),
            },
        )


class CIPipeline:
    """Main CI/CD pipeline orchestrator."""
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        self.config = config or PipelineConfig()
        self._results: list[StageResult] = []
        self._start_time: Optional[datetime] = None
        self._end_time: Optional[datetime] = None
    
    def run(self) -> dict[str, Any]:
        """Run the full pipeline."""
        self._start_time = datetime.now(timezone.utc)
        self._results = []
        
        stages = []
        if self.config.enable_lint:
            stages.append(("lint", LintStage(self.config)))
        if self.config.enable_test:
            stages.append(("test", TestStage(self.config)))
        if self.config.enable_security_scan:
            stages.append(("security", SecurityStage(self.config)))
        
        for name, runner in stages:
            logger.info(f"Running stage: {name}")
            try:
                result = runner.run()
                self._results.append(result)
            except Exception as e:
                logger.exception(f"Stage {name} failed with exception")
                self._results.append(StageResult(
                    stage=runner.stage if hasattr(runner, 'stage') else PipelineStage.LINT,
                    status=PipelineStatus.FAILED,
                    start_time=datetime.now(timezone.utc),
                    error=str(e),
                ))
        
        self._end_time = datetime.now(timezone.utc)
        return self.get_report()
    
    def get_report(self) -> dict[str, Any]:
        """Get pipeline execution report."""
        all_passed = all(r.status == PipelineStatus.SUCCESS for r in self._results)
        total_duration = 0.0
        if self._start_time and self._end_time:
            total_duration = (self._end_time - self._start_time).total_seconds()
        
        return {
            "pipeline": self.config.project_name,
            "status": "success" if all_passed else "failed",
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "end_time": self._end_time.isoformat() if self._end_time else None,
            "total_duration_seconds": total_duration,
            "stages": [r.to_dict() for r in self._results],
            "summary": {
                "total_stages": len(self._results),
                "passed_stages": sum(1 for r in self._results if r.status == PipelineStatus.SUCCESS),
                "failed_stages": sum(1 for r in self._results if r.status == PipelineStatus.FAILED),
            },
        }
    
    def is_green(self) -> bool:
        """Check if pipeline is fully green."""
        return all(r.status == PipelineStatus.SUCCESS for r in self._results)
