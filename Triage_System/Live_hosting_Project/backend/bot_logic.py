import json
import re
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

from providers.knowledge_provider import retrieve_support_plan
from providers.gemini_provider import generate_triage_response
from triage_core.detection import (
    canonical_service as _canonical_service_core,
    contains_any as _contains_any_core,
    detect_all_services as _detect_all_services_core,
    detect_correction as _detect_correction_core,
    detect_escalation_request as _detect_escalation_request_core,
    detect_intent as _detect_intent_core,
    detect_unsupported_service as _detect_unsupported_service_core,
    fuzzy_detect_intent as _fuzzy_detect_intent_core,
    fuzzy_detect_service as _fuzzy_detect_service_core,
    get_hardware_context as _get_hardware_context_core,
    get_multi_issue_context as _get_multi_issue_context_core,
    has_detailed_description as _has_detailed_description_core,
    is_greeting_only as _is_greeting_only_core,
    is_non_issue_message as _is_non_issue_message_core,
    is_social_greeting as _is_social_greeting_core,
    is_unrelated_scope as _is_unrelated_scope_core,
    looks_like_vague_service_message as _looks_like_vague_service_message_core,
    normalize_message as _normalize_message_core,
    pretty_hardware_term as _pretty_hardware_term_core,
    service_label as _service_label_core,
    term_in_text as _term_in_text_core,
)
from triage_core.memory import (
    _memory_tokens,
    build_thread_memory,
    clarify_current_application_reply,
    extract_history_context,
    related_history_match,
    should_clarify_current_application,
)


# ============================================================
# Constants - deterministic guards only
# ============================================================

ESCALATION_TERMS = (
    "agent", "human", "ticket", "support",
    "representative", "person",
)

NEGATED_ESCALATION_PATTERNS = (
    r"\bdon'?t\s+(?:make|open|create|start|need)?\s*a?\s*ticket\b",
    r"\bdo not\s+(?:make|open|create|start|need)?\s*a?\s*ticket\b",
    r"\bno\s+ticket\b",
    r"\bnot\s+(?:yet|right now)?\s*(?:a\s+)?ticket\b",
    r"\bwithout\s+(?:a\s+)?ticket\b",
    r"\bcancel\s+(?:the\s+)?ticket\b",
    r"\bno\s+longer\s+need\s+(?:a\s+)?ticket\b",
    r"\bforget\s+(?:the|about\s+the)?\s*ticket\b",
    r"\bnevermind\s+(?:the\s+)?ticket\b",
    r"\bnever\s+mind\s+(?:the\s+)?ticket\b",
)

STRONG_OUTAGE_TERMS = (
    "outage", "down for everyone", "service down",
    "completely down", "not available", "widespread",
    "major outage",
)

SERVICE_DOWN_TERMS = (
    "is down",
    "are down",
    "went down",
    "currently down",
    "down right now",
    "down now",
    "not available",
    "unavailable",
)

HIGH_PRIORITY_TERMS = (
    "everyone",
    "everybody",
    "all users",
    "multiple users",
    "many users",
    "whole team",
    "entire team",
    "whole office",
    "entire office",
    "whole department",
    "entire department",
    "company wide",
    "company-wide",
    "urgent",
    "asap",
    "deadline",
    "meeting in",
    "client call",
    "board meeting",
    "executive meeting",
    "exec meeting",
)

URGENT_HANDOFF_TERMS = (
    "now",
    "right now",
    "immediately",
    "urgent",
    "asap",
    "emergency",
    "critical",
    "p1",
    "sev1",
    "cannot wait",
    "can't wait",
    "cant wait",
)

WORK_STOPPAGE_TERMS = (
    "cannot work",
    "can't work",
    "cant work",
    "unable to work",
    "blocked from working",
    "stopped me from working",
    "need this for work",
    "locked out",
    "blocking my work",
    "blocking work",
    "work is blocked",
    "cannot use",
    "can't use",
    "cant use",
    "cannot access",
    "can't access",
    "cant access",
    "cannot get in",
    "can't get in",
    "cant get in",
    "cannot send",
    "can't send",
    "cant send",
    "cannot join",
    "can't join",
    "cant join",
    "cannot sign in at all",
    "can't sign in at all",
    "cant sign in at all",
)

BUSINESS_CRITICAL_TERMS = (
    "payroll",
    "client",
    "customer",
    "deadline",
    "meeting",
    "class",
    "exam",
    "presentation",
    "interview",
    "production",
    "prod",
    "revenue",
)

CONTEXT_FOLLOW_UP_TERMS = (
    "it", "this", "that", "same", "again", "still",
    "back", "came back", "that issue", "that problem",
    "that one", "this issue", "this problem",
)

HISTORY_RECAP_TERMS = (
    "what applications was i having trouble with",
    "what apps was i having trouble with",
    "what app was i having trouble with",
    "what applications were we working on",
    "what apps were we working on",
    "what were we working on",
    "what issues were we working on",
    "what issues have we talked about",
    "which apps were we working on",
    "which applications were we working on",
    "which app was i having trouble with",
    "remind me what we were working on",
)

REFERENTIAL_SERVICE_RECAP_TERMS = (
    "same issue as before",
    "same issue",
    "issue as before",
    "same thing as before",
    "same as before",
)

QUEUE_HANDOFF_TERMS = (
    "next", "handle", "switch", "move to", "work on",
)

FALSE_MULTI_TEAM_HARDWARE_TERMS = {
    "mic", "microphone", "camera", "webcam",
    "audio input", "audio output", "sound", "video",
    "mute", "muted", "screen", "screeen", "scren", "sreen", "display",
    "camra", "camrea", "camerra", "cmaera",
}

FALSE_MULTI_OFFICE_HARDWARE_TERMS = {
    "screen", "scren", "sreen", "display", "print",
    "monitor", "moniter", "monitr",
    "video", "screeen", "diplay", "dsplay", "disply",
}

OFFICE_FILE_SERVICES = {"word", "excel", "powerpoint"}

PRINTING_REQUEST_TERMS = (
    "print",
    "prints",
    "printing",
    "printed",
    "printer",
    "cannot print",
    "can't print",
    "cant print",
    "will not print",
    "won't print",
    "wont print",
    "not printing",
    "print job",
)

LOW_PRIORITY_TERMS = (
    "signature",
    "desktop alert",
    "desktop alerts",
    "notification",
    "notifications",
    "banner",
    "banners",
    "dark mode",
    "theme",
    "formatting",
    "format",
    "font",
    "layout",
    "cosmetic",
    "minor",
    "annoying",
    "autocorrect",
    "spellcheck",
    "read receipt",
)

WEB_LINK_RE = re.compile(r"\s*https?://\S+")
ERROR_CODE_RE = re.compile(
    r"\b(?:0x[0-9a-f]{3,8}|[a-z]{2,}[a-z0-9]*\d{3,}|[a-z]\d{5,})\b",
    re.IGNORECASE,
)
AMBIGUOUS_ERROR_CODE_RE = re.compile(
    r"\b[a-z]{2,}(?:[-\s]?\d{2,})\b|\b[a-z]{1,3}-\d{2,}\b"
)

AMBIGUOUS_MICROSOFT_SURFACE_TERMS = (
    "microsoft 365",
    "ms 365",
    "office 365",
    "company 365",
    "work 365",
    "microsoft work",
    "work dashboard",
    "workspace",
    "portal",
    "panel",
    "side panel",
    "window",
    "box",
    "tile",
    "chooser",
    "picker",
    "continue button",
    "purple continue",
    "click allow",
    "click approve",
    "blank white",
    "flashes",
    "closes",
    "loops back",
    "bridge",
    "broker",
    "tenant context",
    "realm mismatch",
    "handshake",
)

AMBIGUOUS_FAILURE_TERMS = (
    "failed",
    "expired",
    "unavailable",
    "stale",
    "mismatch",
    "closes",
    "flashes",
    "loops back",
    "blank",
    "does not show an app",
    "no app name",
    "not sure what it belongs to",
)

UNSUPPORTED_STATUS_KEYWORDS = {
    "azure": ("azure",),
    "power platform admin center": ("power platform admin center",),
    "m365 enterprise": ("m365 enterprise", "microsoft 365 enterprise"),
    "m365 business": ("m365 business", "microsoft 365 business"),
}

UNSUPPORTED_SERVICE_KEYWORDS = {
    "gmail": ("gmail", "google mail"),
    "google drive": ("google drive",),
    "google docs": ("google docs", "google doc"),
    "slack": ("slack",),
    "zoom": ("zoom",),
    "dropbox": ("dropbox",),
}

SERVICE_KEYWORDS = {
    "teams": (
        "teams", "microsoft teams", "ms teams",
        "teems", "msteams", "team chat",
        "meeting", "meetings", "video call",
        "conference call", "meetng", "meetngs", "chat",
        "webinar", "breakout room", "breakout rooms",
        "live captions", "caption", "captions", "teams phone",
        "desk device", "user policy",
        "tems", "temas", "tema", "teeams", "tms", "team app", "teams app",
    ),
    "outlook": (
        "outlook", "exchange", "mail", "email", "inbox",
        "e-mail", "emails", "mails", "mailbox", "calendar",
        "calender", "calendar invite", "outlok", "otlook", "hotmail",
        "shared mailbox", "delegate", "delegates", "focused inbox",
        "mail rule", "rules", "archive", "sent items",
        "outloo", "outllok", "ourlook", "outlokk", "outlookk", "outloook",
    ),
    "onedrive": (
        "onedrive", "one drive", "one-drive", "1drive",
        "one drv", "onedrv", "cloud files", "filez",
        "files on demand", "backup",
        "personal vault", "storage full", "storage quota",
        "wnedrive", "onedirve", "ondrve", "onedrvie", "1 drive",
    ),
    "sharepoint": (
        "sharepoint", "share point", "sharept", "sharepoint site",
        "document library", "checked out", "checkout", "metadata",
        "recycle bin", "required metadata",
        "sharepont", "shaerpoint", "shairpoint", "shaepoint", "sharepiont",
    ),
    "excel": (
        "excel", "excell", "spreadsheet", "spread sheet",
        "worksheet", "workbook", "xls", "xlsx", "csv",
        "power query", "query", "external links", "linked workbook",
        "coauthor", "co-author", "same cells",
        "exel", "excle", "exsel", "exell", "excelsheet", "excel sheet",
    ),
    "word": (
        "word", "microsoft word", "ms word", "docx",
        "word doc", "word document", "document", "doc file",
        "protected view", "sensitivity label", "normal template",
        "wrd", "wird", "wrord", "microsoft wrd",
    ),
    "powerpoint": (
        "powerpoint", "power point", "ppt", "powerpt",
        "powerpint", "pptx", "slide deck", "presentation",
        "slideshow", "slides",
        "morph", "embedded fonts", "presenter remote",
        "powerpont", "powrpoint", "pwerpoint", "powepoint", "power pnt", "powerppt",
    ),
    "windows": (
        "windows", "win10", "win11", "windows 10",
        "windows 11", "winodws", "windws", "windows login", "windows sign in",
        "windows settings", "device manager", "file explorer",
        "windows hello", "mapped drive", "default printer", "vpn",
        "file explor", "taskbar", "start menu",
        "windoes", "widnows", "wndows", "windos", "windwos",
    ),
    "microsoft account": (
        "microsoft account", "ms account", "account",
        "signin", "sign in", "microsoft login", "ms login",
        "live.com", "account recovery", "verification code",
        "security code", "two factor", "2fa", "authenticator",
        "acount", "accont", "acct", "ms acct", "microsoft acct",
    ),
    "microsoft 365": (
        "microsoft 365", "office 365", "office",
        "m365", "o365", "microsoft office",
        "office apps", "office suite", "m365 apps",
        "ofice", "offce", "offfice", "microsft 365", "micorsoft 365",
    ),
}

# Maps hardware terms to the Microsoft service most relevant
# for the software/driver fix. Iteration order matters -
# more specific multi-word terms should come first so they
# are matched before their shorter substrings.
HARDWARE_SERVICE_MAP = {
    # Multi-word terms first
    "second screen":    "windows",
    "second monitor":   "windows",
    "secnd monitor":    "windows",
    "secnd moniter":    "windows",
    "external monitor": "windows",
    "bluetooth headphones": "windows",
    "bluetooth headset": "windows",
    "bluetooth speaker": "windows",
    "bluetooth mouse": "windows",
    "bluetooth keyboard": "windows",
    "dual monitor":     "windows",
    "dual monitors":    "windows",
    "dual screens":     "windows",
    "usb drive":        "windows",
    "usb stick":        "windows",
    "usb stik":         "windows",
    "flsh drv":         "windows",
    "flash drv":        "windows",
    "flash drive":      "windows",
    "thumb drive":      "windows",
    "external drive":   "windows",
    "hard drive":       "windows",
    "sync phone":       "onedrive",
    "docking station":  "windows",
    "dok":              "windows",
    "usb c":            "windows",
    "usb-c":            "windows",
    "displayport":      "windows",
    "audio output":     "windows",
    "audio input":      "windows",
    "no sound":         "windows",
    "no soud":          "windows",
    "cant hear":        "windows",
    "cnt hear":         "windows",
    "cnt here":         "windows",
    "cnt heer":         "windows",
    "can't hear":       "windows",
    "not detected":     "windows",
    "wi-fi":            "windows",

    # Audio / video peripherals - Teams and Windows
    "mic":          "teams",
    "microphone":   "teams",
    "micro":        "teams",
    "mics":         "teams",
    "microphones":  "teams",
    "webcam":       "teams",
    "camera":       "teams",
    "cam":          "teams",
    "headphones":   "windows",
    "headphone":    "windows",
    "headset":      "windows",
    "earphones":    "windows",
    "earbuds":      "windows",
    "airpods":      "windows",
    "air pods":     "windows",
    "speaker":      "windows",
    "speakers":     "windows",
    "speeker":      "windows",
    "speekers":     "windows",
    "audio":        "windows",
    "sound":        "windows",
    "volume":       "windows",
    "mute":         "windows",
    "muted":        "windows",
    "video":        "teams",

    # Input devices - Windows driver/settings
    "keyboard":  "windows",
    "mouse":     "windows",
    "mouce":     "windows",
    "touchpad":  "windows",
    "trackpad":  "windows",

    # Display - Windows display settings
    "monitor":    "windows",
    "moniter":    "windows",
    "display":    "windows",
    "hdmi":       "windows",
    "projector":  "windows",
    "resolution": "windows",
    "screen":     "windows",
    "screeen":    "windows",

    # Connectivity - Windows or OneDrive
    "bluetooth": "windows",
    "wifi":      "windows",
    "wireless":  "windows",
    "usb":       "windows",
    "file explor": "windows",
    "printer":   "windows",
    "print":     "windows",
    "scanner":   "windows",

    # Microphone misspellings
    "micorphone":  "teams",
    "micrphone":   "teams",
    "micropone":   "teams",
    "mikrofone":   "teams",
    "mircophone":  "teams",
    "microphne":   "teams",

    # Camera misspellings
    "camra":    "teams",
    "camrea":   "teams",
    "cmaera":   "teams",
    "kamera":   "teams",
    "camerra":  "teams",
    "cameraa":  "teams",

    # Keyboard misspellings
    "keybord":  "windows",
    "keybard":  "windows",
    "keyborad": "windows",
    "kyboard":  "windows",
    "keybrd":   "windows",
    "keybaord": "windows",

    # Monitor misspellings
    "monitr":   "windows",
    "monitar":  "windows",
    "mointor":  "windows",
    "monitur":  "windows",
    "moniotr":  "windows",

    # Bluetooth misspellings
    "blutooth":    "windows",
    "bluethooth":  "windows",
    "bluetoth":    "windows",
    "bluettoth":   "windows",
    "bleutooth":   "windows",
    "bluetooh":    "windows",
    "bluetoooth":  "windows",

    # Headphones misspellings
    "hedphones":   "windows",
    "headfones":   "windows",
    "headhpones":  "windows",
    "hedset":      "windows",
    "heaset":      "windows",
    "headfone":    "windows",
    "hedphone":    "windows",

    # Printer misspellings
    "printr":   "windows",
    "prnter":   "windows",
    "priinter": "windows",
    "priner":   "windows",
    "prinetr":  "windows",
    "printar":  "windows",

    # Scanner misspellings
    "scaner":   "windows",
    "scannr":   "windows",
    "scannar":  "windows",
    "scannner": "windows",

    # Speaker misspellings
    "speker":   "windows",
    "speakr":   "windows",
    "speakrs":  "windows",
    "speakerr": "windows",
    "spaeaker": "windows",

    # Touchpad misspellings
    "tuchpad":  "windows",
    "touchpd":  "windows",
    "tochpad":  "windows",
    "tuchpd":   "windows",
    "touchapd": "windows",

    # Display misspellings
    "displya":  "windows",
    "diplay":   "windows",
    "dsplay":   "windows",
    "dipslay":  "windows",
    "disply":   "windows",
    "displau":  "windows",

    # Screen misspellings (screeen already exists)
    "scren":    "windows",
    "scrren":   "windows",
    "sreen":    "windows",
    "srceen":   "windows",
}

# Phrases like "someone" and "peers" can look similar to "sound" or
# "speakers" in fuzzy matching. Keep fuzzy hardware matching to terms
# where a typo is common and unlikely to collide with normal sentences.
FUZZY_HARDWARE_TERMS = {
    "microphone",
    "webcam",
    "camera",
    "headphones",
    "headphone",
    "headset",
    "earphones",
    "earbuds",
    "airpods",
    "keyboard",
    "mouse",
    "mouce",
    "touchpad",
    "trackpad",
    "monitor",
    "moniter",
    "display",
    "screen",
    "screeen",
    "projector",
    "bluetooth",
    "printer",
    "scanner",
    # Microphone misspellings
    "micorphone", "micrphone", "micropone", "mikrofone", "mircophone", "microphne",
    # Camera misspellings
    "camra", "camrea", "cmaera", "kamera", "camerra", "cameraa",
    # Keyboard misspellings
    "keybord", "keybard", "keyborad", "kyboard", "keybrd", "keybaord",
    # Monitor misspellings
    "monitr", "monitar", "mointor", "monitur", "moniotr",
    # Bluetooth misspellings
    "blutooth", "bluethooth", "bluetoth", "bluettoth", "bleutooth", "bluetooh", "bluetoooth",
    # Headphones misspellings
    "hedphones", "headfones", "headhpones", "hedset", "heaset", "headfone", "hedphone",
    # Printer misspellings
    "printr", "prnter", "priinter", "priner", "prinetr", "printar",
    # Scanner misspellings
    "scaner", "scannr", "scannar", "scannner",
    # Speaker misspellings
    "speker", "speakr", "speakrs", "speakerr", "spaeaker",
    # Touchpad misspellings
    "tuchpad", "touchpd", "tochpad", "tuchpd", "touchapd",
    # Display misspellings
    "displya", "diplay", "dsplay", "dipslay", "disply", "displau",
    # Screen misspellings
    "scren", "scrren", "sreen", "srceen",
}

AUDIO_INPUT_ISSUE_TERMS = (
    "cannot hear me",
    "can't hear me",
    "cant hear me",
    "can not hear me",
    "cannot hear my",
    "can't hear my",
    "cant hear my",
    "can not hear my",
    "no one can hear me",
    "nobody can hear me",
    "people cannot hear me",
    "people can't hear me",
    "people cant hear me",
    "people cant heer me",
    "ppl cant hear me",
    "ppl cant heer me",
    "ppl cnt hear me",
    "ppl cnt heer me",
    "cant heer me",
    "cnt heer me",
    "cnt heer mee",
    "others cannot hear me",
    "others can't hear me",
    "others cant hear me",
    "they cannot hear me",
    "they can't hear me",
    "they cant hear me",
    "peers cannot hear me",
    "peers can't hear me",
    "peers cant hear me",
    "my mic is muted",
    "microphone is muted",
    "my mic doesnt work",
    "my mic dont work",
    "mic isnt working",
    "mic aint working",
    "voice not going through",
    "i talk but they cant hear",
    "my audio isnt transmitting",
    "im talking but nothing",
    "my voice isnt coming through",
    "noone hears me",
    "no one hears me",
    "collegues cant hear me",
    "coworkers cant hear me",
    "coworkers can't hear me",
    "my voice doesnt come through",
    "mic broke",
    "mic dead",
    "i talk no one hears",
    "they hear nothing from me",
    "my side has no audio",
    "audio not transmitting",
)

AUDIO_OUTPUT_ISSUE_TERMS = (
    "i cannot hear",
    "i can't hear",
    "i cant hear",
    "i cnt hear",
    "i cnt here",
    "i can not hear",
    "cnt hear anybody",
    "cnt here anybody",
    "cannot hear them",
    "can't hear them",
    "cant hear them",
    "can not hear them",
    "cannot hear others",
    "can't hear others",
    "cant hear others",
    "no audio from",
    "no sound from",
    "sound is not coming",
    "i hear nothing",
    "theres no sound",
    "there is no sound",
    "audio isnt working",
    "i dont hear anything",
    "speakers not working",
    "cant hear anyone",
    "can't hear anyone",
    "no audio coming through",
    "audio is dead",
    "sound is dead",
    "audio completely gone",
    "cant hear a thing",
    "can't hear a thing",
    "everything is silent",
    "call is silent",
    "meeting is silent",
    "total silence",
    "no sound at all",
    "audio dropped",
    "lost audio",
    "audio cut out",
    "they went silent",
)

OUTLOOK_CALENDAR_TERMS = (
    "calendar",
    "calender",
    "invite",
    "invte",
    "meeting invite",
    "meetng",
    "appointment",
)

SOCIAL_GREETING_TERMS = (
    "how are you",
    "how r u",
    "how you doing",
    "how are u",
    "how's it going",
    "hows it going",
    "hows it goin",
)

GREETING_REPLIES = (
    "Hi, you are in the right place for Teams, Outlook, OneDrive, Windows, and Microsoft account issues. Send me the messy version of what is happening and I will sort it into steps.",
    "Hey, tell me what app or device is giving you grief and what changed right before it broke. I will help narrow it down.",
    "Hello, I can work through Microsoft app trouble with you. Start with the app name if you know it, or just describe what you are seeing.",
)

SOCIAL_GREETING_REPLIES = (
    "Hello, I am good and ready to help. Even better once you tell me which application is giving you trouble.",
    "I am doing well, thanks for asking. Tell me which Microsoft application is acting up and I will help you sort it out.",
    "I am good, and I have my troubleshooting hat on. Which application or device issue are we tackling?",
)

RESOLUTION_REPLIES = (
    "Glad that worked. If anything else starts acting strange, bring me the error or symptom and we will pick it up from there.",
    "Nice, glad you are back in business. If another Microsoft app gets weird, send me what changed and I will help untangle it.",
    "Good to hear. Keep me posted if it comes back or moves to another app.",
)

SCOPE_REPLIES = (
    "I am built for Microsoft apps and Windows-adjacent troubleshooting, so I cannot help much with that one. If the issue is with Teams, Outlook, OneDrive, Word, Excel, PowerPoint, Windows, or your Microsoft account, tell me what is happening and I will jump in.",
    "That sounds outside my lane. I am strongest with Microsoft apps like Teams, Outlook, OneDrive, Word, Excel, PowerPoint, Windows, and Microsoft account issues. If one of those is involved, send me the details and I will help.",
    "I do not want to fake an answer there. My lane is Microsoft apps and common Windows device settings, so send me the affected app or device symptom and I will give you a clear path.",
)

UNRELATED_TOPIC_TERMS = (
    "weather",
    "recipe",
    "lasagna",
    "car",
    "netflix",
    "tv",
    "television",
    "homework",
    "math homework",
    "payroll",
    "tax",
    "taxes",
    "shopping",
    "shoes",
    "flight",
    "hotel",
    "restaurant",
    "doctor",
    "pizza",
    "uber",
    "amazon",
    "spotify",
    "instagram",
    "tiktok",
    "snapchat",
    "facebook",
    "twitter",
    "youtube",
    "fortnite",
    "minecraft",
    "iphone",
    "apple",
    "macbook",
    "imac",
    "gmail",
    "chrome",
    "firefox",
    "samsung",
    "playstation",
    "dating",
    "tinder",
    "food",
    "delivery",
    "movie",
    "music",
    "song",
    "lyrics",
    "bank",
    "banking",
    "credit card",
    "insurance",
    "medical",
    "pharmacy",
    "workout",
    "gym",
    "school grades",
    "grades",
    "homework help",
    "essay",
    "dissertation",
)

