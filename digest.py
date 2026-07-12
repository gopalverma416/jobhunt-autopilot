"""Daily 9:00 AM IST digest (runs at 03:30 UTC via GitHub Actions).

Sends one Telegram message with:
  (a) jobs found in the last 24h that you haven't applied to yet
  (b) follow-ups due today or overdue
  (c) applications count this week
"""
import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

from notify import send_telegram

TRACKER = Path(__file__).parent / "tracker.csv"


def load_rows():
    if not TRACKER.exists():
        return []
    with open(TRACKER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_date(s):
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except (ValueError, AttributeError):
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
        if r.get("applied_date") and (parse_date(r["applied_date"]) or week_ago) > week_ago
    )

    lines = [f"☀️ JobHunt digest - {today.isoformat()}", ""]

    lines.append(f"\U0001F195 Found in last 24h, not yet applied: {len(fresh)}")
    for r in fresh[:10]:
        lines.append(f"  • {r['role']} @ {r['company']}\n    {r['job_url']}")
    if len(fresh) > 10:
        lines.append(f"  ...and {len(fresh) - 10} more in tracker.csv")

    lines.append("")
    lines.append(f"⏰ Follow-ups due: {len(followups)}")
    for r in followups[:10]:
        who = r.get("contact_name") or "contact"
        lines.append(f"  • {who} re {r['role']} @ {r['company']} "
                     f"(due {r['followup_due']})")
        if r.get("contact_linkedin"):
            lines.append(f"    {r['contact_linkedin']}")

    lines.append("")
    lines.append(f"\U0001F4EC Applications this week: {applied_this_week}")

    if not fresh and not followups:
        lines.append("\nNothing pending. Go solve a Codeforces problem \U0001F642")

    send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
