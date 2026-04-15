import re
from difflib import SequenceMatcher

try:
    from gemma_provider import generate_triage_response
    from status_provider import check_microsoft_public_status
except ModuleNotFoundError:
    from .gemma_provider import generate_triage_response
    from .status_provider import check_microsoft_public_status


# ============================================================
# Constants - deterministic guards only
# ============================================================

ESCALATION_TERMS = (
    "agent", "human", "ticket", "support",
    "representative", "person",
)

STATUS_TERMS = (
    "check status", "status", "health",
    "service health", "is there an issue",
)

# Only genuinely severe broadcast-outage signals.
# Personal issue descriptions ("not working", "broken", "down")
# are intentionally absent - they go to Ollama instead.
STRONG_OUTAGE_TERMS = (
    "outage", "down for everyone", "service down",
    "completely down", "not available", "widespread",
    "major outage",
)

UNSUPPORTED_STATUS_KEYWORDS = {
    "azure": ("azure",),
    "power platform admin center": ("power platform admin center",),
    "m365 enterprise": ("m365 enterprise", "microsoft 365 enterprise"),
    "m365 business": ("m365 business", "microsoft 365 business"),
}

SERVICE_KEYWORDS = {
    "teams": (
        "teams", "microsoft teams", "ms teams",
        "teems", "msteams", "team chat",
        "meeting", "meetings", "video call", "call", "calls",
        "conference call", "chat",
    ),
    "outlook": (
        "outlook", "exchange", "mail", "email", "inbox",
        "e-mail", "emails", "mails", "mailbox", "calendar",
        "calendar invite", "outlok", "otlook", "hotmail",
    ),
    "onedrive": (
        "onedrive", "one drive", "one-drive", "1drive",
        "cloud files", "files on demand", "backup",
    ),
    "sharepoint": (
        "sharepoint", "share point", "sharept", "sharepoint site",
    ),
    "excel": (
        "excel", "excell", "spreadsheet", "spread sheet",
        "worksheet", "workbook", "xls", "xlsx", "csv",
    ),
    "word": (
        "word", "microsoft word", "ms word", "docx",
        "word doc", "word document", "document", "doc file",
    ),
    "powerpoint": (
        "powerpoint", "power point", "ppt", "powerpt",
        "pptx", "slide deck", "presentation", "slideshow", "slides",
    ),
    "windows": (
        "windows", "win10", "win11", "windows 10",
        "windows 11", "windows login", "windows sign in",
        "windows settings", "device manager", "file explorer",
        "taskbar", "start menu",
    ),
    "microsoft account": (
        "microsoft account", "ms account", "account",
        "signin", "sign in", "microsoft login", "ms login",
        "live.com", "account recovery", "verification code",
        "security code", "two factor", "2fa", "authenticator",
    ),
    "microsoft 365": (
        "microsoft 365", "office 365", "office",
        "m365", "o365", "microsoft office",
        "office apps", "office suite", "m365 apps",
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
    "flash drive":      "windows",
    "thumb drive":      "windows",
    "external drive":   "windows",
    "hard drive":       "windows",
    "sync phone":       "onedrive",
    "docking station":  "windows",
    "usb c":            "windows",
    "usb-c":            "windows",
    "displayport":      "windows",
    "audio output":     "windows",
    "audio input":      "windows",
    "no sound":         "windows",
    "cant hear":        "windows",
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
    "touchpad":  "windows",
    "trackpad":  "windows",
    "controller": "windows",

    # Display - Windows display settings
    "monitor":    "windows",
    "display":    "windows",
    "hdmi":       "windows",
    "projector":  "windows",
    "resolution": "windows",
    "screen":     "windows",

    # Connectivity - Windows or OneDrive
    "bluetooth": "windows",
    "wifi":      "windows",
    "wireless":  "windows",
    "usb":       "windows",
    "printer":   "windows",
    "print":     "windows",
    "scanner":   "windows",

    # Mobile/tablet sync - OneDrive or Microsoft account
    "phone":   "onedrive",
    "tablet":  "onedrive",
    "ipad":    "onedrive",
    "android": "onedrive",
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
    "touchpad",
    "trackpad",
    "controller",
    "monitor",
    "display",
    "projector",
    "bluetooth",
    "printer",
    "scanner",
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
)

AUDIO_OUTPUT_ISSUE_TERMS = (
    "i cannot hear",
    "i can't hear",
    "i cant hear",
    "i can not hear",
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
)

PERMISSION_PROBLEM_TERMS = (
    "permission",
    "permissions",
    "blocked",
    "allow",
    "allowed",
    "access denied",
    "privacy",
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
    "teams": "Tell me whether the problem happens when you sign in, join a meeting, or send a message.",
    "outlook": "Tell me whether the issue happens when you sign in, open mail, or send a message.",
    "onedrive": "Tell me whether files are not syncing, not opening, or not uploading.",
    "sharepoint": "Tell me whether the issue is with opening a site, accessing a file, or syncing content.",
    "excel": "Tell me whether the file will not open, crashes, or shows an error.",
    "word": "Tell me whether the document will not open, save, or sign in correctly.",
    "powerpoint": "Tell me whether the presentation will not open, save, or start correctly.",
    "windows": "Tell me whether the issue is with sign-in, opening the app, or an error message.",
    "microsoft account": "Tell me whether the issue is sign-in, password reset, or account access.",
    "microsoft 365": "Tell me which Microsoft app is affected and what happens when you try to use it.",
}

INTENT_KEYWORDS = {
    "email_delivery": (
        "domain not found", "email someone", "send email",
        "sending email", "sending mail", "send mail",
        "message undeliverable", "undeliverable",
        "delivery failed", "delivery failure", "bounce back",
        "bounced back", "recipient not found", "address not found",
        "invalid recipient", "invalid email",
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
        "permission denied",
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
        "send messages", "send message",
    ),
    "crash": (
        "crash", "crashes", "crashing", "crashed",
        "freezes", "frozen", "freeze", "not responding",
        "stopped working", "wont load", "won't load",
        "keeps closing", "keeps crashing", "error", "errors",
        "failed", "fails", "failure", "hang", "hung",
        "blank screen", "black screen", "white screen",
        "wont open", "won't open", "wont start", "won't start",
        "not opening", "will not open", "will not start",
        "force closes", "closing itself", "lagging", "slow",
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
)

GRATITUDE_TERMS = (
    "thanks", "thank you", "thx", "ty", "appreciate it",
    "thank you so much", "many thanks", "cheers",
    "thank u", "thnks", "thnx",
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

DETAIL_HINT_TERMS = (
    "error", "code", "when i", "after i", "trying to",
    "cannot", "can't", "fails", "failed", "message",
    "popup", "prompt", "permission", "blocked",
    "allow", "access denied", "not detected",
    "device", "muted", "selected",
)

# Used only by rule-based fallback - emergency responses when Ollama is down
SHORT_STEP_RESPONSES = {
    "password_reset": [
        "Go to the Microsoft sign-in page and choose Forgot password.",
        "After the reset finishes, try signing in again with the new password.",
    ],
    "sign_in": [
        "Try signing in at microsoft365.com first to see whether the issue affects your full Microsoft account.",
        "If that also fails, use Microsoft's password reset page before trying again.",
    ],
    "sync": [
        "Confirm you are signed in to the correct Microsoft account.",
        "Then refresh the app or reopen it and check whether the content starts syncing again.",
    ],
    "crash": [
        "Close the Microsoft app fully and reopen it.",
        "If it crashes or fails again, note the exact action and any error message you see.",
    ],
    "email_delivery": [
        "Check the recipient's email address for typos, extra spaces, or a misspelled domain after the @ symbol.",
        "Try sending from Outlook on the web at outlook.com or microsoft365.com to see whether the issue is only in the app.",
        "If it still says domain not found, copy the full error text so support can verify the recipient domain.",
    ],
}

# Hardware-specific fallback replies - used only when Ollama is unreachable
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
        "For USB issues, try a different port and check Windows Device Manager for "
        "any driver errors. Windows Update may have a driver fix available."
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
    "cant hear": (
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
    "touchpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the touchpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "trackpad": (
        "Go to: Settings > Bluetooth & devices > Touchpad and confirm the trackpad is turned on. If it disappeared after an update, check Windows Update for driver fixes."
    ),
    "controller": (
        "Reconnect the controller first, then go to: Settings > Bluetooth & devices and confirm it appears under Devices. If it does not, remove it, pair it again, and check Windows Update."
    ),
}


# ============================================================
# Utility helpers
# ============================================================

def _normalize_message(message):
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def _similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def _fuzzy_match_keyword(word, keyword):
    n = len(keyword)
    if n <= 4:
        threshold = 0.90   # short words - tight to avoid "word" -> "work" noise
    elif n == 5:
        threshold = 0.78   # e.g. "teems" -> "teams"
    elif n <= 7:
        threshold = 0.76   # e.g. "outluk" -> "outlook"
    else:
        threshold = 0.75   # long words have enough chars to absorb more edits
    return _similarity(word, keyword) >= threshold


def _fuzzy_detect_service(message):
    tokens = message.split()
    windows = []
    for size in (1, 2, 3):
        for i in range(len(tokens) - size + 1):
            windows.append(" ".join(tokens[i:i + size]))

    best_service = None
    best_score = -1.0

    for service, keywords in SERVICE_KEYWORDS.items():
        for keyword in keywords:
            if len(keyword) < 4:
                continue
            klen = len(keyword)
            for window in windows:
                wlen = len(window)
                if wlen == 0:
                    continue
                if min(wlen, klen) / max(wlen, klen) < 0.55:
                    continue
                score = _similarity(window, keyword)
                if _fuzzy_match_keyword(window, keyword) and score > best_score:
                    best_score = score
                    best_service = service

    return best_service


def _fuzzy_detect_intent(message):
    tokens = message.split()
    windows = []
    for size in (1, 2, 3):
        for i in range(len(tokens) - size + 1):
            windows.append(" ".join(tokens[i:i + size]))

    best_intent = None
    best_score = -1.0

    for intent, keywords in INTENT_KEYWORDS.items():
        if intent == "email_delivery":
            continue
        for keyword in keywords:
            if len(keyword) < 5:
                continue
            klen = len(keyword)
            for window in windows:
                wlen = len(window)
                if wlen == 0:
                    continue
                if min(wlen, klen) / max(wlen, klen) < 0.55:
                    continue
                score = _similarity(window, keyword)
                if score >= 0.78 and score > best_score:
                    best_score = score
                    best_intent = intent

    return best_intent


def _term_in_text(text, term):
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def _contains_any(text, terms):
    return any(_term_in_text(text, term) for term in terms)


def _detect_all_services(message):
    return [
        service
        for service, keywords in SERVICE_KEYWORDS.items()
        if _contains_any(message, keywords)
    ]


def _canonical_service(service_name, fallback=None):
    normalized = str(service_name or "").strip().lower()
    if normalized in SERVICE_KEYWORDS:
        return normalized
    return fallback or "microsoft 365"


def _service_label(service):
    return SERVICE_LABELS.get(service or "microsoft 365", "Microsoft 365")


def _detect_unsupported_service(message):
    for service, keywords in UNSUPPORTED_STATUS_KEYWORDS.items():
        if _contains_any(message, keywords):
            return service
    return None


def _detect_hardware_term(message):
    """
    Returns the first hardware term found in the message,
    or None. Multi-word terms are checked before single-word
    ones because HARDWARE_SERVICE_MAP is ordered that way.
    Exact match runs first; fuzzy pass covers single-word terms
    of 4+ chars only.
    """
    if _contains_any(message, AUDIO_INPUT_ISSUE_TERMS):
        return "audio input"
    if _contains_any(message, AUDIO_OUTPUT_ISSUE_TERMS):
        return "audio output"

    for term in HARDWARE_SERVICE_MAP:
        if _term_in_text(message, term):
            return term
    for token in message.split():
        for term in HARDWARE_SERVICE_MAP:
            if term not in FUZZY_HARDWARE_TERMS:
                continue
            if len(term) < 4:
                continue
            if _fuzzy_match_keyword(token, term):
                return term
    return None


def _is_out_of_scope_hardware(message):
    """
    Returns True when the message describes pure physical
    damage that has no Microsoft software fix.
    """
    if _contains_any(message, OUT_OF_SCOPE_HARDWARE):
        return True

    damage_patterns = (
        r"\b(screen|display|monitor)\b.*\b(crack|cracked|shatter|shattered)\b",
        r"\b(crack|cracked|shatter|shattered)\b.*\b(screen|display|monitor)\b",
        r"\b(won't|wont|cannot|can't|cant)\s+(power on|turn on)\b",
    )
    return any(re.search(pattern, message) for pattern in damage_patterns)


def _get_hardware_context(message):
    """
    Returns a dict with hardware detection results.
    Internal routing data only - not exposed to the frontend.
    """
    term = _detect_hardware_term(message)
    return {
        "has_hardware_term": term is not None,
        "hardware_term": term,
        "suggested_service": HARDWARE_SERVICE_MAP.get(term) if term else None,
        "is_out_of_scope": _is_out_of_scope_hardware(message),
    }


def _extract_history_context(conversation_history):
    history = conversation_history or []
    services_mentioned = []
    seen = set()
    last_service = None
    for turn in history:
        if str(turn.get("sender", "")).lower() != "user":
            continue
        msg = _normalize_message(turn.get("message", ""))
        for svc in _detect_all_services(msg):
            if svc not in seen:
                services_mentioned.append(svc)
                seen.add(svc)
            last_service = svc
    return {
        "services_mentioned": services_mentioned,
        "last_service": last_service,
        "turn_count": len(history),
        "has_prior_context": len(history) > 0,
    }


def _detect_intent(message):
    for intent, keywords in INTENT_KEYWORDS.items():
        if _contains_any(message, keywords):
            return intent
    return _fuzzy_detect_intent(message) or "unknown"


def _has_detailed_description(message):
    words = message.split()
    if len(words) >= 10:
        return True
    if _contains_any(message, DETAIL_HINT_TERMS):
        return True
    if re.search(r"\b[a-z]{2,}\d{2,}\b", message):
        return True
    return False


def _is_non_issue_message(message, intent="unknown",
                          escalation_requested=False,
                          awaiting_ticket_detail=False):
    if awaiting_ticket_detail or escalation_requested:
        return False

    if intent != "unknown" or _contains_any(message, DETAIL_HINT_TERMS):
        return False

    if _contains_any(message, CONTINUING_ISSUE_TERMS):
        return False

    if _contains_any(message, POSITIVE_RESOLUTION_TERMS):
        return True

    if _contains_any(message, GRATITUDE_TERMS):
        return len(message.split()) <= 5

    return False


def _is_greeting_only(message, intent="unknown",
                      escalation_requested=False,
                      awaiting_ticket_detail=False):
    if awaiting_ticket_detail or escalation_requested or intent != "unknown":
        return False
    if _contains_any(message, CONTINUING_ISSUE_TERMS + DETAIL_HINT_TERMS):
        return False
    if _detect_all_services(message) or _get_hardware_context(message)["has_hardware_term"]:
        return False
    return len(message.split()) <= 4 and _contains_any(message, GREETING_TERMS)


def _build_reply(lines):
    return " ".join(line.strip() for line in lines if line and str(line).strip())


def _ask_for_ticket_details(service):
    service_label = _service_label(service)
    return _build_reply([
        "I can create a ticket for you.",
        f"Please describe the {service_label} issue in more detail.",
        "Include what you were trying to do, what happened, and any error message you saw.",
    ])


def _service_specific_prompt(service):
    """Emergency fallback only - used when Ollama is unreachable."""
    service_label = _service_label(service)
    follow_up = SERVICE_FOLLOW_UPS.get(
        service or "microsoft 365", SERVICE_FOLLOW_UPS["microsoft 365"]
    )
    return _build_reply([
        f"I can help with {service_label}.",
        follow_up,
        "If you want support right away, say ticket and I will start that process.",
    ])


def _rule_based_step_reply(service, intent):
    """Emergency fallback only - used when Ollama is unreachable."""
    service_label = _service_label(service)
    reply_lines = list(SHORT_STEP_RESPONSES[intent])
    if service and service != "microsoft 365":
        reply_lines.insert(0, f"I can help with {service_label}.")
    reply_lines.append("If that does not help, say ticket and I will start a support request.")
    return _build_reply(reply_lines)


def _apply_gemma_result(response, gemma_result, detailed_enough,
                        allow_ticket_creation=False, strong_outage=False):
    if not gemma_result:
        return None

    service = _canonical_service(
        gemma_result.get("service"), fallback=response["service"]
    )
    response["service"] = service
    response["intent"] = gemma_result.get("intent", response["intent"])

    raw_priority = gemma_result.get("priority", "medium")
    if raw_priority == "high" and not strong_outage:
        raw_priority = "medium"
    response["priority"] = raw_priority

    reply = str(gemma_result.get("reply", "")).strip()
    if not reply:
        return None

    if gemma_result.get("needs_ticket"):
        if not allow_ticket_creation:
            response["reply"] = _build_reply([
                reply,
                "If you want support right away, say ticket and I will start that process.",
            ])
            response["resolved"] = True
            return response

        response["needs_ticket"] = True
        if gemma_result.get("needs_description") or not detailed_enough:
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
                   conversation_history=None):

    msg = _normalize_message(message)
    conversation_history = conversation_history or []

    # --- Detection ---
    detected_services = _detect_all_services(msg)
    explicit_service = detected_services[0] if detected_services else None
    fuzzy_service = None if explicit_service else _fuzzy_detect_service(msg)
    hardware_context = _get_hardware_context(msg)
    history_context = _extract_history_context(conversation_history)

    # Service hint priority:
    # explicit keyword > hardware mapping > history context > fuzzy match > default
    if explicit_service:
        service = explicit_service
    elif hardware_context["suggested_service"]:
        service = hardware_context["suggested_service"]
    elif history_context["last_service"]:
        service = history_context["last_service"]
    elif fuzzy_service:
        service = fuzzy_service
    else:
        service = "microsoft 365"

    unsupported_service = _detect_unsupported_service(msg)
    intent = _detect_intent(msg)
    escalation_requested = _contains_any(msg, ESCALATION_TERMS)
    outage_claim = _contains_any(msg, STRONG_OUTAGE_TERMS)
    detailed_enough = _has_detailed_description(msg)

    # hardware_context is internal routing data only - kept as a local
    # variable, never added to the response dict that reaches the frontend
    response = {
        "resolved": False,
        "reply": "",
        "needs_ticket": False,
        "needs_description": False,
        "create_ticket": False,
        "service": service,
        "detected_services": detected_services,
        "intent": intent,
        "priority": "medium",
        "status_checked": False,
        "status_summary": "",
        "escalation_requested": escalation_requested,
    }

    # =============================================
    # FAST EXITS - bypass Ollama entirely
    # Only for cases where AI adds zero value
    # =============================================

    # 1. Non-issue / gratitude - no AI needed
    if _is_greeting_only(
        msg,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "resolved": True,
            "reply": (
                "Hi, I can help with Microsoft apps like Teams, Outlook, "
                "OneDrive, Windows, and Microsoft account. Tell me what is "
                "going wrong and I will guide you."
            ),
        })
        return response

    if _is_non_issue_message(
        msg,
        intent=intent,
        escalation_requested=escalation_requested,
        awaiting_ticket_detail=awaiting_ticket_detail,
    ):
        response.update({
            "resolved": True,
            "reply": (
                "Glad to hear it! Feel free to come back "
                "if anything comes up with your Microsoft apps."
            ),
        })
        return response

    # 2. Unsupported service - deterministic scope rejection
    if unsupported_service:
        response.update({
            "resolved": True,
            "service": unsupported_service,
            "reply": (
                f"I do not support {unsupported_service} in this bot. "
                "I handle consumer Microsoft products only: Teams, Outlook, "
                "OneDrive, Word, Excel, PowerPoint, Windows, and Microsoft account."
            ),
        })
        return response

    # 3. Out-of-scope physical hardware damage
    if hardware_context["is_out_of_scope"]:
        response.update({
            "resolved": True,
            "reply": (
                "It sounds like there may be a physical hardware issue with your "
                "device. Unfortunately that is outside what I can help with here. "
                "For hardware repairs, contact your device manufacturer or visit a "
                "local repair service. If there is also a Microsoft software issue "
                "involved, let me know and I can help with that part."
            ),
        })
        return response

    # 4. Explicit escalation - user wants a ticket/human now
    if escalation_requested:
        if detailed_enough:
            response.update({
                "reply": (
                    "I understand. I have enough detail to create your ticket now."
                ),
                "needs_ticket": True,
                "create_ticket": True,
                "priority": "high" if outage_claim else "medium",
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
                "priority": "medium",
            })
        return response

    # 5. Awaiting ticket detail from previous turn
    if awaiting_ticket_detail:
        if detailed_enough:
            response.update({
                "reply": (
                    "Thank you. I have enough detail to create your ticket now."
                ),
                "needs_ticket": True,
                "create_ticket": True,
                "needs_description": False,
                "priority": "high" if outage_claim else "medium",
            })
        else:
            response.update({
                "reply": _ask_for_ticket_details(service),
                "needs_ticket": True,
                "needs_description": True,
            })
        return response

    # =============================================
    # OLLAMA - handles everything else
    # One word, two words, misspellings, hardware,
    # multi-app, bad grammar - all goes here
    # =============================================

    gemma_result, error = generate_triage_response(
        message,
        service_hint=service,
        conversation_history=conversation_history,
        hardware_term=hardware_context["hardware_term"],
    )

    if gemma_result:
        if (
            (
                gemma_result.get("needs_ticket")
                or _contains_any(msg, PERMISSION_PROBLEM_TERMS)
            )
            and hardware_context["has_hardware_term"]
            and not escalation_requested
        ):
            term = hardware_context["hardware_term"]
            fallback_reply = HARDWARE_FALLBACK_RESPONSES.get(term)
            if fallback_reply:
                response.update({
                    "resolved": True,
                    "reply": fallback_reply,
                    "intent": gemma_result.get("intent", response["intent"]),
                })
                return response

        applied = _apply_gemma_result(
            response.copy(),
            gemma_result,
            detailed_enough,
            allow_ticket_creation=True,
            strong_outage=outage_claim,
        )
        if applied:
            return applied

    # =============================================
    # RULE-BASED FALLBACK
    # Only reached when Ollama is unreachable or
    # returned an unreadable response
    # =============================================

    if error:
        print(
            f"[bot_logic] Ollama unavailable, using rule-based fallback. "
            f"Error: {error}"
        )

    # Status / outage fallback
    if _contains_any(msg, STATUS_TERMS) or outage_claim:
        status_result = check_microsoft_public_status(service)
        response.update({
            "resolved": True,
            "reply": status_result["summary"],
            "status_checked": True,
            "status_summary": status_result["summary"],
        })
        return response

    # Hardware fallback - better than the generic paragraph
    if hardware_context["has_hardware_term"]:
        term = hardware_context["hardware_term"]
        fallback_reply = HARDWARE_FALLBACK_RESPONSES.get(term)
        if fallback_reply:
            response.update({
                "resolved": True,
                "reply": fallback_reply,
            })
            return response

    # Known intent fallback
    if intent in SHORT_STEP_RESPONSES:
        response.update({
            "resolved": True,
            "reply": _rule_based_step_reply(service, intent),
        })
        return response

    # Service detected fallback
    if service and service != "microsoft 365":
        response.update({
            "resolved": True,
            "reply": _service_specific_prompt(service),
        })
        return response

    # Generic fallback - absolute last resort
    response.update({
        "reply": (
            "I am having trouble connecting right now. "
            "Please tell me which Microsoft app is affected "
            "and what is going wrong. If you need immediate "
            "support, say ticket and I will create one for you."
        ),
        "needs_description": True,
    })
    return response
