import json
import os
from pathlib import Path


DEFAULT_DOMAIN_NAME = "microsoft365"
DEFAULT_SERVICE = "microsoft 365"
DEFAULT_DOMAIN_LABEL = "Microsoft 365"

_ROOT_DIR = Path(__file__).resolve().parent.parent
_DOMAINS_DIR = _ROOT_DIR / "domains"


def _normalize_key(value):
    return str(value or "").strip().lower()


def as_tuple(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value if str(item or "").strip())
    return (str(value),)


def unique_tuple(*values):
    seen = set()
    items = []
    for value in values:
        for item in as_tuple(value):
            normalized = _normalize_key(item)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            items.append(str(item))
    return tuple(items)


def active_domain_name():
    return _normalize_key(os.getenv("BOT_DOMAIN", DEFAULT_DOMAIN_NAME)) or DEFAULT_DOMAIN_NAME


def active_domain_names():
    raw_names = os.getenv("BOT_DOMAINS", "").strip()
    if not raw_names:
        return (active_domain_name(),)
    names = []
    for item in raw_names.replace(";", ",").split(","):
        normalized = _normalize_key(item)
        if normalized and normalized not in names:
            names.append(normalized)
    return tuple(names or (DEFAULT_DOMAIN_NAME,))


def _domain_path(domain_name, use_explicit_path=False):
    explicit_path = os.getenv("BOT_DOMAIN_PATH", "").strip()
    if use_explicit_path and explicit_path:
        return Path(explicit_path)
    return _DOMAINS_DIR / (domain_name or DEFAULT_DOMAIN_NAME) / "domain.json"


def _empty_pack(domain_name, path=None, load_error=""):
    return {
        "name": domain_name or DEFAULT_DOMAIN_NAME,
        "domain_label": DEFAULT_DOMAIN_LABEL,
        "default_service": DEFAULT_SERVICE,
        "description": "",
        "services": {},
        "intents": {},
        "service_intent_responses": {},
        "knowledge_resources": [],
        "gemini": {},
        "_path": str(path or ""),
        "_load_error": load_error,
    }


def load_domain_pack(domain_name=None):
    name = _normalize_key(domain_name) or active_domain_name()
    path = _domain_path(name, use_explicit_path=domain_name is None)
    if not path.exists():
        return _empty_pack(name, path=path, load_error="missing")

    try:
        with path.open("r", encoding="utf-8-sig") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        return _empty_pack(name, path=path, load_error=str(exc))

    if not isinstance(data, dict):
        return _empty_pack(name, path=path, load_error="domain pack must be a JSON object")

    pack = _empty_pack(name, path=path)
    pack.update(data)
    pack["name"] = _normalize_key(pack.get("name") or name) or name
    pack["domain_label"] = str(pack.get("domain_label") or DEFAULT_DOMAIN_LABEL)
    pack["default_service"] = _normalize_key(pack.get("default_service") or DEFAULT_SERVICE)
    pack["_path"] = str(path)
    pack["_load_error"] = ""

    for key in ("services", "intents", "service_intent_responses", "gemini"):
        if not isinstance(pack.get(key), dict):
            pack[key] = {}
    if not isinstance(pack.get("knowledge_resources"), list):
        pack["knowledge_resources"] = []

    return pack


def _merge_dict_values(*values):
    merged = {}
    for value in values:
        if isinstance(value, dict):
            merged.update(value)
    return merged


