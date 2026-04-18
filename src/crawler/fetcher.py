"""HTTP fetch using urllib (stdlib): timeouts, status, content-type, HTML gating.

Coordinator responsibilities for failed fetches (do not let exceptions escape the crawl loop):
- Always call ``fetch_page`` inside try/except only if you wrap *other* logic; ``fetch_page``
  itself catches transport errors and returns a ``FetchResult`` — it should not raise for
  bad hosts, timeouts, or HTTP error codes.
- On any outcome, persist something via ``PageRepository.save_fetched_page`` (or equivalent):
  store ``status_code``, ``fetch_status``, optional ``body``/snippet, and set ``fetch_status``
  field to a stable string (e.g. ``ok``, ``http_error``, ``network_error``).
- Mark the frontier row ``failed`` when the fetch did not produce a usable document
  (``fetch_status != "ok"`` or not ``is_crawlable_html``), or ``done`` after successful
  processing; never leave items stuck in ``processing`` if the worker exits early.
- Do **not** run ``extract_links_and_text`` unless ``result.is_crawlable_html`` is True;
  for non-HTML responses (PDF, images, JSON) skip link discovery but still record the fetch.
- Do **not** retry infinitely; one attempt per frontier claim is enough unless you add a
  deliberate, bounded retry policy later.
"""

from __future__ import annotations

import socket
import ssl
from dataclasses import dataclass
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


_DEFAULT_MAX_BODY_BYTES = 2 * 1024 * 1024

_HTML_MEDIA = frozenset({"text/html", "application/xhtml+xml"})


@dataclass(frozen=True)
class FetchResult:
    """Structured outcome of a single HTTP GET attempt."""

    requested_url: str
    final_url: str | None
    status_code: int | None
    content_type: str | None
    media_type: str | None
    body: bytes
    fetch_status: str
    error_message: str | None = None

    @property
    def is_crawlable_html(self) -> bool:
        """True when the response is a successful HTML document worth parsing for links."""
        if self.fetch_status != "ok" or self.status_code is None:
            return False
        if not (200 <= self.status_code < 300):
            return False
        if self.media_type is None:
            return False
        return self.media_type in _HTML_MEDIA or self.media_type.startswith("text/html")


def _parse_media_type(content_type_header: str | None) -> tuple[str | None, str | None]:
    if not content_type_header:
        return None, None
    primary = content_type_header.split(";", 1)[0].strip()
    if not primary:
        return content_type_header.strip(), None
    return content_type_header.strip(), primary.lower()


def _read_body_limited(fp: BinaryIO, max_bytes: int) -> tuple[bytes, bool]:
    """Read until EOF or ``max_bytes`` exceeded. Returns (data, too_large)."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = fp.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            return b"".join(chunks), True
        chunks.append(chunk)
    return b"".join(chunks), False


def _scheme_allowed(url: str) -> bool:
    try:
        scheme = urlparse(url).scheme.lower()
    except Exception:
        return False
    return scheme in ("http", "https")


def fetch_page(
    url: str,
    *,
    timeout_sec: float,
    user_agent: str,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
) -> FetchResult:
    """
    GET ``url`` with ``User-Agent``, ``timeout_sec`` socket timeout, and body size cap.

    Returns ``FetchResult`` for all outcomes (no raise for network/HTTP failures).
    """
    if not url or not url.strip():
        return FetchResult(
            requested_url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            media_type=None,
            body=b"",
            fetch_status="invalid_url",
            error_message="empty URL",
        )

    if not _scheme_allowed(url):
        return FetchResult(
            requested_url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            media_type=None,
            body=b"",
            fetch_status="invalid_url",
            error_message="only http and https URLs are supported",
        )

    req = Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.1",
        },
        method="GET",
    )

    try:
        with urlopen(req, timeout=timeout_sec) as resp:  # nosec B310 - intentional crawler use
            final = resp.geturl()
            # Use getcode() only; some test doubles expose a non-numeric ``status`` attribute.
            code = resp.getcode()
            ctype_header = resp.headers.get_content_type()  # lowercased type/subtype only
            raw_header = resp.headers.get("Content-Type")
            # get_content_type() drops parameters; keep full header for debugging.
            full_ct, media = _parse_media_type(raw_header)
            if media is None and ctype_header:
                media = ctype_header
            body, too_large = _read_body_limited(resp, max_body_bytes)
            if too_large:
                return FetchResult(
                    requested_url=url,
                    final_url=final,
                    status_code=int(code) if code is not None else None,
                    content_type=full_ct,
                    media_type=media,
                    body=body,
                    fetch_status="too_large",
                    error_message=f"response exceeded max_body_bytes={max_body_bytes}",
                )
            return FetchResult(
                requested_url=url,
                final_url=final,
                status_code=int(code) if code is not None else None,
                content_type=full_ct,
                media_type=media,
                body=body,
                fetch_status="ok",
                error_message=None,
            )
    except HTTPError as e:
        full_ct, media = _parse_media_type(e.headers.get("Content-Type") if e.headers else None)
        body, too_large = _read_body_limited(e, max_body_bytes)
        status = int(e.code)
        if too_large:
            return FetchResult(
                requested_url=url,
                final_url=e.url if hasattr(e, "url") else None,
                status_code=status,
                content_type=full_ct,
                media_type=media,
                body=body,
                fetch_status="too_large",
                error_message=f"HTTP error body exceeded max_body_bytes={max_body_bytes}",
            )
        return FetchResult(
            requested_url=url,
            final_url=getattr(e, "url", None),
            status_code=status,
            content_type=full_ct,
            media_type=media,
            body=body,
            fetch_status="http_error",
            error_message=str(e.reason) if e.reason else f"HTTP {status}",
        )
    except URLError as e:
        reason = e.reason
        msg = str(reason) if reason else str(e)
        if isinstance(reason, socket.timeout) or isinstance(reason, TimeoutError):
            status = "timeout"
        elif isinstance(reason, ssl.SSLError):
            status = "network_error"
        else:
            status = "network_error"
        return FetchResult(
            requested_url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            media_type=None,
            body=b"",
            fetch_status=status,
            error_message=msg,
        )
    except OSError as e:
        return FetchResult(
            requested_url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            media_type=None,
            body=b"",
            fetch_status="network_error",
            error_message=str(e),
        )
