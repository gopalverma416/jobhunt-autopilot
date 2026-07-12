"""Optional LLM match scoring via the Google Gemini free API (Feature: v2.2).

For each job that already passed the title + location + JD filters, ask
Gemini to score fit (0-100) against profile.md and return a one-line reason.
The tag `🎯 87/100` is added to the alert and the score feeds the dashboard.

FULLY OPTIONAL and FAIL-SAFE:
  - If GEMINI_API_KEY isn't set, scoring is skipped silently (jobs still alert).
  - Any API error -> that job just gets no score. Never blocks an alert.

Setup (free): create a key at https://aistudio.google.com/apikey , add it as
a GitHub Actions secret named GEMINI_API_KEY. Free tier easily covers the
0-5 new jobs/run this pipeline produces.

Model + endpoint are configurable in companies.yaml -> settings.gemini.
"""
import json
import os
import re
from pathlib import Path

import requests

PROFILE = Path(__file__).parent / "profile.md"

_PROMPT = """You are screening software-engineering jobs for a specific candidate.
Score how well THIS JOB fits THIS CANDIDATE from 0 to 100, where 100 = perfect
early-career fit and 0 = totally wrong (senior-only, wrong domain, wrong location).
Weigh: seniority match (fresher/new-grad friendly is best), tech-stack overlap,
domain fit, and India location. Be strict about seniority.

Return ONLY compact JSON: {"score": <int 0-100>, "reason": "<max 12 words>"}

CANDIDATE PROFILE:
{profile}

JOB:
Title: {title}
Company: {company}
Location: {location}
Description (truncated): {jd}
"""


def enabled():
    return bool(os.environ.get("GEMINI_API_KEY"))


def _profile_text():
    try:
        return PROFILE.read_text(encoding="utf-8")
    except OSError:
        return ""


def score_job(title, company, location, jd_text, settings):
    """Return (score:int, reason:str) or None if scoring unavailable/failed."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    gcfg = (settings or {}).get("gemini", {})
    model = gcfg.get("model", "gemini-2.0-flash")
    timeout = gcfg.get("timeout", 15)
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={key}")
    prompt = _PROMPT.format(profile=_profile_text()[:2000],
                            title=title, company=company,
                            location=location or "n/a",
                            jd=(jd_text or "")[:2500])
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0, "maxOutputTokens": 60}}
    try:
        r = requests.post(url, json=body, timeout=timeout)
        r.raise_for_status()
        text = (r.json()["candidates"][0]["content"]["parts"][0]["text"]).strip()
        m = re.search(r"\{.*\}", text, re.S)
        data = json.loads(m.group(0) if m else text)
        score = int(data.get("score", -1))
        reason = str(data.get("reason", "")).strip()[:80]
        if 0 <= score <= 100:
            return score, reason
    except Exception as e:  # noqa: BLE001 - scoring must never block an alert
        print(f"  score skipped ({type(e).__name__}) for {title} @ {company}")
    return None