MULTI_ISSUE_STRONG_MARKERS = (
    ",",
    ";",
    " plus ",
    " also ",
    " too",
    " both ",
    " multiple ",
    " bunch ",
    " everything ",
    " all ",
    "wild today",
    "this is a mess",
)

# Physical damage phrases that have no Microsoft software fix
OUT_OF_SCOPE_HARDWARE = (
    "physically broken",
    "cracked screen",
    "broken screen",
    "shattered",
    "water damage",
    "wont power on",
    "won't power on",
    "won't turn on",
    "wont turn on",
    "dead laptop",
    "physically damaged",
    "dropped my",
    "spilled on",
)

SERVICE_LABELS = {
    "teams": "Teams",
    "outlook": "Outlook",
    "onedrive": "OneDrive",
    "sharepoint": "SharePoint",
    "excel": "Excel",
    "word": "Word",
    "powerpoint": "PowerPoint",
    "windows": "Windows",
    "microsoft account": "Microsoft account",
    "microsoft 365": "Microsoft 365",
}

SERVICE_FOLLOW_UPS = {
    "teams": "Tell me whether Teams failed during sign-in, joining a meeting, chat/messages, or audio/video devices.",
    "outlook": "Tell me whether Outlook failed while sending, receiving, opening mail, searching, using calendar, or signing in.",
    "onedrive": "Tell me whether OneDrive shows a red X, pending sync, missing files, upload failure, or a file that will not open.",
    "sharepoint": "Tell me whether SharePoint blocked the site, the file, editing, sync, or the sharing link.",
    "excel": "Tell me whether Excel is failing for one workbook, saving/AutoSave, formulas/links, formatting, or the whole app.",
    "word": "Tell me whether Word is failing to open, save, upload, format the document, or stay responsive.",
    "powerpoint": "Tell me whether PowerPoint is failing to open the deck, play media, present, save, or stay open.",
    "windows": "Tell me whether Windows is blocking sign-in, display, sound, Bluetooth, printer, update, or another device setting.",
    "microsoft account": "Tell me whether the Microsoft account blocker is password, verification code, Authenticator, recovery, or a sign-in loop.",
    "microsoft 365": "Name the app if you can. If not, tell me what you clicked, what appeared, and any exact code or wording.",
}

SERVICE_REPLY_OPENERS = {
    "teams": "For Teams, the next step depends on whether this is the meeting, messaging, sign-in, or device path.",
    "outlook": "For Outlook, the useful split is webmail versus desktop Outlook, then the specific mail action that failed.",
    "onedrive": "For OneDrive, start with the sync client state and the exact file status before changing the file.",
    "sharepoint": "For SharePoint, check the browser view and account permissions before assuming the file itself is damaged.",
    "excel": "For Excel, isolate whether this follows one workbook or the whole Excel app.",
    "word": "For Word, protect the document first, then test whether the issue follows the file or the Word app.",
    "powerpoint": "For PowerPoint, separate deck content, media playback, presenting, and app startup before changing the file.",
    "windows": "For Windows, start with the local setting, device state, or update screen tied to the symptom.",
    "microsoft account": "For Microsoft account issues, keep secrets out of chat and test the official sign-in page first.",
    "microsoft 365": "Let us narrow this from the symptom instead of guessing the app.",
}

INTENT_WRAP_UPS = {
    "email_delivery": "If it still comes back after that, keep the bounce-back text handy because it tells support exactly where delivery failed.",
    "sync": "If it still does not move after those checks, tell me which item is stuck and I can help decide whether it needs a ticket.",
    "sign_in": "If the same prompt comes back, copy the exact wording so we can separate password trouble from permission trouble.",
    "password_reset": "If the reset page will not accept your info, say ticket and include the sign-in message you see.",
    "crash": "If it fails again, the exact error text and whether it happens to one file or every file will tell us the next move.",
    "unknown": "If that does not line up with what you see, send me the exact wording on screen and I will adjust the path.",
    "activation": "If activation still fails after signing in correctly, check your subscription status at microsoft365.com and confirm the license is assigned to your account.",
    "notification": "If notifications still do not appear after those changes, restart the app to reset the notification state.",
    "update": "If the same update keeps failing, note the error code and we can look up the specific fix for that update.",
    "performance": "If it is still slow after those changes, tell me which app is the worst offender and I will drill into that one.",
    "formatting": "If the layout still looks wrong after those checks, send me what changed visually and whether it happens in one file or every file.",
}

INTENT_KEYWORDS = {
    "email_delivery": (
        "domain not found", "email someone", "send email",
        "sending email", "sending mail", "send mail",
        "message undeliverable", "undeliverable",
        "delivery failed", "delivery failure", "bounce back",
        "bounced back", "recipient not found", "address not found",
        "invalid recipient", "invalid email",
        "domain does not exist", "domain doesn't exist",
        "domain doesnt exist", "recipient domain",
        "domain error", "could not be delivered",
        "couldn't be delivered", "couldnt be delivered",
        "email came back", "mail came back",
        "send emails", "sending emails", "send outgoing",
        "outgoing mail", "send receive", "send/receive", "smtp",
        "returned email", "returned mail",
        "email not sending", "mail not sending",
        "stuck in outbox", "outbox",
        "sent bak", "got sent bak", "bouncd", "recipent", "domane",
        "does not exizt", "domane does not exizt",
    ),
    "password_reset": (
        "password", "reset password", "forgot password",
        "forgotten password", "credential", "credentials",
        "forgot my password", "reset my password",
        "password reset", "pw reset", "pwd reset",
        "pasword", "passward", "passwrod",
    ),
    "sign_in": (
        "login", "log in", "sign in", "signin", "access",
        "locked out", "cant login", "can't login",
        "cant sign in", "can't sign in", "wont let me in",
        "won't let me in", "cant access", "can't access",
        "logon", "log on", "sign-in", "wrong password",
        "wont accept password", "won't accept password",
        "verification code", "security code", "authenticator",
        "permission denied", "bitlocker", "recovery key",
        "bitlocker recovery key", "locked drive",
        "sso", "single sign on", "single sign-on",
        "seamless sign in", "work or school account",
        "conditional access", "modern authentication",
        "web account manager", "wam", "cached token",
        "credentials after password reset", "old alias", "old sign-in alias",
    ),
    "sync": (
        "sync", "syncing", "synced", "not syncing",
        "not updating", "not loading", "not saving",
        "wont sync", "won't sync", "upload", "uploading",
        "not uploading", "not downloading", "stuck syncing",
        "sync issue", "sync problem", "upload failed",
        "download failed", "not backed up", "backup failed",
        "pending", "stale", "not sending", "not send",
        "will not send", "wont send", "won't send",
        "messages not sending", "message not sending",
        "send messages", "send message", "pivot refresh",
        "data refresh", "refresh failed", "refresh all",
        "refresh still failed",
        "upload failed", "storage full", "quota", "checked out",
        "deleted", "recycle bin", "same cells", "coauthor",
    ),
    "crash": (
        "crash", "crashes", "crashing", "crashed",
        "freezes", "frozen", "freeze", "not responding",
        "stopped working", "wont load", "won't load",
        "keeps closing", "keeps crashing", "error", "errors",
        "failed", "fails", "failure", "hang", "hung",
        "hangs",
        "blank screen", "black screen", "white screen",
        "video is black", "black video", "media will not play",
        "media won't play", "media wont play", "playback failed",
        "wont open", "won't open", "wont start", "won't start",
        "not opening", "will not open", "will not start",
        "force closes", "closing itself", "lagging", "slow",
    ),
    "activation": (
        "office not activated", "license expired", "product key",
        "subscription expired", "trial ended", "activation failed",
        "unlicensed product", "activate office", "activashun",
        "lisense", "lisence", "activaton", "produc key",
        "subscrption", "ekspired", "expired lisence", "not activated",
        "unlisensed", "needs activation", "product activation",
        "activate microsoft", "unlicensed", "not licensed",
        "activation fails", "activation failed", "activation proxy",
    ),
    "notification": (
        "notifications not working", "no notifications",
        "missing notifications", "alerts not showing", "no alerts",
        "toast notification", "notification sound", "notificashun",
        "notifcation", "notificaton", "alrts", "no notifs",
        "notifs broken", "push notification", "desktop notification",
        "badge count", "not getting notified", "dont get notifications",
        "don't get notifications",
    ),
    "update": (
        "windows update", "update failed", "update stuck",
        "update error", "update loop", "won't update", "cant update",
        "can't update", "office update", "update pending",
        "updating forever", "restarts for update", "updaet", "updte",
        "updateing", "wont update", "update frozen", "cumulative update",
        "feature update", "update rollback", "update keeps failing",
        "stuck on update", "checking for updates forever",
        "update wont finish", "update not installing",
    ),
    "performance": (
        "running slow", "loads slowly", "high cpu", "high memory",
        "high ram", "high disk", "disk usage", "fan spinning",
        "overheating", "slo", "soooo slow", "sooo slow", "so slow",
        "ridiculously slow", "unusably slow", "crawling", "performace",
        "performence", "preformance", "runs like garbage", "super slow",
        "painfully slow", "freezing up", "keeps lagging", "lags constantly",
        "sluggish", "takes forever", "very slow", "extremely slow",
    ),
    "formatting": (
        "formatting", "layout", "markup", "track changes", "fonts",
        "font changed", "bullets", "spacing", "theme", "themes",
        "style", "styles", "wrong font", "shifted text", "layout exploded",
        "formatting broke", "looks weird", "looks wrong", "mangled",
        "pasted html", "paste from web", "print markup", "markup printing",
        "formula bar missing", "sheet tabs gone", "view settings",
        "formula", "formulas", "not calculating",
        "manual calculation", "calculate now", "recalculate",
        "focused inbox", "live captions", "captions", "morph",
        "embedded fonts", "normal template", "margin", "sensitivity label",
    ),
}

POSITIVE_RESOLUTION_TERMS = (
    "working perfectly", "everything is working", "all good",
    "nothing is wrong", "no issues", "it works", "its working",
    "it's working", "that worked", "it resolved", "never mind",
    "nevermind", "forget it", "no problem", "working fine",
    "fixed itself", "resolved itself", "everything is fine",
    "all is fine", "figured it out", "sorted it out",
    "sorted it", "got it working",
    "problem solved", "issue resolved", "back to normal", "works now",
    "its fine now", "it's fine now", "all fixed", "we good", "we're good",
    "were good", "all set", "good now", "im good", "i'm good",
    "no more issues", "that did it", "that fixed it", "perfect it works",
    "yep that worked", "yes that worked", "fixed thank you",
    "resolved thanks", "nvm", "nvm its working", "oh wait its working",
    "oh nvm", "scratch that it works", "false alarm", "never mind it works",
    "disregard its fixed", "sorted itself out", "magically fixed",
    "restarted and it works",
)

TICKET_CANCEL_TERMS = (
    # Service came back / restored
    "is back up", "came back up", "back up now", "came back online",
    "came back", "working again", "it came back", "back online",
    "it's back", "its back", "back now", "it's back up", "its back up",
    "all back up", "came back on its own",
    "seems to be back", "appears to be back",
    # Working again
    "started working again", "just started working",
    "resolved now", "fixed now",
    # Polite "never mind" signals
    "that is fine", "that's fine",
    "no need", "no longer need", "don't need", "dont need",
    "no need for that", "no need anymore",
    "not needed", "no longer needed",
    # Explicit cancellation of the ticket
    "cancel the ticket", "cancel ticket", "no ticket",
    "no ticket needed", "don't need a ticket", "dont need a ticket",
    "please cancel", "cancel please", "cancel it",
    "forget the ticket", "forget about the ticket",
    "nevermind the ticket", "never mind the ticket",
    # Issue went away on its own
    "actually fine", "actually working", "actually fixed",
    "sorted now", "resolved on its own", "fixed on its own",
    "problem went away", "issue went away", "went away on its own",
    "ended up working",
    # Casual confirmation it resolved
    "it's okay now", "its okay now", "okay now", "ok now",
    "my bad its fine", "my bad it's fine",
    "wait it works", "oh it works",
    "turns out it works", "turns out it was fine",
    "all good now",
    # Scope phrases
    "no longer an issue", "not an issue anymore", "not an issue any more",
)

GRATITUDE_TERMS = (
    "thanks", "thank you", "thx", "ty", "appreciate it",
    "thank you so much", "many thanks", "cheers",
    "thank u", "thnks", "thnx",
    "tysm", "tyvm", "thanks a lot", "thanks so much", "much appreciated",
    "ur the best", "you're the best", "youre the best", "legend",
    "lifesaver", "life saver", "clutch", "goat", "you rock",
    "thanks bro", "thanks man", "thanks fam", "good looks",
    "preciate it", "preciate that", "thank ya", "gracias", "merci",
    "big help", "huge help", "absolute legend", "saved me", "you saved me",
)

CORRECTION_TERMS = (
    # Explicit corrections
    "that's wrong", "thats wrong", "that is wrong",
    "that's not right", "thats not right", "that is not right",
    "that's incorrect", "thats incorrect",
    "wrong answer", "wrong response", "wrong reply",
    "not the answer", "not my answer",
    "you got it wrong", "you're wrong", "youre wrong",
    "you are wrong", "you misunderstood", "you misread",
    "you missed the point",
    # Not their issue
    "that's not my issue", "thats not my issue", "that is not my issue",
    "that's not my problem", "thats not my problem",
    "that's not what i said", "thats not what i said",
    "that's not what i meant", "thats not what i meant",
    "not what i meant", "not what i asked",
    "not what i said", "not what i'm asking",
    "not what im asking",
    "that's not the issue", "thats not the issue",
    "that is not the issue", "that's not the problem",
    "thats not the problem", "that is not the problem",
    "not the issue", "not the problem",
    "different issue", "different problem",
    "wrong issue", "wrong problem",
    "different app", "wrong app",
    "different service", "wrong service",
    # Explicit redirects
    "no i meant", "no i mean",
    "no that's not it", "no thats not it",
    "no that is not it", "no not that",
    "not that", "not that one",
    "i meant", "i mean something else",
    "what i meant was", "what i mean is",
    "let me clarify", "to clarify",
    "actually i meant", "actually my issue is",
    "i was asking about", "my issue is actually",
    # "Doesn't help" variants
    "that doesn't help", "that doesnt help", "that did not help",
    "that didn't help", "didnt help", "didn't help",
    "not helpful", "that wasn't helpful", "that wasnt helpful",
    "unhelpful", "that is not helpful",
    # Already tried variants
    "already tried that", "already done that",
    "tried that already", "done that already",
    "tried that before", "done that before",
    "i already did that", "i already tried that",
    "that didn't work", "that didnt work",
    "that does not work", "that doesn't work",
    "that doesnt work", "still not working",
    "still broken", "still the same",
    "same issue", "same problem",
    "still happening", "still failing",
    "it's still not working", "its still not working",
    "did not fix it", "didn't fix it", "didnt fix it",
    "does not fix it", "doesn't fix it", "doesnt fix it",
    "not fixed",
    # "Not about X" / "about Y" patterns
    "not about that", "not about",
    "this is about", "this is not about",
    "i'm not asking about", "im not asking about",
    "i wasn't asking about", "i wasnt asking about",
    # Try again prompts
    "try again", "please try again", "start over",
    "give me a different answer", "give me something else",
    "different answer", "different suggestion",
    "other suggestions", "other options",
    "something different", "anything else",
    "what else can i do", "what else",
    # Correction prefix phrases
    "no no", "nope", "nah that's not it", "nah thats not it",
    "nah not that", "nah that's wrong",
    "hold on", "wait no", "actually no",
    "incorrect", "wrong", "nope that's wrong",
    # Mild redirects / confusion signals
    "i think you misunderstood", "you seem to have misunderstood",
    "i think you got confused", "you seem confused",
    "that's for a different issue", "thats for a different issue",
    "that's for something else", "thats for something else",
    "that's not what i need", "thats not what i need",
    "that's not what i'm looking for", "thats not what im looking for",
    "not what i need", "not what i'm looking for",
    # Slang / casual dismissals
    "nope not that", "nope wrong",
    "bruh that's wrong", "bruh thats wrong",
    "bro that's not it", "bro thats not it",
    "dude that's wrong", "dude thats wrong",
    "man that's not it", "man thats not it",
    "that's off", "thats off",
    "completely off", "way off",
    "totally off", "totally wrong",
    "completely wrong", "not even close",
    "way off base", "off base",
    "missing the mark", "missed the mark",
    "not even right", "not even close to right",
    # I was talking about...
    "i was talking about", "i'm talking about",
    "im talking about", "i was referring to",
    "i'm referring to", "im referring to",
    "my question was about", "my question is about",
    "i asked about", "my original question",
    "i originally asked",
    # Second-attempt correction signals
    "let me rephrase", "let me reword", "let me explain better",
    "let me be more specific", "to be more specific",
    "more specifically", "to be specific",
    "to be clear", "to clarify again",
    "i should clarify", "clarifying",
)

GREETING_TERMS = (
    "hi", "hello", "hey", "yo", "sup", "wassup",
    "what's up", "whats up", "good morning",
    "good afternoon", "good evening",
)

CONTINUING_ISSUE_TERMS = (
    "still", "not working", "isn't working", "isnt working",
    "need a ticket", "need ticket", "ticket please",
    "issue", "problem", "help", "broken",
    "not fixed", "same issue", "still broken",
)

VAGUE_SERVICE_MESSAGE_TERMS = (
    "broken", "issue", "problem", "help", "again", "pls", "please",
    "bad", "wrong", "weird", "stuck",
)

SHORT_SERVICE_ACTION_TERMS = (
    "wont", "won't", "cant", "can't", "cannot", "join", "open", "load",
    "start", "work", "working", "broke", "broken", "weird", "stuck",
    "slow", "lag", "laggy", "freeze", "frozen", "gray", "grey",
)

PASSWORD_PROMPT_LOOP_TERMS = (
    "keeps asking", "keeps askin", "asking for my password",
    "asks for my password", "password prompt", "credential prompt",
    "prompts me", "prompting me", "password loop", "signin loop",
    "sign in loop", "keeps prompting", "asks me again",
)

MICROSOFT_ACCOUNT_RECOVERY_TERMS = (
    "verification code", "security code", "authenticator", "account recovery",
    "recovery", "old phone", "new phone", "backup email", "cant get code",
    "can't get code", "lost access", "no code", "code never shows", "txt code",
    "old number", "phone number", "number gone", "old phone gone",
)

OUTLOOK_CALLBACK_SYNC_TERMS = (
    "mailbox", "search", "inbox", "mail", "messages",
)

OUTLOOK_EMAIL_DELIVERY_TERMS = (
    "email not sending", "email still not sending",
    "mail not sending", "message not sending",
    "not sending", "still not sending",
    "wont send", "won't send", "will not send",
    "cannot send", "can't send", "cant send",
    "send failed", "send failure", "sending failed",
    "stuck in outbox", "outbox", "not going out",
    "undeliverable", "delivery failed", "delivery failure",
    "bounce back", "bounced back", "came back",
)

SHAREPOINT_READ_ONLY_TERMS = (
    "read only", "readonly", "view only", "can't edit", "cant edit",
    "cannot edit", "locked for editing", "editing blocked",
)

SHAREPOINT_VERSION_HISTORY_TERMS = (
    "version history", "previous version", "older version", "restore version",
    "roll back", "rollback", "yesterday version", "earlier version",
    "version back", "yesterday", "yesterdays",
)

ONEDRIVE_CONFLICT_TERMS = (
    "conflict copy", "conflicting copy", "conflicted copy", "duplicate file",
    "duplicate copy", "duplicate conflict", "two versions", "offline work",
    "made duplicate", "made a duplicate", "conflict copies",
)

MICROSOFT_ACCOUNT_THROTTLE_TERMS = (
    "too many requests", "too many tries", "try again later",
    "authenticator never", "never pings", "wont approve",
    "won't approve", "auth app", "approval not arriving",
)

EXCEL_LINK_WARNING_TERMS = (
    "update links",
    "edit links",
    "external links",
    "source not found",
    "invalid names",
    "name manager",
    "named range",
    "retired file",
    "dead workbook",
)

EXCEL_AUTOSAVE_TERMS = (
    "autosave", "auto save", "greyed out", "grayed out", "toggle greyed out",
    "toggle grayed out",
)

TEAMS_JOIN_TERMS = (
    "join", "wont join", "won't join", "cant join", "can't join",
    "cannot join",
)

DETAIL_HINT_TERMS = (
    "error", "code", "when i", "after i", "trying to",
    "cannot", "can't", "fails", "failed", "message",
    "popup", "prompt", "permission", "blocked",
    "allow", "access denied", "not detected",
    "device", "muted", "selected",
    "crashes", "crashing",
)

# Used only by rule-based fallback - emergency responses when Gemini is down
SHORT_STEP_RESPONSES = {
    "password_reset": [
        "Use the official Microsoft sign-in page and choose Forgot password rather than sharing any password or code here.",
        "After the reset finishes, try the same app again so we know whether the account or the app session was the blocker.",
    ],
    "sign_in": [
        "Try signing in at microsoft365.com first; if that fails too, the account is the blocker rather than just this app.",
        "If the web sign-in works, sign out of the affected app and sign back in so it gets a fresh session token.",
    ],
    "sync": [
        "Confirm the affected app is using the correct work account before changing the file or mailbox.",
        "Then refresh or restart that app and check whether the stuck item moves, sends, or updates in the web version.",
    ],
    "crash": [
        "Close the affected Microsoft app fully and reopen it from the Start menu rather than from a recent file.",
        "If it fails again, note whether the crash happens at launch, when opening one item, or after a specific click.",
    ],
    "email_delivery": [
        "Check the recipient's email address for typos, extra spaces, or a misspelled domain after the @ symbol.",
        "Try sending from Outlook on the web at outlook.com or microsoft365.com to see whether the issue is only in the app.",
        "If it still says domain not found, copy the full error text so support can verify the recipient domain.",
    ],
    "activation": [
        "Open the affected Office app, go to File > Account, and confirm the signed-in account is the one with the Microsoft 365 license.",
        "If it is already signed in but still unlicensed, sign out, restart the app, then sign back in to trigger a fresh license check.",
    ],
    "notification": [
        "Check the app's notification settings first — in Teams go to Settings > Notifications, in Outlook go to File > Options > Mail.",
        "Also check Settings > System > Notifications and confirm the app is allowed to show notifications in Windows.",
    ],
    "update": [
        "Go to Settings > Windows Update and click Check for updates — note any error code shown next to a failed update.",
        "If an update is stuck, run the Windows Update Troubleshooter from Settings > System > Troubleshoot > Other troubleshooters.",
    ],
    "performance": [
        "Press Ctrl + Shift + Esc to open Task Manager and sort the Processes tab by CPU or Disk to find what is consuming resources.",
        "Go to Settings > Apps > Startup apps and disable anything non-essential to reduce background load on every boot.",
    ],
    "audio": [
        "Check the affected app's device settings and confirm the correct microphone and speaker are selected there.",
        "Then open Settings > System > Sound and make sure Windows is using the same input and output devices.",
    ],
    "video": [
        "Check the affected app's device settings and confirm the correct camera is selected there.",
        "Then open Settings > Privacy & security > Camera and make sure Windows allows that app to use the camera.",
    ],
    "display": [
        "Check whether this is the app window, screen sharing, or a second monitor so we stay on the right display path.",
        "Then use the app's sharing/display controls or Windows Settings > System > Display depending on where the problem appears.",
    ],
    "formatting": [
        "Start with the app's own view or layout settings so we can rule out a hidden formatting toggle before changing the file itself.",
        "If this came from pasted content or a shared file, test with a clean copy or plain-text paste so we can separate document formatting from app behavior.",
    ],
    "permissions": [
        "Confirm you are signed in with the correct work account for that file, site, or app.",
        "If it still says access denied, open the item in a browser and ask the owner to verify edit or view permission on that exact link.",
    ],
    "printing": [
        "Open the Print settings and confirm the correct printer is selected and online.",
        "If the printer is missing, reopen Windows printer settings and refresh the device list before trying again.",
    ],
    "device_setup": [
        "Start by reconnecting the device and checking whether Windows or the app detects it at all.",
        "Then open the relevant Windows or app device settings and confirm it is selected as the active device.",
    ],
}

