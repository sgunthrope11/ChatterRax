import ast
import json
import os
import re
import threading
import time
from pathlib import Path
from socket import timeout as SocketTimeout
from urllib.error import URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - app.py already loads dotenv in production
    load_dotenv = None

_ROOT_DIR = Path(__file__).resolve().parent.parent

if load_dotenv:
    load_dotenv(_ROOT_DIR / ".env")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_PRIMARY_MODEL", "qwen2.5:3b")
OLLAMA_FAILOVER_MODEL = os.environ.get("OLLAMA_FAILOVER_MODEL", "").strip()
OLLAMA_ENABLED = os.environ.get("OLLAMA_ENABLED", "True").lower() == "true"
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "45"))
OLLAMA_PRIMARY_TIMEOUT_SECONDS = int(
    os.environ.get("OLLAMA_PRIMARY_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS))
)
OLLAMA_FAILOVER_TIMEOUT_SECONDS = int(
    os.environ.get("OLLAMA_FAILOVER_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS))
)
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_TOP_P = float(os.environ.get("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "120"))
OLLAMA_COLD_START_TIMEOUT_SECONDS = int(
    os.environ.get(
        "OLLAMA_COLD_START_TIMEOUT_SECONDS",
        str(max(OLLAMA_TIMEOUT_SECONDS, 60)),
    )
)
OLLAMA_COMPLEX_PROMPT_TIMEOUT_SECONDS = int(
    os.environ.get(
        "OLLAMA_COMPLEX_PROMPT_TIMEOUT_SECONDS",
        str(max(OLLAMA_TIMEOUT_SECONDS, 45)),
    )
)
OLLAMA_WARMUP_TIMEOUT_SECONDS = int(
    os.environ.get(
        "OLLAMA_WARMUP_TIMEOUT_SECONDS",
        str(min(OLLAMA_COLD_START_TIMEOUT_SECONDS, 30)),
    )
)
OLLAMA_FAILURE_COOLDOWN_SECONDS = int(
    os.environ.get("OLLAMA_FAILURE_COOLDOWN_SECONDS", "30")
)

_LOCK = threading.Lock()
_WARMUP_LOCK = threading.Lock()
_STATE = {
    "primary": {
        "last_error": None,
        "last_failed_at": 0.0,
        "last_success_at": 0.0,
        "has_succeeded": False,
        "consecutive_failures": 0,
    },
    "failover": {
        "last_error": None,
        "last_failed_at": 0.0,
        "last_success_at": 0.0,
        "has_succeeded": False,
        "consecutive_failures": 0,
    },
}

_ALLOWED_SERVICES = {
    "teams",
    "outlook",
    "onedrive",
    "sharepoint",
    "excel",
    "word",
    "powerpoint",
    "windows",
    "microsoft account",
    "microsoft 365",
}
_ALLOWED_INTENTS = {
    "password_reset",
    "sign_in",
    "sync",
    "crash",
    "status",
    "outage",
    "escalation",
    "email_delivery",
    "permissions",
    "device_setup",
    "audio",
    "video",
    "display",
    "formatting",
    "printing",
    "unknown",
}
_ALLOWED_PRIORITIES = {"low", "medium", "high"}

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


def _parse_keep_alive_seconds(value):
    match = re.fullmatch(r"(\d+)(ms|s|m|h)?", str(value or "").strip().lower())
    if not match:
        return None

    amount = int(match.group(1))
    unit = match.group(2) or "s"
    scale = {
        "ms": 0.001,
        "s": 1,
        "m": 60,
        "h": 3600,
    }
    return amount * scale[unit]


def _build_keyword_context_block(keyword_context):
    if not keyword_context or not keyword_context.get("found"):
        return ""

    resource = (keyword_context.get("resources") or [{}])[0]
    matched_terms = ", ".join(resource.get("matched_terms", [])[:3]) or "none"
    first_step = _compact_text((resource.get("steps") or [""])[0], 70) or "none"
    return (
        "\nKB hint: "
        f"{resource.get('title', 'Microsoft issue')}; terms: {matched_terms}; "
        f"check: {first_step}\n"
    )


def _build_thread_memory_block(thread_memory):
    if not thread_memory or not thread_memory.get("threads"):
        return ""

    lines = ["Earlier threads. Use only if the user clearly points back."]

    for thread in thread_memory.get("threads", [])[:2]:
        recent_messages = _compact_text(
            (thread.get("recent_messages") or ["none"])[-1],
            60,
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
        history_block = (
            "\nRecent context:\n"
            + "\n".join(history_lines)
            + "\n"
        )

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

    return f"""You are ChatterRax.
Output ONLY JSON with keys: service, intent, needs_ticket, needs_description, priority, reply.
Reply should be 1-2 warm, specific sentences with no URLs.
Current issue first. Only reuse earlier context if the user clearly points back.
If app or issue is unclear, ask one focused clarification question.
If the user clearly names an app and the issue happens inside that app, prefer that app as the service.
Do not switch to microsoft account unless the user is mainly locked out of the account itself, missing verification codes, or recovering account access.
Password prompts inside Outlook, Teams, OneDrive, or Microsoft 365 apps should usually stay with that app.
Never ask the user to share passwords, verification codes, recovery codes, or other secrets.
Map meeting audio/video with Teams mention to teams; file sync/cloud backup to onedrive; device, driver, install, printer, dock, Bluetooth, USB, Wi-Fi, monitor, mic, webcam, headset to windows unless a better Microsoft app fit is obvious.
Never use hardware words as the service value. Physical damage or power failure is out of scope.
Use KB hints only as backup.
needs_ticket and needs_description must be booleans.
service values: teams, outlook, onedrive, sharepoint, excel, word, powerpoint, windows, microsoft account, microsoft 365, unknown
intent values: password_reset, sign_in, sync, crash, status, outage, escalation, email_delivery, permissions, device_setup, audio, video, display, printing, unknown
priority values: low, medium, high
Use high only for widespread outages, multiple users affected, or a clearly work-stopping lockout with urgent timing.
Use low for minor cosmetic or convenience issues like signatures, notifications, formatting, themes, or non-blocking preferences.
Use medium for the normal single-user support case.
Example schema: {{"service":"outlook","intent":"sync","needs_ticket":false,"needs_description":false,"priority":"medium","reply":"..."}}
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
    label = str(service or "").strip() or "this Microsoft app"
    if label == "unknown":
        label = "this Microsoft app"
    elif label != "this Microsoft app":
        label = label.title()
    return (
        f"Do not share your password or verification codes here. In {label}, "
        "sign out and back in, then use the official Microsoft reset flow only if you cannot regain access."
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
    if model_service != "unknown":
        service = model_service
    elif service_fallback in _ALLOWED_SERVICES | {"microsoft 365"}:
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


def _request_ollama_payload(payload, timeout_seconds):
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_ollama(prompt, model, timeout_seconds):
    return _request_ollama_payload(
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": OLLAMA_KEEP_ALIVE,
            "format": "json",
            "options": {
                "temperature": OLLAMA_TEMPERATURE,
                "top_p": OLLAMA_TOP_P,
                "num_predict": OLLAMA_NUM_PREDICT,
            },
        },
        timeout_seconds,
    )


def _is_timeout_error(error_msg):
    normalized = str(error_msg or "").strip().lower()
    return "timed out" in normalized or "timeout" in normalized


def _slot_cooldown_state(slot):
    with _LOCK:
        failures = _STATE[slot]["consecutive_failures"]
        last_failed_at = _STATE[slot]["last_failed_at"]
        last_error = _STATE[slot]["last_error"]

    in_cooldown = (
        last_error is not None
        and (time.time() - last_failed_at < OLLAMA_FAILURE_COOLDOWN_SECONDS)
    )
    skip_slot = in_cooldown and failures >= 2
    return skip_slot, last_error


def _is_cold_slot(slot):
    keep_alive_seconds = _parse_keep_alive_seconds(OLLAMA_KEEP_ALIVE)

    with _LOCK:
        has_succeeded = _STATE[slot]["has_succeeded"]
        last_success_at = _STATE[slot]["last_success_at"]

    if not has_succeeded:
        return True

    if keep_alive_seconds is not None and keep_alive_seconds >= 0:
        if time.time() - last_success_at >= keep_alive_seconds:
            return True

    return False


def _timeout_for_slot(slot, base_timeout_seconds):
    if _is_cold_slot(slot):
        return max(base_timeout_seconds, OLLAMA_COLD_START_TIMEOUT_SECONDS)

    return base_timeout_seconds


def _prompt_timeout_floor(prompt, base_timeout_seconds):
    prompt_size = len(str(prompt or ""))
    if prompt_size >= 1800:
        return max(base_timeout_seconds, OLLAMA_COMPLEX_PROMPT_TIMEOUT_SECONDS)
    return base_timeout_seconds


def _warm_model(slot, model, timeout_seconds):
    try:
        _request_ollama_payload(
            {
                "model": model,
                "prompt": "ready",
                "stream": False,
                "keep_alive": OLLAMA_KEEP_ALIVE,
                "options": {
                    "temperature": 0,
                    "num_predict": 1,
                },
            },
            timeout_seconds,
        )
        with _LOCK:
            _STATE[slot]["last_error"] = None
            _STATE[slot]["has_succeeded"] = True
            _STATE[slot]["last_success_at"] = time.time()
        return True
    except Exception:
        return False


def warm_qwen_model(reason="activity"):
    if not OLLAMA_ENABLED:
        return False

    with _WARMUP_LOCK:
        warmed = _warm_model(
            "primary",
            OLLAMA_PRIMARY_MODEL,
            OLLAMA_WARMUP_TIMEOUT_SECONDS,
        )
        if warmed:
            print(
                f"[qwen_provider] Warmed {OLLAMA_PRIMARY_MODEL} "
                f"for {reason}."
            )
        return warmed


def _try_model(prompt, slot, model, service_hint, timeout_seconds):
    """Attempt a single Ollama request and update _STATE[slot] accordingly.

    Returns (sanitized_result, error_message).  Exactly one of the two will
    be None on return.
    """
    try:
        raw = _request_ollama(prompt, model, timeout_seconds)
    except Exception as exc:
        if isinstance(exc, URLError):
            error_msg = str(exc.reason)
        elif isinstance(exc, SocketTimeout):
            error_msg = "timed out"
        else:
            error_msg = str(exc)
        with _LOCK:
            _STATE[slot]["last_error"] = error_msg
            _STATE[slot]["last_failed_at"] = time.time()
            _STATE[slot]["consecutive_failures"] += 1
        return None, error_msg

    parsed = _parse_json_like(raw.get("response", ""))
    sanitized = _sanitize_result(parsed, service_hint=service_hint)
    if not sanitized:
        error_msg = "Ollama returned an unreadable response."
        with _LOCK:
            _STATE[slot]["last_error"] = error_msg
            _STATE[slot]["last_failed_at"] = time.time()
            _STATE[slot]["consecutive_failures"] += 1
        return None, error_msg

    with _LOCK:
        _STATE[slot]["last_error"] = None
        _STATE[slot]["has_succeeded"] = True
        _STATE[slot]["last_success_at"] = time.time()
        _STATE[slot]["consecutive_failures"] = 0

    return sanitized, None


def generate_triage_response(message, service_hint=None, conversation_history=None,
                             hardware_term=None, keyword_context=None,
                             thread_memory=None, session_summary=""):
    if not OLLAMA_ENABLED:
        return None, "disabled"

    prompt = _build_prompt(
        message,
        service_hint=service_hint,
        conversation_history=conversation_history,
        hardware_term=hardware_term,
        keyword_context=keyword_context,
        thread_memory=thread_memory,
        session_summary=session_summary,
    )

    skip_primary, primary_error = _slot_cooldown_state("primary")

    if skip_primary:
        return None, primary_error or "primary in cooldown"

    warmed_primary = False
    if _is_cold_slot("primary"):
        warmed_primary = _warm_model(
            "primary",
            OLLAMA_PRIMARY_MODEL,
            OLLAMA_COLD_START_TIMEOUT_SECONDS,
        )

    primary_timeout_seconds = _timeout_for_slot(
        "primary",
        OLLAMA_PRIMARY_TIMEOUT_SECONDS,
    )
    if warmed_primary:
        primary_timeout_seconds = OLLAMA_PRIMARY_TIMEOUT_SECONDS
    primary_timeout_seconds = _prompt_timeout_floor(prompt, primary_timeout_seconds)

    result, err = _try_model(
        prompt,
        "primary",
        OLLAMA_PRIMARY_MODEL,
        service_hint,
        primary_timeout_seconds,
    )
    if result:
        return result, None

    if _is_timeout_error(err):
        print(
            f"[qwen_provider] Primary model ({OLLAMA_PRIMARY_MODEL}) timed out "
            f"after {primary_timeout_seconds}s. Falling back to rules."
        )
        return None, err

    if OLLAMA_FAILOVER_MODEL and OLLAMA_FAILOVER_MODEL != OLLAMA_PRIMARY_MODEL:
        skip_failover, failover_error = _slot_cooldown_state("failover")
        if skip_failover:
            return None, failover_error or err or "failover in cooldown"
        warmed_failover = False
        if _is_cold_slot("failover"):
            warmed_failover = _warm_model(
                "failover",
                OLLAMA_FAILOVER_MODEL,
                OLLAMA_COLD_START_TIMEOUT_SECONDS,
            )
        failover_timeout_seconds = _timeout_for_slot(
            "failover",
            OLLAMA_FAILOVER_TIMEOUT_SECONDS,
        )
        if warmed_failover:
            failover_timeout_seconds = OLLAMA_FAILOVER_TIMEOUT_SECONDS
        failover_timeout_seconds = _prompt_timeout_floor(prompt, failover_timeout_seconds)
        result, failover_err = _try_model(
            prompt,
            "failover",
            OLLAMA_FAILOVER_MODEL,
            service_hint,
            failover_timeout_seconds,
        )
        if result:
            return result, None
        if failover_err:
            return None, failover_err

    return None, err


def qwen_runtime_status():
    with _LOCK:
        return {
            "enabled": OLLAMA_ENABLED,
            "primary_model": OLLAMA_PRIMARY_MODEL,
            "primary_timeout_seconds": OLLAMA_PRIMARY_TIMEOUT_SECONDS,
            "cold_start_timeout_seconds": OLLAMA_COLD_START_TIMEOUT_SECONDS,
            "warmup_timeout_seconds": OLLAMA_WARMUP_TIMEOUT_SECONDS,
            "primary_loaded": (
                _STATE["primary"]["has_succeeded"]
                and _STATE["primary"]["last_error"] is None
            ),
            "primary_error": _STATE["primary"]["last_error"],
            "failover_model": OLLAMA_FAILOVER_MODEL or None,
            "failover_timeout_seconds": OLLAMA_FAILOVER_TIMEOUT_SECONDS,
            "failover_loaded": (
                _STATE["failover"]["has_succeeded"]
                and _STATE["failover"]["last_error"] is None
            ),
            "failover_error": _STATE["failover"]["last_error"],
            "provider": "ollama",
            "url": OLLAMA_URL,
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
