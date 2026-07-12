"""seen_jobs.json v2 state + safe migration from v1.

v1 format (flat): {"<job_url>": "<first_seen_iso>", ...}
v2 format:
{
  "_v": 2,
  "jobs":  {"<key>": {"first": "<iso>", "sig": "<signature>"}},   # every job ever processed
  "sigs":  {"<signature>": "<first_seen_iso>"},                   # earliest sighting per role signature
  "extra": {"tg:<channel>:<msg_id>": "<iso>"}                     # telegram-channel dedupe namespace
}

Signature = "company|normalized title". Location is deliberately NOT part of
the signature: the same posting shows "Bengaluru", "Bangalore, KA, IN" or
"India, Multiple Locations" depending on the source, which caused false
negatives in testing. The India-only location filter + the 21-day age gate +
the different-URL requirement keep false positives rare. (See MIGRATION.md.)

Migration also back-fills sigs from tracker.csv (v1 keys are job URLs, and
tracker rows carry company+role for each), so reposts of jobs seen BEFORE
the upgrade are still detected.
"""
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
SEEN = ROOT / "seen_jobs.json"
TRACKER = ROOT / "tracker.csv"


def norm_sig(company, title):
    """'PhonePe' + 'SDE-1, Backend (Req #423988)' -> 'phonepe|sde backend'.
    Lowercase, strip punctuation, drop tokens containing digits (req IDs,
    level numbers), collapse whitespace."""
    t = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    t = " ".join(w for w in t.split() if not any(c.isdigit() for c in w))
    return f"{company.strip().lower()}|{t.strip()}"


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_state():
    """Load state, transparently migrating v1 -> v2 (idempotent)."""
    if not SEEN.exists():
        return {"_v": 2, "jobs": {}, "sigs": {}, "extra": {}}
    with open(SEEN, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and data.get("_v") == 2:
        return data

    # ---- v1 -> v2 migration ----
    st = {"_v": 2,
          "jobs": {k: {"first": v, "sig": ""} for k, v in data.items()},
          "sigs": {}, "extra": {}}
    # Back-fill signatures from tracker.csv (v1 seen-keys are job URLs).
    if TRACKER.exists():
        with open(TRACKER, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                url = (r.get("job_url") or "").strip()
                if url in st["jobs"] and r.get("company") and r.get("role"):
                    sig = norm_sig(r["company"], r["role"])
                    st["jobs"][url]["sig"] = sig
                    first = st["jobs"][url]["first"]
                    if sig not in st["sigs"] or first < st["sigs"][sig]:
                        st["sigs"][sig] = first
    print(f"migrated seen_jobs.json v1 -> v2: {len(st['jobs'])} jobs, "
          f"{len(st['sigs'])} signatures recovered from tracker.csv")
    return st


def save_state(st):
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=0, sort_keys=True)
        f.write("\n")


def record_job(st, key, sig):
    """Mark a job as processed and keep the earliest date per signature."""
    now = _now_iso()
    st["jobs"][key] = {"first": now, "sig": sig}
    if sig and (sig not in st["sigs"] or now < st["sigs"][sig]):
        st["sigs"][sig] = now


def repost_of(st, key, sig, min_age_days=21):
    """If this NEW key's signature was first seen >= min_age_days ago,
    return the first-seen date string - it's a likely repost."""
    first = st["sigs"].get(sig)
    if not first or key in st["jobs"]:
        return None
    try:
        first_dt = datetime.fromisoformat(first)
    except ValueError:
        return None
    age = (datetime.now(timezone.utc) - first_dt).days
    return first[:10] if age >= min_age_days else None


# ---------------- tracker.csv column migration ----------------
TRACKER_COLUMNS = [
    "date_found", "company", "role", "job_url", "status", "applied_date",
    "resume_version", "contact_name", "contact_linkedin", "outreach_date",
    "outreach_channel", "followup_due", "response", "match_score", "notes",
]


def migrate_tracker():
    """Add any missing columns (v2 adds 'response'). Safe to run every time."""
    if not TRACKER.exists():
        with open(TRACKER, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=TRACKER_COLUMNS).writeheader()
        return
    with open(TRACKER, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        old_cols = reader.fieldnames or []
        rows = list(reader)
    if old_cols == TRACKER_COLUMNS:
        return
    with open(TRACKER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({c: (r.get(c) or "") for c in TRACKER_COLUMNS})
    print(f"migrated tracker.csv: columns {old_cols} -> {TRACKER_COLUMNS}")


def load_tracker_rows():
    if not TRACKER.exists():
        return []
    with open(TRACKER, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))
