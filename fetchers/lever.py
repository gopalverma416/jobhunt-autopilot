"""Lever public postings API.
Docs: https://github.com/lever/postings-api
Verified 2026-07-12: cred.
"""
from datetime import datetime, timezone

from .common import get_json, job


def fetch(cfg, settings):
    slug = cfg["slug"]
    url = f"https://api.lever.co/v0/postings/{slug}?mode=json"
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data:
        cats = j.get("categories") or {}
        loc = cats.get("location") or ", ".join(cats.get("allLocations") or [])
        created = j.get("createdAt")  # epoch millis
        posted = ""
        if created:
            posted = datetime.fromtimestamp(created / 1000, tz=timezone.utc).date().isoformat()
        out.append(job(
            source=f"lever:{slug}",
            company=cfg["name"],
            jid=j["id"],
            title=j.get("text", ""),
            location=loc,
            url=j.get("hostedUrl", ""),
            posted_at=posted,
        ))
    return out
