"""Crawler module import and frontier helper smoke tests."""

from __future__ import annotations

import unittest

from src.crawler.frontier import FrontierTask, InMemoryFrontier


class CrawlerTests(unittest.TestCase):
    def test_frontier_push_pop(self) -> None:
        f = InMemoryFrontier()
        f.push(FrontierTask("https://a.test/", "https://origin.test/", 0, None))
        t = f.pop()
        self.assertIsNotNone(t)
        assert t is not None
        self.assertEqual(t.url, "https://a.test/")


if __name__ == "__main__":
    unittest.main()
