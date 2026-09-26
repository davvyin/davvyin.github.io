from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings


@override_settings(SECURE_SSL_REDIRECT=False, STORAGES={
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class ToolAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = get_user_model().objects.create_superuser("access-owner", password="test-password")
        cls.staff = get_user_model().objects.create_user("access-staff", is_staff=True)
        cls.permissions = {p.codename: p for p in Permission.objects.filter(
            content_type__app_label="portfolio", content_type__model="admintoolaccess")}

    def setUp(self):
        self.client.force_login(self.staff)

    def test_staff_has_no_tools_until_granted_and_grants_are_independent(self):
        paths = {"view_camera": "/admin/camera/", "view_visitor_analytics": "/admin/analytics/",
                 "view_system_health": "/admin/system/"}
        for permission, path in paths.items():
            self.assertEqual(self.client.get(path).status_code, 403)
            self.staff.user_permissions.add(self.permissions[permission])
            self.assertEqual(self.client.get(path).status_code, 200)
            self.assertContains(self.client.get("/admin/"), path)
            for other_permission, other_path in paths.items():
                if other_permission != permission:
                    self.assertEqual(self.client.get(other_path).status_code, 403)
                    self.assertNotContains(self.client.get("/admin/"), other_path)
            self.staff.user_permissions.clear()
            self.assertEqual(self.client.get(path).status_code, 403)

    def test_group_grants_revocation_and_staff_active_flags(self):
        group = Group.objects.create(name="Analytics readers")
        group.permissions.add(self.permissions["view_visitor_analytics"])
        self.staff.groups.add(group)
        self.assertEqual(self.client.get("/admin/analytics/").status_code, 200)
        group.permissions.clear()
        self.assertEqual(self.client.get("/admin/analytics/").status_code, 403)
        self.staff.user_permissions.add(self.permissions["view_visitor_analytics"])
        self.staff.is_staff = False
        self.staff.save()
        self.assertEqual(self.client.get("/admin/analytics/").status_code, 403)
        self.staff.is_staff = True
        self.staff.is_active = False
        self.staff.save()
        self.assertEqual(self.client.get("/admin/analytics/").status_code, 302)

    def test_monitor_assets_and_metrics_require_permission_on_every_request(self):
        self.staff.user_permissions.add(self.permissions["view_system_health"])
        with patch("system_monitor.views.HTTPConnection") as connection:
            upstream = connection.return_value.getresponse.return_value
            upstream.status = 200
            upstream.read.return_value = b"{}"
            upstream.getheader.return_value = "application/json"
            for path in ("api/4/all", "static/glances.js"):
                self.assertEqual(self.client.get("/admin/system/dashboard/" + path).status_code, 200)
            self.staff.user_permissions.clear()
            connection.reset_mock()
            for path in ("api/4/all", "static/glances.js"):
                self.assertEqual(self.client.get("/admin/system/dashboard/" + path).status_code, 403)
            connection.assert_not_called()

    def test_camera_checks_permission_before_opening_and_after_revocation(self):
        with patch("portfolio.views.start_stream") as start:
            self.assertEqual(self.client.get("/admin/camera/stream.mjpg").status_code, 403)
            start.assert_not_called()
        self.staff.user_permissions.add(self.permissions["view_camera"])
        with patch("portfolio.views.start_stream", return_value=(object(), lambda: None)), patch(
            "portfolio.views.multipart_frames", return_value=iter([b"one", b"two", b"three"])
        ), patch("portfolio.views.stop_stream") as stop, patch("portfolio.access.monotonic", side_effect=[10, 16]):
            response = self.client.get("/admin/camera/stream.mjpg")
            frames = iter(response.streaming_content)
            self.assertEqual(next(frames), b"one")
            self.staff.user_permissions.clear()
            with self.assertRaises(StopIteration):
                next(frames)
            self.assertTrue(response.closed)
            stop.assert_called_once()

    def test_camera_closes_after_logout(self):
        self.staff.user_permissions.add(self.permissions["view_camera"])
        with patch("portfolio.views.start_stream", return_value=(object(), lambda: None)), patch(
            "portfolio.views.multipart_frames", return_value=iter([b"one", b"two"])
        ), patch("portfolio.views.stop_stream"), patch("portfolio.access.monotonic", side_effect=[10, 16]):
            response = self.client.get("/admin/camera/stream.mjpg")
            frames = iter(response.streaming_content)
            self.assertEqual(next(frames), b"one")
            self.client.logout()
            with self.assertRaises(StopIteration):
                next(frames)
            self.assertTrue(response.closed)

    def test_only_superusers_can_manage_users_and_groups_even_with_auth_permissions(self):
        self.staff.user_permissions.add(*Permission.objects.filter(content_type__app_label="auth"))
        group = Group.objects.create(name="Editors")
        for path in ("/admin/auth/user/", "/admin/auth/group/", f"/admin/auth/user/{self.staff.pk}/change/",
                     f"/admin/auth/group/{group.pk}/change/", "/admin/auth/user/add/", "/admin/auth/group/add/"):
            self.assertEqual(self.client.get(path).status_code, 403, path)
        response = self.client.post(f"/admin/auth/user/{self.staff.pk}/change/", {"is_superuser": "on"})
        self.assertEqual(response.status_code, 403)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)
        self.client.force_login(self.owner)
        response = self.client.get(f"/admin/auth/user/{self.staff.pk}/change/")
        self.assertContains(response, "Can view visitor analytics (includes IP addresses)")
        self.assertContains(response, "Can view system health")
        self.assertContains(response, "Can view live camera")

    def test_superuser_can_save_staff_permissions_using_existing_admin_form(self):
        self.client.force_login(self.owner)
        response = self.client.post(f"/admin/auth/user/{self.staff.pk}/change/", {
            "username": self.staff.username, "is_active": "on", "is_staff": "on",
            "user_permissions": [self.permissions["view_visitor_analytics"].pk],
            "date_joined_0": self.staff.date_joined.strftime("%Y-%m-%d"),
            "date_joined_1": self.staff.date_joined.strftime("%H:%M:%S"), "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/analytics/").status_code, 200)
        self.assertEqual(self.client.get("/admin/camera/").status_code, 403)
