"""Full job-description fetching + experience filtering (v2, Feature 1).

Endpoints verified live 2026-07-12:
  Greenhouse  GET boards-api.greenhouse.io/v1/boards/{slug}/jobs/{id}   -> content (HTML-escaped)
  Lever       GET api.lever.co/v0/postings/{slug}/{id}                  -> descriptionPlain + lists
  SmartRecr.  GET api.smartrecruiters.com/v1/companies/{slug}/postings/{id} -> jobAd.sections.*.text
  Workday     GET {tenant}.wd{N}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{externalPath}
                                                                        -> jobPostingInfo.jobDescription
  Microsoft   GET apply.careers.microsoft.com/api/pcsx/position_details -> data.jobDescription
Amazon / Atlassian / Ashby / Lever also embed the JD in the list response;
those fetchers attach it as job["_jd"] so no extra request is needed.
Google (HTML source) has no JD -> caller falls back to title-only + ⚠️ tag.
"""
import html
import re

import requests

from fetchers.common import HEADERS

TAG_RE = re.compile(r"<[^>]+>")


def strip_html(s):
    """HTML -> plain text. Unescape twice: Greenhouse double-escapes content."""
    if not s:
        return ""
    s = html.unescape(html.unescape(str(s)))
    s = TAG_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _get(url, timeout):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def fetch_jd(job, company_cfg, settings):
    """Return the plain-text JD for a normalized job, or None if unavailable.
    Raises on network errors (caller treats that as 'JD unverified')."""
    if job.get("_jd"):
        return strip_html(job["_jd"]) or None

    src, jid = job["source"], job["id"]
    timeout = settings["request_timeout"]

    if src.startswith("greenhouse:"):
        slug = src.split(":", 1)[1]
        d = _get(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{jid}", timeout)
        return strip_html(d.get("content", "")) or None

    if src.startswith("lever:"):
        slug = src.split(":", 1)[1]
        d = _get(f"https://api.lever.co/v0/postings/{slug}/{jid}", timeout)
        parts = [d.get("descriptionPlain", "")]
        parts += [strip_html(l.get("content", "")) for l in d.get("lists", [])]
        return re.sub(r"\s+", " ", " ".join(parts)).strip() or None

    if src.startswith("smartrecruiters:"):
        slug = src.split(":", 1)[1]
        d = _get(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{jid}", timeout)
        secs = (d.get("jobAd") or {}).get("sections") or {}
        texts = [s.get("text", "") for s in secs.values() if isinstance(s, dict)]
        return strip_html(" ".join(texts)) or None

    if src.startswith("workday:"):
        tenant, site = src.split(":", 1)[1].split("/", 1)
        wd = (company_cfg or {}).get("wd", 5)
        # jid IS the externalPath (starts with /job/...)
        d = _get(f"https://{tenant}.wd{wd}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{jid}", timeout)
        return strip_html((d.get("jobPostingInfo") or {}).get("jobDescription", "")) or None

    if src == "microsoft":
        d = _get(f"https://apply.careers.microsoft.com/api/pcsx/position_details"
                 f"?position_id={jid}&domain=microsoft.com", timeout)
        return strip_html((d.get("data") or {}).get("jobDescription", "")) or None

    return None  # google_html and unknown sources: no JD available


# ------------------------- experience analysis -------------------------

# "up to 2 years" is a fresher-friendly phrase - remove it before scanning.
UPTO_RE = re.compile(r"\bup\s*to\s*\d{1,2}\s*(?:years?|yrs?)\b")
# "2-4 years", "0 to 1 year", "8 to 12 or more years"
RANGE_RE = re.compile(r"(\d{1,2})\s*(?:-|–|—|to)\s*(\d{1,2})\s*(?:\+|or more)?\s*(?:years?|yrs?)\b")
# "minimum of 3 years", "at least 4 yrs"
MIN_RE = re.compile(r"(?:minimum(?:\s+of)?|at\s*least)\s*(\d{1,2})\s*\+?\s*(?:years?|yrs?)\b")
# "3+ years"
PLUS_RE = re.compile(r"(\d{1,2})\s*\+\s*(?:years?|yrs?)\b")
# "5 years of professional ... experience"
BARE_RE = re.compile(r"(\d{1,2})\s*(?:years?|yrs?)\s+of\s+(?:[\w-]+\s+){0,4}?experience\b")


def analyze_jd(text, jdcfg):
    """Scan JD text for experience requirements.
    Returns {"verdict": pass|borderline|reject, "reason": str, "fresher": bool}.
    Thresholds and pattern lists come from companies.yaml -> filters.jd."""
    t = " " + text.lower() + " "
    fresher = any(re.search(p, t, re.I) for p in jdcfg.get("fresher_patterns", []))
    t = UPTO_RE.sub(" ", t)

    worst, reason = 0, ""          # 0=pass 1=borderline 2=reject

    def bump(level, why):
        nonlocal worst, reason
        if level > worst:
            worst, reason = level, why

    # Ranges first, then remove them so "0-2 years" can't re-match as "2 years".
    for m in RANGE_RE.finditer(t):
        lo, hi = int(m.group(1)), int(m.group(2))
        if lo >= jdcfg.get("range_reject_min", 3):
            bump(2, f"requires {lo}-{hi} years")
        elif lo >= jdcfg.get("range_borderline_min", 2):
            bump(1, f"{lo}-{hi} yrs")
    t = RANGE_RE.sub(" ", t)

    for rx in (MIN_RE, PLUS_RE, BARE_RE):
        for m in rx.finditer(t):
            n = int(m.group(1))
            if n >= jdcfg.get("hard_reject_years", 3):
                bump(2, f"requires {n}+ years")
            elif n >= jdcfg.get("borderline_years", 2):
                bump(1, f"{n}+ yrs")
        t = rx.sub(" ", t)

    for p in jdcfg.get("extra_reject_patterns", []):
        if re.search(p, t, re.I):
            bump(2, f"matched custom pattern: {p}")

    return {"verdict": ("pass", "borderline", "reject")[worst],
            "reason": reason, "fresher": fresher}
