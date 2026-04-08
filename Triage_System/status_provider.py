import os
import re
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


STATUS_PAGE_URL = "https://status.cloud.microsoft/"
CACHE_TTL_SECONDS = int(os.environ.get("MICROSOFT_STATUS_CACHE_TTL", "1800"))
MIN_REQUEST_INTERVAL_SECONDS = int(os.environ.get("MICROSOFT_STATUS_MIN_INTERVAL", "600"))
HTTP_TIMEOUT_SECONDS = int(os.environ.get("MICROSOFT_STATUS_TIMEOUT", "5"))
MAX_PAGE_BYTES = int(os.environ.get("MICROSOFT_STATUS_MAX_BYTES", "200000"))
STATUS_WINDOW_RADIUS = int(os.environ.get("MICROSOFT_STATUS_WINDOW_RADIUS", "300"))

_LOCK = threading.Lock()
_CACHE = {
    "fetched_at": 0.0,
    "next_allowed_at": 0.0,
    "html": "",
    "error": None,
    "fetch_in_progress": False,
    "stale": False,
}

SERVICE_ALIASES = {
    "microsoft 365": ["microsoft 365", "office 365", "m365"],
    "outlook": ["outlook", "exchange"],
    "teams": ["teams", "microsoft teams"],
    "onedrive": ["onedrive"],
    "sharepoint": ["sharepoint"],
    "excel": ["excel"],
    "word": ["word", "microsoft word"],
    "powerpoint": ["powerpoint", "power point"],
    "windows": ["windows", "windows sign in", "windows login"],
    "microsoft account": ["microsoft account", "account.microsoft"],
}

IGNORED_CONTEXT_TERMS = (
    "power platform admin center",
    "m365 enterprise",
    "m365 business",
    "microsoft 365 enterprise",
    "microsoft 365 business",
    "azure",
)

CONSUMER_SECTION_HINTS = (
    "for home",
    "consumer",
    "outlook.com",
    "microsoft account",
    "teams",
    "onedrive",
)

INCIDENT_TERMS = (
    "issue",
    "incident",
    "advisory",
    "degraded",
    "outage",
    "investigating",
    "service unavailable",
    "service issue",
)


def _strip_html(value):
    no_script = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    no_tags = re.sub(r"(?s)<[^>]+>", " ", no_script)
    return re.sub(r"\s+", " ", no_tags).strip()


def _contains_term(text, term):
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _contains_ignored_context(text):
    return any(_contains_term(text, term) for term in IGNORED_CONTEXT_TERMS)


def _consumer_text_scope(text):
    for hint in CONSUMER_SECTION_HINTS:
        pattern = r"\b" + re.escape(hint).replace(r"\ ", r"\s+") + r"\b"
        match = re.search(pattern, text)
        if match:
            return text[match.start():]

    if len(text) > 1200:
        lower_slice_start = int(len(text) * 0.55)
        return text[lower_slice_start:]

    return text


def _fetch_status_page():
    request = Request(
        STATUS_PAGE_URL,
        headers={
            "User-Agent": "ChatterRaxStatusChecker/1.0 (educational capstone; low-frequency health checks)"
        },
    )
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        return response.read(MAX_PAGE_BYTES).decode("utf-8", errors="ignore")


def _get_cached_page():
    now = time.time()
    with _LOCK:
        cached_html = _CACHE["html"]
        cache_is_fresh = cached_html and now - _CACHE["fetched_at"] < CACHE_TTL_SECONDS
        if cache_is_fresh:
            return cached_html, _CACHE["error"], _CACHE["stale"], False

        request_blocked = now < _CACHE["next_allowed_at"]
        if request_blocked or _CACHE["fetch_in_progress"]:
            return cached_html, _CACHE["error"], _CACHE["stale"], False

        _CACHE["fetch_in_progress"] = True
        _CACHE["next_allowed_at"] = now + MIN_REQUEST_INTERVAL_SECONDS

    try:
        html = _fetch_status_page()
        error = None
    except Exception as exc:  # pragma: no cover - network behavior varies at runtime
        html = None
        if isinstance(exc, URLError):
            error = str(exc.reason)
        else:
            error = str(exc)

    completed_at = time.time()
    with _LOCK:
        _CACHE["fetch_in_progress"] = False
        if html:
            _CACHE["html"] = html
            _CACHE["fetched_at"] = completed_at
            _CACHE["stale"] = False
        elif _CACHE["html"]:
            _CACHE["stale"] = True
        _CACHE["error"] = error
        return _CACHE["html"], _CACHE["error"], _CACHE["stale"], True


