"""Extract links and plain text from HTML using html.parser (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser

from src.crawler.normalizer import normalize_url_or_none


_WS = re.compile(r"\s+")


class _HtmlLinkAndTextParser(HTMLParser):
    """Collect normalized http(s) links from <a href> and rough visible text."""

    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base_url = base_url
        self._links: list[str] = []
        self._text_parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in ("script", "style"):
            self._skip += 1
            return
        if self._skip:
            return
        if t == "a":
            href = _attr(attrs, "href")
            if href is None or href.strip() == "":
                return
            normalized = normalize_url_or_none(href, base_url=self._base_url)
            if normalized is not None:
                self._links.append(normalized)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if data.strip():
            self._text_parts.append(data)

    @property
    def links(self) -> list[str]:
        return self._links

    @property
    def text(self) -> str:
        raw = " ".join(self._text_parts)
        return _WS.sub(" ", raw).strip()


def _attr(attrs: list[tuple[str, str | None]], name: str) -> str | None:
    for k, v in attrs:
        if k.lower() == name.lower():
            return v
    return None


def extract_links_and_text(html: bytes, base_url: str) -> tuple[list[str], str]:
    """
    Parse HTML bytes, return (deduplicated normalized links, flattened text).

    Links come from <a href="..."> only. Order is first-seen; duplicates removed.
    Unsupported schemes (javascript:, mailto:, tel:, non-http(s), ...) are dropped.
    """
    text = html.decode("utf-8", errors="replace")
    parser = _HtmlLinkAndTextParser(base_url)
    parser.feed(text)
    parser.close()
    unique_links = list(dict.fromkeys(parser.links))
    return unique_links, parser.text
