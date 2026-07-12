"""Greenhouse public job-board API.
Docs: https://developers.greenhouse.io/job-board.html
Verified 2026-07-12: phonepe, postman, rubrik, canonical, groww,
razorpaysoftwareprivatelimited, arcesiumllc.
"""
from .common import get_json, job


def fetch(cfg, settings):
    slug = cfg["slug"]
    url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data.get("jobs", []):
        out.append(job(
            source=f"greenhouse:{slug}",
            company=cfg["name"],
            jid=j["id"],
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            posted_at=(j.get("first_published") or j.get("updated_at") or "")[:10],
        ))
    return out
