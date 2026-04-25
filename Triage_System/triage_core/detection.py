import re
from difflib import SequenceMatcher


def normalize_message(message):
    return re.sub(r"\s+", " ", str(message or "").strip().lower())


def similarity(a, b):
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_match_keyword(word, keyword):
    n = len(keyword)
    if n <= 4:
        threshold = 0.90
    elif n == 5:
        threshold = 0.78
    elif n <= 7:
        threshold = 0.76
    else:
        threshold = 0.75
    return similarity(word, keyword) >= threshold


def fuzzy_match_hardware_term(token, term):
    if not token or not term:
        return False
    if token[0] != term[0]:
        return False
    if min(len(token), len(term)) / max(len(token), len(term)) < 0.70:
        return False
    threshold = 0.86 if len(term) <= 7 else 0.82
    return similarity(token, term) >= threshold


def term_in_text(text, term):
    pattern = r"\b" + re.escape(term).replace(r"\ ", r"\s+") + r"\b"
    return re.search(pattern, text) is not None


def contains_any(text, terms):
    return any(term_in_text(text, term) for term in terms)


def append_unique(items, value):
    if value and value not in items:
        items.append(value)


def fuzzy_detect_service(message, service_keywords):
    tokens = message.split()
    windows = []
    for size in (1, 2, 3):
        for index in range(len(tokens) - size + 1):
            windows.append(" ".join(tokens[index:index + size]))

    best_service = None
    best_score = -1.0

    for service, keywords in service_keywords.items():
        for keyword in keywords:
            if len(keyword) < 4:
                continue
            keyword_length = len(keyword)
            for window in windows:
                window_length = len(window)
                if window_length == 0:
                    continue
                if min(window_length, keyword_length) / max(window_length, keyword_length) < 0.55:
                    continue
                score = similarity(window, keyword)
                if fuzzy_match_keyword(window, keyword) and score > best_score:
                    best_score = score
                    best_service = service

    return best_service


def fuzzy_detect_intent(message, intent_keywords):
    tokens = message.split()
    windows = []
    for size in (1, 2, 3):
        for index in range(len(tokens) - size + 1):
            windows.append(" ".join(tokens[index:index + size]))

    best_intent = None
    best_score = -1.0

    for intent, keywords in intent_keywords.items():
        if intent == "email_delivery":
            continue
        for keyword in keywords:
            if len(keyword) < 5:
                continue
            keyword_length = len(keyword)
            for window in windows:
                window_length = len(window)
                if window_length == 0:
                    continue
                if min(window_length, keyword_length) / max(window_length, keyword_length) < 0.55:
                    continue
                score = similarity(window, keyword)
                if score >= 0.78 and score > best_score:
                    best_score = score
                    best_intent = intent

    return best_intent


def detect_all_services(message, service_keywords):
    return [
        service
        for service, keywords in service_keywords.items()
        if contains_any(message, keywords)
    ]


def canonical_service(service_name, service_keywords, fallback=None):
    normalized = str(service_name or "").strip().lower()
    if normalized in service_keywords:
        return normalized
    return fallback or "microsoft 365"


def service_label(service, service_labels):
    return service_labels.get(service or "microsoft 365", "Microsoft 365")


def detect_unsupported_service(message, unsupported_status_keywords, unsupported_service_keywords):
    for service, keywords in (
        list(unsupported_status_keywords.items())
        + list(unsupported_service_keywords.items())
    ):
        if contains_any(message, keywords):
            return service
    return None


def detect_hardware_term(
    message,
    audio_input_issue_terms,
    audio_output_issue_terms,
    hardware_service_map,
    fuzzy_hardware_terms,
):
    if contains_any(message, audio_input_issue_terms):
        return "audio input"
    if contains_any(message, audio_output_issue_terms):
        return "audio output"

    for term in hardware_service_map:
        if term_in_text(message, term):
            return term

    for token in message.split():
        for term in hardware_service_map:
            if term not in fuzzy_hardware_terms:
                continue
            if len(term) < 4:
                continue
            if fuzzy_match_hardware_term(token, term):
                return term
    return None


