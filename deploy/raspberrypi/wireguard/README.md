# Raspberry Pi WireGuard admin VPN

This is the detailed setup and operations guide for the self-hosted WireGuard VPN protecting Django admin on the portfolio Pi. The Pi is the always-on server; your Mac is a peer (VPN client). WireGuard is free and uses public/private keys to authenticate peers. The tunnel is a **split tunnel**: it carries traffic only to the Pi's VPN IP, not all Mac internet traffic.

## How the request flows

```text
Mac WireGuard client
  └─ encrypted UDP to vpn.davyin.tech:51820
       └─ router forwards UDP 51820 to Pi 192.168.1.132
            └─ WireGuard wg0: Pi 10.66.66.1 ↔ Mac 10.66.66.3
                 └─ Mac opens http://10.66.66.1:8080/admin/ (and /admin/camera/)
                      └─ Nginx permits only 10.66.66.0/24, then proxies to Django
```

The public portfolio remains on `https://davyin.tech/`. Public requests to `/admin` and every `/admin/*` path, including the camera page and stream, receive 404. The private Nginx listener is on port 8080 and only allows traffic sourced from the WireGuard subnet. WireGuard encrypts the connection between the Mac and Pi, so the private listener uses HTTP inside that tunnel.

## Current deployment and what remains

- Pi LAN address: `192.168.1.132`.
- WireGuard interface: `wg0`, Pi tunnel address `10.66.66.1/24`, UDP port `51820`.
- Mac peer: `10.66.66.3/32` (dedicated Mac key). The older `.2` peer was shared with an iPhone and should be revoked after that device is disabled.
- Endpoint: `vpn.davyin.tech:51820`. Its Cloudflare `A` record is DNS only, and the Pi's hourly DDNS updater now refreshes it.
- Admin URL when the Mac tunnel is active: `http://10.66.66.1:8080/admin/`.
- Mac's home and away profiles are `.wireguard/dawei-mac-home.conf` and `.wireguard/dawei-mac-away.conf`. Both use the unique `.3` peer; only activate one at a time. Git ignores `.wireguard/`; profiles are mode `600` and must not be committed, pasted, or shared.
- The Pi service is enabled at boot. Nginx config is valid. Pi-side tests confirmed public homepage 200, public `/admin/` 404, VPN-source request to port 8080 200, and a non-VPN source to port 8080 403.
- **Remote access:** the user tested from an external network and received HTTP 200 with a Django CSRF cookie from the admin login route. That confirms the remote VPN path reached Django. For a server-side handshake timestamp and counters, run `sudo wg show wg0` on the Pi.

## Values used here

| Item | Value |
| --- | --- |
| SSH target | `dawei@raspberrypi.local` |
| Pi LAN IPv4 | `192.168.1.132` |
| Pi VPN IPv4 | `10.66.66.1` |
| Mac VPN IPv4 | `10.66.66.3` |
| Existing iPhone VPN IPv4 | `10.66.66.2` (revoke after disabling the old profile) |
| WireGuard port | UDP `51820` |
| Private admin listener | TCP `8080` on the VPN path; do not port-forward it |
| Cloudflare VPN hostname | `vpn.davyin.tech`, DNS-only A record |
| Mac home/away profiles | `/Users/dawei/fun/davvyin.github.io/.wireguard/dawei-mac-home.conf` and `dawei-mac-away.conf` |

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

In a **client profile**, `[Interface]` means this device (Mac address `.3` in the current profile), while `[Peer]` means the Pi server (`10.66.66.1`). In the Pi's `/etc/wireguard/wg0.conf`, the meanings are reversed: its `[Interface]` is the Pi and each `[Peer]` is a client device. Give every device its own key and tunnel IP; do not copy one client's profile to another.

The Mac's `AllowedIPs` is a `/32` for only the Pi VPN address. Do not change it to `0.0.0.0/0` unless you intend to route all IPv4 traffic through the Pi. The server peer's `AllowedIPs` binds each client key to only that device's `/32` address. Persistent keepalive sends a small periodic packet so the Mac's NAT mapping stays usable while it is away from home; WireGuard's [quick start](https://www.wireguard.com/quickstart/) explains the key and keepalive settings.

## Add a peer for another device

The Pi's tunnel address `10.66.66.1` is reserved for the server. Pick an unused client address in `10.66.66.0/24`; the recorded setup currently has the legacy iPhone peer at `.2` and the dedicated Mac peer at `.3`. Use `.4` for the next device, or check `sudo wg show wg0` and choose another unused address. Never assign `.1` to a client or reuse a key/profile across devices.

On the Pi, replace `tablet` and `10.66.66.4` below with the new device name and unused IP. This creates a new key and preshared key, adds the peer to the running interface without restarting WireGuard, and saves a one-time client profile in `/home/dawei/` with mode 600:

