"""Google Careers - HTML fallback.

The old careers.google.com/api/v3/search API is DEAD (verified 2026-07-12:
returns {"detail":"Not Found"}). The public search results page still
works and contains job links server-side:
  https://www.google.com/about/careers/applications/jobs/results?q=...&location=India
Job links look like: jobs/results/123456789012345678-software-engineer...

This is the most fragile source (HTML can change). If it starts
returning 0 jobs every run, check the page manually and adjust the regex.
"""
import re

import requests

from .common import HEADERS, job

# id (long digits) + slug from anchors in the results page HTML
JOB_LINK_RE = re.compile(r'jobs/results/(\d{10,25})-([a-z0-9-]+)')


def _slug_to_title(slug):
    """'software-engineer-iii-google-cloud' -> 'Software Engineer Iii Google Cloud'."""
    return " ".join(w.capitalize() for w in slug.split("-"))


def fetch(cfg, settings):
    q = settings["search_text"].replace(" ", "%20")
    url = (f"https://www.google.com/about/careers/applications/jobs/results"
           f"?q={q}&location=India")
    r = requests.get(url, headers={**HEADERS, "Accept": "text/html"},
                     timeout=settings["request_timeout"])
    r.raise_for_status()
    seen, out = set(), []
    for jid, slug in JOB_LINK_RE.findall(r.text):
        if jid in seen:
            continue
        seen.add(jid)
        out.append(job(
            source="google_html",
            company=cfg["name"],
            jid=jid,
            title=_slug_to_title(slug),
            location="India",  # the query itself is India-filtered
            url=(f"https://www.google.com/about/careers/applications/"
                 f"jobs/results/{jid}-{slug}"),
            posted_at="",
        ))
    return out
