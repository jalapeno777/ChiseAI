"""
Runbook Executor Framework for ChiseAI.

Links documentation (docs/runbooks/*.md) to automation (scripts/ops/).
"""

__version__ = "0.1.0"
__all__ = ["RunbookExecutor", "RunbookParser", "ExecutionResult", "StepResult"]

from .executor import ExecutionResult, RunbookExecutor, StepResult
from .parser import RunbookParser
