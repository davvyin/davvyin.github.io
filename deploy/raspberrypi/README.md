# Build and deploy to Raspberry Pi

Build React on your Mac, then run Django, PostgreSQL, Gunicorn, and Nginx as native services on the Pi. This avoids running the memory-intensive JavaScript build on the Pi. Docker is an alternative in the [main README](../../README.md#hosting-with-docker-and-postgresql); use one deployment method.

**Already running the site? Start at [Updating an existing installation](#updating-an-existing-installation).** The recorded `/srv/portfolio/app` installation is a copied snapshot, so `git pull` in another checkout does not update it. First-time setup below is for a fresh installation.

For normal updates, use the [one-command deployment pipeline](COMMANDS.md): `npm run deploy:backend`, `npm run deploy:frontend`, or `npm run deploy:all`. It automates testing/building, SSH upload, backups, migrations, static collection, restart, and verification.

## How the application is built and served

```text
Mac: src/ + public/ + package-lock.json
       │ npm ci; npm run build
       ▼
     build/ (HTML, JavaScript, CSS, images)
       │ package with backend/, assets, and deployment files
       │ scp over SSH
       ▼
Pi: /srv/portfolio/app

LAN browser → Nginx (PI_LAN_IP:80) → Gunicorn (127.0.0.1:8000)
                                        ├─ Django: pages, /api/content/, /admin/
                                        ├─ WhiteNoise: frontend and static assets
                                        └─ PostgreSQL: content, users, sessions
```

- **React 18 + Tailwind:** `npm run build` uses Create React App to produce `build/`. `npm start` is only the development server. Node is needed on the build machine, not the Pi.
- **Django 5.2:** serves public routes, the read-only JSON API, health endpoint, and admin. React fetches `/api/content/` from the same origin.
- **PostgreSQL:** stores editable content and accounts. Migrations create tables and import original content once; later deployments preserve edits. Copying source does not transfer your Mac's SQLite content or passwords.
- **Static assets:** `collectstatic` collects React bundles, Django admin assets, and `src/assets/` into `backend/staticfiles/`. WhiteNoise serves them through Gunicorn; Nginx proxies requests.
- **systemd:** starts Gunicorn at boot as Linux user `portfolio`. The supplied unit uses one worker, four threads, and a 350 MB memory limit. One worker keeps the in-process camera broadcaster singular; four threads allow concurrent streams while leaving capacity for admin requests. Install the Python virtual environment on the Pi; Mac Python packages are not portable to Linux/ARM.
- **Camera:** the optional staff-only `/admin/camera/` page uses `rpicam-vid` on the Pi.

GitHub Pages cannot execute Django or PostgreSQL. Pushing to GitHub alone does not deploy this native installation.

## Values and terminals

**Mac** commands run on your Mac. **Pi** commands run after SSH login. Replace these example values where necessary:

| Value | Example | Meaning |
| --- | --- | --- |
| SSH login | `dawei@raspberrypi.local` | Your normal Pi user, with sudo access |
| Pi private IPv4 | `192.168.1.205` | Confirm in your router/Pi |
| Application | `/srv/portfolio/app` | Running deployment snapshot |
| Python environment | `/srv/portfolio/venv` | Pi-installed dependencies |
| Linux user / DB role | `portfolio` | Service identity, separate from the admin login |
| Database | `portfolio` | Live PostgreSQL database |

Run blocks in order and stop if a command fails. Keep the same Pi shell open where later commands use variables. Keep secrets out of Git and chat.

## First-time installation

### 1. Prepare the Pi

For a new SD card, use Raspberry Pi Imager to install Raspberry Pi OS Lite (64-bit) on a compatible Pi. Configure your hostname, username, password or SSH key, network, and SSH before writing. Reimaging erases the selected card; skip this on an existing installation. See the official [OS setup](https://www.raspberrypi.com/documentation/computers/getting-started.html) and [SSH guide](https://www.raspberrypi.com/documentation/computers/remote-access.html#ssh).

**Mac:**

```sh
ssh dawei@raspberrypi.local
```

If `.local` does not resolve, use the private IP from your router, for example `ssh dawei@192.168.1.205`.

**Pi:**

```sh
hostname -I
uname -m
cat /etc/os-release
df -h /
free -h
sudo apt update
sudo apt install -y python3 python3-venv postgresql postgresql-client nginx rsync curl nano
python3 --version
sudo systemctl enable --now postgresql
```

Python must be 3.10 or newer; upgrade an older OS before proceeding. `aarch64` indicates 64-bit ARM. Reserve the Pi's private IPv4 in your router's DHCP settings because Nginx binds to that address. Keep PostgreSQL local. LAN access needs no router port forwarding.

### 2. Build, package, and upload

**Mac:** use Node 22 with npm, matching the Dockerfile and CI. Install it from the [official downloads](https://nodejs.org/en/download) if needed. Adjust the project path below if necessary.

```sh
cd /Users/dawei/fun/davvyin.github.io
node --version
npm --version
git status --short
npm ci
CI=true npm test -- --watchAll=false --runInBand
GENERATE_SOURCEMAP=false npm run build
test -f build/index.html
test -f build/asset-manifest.json
```

`npm ci` installs the lockfile's dependencies. The build creates the deployable bundle. Do not edit source between building and packaging. This procedure includes current application files, including uncommitted changes, so review `git status`. For reproducible releases, commit intended changes before building.

Package the source and matching build together. The explicit file list excludes `.env`, `.git`, `node_modules`, the Mac's `.venv`, and unrelated files. The exclusions below also omit local databases and generated backend files.

```sh
COPYFILE_DISABLE=1 tar -czf /tmp/portfolio-release.tgz \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='*.sqlite3' --exclude='*.sqlite3-*' --exclude='staticfiles' \
  build backend src public deploy \
  package.json package-lock.json tailwind.config.js postcss.config.js README.md
shasum -a 256 /tmp/portfolio-release.tgz
tar -tzf /tmp/portfolio-release.tgz | head -n 20
git rev-parse HEAD
scp /tmp/portfolio-release.tgz dawei@raspberrypi.local:portfolio-release.tgz
```

Save the checksum and commit ID in your release notes. The checksum identifies the exact archive even when it includes uncommitted changes.

### 3. Extract and install dependencies

**Pi:** compare the SHA-256 output with the Mac's. Extract into a new directory so stale files cannot enter the release.

```sh
sha256sum ~/portfolio-release.tgz
RELEASE_DIR=$(mktemp -d "$HOME/portfolio-release.XXXXXX")
tar -xzf ~/portfolio-release.tgz -C "$RELEASE_DIR"
test -f "$RELEASE_DIR/build/index.html"
test -f "$RELEASE_DIR/backend/manage.py"
```

For a fresh installation, continue:

```sh
sudo adduser --system --group --home /srv/portfolio portfolio
sudo usermod -aG video portfolio
sudo install -d -o portfolio -g portfolio -m 755 /srv/portfolio/app
sudo rsync -a --chown=portfolio:portfolio "$RELEASE_DIR/" /srv/portfolio/app/
sudo -u portfolio python3 -m venv /srv/portfolio/venv
sudo -u portfolio /srv/portfolio/venv/bin/python -m pip install --upgrade pip
sudo -u portfolio /srv/portfolio/venv/bin/pip install -r /srv/portfolio/app/backend/requirements.txt
```

Raspberry Pi OS normally provides the `video` group, which the supplied service requires even without a camera. If the account or application already exists, inspect it and use the update procedure instead of overwriting it.

### 4. Create PostgreSQL role and database

**Pi, first installation only:**

```sh
sudo -u postgres createuser --no-createdb --no-createrole --no-superuser portfolio
sudo -u postgres createdb --owner=portfolio portfolio
sudo -u portfolio psql -d portfolio -c 'SELECT current_user, current_database();'
```

Expect user `portfolio` and database `portfolio`. The app connects over `/var/run/postgresql` using [peer authentication](https://www.postgresql.org/docs/current/auth-peer.html): the Linux user matches the database role, so no database password is needed. Run management commands with `sudo -u portfolio`.

If peer authentication is not configured, locate its configuration with `sudo -u postgres psql -Atc 'SHOW hba_file;'`. Add `local portfolio portfolio peer` before conflicting local rules, then run `sudo systemctl reload postgresql` and repeat the check. Do not enable `trust` authentication or expose PostgreSQL to the LAN.

### 5. Configure Django for LAN HTTP

**Pi:** generate a secret and create the protected configuration file:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
sudo install -o portfolio -g portfolio -m 600 /dev/null /srv/portfolio/app/.env
sudo -u portfolio nano /srv/portfolio/app/.env
```

Paste the following, replacing the secret and both IP addresses. Replace `raspberrypi.local` too if you chose another hostname. Save with Ctrl+O, Enter; exit with Ctrl+X.

```dotenv
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=REPLACE_WITH_GENERATED_SECRET
DATABASE_URL=postgresql://portfolio@/portfolio?host=/var/run/postgresql
DJANGO_ALLOWED_HOSTS=raspberrypi.local,192.168.1.205,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://raspberrypi.local,http://192.168.1.205
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SESSION_COOKIE_SECURE=false
DJANGO_CSRF_COOKIE_SECURE=false
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_TRUST_PROXY=false
```

These settings support HTTP on a trusted LAN. Do not forward this port through the router. Public access requires the [HTTPS procedure](#optional-public-https-with-cloudflare-tunnel). Keep the same secret across updates. `.env.production.example` is for the separate Docker/HTTPS setup, not this native LAN setup.

### 6. Initialize Django and create an admin

**Pi:**

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py migrate --noinput
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py collectstatic --noinput
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py check
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py createsuperuser
```

Choose your admin username and password interactively. It need not match your SSH username. A new database receives the repository's initial content. An existing database retains its content and users; importing a local fixture over it is not part of deployment.

### 7. Start Gunicorn with systemd

**Pi:**

```sh
sudo install -m 644 /srv/portfolio/app/deploy/raspberrypi/portfolio.service /etc/systemd/system/portfolio.service
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio
sudo systemctl status portfolio --no-pager
curl --fail --show-error http://127.0.0.1:8000/healthz/
```

Expect an active service and `{"status": "ok"}`. Gunicorn binds only to loopback. If startup fails, inspect `sudo journalctl -u portfolio -n 100 --no-pager` before proceeding.

### 8. Configure Nginx

**Pi:** set your real private IPv4 below:

```sh
PI_LAN_IP=192.168.1.205
sed "s/PI_LAN_IP/$PI_LAN_IP/g" /srv/portfolio/app/deploy/raspberrypi/nginx-lan.conf.example > /tmp/portfolio-nginx.conf
sudo install -m 644 /tmp/portfolio-nginx.conf /etc/nginx/sites-available/portfolio
sudo ln -sfn /etc/nginx/sites-available/portfolio /etc/nginx/sites-enabled/portfolio
sudo nginx -t
sudo systemctl enable --now nginx
sudo systemctl reload nginx
curl --fail --show-error "http://$PI_LAN_IP/healthz/"
```

If you changed the hostname, edit `server_name` in `/etc/nginx/sites-available/portfolio` before validation. Inspect existing sites with `sudo nginx -T` if you get a duplicate listener or the welcome page; preserve unrelated sites. If a firewall is active, allow TCP 80 from your LAN and retain SSH access. Ports 8000 and 5432 do not need inbound access.

### 9. Verify the deployment

**Mac or another LAN device:** open `http://192.168.1.205/` or `http://raspberrypi.local/`. Visit `/about`, `/projects`, `/technologies`, and `/contact`, then refresh each route. Log in at `/admin/`, edit one text label, save, and reload the public page to confirm the database edit appears.

**Pi:** test through Nginx:

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/deploy/raspberrypi/smoke_test.py http://192.168.1.205
sudo systemctl is-enabled portfolio nginx postgresql
```

The smoke test checks routes, API, static assets, missing pages, and a CSRF-protected admin login. It creates a temporary superuser and removes that account and its session in cleanup. It expects the initial site profile (ID 1), performs temporary database writes, and does not test camera hardware.

`manage.py check` should pass. `check --deploy` reports HTTPS-related warnings for the deliberate LAN HTTP settings; use the stricter check after configuring public HTTPS.

## Updating an existing installation

**Recommended:** use `npm run deploy:backend`, `npm run deploy:frontend`, or `npm run deploy:all` from your Mac. See [command options, logs, and recovery](COMMANDS.md). The steps below remain the manual fallback; do not run them at the same time as the pipeline.

Use this for the recorded Pi deployment. `/home/dawei/davvyin.github.io` was an older frontend checkout; `/srv/portfolio/app` is the running application. There is no deployment-on-push automation in this workflow.

1. **Mac:** repeat [step 2](#2-build-package-and-upload) to test, build, package, and upload.
2. **Pi:** run only the first block in [step 3](#3-extract-and-install-dependencies) to verify/extract the archive and set `RELEASE_DIR`. Do not recreate the user, database, `.env`, or admin.
3. Continue below in the same Pi shell. This is a maintenance-window update; Nginx may show 502 while Gunicorn is stopped.

### Back up before changing files

Check disk space for a full copy of the app/virtual environment and a database dump. Keep this shell open so `BACKUP_DIR` stays set.

```sh
df -h /srv/portfolio
BACKUP_DIR=/srv/portfolio/backups/$(date +%Y%m%d-%H%M%S)
sudo install -d -o portfolio -g portfolio -m 700 /srv/portfolio/backups "$BACKUP_DIR"
sudo systemctl stop portfolio
sudo -u portfolio pg_dump -Fc -d portfolio -f "$BACKUP_DIR/portfolio.dump"
sudo -u portfolio pg_restore --list "$BACKUP_DIR/portfolio.dump" > /dev/null
sudo -u portfolio tar -czf "$BACKUP_DIR/app-venv.tgz" -C /srv/portfolio app venv
sudo cp -a /etc/systemd/system/portfolio.service "$BACKUP_DIR/portfolio.service"
sudo cp -a /etc/nginx/sites-available/portfolio "$BACKUP_DIR/nginx-portfolio.conf"
sudo chmod 600 "$BACKUP_DIR/portfolio.dump" "$BACKUP_DIR/app-venv.tgz"
printf 'Backup directory: %s\n' "$BACKUP_DIR"
```

Save that path. If backup fails, stop the update and restart `portfolio` to resume the unchanged site. `pg_restore --list` checks archive readability; a real restore test is below. The app archive includes `.env` and must remain private. If recovery previously changed your database name, use that name in `pg_dump`.

### Apply the release

Preview the replacement first. `--delete` removes obsolete application files, while the exclusions preserve the Pi's `.env`, collected static files, and any `.git` directory. Confirm source and destination carefully.

```sh
test -f "$RELEASE_DIR/backend/manage.py"
test -f "$RELEASE_DIR/build/index.html"
sudo rsync -ani --delete --chown=portfolio:portfolio \
  --exclude=.env --exclude=.git --exclude=backend/staticfiles/ \
  "$RELEASE_DIR/" /srv/portfolio/app/
```

If the preview is correct:

```sh
sudo rsync -a --delete --chown=portfolio:portfolio \
  --exclude=.env --exclude=.git --exclude=backend/staticfiles/ \
  "$RELEASE_DIR/" /srv/portfolio/app/
sudo -u portfolio /srv/portfolio/venv/bin/pip install -r /srv/portfolio/app/backend/requirements.txt
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py migrate --noinput
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py collectstatic --noinput
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py check
sudo systemctl restart portfolio
sudo systemctl status portfolio --no-pager
curl --fail --show-error http://192.168.1.205/healthz/
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/deploy/raspberrypi/smoke_test.py http://192.168.1.205
```

Use your real address, or the HTTPS hostname if enabled. Repeat step 9's browser checks. Stop and diagnose failures or recover below; do not continue after a failed migration.

For a release changing `portfolio.service`, review/install it as in step 7, run `daemon-reload`, then restart. For Nginx changes, preserve your IP/domain customizations, run `nginx -t`, then reload. A normal app update preserves installed service/proxy configuration and needs no Nginx restart.

Record the release checksum and commit beside the backup path. Existing `/srv/portfolio/deployment.json` is historical provenance; these manual commands do not update it automatically. Admin content-only edits need no deployment. Frontend/local-image changes need a build; Python changes need deployment and restart, plus migrations when the schema changes.

## Backups and recovery

### Copy backups away from the Pi

Use the backup procedure above before updates and repeat database backups after important admin edits. No automatic backup schedule is included. Export a private archive readable by your SSH user.

**Pi:** replace the example timestamp with your actual backup path:

```sh
BACKUP_DIR=/srv/portfolio/backups/20260925-120000
umask 077
sudo tar -czf - -C "$BACKUP_DIR" . > "$HOME/portfolio-backup.tgz"
```

**Mac:**

```sh
umask 077
mkdir -p ~/portfolio-backups
scp dawei@raspberrypi.local:portfolio-backup.tgz ~/portfolio-backups/
```

Rename downloaded backups to keep multiple dates. Store them securely: they contain secrets and account data. Backups only on the Pi cannot protect against SD-card failure.

### Verify a restore without replacing live data

**Pi:** choose a fresh database name for each attempt. Creation uses `postgres` because the application role cannot create databases.

```sh
BACKUP_DIR=/srv/portfolio/backups/20260925-120000
sudo -u postgres createdb --owner=portfolio --template=template0 portfolio_restore_check
sudo -u portfolio pg_restore --exit-on-error --no-owner --no-privileges \
  -d portfolio_restore_check "$BACKUP_DIR/portfolio.dump"
sudo -u portfolio psql -d portfolio_restore_check -c 'SELECT count(*) FROM django_migrations;'
sudo -u portfolio psql -d portfolio_restore_check -c 'SELECT username, is_active, is_superuser FROM auth_user;'
```

If step 4 required a database-specific peer rule, add the corresponding rule for `portfolio_restore_check`. Confirm expected tables, users, and content. Use a PostgreSQL restore tool compatible with the dump's version; see [pg_restore documentation](https://www.postgresql.org/docs/17/app-pgrestore.html).

### Recover from a failed update

Restoring a database returns content/accounts to the backup's time. Preserve current data if you need later edits. Old code is not necessarily compatible with a newly migrated schema.

**Pi:** stop the app, preserve failed code/dependencies, and restore the matching backup at the original paths:

```sh
BACKUP_DIR=/srv/portfolio/backups/20260925-120000
FAILED_DIR=/srv/portfolio/failed-$(date +%Y%m%d-%H%M%S)
sudo systemctl stop portfolio
sudo install -d -m 700 "$FAILED_DIR"
sudo mv /srv/portfolio/app "$FAILED_DIR/app"
sudo mv /srv/portfolio/venv "$FAILED_DIR/venv"
sudo tar -xzf "$BACKUP_DIR/app-venv.tgz" -C /srv/portfolio
sudo cp -a "$BACKUP_DIR/portfolio.service" /etc/systemd/system/portfolio.service
sudo cp -a "$BACKUP_DIR/nginx-portfolio.conf" /etc/nginx/sites-available/portfolio
sudo systemctl daemon-reload
sudo nginx -t
sudo systemctl reload nginx
```

The virtual environment backup is for the same Pi/OS and original path. On a replacement OS, recreate it and reinstall dependencies.

If migrations ran or partially failed, restore the pre-update dump into a **new** database using the procedure above, then edit `/srv/portfolio/app/.env` to use that restored database:

```dotenv
DATABASE_URL=postgresql://portfolio@/portfolio_restore_check?host=/var/run/postgresql
```

Switch only after the restore succeeds. If the update never changed the database, retain the original URL. Then:

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py check
sudo systemctl start portfolio
curl --fail --show-error http://192.168.1.205/healthz/
```

Repeat smoke/browser checks at the appropriate origin. Future backups must use your active database name. This procedure preserves the failed database instead of overwriting it.

## Private admin with WireGuard

For visitor analytics at `/admin/analytics/` and separately assignable staff access to analytics, system health, and camera, follow the [analytics and permissions guide](../../backend/visitor_analytics/README.md). Deploy both frontend and backend, run migrations, and complete its first-time IP-proxy and retention-timer setup. Existing ordinary staff need an explicit camera permission after this update; superusers retain access to every tool.

The live Pi now runs a self-hosted WireGuard server. The public portfolio remains available at `https://davyin.tech/`, while public requests for `/admin/` return 404. Connect the Mac's dedicated WireGuard peer first, then open `http://10.66.66.1:8080/admin/`. Give each device its own peer key and tunnel IP; do not share profiles between the Mac and phone. Follow the [WireGuard runbook](wireguard/README.md) for peer creation/revocation, router forwarding, client import, verification, and recovery steps. Remote access still needs a router rule forwarding UDP 51820 to the Pi; TCP is not needed.

## Optional staff camera

For CPU, memory, storage, network traffic, and sensor monitoring, install the separate [admin-only Glances dashboard](../../backend/system_monitor/README.md) at `/admin/system/`. It includes a dedicated collector service and uses the existing private admin/VPN route without opening another public port.

Connect a supported camera with the Pi powered off, then boot. **Pi:**

```sh
sudo apt install -y rpicam-apps
sudo usermod -aG video portfolio
sudo -u portfolio rpicam-hello --list-cameras
sudo systemctl restart portfolio
```

See the official [camera documentation](https://www.raspberrypi.com/documentation/computers/camera_software.html) for hardware setup. Sign in as staff and open `/admin/camera/`. The default broadcaster captures MJPEG at 1280×720/15 fps once and shares the latest frames with all active viewers; slow viewers skip stale frames instead of building a queue. It stops capture when the last viewer disconnects. This reduces camera work and latency while keeping bandwidth proportional to the number of viewers. It is an in-process broadcaster, so keep one Gunicorn worker. Four Gunicorn threads allow several camera streams plus admin requests; total simultaneous requests remain bounded by the thread count. The previous exclusive one-viewer implementation remains available by setting `CAMERA_STREAM_MODE=exclusive` in `/srv/portfolio/app/.env` and restarting `portfolio`. Django disables Nginx stream buffering with `X-Accel-Buffering: no`. The generic smoke test does not test camera hardware.

## Optional public HTTPS with Cloudflare Tunnel

Verify LAN operation first. You need a domain in an active Cloudflare zone. Traffic follows browser → Cloudflare HTTPS → outbound tunnel → loopback Nginx → Gunicorn. No inbound router ports or public Pi IP record are needed for this tunnel route. A DDNS updater alone does not publish the app.

1. Create a remotely managed tunnel using [Cloudflare's setup guide](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/get-started/create-remote-tunnel/). Run the dashboard's installation/service commands on the Pi for its Linux architecture. Keep the token private and confirm the connector is healthy; use the current commands provided for your tunnel.
2. Choose your hostname, for example `portfolio.example.com`. Enable Cloudflare **Always Use HTTPS** for the applicable zone before publishing the route, so public HTTP redirects at the edge. The fixed HTTPS header below depends on this.
3. **Pi:** create `/etc/nginx/sites-available/portfolio-tunnel` with `sudo nano`, replacing the hostname:

```nginx
server {
    listen 127.0.0.1:8080;
    server_name portfolio.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
    }
}
```

4. Enable with `sudo ln -sfn /etc/nginx/sites-available/portfolio-tunnel /etc/nginx/sites-enabled/portfolio-tunnel`, run `sudo nginx -t`, then `sudo systemctl reload nginx`.
5. Edit the Pi's `.env`, preserving the secret and database URL, and set these values with your actual hostname:

```dotenv
DJANGO_ALLOWED_HOSTS=portfolio.example.com,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://portfolio.example.com
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_TRUST_PROXY=true
```

6. Restart `portfolio`. In the tunnel dashboard, add a published application route for your hostname to **HTTP** service `127.0.0.1:8080`. If setting an origin Host override, use the public hostname. Use the tunnel's DNS route and resolve any conflicting record for that hostname. The public connection is HTTPS; the HTTP hop stays on the Pi's loopback interface.
7. Check `https://portfolio.example.com/healthz/`, public routes, and admin login. Confirm `http://portfolio.example.com/` redirects to HTTPS. Run the smoke test against `https://portfolio.example.com`.
8. After verification, choose an HSTS duration, set `DJANGO_SECURE_HSTS_SECONDS`, and restart. The app applies HSTS to **all subdomains of the served hostname**, so ensure they support HTTPS first. Run `sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py check --deploy --fail-level WARNING` and resolve remaining warnings. With HSTS at zero, its warning is expected.

The separate loopback listener overwrites the protocol header. Do not put its fixed `https` header on the LAN/public HTTP listener. Do not use the LAN block's `$scheme` on the tunnel listener, which would report HTTP and cause redirect loops. See Django's [proxy-header requirements](https://docs.djangoproject.com/en/5.2/ref/settings/#secure-proxy-ssl-header). Use the HTTPS hostname after switching; secure cookies no longer support LAN HTTP admin login. Include the tunnel site configuration in your server backups if you customize it.

Nginx is a web proxy, not a DNS resolver. Resolving `cloudflare.com` only proves outbound DNS works. Do not use Cloudflare Flexible TLS or expose an unauthenticated camera port.

## Troubleshooting and routine operations

| Symptom | Check / action |
| --- | --- |
| SSH fails | Check power, network, SSH enablement, username, and router address. Try the IP if `.local` fails. |
| Nginx welcome page / refused connection | Check actual IP, `sudo nginx -T`, enabled site, firewall, and Nginx status. |
| 502 Bad Gateway | Read `journalctl -u portfolio`; check Gunicorn's local `/healthz/` in LAN mode. |
| 400 Bad Request | Add the exact hostname/IP to `DJANGO_ALLOWED_HOSTS` without a scheme; restart. |
| Admin CSRF error / login loop | Match trusted origins, cookie settings, and protocol to the browser URL; restart after `.env` edits. |
| Tunnel HTTPS loop | Check the separate loopback listener and overwritten `X-Forwarded-Proto https`. |
| Peer authentication failed | Run as Linux user `portfolio`; check socket URL, role, and matching `pg_hba.conf` rule. |
| Blank UI / missing assets | Check `build/index.html`, build/source consistency, `collectstatic`, `/api/content/`, and browser network errors. |
| Admin edits missing | Check database URL and server address. Content comes from PostgreSQL, not `src/Details.js`. |
| Gunicorn killed | Check memory and journal logs; build on the Mac and diagnose usage before changing the unit's memory limit. |
| Camera unavailable | Check camera detection, `rpicam-vid`, group access, and another active stream. |

Useful **Pi** commands:

```sh
sudo systemctl status portfolio nginx postgresql --no-pager
sudo journalctl -u portfolio -n 100 --no-pager
sudo tail -n 100 /var/log/nginx/error.log
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py showmigrations
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py changepassword YOUR_ADMIN_USERNAME
sudo systemctl restart portfolio
```

Install OS security updates regularly and verify after rebooting. Use the [main README verification commands](../../README.md#verification) in development; do not run tests against the live database or grant the production role database-creation privileges just for tests.

## Previously recorded installation (2026-09-23 / 2026-09-24)

These are historical notes, not a fresh live inspection:

- The site was originally available at `http://raspberrypi.local` / `http://192.168.1.132`, with admin at `/admin/`. It was LAN-only HTTP; public HTTPS was not configured.
- The local `dawei` admin was transferred with its password unchanged. A fresh installation following this guide creates the account you choose.
- The site-copy release was recorded as passing 17 backend tests, 7 frontend tests, and 30 live HTTP checks. Those counts describe that release.
- The 2026-09-24 snapshot was based on commit `e95c5f4` plus local changes, SHA-256 `24b0e56a455a68c403f92331c9cf2c7f5c8a7340087eb42b7559b96346a35e5c`. Provenance was stored in `/srv/portfolio/deployment.json`.
- `/home/dawei/davvyin.github.io` was left unchanged; `/srv/portfolio/app` was the running snapshot.
- `/srv/portfolio/backups/initial-20260923.dump` was a one-time backup, not a schedule. Make a new backup before updating.
