"""Title + location + freshness filtering. All rules live in companies.yaml.

Design goal: precise guards that drop obvious non-fits (US/SF-only roles,
ancient postings, support/sales "engineer" roles) WITHOUT dropping genuine
India fresher openings. When in doubt, the filter lets a job through.
"""
import re
from datetime import date, datetime


class JobFilter:
    def __init__(self, cfg):
        # Include keywords -> whole-word regexes. \b + [\s\-] so "sde 1"
        # matches "SDE-1"; \b keeps "sde" from matching "sdet".
        self.include = [
            re.compile(r"\b" + re.escape(k.strip()).replace(r"\ ", r"[\s\-]") + r"\b",
                       re.IGNORECASE)
            for k in cfg["include_titles"]
        ]
        self.exclude = [re.compile(p, re.IGNORECASE)
                        for p in cfg["exclude_title_patterns"]]
        # India / remote tokens that make a location acceptable.
        self.locations = [l.lower() for l in cfg["locations_allow"]]
        # Tokens that mark a location as NON-India (e.g. "united states",
        # "san francisco"). If present and no India token is, the job is
        # rejected even if it says "remote"/"hybrid".
        self.locations_block = [l.lower() for l in cfg.get("locations_block", [])]
        # India tokens (subset of locations_allow, minus the generic
        # remote/hybrid words) - used to override a block token.
        generic = {"remote", "hybrid", "work from home", "wfh", "pan india", " in"}
        self.india_tokens = [t for t in self.locations if t not in generic]
        self.allow_empty_location = bool(cfg.get("allow_empty_location", True))
        # Freshness: reject postings older than this many days when the date
        # is known & parseable. 0/None = no freshness guard. Generous default
        # so real openings are never lost to a slightly-old repost.
        self.max_age_days = int(cfg.get("max_age_days", 0) or 0)

    def title_ok(self, title):
        t = title.strip()
        if not t:
            return False
        if not any(rx.search(t) for rx in self.include):
            return False
        if any(rx.search(t) for rx in self.exclude):
            return False
        return True

    def location_ok(self, location):
        loc = (location or "").strip().lower()
        if not loc:
            return self.allow_empty_location
        has_india = any(tok in loc for tok in self.india_tokens)
        # A non-India country/city present without any India mention -> drop.
        # (This is what stops "Remote - United States" / "Hybrid - San Francisco".)
        if not has_india and any(b in loc for b in self.locations_block):
            return False
        return any(tok in loc for tok in self.locations)

    def fresh_ok(self, posted_at):
        """True if the posting isn't older than max_age_days. Unknown or
        unparseable dates always pass (minimal guard - never drop on doubt)."""
        if not self.max_age_days or not posted_at:
            return True
        s = str(posted_at).strip()
        d = None
        # ISO first (most sources: "2026-07-09")
        try:
            d = datetime.strptime(s[:10], "%Y-%m-%d").date()
        except ValueError:
            # Amazon-style "July 8, 2026"
            for fmt in ("%B %d, %Y", "%b %d, %Y"):
                try:
                    d = datetime.strptime(s, fmt).date()
                    break
                except ValueError:
                    continue
        if d is None:
            return True  # can't parse -> don't reject
        return (date.today() - d).days <= self.max_age_days

    def match(self, job):
        return (self.title_ok(job["title"])
                and self.location_ok(job["location"])
                and self.fresh_ok(job.get("posted_at", "")))
