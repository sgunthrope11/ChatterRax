"""
Static support link router for ChatterRax. Maps detected service and intent to the most
relevant official Microsoft support URL and returns it with a helpful human-feeling
message. No scraping, page fetching, browser automation, or search API calls.
"""

import json
import os
import time
from pathlib import Path


# SUPPORT_LINK_ROUTER_* names are preferred. LIVE_RETRIEVAL_* is still honored
# so older local .env files keep working without another setup step.
ROUTER_CACHE_TTL_SECONDS = int(
    os.getenv(
        "SUPPORT_LINK_ROUTER_CACHE_SECONDS",
        os.getenv("LIVE_RETRIEVAL_CACHE_SECONDS", "86400"),
    )
)
MIN_SECONDS_BETWEEN_LINK_RESPONSES = int(
    os.getenv(
        "SUPPORT_LINK_ROUTER_RATE_LIMIT_SECONDS",
        os.getenv("LIVE_RETRIEVAL_RATE_LIMIT_SECONDS", "30"),
    )
)

_SEARCH_CACHE = {}
_LAST_LINK_RESPONSE_AT = 0.0
_ROOT_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT_DIR / "data"
SUPPORT_LINK_CACHE_PATH = Path(
    os.getenv(
        "SUPPORT_LINK_ROUTER_CACHE_PATH",
        os.getenv("LIVE_RETRIEVAL_CACHE_PATH", _DATA_DIR / "support_link_cache.json"),
    )
)


# ============================================================
# Support link master dictionary - keyed by (service, intent)
# ============================================================

