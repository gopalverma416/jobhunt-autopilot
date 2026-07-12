"""JobHunt Autopilot v2 - hourly watcher.

Pipeline per run:
  1. migrate state files if needed (seen_jobs v1->v2, tracker columns)
  2. fetch all ATS sources + all t.me channels concurrently
  3. title + location filter -> keep only NEW jobs (not in seen state)
  4. fetch full JDs for those new jobs (concurrently, 0-5 typical)
     -> reject over-experienced roles into rejected_log.csv
     -> tag borderline (🤔) / fresher-friendly (✅) / unverified (⚠️)
  5. repost detection via role signatures (21+ days, different URL)
  6. contact lookup from contacts.csv for each alert
  7. Telegram alerts + tracker.csv append + save state

Usage:  python watcher.py [--dry-run]
"""
import argparse
import concurrent.futures as cf
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

from contacts_db import find_for_company, load_contacts
from fetchers import FETCHERS
from filters import JobFilter
from jd import analyze_jd, fetch_jd
from notify import format_channel_alert, format_job_alert, send_telegram
from state import (TRACKER_COLUMNS, load_state, load_tracker_rows,
                   migrate_tracker, norm_sig, record_job, repost_of,
                   save_state)
from tg_channels import build_matcher, fetch_channel

ROOT = Path(__file__).parent
CONFIG = ROOT / "companies.yaml"
TRACKER = ROOT / "tracker.csv"
REJECTED = ROOT / "rejected_log.csv"


def load_config():
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_one(company_cfg, settings):
    name = company_cfg["name"]
    fn = FETCHERS.get(company_cfg["ats"])
    if fn is None:
        return name, [], f"unknown ats '{company_cfg['ats']}'"
    try:
        return name, fn(company_cfg, settings), None
    except Exception as e:  # noqa: BLE001 - one bad source must not crash the run
        return name, [], f"{type(e).__name__}: {e}"


def job_key(job):
    return job["url"] or f"{job['source']}:{job['id']}"


