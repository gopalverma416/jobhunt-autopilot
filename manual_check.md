# Companies without a usable public ATS endpoint

These were all tested live on **2026-07-12**. No stable, public,
no-auth JSON endpoint was found, so the watcher can't poll them.
Bookmark these and check ~2x per week (Tue/Fri works well).

| Company | Careers URL | What I found |
|---|---|---|
| Swiggy | https://careers.swiggy.com | Custom SPA; no jobs API surfaced in network traffic |
| Meesho | https://www.meesho.io/jobs | Next.js site, jobs loaded client-side; no stable public API |
| Zepto | https://zepto.talentrecruit.com/career-page | TalentRecruit ATS, no public JSON API |
| Flipkart | https://www.flipkartcareers.com | Custom portal, no public API |
| PayU | https://payu.hire.trakstar.com / https://careers.payu.in | Trakstar + SuccessFactors, no public JSON |
| Uber | https://www.uber.com/us/en/careers/list/ | API exists but POST + CSRF token; fragile, not worth automating |
| Oracle | https://careers.oracle.com/en/sites/jobsearch/jobs?keyword=software+engineer | Oracle HCM REST exists but couldn't be verified reliably |
| Intuit | https://jobs.intuit.com | Radancy platform, no public JSON API |
| Goldman Sachs | https://higher.gs.com/results?LOCATION=Bengaluru | GraphQL POST API (opaque payload) |
| DE Shaw | https://www.deshaw.com/careers | Custom site |
| Cisco | https://jobs.cisco.com | Custom portal, HTML only |
| Nutanix | https://careers.nutanix.com/en/jobs/ | Phenom People site; widget API returned nothing publicly |
| Cohesity | https://www.cohesity.com/careers/open-positions/ | Custom listing, no public API |
| Media.net | https://careers.media.net/engineering/ | WordPress careers pages, no API |

## Watchlist note: Zomato / Eternal

Zomato's SmartRecruiters board (`Zomato1`) IS polled by the watcher, but
it's sparse and mostly stale — Eternal (the parent brand) posts most new
roles at https://www.eternal.com/careers/ instead. Check that page manually
too.

## Workday companies pending tenant verification (added 2026-07-12)

These are real fresher-hiring companies, but their Workday `tenant`/`wd`/`site`
values need live network inspection before adding to `companies.yaml` (a
guessed tenant just 404s every run). To wire one up: open its careers page,
watch the network tab for a POST to `.../wday/cxs/{tenant}/{site}/jobs`, read
the `wd{N}` from the hostname, and add the verified line to `companies.yaml`.

| Company | Careers URL |
|---|---|
| AMD | https://careers.amd.com |
| Intel | https://jobs.intel.com |
| SAP | https://jobs.sap.com (SuccessFactors, not Workday - may need a different fetcher) |
| ServiceNow | https://careers.servicenow.com |
| Palo Alto Networks | https://jobs.paloaltonetworks.com |
| Siemens EDA | https://jobs.siemens.com |
| Nutanix | https://careers.nutanix.com (Phenom platform - no public JSON) |

## Tips

- Several of these (Swiggy, Meesho, Zepto, Flipkart) post fresher drives on
  LinkedIn/Instahyre before their own portals. Set LinkedIn job alerts for
  them as a complement.
- If any of these companies later moves to Greenhouse/Lever/Ashby/
  SmartRecruiters/Workday, add one line to `companies.yaml` and it's
  automated (see README "Adding a company").
