import ast
from collections import deque
from email.utils import parsedate_to_datetime
import json
import os
import re
import threading
import time
from pathlib import Path
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener, urlopen

from triage_core.domain_config import (
    DEFAULT_SERVICE,
    intent_names,
    load_domain_packs,
    service_names,
)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_ROOT_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_ROOT_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_ENABLED = os.environ.get("GEMINI_ENABLED", "True").lower() == "true"
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "30"))
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_TOKENS = int(os.environ.get("GEMINI_MAX_TOKENS", "1024"))
GEMINI_THINKING_BUDGET = int(os.environ.get("GEMINI_THINKING_BUDGET", "0"))
GEMINI_BYPASS_PROXY = os.environ.get("GEMINI_BYPASS_PROXY", "True").lower() == "true"
GEMINI_TPM_LIMIT = int(os.environ.get("GEMINI_TPM_LIMIT", "250000"))
GEMINI_RPM_LIMIT = int(os.environ.get("GEMINI_RPM_LIMIT", "5"))
GEMINI_MIN_REQUEST_INTERVAL_SECONDS = float(
    os.environ.get("GEMINI_MIN_REQUEST_INTERVAL_SECONDS", "0.25")
)
GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS = float(
    os.environ.get("GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS", "3")
)
GEMINI_RATE_LIMIT_RETRIES = int(os.environ.get("GEMINI_RATE_LIMIT_RETRIES", "1"))
GEMINI_429_COOLDOWN_SECONDS = float(os.environ.get("GEMINI_429_COOLDOWN_SECONDS", "8"))
GEMINI_429_MAX_COOLDOWN_SECONDS = float(
    os.environ.get("GEMINI_429_MAX_COOLDOWN_SECONDS", "300")
)

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_RATE_WINDOW_SECONDS = 60
_RATE_LIMIT_LOCK = threading.Lock()
_RATE_LIMIT_USAGE = deque()
_REQUEST_TIMESTAMPS = deque()
_NEXT_REQUEST_AT = 0.0
_PAUSE_UNTIL = 0.0
_CONSECUTIVE_429S = 0
DOMAIN_PACK = load_domain_packs()
DOMAIN_DEFAULT_SERVICE = DOMAIN_PACK.get("default_service") or DEFAULT_SERVICE
DOMAIN_LABEL = DOMAIN_PACK.get("domain_label") or DOMAIN_DEFAULT_SERVICE.title()

_ALLOWED_SERVICES = service_names(DOMAIN_PACK) or {DOMAIN_DEFAULT_SERVICE}
_ALLOWED_INTENTS = intent_names(DOMAIN_PACK) | {"unknown"}
_ALLOWED_PRIORITIES = {"low", "medium", "high"}
_SERVICE_VALUES_TEXT = ", ".join(sorted(_ALLOWED_SERVICES | {"unknown"}))
_INTENT_VALUES_TEXT = ", ".join(sorted(_ALLOWED_INTENTS))
_ROUTING_RULES_TEXT = (
    """Stay inside the configured domain services. If the user mentions multiple supported areas, choose the one that owns the current symptom.
If the service or issue is unclear, ask one focused clarification question instead of guessing.
Use only the configured service values; do not introduce unconfigured service names."""
)
_DOMAIN_EXTRA_RULES = tuple(
    str(rule).strip()
    for rule in (DOMAIN_PACK.get("gemini") or {}).get("extra_rules", [])
    if str(rule).strip()
)
_DOMAIN_EXTRA_RULES_TEXT = (
    "\n" + "\n".join(f"Domain rule: {rule}" for rule in _DOMAIN_EXTRA_RULES)
    if _DOMAIN_EXTRA_RULES
    else ""
)

_INTENT_ALIASES = {
    "hearing": "audio",
    "mic": "audio",
    "microphone": "audio",
    "speaker": "audio",
    "speakers": "audio",
    "camera": "video",
    "webcam": "video",
    "screen": "display",
    "monitor": "display",
    "font": "formatting",
    "fonts": "formatting",
    "layout": "formatting",
    "formatting": "formatting",
    "markup": "formatting",
    "email": "email_delivery",
    "mail": "email_delivery",
    "delivery": "email_delivery",
    "permission": "permissions",
}
_SENSITIVE_REQUEST_PATTERNS = (
    r"\bprovide\b.*\bpassword\b",
    r"\bshare\b.*\bpassword\b",
    r"\bgive\b.*\bpassword\b",
    r"\b(send|enter|type)\b.*\bpassword\b",
    r"\bemail and password\b",
    r"\bverification code\b",
    r"\b2fa code\b",
    r"\bauthenticator code\b",
    r"\brecovery code\b",
)


