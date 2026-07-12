"""Shared helpers for contacts.csv (Feature 2). Used by contact.py,
watcher alerts, and the daily digest.

PRIVACY: contacts.csv contains personal data of real people. Keep the repo
private; use this data only for your own 1-to-1 outreach.
"""
import csv
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
CONTACTS = ROOT / "contacts.csv"

COLUMNS = ["name", "company", "role", "linkedin_url", "relationship",
           "source", "school_link", "last_contact_date", "last_context",
           "followup_due", "notes"]

FOLLOWUP_DAYS = 5        # nudge N days after an outreach
ANTI_SPAM_DAYS = 14      # never suggest pinging the same person twice within this


def load_contacts():
    if not CONTACTS.exists():
        return []
    with open(CONTACTS, newline="", encoding="utf-8") as f:
        return [{c: (r.get(c) or "").strip() for c in COLUMNS}
                for r in csv.DictReader(f)]


def save_contacts(rows):
    with open(CONTACTS, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def canonical(name, aliases):
    """Map company aliases to one canonical name, case-insensitively.
    aliases (from companies.yaml) maps Alias -> Canonical, e.g. Eternal -> Zomato."""
    n = (name or "").strip().lower()
    for alias, canon in (aliases or {}).items():
        if n == alias.strip().lower():
            return canon.strip().lower()
    return n


def find_for_company(rows, company, aliases=None):
    target = canonical(company, aliases)
    return [r for r in rows if canonical(r["company"], aliases) == target]


def contact_line(r):
    """One alert/digest line: 'Krishna — SDE-2, warm, last contact 20 Jun ("agreed to refer")'."""
    bits = [r["name"]]
    desc = ", ".join(x for x in [r["role"], r["relationship"] or "cold"] if x)
    when = (f"last contact {r['last_contact_date']}" if r["last_contact_date"]
            else "never contacted")
    line = f"• {bits[0]} — {desc}, {when}"
    if r["last_context"]:
        line += f' ("{r["last_context"]}")'
    return line


def set_contacted(row, on_date=None, context=None):
    """Record an outreach; auto-schedule the follow-up nudge.
    Returns a warning string if this violates the 14-day anti-spam window."""
    today = on_date or date.today().isoformat()
    warning = None
    prev = row.get("last_contact_date", "")
    if prev:
        try:
            days = (date.fromisoformat(today) - date.fromisoformat(prev)).days
            if 0 <= days < ANTI_SPAM_DAYS:
                warning = (f"⚠️ you already contacted {row['name']} {days} day(s) ago "
                           f"({prev}) — twice within {ANTI_SPAM_DAYS} days risks being spammy")
        except ValueError:
            pass
    row["last_contact_date"] = today
    row["followup_due"] = (date.fromisoformat(today)
                           + timedelta(days=FOLLOWUP_DAYS)).isoformat()
    if context:
        row["last_context"] = context
    return warning


def due_for_nudge(rows, today=None):
    """Contacts whose follow-up is due TODAY under the anti-spam rule:
    shown on the due date, then every ANTI_SPAM_DAYS after - never more
    often. Stateless on purpose (the digest job has read-only permissions)."""
    today = today or date.today()
    out = []
    for r in rows:
        if not r["followup_due"]:
            continue
        try:
            over = (today - date.fromisoformat(r["followup_due"])).days
        except ValueError:
            continue
        if over >= 0 and over % ANTI_SPAM_DAYS == 0:
            out.append(r)
    return out
