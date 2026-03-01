"""BrainEval scheduling scripts.

# SAFETY: No risk cap logic modified
# SAFETY: No promotion gate logic modified
# SAFETY: No live trading flow modified

Provides scheduling infrastructure for MiniBrainEval runs at 6h, daily, and weekly cadences.

Modules:
    schedule_brain_eval: Main scheduler script for running evaluations
    run_6h_eval: Shell wrapper for 6-hour evaluations
    run_daily_eval: Shell wrapper for daily evaluations
    run_weekly_eval: Shell wrapper for weekly evaluations
"""

__all__ = ["schedule_brain_eval"]