SUPPORT_LINKS = {
    # Teams
    ("teams", "sign_in"):        "https://support.microsoft.com/en-us/office/how-to-log-in-to-microsoft-teams-ea4b1443-d11b-4791-8ae1-9977e7723055",
    ("teams", "crash"):          "https://support.microsoft.com/en-us/teams",
    ("teams", "sync"):           "https://support.microsoft.com/en-us/teams",
    ("teams", "notification"):   "https://support.microsoft.com/en-us/office/manage-notifications-in-microsoft-teams-1cc31834-5fe5-412b-8edb-43fecc78413d",
    ("teams", "performance"):    "https://support.microsoft.com/en-us/teams",
    ("teams", "activation"):     "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("teams", "unknown"):        "https://support.microsoft.com/en-us/teams",

    # Outlook
    ("outlook", "sign_in"):       "https://support.microsoft.com/en-us/office/sign-in-to-microsoft-365-b9582171-fd1f-4284-9846-bdd72bb28426",
    ("outlook", "crash"):         "https://support.microsoft.com/en-us/office/outlook-for-windows-not-responding-hangs-freezes-or-stops-working-241bb0fc-b201-4bb2-98d3-74750a27029e",
    ("outlook", "sync"):          "https://support.microsoft.com/en-us/office/issues-sending-and-receiving-email-ba6bda48-3417-4600-b36e-04952bbf5b80",
    ("outlook", "email_delivery"): "https://support.microsoft.com/en-us/office/issues-sending-and-receiving-email-ba6bda48-3417-4600-b36e-04952bbf5b80",
    ("outlook", "notification"):  "https://support.microsoft.com/en-us/office/turn-new-message-alert-pop-up-on-or-off-in-outlook-9940c70e-b306-442e-a856-d94b20318481",
    ("outlook", "performance"):   "https://support.microsoft.com/en-us/office/outlook-for-windows-not-responding-hangs-freezes-or-stops-working-241bb0fc-b201-4bb2-98d3-74750a27029e",
    ("outlook", "activation"):    "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("outlook", "calendar"):      "https://support.microsoft.com/en-us/office/introduction-to-the-outlook-calendar-d94c5203-77c7-48ec-90a5-2e2bc10bd6f8",
    ("outlook", "unknown"):       "https://support.microsoft.com/en-us/outlook",

    # OneDrive
    ("onedrive", "sync"):         "https://support.microsoft.com/en-us/office/fix-onedrive-sync-problems-0899b115-05f7-45ec-95b2-e4cc8c4670b2",
    ("onedrive", "sign_in"):      "https://support.microsoft.com/en-us/office/can-t-sign-in-to-onedrive-3f99e6e3-042e-49a3-897a-8b7fb0fb8477",
    ("onedrive", "crash"):        "https://support.microsoft.com/en-us/office/fix-onedrive-sync-problems-0899b115-05f7-45ec-95b2-e4cc8c4670b2",
    ("onedrive", "performance"):  "https://support.microsoft.com/en-us/office/fix-onedrive-sync-problems-0899b115-05f7-45ec-95b2-e4cc8c4670b2",
    ("onedrive", "unknown"):      "https://support.microsoft.com/en-us/onedrive",

    # SharePoint
    ("sharepoint", "sign_in"):    "https://support.microsoft.com/en-us/office/share-sharepoint-files-or-folders-1fe37332-0f9a-4719-970e-d2578da4941c",
    ("sharepoint", "sync"):       "https://support.microsoft.com/en-us/office/fix-onedrive-sync-problems-0899b115-05f7-45ec-95b2-e4cc8c4670b2",
    ("sharepoint", "crash"):      "https://support.microsoft.com/en-us/sharepoint",
    ("sharepoint", "unknown"):    "https://support.microsoft.com/en-us/sharepoint",

    # Excel
    ("excel", "crash"):           "https://support.microsoft.com/en-us/office/excel-not-responding-hangs-freezes-or-stops-working-37e7d3c9-9e84-40bf-a805-4ca6853a1ff4",
    ("excel", "sync"):            "https://support.microsoft.com/en-us/office/save-your-workbook-to-onedrive-in-excel-0cf0055d-49f8-464e-9dfa-8f582b32453b",
    ("excel", "activation"):      "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("excel", "performance"):     "https://support.microsoft.com/en-us/office/excel-not-responding-hangs-freezes-or-stops-working-37e7d3c9-9e84-40bf-a805-4ca6853a1ff4",
    ("excel", "unknown"):         "https://support.microsoft.com/en-us/excel",

    # Word
    ("word", "crash"):            "https://support.microsoft.com/en-us/office/i-get-a-stopped-working-error-when-i-start-office-applications-on-my-pc-52bd7985-4e99-4a35-84c8-2d9b8301a2fa",
    ("word", "sync"):             "https://support.microsoft.com/en-us/office/save-your-document-to-onedrive-in-word-d7c23ed3-a80a-4ff4-ade5-91211a7614f3",
    ("word", "activation"):       "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("word", "performance"):      "https://support.microsoft.com/en-us/office/i-get-a-stopped-working-error-when-i-start-office-applications-on-my-pc-52bd7985-4e99-4a35-84c8-2d9b8301a2fa",
    ("word", "unknown"):          "https://support.microsoft.com/en-us/word",

    # PowerPoint
    ("powerpoint", "crash"):      "https://support.microsoft.com/en-us/office/powerpoint-isn-t-responding-hangs-or-freezes-652ede6e-e3d2-449a-a07f-8c800dfb948d",
    ("powerpoint", "activation"): "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("powerpoint", "performance"): "https://support.microsoft.com/en-us/office/powerpoint-isn-t-responding-hangs-or-freezes-652ede6e-e3d2-449a-a07f-8c800dfb948d",
    ("powerpoint", "unknown"):    "https://support.microsoft.com/en-us/powerpoint",

    # Windows
    ("windows", "sign_in"):       "https://support.microsoft.com/en-us/windows/sign-in-options-in-windows-8ae09c04-c5da-41c9-972f-b126a13d18a8",
    ("windows", "crash"):         "https://support.microsoft.com/en-us/windows/troubleshooting-windows-unexpected-restarts-and-stop-code-errors-60b01860-58f2-be66-7516-5c45a66ae3c6",
    ("windows", "update"):        "https://support.microsoft.com/en-us/windows/windows-update-troubleshooter-19bc41ca-ad72-ae67-af3c-89ce169755dd",
    ("windows", "performance"):   "https://support.microsoft.com/en-us/windows/tips-to-improve-pc-performance-in-windows-b3b3ef5b-5953-fb6a-2528-4bbed82fba96",
    ("windows", "notification"):  "https://support.microsoft.com/en-us/windows/notifications-and-do-not-disturb-in-windows-feeca47f-0baf-5680-16f0-8801db1a8466",
    ("windows", "unknown"):       "https://support.microsoft.com/en-us/windows",

    # Microsoft Account
    ("microsoft account", "sign_in"):        "https://support.microsoft.com/en-us/account-billing/i-can-t-sign-in-to-my-microsoft-account-475c9b5c-8c25-49f1-9c2d-c64b7072e735",
    ("microsoft account", "password_reset"): "https://support.microsoft.com/en-us/account-billing/reset-a-forgotten-microsoft-account-password-eff4f067-5042-c1a3-fe72-b04d60556c37",
    ("microsoft account", "unknown"):        "https://support.microsoft.com/en-us/account-billing/get-help-with-your-microsoft-account-ace6f3b3-e2d3-aeb1-6b96-d2e9e7e52133",

    # Microsoft 365
    ("microsoft 365", "activation"): "https://support.microsoft.com/en-us/office/activate-office-for-windows-5bd38f38-db92-448b-a982-ad170b1e187e",
    ("microsoft 365", "sign_in"):    "https://support.microsoft.com/en-us/office/sign-in-to-microsoft-365-b9582171-fd1f-4284-9846-bdd72bb28426",
    ("microsoft 365", "crash"):      "https://support.microsoft.com/en-us/office/i-get-a-stopped-working-error-when-i-start-office-applications-on-my-pc-52bd7985-4e99-4a35-84c8-2d9b8301a2fa",
    ("microsoft 365", "unknown"):    "https://support.microsoft.com/en-us/microsoft-365",

    # Status fallback
    ("status", "unknown"): "https://status.cloud.microsoft/",
}

