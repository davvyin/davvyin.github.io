# One-command Pi deployments

Run these from the project directory on your Mac:

```sh
npm run deploy:backend
npm run deploy:frontend
npm run deploy:all
```

Choose **one** for the change you want to publish. These commands update the existing native installation at `/srv/portfolio/app`. They work with the copied snapshot already on the Pi; Git on the Pi is not required.

| Command | What it deploys | Preparation |
| --- | --- | --- |
| `deploy:backend` | Django code, templates, migrations, monitoring integration | Local backend tests; update changed Python requirements on Pi; apply pending migrations |
| `deploy:frontend` | Built React `build/` and `src/assets/` | Install locked npm dependencies, frontend tests, production build on Mac |
| `deploy:all` | Both components together | Both sets of tests and build steps; use when API and frontend changes depend on each other |

The normal commands create a database/app/environment backup, run `collectstatic`, restart Gunicorn, and check the site through the private Nginx origin. Django serves the React build, so even a frontend-only update requires a short Gunicorn restart. The Pi does not run Node/npm.

The scripts preserve `.env`, database content, the unselected component, existing Nginx rules, WireGuard settings, and installed systemd units. Admin-only content edits still need no deployment. They do not push Git commits or configure deployment on every GitHub push.

## Fast deployments

For updates without tests or backups, run one of these on your Mac:

```sh
npm run deploy:backend:fast
npm run deploy:frontend:fast
npm run deploy:all:fast
```

These are shortcuts for adding `--fast` to the normal command, for example `npm run deploy:backend -- --fast`.

| Step | Normal | Fast |
| --- | --- | --- |
| Local frontend/backend tests | Run | Skip |
| Database, app, and environment backups | Create | Skip |
| Live admin/asset smoke tests and collector metrics check | Run | Skip |
| Frontend npm install and production build, when selected | Run | Run |
| Changed Python dependencies and pending migrations | Apply | Apply |
| Django configuration checks, `collectstatic`, restart | Run | Run |
| Basic `/healthz/` and collector service status | Check | Check |
| Automatic rollback before migrations | Available | Unavailable after files change |

Fast backend deployments do not need a local `.venv` or frontend build because they do not run local tests. Frontend/all fast deployments still install locked npm dependencies and build the selected source snapshot; they do not upload a potentially stale `build/` from your working directory.

Fast mode does not create temporary smoke-test accounts or new backup directories. It preserves secrets, existing database content, component selection, deployment locking, archive validation, and private admin access. Logs/status are still recorded, with `fast: true`, `backup: null`, and explicit skipped-check flags.

**There is no new backup or automatic rollback in fast mode.** If a failure happens after files change, the worker leaves the app stopped with status `failed-no-backup`. Fix and redeploy, or recover using an earlier backup. Failures before any files change resume the unchanged service.

Preview fast mode without deploying:

```sh
npm run deploy:backend:fast -- --dry-run
```

You can combine it with the normal address options, for example `npm run deploy:all:fast -- --host dawei@10.66.66.1`. Using `--skip-tests` alone is different: it skips only local tests and retains backups and remote smoke tests.

## First use

