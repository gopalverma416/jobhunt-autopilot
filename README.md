# JobHunt Autopilot

Zero-cost, low-maintenance off-campus job-search automation for SDE/SDE-1
roles in India. Polls official ATS APIs hourly via GitHub Actions, pushes
Telegram alerts with pre-built LinkedIn people-search links, tracks
everything in a CSV, and sends a 9 AM IST digest of follow-ups due.

**Cost: ₹0/month.** GitHub Actions free tier + public ATS APIs + Telegram
Bot API. No scraping of LinkedIn, no logging into your accounts, no
auto-applying — discovery, tracking and drafting only.

```
watcher (hourly)          digest (daily 9AM IST)
   |                          |
fetchers/* ──filter──► seen_jobs.json (dedupe, committed back to repo)
   |                          |
Telegram alert          tracker.csv ◄── track.py (your 5-second updates)
                              |
                         draft.py + templates/ (referral / recruiter messages)
```

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
