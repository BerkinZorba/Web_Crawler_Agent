"""Search/index scaffolding import tests."""

from __future__ import annotations

import unittest

from src.indexer.tokenizer import tokenize


class SearchTests(unittest.TestCase):
    def test_tokenize_basic(self) -> None:
        self.assertEqual(tokenize("Hello, world!"), ["hello", "world"])


if __name__ == "__main__":
    unittest.main()
