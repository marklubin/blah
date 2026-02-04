"""Radar commands - config, pull, report, status."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def radar():
    """Monitor feeds and review reports."""


@radar.command("config")
def radar_config():
    """Configure radar sources via chat."""
    console.print("[yellow]Not implemented yet. Coming in Phase 4.[/yellow]")


@radar.command()
def pull():
    """Manually trigger source polling."""
    console.print("[yellow]Not implemented yet. Coming in Phase 4.[/yellow]")


@radar.command()
@click.argument("report_id", required=False)
def report(report_id: str | None):
    """Review a radar report via chat."""
    console.print("[yellow]Not implemented yet. Coming in Phase 4.[/yellow]")


@radar.command("status")
def radar_status():
    """Show radar configuration status."""
    console.print("[yellow]Not implemented yet. Coming in Phase 4.[/yellow]")
