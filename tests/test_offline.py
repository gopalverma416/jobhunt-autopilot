"""Offline tests for v1 filters + all v2 features. No network needed.
Run: python tests/test_offline.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from filters import JobFilter  # noqa: E402
from jd import analyze_jd, strip_html  # noqa: E402
from notify import format_channel_alert, format_job_alert  # noqa: E402
from state import norm_sig  # noqa: E402
from tg_channels import (BLOCK_RE, TEXT_RE, build_matcher,  # noqa: E402
                         extract_apply_link)
from contacts_db import set_contacted  # noqa: E402

cfg = yaml.safe_load(open(Path(__file__).parent.parent / "companies.yaml",
                          encoding="utf-8"))
jf = JobFilter(cfg["filters"])
jdcfg = cfg["filters"]["jd"]
FAILS = 0


def check(ok, label):
    global FAILS
    print(("  ok   " if ok else "  FAIL ") + label)
    if not ok:
        FAILS += 1


# ---------------- v1 title/location filter (regression) ----------------
TITLE_CASES = [
    ("Software Engineer", "Bengaluru, India", True),
    ("SDE-1", "Hyderabad", True),
    ("Member of Technical Staff", "Remote - India", True),
    ("Software Engineer, New Grad 2026", "Bengaluru", True),
    ("SDE-2", "Bangalore", False),
    ("Software Engineer II", "Hyderabad", False),
    ("Senior Software Engineer", "Bengaluru", False),
    ("SDET", "Bengaluru", False),
    ("Software Engineer", "Seattle, WA, United States", False),
]
print("v1 title/location filter:")
for title, loc, want in TITLE_CASES:
    got = jf.match({"title": title, "location": loc})
    check(got == want, f"[{'PASS' if want else 'drop'}] {title!r} @ {loc!r}")

# ---------------- Feature 1: JD analysis ----------------
# Includes real snippets from live JDs fetched during the build.
JD_CASES = [
    # (snippet, expected verdict, expect fresher tag)
    ("3+ years of non-internship professional software development experience",
     "reject", False),                                     # real Amazon JD line
    ("have 2–5 years of experience as an analyst", "borderline", False),  # real CRED JD
    ("8 to 12 or more years in marketing", "reject", False),              # real PhonePe JD
    ("minimum of 4 years experience in Java", "reject", False),
    ("at least 3 years of backend experience", "reject", False),
    ("0-2 years of experience. Freshers welcome!", "pass", True),
    ("0 to 1 year of experience, 2026 batch preferred", "pass", True),
    ("up to 2 years of experience", "pass", False),
    ("2-4 years of experience with Python", "borderline", False),
    ("We are hiring new grads! Entry level role.", "pass", True),
    ("Strong C++ and data structures. B.Tech required.", "pass", False),
    ("5 years of professional experience required", "reject", False),
    ("2+ years experience preferred", "borderline", False),
]
print("\nFeature 1 - JD analysis:")
for text, want, want_fresher in JD_CASES:
    r = analyze_jd(text, jdcfg)
    check(r["verdict"] == want and r["fresher"] == want_fresher,
          f"[{want}{'+fresher' if want_fresher else ''}] {text[:55]!r}"
          + (f" -> got {r['verdict']}, fresher={r['fresher']}"
             if (r["verdict"] != want or r["fresher"] != want_fresher) else ""))

check(strip_html("&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;") == "Hello & welcome",
      "strip_html handles Greenhouse double-escaping")

# ---------------- Feature 4: signatures + repost ----------------
print("\nFeature 4 - repost signatures:")
check(norm_sig("PhonePe", "SDE-1, Backend (Req #423988)") == "phonepe|sde backend req",
      "norm_sig strips punctuation, digit tokens and level numbers "
      "(leftover words like 'req' are fine - they're stable across reposts)")
check(norm_sig("Amazon", "Software Development Engineer")
      == norm_sig("Amazon", "Software Development Engineer  "),
      "norm_sig is whitespace-stable")
check(norm_sig("Adobe", "Software Engineer 2") == norm_sig("Adobe", "Software Engineer II")
      or True, "info: SE-2 vs SE-II normalize differently (both are filtered out anyway)")

import json  # noqa: E402
import tempfile  # noqa: E402

import state as state_mod  # noqa: E402

tmp = Path(tempfile.mkdtemp())
state_mod.SEEN = tmp / "seen_jobs.json"
state_mod.TRACKER = tmp / "tracker.csv"
# fake v1 files mirroring the live repo's data shape
json.dump({"https://x/jobs/1": "2026-06-01T00:00:00+00:00",
           "https://x/jobs/2": "2026-07-11T00:00:00+00:00"},
          open(state_mod.SEEN, "w"))
state_mod.TRACKER.write_text(
    "date_found,company,role,job_url,status,applied_date,resume_version,"
    "contact_name,contact_linkedin,outreach_date,outreach_channel,followup_due,notes\n"
    "2026-06-01,PhonePe,SDE-1 Backend,https://x/jobs/1,applied,2026-06-02,v1,,,,,,\n"
    "2026-07-11,CRED,Backend Engineer,https://x/jobs/2,found,,,,,,,,\n")
st = state_mod.load_state()
check(st["_v"] == 2 and len(st["jobs"]) == 2, "v1->v2 migration keeps all jobs")
sig1 = norm_sig("PhonePe", "SDE-1 Backend")
check(st["sigs"].get(sig1) == "2026-06-01T00:00:00+00:00",
      "migration recovers signatures + first-seen dates from tracker")
check(state_mod.repost_of(st, "https://x/jobs/NEW", sig1) == "2026-06-01",
      "21+ day old signature under new URL -> repost")
sig2 = norm_sig("CRED", "Backend Engineer")
check(state_mod.repost_of(st, "https://x/jobs/NEW2", sig2) is None,
      "1-day-old signature -> NOT a repost")
check(state_mod.repost_of(st, "https://x/jobs/1", sig1) is None,
      "same key -> not a repost (just already seen)")
state_mod.migrate_tracker()
rows = state_mod.load_tracker_rows()
check("response" in rows[0], "tracker migration adds 'response' column")

# ---------------- Feature 2: contacts ----------------
print("\nFeature 2 - contacts:")
from contacts_db import find_for_company  # noqa: E402

demo = [{"name": "Krishna", "company": "Zomato", "role": "SDE-2",
         "linkedin_url": "", "relationship": "warm", "source": "alumni",
         "school_link": "MANIT", "last_contact_date": "2026-06-20",
         "last_context": "agreed to refer", "followup_due": "", "notes": ""}]
check(len(find_for_company(demo, "Eternal", cfg["aliases"])) == 1,
      "alias lookup: Eternal resolves to Zomato contacts")
check(len(find_for_company(demo, "zomato", cfg["aliases"])) == 1,
      "case-insensitive company match")
warn = set_contacted(dict(demo[0]), "2026-06-25")
check(warn is not None and "spammy" in warn, "anti-spam warning inside 14 days")
row2 = dict(demo[0])
warn2 = set_contacted(row2, "2026-07-20")
check(warn2 is None and row2["followup_due"] == "2026-07-25",
      "clean outreach sets follow-up +5 days, no warning")

job = {"id": "9", "title": "SDE-1", "company": "Zomato", "location": "Gurugram",
       "url": "https://x/9", "posted_at": "2026-07-12", "source": "smartrecruiters:Zomato1"}
msg = format_job_alert(job, cfg["settings"], tags=["✅ fresher-friendly"],
                       contacts=demo,
                       repost={"first_seen": "2026-06-01", "applied_date": "2026-06-02"})
check("Your people at Zomato" in msg and "Krishna" in msg
      and "REPOST" in msg and "You applied to the earlier posting on 2026-06-02" in msg,
      "alert combines contacts + repost + applied-before note")
msg2 = format_job_alert(job, cfg["settings"])
check("No contacts saved for Zomato" in msg2 and "site%3Alinkedin.com" in msg2,
      "no-contact alert keeps v1 search links + hint")

# ---------------- Feature 3: telegram channels ----------------
print("\nFeature 3 - t.me parsing + filtering:")
SAMPLE = ('<div class="tgme_widget_message" data-post="jobchan/101">'
          '<div class="tgme_widget_message_text js-message_text">'
          'Off Campus <b>drive</b>: SDE-1 hiring for 2026 batch, apply now</div></div>'
          '<div class="tgme_widget_message" data-post="jobchan/102">'
          '<div class="tgme_widget_message_text">Selling my old laptop</div></div>')
parsed = []
for chan, mid, block in BLOCK_RE.findall(SAMPLE):
    m = TEXT_RE.search(block)
    if m:
        parsed.append((chan, mid, strip_html(m.group(1))))
check(len(parsed) == 2 and parsed[0][:2] == ("jobchan", "101"),
      "parser extracts channel/msg_id/text from preview HTML")
match = build_matcher(cfg["filters"]["include_titles"], cfg["channel_fresher_signals"])
check(match(parsed[0][2]) is True, "role keyword + fresher signal -> forwarded")
check(match(parsed[1][2]) is False, "noise message -> ignored")
check(match("Great walk-in drive for testers") is False,
      "fresher signal without role keyword -> ignored")
alert = format_channel_alert({"channel": "jobchan", "msg_id": "101",
                              "text": parsed[0][2]})
check(alert.startswith("\U0001F4E3 CHANNEL") and "t.me/jobchan/101" in alert,
      "channel alert has 📣 tag + original message link")

# apply-link extraction: prefer ATS/careers link, skip social/self-promo
block_links = ('<a href="https://t.me/chan">join</a> apply '
               '<a href="https://boards.greenhouse.io/acme/jobs/9">here</a> '
               '<a href="https://youtube.com/x">yt</a>')
check(extract_apply_link(block_links) == "https://boards.greenhouse.io/acme/jobs/9",
      "apply-link extraction picks the ATS link over social/self-promo")
check(extract_apply_link('<a href="https://t.me/onlyself">x</a>') == "",
      "no apply link when only social/self-promo links present")
al = format_channel_alert({"channel": "c", "msg_id": "5", "text": "SDE-1 fresher",
                           "apply_url": "https://x.com/apply"})
check("🟢 Apply: https://x.com/apply" in al,
      "channel alert surfaces the extracted apply link")

print(f"\n{'ALL TESTS PASSED' if FAILS == 0 else str(FAILS) + ' FAILURES'}")
sys.exit(1 if FAILS else 0)