```sh
sudo bash <<'ROOT'
set -eu
umask 077
CLIENT_NAME=tablet
CLIENT_IP=10.66.66.4
if wg show wg0 allowed-ips | grep -Fq "$CLIENT_IP/32"; then
  echo "That client IP is already assigned; choose another one." >&2
  exit 1
fi
CLIENT_PRIVATE=$(wg genkey)
CLIENT_PUBLIC=$(printf '%s' "$CLIENT_PRIVATE" | wg pubkey)
CLIENT_PSK=$(wg genpsk)
SERVER_PUBLIC=$(wg show wg0 | awk '/public key:/ {print $3; exit}')
PSK_FILE=$(mktemp /run/wg-peer-psk.XXXXXX)
printf '%s\n' "$CLIENT_PSK" > "$PSK_FILE"
chmod 600 "$PSK_FILE"
cp -a /etc/wireguard/wg0.conf "/etc/wireguard/wg0.conf.before-${CLIENT_NAME}-$(date +%Y%m%d-%H%M%S)"
cat >> /etc/wireguard/wg0.conf <<EOF

[Peer]
PublicKey = ${CLIENT_PUBLIC}
PresharedKey = ${CLIENT_PSK}
AllowedIPs = ${CLIENT_IP}/32
EOF
chmod 600 /etc/wireguard/wg0.conf
wg set wg0 peer "$CLIENT_PUBLIC" preshared-key "$PSK_FILE" allowed-ips "$CLIENT_IP/32"
rm -f "$PSK_FILE"
cat > "/home/dawei/${CLIENT_NAME}.conf" <<EOF
[Interface]
PrivateKey = ${CLIENT_PRIVATE}
Address = ${CLIENT_IP}/32

[Peer]
PublicKey = ${SERVER_PUBLIC}
PresharedKey = ${CLIENT_PSK}
Endpoint = vpn.davyin.tech:51820
AllowedIPs = 10.66.66.1/32
PersistentKeepalive = 25
EOF
chown dawei:dawei "/home/dawei/${CLIENT_NAME}.conf"
chmod 600 "/home/dawei/${CLIENT_NAME}.conf"
unset CLIENT_PRIVATE CLIENT_PSK
printf 'Peer %s created for %s/32. Transfer /home/dawei/%s.conf securely.\n' "$CLIENT_PUBLIC" "$CLIENT_IP" "$CLIENT_NAME"
wg show wg0
ROOT
```

The generated profile's `[Interface]` is the new device; its `[Peer]` is the Pi. If the client is at home and the router lacks NAT loopback, change its `Endpoint` to `192.168.1.132:51820`; use `vpn.davyin.tech:51820` away from home. Transfer the profile with `scp`, store it only on that device with mode 600, and remove the temporary copy from the Pi after importing it. Never enable two profiles that share one peer key at the same time.

To revoke a device, first identify its public key with `sudo wg show wg0`, then remove that peer from the running interface using `sudo wg set wg0 peer PEER_PUBLIC_KEY remove`. Also remove its matching `[Peer]` block from `/etc/wireguard/wg0.conf` with `sudoedit`, so it does not return after a reboot. Keep the Pi's `[Interface]` and all other device peers intact.

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

The DDNS updater only updates existing records. Create the initial `vpn` A record in the Cloudflare dashboard, then ensure `CF_RECORD_NAMES` includes `vpn.davyin.tech` and run the updater once.

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

## 7. Copy and activate the current Mac peer

The first-time setup above uses `.2` as its example client. The live Pi now reserves `.2` for the old iPhone peer and has a separate Mac peer at `.3`. On the Mac, turn off any old `.2` WireGuard profile first, then copy the `.3` profiles if they are not already in the local ignored directory:

```sh
cd /Users/dawei/fun/davvyin.github.io
mkdir -p .wireguard
scp dawei@raspberrypi.local:/home/dawei/dawei-mac-home.conf .wireguard/dawei-mac-home.conf
scp dawei@raspberrypi.local:/home/dawei/dawei-mac-away.conf .wireguard/dawei-mac-away.conf
chmod 600 .wireguard/dawei-mac-home.conf .wireguard/dawei-mac-away.conf
git check-ignore .wireguard/dawei-mac-home.conf
```

The final command should report `.wireguard/` as ignored. Never commit or share the profiles; both contain the Mac's private key and preshared key. After securely copying them, delete the temporary copies from `/home/dawei` on the Pi.

Install the CLI with Homebrew:

```sh
brew install wireguard-tools
command -v wg
command -v wg-quick
command -v wireguard-go
```

Homebrew's `wireguard-tools` formula includes `wg`/`wg-quick` and depends on the userspace `wireguard-go` implementation. The [official WireGuard install page](https://www.wireguard.com/install/) lists this Mac CLI option. At home, activate the home endpoint and test the admin route:

```sh
cd /Users/dawei/fun/davvyin.github.io
sudo "$(brew --prefix)/bin/wg-quick" up "$PWD/.wireguard/dawei-mac-home.conf"
sudo "$(brew --prefix)/bin/wg" show
curl --connect-timeout 5 -I http://10.66.66.1:8080/admin/login/
```

The home profile uses `192.168.1.132:51820`; the away profile uses `vpn.davyin.tech:51820`. Only enable one profile at a time. When leaving home, stop the home profile and start the away profile. When finished, stop the active tunnel:

```sh
sudo "$(brew --prefix)/bin/wg-quick" down "$PWD/.wireguard/dawei-mac-home.conf"
```

The CLI tunnel is active until you stop it or restart the Mac. To use a GUI instead, install the official [WireGuard macOS app](https://www.wireguard.com/install/), import the matching home or away profile, and turn only that profile on. Do not keep the old `.2` Mac profile enabled.

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

For this deployment, WireGuard tools were installed on the Pi, `wg0` was configured at `10.66.66.1/24`, the original `.2` peer was used by an iPhone and later reused on the Mac, and a dedicated Mac peer `.3` was added to prevent that collision. The Pi has home and away Mac profiles using the `.3` key. The Cloudflare DNS-only `vpn.davyin.tech` A record is managed by the hourly updater. Nginx's public `/admin` routes are blocked and the private listener is limited to the WireGuard subnet. The user confirmed the router forwarding and successfully reached the admin login route from an external network.
