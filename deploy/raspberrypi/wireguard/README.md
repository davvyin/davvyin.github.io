# Raspberry Pi WireGuard admin VPN

This is the detailed setup and operations guide for the self-hosted WireGuard VPN protecting Django admin on the portfolio Pi. The Pi is the always-on server; your Mac is a peer (VPN client). WireGuard is free and uses public/private keys to authenticate peers. The tunnel is a **split tunnel**: it carries traffic only to the Pi's VPN IP, not all Mac internet traffic.

## How the request flows

```text
Mac WireGuard client
  └─ encrypted UDP to vpn.davyin.tech:51820
       └─ router forwards UDP 51820 to Pi 192.168.1.132
            └─ WireGuard wg0: Pi 10.66.66.1 ↔ Mac 10.66.66.2
                 └─ Mac opens http://10.66.66.1:8080/admin/ (and /admin/camera/)
                      └─ Nginx permits only 10.66.66.0/24, then proxies to Django
```

The public portfolio remains on `https://davyin.tech/`. Public requests to `/admin` and every `/admin/*` path, including the camera page and stream, receive 404. The private Nginx listener is on port 8080 and only allows traffic sourced from the WireGuard subnet. WireGuard encrypts the connection between the Mac and Pi, so the private listener uses HTTP inside that tunnel.

## Current deployment and what remains

- Pi LAN address: `192.168.1.132`.
- WireGuard interface: `wg0`, Pi tunnel address `10.66.66.1/24`, UDP port `51820`.
- Mac peer: `10.66.66.2/32`.
- Endpoint: `vpn.davyin.tech:51820`. Its Cloudflare `A` record is DNS only, and the Pi's hourly DDNS updater now refreshes it.
- Admin URL when the Mac tunnel is active: `http://10.66.66.1:8080/admin/`.
- Mac's private profile is at `.wireguard/dawei-mac.conf` in the local repo checkout. Git ignores `.wireguard/`; the file is mode `600`. It contains a private key and must not be committed, pasted, or shared.
- The Pi service is enabled at boot. Nginx config is valid. Pi-side tests confirmed public homepage 200, public `/admin/` 404, VPN-source request to port 8080 200, and a non-VPN source to port 8080 403.
- **Remote access:** the user tested from an external network and received HTTP 200 with a Django CSRF cookie from the admin login route. That confirms the remote VPN path reached Django. For a server-side handshake timestamp and counters, run `sudo wg show wg0` on the Pi.

## Values used here

| Item | Value |
| --- | --- |
| SSH target | `dawei@raspberrypi.local` |
| Pi LAN IPv4 | `192.168.1.132` |
| Pi VPN IPv4 | `10.66.66.1` |
| Mac VPN IPv4 | `10.66.66.2` |
| WireGuard port | UDP `51820` |
| Private admin listener | TCP `8080` on the VPN path; do not port-forward it |
| Cloudflare VPN hostname | `vpn.davyin.tech`, DNS-only A record |
| Mac profile | `/Users/dawei/fun/davvyin.github.io/.wireguard/dawei-mac.conf` |

Commands below are split into **Mac** and **Pi** sections. Commands in “fresh install” sections are reference instructions; do not regenerate keys over this live setup unless you intend to replace the current peer credentials.

## 1. Check the Pi and install WireGuard

From the Mac, connect and inspect the Pi:

```sh
ssh dawei@raspberrypi.local
```

On the Pi:

```sh
hostname -I
uname -m
cat /etc/os-release
command -v wg || true
```

On Raspberry Pi OS/Debian, install the tools and prepare the protected config directory:

```sh
sudo apt update
sudo apt install -y wireguard-tools
sudo install -d -o root -g root -m 700 /etc/wireguard
```

The deployed Pi uses Debian's `wireguard-tools` package. WireGuard runs as a kernel network interface and `wg-quick` wraps interface, address, and route setup.

## 2. Generate server and Mac peer keys (fresh setup only)

Run on the Pi. The redirections write private keys to files; the private values are not printed:

