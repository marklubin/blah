"""Context commands - show, edit."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def context():
    """View and edit shared context."""


@context.command()
def show():
    """Display context.md contents."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")


@context.command()
def edit():
    """Open context.md in $EDITOR."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")
