"""Rant commands - create, list, show, chat, publish, delete."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from blah.config.settings import BlahSettings, get_blah_home
from blah.db.connection import get_db, init_db
from blah.db.repository import PieceRepo, RantRepo

console = Console()


def _require_init() -> BlahSettings:
    """Load settings, abort if not initialized."""
    home = get_blah_home()
    if not home.exists():
        console.print("[red]Blah not initialized. Run 'blah init' first.[/red]")
        raise SystemExit(1)
    return BlahSettings.load()


@click.group()
def rant():
    """Create and manage rants."""


@rant.command()
def create():
    """Start a new rant via chat."""
    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        from blah.agents.rant import RantAgent
        from blah.llm.client import LLMClient

        rant_repo = RantRepo(conn)
        new_rant = rant_repo.create()
        rant_id = new_rant["id"]

        console.print(f"[green]Created rant {rant_id}[/green]\n")

        llm = LLMClient(model=settings.models.conversation.model)
        agent = RantAgent(llm, conn, settings, rant_id)
        agent.run_chat(f"rant:{rant_id}")
    finally:
        conn.close()


@rant.command("list")
def list_rants():
    """List all rants."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        rant_repo = RantRepo(conn)
        piece_repo = PieceRepo(conn)
        rants = rant_repo.list_all()

        if not rants:
            console.print("[dim]No rants yet. Run 'blah rant create' to start one.[/dim]")
            return

        table = Table(title="Rants")
        table.add_column("ID", style="bold")
        table.add_column("Title")
        table.add_column("Status")
        table.add_column("Pieces")
        table.add_column("Created")

        for r in rants:
            pieces = piece_repo.list_by_rant(r["id"])
            piece_summary = ", ".join(
                f"{p['platform']}({p['status']})" for p in pieces
            ) if pieces else "-"
            table.add_row(
                r["id"],
                r["title"] or "(untitled)",
                r["status"],
                piece_summary,
                r["created_at"] or "",
            )

        console.print(table)
    finally:
        conn.close()


@rant.command()
@click.argument("rant_id")
def show(rant_id: str):
    """Show rant details."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        rant_repo = RantRepo(conn)
        piece_repo = PieceRepo(conn)

        r = rant_repo.get(rant_id)
        if r is None:
            console.print(f"[red]Rant {rant_id} not found.[/red]")
            raise SystemExit(1)

        console.print(f"\n[bold]Rant {r['id']}[/bold]")
        console.print(f"  Title:   {r['title'] or '(untitled)'}")
        console.print(f"  Summary: {r['summary'] or '(none)'}")
        console.print(f"  Status:  {r['status']}")
        console.print(f"  Created: {r['created_at']}")

        pieces = piece_repo.list_by_rant(rant_id)
        if pieces:
            console.print(f"\n[bold]Pieces ({len(pieces)}):[/bold]")
            for p in pieces:
                status_color = {
                    "draft": "yellow",
                    "approved": "green",
                    "published": "blue",
                    "failed": "red",
                }.get(p["status"], "white")
                platform = p["platform"]
                console.print(
                    f"\n  [{status_color}]{platform}[/{status_color}] "
                    f"({p['status']}) — ID: {p['id']}"
                )
                console.print(f"  {p['content']}")
                if p.get("external_url"):
                    console.print(f"  URL: {p['external_url']}")
                if p.get("error"):
                    console.print(f"  [red]Error: {p['error']}[/red]")
        else:
            console.print("\n  No pieces yet.")
    finally:
        conn.close()


@rant.command()
@click.argument("rant_id")
def chat(rant_id: str):
    """Resume a rant conversation."""
    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        from blah.agents.rant import RantAgent
        from blah.llm.client import LLMClient

        rant_repo = RantRepo(conn)
        r = rant_repo.get(rant_id)
        if r is None:
            console.print(f"[red]Rant {rant_id} not found.[/red]")
            raise SystemExit(1)

        console.print(f"[bold]Rant: {r['title'] or '(untitled)'}[/bold] ({r['status']})\n")

        llm = LLMClient(model=settings.models.conversation.model)
        agent = RantAgent(llm, conn, settings, rant_id)
        agent.run_chat(f"rant:{rant_id}")
    finally:
        conn.close()


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
