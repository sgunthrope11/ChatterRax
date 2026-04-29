import json
import os
import re
import time
from pathlib import Path

try:
    from providers.knowledge_resources_expanded import EXPANDED_KNOWLEDGE_RESOURCES
    from providers.knowledge_resources_boost import ADDITIONAL_KNOWLEDGE_RESOURCES
    from providers.knowledge_resources_it_expanded import IT_KNOWLEDGE_RESOURCES
except ImportError:
    from .knowledge_resources_expanded import EXPANDED_KNOWLEDGE_RESOURCES
    from .knowledge_resources_boost import ADDITIONAL_KNOWLEDGE_RESOURCES
    from .knowledge_resources_it_expanded import IT_KNOWLEDGE_RESOURCES

from triage_core.domain_config import (
    DEFAULT_SERVICE,
    domain_knowledge_resources,
    load_domain_packs,
    service_names,
)


CACHE_TTL_SECONDS = 900
MAX_CACHE_ITEMS = 64
MIN_CONFIDENCE = 0.58

_CACHE = {}
_ROOT_DIR = Path(__file__).resolve().parent.parent
_DATA_DIR = _ROOT_DIR / "data"
LEARNED_KNOWLEDGE_PATH = Path(
    os.getenv("LEARNED_KNOWLEDGE_PATH", _DATA_DIR / "learned_knowledge.json")
)
DOMAIN_PACK = load_domain_packs()
DOMAIN_DEFAULT_SERVICE = DOMAIN_PACK.get("default_service") or DEFAULT_SERVICE
if DOMAIN_DEFAULT_SERVICE == "microsoft 365":
    BROAD_SERVICE_HINT_SERVICES = {
        "outlook", "teams", "onedrive", "sharepoint", "word", "excel",
        "powerpoint", "microsoft account",
    }
else:
    BROAD_SERVICE_HINT_SERVICES = service_names(DOMAIN_PACK) - {DOMAIN_DEFAULT_SERVICE}


