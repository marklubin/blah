"""Radar commands - config, pull, report, status."""

from __future__ import annotations

import logging
import os

import click
import httpx
from rich.console import Console
from rich.table import Table

from blah.config.settings import BlahSettings, get_blah_home
from blah.db.connection import get_db, init_db
from blah.db.repository import FeedItemRepo, ReportRepo, SourceRepo

console = Console()
logger = logging.getLogger(__name__)


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
    from blah.adapters.discord import DiscordAdapter
    from blah.adapters.hackernews import HackerNewsAdapter
    from blah.adapters.reddit import RedditAdapter
    from blah.adapters.twitter import TwitterAdapter

    adapters = {}

    # Bluesky
    bsky = settings.platforms.get("bluesky")
    if bsky and bsky.enabled and bsky.handle and bsky.app_password:
        adapter = BlueskyAdapter(handle=bsky.handle, app_password=bsky.app_password)
        adapter.authenticate()
        adapters["bluesky"] = adapter

    # Twitter/X — allow read-only mode with just twitterapi.io key
    twitter = settings.platforms.get("twitter")
    if twitter and twitter.enabled:
        has_oauth = bool(twitter.client_id and twitter.oauth2_token)
        has_read = bool(twitter.twitterapi_io_key)
        if has_oauth or has_read:
            adapter = TwitterAdapter(
                client_id=twitter.client_id or "",
                oauth2_token=twitter.oauth2_token or {},
                client_secret=twitter.client_secret,
                twitterapi_io_key=twitter.twitterapi_io_key,
                settings=settings,
            )
            if has_oauth:
                adapter.authenticate()
            else:
                # Read-only: set up HTTP client for twitterapi.io only
                adapter._http_client = httpx.Client(
                    base_url="https://api.twitterapi.io",
                    headers={"x-api-key": twitter.twitterapi_io_key},
                    timeout=30.0,
                )
            adapters["twitter"] = adapter

    # Reddit
    reddit = settings.platforms.get("reddit")
    if (
        reddit
        and reddit.enabled
        and reddit.reddit_client_id
        and reddit.reddit_client_secret
        and reddit.reddit_username
        and reddit.reddit_password
    ):
        adapter = RedditAdapter(
            client_id=reddit.reddit_client_id,
            client_secret=reddit.reddit_client_secret,
            username=reddit.reddit_username,
            password=reddit.reddit_password,
        )
        adapter.authenticate()
        adapters["reddit"] = adapter

    # Hacker News (public API, no credentials needed)
    hn = settings.platforms.get("hackernews")
    if hn and hn.enabled:
        adapter = HackerNewsAdapter()
        adapter.authenticate()
        adapters["hackernews"] = adapter

    # Discord (via MCP router)
    discord_cfg = settings.platforms.get("discord")
    if discord_cfg and discord_cfg.enabled:
        router_url = os.environ.get("ROUTER_URL") or f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8080')}"
        adapter = DiscordAdapter(router_url=router_url)
        try:
            adapter.authenticate()
            adapters["discord"] = adapter
        except Exception:
            logger.warning("Discord: router unreachable or token invalid", exc_info=True)

    # Telegram
    telegram_cfg = settings.platforms.get("telegram")
    if (
        telegram_cfg
        and telegram_cfg.enabled
        and telegram_cfg.telegram_api_id
        and telegram_cfg.telegram_api_hash
        and telegram_cfg.telegram_session_string
    ):
        from blah.adapters.telegram import TelegramAdapter

        tg_adapter = TelegramAdapter(
            api_id=telegram_cfg.telegram_api_id,
            api_hash=telegram_cfg.telegram_api_hash,
            session_string=telegram_cfg.telegram_session_string,
        )
        try:
            tg_adapter.authenticate()
            adapters["telegram"] = tg_adapter
        except Exception:
            logger.warning("Telegram: auth failed or session expired", exc_info=True)

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

        source_repo = SourceRepo(conn)
        sources = source_repo.list_all(enabled_only=True)
        if not sources:
            console.print("[yellow]No sources configured.[/yellow]")
            console.print("[dim]Use 'blah radar config' to add sources first.[/dim]")
            return

        # Check which sources have API adapters vs browser-only
        api_sources = [s for s in sources if s["platform"] in adapters]
        browser_sources = [s for s in sources if s["platform"] not in adapters]
        if not adapters and not browser_sources and not skip_poll:
            console.print("[red]No platform adapters configured.[/red]")
            console.print("[dim]Configure credentials in ~/.blah/config.yaml[/dim]")
            raise SystemExit(1)

        console.print("[bold]Running radar pipeline[/bold]")
        console.print(f"  Sources: {len(sources)}")
        if adapters:
            console.print(f"  API platforms: {', '.join(adapters.keys())}")
        if browser_sources:
            by_platform = {}
            for s in browser_sources:
                by_platform.setdefault(s["platform"], 0)
                by_platform[s["platform"]] += 1
            parts = [f"{count} {plat}" for plat, count in by_platform.items()]
            console.print(f"  Browser-only sources: {', '.join(parts)} (requires agent scraping)")
        console.print()

        pipeline = RadarPipeline(conn, settings, adapters)
        result = pipeline.run(skip_poll=skip_poll)

        # Track published piece metrics
        try:
            metrics = pipeline.track_published_pieces()
            if metrics["tracked"]:
                console.print(f"  [green]Tracked[/green] metrics for {metrics['tracked']} published pieces")
            if metrics["failed"]:
                console.print(f"  [yellow]Failed[/yellow] to track {metrics['failed']} pieces")
        except Exception:
            logger.exception("Failed to track published piece metrics")

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
            table.add_column("Notes")

            for s in sources:
                status = "[green]✓[/green]" if s.get("enabled", True) else "[red]✗[/red]"
                config = s.get("config", {})
                state = s.get("state", {})
                notes = ""
                if s["platform"] == "linkedin":
                    auth = state.get("auth_status", "unknown")
                    last_scrape = state.get("last_scrape", "never")
                    notes = f"auth: {auth}, scraped: {last_scrape}"
                elif s["platform"] == "discord":
                    channel_id = config.get("channel_id", "")
                    server_id = config.get("server_id", "")
                    if channel_id:
                        notes = f"channel: {channel_id[:8]}"
                        if server_id:
                            notes += f", server: {server_id[:8]}"
                table.add_row(
                    status,
                    s["platform"],
                    s["type"],
                    config.get("label") or "-",
                    s["id"][:8],
                    notes,
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


@radar.command("sync")
@click.argument("platform")
def sync_platform(platform: str):
    """Auto-populate sources from a platform. Currently supports: discord."""
    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        if platform != "discord":
            console.print(f"[red]Sync not supported for '{platform}'. Supported: discord[/red]")
            raise SystemExit(1)

        # Build Discord adapter
        discord_cfg = settings.platforms.get("discord")
        if not discord_cfg or not discord_cfg.enabled:
            console.print("[red]Discord is not enabled in config.yaml[/red]")
            raise SystemExit(1)

        from blah.adapters.discord import DiscordAdapter

        router_url = os.environ.get("ROUTER_URL") or f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8080')}"
        adapter = DiscordAdapter(router_url=router_url)
        try:
            adapter.authenticate()
        except Exception as exc:
            console.print(f"[red]Discord auth failed: {exc}[/red]")
            raise SystemExit(1)

        source_repo = SourceRepo(conn)

        # Get existing Discord sources to avoid duplicates
        existing_sources = source_repo.list_by_platform("discord")
        existing_channel_ids = set()
        for s in existing_sources:
            cid = s.get("config", {}).get("channel_id")
            if cid:
                existing_channel_ids.add(cid)

        guilds = adapter.get_guilds()
        if not guilds:
            console.print("[yellow]No Discord servers found.[/yellow]")
            return

        total_channels = 0
        created = 0
        already_existed = 0

        for guild in guilds:
            channels = adapter.get_guild_channels(guild["id"])
            for ch in channels:
                total_channels += 1
                if ch["id"] in existing_channel_ids:
                    already_existed += 1
                    continue

                label = f"#{ch['name']} ({guild['name']})"
                source_repo.create(
                    platform="discord",
                    source_type="channel",
                    config={
                        "channel_id": ch["id"],
                        "server_id": guild["id"],
                        "label": label,
                    },
                )
                created += 1

        console.print(f"[bold]Discord sync complete[/bold]")
        console.print(f"  Servers: {len(guilds)}")
        console.print(f"  Channels found: {total_channels}")
        console.print(f"  [green]Sources created: {created}[/green]")
        if already_existed:
            console.print(f"  [dim]Already existed: {already_existed}[/dim]")

    finally:
        conn.close()


@radar.command("ingest")
@click.argument("json_file", required=False, type=click.Path(exists=True))
@click.option("--source-id", default=None, help="Source ID to associate items with")
@click.option("--platform", default="linkedin", help="Platform name (default: linkedin)")
def ingest(json_file: str | None, source_id: str | None, platform: str):
    """Ingest scraped posts from a JSON file or stdin."""
    import json
    import sys

    settings = _require_init()
    conn = init_db(settings.db_path)

    try:
        # Read JSON from file or stdin
        if json_file:
            with open(json_file) as f:
                data = json.load(f)
        else:
            data = json.load(sys.stdin)

        if not isinstance(data, list):
            console.print("[red]Expected a JSON array of posts[/red]")
            raise SystemExit(1)

        # Find or create source
        source_repo = SourceRepo(conn)
        if not source_id:
            # Look for an existing feed source for this platform
            sources = source_repo.list_by_platform(platform)
            if sources:
                source_id = sources[0]["id"]
            else:
                # Create a default source
                source = source_repo.create(
                    platform=platform,
                    source_type="feed",
                    config={"label": f"{platform} feed (ingested)"},
                )
                source_id = source["id"]

        # Normalize items and add source_id
        items = []
        for post in data:
            items.append({
                "source_id": source_id,
                "platform": platform,
                "external_id": post.get("external_id", ""),
                "author": post.get("author", ""),
                "content": post.get("text") or post.get("content", ""),
                "url": post.get("url", ""),
            })

        feed_repo = FeedItemRepo(conn)
        result = feed_repo.create_batch(items)

        console.print(f"[green]Ingested[/green] {result['ingested']} items")
        if result["skipped"]:
            console.print(f"[yellow]Skipped[/yellow] {result['skipped']} (duplicates or missing ID)")
    finally:
        conn.close()


def _check_all_platforms(settings: BlahSettings, source_repo: SourceRepo) -> list[dict]:
    """Check each known platform's status, credentials, and connectivity."""
    from blah.adapters.bluesky import BlueskyAdapter
    from blah.adapters.discord import DiscordAdapter
    from blah.adapters.hackernews import HackerNewsAdapter
    from blah.adapters.reddit import RedditAdapter
    from blah.adapters.twitter import TwitterAdapter

    results = []

    # --- Browser (MCP Router) — check first, other platforms reference browser_ok ---
    router_url = os.environ.get("ROUTER_URL") or f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8080')}"
    browser_ok = False
    browser_connectivity = "[dim]--[/dim]"
    try:
        resp = httpx.get(f"{router_url}/notifications/summary", timeout=5.0)
        resp.raise_for_status()
        browser_ok = True
        browser_connectivity = "[green]OK[/green]"
    except Exception as exc:
        logger.warning("Browser/MCP router health check failed", exc_info=True)
        browser_connectivity = f"[red]FAIL ({exc})[/red]"
    results.append({
        "name": "browser (MCP)",
        "enabled": True,
        "credentials": "[green]✓[/green]",
        "connectivity": browser_connectivity,
        "sources": "-",
    })

    # --- Bluesky ---
    bsky = settings.platforms.get("bluesky")
    bsky_enabled = bool(bsky and bsky.enabled)
    bsky_has_creds = bool(bsky and bsky.handle and bsky.app_password)
    bsky_connectivity = "[dim]--[/dim]"
    if bsky_enabled and bsky_has_creds:
        try:
            adapter = BlueskyAdapter(handle=bsky.handle, app_password=bsky.app_password)
            adapter.authenticate()
            bsky_connectivity = "[green]OK[/green]"
        except Exception as exc:
            logger.warning("Bluesky health check failed", exc_info=True)
            bsky_connectivity = f"[red]FAIL ({exc})[/red]"
    results.append({
        "name": "bluesky",
        "enabled": bsky_enabled,
        "credentials": "[green]✓[/green]" if bsky_has_creds else "[red]✗[/red]",
        "connectivity": bsky_connectivity,
        "sources": len(source_repo.list_by_platform("bluesky")),
    })

    # --- Twitter ---
    twitter = settings.platforms.get("twitter")
    tw_enabled = bool(twitter and twitter.enabled)
    tw_has_oauth = bool(twitter and twitter.client_id and twitter.oauth2_token)
    tw_has_read = bool(twitter and twitter.twitterapi_io_key)
    tw_has_creds = tw_has_oauth or tw_has_read
    tw_connectivity = "[dim]--[/dim]"
    tw_mode = ""
    if tw_enabled and tw_has_creds:
        try:
            if tw_has_oauth:
                adapter = TwitterAdapter(
                    client_id=twitter.client_id,
                    oauth2_token=twitter.oauth2_token,
                    client_secret=twitter.client_secret,
                    twitterapi_io_key=twitter.twitterapi_io_key,
                    settings=settings,
                )
                adapter.authenticate()
                tw_connectivity = "[green]OK[/green]"
            else:
                # Read-only: verify twitterapi.io connectivity
                resp = httpx.get(
                    "https://api.twitterapi.io/twitter/user/info",
                    params={"userName": "x"},
                    headers={"x-api-key": twitter.twitterapi_io_key},
                    timeout=10.0,
                )
                resp.raise_for_status()
                tw_connectivity = "[green]OK (read-only)[/green]"
                tw_mode = " (read-only)"
        except Exception as exc:
            logger.warning("Twitter health check failed", exc_info=True)
            tw_connectivity = f"[red]FAIL ({exc})[/red]"
    cred_label = "[green]✓[/green]" if tw_has_creds else "[red]✗[/red]"
    if tw_has_creds and not tw_has_oauth:
        cred_label = "[green]✓[/green] (read-only)"
    results.append({
        "name": "twitter",
        "enabled": tw_enabled,
        "credentials": cred_label,
        "connectivity": tw_connectivity,
        "sources": len(source_repo.list_by_platform("twitter")),
    })

    # --- Reddit ---
    reddit = settings.platforms.get("reddit")
    rd_enabled = bool(reddit and reddit.enabled)
    rd_has_creds = bool(
        reddit
        and reddit.reddit_client_id
        and reddit.reddit_client_secret
        and reddit.reddit_username
        and reddit.reddit_password
    )
    rd_connectivity = "[dim]--[/dim]"
    if rd_enabled and rd_has_creds:
        try:
            adapter = RedditAdapter(
                client_id=reddit.reddit_client_id,
                client_secret=reddit.reddit_client_secret,
                username=reddit.reddit_username,
                password=reddit.reddit_password,
            )
            adapter.authenticate()
            rd_connectivity = "[green]OK[/green]"
        except Exception as exc:
            logger.warning("Reddit health check failed", exc_info=True)
            rd_connectivity = f"[red]FAIL ({exc})[/red]"
    rd_cred_label = "[green]✓[/green]" if rd_has_creds else "[yellow]browser[/yellow]"
    rd_auth_status = None
    if rd_enabled and not rd_has_creds and browser_ok:
        try:
            auth = _browser_auth_check(
                router_url,
                "https://www.reddit.com",
                logged_in=["Create Post", "karma"],
                logged_out=["Log In", "Sign Up"],
            )
            rd_auth_status = auth.get("auth_status")
            if rd_auth_status == "logged_in":
                rd_connectivity = "[green]OK (logged in)[/green]"
            elif rd_auth_status == "logged_out":
                rd_connectivity = "[red]NOT LOGGED IN[/red]"
            else:
                rd_connectivity = f"[yellow]{rd_auth_status} (browser)[/yellow]"
        except Exception as exc:
            logger.warning("Reddit browser auth check failed", exc_info=True)
            rd_connectivity = f"[red]FAIL ({exc})[/red]"
    elif rd_enabled and not rd_has_creds:
        rd_connectivity = "[red]FAIL (router)[/red]"
    results.append({
        "name": "reddit",
        "enabled": rd_enabled,
        "credentials": rd_cred_label,
        "connectivity": rd_connectivity,
        "sources": len(source_repo.list_by_platform("reddit")),
        "auth_status": rd_auth_status,
    })

    # --- Hacker News ---
    hn = settings.platforms.get("hackernews")
    hn_enabled = bool(hn and hn.enabled)
    hn_connectivity = "[dim]--[/dim]"
    if hn_enabled:
        try:
            adapter = HackerNewsAdapter()
            adapter.authenticate()
            hn_connectivity = "[green]OK[/green]"
        except Exception as exc:
            logger.warning("HackerNews health check failed", exc_info=True)
            hn_connectivity = f"[red]FAIL ({exc})[/red]"
    results.append({
        "name": "hackernews",
        "enabled": hn_enabled,
        "credentials": "[green]✓[/green]",  # no credentials needed
        "connectivity": hn_connectivity,
        "sources": len(source_repo.list_by_platform("hackernews")),
    })

    # --- Discord ---
    discord_cfg = settings.platforms.get("discord")
    dc_enabled = bool(discord_cfg and discord_cfg.enabled)
    dc_has_creds = bool(dc_enabled)  # just needs ROUTER_PORT env
    dc_connectivity = "[dim]--[/dim]"
    if dc_enabled:
        try:
            router_url = os.environ.get("ROUTER_URL") or f"http://127.0.0.1:{os.environ.get('ROUTER_PORT', '8080')}"
            adapter = DiscordAdapter(router_url=router_url)
            adapter.authenticate()
            dc_connectivity = "[green]OK[/green]"
        except Exception as exc:
            logger.warning("Discord health check failed", exc_info=True)
            dc_connectivity = f"[red]FAIL ({exc})[/red]"
    results.append({
        "name": "discord",
        "enabled": dc_enabled,
        "credentials": "[green]✓[/green]" if dc_has_creds else "[red]✗[/red]",
        "connectivity": dc_connectivity,
        "sources": len(source_repo.list_by_platform("discord")),
    })

    # --- LinkedIn ---
    li = settings.platforms.get("linkedin")
    li_enabled = bool(li and li.enabled)
    li_connectivity = "[dim]--[/dim]"
    li_auth_status = None
    if li_enabled and browser_ok:
        try:
            auth = _browser_auth_check(
                router_url,
                "https://www.linkedin.com/feed/",
                logged_in=["Start a post", "My Network", "Messaging"],
                logged_out=["Sign in", "Join now"],
            )
            li_auth_status = auth.get("auth_status")
            if li_auth_status == "logged_in":
                li_connectivity = "[green]OK (logged in)[/green]"
            elif li_auth_status == "logged_out":
                li_connectivity = "[red]NOT LOGGED IN[/red]"
            else:
                li_connectivity = f"[yellow]{li_auth_status}[/yellow]"
        except Exception as exc:
            logger.warning("LinkedIn browser auth check failed", exc_info=True)
            li_connectivity = f"[red]FAIL ({exc})[/red]"
    elif li_enabled:
        li_connectivity = "[red]FAIL (router)[/red]"
    results.append({
        "name": "linkedin",
        "enabled": li_enabled,
        "credentials": "[yellow]browser[/yellow]",
        "connectivity": li_connectivity,
        "sources": len(source_repo.list_by_platform("linkedin")),
        "auth_status": li_auth_status,
    })

    # --- Telegram ---
    telegram_cfg = settings.platforms.get("telegram")
    tg_enabled = bool(telegram_cfg and telegram_cfg.enabled)
    tg_has_creds = bool(
        telegram_cfg
        and telegram_cfg.telegram_api_id
        and telegram_cfg.telegram_api_hash
        and telegram_cfg.telegram_session_string
    )
    tg_connectivity = "[dim]--[/dim]"
    if tg_enabled and tg_has_creds:
        try:
            from blah.adapters.telegram import TelegramAdapter

            tg_adapter = TelegramAdapter(
                api_id=telegram_cfg.telegram_api_id,
                api_hash=telegram_cfg.telegram_api_hash,
                session_string=telegram_cfg.telegram_session_string,
            )
            tg_adapter.authenticate()
            tg_connectivity = "[green]OK[/green]"
        except Exception as exc:
            logger.warning("Telegram health check failed", exc_info=True)
            tg_connectivity = f"[red]FAIL ({exc})[/red]"
    results.append({
        "name": "telegram",
        "enabled": tg_enabled,
        "credentials": "[green]✓[/green]" if tg_has_creds else "[red]✗[/red]",
        "connectivity": tg_connectivity,
        "sources": len(source_repo.list_by_platform("telegram")),
    })

    return results


def _browser_auth_check(router_url: str, url: str, logged_in: list[str], logged_out: list[str]) -> dict:
    """Call the MCP router's browser auth-check endpoint."""
    resp = httpx.get(
        f"{router_url}/browser/auth-check",
        params={
            "url": url,
            "logged_in": ",".join(logged_in),
            "logged_out": ",".join(logged_out),
        },
        timeout=25.0,
    )
    resp.raise_for_status()
    return resp.json()


def _fmt_bool(value: bool) -> str:
    """Format a boolean as a colored check/cross."""
    return "[green]✓[/green]" if value else "[red]✗[/red]"


@radar.command("health")
def radar_health():
    """Check platform connectivity and configuration status."""
    settings = _require_init()
    conn = get_db(settings.db_path)

    try:
        source_repo = SourceRepo(conn)

        console.print("[bold]Radar Health Check[/bold]\n")

        table = Table(show_header=True, header_style="bold")
        table.add_column("Platform")
        table.add_column("Enabled")
        table.add_column("Credentials")
        table.add_column("Connectivity")
        table.add_column("Sources")

        platforms = _check_all_platforms(settings, source_repo)

        for p in platforms:
            sources_str = str(p["sources"]) if isinstance(p["sources"], int) else p["sources"]
            table.add_row(
                p["name"],
                _fmt_bool(p["enabled"]),
                p["credentials"],
                p["connectivity"],
                sources_str,
            )

        console.print(table)

        # Auto-create LinkedIn feed source if logged in and no sources exist
        li_result = next((p for p in platforms if p["name"] == "linkedin"), None)
        if (
            li_result
            and li_result["enabled"]
            and li_result.get("auth_status") == "logged_in"
            and li_result["sources"] == 0
        ):
            from blah.db.connection import init_db as _init_db
            conn.close()
            conn = _init_db(settings.db_path)
            source_repo = SourceRepo(conn)
            source_repo.create(
                platform="linkedin",
                source_type="feed",
                config={"label": "LinkedIn home feed"},
            )
            console.print("\n[green]Auto-created[/green] LinkedIn home feed source.")
    finally:
        conn.close()
