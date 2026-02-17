"""Config commands - show, edit, models, credentials, sources, auth."""

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


@config.group()
def auth():
    """Authenticate with platforms."""


@auth.command("twitter")
def auth_twitter():
    """Authenticate with Twitter/X via OAuth 2.0 PKCE."""
    import http.server
    import urllib.parse
    import webbrowser

    from xdk import Client as XClient

    from blah.config.settings import BlahSettings, get_blah_home

    home = get_blah_home()
    if not home.exists():
        console.print("[red]Blah not initialized. Run 'blah init' first.[/red]")
        raise SystemExit(1)

    settings = BlahSettings.load()

    console.print("[bold]Twitter/X OAuth 2.0 Setup[/bold]\n")

    # Read existing credentials from config
    twitter = settings.platforms.get("twitter")
    existing_client_id = twitter.client_id if twitter else None
    existing_client_secret = twitter.client_secret if twitter else None
    existing_io_key = twitter.twitterapi_io_key if twitter else None

    # Prompt only if not already configured
    if existing_client_id:
        console.print(f"Using client_id from config: {existing_client_id[:8]}...")
        client_id = existing_client_id
    else:
        client_id = click.prompt("Enter your X app Client ID")

    if existing_client_secret:
        console.print(f"Using client_secret from config: {existing_client_secret[:8]}...")
        client_secret = existing_client_secret
    else:
        client_secret = click.prompt(
            "Enter your X app Client Secret (optional)",
            default="",
        ) or None

    if existing_io_key:
        twitterapi_io_key = existing_io_key
    else:
        twitterapi_io_key = click.prompt(
            "Enter your twitterapi.io key (optional, for cheaper reads)",
            default="",
        ) or None

    redirect_uri = "http://127.0.0.1:8888/callback"
    scopes = "tweet.read tweet.write follows.read follows.write users.read offline.access"

    # Create xdk client for OAuth flow
    xdk_kwargs = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
    }
    if client_secret:
        xdk_kwargs["client_secret"] = client_secret
    client = XClient(**xdk_kwargs)

    # Generate auth URL
    auth_url = client.get_authorization_url()
    console.print("\nOpening browser for authorization...\n")
    console.print(f"If the browser doesn't open, visit:\n[link]{auth_url}[/link]\n")
    webbrowser.open(auth_url)

    # Spin up localhost callback handler
    class _OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
        code = None

        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            _OAuthCallbackHandler.code = params.get("code", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Authorization complete. You can close this tab.")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 8888), _OAuthCallbackHandler)
    server.timeout = 120

    console.print("Waiting for callback (120s timeout)...")
    server.handle_request()

    code = _OAuthCallbackHandler.code
    if not code:
        console.print("[red]No authorization code received. Timed out or denied.[/red]")
        raise SystemExit(1)

    # Exchange code for token
    console.print("Exchanging code for token...")
    token = client.exchange_code(code)

    # Verify by fetching user info
    me = client.users.get_me()
    if me:
        data = me.data if hasattr(me, "data") else me
        if isinstance(data, dict):
            username = data.get("username")
        else:
            username = getattr(data, "username", None)
        if username:
            console.print(f"\n[green]Authenticated as @{username}[/green]")
        else:
            console.print("[yellow]Token obtained but could not read username.[/yellow]")
    else:
        console.print("[yellow]Token obtained but could not verify user.[/yellow]")

    # Save to settings
    if "twitter" not in settings.platforms:
        from blah.config.settings import PlatformCredentials

        settings.platforms["twitter"] = PlatformCredentials()

    settings.platforms["twitter"].enabled = True
    settings.platforms["twitter"].client_id = client_id
    settings.platforms["twitter"].oauth2_token = token
    if client_secret:
        settings.platforms["twitter"].client_secret = client_secret
    if twitterapi_io_key:
        settings.platforms["twitter"].twitterapi_io_key = twitterapi_io_key

    settings.save()
    console.print(f"[green]Saved credentials to {settings.config_path}[/green]")