SERVICE_INTENT_RESPONSES = {
    ("teams", "sync"): [
        "Teams messages getting stuck usually means the desktop app, network, or session cache needs a reset.",
        "Check your internet connection, fully quit Teams, and reopen it.",
        "If messages still will not send, try Teams on the web to see whether the issue is only in the desktop app.",
    ],
    ("onedrive", "sync"): [
        "OneDrive being stuck usually means sync needs a clean restart or the account needs to be confirmed.",
        "Confirm you are signed in to the correct Microsoft account, then pause and resume sync from the OneDrive cloud icon.",
        "If the file still says pending, reopen OneDrive and check for sync errors.",
    ],
    ("microsoft account", "sign_in"): [
        "Microsoft account prompts can loop when the sign-in session or verification method is out of step.",
        "Try signing in at microsoft365.com and confirm whether the verification code or Authenticator prompt appears.",
        "If the prompt does not appear, use account recovery or password reset before trying again.",
    ],
    ("windows", "sign_in"): [
        "For Windows sign-in, start with the basics that can block a correct password.",
        "Restart once, confirm the keyboard layout and internet connection on the sign-in screen, then try your Microsoft account password again.",
        "If that fails, use the password reset option for your Microsoft account.",
    ],
    ("outlook", "email_delivery"): [
        "That bounce-back points to Outlook delivery or the recipient address, not an app crash.",
        "Check the recipient's email address for typos, extra spaces, or a misspelled domain after the @ symbol.",
        "Try sending from Outlook on the web at outlook.com or microsoft365.com to see whether the issue is only in the app.",
    ],
    ("sharepoint", "sign_in"): [
        "SharePoint access errors usually mean the link and the signed-in account do not line up.",
        "Open the file or site link in a browser and confirm you are signed in with the correct Microsoft account.",
        "If it still says access denied, ask the file owner to share it again or verify your permissions from SharePoint.",
    ],
    ("sharepoint", "permissions"): [
        "A SharePoint file opening as read-only usually means the file permissions, checkout state, or sync location is limiting edits.",
        "Open the file in the browser first and check whether it says View only, Checked out, or requires edit access.",
        "If it should be editable, ask the site or file owner to confirm you have edit permission and that nobody else has it locked.",
    ],
    ("word", "crash"): [
        "For Word, protect the document first, then test whether the issue is the file or the save location.",
        "Use File > Save As and try saving a copy to OneDrive or Desktop so we can tell whether the issue is the document or the location.",
        "If Word still errors, close Word fully, reopen the document, and note the exact save error.",
    ],
    ("word", "performance"): [
        "Word slowing down or freezing is usually caused by the document itself, an add-in, or the save location.",
        "Open Word first without the document. If Word is fine, open the file and use Save As to store a copy on Desktop or OneDrive.",
        "If Word is slow even before the file opens, start Word in safe mode by holding Ctrl while opening it and see whether the lag clears.",
    ],
    ("word", "formatting"): [
        "Word layout or markup issues are often caused by view settings, tracked changes, or pasted formatting rather than a damaged file.",
        "Switch to No Markup or Print Layout first, then check whether the same issue appears in Print Preview or only on screen.",
        "If web content caused it, paste once as text only or into a clean copy so hidden formatting does not keep coming back.",
    ],
    ("powerpoint", "crash"): [
        "For PowerPoint, check whether the deck itself is the trigger before changing anything bigger.",
        "Close PowerPoint fully and reopen the presentation. If it crashes again, try opening PowerPoint first, then use File > Open to load the deck.",
        "If the same slide or media file triggers it, note that detail for support.",
    ],
    ("powerpoint", "formatting"): [
        "PowerPoint layout problems usually come from missing fonts, theme differences, or slide content that was positioned for another device.",
        "Open the deck on the affected machine and check which fonts or theme elements changed before editing the slide manually.",
        "If this deck moves between machines often, embed fonts in the file or keep a PDF backup so the layout stays stable.",
    ],
    ("outlook", "sign_in"): [
        "Outlook credential loops usually mean the saved password or token in Windows Credential Manager is out of date.",
        "Open Windows Credential Manager, find any saved Outlook or Office entries, remove them, then restart Outlook and sign in fresh.",
        "If the prompt returns, try signing in at outlook.com or microsoft365.com to confirm whether the issue is the app or the account.",
    ],
    ("outlook", "crash"): [
        "Outlook freezing usually comes down to add-ins, the mailbox cache, or a corrupted profile.",
        "Start Outlook in safe mode by holding Ctrl while opening it — if it loads cleanly, go to File > Options > Add-ins and disable non-Microsoft add-ins one at a time.",
        "If safe mode also crashes, try repairing Office from Settings > Apps > Microsoft 365 > Modify.",
    ],
    ("outlook", "sync"): [
        "When Outlook stops receiving new mail, the first check is whether the mail appears in Outlook on the web.",
        "Go to outlook.com or microsoft365.com and check the inbox — if mail is there, the desktop app cache needs a reset.",
        "If the web inbox also shows nothing new, check junk, filters, and whether any rules are redirecting incoming mail.",
    ],
    ("outlook", "formatting"): [
        "Outlook display quirks are usually tied to view settings, signature formatting, or pasted content rather than mailbox loss.",
        "Check the current Outlook view or the message formatting options first, then test whether the same issue appears in Outlook on the web.",
        "If it only breaks on one device, rebuild the local formatting piece instead of changing the whole mailbox.",
    ],
    ("teams", "sign_in"): [
        "Teams sign-in loops are usually caused by a stuck authentication token or a corrupted app cache.",
        "Fully quit Teams, then open %appdata%\\Microsoft\\Teams and delete the contents of that folder, then reopen Teams.",
        "If Teams still loops, try signing in at teams.microsoft.com in a browser to separate the desktop app from the account.",
    ],
    ("teams", "audio"): [
        "If people cannot hear you in Teams, start in the meeting controls and confirm you are not muted and the correct microphone is selected.",
        "Then open Teams device settings and Windows Sound settings to make sure the same microphone is set as the input device in both places.",
        "If the mic still looks fine but nobody hears you, leave and rejoin the meeting once to refresh the audio session.",
    ],
    ("teams", "crash"): [
        "Teams crashing on load usually means the app cache or a recent update needs a reset.",
        "Fully quit Teams, clear the Teams cache folder at %appdata%\\Microsoft\\Teams, then reopen Teams.",
        "If it keeps happening, check for Windows updates and try the Teams web app at teams.microsoft.com as a workaround.",
    ],
    ("excel", "crash"): [
        "Excel freezing is usually triggered by a specific workbook, an add-in, or a corrupted recent file entry.",
        "Try opening Excel without any file first — if Excel opens cleanly, the issue is the workbook not the app.",
        "Hold Ctrl while opening Excel to start in safe mode, which disables add-ins, and see whether it opens cleanly that way.",
    ],
    ("excel", "formatting"): [
        "Excel layout issues usually come from hidden view options, workbook display settings, or pasted content that brought its own formatting with it.",
        "Check the View tab and the workbook display options first so we can restore hidden bars, tabs, or panes before editing the sheet.",
        "If the problem came from pasted or linked content, test a clean copy of the workbook so we can tell whether the formatting problem is file-specific.",
    ],
    ("excel", "sync"): [
        "Excel not saving to OneDrive usually means AutoSave needs the account confirmed or the file path is too long.",
        "Check the AutoSave toggle at the top of Excel — if it is off, confirm you are signed in to OneDrive and the file is stored in a OneDrive folder.",
        "If AutoSave is on but conflicts appear, go to File > Info > Version History to see the conflict and choose which version to keep.",
    ],
    ("word", "sync"): [
        "Word showing upload failed or a sync conflict usually means OneDrive has a version mismatch on that document.",
        "Go to File > Info and check whether a conflict version is listed — if so, open both and copy the content you want to keep.",
        "Delete the conflicted copy and confirm the file saves cleanly to OneDrive before closing Word.",
    ],
    ("onedrive", "sign_in"): [
        "OneDrive prompting to sign in again usually means the token expired or the wrong account is cached.",
        "Click the OneDrive cloud icon, go to Settings > Account, and check which account is signed in — sign out and back in if it does not match.",
        "If the prompt keeps returning, right-click the OneDrive icon, choose Quit, then reopen OneDrive from the Start menu and sign in fresh.",
    ],
    ("onedrive", "crash"): [
        "When OneDrive is not running or missing from the taskbar, it may have stopped or failed to start after an update.",
        "Search for OneDrive in the Start menu and open it — this restarts the sync client without reinstalling.",
        "If it opens briefly then disappears, go to Settings > Apps and check whether OneDrive needs a repair or update.",
    ],
    ("windows", "crash"): [
        "Blue screens and restart loops in Windows usually point to a recent driver update, a Windows Update, or failing hardware.",
        "After the PC restarts, check Reliability Monitor in Windows or Event Viewer for the error code and timestamp.",
        "If you see a stop code on the blue screen, note it exactly — most BSOD codes have a specific fix on Microsoft support.",
    ],
    ("sharepoint", "sync"): [
        "SharePoint files not syncing locally usually means the OneDrive sync client needs to reconnect to the library.",
        "Click the OneDrive cloud icon and check for sync errors listed there — a yellow warning means a specific file is blocked.",
        "If the whole library is missing, open the SharePoint site in a browser, find the library, and click Sync to reconnect it.",
    ],
    ("sharepoint", "crash"): [
        "SharePoint sites not loading usually means a browser issue, a permission problem, or a session that needs refreshing.",
        "Try opening the SharePoint site in a different browser or in a private or InPrivate window first.",
        "If it still fails, clear your browser cache and cookies, then sign back in with your Microsoft account and try again.",
    ],
    ("microsoft account", "password_reset"): [
        "To reset a Microsoft account password, go to account.live.com/password/reset and choose I forgot my password.",
        "Enter the email or phone linked to the account, complete the verification step, then create a new password.",
        "If no verification options are available, choose I do not have any of these and follow the account recovery steps.",
    ],
    ("microsoft 365", "sign_in"): [
        "When sign-in fails across multiple Office apps, the shared Microsoft 365 account token is usually the cause.",
        "Open any Office app, go to File > Account, sign out, then sign back in with your Microsoft 365 credentials.",
        "If that does not help, try signing in at microsoft365.com in a browser to confirm whether the account itself is the blocker.",
    ],
    ("microsoft 365", "crash"): [
        "Multiple Office apps crashing at once usually points to a corrupted installation or a recent update that needs repair.",
        "Go to Settings > Apps > Installed apps, find Microsoft 365, choose Modify, and run Quick Repair first.",
        "If Quick Repair does not help, run Online Repair and restart Windows when it finishes.",
    ],
    ("teams", "notification"): [
        "Teams notifications not appearing usually means the notification settings inside Teams or Windows have been changed.",
        "Go to Teams > Settings > Notifications and confirm calls, mentions, and messages are set to Banner or Feed, not Off.",
        "Also check Settings > System > Notifications and make sure Microsoft Teams is allowed to show notifications.",
    ],
    ("outlook", "notification"): [
        "Outlook desktop alerts not showing usually means the notification setting in Outlook itself has been turned off.",
        "Go to File > Options > Mail and scroll to Message arrival — make sure Display a Desktop Alert is checked.",
        "Also check Settings > System > Notifications and confirm Outlook is allowed to send notifications in Windows.",
    ],
    ("windows", "update"): [
        "Windows Update getting stuck or failing usually means a specific update has an install error or the update service needs a reset.",
        "Go to Settings > Windows Update and click Check for updates — note the error code shown next to any failed update.",
        "If it is stuck on the same update, run the Windows Update Troubleshooter from Settings > System > Troubleshoot > Other troubleshooters.",
    ],
    ("windows", "performance"): [
        "Windows running slowly usually means high CPU, RAM, or disk usage — start by checking Task Manager.",
        "Press Ctrl + Shift + Esc to open Task Manager, go to Processes, and sort by CPU or Disk to find the heavy app.",
        "Also check Settings > Apps > Startup apps and disable anything non-essential to reduce background load on every boot.",
    ],
    ("teams", "performance"): [
        "Teams running slow in meetings is usually caused by GPU rendering, background apps, or a bloated Teams cache.",
        "In Teams, go to Settings > General and turn off GPU hardware acceleration, then restart Teams.",
        "Also close other apps during the call and check whether Teams on the web at teams.microsoft.com performs better.",
    ],
    ("outlook", "performance"): [
        "Outlook loading slowly is usually caused by a large mailbox, too many add-ins, or a bloated cache file.",
        "Go to File > Options > Add-ins and disable non-Microsoft add-ins, then restart Outlook and check load time.",
        "If search is the slow part, go to File > Options > Search and rebuild the search index.",
    ],
    ("microsoft 365", "activation"): [
        "The unlicensed product banner means Office cannot verify your Microsoft 365 subscription on this device.",
        "Open any Office app, go to File > Account, and click Sign In or Activate using the email tied to your subscription.",
        "If the account shows correctly but activation still fails, sign out of all Office apps, restart Windows, then sign back in.",
    ],
    ("excel", "activation"): [
        "Excel showing unlicensed means Office cannot confirm the subscription for the signed-in account on this device.",
        "Open Excel, go to File > Account, and click Sign In or Activate with the email tied to your Microsoft 365 subscription.",
        "If already signed in and still unlicensed, sign out from File > Account, restart Excel, then sign back in.",
    ],
    ("word", "activation"): [
        "Word showing unlicensed means Office cannot verify the Microsoft 365 subscription from this account.",
        "Open Word, go to File > Account, and click Activate or confirm the signed-in account is the correct Microsoft 365 account.",
        "If it is already signed in but still shows unlicensed, sign out, restart Word, then sign back in.",
    ],
    ("powerpoint", "activation"): [
        "PowerPoint showing unlicensed means the subscription is not being confirmed on this device.",
        "Open PowerPoint, go to File > Account, and click Sign In or Activate with the correct Microsoft 365 account.",
        "If already signed in, sign out from File > Account, restart PowerPoint, and sign in again to trigger a fresh license check.",
    ],
}

MULTI_SERVICE_GUIDANCE = {
    "teams": (
        "Teams: pin down whether the failing part is devices, chat or channel access, "
        "or calendar and joining, then test that same action in Teams web versus desktop."
    ),
    "outlook": (
        "Outlook: try Outlook on the web, then check the recipient address, "
        "calendar view, or mailbox sync depending on what failed."
    ),
    "onedrive": (
        "OneDrive: use the cloud icon to pause and resume sync, confirm the "
        "correct Microsoft account, and look for sync errors."
    ),
    "sharepoint": (
        "SharePoint: open the site or file in a browser first and note whether the blocker "
        "is page loading, read-only mode, or permissions so the next step stays specific."
    ),
    "excel": (
        "Excel: reopen the workbook from Excel > File > Open and note whether "
        "one file or every spreadsheet crashes."
    ),
    "word": (
        "Word: try File > Save As to OneDrive or Desktop, then reopen Word and "
        "capture the exact save or crash message."
    ),
    "powerpoint": (
        "PowerPoint: reopen the deck, check slide media volume for sound issues, "
        "then go to: Settings > System > Sound and verify the correct Output device."
    ),
    "windows": (
        "Windows: check Settings for sign-in, display, sound, Bluetooth, or "
        "printer settings based on the device that is failing."
    ),
    "microsoft account": (
        "Microsoft account: sign in at microsoft365.com and confirm whether the "
        "password, Authenticator prompt, or verification code is the blocker."
    ),
}

SERVICE_CAPABILITY_TERMS = {
    "outlook": (
        "email", "emails", "e-mail", "mail", "mailbox", "inbox",
        "outbox", "recipient", "calendar", "invite", "meeting invite",
        "send", "sending", "sent", "not sending", "wont send",
        "won't send", "will not send", "cannot send", "can't send",
        "cant send", "deliver", "delivery", "undeliverable",
        "bounce back", "bounced back", "came back", "exchange",
        "credential prompt", "modern authentication", "wam",
    ),
    "teams": (
        "teams meeting", "meeting", "meetings", "call", "video call",
        "chat", "channel", "screen share", "share screen", "mic",
        "microphone", "camera", "speaker", "audio", "join",
        "message not sending", "messages not sending", "chat not sending",
        "not sending", "wont send", "won't send", "sign in loop",
        "desktop app", "meeting policy",
    ),
    "onedrive": (
        "onedrive", "file", "files", "folder", "folders", "sync",
        "syncing", "upload", "uploading", "download", "downloading",
        "cloud", "backup", "pending", "red x", "green check",
        "available offline", "free up space",
        "wrong tenant", "wrong account", "sync client",
    ),
    "sharepoint": (
        "sharepoint", "site", "library", "document library", "link",
        "permissions", "permission", "access denied", "read only",
        "view only", "checked out", "metadata", "version history",
        "restore version", "recycle bin",
        "conditional access", "external sharing", "guest access",
    ),
    "word": (
        "word", "document", "doc", "docx", "track changes", "markup",
        "spell check", "grammar", "header", "footer", "page break",
        "table of contents",
    ),
    "excel": (
        "excel", "spreadsheet", "workbook", "worksheet", "formula",
        "formulas", "cell", "cells", "pivot", "filter", "sheet",
        "csv", "autosave",
        "pivot refresh", "protected view", "trust center",
    ),
    "powerpoint": (
        "powerpoint", "presentation", "slides", "slide deck", "ppt",
        "pptx", "present", "presenting", "slideshow", "animation",
        "speaker notes", "embedded video", "slide master", "template",
    ),
    "windows": (
        "windows", "pc", "computer", "laptop", "printer", "scanner",
        "screen", "monitor", "display", "wifi", "wi-fi", "bluetooth",
        "keyboard", "mouse", "touchpad", "update", "taskbar",
        "start menu", "file explorer", "bitlocker",
        "work or school account", "vpn", "dns", "device registration",
    ),
    "microsoft account": (
        "password", "sign in", "signin", "login", "authenticator",
        "verification code", "security code", "mfa", "2fa",
        "account recovery", "locked out", "recovery email",
        "sso", "single sign on", "single sign-on", "mfa",
    ),
}