def detect_all_hardware_terms(
    message,
    audio_input_issue_terms,
    audio_output_issue_terms,
    hardware_service_map,
    fuzzy_hardware_terms,
):
    terms = []

    if contains_any(message, audio_input_issue_terms):
        append_unique(terms, "audio input")
    if contains_any(message, audio_output_issue_terms):
        append_unique(terms, "audio output")

    for term in hardware_service_map:
        if not term_in_text(message, term):
            continue
        if any(term in existing for existing in terms):
            continue
        append_unique(terms, term)

    for token in message.split():
        for term in hardware_service_map:
            if term not in fuzzy_hardware_terms:
                continue
            if len(term) < 4:
                continue
            if any(term in existing or existing in term for existing in terms):
                continue
            if fuzzy_match_hardware_term(token, term):
                append_unique(terms, term)

    return terms


def is_out_of_scope_hardware(message, out_of_scope_hardware):
    if contains_any(message, out_of_scope_hardware):
        return True

    damage_patterns = (
        r"\b(screen|display|monitor)\b.*\b(crack|cracked|shatter|shattered)\b",
        r"\b(crack|cracked|shatter|shattered)\b.*\b(screen|display|monitor)\b",
        r"\b(won't|wont|cannot|can't|cant)\s+(power on|turn on)\b",
    )
    return any(re.search(pattern, message) for pattern in damage_patterns)


def get_hardware_context(
    message,
    audio_input_issue_terms,
    audio_output_issue_terms,
    hardware_service_map,
    fuzzy_hardware_terms,
    out_of_scope_hardware,
):
    term = detect_hardware_term(
        message,
        audio_input_issue_terms,
        audio_output_issue_terms,
        hardware_service_map,
        fuzzy_hardware_terms,
    )
    return {
        "has_hardware_term": term is not None,
        "hardware_term": term,
        "hardware_terms": detect_all_hardware_terms(
            message,
            audio_input_issue_terms,
            audio_output_issue_terms,
            hardware_service_map,
            fuzzy_hardware_terms,
        ),
        "suggested_service": hardware_service_map.get(term) if term else None,
        "is_out_of_scope": is_out_of_scope_hardware(message, out_of_scope_hardware),
    }


def detect_intent(message, intent_keywords):
    for intent, keywords in intent_keywords.items():
        if contains_any(message, keywords):
            return intent
    return fuzzy_detect_intent(message, intent_keywords) or "unknown"


def looks_like_vague_service_message(
    message,
    service,
    intent,
    vague_service_message_terms,
    short_service_action_terms,
    status_terms,
    strong_outage_terms,
    teams_join_terms,
    explicit_service=None,
    fuzzy_service=None,
    hardware_context=None,
    known_issue=None,
    multi_context=None,
):
    if not service or service == "microsoft 365":
        return False
    if hardware_context and hardware_context.get("has_hardware_term"):
        return False
    if known_issue:
        return False
    if multi_context and multi_context.get("is_multi"):
        return False
    if not (explicit_service or fuzzy_service):
        return False
    if contains_any(message, status_terms + strong_outage_terms):
        return False
    if service == "teams" and contains_any(message, teams_join_terms):
        return False

    words = [word for word in str(message or "").split() if word.strip()]
    if not words:
        return False
    if len(words) == 1:
        return True
    if len(words) > 3 or intent != "unknown":
        return False

    normalized = {re.sub(r"[^a-z0-9]+", "", word.lower()) for word in words}
    service_tokens = {re.sub(r"[^a-z0-9]+", "", token) for token in str(service).split()}
    filler_tokens = {
        re.sub(r"[^a-z0-9]+", "", token.lower())
        for token in vague_service_message_terms
    }
    action_tokens = {
        re.sub(r"[^a-z0-9]+", "", token.lower())
        for token in short_service_action_terms
    }
    meaningful = {token for token in normalized if token}
    non_service_tokens = meaningful - service_tokens
    if not non_service_tokens:
        return True
    return non_service_tokens.issubset(filler_tokens | action_tokens)