def _extract_json_block(text):
    cleaned = re.sub(
        r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.MULTILINE
    ).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return cleaned[start : end + 1]


def _parse_json_like(text):
    candidate = _extract_json_block(text)
    if not candidate:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(candidate)
        except (ValueError, SyntaxError):
            return None


def _compact_text(text, max_chars=120):
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def estimate_token_count(text):
    """Fast token estimate for limiter math; Gemini billing may differ slightly."""
    words = re.findall(r"\S+", str(text or ""))
    char_estimate = max(1, (len(str(text or "")) + 3) // 4)
    word_estimate = int(len(words) * 1.35) + 1
    return max(char_estimate, word_estimate)


def _estimated_request_tokens(prompt):
    output_budget = GEMINI_MAX_TOKENS + max(0, GEMINI_THINKING_BUDGET)
    return estimate_token_count(prompt) + output_budget


def _prune_rate_limit_state(now):
    cutoff = now - _RATE_WINDOW_SECONDS
    while _RATE_LIMIT_USAGE and _RATE_LIMIT_USAGE[0][0] <= cutoff:
        _RATE_LIMIT_USAGE.popleft()
    while _REQUEST_TIMESTAMPS and _REQUEST_TIMESTAMPS[0] <= cutoff:
        _REQUEST_TIMESTAMPS.popleft()


def _current_window_tokens():
    return sum(tokens for _, tokens in _RATE_LIMIT_USAGE)


def _reserve_gemini_capacity(estimated_tokens):
    global _NEXT_REQUEST_AT
    if GEMINI_TPM_LIMIT <= 0 and GEMINI_RPM_LIMIT <= 0 and GEMINI_MIN_REQUEST_INTERVAL_SECONDS <= 0:
        return 0.0, None

    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        _prune_rate_limit_state(now)
        wait_until = max(_PAUSE_UNTIL, _NEXT_REQUEST_AT)

        if GEMINI_TPM_LIMIT > 0:
            window_tokens = _current_window_tokens()
            if window_tokens + estimated_tokens > GEMINI_TPM_LIMIT:
                if _RATE_LIMIT_USAGE:
                    wait_until = max(wait_until, _RATE_LIMIT_USAGE[0][0] + _RATE_WINDOW_SECONDS)
                else:
                    return 0.0, "rate_limited_tpm"

        if GEMINI_RPM_LIMIT > 0 and len(_REQUEST_TIMESTAMPS) >= GEMINI_RPM_LIMIT:
            wait_until = max(wait_until, _REQUEST_TIMESTAMPS[0] + _RATE_WINDOW_SECONDS)

        wait_seconds = max(0.0, wait_until - now)
        if wait_seconds > GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS:
            return wait_seconds, "rate_limited_wait_too_long"

        reservation_time = max(now, wait_until)
        _RATE_LIMIT_USAGE.append((reservation_time, estimated_tokens))
        _REQUEST_TIMESTAMPS.append(reservation_time)
        _NEXT_REQUEST_AT = reservation_time + max(0.0, GEMINI_MIN_REQUEST_INTERVAL_SECONDS)
        return wait_seconds, None


def _parse_retry_after(headers):
    retry_after = headers.get("Retry-After") if headers else None
    if not retry_after:
        return None
    try:
        return max(0.0, float(retry_after))
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(retry_after)
            return max(0.0, retry_at.timestamp() - time.time())
        except (TypeError, ValueError, AttributeError, OverflowError):
            return None


def _parse_retry_delay_from_error_body(error_body):
    try:
        payload = json.loads(error_body or "{}")
    except (TypeError, json.JSONDecodeError):
        return None
    details = payload.get("error", {}).get("details") or []
    for detail in details:
        retry_delay = detail.get("retryDelay")
        if not retry_delay:
            continue
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(retry_delay).strip())
        if match:
            return float(match.group(1))
    message = str(payload.get("error", {}).get("message") or "")
    match = re.search(r"retry in (\d+(?:\.\d+)?)s", message, flags=re.IGNORECASE)
    if match:
        return float(match.group(1))
    return None


