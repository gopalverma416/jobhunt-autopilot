"""Shared helpers for all fetchers.

Every fetcher returns a list of "normalized job" dicts:
    {id, title, company, location, url, posted_at, source}
posted_at is an ISO date string when the ATS provides it, else "".
"""
import requests

# Polite, identifiable User-Agent (some APIs 403 blank/bot-looking UAs).
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) JobHuntAutopilot/1.0 "
        "(personal job-alert bot; low volume; 1 req/source/hour)"
    ),
    "Accept": "application/json",
}


def get_json(url, timeout):
    """GET a URL and parse JSON. Raises on HTTP errors (watcher catches them)."""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def post_json(url, body, timeout):
    """POST a JSON body and parse the JSON response."""
    r = requests.post(url, json=body, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


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
