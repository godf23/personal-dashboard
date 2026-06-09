import json
import urllib.request

BASE = "http://127.0.0.1:8765"


def req(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    headers = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(BASE + path, data=body, method=method, headers=headers)
    with urllib.request.urlopen(r) as resp:
        return json.loads(resp.read())


print("status", req("GET", "/api/status"))
link = req("POST", "/api/links", {"title": "Google", "url": "https://google.com"})
print("link", link)
print("click", req("POST", f"/api/links/{link['id']}/click"))
print("links", req("GET", "/api/links?sort=most_used"))
w = req("POST", "/api/weather/locations", {"label": "San Diego, CA"})
print("weather loc", w)
n = req("POST", "/api/news/locations", {"label": "California"})
print("news loc", n)
print("settings", req("GET", "/api/settings"))
print("proxmox", req("GET", "/api/proxmox/stats"))
