"""Regression checks for deployment scope, secrets, and recovery boundaries."""
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import deploy
import remote_deploy


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ["backend/manage.py", "backend/config/settings.py", "backend/.env",
                     "backend/db.sqlite3", "backend/staticfiles/old.css", "backend/__pycache__/old.pyc",
                     "build/index.html", "src/assets/photo.jpg", "deploy/raspberrypi/smoke_test.py"]:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("test")
        (self.root / "release.json").write_text(json.dumps({"mode": "backend"}))

    def archive_names(self, mode):
        target = self.root / "release.tgz"
        deploy.make_archive(self.root, target, mode)
        with tarfile.open(target) as archive:
            remote_deploy.validate_members(archive)
            return archive.getnames()

    def test_backend_never_includes_frontend_or_local_secrets(self):
        names = self.archive_names("backend")
        self.assertIn("backend/manage.py", names)
        for forbidden in ["build/index.html", "src/assets/photo.jpg", "backend/.env", "backend/db.sqlite3",
                          "backend/staticfiles/old.css", "backend/__pycache__/old.pyc"]:
            self.assertNotIn(forbidden, names)

    def test_frontend_never_includes_backend(self):
        names = self.archive_names("frontend")
        self.assertIn("build/index.html", names)
        self.assertIn("src/assets/photo.jpg", names)
        self.assertFalse(any(name.startswith("backend") for name in names))

    def test_combined_release_has_both_components(self):
        names = self.archive_names("all")
        self.assertIn("build/index.html", names)
        self.assertIn("backend/manage.py", names)

    def test_links_are_rejected(self):
        (self.root / "backend/link").symlink_to(self.root / "release.json")
        with self.assertRaises(ValueError):
            deploy.make_archive(self.root, self.root / "bad.tgz", "backend")

    def test_fast_backend_preparation_needs_no_local_build_or_test_environment(self):
        work = self.root / "work"
        work.mkdir()
        args = SimpleNamespace(mode="backend", skip_tests=False, fast=True)
        with patch.object(deploy, "REPO", self.root), patch.object(deploy.subprocess, "check_output", return_value="test-revision"), patch.object(deploy, "run") as run:
            archive, release = deploy.prepare(args, work)
        run.assert_not_called()
        self.assertTrue(release["fast"])
        self.assertTrue(release["tests_skipped"])
        self.assertFalse((work / "source/build").exists())
        with tarfile.open(archive) as payload:
            self.assertTrue(json.load(payload.extractfile("release.json"))["fast"])

    def test_malicious_archives_cannot_escape_or_replace_secrets(self):
        for name, kind in [("../../etc/passwd", tarfile.REGTYPE), ("/etc/passwd", tarfile.REGTYPE),
                           ("backend/.env", tarfile.REGTYPE), ("backend/link", tarfile.SYMTYPE),
                           ("backend/hardlink", tarfile.LNKTYPE), ("backend/fifo", tarfile.FIFOTYPE)]:
            with self.subTest(name=name, kind=kind):
                stream = io.BytesIO()
                with tarfile.open(fileobj=stream, mode="w") as archive:
                    member = tarfile.TarInfo(name)
                    member.type = kind
                    member.linkname = "/etc/passwd"
                    archive.addfile(member)
                stream.seek(0)
                with tarfile.open(fileobj=stream) as archive, self.assertRaises(ValueError):
                    remote_deploy.validate_members(archive)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ["app", "venv", "backups", "release"]:
            (self.root / name).mkdir()
        for key, value in {"ROOT": self.root, "APP": self.root / "app", "VENV": self.root / "venv"}.items():
            patcher = patch.object(remote_deploy, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.worker = remote_deploy.Deployment(self.root / "release", {"id": "test", "mode": "backend"}, "http://localhost")
        self.addCleanup(self.worker.log_file.close)

    def test_failure_after_migration_does_not_restore_database_or_start_old_code(self):
        self.worker.stopped = True
        self.worker.backed_up = True
        self.worker.migrations_started = True
        with patch.object(self.worker, "run") as run:
            self.worker.recover()
        self.assertEqual(run.call_args_list[0].args[0], ["systemctl", "stop", "portfolio"])
        self.assertEqual(run.call_count, 1)
        status = json.loads((self.root / "release/status.json").read_text())
        self.assertEqual(status["status"], "needs-recovery")
        self.assertTrue((self.root / "app").exists())

    def test_failed_backup_resumes_unchanged_service(self):
        self.worker.stopped = True
        with patch.object(self.worker, "run") as run:
            self.worker.recover()
        commands = [call.args[0] for call in run.call_args_list]
        self.assertIn(["systemctl", "start", "portfolio"], commands)
        self.assertFalse(any(command[0] == "tar" for command in commands))

    def test_failed_release_restores_matching_files_without_touching_database(self):
        self.worker.backup.mkdir()
        (self.root / "app/version").write_text("working")
        (self.root / "venv/version").write_text("working dependencies")
        with tarfile.open(self.worker.backup / "app-venvs.tgz", "w:gz") as archive:
            for name in ["app", "venv"]:
                archive.add(self.root / name, arcname=name)
        (self.root / "app/version").write_text("broken")
        (self.root / "venv/version").write_text("new dependencies")
        self.worker.stopped = self.worker.backed_up = True
        def execute(command, **_kwargs):
            if command[0] == "tar":
                with tarfile.open(command[2]) as archive:
                    archive.extractall(self.root)
        with patch.object(self.worker, "run", side_effect=execute) as run:
            self.worker.recover()
        self.assertEqual((self.root / "app/version").read_text(), "working")
        self.assertEqual((self.root / "venv/version").read_text(), "working dependencies")
        self.assertEqual((self.root / "release/failed/app/version").read_text(), "broken")
        self.assertFalse(any(call.args[0][0] == "pg_restore" for call in run.call_args_list))

    def test_failure_before_stop_leaves_services_alone(self):
        with patch.object(self.worker, "run") as run:
            self.worker.recover()
        run.assert_not_called()

    def test_fast_failure_after_file_changes_never_claims_to_restore_old_code(self):
        self.worker.fast = True
        self.worker.stopped = self.worker.modified = True
        with patch.object(self.worker, "run") as run:
            self.worker.recover()
        self.assertEqual([call.args[0] for call in run.call_args_list], [["systemctl", "stop", "portfolio"]])
        status = json.loads((self.root / "release/status.json").read_text())
        self.assertEqual(status["status"], "failed-no-backup")
        self.assertIsNone(status["backup"])

    def test_fast_failure_before_file_changes_resumes_unchanged_service(self):
        self.worker.fast = True
        self.worker.stopped = True
        with patch.object(self.worker, "run") as run:
            self.worker.recover()
        self.assertIn(["systemctl", "start", "portfolio"], [call.args[0] for call in run.call_args_list])

    def test_fast_modes_skip_backups_and_smoke_tests_but_keep_required_steps(self):
        source = self.root / "release/payload"
        for base in [source, self.root / "app"]:
            for name in ["backend/manage.py", "backend/requirements.txt", "build/index.html", "build/asset-manifest.json", "src/assets/image.jpg", "deploy/raspberrypi/smoke_test.py"]:
                file = base / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("test")
        for mode in ["backend", "frontend", "all"]:
            with self.subTest(mode=mode):
                self.worker.fast = True
                self.worker.release.update(mode=mode, fast=True)
                self.worker.migrations_started = False
                response = MagicMock()
                response.__enter__.return_value = io.BytesIO(b'{"status":"ok"}')
                with patch.object(self.worker, "run", return_value=SimpleNamespace(returncode=0)) as run, patch.object(self.worker, "manage", return_value=SimpleNamespace(stdout="True")) as manage, patch.object(remote_deploy.urllib.request, "urlopen", return_value=response) as health, patch.object(remote_deploy.shutil, "disk_usage", side_effect=AssertionError("Fast mode must not size backup")), patch.object(remote_deploy.subprocess, "run", side_effect=AssertionError("No direct dump process allowed")):
                    self.worker.update()
                commands = [list(map(str, call.args[0])) for call in run.call_args_list]
                self.assertFalse(any(command[0] in {"tar", "pg_dump", "pg_restore"} for command in commands))
                self.assertFalse(any("smoke_test.py" in part for command in commands for part in command))
                self.assertIn(["systemctl", "start", "portfolio"], commands)
                self.assertIn(("collectstatic", "--noinput"), [call.args for call in manage.call_args_list])
                self.assertEqual(("migrate", "--noinput") in [call.args for call in manage.call_args_list], mode != "frontend")
                health.assert_called_once_with("http://localhost/healthz/", timeout=3)
                self.assertFalse(self.worker.backup.exists())
                status = json.loads((self.root / "release/status.json").read_text())
                self.assertEqual(status["status"], "success")
                self.assertIsNone(status["backup"])
                self.assertTrue(status["smoke_tests_skipped"])


if __name__ == "__main__":
    unittest.main()
