"""Tests for urllib-based fetcher (mocked, no real network)."""

from __future__ import annotations

import http.client
import io
import socket
import unittest
from unittest.mock import MagicMock, patch

from urllib.error import HTTPError, URLError

from src.crawler.fetcher import fetch_page


def _html_headers() -> http.client.HTTPMessage:
    m = http.client.HTTPMessage()
    m.add_header("Content-Type", "text/html; charset=utf-8")
    return m


class FetcherTests(unittest.TestCase):
    def test_invalid_scheme(self) -> None:
        r = fetch_page("mailto:a@b", timeout_sec=5.0, user_agent="Test/1")
        self.assertEqual(r.fetch_status, "invalid_url")
        self.assertIsNone(r.status_code)

    @patch("src.crawler.fetcher.urlopen")
    def test_ok_html(self, mock_open: MagicMock) -> None:
        body = b"<!doctype html><title>x</title>"
        resp = MagicMock()
        resp.geturl.return_value = "https://example.com/page"
        resp.getcode.return_value = 200
        resp.headers.get.return_value = "text/html; charset=utf-8"
        resp.headers.get_content_type.return_value = "text/html"
        buf = io.BytesIO(body)

        def read_chunk(n: int = -1) -> bytes:
            return buf.read(n)

        resp.read = read_chunk
        mock_open.return_value.__enter__.return_value = resp
        mock_open.return_value.__exit__.return_value = None

        r = fetch_page("https://example.com/page", timeout_sec=10.0, user_agent="Test/1")
        self.assertEqual(r.fetch_status, "ok")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.media_type, "text/html")
        self.assertEqual(r.body, body)
        self.assertTrue(r.is_crawlable_html)

    @patch("src.crawler.fetcher.urlopen")
    def test_json_not_crawlable(self, mock_open: MagicMock) -> None:
        body = b'{"a":1}'
        resp = MagicMock()
        resp.geturl.return_value = "https://example.com/api"
        resp.getcode.return_value = 200
        resp.headers.get.return_value = "application/json"
        resp.headers.get_content_type.return_value = "application/json"
        buf = io.BytesIO(body)
        resp.read = buf.read
        mock_open.return_value.__enter__.return_value = resp
        mock_open.return_value.__exit__.return_value = None

        r = fetch_page("https://example.com/api", timeout_sec=10.0, user_agent="Test/1")
        self.assertEqual(r.fetch_status, "ok")
        self.assertFalse(r.is_crawlable_html)

    @patch("src.crawler.fetcher.urlopen")
    def test_http_error_not_crawlable(self, mock_open: MagicMock) -> None:
        hdrs = _html_headers()
        fp = io.BytesIO(b"<html>err</html>")
        err = HTTPError("https://example.com/missing", 404, "Not Found", hdrs, fp)
        mock_open.side_effect = err

        r = fetch_page("https://example.com/missing", timeout_sec=10.0, user_agent="Test/1")
        self.assertEqual(r.fetch_status, "http_error")
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.is_crawlable_html)

    @patch("src.crawler.fetcher.urlopen")
    def test_timeout(self, mock_open: MagicMock) -> None:
        mock_open.side_effect = URLError(socket.timeout("timed out"))

        r = fetch_page("https://example.com/slow", timeout_sec=1.0, user_agent="Test/1")
        self.assertEqual(r.fetch_status, "timeout")
        self.assertIsNone(r.status_code)

    @patch("src.crawler.fetcher.urlopen")
    def test_body_size_cap(self, mock_open: MagicMock) -> None:
        body = b"x" * 100
        resp = MagicMock()
        resp.geturl.return_value = "https://example.com/big"
        resp.getcode.return_value = 200
        resp.headers.get.return_value = "text/html"
        resp.headers.get_content_type.return_value = "text/html"
        buf = io.BytesIO(body)
        resp.read = buf.read
        mock_open.return_value.__enter__.return_value = resp
        mock_open.return_value.__exit__.return_value = None

        r = fetch_page(
            "https://example.com/big",
            timeout_sec=10.0,
            user_agent="Test/1",
            max_body_bytes=20,
        )
        self.assertEqual(r.fetch_status, "too_large")
        self.assertEqual(r.status_code, 200)


if __name__ == "__main__":
    unittest.main()
