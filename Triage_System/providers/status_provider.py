STATUS_PAGE_URL = "https://status.cloud.microsoft/"

KNOWN_SERVICES = {
    "microsoft 365": ["microsoft 365", "office 365", "m365"],
    "outlook": ["outlook", "exchange"],
    "teams": ["teams", "microsoft teams"],
    "onedrive": ["onedrive"],
    "sharepoint": ["sharepoint"],
    "excel": ["excel"],
    "word": ["word", "microsoft word"],
    "powerpoint": ["powerpoint", "power point"],
    "windows": ["windows", "windows sign in", "windows login"],
    "microsoft account": ["microsoft account", "account.microsoft"],
}


def _resolve_service(service_name):
    normalized = str(service_name or "").strip().lower()
    if normalized in KNOWN_SERVICES:
        return normalized, True
    if normalized:
        return normalized, False
    return "microsoft 365", True


def check_microsoft_public_status(service_name=None):
    resolved_service, service_known = _resolve_service(service_name)
    return {
        "source": STATUS_PAGE_URL,
        "service": resolved_service,
        "issue_found": False,
        "summary": (
            "I am not able to check Microsoft service status automatically right now. "
            f"You can check {STATUS_PAGE_URL} directly for the latest information."
        ),
        "status_available": False,
        "error": None,
        "service_known": service_known,
        "stale": False,
    }
