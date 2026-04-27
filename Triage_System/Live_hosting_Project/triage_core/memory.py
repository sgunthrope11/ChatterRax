import re


MEMORY_STOPWORDS = {
    "the", "and", "but", "for", "with", "that", "this", "then", "than",
    "from", "into", "onto", "when", "where", "what", "which", "about",
    "have", "has", "had", "was", "were", "been", "being", "just", "really",
    "very", "still", "same", "again", "issue", "problem", "broken", "thing",
    "stuff", "help", "please", "after", "before", "today", "yesterday",
    "there", "their", "they", "them", "your", "ours", "mine", "ourselves",
    "does", "doesnt", "don't", "dont", "wont", "won't", "cant", "can't",
    "cannot", "isnt", "isn't", "aint", "like", "keep", "keeps", "more",
    "less", "some", "back", "need", "needs", "want", "wants",
}

REFERENTIAL_TERMS = (
    "same", "again", "still", "before", "back to", "earlier", "previous",
    "that issue", "that one", "that problem", "that outlook issue",
    "same issue", "same issue as before", "issue as before",
)

META_MEMORY_PATTERNS = (
    "what applications was i having trouble with",
    "what apps was i having trouble with",
    "what app was i having trouble with",
    "what apps were we working on",
    "what applications were we working on",
    "what were we working on",
    "what issues have we talked about",
    "what issues were we working on",
    "remind me what we were working on",
    "let's handle ",
    "lets handle ",
    " it is the same issue as before",
    " it's the same issue as before",
)


def _memory_tokens(message):
    return {
        token
        for token in re.findall(r"[a-z0-9']+", str(message or "").lower())
        if len(token) >= 3 and token not in MEMORY_STOPWORDS
    }


def _split_issue_clauses(message):
    raw = str(message or "").strip()
    if not raw:
        return []
    clauses = [
        clause.strip(" ,.;")
        for clause in re.split(r"\b(?:and|but)\b|[;,]", raw, flags=re.IGNORECASE)
        if clause and clause.strip(" ,.;")
    ]
    return clauses or [raw]


def _service_specific_history_message(raw_message, service, detect_all_services):
    clauses = _split_issue_clauses(raw_message)
    for clause in clauses:
        detected = list(detect_all_services(clause) or [])
        if service in detected:
            return clause
    return str(raw_message or "").strip()


def _is_meta_memory_message(message):
    normalized = str(message or "").strip().lower()
    if not normalized:
        return False
    if re.search(r"\bthe\s+.+\s+one\b", normalized):
        return True
    return any(pattern in normalized for pattern in META_MEMORY_PATTERNS)


def extract_history_context(conversation_history, normalize_message, detect_all_services):
    history = conversation_history or []
    services_mentioned = []
    seen = set()
    last_service = None
    current_focus = None

    for turn in history:
        if str(turn.get("sender", "")).lower() != "user":
            continue
        msg = normalize_message(turn.get("message", ""))
        detected_services = list(detect_all_services(msg) or [])
        for service in detected_services:
            if service not in seen:
                services_mentioned.append(service)
                seen.add(service)
            last_service = service
        if len(detected_services) == 1 and detected_services[0] != "microsoft 365":
            current_focus = detected_services[0]

    return {
        "services_mentioned": services_mentioned,
        "last_service": last_service,
        "current_focus": current_focus,
        "turn_count": len(history),
        "has_prior_context": len(history) > 0,
    }


def _resolve_history_message_service(
    message,
    fallback_service,
    detect_all_services,
    get_hardware_context,
    fuzzy_detect_service,
):
    detected_services = detect_all_services(message)
    if detected_services:
        return detected_services[0]

    hardware_context = get_hardware_context(message)
    if hardware_context["suggested_service"]:
        return hardware_context["suggested_service"]

    fuzzy_service = fuzzy_detect_service(message)
    if fuzzy_service:
        return fuzzy_service

    return fallback_service


