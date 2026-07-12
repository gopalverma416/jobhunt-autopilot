"""Atlassian careers listings endpoint (backs atlassian.com/company/careers).
Verified 2026-07-12: returns a JSON array of all open roles.
Schema: {id, title, locations: [..], category,
         portalJobPost: {portalUrl (icims apply link), updatedDate}}
This endpoint has no server-side filtering, so we filter locally.
"""
from .common import get_json, job


def fetch(cfg, settings):
    url = "https://www.atlassian.com/endpoint/careers/listings"
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data:
        portal = j.get("portalJobPost") or {}
        out.append(job(
            source="atlassian",
            company=cfg["name"],
            jid=j.get("id", ""),
            title=j.get("title", ""),
            location="; ".join(j.get("locations") or []),
            url=portal.get("portalUrl", "https://www.atlassian.com/company/careers/all-jobs"),
            posted_at="",  # only "updatedDate" is exposed; not a posting date
        ))
    return out
