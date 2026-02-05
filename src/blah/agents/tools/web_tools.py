"""Web tools for research — search and URL fetching."""

from __future__ import annotations

import json
import logging
import re
from urllib.parse import urlparse

import httpx

from blah.agents.tools.base import ToolResult, tool

logger = logging.getLogger(__name__)

# Simple HTML tag stripper
TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    return TAG_RE.sub("", text)


def _truncate(text: str, max_len: int = 4000) -> str:
    """Truncate text to max length."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...[truncated]"


class WebTools:
    """Web research tools — search and URL fetching."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @tool(
        name="web_search",
        description=(
            "Search the web for information on a topic. "
            "Use this to research topics, find current events, or gather context for rants. "
            "Returns a list of search results with titles, snippets, and URLs."
        ),
        parameters={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query",
                },
                "num_results": {
                    "type": "integer",
                    "description": "Number of results to return (default 5, max 10)",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    )
    def web_search(self, query: str, num_results: int = 5) -> ToolResult:
        """Search using DuckDuckGo HTML (no API key needed)."""
        num_results = min(num_results, 10)

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                # Use DuckDuckGo HTML search
                resp = client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Blah/1.0)"},
                )
                resp.raise_for_status()

                results = self._parse_ddg_html(resp.text, num_results)

                if not results:
                    return ToolResult(
                        content=json.dumps({
                            "query": query,
                            "results": [],
                            "message": "No results found",
                        })
                    )

                return ToolResult(
                    content=json.dumps({
                        "query": query,
                        "results": results,
                    })
                )

        except httpx.TimeoutException:
            return ToolResult(
                content=json.dumps({"error": "Search timed out"}),
                is_error=True,
            )
        except Exception as e:
            logger.exception("Web search failed")
            return ToolResult(
                content=json.dumps({"error": f"Search failed: {e!s}"}),
                is_error=True,
            )

    def _parse_ddg_html(self, html: str, max_results: int) -> list[dict]:
        """Parse DuckDuckGo HTML results (simple regex parsing)."""
        results = []

        # Find result blocks - DDG uses class="result__a" for links
        link_pattern = re.compile(
            r'class="result__a"[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
            re.IGNORECASE,
        )
        snippet_pattern = re.compile(
            r'class="result__snippet"[^>]*>([^<]+(?:<[^>]+>[^<]*</[^>]+>)*[^<]*)</a',
            re.IGNORECASE | re.DOTALL,
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (url, title) in enumerate(links[:max_results]):
            # DDG uses redirect URLs, extract the actual URL
            if "uddg=" in url:
                actual_url = re.search(r"uddg=([^&]+)", url)
                if actual_url:
                    from urllib.parse import unquote
                    url = unquote(actual_url.group(1))

            snippet = ""
            if i < len(snippets):
                snippet = _strip_html(snippets[i]).strip()

            results.append({
                "title": _strip_html(title).strip(),
                "url": url,
                "snippet": snippet[:300],
            })

        return results

    @tool(
        name="fetch_url",
        description=(
            "Fetch and extract text content from a URL. "
            "Use this to read articles, blog posts, or other web pages for research. "
            "Returns the main text content of the page."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL to fetch",
                },
            },
            "required": ["url"],
        },
    )
    def fetch_url(self, url: str) -> ToolResult:
        """Fetch URL and extract main text content."""
        # Validate URL
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(
                content=json.dumps({"error": "Invalid URL scheme, must be http or https"}),
                is_error=True,
            )

        try:
            with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; Blah/1.0)"},
                )
                resp.raise_for_status()

                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return ToolResult(
                        content=json.dumps({
                            "error": f"Unsupported content type: {content_type}",
                            "url": url,
                        }),
                        is_error=True,
                    )

                # Extract text from HTML
                text = self._extract_text(resp.text)
                text = _truncate(text, 8000)

                return ToolResult(
                    content=json.dumps({
                        "url": url,
                        "content": text,
                    })
                )

        except httpx.TimeoutException:
            return ToolResult(
                content=json.dumps({"error": "Request timed out", "url": url}),
                is_error=True,
            )
        except httpx.HTTPStatusError as e:
            return ToolResult(
                content=json.dumps({
                    "error": f"HTTP {e.response.status_code}",
                    "url": url,
                }),
                is_error=True,
            )
        except Exception as e:
            logger.exception("URL fetch failed")
            return ToolResult(
                content=json.dumps({"error": f"Fetch failed: {e!s}", "url": url}),
                is_error=True,
            )

    def _extract_text(self, html: str) -> str:
        """Extract readable text from HTML (simple approach)."""
        # Remove script and style tags
        html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = _strip_html(html)

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text)
        text = "\n".join(line.strip() for line in text.split("\n") if line.strip())

        return text.strip()
