"""Ashby public posting API.
Docs: https://developers.ashbyhq.com/docs/public-job-posting-api
No current target company uses Ashby (kept for future additions -
many newer startups are on it; add `{name: X, ats: ashby, slug: x}`).
"""
from .common import get_json, job


def fetch(cfg, settings):
    slug = cfg["slug"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false"
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data.get("jobs", []):
        out.append(job(
            source=f"ashby:{slug}",
            company=cfg["name"],
            jid=j.get("id", j.get("jobUrl", "")),
            title=j.get("title", ""),
            location=j.get("location", ""),
            url=j.get("jobUrl") or j.get("applyUrl", ""),
            posted_at=(j.get("publishedAt") or "")[:10],
        ))
    return out
