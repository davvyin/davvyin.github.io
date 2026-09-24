# Raspberry Pi deployment

For a Pi with limited memory, run PostgreSQL, Gunicorn, and Nginx as native services. The frontend can be built on another machine from the same Git commit and copied as `build/`; JavaScript bundles are architecture-independent.

Deployment layout:

- Git checkout: `/srv/portfolio/app`
- Python virtual environment: `/srv/portfolio/venv`
- Runtime account and database owner: `portfolio`
- Application service: `portfolio.service`
- Database: PostgreSQL `portfolio`, listening only locally
- Nginx: forwards the Pi's private IPv4 port 80 to `127.0.0.1:8000`

Install `git python3-venv postgresql nginx` using apt. Create the `portfolio` system user with home `/srv/portfolio`, clone the repository into `app`, and create the virtual environment. Install `backend/requirements.txt`, build/copy the frontend, and run Django migrations and `collectstatic` as `portfolio`.

Store configuration in `/srv/portfolio/app/.env`, owned by `portfolio`, mode 600. Generate a unique `DJANGO_SECRET_KEY` on the Pi. Use a PostgreSQL URL and explicit allowed hosts. Unix socket peer authentication can avoid a database password when the service and database role are both `portfolio`:

```dotenv
DJANGO_DEBUG=false
DJANGO_SECRET_KEY=REPLACE_WITH_GENERATED_SECRET
DATABASE_URL=postgresql://portfolio@/portfolio?host=/var/run/postgresql
DJANGO_ALLOWED_HOSTS=raspberrypi.local,PI_LAN_IP,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=http://raspberrypi.local,http://PI_LAN_IP
DJANGO_SECURE_SSL_REDIRECT=false
DJANGO_SESSION_COOKIE_SECURE=false
DJANGO_CSRF_COOKIE_SECURE=false
DJANGO_SECURE_HSTS_SECONDS=0
DJANGO_TRUST_PROXY=false
```

These HTTP settings are only for trusted LAN access. Before publishing on a public domain, configure HTTPS, enable SSL redirects and secure cookies, update allowed hosts/origins, and configure trusted proxy handling. Do not forward the HTTP LAN port through the router.

Install `portfolio.service` into `/etc/systemd/system/`. Replace `PI_LAN_IP` in `nginx-lan.conf.example`, install it as an enabled Nginx site, validate with `nginx -t`, and enable/restart the services. Keep the IP stable with a DHCP reservation.

Create the administrator interactively:

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py createsuperuser
```

For subsequent updates, back up the database, pull the intended Git revision, update Python dependencies, replace `build/` from that revision, run migrations and `collectstatic`, and restart `portfolio`.

Useful operations:

```sh
sudo systemctl status portfolio nginx postgresql
sudo journalctl -u portfolio -n 100 --no-pager
sudo -u portfolio pg_dump -Fc portfolio > portfolio-backup.dump
sudo systemctl restart portfolio
```

Check `/healthz/`, `/api/content/`, all public routes, and `/admin/login/` from another device on the LAN. Verify a real admin login to confirm cookies and CSRF work through Nginx.

The included smoke test creates a temporary administrator, verifies login through the actual web server, then removes the account and session:

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/deploy/raspberrypi/smoke_test.py http://192.168.1.132
```

## Current installation (2026-09-23)

The app runs at `http://raspberrypi.local` / `http://192.168.1.132`, with admin at `/admin/`. The existing local `dawei` admin account was transferred with its password unchanged. The site-copy release passed all 17 backend tests, 7 frontend tests, and 30 live HTTP checks on the Pi.

The admin edits the original portfolio values and the visible page copy. The `Site text and labels` section controls headings, navigation labels, greeting, and card buttons. Saving text updates the database API; refreshing the page renders the edited value. The 2026-09-24 release is a workspace snapshot based on commit `e95c5f4` plus local changes, SHA-256 `24b0e56a455a68c403f92331c9cf2c7f5c8a7340087eb42b7559b96346a35e5c`. Make a verified database backup before future updates.

## Staff-only camera stream

The Django admin exposes a live camera page at `/admin/camera/`. Both the page and its MJPEG stream endpoint require a signed-in Django staff account. The stream uses `rpicam-vid` at 1280x720/15 fps and allows one active stream. The `portfolio` system user needs access to the Linux `video` group; the service unit declares `SupplementaryGroups=video`. Nginx should pass `/admin/camera/stream.mjpg` without buffering (`X-Accel-Buffering: no` is set by Django). Keep the origin on HTTPS and do not publish a separate unauthenticated camera port.

The original `/home/dawei/davvyin.github.io` checkout contained only the older frontend and was left unchanged. The running `/srv/portfolio/app` is a deployment snapshot of the completed local workspace (base commit `e95c5f4` plus the Raspberry Pi configuration changes), not a Git checkout. Update it from the completed project; pulling the old checkout will not update the running app. Deployment provenance is recorded in `/srv/portfolio/deployment.json`.

An initial PostgreSQL backup is stored at `/srv/portfolio/backups/initial-20260923.dump`. This is a one-time backup, not an automated backup schedule. Services are enabled at boot. This installation is LAN-only HTTP; public-domain HTTPS has not been configured.

## DNS and Cloudflare

Nginx forwards HTTP on the Pi's private LAN address to Gunicorn. It does not run a recursive DNS resolver or configure Cloudflare. The Pi asks the router at `192.168.1.1` for DNS; the router also advertises an IPv6 DNS server. The fact that the Pi can resolve `cloudflare.com` proves outbound DNS works.

Cloudflare website DNS requires a hostname and an active Cloudflare zone. A proxied `A`, `AAAA`, or `CNAME` record points at the public origin or tunnel. Cloudflare's proxy status decides whether public web requests pass through its network. DNS records, the Nginx virtual host, and Django `DJANGO_ALLOWED_HOSTS` must all use the same hostname. See Cloudflare's [DNS record setup](https://developers.cloudflare.com/dns/manage-dns-records/how-to/create-dns-records/) and [proxy status](https://developers.cloudflare.com/dns/proxy-status/) guides.

No public hostname is configured on this Pi; the site is LAN-only HTTP. For public access, use a Cloudflare Tunnel to avoid opening inbound router ports, configure the actual hostname in Django's allowed and CSRF trusted hosts, and enable HTTPS cookies and redirects. Do not use plain public HTTP or Cloudflare Flexible TLS for the admin login.