SERVICE_HARDWARE_RESPONSES = {
    ("powerpoint", "audio"): (
        "PowerPoint audio can fail inside the slide or at the Windows output level. First confirm the video or slide audio is not muted inside PowerPoint. "
        "Then go to: Settings > System > Sound and verify the correct Output device is selected. "
        "If you are presenting through Teams, also turn on Include computer sound when sharing."
    ),
    ("powerpoint", "sound"): (
        "PowerPoint sound has two places to check: the media in the slide and the Windows output device. Check the media volume inside the slide first, then go to: "
        "Settings > System > Sound and verify the correct Output device is selected. "
        "If you are sharing in Teams, make sure Include computer sound is enabled."
    ),
    ("powerpoint", "no sound"): (
        "For a silent PowerPoint video, check the video's volume inside the slide and make sure it is not muted. "
        "Then go to: Settings > System > Sound and verify the correct Output device is selected. "
        "If this is during a Teams presentation, share again with Include computer sound turned on."
    ),
    ("powerpoint", "no soud"): (
        "For a silent PowerPoint video, check the video's volume inside the slide and make sure it is not muted. "
        "Then go to: Settings > System > Sound and verify the correct Output device is selected. "
        "If this is during a Teams presentation, share again with Include computer sound turned on."
    ),
    ("powerpoint", "audio output"): (
        "If PowerPoint is playing but you cannot hear it, check the slide media volume first, then go to: "
        "Settings > System > Sound and confirm the correct Output device is selected. "
        "If you are presenting in Teams, enable Include computer sound before sharing."
    ),
    ("powerpoint", "cant hear"): (
        "If the audience cannot hear the PowerPoint media, check the presentation's media volume first, then go to: "
        "Settings > System > Sound and confirm the correct Output device is selected. "
        "If you are presenting through Teams, share with Include computer sound turned on."
    ),
    ("powerpoint", "can't hear"): (
        "If the audience cannot hear the PowerPoint media, check the presentation's media volume first, then go to: "
        "Settings > System > Sound and confirm the correct Output device is selected. "
        "If you are presenting through Teams, share with Include computer sound turned on."
    ),
    # Teams microphone
    ("teams", "microphone"): (
        "For Teams microphone issues, go to: Settings > Privacy & security > Microphone and confirm Teams has access. "
        "Then in Teams, go to: Settings > Devices and select the correct microphone. "
        "If it still shows no input, leave and rejoin the meeting after changing the device."
    ),
    ("teams", "mic"): (
        "Make sure the mic is not muted on the headset or keyboard first. "
        "Then go to: Settings > Privacy & security > Microphone and confirm Teams access is on, "
        "and check: Teams > Settings > Devices to select the correct microphone."
    ),
    ("teams", "mics"): (
        "Make sure the mic is not muted on the headset or keyboard first. "
        "Then go to: Settings > Privacy & security > Microphone and confirm Teams access is on, "
        "and check: Teams > Settings > Devices to select the correct microphone."
    ),
    ("teams", "microphones"): (
        "For Teams microphone issues, go to: Settings > Privacy & security > Microphone and confirm Teams has access. "
        "Then in Teams, go to: Settings > Devices and select the correct microphone. "
        "If it still shows no input, leave and rejoin the meeting after changing the device."
    ),
    # Teams camera
    ("teams", "camera"): (
        "Go to: Settings > Privacy & security > Camera and confirm Teams access is on. "
        "Then in Teams, go to: Settings > Devices and select the correct camera. "
        "If the preview is blank, leave and rejoin the call after selecting the camera."
    ),
    ("teams", "cam"): (
        "Go to: Settings > Privacy & security > Camera and confirm Teams access is on. "
        "Then in Teams, go to: Settings > Devices and pick the correct camera from the dropdown."
    ),
    ("teams", "webcam"): (
        "Go to: Settings > Privacy & security > Camera and confirm Teams access is on. "
        "Then in Teams, go to: Settings > Devices and select the correct webcam. "
        "If it still shows no image, check Windows Update for a webcam driver fix."
    ),
    # Teams audio input/output
    ("teams", "audio input"): (
        "For Teams audio input, go to: Settings > Privacy & security > Microphone and confirm Teams access is on. "
        "Then go to: Teams > Settings > Devices and select the correct microphone under Audio devices. "
        "If you see input signal but others cannot hear you, confirm you are not muted in the meeting controls."
    ),
    ("teams", "audio output"): (
        "For Teams audio output, go to: Teams > Settings > Devices and confirm the correct speaker is selected. "
        "Also check: Settings > System > Sound and verify the correct Output device. "
        "If you can hear Windows sounds but not Teams audio, restart Teams after changing the speaker selection."
    ),
    # Teams audio/sound
    ("teams", "audio"): (
        "Teams audio issues split between microphone and speaker. Go to: Teams > Settings > Devices "
        "and confirm both the microphone and speaker are set to the correct device. "
        "Then check: Settings > System > Sound for both Input and Output."
    ),
    ("teams", "sound"): (
        "Teams sound issues usually mean the wrong Output device is selected. Go to: Settings > System > Sound "
        "and confirm the correct speaker or headset is selected under Output. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker matches."
    ),
    ("teams", "no sound"): (
        "If you have no sound in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then go to: Teams > Settings > Devices and confirm the speaker matches the selected output. "
        "Also check that Teams is not muted in the Windows Volume Mixer."
    ),
    ("teams", "no soud"): (
        "If you have no sound in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then go to: Teams > Settings > Devices and confirm the speaker matches the selected output."
    ),
    # Teams speakers
    ("teams", "speaker"): (
        "Go to: Settings > System > Sound and confirm the correct speaker is selected under Output. "
        "Then in Teams, go to: Settings > Devices and match the speaker selection. "
        "If you can hear other apps but not Teams, check the Windows Volume Mixer for a Teams-specific mute."
    ),
    ("teams", "speakers"): (
        "Go to: Settings > System > Sound and confirm the correct speakers are selected under Output. "
        "Then in Teams, go to: Settings > Devices and match the speaker selection. "
        "Restart Teams after changing device settings to reset the audio session."
    ),
    ("teams", "speeker"): (
        "Go to: Settings > System > Sound and confirm the correct speaker is selected under Output. "
        "Then in Teams, go to: Settings > Devices and match the speaker selection."
    ),
    ("teams", "speekers"): (
        "Go to: Settings > System > Sound and confirm the correct speakers are selected under Output. "
        "Then in Teams, go to: Settings > Devices and match the speaker selection."
    ),
    # Teams headset/headphones/earbuds
    ("teams", "headset"): (
        "Check the headset is powered on and connected first. Then go to: Settings > System > Sound "
        "and confirm the headset is selected for both Input and Output. "
        "In Teams, go to: Settings > Devices and set the headset for the microphone and speaker."
    ),
    ("teams", "headphones"): (
        "Check the headphones are connected and not muted first. Then go to: Settings > System > Sound "
        "and confirm they are selected under Output. "
        "In Teams, go to: Settings > Devices and confirm the headphones are selected for speaker."
    ),
    ("teams", "headphone"): (
        "Check the headphone connection first, then go to: Settings > System > Sound "
        "and confirm it is selected under Output. "
        "In Teams, go to: Settings > Devices and set it as the speaker."
    ),
    ("teams", "earbuds"): (
        "Check the earbuds are connected and not muted first. Then go to: Settings > System > Sound "
        "and confirm they are selected under Output. "
        "In Teams, go to: Settings > Devices and set them as the speaker."
    ),
    ("teams", "earphones"): (
        "Check the earphones are connected first. Then go to: Settings > System > Sound "
        "and confirm they are selected under Output. "
        "In Teams, go to: Settings > Devices and set them as the speaker."
    ),
    # Teams Bluetooth
    ("teams", "bluetooth headset"): (
        "Go to: Settings > Bluetooth & devices and confirm the headset is connected. "
        "Then go to: Settings > System > Sound and select it for both Input and Output. "
        "In Teams, go to: Settings > Devices and match the headset selection."
    ),
    ("teams", "bluetooth headphones"): (
        "Go to: Settings > Bluetooth & devices and confirm the headphones are connected. "
        "Then go to: Settings > System > Sound and select them under Output. "
        "In Teams, go to: Settings > Devices and confirm the headphones are selected as speaker."
    ),
    ("teams", "bluetooth speaker"): (
        "Go to: Settings > Bluetooth & devices and confirm the speaker is connected. "
        "Then go to: Settings > System > Sound and select it under Output. "
        "In Teams, go to: Settings > Devices and confirm it is selected as the speaker."
    ),
    # Teams cant hear
    ("teams", "cant hear"): (
        "If you cannot hear others in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker matches. "
        "Check that Teams is not muted in the Windows Volume Mixer."
    ),
    ("teams", "can't hear"): (
        "If you cannot hear others in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker matches."
    ),
    ("teams", "cnt hear"): (
        "If you cannot hear others in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker is correct."
    ),
    ("teams", "cnt here"): (
        "If you cannot hear others in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker is correct."
    ),
    ("teams", "cnt heer"): (
        "If you cannot hear others in Teams, go to: Settings > System > Sound and confirm the correct Output device is selected. "
        "Then in Teams, go to: Settings > Devices and confirm the speaker is correct."
    ),
    # Teams video / screen share
    ("teams", "video"): (
        "Go to: Settings > Privacy & security > Camera and confirm Teams access is on. "
        "Then in Teams, go to: Settings > Devices and select the correct camera. "
        "If the video preview is blank, leave and rejoin the meeting after selecting the camera."
    ),
    ("teams", "screen"): (
        "For Teams screen sharing, make sure you allow sharing when Teams prompts, then select the correct window or screen. "
        "If the shared screen shows black to others, close any background effects and try sharing a specific window instead of the whole screen. "
        "On Windows 11, check: Settings > Privacy & security > Screen capture and confirm Teams is allowed."
    ),
    ("teams", "display"): (
        "For Teams display sharing, click the Share button in the meeting and choose the correct screen or window. "
        "If others see a black screen, try sharing a specific window instead of the whole desktop. "
        "On Windows 11, check: Settings > Privacy & security > Screen capture and confirm Teams is allowed."
    ),
    # Office printing
    ("word", "printer"): (
        "For Word printing, go to File > Print and confirm the correct printer is selected. "
        "Make sure the printer is powered on, then try a test page from: Settings > Bluetooth & devices > Printers & scanners."
    ),
    ("word", "print"): (
        "For Word printing, go to File > Print and confirm the correct printer is selected. "
        "If no printers appear, go to: Settings > Bluetooth & devices > Printers & scanners and add or repair the printer."
    ),
    ("excel", "printer"): (
        "For Excel printing, go to File > Print and confirm the correct printer is selected. "
        "If the printer is missing, go to: Settings > Bluetooth & devices > Printers & scanners and check its status."
    ),
    ("excel", "print"): (
        "For Excel printing, go to File > Print and confirm the correct printer and layout are selected. "
        "If no printers appear, go to: Settings > Bluetooth & devices > Printers & scanners and add or repair the printer."
    ),
    ("outlook", "printer"): (
        "For Outlook printing, go to File > Print and confirm the correct printer and style are selected. "
        "If the printer is missing, go to: Settings > Bluetooth & devices > Printers & scanners and check its status."
    ),
    ("outlook", "print"): (
        "For Outlook printing, go to File > Print and confirm the correct printer is selected. "
        "If no printers appear, go to: Settings > Bluetooth & devices > Printers & scanners and add or repair the printer."
    ),
    ("powerpoint", "printer"): (
        "For PowerPoint printing, go to File > Print and confirm the correct printer and slide layout are selected. "
        "If the printer is missing, go to: Settings > Bluetooth & devices > Printers & scanners and check its status."
    ),
    ("powerpoint", "print"): (
        "For PowerPoint printing, go to File > Print and confirm the correct printer and handout layout are selected. "
        "If no printers appear, go to: Settings > Bluetooth & devices > Printers & scanners and add or repair the printer."
    ),
    # Outlook calls
    ("outlook", "camera"): (
        "For Outlook camera issues in video calls, go to: Settings > Privacy & security > Camera and confirm Outlook access is on. "
        "Then in the Outlook call, check the video settings and confirm the correct camera is selected."
    ),
    ("outlook", "microphone"): (
        "For Outlook microphone issues, go to: Settings > Privacy & security > Microphone and confirm Outlook access is on. "
        "Then in the Outlook call, check the audio settings and select the correct microphone."
    ),
    ("outlook", "mic"): (
        "For Outlook mic issues, go to: Settings > Privacy & security > Microphone and confirm Outlook access is on. "
        "Then in the call settings, confirm the correct microphone is selected."
    ),
}

KNOWN_ISSUE_RETRIEVAL = (
    {
        "id": "outlook_domain_delivery",
        "service": "outlook",
        "intent": "email_delivery",
        "service_terms": (
            "outlook", "email", "mail", "e-mail",
            "message", "sent", "send",
        ),
        "issue_terms": (
            "domain does not exist",
            "domain doesn't exist",
            "domain doesnt exist",
            "domain not found",
            "recipient domain",
            "domain error",
            "got sent back",
            "sent back",
            "sent bak",
            "got sent bak",
            "bouncd",
            "recipent",
            "came back",
            "domane",
            "does not exizt",
            "domane does not exizt",
            "returned email",
            "returned mail",
            "could not be delivered",
            "couldn't be delivered",
            "couldnt be delivered",
            "undeliverable",
            "bounce back",
            "bounced back",
        ),
    },
    {
        "id": "teams_mic_in_meeting",
        "service": "teams",
        "intent": "audio",
        "service_terms": (
            "teams", "meeting", "call", "conference", "mtg",
        ),
        "issue_terms": (
            "can't hear me",
            "cant hear me",
            "mic not working",
            "muted",
            "no one can hear me",
            "nobody can hear me",
            "peers cant hear me",
            "microphone not working",
            "they cant hear me",
            "people cant hear me",
            "mic dead",
            "mic broke",
            "voice not going through",
            "my audio isnt transmitting",
            "noone hears me",
            "nobody hears me",
            "hear nobody from me",
            "collegues cant hear me",
            "coworkers cant hear me",
        ),
    },
    {
        "id": "onedrive_sync_conflict",
        "service": "onedrive",
        "intent": "sync",
        "service_terms": (
            "onedrive", "one drive", "cloud", "files",
        ),
        "issue_terms": (
            "sync conflict",
            "conflicting copy",
            "duplicate file",
            "duplicate copy",
            "two copies",
            "same file twice",
            "same spreadsheet twice",
            "duplicate conflict",
            "two versions",
            "conflict copy",
            "conflict copies",
            "file conflict",
            "version conflict",
            "conflicted copy",
            "offline work",
            "offline edit",
            "made duplicate",
            "made a duplicate",
        ),
    },
    {
        "id": "office_activation_error",
        "service": "microsoft 365",
        "intent": "activation",
        "service_terms": (
            "office", "microsoft 365", "word", "excel", "powerpoint", "outlook",
        ),
        "issue_terms": (
            "product activation failed",
            "unlicensed product",
            "subscription expired",
            "activate office",
            "not activated",
            "activation required",
            "license expired",
            "needs activation",
            "trial expired",
        ),
    },
    {
        "id": "windows_update_stuck",
        "service": "windows",
        "intent": "update",
        "service_terms": (
            "windows", "update", "pc", "computer",
        ),
        "issue_terms": (
            "update stuck",
            "update won't install",
            "update loop",
            "pending restart",
            "update error",
            "stuck on update",
            "update keeps failing",
            "update frozen",
            "update not installing",
            "checking for updates forever",
        ),
    },
    {
        "id": "teams_screen_share",
        "service": "teams",
        "intent": "display",
        "service_terms": (
            "teams", "meeting", "call", "screen share", "sharing",
        ),
        "issue_terms": (
            "screen share not working",
            "can't share screen",
            "share screen black",
            "others can't see my screen",
            "sharing shows black",
            "screen sharing broken",
            "cant share screen",
            "black screen when sharing",
            "screen share failed",
            "presentation not showing",
        ),
    },
)

