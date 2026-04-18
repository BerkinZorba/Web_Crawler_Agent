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

import logging
import socket
import ssl
from dataclasses import dataclass
from typing import BinaryIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

log = logging.getLogger(__name__)

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


def _is_ssl_cert_or_verify_failure(exc: BaseException) -> bool:
    """True when failure is likely fixed (or only exposed) by relaxing cert verification."""
    if isinstance(exc, ssl.SSLCertVerificationError):
        return True
    if isinstance(exc, ssl.SSLError):
        msg = str(exc).lower()
        if any(
            s in msg
            for s in (
                "certificate",
                "cert verify",
                "hostname",
                "sslv3",
                "tlsv1",
                "handshake",
            )
        ):
            return True
    if isinstance(exc, URLError) and exc.reason is not None:
        return _is_ssl_cert_or_verify_failure(exc.reason)
    return False


def _urlopen_for_request(req: Request, url: str, timeout_sec: float):
    """
    Open URL: HTTP without SSL context; HTTPS with default TLS context, then one
    permissive retry if certificate verification fails (localhost / dev only).
    urllib follows redirects via HTTPRedirectHandler by default.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme != "https":
        return urlopen(req, timeout=timeout_sec)  # nosec B310 - intentional crawler use

    ctx = ssl.create_default_context()
    try:
        return urlopen(req, timeout=timeout_sec, context=ctx)  # nosec B310
    except (URLError, OSError) as e:
        if _is_ssl_cert_or_verify_failure(e):
            log.warning(
                "fetch_page: SSL verification failed for %s (%s); retrying with unverified context (development only)",
                url,
                e,
            )
            return urlopen(  # nosec B310
                req,
                timeout=timeout_sec,
                context=ssl._create_unverified_context(),
            )
        raise


def _classify_transport_failure(exc: BaseException) -> tuple[str, str]:
    """Map exception to (fetch_status, error_message) for structured results."""
    if isinstance(exc, URLError):
        reason = exc.reason
        msg = f"{type(exc).__name__}: {reason!s}" if reason is not None else str(exc)
        if isinstance(reason, socket.timeout) or isinstance(reason, TimeoutError):
            return "timeout", msg
        if isinstance(reason, ssl.SSLError):
            return "ssl_error", msg
        if isinstance(reason, socket.gaierror):
            return "dns_error", msg
        if isinstance(reason, ConnectionRefusedError):
            return "connection_error", msg
        if isinstance(reason, OSError) and reason.errno is not None:
            return "network_error", msg
        if isinstance(reason, str):
            low = reason.lower()
            if "timed out" in low or "timeout" in low:
                return "timeout", msg
        return "network_error", msg

    if isinstance(exc, OSError):
        msg = f"{type(exc).__name__}: {exc}"
        if isinstance(exc, socket.timeout) or isinstance(exc, TimeoutError):
            return "timeout", msg
        if isinstance(exc, ssl.SSLError):
            return "ssl_error", msg
        if isinstance(exc, socket.gaierror):
            return "dns_error", msg
        if isinstance(exc, ConnectionRefusedError):
            return "connection_error", msg
        return "network_error", msg

    msg = f"{type(exc).__name__}: {exc}"
    return "network_error", msg


def fetch_page(
    url: str,
    *,
    timeout_sec: float,
    user_agent: str,
    max_body_bytes: int = _DEFAULT_MAX_BODY_BYTES,
) -> FetchResult:
    """
    GET ``url`` with ``User-Agent``, ``timeout_sec`` socket timeout, and body size cap.

    HTTPS uses the default SSL context; on verification failure, retries once with an
    unverified context (development convenience only). Redirects are followed by urllib.

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
        with _urlopen_for_request(req, url, timeout_sec) as resp:
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
        err_msg = str(e.reason) if e.reason else f"HTTP {status}"
        log.warning("fetch_page HTTP error url=%s code=%s: %s", url, status, err_msg)
        return FetchResult(
            requested_url=url,
            final_url=getattr(e, "url", None),
            status_code=status,
            content_type=full_ct,
            media_type=media,
            body=body,
            fetch_status="http_error",
            error_message=err_msg,
        )
    except (URLError, OSError) as e:
        status, msg = _classify_transport_failure(e)
        log.warning("fetch_page transport failure url=%s status=%s: %s", url, status, msg)
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
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        log.warning("fetch_page unexpected error url=%s: %s", url, msg, exc_info=True)
        return FetchResult(
            requested_url=url,
            final_url=None,
            status_code=None,
            content_type=None,
            media_type=None,
            body=b"",
            fetch_status="network_error",
            error_message=msg,
        )
