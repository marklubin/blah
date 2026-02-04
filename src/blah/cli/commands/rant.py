"""Rant commands - create, list, show, chat, publish, delete."""

from __future__ import annotations

import click
from rich.console import Console

console = Console()


@click.group()
def rant():
    """Create and manage rants."""


@rant.command()
def create():
    """Start a new rant via chat."""
    console.print("[yellow]Not implemented yet. Coming in Phase 2.[/yellow]")


@rant.command("list")
def list_rants():
    """List all rants."""
    console.print("[yellow]Not implemented yet. Coming in Phase 2.[/yellow]")


@rant.command()
@click.argument("rant_id")
def show(rant_id: str):
    """Show rant details."""
    console.print("[yellow]Not implemented yet. Coming in Phase 2.[/yellow]")


@rant.command()
@click.argument("rant_id")
def chat(rant_id: str):
    """Resume a rant conversation."""
    console.print("[yellow]Not implemented yet. Coming in Phase 2.[/yellow]")


@rant.command()
@click.argument("rant_id")
def publish(rant_id: str):
    """Publish approved pieces for a rant."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")


@rant.command()
@click.argument("rant_id")
def delete(rant_id: str):
    """Delete a rant."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")


@rant.command()
def failures():
    """List failed pieces."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")


@rant.command()
@click.argument("piece_id")
def retry(piece_id: str):
    """Retry a failed piece."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")


@rant.command("mark-posted")
@click.argument("piece_id")
@click.argument("url")
def mark_posted(piece_id: str, url: str):
    """Mark a piece as manually posted."""
    console.print("[yellow]Not implemented yet. Coming in Phase 3.[/yellow]")
