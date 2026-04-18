"""Lightweight scoring for keyword hits (TODO)."""

from __future__ import annotations

# TODO: combine term frequency, title boosts, simple recency or depth penalty if desired.


def score_page(**_kwargs: object) -> float:
    raise NotImplementedError
