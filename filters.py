"""Title + location filtering. All rules live in companies.yaml."""
import re


class JobFilter:
    def __init__(self, cfg):
        # Include keywords -> whole-word regexes ("sde" must not match "sdet"...
        # actually \b lets "sdet" fail since t is a word char after e? No:
        # \bsde\b requires a non-word char after "sde", so "sdet" does NOT match. Good.)
        self.include = [
            re.compile(r"\b" + re.escape(k.strip()).replace(r"\ ", r"[\s\-]") + r"\b",
                       re.IGNORECASE)
            for k in cfg["include_titles"]
        ]
        self.exclude = [re.compile(p, re.IGNORECASE)
                        for p in cfg["exclude_title_patterns"]]
        self.locations = [l.lower() for l in cfg["locations_allow"]]
        self.allow_empty_location = bool(cfg.get("allow_empty_location", True))

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
        return any(tok in loc for tok in self.locations)

    def match(self, job):
        return self.title_ok(job["title"]) and self.location_ok(job["location"])
