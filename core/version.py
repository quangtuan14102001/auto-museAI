"""
Application version and semantic comparison utilities.
"""

APP_VERSION = "1.2.15"


def parse_semver(v: str) -> tuple:
    """Parses 'v1.2.3' or '1.2.3-beta' into a tuple (1, 2, 3) for clean comparison."""
    if not v:
        return (0, 0, 0)
    cleaned = v.strip().lstrip("vV")
    parts = []
    for p in cleaned.split("."):
        digits = ""
        for ch in p:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def is_newer_version(latest_str: str, current_str: str = APP_VERSION) -> bool:
    """Returns True if latest_str is strictly newer than current_str."""
    return parse_semver(latest_str) > parse_semver(current_str)