def has_detailed_description(message, detail_hint_terms):
    words = message.split()
    if len(words) >= 8:
        return True
    if contains_any(message, detail_hint_terms):
        return True
    if re.search(r"\b[a-z]{2,}\d{2,}\b", message):
        return True
    return False


def is_non_issue_message(
    message,
    positive_resolution_terms,
    gratitude_terms,
    continuing_issue_terms,
    detail_hint_terms,
    intent="unknown",
    escalation_requested=False,
    awaiting_ticket_detail=False,
):
    if awaiting_ticket_detail or escalation_requested:
        return False
    if intent != "unknown" or contains_any(message, detail_hint_terms):
        return False
    if contains_any(message, continuing_issue_terms):
        return False
    if contains_any(message, positive_resolution_terms):
        return True
    if contains_any(message, gratitude_terms):
        return len(message.split()) <= 5
    return False


def is_greeting_only(
    message,
    greeting_terms,
    continuing_issue_terms,
    detail_hint_terms,
    detect_all_services_fn,
    get_hardware_context_fn,
    intent="unknown",
    escalation_requested=False,
    awaiting_ticket_detail=False,
):
    if awaiting_ticket_detail or escalation_requested or intent != "unknown":
        return False
    if contains_any(message, continuing_issue_terms + detail_hint_terms):
        return False
    if detect_all_services_fn(message) or get_hardware_context_fn(message)["has_hardware_term"]:
        return False
    return len(message.split()) <= 4 and contains_any(message, greeting_terms)


def is_social_greeting(
    message,
    social_greeting_terms,
    detect_all_services_fn,
    get_hardware_context_fn,
    intent="unknown",
    escalation_requested=False,
    awaiting_ticket_detail=False,
):
    if awaiting_ticket_detail or escalation_requested or intent != "unknown":
        return False
    if detect_all_services_fn(message) or get_hardware_context_fn(message)["has_hardware_term"]:
        return False
    return len(message.split()) <= 7 and contains_any(message, social_greeting_terms)


def detect_correction(message, correction_terms, conversation_history=None):
    if not contains_any(message, correction_terms):
        return False
    history = conversation_history or []
    bot_turns = [
        turn for turn in history
        if str(turn.get("sender", "")).lower() != "user"
    ]
    return len(bot_turns) >= 1


def detect_escalation_request(message, escalation_terms, negated_escalation_patterns):
    if not contains_any(message, escalation_terms):
        return False
    return not any(re.search(pattern, message) for pattern in negated_escalation_patterns)


def is_unrelated_scope(
    message,
    detected_services,
    hardware_context,
    intent,
    unrelated_topic_terms,
    greeting_terms,
):
    if hardware_context["is_out_of_scope"]:
        return False
    if detected_services or hardware_context["has_hardware_term"]:
        return False
    if contains_any(message, unrelated_topic_terms):
        return True
    if intent == "unknown" and not contains_any(message, greeting_terms):
        return len(message.split()) >= 3
    return False


def has_multi_issue_marker(message, topic_count, multi_issue_strong_markers):
    padded = f" {message} "
    for marker in multi_issue_strong_markers:
        if marker.strip() and marker.strip().replace(" ", "").isalnum():
            if term_in_text(message, marker.strip()):
                return True
        elif marker in padded:
            return True
    return topic_count >= 3 and " and " in f" {message} "