BUILTIN_KNOWLEDGE_RESOURCES = (
    {
        "id": "outlook_delivery_domain",
        "service": "outlook",
        "intent": "email_delivery",
        "title": "Outlook message returned or recipient domain error",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "outlook", "email", "mail", "send", "sent", "returned",
            "sent back", "came back", "bounce", "bounced", "undeliverable",
            "domain", "domain does not exist", "domain not found",
            "recipient", "delivery", "address",
        ),
        "steps": (
            "Check the recipient address for typos, extra spaces, or a misspelled domain after the @ symbol.",
            "Try sending the same message from Outlook on the web at outlook.com or microsoft365.com.",
            "If Outlook on the web also fails, ask the recipient to confirm the correct address or send you a fresh message to reply to.",
            "If the message still returns, copy the full bounce-back text so support can check the recipient domain and mail routing.",
        ),
    },
    {
        "id": "teams_audio_devices",
        "service": "teams",
        "intent": "unknown",
        "title": "Teams microphone, speaker, or meeting audio issue",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "teams", "meeting", "call", "microphone", "mic", "camera",
            "speaker", "audio", "sound", "hear me", "cant hear",
            "can't hear", "mute", "muted", "device",
            "teems", "meetin", "nobody hears", "nobody hears me",
            "they cant hear", "nobody can hear", "my mic", "im muted",
            "silent", "cant hear me",
        ),
        "steps": (
            "Go to: Settings > System > Sound and confirm the correct Input or Output device is selected.",
            "Go to: Settings > Privacy & security > Microphone or Camera and confirm app access is turned on.",
            "In Teams, go to: Settings > Devices and choose the correct microphone, speaker, and camera.",
            "Test in the meeting after changing devices however if it does not work leave and rejoin so Teams refreshes the audio session.",
        ),
    },
    {
        "id": "outlook_mailbox_sync_search",
        "service": "outlook",
        "intent": "sync",
        "title": "Outlook inbox, mailbox sync, or missing mail issue",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "outlook", "email", "emails", "mail", "inbox", "mailbox",
            "missing", "not loading", "not updating", "sync", "search",
            "old mail", "old email", "messages", "folder",
            "outluk", "outlok", "zero results", "hasnt loaded", "serach",
            "nothing comes up", "searched", "no mail", "messages gone",
        ),
        "steps": (
            "Try Outlook on the web at outlook.com or microsoft365.com to confirm whether the mail is missing from the account or only the app.",
            "In Outlook, check the current folder, focused inbox, filters, and search terms.",
            "Refresh or restart Outlook, then check whether new mail appears.",
            "If Outlook on the web has the mail but the desktop app does not, the desktop mailbox cache may need repair or resync.",
        ),
    },
    {
        "id": "onedrive_sync_pending",
        "service": "onedrive",
        "intent": "sync",
        "title": "OneDrive sync stuck, pending, or not uploading",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "onedrive", "one drive", "one drv", "sync", "syncing",
            "pending", "upload", "download", "cloud", "files",
            "stuck", "not updating", "not uploading",
            "ondrive", "uploadin", "not syncing up", "pending upload",
            "nothing is syncing", "wont upload", "sync stuck",
        ),
        "steps": (
            "Select the OneDrive cloud icon and confirm you are signed in with the correct Microsoft account.",
            "Pause syncing, wait a few seconds, then resume syncing from the OneDrive cloud icon.",
            "Check the OneDrive activity panel for file-specific errors such as invalid characters, long paths, or permission problems.",
            "If only one file is stuck, rename it or move it to a shorter folder path, then let OneDrive retry.",
        ),
    },
    {
        "id": "windows_display_detect",
        "service": "windows",
        "intent": "unknown",
        "title": "Windows second monitor or display not detected",
        "source": "Local Windows support playbook",
        "keywords": (
            "windows", "monitor", "screen", "display", "second monitor",
            "second screen", "external monitor", "dock", "docking station",
            "usb c", "usb-c", "hdmi", "displayport", "not detected",
        ),
        "steps": (
            "Confirm the monitor is powered on and set to the correct input source.",
            "Reconnect the cable or dock, then press Windows + P and choose Extend or Duplicate.",
            "Go to: Settings > System > Display > Multiple displays and select Detect.",
            "If the display still does not appear, open Device Manager and check for display adapter or USB-C dock warnings.",
        ),
    },
    {
        "id": "camera_permission",
        "service": "teams",
        "intent": "unknown",
        "title": "Camera blocked by app, browser, or Windows permissions",
        "source": "Local Windows and Teams support playbook",
        "keywords": (
            "camera", "webcam", "cam", "blocked", "permission",
            "permissions", "privacy", "browser", "teams", "allow",
            "teems", "permision", "shows black", "black screen",
            "camera blocked", "camera not working", "in use by another",
            "camera permission", "video blocked", "cant see camera",
        ),
        "steps": (
            "Go to: Settings > Privacy & security > Camera and turn on camera access.",
            "Confirm the browser or desktop app is allowed to use the camera.",
            "If using a browser, select the lock icon near the address bar and allow camera access for the site.",
            "Open the app's device settings and select the correct camera.",
        ),
    },
    {
        "id": "bluetooth_audio_pairing",
        "service": "windows",
        "intent": "unknown",
        "title": "Bluetooth headset, speaker, keyboard, or mouse will not connect",
        "source": "Local Windows support playbook",
        "keywords": (
            "bluetooth", "headphones", "headset", "speaker", "keyboard",
            "mouse", "pair", "paired", "connect", "connected", "wireless",
            "disconnectin", "keeps dropping", "drops", "randomly drops",
            "keeps disconnecting", "drops connection", "disconnecting",
            "random disconnect", "bluetooth drops", "headset disconnects",
        ),
        "steps": (
            "Go to: Settings > Bluetooth & devices and confirm Bluetooth is turned on.",
            "Remove the device from Bluetooth devices, then put it back in pairing mode.",
            "Pair the device again and confirm it shows as connected.",
            "For audio devices, go to: Settings > System > Sound and select the device under Output or Input.",
        ),
    },
    {
        "id": "printer_scanner_missing",
        "service": "windows",
        "intent": "unknown",
        "title": "Printer or scanner missing in Windows",
        "source": "Local Windows support playbook",
        "keywords": (
            "printer", "print", "scanner", "scan", "not found",
            "missing", "offline", "printers", "scanners",
            "disapeared", "disappeared", "vanished", "not showing up",
            "gone from list", "cant print", "printer gone", "printer missing",
            "printer vanished", "printer offline", "print not working",
        ),
        "steps": (
            "Confirm the printer or scanner is powered on and connected to the same network or cable.",
            "Go to: Settings > Bluetooth & devices > Printers & scanners.",
            "Remove the device if it is stuck or offline, then add it again.",
            "If Windows still cannot find it, check Windows Update or the manufacturer's driver utility.",
        ),
    },
    {
        "id": "usb_drive_missing",
        "service": "windows",
        "intent": "crash",
        "title": "USB drive not showing in File Explorer",
        "source": "Local Windows support playbook",
        "keywords": (
            "usb", "usb drive", "flash drive", "thumb drive", "external drive",
            "file explorer", "drive letter", "not showing", "not detected",
            "not showin up", "explrer", "doesnt show up", "drive not showing",
            "flash drive not showing", "usb not showing", "drive not found",
            "drive missing", "not recognized", "light is on",
        ),
        "steps": (
            "Try a different USB port and reconnect the drive.",
            "Open File Explorer and check whether Windows assigned the drive a letter.",
            "Open Device Manager and check for USB or disk drive warning icons.",
            "If the drive appears in Disk Management but not File Explorer, it may need a drive letter assigned.",
        ),
    },
    {
        "id": "sharepoint_access_denied",
        "service": "sharepoint",
        "intent": "sign_in",
        "title": "SharePoint file or site says access denied",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "sharepoint", "share point", "access denied", "permission",
            "permissions", "file", "site", "link", "cannot access",
            "sharepoiint", "sharepiont", "shaepoint", "acess denied",
            "permision", "no access", "cant access", "need access",
            "get permission", "denied",
        ),
        "steps": (
            "Open the SharePoint link in a browser and confirm you are signed in with the correct Microsoft account.",
            "Try opening the file from the SharePoint site instead of an old shared link.",
            "If it still says access denied, ask the owner to share it again or verify your permissions.",
            "If other users also cannot access it, the owner or admin should check site permissions.",
        ),
    },
    {
        "id": "office_app_crash",
        "service": "microsoft 365",
        "intent": "crash",
        "title": "Office app crashing, freezing, or failing to open",
        "source": "Local Microsoft 365 support playbook",
        "keywords": (
            "word", "excel", "powerpoint", "office", "crash", "crashing",
            "freeze", "frozen", "not responding", "error", "wont open",
            "won't open", "save failed",
            "crashin", "freezin", "keeps crashin", "keeps freezin", "wont respond",
            "randomly crashing", "randomly freezing", "keeps crashing",
            "keeps freezing", "crashes n freezes", "freezes randomly",
        ),
        "steps": (
            "Close the Office app fully and reopen it from the Start menu.",
            "Try opening the file from File > Open instead of double-clicking it.",
            "If only one file fails, save a copy to Desktop or OneDrive and try opening the copy.",
            "If every Office app fails, restart Windows and check for Office updates.",
        ),
    },
    {
        "id": "microsoft_account_sign_in",
        "service": "microsoft account",
        "intent": "sign_in",
        "title": "Microsoft account sign-in, password, or Authenticator issue",
        "source": "Local Microsoft account support playbook",
        "keywords": (
            "microsoft account", "ms account", "sign in", "signin", "login",
            "password", "authenticator", "verification code", "security code",
            "2fa", "locked out", "wrong password",
            "pasword", "acunt", "failin", "wont accept", "keeps sayin",
            "microsoft acunt", "cant sign in", "password wrong", "signin failing",
            "microsft account", "microsoft acct",
        ),
        "steps": (
            "Try signing in at microsoft365.com to confirm whether the issue affects the whole account.",
            "If the password is not accepted, use the Forgot password option on the Microsoft sign-in page.",
            "If Authenticator does not prompt, choose another verification method if available.",
            "If no verification method works, use account recovery or create a support ticket with the exact sign-in message.",
        ),
    },
) + EXPANDED_KNOWLEDGE_RESOURCES + ADDITIONAL_KNOWLEDGE_RESOURCES + IT_KNOWLEDGE_RESOURCES

