"""Blah CLI entry point."""

from __future__ import annotations

import os

import click
from rich.console import Console
from rich.table import Table

from blah import __version__
from blah.cli.commands.config import config
from blah.cli.commands.context import context
from blah.cli.commands.radar import radar
from blah.cli.commands.rant import rant
from blah.config.settings import BlahSettings, get_blah_home
from blah.db.connection import init_db

console = Console()

DEFAULT_CONTEXT_MD = """# Context

## Voice
<!-- Describe your voice/tone here -->

## Topics
<!-- What topics do you care about? -->

## People
<!-- Accounts to follow or reference -->

## Platforms
<!-- Which platforms to use -->

## Notes
<!-- Anything else agents should know -->
"""

DEFAULT_CONFIG_YAML = """# Blah configuration

models:
  triage:
    provider: anthropic
    model: claude-sonnet-4-5
  research:
    provider: anthropic
    model: claude-sonnet-4-5
  conversation:
    provider: anthropic
    model: claude-sonnet-4-5

context:
  path: context.md
  max_tokens: 2000

platforms:
  bluesky:
    enabled: false
    # handle: your.handle.bsky.social
    # app_password: xxxx-xxxx-xxxx-xxxx
  twitter:
    enabled: false
    # consumer_key: ...
    # consumer_secret: ...
    # access_token: ...
    # access_token_secret: ...
"""


@click.group()
@click.version_option(version=__version__, prog_name="blah")
def cli():
    """Blah - Social engagement agent. Makes noise so you don't have to."""
    # Set up logging if home exists
    home = get_blah_home()
    if home.exists():
        from blah.logging import setup_logging
        setup_logging(home)


@cli.command()
def init():
    """Initialize Blah home directory and database."""
    home = get_blah_home()

    if home.exists():
        console.print(f"[yellow]Blah home already exists at {home}[/yellow]")
        console.print("Ensuring database schema is up to date...")
        init_db(home / "blah.db")
        console.print("[green]Done.[/green]")
        return

    home.mkdir(parents=True)
    (home / "resources").mkdir()

    # Write default config
    (home / "config.yaml").write_text(DEFAULT_CONFIG_YAML)
    console.print(f"  Created {home / 'config.yaml'}")

    # Write default context
    (home / "context.md").write_text(DEFAULT_CONTEXT_MD)
    console.print(f"  Created {home / 'context.md'}")

    # Initialize database
    init_db(home / "blah.db")
    console.print(f"  Created {home / 'blah.db'}")

    console.print(f"\n[green]Blah initialized at {home}[/green]")
    console.print("\nNext steps:")
    console.print("  1. Edit config.yaml to add platform credentials")
    console.print("  2. Edit context.md to describe your voice and interests")
    console.print("  3. Run [bold]blah rant create[/bold] to create your first rant")


@cli.command()
def status():
    """Show system status."""
    home = get_blah_home()

    if not home.exists():
        console.print("[red]Blah not initialized. Run 'blah init' first.[/red]")
        raise SystemExit(1)

    settings = BlahSettings.load()

    table = Table(title="Blah Status", show_header=False)
    table.add_column("Key", style="bold")
    table.add_column("Value")

    table.add_row("BLAH_HOME", str(home))
    table.add_row("Version", __version__)

    # DB info
    db_path = settings.db_path
    if db_path.exists():
        size_kb = db_path.stat().st_size / 1024
        table.add_row("Database", f"{db_path} ({size_kb:.1f} KB)")
    else:
        table.add_row("Database", "[red]Not found[/red]")

    # Config
    if settings.config_path.exists():
        table.add_row("Config", str(settings.config_path))
    else:
        table.add_row("Config", "[red]Not found[/red]")

    # Context
    if settings.context_path.exists():
        ctx_size = settings.context_path.stat().st_size
        table.add_row("Context", f"{settings.context_path} ({ctx_size} bytes)")
    else:
        table.add_row("Context", "[red]Not found[/red]")

    # Platforms
    enabled_platforms = [
        name for name, creds in settings.platforms.items()
        if isinstance(creds, dict) and creds.get("enabled")
        or hasattr(creds, "enabled") and creds.enabled
    ]
    platforms_str = ", ".join(enabled_platforms) if enabled_platforms else "None configured"
    table.add_row("Platforms", platforms_str)

    # Counts from DB
    if db_path.exists():
        from blah.db.connection import get_db
        from blah.db.repository import RantRepo, ReportRepo, SourceRepo

        conn = get_db(db_path)
        try:
            table.add_row("Rants", str(RantRepo(conn).count()))
            table.add_row("Sources", str(SourceRepo(conn).count()))
            table.add_row("Reports", str(ReportRepo(conn).count()))
        finally:
            conn.close()

    # API key
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    table.add_row("Anthropic API Key", "[green]Set[/green]" if has_key else "[red]Not set[/red]")

    console.print(table)


cli.add_command(rant)
cli.add_command(radar)
cli.add_command(context)
cli.add_command(config)
