"""Crawler module tests: frontier helper, URL normalization, HTML extraction."""

from __future__ import annotations

import unittest

from src.crawler.extractor import extract_links_and_text
from src.crawler.frontier import FrontierTask, InMemoryFrontier
from src.crawler.normalizer import normalize_url, normalize_url_or_none, resolve_link


class CrawlerTests(unittest.TestCase):
    def test_frontier_push_pop(self) -> None:
        f = InMemoryFrontier()
        f.push(FrontierTask("https://a.test/", "https://origin.test/", 0, None))
        t = f.pop()
        self.assertIsNotNone(t)
        assert t is not None
        self.assertEqual(t.url, "https://a.test/")

    def test_normalize_lowercase_host_and_strip_fragment(self) -> None:
        self.assertEqual(
            normalize_url("http://Example.COM:80/a#frag"),
            "http://example.com/a",
        )
        self.assertEqual(
            normalize_url("https://Example.COM:443/b?x=1#y"),
            "https://example.com/b?x=1",
        )

    def test_normalize_path_dots(self) -> None:
        # /a/./b/../c collapses to /a/c (.. removes b, not the /a segment).
        self.assertEqual(normalize_url("http://example.com/a/./b/../c"), "http://example.com/a/c")
        self.assertEqual(normalize_url("http://example.com/a/../c"), "http://example.com/c")

    def test_normalize_rejects_schemes(self) -> None:
        for bad in ("mailto:a@b.com", "javascript:void(0)", "tel:+1"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    normalize_url(bad)

    def test_normalize_or_none_relative(self) -> None:
        base = "https://example.com/dir/page.html"
        self.assertEqual(
            normalize_url_or_none("../other", base_url=base),
            "https://example.com/other",
        )
        self.assertIsNone(normalize_url_or_none("mailto:x@y", base_url=base))

    def test_resolve_link_protocol_relative(self) -> None:
        base = "https://example.com/dir/page"
        self.assertEqual(resolve_link("//cdn.test/x", base), "https://cdn.test/x")

    def test_extract_links_dedup_and_text(self) -> None:
        html = b"""<!doctype html>
        <html><head><title>t</title></head><body>
        <a href="/a">1</a>
        <a href='/a'>dup</a>
        <a href="mailto:x@y">m</a>
        <a href="javascript:void(0)">j</a>
        <script>alert('no')</script>
        <p>Hello <b>world</b></p>
        </body></html>
        """
        base = "https://site.example/dir/page.html"
        links, text = extract_links_and_text(html, base)
        self.assertEqual(links, ["https://site.example/a"])
        self.assertIn("Hello", text)
        self.assertIn("world", text)
        self.assertNotIn("alert", text)


if __name__ == "__main__":
    unittest.main()
