from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import PageView


@override_settings(SECURE_SSL_REDIRECT=False, ANALYTICS_ENABLED=True, ANALYTICS_TRUSTED_PROXIES=[])
class CollectionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)

    def send(self, data=None, **headers):
        options = {"HTTP_ORIGIN": "http://testserver", "REMOTE_ADDR": "203.0.113.10",
                   "HTTP_USER_AGENT": "Mozilla/5.0 Chrome/130.0 Safari/537.36", **headers}
        return self.client.post("/api/analytics/pageview/", data=data or {
            "event_id": str(uuid4()), "path": "/projects", "referrer": "https://search.example/results?secret=hidden",
        }, content_type="application/json", **options)

    def test_records_page_view_without_persistent_identity_or_referrer_path(self):
        response = self.send()
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.content, b"")
        self.assertFalse(response.cookies)
        event = PageView.objects.get()
        self.assertEqual((event.ip_address, event.path, event.referrer, event.browser, event.device),
                         ("203.0.113.10", "/projects", "search.example", "Chrome", "Desktop"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_event_id_deduplicates_retries(self):
        data = {"event_id": str(uuid4()), "path": "/about/"}
        self.send(data)
        self.send(data)
        self.assertEqual(PageView.objects.count(), 1)
        self.assertEqual(PageView.objects.get().path, "/about")

    def test_untrusted_headers_cannot_spoof_visitor_ip(self):
        self.send(HTTP_X_REAL_IP="1.1.1.1", HTTP_X_FORWARDED_FOR="2.2.2.2", HTTP_CF_CONNECTING_IP="3.3.3.3")
        self.assertEqual(PageView.objects.get().ip_address, "203.0.113.10")

    @override_settings(ANALYTICS_TRUSTED_PROXIES=["127.0.0.1/32", "::1/128"])
    def test_explicitly_trusted_proxy_accepts_only_one_valid_real_ip(self):
        self.send(REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="2001:db8::1234")
        self.assertEqual(PageView.objects.get().ip_address, "2001:db8::1234")
        self.send(REMOTE_ADDR="::1", HTTP_X_REAL_IP="203.0.113.2, 1.1.1.1")
        self.assertEqual(PageView.objects.count(), 1)
        self.send(REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="::ffff:192.0.2.1")
        self.assertTrue(PageView.objects.filter(ip_address="192.0.2.1").exists())

    def test_rejects_cross_origin_missing_origin_and_non_json(self):
        for origin in ("https://evil.example", "http://testserver.evil.example", "null", ""):
            self.assertEqual(self.send(HTTP_ORIGIN=origin).status_code, 403)
        self.assertEqual(self.client.post("/api/analytics/pageview/", {"path": "/"},
                                         HTTP_ORIGIN="http://testserver").status_code, 415)
        self.assertEqual(self.client.get("/api/analytics/pageview/").status_code, 405)
        self.assertFalse(PageView.objects.exists())

    def test_rejects_private_unknown_and_malformed_payloads(self):
        for path in ("/admin/", "/api/content/", "/static/test.js", "/healthz/", "/unknown", "/?secret=yes", [], None):
            self.assertEqual(self.send({"event_id": str(uuid4()), "path": path}).status_code, 400)
        for data in ([1], {"event_id": "invalid", "path": "/"}, {"event_id": str(uuid4()), "path": "/", "referrer": []}):
            self.assertEqual(self.send(data).status_code, 400)
        response = self.client.post("/api/analytics/pageview/", "{", content_type="application/json",
                                    HTTP_ORIGIN="http://testserver")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.send({"event_id": str(uuid4()), "path": "/", "extra": "x" * 3000}).status_code, 413)
        self.assertFalse(PageView.objects.exists())

    def test_excludes_staff_privacy_signals_known_bots_and_invalid_ips(self):
        for headers in ({"HTTP_DNT": "1"}, {"HTTP_SEC_GPC": "1"}, {"HTTP_USER_AGENT": "Googlebot"}, {"REMOTE_ADDR": "invalid"}):
            self.assertEqual(self.send(**headers).status_code, 204)
        staff = get_user_model().objects.create_user("staff-collector", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.send().status_code, 204)
        self.assertFalse(PageView.objects.exists())

    @override_settings(ANALYTICS_ENABLED=False)
    def test_can_disable_collection(self):
        self.assertEqual(self.send().status_code, 204)
        self.assertFalse(PageView.objects.exists())

    def test_rate_limit_bounds_writes_and_does_not_block_other_ips(self):
        for _ in range(60):
            self.assertEqual(self.send().status_code, 204)
        self.assertEqual(self.send().status_code, 429)
        self.assertEqual(self.send(REMOTE_ADDR="203.0.113.11").status_code, 204)
        self.assertEqual(PageView.objects.count(), 61)

    def test_database_failure_does_not_expose_details(self):
        with patch("visitor_analytics.views.PageView.objects.get_or_create", side_effect=DatabaseError("secret detail")):
            response = self.send()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b"secret", response.content)


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class DashboardTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model().objects
        cls.admin = users.create_superuser("analytics-admin", "admin@example.com", "test-only-password")
        cls.staff = users.create_user("analytics-staff", is_staff=True)
        cls.reader = users.create_user("analytics-reader")
        cls.now = datetime(2026, 9, 26, 12, tzinfo=dt_timezone.utc)
        for ip, path, age in [("203.0.113.1", "/", 0), ("203.0.113.1", "/projects", 1), ("2001:db8::1", "/", 2)]:
            PageView.objects.create(event_id=uuid4(), ip_address=ip, path=path, occurred_at=cls.now - timedelta(days=age),
                                    referrer="search.example", browser="Safari", device="Mobile")
        PageView.objects.create(event_id=uuid4(), ip_address="192.0.2.99", path="/", occurred_at=cls.now - timedelta(days=100),
                                browser="Other", device="Desktop")

    def dashboard(self, query=""):
        with patch("visitor_analytics.views.timezone.now", return_value=self.now):
            return self.client.get("/admin/analytics/" + query)

    def test_requires_active_staff_superuser_and_never_caches_private_data(self):
        response = self.dashboard()
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        for user in (self.staff, self.reader):
            self.client.force_login(user)
            response = self.dashboard()
            self.assertEqual(response.status_code, 403)
            self.assertNotContains(response, "203.0.113.1", status_code=403)
        self.client.force_login(self.admin)
        response = self.dashboard()
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response["Cache-Control"])
        self.admin.is_superuser = False
        self.admin.save()
        self.assertEqual(self.dashboard().status_code, 403)
        self.admin.is_active = False
        self.admin.save()
        self.assertEqual(self.dashboard().status_code, 302)

    def test_dashboard_counts_distinct_ips_instead_of_summing_daily_totals(self):
        self.client.force_login(self.admin)
        response = self.dashboard()
        self.assertEqual(response.context["totals"], {"views": 3, "unique_ips": 2})
        self.assertEqual(response.context["active_ips"], 1)
        self.assertEqual(len(response.context["chart"]), 30)
        self.assertNotContains(response, "192.0.2.99")
        self.assertContains(response, "2001:db8::1")
        self.assertEqual(response.context["ip_page"].paginator.count, 2)

    def test_filters_all_panels_by_ip_and_date_and_handles_invalid_filters(self):
        self.client.force_login(self.admin)
        response = self.dashboard("?days=7&ip=203.0.113.1")
        self.assertEqual(response.context["totals"], {"views": 2, "unique_ips": 1})
        self.assertEqual(len(response.context["recent"]), 2)
        self.assertEqual(self.dashboard("?days=1").context["totals"]["views"], 1)
        self.assertContains(self.dashboard("?ip=invalid"), "Enter a complete IPv4 or IPv6 address.")
        self.assertEqual(self.dashboard("?days=999").context["days"], 30)
        self.assertEqual(self.dashboard("?days=bad").context["days"], 30)

    def test_pagination_empty_state_and_escaped_values(self):
        self.client.force_login(self.admin)
        PageView.objects.filter(ip_address="203.0.113.1").update(referrer='<script>alert("x")</script>')
        response = self.dashboard()
        self.assertNotContains(response, '<script>alert("x")</script>')
        self.assertContains(response, "&lt;script&gt;")
        for number in range(30):
            PageView.objects.create(event_id=uuid4(), ip_address=f"198.51.100.{number}", path="/", occurred_at=self.now,
                                    browser="Other", device="Desktop")
        self.assertEqual(len(self.dashboard().context["ip_page"]), 25)
        self.assertEqual(len(self.dashboard("?page=2").context["ip_page"]), 7)
        self.assertEqual(self.dashboard("?page=bad").status_code, 200)
        self.assertContains(self.dashboard("?ip=192.0.2.123"), "No visits in this view yet.")

    def test_new_tab_link_visible_only_to_superusers(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/admin/"), 'href="/admin/analytics/" target="_blank" rel="noopener"')
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get("/admin/"), "/admin/analytics/")

    @override_settings(ANALYTICS_RETENTION_DAYS=90)
    def test_cleanup_only_deletes_expired_rows_and_supports_dry_run(self):
        with patch("visitor_analytics.management.commands.prune_visitor_analytics.timezone.now", return_value=self.now):
            call_command("prune_visitor_analytics", dry_run=True, stdout=StringIO())
            self.assertEqual(PageView.objects.count(), 4)
            call_command("prune_visitor_analytics", stdout=StringIO())
        self.assertEqual(PageView.objects.count(), 3)
        self.assertFalse(PageView.objects.filter(ip_address="192.0.2.99").exists())
