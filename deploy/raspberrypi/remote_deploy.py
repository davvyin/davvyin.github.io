#!/usr/bin/env python3
"""Root-side deployment worker. Invoked by deploy.py, not a public service."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
import urllib.request

ROOT = Path("/srv/portfolio")
APP = ROOT / "app"
VENV = ROOT / "venv"


def validate_members(archive):
    members = archive.getmembers()
    for entry in members:
        path = PurePosixPath(entry.name)
        allowed = (entry.name == "release.json" or path.parts[:1] in {("backend",), ("build",)}
                   or path.parts[:2] == ("src", "assets") or entry.name == "deploy/raspberrypi/smoke_test.py")
        if not allowed or path.is_absolute() or ".." in path.parts or not (entry.isfile() or entry.isdir()):
            raise ValueError(f"Unsafe release entry: {entry.name}")
        if any(part.startswith(".env") or ".sqlite3" in part or part in {"staticfiles", "__pycache__", ".git"} for part in path.parts):
            raise ValueError(f"Local-only file in release: {entry.name}")
    return members


def rollback_policy(migrations_started):
    return "manual" if migrations_started else "automatic"


class Deployment:
    def __init__(self, directory, release, origin):
        self.directory = directory
        self.release = release
        self.fast = release.get("fast", False)
        self.origin = origin
        self.backup = ROOT / "backups" / ("deploy-" + release["id"])
        self.log_file = (directory / "deploy.log").open("a", buffering=1)
        self.stopped = False
        self.backed_up = False
        self.migrations_started = False
        self.monitor_active = False
        self.modified = False

    def log(self, message):
        self.log_file.write(message + "\n")
        try:
            print(message, flush=True)
        except (BrokenPipeError, OSError):
            pass

    def run(self, command, *, app_user=False, check=True, capture=False):
        if app_user:
            command = ["sudo", "-u", "portfolio", *map(str, command)]
        self.log("Running: " + " ".join(map(str, command)))
        result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE if capture else self.log_file,
                                stderr=self.log_file, text=True)
        if check and result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}); see {self.directory / 'deploy.log'}")
        return result

    def manage(self, *args, **kwargs):
        return self.run([VENV / "bin/python", APP / "backend/manage.py", *args], app_user=True, **kwargs)

    def status(self, value, **extra):
        record = {**self.release, "status": value, "updated_at": datetime.now(timezone.utc).isoformat(),
                  "backup": None if self.fast else str(self.backup), "backups_skipped": self.fast,
                  "smoke_tests_skipped": self.fast, "migrations_started": self.migrations_started, **extra}
        (self.directory / "status.json").write_text(json.dumps(record, indent=2) + "\n")

    def update(self):
        self.status("preflight")
        source = self.directory / "payload"
        required = ["deploy/raspberrypi/smoke_test.py"]
        if self.release["mode"] != "frontend":
            required.extend(["backend/manage.py", "backend/requirements.txt"])
        if self.release["mode"] != "backend":
            required.extend(["build/index.html", "build/asset-manifest.json"])
        for name in required:
            if not (source / name).is_file():
                raise RuntimeError(f"Incomplete release: {name}")
        if self.release["mode"] != "backend" and not (source / "src/assets").is_dir():
            raise RuntimeError("Incomplete release: src/assets")
        self.manage("check")
        self.monitor_active = self.run(["systemctl", "is-active", "--quiet", "portfolio-monitor"], check=False).returncode == 0
        names = ["app", "venv"]
        if self.release["mode"] != "frontend" and (ROOT / "monitor-venv").exists():
            names.append("monitor-venv")
        if not self.fast:
            needed = sum(p.stat().st_size for name in names for p in (ROOT / name).rglob("*") if p.is_file())
            if shutil.disk_usage(ROOT).free < needed * 2 + 200 * 1024 * 1024:
                raise RuntimeError("Insufficient disk space for backup and recovery copies")
            self.backup.mkdir(mode=0o700)
            self.log(f"Backup: {self.backup}")
        else:
            self.log("Fast mode: skipping backups and smoke tests; basic health check remains enabled.")
        self.run(["systemctl", "stop", "portfolio"])
        self.stopped = True
        if self.monitor_active and self.release["mode"] != "frontend":
            self.run(["systemctl", "stop", "portfolio-monitor"])
        if not self.fast:
            # Read only the database name, never print or pass the credential URL.
            name = self.manage("shell", "-c", "from django.conf import settings; print(settings.DATABASES['default']['NAME'])", capture=True).stdout.strip().splitlines()[-1]
            if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
                raise RuntimeError("Expected native local PostgreSQL database with a simple name")
            # This pipeline targets the existing local peer-authenticated Pi database.
            with (self.backup / "database.dump").open("wb") as dump:
                subprocess.run(["sudo", "-u", "portfolio", "pg_dump", "-Fc", "-d", name], stdout=dump, stderr=self.log_file, check=True)
            self.run(["pg_restore", "--list", self.backup / "database.dump"])
            self.run(["tar", "-czf", self.backup / "app-venvs.tgz", "-C", ROOT, *names])
            self.backed_up = True
        self.status("applying")
        source = self.directory / "payload"
        if self.release["mode"] != "frontend":
            old_requirements = (APP / "backend/requirements.txt").read_bytes()
            old_monitor = APP / "backend/system_monitor/requirements.txt"
            old_monitor_requirements = old_monitor.read_bytes() if old_monitor.exists() else None
            self.modified = True
            self.run(["rsync", "-a", "--delete", "--chown=portfolio:portfolio", "--exclude=staticfiles/", "--exclude=*.sqlite3*", str(source / "backend") + "/", str(APP / "backend") + "/"])
            if old_requirements != (APP / "backend/requirements.txt").read_bytes():
                self.run([VENV / "bin/pip", "install", "--disable-pip-version-check", "-r", APP / "backend/requirements.txt"], app_user=True)
            if (ROOT / "monitor-venv").exists() and old_monitor.exists() and old_monitor_requirements != old_monitor.read_bytes():
                self.run([ROOT / "monitor-venv/bin/pip", "install", "--disable-pip-version-check", "-r", old_monitor])
            self.manage("check")
            # Query the migration graph explicitly: a failed preflight is not a
            # reason to assume migrations are needed and start mutating the DB.
            pending = self.manage("shell", "-c", "from django.db import connection; from django.db.migrations.executor import MigrationExecutor; e=MigrationExecutor(connection); print(bool(e.migration_plan(e.loader.graph.leaf_nodes())))", capture=True).stdout.strip().splitlines()[-1]
            if pending not in {"True", "False"}:
                raise RuntimeError("Could not determine pending migrations")
            if pending == "True":
                self.migrations_started = True
                self.status("migrating")
                self.manage("migrate", "--noinput")
        if self.release["mode"] != "backend":
            self.modified = True
            for name in ["build", "src/assets"]:
                (APP / name).mkdir(parents=True, exist_ok=True)
                self.run(["rsync", "-a", "--delete", "--chown=portfolio:portfolio", str(source / name) + "/", str(APP / name) + "/"])
        target = APP / "deploy/raspberrypi/smoke_test.py"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / "deploy/raspberrypi/smoke_test.py", target)
        self.manage("collectstatic", "--noinput")
        self.manage("check")
        self.run(["systemctl", "start", "portfolio"])
        if self.monitor_active and self.release["mode"] != "frontend":
            self.run(["systemctl", "start", "portfolio-monitor"])
        self.status("verifying")
        for attempt in range(30):
            try:
                with urllib.request.urlopen(self.origin + "/healthz/", timeout=3) as response:
                    if json.load(response) == {"status": "ok"}:
                        break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Health check did not become ready")
        if not self.fast:
            self.run([VENV / "bin/python", target, self.origin], app_user=True)
        if self.monitor_active:
            self.run(["systemctl", "is-active", "--quiet", "portfolio-monitor"])
            if not self.fast:
                with urllib.request.urlopen("http://127.0.0.1:61208/admin/system/dashboard/api/4/all", timeout=10) as response:
                    stats = json.load(response)
                    if not stats.get("cpu") or not stats.get("mem"):
                        raise RuntimeError("Monitoring collector returned no CPU/memory metrics")
        self.status("success")
        shutil.copy2(self.directory / "status.json", ROOT / "last-deployment.json")
        self.log(f"Deployment succeeded. Log: {self.directory / 'deploy.log'}")

    def recover(self):
        if not self.stopped:
            self.status("failed-before-stop")
            return
        self.run(["systemctl", "stop", "portfolio"], check=False)
        if self.monitor_active and self.release["mode"] != "frontend":
            self.run(["systemctl", "stop", "portfolio-monitor"], check=False)
        if self.fast and self.modified:
            self.status("failed-no-backup")
            self.log("Fast deployment failed after files changed. App left stopped; no backup was created. Fix and redeploy, or recover from an earlier backup.")
            return
        if rollback_policy(self.migrations_started) == "manual":
            self.status("needs-recovery")
            self.log(f"Migrations may have changed the database. App left stopped. Recover with {self.backup}; do not blindly revert code.")
            return
        if self.backed_up:
            failed = self.directory / "failed"
            failed.mkdir()
            names = ["app", "venv"]
            if self.release["mode"] != "frontend" and (ROOT / "monitor-venv").exists():
                names.append("monitor-venv")
            for name in names:
                (ROOT / name).rename(failed / name)
            self.run(["tar", "-xzf", self.backup / "app-venvs.tgz", "-C", ROOT])
        self.run(["systemctl", "start", "portfolio"])
        if self.monitor_active:
            self.run(["systemctl", "start", "portfolio-monitor"])
        self.status("rolled-back" if self.backed_up else ("failed-before-update-app-resumed" if self.fast else "failed-backup-app-resumed"))
        self.log("Previous application resumed; database was not overwritten.")


def main():
    if os.geteuid() != 0:
        raise RuntimeError("Run the deployment worker through sudo")
    archive_path, digest, origin = sys.argv[1:]
    if hashlib.sha256(Path(archive_path).read_bytes()).hexdigest() != digest:
        raise ValueError("Release checksum mismatch")
    if not (APP / ".env").is_file() or not (VENV / "bin/python").is_file():
        raise RuntimeError("Existing native installation required; see first-time setup")
    for command in ["rsync", "tar", "pg_dump", "pg_restore", "systemctl", "sudo"]:
        if not shutil.which(command):
            raise RuntimeError(f"Required Pi command not found: {command}")
    os.umask(0o077)
    with (ROOT / "deploy.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        signal.signal(signal.SIGHUP, signal.SIG_IGN)
        with tarfile.open(archive_path) as archive:
            members = validate_members(archive)
            release = json.load(archive.extractfile("release.json"))
            if release.get("mode") not in {"backend", "frontend", "all"} or not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{6}", release.get("id", "")):
                raise ValueError("Invalid release metadata")
            if not isinstance(release.get("fast", False), bool):
                raise ValueError("Invalid fast-mode flag")
            directory = ROOT / "releases" / release["id"]
            directory.mkdir(parents=True, mode=0o700)
            source = directory / "payload"
            source.mkdir()
            archive.extractall(source, members=members)
        release["sha256"] = digest
        if not release.get("fast", False):
            (ROOT / "backups").mkdir(mode=0o700, exist_ok=True)
        deployment = Deployment(directory, release, origin.rstrip("/"))
        try:
            deployment.update()
        except BaseException:
            deployment.log("Deployment failed; evaluating recovery.")
            deployment.recover()
            raise
        finally:
            deployment.log_file.close()


if __name__ == "__main__":
    try:
        main()
    except BaseException as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
