"""HTTP fetch using urllib (stdlib); timeouts and redirects (TODO)."""

from __future__ import annotations

# TODO: urllib.request with User-Agent, timeout, size cap, content-type check.


def fetch_url(url: str, *, timeout_sec: float, user_agent: str) -> bytes:
    raise NotImplementedError
