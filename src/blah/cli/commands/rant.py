"""Rant commands - create, list, show, chat, publish, delete."""

from __future__ import annotations

from datetime import datetime

import click
from rich.console import Console
from rich.table import Table

from blah.config.settings import BlahSettings, get_blah_home
from blah.db.connection import get_db, init_db
from blah.db.repository import PieceRepo, RantRepo

console = Console()


def _truncate_error(error: str | None, max_len: int = 60) -> str:
    """Truncate error message for table display."""
    if not error:
        return ""
    return error[:max_len] + "..." if len(error) > max_len else error


def _require_init() -> BlahSettings:
    """Load settings, abort if not initialized."""
    home = get_blah_home()
    if not home.exists():
        console.print("[red]Blah not initialized. Run 'blah init' first.[/red]")
        raise SystemExit(1)
    return BlahSettings.load()


def _get_adapters(settings: BlahSettings) -> dict:
    """Build platform adapters from settings."""
    from blah.adapters.bluesky import BlueskyAdapter
    from blah.adapters.twitter import TwitterAdapter

    adapters = {}

    # Bluesky
    bsky = settings.platforms.get("bluesky")
    if bsky and bsky.enabled and bsky.handle and bsky.app_password:
        adapter = BlueskyAdapter(handle=bsky.handle, app_password=bsky.app_password)
        adapter.authenticate()
        adapters["bluesky"] = adapter

    # Twitter/X
    twitter = settings.platforms.get("twitter")
    if (
        twitter
        and twitter.enabled
        and twitter.consumer_key
        and twitter.consumer_secret
        and twitter.access_token
        and twitter.access_token_secret
    ):
        adapter = TwitterAdapter(
            consumer_key=twitter.consumer_key,
            consumer_secret=twitter.consumer_secret,
            access_token=twitter.access_token,
            access_token_secret=twitter.access_token_secret,
            twitterapi_io_key=getattr(twitter, "twitterapi_io_key", None),
        )
        adapter.authenticate()
        adapters["twitter"] = adapter

    return adapters


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
    from blah.services.publishing import PublishService

    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        rant_repo = RantRepo(conn)
        r = rant_repo.get(rant_id)
        if r is None:
            console.print(f"[red]Rant {rant_id} not found.[/red]")
            raise SystemExit(1)

        pieces = PieceRepo(conn).list_by_rant(rant_id)
        approved = [p for p in pieces if p["status"] == "approved"]
        if not approved:
            console.print(f"[yellow]No approved pieces for rant {rant_id}.[/yellow]")
            console.print("[dim]Use 'blah rant chat' to finalize the rant first.[/dim]")
            return

        console.print(f"Publishing {len(approved)} piece(s) for rant {rant_id}...\n")

        adapters = _get_adapters(settings)
        if not adapters:
            console.print("[red]No platform adapters configured.[/red]")
            console.print("[dim]Configure credentials in ~/.blah/config.yaml[/dim]")
            raise SystemExit(1)

        service = PublishService(conn, adapters)
        result = service.publish_rant(rant_id)

        for p in result.published:
            platform = p["platform"]
            console.print(f"  [green]Published[/green] {platform}: {p.get('external_url', '')}")

        for p in result.failed:
            platform = p["platform"]
            console.print(f"  [red]Failed[/red] {platform}: {p.get('error', 'unknown error')}")

        for p in result.skipped:
            platform = p["platform"]
            console.print(f"  [yellow]Skipped[/yellow] {platform}: no adapter configured")

        console.print(f"\n{result.summary}")
    finally:
        conn.close()


@rant.command()
@click.argument("rant_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete(rant_id: str, yes: bool):
    """Delete a rant and all its pieces."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        rant_repo = RantRepo(conn)
        r = rant_repo.get(rant_id)
        if r is None:
            console.print(f"[red]Rant {rant_id} not found.[/red]")
            raise SystemExit(1)

        if not yes:
            title = r["title"] or "(untitled)"
            click.confirm(f"Delete rant '{title}' ({rant_id})?", abort=True)

        # Delete pieces first (foreign key)
        conn.execute("DELETE FROM pieces WHERE rant_id = ?", (rant_id,))
        conn.execute("DELETE FROM rant_resources WHERE rant_id = ?", (rant_id,))
        rant_repo.delete(rant_id)
        console.print(f"[green]Deleted rant {rant_id}.[/green]")
    finally:
        conn.close()


@rant.command()
def failures():
    """List failed pieces across all rants."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        piece_repo = PieceRepo(conn)
        failed = piece_repo.list_failed()

        if not failed:
            console.print("[dim]No failed pieces.[/dim]")
            return

        table = Table(title="Failed Pieces")
        table.add_column("Piece ID", style="bold")
        table.add_column("Rant ID")
        table.add_column("Platform")
        table.add_column("Retries")
        table.add_column("Error")

        for p in failed:
            platform = p["platform"]
            table.add_row(
                p["id"],
                p["rant_id"],
                platform,
                str(p.get("retry_count", 0) or 0),
                _truncate_error(p.get("error")),
            )

        console.print(table)
    finally:
        conn.close()


@rant.command()
@click.argument("piece_id")
def retry(piece_id: str):
    """Retry a failed piece."""
    from blah.services.publishing import PublishService

    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        piece_repo = PieceRepo(conn)
        piece = piece_repo.get(piece_id)
        if piece is None:
            console.print(f"[red]Piece {piece_id} not found.[/red]")
            raise SystemExit(1)

        if piece["status"] != "failed":
            status = piece["status"]
            console.print(f"[yellow]Piece {piece_id} is '{status}', not 'failed'.[/yellow]")
            return

        adapters = _get_adapters(settings)
        if not adapters:
            console.print("[red]No platform adapters configured.[/red]")
            raise SystemExit(1)

        console.print(f"Retrying piece {piece_id} ({piece['platform']})...")

        service = PublishService(conn, adapters)
        result = service.publish_piece(piece_id)

        if result.published:
            p = result.published[0]
            console.print(f"[green]Published[/green]: {p.get('external_url', '')}")
        elif result.failed:
            p = result.failed[0]
            console.print(f"[red]Failed again[/red]: {p.get('error', 'unknown')}")
    finally:
        conn.close()


@rant.command("mark-posted")
@click.argument("piece_id")
@click.argument("url")
def mark_posted(piece_id: str, url: str):
    """Mark a piece as manually posted with its URL."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        piece_repo = PieceRepo(conn)
        piece = piece_repo.get(piece_id)
        if piece is None:
            console.print(f"[red]Piece {piece_id} not found.[/red]")
            raise SystemExit(1)

        piece_repo.update(
            piece_id,
            status="published",
            external_url=url,
            published_at=datetime.now().isoformat(),
        )
        console.print(f"[green]Marked piece {piece_id} as posted.[/green]")
    finally:
        conn.close()