def _quota_error_label(error_body):
    try:
        payload = json.loads(error_body or "{}")
    except (TypeError, json.JSONDecodeError):
        return "rate_limited_429"
    error = payload.get("error", {})
    details = error.get("details") or []
    for detail in details:
        violations = detail.get("violations") or []
        for violation in violations:
            quota_id = str(violation.get("quotaId") or "")
            quota_metric = str(violation.get("quotaMetric") or "")
            if "PerDay" in quota_id:
                return "quota_exhausted_daily"
            if "requests" in quota_metric or "Requests" in quota_id:
                return "rate_limited_requests"
    if error.get("status") == "RESOURCE_EXHAUSTED":
        return "quota_exhausted"
    return "rate_limited_429"


def _record_rate_limit_429(seconds=None):
    global _CONSECUTIVE_429S, _PAUSE_UNTIL
    with _RATE_LIMIT_LOCK:
        _CONSECUTIVE_429S += 1
        exponential_cooldown = GEMINI_429_COOLDOWN_SECONDS * (
            2 ** min(_CONSECUTIVE_429S - 1, 6)
        )
        requested_cooldown = 0.0 if seconds is None else float(seconds)
        cooldown = max(exponential_cooldown, requested_cooldown)
        cooldown = min(max(0.0, cooldown), GEMINI_429_MAX_COOLDOWN_SECONDS)
        _PAUSE_UNTIL = max(_PAUSE_UNTIL, time.monotonic() + cooldown)


def _record_gemini_success():
    global _CONSECUTIVE_429S
    with _RATE_LIMIT_LOCK:
        _CONSECUTIVE_429S = 0


def get_gemini_rate_limit_status():
    now = time.monotonic()
    with _RATE_LIMIT_LOCK:
        _prune_rate_limit_state(now)
        used_tokens = _current_window_tokens()
        pause_remaining = max(0.0, _PAUSE_UNTIL - now)
        next_request_wait = max(0.0, _NEXT_REQUEST_AT - now, pause_remaining)
        return {
            "tpm_limit": GEMINI_TPM_LIMIT,
            "rpm_limit": GEMINI_RPM_LIMIT,
            "estimated_tokens_used_last_minute": used_tokens,
            "estimated_tokens_remaining_last_minute": (
                max(0, GEMINI_TPM_LIMIT - used_tokens) if GEMINI_TPM_LIMIT > 0 else None
            ),
            "requests_used_last_minute": len(_REQUEST_TIMESTAMPS),
            "min_request_interval_seconds": GEMINI_MIN_REQUEST_INTERVAL_SECONDS,
            "max_wait_seconds": GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS,
            "cooldown_remaining_seconds": round(pause_remaining, 2),
            "next_request_wait_seconds": round(next_request_wait, 2),
            "consecutive_429s": _CONSECUTIVE_429S,
        }


def _build_keyword_context_block(keyword_context):
    if not keyword_context or not keyword_context.get("found"):
        return ""
    lines = [
        "KB context. Use it to ground troubleshooting, but write a fresh concise answer. Do not quote it verbatim."
    ]
    for index, resource in enumerate((keyword_context.get("resources") or [])[:2], start=1):
        matched_terms = ", ".join(resource.get("matched_terms", [])[:5]) or "none"
        steps = [
            _compact_text(step, 90)
            for step in (resource.get("steps") or [])[:3]
            if str(step).strip()
        ]
        advanced_steps = [
            _compact_text(step, 90)
            for step in (resource.get("advanced_steps") or [])[:2]
            if str(step).strip()
        ]
        line = (
            f"{index}. {resource.get('service', DOMAIN_DEFAULT_SERVICE)} / "
            f"{resource.get('intent', 'unknown')} / {resource.get('title', f'{DOMAIN_LABEL} issue')}. "
            f"Matched: {matched_terms}. Checks: {' | '.join(steps) or 'none'}."
        )
        if advanced_steps:
            line += f" Deeper checks: {' | '.join(advanced_steps)}."
        lines.append(line)
    return "\n" + "\n".join(lines) + "\n"


def _build_thread_memory_block(thread_memory):
    if not thread_memory or not thread_memory.get("threads"):
        return ""
    lines = ["Earlier threads. Use only if the user clearly points back."]
    for thread in thread_memory.get("threads", [])[:2]:
        recent_messages = _compact_text(
            (thread.get("recent_messages") or ["none"])[-1], 60
        )
        lines.append(
            f"- {thread.get('service', 'unknown')} | {thread.get('last_intent', 'unknown')} | {recent_messages}"
        )
    return "\n" + "\n".join(lines) + "\n"


