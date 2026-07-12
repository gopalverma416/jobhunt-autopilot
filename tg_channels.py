"""Telegram public-channel polling via t.me/s/<channel> web previews
(Feature 3). Plain HTTPS GET - no account, no login, no Telegram API.

Message blocks in the preview HTML look like (verified 2026-07-12):
  <div class="tgme_widget_message ..." data-post="channelname/1234" ...>
    ... <div class="tgme_widget_message_text ...">message html</div> ...
Channels can disable web previews - then the page has zero data-post blocks;
we detect that and report it instead of failing silently.
"""
import re

import requests

from fetchers.common import HEADERS
from jd import strip_html

# Split page into message blocks, capture "channel/id" + the rest of the block.
BLOCK_RE = re.compile(
    r'data-post="([\w_]+)/(\d+)"(.*?)(?=data-post="|\Z)', re.S)
TEXT_RE = re.compile(
    r'class="tgme_widget_message_text[^"]*"[^>]*>(.*?)</div>', re.S)


def fetch_channel(channel, settings):
    """Return (messages, error). messages = [{channel, msg_id, text}].
    error is None on success, else a short human-readable string."""
    url = f"https://t.me/s/{channel}"
    try:
        r = requests.get(url, headers={**HEADERS, "Accept": "text/html"},
                         timeout=settings["request_timeout"])
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001 - one channel must not crash the run
        return [], f"{type(e).__name__}: {e}"
    msgs = []
    for chan, msg_id, block in BLOCK_RE.findall(r.text):
        m = TEXT_RE.search(block)
        if not m:
            continue  # media-only message, no text
        text = strip_html(m.group(1))
        if text:
            msgs.append({"channel": chan, "msg_id": msg_id, "text": text})
    if not msgs:
        return [], ("no messages parsed - channel may have web preview "
                    "disabled, or has only media posts")
    return msgs, None


def build_matcher(include_titles, fresher_signals):
    """Compile the two keyword passes once per run."""
    role_rx = [re.compile(r"\b" + re.escape(k.strip()).replace(r"\ ", r"[\s\-]")
                          + r"\b", re.I) for k in include_titles]
    sig_rx = [re.compile(re.escape(s.strip()).replace(r"\ ", r"[\s\-]"), re.I)
              for s in fresher_signals]

    def match(text):
        return (any(rx.search(text) for rx in role_rx)
                and any(rx.search(text) for rx in sig_rx))
    return match
