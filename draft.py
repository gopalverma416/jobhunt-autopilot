"""Fill a message template from a tracker row and print it for copy-paste.

Usage:
  python draft.py referral_alumni 7737482003
  python draft.py cold_recruiter 7737482003 --contact "Priya"
  python draft.py followup 7737482003

Templates live in templates/*.txt and use {company}, {role}, {job_url},
{contact_name} placeholders. --contact overrides the tracker's contact_name.
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent
TRACKER = ROOT / "tracker.csv"
TEMPLATES = ROOT / "templates"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("template",
                    help="template name (a .txt file in templates/), e.g. referral_alumni")
    ap.add_argument("url", help="substring of the job_url in tracker.csv")
    ap.add_argument("--contact", default=None, help="override contact name")
    a = ap.parse_args()

    tpl_path = TEMPLATES / f"{a.template}.txt"
    if not tpl_path.exists():
        options = ", ".join(p.stem for p in TEMPLATES.glob("*.txt"))
        sys.exit(f"no template '{a.template}'. Available: {options}")

    with open(TRACKER, newline="", encoding="utf-8") as f:
        hits = [r for r in csv.DictReader(f) if a.url in r["job_url"]]
    if not hits:
        sys.exit(f"no tracker row whose job_url contains '{a.url}'")
    if len(hits) > 1:
        for r in hits:
            print(f"  {r['company']} | {r['role']} | {r['job_url']}")
        sys.exit("multiple matches - be more specific")
    row = hits[0]

    contact = a.contact or row.get("contact_name") or "there"
    text = tpl_path.read_text(encoding="utf-8").format(
        company=row["company"], role=row["role"],
        job_url=row["job_url"], contact_name=contact,
    )
    print(text)


if __name__ == "__main__":
    main()
