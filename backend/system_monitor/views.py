"""Keep Glances HTML, assets, and metrics behind the Django admin session.

The upstream is deliberately fixed to loopback. Never accept a target URL or
forward session cookies, authorization headers, redirects, or CORS headers.
"""

from http.client import HTTPConnection, HTTPException
import logging
import re

from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_safe
from portfolio.access import admin_tool_required

logger = logging.getLogger(__name__)
UPSTREAM_PREFIX = "/admin/system/dashboard/"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
# These are the read endpoints used by the pinned Glances Web UI. Do not expose
# the collector's mutation endpoints, server discovery, or arbitrary proxy paths.
API_PATHS = {
    "api/4/all", "api/4/all/views", "api/4/all/limits",
    "api/4/args", "api/4/config", "api/4/help",
}
ASSET_PATH = re.compile(r"static/[a-zA-Z0-9_./-]+\Z")


@never_cache
@admin_tool_required("portfolio.view_system_health")
@require_safe
def index(request):
    context = {**admin.site.each_context(request), "title": "System health"}
    return render(request, "system_monitor/index.html", context)


def unavailable(request, path):
    if path.startswith("api/"):
        return JsonResponse({"error": "System monitoring is unavailable. Please retry shortly."}, status=503)
    return render(request, "system_monitor/unavailable.html", status=503)


@never_cache
@admin_tool_required("portfolio.view_system_health")
@require_safe
@xframe_options_sameorigin
def dashboard(request, path=""):
    # Reject traversal (including repeated encoding), absolute URLs, and control
    # characters before constructing a request to the fixed collector.
    if path and path not in API_PATHS:
        if not ASSET_PATH.fullmatch(path) or any(part in {".", "..", ""} for part in path.split("/")):
            return HttpResponse(status=404)

    connection = HTTPConnection("127.0.0.1", 61208, timeout=3)
    try:
        # The UI needs no query parameters or incoming headers. Always fetch GET
        # because some Glances API routes do not implement HEAD.
        connection.request("GET", UPSTREAM_PREFIX + path, headers={"Accept-Encoding": "identity"})
        upstream = connection.getresponse()
        if upstream.status not in {200, 404}:
            return unavailable(request, path)
        body = upstream.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            logger.warning("Glances response exceeded the monitoring proxy size limit")
            return unavailable(request, path)
        return HttpResponse(
            body if request.method == "GET" else b"",
            status=upstream.status,
            content_type=upstream.getheader("Content-Type", "application/octet-stream"),
        )
    except (OSError, HTTPException):
        logger.warning("Local Glances service unavailable")
        return unavailable(request, path)
    finally:
        connection.close()