def _build_prompt(message, service_hint=None, conversation_history=None,
                  hardware_term=None, keyword_context=None,
                  thread_memory=None, session_summary=""):
    history = conversation_history or []
    service_line = service_hint or "unknown"

    history_lines = []
    for turn in reversed(history):
        if turn.get("sender") == "user":
            history_lines.append(
                f"Prev user: {_compact_text(turn.get('message', ''), 80)}"
            )
            break

    history_block = ""
    if history_lines:
        history_block = "\nRecent context:\n" + "\n".join(history_lines) + "\n"

    hardware_line = ""
    if hardware_term:
        hardware_line = (
            f"Hardware mention: {hardware_term}. Assume software/settings first.\n"
        )

    keyword_block = _build_keyword_context_block(keyword_context)
    thread_block = _build_thread_memory_block(thread_memory)
    session_summary_block = ""
    if str(session_summary or "").strip():
        session_summary_block = (
            "\nPersisted session summary:\n"
            + _compact_text(session_summary, 260)
            + "\n"
        )

    return f"""You are ChatterRax for the {DOMAIN_LABEL} domain.
Output ONLY JSON with keys: service, intent, needs_ticket, needs_description, priority, reply.
Reply should be 1-2 warm, specific sentences with no URLs.
Current issue first. Only reuse earlier context if the user clearly points back.
If app or issue is unclear, ask one focused clarification question.
For unclear app names, made-up error codes, vague popups, or missing details, do not open or suggest a ticket yet. Set needs_ticket false and ask for the app name, the action taken, or the exact message.
Set needs_ticket true only when the user explicitly asks for a ticket, human, agent, or handoff, or when the issue is clearly business-critical with enough detail to route it.
If the user clearly names an app and the issue happens inside that app, prefer that app as the service.
{_ROUTING_RULES_TEXT}
Never ask the user to share passwords, verification codes, recovery codes, or other secrets.
Never use hardware words as the service value. Physical damage or power failure is out of scope.
Use KB context as the grounded troubleshooting source when it matches the app and symptom. Adapt it to the user's wording; do not copy every step blindly.
Never include URLs or tell the user to go read an article. Provide the fix path directly in the reply.
needs_ticket and needs_description must be booleans.
service values: {_SERVICE_VALUES_TEXT}
intent values: {_INTENT_VALUES_TEXT}
priority values: low, medium, high
Use high only for widespread outages, multiple users affected, or a clearly work-stopping lockout with urgent timing.
Use low for minor cosmetic or convenience issues like signatures, notifications, formatting, themes, or non-blocking preferences.
Use medium for the normal single-user support case.
{_DOMAIN_EXTRA_RULES_TEXT}
Example schema: {{"service":"{DOMAIN_DEFAULT_SERVICE}","intent":"sync","needs_ticket":false,"needs_description":false,"priority":"medium","reply":"..."}}
{history_block}
{thread_block}
{session_summary_block}
Hint: {service_line}
{hardware_line}User message: {_compact_text(message, 400)}
{keyword_block}
"""


def _sanitize_choice(value, allowed_values, fallback):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed_values else fallback


def _sanitize_intent(value):
    normalized = str(value or "").strip().lower()
    normalized = _INTENT_ALIASES.get(normalized, normalized)
    return normalized if normalized in _ALLOWED_INTENTS else "unknown"


