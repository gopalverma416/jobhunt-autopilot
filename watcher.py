"""JobHunt Autopilot - hourly watcher.

For every company in companies.yaml:
  fetch (concurrently) -> filter (title + location) -> dedupe against
  seen_jobs.json -> Telegram alert + append to tracker.csv.

Designed for GitHub Actions free tier: all sources fetched in parallel
with short timeouts; one broken source never crashes the run.

Usage:
  python watcher.py             # normal run
  python watcher.py --dry-run   # fetch + filter, print alerts, write nothing

First run behaviour: if seen_jobs.json is empty, every currently-open
posting would be "new" and you'd get flooded. Instead we seed the state
(mark everything seen), alert only, at most, max_alerts_per_run of the
matching jobs, and tell you how many were seeded.
"""
import argparse
import concurrent.futures as cf
import csv
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from fetchers import FETCHERS
from filters import JobFilter
from notify import format_job_alert, send_telegram

ROOT = Path(__file__).parent
CONFIG = ROOT / "companies.yaml"
SEEN = ROOT / "seen_jobs.json"
TRACKER = ROOT / "tracker.csv"

TRACKER_COLUMNS = [
    "date_found", "company", "role", "job_url", "status", "applied_date",
    "resume_version", "contact_name", "contact_linkedin", "outreach_date",
    "outreach_channel", "followup_due", "notes",
]


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen():
    if SEEN.exists():
        with open(SEEN, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN, "w", encoding="utf-8") as f:
        json.dump(seen, f, indent=0, sort_keys=True)
        f.write("\n")


def job_key(job):
    """Stable dedupe key: prefer the URL, fall back to source:id."""
    return job["url"] or f"{job['source']}:{job['id']}"


def fetch_one(company_cfg, settings):
    """Fetch one source. Returns (company_name, jobs, error_or_None)."""
    name = company_cfg["name"]
    fn = FETCHERS.get(company_cfg["ats"])
    if fn is None:
        return name, [], f"unknown ats '{company_cfg['ats']}'"
    try:
        return name, fn(company_cfg, settings), None
    except Exception as e:  # noqa: BLE001 - one bad source must not crash the run
        return name, [], f"{type(e).__name__}: {e}"


def append_tracker(jobs):
    """Append newly found jobs to tracker.csv with status 'found'."""
    exists = TRACKER.exists()
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        if not exists:
            w.writeheader()
        today = datetime.now(timezone.utc).date().isoformat()
        for j in jobs:
            w.writerow({
                "date_found": today, "company": j["company"],
                "role": j["title"], "job_url": j["url"], "status": "found",
                "applied_date": "", "resume_version": "", "contact_name": "",
                "contact_linkedin": "", "outreach_date": "",
                "outreach_channel": "", "followup_due": "", "notes": "",
            })


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + filter + print, but write/send nothing")
    args = ap.parse_args()

    t0 = time.time()
    cfg = load_config()
    settings = cfg["settings"]
    jf = JobFilter(cfg["filters"])
    seen = load_seen()
    first_run = not seen

    # ---- fetch all sources concurrently ----
    companies = cfg["companies"]
    results = []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = [ex.submit(fetch_one, c, settings) for c in companies]
        for fut in cf.as_completed(futs):
            results.append(fut.result())

    all_jobs, failures = [], []
    for name, jobs, err in sorted(results):
        if err:
            failures.append(f"{name}: {err}")
            print(f"  FAIL {name}: {err}")
        else:
            print(f"  OK   {name}: {len(jobs)} postings")
            all_jobs.extend(jobs)

    # ---- filter + dedupe ----
    matching = [j for j in all_jobs if jf.match(j)]
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new_jobs = []
    for j in matching:
        k = job_key(j)
        if k not in seen:
            seen[k] = now_iso
            new_jobs.append(j)

    # ---- alert ----
    max_alerts = int(settings.get("max_alerts_per_run", 15))
    to_alert = new_jobs[:max_alerts]
    suppressed = len(new_jobs) - len(to_alert)

    if first_run and new_jobs:
        send_telegram(
            f"\U0001F331 JobHunt Autopilot: first run. Seeded "
            f"{len(seen)} existing postings; {len(new_jobs)} currently match "
            f"your filters (showing up to {max_alerts}). From now on you'll "
            f"only get genuinely NEW postings.",
            dry_run=args.dry_run)

    for j in to_alert:
        send_telegram(format_job_alert(j, settings["alumni_keywords"]),
                      dry_run=args.dry_run)
        time.sleep(0.5)  # stay well under Telegram rate limits
    if suppressed > 0:
        send_telegram(f"(+{suppressed} more new matches not alerted - "
                      f"see tracker.csv)", dry_run=args.dry_run)

    # ---- persist ----
    if not args.dry_run:
        if new_jobs:
            append_tracker(new_jobs)
        save_seen(seen)

    dt = time.time() - t0
    print(f"\nrun summary: {len(all_jobs)} fetched | {len(matching)} match "
          f"filters | {len(new_jobs)} new | {len(failures)} source(s) failed "
          f"| {dt:.1f}s")
    # Exit 0 even with partial failures - only a fully broken run should
    # look red in Actions. If EVERY source failed, exit 1 so you notice.
    if results and all(err for _, _, err in results):
        print("ERROR: all sources failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
