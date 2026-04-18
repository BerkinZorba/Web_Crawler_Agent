"""URL normalization for deduplication (http/https only, explicit rules)."""

from __future__ import annotations

import ipaddress
from posixpath import normpath
from urllib.parse import urldefrag, urljoin, urlparse, urlunparse


_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REJECT_SCHEMES = frozenset(
    {
        "javascript",
        "mailto",
        "tel",
        "ftp",
        "file",
        "data",
        "about",
    }
)


def resolve_link(href: str, base_url: str) -> str:
    """Resolve a possibly-relative href against the document URL (RFC 3986). Does not filter schemes."""
    return urljoin(base_url, href.strip())


def _netloc(host: str, port: int | None) -> str:
    """Build netloc for urlunparse (brackets for IPv6 literals)."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        host_part = host
    else:
        host_part = f"[{host}]" if ip.version == 6 else host
    if port is not None:
        return f"{host_part}:{port}"
    return host_part


def normalize_url(url: str) -> str:
    """
    Return a canonical http(s) URL string for duplicate detection and storage.

    Rules:
    - strip fragments (# and following)
    - lowercase scheme and host
    - drop default ports (:80 for http, :443 for https)
    - normalize path with POSIX rules (. and ..); empty path becomes /
    - preserve query string as given (no parameter reordering)

    Raises ValueError if the URL is not an absolute http(s) URL with a host,
    or uses an explicitly rejected scheme (javascript:, mailto:, tel:, ...).
    """
    raw = url.strip()
    if not raw:
        raise ValueError("empty URL")

    without_frag, _frag = urldefrag(raw)
    parsed = urlparse(without_frag)

    scheme = (parsed.scheme or "").lower()
    if scheme in _REJECT_SCHEMES or scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"unsupported or non-http(s) scheme: {scheme!r}")

    host = parsed.hostname
    if not host:
        raise ValueError(f"missing host in URL: {url!r}")

    host_lower = host.lower()
    port = parsed.port
    if scheme == "http" and port == 80:
        port = None
    elif scheme == "https" and port == 443:
        port = None

    netloc_out = _netloc(host_lower, port)

    path = parsed.path or "/"
    if path != "/":
        collapsed = normpath(path)
        if collapsed in (".", ""):
            path_out = "/"
        elif path.startswith("/") and not collapsed.startswith("/"):
            path_out = "/" + collapsed
        else:
            path_out = collapsed or "/"
    else:
        path_out = "/"

    query = parsed.query

    return urlunparse((scheme, netloc_out, path_out, "", query, ""))


def normalize_url_or_none(url: str, *, base_url: str | None = None) -> str | None:
    """
    Resolve against base_url when given, then normalize.
    Returns None for unsupported schemes, relative resolution failures, or other invalid URLs.
    """
    try:
        resolved = urljoin(base_url, url.strip()) if base_url else url.strip()
        return normalize_url(resolved)
    except ValueError:
        return None
