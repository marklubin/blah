"""Context commands - show, edit."""

from __future__ import annotations

import os
import subprocess

import click
from rich.console import Console
from rich.markdown import Markdown

from blah.config.settings import BlahSettings, get_blah_home

console = Console()


def _require_init() -> BlahSettings:
    """Load settings, abort if not initialized."""
    home = get_blah_home()
    if not home.exists():
        console.print("[red]Blah not initialized. Run 'blah init' first.[/red]")
        raise SystemExit(1)
    return BlahSettings.load()


@click.group()
def context():
    """View and edit shared context."""


@context.command()
def show():
    """Display context.md contents."""
    settings = _require_init()
    ctx_path = settings.context_path

    if not ctx_path.exists():
        console.print("[yellow]No context.md found.[/yellow]")
        console.print(f"[dim]Expected at: {ctx_path}[/dim]")
        return

    content = ctx_path.read_text()
    if not content.strip():
        console.print("[dim]context.md is empty.[/dim]")
        return

    console.print(Markdown(content))


@context.command()
def edit():
    """Open context.md in $EDITOR."""
    settings = _require_init()
    ctx_path = settings.context_path

    if not ctx_path.exists():
        ctx_path.write_text("# Context\n\n## Voice\n\n## Interests\n\n## Notes\n")

    editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))

    try:
        subprocess.run([editor, str(ctx_path)], check=True)
        console.print("[green]Context updated.[/green]")
    except FileNotFoundError:
        console.print(f"[red]Editor '{editor}' not found.[/red]")
        console.print("[dim]Set $EDITOR to your preferred editor.[/dim]")
        raise SystemExit(1) from None
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Editor exited with error: {e.returncode}[/red]")
        raise SystemExit(1) from None