```sh
sudo bash <<'ROOT'
set -eu
umask 077
wg genkey > /etc/wireguard/server.key
wg pubkey < /etc/wireguard/server.key > /etc/wireguard/server.pub
wg genkey > /etc/wireguard/mac.key
wg pubkey < /etc/wireguard/mac.key > /etc/wireguard/mac.pub
wg genpsk > /etc/wireguard/mac.psk
chmod 600 /etc/wireguard/*.key /etc/wireguard/*.psk
chmod 644 /etc/wireguard/*.pub
ROOT
```

Create the server configuration on the Pi. This command reads keys from the protected files and writes the resulting configuration as root:

```sh
sudo bash <<'ROOT'
set -eu
umask 077
server_private=$(cat /etc/wireguard/server.key)
mac_public=$(cat /etc/wireguard/mac.pub)
preshared=$(cat /etc/wireguard/mac.psk)
cat > /etc/wireguard/wg0.conf <<EOF
[Interface]
Address = 10.66.66.1/24
ListenPort = 51820
PrivateKey = ${server_private}

[Peer]
PublicKey = ${mac_public}
PresharedKey = ${preshared}
AllowedIPs = 10.66.66.2/32
EOF
chmod 600 /etc/wireguard/wg0.conf
ROOT
```

Create a client profile on the Pi. It contains the Mac's private key, so keep it mode 600 and transfer it only over SSH:

```sh
sudo bash <<'ROOT'
set -eu
umask 077
mac_private=$(cat /etc/wireguard/mac.key)
server_public=$(cat /etc/wireguard/server.pub)
preshared=$(cat /etc/wireguard/mac.psk)
cat > /home/dawei/wireguard-mac.conf <<EOF
[Interface]
PrivateKey = ${mac_private}
Address = 10.66.66.2/32

[Peer]
PublicKey = ${server_public}
PresharedKey = ${preshared}
Endpoint = vpn.davyin.tech:51820
AllowedIPs = 10.66.66.1/32
PersistentKeepalive = 25
EOF
chown dawei:dawei /home/dawei/wireguard-mac.conf
chmod 600 /home/dawei/wireguard-mac.conf
ROOT
```

