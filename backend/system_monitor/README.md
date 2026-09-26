# Administrator-only Pi system monitoring

Open **Admin → Raspberry Pi health → Open system monitoring dashboard**, or visit `/admin/system/` on your admin origin. On the recorded WireGuard installation, connect the VPN and use `http://10.66.66.1:8080/admin/system/`. Sign in with an active Django **superuser** that also has staff access, or a staff account granted **Can view system health** (`portfolio.view_system_health`). Other staff/content editors receive 403. Superusers assign access through Users or Groups; see the [staff access guide](../visitor_analytics/README.md#control-staff-access-to-all-three-tools).

This feature integrates [Glances](https://github.com/nicolargo/glances), using its existing Vue/Bootstrap Web UI and Python/psutil collectors. It does not recreate the graphs or poll hardware inside Django. The pinned `glances[web]==4.5.6` PyPI distribution supplies the compiled UI and collector; its source is LGPL-3.0 licensed. No CDN or separate JavaScript build is needed for this feature.

## What you can see

| Area | Metrics / specifications |
| --- | --- |
| Host | Hostname, operating system/kernel, architecture, uptime |
| CPU | Logical cores, usage, load averages, available frequency information |
| Memory | Total/used/available RAM and swap |
| Storage | Mounted filesystem capacity/usage and disk read/write activity |
| Network | Receive/transmit rates per interface, including Ethernet, Wi-Fi, and WireGuard when present |
| Sensors | Temperature and other readings supported by the OS/hardware |
| Processes | Processes visible to the unprivileged collector, CPU and memory usage |

The dashboard refreshes every five seconds and uses Glances' responsive layout, color-coded utilization, and native controls. Open **Open full dashboard** for more room on a phone or small screen. If the collector is offline, an explanatory retry screen appears while the rest of the site continues working.

Network counters describe the **Pi's interface traffic**, including local-network and VPN traffic. They do not measure the whole router's internet usage, separate WAN from LAN, or run a speed test. Do not add rates from `wg0` and its underlying interface: a tunneled transfer can appear on both. This is live monitoring, not persistent historical reporting. Exact Pi board model, throttling flags, and sensors are not guaranteed by Glances; missing hardware readings remain unavailable rather than being estimated.

The integration is read-only. Glances controls that clear alerts or request extended process details use POST and are intentionally blocked. Display/filter controls and the live dashboard remain available.

## Architecture and access controls

```text
Browser / VPN → existing Nginx admin route → Django session + tool permission
                                               ├─ /admin/system/ (admin wrapper)
                                               └─ /admin/system/dashboard/*
                                                     ↓ fixed loopback proxy
                                              Glances 127.0.0.1:61208
                                                     ↓ psutil / OS interfaces
                                                Pi host statistics
```

- Django authorizes **every** HTML, JavaScript, icon, and API request. Logging out, disabling the account, or removing all grants of system-health access blocks the next request. Previously displayed information cannot be erased from an already-open browser.
- HTML/assets/API responses use `Cache-Control: no-store`. Only the embedded dashboard allows same-origin framing; the rest of the admin retains its existing protection.
- The proxy accepts GET/HEAD and only the upstream Web UI's required read endpoints/static assets. It uses a fixed loopback host/port, does not follow redirects, and forwards no browser cookies, authorization headers, or query parameters. Requests have a three-second socket timeout and an 8 MiB response limit.
- Glances binds only to `127.0.0.1`, restricts accepted Host headers, and runs under its own unprivileged Linux account. It does not load Django's `.env` or need database access. As with other loopback services, trusted local OS users/processes can connect directly; Django authorization protects browser access through the website.
- Keep the existing public `/admin/*` block and VPN restrictions. Do **not** add an Nginx location directly proxying to port 61208, publish that port, or add it to router forwarding: that would bypass Django authentication. The existing catch-all proxy to Django already handles this feature.
- The collector needs no database table. Run Django migrations to create the admin-tool permissions. Collector failure does not make the existing `/healthz/` database check fail or expose hardware information there.

## Install on the existing Pi

First deploy this repository's updated backend using the [normal update procedure](../../deploy/raspberrypi/README.md#updating-an-existing-installation). Preserve the Pi's `.env`, database, and private Nginx/VPN settings. The `backend/system_monitor/` folder is included by that guide's archive command. This backend feature does not require rebuilding React.

**Pi, after SSH login:** install a separate virtual environment for Glances. These first-time commands assume `/srv/portfolio/app` and Linux group `portfolio` already exist.

```sh
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential
sudo adduser --system --group --no-create-home --home /nonexistent portfolio-monitor
sudo chmod g+x /srv/portfolio
sudo python3 -m venv /srv/portfolio/monitor-venv
sudo /srv/portfolio/monitor-venv/bin/python -m pip install --upgrade pip
sudo /srv/portfolio/monitor-venv/bin/pip install -r /srv/portfolio/app/backend/system_monitor/requirements.txt
sudo install -m 644 /srv/portfolio/app/backend/system_monitor/portfolio-monitor.service /etc/systemd/system/portfolio-monitor.service
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-monitor
sudo systemctl restart portfolio
sudo systemctl status portfolio-monitor portfolio --no-pager
```

Python 3.10+ is required. Build tools cover systems where a psutil wheel is unavailable. Installing from PyPI with the `web` extra includes the UI; some distribution packages omit those files. Do not install Glances into the Django virtual environment, and do not run the collector as root. The service's supplementary `portfolio` group and the directory's group execute bit permit traversal of the deployment directory without granting directory-listing access. `.env` must remain owned by `portfolio` with mode 600 and backup directories mode 700.

The collector reads `backend/system_monitor/glances.conf`, with `/admin/system/dashboard/` as its URL prefix. Keep the final slash. The service fixes the bind address, port, and five-second interval. Public-IP discovery, cloud, and container plugins are disabled; no external monitoring account or container-engine socket is needed. Glances still sees ordinary host network counters, including this website's traffic.

### Verify on the Pi and from your browser

**Pi:**

```sh
sudo ss -ltnp 'sport = :61208'
curl --fail --show-error http://127.0.0.1:61208/admin/system/dashboard/api/4/all
sudo journalctl -u portfolio-monitor -n 80 --no-pager
```

The listening address must be `127.0.0.1:61208`, never `0.0.0.0` or `[::]`. The curl command deliberately bypasses Django from the Pi itself and returns host details; do not publish its output.

**Mac, with WireGuard active on the recorded installation:**

```sh
curl -I http://10.66.66.1:8080/admin/system/
curl -I http://10.66.66.1:8080/admin/system/dashboard/api/4/all
curl -I https://davyin.tech/admin/system/
```

Without browser session cookies, the first two requests should redirect to `/admin/login/`; the public URL should remain 404 under the existing Nginx configuration. For a fresh LAN installation, substitute its own admin origin.

In the browser:

1. Log in as a superuser and open `/admin/system/`. Confirm host information and live CPU/memory/storage/network readings appear.
2. Wait at least two refresh cycles. Generate ordinary traffic to the Pi, for example by navigating the portfolio in another tab, and check the relevant interface changes.
3. Open the full dashboard and try a narrow/mobile viewport. Check that the native dashboard remains usable.
4. Log out and reload the dashboard and its API URL; neither should return metrics. Sign in with an ordinary staff account and confirm 403.
5. Optionally stop `portfolio-monitor`, reload the dashboard to confirm the retry screen, and start the service again. The public portfolio should remain available throughout.

Sensor coverage, ARM package installation, and the service's actual host readings must be verified on the Pi. Local development shows the local machine's stats, not the Pi's.

## Updates, operation, and removal

Routine application updates preserve `/srv/portfolio/monitor-venv`, which is outside the app snapshot. If the collector requirements change, update them separately and restart:

```sh
sudo /srv/portfolio/monitor-venv/bin/pip install -r /srv/portfolio/app/backend/system_monitor/requirements.txt
sudo install -m 644 /srv/portfolio/app/backend/system_monitor/portfolio-monitor.service /etc/systemd/system/portfolio-monitor.service
sudo systemctl daemon-reload
sudo systemctl restart portfolio-monitor
sudo journalctl -u portfolio-monitor -n 80 --no-pager
```

Keep the dependency pinned until its URL prefix, UI assets, and API requests have been reverified. Include the monitor config, service unit, and requirements in your normal configuration backups; live statistics are not stored in PostgreSQL. The base app/venv backup in the deployment guide does not include `monitor-venv`; reinstall its pinned dependencies if rebuilding the Pi. Roll back collector version/configuration together if an upgrade fails.

To disable collection without affecting the portfolio:

```sh
sudo systemctl disable --now portfolio-monitor
```

The admin then shows the unavailable screen. No database cleanup is required.

| Problem | Diagnosis |
| --- | --- |
| 403 in Django | The account needs active and staff flags, plus superuser status or the `portfolio.view_system_health` permission (directly or through a group). |
| Public URL is 404 | Expected for this Pi: connect WireGuard and use the private admin origin. |
| Retry screen / 503 | Check service status and journal, then the local curl command. Confirm port 61208 and the exact URL prefix. |
| Blank dashboard / missing JavaScript | Install the pinned PyPI `web` extra; inspect requests under `/admin/system/dashboard/static/`. |
| API fails after working previously | Your session may have expired or permissions changed. Sign in again and refresh. |
| Host differs from the Pi | The collector runs on another host or in a container. Install it natively on the Pi for Pi metrics. |
| Missing temperature/process fields | Some OS/hardware readings need unavailable sensors or permissions. Do not grant root merely to fill optional fields. |
| High collector overhead | Inspect process count and usage; increase `--time` in the service and reload/restart if necessary. Match the wrapper's refresh description to your setting. |

## Development and tests

The Django application has no additional Python dependencies. Its access-control/proxy tests use a fake upstream, so Glances need not run:

```sh
python backend/manage.py test portfolio system_monitor visitor_analytics
```

To preview actual local-machine metrics, create a separate environment and run the collector alongside the usual Django development server:

```sh
python3 -m venv /tmp/portfolio-monitor-venv
/tmp/portfolio-monitor-venv/bin/pip install -r backend/system_monitor/requirements.txt
/tmp/portfolio-monitor-venv/bin/glances --webserver --bind 127.0.0.1 --port 61208 --time 5 --byte --disable-config-exec --disable-autodiscover --config backend/system_monitor/glances.conf
```

In another terminal run Django normally, sign in with a local superuser, and visit `http://127.0.0.1:8000/admin/system/`. Stop the collector with Ctrl+C when finished. For a Docker-hosted Django app, loopback points inside the container; the supplied integration targets the native Pi installation and does not configure host access from containers.

Upstream references: [installation and source](https://github.com/nicolargo/glances), [Web UI](https://glances.readthedocs.io/en/latest/quickstart.html#web-server-mode), [API/prefix and security configuration](https://glances.readthedocs.io/en/latest/api/restful.html), [configuration reference](https://glances.readthedocs.io/en/latest/config.html).
