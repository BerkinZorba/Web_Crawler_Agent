"""Search/index tests: tokenizer and ranking."""

from __future__ import annotations

import unittest

from src.indexer.ranking import (
    DEPTH_PENALTY_PER_LEVEL,
    WEIGHT_BODY_FREQUENCY,
    WEIGHT_DISTINCT_QUERY_TERM,
    WEIGHT_TITLE_FREQUENCY,
    score_page,
)
from src.indexer.tokenizer import token_counts, tokenize


class SearchTests(unittest.TestCase):
    def test_tokenize_basic(self) -> None:
        self.assertEqual(tokenize("Hello, world!"), ["hello", "world"])

    def test_tokenize_drops_stopwords_and_short_tokens(self) -> None:
        self.assertEqual(tokenize("The and OR a I x running"), ["running"])

    def test_token_counts(self) -> None:
        self.assertEqual(token_counts(tokenize("cat cat dog")), {"cat": 2, "dog": 1})

    def test_score_page_formula(self) -> None:
        # 2 distinct, body 10, title 1, depth 2
        # -> 5*2 + 1*10 + 3*1 - 0.2*2 = 10 + 10 + 3 - 0.4 = 22.6
        s = score_page(
            matched_distinct_terms=2,
            body_frequency_sum=10,
            title_frequency_sum=1,
            depth=2,
        )
        self.assertAlmostEqual(
            s,
            WEIGHT_DISTINCT_QUERY_TERM * 2
            + WEIGHT_BODY_FREQUENCY * 10
            + WEIGHT_TITLE_FREQUENCY * 1
            - DEPTH_PENALTY_PER_LEVEL * 2,
        )

    def test_score_page_rejects_negative_inputs(self) -> None:
        with self.assertRaises(ValueError):
            score_page(
                matched_distinct_terms=-1,
                body_frequency_sum=0,
                title_frequency_sum=0,
                depth=0,
            )


if __name__ == "__main__":
    unittest.main()
