# JobHunt Autopilot (v2)

Zero-cost, low-maintenance off-campus job-search automation for SDE/SDE-1
roles in India. Polls official ATS APIs + public Telegram channel previews
hourly via GitHub Actions, filters by title *and full job description*,
detects reposts, pushes Telegram alerts wired to your own contact database,
and reports weekly on what's actually working.

**Cost: ₹0/month.** GitHub Actions free tier + public APIs + Telegram Bot
API. No scraping of LinkedIn, no logging into your accounts, no
auto-applying — discovery, tracking and drafting only.

```
watcher (hourly)                          digest (daily 9AM IST)   weekly report (Sun 9AM IST)
   |                                          |                        |
fetchers/* + t.me/s/ channels                 |                   analytics.py -> reports/YYYY-WW.md
   | title+location filter                    |
   | full-JD filter (new jobs only) ──► rejected_log.csv (audit weekly)
   | repost detection (seen_jobs.json signatures)
   | contact lookup (contacts.csv ◄── contact.py)
   v
Telegram alert ──► tracker.csv ◄── track.py (applied / outreach / response)
                        |
                   draft.py + templates/
```

**🔒 Privacy note:** `contacts.csv` contains personal data of real people.
This repo must stay **private**, and that data is for your personal
outreach only.

## Setup (one time, ~15 minutes)

### 1. Create the Telegram bot

1. In Telegram, message **@BotFather** → send `/newbot` → pick a name and a
   username (must end in `bot`). BotFather replies with a **bot token** like
   `7123456789:AAF...xyz`. Save it.
2. Open a chat with your new bot and send it any message (e.g. "hi") —
   a bot cannot message you first.
3. Get your **chat id**: open
   `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   in a browser and find `"chat":{"id":123456789,...}` in the JSON.
   That number is your chat id.

### 2. Create the GitHub repo

1. Create a **private** repo (e.g. `jobhunt-autopilot`) and push this folder:
   ```bash
   cd jobhunt-autopilot
   git init && git add -A && git commit -m "initial"
   git branch -M main
   git remote add origin git@github.com:<you>/jobhunt-autopilot.git
   git push -u origin main
   ```
2. Add the secrets: repo → **Settings → Secrets and variables → Actions →
   New repository secret**:
   - `TELEGRAM_BOT_TOKEN` = the token from BotFather
   - `TELEGRAM_CHAT_ID` = your chat id
3. Repo → **Actions** tab → enable workflows if prompted → open **watcher**
   → **Run workflow** to test. First run seeds the dedupe state and sends a
   summary instead of flooding you; after that you only get genuinely new
   postings.

Free-tier budget: hourly × ~1 min ≈ 745 min/month, well inside the 2,000
free minutes for private repos. Don't increase the frequency beyond hourly.
GitHub cron can lag 10–30 min at peak; that's expected.

### 3. Try it locally (optional)

```bash
pip install -r requirements.txt
python watcher.py --dry-run    # fetches + filters, prints alerts, writes nothing
```

## Daily use

- **Alert arrives** → open the job link, apply, then:
  `python track.py applied <job-id-or-url-fragment> --resume v12`
  (or just edit `tracker.csv` in the GitHub web UI — the watcher only
  appends, your edits are safe.)
- **Found a person to message** (use the alert's tap-to-search links):
  `python track.py outreach <job> --contact "Priya S" --linkedin <url>`
  → follow-up auto-scheduled for +4 days.
- **Need the message text**:
  `python draft.py referral_alumni <job>` or
  `python draft.py cold_recruiter <job> --contact "Priya"` or
  `python draft.py followup <job>` → copy, personalize one line, send.
- **9 AM IST digest** tells you what's new, what follow-ups are due
  (`python track.py followup <job> --days 7` after you nudge), and your
  weekly application count.
- **Check `manual_check.md` companies ~2x/week** — those can't be polled.

## Tuning filters

Everything is in `companies.yaml`:

- `filters.include_titles` — plain keywords, matched as whole words,
  case-insensitive (`-`/space interchangeable, so `sde 1` matches `SDE-1`).
- `filters.exclude_title_patterns` — Python regexes. The level rule
  `'[-–—/. ][23]\b'` is why "SDE-2" is dropped but "SDE-1" and "2024" pass.
- `filters.locations_allow` — substring match on the location field;
  empty locations pass (global-remote posts often have no location).
- `settings.max_alerts_per_run` — flood protection.

### v2: full-JD filter (`filters.jd`)

After a NEW job passes the title filter, its full description is fetched
(concurrently, 10s timeout; typically 0–5 per run so runtime is unaffected)
and scanned for experience requirements:

- `hard_reject_years: 3` — "3+ years", "minimum of 3 years", "5 years of
  experience" → **rejected**, logged to `rejected_log.csv` with the reason.
  Audit that file weekly and tune these knobs.
- `range_borderline_min: 2` — "2-4 years" → alerted with a `🤔 2-4 yrs` tag.
- "0-2 years", "0 to 1 year", "up to 2 years" always pass.
- `fresher_patterns` — any match adds a `✅ fresher-friendly` tag.
- If the JD can't be fetched (Google source, network hiccup), the alert is
  sent anyway with `⚠️ JD unverified`.
- Rejected jobs still enter `seen_jobs.json` so they're never re-processed.

## v2: contact database (`contacts.csv` + `contact.py`)

The referral engine. When an alert fires and you have contacts at that
company, the alert shows *your people* instead of generic search links
(company aliases like Eternal↔Zomato are handled via `aliases:` in the YAML).

```bash
python contact.py add --name "Krishna A" --company PhonePe --role SDE-2 \
    --linkedin https://linkedin.com/in/... --relationship warm --source alumni --school MANIT
