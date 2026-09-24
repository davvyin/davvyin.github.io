"""Verify the deployed HTTP app using a temporary admin, removed on completion."""
import argparse
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request

APP = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(APP / "backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()
from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session

parser = argparse.ArgumentParser()
parser.add_argument("base_url", help="The deployed origin, e.g. http://192.168.1.132")
args = parser.parse_args()
base = args.base_url.rstrip("/")
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
checks = 0


def request(path, expected=200, data=None, headers=None):
    global checks
    req = urllib.request.Request(base + path, data=data, headers=headers or {})
    try:
        response = client.open(req, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    assert response.status == expected, (path, response.status)
    body = response.read()
    final_url = response.geturl()
    response.close()
    checks += 1
    return body, final_url


content = json.loads(request("/api/content/")[0])
assert json.loads(request("/healthz/")[0]) == {"status": "ok"}
for route in ["/", "/about", "/projects", "/contact", "/technologies"]:
    assert b'id="root"' in request(route)[0]
manifest = json.loads((APP / "build/asset-manifest.json").read_text())
for path in manifest["entrypoints"]:
    request("/" + path)
images = [content["personalDetails"]["img"], content["logos"]["logo"]]
images += [item["image"] for item in content["projectDetails"]]
images += [item["image"] for item in content["technologies"]]
for path in set(images):
    if path.startswith("/"):
        request(path)
for path in ["/static/admin/css/base.css", "/favicon/favicon.ico"]:
    request(path)
for path in ["/missing", "/api/missing/", "/static/missing.js"]:
    request(path, 404)
assert "/admin/login/" in request("/admin/")[1]
request("/api/content/", 403, data=b"{}")

password = secrets.token_urlsafe(32)
user = get_user_model().objects.create_superuser(
    "deploy-check-" + secrets.token_hex(8), password=password
)
try:
    request("/admin/login/?next=/admin/")
    token = next(cookie.value for cookie in cookies if cookie.name == "csrftoken")
    fields = {"username": user.username, "password": password,
              "csrfmiddlewaretoken": token, "next": "/admin/"}
    body, url = request("/admin/login/?next=/admin/", data=urllib.parse.urlencode(fields).encode(),
                        headers={"Referer": base + "/admin/login/", "Origin": base})
    assert urllib.parse.urlparse(url).path == "/admin/", "Admin login did not succeed"
    assert b"Portfolio administration" in body
    request("/admin/portfolio/profile/1/change/")
finally:
    for cookie in cookies:
        if cookie.name == "sessionid":
            Session.objects.filter(session_key=cookie.value).delete()
    user.delete()

assert get_user_model().objects.filter(username="dawei", is_active=True, is_superuser=True).exists()
print(f"Passed {checks} deployed HTTP checks, including a CSRF-protected admin login. Temporary account removed.")
