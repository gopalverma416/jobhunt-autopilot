"""Daily 9:00 AM IST digest (03:30 UTC via GitHub Actions).

Sections:
  (a) jobs found in the last 24h not yet applied to
  (b) job follow-ups due (from tracker.csv)
  (c) PEOPLE follow-ups due (from contacts.csv, 14-day anti-spam rule)
  (d) applications count this week
"""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from contacts_db import due_for_nudge, load_contacts
from notify import send_telegram

TRACKER = Path(__file__).parent / "tracker.csv"


def load_rows():
    if not TRACKER.exists():
        return []
    with open(TRACKER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def main():
    rows = load_rows()
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    fresh = [r for r in rows
             if r.get("status") == "found"
             and (parse_date(r.get("date_found", "")) or week_ago) >= yesterday]

    followups = [r for r in rows
                 if r.get("followup_due")
                 and (parse_date(r["followup_due"]) or today) <= today
                 and r.get("status") not in ("offer", "rejected")]

    applied_this_week = sum(
        1 for r in rows
        if r.get("applied_date")
        and (parse_date(r["applied_date"]) or week_ago) > week_ago)

    contacts = [c for c in load_contacts()
                if not c["name"].upper().startswith("DUMMY")]
    nudges = due_for_nudge(contacts, today)

    lines = [f"☀️ JobHunt digest - {today.isoformat()}", ""]

    lines.append(f"\U0001F195 Found in last 24h, not yet applied: {len(fresh)}")
    for r in fresh[:10]:
        lines.append(f"  • {r['role']} @ {r['company']}\n    {r['job_url']}")
    if len(fresh) > 10:
        lines.append(f"  ...and {len(fresh) - 10} more in tracker.csv")

    lines.append("")
    lines.append(f"⏰ Job follow-ups due: {len(followups)}")
    for r in followups[:10]:
        who = r.get("contact_name") or "contact"
        lines.append(f"  • {who} re {r['role']} @ {r['company']} (due {r['followup_due']})")
        if r.get("contact_linkedin"):
            lines.append(f"    {r['contact_linkedin']}")

    lines.append("")
    lines.append(f"\U0001F465 People to nudge today: {len(nudges)}")
    for c in nudges[:10]:
        lines.append(f"  • {c['name']} @ {c['company']} — last contact "
                     f"{c['last_contact_date'] or '?'}"
                     + (f' ("{c["last_context"]}")' if c["last_context"] else ""))
        if c["linkedin_url"]:
            lines.append(f"    {c['linkedin_url']}")

    lines.append("")
    lines.append(f"\U0001F4EC Applications this week: {applied_this_week}")

    if not fresh and not followups and not nudges:
        lines.append("\nNothing pending. Go solve a Codeforces problem \U0001F642")

    send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
