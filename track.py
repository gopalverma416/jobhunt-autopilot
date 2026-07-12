"""5-second tracker updates from the command line.

Rows are matched by a SUBSTRING of the job URL (usually the numeric job id
is enough). If the substring matches several rows you'll be shown them and
nothing is changed.

Examples:
  python track.py applied 7737482003 --resume v12
  python track.py outreach 7737482003 --contact "Priya S" --linkedin https://linkedin.com/in/... --channel linkedin
  python track.py followup 7737482003 --days 7
  python track.py status 7737482003 oa
  python track.py note 7737482003 "referred by senior; OA next week"
  python track.py due                     # list follow-ups due today
"""
import argparse
import csv
import sys
from datetime import date, timedelta
from pathlib import Path

TRACKER = Path(__file__).parent / "tracker.csv"
STATUSES = ["found", "applied", "referred", "oa", "interview", "offer", "rejected"]
DEFAULT_FOLLOWUP_DAYS = 4   # first nudge: outreach + 4 days
SECOND_FOLLOWUP_DAYS = 7    # next nudge: + 7 days


def load():
    if not TRACKER.exists():
        sys.exit("tracker.csv not found - run the watcher first.")
    with open(TRACKER, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        return list(r), r.fieldnames


def save(rows, fieldnames):
    with open(TRACKER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def find_row(rows, needle):
    hits = [r for r in rows if needle in r["job_url"]]
    if not hits:
        sys.exit(f"no row whose job_url contains '{needle}'")
    if len(hits) > 1:
        print(f"'{needle}' matches {len(hits)} rows - be more specific:")
        for r in hits:
            print(f"  {r['company']} | {r['role']} | {r['job_url']}")
        sys.exit(1)
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("applied", help="mark a job as applied (today)")
    p.add_argument("url"); p.add_argument("--resume", default="")

    p = sub.add_parser("outreach", help="log outreach; sets follow-up in 4 days")
    p.add_argument("url"); p.add_argument("--contact", required=True)
    p.add_argument("--linkedin", default=""); p.add_argument("--channel", default="linkedin")

    p = sub.add_parser("followup", help="log a follow-up done; schedule the next one")
    p.add_argument("url"); p.add_argument("--days", type=int, default=SECOND_FOLLOWUP_DAYS)

    p = sub.add_parser("status", help=f"set status ({'/'.join(STATUSES)})")
    p.add_argument("url"); p.add_argument("new_status", choices=STATUSES)

    p = sub.add_parser("note", help="append a note")
    p.add_argument("url"); p.add_argument("text")

    sub.add_parser("due", help="list follow-ups due today or earlier")

    a = ap.parse_args()
    rows, cols = load()
    today = date.today()

    if a.cmd == "due":
        due = [r for r in rows if r["followup_due"]
               and r["followup_due"] <= today.isoformat()
               and r["status"] not in ("offer", "rejected")]
        for r in due:
            print(f"{r['followup_due']} | {r.get('contact_name') or '-'} | "
                  f"{r['role']} @ {r['company']} | {r['job_url']}")
        if not due:
            print("nothing due \U0001F389")
        return

    row = find_row(rows, a.url)

    if a.cmd == "applied":
        row["status"] = "applied"
        row["applied_date"] = today.isoformat()
        if a.resume:
            row["resume_version"] = a.resume
    elif a.cmd == "outreach":
        row["contact_name"] = a.contact
        if a.linkedin:
            row["contact_linkedin"] = a.linkedin
        row["outreach_channel"] = a.channel
        row["outreach_date"] = today.isoformat()
        row["followup_due"] = (today + timedelta(days=DEFAULT_FOLLOWUP_DAYS)).isoformat()
    elif a.cmd == "followup":
        row["followup_due"] = (today + timedelta(days=a.days)).isoformat()
    elif a.cmd == "status":
        row["status"] = a.new_status
        if a.new_status in ("offer", "rejected"):
            row["followup_due"] = ""
    elif a.cmd == "note":
        row["notes"] = (row["notes"] + " | " if row["notes"] else "") + a.text

    save(rows, cols)
    print(f"updated: {row['company']} | {row['role']} | status={row['status']}"
          + (f" | followup_due={row['followup_due']}" if row["followup_due"] else ""))


if __name__ == "__main__":
    main()
