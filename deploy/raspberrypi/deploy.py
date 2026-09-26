#!/usr/bin/env python3
"""Build a scoped release locally and apply it to the existing native Pi app."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parents[2]
EXCLUDED = {"__pycache__", "staticfiles", "node_modules", ".git", ".venv"}


def excluded(name):
    return name in EXCLUDED or name.startswith(".env") or ".sqlite3" in name or name.endswith((".pyc", ".pyo"))


def copy_tree(source, destination):
    # Refuse symlinks rather than silently packaging files outside the workspace.
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Remove the symlink from deployment source: {path}")
    shutil.copytree(source, destination, dirs_exist_ok=True,
                    ignore=lambda _path, names: [name for name in names if excluded(name)])


def run(command, **kwargs):
    print("+ " + shlex.join([str(part) for part in command]), flush=True)
    return subprocess.run(command, check=True, **kwargs)


def payload_paths(mode):
    paths = ["release.json", "deploy/raspberrypi/smoke_test.py"]
    if mode in {"backend", "all"}:
        paths.append("backend")
    if mode in {"frontend", "all"}:
        paths.extend(["build", "src/assets"])
    return paths


def make_archive(stage, destination, mode):
    def clean(member):
        if any(excluded(part) for part in Path(member.name).parts):
            return None
        if not (member.isfile() or member.isdir()):
            raise ValueError(f"Unsupported archive entry: {member.name}")
        member.uid = member.gid = 0
        member.uname = member.gname = ""
        member.mode = 0o755 if member.isdir() else 0o644
        return member
    with tarfile.open(destination, "w:gz") as archive:
        for name in payload_paths(mode):
            archive.add(stage / name, arcname=name, filter=clean)


def prepare(args, work):
    skip_tests = args.skip_tests or args.fast
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=REPO, text=True).strip())
    stage = work / "source"
    stage.mkdir()
    # Snapshot source before testing/building: edits made afterward are next release.
    if args.mode != "backend" or not skip_tests:
        copy_tree(REPO / "src", stage / "src")
    if args.mode in {"backend", "all"}:
        copy_tree(REPO / "backend", stage / "backend")
    if args.mode in {"frontend", "all"}:
        copy_tree(REPO / "public", stage / "public")
        for name in ["package.json", "package-lock.json", "tailwind.config.js", "postcss.config.js"]:
            shutil.copy2(REPO / name, stage / name)
        env = dict(os.environ, CI="true", GENERATE_SOURCEMAP="false")
        run(["npm", "ci", "--no-audit", "--no-fund"], cwd=stage, env=env)
        if not skip_tests:
            run(["npm", "test", "--", "--watchAll=false", "--runInBand"], cwd=stage, env=env)
        run(["npm", "run", "build"], cwd=stage, env=env)
    elif not skip_tests:
        if not (REPO / "build/index.html").is_file():
            raise ValueError("Backend tests need an existing local build. Run npm run build once, or use deploy:all.")
        copy_tree(REPO / "build", stage / "build")
    if args.mode in {"backend", "all"} and not skip_tests:
        # Keep the venv symlink path: resolving it would select the base Python.
        python = Path(args.python).expanduser().absolute()
        if not python.is_file():
            raise ValueError("Install backend dependencies in .venv first, or pass --python /path/to/python.")
        env = dict(os.environ, DJANGO_DEBUG="true", DATABASE_URL="sqlite:///:memory:",
                   DJANGO_SECRET_KEY="disposable-deployment-test-key", DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1",
                   DJANGO_SECURE_SSL_REDIRECT="false", DJANGO_SESSION_COOKIE_SECURE="false",
                   DJANGO_CSRF_COOKIE_SECURE="false", DJANGO_SECURE_HSTS_SECONDS="0", DJANGO_TRUST_PROXY="false")
        for command in [["collectstatic", "--noinput"], ["makemigrations", "--check", "--dry-run"], ["test"]]:
            run([str(python), "manage.py", *command], cwd=stage / "backend", env=env)
    (stage / "deploy/raspberrypi").mkdir(parents=True)
    shutil.copy2(REPO / "deploy/raspberrypi/smoke_test.py", stage / "deploy/raspberrypi/smoke_test.py")
    release = {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + secrets.token_hex(3),
               "mode": args.mode, "revision": revision, "workspace_dirty": dirty,
               "tests_skipped": skip_tests, "fast": args.fast}
    (stage / "release.json").write_text(json.dumps(release, indent=2) + "\n")
    archive = work / "release.tgz"
    make_archive(stage, archive, args.mode)
    return archive, release


def deploy(args, work, archive):
    control = str(work / "ssh")
    options = ["-o", f"ControlPath={control}", "-o", "ControlMaster=auto", "-o", "ControlPersist=600",
               "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=4"]
    ssh = ["ssh", *options]
    try:
        run([*ssh, args.host, "true"])
        upload = subprocess.check_output([*ssh, args.host, "mktemp -d /tmp/portfolio-upload.XXXXXXXX"], text=True).strip()
        if not re.fullmatch(r"/tmp/portfolio-upload\.[A-Za-z0-9]+", upload):
            raise ValueError("Unexpected remote staging directory")
        run(["scp", *options, str(archive), str(REPO / "deploy/raspberrypi/remote_deploy.py"), f"{args.host}:{upload}/"])
        digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        command = shlex.join(["sudo", "python3", upload + "/remote_deploy.py", upload + "/release.tgz", digest, args.health_url])
        run([*ssh, "-tt", args.host, command])
        # Uploads contain no secrets. Remove only this uniquely created directory.
        run([*ssh, args.host, shlex.join(["rm", "-rf", "--", upload])])
    finally:
        subprocess.run(["ssh", "-S", control, "-O", "exit", args.host], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["backend", "frontend", "all"])
    parser.add_argument("--host", default=os.getenv("PI_HOST", "dawei@raspberrypi.local"))
    parser.add_argument("--health-url", default=os.getenv("PI_HEALTH_URL", "http://10.66.66.1:8080"),
                        help="Admin-capable origin reachable from the Pi, not the public admin-blocked domain")
    parser.add_argument("--python", default=str(REPO / ".venv/bin/python"), help="Local Python with backend dependencies")
    parser.add_argument("--skip-tests", action="store_true", help="Skip local tests only; builds and remote checks still run")
    parser.add_argument("--fast", action="store_true", help="Skip local tests, Pi backups, and live smoke tests; keep build, migrations, restart, and basic health check")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without building, uploading, or changing the Pi")
    parser.add_argument("--prepare-only", type=Path, metavar="ARCHIVE", help="Build/test and save an archive without SSH")
    args = parser.parse_args()
    origin = urlsplit(args.health_url)
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.@-]*", args.host):
        parser.error("Use user@hostname or an SSH config alias for --host")
    if origin.scheme not in {"http", "https"} or not origin.hostname or origin.username or origin.password or origin.query or origin.fragment or origin.path not in {"", "/"}:
        parser.error("--health-url must be an HTTP(S) origin without credentials, path, or query")
    args.health_url = args.health_url.rstrip("/")
    print(f"Deploy {args.mode} to {args.host}; verify through {args.health_url}", flush=True)
    print("Payload: " + ", ".join(payload_paths(args.mode)), flush=True)
    if args.fast:
        print("Fast mode: no tests or backups; no automatic rollback after files change.", flush=True)
    if args.dry_run:
        if args.fast:
            print("Plan: snapshot → frontend build if selected → SSH upload → lock → scoped update/migrations → collectstatic → restart → /healthz/")
        else:
            print("Plan: snapshot → local tests/build → SSH upload → lock → backup → scoped update → collectstatic → restart → HTTP/admin checks")
        print("Preserve: Pi .env, database content, unselected app component, Nginx, WireGuard, and installed service units.")
        return
    with tempfile.TemporaryDirectory(prefix="pi-deploy-", dir="/tmp") as directory:
        work = Path(directory)
        archive, release = prepare(args, work)
        print(f"Prepared {release['id']} (Git {release['revision'][:12]}, dirty={release['workspace_dirty']})", flush=True)
        if args.prepare_only:
            destination = args.prepare_only.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(archive, destination)
            print(f"Archive: {destination}\nSHA-256: {hashlib.sha256(archive.read_bytes()).hexdigest()}")
        else:
            deploy(args, work, archive)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        sys.exit(1)
