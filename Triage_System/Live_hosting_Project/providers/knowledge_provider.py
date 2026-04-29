import json
import os
import re
import time
from pathlib import Path

try:
    from providers.knowledge_resources_expanded import EXPANDED_KNOWLEDGE_RESOURCES
    from providers.knowledge_resources_boost import ADDITIONAL_KNOWLEDGE_RESOURCES
    from providers.knowledge_resources_it_expanded import IT_KNOWLEDGE_RESOURCES
    from providers.knowledge_resources_m365_base import M365_BASE_KNOWLEDGE_RESOURCES
except ImportError:
    from .knowledge_resources_expanded import EXPANDED_KNOWLEDGE_RESOURCES
    from .knowledge_resources_boost import ADDITIONAL_KNOWLEDGE_RESOURCES
    from .knowledge_resources_it_expanded import IT_KNOWLEDGE_RESOURCES
    from .knowledge_resources_m365_base import M365_BASE_KNOWLEDGE_RESOURCES

from triage_core.domain_config import (
    DEFAULT_SERVICE,
    as_tuple,
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
DOMAIN_LABEL = str(DOMAIN_PACK.get("domain_label") or DOMAIN_DEFAULT_SERVICE.title())
BROAD_SERVICE_HINT_SERVICES = service_names(DOMAIN_PACK) - {DOMAIN_DEFAULT_SERVICE}
ACTIVE_DOMAIN_PROFILES = {
    str(item or "").strip().lower()
    for item in (
        as_tuple(DOMAIN_PACK.get("built_in_profiles"))
        + as_tuple(DOMAIN_PACK.get("built_in_profile"))
    )
    if str(item or "").strip()
}


BUILTIN_KNOWLEDGE_RESOURCES = (
    M365_BASE_KNOWLEDGE_RESOURCES
    + EXPANDED_KNOWLEDGE_RESOURCES
    + ADDITIONAL_KNOWLEDGE_RESOURCES
    + IT_KNOWLEDGE_RESOURCES
)

DOMAIN_KNOWLEDGE_RESOURCES = domain_knowledge_resources(DOMAIN_PACK)
if "microsoft365" in ACTIVE_DOMAIN_PROFILES and not DOMAIN_PACK.get("replace_builtin_knowledge"):
    KNOWLEDGE_RESOURCES = BUILTIN_KNOWLEDGE_RESOURCES + DOMAIN_KNOWLEDGE_RESOURCES
else:
    KNOWLEDGE_RESOURCES = DOMAIN_KNOWLEDGE_RESOURCES


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
            "service": str(resource.get("service") or DOMAIN_DEFAULT_SERVICE),
            "intent": str(resource.get("intent") or "unknown"),
            "title": str(resource.get("title") or f"{DOMAIN_LABEL} support article"),
            "source": str(resource.get("source") or "Learned support memory"),
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
    if not DOMAIN_PACK.get("include_learned_knowledge"):
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
        "service": str(resource.get("service") or DOMAIN_DEFAULT_SERVICE),
        "intent": str(resource.get("intent") or "unknown"),
        "title": str(resource.get("title") or f"{DOMAIN_LABEL} support article"),
        "source": str(resource.get("source") or "Official support"),
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
