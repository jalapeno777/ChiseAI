"""CLI commands for kill-switch management.

Provides command-line interface for kill-switch status checking,
manual triggering, and reauthorization.

For ST-EX-003: Kill-Switch Executor Implementation
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import click


@click.group(name="kill-switch")
def kill_switch_cli():
    """Kill-switch management commands."""
    pass


@kill_switch_cli.command(name="status")
@click.option(
    "--config",
    "-c",
    type=str,
    default=None,
    help="Path to configuration file",
)
def status_command(config: str | None) -> None:
    """Show current kill-switch status."""
    asyncio.run(_show_status(config))


async def _show_status(config_path: str | None) -> None:
    """Display kill-switch status."""
    try:
        # Import here to avoid circular imports
        from execution.kill_switch.executor import KillSwitchExecutor
        from execution.kill_switch.state import KillSwitchState

        # Create executor (would normally load from config)
        executor = KillSwitchExecutor()

        state = executor.get_state()
        summary = executor.get_summary()

        # Print status
        click.echo("=" * 50)
        click.echo("KILL-SWITCH STATUS")
        click.echo("=" * 50)

        # State with color
        state_colors = {
            KillSwitchState.ARMED: click.style("ARMED", fg="green", bold=True),
            KillSwitchState.TRIGGERED: click.style("TRIGGERED", fg="red", bold=True),
            KillSwitchState.DISABLED: click.style("DISABLED", fg="yellow"),
        }
        click.echo(f"State: {state_colors.get(state, state.value)}")

        # Trigger info
        if summary.get("triggered_at"):
            click.echo(f"Triggered At: {summary['triggered_at']}")
            click.echo(f"Triggered By: {summary.get('triggered_by', 'unknown')}")
            click.echo(f"Reason: {summary.get('trigger_reason', 'N/A')}")

        # Reauthorization info
        if summary.get("reauthorized_at"):
            click.echo(f"Reauthorized At: {summary['reauthorized_at']}")
            click.echo(f"Reauthorized By: {summary.get('reauthorized_by', 'unknown')}")

        # Last result
        last_result = summary.get("last_result")
        if last_result:
            click.echo("-" * 50)
            click.echo("LAST EXECUTION:")
            click.echo(f"  Success: {last_result.get('success')}")
            click.echo(f"  Positions Closed: {last_result.get('positions_closed', 0)}")
            click.echo(f"  Total PnL: {last_result.get('total_pnl', 0):.2f}")
            click.echo(f"  Environment: {last_result.get('environment', 'unknown')}")

            metadata = last_result.get("metadata", {})
            if metadata.get("drawdown_pct"):
                click.echo(f"  Drawdown: {metadata['drawdown_pct']:.2f}%")

        # Config
        cfg = summary.get("config", {})
        click.echo("-" * 50)
        click.echo("CONFIGURATION:")
        click.echo(f"  Drawdown Threshold: {cfg.get('drawdown_threshold_pct', 15.0)}%")
        click.echo(f"  Rolling Window: {cfg.get('rolling_window_hours', 24)}h")
        click.echo(
            f"  Require Reauthorization: {cfg.get('require_reauthorization', True)}"
        )
        click.echo(f"  Max Close Retries: {cfg.get('max_close_retries', 3)}")

        click.echo("=" * 50)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@kill_switch_cli.command(name="trigger")
@click.option(
    "--reason",
    "-r",
    type=str,
    default="manual",
    help="Reason for kill-switch trigger",
)
@click.option(
    "--environment",
    "-e",
    type=click.Choice(["live", "paper", "demo"]),
    default="paper",
    help="Trading environment",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt",
)
def trigger_command(reason: str, environment: str, force: bool) -> None:
    """Manually trigger kill-switch with confirmation."""
    asyncio.run(_trigger_kill_switch(reason, environment, force))


async def _trigger_kill_switch(reason: str, environment: str, force: bool) -> None:
    """Execute kill-switch trigger."""
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchState

    try:
        # Create executor
        executor = KillSwitchExecutor()

        # Check current state
        if executor.state == KillSwitchState.DISABLED:
            click.echo(
                click.style(
                    "Error: Kill-switch is disabled. Enable it first.", fg="red"
                ),
                err=True,
            )
            sys.exit(1)

        if executor.state == KillSwitchState.TRIGGERED:
            click.echo(
                click.style("Error: Kill-switch already triggered.", fg="red"),
                err=True,
            )
            sys.exit(1)

        # Confirmation prompt
        if not force:
            click.echo(
                click.style(
                    "WARNING: This will close ALL positions immediately!",
                    fg="red",
                    bold=True,
                )
            )
            click.echo(f"Environment: {environment}")
            click.echo(f"Reason: {reason}")
            click.echo()

            if environment == "live":
                click.echo(
                    click.style(
                        "LIVE ENVIRONMENT - REAL MONEY AT RISK!", fg="red", blink=True
                    )
                )

            confirmed = click.confirm(
                "Are you sure you want to trigger the kill-switch?"
            )
            if not confirmed:
                click.echo("Kill-switch trigger cancelled.")
                return

        # Execute kill-switch
        click.echo("Triggering kill-switch...")

        result = await executor.execute_kill_switch(
            reason=reason,
            triggered_by="manual_cli",
            environment=environment,
        )

        # Display result
        click.echo()
        click.echo("=" * 50)
        click.echo("KILL-SWITCH EXECUTION RESULT")
        click.echo("=" * 50)

        if result.success:
            click.echo(click.style("SUCCESS", fg="green", bold=True))
        else:
            click.echo(click.style("FAILED", fg="red", bold=True))

        click.echo(f"Positions Closed: {result.positions_closed}")
        click.echo(f"Total PnL: {result.total_pnl:.2f}")
        click.echo(f"Environment: {result.environment}")

        if result.close_results:
            click.echo("-" * 50)
            click.echo("POSITION DETAILS:")
            for close_result in result.close_results:
                status_color = (
                    "green" if close_result.status.value == "success" else "red"
                )
                click.echo(
                    f"  {close_result.symbol}: "
                    f"{close_result.side} {close_result.quantity} @ {close_result.price:.4f} "
                    f"[{click.style(close_result.status.value, fg=status_color)}]"
                )
                if close_result.error:
                    click.echo(f"    Error: {close_result.error}")

        click.echo("=" * 50)

        # Exit with error code if failed
        if not result.success:
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@kill_switch_cli.command(name="reauthorize")
@click.option(
    "--packet-id",
    "-p",
    type=str,
    required=True,
    help="Signed authorization packet ID",
)
def reauthorize_command(packet_id: str) -> None:
    """Reauthorize kill-switch after trigger."""
    asyncio.run(_reauthorize(packet_id))


async def _reauthorize(packet_id: str) -> None:
    """Reauthorize kill-switch."""
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchState

    try:
        # Create executor
        executor = KillSwitchExecutor()

        # Check current state
        if executor.state != KillSwitchState.TRIGGERED:
            click.echo(
                click.style(
                    f"Error: Kill-switch is {executor.state.value}, not triggered.",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

        # Validate packet ID format (basic check)
        if not packet_id or len(packet_id) < 8:
            click.echo(
                click.style("Error: Invalid packet ID format.", fg="red"),
                err=True,
            )
            sys.exit(1)

        # Execute reauthorization
        click.echo(f"Reauthorizing kill-switch with packet: {packet_id[:16]}...")

        success = await executor.reauthorize(packet_id)

        if success:
            click.echo(
                click.style(
                    "Kill-switch reauthorized successfully!", fg="green", bold=True
                )
            )
            click.echo(f"New state: {executor.state.value}")
        else:
            click.echo(click.style("Reauthorization failed.", fg="red"), err=True)
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@kill_switch_cli.command(name="arm")
def arm_command() -> None:
    """Arm the kill-switch (enable monitoring)."""
    asyncio.run(_arm())


async def _arm() -> None:
    """Arm kill-switch."""
    from execution.kill_switch.executor import KillSwitchExecutor

    try:
        executor = KillSwitchExecutor()
        success = await executor.arm()

        if success:
            click.echo(
                click.style(
                    f"Kill-switch armed. State: {executor.state.value}", fg="green"
                )
            )
        else:
            click.echo(
                click.style(
                    "Failed to arm kill-switch. Check if reauthorization is required.",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


@kill_switch_cli.command(name="disable")
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Force disable even if triggered",
)
def disable_command(force: bool) -> None:
    """Disable the kill-switch (stop monitoring)."""
    asyncio.run(_disable(force))


async def _disable(force: bool) -> None:
    """Disable kill-switch."""
    from execution.kill_switch.executor import KillSwitchExecutor
    from execution.kill_switch.state import KillSwitchState

    try:
        executor = KillSwitchExecutor()

        # Check if triggered
        if executor.state == KillSwitchState.TRIGGERED and not force:
            click.echo(
                click.style(
                    "Error: Kill-switch is triggered. Use --force to disable anyway "
                    "(not recommended).",
                    fg="red",
                ),
                err=True,
            )
            sys.exit(1)

        success = await executor.disable()

        if success:
            click.echo(
                click.style(
                    f"Kill-switch disabled. State: {executor.state.value}", fg="yellow"
                )
            )
        else:
            click.echo(
                click.style("Failed to disable kill-switch.", fg="red"),
                err=True,
            )
            sys.exit(1)

    except Exception as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(1)


def register_commands(cli: click.Group) -> None:
    """Register kill-switch commands with the main CLI.

    Args:
        cli: Main CLI group to register commands with
    """
    cli.add_command(kill_switch_cli)


# Standalone entry point
if __name__ == "__main__":
    kill_switch_cli()