# ============================================================
# Service-level fallback links - used when intent has no match
# ============================================================

SERVICE_FALLBACK_LINKS = {
    "teams":             "https://support.microsoft.com/en-us/teams",
    "outlook":           "https://support.microsoft.com/en-us/outlook",
    "onedrive":          "https://support.microsoft.com/en-us/onedrive",
    "sharepoint":        "https://support.microsoft.com/en-us/sharepoint",
    "excel":             "https://support.microsoft.com/en-us/excel",
    "word":              "https://support.microsoft.com/en-us/word",
    "powerpoint":        "https://support.microsoft.com/en-us/powerpoint",
    "windows":           "https://support.microsoft.com/en-us/windows",
    "microsoft account": "https://support.microsoft.com/en-us/account-billing/get-help-with-your-microsoft-account-ace6f3b3-e2d3-aeb1-6b96-d2e9e7e52133",
    "microsoft 365":     "https://support.microsoft.com/en-us/microsoft-365",
}

# ============================================================
# Reply variants - picked deterministically by message hash
# ============================================================

LINK_REPLY_VARIANTS = (
    "I did not find a specific fix in my local knowledge for that {service_label} issue, but here is the official Microsoft support page that covers it: {url} - Work through it and let me know if you hit a step that does not match what you see.",
    "Here is the Microsoft support page most relevant to that {service_label} issue: {url} - If the steps there do not line up with what you are seeing, tell me what screen you land on and I will adjust.",
    "My local knowledge does not have a step-by-step for that exact {service_label} scenario, but this official page should cover it: {url} - Try it and come back if any step does not match or you hit a new error.",
    "The closest official Microsoft resource for that {service_label} issue is here: {url} - Go through it in order and let me know which step you get stuck on if it does not resolve.",
    "For that {service_label} issue, this is the Microsoft support page that will get you furthest: {url} - If it does not resolve after working through it, say ticket and I will get the right details for support.",
    "I am routing you to the best official {service_label} support page for that: {url} - If any step looks different on your end, send me the exact wording and I will help you navigate it.",
    "That {service_label} issue has a dedicated Microsoft support page here: {url} - Work through the steps and let me know if something does not match what you see, or if a new error appears.",
    "Here is the most relevant Microsoft support page for your {service_label} issue: {url} - If you need hands-on help after trying it, say ticket and I will collect the details.",
)


