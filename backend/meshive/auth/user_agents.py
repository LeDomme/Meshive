from dataclasses import dataclass


@dataclass(frozen=True)
class ClientMetadata:
    browser: str | None
    operating_system: str | None
    device_type: str | None


def parse_user_agent(user_agent: str | None) -> ClientMetadata:
    """Return broad client information without retaining the raw user agent."""
    value = user_agent or ""

    if "Edg/" in value or "EdgiOS/" in value or "EdgA/" in value:
        browser = "Microsoft Edge"
    elif "OPR/" in value or "Opera/" in value:
        browser = "Opera"
    elif "CriOS/" in value or "Chrome/" in value:
        browser = "Google Chrome"
    elif "FxiOS/" in value or "Firefox/" in value:
        browser = "Mozilla Firefox"
    elif "Safari/" in value and "Version/" in value:
        browser = "Safari"
    else:
        browser = None

    if "Windows" in value:
        operating_system = "Windows"
    elif "Android" in value:
        operating_system = "Android"
    elif "iPhone" in value:
        operating_system = "iOS"
    elif "iPad" in value:
        operating_system = "iPadOS"
    elif "Macintosh" in value or "Mac OS X" in value:
        operating_system = "macOS"
    elif "CrOS" in value:
        operating_system = "ChromeOS"
    elif "Linux" in value:
        operating_system = "Linux"
    else:
        operating_system = None

    if "iPad" in value or "Tablet" in value:
        device_type = "Tablet"
    elif "Mobile" in value or "iPhone" in value:
        device_type = "Mobile"
    elif "Android" in value:
        device_type = "Tablet"
    elif browser is not None or operating_system is not None:
        device_type = "Desktop"
    else:
        device_type = None

    return ClientMetadata(
        browser=browser,
        operating_system=operating_system,
        device_type=device_type,
    )
