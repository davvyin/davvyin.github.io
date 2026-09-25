from http.client import HTTPException
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from .views import API_PATHS, MAX_RESPONSE_BYTES

BASE = "/admin/system/"
DASHBOARD = BASE + "dashboard/"


class MonitorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.admin = users.objects.create_superuser("monitor-admin", password="test-only-password")
        cls.staff = users.objects.create_user("editor", is_staff=True)
        cls.reader = users.objects.create_user("reader")
        cls.inactive = users.objects.create_superuser("inactive", password="test-only-password", is_active=False)

    def setUp(self):
        self.patcher = patch("system_monitor.views.HTTPConnection")
        self.connection_class = self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.connection = self.connection_class.return_value
        self.upstream = self.connection.getresponse.return_value
        self.upstream.status = 200
        self.upstream.read.return_value = b'{"cpu":{"total":12.5}}'
        self.upstream.getheader.return_value = "application/json"

    def test_every_resource_requires_login_before_contacting_collector(self):
        for path in [BASE, DASHBOARD, DASHBOARD + "static/glances.js", DASHBOARD + "api/4/all"]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin/login/?next=", response.url)
            self.assertIn("no-store", response["Cache-Control"])
        self.connection_class.assert_not_called()

    def test_staff_and_regular_users_cannot_read_metrics_or_assets(self):
        for user in [self.staff, self.reader]:
            self.client.force_login(user)
            for path in [BASE, DASHBOARD, DASHBOARD + "api/4/all", DASHBOARD + "static/glances.js"]:
                self.assertEqual(self.client.get(path).status_code, 403)
        self.connection_class.assert_not_called()

    def test_inactive_admin_cannot_read_metrics(self):
        self.client.force_login(self.inactive)
        self.assertEqual(self.client.get(DASHBOARD + "api/4/all").status_code, 302)
        self.connection_class.assert_not_called()

    def test_admin_without_staff_flag_is_denied(self):
        self.admin.is_staff = False
        self.admin.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(BASE).status_code, 403)

    def test_admin_page_and_navigation(self):
        self.client.force_login(self.admin)
        page = self.client.get(BASE)
        self.assertContains(page, 'title="Glances live system monitoring dashboard"')
        self.assertContains(page, f'src="{DASHBOARD}"')
        self.assertContains(self.client.get("/admin/"), BASE)
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get("/admin/"), BASE)

    def test_metrics_assets_and_html_are_proxied_with_no_store(self):
        self.client.force_login(self.admin)
        for path in ["", "static/glances.js", "static/favicon.ico", *API_PATHS]:
            response = self.client.get(DASHBOARD + path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.content, self.upstream.read.return_value)
            self.assertIn("no-store", response["Cache-Control"])
            self.assertEqual(response["X-Frame-Options"], "SAMEORIGIN")
            self.connection_class.assert_called_with("127.0.0.1", 61208, timeout=3)
            self.connection.request.assert_called_with(
                "GET", DASHBOARD + path, headers={"Accept-Encoding": "identity"}
            )
            self.connection.close.assert_called()

    def test_credentials_and_user_controlled_target_are_not_forwarded(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            DASHBOARD + "api/4/all?url=http://example.com&token=secret",
            HTTP_AUTHORIZATION="Bearer private", HTTP_X_FORWARDED_HOST="example.com",
        )
        self.assertEqual(response.status_code, 200)
        self.connection.request.assert_called_once_with(
            "GET", DASHBOARD + "api/4/all", headers={"Accept-Encoding": "identity"}
        )
        for header in ["Set-Cookie", "Access-Control-Allow-Origin", "Location"]:
            self.assertNotIn(header, response)

    def test_logout_or_revocation_takes_effect_on_next_poll(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(DASHBOARD + "api/4/all").status_code, 200)
        self.admin.is_superuser = False
        self.admin.save()
        self.assertEqual(self.client.get(DASHBOARD + "api/4/all").status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(DASHBOARD + "api/4/all").status_code, 302)
        self.assertEqual(self.connection.request.call_count, 1)

    def test_mutations_are_rejected(self):
        self.client.force_login(self.admin)
        for method in ["post", "put", "patch", "delete", "options"]:
            response = getattr(self.client, method)(DASHBOARD + "api/4/events/clear/all")
            self.assertEqual(response.status_code, 405)
        self.connection_class.assert_not_called()

    def test_non_ui_endpoints_and_traversal_are_not_forwarded(self):
        self.client.force_login(self.admin)
        for path in [
            "api/4/serverslist", "api/4/events/clear/all", "docs", "http://example.com",
            "static/../api/4/all", "static/%2e%2e/api/4/all", "static/%252e%252e/secret",
            "static//file", "static/./file", "static/file%0d%0aHost:evil",
        ]:
            self.assertEqual(self.client.get(DASHBOARD + path).status_code, 404, path)
        self.connection_class.assert_not_called()

    def test_unavailable_collector_has_friendly_page_and_json(self):
        self.client.force_login(self.admin)
        for error in [ConnectionRefusedError(), TimeoutError(), HTTPException()]:
            self.connection.request.side_effect = error
            self.assertContains(self.client.get(DASHBOARD), "Monitoring is not available yet", status_code=503)
            response = self.client.get(DASHBOARD + "api/4/all")
            self.assertEqual(response.status_code, 503)
            self.assertIn("error", response.json())
            self.assertIn("no-store", response["Cache-Control"])
            self.connection.close.assert_called()

    def test_upstream_redirects_and_errors_are_not_relayed(self):
        self.client.force_login(self.admin)
        for status in [301, 302, 307, 401, 500]:
            self.upstream.status = status
            response = self.client.get(DASHBOARD)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("Location", response)

    def test_missing_assets_keep_404(self):
        self.client.force_login(self.admin)
        self.upstream.status = 404
        self.assertEqual(self.client.get(DASHBOARD + "static/missing.js").status_code, 404)

    def test_oversized_response_is_bounded(self):
        self.client.force_login(self.admin)
        self.upstream.read.return_value = b"x" * (MAX_RESPONSE_BYTES + 1)
        self.assertEqual(self.client.get(DASHBOARD).status_code, 503)
        self.upstream.read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)

    def test_head_has_no_body(self):
        self.client.force_login(self.admin)
        response = self.client.head(DASHBOARD + "api/4/all")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")
