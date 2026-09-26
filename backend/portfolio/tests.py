import json
import queue
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError
from django.forms.models import model_to_dict
from django.test import Client, TestCase, override_settings
from .models import Experience, Profile, Project, SiteText, SocialLink, Technology
from .validators import image_url


class ContentTests(TestCase):
    def test_initial_content_matches_original_site(self):
        response = self.client.get("/api/content/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["personalDetails"]["name"], "Dawei (David) Yin")
        self.assertEqual(len(data["projectDetails"]), 5)
        self.assertEqual(len(data["workDetails"]), 4)
        self.assertEqual(len(data["eduDetails"]), 3)
        self.assertEqual(len(data["technologies"]), 27)
        self.assertEqual(data["projectDetails"][0]["title"], "LingoLeap")
        self.assertEqual(data["contactDetails"]["email"], "dawei.yin at columbia dot edu")
        self.assertEqual(data["siteCopy"]["projects_heading"], "Selected Projects")
        self.assertEqual(len(data["siteCopy"]), 20)
        self.assertNotIn("password", response.content.decode())
        self.assertIn("no-store", response["Cache-Control"])
        for model in [Profile, Project, Experience, SocialLink, Technology]:
            for item in model.objects.all():
                item.full_clean()

    def test_site_copy_edits_appear_on_the_public_api(self):
        SiteText.objects.filter(key="projects_heading").update(text="My work")
        self.assertEqual(self.client.get("/api/content/").json()["siteCopy"]["projects_heading"], "My work")

    def test_site_copy_migration_preserves_edits(self):
        SiteText.objects.filter(key="about_heading").update(text="Hello there")
        call_command("migrate", verbosity=0)
        self.assertEqual(SiteText.objects.get(key="about_heading").text, "Hello there")

    def test_order_visibility_and_empty_collections_are_authoritative(self):
        Project.objects.all().update(is_visible=False)
        visible = Project.objects.create(title="Visible", description="New", order=8)
        first = Project.objects.create(title="First", description="New", order=1)
        Experience.objects.filter(kind="work").update(is_visible=False)
        Technology.objects.all().update(is_visible=False)
        SocialLink.objects.all().update(is_visible=False)
        data = self.client.get("/api/content/").json()
        self.assertEqual([p["id"] for p in data["projectDetails"]], [first.pk, visible.pk])
        self.assertEqual(data["workDetails"], [])
        self.assertEqual(data["technologies"], [])
        self.assertEqual(data["socialMediaUrl"], {})
        self.assertEqual(len(data["eduDetails"]), 3)
        Project.objects.all().delete()
        self.assertEqual(self.client.get("/api/content/").json()["projectDetails"], [])

    def test_public_api_rejects_writes(self):
        before = Project.objects.count()
        for method in ["post", "put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)("/api/content/", data={}).status_code, 405)
        self.assertEqual(Project.objects.count(), before)

    def test_missing_profile_returns_service_unavailable(self):
        Profile.objects.all().delete()
        self.assertEqual(self.client.get("/api/content/").status_code, 503)

    def test_repeated_migrations_preserve_edits_and_deletions(self):
        Profile.objects.filter(pk=1).update(name="Edited name")
        Project.objects.all().delete()
        call_command("migrate", verbosity=0)
        self.assertEqual(Profile.objects.get(pk=1).name, "Edited name")
        self.assertFalse(Project.objects.exists())

    def test_image_url_validation(self):
        for value in ["/static/portfolio/profile.jpg", "https://example.com/photo.jpg"]:
            image_url(value)
        for value in ["javascript:alert(1)", "//example.com/image.png", "/\\example.com/image.png", "data:text/html,test"]:
            with self.assertRaises(ValidationError):
                image_url(value)


class AdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser("admin-test", "admin@example.com", "test-only-password")
        cls.user = get_user_model().objects.create_user("reader", password="test-only-password")
        cls.staff = get_user_model().objects.create_user("staff", password="test-only-password", is_staff=True)

    def test_admin_requires_staff_login(self):
        self.assertRedirects(self.client.get("/admin/"), "/admin/login/?next=/admin/")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get("/admin/").status_code, 302)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get("/admin/portfolio/profile/1/change/").status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/admin/"), "Portfolio administration")

    def test_camera_page_is_limited_to_staff_and_linked_from_admin(self):
        self.assertRedirects(
            self.client.get("/admin/camera/"),
            "/admin/login/?next=/admin/camera/",
        )
        self.client.force_login(self.user)
        self.assertRedirects(
            self.client.get("/admin/camera/"),
            "/admin/login/?next=/admin/camera/",
        )
        self.client.force_login(self.staff)
        self.assertContains(self.client.get("/admin/camera/"), "/admin/camera/stream.mjpg")
        self.assertContains(self.client.get("/admin/"), "Open staff-only live camera view")

    def test_camera_stream_is_staff_only_and_serves_multipart_jpegs(self):
        stream_path = "/admin/camera/stream.mjpg"
        with patch("portfolio.views.start_stream") as start:
            self.assertEqual(self.client.get(stream_path).status_code, 302)
            start.assert_not_called()

        self.client.force_login(self.staff)
        jpeg1 = b"\xff\xd8first-frame\xff\xd9"
        jpeg2 = b"\xff\xd8second-frame\xff\xd9"
        with patch("portfolio.views.start_stream", return_value=(object(), lambda: None)), patch(
            "portfolio.views.multipart_frames", return_value=iter([b"--frame\r\n" + jpeg1, b"--frame\r\n" + jpeg2])
        ), patch("portfolio.views.stop_stream"):
            response = self.client.get(stream_path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "multipart/x-mixed-replace; boundary=frame")
            self.assertEqual(response["X-Accel-Buffering"], "no")
            body = b"".join(response.streaming_content)
            self.assertEqual(body.count(b"--frame\r\n"), 2)
            self.assertIn(jpeg1, body)
            self.assertIn(jpeg2, body)
            response.close()

    def test_camera_stream_reports_missing_camera_tool(self):
        self.client.force_login(self.staff)
        with patch("portfolio.views.start_stream", return_value=(None, None)):
            response = self.client.get("/admin/camera/stream.mjpg")
        self.assertEqual(response.status_code, 503)

    def test_admin_edit_with_csrf_appears_in_public_api(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        url = "/admin/portfolio/profile/1/change/"
        form = client.get(url)
        self.assertEqual(form.status_code, 200)
        data = model_to_dict(Profile.objects.get(pk=1))
        data.update(name="Updated through admin", _save="Save")
        self.assertEqual(client.post(url, data).status_code, 403)
        data["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        response = client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/api/content/").json()["personalDetails"]["name"], "Updated through admin")

    def test_site_copy_is_editable_in_admin_and_updates_live_api(self):
        self.client.force_login(self.admin)
        text = SiteText.objects.get(key="projects_heading")
        response = self.client.post(f"/admin/portfolio/sitetext/{text.pk}/change/", {
            "key": text.key, "text": "My portfolio work", "_save": "Save",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get("/api/content/").json()["siteCopy"]["projects_heading"], "My portfolio work")

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=False,
                       SESSION_COOKIE_SECURE=False, CSRF_COOKIE_SECURE=False)
    def test_lan_admin_login_with_csrf_and_session_cookie(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.cookies["csrftoken"]["secure"])
        response = client.post("/admin/login/?next=/admin/", {
            "username": "admin-test", "password": "test-only-password",
            "csrfmiddlewaretoken": client.cookies["csrftoken"].value,
            "next": "/admin/",
        })
        self.assertEqual(response.status_code, 302)
        self.assertFalse(response.cookies["sessionid"]["secure"])
        self.assertContains(client.get("/admin/"), "Portfolio administration")

    def test_profile_cannot_be_duplicated_or_deleted_from_admin(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/admin/portfolio/profile/add/").status_code, 403)
        self.assertEqual(self.client.post("/admin/portfolio/profile/1/delete/", {"post": "yes"}).status_code, 403)

    def test_admin_rejects_unsafe_project_links(self):
        self.client.force_login(self.admin)
        project = Project.objects.first()
        data = model_to_dict(project)
        data["preview_link"] = "javascript:alert(1)"
        response = self.client.post(f"/admin/portfolio/project/{project.pk}/change/", data)
        self.assertEqual(response.status_code, 200)
        self.assertIn("preview_link", response.context["adminform"].form.errors)
        project.refresh_from_db()
        self.assertNotEqual(project.preview_link, data["preview_link"])


class CameraBroadcastTests(TestCase):
    class Pipe:
        def __init__(self):
            self.chunks = queue.Queue()

        def read(self, size):
            return self.chunks.get()

        def close(self):
            self.chunks.put(b"")

    class Process:
        def __init__(self):
            self.stdout = CameraBroadcastTests.Pipe()
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self):
            self.returncode = -15
            self.stdout.close()

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9
            self.stdout.close()

    def test_two_viewers_share_one_capture_and_receive_each_frame(self):
        from camera.broadcast import _Broadcaster

        broadcaster = _Broadcaster()
        process = self.Process()
        frames = [b"\xff\xd8frame-one\xff\xd9", b"\xff\xd8frame-two\xff\xd9"]
        with patch("camera.broadcast.camera_command", return_value=["rpicam-vid"]), patch(
            "camera.broadcast.subprocess.Popen", return_value=process
        ) as popen:
            first = broadcaster.subscribe()
            second = broadcaster.subscribe()
            self.assertIsNotNone(first)
            self.assertIsNotNone(second)
            self.assertEqual(popen.call_count, 1)

            for expected in frames:
                process.stdout.chunks.put(expected)
                with broadcaster.condition:
                    self.assertTrue(broadcaster.condition.wait_for(
                        lambda: broadcaster.latest_frame == expected,
                        timeout=2,
                    ))
                self.assertEqual(first.next_frame(), expected)
            self.assertEqual(second.next_frame(), expected)

            broadcaster.unsubscribe(first)
            self.assertIsNotNone(broadcaster.process)
            self.assertIsNone(process.returncode)
            broadcaster.unsubscribe(second)
            self.assertEqual(process.returncode, -15)

    def test_slow_viewer_skips_stale_frames(self):
        from camera.broadcast import _Broadcaster

        broadcaster = _Broadcaster()
        process = self.Process()
        old = b"\xff\xd8old\xff\xd9"
        latest = b"\xff\xd8new\xff\xd9"
        with patch("camera.broadcast.camera_command", return_value=["rpicam-vid"]), patch(
            "camera.broadcast.subprocess.Popen", return_value=process
        ):
            subscription = broadcaster.subscribe()
            process.stdout.chunks.put(old + latest)
            with broadcaster.condition:
                self.assertTrue(broadcaster.condition.wait_for(
                    lambda: broadcaster.latest_frame == latest,
                    timeout=2,
                ))
            self.assertEqual(subscription.next_frame(), latest)
            broadcaster.unsubscribe(subscription)


class RoutingTests(TestCase):
    def test_health_checks_database(self):
        self.assertEqual(self.client.get("/healthz/").json(), {"status": "ok"})
        with patch("portfolio.views.connection.cursor", side_effect=DatabaseError):
            response = self.client.get("/healthz/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})

    def test_frontend_deep_links_and_unknown_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text('<div id="root">App</div>')
            with override_settings(FRONTEND_DIR=Path(directory)):
                for path in ["/", "/about", "/projects/", "/contact", "/technologies"]:
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(b'id="root"', b"".join(response.streaming_content))
                    self.assertIn("no-store", response["Cache-Control"])
                for path in ["/api/missing/", "/static/missing.js", "/missing", "/admin/missing/"]:
                    self.assertNotEqual(self.client.get(path).status_code, 200)
        with override_settings(FRONTEND_DIR=Path(directory)):
            self.assertEqual(self.client.get("/").status_code, 503)

    @override_settings(DEBUG=False, SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True,
                       CSRF_COOKIE_SECURE=True, ALLOWED_HOSTS=["testserver"])
    def test_production_routes_and_assets(self):
        self.assertEqual(self.client.get("/api/content/").status_code, 301)
        self.assertEqual(self.client.get("/api/content/", secure=True).status_code, 200)
        # Run npm run build and collectstatic before this integration test.
        self.assertTrue((settings.FRONTEND_DIR / "index.html").exists(), "Build React before testing production assets")
        self.assertTrue((settings.STATIC_ROOT / "staticfiles.json").exists(), "Run collectstatic before testing production assets")
        manifest = json.loads((settings.FRONTEND_DIR / "asset-manifest.json").read_text())
        for path in ["/", "/projects", "/admin/login/", "/favicon/favicon.ico",
                     "/static/admin/css/base.css", "/static/portfolio/profile.jpg",
                     manifest["files"]["main.js"], manifest["files"]["main.css"]]:
            response = self.client.get(path, secure=True)
            self.assertEqual(response.status_code, 200, path)
            if getattr(response, "streaming", False):
                response.close()
        response = self.client.get("/admin/login/", secure=True)
        self.assertTrue(response.cookies["csrftoken"]["secure"])