def _resolve_service(service_name):
    normalized = str(service_name or "").strip().lower()
    aliases = SERVICE_ALIASES.get(normalized)
    if aliases:
        return normalized, aliases, True
    if normalized:
        return normalized, [normalized], False
    return "microsoft 365", SERVICE_ALIASES["microsoft 365"], True


def check_microsoft_public_status(service_name=None):
    """
    Checks the public Microsoft backup status page in a highly limited way.
    Uses a shared cache and a minimum request interval to avoid repeated fetches.
    """
    html, fetch_error, is_stale, _ = _get_cached_page()
    text = _strip_html((html or "").lower())
    resolved_service, aliases, is_known_service = _resolve_service(service_name)
    consumer_text = _consumer_text_scope(text)

    result = {
        "source": STATUS_PAGE_URL,
        "service": resolved_service,
        "issue_found": False,
        "summary": "",
        "status_available": bool(text),
        "error": fetch_error,
        "service_known": is_known_service,
        "stale": is_stale,
    }

    freshness_warning = "Public Microsoft status information may not reflect the most recent service changes. "

    if not text:
        result["summary"] = (
            f"{freshness_warning}I could not reach the public Microsoft status page just now."
        )
        return result

    stale_prefix = "Using cached Microsoft status information. " if is_stale else ""
    prefix = f"{stale_prefix}{freshness_warning}"

    if service_name:
        matches = [alias for alias in aliases if _contains_term(consumer_text, alias)]
        if matches:
            windows = []
            for match in matches:
                pattern = r"\b" + re.escape(match).replace(r"\ ", r"\s+") + r"\b"
                for alias_match in re.finditer(pattern, consumer_text):
                    alias_index = alias_match.start()
                    window_start = max(0, alias_index - STATUS_WINDOW_RADIUS)
                    window_end = alias_index + STATUS_WINDOW_RADIUS
                    window = consumer_text[window_start:window_end]
                    if not _contains_ignored_context(window):
                        windows.append(window)

            if windows:
                issue_found = any(
                    _contains_term(window, term)
                    for window in windows
                    for term in INCIDENT_TERMS
                )
            else:
                issue_found = False
            result["issue_found"] = issue_found
            if issue_found:
                result["summary"] = (
                    f"{prefix}Microsoft's public status page appears to mention an issue related to {resolved_service}."
                )
            else:
                result["summary"] = (
                    f"{prefix}I do not see a clear public Microsoft status issue for {resolved_service} right now."
                )
            return result

        if not is_known_service:
            result["summary"] = (
                f"{prefix}I do not have a dedicated Microsoft status mapping for {resolved_service}, "
                "so I could not verify it reliably on the public status page."
            )
            return result

        result["summary"] = (
            f"{prefix}I checked the public Microsoft status page, but I did not find a specific "
            f"{resolved_service} listing there."
        )
        return result

    filtered_text = consumer_text
    for ignored_term in IGNORED_CONTEXT_TERMS:
        filtered_text = re.sub(
            r"\b" + re.escape(ignored_term).replace(r"\ ", r"\s+") + r"\b",
            " ",
            filtered_text,
        )

    issue_found = any(_contains_term(filtered_text, term) for term in INCIDENT_TERMS)
    result["issue_found"] = issue_found
    if issue_found:
        result["summary"] = f"{prefix}Microsoft's public backup status page appears to show an active service issue."
    else:
        result["summary"] = f"{prefix}I do not see a clear active issue on Microsoft's public backup status page right now."
    return result
