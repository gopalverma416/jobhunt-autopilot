"""SmartRecruiters public postings API.
Docs: https://developers.smartrecruiters.com/reference/postingsget-1
Verified 2026-07-12 (browser): Zomato1, Visa.
"""
from .common import get_json, job


def fetch(cfg, settings):
    slug = cfg["slug"]
    url = f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=100"
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data.get("content", []):
        loc = (j.get("location") or {}).get("fullLocation", "")
        # Posting page URL pattern used by SmartRecruiters career sites.
        posting_url = f"https://jobs.smartrecruiters.com/{slug}/{j['id']}"
        out.append(job(
            source=f"smartrecruiters:{slug}",
            company=cfg["name"],
            jid=j["id"],
            title=j.get("name", ""),
            location=loc,
            url=posting_url,
            posted_at=(j.get("releasedDate") or "")[:10],
        ))
    return out
