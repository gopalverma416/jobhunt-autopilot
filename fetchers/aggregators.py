"""ToS-safe job aggregators (v2.3, Feature 1C).

Unlike ATS fetchers (one company each), an aggregator returns jobs from MANY
companies, so the per-job company name comes from the feed, not the config.

Verified reachable 2026-07-14:
  - Adzuna India: official REST API, India endpoint, FREE key required.
      Very India-relevant. Get a free key at https://developer.adzuna.com/
      then add GitHub secrets ADZUNA_APP_ID + ADZUNA_APP_KEY. Skipped if unset.
  - RemoteOK: public JSON at https://remoteok.com/api, no key. All-remote
      roles (global) - lower India-fresher yield but free; seniority is
      handled by the JD + Gemini filters downstream.
"""
import os

from .common import get_json, job


def _adzuna(cfg, settings):
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        # optional source - no key means quietly skip (not an error)
        return []
    what = settings["search_text"].replace(" ", "%20")
    url = (f"https://api.adzuna.com/v1/api/jobs/in/search/1"
           f"?app_id={app_id}&app_key={app_key}"
           f"&results_per_page=50&what={what}&max_days_old=7&sort_by=date"
           f"&content-type=application/json")
    data = get_json(url, settings["request_timeout"])
    out = []
    for j in data.get("results", []):
        o = job(
            source="adzuna",
            company=(j.get("company") or {}).get("display_name", "Unknown"),
            jid=j.get("id", j.get("redirect_url", "")),
            title=j.get("title", ""),
            location=(j.get("location") or {}).get("display_name", ""),
            url=j.get("redirect_url", ""),
            posted_at=(j.get("created") or "")[:10],
        )
        o["_jd"] = j.get("description", "")
        out.append(o)
    return out


def _remoteok(cfg, settings):
    data = get_json("https://remoteok.com/api", settings["request_timeout"])
    out = []
    for j in data:
        # first element is a legal/notice object with no 'id' position
        if not isinstance(j, dict) or not j.get("position"):
            continue
        loc = j.get("location") or ""
        # every RemoteOK role is remote - tag it so the location filter passes
        loc = f"Remote - {loc}" if loc else "Remote"
        o = job(
            source="remoteok",
            company=j.get("company", "Unknown"),
            jid=j.get("id", j.get("slug", "")),
            title=j.get("position", ""),
            location=loc,
            url=j.get("url") or j.get("apply_url", ""),
            posted_at=(j.get("date") or "")[:10],
        )
        o["_jd"] = j.get("description", "")
        out.append(o)
    return out


def fetch(cfg, settings):
    """Dispatch on cfg['feed'] so one 'aggregator' ATS type serves several."""
    feed = cfg.get("feed")
    if feed == "adzuna":
        return _adzuna(cfg, settings)
    if feed == "remoteok":
        return _remoteok(cfg, settings)
    raise ValueError(f"unknown aggregator feed: {feed!r}")
