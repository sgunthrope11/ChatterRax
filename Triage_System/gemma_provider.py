import ast
import json
import os
import re
import threading
import time
from socket import timeout as SocketTimeout
from urllib.error import URLError
from urllib.request import Request, urlopen


OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate")
OLLAMA_PRIMARY_MODEL = os.environ.get("OLLAMA_PRIMARY_MODEL", "gemma3:1b")
OLLAMA_FAILOVER_MODEL = os.environ.get("OLLAMA_FAILOVER_MODEL", "llama3.2:3b")
OLLAMA_ENABLED = os.environ.get("OLLAMA_ENABLED", "True").lower() == "true"
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "65"))
OLLAMA_PRIMARY_TIMEOUT_SECONDS = int(
    os.environ.get("OLLAMA_PRIMARY_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS))
)
OLLAMA_FAILOVER_TIMEOUT_SECONDS = int(
    os.environ.get("OLLAMA_FAILOVER_TIMEOUT_SECONDS", "35")
)
OLLAMA_FAILOVER_ENABLED = os.environ.get("OLLAMA_FAILOVER_ENABLED", "False").lower() == "true"
OLLAMA_KEEP_ALIVE = os.environ.get("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_TEMPERATURE = float(os.environ.get("OLLAMA_TEMPERATURE", "0.3"))
OLLAMA_TOP_P = float(os.environ.get("OLLAMA_TOP_P", "0.9"))
OLLAMA_NUM_PREDICT = int(os.environ.get("OLLAMA_NUM_PREDICT", "120"))
OLLAMA_FAILURE_COOLDOWN_SECONDS = int(
    os.environ.get("OLLAMA_FAILURE_COOLDOWN_SECONDS", "30")
)

_LOCK = threading.Lock()
_STATE = {
    "primary": {
        "last_error": None,
        "last_failed_at": 0.0,
        "has_succeeded": False,
        "consecutive_failures": 0,
    },
    "failover": {
        "last_error": None,
        "last_failed_at": 0.0,
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
    "email": "email_delivery",
    "mail": "email_delivery",
    "delivery": "email_delivery",
    "permission": "permissions",
}


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


def _build_prompt(message, service_hint=None, conversation_history=None,
                  hardware_term=None):
    history = conversation_history or []
    service_line = service_hint or "unknown"

    history_lines = []
    for turn in history[-2:]:
        role = "User" if turn.get("sender") == "user" else "Bot"
        history_lines.append(f"{role}: {turn.get('message', '').strip()}")

    services_seen = []
    for turn in history:
        if turn.get("sender") == "user":
            msg = turn.get("message", "").lower()
            for svc in [
                "teams", "outlook", "onedrive", "sharepoint", "excel",
                "word", "powerpoint", "windows", "microsoft account",
                "microsoft 365",
            ]:
                if svc in msg and svc not in services_seen:
                    services_seen.append(svc)

    history_block = ""
    if history_lines:
        history_block = (
            "\nPrevious conversation:\n"
            + "\n".join(history_lines)
            + "\n"
        )

    services_block = ""
    if services_seen:
        services_block = (
            f"Services mentioned so far: {', '.join(services_seen)}\n"
        )

    hardware_line = ""
    if hardware_term:
        hardware_line = (
            f"Hardware peripheral mentioned: {hardware_term}"
            f" - assume software/driver cause first.\n"
        )

    return f"""You are ChatterRax, a Microsoft consumer support bot.

Scope: Teams, Outlook, OneDrive, SharePoint, Word, Excel,
PowerPoint, Windows, Microsoft account, Microsoft 365 only.

Rules:
- Users may open casually with "yo", "wassup", "hey", slang,
  typos, bad grammar, fragments, or run-on sentences. Understand
  the intent, but keep your reply professional, warm, and concise.
- The user message may be just one or two words like "excel"
  or "teams broken". This is valid input. Infer what you can
  and ask ONE focused follow-up question.
- If the message is very short and you cannot determine the
  issue, ask specifically what is going wrong with that app
  rather than giving a generic response.
- If user misspells a Microsoft product name, infer the correct
  service. Examples: excell=Excel, outlok=Outlook,
  one drive=OneDrive, powerpt=PowerPoint, teems=Teams,
  windwos=Windows.
- Never use hardware words as the service value. For camera,
  microphone, speaker, headset, or meeting audio/video issues,
  use "teams" when a meeting/app is mentioned, otherwise "windows".
  For monitor, dock, display, printer, Bluetooth, USB, Wi-Fi, or
  device-driver issues, use "windows". For file sync/cloud backup
  issues, use "onedrive".
- Hardware peripheral issues are IN SCOPE when they have a
  Microsoft software or driver fix. Examples:
  * Mic not working in Teams -> Windows sound privacy settings
    or Teams audio device settings
  * Webcam not detected -> Windows camera privacy settings
    or Teams video settings
  * Headphones no sound -> Windows audio output settings
  * Bluetooth device not connecting -> Windows Bluetooth settings
  * Printer not found -> Windows printer settings
  * External monitor not detected -> Windows display settings
  * USB drive not showing -> Windows file explorer or OneDrive
- When a hardware issue has a clear Microsoft software fix,
  give that specific fix in 1-2 sentences.
- When a hardware issue might need a driver update, mention
  checking Windows Update as the first step.
- Physical damage (cracked screen, water damage, device won't
  power on) is NOT in scope - do not attempt to troubleshoot.
- If a user mentions a peripheral (mic, webcam, headset,
  printer, etc.) assume it is a software/settings issue first
  unless they explicitly say it is physically broken.
- Reply in 1-2 sentences only. Be specific to what they said.
- Do not give generic advice. Reference their actual issue.
- If continuing a conversation, do not repeat earlier questions.
- If unsure, ask one focused follow-up question.
- If issue needs a ticket, set needs_ticket true.
- Never mention Azure, admin centers, or enterprise products.
- When giving a self-serve solution that has an official
  Microsoft URL, include it in your reply naturally. Only
  include a URL when it directly helps resolve the issue.
  Do not include URLs when creating a ticket.
- Always include a helpful "reply" string.
- "needs_ticket" and "needs_description" must be JSON booleans,
  not text.
- Do not invent fields. Do not use values outside the valid lists.
{services_block}
Return ONLY valid JSON. Pick exactly ONE value per field - do not copy the lists below.
Valid service values: teams, outlook, onedrive, sharepoint, excel, word, powerpoint, windows, microsoft account, microsoft 365, unknown
Valid intent values: password_reset, sign_in, sync, crash, status, outage, escalation, email_delivery, permissions, device_setup, audio, video, display, printing, unknown
Valid priority values: low, medium, high
{{
  "service": "teams",
  "intent": "audio",
  "needs_ticket": false,
  "needs_description": false,
  "priority": "medium",
  "reply": "Go to: Settings > Privacy & security > Microphone and make sure microphone access is on. Then in Teams, go to: Settings > Devices and select the correct microphone."
}}
Example input: "yo my ondrive files aint syncing and it says pending forever"
Example JSON:
{{
  "service": "onedrive",
  "intent": "sync",
  "needs_ticket": false,
  "needs_description": false,
  "priority": "medium",
  "reply": "Open OneDrive, check that you are signed in to the right Microsoft account, then pause and resume sync. If the file still says pending, reopen OneDrive and check for sync errors."
}}
{history_block}
Detected service: {service_line}
{hardware_line}User message: {message}
"""


def _sanitize_choice(value, allowed_values, fallback):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed_values else fallback


def _sanitize_intent(value):
    normalized = str(value or "").strip().lower()
    normalized = _INTENT_ALIASES.get(normalized, normalized)
    return normalized if normalized in _ALLOWED_INTENTS else "unknown"


def _sanitize_result(raw_result, service_hint=None):
    if not isinstance(raw_result, dict):
        return None
    reply = str(raw_result.get("reply", "")).strip()
    if not reply and isinstance(raw_result.get("needs_description"), str):
        reply = raw_result.get("needs_description", "").strip()
    if not reply:
        return None
    service_fallback = (service_hint or "unknown").strip().lower()
    if service_fallback and service_fallback not in {"unknown", "microsoft 365"}:
        service = service_fallback
    else:
        service = _sanitize_choice(
            raw_result.get("service"),
            _ALLOWED_SERVICES | {"unknown"},
            service_fallback or "unknown",
        )
    intent = _sanitize_intent(raw_result.get("intent"))
    priority = _sanitize_choice(raw_result.get("priority"), _ALLOWED_PRIORITIES, "medium")
    return {
        "service": service,
        "intent": intent,
        "needs_ticket": bool(raw_result.get("needs_ticket", False)),
        "needs_description": bool(raw_result.get("needs_description", False)),
        "priority": priority,
        "reply": reply,
    }


def _request_ollama(prompt, model, timeout_seconds):
    payload = {
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
    }
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        OLLAMA_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def _is_timeout_error(error_msg):
    normalized = str(error_msg or "").strip().lower()
    return "timed out" in normalized or "timeout" in normalized


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
        _STATE[slot]["consecutive_failures"] = 0

    return sanitized, None


def generate_triage_response(message, service_hint=None, conversation_history=None,
                             hardware_term=None):
    if not OLLAMA_ENABLED:
        return None, "disabled"

    prompt = _build_prompt(
        message,
        service_hint=service_hint,
        conversation_history=conversation_history,
        hardware_term=hardware_term,
    )

    # --- Primary attempt ---
    with _LOCK:
        primary_failures = _STATE["primary"]["consecutive_failures"]
        primary_last_failed = _STATE["primary"]["last_failed_at"]
        primary_error = _STATE["primary"]["last_error"]

    in_cooldown = (
        primary_error is not None
        and (time.time() - primary_last_failed < OLLAMA_FAILURE_COOLDOWN_SECONDS)
    )

    # Still try primary unless it has failed 2+ consecutive times AND is in cooldown.
    # A single failure (consecutive_failures < 2) should not trigger failover.
    skip_primary = in_cooldown and primary_failures >= 2

    if not skip_primary:
        result, err = _try_model(
            prompt,
            "primary",
            OLLAMA_PRIMARY_MODEL,
            service_hint,
            OLLAMA_PRIMARY_TIMEOUT_SECONDS,
        )
        if result:
            return result, None

        if _is_timeout_error(err):
            print(
                f"[gemma_provider] Primary model ({OLLAMA_PRIMARY_MODEL}) timed out "
                f"after {OLLAMA_PRIMARY_TIMEOUT_SECONDS}s. Falling back to rules."
            )
            return None, err

        # Primary just failed - check whether we should escalate to failover
        with _LOCK:
            primary_failures = _STATE["primary"]["consecutive_failures"]

        if primary_failures < 2:
            # Single transient failure; let rule-based fallback in bot_logic handle it
            return None, err

    if not OLLAMA_FAILOVER_ENABLED:
        return None, (err if not skip_primary else primary_error) or "failover disabled"

    # --- Failover attempt (consecutive_failures >= 2 OR primary skipped) ---
    print(
        f"[gemma_provider] Primary model ({OLLAMA_PRIMARY_MODEL}) failed "
        f"{primary_failures}x - trying failover ({OLLAMA_FAILOVER_MODEL})"
    )
    result, err = _try_model(
        prompt,
        "failover",
        OLLAMA_FAILOVER_MODEL,
        service_hint,
        OLLAMA_FAILOVER_TIMEOUT_SECONDS,
    )
    if result:
        return result, None

    # Both models failed
    with _LOCK:
        p_err = _STATE["primary"]["last_error"]
        f_err = _STATE["failover"]["last_error"]
    print(f"[gemma_provider] Both models failed. Primary: {p_err} | Failover: {f_err}")
    return None, err


def gemma_runtime_status():
    with _LOCK:
        return {
            "enabled": OLLAMA_ENABLED,
            "primary_model": OLLAMA_PRIMARY_MODEL,
            "failover_model": OLLAMA_FAILOVER_MODEL,
            "primary_timeout_seconds": OLLAMA_PRIMARY_TIMEOUT_SECONDS,
            "failover_timeout_seconds": OLLAMA_FAILOVER_TIMEOUT_SECONDS,
            "failover_enabled": OLLAMA_FAILOVER_ENABLED,
            "primary_loaded": (
                _STATE["primary"]["has_succeeded"]
                and _STATE["primary"]["last_error"] is None
            ),
            "failover_loaded": (
                _STATE["failover"]["has_succeeded"]
                and _STATE["failover"]["last_error"] is None
            ),
            "primary_error": _STATE["primary"]["last_error"],
            "failover_error": _STATE["failover"]["last_error"],
            "provider": "ollama",
            "url": OLLAMA_URL,
        }