python contact.py update Krishna --contacted today --context "agreed to refer"
python contact.py list --company PhonePe      # or --due
python contact.py import apify_export.csv     # best-effort column mapping
```

- Logging an outreach auto-schedules a **+5 day follow-up nudge** in the
  daily digest.
- **Anti-spam guard:** contacting someone twice within 14 days prints a
  warning, and the digest never suggests the same person more than once
  per 14 days.
- The two `DUMMY` rows are demo data — replace them. The watcher ignores
  DUMMY rows as soon as you add one real contact.

## v2: Telegram job channels

Public channels are polled via `https://t.me/s/<channel>` (plain GET, no
account, no Telegram API). Fill `telegram_channels:` in `companies.yaml`
with 3–6 Indian fresher-hiring channels **you** trust (the @name without @),
then run `python watcher.py --dry-run` once: the log prints
`CHAN <name>: N msgs` per channel, or a warning if the channel has web
previews disabled (those can't be polled — pick another).

A message is forwarded (tagged `📣 CHANNEL`, trimmed to 500 chars, with a
link to the original) only if it contains a role keyword AND a fresher
signal (`channel_fresher_signals:`). Channel finds are NOT auto-added to
the tracker — add the good ones yourself with `track.py`.

## v2: repost detection

Every job gets a signature (`company|normalized title` — see MIGRATION.md
for why location is excluded). If a "new" URL matches a signature first
seen **21+ days ago**, the alert is tagged `🔁 REPOST — likely unfilled,
push hard with a referral`, mentions your contacts at that company, and —
if the tracker shows you applied to the earlier posting — tells you to
follow up rather than re-apply.

## v2: weekly report (Sundays 9 AM IST)

`analytics.py` reads tracker + contacts and sends a Telegram report, also
committed to `reports/YYYY-WW.md`:

- **Funnel** — found → applied → OA → interview → offer, all-time & last 7d.
- **Response rate by channel** — needs you to log `track.py outreach ...
  --channel referral|linkedin|email` and `track.py response <job> yes|no`.
- **By resume version** — tag applications with `--resume v12` to populate.
- **By company type** — the `type:` field on each company in the YAML.
- **Observations** — 2-3 plain-English takeaways; honest about tiny samples
  ("n=4 — too early to conclude"); flags follow-ups overdue >7 days.

### New tracker columns (v2)

`response` (yes/no/pending) was added — set it with
`python track.py response <job> yes` when someone replies. Existing rows
migrate automatically (see MIGRATION.md).

## Adding a company

Find its ATS, then add one line under `companies:`.

| If careers page URL looks like | ATS | Config line |
|---|---|---|
| `job-boards.greenhouse.io/<slug>` or `boards.greenhouse.io/<slug>` | greenhouse | `{name: X, ats: greenhouse, slug: <slug>}` |
| `jobs.lever.co/<slug>` | lever | `{name: X, ats: lever, slug: <slug>}` |
| `jobs.ashbyhq.com/<slug>` | ashby | `{name: X, ats: ashby, slug: <slug>}` |
| `jobs.smartrecruiters.com/<Slug>/...` | smartrecruiters | `{name: X, ats: smartrecruiters, slug: <Slug>}` |
| `<tenant>.wd<N>.myworkdayjobs.com/<site>` | workday | `{name: X, ats: workday, tenant: <tenant>, wd: <N>, site: <site>}` |

Verify before committing (one command):
```bash
python -c "
import yaml; from fetchers import FETCHERS
cfg={'name':'X','ats':'greenhouse','slug':'SLUG'}   # <- edit me
s=yaml.safe_load(open('companies.yaml'))['settings']
jobs=FETCHERS[cfg['ats']](cfg,s); print(len(jobs), jobs[0] if jobs else 'EMPTY')"
```
If it errors or prints EMPTY, the slug is wrong → put the company in
`manual_check.md` instead. Never add unverified endpoints.

## Verification log (2026-07-12)

Every source in `companies.yaml` was fetched live during the build:

| Source | Evidence |
|---|---|
| Greenhouse ×7 (PhonePe, Postman, Rubrik, Canonical, Groww, Razorpay, Arcesium) | jobs JSON returned for each; e.g. Groww "Platform Engineer - III", Razorpay 52 postings |
| Lever (CRED) | postings JSON with hostedUrl links |
| SmartRecruiters (Zomato1, Visa) | postings JSON; e.g. Zomato "Software Engineer – Back End", Gurugram |
| Workday ×6 (Adobe, Salesforce, Qualcomm, Mastercard, Walmart, Sprinklr) | board pages/job URLs verified per tenant + CXS POST tested live on Adobe (HTTP 200, 96 results) |
| Amazon | search.json: 371 India hits, newest "SDE, Payroll Tax & Accounting Tech" (Hyderabad) |
| Microsoft | NEW endpoint `apply.careers.microsoft.com/api/pcsx/search` (old gcsservices API is dead); returned "Software Engineer 2", Hyderabad/Bangalore |
| Atlassian | `atlassian.com/endpoint/careers/listings`: 199-role JSON array |
| Google | HTML results page: 199 India SWE roles, job IDs parseable (v3 API is dead) |

## v2.2: LLM match scoring (optional), resilience, dedup

**Gemini fit score.** If you add a `GEMINI_API_KEY` secret (free key from
https://aistudio.google.com/apikey), each job that passes the filters gets a
`🎯 0-100` fit score + one-line reason in its alert, and alerts arrive
best-match-first. The score is compared against `profile.md` — **edit that
file** to describe yourself; it's the "you" the model matches against. Fully
optional: no key = no scoring, everything else works unchanged. Free tier
easily covers the 0-5 new jobs/run this produces. Model is set in
`companies.yaml → settings.gemini`.

**Datacenter-IP resilience.** GitHub Actions runs from Azure IPs that big ATS
stacks sometimes soft-block. `fetchers/common.py` now rotates browser
User-Agents, adds request jitter, and retries once with backoff on
403/429/5xx. (No proxies/Playwright — those don't fit the free-tier 1-min
budget.) A source still failing is logged `FAIL` and skipped, as before.

**Duplicate collapsing.** Multiple simultaneous reqs for the same
company+title+location (e.g. the same ClickHouse C++ role posted 5×) now
collapse to a single alert; the rest are marked seen so they never re-fire.

**Adding companies safely.** Only add a company after you've *verified its
slug/tenant returns jobs* (README "Adding a company" has the one-command
check). An unverified guess just 404s every run. Companies whose ATS you
can't confirm belong in `manual_check.md`, not `companies.yaml`.

## Troubleshooting

- **A source starts failing every run** — open the Actions log; the watcher
  prints `FAIL <company>: <error>` per source and carries on. 404 usually
  means the company changed ATS/slug: re-discover it and update the YAML,
  or move it to `manual_check.md`.
- **`google_html` returns 0 jobs repeatedly** — Google changed the page
  markup or is serving a consent wall to datacenter IPs. It's the flakiest
  source by design; the regex lives in `fetchers/google_html.py`.
- **Microsoft/SmartRecruiters 403 from Actions** — some APIs occasionally
  block datacenter IPs. The run continues without them; if it persists,
  move the company to `manual_check.md`.
- **No Telegram messages** — check both secrets, and make sure you've sent
  the bot a message at least once.
- **Alert flood after editing filters** — new filter matches on old
  postings all look "new". Lower `max_alerts_per_run` caps the damage.

## Design constraints (do not break these)

- One request per source per run, 10 s timeout, custom User-Agent.
- Hourly is the ceiling — the Actions math above depends on it.
- Watcher must exit 0 on partial failure (only all-sources-down exits 1).
- No LinkedIn scraping, no auto-apply, no credentialed requests. Ever.