def _merge_domain_packs(packs):
    packs = [pack for pack in packs if isinstance(pack, dict)]
    if not packs:
        return _empty_pack(DEFAULT_DOMAIN_NAME)
    if len(packs) == 1:
        return packs[0]

    names = [pack.get("name") or DEFAULT_DOMAIN_NAME for pack in packs]
    includes_default = DEFAULT_DOMAIN_NAME in names
    default_pack = packs[0]
    services = _merge_dict_values(*(pack.get("services") for pack in packs))
    intents = _merge_dict_values(*(pack.get("intents") for pack in packs))
    responses = _merge_dict_values(*(pack.get("service_intent_responses") for pack in packs))
    gemini = {"extra_rules": []}
    knowledge_resources = []
    labels = []
    scopes = []
    descriptions = []
    paths = []
    load_errors = []

    for pack in packs:
        label = str(pack.get("domain_label") or "").strip()
        if label:
            labels.append(label)
        scope = str(pack.get("supported_scope") or "").strip()
        if scope:
            scopes.append(scope)
        description = str(pack.get("description") or "").strip()
        if description:
            descriptions.append(description)
        path = str(pack.get("_path") or "").strip()
        if path:
            paths.append(path)
        load_error = str(pack.get("_load_error") or "").strip()
        if load_error:
            load_errors.append(f"{pack.get('name')}: {load_error}")
        knowledge_resources.extend(pack.get("knowledge_resources") or [])
        extra_rules = (pack.get("gemini") or {}).get("extra_rules") or []
        gemini["extra_rules"].extend(as_tuple(extra_rules))

    return {
        "name": ",".join(names),
        "domain_names": tuple(names),
        "domain_label": " + ".join(labels) or DEFAULT_DOMAIN_LABEL,
        "default_service": _normalize_key(default_pack.get("default_service") or DEFAULT_SERVICE),
        "supported_scope": " ".join(scopes),
        "description": " ".join(descriptions),
        "services": services,
        "intents": intents,
        "service_intent_responses": responses,
        "knowledge_resources": knowledge_resources,
        "gemini": gemini,
        "replace_builtin_services": not includes_default or all(
            bool(pack.get("replace_builtin_services")) for pack in packs
        ),
        "replace_builtin_intents": not includes_default or all(
            bool(pack.get("replace_builtin_intents")) for pack in packs
        ),
        "replace_builtin_knowledge": not includes_default or all(
            bool(pack.get("replace_builtin_knowledge")) for pack in packs
        ),
        "replace_builtin_responses": not includes_default or all(
            bool(pack.get("replace_builtin_responses")) for pack in packs
        ),
        "include_learned_knowledge": any(
            bool(pack.get("include_learned_knowledge")) for pack in packs
        ),
        "_path": ";".join(paths),
        "_load_error": "; ".join(load_errors),
    }


def load_domain_packs(domain_names=None):
    if domain_names is None and os.getenv("BOT_DOMAIN_PATH", "").strip() and not os.getenv("BOT_DOMAINS", "").strip():
        return load_domain_pack()
    names = tuple(domain_names or active_domain_names())
    packs = [load_domain_pack(name) for name in names]
    return _merge_domain_packs(packs)


def service_names(pack):
    names = {_normalize_key(pack.get("default_service") or DEFAULT_SERVICE)}
    for service_name in (pack.get("services") or {}):
        normalized = _normalize_key(service_name)
        if normalized:
            names.add(normalized)
    return names


def intent_names(pack):
    names = set()
    for intent_name in (pack.get("intents") or {}):
        normalized = _normalize_key(intent_name)
        if normalized:
            names.add(normalized)
    for key in (pack.get("service_intent_responses") or {}):
        parts = str(key or "").split("|", 1)
        if len(parts) == 2 and _normalize_key(parts[1]):
            names.add(_normalize_key(parts[1]))
    return names


def normalize_knowledge_resource(resource, default_service=None):
    if not isinstance(resource, dict):
        return None
    resource_id = str(resource.get("id") or "").strip()
    steps = as_tuple(resource.get("steps"))
    keywords = as_tuple(resource.get("keywords"))
    if not resource_id or not steps or not keywords:
        return None

    required_any = []
    for group in resource.get("required_any") or []:
        terms = as_tuple(group)
        if terms:
            required_any.append(terms)

    return {
        "id": resource_id,
        "service": _normalize_key(resource.get("service") or default_service or DEFAULT_SERVICE),
        "intent": _normalize_key(resource.get("intent") or "unknown") or "unknown",
        "title": str(resource.get("title") or resource_id),
        "source": str(resource.get("source") or "Domain support playbook"),
        "source_url": str(resource.get("source_url") or ""),
        "keywords": keywords,
        "required_any": tuple(required_any),
        "steps": steps,
        "advanced_steps": as_tuple(resource.get("advanced_steps")),
        "domain": str(resource.get("domain") or ""),
    }


def domain_knowledge_resources(pack):
    default_service = pack.get("default_service") or DEFAULT_SERVICE
    resources = []
    for resource in pack.get("knowledge_resources") or []:
        cleaned = normalize_knowledge_resource(resource, default_service=default_service)
        if cleaned:
            resources.append(cleaned)
    return tuple(resources)
