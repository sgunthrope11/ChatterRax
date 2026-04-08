import re

try:
    from status_provider import check_microsoft_public_status
except ModuleNotFoundError:
    from .status_provider import check_microsoft_public_status


ESCALATION_TERMS = ("agent", "human", "ticket", "support", "representative", "person")
STATUS_TERMS = ("check status", "status", "health", "service health", "outage", "is there an issue")
OUTAGE_TERMS = ("down", "outage", "offline", "broken", "not working", "isn't working", "wont open", "won't open")

SERVICE_KEYWORDS = {
    "teams": ("teams", "microsoft teams", "meeting", "call", "chat"),
    "outlook": ("outlook", "exchange", "mail", "email", "inbox"),
    "onedrive": ("onedrive",),
    "sharepoint": ("sharepoint",),
    "excel": ("excel", "spreadsheet"),
    "word": ("word", "document"),
    "powerpoint": ("powerpoint", "presentation", "slides"),
    "windows": ("windows", "windows login", "windows sign in"),
    "microsoft account": ("microsoft account", "account", "signin", "sign in"),
    "microsoft 365": ("microsoft 365", "office 365", "office", "m365"),
}

UNSUPPORTED_STATUS_KEYWORDS = {
    "azure": ("azure",),
    "power platform admin center": ("power platform admin center",),
    "m365 enterprise": ("m365 enterprise", "microsoft 365 enterprise"),
    "m365 business": ("m365 business", "microsoft 365 business"),
}

INTENT_KEYWORDS = {
    "password_reset": ("password", "reset password", "forgot password", "credential"),
    "sign_in": ("login", "log in", "sign in", "signin", "access", "locked out"),
    "sync": ("sync", "syncing", "not updating", "not loading", "not loading", "not saving"),
    "crash": ("crash", "freezes", "frozen", "error", "failed"),
}

DETAIL_HINT_TERMS = ("error", "code", "when i", "after i", "trying to", "cannot", "can't", "fails", "failed")

SHORT_STEP_RESPONSES = {
    "password_reset": [
        "Step 1: Go to the Microsoft sign-in page and select Forgot password.",
        "Step 2: Complete the reset and then try signing in again.",
    ],
    "sign_in": [
        "Step 1: Try signing in to microsoft365.com to confirm whether the issue affects your whole Microsoft account.",
        "Step 2: If that also fails, use Microsoft's password reset page before trying again.",
    ],
    "sync": [
        "Step 1: Confirm you are signed in to the correct Microsoft account.",
        "Step 2: Refresh the app or reopen it and check whether the file or mailbox syncs again.",
    ],
    "crash": [
        "Step 1: Close the Microsoft app fully and reopen it.",
        "Step 2: If it crashes again, note the exact action and any error message you saw.",
    ],
}


def _normalize_message(message):
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def _term_in_text(text, term):
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _contains_any(text, terms):
    return any(_term_in_text(text, term) for term in terms)


def _detect_service(message):
    for service, keywords in SERVICE_KEYWORDS.items():
        if _contains_any(message, keywords):
            return service
    return "microsoft 365"


def _detect_unsupported_service(message):
    for service, keywords in UNSUPPORTED_STATUS_KEYWORDS.items():
        if _contains_any(message, keywords):
            return service
    return None


def _detect_intent(message):
    for intent, keywords in INTENT_KEYWORDS.items():
        if _contains_any(message, keywords):
            return intent
    return "unknown"


def _has_detailed_description(message):
    words = message.split()
    if len(words) >= 10:
        return True
    if _contains_any(message, DETAIL_HINT_TERMS):
        return True
    if re.search(r"\b[a-z]{2,}\d{2,}\b", message):
        return True
    return False


def _build_reply(lines):
    return " ".join(lines)


def _ask_for_ticket_details(service):
    return _build_reply([
        "I can create a ticket for you.",
        f"Please describe the {service} issue in more detail.",
        "Include what you were trying to do, what happened, and any error message you saw.",
    ])


def handle_message(message, awaiting_ticket_detail=False):
    msg = _normalize_message(message)
    service = _detect_service(msg)
    unsupported_service = _detect_unsupported_service(msg)
    intent = _detect_intent(msg)
    status_request = _contains_any(msg, STATUS_TERMS)
    escalation_requested = _contains_any(msg, ESCALATION_TERMS)
    outage_claim = _contains_any(msg, OUTAGE_TERMS)
    detailed_enough = _has_detailed_description(msg)

    response = {
        "resolved": False,
        "reply": "",
        "needs_ticket": False,
        "needs_description": False,
        "create_ticket": False,
        "service": service,
        "intent": intent,
        "priority": "medium",
        "status_checked": False,
        "status_summary": "",
        "escalation_requested": escalation_requested,
    }

    if unsupported_service:
        response.update({
            "resolved": True,
            "service": unsupported_service,
            "reply": (
                f"I do not support status or troubleshooting checks for {unsupported_service} in this bot. "
                "This bot is limited to consumer Microsoft products such as Teams, Outlook, OneDrive, Word, Excel, PowerPoint, Windows, and Microsoft account issues."
            ),
        })
        return response

    if awaiting_ticket_detail:
        if detailed_enough:
            response.update({
                "reply": "Thank you. I have enough detail to create your ticket now.",
                "needs_ticket": True,
                "create_ticket": True,
                "needs_description": False,
                "priority": "high" if outage_claim or "error" in msg else "medium",
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
            })
        return response

    if status_request or outage_claim:
        status_result = check_microsoft_public_status(service)
        response["status_checked"] = True
        response["status_summary"] = status_result["summary"]

        if status_request:
            response.update({
                "resolved": True,
                "reply": status_result["summary"],
            })
            return response

        if status_result["issue_found"]:
            response.update({
                "resolved": True,
                "reply": _build_reply([
                    status_result["summary"],
                    "If this is blocking your work, say ticket and I will start a support request.",
                ]),
            })
            return response

        if detailed_enough:
            response.update({
                "reply": _build_reply([
                    status_result["summary"],
                    "I will create a ticket so this can be reviewed directly.",
                ]),
                "needs_ticket": True,
                "create_ticket": True,
                "priority": "high",
            })
        else:
            response.update({
                "reply": _build_reply([
                    status_result["summary"],
                    "I can create a ticket for this.",
                    "Please describe exactly what happens when you try to use it.",
                ]),
                "needs_ticket": True,
                "needs_description": True,
                "priority": "high",
            })
        return response

    if escalation_requested:
        if detailed_enough:
            response.update({
                "reply": "I understand. I have enough detail to create your ticket now.",
                "needs_ticket": True,
                "create_ticket": True,
                "priority": "medium",
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
                "priority": "medium",
            })
        return response

    if intent in SHORT_STEP_RESPONSES:
        reply_lines = list(SHORT_STEP_RESPONSES[intent])
        reply_lines.append("If that does not help, say ticket and I will start a support request.")
        response.update({
            "resolved": True,
            "reply": _build_reply(reply_lines),
        })
        return response

    if detailed_enough:
        response.update({
            "reply": _build_reply([
                "I am not confident enough to troubleshoot this further from the chat alone.",
                "I can create a ticket so this can be reviewed directly.",
            ]),
            "needs_ticket": True,
            "create_ticket": True,
            "priority": "medium",
        })
        return response

    response.update({
        "reply": _build_reply([
            "Please tell me which Microsoft app is affected and what happens when you try to use it.",
            "If you want support right away, say ticket and I will start that process.",
        ]),
        "needs_description": True,
    })
    return response
