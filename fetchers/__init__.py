"""Fetcher registry: maps the `ats` value in companies.yaml to a function.

Each fetcher has signature fetch(company_cfg, settings) -> list[job dict].
Adding a new ATS = add a module + one line here.
"""
from . import (amazon, ashby, atlassian, google_html, greenhouse, lever,
               microsoft, smartrecruiters, workday)

FETCHERS = {
    "greenhouse": greenhouse.fetch,
    "lever": lever.fetch,
    "ashby": ashby.fetch,
    "smartrecruiters": smartrecruiters.fetch,
    "workday": workday.fetch,
    "amazon": amazon.fetch,
    "microsoft": microsoft.fetch,
    "atlassian": atlassian.fetch,
    "google_html": google_html.fetch,
}
