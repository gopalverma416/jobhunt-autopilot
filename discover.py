"""ATS auto-discovery + bulk import.

Given a list of candidate company "slugs", probe the public ATS APIs
(Greenhouse / Lever / Ashby / SmartRecruiters) and keep the ones that return
real jobs. This is the ToS-safe version of what big job aggregators do:
poll thousands of standard ATS endpoints instead of scraping.

Workday is intentionally OUT of scope here - it needs a tenant/wd/site trio
that can't be guessed from a slug, so add those manually (see manual_check.md).

Usage:
  python discover.py stripe figma vercel          # probe a few, print results
  python discover.py --file candidates.txt        # probe a bulk list, print
  python discover.py --file candidates.txt --append --min-jobs 1
        # append VERIFIED, NEW companies to companies.yaml (deduped by slug)

Run it as a GitHub Actions workflow (discover.yml) so the probing happens from
a network that can reach these APIs, and new companies auto-commit.
"""
import argparse
import concurrent.futures as cf
import re
import sys
from pathlib import Path

from fetchers.common import get_json

ROOT = Path(__file__).parent
CONFIG = ROOT / "companies.yaml"

# Each prober returns the number of open postings for a slug, or -1 if the
# board doesn't exist / has none. Kept deliberately cheap (1 request each).
PROBES = {}


def _probe_greenhouse(slug, timeout):
    d = get_json(f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs", timeout)
    return len(d.get("jobs", []))


def _probe_lever(slug, timeout):
    d = get_json(f"https://api.lever.co/v0/postings/{slug}?mode=json&limit=1", timeout)
    return len(d) if isinstance(d, list) else -1


def _probe_ashby(slug, timeout):
    d = get_json(f"https://api.ashbyhq.com/posting-api/job-board/{slug}", timeout)
    return len(d.get("jobs", []))


def _probe_smartrecruiters(slug, timeout):
    d = get_json(f"https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1", timeout)
    return int(d.get("totalFound", 0))


PROBES = {
    "greenhouse": _probe_greenhouse,
    "lever": _probe_lever,
    "ashby": _probe_ashby,
    "smartrecruiters": _probe_smartrecruiters,
}


def discover_one(slug, timeout=10):
    """Return list of (ats, count) for every ATS that has jobs for this slug."""
    found = []
    for ats, fn in PROBES.items():
        try:
            n = fn(slug, timeout)
            if n and n > 0:
                found.append((ats, n))
        except Exception:  # noqa: BLE001 - 404/JSON errors = "not this ATS"
            pass
    return found


def existing_slugs():
    """Slugs already present in companies.yaml, to avoid duplicates."""
    if not CONFIG.exists():
        return set()
    text = CONFIG.read_text(encoding="utf-8")
    return set(m.lower() for m in re.findall(r"slug:\s*([^\s,}]+)", text))


def _yaml_name(slug):
    return slug.replace("-", " ").replace("_", " ").title()


def append_to_config(discovered):
    """Append verified new companies to the end of companies.yaml's list."""
    lines = ["", "  # --- auto-discovered (discover.py) ---"]
    for slug, ats, n in discovered:
        lines.append(f"  - {{name: \"{_yaml_name(slug)}\", ats: {ats}, "
                     f"slug: {slug}, type: discovered}}  # {n} postings")
    with open(CONFIG, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slugs", nargs="*", help="candidate slugs to probe")
    ap.add_argument("--file", help="file with one candidate slug per line")
    ap.add_argument("--append", action="store_true",
                    help="append verified NEW companies to companies.yaml")
    ap.add_argument("--min-jobs", type=int, default=1,
                    help="only keep boards with at least this many postings")
    ap.add_argument("--timeout", type=int, default=10)
    a = ap.parse_args()

    candidates = list(a.slugs)
    if a.file:
        candidates += [l.strip() for l in Path(a.file).read_text(encoding="utf-8").splitlines()
                       if l.strip() and not l.startswith("#")]
    # de-dupe, preserve order
    seen, uniq = set(), []
    for c in candidates:
        cl = c.strip().lower()
        if cl and cl not in seen:
            seen.add(cl)
            uniq.append(c.strip())
    if not uniq:
        sys.exit("no candidate slugs given (pass slugs or --file).")

    known = existing_slugs()
    print(f"probing {len(uniq)} candidate slugs across "
          f"{len(PROBES)} ATS types...\n")

    results = {}
    with cf.ThreadPoolExecutor(max_workers=40) as ex:  # ~2k probes for a big list
        futs = {ex.submit(discover_one, s, a.timeout): s for s in uniq}
        for fut in cf.as_completed(futs):
            results[futs[fut]] = fut.result()

    discovered, already, none = [], [], []
    for slug in uniq:
        hits = results.get(slug, [])
        hits = [(ats, n) for ats, n in hits if n >= a.min_jobs]
        if not hits:
            none.append(slug)
            continue
        # if a slug matches multiple ATSs, keep the one with most postings
        ats, n = max(hits, key=lambda x: x[1])
        if slug.lower() in known:
            already.append((slug, ats, n))
        else:
            discovered.append((slug, ats, n))

    print(f"✅ NEW verified ({len(discovered)}):")
    for slug, ats, n in sorted(discovered, key=lambda x: -x[2]):
        print(f"   {slug:<24} {ats:<16} {n} postings")
    if already:
        print(f"\n↺ already in config ({len(already)}): "
              + ", ".join(s for s, _, _ in already))
    print(f"\n✗ no public board found ({len(none)}): "
          + ", ".join(none[:40]) + (" ..." if len(none) > 40 else ""))

    if a.append and discovered:
        append_to_config(discovered)
        print(f"\nappended {len(discovered)} new companies to companies.yaml")
    elif a.append:
        print("\nnothing new to append.")


if __name__ == "__main__":
    main()