def build_thread_memory(
    conversation_history,
    normalize_message,
    detect_all_services,
    get_hardware_context,
    fuzzy_detect_service,
    detect_intent,
):
    threads_by_service = {}
    last_service = None

    for index, turn in enumerate(conversation_history or []):
        if str(turn.get("sender", "")).lower() != "user":
            continue

        raw_message = str(turn.get("message", "")).strip()
        if not raw_message:
            continue
        if _is_meta_memory_message(raw_message):
            continue

        message = normalize_message(raw_message)
        detected_services = list(detect_all_services(message) or [])
        candidate_services = [
            service_name
            for service_name in detected_services
            if service_name and service_name != "microsoft 365"
        ]

        if not candidate_services:
            resolved_service = _resolve_history_message_service(
                message,
                fallback_service=last_service,
                detect_all_services=detect_all_services,
                get_hardware_context=get_hardware_context,
                fuzzy_detect_service=fuzzy_detect_service,
            )
            if resolved_service:
                candidate_services = [resolved_service]

        if (
            "sharepoint" in candidate_services
            and any(service_name in {"word", "excel", "powerpoint"} for service_name in candidate_services)
            and any(
                phrase in message
                for phrase in (
                    "metadata",
                    "required columns",
                    "required column",
                    "document info panel",
                    "properties panel",
                    "info panel",
                )
            )
        ):
            candidate_services = ["sharepoint"]

        normalized_services = []
        for service in candidate_services:
            if service == "microsoft 365" and last_service:
                service = last_service
            if service and service not in normalized_services:
                normalized_services.append(service)

        if not normalized_services:
            continue

        last_service = normalized_services[-1]
        for service in normalized_services:
            service_message = _service_specific_history_message(
                raw_message,
                service,
                detect_all_services,
            )
            normalized_service_message = normalize_message(service_message)
            service_intent = detect_intent(normalized_service_message)
            thread = threads_by_service.setdefault(
                service,
                {
                    "service": service,
                    "last_intent": "unknown",
                    "recent_messages": [],
                    "keywords": set(),
                    "last_turn": index,
                },
            )

            if service_intent != "unknown":
                thread["last_intent"] = service_intent

            thread["last_turn"] = index
            thread["keywords"].update(_memory_tokens(normalized_service_message))
            thread["recent_messages"].append(service_message)
            thread["recent_messages"] = thread["recent_messages"][-3:]

    ordered_threads = sorted(
        threads_by_service.values(),
        key=lambda item: item["last_turn"],
        reverse=True,
    )
    return {
        "threads": ordered_threads,
        "last_service": last_service,
    }


def related_history_match(message, thread_memory, contains_any):
    threads = list(thread_memory.get("threads") or [])
    if not threads:
        return {
            "service": None,
            "score": 0,
            "referential": False,
        }

    message_tokens = _memory_tokens(message)
    if not message_tokens:
        return {
            "service": None,
            "score": 0,
            "referential": contains_any(message, REFERENTIAL_TERMS),
        }

    referential = contains_any(message, REFERENTIAL_TERMS) or bool(
        re.search(r"\bthe\s+.+\s+one\b", str(message or "").lower())
    )
    best_service = None
    best_score = 0

    for rank, thread in enumerate(threads):
        overlap = len(message_tokens & thread.get("keywords", set()))
        if overlap == 0:
            continue

        score = (overlap * 2) + max(0, 2 - rank)
        if referential:
            score += 1

        if score > best_score:
            best_score = score
            best_service = thread.get("service")

    return {
        "service": best_service,
        "score": best_score,
        "referential": referential,
    }


def clarify_current_application_reply(thread_memory, service_label):
    recent_services = [
        thread.get("service")
        for thread in (thread_memory.get("threads") or [])[:2]
        if thread.get("service") and thread.get("service") != "microsoft 365"
    ]

    unique_services = []
    for service in recent_services:
        if service not in unique_services:
            unique_services.append(service)

    if len(unique_services) >= 2:
        labels = " or ".join(service_label(service) for service in unique_services[:2])
        return (
            f"I want to focus on the issue happening right now. Are we back on {labels}, "
            "or is a different Microsoft app giving you trouble now?"
        )
    if len(unique_services) == 1:
        return (
            "I want to focus on the current issue first. Are we still working on the "
            f"{service_label(unique_services[0])} problem, or is another Microsoft app the one acting up now?"
        )
    return (
        "I want to focus on the current issue first. Which Microsoft app is giving you trouble right now?"
    )


def should_clarify_current_application(
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
    if not history_context.get("has_prior_context"):
        return False
    if len(str(message or "").split()) >= 12 and not related_match.get("referential"):
        return False
    score = related_match.get("score", 0)
    if score >= 4:
        return False
    return True
