from datetime import datetime, time, timedelta, timezone as dt_timezone
from ipaddress import ip_address
import json
import logging
from urllib.parse import urlencode
from uuid import UUID

from django.conf import settings
from django.contrib import admin
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Max, Min
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from portfolio.access import admin_tool_required

from .collection import PUBLIC_PATHS, client_ip, client_labels, referrer_host
from .models import PageView

logger = logging.getLogger(__name__)


@csrf_exempt
@never_cache
@require_POST
def collect(request):
    # Public, write-only telemetry: no cookies are issued and no records returned.
    # A strict Origin check + JSON disallows cross-site forms and browser beacons.
    if request.headers.get("Origin") != f"{request.scheme}://{request.get_host()}":
        return HttpResponse(status=403)
    if request.content_type != "application/json":
        return HttpResponse(status=415)
    try:
        if int(request.META.get("CONTENT_LENGTH") or 0) > 2048 or len(request.body) > 2048:
            return HttpResponse(status=413)
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        path = data.get("path", "")
        if not isinstance(path, str):
            raise ValueError
        path = path.rstrip("/") or "/"
        if path not in PUBLIC_PATHS:
            raise ValueError
        event_id = UUID(str(data.get("event_id", "")))
        referrer = data.get("referrer", "")
        if not isinstance(referrer, str):
            raise ValueError
    except (ValueError, TypeError, UnicodeError):
        return HttpResponse(status=400)
    if (not settings.ANALYTICS_ENABLED or request.user.is_staff
            or request.headers.get("DNT") == "1" or request.headers.get("Sec-GPC") == "1"):
        return HttpResponse(status=204)
    address = client_ip(request)
    labels = client_labels(request.headers.get("User-Agent", "")[:1024])
    if not address or not labels:
        return HttpResponse(status=204)
    # Best-effort per-process bound for the Pi's one-worker deployment. Nginx
    # supplies the authoritative request-rate limit in the deployment snippet.
    minute = int(timezone.now().timestamp()) // 60
    key = f"analytics:{address}:{minute}"
    if not cache.add(key, 1, timeout=120):
        try:
            if cache.incr(key) > 60:
                return HttpResponse(status=429)
        except ValueError:  # Cache eviction between add and incr is harmless.
            cache.set(key, 1, timeout=120)
    try:
        PageView.objects.get_or_create(event_id=event_id, defaults={
            "ip_address": address, "path": path,
            "referrer": referrer_host(referrer, request.get_host()),
            "browser": labels[0], "device": labels[1],
        })
    except DatabaseError:
        # Analytics must never prevent a visitor from using the website.
        logger.warning("Visitor analytics write failed", exc_info=False)
        return HttpResponse(status=503)
    return HttpResponse(status=204)


@never_cache
@admin_tool_required("portfolio.view_visitor_analytics")
@require_GET
def dashboard(request):
    try:
        days = int(request.GET.get("days", "30"))
    except ValueError:
        days = 30
    if days not in {1, 7, 30, 90}:
        days = 30
    now = timezone.now()
    today = now.date()
    start_date = today - timedelta(days=days - 1)
    start = datetime.combine(start_date, time.min, tzinfo=dt_timezone.utc)
    end = datetime.combine(today + timedelta(days=1), time.min, tzinfo=dt_timezone.utc)
    visits = PageView.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
    search = request.GET.get("ip", "").strip()[:45]
    error = ""
    if search:
        try:
            search = str(ip_address(search))
            visits = visits.filter(ip_address=search)
        except ValueError:
            error = "Enter a complete IPv4 or IPv6 address."
            visits = visits.none()
    totals = visits.aggregate(views=Count("id"), unique_ips=Count("ip_address", distinct=True))
    daily = {item["day"]: item for item in visits.annotate(
        day=TruncDate("occurred_at", tzinfo=dt_timezone.utc)
    ).values("day").annotate(views=Count("id"), ips=Count("ip_address", distinct=True))}
    peak = max((item["views"] for item in daily.values()), default=0)
    chart = []
    for offset in range(days):
        day = start_date + timedelta(days=offset)
        item = daily.get(day, {"views": 0, "ips": 0})
        chart.append({"day": day, **item, "height": round(item["views"] / (peak or 1) * 100, 2)})
    addresses = visits.values("ip_address").annotate(
        views=Count("id"), pages=Count("path", distinct=True),
        first_seen=Min("occurred_at"), last_seen=Max("occurred_at"),
    ).order_by("-last_seen", "ip_address")
    page = Paginator(addresses, 25).get_page(request.GET.get("page"))

    def breakdown(field):
        return visits.values(field).annotate(views=Count("id")).order_by("-views", field)[:8]

    context = {
        **admin.site.each_context(request), "title": "Visitor analytics", "days": days,
        "periods": [1, 7, 30, 90], "ip": search, "error": error, "totals": totals,
        "chart": chart, "peak": peak, "start_date": start_date, "end_date": today,
        "active_ips": visits.filter(occurred_at__gte=now - timedelta(minutes=5)).values("ip_address").distinct().count(),
        "pages": breakdown("path"), "referrers": breakdown("referrer"),
        "browsers": breakdown("browser"), "devices": breakdown("device"),
        "ip_page": page, "pagination_query": urlencode({"days": days, "ip": search}),
        "recent": visits.order_by("-occurred_at", "-pk")[:15],
        "enabled": settings.ANALYTICS_ENABLED,
        "proxy_configured": bool(settings.ANALYTICS_TRUSTED_PROXIES),
        "retention_days": settings.ANALYTICS_RETENTION_DAYS,
    }
    return render(request, "visitor_analytics/dashboard.html", context)
