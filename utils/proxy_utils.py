"""
Proxy utilities for parsing and formatting proxy configurations for Playwright.
Supports standard formats:
- ip:port:username:password
- ip:port
- http://username:password@ip:port
- http://ip:port
- socks5://username:password@ip:port
- socks5://ip:port:username:password
- socks5://ip:port
"""

from typing import Optional, Dict
import urllib.parse


def parse_proxy(proxy_str: str) -> Optional[Dict[str, str]]:
    """
    Parses a raw proxy string into a Playwright-compatible proxy dict:
    {
        "server": "http://ip:port",
        "username": "user",
        "password": "pwd"
    }
    Returns None if proxy_str is empty or invalid.
    """
    if not proxy_str:
        return None

    raw = proxy_str.strip()
    if not raw:
        return None

    scheme = "http"
    if raw.startswith("socks5://") or raw.startswith("socks4://") or raw.startswith("http://") or raw.startswith("https://"):
        parsed = urllib.parse.urlparse(raw)
        scheme = parsed.scheme
        host = parsed.hostname
        port = parsed.port
        username = parsed.username
        password = parsed.password

        if not host or not port:
            return None

        result = {"server": f"{scheme}://{host}:{port}"}
        if username:
            result["username"] = username
        if password:
            result["password"] = password
        return result

    # Format without protocol prefix, e.g. ip:port:user:pass or ip:port
    parts = raw.split(":")
    if len(parts) == 2:
        # ip:port
        ip, port = parts[0].strip(), parts[1].strip()
        return {"server": f"{scheme}://{ip}:{port}"}

    elif len(parts) == 4:
        # ip:port:user:pass
        ip, port, user, pwd = parts[0].strip(), parts[1].strip(), parts[2].strip(), parts[3].strip()
        return {
            "server": f"{scheme}://{ip}:{port}",
            "username": user,
            "password": pwd
        }

    return None


def format_proxy_display(proxy_str: str) -> str:
    """
    Formats proxy for display in UI table (hiding sensitive password).
    e.g. 103.142.25.10:8080 (Auth) or 103.142.25.10:8080 or 'Mạng nhà'
    """
    if not proxy_str or not proxy_str.strip():
        return "Mạng nhà"

    parsed = parse_proxy(proxy_str)
    if not parsed:
        return "Lỗi format"

    server = parsed.get("server", "").replace("http://", "").replace("https://", "").replace("socks5://", "")
    has_auth = bool(parsed.get("username"))

    if has_auth:
        return f"{server} (auth)"
    return server
