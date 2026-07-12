"""Amazon.jobs public search JSON.
Verified 2026-07-12: params base_query/country/sort/result_limit all work
(371 India software-engineer hits at time of writing).
"""
from urllib.parse import quote_plus

from .common import get_json, job


def fetch(cfg, settings):
    q = quote_plus(settings["search_text"])
    url = (f"https://www.amazon.jobs/en/search.json?base_query={q}"
           f"&country=IND&sort=recent&result_limit=30")
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data.get("jobs", []):
        out.append(job(
            source="amazon",
            company=cfg["name"],
            jid=j.get("id_icims") or j.get("id", ""),
            title=j.get("title", ""),
            location=j.get("normalized_location") or j.get("location", ""),
            url="https://www.amazon.jobs" + j.get("job_path", ""),
            posted_at=j.get("posted_date", ""),
        ))
    return out
