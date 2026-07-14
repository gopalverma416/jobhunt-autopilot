"""Telegram alerts (v2): job alerts with JD tags, contact lookup and repost
info, plus channel-forward alerts. Needs TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID.

Backward compatible: format_job_alert(job, alumni_keywords) still works the
v1 way if you pass a list as the second argument.
"""
import os
import time
from urllib.parse import quote_plus

import requests

from contacts_db import contact_line


def _linkedin_search_links(company, alumni_keywords):
    alumni_q = f'site:linkedin.com/in ({" OR ".join(alumni_keywords)}) "{company}"'
    recruiter_q = (f'site:linkedin.com/in ("recruiter" OR "talent acquisition") '
                   f'"{company}" India')
    em_q = f'site:linkedin.com/in "engineering manager" "{company}" India'
    g = "https://www.google.com/search?q="
    return {"alumni": g + quote_plus(alumni_q),
            "recruiters": g + quote_plus(recruiter_q),
            "eng_managers": g + quote_plus(em_q)}


def format_job_alert(job, settings_or_keywords, tags=(), contacts=(), repost=None):
    """Build one job alert. `settings_or_keywords` may be the settings dict
    (v2) or the alumni_keywords list (v1 call style)."""
    if isinstance(settings_or_keywords, dict):
        alumni_keywords = settings_or_keywords.get("alumni_keywords", [])
    else:
        alumni_keywords = settings_or_keywords

    head = "\U0001F501 REPOST" if repost else "\U0001F6A8 NEW"
    age = f"posted {job['posted_at']}" if job["posted_at"] else "just spotted"
    loc = job["location"] or "location not listed"
    lines = [f"{head}: {job['title']} @ {job['company']}",
             f"\U0001F4CD {loc} | {age}"]
    if tags:
        lines.append(" ".join(tags))
    if repost:
        lines.append(f"\U0001F501 Same role first seen {repost['first_seen']} under a "
                     f"different posting — likely unfilled, push hard with a referral.")
        if repost.get("applied_date"):
            lines.append(f"\U0001F4CC You applied to the earlier posting on "
                         f"{repost['applied_date']} — worth a follow-up + referral, "
                         f"not a duplicate application.")
    lines.append(f"\U0001F517 {job['url']}")
    lines.append("")

    if contacts:
        lines.append(f"\U0001F465 Your people at {job['company']}:")
        for c in contacts[:6]:
            lines.append(contact_line(c))
        if repost:
            lines.append("\U0001F449 A repost + a warm contact = your best shot. Ask for the referral.")
    else:
        links = _linkedin_search_links(job["company"], alumni_keywords)
        lines.append("\U0001F465 Find people (tap to search):")
        lines.append(f"• Alumni: {links['alumni']}")
        lines.append(f"• Recruiters: {links['recruiters']}")
        lines.append(f"• Eng managers: {links['eng_managers']}")
        lines.append(f"\U0001F4C7 No contacts saved for {job['company']} yet — add with contact.py")
    return "\n".join(lines)


def format_channel_alert(msg):
    """📣 CHANNEL alert for a matched t.me message, with the extracted
    apply link (when the post embedded one) shown first for one-tap apply."""
    text = msg["text"]
    if len(text) > 500:
        text = text[:500] + "…"
    lines = [f"\U0001F4E3 CHANNEL @{msg['channel']}"]
    if msg.get("apply_url"):
        lines.append(f"\U0001F7E2 Apply: {msg['apply_url']}")
    lines.append(text)
    lines.append(f"\U0001F517 Source: https://t.me/{msg['channel']}/{msg['msg_id']}")
    return "\n".join(lines)


def send_telegram(text, dry_run=False):
    """Send one message; never raises. Splits messages over 4096 chars."""
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
    ok = True
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)] or [""]
    for chunk in chunks:
        try:
            r = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": chunk,
                      "disable_web_page_preview": True},
                timeout=10)
            if r.status_code == 429:
                wait = r.json().get("parameters", {}).get("retry_after", 3)
                time.sleep(min(wait, 10))
                r = requests.post(
                    f"https://api.telegram.org/bot{token}/sendMessage",
                    json={"chat_id": chat_id, "text": chunk,
                          "disable_web_page_preview": True},
                    timeout=10)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            print(f"WARN: telegram send failed: {e}")
            ok = False
    return ok