The Mac's `AllowedIPs` is a `/32` for only the Pi VPN address. Do not change it to `0.0.0.0/0` unless you intend to route all IPv4 traffic through the Pi. The server peer's `AllowedIPs` binds the Mac key to only `10.66.66.2`. Persistent keepalive sends a small periodic packet so the Mac's NAT mapping stays usable while it is away from home; WireGuard's [quick start](https://www.wireguard.com/quickstart/) explains the key and keepalive settings.

## 3. Enable WireGuard on the Pi

On the Pi:

```sh
sudo systemctl enable --now wg-quick@wg0
sudo systemctl status wg-quick@wg0 --no-pager
sudo wg show wg0
sudo ss -lunp | grep ':51820'
```

Expected: `wg-quick@wg0` is enabled and active, `wg show` reports listen port 51820 and a Mac peer, and `ss` shows UDP port 51820. There will not be a `latest handshake` until a client connects.

No IP forwarding or NAT masquerade is needed here: the VPN only provides access to services running on the Pi. It does not make other home-LAN devices reachable and does not route the Mac's normal internet traffic through the Pi.

## 4. Configure Cloudflare DNS and DDNS from the Pi

The public website's proxied DNS records are not the WireGuard endpoint. Create a separate **DNS-only** A record because regular Cloudflare proxying is for supported web traffic, not this WireGuard UDP endpoint.

The current deployment already has `vpn.davyin.tech` set to DNS-only and updated by the hourly job. On the Pi, verify without showing the API token:

```sh
sudo grep '^CF_RECORD_NAMES=' /etc/cloudflare-ddns.env
getent ahostsv4 vpn.davyin.tech
sudo systemctl start cloudflare-ddns.service
sudo journalctl -u cloudflare-ddns.service -n 20 --no-pager
```

For a new install, the Cloudflare token should have Zone Read and DNS Edit for `davyin.tech` and must be stored in `/etc/cloudflare-ddns.env`, owned by root with mode 600. Use `sudoedit /etc/cloudflare-ddns.env` and set these values (keep the existing token private):

```dotenv
CF_API_TOKEN=PASTE_TOKEN_IN_ROOT_EDITOR_ONLY
CF_ZONE_NAME=davyin.tech
CF_RECORD_NAMES=davyin.tech,www.davyin.tech,vpn.davyin.tech
```

Then enforce permissions:

```sh
sudo chown root:root /etc/cloudflare-ddns.env
sudo chmod 600 /etc/cloudflare-ddns.env
```

Create the initial DNS record in Cloudflare **DNS → Records**: Type `A`, Name `vpn`, IPv4 content equal to the current public IPv4, Proxy status **DNS only** (gray cloud), TTL Auto. After it exists, the updater changes its IP hourly. The updater intentionally edits existing A records only; it does not create or delete records. Never set the VPN record to Proxied.

To create or reconcile this record from the Pi CLI, run the Python block below after `/etc/cloudflare-ddns.env` has the token and zone. It reads the token from the protected file rather than placing it in a command argument. It fails if the name is a CNAME or has multiple A records:

```sh
sudo python3 - <<'PY'
from pathlib import Path
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

env = {
    key: value
    for line in Path('/etc/cloudflare-ddns.env').read_text().splitlines()
    if '=' in line and not line.lstrip().startswith('#')
    for key, value in [line.split('=', 1)]
}
token = env['CF_API_TOKEN'].strip()
zone_name = env['CF_ZONE_NAME'].strip().rstrip('.')
record_name = 'vpn.' + zone_name
base = 'https://api.cloudflare.com/client/v4'
headers = {
    'Authorization': 'Bearer ' + token,
    'Accept': 'application/json',
    'Content-Type': 'application/json',
}

def api(path, method='GET', payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        raise SystemExit(f'Cloudflare API HTTP {exc.code}: {exc.read(500).decode(errors="replace")}')
    if not result.get('success'):
        raise SystemExit('Cloudflare API error: ' + '; '.join(e['message'] for e in result.get('errors', [])))
    return result['result']

ip = str(ipaddress.IPv4Address(urllib.request.urlopen('https://api4.ipify.org', timeout=15).read().decode().strip()))
zones = api('/zones?' + urllib.parse.urlencode({'name': zone_name, 'status': 'active'}))
if len(zones) != 1:
    raise SystemExit(f'Expected exactly one active zone for {zone_name}; found {len(zones)}')
zone_id = zones[0]['id']
records = api(f'/zones/{zone_id}/dns_records?' + urllib.parse.urlencode({'name': record_name, 'per_page': 100}))
if any(r['type'] != 'A' for r in records):
    raise SystemExit(f'{record_name} already has a non-A record; resolve that DNS conflict first')
if len(records) > 1:
    raise SystemExit(f'{record_name} has multiple A records; resolve duplicates first')

if records:
    record = records[0]
    payload = {k: record[k] for k in ('type', 'name', 'ttl', 'comment', 'tags', 'settings') if k in record}
    payload.update(content=ip, proxied=False)
    result = api(f'/zones/{zone_id}/dns_records/{record["id"]}', 'PUT', payload)
    action = 'updated'
else:
    result = api(f'/zones/{zone_id}/dns_records', 'POST', {
        'type': 'A', 'name': record_name, 'content': ip, 'ttl': 120,
        'proxied': False, 'comment': 'WireGuard endpoint; managed by Raspberry Pi DDNS',
    })
    action = 'created'
print(f'{action} {result["name"]} -> {result["content"]}; DNS-only={not result["proxied"]}')
PY
```

The token needs Cloudflare Zone Read and DNS Edit for this zone. The Python snippet prints only the DNS record result, never the token. After creating the A record, set `CF_RECORD_NAMES` to include `vpn.davyin.tech` in the environment file and run the DDNS service once.

Optional CLI check for the current public IPv4 and DNS answer:

```sh
curl -4 https://api4.ipify.org
dig +short A vpn.davyin.tech
```

They should show the same IPv4. If `dig` is unavailable, use `getent ahostsv4 vpn.davyin.tech` on the Pi.

## 5. Configure nginx and Django

The existing public HTTPS virtual host in `/etc/nginx/sites-available/portfolio` must contain these locations **before** its general `location /` proxy. This blocks the admin URL and all nested paths on the public site:

```nginx
location = /admin { return 404; }
location ^~ /admin/ { return 404; }
```

Edit the file with `sudoedit /etc/nginx/sites-available/portfolio`; preserve the existing public homepage proxy and TLS settings.

Create the private Nginx listener on the Pi:

```sh
sudo tee /etc/nginx/conf.d/wireguard-admin.conf >/dev/null <<'NGINX'
server {
    listen 8080;
    server_name _;

    allow 10.66.66.0/24;
    deny all;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto http;
        proxy_redirect off;
    }
}
NGINX
```

In `/srv/portfolio/app/.env`, append these values to the existing comma-separated lists; do not replace the existing domain values:

```dotenv
DJANGO_ALLOWED_HOSTS=...existing hosts...,10.66.66.1
DJANGO_CSRF_TRUSTED_ORIGINS=...existing origins...,http://10.66.66.1:8080
```

Use `sudoedit /srv/portfolio/app/.env`, preserving its existing owner and mode 600. Then validate and apply:

```sh
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl restart portfolio
sudo systemctl is-active nginx portfolio wg-quick@wg0
```

The port-8080 Nginx server listens on IPv4 but rejects requests unless the source is in the WireGuard subnet. Do not create a router forward for 8080. If UFW is already enabled, check `sudo ufw status`; allow WireGuard UDP and traffic arriving on `wg0` to port 8080, not public TCP 8080:

```sh
sudo ufw allow 51820/udp
sudo ufw allow in on wg0 from 10.66.66.0/24 to any port 8080 proto tcp
```

## 6. Router setup (not a generic CLI operation)

Router configuration is vendor-specific and cannot be changed through a standard Linux command on the Pi. Use the router's web admin page or its own vendor CLI/API. First reserve `192.168.1.132` for the Pi's Wi-Fi MAC address. Then add exactly this port-forward:

| Router field | Value |
| --- | --- |
| Protocol | UDP |
| External/WAN port | `51820` |
| Internal/LAN address | `192.168.1.132` |
| Internal port | `51820` |

Do not forward TCP 51820, TCP 8080, Django/Gunicorn port 8000, or PostgreSQL port 5432. Only UDP 51820 is needed for this VPN. If the router's WAN address is private or differs from the current public IP, the ISP may use CGNAT; ordinary port forwarding will not work through CGNAT.

## 7. Copy and activate the Mac profile with CLI

On the Mac, from the project checkout, ensure the local-only directory exists and retrieve the profile over SSH:

```sh
cd /Users/dawei/fun/davvyin.github.io
mkdir -p .wireguard
scp dawei@raspberrypi.local:/home/dawei/wireguard-mac.conf .wireguard/dawei-mac.conf
chmod 600 .wireguard/dawei-mac.conf
git check-ignore .wireguard/dawei-mac.conf
```

The final command should report `.wireguard/` as ignored. Never commit the profile. The Mac profile contains its private key and shared preshared key.

Install the CLI with Homebrew:

```sh
brew install wireguard-tools
command -v wg
command -v wg-quick
command -v wireguard-go
```

Homebrew's `wireguard-tools` formula includes `wg`/`wg-quick` and depends on the userspace `wireguard-go` implementation. The [official WireGuard install page](https://www.wireguard.com/install/) lists this Mac CLI option. Bring the tunnel up and test the admin route:

```sh
cd /Users/dawei/fun/davvyin.github.io
sudo "$(brew --prefix)/bin/wg-quick" up "$PWD/.wireguard/dawei-mac.conf"
sudo "$(brew --prefix)/bin/wg" show
curl --connect-timeout 5 -I http://10.66.66.1:8080/admin/login/
```

When finished, stop the tunnel:

```sh
sudo "$(brew --prefix)/bin/wg-quick" down "$PWD/.wireguard/dawei-mac.conf"
```

The CLI tunnel is active until you stop it or restart the Mac. To use a GUI instead, install the official [WireGuard macOS app](https://www.wireguard.com/install/), import `.wireguard/dawei-mac.conf`, and turn the tunnel on/off in the app.

## 8. Verify end-to-end connectivity

First activate the Mac tunnel from a network **outside** the home Wi-Fi (for example, a phone hotspot). On the Mac:

```sh
sudo "$(brew --prefix)/bin/wg" show
curl --connect-timeout 5 -I http://10.66.66.1:8080/admin/login/
```

The curl response should be HTTP 200. On the Pi, confirm a recent peer handshake:

```sh
sudo wg show wg0
```

Look for `latest handshake` and nonzero transfer counters. Then test public/private access:

```sh
# From the Mac, with VPN on:
curl --connect-timeout 5 -I http://10.66.66.1:8080/admin/login/
curl --connect-timeout 5 -I https://davyin.tech/
curl --connect-timeout 5 -I https://davyin.tech/admin/
```

Expected while WireGuard is **up**: `http://10.66.66.1:8080/admin/login/` returns 200, and `/admin/` returns 302 redirecting to the login page. The public homepage returns 200; public `https://davyin.tech/admin/` returns 404 by design. After `wg-quick down`, the private `10.66.66.1:8080` address should time out because that route exists only through the tunnel. Some routers lack NAT loopback, so test the public endpoint from outside home Wi-Fi; a failed public-endpoint test while inside the home does not prove the port-forward is wrong.

Do not use `https://davyin.tech/admin/` or `https://vpn.davyin.tech/admin/` to sign in. Those hostnames reach the public HTTPS virtual host, which intentionally hides every `/admin/*` path. The public page's Admin link points to `http://10.66.66.1:8080/admin/`; use it with the WireGuard tunnel active. HTTP here is carried inside the encrypted WireGuard tunnel; the public site's HTTPS configuration is unchanged. Other VPN clients can use that same address without DNS changes.

Pi-side checks:

```sh
sudo systemctl status wg-quick@wg0 nginx portfolio --no-pager
sudo ss -lunp | grep ':51820'
sudo nginx -t
sudo journalctl -u wg-quick@wg0 -n 100 --no-pager
sudo journalctl -u nginx -n 100 --no-pager
sudo journalctl -u cloudflare-ddns.service -n 50 --no-pager
```

The Pi passed its local HTTP and config checks. The user subsequently confirmed that a request from an external network received HTTP 200 from the admin login route, confirming end-to-end access. Do not mistake that login-page response for an authenticated Django session; log in with the existing staff account. `sudo wg show wg0` on the Pi shows the server-side latest handshake and transfer counters.

## 9. Common failures and recovery

| Symptom | Likely cause and check |
| --- | --- |
| No latest handshake | Confirm Mac tunnel is on; check `vpn.davyin.tech` resolves to current public IPv4; confirm router forwards UDP 51820 to `192.168.1.132`; check ISP/CGNAT. |
| Handshake works but admin times out | Check `wg show`, Nginx status, port-8080 source filter, `DJANGO_ALLOWED_HOSTS`, and Django logs. |
| Django returns 400 | Include `10.66.66.1` in `DJANGO_ALLOWED_HOSTS` (without scheme/port), then restart `portfolio`. |
| CSRF failure on admin login | Include `http://10.66.66.1:8080` in `DJANGO_CSRF_TRUSTED_ORIGINS`, then restart `portfolio`. |
| Nginx rejects config | Run `sudo nginx -t`; correct the indicated file/line before reloading. |
| Public admin still responds | Check both exact `/admin` and prefix `/admin/` locations are inside the active HTTPS server; run `sudo nginx -T` and reload after `nginx -t`. |
| VPN stopped after reboot | Run `sudo systemctl enable --now wg-quick@wg0`, then inspect `journalctl -u wg-quick@wg0`. |

To apply a WireGuard server config edit:

```sh
sudo chmod 600 /etc/wireguard/wg0.conf
sudo systemctl restart wg-quick@wg0
sudo wg show wg0
```

If a peer profile is lost or exposed, remove that peer from `/etc/wireguard/wg0.conf`, restart the service, and generate a new key/profile. Do not reuse a lost profile. Add one unique peer IP/key per device.

## Deployment history

For this deployment, WireGuard tools were installed on the Pi, `wg0` was configured at `10.66.66.1/24`, a separate Mac peer at `10.66.66.2/32` was generated, and the service was enabled at boot. The Cloudflare DNS-only `vpn.davyin.tech` A record was created and added to the hourly updater. Nginx's public `/admin` routes were blocked and a source-filtered private listener was added; Django host/CSRF settings were extended for the private URL. Tailscale was removed before joining any account. The user later confirmed the router forwarding and successfully reached the admin login route from an external network.