DOMAIN_KNOWLEDGE_RESOURCES = domain_knowledge_resources(DOMAIN_PACK)
if DOMAIN_PACK.get("replace_builtin_knowledge"):
    KNOWLEDGE_RESOURCES = DOMAIN_KNOWLEDGE_RESOURCES
else:
    KNOWLEDGE_RESOURCES = BUILTIN_KNOWLEDGE_RESOURCES + DOMAIN_KNOWLEDGE_RESOURCES


def _safe_load_learned_resources():
    if not LEARNED_KNOWLEDGE_PATH.exists():
        return []
    try:
        with LEARNED_KNOWLEDGE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []

    resources = data if isinstance(data, list) else data.get("resources", [])
    cleaned = []
    for resource in resources:
        if not isinstance(resource, dict):
            continue
        if not resource.get("id") or not resource.get("steps"):
            continue
        cleaned.append({
            "id": str(resource.get("id")),
            "service": str(resource.get("service") or "microsoft 365"),
            "intent": str(resource.get("intent") or "unknown"),
            "title": str(resource.get("title") or "Microsoft support article"),
            "source": str(resource.get("source") or "Learned Microsoft support memory"),
            "source_url": str(resource.get("source_url") or ""),
            "keywords": tuple(str(term) for term in resource.get("keywords", []) if term),
            "required_any": tuple(
                tuple(str(term) for term in group if term)
                for group in resource.get("required_any", [])
                if group
            ),
            "steps": tuple(str(step) for step in resource.get("steps", []) if step),
            "advanced_steps": tuple(str(step) for step in resource.get("advanced_steps", []) if step),
            "learned": True,
            "created_at": resource.get("created_at"),
        })
    return cleaned


