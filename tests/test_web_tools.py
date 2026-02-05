"""Tests for WebTools (web search and URL fetching)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from blah.agents.tools.web_tools import WebTools


@pytest.fixture
def web_tools():
    return WebTools(timeout=10.0)


class TestWebSearch:
    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_web_search_success(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        # Mock DuckDuckGo HTML response
        mock_resp = MagicMock()
        mock_resp.text = """
        <div class="result">
            <a class="result__a" href="//ddg.co/l/?uddg=https%3A%2F%2Fexample.com%2Fpage1">
                Example Page 1
            </a>
            <a class="result__snippet">This is snippet 1</a>
        </div>
        <div class="result">
            <a class="result__a" href="//ddg.co/l/?uddg=https%3A%2F%2Fexample.com%2Fpage2">
                Example Page 2
            </a>
            <a class="result__snippet">This is snippet 2</a>
        </div>
        """
        mock_client.get.return_value = mock_resp

        result = web_tools.web_search("test query", num_results=5)

        assert not result.is_error
        data = json.loads(result.content)
        assert data["query"] == "test query"
        assert len(data["results"]) == 2
        assert data["results"][0]["title"] == "Example Page 1"
        assert "example.com/page1" in data["results"][0]["url"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_web_search_no_results(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.text = '<div>No results found</div>'
        mock_client.get.return_value = mock_resp

        result = web_tools.web_search("obscure query xyz123")

        assert not result.is_error
        data = json.loads(result.content)
        assert data["results"] == []
        assert "No results" in data["message"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_web_search_timeout(self, mock_client_cls, web_tools):
        import httpx
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        result = web_tools.web_search("test query")

        assert result.is_error
        data = json.loads(result.content)
        assert "timed out" in data["error"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_web_search_error(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = RuntimeError("Connection failed")

        result = web_tools.web_search("test query")

        assert result.is_error
        data = json.loads(result.content)
        assert "failed" in data["error"].lower()

    def test_web_search_limits_results(self, web_tools):
        # num_results should be capped at 10
        with patch("blah.agents.tools.web_tools.httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_resp = MagicMock()
            mock_resp.text = '<div>No results</div>'
            mock_client.get.return_value = mock_resp

            # Even if we ask for 100, it should be capped
            web_tools.web_search("test", num_results=100)
            # Just verify it doesn't error


class TestFetchUrl:
    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_success(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = '''
        <html>
        <head><title>Test Page</title></head>
        <body>
            <h1>Hello World</h1>
            <p>This is the main content.</p>
        </body>
        </html>
        '''
        mock_client.get.return_value = mock_resp

        result = web_tools.fetch_url("https://example.com/page")

        assert not result.is_error
        data = json.loads(result.content)
        assert data["url"] == "https://example.com/page"
        assert "Hello World" in data["content"]
        assert "main content" in data["content"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_strips_scripts(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = '''
        <html>
        <head><script>alert("bad")</script></head>
        <body>
            <p>Good content</p>
            <script>console.log("also bad")</script>
        </body>
        </html>
        '''
        mock_client.get.return_value = mock_resp

        result = web_tools.fetch_url("https://example.com")

        data = json.loads(result.content)
        assert "alert" not in data["content"]
        assert "console" not in data["content"]
        assert "Good content" in data["content"]

    def test_fetch_url_invalid_scheme(self, web_tools):
        result = web_tools.fetch_url("ftp://example.com/file")

        assert result.is_error
        data = json.loads(result.content)
        assert "Invalid URL scheme" in data["error"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_unsupported_content_type(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "application/pdf"}
        mock_client.get.return_value = mock_resp

        result = web_tools.fetch_url("https://example.com/doc.pdf")

        assert result.is_error
        data = json.loads(result.content)
        assert "Unsupported content type" in data["error"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_timeout(self, mock_client_cls, web_tools):
        import httpx
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client
        mock_client.get.side_effect = httpx.TimeoutException("timeout")

        result = web_tools.fetch_url("https://example.com")

        assert result.is_error
        data = json.loads(result.content)
        assert "timed out" in data["error"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_http_error(self, mock_client_cls, web_tools):
        import httpx
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        error = httpx.HTTPStatusError("Not found", request=MagicMock(), response=mock_resp)
        mock_client.get.side_effect = error

        result = web_tools.fetch_url("https://example.com/notfound")

        assert result.is_error
        data = json.loads(result.content)
        assert "404" in data["error"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_truncates_long_content(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/html"}
        # Create very long content
        mock_resp.text = "<html><body>" + "x" * 20000 + "</body></html>"
        mock_client.get.return_value = mock_resp

        result = web_tools.fetch_url("https://example.com")

        data = json.loads(result.content)
        # Should be truncated to 8000 chars max
        assert len(data["content"]) <= 8100  # 8000 + "...[truncated]"
        assert "truncated" in data["content"]

    @patch("blah.agents.tools.web_tools.httpx.Client")
    def test_fetch_url_plain_text(self, mock_client_cls, web_tools):
        mock_client = MagicMock()
        mock_client_cls.return_value.__enter__.return_value = mock_client

        mock_resp = MagicMock()
        mock_resp.headers = {"content-type": "text/plain"}
        mock_resp.text = "Plain text content here"
        mock_client.get.return_value = mock_resp

        result = web_tools.fetch_url("https://example.com/file.txt")

        assert not result.is_error
        data = json.loads(result.content)
        assert "Plain text content" in data["content"]
