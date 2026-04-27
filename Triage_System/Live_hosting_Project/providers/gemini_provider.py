import ast
import json
import os
import re
from pathlib import Path
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

_ROOT_DIR = Path(__file__).resolve().parent.parent
if load_dotenv:
    load_dotenv(_ROOT_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GEMINI_ENABLED = os.environ.get("GEMINI_ENABLED", "True").lower() == "true"
GEMINI_TIMEOUT_SECONDS = int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "30"))
GEMINI_TEMPERATURE = float(os.environ.get("GEMINI_TEMPERATURE", "0.3"))
GEMINI_MAX_TOKENS = int(os.environ.get("GEMINI_MAX_TOKENS", "256"))

_GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

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


def _call_gemini_api(prompt):
    if not GEMINI_API_KEY:
        return None, "no_api_key"
    url = f"{_GEMINI_API_BASE}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": GEMINI_TEMPERATURE,
            "maxOutputTokens": GEMINI_MAX_TOKENS,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as response:
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
        return text, None
    except HTTPError as exc:
        return None, f"http_error_{exc.code}"
    except (URLError, SocketTimeout, TimeoutError) as exc:
        return None, f"timeout_or_network: {exc}"
    except Exception as exc:
        return None, str(exc)


def warm_qwen_model(reason="activity"):
    return True


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

    text, err = _call_gemini_api(prompt)
    if err:
        print(f"[gemini_provider] API error: {err}")
        return None, err

    parsed = _parse_json_like(text)
    sanitized = _sanitize_result(parsed, service_hint=service_hint)
    if not sanitized:
        print(f"[gemini_provider] Could not parse or sanitize response: {str(text)[:200]!r}")
        return None, "unreadable_response"

    return sanitized, None
