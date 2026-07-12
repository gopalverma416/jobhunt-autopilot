"""Contact database CLI (Feature 2) - same ergonomics as track.py.

Examples:
  python contact.py add --name "Krishna Acharya" --company PhonePe --role SDE-2 \\
      --linkedin https://linkedin.com/in/... --relationship warm --source alumni --school MANIT
  python contact.py update Krishna --contacted today --context "agreed to refer"
  python contact.py update Krishna --relationship warm
  python contact.py list --company PhonePe
  python contact.py list --due
  python contact.py import apify_export.csv

`update --contacted` sets last_contact_date and auto-schedules a follow-up
nudge (+5 days) that shows up in the daily digest. If the person was already
contacted within the last 14 days you get a warning (not a block).
"""
import argparse
import csv
import sys
from datetime import date

from contacts_db import (ANTI_SPAM_DAYS, COLUMNS, due_for_nudge,
                         load_contacts, save_contacts, set_contacted)

RELATIONSHIPS = ["warm", "contacted", "cold"]
SOURCES = ["alumni", "recruiter", "referral-chain", "other"]


def find_one(rows, needle):
    hits = [r for r in rows if needle.lower() in r["name"].lower()]
    if not hits:
        sys.exit(f"no contact whose name contains '{needle}'")
    if len(hits) > 1:
        print(f"'{needle}' matches {len(hits)} contacts - be more specific:")
        for r in hits:
            print(f"  {r['name']} | {r['company']} | {r['role']}")
        sys.exit(1)
    return hits[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("add", help="add a new contact")
    p.add_argument("--name", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--role", default="")
    p.add_argument("--linkedin", default="")
    p.add_argument("--relationship", default="cold", choices=RELATIONSHIPS)
    p.add_argument("--source", default="other", choices=SOURCES)
    p.add_argument("--school", default="", help="MANIT / other")
    p.add_argument("--notes", default="")
    p.add_argument("--contacted", nargs="?", const="today", default=None,
                   help="log an outreach now ('today' or YYYY-MM-DD)")
    p.add_argument("--context", default="", help="one-line context of last contact")

    p = sub.add_parser("update", help="update a contact (match by name substring)")
    p.add_argument("name")
    p.add_argument("--contacted", nargs="?", const="today", default=None)
    p.add_argument("--context", default=None)
    p.add_argument("--relationship", choices=RELATIONSHIPS, default=None)
    p.add_argument("--role", default=None)
    p.add_argument("--linkedin", default=None)
    p.add_argument("--notes", default=None, help="appended, not replaced")

    p = sub.add_parser("list", help="list contacts")
    p.add_argument("--company", default=None)
    p.add_argument("--due", action="store_true", help="only follow-ups due")

    p = sub.add_parser("import", help="best-effort import from an exported CSV "
                                      "(e.g. Apify LinkedIn people-search)")
    p.add_argument("file")
    p.add_argument("--source", default="other", choices=SOURCES)

    a = ap.parse_args()
    rows = load_contacts()

    if a.cmd == "add":
        row = {c: "" for c in COLUMNS}
        row.update({"name": a.name, "company": a.company, "role": a.role,
                    "linkedin_url": a.linkedin, "relationship": a.relationship,
                    "source": a.source, "school_link": a.school, "notes": a.notes})
        if a.contacted:
            when = date.today().isoformat() if a.contacted == "today" else a.contacted
            warn = set_contacted(row, when, a.context)
            if warn:
                print(warn)
        rows.append(row)
        save_contacts(rows)
        print(f"added: {row['name']} @ {row['company']} ({row['relationship']})"
              + (f" | follow-up due {row['followup_due']}" if row["followup_due"] else ""))

    elif a.cmd == "update":
        row = find_one(rows, a.name)
        if a.contacted:
            when = date.today().isoformat() if a.contacted == "today" else a.contacted
            warn = set_contacted(row, when, a.context)
            if warn:
                print(warn)
            row["relationship"] = row["relationship"] if row["relationship"] == "warm" else "contacted"
        if a.context is not None and not a.contacted:
            row["last_context"] = a.context
        if a.relationship:
            row["relationship"] = a.relationship
        if a.role is not None:
            row["role"] = a.role
        if a.linkedin is not None:
            row["linkedin_url"] = a.linkedin
        if a.notes is not None:
            row["notes"] = (row["notes"] + " | " if row["notes"] else "") + a.notes
        save_contacts(rows)
        print(f"updated: {row['name']} @ {row['company']} | {row['relationship']}"
              + (f" | follow-up due {row['followup_due']}" if row["followup_due"] else ""))

    elif a.cmd == "list":
        subset = rows
        if a.company:
            subset = [r for r in subset
                      if a.company.lower() in r["company"].lower()]
        if a.due:
            subset = due_for_nudge(subset)
        if not subset:
            print("no matching contacts")
        for r in subset:
            print(f"{r['name']:<28} {r['company']:<18} {r['role']:<22} "
                  f"{r['relationship']:<10} last={r['last_contact_date'] or '-':<12} "
                  f"due={r['followup_due'] or '-'}")

    elif a.cmd == "import":
        # Best-effort column mapping - exported CSVs vary wildly.
        NAME_KEYS = ["name", "fullname", "full_name", "profilename"]
        URL_KEYS = ["linkedin_url", "profileurl", "profile_url", "url", "linkedinurl", "link"]
        COMPANY_KEYS = ["company", "companyname", "company_name", "organization", "employer"]
        ROLE_KEYS = ["role", "title", "jobtitle", "job_title", "headline", "position"]

        def pick(r, keys):
            low = {k.lower().replace(" ", ""): v for k, v in r.items() if k}
            for k in keys:
                if low.get(k):
                    return str(low[k]).strip()
            return ""

        existing_urls = {r["linkedin_url"] for r in rows if r["linkedin_url"]}
        added = skipped = 0
        with open(a.file, newline="", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                first = pick(r, ["firstname", "first_name"])
                last = pick(r, ["lastname", "last_name"])
                name = pick(r, NAME_KEYS) or f"{first} {last}".strip()
                url = pick(r, URL_KEYS)
                if not name or (url and url in existing_urls):
                    skipped += 1
                    continue
                row = {c: "" for c in COLUMNS}
                row.update({"name": name, "company": pick(r, COMPANY_KEYS),
                            "role": pick(r, ROLE_KEYS), "linkedin_url": url,
                            "relationship": "cold", "source": a.source,
                            "notes": "imported - verify details"})
                rows.append(row)
                existing_urls.add(url)
                added += 1
        save_contacts(rows)
        print(f"imported {added} contacts ({skipped} skipped: no name or duplicate URL). "
              f"Review with: python contact.py list")


if __name__ == "__main__":
    main()