def get_all_knowledge_resources():
    if DOMAIN_PACK.get("replace_builtin_knowledge") and not DOMAIN_PACK.get("include_learned_knowledge"):
        return tuple(KNOWLEDGE_RESOURCES)
    return tuple(KNOWLEDGE_RESOURCES) + tuple(_safe_load_learned_resources())


def _read_learned_file():
    if not LEARNED_KNOWLEDGE_PATH.exists():
        return []
    try:
        with LEARNED_KNOWLEDGE_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return []
    return data if isinstance(data, list) else data.get("resources", [])


def _write_learned_file(resources):
    LEARNED_KNOWLEDGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = LEARNED_KNOWLEDGE_PATH.with_suffix(".tmp")
    with temp_path.open("w", encoding="utf-8") as file:
        json.dump({"resources": resources}, file, indent=2)
    os.replace(temp_path, LEARNED_KNOWLEDGE_PATH)


def add_learned_resource(resource):
    """
    Persist a high-confidence official-source result for future sessions.
    Only sanitized keywords and official source metadata should be passed here.
    """
    if not resource.get("id") or not resource.get("steps"):
        return False

    learned = _read_learned_file()
    existing_ids = {item.get("id") for item in learned if isinstance(item, dict)}
    if resource["id"] in existing_ids:
        return False

    learned.append({
        "id": str(resource["id"]),
        "service": str(resource.get("service") or "microsoft 365"),
        "intent": str(resource.get("intent") or "unknown"),
        "title": str(resource.get("title") or "Microsoft support article"),
        "source": str(resource.get("source") or "Official Microsoft support"),
        "source_url": str(resource.get("source_url") or ""),
        "keywords": list(resource.get("keywords") or ()),
        "required_any": [list(group) for group in resource.get("required_any", [])],
        "steps": list(resource.get("steps") or ()),
        "advanced_steps": list(resource.get("advanced_steps") or ()),
        "created_at": int(time.time()),
    })
    _write_learned_file(learned[-128:])
    return True


def _normalize(text):
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def sanitize_query(message):
    text = _normalize(message)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.\w+\b", "[email]", text)
    text = re.sub(r"https?://\S+", "[url]", text)
    text = re.sub(r"\b[\w.-]+\.(com|net|org|edu|gov|io|co)\b", "[domain]", text)
    text = re.sub(r"\b\d{4,}\b", "[number]", text)
    return text


def _term_in_text(text, term):
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _required_group_matches(query, group, service_hint=None):
    for term in group:
        normalized = str(term or "").strip().lower()
        if not normalized:
            continue
        if _term_in_text(query, normalized):
            return True
        if service_hint and normalized == str(service_hint).strip().lower():
            return True
    return False