1. Complete the [native Pi setup](README.md#first-time-installation) if the application is not already installed. These commands update an existing installation; they do not reimage the Pi, create the database, or create your permanent admin account.
2. On the Mac, install Python 3.10+, Node 22/npm, and OpenSSH (`ssh` and `scp`). For backend tests, install the existing backend requirements in the project's `.venv` as described in the [main README](../../README.md#local-development). Backend-only tests also need an existing local `build/`; run `npm run build` once, or use `deploy:all` for the first deployment.
3. Confirm you can SSH to `dawei@raspberrypi.local` and use sudo. SSH and sudo prompt in your terminal as necessary. Passwords are never written to a config file or passed on the command line. SSH connection reuse avoids repeated SSH logins during upload and deployment.
4. On the Pi, `rsync`, `tar`, PostgreSQL client tools, Python, and systemd must be installed. The current Pi already has the application environment; install missing OS tools with apt before deployment.

The default verification origin is `http://10.66.66.1:8080`, which the deployment worker accesses **from the Pi**. Your Mac needs SSH connectivity (LAN or VPN); the smoke test can reach the Pi's own VPN address without routing the Mac's requests through it. Keep the public `/admin/*` block. Using the public domain as the health origin fails the admin-login checks by design.

The database backup supports this native installation's local PostgreSQL peer authentication: Linux user `portfolio` owns the database, and the database name is read from Django's settings. This is not a managed-database or Docker deployment command.

## Preview, custom addresses, and archive-only builds

A dry run prints the scope and planned steps without connecting, building, installing packages, or changing the Pi:

```sh
npm run deploy:backend -- --dry-run
npm run deploy:frontend -- --dry-run
```

Use an IP or SSH config alias if `.local` is unavailable. When away from home, connect WireGuard and SSH to the Pi's VPN address:

```sh
npm run deploy:backend -- --host dawei@10.66.66.1
```

For a different installation or admin origin:

```sh
npm run deploy:all -- --host dawei@192.168.1.132 --health-url http://192.168.1.132
```

Only use that example health URL when it actually serves your admin route; the current Pi uses the private port-8080 origin. You can also set `PI_HOST` and `PI_HEALTH_URL` in your shell. No secrets belong in these variables.

To build/test and produce a release without publishing:

```sh
npm run deploy:all -- --prepare-only /tmp/portfolio-release.tgz
```

The output reports its SHA-256. Use `tar -tzf /tmp/portfolio-release.tgz` to inspect it. Archives contain only selected app files and release metadata, never `.env`, local SQLite databases, caches, `node_modules`, `.venv`, VPN profiles, or unrelated files like `t.json`.

`--python /path/to/venv/bin/python` selects another local backend-test interpreter. `--skip-tests` skips local tests only; it still builds React when selected and runs all remote checks. Leave tests enabled for normal deployments.

## What happens

1. **Snapshot:** copy application source into a temporary directory. Tests/builds run against that snapshot, so later editor changes wait for the next release. Uncommitted application changes are included. Release metadata records the base Git commit, whether the workspace is dirty, selected mode, and whether tests were skipped.
2. **Prepare:** run applicable local tests; build frontend when selected. Backend tests use disposable SQLite, not your local or Pi database. Temporary source/dependency directories are cleaned up afterward.
3. **Upload:** connect over SSH, transfer a scoped archive and deployment worker, and verify the archive's checksum. Archive paths and entry types are checked before extraction.
4. **Preflight:** acquire a Pi-wide deployment lock, validate required files and disk space, and check Django. Concurrent deploys fail instead of overlapping.
5. **Backup:** stop Gunicorn and, for backend updates, the running monitoring collector. Save a PostgreSQL dump and the current app/virtual environments in a private timestamped directory. The dump is checked for readability. Backups are retained; copy them off the Pi and periodically test a full database restore.
6. **Apply:** replace only the selected component, removing its obsolete files. Update Python packages only when requirements changed. Backend deploys inspect the migration graph and apply pending migrations. If Glances is installed, changed monitor requirements are installed in its separate environment; first-time collector provisioning still uses the [monitor guide](../../backend/system_monitor/README.md).
7. **Activate:** collect static files, check Django, restart services, and wait for database health. Run HTTP checks for public routes/assets, missing pages, read-only API behavior, and CSRF-protected admin login using a temporary account that is removed afterward. An already-running collector is checked for CPU/memory data.
8. **Record:** retain deployment status, release checksum, backup path, and command logs on the Pi. Installed service unit or Nginx changes remain deliberate infrastructure updates; this command does not overwrite customized units/proxy rules.

This is a maintenance-window deployment, not zero downtime. Requests may receive 502 while Gunicorn is stopped. Backing up environments and applying migrations can take longer than a simple restart.

## Logs and recovery

Each attempt prints its release ID, backup path, and log path:

```text
/srv/portfolio/releases/RELEASE_ID/deploy.log
/srv/portfolio/releases/RELEASE_ID/status.json
/srv/portfolio/backups/deploy-RELEASE_ID/database.dump
/srv/portfolio/backups/deploy-RELEASE_ID/app-venvs.tgz
/srv/portfolio/last-deployment.json
```

Use sudo to read these files. `last-deployment.json` records the most recent **successful** pipeline deployment; older `/srv/portfolio/deployment.json` records are preserved. Logs and backups may contain private operational details and must stay private. No automatic backup/release deletion is performed.

- **Failure before stopping services:** no application changes occur.
- **Backup failure:** resume the unchanged application.
- **Failure before migrations start:** automatically restore the app/environments, then restart. Failed files remain in the release's `failed/` directory. The database is not overwritten.
- **Failure after migrations start:** leave the application stopped and mark `needs-recovery`. Schema changes or partial migrations may be incompatible with old code, so the script never silently restores an old database or starts old code against it. Follow the [restore procedure](README.md#recover-from-a-failed-update), using this release's `database.dump` and `app-venvs.tgz` filenames. Fix forward or restore a matching database into a separate database and update `.env` deliberately.

After a network interruption, reconnect and inspect the release's status/log and `systemctl status portfolio portfolio-monitor` before retrying. The worker ignores SSH hangup, but power loss, OS termination, or a failed recovery command can still require manual recovery. The deployment lock prevents overlapping live workers.

For diagnostics on the Pi:

```sh
sudo cat /srv/portfolio/last-deployment.json
sudo systemctl status portfolio portfolio-monitor --no-pager
sudo journalctl -u portfolio -n 100 --no-pager
```

The pipeline reuses the existing smoke test, which expects the initial site profile (ID 1) and working site-relative images. If you intentionally change these assumptions, update the smoke test with that application change.

Run the deployment-tool regression tests locally with `npm run test:deploy`. They check component isolation, secret exclusion, archive traversal/link rejection, and recovery boundaries. CI runs them too.

## Verified deployment

On 2026-09-26 (UTC), `npm run deploy:all` successfully deployed release `20260926T035440Z-8d70e6` to the existing Pi, using a workspace snapshot based on `f0b67452e142`. The run passed 7 frontend tests and 35 backend tests, built React locally, backed up the app/database/environments, applied both components, and passed the live smoke test through `http://10.66.66.1:8080`. The collector returned CPU and memory data. The deployment tool's 9 regression tests also pass locally.

Backup: `/srv/portfolio/backups/deploy-20260926T035440Z-8d70e6`. Log: `/srv/portfolio/releases/20260926T035440Z-8d70e6/deploy.log`. Public `/healthz/` returned `{"status":"ok"}` afterward; the public monitoring page and API both remained 404. Source edits made after the snapshot were not included in that deployment.
