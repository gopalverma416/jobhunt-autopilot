# v1 → v2 migration notes

Two file schemas changed. **Both migrations are automatic and idempotent** —
they run at the start of every watcher run (and `track.py` triggers the
tracker one too). You don't have to do anything.

## seen_jobs.json: flat map → structured v2

- v1: `{"<job_url>": "<first_seen_iso>"}`
- v2: `{"_v": 2, "jobs": {...}, "sigs": {...}, "extra": {...}}`
  - `jobs` — every processed job with its first-seen date and role signature
  - `sigs` — earliest sighting per `company|normalized-title` signature
    (powers 🔁 repost detection)
  - `extra` — Telegram-channel message dedupe (`tg:<channel>:<msg_id>`)

The migration keeps every v1 entry and **back-fills signatures from
tracker.csv** (v1 keys are job URLs; tracker rows carry company + role for
each URL), so reposts of jobs seen *before* the upgrade are still detected.

**Deliberate deviation from the spec:** the signature is
`company|normalized title` — location is *not* included. Reason: the same
role renders its location differently per source ("Bengaluru" vs
"Bangalore, KA, IN" vs "India, Multiple Locations"), which produced false
negatives. The 21-day age gate + different-URL requirement + India-only
location filter keep false positives rare. If you want location back, edit
`norm_sig()` in `state.py`.

## tracker.csv: one new column

- Added `response` (yes / no / pending) after `followup_due` — feeds the
  weekly response-rate analytics. Set it with
  `python track.py response <job> yes|no|pending`.
- Existing rows get an empty value; nothing else changes. The watcher
  rewrites the header once and preserves all rows.

## New files (no migration needed)

- `contacts.csv` — alumni/recruiter contact DB (seeded with 2 DUMMY rows;
  replace them). **Contains personal data — repo must stay private.**
- `rejected_log.csv` — created on first JD rejection; audit it weekly.
- `reports/YYYY-WW.md` — weekly analytics history.

## Verification on your live data

Run `python watcher.py --dry-run` (or just let the hourly run fire): the log
prints one line per migration, e.g.
`migrated seen_jobs.json v1 -> v2: 34 jobs, N signatures recovered` and
`migrated tracker.csv: columns [...] -> [...]`. Dry-run does NOT write the
migrated files; the first real run commits them.
