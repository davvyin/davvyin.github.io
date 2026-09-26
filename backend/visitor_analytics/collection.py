"""Small, first-party page-view collector. Never use an untrusted IP header."""
from ipaddress import ip_address, ip_network
from urllib.parse import urlsplit

from django.conf import settings

PUBLIC_PATHS = {"/", "/about", "/projects", "/technologies", "/contact"}


def client_ip(request):
    try:
        peer = ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None
    trusted = any(peer in ip_network(network) for network in settings.ANALYTICS_TRUSTED_PROXIES)
    if trusted and request.META.get("HTTP_X_REAL_IP"):
        try:
            peer = ip_address(request.META["HTTP_X_REAL_IP"])
        except ValueError:
            return None
    # Normalize IPv4-mapped IPv6 so a single address has a single identity.
    return str(getattr(peer, "ipv4_mapped", None) or peer)


def referrer_host(value, current_host):
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().encode("idna").decode("ascii")
        if parsed.scheme not in {"http", "https"} or len(host) > 253:
            return ""
        if host == urlsplit("//" + current_host).hostname:
            return ""
        return host
    except (ValueError, UnicodeError):
        return ""


def client_labels(user_agent):
    ua = user_agent.lower()
    if any(token in ua for token in ("bot", "crawler", "spider", "headless", "curl/", "wget/")):
        return None
    browser = "Other"
    for tokens, label in [
        (("edg/", "edga/", "edgios/"), "Edge"),
        (("opr/", "opera"), "Opera"),
        (("firefox/", "fxios/"), "Firefox"),
        (("chrome/", "crios/"), "Chrome"),
        (("safari/",), "Safari"),
    ]:
        if any(token in ua for token in tokens):
            browser = label
            break
    device = "Tablet" if "ipad" in ua or ("android" in ua and "mobile" not in ua) else (
        "Mobile" if any(token in ua for token in ("mobile", "iphone")) else "Desktop"
    )
    return browser, device
