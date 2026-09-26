# Visitor analytics and staff tool access

Open **Admin → Visitor analytics**, or **Open visitor analytics in a new tab** on the admin home page. On the Pi, connect WireGuard and visit `http://10.66.66.1:8080/admin/analytics/`. Keep the public Nginx `/admin/` block in place.

The dashboard includes page views, distinct IP addresses, IPs active within the last five minutes, a daily traffic chart, a paginated IP list with first/last seen and page counts, popular pages, referring domains, browser/device summaries, and recent page views. Filter by today/7/30/90 days and an exact IPv4 or IPv6 address. Selecting an IP filters every panel to that address. Counts and timestamps use UTC. The responsive UI supports Django's light/dark theme and an accessible daily-count table alongside the chart.

## Control staff access to all three tools

Only an active **superuser with staff status** can manage Users and Groups. Superusers can view all tools automatically. Ordinary staff start with no tool access; there is no automatic grant to existing staff. This changes camera access from the former all-staff behavior.

1. Sign in with your superuser account and open **Authentication and Authorization → Users**.
2. Select the existing staff user (or create an account and then edit it).
3. Under **Permissions**, enable **Active** and **Staff status**. Leave **Superuser status** off for users whose access you want to restrict.
4. In **User permissions**, search for the desired permission and move it to the selected list:

   | Permission label | Tool | Permission code |
   | --- | --- | --- |
   | Can view visitor analytics (includes IP addresses) | `/admin/analytics/` | `portfolio.view_visitor_analytics` |
   | Can view system health | `/admin/system/` and all proxied assets/metrics | `portfolio.view_system_health` |
   | Can view live camera | `/admin/camera/` and the stream | `portfolio.view_camera` |

5. Save. The user's admin navigation now shows only the tools they can access.

For several users, create a **Group** such as “Analytics readers”, assign the permission to the group, then add users to that group. Permissions are additive: to revoke access, remove both direct permissions and any group granting the same permission. Do not mark restricted users as superusers; that grants all permissions. Existing Django content permissions (view/add/change/delete projects, site text, etc.) still control content editing independently.

These checks protect URLs directly, not just navigation links. Anonymous users are sent to login; staff without the permission receive 403. Permission changes take effect on the next request. The camera additionally checks a fresh session and permission set every five seconds as frames flow, stopping on logout, account deactivation, or permission removal. Already received data cannot be recalled. Users/Groups remain restricted to superusers even if a staff user is accidentally granted `auth` editing permissions.

## How collection works

- `src/VisitorAnalytics.js` sends a small same-origin JSON POST to `/api/analytics/pageview/` on the initial public page load and each React route change. The allowed pages are `/`, `/about`, `/projects`, `/technologies`, and `/contact`. Query strings, fragments, and private/admin URLs are never sent. This also records visits when Cloudflare serves cached HTML.
- The endpoint is **write-only** and returns an empty response, never IP lists or stats. It checks the exact Origin, JSON content type, payload size, page allowlist, and UUID. Repeated event IDs are deduplicated. IDs identify page-view events, not returning people.
- Each record stores the server timestamp, IP address, path, referrer **hostname only**, and coarse browser/device labels. No raw user agent, full referrer URL, analytics cookie, local-storage identifier, geolocation service, or third-party analytics request is used.
- Signed-in staff on the same origin, known bot user agents, and Do Not Track/Global Privacy Control requests are excluded. A public-domain visit without the private admin's session cookie is anonymous and can be counted. JavaScript-disabled/blocked visits are absent. Client events and browser labels can be forged; this is traffic reporting, not an audit or billing log.
- “Unique IPs” means distinct addresses, not unique people. Shared Wi-Fi/NAT, VPNs, changing mobile addresses, and IPv6 affect counts. “Recently active” means a recorded page view within five minutes, not an open-tab heartbeat. First/last seen apply to the selected date range. Empty or internal referrers appear as “Direct / internal / unknown”. Data begins after deployment; existing access logs are not imported.
- The Pi's collector has a best-effort per-process limit of 60 events/IP/minute. Install the Nginx rate limit below for a shared limit across workers. Collection failures never block React navigation.

## Deploy this branch to the Pi

This feature changes **both frontend and backend**. From the Mac project folder on `feature/visitor-analytics`, run:

```sh
npm run deploy:all
```

The pipeline builds React, applies migrations (including the three permission definitions), collects dashboard CSS, and restarts Django. It preserves the Pi's environment and Nginx configuration. It does not automatically install the following first-time proxy or timer configuration. `npm run deploy:all:fast` is also available, with the existing no-backup/no-test tradeoffs.

On the Pi, add to `/srv/portfolio/app/.env`:

```dotenv
ANALYTICS_ENABLED=true
ANALYTICS_TRUSTED_PROXIES=127.0.0.1/32,::1/128
ANALYTICS_RETENTION_DAYS=90
DJANGO_TRUST_PROXY=true
```

`ANALYTICS_TRUSTED_PROXIES` defaults to empty. Django then records its direct connection peer and ignores forwarded IP headers. For this native Pi setup, Gunicorn binds to loopback and Nginx must overwrite `X-Real-IP` with the verified visitor address. Never trust arbitrary incoming `X-Forwarded-For` or `CF-Connecting-IP` directly in Django. Other deployments must supply only their actual, trusted proxy CIDRs.

