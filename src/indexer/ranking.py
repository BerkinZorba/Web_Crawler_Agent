"""Lightweight keyword relevance scoring (explainable; no ML)."""

from __future__ import annotations

from typing import Final

# Weights are documented for README/demos; tune here only if you keep the story consistent.
WEIGHT_DISTINCT_QUERY_TERM: Final = 5.0
"""Points per *distinct* query term that matched the page (coverage bonus)."""

WEIGHT_BODY_FREQUENCY: Final = 1.0
"""Points per body occurrence (summed ``frequency`` from ``page_terms``)."""

WEIGHT_TITLE_FREQUENCY: Final = 3.0
"""Points per title occurrence (summed ``in_title_frequency``)."""

DEPTH_PENALTY_PER_LEVEL: Final = 0.2
"""Small penalty per crawl hop from origin (shallower pages preferred)."""


def score_page(
    *,
    matched_distinct_terms: int,
    body_frequency_sum: int,
    title_frequency_sum: int,
    depth: int,
) -> float:
    """
    Compute a relevance score from index statistics.

    Formula::

        score = (Wq × matched_distinct_terms)
              + (Wb × body_frequency_sum)
              + (Wt × title_frequency_sum)
              - (Wd × depth)

    Where:
    - ``matched_distinct_terms`` = how many *different* query terms appear on the page
    - ``body_frequency_sum`` = sum of body hit counts for those terms
    - ``title_frequency_sum`` = sum of title hit counts for those terms
    - ``depth`` = crawl depth from origin (0 for the seed URL)

    Constants: ``Wq`` = :data:`WEIGHT_DISTINCT_QUERY_TERM`, ``Wb`` = :data:`WEIGHT_BODY_FREQUENCY`,
    ``Wt`` = :data:`WEIGHT_TITLE_FREQUENCY`, ``Wd`` = :data:`DEPTH_PENALTY_PER_LEVEL`.
    """
    if matched_distinct_terms < 0 or body_frequency_sum < 0 or title_frequency_sum < 0 or depth < 0:
        raise ValueError("score inputs must be non-negative integers")
    return (
        WEIGHT_DISTINCT_QUERY_TERM * matched_distinct_terms
        + WEIGHT_BODY_FREQUENCY * body_frequency_sum
        + WEIGHT_TITLE_FREQUENCY * title_frequency_sum
        - DEPTH_PENALTY_PER_LEVEL * depth
    )
