"""Workday CXS job search API (used by Adobe, Salesforce, Qualcomm,
Mastercard, Walmart, Sprinklr, ...).

POST https://{tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs
body: {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "..."}

Verified live 2026-07-12 (adobe/external_experienced: 200 OK, real jobs).
We request sorted-by-default relevance with the configured search text;
20 results/run is plenty because we run hourly and dedupe.
"""
from .common import job, post_json


def fetch(cfg, settings):
    tenant, n, site = cfg["tenant"], cfg["wd"], cfg["site"]
    base = f"https://{tenant}.wd{n}.myworkdayjobs.com"
    url = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    body = {
        "appliedFacets": {},
        "limit": 20,
        "offset": 0,
        "searchText": settings["search_text"],
    }
    data = post_json(url, body, settings["request_timeout"])
    out = []
    for j in data.get("jobPostings", []):
        path = j.get("externalPath", "")
        if not path:
            continue
        out.append(job(
            source=f"workday:{tenant}/{site}",
            company=cfg["name"],
            jid=path,  # externalPath is unique and stable
            title=j.get("title", ""),
            location=j.get("locationsText", ""),
            url=f"{base}/en-US/{site}{path.replace('/job/', '/job/', 1)}"
                if path.startswith("/job/") else f"{base}/en-US/{site}{path}",
            posted_at="",  # CXS only gives "Posted X days ago" text
        ))
    return out
