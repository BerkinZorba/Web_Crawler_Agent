"""Extract links and text from HTML without heavy parsers (TODO)."""

from __future__ import annotations

# TODO: html.parser-based link href collection + rough text extraction.


def extract_links_and_text(html: bytes, base_url: str) -> tuple[list[str], str]:
    raise NotImplementedError