def _sanitize_bool(value, fallback=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return fallback
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n", ""}:
            return False
        return fallback
    if isinstance(value, (int, float)):
        return bool(value)
    return fallback


def _reply_requests_sensitive_info(reply_text):
    normalized = str(reply_text or "").strip().lower()
    return any(re.search(pattern, normalized) for pattern in _SENSITIVE_REQUEST_PATTERNS)


def _safe_reply_for_sensitive_request(service):
    generic_label = "this service"
    label = str(service or "").strip() or generic_label
    if label == "unknown":
        label = generic_label
    elif label != generic_label:
        label = label.title()
    return (
        f"Do not share your password or verification codes here. In {label}, "
        "sign out and back in, then use the official account recovery flow only if you cannot regain access."
    )


def _sanitize_result(raw_result, service_hint=None):
    if not isinstance(raw_result, dict):
        return None
    reply = str(raw_result.get("reply", "")).strip()
    if not reply and isinstance(raw_result.get("needs_description"), str):
        reply = raw_result.get("needs_description", "").strip()
    if not reply:
        return None
    service_fallback = (service_hint or "unknown").strip().lower()
    model_service = _sanitize_choice(
        raw_result.get("service"),
        _ALLOWED_SERVICES | {"unknown"},
        "unknown",
    )
    allowed_fallback_services = _ALLOWED_SERVICES | {DOMAIN_DEFAULT_SERVICE}
    if model_service != "unknown":
        service = model_service
    elif service_fallback in allowed_fallback_services:
        service = service_fallback
    else:
        service = "unknown"
    intent = _sanitize_intent(raw_result.get("intent"))
    priority = _sanitize_choice(raw_result.get("priority"), _ALLOWED_PRIORITIES, "medium")
    if _reply_requests_sensitive_info(reply):
        reply = _safe_reply_for_sensitive_request(service)
    return {
        "service": service,
        "intent": intent,
        "needs_ticket": _sanitize_bool(raw_result.get("needs_ticket", False)),
        "needs_description": _sanitize_bool(raw_result.get("needs_description", False)),
        "priority": priority,
        "reply": reply,
    }


def _call_gemini_api(prompt, estimated_tokens=None):
    if not GEMINI_API_KEY:
        return None, "no_api_key"
    url = f"{_GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_TOKENS,
            "responseMimeType": "application/json",
        },
    }
    if "2.5" in GEMINI_MODEL:
        payload["generationConfig"]["thinkingConfig"] = {
            "thinkingBudget": GEMINI_THINKING_BUDGET,
        }
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    attempts = max(1, GEMINI_RATE_LIMIT_RETRIES + 1)
    estimated_tokens = estimated_tokens or _estimated_request_tokens(prompt)

    for attempt in range(attempts):
        wait_seconds, wait_error = _reserve_gemini_capacity(estimated_tokens)
        if wait_error:
            return None, wait_error
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        try:
            opener = build_opener(ProxyHandler({})) if GEMINI_BYPASS_PROXY else None
            open_request = opener.open if opener else urlopen
            with open_request(req, timeout=GEMINI_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            candidates = data.get("candidates") or []
            if not candidates:
                return None, "empty_candidates"
            text = (
                candidates[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            _record_gemini_success()
            return text, None
        except HTTPError as exc:
            if exc.code == 429:
                error_body = exc.read().decode("utf-8", errors="replace")
                retry_after = (
                    _parse_retry_after(exc.headers)
                    or _parse_retry_delay_from_error_body(error_body)
                )
                cooldown = retry_after if retry_after is not None else GEMINI_429_COOLDOWN_SECONDS
                _record_rate_limit_429(cooldown)
                if attempt < attempts - 1 and cooldown <= GEMINI_RATE_LIMIT_MAX_WAIT_SECONDS:
                    time.sleep(cooldown)
                    continue
                return None, _quota_error_label(error_body)
            return None, f"http_error_{exc.code}"
        except (URLError, SocketTimeout, TimeoutError) as exc:
            return None, f"timeout_or_network: {exc}"
        except Exception as exc:
            return None, str(exc)

    return None, "rate_limited_429"


def get_gemini_health_status():
    """Return Gemini configuration status without calling the model API."""
    return {
        "provider": "gemini",
        "enabled": GEMINI_ENABLED,
        "configured": bool(GEMINI_API_KEY),
        "model": GEMINI_MODEL,
        "max_tokens": GEMINI_MAX_TOKENS,
        "thinking_budget": GEMINI_THINKING_BUDGET,
        "bypass_proxy": GEMINI_BYPASS_PROXY,
        "rate_limit": get_gemini_rate_limit_status(),
    }


def generate_triage_response(message, service_hint=None, conversation_history=None,
                             hardware_term=None, keyword_context=None,
                             thread_memory=None, session_summary=""):
    if not GEMINI_ENABLED:
        return None, "disabled"

    if not GEMINI_API_KEY:
        return None, "no_api_key"

    prompt = _build_prompt(
        message,
        service_hint=service_hint,
        conversation_history=conversation_history,
        hardware_term=hardware_term,
        keyword_context=keyword_context,
        thread_memory=thread_memory,
        session_summary=session_summary,
    )

    estimated_tokens = _estimated_request_tokens(prompt)
    text, err = _call_gemini_api(prompt, estimated_tokens=estimated_tokens)
    if err:
        print(f"[gemini_provider] API error: {err}")
        return None, err

    parsed = _parse_json_like(text)
    sanitized = _sanitize_result(parsed, service_hint=service_hint)
    if not sanitized:
        print(f"[gemini_provider] Could not parse or sanitize response: {str(text)[:200]!r}")
        return None, "unreadable_response"

    return sanitized, None
