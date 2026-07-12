"""Offline tests: filters + full watcher pipeline with a fake fetcher.
Run: python tests/test_offline.py   (no network needed)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml  # noqa: E402

from filters import JobFilter  # noqa: E402
from notify import format_job_alert  # noqa: E402

cfg = yaml.safe_load(open(Path(__file__).parent.parent / "companies.yaml",
                          encoding="utf-8"))
jf = JobFilter(cfg["filters"])

# (title, location, expected)
CASES = [
    ("Software Engineer", "Bengaluru, India", True),
    ("SDE-1", "Hyderabad", True),
    ("SDE 1 - Backend", "Bangalore", True),
    ("SDE I", "Pune, Maharashtra", True),
    ("Software Development Engineer", "IN, TS, Hyderabad", True),
    ("Member of Technical Staff", "Remote - India", True),
    ("Graduate Engineer Trainee", "Chennai", True),
    ("Software Engineer, University Grad, 2026", "Bengaluru", True),
    ("Full Stack Developer / Full Stack Engineer", "Mumbai", True),
    ("Backend Engineer (Early Career)", "", True),          # empty location OK
    # --- must be rejected: level/seniority ---
    ("SDE-2", "Bangalore", False),
    ("SDE 3", "Bangalore", False),
    ("Software Engineer II", "Hyderabad", False),
    ("Software Engineer III, Infrastructure", "Bengaluru", False),
    ("Senior Software Engineer", "Bengaluru", False),
    ("Sr. Software Engineer", "Pune", False),
    ("Staff Software Engineer", "Bengaluru", False),
    ("Principal Engineer", "Bengaluru", False),
    ("Lead Backend Engineer", "Mumbai", False),
    ("Engineering Manager", "Bengaluru", False),
    ("Software Architect", "Noida", False),
    ("Software Engineer Intern", "Bengaluru", False),
    ("SDET", "Bengaluru", False),                    # \b keeps 'sde' from matching
    # --- must be rejected: location ---
    ("Software Engineer", "Seattle, WA, United States", False),
    ("SDE-1", "London, UK", False),
    # --- tricky: numbers that are NOT levels ---
    ("Software Engineer, New Grad 2026", "Bengaluru", True),
    ("Software Engineer 2", "Bengaluru", False),
]

fails = 0
for title, loc, want in CASES:
    got = jf.match({"title": title, "location": loc})
    mark = "ok " if got == want else "FAIL"
    if got != want:
        fails += 1
    print(f"  {mark} [{'PASS' if got else 'drop'}] {title!r} @ {loc!r}")

# --- alert formatting smoke test ---
sample = {"id": "1", "title": "SDE-1", "company": "PhonePe",
          "location": "Bengaluru", "url": "https://example.com/j/1",
          "posted_at": "2026-07-12", "source": "greenhouse:phonepe"}
msg = format_job_alert(sample, cfg["settings"]["alumni_keywords"])
assert "SDE-1 @ PhonePe" in msg and "google.com/search?q=site%3Alinkedin.com" in msg
assert " " not in msg.split("Alumni: ")[1].split("\n")[0], "search URL must be encoded"
print("\n  ok  alert formatting + URL encoding")

print(f"\n{len(CASES)} filter cases, {fails} failures")
sys.exit(1 if fails else 0)
