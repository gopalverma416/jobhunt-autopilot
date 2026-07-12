"""Weekly analytics (Feature 5). Runs Sundays 03:30 UTC (= 9 AM IST).

Reads tracker.csv + contacts.csv + companies.yaml and produces:
  - funnel: found -> applied -> oa -> interview -> offer (all-time & last 7d)
  - response rate by outreach channel (referral / cold / recruiter ...)
  - applications & responses per resume_version
  - response rate by company `type` (set per company in companies.yaml)
  - 2-3 plain-English observations + overdue follow-ups flag
Sends the report to Telegram (auto-split under the 4096-char limit) and
commits reports/YYYY-WW.md for history. Honest about tiny sample sizes.
"""
import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from contacts_db import load_contacts
from notify import send_telegram

ROOT = Path(__file__).parent
TRACKER = ROOT / "tracker.csv"
REPORTS = ROOT / "reports"

FUNNEL = ["found", "applied", "oa", "interview", "offer"]
# how many funnel stages each status implies were REACHED
# (an "oa" row reached found + applied + oa; a rejection implies an application)
REACHED = {"found": 1, "applied": 2, "referred": 2, "rejected": 2,
           "oa": 3, "interview": 4, "offer": 5}


def parse_date(s):
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def small_n(n, threshold=5):
    return f" (n={n} — too early to conclude)" if n < threshold else ""


def pct(part, whole):
    return f"{part}/{whole}" + (f" ({100 * part // whole}%)" if whole else "")


def main():
    rows = []
    if TRACKER.exists():
        with open(TRACKER, newline="", encoding="utf-8") as f:
            # normalize: tolerate pre-v2 files that lack the 'response' column
            rows = [{k: (r.get(k) or "") for k in
                     list(r.keys()) + ["response", "outreach_channel",
                                       "resume_version", "followup_due"]}
                    for r in csv.DictReader(f)]
    contacts = [c for c in load_contacts()
                if not c["name"].upper().startswith("DUMMY")]
    with open(ROOT / "companies.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    company_type = {c["name"].lower(): c.get("type", "unknown")
                    for c in cfg.get("companies", [])}

    today = datetime.now(timezone.utc).date()
    week_ago = today - timedelta(days=7)
    lines = [f"# JobHunt weekly report — {today.isoformat()}", ""]

    # ---- funnel ----
    def funnel_counts(subset):
        counts = {s: 0 for s in FUNNEL}
        for r in subset:
            for stage in FUNNEL[:REACHED.get(r.get("status", ""), 0)]:
                counts[stage] += 1
        return counts

    all_c = funnel_counts(rows)
    last7 = funnel_counts([r for r in rows
                           if (parse_date(r.get("date_found")) or week_ago) > week_ago])
    lines.append("## Funnel (reached-at-least stage)")
    lines.append("stage      | all-time | last 7d")
    lines.append("---------- | -------- | -------")
    for s in FUNNEL:
        lines.append(f"{s:<10} | {all_c[s]:<8} | {last7[s]}")
    lines.append("")

    # ---- response rate by channel ----
    lines.append("## Response rate by outreach channel")
    by_channel = {}
    for r in rows:
        ch = (r.get("outreach_channel") or "").strip().lower()
        if not ch and r.get("status") in ("applied", "oa", "interview", "offer", "rejected"):
            ch = "cold application"
        if not ch:
            continue
        yes = r.get("response", "").strip().lower() == "yes"
        pending = r.get("response", "").strip().lower() in ("", "pending")
        a, y, p = by_channel.get(ch, (0, 0, 0))
        by_channel[ch] = (a + 1, y + (1 if yes else 0), p + (1 if pending else 0))
    if by_channel:
        for ch, (attempts, yes, pending) in sorted(by_channel.items()):
            lines.append(f"- {ch}: {pct(yes, attempts)} responses"
                         f" ({pending} pending){small_n(attempts)}")
    else:
        lines.append("- no outreach logged yet (use track.py outreach / response)")
    lines.append("")

    # ---- by resume version ----
    lines.append("## By resume version")
    by_resume = {}
    for r in rows:
        v = (r.get("resume_version") or "").strip()
        if not v:
            continue
        yes = r.get("response", "").strip().lower() == "yes"
        a, y = by_resume.get(v, (0, 0))
        by_resume[v] = (a + 1, y + (1 if yes else 0))
    if by_resume:
        for v, (apps, yes) in sorted(by_resume.items()):
            lines.append(f"- {v}: {apps} applications, {pct(yes, apps)} responses{small_n(apps)}")
    else:
        lines.append("- no resume versions logged yet (track.py applied <job> --resume vX)")
    lines.append("")

    # ---- by company type ----
    lines.append("## By company type")
    by_type = {}
    for r in rows:
        if r.get("status") not in ("applied", "referred", "oa", "interview", "offer", "rejected"):
            continue
        t = company_type.get((r.get("company") or "").lower(), "unknown")
        yes = r.get("response", "").strip().lower() == "yes" \
            or r.get("status") in ("oa", "interview", "offer")
        a, y = by_type.get(t, (0, 0))
        by_type[t] = (a + 1, y + (1 if yes else 0))
    if by_type:
        for t, (apps, yes) in sorted(by_type.items()):
            lines.append(f"- {t}: {apps} applications, {pct(yes, apps)} responses{small_n(apps)}")
    else:
        lines.append("- no applications yet")
    lines.append("")

    # ---- observations ----
    lines.append("## What the data says")
    obs = []
    ref = by_channel.get("referral") or by_channel.get("linkedin")
    cold = by_channel.get("cold application")
    if ref and cold and ref[0] >= 3 and cold[0] >= 3:
        obs.append(f"Referral-ish outreach: {pct(ref[1], ref[0])} responses vs cold applies "
                   f"{pct(cold[1], cold[0])}. "
                   + ("Prioritize referral-first." if ref[1] * cold[0] > cold[1] * ref[0]
                      else "Cold applies are holding their own — keep both lanes."))
    total_apps = all_c["applied"]
    if total_apps < 10:
        obs.append(f"Only {total_apps} applications so far — volume is the bottleneck, "
                   f"not conversion. Aim for 10+/week before reading these stats.")
    overdue = [r for r in rows
               if r.get("followup_due")
               and (parse_date(r["followup_due"]) or today) < today - timedelta(days=7)
               and r.get("status") not in ("offer", "rejected")]
    if overdue:
        obs.append(f"⚠️ {len(overdue)} follow-up(s) overdue by more than 7 days — "
                   f"oldest: {min(r['followup_due'] for r in overdue)}. Clear them today.")
    never = sum(1 for c in contacts if not c["last_contact_date"])
    if never >= 3:
        obs.append(f"{never} saved contacts never contacted — pick 2 and send the "
                   f"referral template this week.")
    if not obs:
        obs.append("Not enough data for patterns yet. Keep applying + logging.")
    lines += [f"{i+1}. {o}" for i, o in enumerate(obs)]

    report = "\n".join(lines)

    # commit history file
    REPORTS.mkdir(exist_ok=True)
    iso_year, iso_week, _ = today.isocalendar()
    out = REPORTS / f"{iso_year}-W{iso_week:02d}.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(f"wrote {out}")

    send_telegram("\U0001F4CA " + report)


if __name__ == "__main__":
    main()