def append_tracker(jobs):
    exists = TRACKER.exists()
    with open(TRACKER, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        if not exists:
            w.writeheader()
        today = datetime.now(timezone.utc).date().isoformat()
        for j in jobs:
            row = {c: "" for c in TRACKER_COLUMNS}
            row.update({"date_found": today, "company": j["company"],
                        "role": j["title"], "job_url": j["url"], "status": "found"})
            w.writerow(row)


def append_rejected(rows):
    """rejected_log.csv: audit trail for JD-filter rejections (tune weekly)."""
    exists = REJECTED.exists()
    with open(REJECTED, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(["date", "company", "title", "job_url", "reason"])
        today = datetime.now(timezone.utc).date().isoformat()
        for j, reason in rows:
            w.writerow([today, j["company"], j["title"], j["url"], reason])


def applied_earlier(tracker_rows, sig):
    """If the tracker shows an application to a same-signature job, return its date."""
    for r in tracker_rows:
        if (r.get("status") in ("applied", "referred", "oa", "interview", "offer")
                and norm_sig(r.get("company", ""), r.get("role", "")) == sig):
            return r.get("applied_date") or r.get("date_found") or "earlier"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="fetch + filter + print, but write/send nothing")
    args = ap.parse_args()
    t0 = time.time()

    cfg = load_config()
    settings = cfg["settings"]
    jdcfg = cfg["filters"].get("jd", {})
    aliases = cfg.get("aliases", {})
    jf = JobFilter(cfg["filters"])
    if not args.dry_run:
        migrate_tracker()
    state = load_state()
    first_run = not state["jobs"]
    contacts = load_contacts()
    contacts = [c for c in contacts if not c["name"].upper().startswith("DUMMY")] \
        or contacts  # keep DUMMY rows only if there's nothing else (demo mode)
    tracker_rows = load_tracker_rows()
    cfg_by_name = {c["name"]: c for c in cfg["companies"]}

    # ---- 1. fetch ATS sources + telegram channels concurrently ----
    channels = cfg.get("telegram_channels") or []
    results, ch_results = [], []
    with cf.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_one, c, settings): ("ats", c["name"])
                for c in cfg["companies"]}
        futs.update({ex.submit(fetch_channel, ch, settings): ("tg", ch)
                     for ch in channels})
        for fut in cf.as_completed(futs):
            kind, name = futs[fut]
            if kind == "ats":
                results.append(fut.result())
            else:
                msgs, err = fut.result()
                ch_results.append((name, msgs, err))

    all_jobs, failures = [], 0
    for name, jobs, err in sorted(results):
        if err:
            failures += 1
            print(f"  FAIL {name}: {err}")
        else:
            print(f"  OK   {name}: {len(jobs)} postings")
            all_jobs.extend(jobs)

    # ---- 2. title/location filter + new-only ----
    matching = [j for j in all_jobs if jf.match(j)]
    new_jobs = [j for j in matching if job_key(j) not in state["jobs"]]

    # ---- 3. full-JD pass for new jobs only (concurrent) ----
    def jd_task(j):
        try:
            return j, fetch_jd(j, cfg_by_name.get(j["company"]), settings), None
        except Exception as e:  # noqa: BLE001
            return j, None, f"{type(e).__name__}: {e}"

    alerts, rejected = [], []
    if new_jobs:
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for j, text, err in ex.map(jd_task, new_jobs):
                tags = []
                if text is None:
                    tags.append("⚠️ JD unverified")
                    verdict = {"verdict": "pass", "reason": "", "fresher": False}
                    if err:
                        print(f"  JD fetch failed for {j['title']} @ {j['company']}: {err}")
                else:
                    verdict = analyze_jd(text, jdcfg)
                key, sig = job_key(j), norm_sig(j["company"], j["title"])
                if verdict["verdict"] == "reject":
                    print(f"  JD-REJECT {j['title']} @ {j['company']}: {verdict['reason']}")
                    rejected.append((j, verdict["reason"]))
                    record_job(state, key, sig)   # never re-process
                    continue
                if verdict["verdict"] == "borderline":
                    tags.append(f"\U0001F914 {verdict['reason']}")
                if verdict["fresher"]:
                    tags.append("✅ fresher-friendly")
                # repost check BEFORE recording this key
                first_seen = repost_of(state, key, sig,
                                       settings.get("repost_min_age_days", 21))
                repost = None
                if first_seen:
                    repost = {"first_seen": first_seen,
                              "applied_date": applied_earlier(tracker_rows, sig)}
                record_job(state, key, sig)
                alerts.append((j, tags, repost))

    # ---- 4. telegram channel messages ----
    ch_alerts = []
    if channels:
        match = build_matcher(cfg["filters"]["include_titles"],
                              cfg.get("channel_fresher_signals", []))
        for name, msgs, err in sorted(ch_results):
            if err:
                print(f"  CHAN {name}: {err}")
                continue
            hits = 0
            for m in msgs:
                k = f"tg:{m['channel']}:{m['msg_id']}"
                if k not in state["extra"] and match(m["text"]):
                    state["extra"][k] = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    ch_alerts.append(m)
                    hits += 1
            print(f"  CHAN {name}: {len(msgs)} msgs, {hits} new matches")

    # ---- 5. send alerts (flood-capped) ----
    max_alerts = int(settings.get("max_alerts_per_run", 15))
    to_send = alerts[:max_alerts]
    suppressed = len(alerts) - len(to_send)

    if first_run and alerts:
        send_telegram(f"\U0001F331 First run: seeded {len(state['jobs'])} postings; "
                      f"alerting up to {max_alerts} current matches.",
                      dry_run=args.dry_run)
    for j, tags, repost in to_send:
        cts = find_for_company(contacts, j["company"], aliases)
        send_telegram(format_job_alert(j, settings, tags=tags, contacts=cts,
                                       repost=repost), dry_run=args.dry_run)
        time.sleep(0.5)
    for m in ch_alerts[:max_alerts]:
        send_telegram(format_channel_alert(m), dry_run=args.dry_run)
        time.sleep(0.5)
    if suppressed > 0:
        send_telegram(f"(+{suppressed} more new matches not alerted - see tracker.csv)",
                      dry_run=args.dry_run)

    # ---- 6. persist ----
    if not args.dry_run:
        if alerts:
            append_tracker([j for j, _, _ in alerts])
        if rejected:
            append_rejected(rejected)
        save_state(state)

    print(f"\nrun summary: {len(all_jobs)} fetched | {len(matching)} match title/loc | "
          f"{len(alerts)} alerted | {len(rejected)} JD-rejected | "
          f"{len(ch_alerts)} channel hits | {failures} source(s) failed | "
          f"{time.time()-t0:.1f}s")
    if results and all(err for _, _, err in results):
        print("ERROR: all sources failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