# ============================================================
# Cache helpers
# ============================================================

def _cache_get(key):
    item = _SEARCH_CACHE.get(key)
    if not item:
        item = _persistent_cache_read().get(key)
        if item:
            _SEARCH_CACHE[key] = item
    if not item:
        return None
    if time.time() - item["created_at"] > ROUTER_CACHE_TTL_SECONDS:
        _SEARCH_CACHE.pop(key, None)
        return None
    value = dict(item["value"])
    value["from_cache"] = True
    return value


def _cache_set(key, value):
    _SEARCH_CACHE[key] = {
        "created_at": time.time(),
        "value": value,
    }
    persistent = _persistent_cache_read()
    persistent[key] = _SEARCH_CACHE[key]
    if len(persistent) > 128:
        sorted_items = sorted(
            persistent.items(),
            key=lambda item: item[1].get("created_at", 0),
        )
        persistent = dict(sorted_items[-128:])
    _persistent_cache_write(persistent)


def _persistent_cache_read():
    if not SUPPORT_LINK_CACHE_PATH.exists():
        return {}
    try:
        with SUPPORT_LINK_CACHE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _persistent_cache_write(data):
    SUPPORT_LINK_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = SUPPORT_LINK_CACHE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    os.replace(temp_path, SUPPORT_LINK_CACHE_PATH)


# ============================================================
# Rate limiting
# ============================================================

def _link_response_rate_limited():
    global _LAST_LINK_RESPONSE_AT
    now = time.time()
    if now - _LAST_LINK_RESPONSE_AT < MIN_SECONDS_BETWEEN_LINK_RESPONSES:
        return True
    _LAST_LINK_RESPONSE_AT = now
    return False


# ============================================================
# Public API
# ============================================================

def support_link_routing_enabled():
    explicit = os.getenv("SUPPORT_LINK_ROUTER_ENABLED")
    if explicit is not None:
        return explicit.strip().lower() == "true"
    return os.getenv("LIVE_RETRIEVAL_ENABLED", "false").strip().lower() == "true"


def retrieve_support_link_plan(message, service_hint=None, intent_hint=None):
    if not support_link_routing_enabled():
        return {
            "found": False,
            "reason": "disabled",
            "reply": "",
            "confidence": 0.0,
            "from_cache": False,
        }

    cache_key = f"{service_hint}|{intent_hint}|{str(message or '')[:120]}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    if _link_response_rate_limited():
        return {
            "found": False,
            "reason": "rate_limited",
            "reply": "",
            "confidence": 0.0,
            "from_cache": False,
        }

    # Resolve URL: exact tuple match -> (service, "unknown") -> service fallback -> absolute fallback
    url = SUPPORT_LINKS.get((service_hint, intent_hint))
    if not url:
        url = SUPPORT_LINKS.get((service_hint, "unknown"))
    if not url:
        url = SERVICE_FALLBACK_LINKS.get(service_hint or "")
    if not url:
        url = "https://support.microsoft.com/en-us"

    service_label = _service_label_for(service_hint)

    index = sum(ord(c) for c in str(message or "")) % len(LINK_REPLY_VARIANTS)
    reply = LINK_REPLY_VARIANTS[index].format(service_label=service_label, url=url)

    result = {
        "found": True,
        "reply": reply,
        "confidence": 0.35,
        "from_cache": False,
        "reason": "low_confidence_fallback",
        "source_url": url,
        "learned": False,
    }
    _cache_set(cache_key, result)
    return result


def _service_label_for(service_hint):
    labels = {
        "teams":             "Teams",
        "outlook":           "Outlook",
        "onedrive":          "OneDrive",
        "sharepoint":        "SharePoint",
        "excel":             "Excel",
        "word":              "Word",
        "powerpoint":        "PowerPoint",
        "windows":           "Windows",
        "microsoft account": "Microsoft account",
        "microsoft 365":     "Microsoft 365",
    }
    return labels.get(service_hint or "", "Microsoft 365")