def infer_loose_services(message, services):
    inferred = list(services)

    if contains_any(message, ("email", "emails", "mail", "inbox", "bounce", "bounced")):
        append_unique(inferred, "outlook")
    if contains_any(message, ("meeting", "meetings", "video call", "teams call", "channel", "chat")):
        append_unique(inferred, "teams")
    if (
        contains_any(message, ("files", "cloud files", "upload", "uploading", "pending"))
        or (
            contains_any(message, ("sync", "syncing"))
            and contains_any(message, ("onedrive", "one drive", "cloud", "folder", "file", "files"))
        )
    ):
        if "sharepoint" not in inferred:
            append_unique(inferred, "onedrive")
    if contains_any(message, ("authenticator", "verification code", "security code", "wrong password", "ms account", "microsoft login")):
        append_unique(inferred, "microsoft account")
    if contains_any(message, ("dock", "docking station", "screen", "monitor", "printer", "scanner", "wifi", "wi-fi")):
        append_unique(inferred, "windows")

    return inferred


def pretty_hardware_term(term):
    special = {
        "usb": "USB",
        "usb drive": "USB drive",
        "usb stick": "USB stick",
        "usb stik": "USB stick",
        "flsh drv": "flash drive",
        "flash drv": "flash drive",
        "usb c": "USB-C",
        "usb-c": "USB-C",
        "wi-fi": "Wi-Fi",
        "wifi": "Wi-Fi",
        "bluetooth": "Bluetooth",
        "blutooth": "Bluetooth",
        "bluethooth": "Bluetooth",
        "bluetoth": "Bluetooth",
        "bluettoth": "Bluetooth",
        "bleutooth": "Bluetooth",
        "bluetooh": "Bluetooth",
        "bluetoooth": "Bluetooth",
        "bluetooth mouse": "Bluetooth mouse",
        "bluetooth keyboard": "Bluetooth keyboard",
        "bluetooth speaker": "Bluetooth speaker",
        "bluetooth headset": "Bluetooth headset",
        "bluetooth headphones": "Bluetooth headphones",
        "audio input": "audio input",
        "audio output": "audio output",
        "no soud": "no sound",
        "cnt hear": "cannot hear audio",
        "cnt here": "cannot hear audio",
        "cnt heer": "cannot hear audio",
        "screeen": "screen",
        "moniter": "monitor",
        "secnd monitor": "second monitor",
        "secnd moniter": "second monitor",
        "mouce": "mouse",
        "dok": "dock",
        "printr": "printer",
        "prnter": "printer",
        "priinter": "printer",
        "priner": "printer",
        "prinetr": "printer",
        "printar": "printer",
        "scaner": "scanner",
        "scannr": "scanner",
        "scannar": "scanner",
        "scannner": "scanner",
    }
    return special.get(term, term)


def get_multi_issue_context(
    message,
    detected_services,
    hardware_context,
    fuzzy_detect_service_fn,
    hardware_service_map,
    multi_issue_strong_markers,
):
    hardware_terms = hardware_context.get("hardware_terms") or []
    services = infer_loose_services(message, detected_services)
    fuzzy_service = fuzzy_detect_service_fn(message)
    if (
        fuzzy_service == "onedrive"
        and hardware_context.get("hardware_term") in {
            "usb drive", "usb stick", "usb stik", "flash drive",
            "flsh drv", "thumb drive", "external drive", "hard drive", "usb",
        }
    ):
        fuzzy_service = None
    append_unique(services, fuzzy_service)

    base_service_count = len([service for service in services if service != "microsoft 365"])
    topic_count = base_service_count + len(hardware_terms)
    is_multi = (
        base_service_count >= 2
        or (
            len(hardware_terms) >= 2
            and has_multi_issue_marker(message, topic_count, multi_issue_strong_markers)
        )
        or (
            base_service_count >= 1
            and len(hardware_terms) >= 1
            and has_multi_issue_marker(message, topic_count, multi_issue_strong_markers)
        )
    )

    if is_multi:
        for term in hardware_terms:
            mapped_service = hardware_service_map.get(term)
            if mapped_service and mapped_service != "teams":
                append_unique(services, mapped_service)

    return {
        "is_multi": is_multi,
        "services": services,
        "hardware_terms": hardware_terms,
    }
