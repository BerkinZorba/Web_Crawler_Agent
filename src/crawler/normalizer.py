"""URL normalization for deduplication and same-site rules (TODO)."""

from __future__ import annotations

from urllib.parse import urljoin, urlparse


def normalize_url(url: str) -> str:
    # TODO: strip fragments, lowercase host, resolve relative URLs with base when needed.
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"not an absolute URL: {url!r}")
    return url.strip()


def resolve_link(href: str, base_url: str) -> str:
    return urljoin(base_url, href)
