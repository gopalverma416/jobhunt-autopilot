"""Microsoft careers (Eightfold-based portal, July 2026).

The old gcsservices.careers.microsoft.com API is DEAD (verified 2026-07-12).
Current endpoint (discovered from the live site's network traffic):
  GET https://apply.careers.microsoft.com/api/pcsx/search
      ?domain=microsoft.com&query=...&location=India&start=0&sort_by=timestamp
Job page: https://apply.careers.microsoft.com/careers/job/{id}

sort_by=timestamp gives newest first - ideal for hourly polling.
"""
from datetime import datetime, timezone
from urllib.parse import quote_plus

from .common import get_json, job


def fetch(cfg, settings):
    q = quote_plus(settings["search_text"])
    url = (f"https://apply.careers.microsoft.com/api/pcsx/search"
           f"?domain=microsoft.com&query={q}&location=India"
           f"&start=0&sort_by=timestamp")
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in (data.get("data") or {}).get("positions", []):
        posted = ""
        if j.get("postedTs"):
            posted = datetime.fromtimestamp(
                j["postedTs"], tz=timezone.utc).date().isoformat()
        out.append(job(
            source="microsoft",
            company=cfg["name"],
            jid=j["id"],
            title=j.get("name", ""),
            location="; ".join(j.get("locations") or []),
            url=f"https://apply.careers.microsoft.com/careers/job/{j['id']}",
            posted_at=posted,
        ))
    return out