# Hardware-specific support replies for exact device/settings issues.
HARDWARE_FALLBACK_RESPONSES = {
    "mic": (
        "First make sure the mic is not muted on the headset, keyboard, or inline cable. "
        "Then go to: Settings > Privacy & security > Microphone and confirm microphone access is on. "
        "After that, open Teams or the app you are using and confirm the correct input device is selected."
    ),
    "microphone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "mics": (
        "First make sure the mic is not muted on the headset, keyboard, or inline cable. "
        "Then go to: Settings > Privacy & security > Microphone and confirm microphone access is on, "
        "and check the app's audio settings for the correct input device."
    ),
    "microphones": (
        "First make sure the microphone is connected and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is on, "
        "and verify the correct input device is selected in the app."
    ),
    "webcam": (
        "Go to: Settings > Privacy & security > Camera and make sure camera access is enabled. "
        "Then check the app's video settings and confirm the correct camera is selected. "
        "If it still does not appear, run Windows Update for possible driver fixes."
    ),
    "camera": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "headphones": (
        "Check that the headphones are fully plugged in or paired and that the headset itself is not muted. "
        "Then go to: Settings > System > Sound and make sure your headphones are selected under Output."
    ),
    "headphone": (
        "Check that the headphone connection is secure and that the device is not muted first. "
        "Then go to: Settings > System > Sound and make sure it is selected under Output."
    ),
    "headset": (
        "Start by checking the cable, dongle, or Bluetooth connection and make sure the headset is powered on. "
        "Then go to: Settings > System > Sound and confirm the headset is selected for both Input and Output."
    ),
    "earphones": (
        "Check that the earphones are fully connected or paired first. Then go to: Settings > System > Sound "
        "and make sure the correct output device is selected."
    ),
    "earbuds": (
        "Make sure the earbuds are charged, connected, and not muted first. Then go to: Settings > System > Sound "
        "and set them as the selected output or input device."
    ),
    "speaker": (
        "Make sure volume is up and the device is not muted first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speakers": (
        "Make sure volume is up and the speakers are connected first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speeker": (
        "Make sure volume is up and the speaker is connected first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speekers": (
        "Make sure volume is up and the speakers are connected first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "bluetooth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluetooth headphones": (
        "Go to: Settings > Bluetooth & devices and confirm the headphones show as connected. "
        "If they keep failing, remove them and pair them again, then go to: Settings > System > Sound and select them as the output device."
    ),
    "bluetooth headset": (
        "Go to: Settings > Bluetooth & devices and confirm the headset is connected. "
        "Then go to: Settings > System > Sound and select it for both Input and Output if you need the microphone too."
    ),
    "bluetooth speaker": (
        "Go to: Settings > Bluetooth & devices and confirm the speaker is connected. "
        "Then go to: Settings > System > Sound and select it as the Output device."
    ),
    "bluetooth mouse": (
        "Go to: Settings > Bluetooth & devices and confirm the mouse is paired and connected. "
        "If it is listed but not working, remove it, pair it again, and check the battery."
    ),
    "bluetooth keyboard": (
        "Go to: Settings > Bluetooth & devices and confirm the keyboard is paired and connected. "
        "If it is listed but not typing, remove it, pair it again, and check the battery."
    ),
    "printer": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "monitor": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    "usb": (
        "For USB issues, try a different port first, then open File Explorer to check whether the device appears. "
        "If it still does not show, check Windows Device Manager for driver errors."
    ),
    "usb stick": (
        "Try a different USB port first, then open File Explorer to see whether the USB stick appears. "
        "If it does not, open Device Manager and check for USB or disk drive warnings."
    ),
    "usb stik": (
        "Try a different USB port first, then open File Explorer to see whether the USB stick appears. "
        "If it does not, open Device Manager and check for USB or disk drive warnings."
    ),
    "audio": (
        "First check whether the device is muted or the wrong headset or speaker is selected. "
        "Then go to: Settings > System > Sound and review both Output and Input device selections."
    ),
    "audio output": (
        "Go to: Settings > System > Sound and review the Output section to make sure the correct speaker, monitor, or headset is selected. "
        "If this is in Teams, also go to: Teams > Settings > Devices and confirm the correct speaker is selected."
    ),
    "audio input": (
        "Go to: Settings > System > Sound and review the Input section to make sure the correct microphone is selected. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is on. If this is in Teams, also check: Teams > Settings > Devices."
    ),
    "sound": (
        "Start by checking volume, mute, and whether the correct device is connected. "
        "Then go to: Settings > System > Sound and verify the right Output or Input device is selected."
    ),
    "no sound": (
        "Check whether the device is muted and whether the right headset, speaker, or monitor is selected first. "
        "Then go to: Settings > System > Sound and verify the correct output device under Output."
    ),
    "no soud": (
        "Check whether the device is muted and whether the right headset, speaker, or monitor is selected first. "
        "Then go to: Settings > System > Sound and verify the correct Output device."
    ),
    "cant hear": (
        "First make sure the volume is up and the correct headset, speaker, or monitor is selected. "
        "Then go to: Settings > System > Sound and verify the Output device."
    ),
    "cnt hear": (
        "First make sure the volume is up and the correct headset, speaker, or monitor is selected. "
        "Then go to: Settings > System > Sound and verify the Output device."
    ),
    "cnt here": (
        "First make sure the volume is up and the correct headset, speaker, or monitor is selected. "
        "Then go to: Settings > System > Sound and verify the Output device."
    ),
    "cnt heer": (
        "First make sure the volume is up and the correct headset, speaker, or monitor is selected. "
        "Then go to: Settings > System > Sound and verify the Output device."
    ),
    "can't hear": (
        "First make sure the volume is up and the correct headset, speaker, or monitor is selected. "
        "Then go to: Settings > System > Sound and verify the Output device."
    ),
    "video": (
        "Go to: Settings > Privacy & security > Camera and make sure camera access is enabled. "
        "Then open your app's video settings and choose the correct camera."
    ),
    "display": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "hdmi": (
        "Make sure the HDMI cable is fully seated on both ends and the monitor or TV is set to the HDMI input you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the screen."
    ),
    "displayport": (
        "Make sure the DisplayPort cable is firmly connected and the monitor is set to the correct input. "
        "Then press Windows + P and go to: Settings > System > Display to detect the screen."
    ),
    "second screen": (
        "Make sure the second display is powered on and connected to the right port. "
        "Then press Windows + P and go to: Settings > System > Display > Multiple displays to detect and arrange it."
    ),
    "second monitor": (
        "Check that the second monitor is powered on and using the correct input source. "
        "Then press Windows + P and go to: Settings > System > Display > Multiple displays to detect it."
    ),
    "secnd monitor": (
        "Check that the second monitor is powered on and using the correct input source. "
        "Then press Windows + P and go to: Settings > System > Display > Multiple displays to detect it."
    ),
    "secnd moniter": (
        "Check that the second monitor is powered on and using the correct input source. "
        "Then press Windows + P and go to: Settings > System > Display > Multiple displays to detect it."
    ),
    "external monitor": (
        "Check the cable, adapter, and monitor input first. Then go to: Settings > System > Display > Multiple displays "
        "and select Detect if Windows does not see the monitor."
    ),
    "dual monitor": (
        "Check the cable and input source on both screens first. Then press Windows + P and go to: Settings > System > Display "
        "to set the screens to Extend and arrange them correctly."
    ),
    "dual monitors": (
        "Check the cable and input source on both screens first. Then press Windows + P and go to: Settings > System > Display "
        "to set the screens to Extend and arrange them correctly."
    ),
    "dual screens": (
        "Check the cable and input source on both screens first. Then press Windows + P and go to: Settings > System > Display "
        "to set the screens to Extend and arrange them correctly."
    ),
    "screen": (
        "If this is a second-display issue, check the cable and monitor input first. Then go to: Settings > System > Display "
        "and use Detect if Windows does not see the screen."
    ),
    "projector": (
        "Make sure the projector is powered on, connected firmly, and set to the right input source first. "
        "Then press Windows + P and choose Duplicate or Extend as needed."
    ),
    "wifi": (
        "Make sure Wi-Fi is turned on and that Airplane mode is off first. Then go to: Settings > Network & internet > Wi-Fi "
        "and reconnect to the network. If it still fails, check Windows Update for adapter updates."
    ),
    "wi-fi": (
        "Make sure Wi-Fi is turned on and that Airplane mode is off first. Then go to: Settings > Network & internet > Wi-Fi "
        "and reconnect to the network. If it still fails, check Windows Update for adapter updates."
    ),
    "usb drive": (
        "Try a different USB port first, then open File Explorer to see if the drive appears. "
        "If not, open Device Manager and check whether Windows sees the device with a warning icon."
    ),
    "flsh drv": (
        "Try a different USB port first, then open File Explorer to see if the flash drive appears. "
        "If not, open Device Manager and check whether Windows sees the device with a warning icon."
    ),
    "flash drv": (
        "Try a different USB port first, then open File Explorer to see if the flash drive appears. "
        "If not, open Device Manager and check whether Windows sees the device with a warning icon."
    ),
    "usb c": (
        "Check that the USB-C cable or adapter is fully seated first, then try another port if available. "
        "If the device still is not detected, open Device Manager and check for driver warnings."
    ),
    "usb-c": (
        "Check that the USB-C cable or adapter is fully seated first, then try another port if available. "
        "If the device still is not detected, open Device Manager and check for driver warnings."
    ),
    "flash drive": (
        "Try a different USB port first, then open File Explorer to see if the drive appears. "
        "If not, open Device Manager and check whether Windows sees the device with a warning icon."
    ),
    "thumb drive": (
        "Try a different USB port first, then open File Explorer to see if the drive appears. "
        "If not, open Device Manager and check whether Windows sees the device with a warning icon."
    ),
    "external drive": (
        "Try a different port or cable first, then open File Explorer to see whether the external drive appears. "
        "If it is still missing, open Device Manager and check for a warning icon under disk or USB devices."
    ),
    "scanner": (
        "Make sure the scanner is powered on and connected first. Then go to: Settings > Bluetooth & devices > Printers & scanners "
        "and confirm Windows sees it. If not, remove and add it again."
    ),
    "airpods": (
        "Make sure the AirPods have charge and are connected in Windows first. Then go to: Settings > Bluetooth & devices "
        "to confirm they show as connected, and go to: Settings > System > Sound to set them as Input or Output."
    ),
    "air pods": (
        "Make sure the AirPods have charge and are connected in Windows first. Then go to: Settings > Bluetooth & devices "
        "to confirm they show as connected, and go to: Settings > System > Sound to set them as Input or Output."
    ),
    "docking station": (
        "Check that the dock is powered and the cable to the laptop is fully seated first. "
        "Then reconnect the dock and go to: Settings > System > Display or Settings > System > Sound depending on which device is missing."
    ),
    "not detected": (
        "Start with the simple checks: reconnect the device, try another port if possible, and make sure it has power. "
        "If Windows still does not see it, open Device Manager and check for warning icons or disabled devices."
    ),
    "keyboard": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "mouse": (
        "Check the mouse battery or cable first, then try a different USB port if it has a receiver. If it is Bluetooth, go to: Settings > Bluetooth & devices and reconnect it."
    ),
    "mouce": (
        "Check the mouse battery or cable first, then try a different USB port if it has a receiver. If it is Bluetooth, go to: Settings > Bluetooth & devices and reconnect it."
    ),
    "touchpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "trackpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the trackpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    # Microphone misspellings
    "micorphone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "micrphone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "micropone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "mikrofone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "mircophone": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    "microphne": (
        "Start with the simple check: make sure the microphone is plugged in and not muted. "
        "Then go to: Settings > Privacy & security > Microphone and confirm access is allowed, "
        "and check the app's audio settings for the correct input device."
    ),
    # Camera misspellings
    "camra": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "camrea": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "cmaera": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "kamera": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "camerra": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    "cameraa": (
        "Go to: Settings > Privacy & security > Camera and confirm camera access is turned on. "
        "If you are using the browser, also allow camera access for the site, then verify the right camera is selected in the app."
    ),
    # Keyboard misspellings
    "keybord": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "keybard": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "keyborad": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "kyboard": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "keybrd": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    "keybaord": (
        "Check whether the keyboard is wired, wireless, or Bluetooth first. Reseat the cable or check the battery, then go to: Settings > Bluetooth & devices > Devices and confirm Windows sees it."
    ),
    # Monitor misspellings
    "monitr": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    "monitar": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    "mointor": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    "monitur": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    "moniotr": (
        "Make sure the monitor is on, the cable is firmly connected, and the display input matches the cable you are using. "
        "Then press Windows + P and go to: Settings > System > Display to detect the second screen."
    ),
    # Bluetooth misspellings
    "blutooth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluethooth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluetoth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluettoth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bleutooth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluetooh": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    "bluetoooth": (
        "Go to: Settings > Bluetooth & devices and confirm Bluetooth is on and the device is connected. "
        "If it keeps failing, remove the device and pair it again, then check Windows Update for driver fixes."
    ),
    # Headphones misspellings
    "hedphones": (
        "Check that the headphones are fully plugged in or paired and that the headset itself is not muted. "
        "Then go to: Settings > System > Sound and make sure your headphones are selected under Output."
    ),
    "headfones": (
        "Check that the headphones are fully plugged in or paired and that the headset itself is not muted. "
        "Then go to: Settings > System > Sound and make sure your headphones are selected under Output."
    ),
    "headhpones": (
        "Check that the headphones are fully plugged in or paired and that the headset itself is not muted. "
        "Then go to: Settings > System > Sound and make sure your headphones are selected under Output."
    ),
    "hedset": (
        "Start by checking the cable, dongle, or Bluetooth connection and make sure the headset is powered on. "
        "Then go to: Settings > System > Sound and confirm the headset is selected for both Input and Output."
    ),
    "heaset": (
        "Start by checking the cable, dongle, or Bluetooth connection and make sure the headset is powered on. "
        "Then go to: Settings > System > Sound and confirm the headset is selected for both Input and Output."
    ),
    "headfone": (
        "Check that the headphone connection is secure and that the device is not muted first. "
        "Then go to: Settings > System > Sound and make sure it is selected under Output."
    ),
    "hedphone": (
        "Check that the headphone connection is secure and that the device is not muted first. "
        "Then go to: Settings > System > Sound and make sure it is selected under Output."
    ),
    # Printer misspellings
    "printr": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "prnter": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "priinter": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "priner": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "prinetr": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    "printar": (
        "Make sure the printer is powered on and connected to the same network or cable first. "
        "Then go to: Settings > Bluetooth & devices > Printers & scanners, remove the printer if needed, and add it again."
    ),
    # Scanner misspellings
    "scaner": (
        "Make sure the scanner is powered on and connected first. Then go to: Settings > Bluetooth & devices > Printers & scanners "
        "and confirm Windows sees it. If not, remove and add it again."
    ),
    "scannr": (
        "Make sure the scanner is powered on and connected first. Then go to: Settings > Bluetooth & devices > Printers & scanners "
        "and confirm Windows sees it. If not, remove and add it again."
    ),
    "scannar": (
        "Make sure the scanner is powered on and connected first. Then go to: Settings > Bluetooth & devices > Printers & scanners "
        "and confirm Windows sees it. If not, remove and add it again."
    ),
    "scannner": (
        "Make sure the scanner is powered on and connected first. Then go to: Settings > Bluetooth & devices > Printers & scanners "
        "and confirm Windows sees it. If not, remove and add it again."
    ),
    # Speaker misspellings
    "speker": (
        "Make sure volume is up and the device is not muted first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speakr": (
        "Make sure volume is up and the device is not muted first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speakrs": (
        "Make sure volume is up and the speakers are connected first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "speakerr": (
        "Make sure volume is up and the device is not muted first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    "spaeaker": (
        "Make sure volume is up and the device is not muted first. Then go to: Settings > System > Sound "
        "and confirm the correct output device is selected under Output."
    ),
    # Touchpad misspellings
    "tuchpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "touchpd": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "tochpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "tuchpd": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "touchapd": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    # Display misspellings
    "displya": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "diplay": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "dsplay": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "dipslay": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "disply": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    "displau": (
        "Check the cable and the monitor's input source first. Then go to: Settings > System > Display "
        "and select Detect if the extra screen does not appear."
    ),
    # Screen misspellings
    "scren": (
        "If this is a second-display issue, check the cable and monitor input first. Then go to: Settings > System > Display "
        "and use Detect if Windows does not see the screen."
    ),
    "scrren": (
        "If this is a second-display issue, check the cable and monitor input first. Then go to: Settings > System > Display "
        "and use Detect if Windows does not see the screen."
    ),
    "sreen": (
        "If this is a second-display issue, check the cable and monitor input first. Then go to: Settings > System > Display "
        "and use Detect if Windows does not see the screen."
    ),
    "srceen": (
        "If this is a second-display issue, check the cable and monitor input first. Then go to: Settings > System > Display "
        "and use Detect if Windows does not see the screen."
    ),
}


# ============================================================
# Utility helpers
# ============================================================

def _normalize_message(message):
    return _normalize_message_core(message)


def _fuzzy_detect_service(message):
    return _fuzzy_detect_service_core(message, SERVICE_KEYWORDS)


def _fuzzy_detect_intent(message):
    return _fuzzy_detect_intent_core(message, INTENT_KEYWORDS)


def _term_in_text(text, term):
    return _term_in_text_core(text, term)


def _contains_any(text, terms):
    return _contains_any_core(text, terms)


def _detect_all_services(message):
    return _detect_all_services_core(message, SERVICE_KEYWORDS)


def _canonical_service(service_name, fallback=None):
    return _canonical_service_core(service_name, SERVICE_KEYWORDS, fallback=fallback)


def _service_label(service):
    return _service_label_core(service, SERVICE_LABELS)


def _detect_unsupported_service(message):
    return _detect_unsupported_service_core(
        message,
        UNSUPPORTED_STATUS_KEYWORDS,
        UNSUPPORTED_SERVICE_KEYWORDS,
    )


def _get_hardware_context(message):
    return _get_hardware_context_core(
        message,
        AUDIO_INPUT_ISSUE_TERMS,
        AUDIO_OUTPUT_ISSUE_TERMS,
        HARDWARE_SERVICE_MAP,
        FUZZY_HARDWARE_TERMS,
        OUT_OF_SCOPE_HARDWARE,
    )


def _parse_session_summary(session_summary):
    raw_summary = str(session_summary or "").strip()
    if not raw_summary:
        return {}

    try:
        parsed = json.loads(raw_summary)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _merge_thread_memory_with_session_summary(thread_memory, session_summary):
    summary = _parse_session_summary(session_summary)
    summary_threads = summary.get("threads") or []
    if not summary_threads:
        return thread_memory

    merged_threads = list((thread_memory or {}).get("threads") or [])
    existing = {thread.get("service"): thread for thread in merged_threads if thread.get("service")}
    last_turn_seed = min(
        [thread.get("last_turn", 0) for thread in merged_threads] or [0]
    ) - 1

    for index, item in enumerate(summary_threads):
        service = _canonical_service(item.get("service"))
        if not service or service == "microsoft 365":
            continue

        snippet = str(item.get("snippet") or "").strip()
        summary_intent = str(item.get("intent") or "unknown").strip() or "unknown"
        existing_thread = existing.get(service)
        if existing_thread:
            if snippet and snippet not in existing_thread.get("recent_messages", []):
                existing_thread.setdefault("recent_messages", []).append(snippet)
                existing_thread["recent_messages"] = existing_thread["recent_messages"][-4:]
            if summary_intent != "unknown" and existing_thread.get("last_intent") == "unknown":
                existing_thread["last_intent"] = summary_intent
            if snippet:
                existing_thread.setdefault("keywords", set()).update(
                    _memory_tokens(snippet)
                )
            continue

        synthetic_thread = {
            "service": service,
            "last_intent": summary_intent,
            "recent_messages": [snippet] if snippet else [],
            "keywords": _memory_tokens(snippet) if snippet else set(),
            "last_turn": last_turn_seed - index,
        }
        merged_threads.append(synthetic_thread)
        existing[service] = synthetic_thread

    merged_threads = sorted(
        merged_threads,
        key=lambda item: item.get("last_turn", 0),
        reverse=True,
    )

    merged_last_service = thread_memory.get("last_service") if thread_memory else None
    if not merged_last_service:
        merged_last_service = _canonical_service(summary.get("current_focus"))

    return {
        "threads": merged_threads,
        "last_service": merged_last_service,
    }


def _merge_history_context_with_session_summary(history_context, session_summary):
    summary = _parse_session_summary(session_summary)
    if not summary:
        return history_context

    merged = dict(history_context or {})
    services_mentioned = list(merged.get("services_mentioned") or [])
    for item in summary.get("threads") or []:
        service = _canonical_service(item.get("service"))
        if service and service != "microsoft 365" and service not in services_mentioned:
            services_mentioned.append(service)

    current_focus = _canonical_service(summary.get("current_focus"))
    if current_focus and current_focus != "microsoft 365":
        merged["current_focus"] = current_focus
        merged["last_service"] = current_focus
        if current_focus not in services_mentioned:
            services_mentioned.insert(0, current_focus)

    merged["services_mentioned"] = services_mentioned
    if services_mentioned:
        merged["has_prior_context"] = True
    return merged


def _extract_history_context(conversation_history, session_summary=""):
    history_context = extract_history_context(
        conversation_history,
        normalize_message=_normalize_message,
        detect_all_services=_detect_all_services,
    )
    return _merge_history_context_with_session_summary(history_context, session_summary)


def _build_thread_memory(conversation_history, session_summary=""):
    thread_memory = build_thread_memory(
        conversation_history,
        normalize_message=_normalize_message,
        detect_all_services=_detect_all_services,
        get_hardware_context=_get_hardware_context,
        fuzzy_detect_service=_fuzzy_detect_service,
        detect_intent=_detect_intent,
    )
    return _merge_thread_memory_with_session_summary(thread_memory, session_summary)


def _related_history_match(message, thread_memory):
    return related_history_match(
        message,
        thread_memory,
        contains_any=_contains_any,
    )


def _clarify_current_application_reply(thread_memory):
    return clarify_current_application_reply(
        thread_memory,
        service_label=_service_label,
    )


def _should_clarify_current_application(message, history_context, related_match,
                                        explicit_service=None, fuzzy_service=None,
                                        hardware_context=None, multi_context=None):
    return should_clarify_current_application(
        message,
        history_context,
        related_match,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        multi_context=multi_context,
    )


def _capability_history_match(message, history_context, thread_memory):
    prior_services = []

    def add_prior(service):
        canonical = _canonical_service(service)
        if canonical and canonical != "microsoft 365" and canonical not in prior_services:
            prior_services.append(canonical)

    for service in history_context.get("services_mentioned") or []:
        add_prior(service)
    for thread in (thread_memory or {}).get("threads") or []:
        add_prior(thread.get("service"))

    if not prior_services:
        return {
            "service": None,
            "score": 0,
            "matched_terms": [],
        }

    scored = []
    for service in prior_services:
        terms = SERVICE_CAPABILITY_TERMS.get(service, ())
        matched_terms = [term for term in terms if _term_in_text(message, term)]
        if not matched_terms:
            continue
        scored.append({
            "service": service,
            "score": len(matched_terms),
            "matched_terms": matched_terms,
        })

    if not scored:
        return {
            "service": None,
            "score": 0,
            "matched_terms": [],
        }

    scored.sort(key=lambda item: item["score"], reverse=True)
    best = scored[0]
    second_score = scored[1]["score"] if len(scored) > 1 else 0
    if best["score"] <= second_score:
        return {
            "service": None,
            "score": best["score"],
            "matched_terms": best["matched_terms"],
        }
    return best


def _should_inherit_recent_service(
    message,
    history_context,
    related_match,
    explicit_service=None,
    fuzzy_service=None,
    hardware_context=None,
    multi_context=None,
):
    if explicit_service or fuzzy_service:
        return False
    if hardware_context and hardware_context.get("suggested_service"):
        return False
    if multi_context and multi_context.get("is_multi"):
        return False

    last_service = history_context.get("current_focus") or history_context.get("last_service")
    if not last_service or last_service == "microsoft 365":
        return False

    word_count = len(str(message or "").split())
    if related_match.get("score", 0) >= 2:
        return True
    if related_match.get("referential") and word_count <= 10:
        return True
    if word_count <= 6 and _contains_any(message, CONTEXT_FOLLOW_UP_TERMS):
        return True
    return False



def _inherited_context_is_ambiguous(
    history_context,
    related_match,
    explicit_service=None,
    fuzzy_service=None,
    hardware_context=None,
    multi_context=None,
):
    if explicit_service or fuzzy_service:
        return False
    if hardware_context and hardware_context.get("suggested_service"):
        return False
    if multi_context and multi_context.get("is_multi"):
        return False
    current_focus = history_context.get("current_focus")
    if current_focus and current_focus != "microsoft 365":
        return False
    services_mentioned = [
        service for service in (history_context.get("services_mentioned") or [])
        if service and service != "microsoft 365"
    ]
    if len(services_mentioned) <= 1:
        return False
    return related_match.get("score", 0) < 2



def _current_issue_follow_up_reply(service):
    service_label = _service_label(service)
    return (
        f"We are still on {service_label}. Tell me what it is doing right now, "
        "like the exact error, the step that fails, or what changed since it last worked."
    )


def _refine_multi_issue_context(message, service, multi_context, explicit_service=None):
    if not multi_context.get("is_multi"):
        return multi_context

    services = [
        item for item in (multi_context.get("services") or [])
        if item and item != "microsoft 365"
    ]
    hardware_terms = list(multi_context.get("hardware_terms") or [])

    if (
        service in {"onedrive", "sharepoint"}
        and any(item in OFFICE_FILE_SERVICES for item in services)
        and _contains_any(
            message,
            (
                "sync", "pending", "conflict", "duplicate", "offline",
                "shortcut", "target moved", "backup", "vault", "locked",
                "checked out", "file", "folder", "library",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": [service],
            "hardware_terms": [],
        }

    if (
        service == "teams"
        and hardware_terms
        and set(hardware_terms).issubset(FALSE_MULTI_TEAM_HARDWARE_TERMS)
        and _contains_any(
            message,
            (
                "meeting", "call", "camera", "mic", "mute", "audio",
                "video", "black", "hear", "screen share", "screen sharing",
                "sharing screen", "presenting",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": ["teams"],
            "hardware_terms": [],
        }

    if (
        {"teams", "outlook"}.issubset(set(services))
        and (
            explicit_service == "outlook"
            or _contains_any(message, ("outlook", "mailbox", "shared calendar", "delegate"))
        )
        and _contains_any(
            message,
            (
                "calendar", "calender", "shared calendar", "delegate",
                "delegates", "boss calendar", "old meetings", "meeting updates",
                "not updating", "isn't updating", "isnt updating",
            ),
        )
        and not _contains_any(
            message,
            (
                "teams", "teems", "channel", "chat", "banner", "notification",
                "mic", "camera", "join meeting", "screen share",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": ["outlook"],
            "hardware_terms": [],
        }

    if (
        {"teams", "outlook"}.issubset(set(services))
        and _contains_any(
            message,
            (
                "teams addin", "teams add-in", "new teams meeting",
                "teams link button", "meeting addin", "meeting add-in",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": ["teams"],
            "hardware_terms": [],
        }

    if (
        explicit_service == "sharepoint"
        and "word" in services
        and _contains_any(
            message,
            (
                "metadata", "required columns", "required column",
                "document info panel", "properties pane", "properties panel",
                "column values", "info panel",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": ["sharepoint"],
            "hardware_terms": [],
        }

    if (
        service in OFFICE_FILE_SERVICES
        and hardware_terms
        and set(hardware_terms).issubset(FALSE_MULTI_OFFICE_HARDWARE_TERMS)
        and _contains_any(
            message,
            (
                "preview", "print preview", "presenter view", "slide",
                "deck", "document", "sheet", "layout", "fonts", "markup",
                "presenter", "audience", "embedded video", "video",
            ),
        )
    ):
        return {
            "is_multi": False,
            "services": [service],
            "hardware_terms": [],
        }

    if (
        explicit_service == "onedrive"
        and _contains_any(message, ("personal vault", "vault"))
    ):
        return {
            "is_multi": False,
            "services": ["onedrive"],
            "hardware_terms": [],
        }

    if (
        {"onedrive", "microsoft account"}.issubset(set(services))
        and explicit_service == "onedrive"
        and _contains_any(message, PASSWORD_PROMPT_LOOP_TERMS)
    ):
        return {
            "is_multi": False,
            "services": ["onedrive"],
            "hardware_terms": [],
        }

    return multi_context


def _thread_for_service(thread_memory, service):
    for thread in (thread_memory or {}).get("threads", []):
        if thread.get("service") == service:
            return thread
    return None


def _is_queue_handoff_message(message, service, thread_memory):
    if not service or service == "microsoft 365":
        return False
    if not _thread_for_service(thread_memory, service):
        return False
    if not _contains_any(message, QUEUE_HANDOFF_TERMS):
        return False
    return len(str(message or "").split()) <= 8


def _compact_reply_snippet(text, max_chars=120):
    compact = re.sub(r"\s+", " ", str(text or "").strip())
    if len(compact) <= max_chars:
        return compact
    return compact[: max_chars - 3].rstrip() + "..."


def _service_specific_thread_snippet(service, text):
    raw_text = str(text or "").strip()
    if not raw_text:
        return ""

    lower_text = raw_text.lower()
    clauses = [
        clause.strip(" ,.;")
        for clause in re.split(r"\b(?:and|but|also|plus)\b|[.,;]", raw_text, flags=re.IGNORECASE)
        if clause and clause.strip(" ,.;")
    ]

    for clause in clauses:
        lower_clause = clause.lower()
        if any(_term_in_text(lower_clause, keyword) for keyword in SERVICE_KEYWORDS.get(service, ())):
            return _compact_reply_snippet(clause, 140)

    keyword_positions = []
    for keyword in SERVICE_KEYWORDS.get(service, ()):
        index = lower_text.find(str(keyword).lower())
        if index >= 0:
            keyword_positions.append(index)

    if not keyword_positions:
        return _compact_reply_snippet(raw_text, 140)

    start = min(keyword_positions)
    end = len(raw_text)
    for separator in (" and ", " but ", ";", ".", ", and ", ","):
        next_index = lower_text.find(separator, start + 1)
        if next_index != -1:
            end = min(end, next_index)

    snippet = raw_text[start:end].strip(" ,.;")
    if snippet and len(snippet) > len(service) + 4:
        return _compact_reply_snippet(snippet, 140)
    return _compact_reply_snippet(raw_text, 140)


def _queued_issue_handoff_payload(service, thread):
    service_label = _service_label(service)
    last_intent = thread.get("last_intent", "unknown")
    recent_messages = thread.get("recent_messages") or []
    recent_message = recent_messages[-1] if recent_messages else ""
    snippet = _service_specific_thread_snippet(service, recent_message)
    snippet_intent = _detect_intent(_normalize_message(snippet)) if snippet else "unknown"
    if snippet_intent != "unknown":
        last_intent = snippet_intent

    if (
        last_intent == "update"
        and service != "windows"
        and (service, last_intent) not in SERVICE_INTENT_RESPONSES
    ):
        last_intent = "unknown"

    if (
        last_intent in SHORT_STEP_RESPONSES
        or (service, last_intent) in SERVICE_INTENT_RESPONSES
    ):
        blocks = [
            f"Switching to {service_label}.",
            "I kept the earlier issue context for this app, so we can pick it back up without starting over.",
        ]
        if snippet:
            blocks.append(f"Earlier you mentioned: \"{snippet}\"")
        blocks.append(_rule_based_step_reply(service, last_intent))
        return {
            "reply": _build_block_reply(blocks),
            "intent": last_intent,
        }

    if snippet:
        return {
            "reply": _build_reply([
                f"Switching to {service_label}.",
                f"Earlier you mentioned: \"{snippet}\"",
                f"If that is still the {service_label} issue you want next, tell me the exact step that is failing now or any error text you see.",
            ]),
            "intent": last_intent if last_intent != "unknown" else "unknown",
        }

    return {
        "reply": _build_reply([
            f"Switching to {service_label}.",
            f"Tell me what the {service_label} issue is doing right now and I will pick that thread back up.",
        ]),
        "intent": last_intent if last_intent != "unknown" else "unknown",
    }


def _is_history_recap_request(message):
    return _contains_any(message, HISTORY_RECAP_TERMS)


def _service_thread_issue_snippets(service, thread):
    snippets = []
    for raw_message in reversed(thread.get("recent_messages") or []):
        snippet = _service_specific_thread_snippet(service, raw_message)
        if snippet and snippet not in snippets:
            snippets.append(snippet)
    return snippets[:3]


def _history_recap_reply(thread_memory):
    threads = [
        thread
        for thread in (thread_memory.get("threads") or [])
        if thread.get("service") and thread.get("service") != "microsoft 365"
    ]
    if not threads:
        return (
            "I do not have a clear list of earlier app threads yet. Tell me the Microsoft app "
            "you want to go back to and I will focus there."
        )

    blocks = ["So far in this session, these are the main app threads I have tracked:"]
    for index, thread in enumerate(threads[:4], start=1):
        service = thread.get("service")
        label = _service_label(service)
        snippets = _service_thread_issue_snippets(service, thread)
        if snippets:
            blocks.append(f"{index}. {label} — {snippets[0]}")
        else:
            blocks.append(f"{index}. {label}")

    blocks.append(
        "Tell me which one you want to go back to, and I will pick that thread up."
    )
    return _build_block_reply(blocks)


def _service_thread_recap_reply(service, thread):
    service_label = _service_label(service)
    snippets = _service_thread_issue_snippets(service, thread)
    if not snippets:
        return _build_reply([
            f"I can go back to the earlier {service_label} thread.",
            f"Tell me what the {service_label} issue is doing right now and I will continue from there.",
        ])

    if len(snippets) == 1:
        return _build_block_reply([
            f"I can go back to the earlier {service_label} thread.",
            f"The last {service_label} issue I tracked was: \"{snippets[0]}\"",
            f"If that is the same issue, tell me what changed now or paste the exact error text you see.",
        ])

    lines = [f"I can go back to the earlier {service_label} threads.", "I still have these recent issue paths for that app:"]
    for index, snippet in enumerate(snippets, start=1):
        lines.append(f"{index}. {snippet}")
    lines.append(f"Tell me which {service_label} thread you mean, and I will stay on that one.")
    return _build_block_reply(lines)


def _detect_intent(message):
    return _detect_intent_core(message, INTENT_KEYWORDS)


def _retrieve_known_issue(message):
    """
    Tiny local retrieval layer for high-confidence support phrases.
    This is intentionally narrow: no browser, no private data leaves
    the app, and entries must include both service and issue clues.
    """
    for entry in KNOWN_ISSUE_RETRIEVAL:
        if not _contains_any(message, entry["service_terms"]):
            continue
        if not _contains_any(message, entry["issue_terms"]):
            continue
        return entry
    return None


def _looks_like_vague_service_message(message, service, intent,
                                      explicit_service=None, fuzzy_service=None,
                                      hardware_context=None, known_issue=None,
                                      multi_context=None):
    return _looks_like_vague_service_message_core(
        message,
        service,
        intent,
        VAGUE_SERVICE_MESSAGE_TERMS,
        SHORT_SERVICE_ACTION_TERMS,
        (),
        STRONG_OUTAGE_TERMS,
        TEAMS_JOIN_TERMS,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        known_issue=known_issue,
        multi_context=multi_context,
    )


def _has_detailed_description(message):
    return _has_detailed_description_core(message, DETAIL_HINT_TERMS)


def _is_non_issue_message(message, intent="unknown",
                          escalation_requested=False,
                          awaiting_ticket_detail=False):
    return _is_non_issue_message_core(
        message,
        POSITIVE_RESOLUTION_TERMS,
        GRATITUDE_TERMS,
        CONTINUING_ISSUE_TERMS,
        DETAIL_HINT_TERMS,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    )


def _is_greeting_only(message, intent="unknown",
                      escalation_requested=False,
                      awaiting_ticket_detail=False):
    return _is_greeting_only_core(
        message,
        GREETING_TERMS,
        CONTINUING_ISSUE_TERMS,
        DETAIL_HINT_TERMS,
        _detect_all_services,
        _get_hardware_context,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    )


def _is_social_greeting(message, intent="unknown",
                        escalation_requested=False,
                        awaiting_ticket_detail=False):
    return _is_social_greeting_core(
        message,
        SOCIAL_GREETING_TERMS,
        _detect_all_services,
        _get_hardware_context,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    )


def _detect_correction(message, conversation_history=None):
    """
    Returns True when the user's message signals they are correcting the
    bot's previous response. Requires both a correction phrase in the
    current message AND at least one prior bot turn — prevents false
    positives on first-turn messages like "that's not my issue yet".
    """
    return _detect_correction_core(
        message,
        CORRECTION_TERMS,
        conversation_history=conversation_history,
    )


def _detect_escalation_request(message):
    return _detect_escalation_request_core(
        message,
        ESCALATION_TERMS,
        NEGATED_ESCALATION_PATTERNS,
    )


def _is_unrelated_scope(message, detected_services, hardware_context, intent):
    return _is_unrelated_scope_core(
        message,
        detected_services,
        hardware_context,
        intent,
        UNRELATED_TOPIC_TERMS,
        GREETING_TERMS,
    )


def _pretty_hardware_term(term):
    return _pretty_hardware_term_core(term)


def _get_multi_issue_context(message, detected_services, hardware_context):
    return _get_multi_issue_context_core(
        message,
        detected_services,
        hardware_context,
        _fuzzy_detect_service,
        HARDWARE_SERVICE_MAP,
        MULTI_ISSUE_STRONG_MARKERS,
    )


def _build_reply(lines):
    return " ".join(line.strip() for line in lines if line and str(line).strip())


def _build_block_reply(blocks):
    return "\n\n".join(
        block.strip() for block in blocks if block and str(block).strip()
    )


def _build_guided_reply(intro, steps=None, wrap_up=""):
    blocks = []
    intro_text = str(intro or "").strip()
    if intro_text:
        blocks.append(intro_text)

    cleaned_steps = [
        str(step).strip()
        for step in (steps or [])
        if str(step).strip()
    ]
    if cleaned_steps:
        step_lines = ["Try these checks first:"]
        for index, step in enumerate(cleaned_steps, start=1):
            step_lines.append(f"{index}. {step}")
        blocks.append("\n".join(step_lines))

    wrap_up_text = str(wrap_up or "").strip()
    if wrap_up_text:
        blocks.append(wrap_up_text)

    return _build_block_reply(blocks)


def _service_label_list(items):
    labels = []
    seen = set()
    for item in items or []:
        label = str(item or "").strip()
        if not label:
            continue
        normalized = label.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        labels.append(label)
    return labels


def _apply_priority_policy(model_priority, inferred_priority, strong_outage=False):
    if strong_outage or inferred_priority == "high":
        return "high"
    if str(model_priority or "").strip().lower() == "high":
        return "medium"
    if inferred_priority == "low":
        return "low"
    if str(model_priority or "").strip().lower() == "low":
        return "low"
    return "medium"


def _should_auto_escalate(
    message,
    service,
    intent,
    inferred_priority,
    detailed_enough,
    escalation_requested=False,
    awaiting_ticket_detail=False,
):
    if escalation_requested or awaiting_ticket_detail:
        return False
    if inferred_priority != "high" or not detailed_enough:
        return False

    lower_message = str(message or "").lower()
    if service in {"teams", "outlook", "windows", "microsoft account", "microsoft 365"}:
        if _contains_any(lower_message, STRONG_OUTAGE_TERMS + WORK_STOPPAGE_TERMS + HIGH_PRIORITY_TERMS):
            return True

    return intent == "outage" and _contains_any(lower_message, STRONG_OUTAGE_TERMS)


def _build_thread_summary(service, intent, priority, next_issue_options=None, thread_memory=None):
    summary_threads = []
    for thread in (thread_memory or {}).get("threads", [])[:4]:
        thread_service = _canonical_service(thread.get("service"))
        if not thread_service or thread_service == "microsoft 365":
            continue
        snippets = _service_thread_issue_snippets(thread_service, thread)
        summary_threads.append({
            "service": thread_service,
            "intent": thread.get("last_intent", "unknown"),
            "snippet": snippets[0] if snippets else "",
        })

    summary_payload = {
        "current_focus": _canonical_service(service),
        "intent": intent or "unknown",
        "priority": priority or "medium",
        "queued_next": _service_label_list(next_issue_options)[:4],
        "threads": summary_threads,
    }
    return json.dumps(summary_payload, ensure_ascii=True, separators=(",", ":"))


def _has_low_priority_context(message, service):
    lower_msg = str(message or "").lower()
    if _contains_any(lower_msg, LOW_PRIORITY_TERMS):
        return True
    if service == "outlook" and _contains_any(lower_msg, ("signature", "desktop alert", "notification", "notifications")):
        return True
    if service == "teams" and _contains_any(lower_msg, ("banner", "banners", "notification", "notifications")):
        return True
    if service in {"word", "excel", "powerpoint"} and _contains_any(
        lower_msg,
        ("theme", "dark mode", "formatting", "format", "font", "layout", "template"),
    ):
        return True
    return False


def _has_high_impact_context(message):
    lower_msg = str(message or "").lower()
    return (
        _contains_any(lower_msg, HIGH_PRIORITY_TERMS)
        or _contains_any(lower_msg, WORK_STOPPAGE_TERMS)
        or _contains_any(lower_msg, BUSINESS_CRITICAL_TERMS)
    )


def _has_service_down_context(message):
    lower_msg = str(message or "").lower()
    if _contains_any(lower_msg, STRONG_OUTAGE_TERMS):
        return True
    if _contains_any(lower_msg, SERVICE_DOWN_TERMS):
        return True
    return False


def _infer_priority(message, service, intent, multi_context=None):
    msg = str(message or "")
    lower_msg = msg.lower()
    multi_context = multi_context or {}
    low_priority_context = _has_low_priority_context(lower_msg, service)
    high_impact_context = _has_high_impact_context(lower_msg)
    service_down_context = _has_service_down_context(lower_msg)
    urgent_handoff = _contains_any(lower_msg, URGENT_HANDOFF_TERMS)
    explicit_handoff = _detect_escalation_request(lower_msg)
    critical_service = service in {"teams", "outlook", "windows", "microsoft account", "microsoft 365"}

    if _contains_any(lower_msg, STRONG_OUTAGE_TERMS):
        return "high"

    if low_priority_context and not high_impact_context and not service_down_context:
        return "low"

    if service_down_context and critical_service:
        return "high"

    if high_impact_context:
        if _contains_any(lower_msg, ("everyone", "everybody", "all users", "multiple users", "many users")):
            return "high"
        if critical_service:
            return "high"

    if _contains_any(lower_msg, WORK_STOPPAGE_TERMS):
        if critical_service:
            return "high"

    if urgent_handoff and explicit_handoff and critical_service and not low_priority_context:
        return "high"

    if (
        service == "microsoft account"
        and _contains_any(lower_msg, MICROSOFT_ACCOUNT_RECOVERY_TERMS)
        and _contains_any(lower_msg, WORK_STOPPAGE_TERMS)
    ):
        return "high"

    if (
        service == "teams"
        and intent in {"audio", "video", "sign_in"}
        and _contains_any(lower_msg, ("meeting in", "client call", "executive meeting", "exec meeting"))
    ):
        return "high"

    if multi_context.get("is_multi"):
        return "medium"

    if low_priority_context:
        return "low"

    return "medium"


def _choose_reply(message, options):
    """
    Pick a stable variant so common greetings and closings do not
    feel copy-pasted, while tests and chat history remain predictable.
    """
    if not options:
        return ""
    index = sum(ord(char) for char in str(message or "")) % len(options)
    return options[index]


def _user_cancelled_ticket(message):
    return (
        _contains_any(message, POSITIVE_RESOLUTION_TERMS)
        or _contains_any(message, TICKET_CANCEL_TERMS)
    )


def _ask_for_ticket_details(service):
    service_label = _service_label(service)
    return _build_reply([
        "I can get a ticket started.",
        f"Before I do, give me the clearest snapshot of the {service_label} issue.",
        "Include what you clicked, what happened next, and any exact error text.",
    ])


def _service_specific_prompt(service):
    """Ask for detail when we only know the affected Microsoft service."""
    service_label = _service_label(service)
    follow_up = SERVICE_FOLLOW_UPS.get(
        service or "microsoft 365", SERVICE_FOLLOW_UPS["microsoft 365"]
    )
    return _build_reply([
        SERVICE_REPLY_OPENERS.get(service, f"Let us narrow down the {service_label} issue."),
        follow_up,
        "If you already know this needs hands-on support, say ticket and I will collect the right details.",
    ])


def _strip_web_links(reply):
    """Keep model replies focused on steps; link fallback is handled separately."""
    return WEB_LINK_RE.sub("", str(reply or "")).strip()


def _extract_error_codes(message):
    seen = set()
    codes = []
    for match in ERROR_CODE_RE.findall(str(message or "")):
        code = str(match).strip()
        normalized = code.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        codes.append(code)
    return codes[:3]


def _is_error_code_focused_message(message):
    text = str(message or "").strip()
    codes = _extract_error_codes(text)
    if not codes:
        return False
    remainder = ERROR_CODE_RE.sub(" ", text)
    remainder = re.sub(
        r"\b(?:error|code|err|it|is|says|said|showed|shows|this|that|the|number|message)\b",
        " ",
        remainder,
        flags=re.IGNORECASE,
    )
    remainder = re.sub(r"[^a-z0-9]+", " ", remainder.lower()).strip()
    return not remainder or len(text.split()) <= 5


def _context_service_for_error_code(history_context, related_match, service):
    for candidate in (
        history_context.get("current_focus"),
        history_context.get("last_service"),
        related_match.get("service"),
        service,
    ):
        canonical = _canonical_service(candidate)
        if canonical and canonical != "microsoft 365":
            return canonical
    return "microsoft 365"


def _context_intent_for_service(thread_memory, service, fallback_intent):
    thread = _thread_for_service(thread_memory, service)
    thread_intent = (thread or {}).get("last_intent")
    if thread_intent and thread_intent != "unknown":
        return thread_intent
    return fallback_intent if fallback_intent and fallback_intent != "unknown" else "unknown"


def _error_code_reply(service, intent, codes, has_context=True):
    code_text = ", ".join(codes)
    service_label = _service_label(service)
    if not has_context or service == "microsoft 365":
        return _build_reply([
            f"That code ({code_text}) is useful, but I need the Microsoft app before I map it to a fix.",
            "Tell me which app showed it and what you clicked right before it appeared.",
        ])

    context_line = (
        f"Got it, I am keeping this on the {service_label} issue. "
        f"The code {code_text} helps, but the app and action matter more than the number by itself."
    )

    guidance = {
        "teams": [
            context_line,
            "If this happened in Teams desktop, try the same action in Teams on the web. If web works, fully quit Teams and reopen it before clearing cache.",
            "If it happened while joining or signing in, tell me that step so we do not treat a meeting error like a chat error.",
        ],
        "outlook": [
            context_line,
            "First try the same send/receive action in Outlook on the web. If webmail works, the issue is likely desktop Outlook, its profile, or the local connection.",
            "If webmail also fails, keep the full error text because support will need the server or recipient detail behind the code.",
        ],
        "onedrive": [
            context_line,
            "Open the OneDrive cloud icon and check the activity panel for the file or folder that is failing. Pause and resume sync once after confirming the right account.",
            "If the file opens in the browser but not locally, the local sync client is the likely path; if the browser fails too, it is probably permission or file access.",
        ],
        "sharepoint": [
            context_line,
            "Open the SharePoint file or site in a browser or private window and confirm you are signed in with the expected work account.",
            "If the browser also shows the code, capture the link type and whether it says view-only, access denied, or site unavailable.",
        ],
        "excel": [
            context_line,
            "Open Excel first without the workbook. If Excel opens normally, use File > Open to load the workbook and see whether the code follows that one file.",
            "If every workbook shows the code, test Excel safe mode before changing the file.",
        ],
        "word": [
            context_line,
            "Open Word first without the document. If Word is fine, use File > Open and Save As to test whether the code follows that document or save location.",
            "If Word itself shows the code before any document opens, the app or account state is the better path.",
        ],
        "powerpoint": [
            context_line,
            "Open PowerPoint first without the deck. If that works, open the deck with File > Open and note whether the code appears on one slide, media file, or while presenting.",
            "If PowerPoint shows the code before a deck opens, test app repair or account sign-in before editing the presentation.",
        ],
        "windows": [
            context_line,
            "Match the code to the Windows screen where it appeared: sign-in, update, display/device, or printer settings. Start by repeating the exact action once and capture the full wording.",
            "If this came from Windows Update, use Settings > Windows Update > Update history so support can see the failed update name with the code.",
        ],
        "microsoft account": [
            context_line,
            "Do not send passwords, verification codes, recovery codes, or Authenticator codes here. Try the same sign-in in a private browser window at microsoft365.com.",
            "If the code appears again, tell me whether it was password, verification, Authenticator, or account recovery so we keep the next step safe.",
        ],
    }

    lines = guidance.get(service)
    if not lines:
        lines = [
            context_line,
            f"Try the same action in the web version if {service_label} has one, then tell me whether the code appears there too.",
            "If it only appears in the desktop app, the next path is usually app cache, account sign-in, or repair rather than a new ticket immediately.",
        ]

    if intent == "email_delivery" and service == "outlook":
        lines[1] = (
            "First try sending the same message from Outlook on the web. If webmail sends, desktop Outlook likely cannot reach the outgoing mail path or local profile cleanly."
        )
    elif intent == "sync" and service in {"onedrive", "sharepoint", "outlook"}:
        lines.append("If the web version is current but the desktop copy is not, treat this as a local sync/cache problem first.")
    elif intent == "sign_in":
        lines.append("If this is blocking urgent work or the web sign-in fails too, say ticket and I will capture it with the right priority.")

    return _build_reply(lines)


def _should_defer_ambiguous_surface_to_gemini(
    message,
    service,
    intent,
    explicit_service=None,
    fuzzy_service=None,
    hardware_context=None,
    known_issue=None,
    multi_context=None,
    escalation_requested=False,
    awaiting_ticket_detail=False,
    unsupported_service=None,
    user_is_correcting=False,
):
    if escalation_requested or awaiting_ticket_detail or unsupported_service:
        return False
    if user_is_correcting:
        return False
    if known_issue and known_issue.get("intent") != "unknown":
        return False
    if hardware_context and hardware_context.get("is_out_of_scope"):
        return False

    lower_msg = str(message or "").lower()
    has_surface_term = _contains_any(lower_msg, AMBIGUOUS_MICROSOFT_SURFACE_TERMS)
    has_error_code = AMBIGUOUS_ERROR_CODE_RE.search(lower_msg) is not None
    has_ambiguous_failure = _contains_any(lower_msg, AMBIGUOUS_FAILURE_TERMS)
    if not (has_surface_term and (has_error_code or has_ambiguous_failure)):
        return False

    clear_service = explicit_service and explicit_service != "microsoft 365"
    if clear_service and intent != "unknown":
        return False

    has_clear_hardware = bool(
        hardware_context
        and hardware_context.get("has_hardware_term")
        and hardware_context.get("hardware_term")
    )
    if has_clear_hardware and intent != "unknown":
        return False

    if multi_context and multi_context.get("is_multi") and explicit_service:
        return False

    return service in {
        "microsoft 365",
        "microsoft account",
        "windows",
        "word",
        "excel",
        "powerpoint",
    } or bool(fuzzy_service)


def _wrap_up_for(service, intent):
    if service == "teams" and intent == "sync":
        return "If web Teams works but the desktop app does not, that tells us the desktop app is the problem."
    if service == "onedrive" and intent == "sync":
        return "If the same file stays pending, send me the file status or say ticket and we can capture it cleanly."
    if service == "outlook" and intent == "email_delivery":
        return "If it still bounces back, keep the full returned-message text because it usually names the failing address or domain."
    if service == "sharepoint" and intent == "sign_in":
        return "If the owner confirms you have access and it still fails, say ticket and include the link type you are opening."
    if service == "word" and intent == "crash":
        return "If the copy fails too, the exact save/open error will tell us whether this is the document, Word, or the storage location."
    if service == "powerpoint" and intent == "crash":
        return "If it fails on the same slide again, note that slide number or media file before opening a ticket."
    if service == "outlook" and intent == "sign_in":
        return "If the same prompt comes back after removing credentials, sign in at microsoft365.com first and note the exact error."
    if service == "outlook" and intent == "crash":
        return "If it crashes on the same action again, the exact error message and which file or step triggers it will speed things up."
    if service == "outlook" and intent == "sync":
        return "If the inbox still does not update, try Outlook on the web to confirm whether mail is missing from the account or only the desktop app."
    if service == "teams" and intent == "sign_in":
        return "If Teams still loops after clearing the cache, try signing in at teams.microsoft.com in a browser to separate the desktop app from the account."
    if service == "teams" and intent == "crash":
        return "If it keeps closing, note whether the crash happens at startup or during a specific action before opening a ticket."
    if service == "excel" and intent == "crash":
        return "If Excel still crashes on that file, try opening a blank workbook first to check whether the issue is the file or the app."
    if service == "excel" and intent == "sync":
        return "If the file still does not save to OneDrive, check the OneDrive icon for a specific error message on that file."
    if service == "word" and intent == "sync":
        return "If the upload conflict stays, rename the file and save a fresh copy to OneDrive, then delete the conflicted version."
    if service == "onedrive" and intent == "sign_in":
        return "If OneDrive still prompts after signing in, sign out fully and sign back in from the OneDrive Settings > Account panel."
    if service == "onedrive" and intent == "crash":
        return "If OneDrive still does not start, try reinstalling it from microsoft365.com or check Windows Event Viewer for a startup error."
    if service == "windows" and intent == "crash":
        return "If the blue screen or restart keeps happening, note the exact stop code shown — most BSOD codes have a specific Microsoft fix."
    if service == "sharepoint" and intent == "sync":
        return "If files still do not sync after reconnecting the library, check the OneDrive client for SharePoint-specific error details."
    if service == "sharepoint" and intent == "crash":
        return "If the site still will not load in multiple browsers, say ticket and include the URL and the error message you see."
    if service == "microsoft account" and intent == "password_reset":
        return "If the reset page will not accept your info, say ticket and include the exact message from the sign-in screen."
    if service == "microsoft 365" and intent == "sign_in":
        return "If sign-in still fails after clearing credentials, try signing in fresh from microsoft365.com in a private browser tab."
    if service == "microsoft 365" and intent == "crash":
        return "If multiple Office apps are still crashing after the repair, say ticket and note which apps fail and what error you see."
    if service == "teams" and intent == "notification":
        return "If notifications still do not appear, check Windows Focus assist — it can suppress all app alerts silently."
    if service == "outlook" and intent == "notification":
        return "If desktop alerts still do not appear after checking both settings, restart Outlook to reset the notification state."
    if service == "windows" and intent == "update":
        return "If the same update keeps failing, note the error code and we can look up the specific fix for that update."
    if service == "windows" and intent == "performance":
        return "If the device is still sluggish after those steps, the Task Manager startup tab is the next place to look for heavy background programs."
    if service == "teams" and intent == "performance":
        return "If Teams is still slow in meetings, check whether the issue improves on Teams web — if it does, the desktop app needs a reinstall."
    if service == "outlook" and intent == "performance":
        return "If Outlook still loads slowly after disabling add-ins, try Outlook on the web to confirm whether it is the app or the mailbox."
    if service == "microsoft 365" and intent == "activation":
        return "If activation still fails after signing in correctly, use the Office Activation Troubleshooter from microsoft365.com."
    if service == "excel" and intent == "activation":
        return "If Excel still shows unlicensed after signing in, confirm your Microsoft 365 subscription is active at microsoft365.com."
    if service == "word" and intent == "activation":
        return "If Word still shows unlicensed after signing back in, confirm your subscription is active at microsoft365.com."
    if service == "powerpoint" and intent == "activation":
        return "If PowerPoint still says unlicensed after signing in, confirm your subscription status at microsoft365.com."
    return INTENT_WRAP_UPS.get(intent, INTENT_WRAP_UPS["unknown"])


def _rule_based_step_reply(service, intent):
    """Return a concise deterministic fix for common known intents."""
    specialized = SERVICE_INTENT_RESPONSES.get((service, intent))
    if specialized:
        intro = specialized[0]
        steps = specialized[1:]
        return _build_guided_reply(
            intro,
            steps,
            _wrap_up_for(service, intent),
        )

    service_label = _service_label(service)
    reply_lines = list(SHORT_STEP_RESPONSES[intent])
    intro = ""
    if service and service != "microsoft 365":
        intro = SERVICE_REPLY_OPENERS.get(
            service,
            f"Let us use the {service_label} clues to narrow this down.",
        )
    elif service_label:
        intro = f"Let us use the {service_label} clues to narrow this down."

    return _build_guided_reply(
        intro,
        reply_lines,
        _wrap_up_for(service, intent),
    )


def _specialized_niche_reply(message):
    """Narrow deterministic replies for niche cases that should not need Gemini."""
    msg = _normalize_message(message)

    if _contains_any(msg, ("forwarding", "forward", "archive")) and _contains_any(msg, ("rule", "rules", "boss", "mail")):
        return {
            "service": "outlook",
            "intent": "sync",
            "reply": _build_guided_reply(
                "That sounds like an Outlook rule or mailbox rule is moving mail before you see it.",
                [
                    "In Outlook on the web, open Settings > Mail > Rules and check for forwarding, move-to-folder, or delete rules.",
                    "Also check desktop Outlook rules because client-only rules can move mail even when web rules look clean.",
                    "Search the Archive folder for one affected sender, then disable the matching rule before moving messages back.",
                ],
                "If you cannot find the rule in either place, say ticket and include one sender plus the folder where the mail lands.",
            ),
        }

    if _contains_any(msg, ("shared mailbox", "sent items")):
        return {
            "service": "outlook",
            "intent": "sync",
            "reply": _build_guided_reply(
                "Shared mailbox sent mail can save to the sender mailbox instead of the shared mailbox.",
                [
                    "First check your own Sent Items for one missing message to confirm where Outlook stored it.",
                    "Try sending from Outlook on the web through the shared mailbox and compare where that copy lands.",
                    "If web behaves the same way, an admin likely needs to enable shared mailbox sent-item copy behavior.",
                ],
                "If you open a ticket, include the shared mailbox address and whether Send As or Send on Behalf was used.",
            ),
        }

    if _contains_any(msg, ("delegate", "private meeting", "private meetings", "my calendar")):
        return {
            "service": "outlook",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "Outlook delegate calendar limits usually come from delegate permissions or private-item visibility.",
                [
                    "Open Outlook calendar permissions and confirm the delegate has the expected role, not only reviewer access.",
                    "If private meetings are involved, check whether the delegate is allowed to view private items.",
                    "Have the delegate test in Outlook on the web so we can separate a mailbox permission issue from desktop cache.",
                ],
                "If permissions look correct but it still fails, a ticket should include both mailbox names and the exact calendar action blocked.",
            ),
        }

    if _contains_any(msg, ("focused inbox",)):
        return {
            "service": "outlook",
            "intent": "formatting",
            "reply": _build_guided_reply(
                "Focused Inbox can disappear when the mailbox type, view, or migration state changes.",
                [
                    "Check View > Show Focused Inbox in Outlook desktop, then check the same mailbox in Outlook on the web.",
                    "If it is missing in both places after migration, confirm the mailbox is fully moved and still licensed for Exchange Online.",
                    "If it only disappears on desktop, reset the Outlook view or rebuild the profile after confirming web is correct.",
                ],
                "If this needs a ticket, include whether Focused Inbox is missing in web, desktop, or both.",
            ),
        }

    if _contains_any(msg, ("alias", "old sign-in", "old signin", "old one")) and _contains_any(msg, ("outlook", "prompts", "prompt", "sign-in")):
        return {
            "service": "outlook",
            "intent": "sign_in",
            "reply": _build_guided_reply(
                "Outlook can keep prompting for an old alias when cached Office credentials still point at the previous sign-in name.",
                [
                    "Sign into microsoft365.com with the new alias first to confirm the account itself accepts it.",
                    "In Outlook, go to File > Account and sign out of the old account entry, then close all Office apps.",
                    "Open Windows Credential Manager and remove stale Office or Outlook credentials that show the old alias, then reopen Outlook and sign in fresh.",
                ],
                "If the old alias still appears after that, check whether the old address remains as the mailbox primary SMTP or UPN in admin settings.",
            ),
        }

    if _contains_any(msg, ("tenant chooser", "company names", "realm mismatch", "flipping between")):
        return {
            "service": "microsoft 365",
            "intent": "sign_in",
            "reply": _build_guided_reply(
                "That sounds like Microsoft 365 is bouncing between two tenant identities instead of settling on the right work account.",
                [
                    "Sign out of Microsoft 365 in the browser, then open the same page in an InPrivate window and choose the intended work account.",
                    "In Windows, go to Settings > Accounts > Access work or school and disconnect any old tenant or stale work account you no longer use.",
                    "If both company names are valid, confirm which tenant owns the app or file before approving the sign-in prompt again.",
                ],
                "If it still flips tenants, a ticket should include both tenant names and the exact app or link you were opening.",
            ),
        }

    if _contains_any(msg, ("location does not allow confidential", "does not allow confidential", "confidential files")):
        return {
            "service": "microsoft 365",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "That sounds like a sensitivity or data-loss-prevention policy blocking where the file can be saved.",
                [
                    "Save the blank document to your approved OneDrive or SharePoint work location first, not a local or personal folder.",
                    "Check the sensitivity label shown in the Office title bar or File > Info and confirm it matches the destination policy.",
                    "If the file is truly blank, create a new blank document in the approved library and test saving there before copying content in.",
                ],
                "If the policy still blocks a blank file, include the destination path and label name in a ticket.",
            ),
        }

    if _contains_any(msg, ("label mismatch", "only lets me view", "view it in the browser")):
        return {
            "service": "microsoft 365",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "A label mismatch usually means the file's sensitivity label and the app or location policy do not agree.",
                [
                    "Open the file in the browser and check the sensitivity label or information-protection banner.",
                    "Confirm you are signed in with the same work account the coworker shared the file with.",
                    "Ask the file owner to verify the label and sharing permissions before you download or edit a copy.",
                ],
                "If the browser is the only place it opens, a ticket should include the file location, label wording, and whether others can edit it.",
            ),
        }

    if _contains_any(msg, ("handshake expired", "side panel", "reload does nothing")):
        return {
            "service": "microsoft 365",
            "intent": "sign_in",
            "reply": _build_reply([
                "That sounds like an embedded Microsoft sign-in panel expired, but the app name matters before clearing the wrong cache.",
                "Close the panel, sign out of Microsoft 365 in the browser, then reopen the same action in an InPrivate window to force a fresh sign-in.",
                "Tell me which app or page owns the side panel, like Teams, Outlook, SharePoint, Office web, or another Microsoft app, and I can give the app-specific cache path.",
            ]),
        }

    if _contains_any(msg, ("blue box", "action needed", "button is grey", "button is gray")):
        return {
            "service": "microsoft 365",
            "intent": "unknown",
            "reply": _build_reply([
                "That is too little context to safely route yet, but it still sounds like a Microsoft app or browser prompt.",
                "Tell me which app the blue box appears in and what button is greyed out.",
                "If you can, copy the exact text in the box and what you clicked right before it appeared.",
            ]),
        }

    if _contains_any(msg, ("live captions", "captions")):
        return {
            "service": "teams",
            "intent": "audio",
            "reply": _build_guided_reply(
                "Teams captions use meeting language settings, so a wrong language usually is not an audio-device problem.",
                [
                    "In the meeting, open More > Language and speech and set the spoken language to the language people are actually using.",
                    "Turn captions off and back on after changing the spoken language.",
                    "If only one user sees the wrong language, have them leave and rejoin from Teams desktop instead of the browser.",
                ],
                "If captions are wrong for everyone, note the meeting type and organizer because policy or meeting settings may be involved.",
            ),
        }

    if _contains_any(msg, ("teams phone", "desk device", "fetch user policy", "user policy")):
        return {
            "service": "teams",
            "intent": "sign_in",
            "reply": _build_guided_reply(
                "A Teams phone that cannot fetch user policy is usually signed in but not receiving Teams device policy correctly.",
                [
                    "Restart the desk phone, then sign out and sign back in with the affected user.",
                    "Confirm the user has the right Teams Phone license and any required calling policy assigned.",
                    "If only that device fails, check for a firmware update or factory reset the phone before replacing policy assignments.",
                ],
                "A ticket should include the phone model, user account, and whether Teams desktop works for the same user.",
            ),
        }

    if _contains_any(msg, ("webinar", "lobby")):
        return {
            "service": "teams",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "Teams webinar lobby behavior follows webinar meeting options, which can differ from normal meetings.",
                [
                    "Open the webinar meeting options and check Who can bypass the lobby.",
                    "Confirm attendees are joining with the expected email identity, not as anonymous guests.",
                    "If presenters can enter but attendees cannot, compare webinar policy and lobby settings for that event.",
                ],
                "If attendees remain stuck, capture the event link type and one attendee email for a ticket.",
            ),
        }

    if _contains_any(msg, ("colon", "invalid character", "invalid characters", "filename", "file name")) and _contains_any(msg, ("onedrive", "sync")):
        return {
            "service": "onedrive",
            "intent": "sync",
            "reply": _build_guided_reply(
                "OneDrive cannot sync some characters that a Mac may allow in filenames.",
                [
                    "Rename the file to remove characters like colon, asterisk, question mark, quotes, angle brackets, pipe, or trailing spaces.",
                    "Keep the path shorter if the file is nested deeply inside folders.",
                    "After renaming, pause and resume OneDrive sync so the client retries the file.",
                ],
                "If several files are affected, fix one example first and confirm the sync error clears before renaming a whole folder.",
            ),
        }

    if _contains_any(msg, ("storage full", "storage quota", "quota")) and _contains_any(msg, ("onedrive", "admin portal", "space")):
        return {
            "service": "onedrive",
            "intent": "sync",
            "reply": _build_guided_reply(
                "A OneDrive quota mismatch can be either user storage, local disk space, or a stale sync-client reading.",
                [
                    "Check OneDrive on the web first; if web shows space available, the desktop sync client may be stale.",
                    "Confirm the PC itself is not low on disk space, because local disk warnings can look like OneDrive storage errors.",
                    "Quit and reopen OneDrive, then check Settings > Account > Storage to refresh the quota shown to the client.",
                ],
                "If web and desktop disagree after restart, open a ticket with screenshots of both quota views.",
            ),
        }

    if _contains_any(msg, ("checked out", "checkout")) and _contains_any(msg, ("sharepoint", "file")):
        return {
            "service": "sharepoint",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "A SharePoint file checked out to someone else needs a library-owner action, especially if that person left.",
                [
                    "Open the file in the SharePoint library and check the Checked out to column or file details pane.",
                    "If you are a library owner, use More actions > More > Check in or discard checkout after confirming no edits need saving.",
                    "If you are not an owner, ask the site owner to take over the checkout or restore the last checked-in version.",
                ],
                "Avoid uploading a replacement until the checkout state is cleared, or version history can get messier.",
            ),
        }

    if _contains_any(msg, ("recycle bin", "deleted")) and _contains_any(msg, ("sharepoint", "folder")):
        return {
            "service": "sharepoint",
            "intent": "sync",
            "reply": _build_guided_reply(
                "SharePoint deleted folders are usually recoverable from the site recycle bin if retention has not expired.",
                [
                    "Open the SharePoint site, go to Recycle bin, and search using the part of the folder name you remember.",
                    "Sort by Deleted date if the name search is not enough.",
                    "Restore the folder from the recycle bin, then verify permissions because restored folders keep their previous sharing state.",
                ],
                "If it is not in the first-stage recycle bin, ask a site owner to check the second-stage recycle bin.",
            ),
        }

    if _contains_any(msg, ("required metadata", "metadata is missing", "required column", "required columns")):
        return {
            "service": "sharepoint",
            "intent": "sync",
            "reply": _build_guided_reply(
                "SharePoint upload can fail when the library requires metadata before the file can be checked in.",
                [
                    "Open the library in the browser and look for required columns marked with an asterisk.",
                    "Upload the file through the browser, then fill in the required properties from the details pane.",
                    "If syncing from File Explorer keeps failing, complete the metadata in SharePoint web first, then let OneDrive sync again.",
                ],
                "If the required field is unclear, the library owner needs to confirm which column blocks upload.",
            ),
        }

    if (
        _contains_any(msg, ("power query", "query credentials", "data source credentials"))
        or (
            _contains_any(msg, ("excel", "workbook"))
            and _contains_any(msg, ("query", "data source"))
            and _contains_any(msg, ("credentials", "password reset", "sign in"))
        )
    ):
        return {
            "service": "excel",
            "intent": "sign_in",
            "reply": _build_guided_reply(
                "Power Query often keeps old credentials after a password reset.",
                [
                    "In Excel, go to Data > Get Data > Data Source Settings and clear permissions for the affected source.",
                    "Close and reopen Excel, then refresh the query and sign in with the new password when prompted.",
                    "If the source is SharePoint or OneDrive, also confirm Office is signed into the same work account.",
                ],
                "If it still loops, include the data source type and whether refresh works in Excel web.",
            ),
        }

    if _contains_any(msg, ("same cells", "coauthor", "co-author", "another user changed")):
        return {
            "service": "excel",
            "intent": "sync",
            "reply": _build_guided_reply(
                "Excel coauthor conflicts happen when two people edit the same area before the workbook merges changes.",
                [
                    "Open File > Info and check for upload or conflict messages.",
                    "Use Version History to compare the current version with the conflicted version before discarding anything.",
                    "Copy the cells you need into the live workbook, then let AutoSave finish before closing Excel.",
                ],
                "If conflicts keep happening, have everyone reopen the workbook from SharePoint or OneDrive web to reset coauthoring.",
            ),
        }

    if _contains_any(msg, ("sensitivity label",)):
        return {
            "service": "word",
            "intent": "permissions",
            "reply": _build_guided_reply(
                "Sensitivity labels are controlled by policy, so Word may block removal even when you own the draft.",
                [
                    "Check the label menu and see whether a lower label is available or greyed out.",
                    "If removal is blocked, confirm whether your organization requires a justification or prevents downgrades.",
                    "Try Word on the web once; if policy blocks it there too, an admin must change label permissions or policy.",
                ],
                "Do not copy sensitive content into an unlabeled file just to bypass the label.",
            ),
        }

    if _contains_any(msg, ("normal template", "new document", "weird margin", "weird font")):
        return {
            "service": "word",
            "intent": "formatting",
            "reply": _build_guided_reply(
                "When every new Word document has the wrong font or margins, the Normal template is usually carrying the bad default.",
                [
                    "Open a blank document and set the correct font and margins, then choose Set As Default where available.",
                    "If the issue returns, close Word and rename the Normal.dotm template so Word creates a clean one.",
                    "If this is a corporate template, check whether a startup template is being pushed by policy.",
                ],
                "If you rename Normal.dotm, keep the old copy until you confirm macros or custom styles are not needed.",
            ),
        }

    if _contains_any(msg, ("embedded fonts", "embedded font", "fonts cannot be saved")):
        return {
            "service": "powerpoint",
            "intent": "formatting",
            "reply": _build_guided_reply(
                "PowerPoint cannot embed some fonts because of font licensing or unsupported font types.",
                [
                    "Use File > Options > Save and check whether font embedding is enabled for the presentation.",
                    "Replace any restricted font with a standard Office font if PowerPoint says the font cannot be embedded.",
                    "Save a PDF copy for presenting if the deck must look identical on another computer.",
                ],
                "If this is a brand font, a ticket should include the font name and whether the font is installed on the presenting PC.",
            ),
        }

    if _contains_any(msg, ("presenter remote", "remote advances")):
        return {
            "service": "powerpoint",
            "intent": "device_setup",
            "reply": _build_guided_reply(
                "A presenter remote sends keys to whichever app has focus, so it can control the wrong window.",
                [
                    "Click once inside the PowerPoint slideshow window before using the remote.",
                    "Close or minimize media players that may be stealing focus.",
                    "In Slide Show settings, confirm the deck is presented by PowerPoint on the display you are actually using.",
                ],
                "If the remote still controls another app, test the keyboard arrow keys; if those also affect the wrong app, it is a focus/display issue.",
            ),
        }

    if _contains_any(msg, ("morph", "transition is missing")):
        return {
            "service": "powerpoint",
            "intent": "formatting",
            "reply": _build_guided_reply(
                "Morph availability depends on the PowerPoint version, license, and file format.",
                [
                    "Open File > Account and confirm Office is signed in and updated.",
                    "Save the deck as `.pptx`; older formats can hide newer transitions.",
                    "If Morph is missing only on one computer, run Office Update from File > Account > Update Options.",
                ],
                "If it still is not available after updating, compare the Office build number with a computer where Morph appears.",
            ),
        }

    if _contains_any(msg, ("windows hello", "hello")) and _contains_any(msg, ("camera", "turn on")):
        return {
            "service": "windows",
            "intent": "sign_in",
            "reply": _build_guided_reply(
                "Windows Hello uses the biometric/IR camera path, which can fail even when a normal Teams camera preview works.",
                [
                    "Go to Settings > Accounts > Sign-in options and remove then re-add Windows Hello face if the option is available.",
                    "Check Windows Update for biometric or camera driver updates.",
                    "In Device Manager, look for Windows Hello Face Software Device or biometric camera warnings.",
                ],
                "If Teams camera works but Hello still fails, include the camera model and any Device Manager warning in a ticket.",
            ),
        }

    if _contains_any(msg, ("default printer", "changing the default printer", "keeps changing")):
        return {
            "service": "windows",
            "intent": "printing",
            "reply": _build_guided_reply(
                "Windows may be set to automatically manage the default printer based on the last printer used.",
                [
                    "Go to Settings > Bluetooth & devices > Printers & scanners.",
                    "Turn off Let Windows manage my default printer.",
                    "Select the real printer you want and choose Set as default.",
                ],
                "If it keeps switching to OneNote after that, remove the OneNote virtual printer only if your workflow does not need it.",
            ),
        }

    if _contains_any(msg, ("mapped drive", "disconnects after sleep")):
        return {
            "service": "windows",
            "intent": "sync",
            "reply": _build_guided_reply(
                "Mapped drives that drop after sleep usually need the network session refreshed, not a full internet fix.",
                [
                    "Disconnect and reconnect the mapped drive after waking the laptop to confirm the path and credentials still work.",
                    "Open Credential Manager and refresh saved Windows credentials for the file server if the reconnect prompts again.",
                    "If this happens only on VPN, connect VPN before opening File Explorer so the drive maps after the tunnel is ready.",
                ],
                "If the drive still drops daily, a ticket should include the drive letter, server path, and whether VPN was connected.",
            ),
        }

    if _contains_any(msg, ("activation fails", "activation failed", "office activation")) and _contains_any(msg, ("vpn", "proxy")):
        return {
            "service": "microsoft 365",
            "intent": "activation",
            "reply": _build_guided_reply(
                "Office activation failing only on VPN usually means the VPN or proxy is blocking the licensing endpoint.",
                [
                    "Disconnect VPN and confirm Office activates on the normal network.",
                    "Reconnect VPN and test signing in at microsoft365.com in a browser.",
                    "If browser sign-in works but activation fails, the VPN/proxy policy may need to allow Microsoft licensing traffic.",
                ],
                "A ticket should include whether activation works off VPN and the exact activation message shown on VPN.",
            ),
        }

    if _contains_any(msg, ("floating toolbar", "toolbar covers", "covers the submit button")):
        return {
            "service": "microsoft 365",
            "intent": "display",
            "reply": _build_reply([
                "That sounds like a Microsoft app window or browser toolbar is blocking part of the form, but I need the app name to avoid guessing.",
                "Try zooming the page to 90 percent or pressing Esc once to dismiss floating controls, then tell me whether this is in Teams, Outlook, SharePoint, Office web, or another Microsoft app.",
                "If the toolbar appears only in the browser, test the same page in an InPrivate window so we can separate an extension from the Microsoft page itself.",
            ]),
        }

    return None


def _outlook_calendar_reply():
    return _build_reply([
        "Outlook calendar issues are usually either view/filter related or the invite is missing from the mailbox.",
        "Open Calendar view, check the date range and search for the meeting title or organizer.",
        "If it is still missing, try Outlook on the web to see whether the invite is missing from the account or only from the desktop app.",
    ])


def _microsoft_account_recovery_reply():
    return _build_reply([
        "That sounds more like Microsoft account recovery than a normal sign-in typo.",
        "Do not send passwords, verification codes, recovery codes, or Authenticator codes in this chat.",
        "Start at the Microsoft account recovery page and choose the option that says you no longer have access to the old phone, code, or Authenticator method.",
        "If Microsoft offers a backup email or recovery form, use that path first so you can update the security method before trying to sign in again.",
    ])


def _microsoft_account_throttle_reply():
    return _build_guided_reply(
        "That sounds more like a temporary Microsoft sign-in throttle than a permanent account loss.",
        [
            "Stop retrying for a few minutes, then try one fresh sign-in attempt and switch verification methods if another option is available.",
            "If Authenticator still never prompts after the cooldown, check the app directly on the phone and make sure the phone time is automatic before trying again.",
        ],
        "If the sign-in page still blocks you after the cooldown, send me the exact message and I can help decide whether it needs a ticket.",
    )


def _outlook_wrong_directory_reply():
    return _build_guided_reply(
        "That sounds like Outlook is resolving the wrong person from the local cache or company directory.",
        [
            "Start a new message, highlight the wrong cached name suggestion, and delete it so Outlook stops preferring the stale match.",
            "Use Check Names or the address book picker and confirm you are choosing the correct person by department or email address instead of display name alone.",
            "If the wrong person keeps winning automatically, remove any local contact entry with that same display name because local contacts can override directory resolution.",
        ],
        "If Outlook still resolves the wrong coworker everywhere after that, tell me whether it happens only on this device or in Outlook on the web too.",
    )


def _outlook_callback_sync_reply():
    return _build_reply([
        "That sounds like the earlier Outlook mailbox issue coming back, and search may be tied to the same cache or indexing problem.",
        "Check whether the newest mail appears in Outlook on the web first. If it does, the desktop app is the likely problem rather than the mailbox itself.",
        "If the web inbox is current but desktop search is still wrong, rebuild Outlook search or restart Outlook so the local cache can catch up again.",
    ])


def _sharepoint_version_history_reply():
    return _build_reply([
        "SharePoint can usually recover an earlier file copy through version history.",
        "Open the file in SharePoint or OneDrive on the web, choose Version history, and look for the copy from the time you want back.",
        "If you find the right version, restore it or download that version first so you do not overwrite the current file by accident.",
    ])


def _onedrive_conflict_reply():
    return _build_reply([
        "OneDrive conflict copies usually appear when the same file changed in two places before sync could merge them cleanly.",
        "Open the duplicate files, keep the newest content you need, then rename or merge the version you want to keep.",
        "After that, let OneDrive finish syncing and confirm only one clean copy remains in the folder.",
    ])


def _excel_autosave_reply():
    return _build_reply([
        "Excel AutoSave is usually greyed out when the workbook is local, in an older format, or opened from a location that does not support live saving.",
        "Save the workbook as a modern `.xlsx` file in OneDrive or SharePoint, then reopen it and check whether the AutoSave toggle turns on.",
        "If it is already in OneDrive or SharePoint and still greyed out, confirm the file is not read-only, checked out, or opened in compatibility mode.",
    ])


def _teams_join_clarify_reply():
    return _build_reply([
        "I can help with Teams, but I want to stay on the right path.",
        "Are you unable to join a meeting, join a team or channel, or sign in to the Teams app itself?",
        "If you already see an error, paste the wording and I will narrow it down faster.",
    ])


def _service_hardware_reply(service, hardware_term):
    return SERVICE_HARDWARE_RESPONSES.get((service, hardware_term))


def _should_keep_office_app_context(service, hardware_context, message):
    hardware_term = str(hardware_context.get("hardware_term") or "").strip().lower()
    if service not in OFFICE_FILE_SERVICES:
        return False
    if hardware_term not in FALSE_MULTI_OFFICE_HARDWARE_TERMS:
        return False
    return _contains_any(
        message,
        (
            "preview", "print preview", "presenter view", "presenter",
            "audience", "notes", "speaker notes", "lectern", "slide",
            "deck", "document", "sheet", "layout", "fonts", "markup",
            "embedded video", "video", "bullets", "spacing", "theme",
        ),
    )


def _multi_issue_reply(message, services, hardware_terms):
    service_labels = [_service_label(service) for service in services if service != "microsoft 365"]
    generic_hardware_labels = {
        "mic",
        "microphone",
        "camera",
        "webcam",
        "audio input",
        "audio output",
        "sound",
        "video",
    }
    hardware_labels = []
    for term in hardware_terms:
        label = _pretty_hardware_term(term)
        if services and label.lower() in generic_hardware_labels:
            continue
        normalized_label = label.lower()
        skip_label = False
        for index, existing in enumerate(list(hardware_labels)):
            normalized_existing = existing.lower()
            if normalized_label == normalized_existing or normalized_label in normalized_existing:
                skip_label = True
                break
            if normalized_existing in normalized_label:
                hardware_labels[index] = label
                skip_label = True
                break
        if not skip_label:
            hardware_labels.append(label)
    topic_labels = service_labels + hardware_labels

    intro = _choose_reply(message, (
        "I see a few issues stacked together, so let's split them up instead of chasing only one symptom.",
        "There are a couple threads tangled together here. I will separate them so the fixes stay clear.",
        "That is a few things at once, which is normal when everything decides to be dramatic at the same time. Let's triage it cleanly.",
    ))

    blocks = [
        intro,
        "I picked out these separate issue buckets: " + ", ".join(topic_labels[:7]) + ".",
    ]

    ordered_topics = []
    for service in services[:4]:
        guidance = MULTI_SERVICE_GUIDANCE.get(service)
        if guidance:
            ordered_topics.append((_service_label(service), guidance))

    if hardware_labels:
        terms = ", ".join(hardware_labels[:5])
        hardware_guidance = (
            f"For the device side ({terms}), start with power, cables, or pairing first, "
            "then check Windows Settings or Device Manager for warnings."
        )
        if any(term in hardware_terms for term in ("usb drive", "flash drive", "thumb drive", "external drive")):
            hardware_guidance += (
                " For removable drives, reconnect the USB device and open File Explorer "
                "to confirm whether Windows gave it a drive letter."
            )
        ordered_topics.append((terms, hardware_guidance))

    next_issue_options = []
    if ordered_topics:
        primary_label, primary_guidance = ordered_topics[0]
        blocks.append(f"Priority 1: {primary_label}\n{primary_guidance}")

        if len(ordered_topics) > 1:
            queued_lines = []
            for index, (label, _) in enumerate(ordered_topics[1:], start=2):
                queued_lines.append(f"{index}. {label}")
                next_issue_options.append(label)
            blocks.append(
                "Queued next:\n" + "\n".join(queued_lines)
            )

    blocks.append(
        "When you are ready, tell me which issue you want next by name, or tell me if a different app has become the priority."
    )
    return _build_block_reply(blocks), next_issue_options


def _apply_model_result(response, model_result, detailed_enough,
                        allow_ticket_creation=False, strong_outage=False,
                        inferred_priority="medium"):
    if not model_result:
        return None

    fallback_service = response["service"]
    detected_services = [
        _canonical_service(service_name)
        for service_name in response.get("detected_services", [])
        if _canonical_service(service_name) != "microsoft 365"
    ]
    service = _canonical_service(
        model_result.get("service"), fallback=fallback_service
    )
    unique_detected_services = list(dict.fromkeys(detected_services))
    if (
        fallback_service != "microsoft 365"
        and service != fallback_service
        and len(unique_detected_services) == 1
        and unique_detected_services[0] == fallback_service
        and service not in unique_detected_services
    ):
        service = fallback_service
    response["service"] = service
    response["intent"] = model_result.get("intent", response["intent"])

    raw_priority = model_result.get("priority", "medium")
    response["priority"] = _apply_priority_policy(
        raw_priority,
        inferred_priority,
        strong_outage=strong_outage,
    )

    reply = _strip_web_links(model_result.get("reply", ""))
    if not reply:
        return None

    if model_result.get("needs_ticket"):
        if not allow_ticket_creation:
            response["reply"] = _build_reply([
                reply,
                "If you want this handed off instead, say ticket and I will gather the details.",
            ])
            response["resolved"] = True
            return response

        response["needs_ticket"] = True
        if model_result.get("needs_description") or not detailed_enough:
            response["reply"] = _ask_for_ticket_details(service)
            response["needs_description"] = True
            response["create_ticket"] = False
        else:
            response["reply"] = reply
            response["create_ticket"] = True
            response["resolved"] = False
        return response

    # Pass model reply through as-is - model decides whether to include URLs
    response["reply"] = reply
    response["resolved"] = True
    return response


# ============================================================
# Main entry point
# ============================================================

def handle_message(message, awaiting_ticket_detail=False,
                   conversation_history=None, session_summary=""):

    msg = _normalize_message(message)
    conversation_history = conversation_history or []
    thread_memory = _build_thread_memory(conversation_history, session_summary=session_summary)

    # --- Detection ---
    detected_services = _detect_all_services(msg)
    explicit_service = detected_services[0] if detected_services else None
    fuzzy_service = None if explicit_service else _fuzzy_detect_service(msg)
    hardware_context = _get_hardware_context(msg)
    history_context = _extract_history_context(conversation_history, session_summary=session_summary)
    related_match = {
        "service": None,
        "score": 0,
        "referential": False,
    }
    if not explicit_service:
        related_match = _related_history_match(msg, thread_memory)
    capability_match = {
        "service": None,
        "score": 0,
        "matched_terms": [],
    }
    if not explicit_service and not fuzzy_service and not hardware_context["suggested_service"]:
        capability_match = _capability_history_match(
            msg,
            history_context,
            thread_memory,
        )

    # Service hint priority:
    # explicit keyword > capability from prior apps > confident related
    # thread > hardware mapping > fuzzy match > recent focus > default
    if explicit_service:
        service = explicit_service
    elif capability_match.get("service"):
        service = capability_match["service"]
    elif (
        related_match.get("referential")
        and related_match.get("score", 0) >= 1
        and related_match.get("service")
    ):
        service = related_match["service"]
    elif related_match.get("score", 0) >= 4 and related_match.get("service"):
        service = related_match["service"]
    elif hardware_context["suggested_service"]:
        service = hardware_context["suggested_service"]
    elif fuzzy_service:
        service = fuzzy_service
    elif _should_inherit_recent_service(
        msg,
        history_context,
        related_match,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        multi_context=None,
    ):
        service = history_context["last_service"]
    else:
        service = "microsoft 365"

    unsupported_service = _detect_unsupported_service(msg)
    intent = _detect_intent(msg)
    known_issue = _retrieve_known_issue(msg)
    if known_issue:
        service = known_issue["service"]
        intent = known_issue["intent"]
    specialized_case = _specialized_niche_reply(msg)
    if specialized_case:
        service = specialized_case["service"]
        intent = specialized_case["intent"]
    if service == "outlook" and _contains_any(msg, OUTLOOK_EMAIL_DELIVERY_TERMS):
        intent = "email_delivery"
    if (
        service in {"outlook", "teams", "onedrive", "microsoft 365"}
        and _contains_any(msg, PASSWORD_PROMPT_LOOP_TERMS)
    ):
        intent = "sign_in"
    if service == "microsoft account" and _contains_any(msg, MICROSOFT_ACCOUNT_RECOVERY_TERMS):
        intent = "sign_in"
    has_outlook_callback_context = (
        (
            history_context.get("has_prior_context")
            and history_context.get("last_service") == "outlook"
        )
        or (
            related_match.get("service") == "outlook"
            and related_match.get("score", 0) >= 3
        )
    )
    if (
        service == "outlook"
        and has_outlook_callback_context
        and _contains_any(msg, OUTLOOK_CALLBACK_SYNC_TERMS)
        and _contains_any(msg, ("again", "back", "before", "still", "came back"))
    ):
        intent = "sync"
    if service == "excel" and _contains_any(msg, EXCEL_LINK_WARNING_TERMS):
        intent = "unknown"
    if service == "sharepoint" and _contains_any(msg, SHAREPOINT_READ_ONLY_TERMS):
        intent = "permissions"
    if service == "onedrive" and _contains_any(msg, ("red x", "sync error", "sync errors", "error icon")):
        intent = "sync"
    if service == "onedrive" and _contains_any(msg, ONEDRIVE_CONFLICT_TERMS):
        intent = "sync"
    if (
        hardware_context["hardware_term"] in {"printer", "scanner"}
        and intent == "update"
    ):
        intent = "printing"
    escalation_requested = _detect_escalation_request(msg)
    outage_claim = _contains_any(msg, STRONG_OUTAGE_TERMS)
    detailed_enough = _has_detailed_description(msg)
    if (
        escalation_requested
        and service == "microsoft 365"
        and history_context.get("current_focus")
        and history_context.get("current_focus") != "microsoft 365"
    ):
        service = history_context["current_focus"]
    multi_context = _get_multi_issue_context(msg, detected_services, hardware_context)
    multi_context = _refine_multi_issue_context(
        msg,
        service,
        multi_context,
        explicit_service=explicit_service,
    )
    user_is_correcting = _detect_correction(msg, conversation_history)
    queue_handoff = _is_queue_handoff_message(msg, service, thread_memory)
    inherited_context_ambiguous = _inherited_context_is_ambiguous(
        history_context,
        related_match,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        multi_context=multi_context,
    )
    if capability_match.get("service") == service:
        inherited_context_ambiguous = False
    inherited_recent_service = (
        service == history_context.get("last_service")
        and service != "microsoft 365"
        and not explicit_service
        and not fuzzy_service
        and not hardware_context["suggested_service"]
        and not multi_context["is_multi"]
    )
    if inherited_context_ambiguous:
        inherited_recent_service = False
    if (
        explicit_service
        and hardware_context["hardware_term"] in {"printer", "scanner"}
        and _contains_any(msg, PRINTING_REQUEST_TERMS)
    ):
        intent = "printing"
        service = explicit_service
        multi_context = {
            "is_multi": False,
            "services": [explicit_service],
            "hardware_terms": [hardware_context["hardware_term"]],
        }
    inferred_priority = _infer_priority(
        msg,
        service,
        intent,
        multi_context=multi_context,
    )

    # hardware_context is internal routing data only - kept as a local
    # variable, never added to the response dict that reaches the frontend
    response = {
        "resolved": False,
        "reply": "",
        "needs_ticket": False,
        "needs_description": False,
        "create_ticket": False,
        "service": service,
        "detected_services": multi_context["services"] or detected_services,
        "intent": intent,
        "priority": inferred_priority,
        "next_issue_options": [],
        "thread_summary": "",
        "escalation_requested": escalation_requested,
        "response_source": "rules",
    }
    prefer_gemini_for_ambiguous_surface = _should_defer_ambiguous_surface_to_gemini(
        msg,
        service,
        intent,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        known_issue=known_issue,
        multi_context=multi_context,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
        unsupported_service=unsupported_service,
        user_is_correcting=user_is_correcting,
    )
    if prefer_gemini_for_ambiguous_surface:
        service = "microsoft 365"
        intent = "unknown"
        response.update({
            "service": service,
            "intent": intent,
            "detected_services": [],
            "priority": "medium",
        })

    def _finalize_response(payload):
        payload.setdefault("response_source", "rules")
        next_issue_options = _service_label_list(payload.get("next_issue_options", []))
        payload["next_issue_options"] = next_issue_options

        summary_service = payload.get("service")
        detected_summary_services = payload.get("detected_services") or []
        if summary_service == "microsoft 365" and detected_summary_services:
            summary_service = detected_summary_services[0]

        payload["thread_summary"] = _build_thread_summary(
            summary_service or service,
            payload.get("intent", intent),
            payload.get("priority", inferred_priority),
            next_issue_options=next_issue_options,
            thread_memory=thread_memory,
        )
        return payload

    if (
        specialized_case
        and not escalation_requested
        and not awaiting_ticket_detail
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "service": specialized_case["service"],
            "intent": specialized_case["intent"],
            "reply": specialized_case["reply"],
            "response_source": "rules",
        })
        return _finalize_response(response)

    if (
        _is_error_code_focused_message(msg)
        and not escalation_requested
        and not awaiting_ticket_detail
    ):
        error_codes = _extract_error_codes(message)
        context_service = _context_service_for_error_code(
            history_context,
            related_match,
            service,
        )
        has_context_service = context_service != "microsoft 365"
        context_intent = _context_intent_for_service(
            thread_memory,
            context_service,
            intent,
        )
        response.update({
            "resolved": True,
            "service": context_service,
            "intent": context_intent,
            "priority": _infer_priority(
                msg,
                context_service,
                context_intent,
                multi_context={"is_multi": False},
            ),
            "reply": _error_code_reply(
                context_service,
                context_intent,
                error_codes,
                has_context=has_context_service,
            ),
        })
        return _finalize_response(response)

    # =============================================
    # FAST EXITS - bypass Gemini entirely
    # Only for cases where AI adds zero value
    # =============================================

    # 1. Non-issue / gratitude - no AI needed
    if _is_social_greeting(
        msg,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "resolved": True,
            "reply": _choose_reply(msg, SOCIAL_GREETING_REPLIES),
        })
        return _finalize_response(response)

    if _is_greeting_only(
        msg,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "resolved": True,
            "reply": _choose_reply(msg, GREETING_REPLIES),
        })
        return _finalize_response(response)

    if _is_non_issue_message(
        msg,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "resolved": True,
            "reply": _choose_reply(msg, RESOLUTION_REPLIES),
        })
        return _finalize_response(response)

    if (
        (explicit_service == "outlook" or service == "outlook")
        and not user_is_correcting
        and _contains_any(
            msg,
            (
                "wrong dan",
                "wrong person",
                "company directory",
                "directory person",
                "wrong internal user",
                "resolving dan",
                "resolves dan",
                "wrong dan in our company directory",
            ),
        )
    ):
        response.update({
            "resolved": True,
            "service": "outlook",
            "intent": "unknown",
            "reply": _outlook_wrong_directory_reply(),
        })
        return _finalize_response(response)

    if _is_history_recap_request(msg):
        response.update({
            "resolved": True,
            "service": "microsoft 365",
            "reply": _history_recap_reply(thread_memory),
        })
        return _finalize_response(response)

    if not escalation_requested and not inherited_recent_service and not capability_match.get("service") and _should_clarify_current_application(
        msg,
        history_context,
        related_match,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        multi_context=multi_context,
    ):
        response.update({
            "resolved": True,
            "service": "microsoft 365",
            "reply": _clarify_current_application_reply(thread_memory),
        })
        return _finalize_response(response)

    if inherited_context_ambiguous and not escalation_requested and not awaiting_ticket_detail:
        response.update({
            "resolved": True,
            "service": "microsoft 365",
            "reply": _clarify_current_application_reply(thread_memory),
        })
        return _finalize_response(response)

    # 2. Unsupported service - deterministic scope rejection
    if unsupported_service:
        response.update({
            "resolved": True,
            "service": unsupported_service,
            "reply": (
                f"I do not support {unsupported_service} in this bot. "
                "I handle Microsoft workplace support issues for Teams, Outlook, "
                "OneDrive, Word, Excel, PowerPoint, Windows, and Microsoft account."
            ),
        })
        return _finalize_response(response)

    if queue_handoff and not escalation_requested and not awaiting_ticket_detail:
        handoff_payload = _queued_issue_handoff_payload(
            service,
            _thread_for_service(thread_memory, service),
        )
        response.update({
            "resolved": True,
            **handoff_payload,
        })
        return _finalize_response(response)

    if (
        related_match.get("referential")
        and related_match.get("score", 0) >= 1
        and not explicit_service
        and not escalation_requested
        and not awaiting_ticket_detail
        and len(msg.split()) <= 6
    ):
        referential_service = related_match.get("service") or service
        referential_thread = _thread_for_service(thread_memory, referential_service)
        if referential_thread:
            handoff_payload = _queued_issue_handoff_payload(
                referential_service,
                referential_thread,
            )
            response.update({
                "resolved": True,
                "service": referential_service,
                **handoff_payload,
            })
            return _finalize_response(response)

    if (
        explicit_service
        and _contains_any(msg, REFERENTIAL_SERVICE_RECAP_TERMS)
        and not known_issue
        and not escalation_requested
        and not awaiting_ticket_detail
    ):
        service_thread = _thread_for_service(thread_memory, explicit_service)
        if service_thread:
            response.update({
                "resolved": True,
                "service": explicit_service,
                "reply": _service_thread_recap_reply(explicit_service, service_thread),
            })
            return _finalize_response(response)

    if not prefer_gemini_for_ambiguous_surface and _looks_like_vague_service_message(
        msg,
        service,
        intent,
        explicit_service=explicit_service,
        fuzzy_service=fuzzy_service,
        hardware_context=hardware_context,
        known_issue=known_issue,
        multi_context=multi_context,
    ):
        response.update({
            "resolved": True,
            "reply": _service_specific_prompt(service),
        })
        return _finalize_response(response)

    if (
        not prefer_gemini_for_ambiguous_surface
        and not inherited_recent_service
        and not escalation_requested
        and not awaiting_ticket_detail
        and _is_unrelated_scope(msg, detected_services, hardware_context, intent)
    ):
        response.update({
            "resolved": True,
            "reply": _choose_reply(msg, SCOPE_REPLIES),
        })
        return _finalize_response(response)

    if (
        inherited_recent_service
        and not prefer_gemini_for_ambiguous_surface
        and intent == "unknown"
        and not known_issue
        and len(msg.split()) <= 8
        and not escalation_requested
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _current_issue_follow_up_reply(service),
        })
        return _finalize_response(response)

    # 3. Out-of-scope physical hardware damage
    if hardware_context["is_out_of_scope"]:
        response.update({
            "resolved": True,
            "reply": (
                "It sounds like there may be a physical hardware issue with your "
                "device. That usually needs repair or manufacturer support rather than a Microsoft settings change. "
                "For hardware repairs, contact your device manufacturer or visit a "
                "local repair service. If there is also a Microsoft software issue "
                "involved, tell me that symptom and I will focus on the software side."
            ),
        })
        return _finalize_response(response)

    if _should_auto_escalate(
        msg,
        service,
        intent,
        inferred_priority,
        detailed_enough,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "reply": (
                "This looks business-critical, and I have enough detail to open a high-priority ticket now."
            ),
            "needs_ticket": True,
            "create_ticket": True,
            "priority": "high",
        })
        return _finalize_response(response)

    # 4. Explicit escalation - user wants a ticket/human now
    if escalation_requested:
        if inherited_context_ambiguous:
            response.update({
                "reply": _clarify_current_application_reply(thread_memory),
                "needs_ticket": True,
                "needs_description": False,
                "create_ticket": False,
                "service": "microsoft 365",
            })
            return _finalize_response(response)
        if detailed_enough:
            response.update({
                "reply": (
                    "I understand. I have enough detail to create your ticket now."
                ),
                "needs_ticket": True,
                "create_ticket": True,
                "priority": _apply_priority_policy(
                    inferred_priority,
                    inferred_priority,
                    strong_outage=outage_claim,
                ),
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
                "priority": inferred_priority,
            })
        return _finalize_response(response)

    # 6. Awaiting ticket detail from previous turn
    if awaiting_ticket_detail:
        if _user_cancelled_ticket(msg) and not escalation_requested:
            response.update({
                "resolved": True,
                "reply": "Glad the issue is sorted. I have cancelled the ticket request — let me know if anything else comes up.",
                "needs_ticket": False,
                "create_ticket": False,
                "needs_description": False,
            })
            return _finalize_response(response)
        if inherited_context_ambiguous:
            response.update({
                "reply": _clarify_current_application_reply(thread_memory),
                "needs_ticket": True,
                "needs_description": False,
                "create_ticket": False,
                "service": "microsoft 365",
            })
            return _finalize_response(response)
        if detailed_enough:
            response.update({
                "reply": (
                    "Thank you. I have enough detail to create your ticket now."
                ),
                "needs_ticket": True,
                "create_ticket": True,
                "needs_description": False,
                "priority": _apply_priority_policy(
                    inferred_priority,
                    inferred_priority,
                    strong_outage=outage_claim,
                ),
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
                "priority": inferred_priority,
            })
        return _finalize_response(response)

    if (
        multi_context["is_multi"]
        and not prefer_gemini_for_ambiguous_surface
        and not escalation_requested
    ):
        multi_reply, next_issue_options = _multi_issue_reply(
            msg,
            multi_context["services"],
            multi_context["hardware_terms"],
        )
        response.update({
            "resolved": True,
            "service": "microsoft 365",
            "detected_services": multi_context["services"],
            "reply": multi_reply,
            "next_issue_options": next_issue_options,
        })
        return _finalize_response(response)

    if (
        known_issue
        and not prefer_gemini_for_ambiguous_surface
        and known_issue.get("intent") != "unknown"
        and not escalation_requested
        and not user_is_correcting
    ):
        hardware_reply = None
        if (
            hardware_context["has_hardware_term"]
            and not _should_keep_office_app_context(service, hardware_context, msg)
        ):
            hardware_reply = _service_hardware_reply(
                known_issue["service"],
                hardware_context["hardware_term"],
            )
        known_issue_reply = None
        if known_issue.get("id") == "onedrive_sync_conflict":
            known_issue_reply = _onedrive_conflict_reply()
        response.update({
            "resolved": True,
            "service": known_issue["service"],
            "intent": known_issue["intent"],
            "reply": hardware_reply or known_issue_reply or _rule_based_step_reply(
                known_issue["service"],
                known_issue["intent"],
            ),
        })
        return _finalize_response(response)

    if (
        not prefer_gemini_for_ambiguous_surface
        and service == "outlook"
        and _contains_any(msg, OUTLOOK_CALENDAR_TERMS)
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _outlook_calendar_reply(),
        })
        return _finalize_response(response)

    if (
        service == "microsoft account"
        and not prefer_gemini_for_ambiguous_surface
        and _contains_any(msg, MICROSOFT_ACCOUNT_THROTTLE_TERMS)
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "intent": "sign_in",
            "reply": _microsoft_account_throttle_reply(),
        })
        return _finalize_response(response)

    if (
        not prefer_gemini_for_ambiguous_surface
        and service == "microsoft account"
        and _contains_any(msg, MICROSOFT_ACCOUNT_RECOVERY_TERMS)
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "intent": "sign_in",
            "reply": _microsoft_account_recovery_reply(),
        })
        return _finalize_response(response)

    if (
        service == "outlook"
        and not prefer_gemini_for_ambiguous_surface
        and has_outlook_callback_context
        and _contains_any(msg, OUTLOOK_CALLBACK_SYNC_TERMS)
        and _contains_any(msg, ("again", "back", "before", "still", "came back"))
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "intent": "sync",
            "reply": _outlook_callback_sync_reply(),
        })
        return _finalize_response(response)

    if (
        service == "sharepoint"
        and not prefer_gemini_for_ambiguous_surface
        and _contains_any(msg, SHAREPOINT_VERSION_HISTORY_TERMS)
        and not _contains_any(msg, ("checked out", "locked for editing", "another device"))
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _sharepoint_version_history_reply(),
        })
        return _finalize_response(response)

    if (
        service == "onedrive"
        and not prefer_gemini_for_ambiguous_surface
        and _contains_any(msg, ONEDRIVE_CONFLICT_TERMS)
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "intent": "sync",
            "reply": _onedrive_conflict_reply(),
        })
        return _finalize_response(response)

    if (
        service == "excel"
        and not prefer_gemini_for_ambiguous_surface
        and _contains_any(msg, EXCEL_AUTOSAVE_TERMS)
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _excel_autosave_reply(),
        })
        return _finalize_response(response)

    if (
        service == "teams"
        and not prefer_gemini_for_ambiguous_surface
        and _contains_any(msg, TEAMS_JOIN_TERMS)
        and len(msg.split()) <= 3
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _teams_join_clarify_reply(),
        })
        return _finalize_response(response)

    keyword_context = retrieve_support_plan(
        message,
        service_hint=service,
        intent_hint=intent,
        min_confidence=0.35,
    )

    if (
        keyword_context.get("found")
        and keyword_context.get("confidence", 0.0) >= 0.55
        and not escalation_requested
        and not user_is_correcting
    ):
        primary_resource = keyword_context["resources"][0]
        resource_intent = primary_resource.get("intent")
        response.update({
            "resolved": True,
            "reply": keyword_context["reply"],
            "service": primary_resource.get("service", service),
            "intent": resource_intent if resource_intent and resource_intent != "unknown" else intent,
            "knowledge_retrieved": True,
            "knowledge_source": "local_context",
            "knowledge_confidence": keyword_context.get("confidence", 0.0),
            "response_source": "local_fallback",
        })
        return _finalize_response(response)

    if (
        not prefer_gemini_for_ambiguous_surface
        and (service, intent) in SERVICE_INTENT_RESPONSES
        and not keyword_context.get("found")
        and not escalation_requested
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _rule_based_step_reply(service, intent),
        })
        return _finalize_response(response)

    if (
        hardware_context["has_hardware_term"]
        and not prefer_gemini_for_ambiguous_surface
        and not _should_keep_office_app_context(service, hardware_context, msg)
        and not escalation_requested
        and not user_is_correcting
    ):
        term = hardware_context["hardware_term"]
        service_hardware_reply = _service_hardware_reply(service, term)
        if service_hardware_reply:
            response.update({
                "resolved": True,
                "reply": service_hardware_reply,
            })
            return _finalize_response(response)
        fallback_reply = HARDWARE_FALLBACK_RESPONSES.get(term)
        if fallback_reply:
            response.update({
                "resolved": True,
                "reply": fallback_reply,
            })
            return _finalize_response(response)

    # =============================================
    # GEMINI - handles everything else
    # One word, two words, misspellings, hardware,
    # multi-app, bad grammar - all goes here
    # =============================================

    model_result, error = generate_triage_response(
        message,
        service_hint=service,
        conversation_history=conversation_history,
        hardware_term=hardware_context["hardware_term"],
        keyword_context=keyword_context if keyword_context.get("found") else None,
        thread_memory=thread_memory if thread_memory.get("threads") else None,
        session_summary=session_summary,
    )

    if model_result:
        if (
            model_result.get("needs_ticket")
            and not escalation_requested
            and intent in SHORT_STEP_RESPONSES
        ):
            response.update({
                "resolved": True,
                "reply": _rule_based_step_reply(service, intent),
                "intent": intent,
            })
            return _finalize_response(response)

        applied = _apply_model_result(
            response.copy(),
            model_result,
            detailed_enough,
            allow_ticket_creation=True,
            strong_outage=outage_claim,
            inferred_priority=inferred_priority,
        )
        if applied:
            applied["response_source"] = "gemini"
            if keyword_context.get("found"):
                applied.update({
                    "knowledge_retrieved": True,
                    "knowledge_source": "local_context",
                    "knowledge_confidence": keyword_context.get("confidence", 0.0),
                })
            return _finalize_response(applied)

    # =============================================
    # RULE-BASED FALLBACK
    # Only reached when Gemini is unreachable or
    # returned an unreadable response
    # =============================================

    if error:
        print(
            f"[bot_logic] Gemini unavailable, using rule-based fallback. "
            f"Error: {error}"
        )

    keyword_fallback = retrieve_support_plan(
        message,
        service_hint=service,
        intent_hint=intent,
    )
    if keyword_fallback.get("found") and not escalation_requested:
        primary_resource = keyword_fallback["resources"][0]
        resource_intent = primary_resource.get("intent")
        response.update({
            "resolved": True,
            "reply": keyword_fallback["reply"],
            "service": primary_resource.get("service", service),
            "intent": resource_intent if resource_intent and resource_intent != "unknown" else intent,
            "knowledge_retrieved": True,
            "knowledge_source": "local_fallback",
            "knowledge_confidence": keyword_fallback.get("confidence", 0.0),
            "response_source": "local_fallback",
        })
        return _finalize_response(response)

    # Hardware fallback - better than the generic paragraph
    if (
        hardware_context["has_hardware_term"]
        and not prefer_gemini_for_ambiguous_surface
        and not _should_keep_office_app_context(service, hardware_context, msg)
    ):
        term = hardware_context["hardware_term"]
        fallback_reply = HARDWARE_FALLBACK_RESPONSES.get(term)
        if fallback_reply:
            response.update({
                "resolved": True,
                "reply": fallback_reply,
            })
            return _finalize_response(response)

    # Known intent fallback
    if (
        not prefer_gemini_for_ambiguous_surface
        and intent in SHORT_STEP_RESPONSES
        and not user_is_correcting
    ):
        response.update({
            "resolved": True,
            "reply": _rule_based_step_reply(service, intent),
        })
        return _finalize_response(response)

    # Service detected fallback
    if (
        not prefer_gemini_for_ambiguous_surface
        and service
        and service != "microsoft 365"
    ):
        response.update({
            "resolved": True,
            "reply": _service_specific_prompt(service),
        })
        return _finalize_response(response)

    # Generic fallback - absolute last resort
    response.update({
        "reply": (
            "I do not have a confident match for that yet. "
            "Send the app name, what you clicked, and the exact message on screen. "
            "If you already need hands-on help, say ticket and I will gather the details."
        ),
        "needs_description": True,
        "response_source": "fallback",
    })
    return _finalize_response(response)
