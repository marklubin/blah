"""Radar commands - config, pull, report, status."""

from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table

from blah.config.settings import BlahSettings, get_blah_home
from blah.db.connection import get_db, init_db
from blah.db.repository import FeedItemRepo, ReportRepo, SourceRepo

console = Console()


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
    if twitter and twitter.enabled and twitter.client_id and twitter.oauth2_token:
        adapter = TwitterAdapter(
            client_id=twitter.client_id,
            oauth2_token=twitter.oauth2_token,
            client_secret=twitter.client_secret,
            twitterapi_io_key=twitter.twitterapi_io_key,
            settings=settings,
        )
        adapter.authenticate()
        adapters["twitter"] = adapter

    return adapters


@click.group()
def radar():
    """Monitor feeds and review reports."""


@radar.command("config")
def radar_config():
    """Configure radar sources via chat."""
    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        from blah.agents.radar_config import RadarConfigAgent
        from blah.llm.client import LLMClient

        adapters = _get_adapters(settings)
        if not adapters:
            console.print("[yellow]Warning: No platform adapters configured.[/yellow]")
            console.print("[dim]Configure credentials in ~/.blah/config.yaml first.[/dim]")
            console.print("[dim]You can still configure sources, but pull won't work.[/dim]\n")

        llm = LLMClient(model=settings.models.conversation.model)
        agent = RadarConfigAgent(llm, conn, settings, adapters)
        agent.run_chat("radar:config")
    finally:
        conn.close()


@radar.command()
@click.option("--skip-research", is_flag=True, help="Skip research phase (triage only)")
@click.option("--skip-poll", is_flag=True, help="Skip polling, use existing raw items")
def pull(skip_research: bool, skip_poll: bool):
    """Run the radar pipeline: poll sources, triage, research, generate report."""
    from blah.services.pipeline import RadarPipeline

    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        adapters = _get_adapters(settings)
        if not adapters:
            console.print("[red]No platform adapters configured.[/red]")
            console.print("[dim]Configure credentials in ~/.blah/config.yaml[/dim]")
            raise SystemExit(1)

        source_repo = SourceRepo(conn)
        sources = source_repo.list_all(enabled_only=True)
        if not sources:
            console.print("[yellow]No sources configured.[/yellow]")
            console.print("[dim]Use 'blah radar config' to add sources first.[/dim]")
            return

        console.print("[bold]Running radar pipeline[/bold]")
        console.print(f"  Sources: {len(sources)}")
        console.print(f"  Platforms: {', '.join(adapters.keys())}\n")

        pipeline = RadarPipeline(conn, settings, adapters)
        result = pipeline.run(skip_poll=skip_poll)

        # Display results
        if result.items_fetched:
            n = result.items_fetched
            s = len(result.sources_polled)
            console.print(f"  [green]Fetched[/green] {n} items from {s} sources")

        if result.items_triaged:
            passed, disc = result.items_passed, result.items_discarded
            console.print(f"  [green]Triaged[/green] {passed} passed, {disc} discarded")

        if result.items_researched:
            console.print(f"  [green]Researched[/green] {result.items_researched} items")
            if result.research_failed:
                console.print(f"  [yellow]Research failed[/yellow] {result.research_failed} items")

        if result.report_id:
            console.print(f"\n  [bold green]Report generated[/bold green]: {result.report_id[:8]}")
            console.print(f"  Items in report: {result.report_items}")
            console.print(f"\n[dim]Review with: blah radar report {result.report_id[:8]}[/dim]")
        else:
            console.print("\n[dim]No report generated (no items passed triage).[/dim]")

    finally:
        conn.close()


@radar.command()
@click.argument("report_id", required=False)
def report(report_id: str | None):
    """Review a radar report via chat."""
    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        from blah.agents.radar_report import RadarReportAgent
        from blah.llm.client import LLMClient

        report_repo = ReportRepo(conn)

        # Find the report
        if report_id:
            # Try to find by prefix
            all_reports = report_repo.list_all()
            target = None
            for r in all_reports:
                if r["id"].startswith(report_id):
                    target = r
                    break
            if not target:
                console.print(f"[red]Report {report_id} not found.[/red]")
                raise SystemExit(1)
            report_id = target["id"]
        else:
            # Get latest pending report
            target = report_repo.get_latest_pending()
            if not target:
                console.print("[yellow]No pending reports.[/yellow]")
                console.print("[dim]Run 'blah radar pull' to generate a report.[/dim]")
                return
            report_id = target["id"]

        adapters = _get_adapters(settings)
        if not adapters:
            console.print("[yellow]Warning: No platform adapters configured.[/yellow]")
            console.print("[dim]You can review but won't be able to engage.[/dim]\n")

        console.print(f"[bold]Reviewing report {report_id[:8]}[/bold]\n")

        llm = LLMClient(model=settings.models.conversation.model)
        agent = RadarReportAgent(llm, conn, settings, adapters, report_id)
        agent.run_chat(f"radar:report:{report_id}")
    finally:
        conn.close()


