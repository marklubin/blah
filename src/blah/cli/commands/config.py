"""Config commands - show, edit, models, credentials, sources."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group("config")
def config():
    """Manage Blah configuration."""


@config.command()
def show():
    """Show current configuration."""
    console.print("[yellow]Not implemented yet. Coming in Phase 5.[/yellow]")


@config.command()
def edit():
    """Open config.yaml in $EDITOR."""
    console.print("[yellow]Not implemented yet. Coming in Phase 5.[/yellow]")


@config.command()
def models():
    """Configure models per agent/task."""
    console.print("[yellow]Not implemented yet. Coming in Phase 5.[/yellow]")


@config.command()
def credentials():
    """Set up platform API keys."""
    console.print("[yellow]Not implemented yet. Coming in Phase 5.[/yellow]")


@config.command()
def sources():
    """Manage radar sources."""
    console.print("[yellow]Not implemented yet. Coming in Phase 5.[/yellow]")
