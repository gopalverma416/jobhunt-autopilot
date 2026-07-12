"""Shared helpers for all fetchers (v2.2: datacenter-IP resilience).

Every fetcher returns a list of "normalized job" dicts:
    {id, title, company, location, url, posted_at, source}
posted_at is an ISO date string when the ATS provides it, else "".

Resilience layer: GitHub Actions runs from Azure datacenter IPs, which big
ATS/CDN stacks (Workday, Akamai, Cloudflare) sometimes rate-limit or 403.
We can't use paid proxies (₹0 budget), so we do the free, polite things:
  - rotate a small set of real browser User-Agent strings per request
  - add a little random jitter so N concurrent fetchers don't hit as a burst
  - on 403/429/503, back off and retry once with a different UA
One source still failing after that just logs FAIL upstream and is skipped.
"""
import random
import time

import requests

# A few realistic desktop UA strings. Rotating these is the cheapest way to
# look less like a single scripted client from one datacenter IP.
_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]

# Status codes worth one polite retry (transient / soft-block).
_RETRY_STATUS = {403, 429, 500, 502, 503, 504}

# Kept for callers that imported HEADERS directly (jd.py, tg_channels.py).
HEADERS = {"User-Agent": _USER_AGENTS[0], "Accept": "application/json"}


def _headers(accept="application/json"):
    return {
        "User-Agent": random.choice(_USER_AGENTS),
        "Accept": accept,
        "Accept-Language": "en-US,en;q=0.9",
    }


def _request(method, url, timeout, *, json_body=None, accept="application/json"):
    """One request with UA rotation, tiny jitter, and a single backoff retry
    on soft-block status codes. Raises on the final failure."""
    time.sleep(random.uniform(0, 0.4))  # spread concurrent fetchers
    last_exc = None
    for attempt in range(2):
        try:
            r = requests.request(method, url, headers=_headers(accept),
                                  json=json_body, timeout=timeout)
            if r.status_code in _RETRY_STATUS and attempt == 0:
                # honour Retry-After if present, else short backoff
                wait = r.headers.get("Retry-After")
                time.sleep(min(float(wait), 5) if (wait or "").isdigit() else 1.5)
                continue
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            last_exc = e
            if attempt == 0:
                time.sleep(1.0)
                continue
            raise
    raise last_exc  # pragma: no cover


def get_json(url, timeout):
    """GET a URL and parse JSON. Raises on HTTP errors (watcher catches them)."""
    return _request("GET", url, timeout).json()


def get_text(url, timeout):
    """GET a URL as text (HTML sources). Raises on HTTP errors."""
    return _request("GET", url, timeout, accept="text/html").text


def post_json(url, body, timeout):
    """POST a JSON body and parse the JSON response."""
    return _request("POST", url, timeout, json_body=body).json()


def job(source, company, jid, title, location, url, posted_at=""):
    """Build a normalized job dict. jid is coerced to str for stable dedupe keys."""
    return {
        "id": str(jid),
        "title": (title or "").strip(),
        "company": company,
        "location": (location or "").strip(),
        "url": url,
        "posted_at": posted_at or "",
        "source": source,
    }
