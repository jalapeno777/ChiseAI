"""Hyperparameter comparison utilities."""

from typing import Any

from .models import HyperparameterSet


class HyperparameterComparator:
    """Utility class for comparing hyperparameter sets."""

    @staticmethod
    def compare(exp1: HyperparameterSet, exp2: HyperparameterSet) -> dict[str, Any]:
        """Compare two hyperparameter sets and return differences.

        Args:
            exp1: First hyperparameter set
            exp2: Second hyperparameter set

        Returns:
            Dictionary containing differences between the two sets
        """
        diff = {"changed": {}, "added": {}, "removed": {}, "unchanged": {}}

        # Convert to dictionaries for comparison
        dict1 = exp1.to_dict()
        dict2 = exp2.to_dict()

        # Get all unique keys
        all_keys = set(dict1.keys()) | set(dict2.keys())

        for key in all_keys:
            val1 = dict1.get(key)
            val2 = dict2.get(key)

            if key not in dict1:
                # Key exists only in exp2
                diff["added"][key] = val2
            elif key not in dict2:
                # Key exists only in exp1
                diff["removed"][key] = val1
            elif val1 != val2:
                # Key exists in both but values differ
                diff["changed"][key] = {"old": val1, "new": val2}
            else:
                # Key exists in both with same value
                diff["unchanged"][key] = val1

        return diff

    @staticmethod
    def diff_to_string(diff_dict: dict[str, Any]) -> str:
        """Convert difference dictionary to human-readable string.

        Args:
            diff_dict: Dictionary containing differences

        Returns:
            Human-readable string representation of differences
        """
        lines = []

        if diff_dict.get("changed"):
            lines.append("Changed parameters:")
            for key, values in diff_dict["changed"].items():
                lines.append(f"  {key}: {values['old']} → {values['new']}")

        if diff_dict.get("added"):
            lines.append("Added parameters:")
            for key, value in diff_dict["added"].items():
                lines.append(f"  {key}: {value}")

        if diff_dict.get("removed"):
            lines.append("Removed parameters:")
            for key, value in diff_dict["removed"].items():
                lines.append(f"  {key}: {value}")

        if diff_dict.get("unchanged"):
            lines.append(f"Unchanged parameters: {len(diff_dict['unchanged'])}")

        if not any(
            [diff_dict.get("changed"), diff_dict.get("added"), diff_dict.get("removed")]
        ):
            return "No differences found - hyperparameter sets are identical"

        return "\n".join(lines)

    @staticmethod
    def get_changed_params(
        exp1: HyperparameterSet, exp2: HyperparameterSet
    ) -> list[str]:
        """Get list of parameter names that changed between two hyperparameter sets.

        Args:
            exp1: First hyperparameter set
            exp2: Second hyperparameter set

        Returns:
            List of parameter names that changed
        """
        diff = HyperparameterComparator.compare(exp1, exp2)
        return list(diff.get("changed", {}).keys())

    @staticmethod
    def get_unchanged_params(
        exp1: HyperparameterSet, exp2: HyperparameterSet
    ) -> list[str]:
        """Get list of parameter names that remained unchanged between two hyperparameter sets.

        Args:
            exp1: First hyperparameter set
            exp2: Second hyperparameter set

        Returns:
            List of parameter names that remained unchanged
        """
        diff = HyperparameterComparator.compare(exp1, exp2)
        return list(diff.get("unchanged", {}).keys())
