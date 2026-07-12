"""One-time (re-runnable) JD backfill.

v1 seeded the tracker with title-filtered jobs BEFORE the JD filter
existed. This script re-checks every un-applied ('found') row against the
v2 JD filter and marks over-experienced ones status='not_fit' (kept in the
tracker for audit, logged to rejected_log.csv, excluded from the dashboard
"To apply" list and the digest).

The job's ATS is inferred from its URL; if there is no API for it we fetch
the public job page HTML and strip tags - good enough for a yes/no
experience check. Jobs whose JD can't be fetched are left as 'found'.

Run manually:      python backfill_jd.py
Or via Actions:    workflow "jd-backfill" -> Run workflow
"""
import concurrent.futures as cf
import csv
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

from dashboard import write_dashboard
from fetchers.common import get_text
from jd import _get, analyze_jd, strip_html
from state import TRACKER_COLUMNS, migrate_tracker

ROOT = Path(__file__).parent
TRACKER = ROOT / "tracker.csv"
REJECTED = ROOT / "rejected_log.csv"


def fetch_jd_by_url(url, timeout):
    """Best JD source for a bare job URL. Returns plain text or None."""
    m = re.search(r"greenhouse\.io/([^/]+)/jobs/(\d+)", url)
    if m:
        d = _get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}", timeout)
        return strip_html(d.get("content", ""))
    m = re.search(r"jobs\.smartrecruiters\.com/([^/]+)/(\d+)", url)
    if m:
        d = _get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}", timeout)
        secs = (d.get("jobAd") or {}).get("sections") or {}
        return strip_html(" ".join(s.get("text", "") for s in secs.values() if isinstance(s, dict)))
    m = re.search(r"jobs\.lever\.co/([^/]+)/([\w-]+)", url)
    if m:
        d = _get(f"https://api.lever.co/v0/postings/{m.group(1)}/{m.group(2)}", timeout)
        return strip_html(d.get("descriptionPlain", "") + " "
                          + " ".join(l.get("content", "") for l in d.get("lists", [])))
    m = re.search(r"apply\.careers\.microsoft\.com/careers/job/(\d+)", url)
    if m:
        d = _get(f"https://apply.careers.microsoft.com/api/pcsx/position_details"
                 f"?position_id={m.group(1)}&domain=microsoft.com", timeout)
        return strip_html((d.get("data") or {}).get("jobDescription", ""))
    # Generic fallback: the public job page itself (works for amazon.jobs,
    # icims, google careers - they render the JD server-side).
    text = strip_html(get_text(url, timeout))
    return text if len(text) > 300 else None  # a JS shell has ~no text


def main():
    migrate_tracker()
    with open(TRACKER, newline="", encoding="utf-8") as f:
        rows = [{c: (r.get(c) or "") for c in TRACKER_COLUMNS}
                for r in csv.DictReader(f)]
    cfg = yaml.safe_load(open(ROOT / "companies.yaml", encoding="utf-8"))
    jdcfg = cfg["filters"]["jd"]
    timeout = cfg["settings"]["request_timeout"]

    todo = [r for r in rows if r["status"] == "found"]
    print(f"re-checking {len(todo)} 'found' rows against the JD filter...")

    def task(r):
        try:
            return r, fetch_jd_by_url(r["job_url"], timeout), None
        except Exception as e:  # noqa: BLE001
            return r, None, f"{type(e).__name__}: {e}"

    kept = dropped = unknown = 0
    rejected_rows = []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r, text, err in ex.map(task, todo):
            if text is None:
                unknown += 1
                print(f"  ?  JD unavailable ({err or 'page has no text'}): "
                      f"{r['role']} @ {r['company']}")
                continue
            v = analyze_jd(text, jdcfg)
            if v["verdict"] == "reject":
                dropped += 1
                r["status"] = "not_fit"
                r["notes"] = (r["notes"] + " | " if r["notes"] else "") \
                    + f"JD-backfill: {v['reason']}"
                rejected_rows.append((r, v["reason"]))
                print(f"  ✗  {r['role']} @ {r['company']} -> {v['reason']}")
            else:
                kept += 1
                if v["verdict"] == "borderline":
                    tag = f"JD-backfill: borderline {v['reason']}"
                    if tag not in r["notes"]:
                        r["notes"] = (r["notes"] + " | " if r["notes"] else "") + tag
                print(f"  ✓  {r['role']} @ {r['company']}"
                      + (f" (borderline {v['reason']})" if v["verdict"] == "borderline" else "")
                      + (" (fresher-friendly)" if v["fresher"] else ""))

    with open(TRACKER, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=TRACKER_COLUMNS)
        w.writeheader()
        w.writerows(rows)

    if rejected_rows:
        exists = REJECTED.exists()
        with open(REJECTED, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["date", "company", "title", "job_url", "reason"])
            today = datetime.now(timezone.utc).date().isoformat()
            for r, reason in rejected_rows:
                w.writerow([today, r["company"], r["role"], r["job_url"],
                            f"backfill: {reason}"])

    write_dashboard(rows, cfg["settings"])
    print(f"\nbackfill done: {kept} kept | {dropped} marked not_fit | "
          f"{unknown} JD unavailable (left as found)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
