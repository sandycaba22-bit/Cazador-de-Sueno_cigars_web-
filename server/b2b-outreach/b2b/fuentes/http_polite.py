from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

USER_AGENT = (
    "CazadorDeSuenos-B2B-Research/1.0 "
    "(+https://www.cazadordesuenocigar.com/wholesale.html; contacto mayorista)"
)
DOMAIN_LAST_FETCH: dict[str, float] = {}
MIN_INTERVAL = 3.0
TIMEOUT = 30


def _dominio(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _robots_url(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}/robots.txt"


def permitido_robots(url: str) -> bool:
    try:
        req = urllib.request.Request(_robots_url(url), headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            robots = resp.read(100_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return False
    path = urllib.parse.urlparse(url).path or "/"
    reglas: dict[str, list[str]] = {"*": []}
    agent = "*"
    for line in robots.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        low = line.lower()
        if low.startswith("user-agent:"):
            agent = line.split(":", 1)[1].strip()
            reglas.setdefault(agent, [])
        elif low.startswith("disallow:"):
            reglas.setdefault(agent, []).append(line.split(":", 1)[1].strip())
    for key in ("*", agent):
        for rule in reglas.get(key, []):
            if rule and path.startswith(rule):
                return False
    return True


def fetch_url(url: str) -> str:
    dom = _dominio(url)
    ahora = time.time()
    ultimo = DOMAIN_LAST_FETCH.get(dom, 0.0)
    if ahora - ultimo < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - (ahora - ultimo))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read(800_000)
    DOMAIN_LAST_FETCH[dom] = time.time()
    return raw.decode("utf-8", errors="replace")