@radar.command("status")
def radar_status():
    """Show radar configuration status."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        source_repo = SourceRepo(conn)
        report_repo = ReportRepo(conn)
        feed_repo = FeedItemRepo(conn)

        sources = source_repo.list_all()
        enabled = [s for s in sources if s.get("enabled", True)]

        console.print("[bold]Radar Status[/bold]\n")

        # Sources
        console.print(f"[bold]Sources:[/bold] {len(enabled)} enabled / {len(sources)} total")
        if sources:
            table = Table(show_header=True, header_style="bold")
            table.add_column("Status")
            table.add_column("Platform")
            table.add_column("Type")
            table.add_column("Label")
            table.add_column("ID")

            for s in sources:
                status = "[green]✓[/green]" if s.get("enabled", True) else "[red]✗[/red]"
                config = s.get("config", {})
                table.add_row(
                    status,
                    s["platform"],
                    s["type"],
                    config.get("label") or "-",
                    s["id"][:8],
                )
            console.print(table)
        console.print()

        # Feed items
        raw_items = feed_repo.list_by_status("raw")
        triaged_items = feed_repo.list_by_status("triaged")
        researched_items = feed_repo.list_by_status("researched")
        console.print("[bold]Feed Items:[/bold]")
        console.print(f"  Raw: {len(raw_items)}")
        console.print(f"  Triaged: {len(triaged_items)}")
        console.print(f"  Researched: {len(researched_items)}")
        console.print()

        # Reports
        reports = report_repo.list_all()
        pending = [r for r in reports if r.get("status") == "pending"]
        console.print(f"[bold]Reports:[/bold] {len(pending)} pending / {len(reports)} total")

        if pending:
            console.print("\n[bold]Pending Reports:[/bold]")
            for r in pending[:5]:
                console.print(f"  {r['id'][:8]} — {r.get('created_at', 'unknown')}")

            if pending:
                console.print("\n[dim]Review with: blah radar report[/dim]")

    finally:
        conn.close()


@radar.command("sources")
def list_sources():
    """List all configured sources."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        source_repo = SourceRepo(conn)
        sources = source_repo.list_all()

        if not sources:
            console.print("[dim]No sources configured.[/dim]")
            console.print("[dim]Use 'blah radar config' to add sources.[/dim]")
            return

        table = Table(title="Radar Sources")
        table.add_column("ID", style="bold")
        table.add_column("Platform")
        table.add_column("Type")
        table.add_column("Label")
        table.add_column("Status")

        for s in sources:
            status = "[green]enabled[/green]" if s.get("enabled", True) else "[red]disabled[/red]"
            config = s.get("config", {})
            table.add_row(
                s["id"][:8],
                s["platform"],
                s["type"],
                config.get("label") or "-",
                status,
            )

        console.print(table)
    finally:
        conn.close()


@radar.command("reports")
@click.option("--all", "show_all", is_flag=True, help="Show all reports, not just pending")
def list_reports(show_all: bool):
    """List radar reports."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        from blah.db.repository import ReportItemRepo

        report_repo = ReportRepo(conn)
        report_item_repo = ReportItemRepo(conn)

        reports = report_repo.list_all()
        if not show_all:
            reports = [r for r in reports if r.get("status") == "pending"]

        if not reports:
            msg = "No reports." if show_all else "No pending reports."
            console.print(f"[dim]{msg}[/dim]")
            console.print("[dim]Run 'blah radar pull' to generate a report.[/dim]")
            return

        table = Table(title="Radar Reports")
        table.add_column("ID", style="bold")
        table.add_column("Created")
        table.add_column("Status")
        table.add_column("Items")

        for r in reports:
            item_count = report_item_repo.count_by_report(r["id"])
            table.add_row(
                r["id"][:8],
                r.get("created_at", "unknown"),
                r.get("status", "pending"),
                str(item_count),
            )

        console.print(table)
    finally:
        conn.close()