def _score_resource(query, resource, service_hint=None, intent_hint=None):
    if (
        service_hint
        and service_hint != DOMAIN_DEFAULT_SERVICE
        and resource.get("service") != service_hint
    ):
        return 0.0, []

    required_groups = resource.get("required_any") or ()
    for group in required_groups:
        terms = group if isinstance(group, (tuple, list, set)) else (group,)
        if not _required_group_matches(query, terms, service_hint=service_hint):
            return 0.0, []

    keywords = resource["keywords"]
    matched = [term for term in keywords if _term_in_text(query, term)]
    if not matched:
        return 0.0, []

    score = 0.0
    score += min(0.45, len(matched) * 0.075)

    longest_match = max((len(term.split()) for term in matched), default=1)
    if longest_match >= 3:
        score += 0.18
    elif longest_match == 2:
        score += 0.10

    if service_hint and service_hint == resource["service"]:
        score += 0.20
    elif service_hint == DOMAIN_DEFAULT_SERVICE and resource["service"] in BROAD_SERVICE_HINT_SERVICES:
        score += 0.05

    if intent_hint and intent_hint == resource["intent"]:
        score += 0.15

    if resource["service"] in matched:
        score += 0.07

    if required_groups:
        score += 0.04

    return min(score, 0.99), matched


def _cache_get(key):
    entry = _CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["created_at"] > CACHE_TTL_SECONDS:
        _CACHE.pop(key, None)
        return None
    return entry["value"]


def _cache_set(key, value):
    if len(_CACHE) >= MAX_CACHE_ITEMS:
        oldest_key = min(_CACHE, key=lambda item: _CACHE[item]["created_at"])
        _CACHE.pop(oldest_key, None)
    _CACHE[key] = {
        "created_at": time.time(),
        "value": value,
    }


def _format_plan(resources):
    primary = resources[0]
    seed = sum(ord(char) for char in str(primary.get("id") or primary.get("title") or "kb"))
    openers = (
        f"This lines up with {primary['title']}.",
        f"I am matching this to {primary['title']}.",
        f"The closest local playbook is {primary['title']}.",
        f"That pattern fits {primary['title']}.",
    )
    headers = (
        "Try the safest checks first:",
        "Work through these in order:",
        "Start with these low-risk checks:",
        "Use this path first:",
    )
    lines = [
        openers[seed % len(openers)],
        headers[seed % len(headers)],
    ]

    seen_steps = set()
    step_number = 1
    for resource in resources:
        resource_steps = list(resource["steps"]) + list(resource.get("advanced_steps") or ())
        for step in resource_steps:
            if step in seen_steps:
                continue
            seen_steps.add(step)
            lines.append(f"{step_number}. {step}")
            step_number += 1
            if step_number > 6:
                break
        if step_number > 6:
            break

    wrap_ups = (
        "If your screen looks different, send me the exact wording you see and I will adjust the path.",
        "If the wording differs, send me the exact prompt or code and I will narrow the next step.",
        "If it still fails after these checks, the exact error text will decide whether this needs a ticket.",
        "If the first path does not match what you see, tell me the app screen and message so I can pivot.",
    )
    lines.append(wrap_ups[seed % len(wrap_ups)])
    return "\n\n".join(lines)


def retrieve_support_plan(message, service_hint=None, intent_hint=None,
                          min_confidence=MIN_CONFIDENCE, max_resources=2):
    query = sanitize_query(message)
    cache_key = (
        f"{service_hint}|{intent_hint}|{min_confidence:.2f}|"
        f"{max_resources}|{query}"
    )
    cached = _cache_get(cache_key)
    if cached:
        result = dict(cached)
        result["from_cache"] = True
        return result

    scored = []
    for resource in get_all_knowledge_resources():
        score, matched_terms = _score_resource(query, resource, service_hint, intent_hint)
        if score >= min_confidence:
            item = dict(resource)
            item["score"] = round(score, 2)
            item["matched_terms"] = matched_terms
            scored.append(item)

    scored.sort(key=lambda item: item["score"], reverse=True)
    selected = scored[:max_resources]

    if not selected:
        result = {
            "found": False,
            "confidence": 0.0,
            "reply": "",
            "resources": [],
            "from_cache": False,
            "sanitized_query": query,
        }
        _cache_set(cache_key, result)
        return result

    result = {
        "found": True,
        "confidence": selected[0]["score"],
        "reply": _format_plan(selected),
        "resources": selected,
        "from_cache": False,
        "sanitized_query": query,
    }
    _cache_set(cache_key, result)
    return result
