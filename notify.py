"""Telegram alerts. Needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID env vars
(set as GitHub Actions secrets - see README)."""
import os
import time
from urllib.parse import quote_plus

import requests


def _linkedin_search_links(company, alumni_keywords):
    """Pre-built Google searches over LinkedIn profiles, URL-encoded so
    they're tappable in Telegram."""
    alumni_q = f'site:linkedin.com/in ({" OR ".join(alumni_keywords)}) "{company}"'
    recruiter_q = (f'site:linkedin.com/in ("recruiter" OR "talent acquisition") '
                   f'"{company}" India')
    em_q = f'site:linkedin.com/in "engineering manager" "{company}" India'
    g = "https://www.google.com/search?q="
    return {
        "alumni": g + quote_plus(alumni_q),
        "recruiters": g + quote_plus(recruiter_q),
        "eng_managers": g + quote_plus(em_q),
    }


def format_job_alert(job, alumni_keywords):
    links = _linkedin_search_links(job["company"], alumni_keywords)
    age = f"posted {job['posted_at']}" if job["posted_at"] else "just spotted"
    loc = job["location"] or "location not listed"
    return (
        f"\U0001F6A8 NEW: {job['title']} @ {job['company']}\n"
        f"\U0001F4CD {loc} | {age}\n"
        f"\U0001F517 {job['url']}\n\n"
        f"\U0001F465 Find people (tap to search):\n"
        f"• Alumni: {links['alumni']}\n"
        f"• Recruiters: {links['recruiters']}\n"
        f"• Eng managers: {links['eng_managers']}"
    )


def send_telegram(text, dry_run=False):
    """Send one message. Returns True on success. Never raises
    (a Telegram hiccup must not kill the whole run)."""
    if dry_run:
        print("---- DRY RUN (not sent) ----")
        print(text)
        print("----------------------------")
        return True
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("WARN: TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; printing instead.")
        print(text)
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text,
                  "disable_web_page_preview": True},
            timeout=10,
        )
        if r.status_code == 429:  # rate-limited: wait once and retry
            wait = r.json().get("parameters", {}).get("retry_after", 3)
            time.sleep(min(wait, 10))
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text,
                      "disable_web_page_preview": True},
                timeout=10,
            )
        r.raise_for_status()
        return True
    except Exception as e:  # noqa: BLE001 - deliberately broad
        print(f"WARN: telegram send failed: {e}")
        return False