`DJANGO_TRUST_PROXY=true` also lets Django use Nginx's overwritten `X-Forwarded-Proto` header for the collector's same-origin check. Keep the private VPN listener's value `http` and the public HTTPS listener's value `$scheme`; preserve the existing private-admin HTTP/secure-cookie settings.

### Restore visitor IPs behind Cloudflare

Cloudflare supplies the visitor address in [`CF-Connecting-IP`](https://developers.cloudflare.com/fundamentals/reference/http-headers/#cf-connecting-ip). Nginx's [real-IP module](https://nginx.org/en/docs/http/ngx_http_realip_module.html) must accept that header **only from Cloudflare's published networks**. The supplied snippet contains the official [IPv4](https://www.cloudflare.com/ips-v4/) and [IPv6](https://www.cloudflare.com/ips-v6/) lists verified on 2026-09-26; recheck them during maintenance. For this setup, use Cloudflare's normal IPv6 mode rather than Pseudo IPv4 “Overwrite Headers” if you want the original IPv6 address.

```sh
sudo install -m 644 /srv/portfolio/app/backend/visitor_analytics/nginx-cloudflare-realip.conf /etc/nginx/snippets/portfolio-cloudflare-realip.conf
sudo nano /etc/nginx/sites-available/portfolio
```

Inside the existing **public HTTPS server block** bound to `192.168.1.205:443`, add:

```nginx
include /etc/nginx/snippets/portfolio-cloudflare-realip.conf;
```

Ensure its Django proxy location overwrites headers:

```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
```

Keep the existing `/admin` and `/admin/*` public-deny locations and the VPN-only port-8080 listener. Do not apply the Cloudflare snippet to the private listener. Direct LAN requests will use the LAN source IP; the public website uses Cloudflare's verified visitor IP.

For the collection rate limit, put this line in `/etc/nginx/conf.d/portfolio-analytics-limit.conf` (Nginx's `http` context):

```nginx
limit_req_zone $binary_remote_addr zone=portfolio_analytics:1m rate=1r/s;
```

Then add this exact location in the public HTTPS server, alongside the existing application location:

```nginx
location = /api/analytics/pageview/ {
    client_max_body_size 2k;
    limit_req zone=portfolio_analytics burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Validate and apply:

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart portfolio
```

### Retention and cleanup

The retention setting is enforced by a daily cleanup command, not during page requests. Install the included timer:

```sh
sudo install -m 644 /srv/portfolio/app/backend/visitor_analytics/portfolio-analytics-prune.service /etc/systemd/system/
sudo install -m 644 /srv/portfolio/app/backend/visitor_analytics/portfolio-analytics-prune.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now portfolio-analytics-prune.timer
sudo systemctl list-timers portfolio-analytics-prune.timer
```

Preview deletion or run it immediately:

```sh
sudo -u portfolio /srv/portfolio/venv/bin/python /srv/portfolio/app/backend/manage.py prune_visitor_analytics --dry-run
sudo systemctl start portfolio-analytics-prune.service
sudo journalctl -u portfolio-analytics-prune.service --no-pager -n 20
```

`ANALYTICS_RETENTION_DAYS` accepts 1–3650 (default 90). Cleanup deletes only analytics records, not users or website content. The daily schedule allows up to roughly one extra day before removal. Database backups and Nginx logs have their own retention. Full IPs are retained for the requested IP list; describe this collection in your site's privacy information. To pause collection, set `ANALYTICS_ENABLED=false` and restart `portfolio`; existing reports remain available. `REACT_APP_ANALYTICS_ENABLED=false` also disables the client tracker at frontend build time.

## Verify

If a phone visit does not change the dashboard, use a Private/Incognito tab on the **public website** and then click **Refresh stats** in analytics with the IP filter cleared. Signed-in staff sessions and privacy opt-outs intentionally return 204 without storing a page view, so a 204 response alone does not prove that a new row was saved. A shared home Wi-Fi address also will not increase the unique-IP total, although it should increase page views. If every recorded address is `127.0.0.1`, finish the proxy setup above; the old rows cannot be retroactively assigned their real visitor addresses.

1. Visit the public site from a browser without an admin session; navigate between two pages. In browser Network tools, the page-view POSTs should return 204.
2. As the superuser, open analytics over the VPN. Confirm those pages and the expected visitor IP appear. `127.0.0.1` or a Cloudflare edge IP indicates an incomplete proxy setup.
3. Try each tool with a staff account before and after granting its permission. Confirm unrelated tools remain hidden and return 403 even when their URL is entered directly.
4. Revoke camera access during a stream and confirm it stops. Revoke system health permission and confirm the next metrics request fails.
5. Confirm public `https://davyin.tech/admin/analytics/` still returns 404, and the private route requires login. No analytics read API is exposed publicly.

Local automated checks:

```sh
DJANGO_DEBUG=true DATABASE_URL=sqlite:///:memory: .venv/bin/python backend/manage.py test portfolio system_monitor visitor_analytics
CI=true npm test -- --watchAll=false --runInBand
CI=true GENERATE_SOURCEMAP=false npm run build
```

CI also runs the backend tests against PostgreSQL. Tests cover count aggregation, date/IP filtering, pagination, spoofed forwarding headers, malformed payloads, rate limiting, deduplication, origin checks, opt-out signals, cleanup, direct and group grants, revocation, camera stream termination, and owner-only account management.
