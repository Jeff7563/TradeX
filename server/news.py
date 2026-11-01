"""Pause signals and trading around high-impact news (CPI, NFP, FOMC ...).

The calendar is Forex Factory's free weekly feed. It is downloaded at most
every few hours and kept in news_cache.json. If the download fails, the last
cached copy is used; with no copy at all the scanner keeps running and says so.

config.json:
  "news": {"enabled": true, "currencies": ["USD"], "impact": ["High"],
           "minutes_before": 30, "minutes_after": 30}
"""
from __future__ import annotations

import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

FEED = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

DEFAULTS = {
    "enabled": True,
    "currencies": ["USD"],
    "impact": ["High"],
    "minutes_before": 30,
    "minutes_after": 30,
    "refresh_hours": 6,
    "url": FEED,
}


def parse_events(raw: list, currencies: list[str], impact: list[str]) -> list[dict]:
    """Keep the events we care about, with their time as UTC epoch seconds."""
    want_cur = {c.upper() for c in currencies}
    want_imp = {i.lower() for i in impact}
    out = []
    for e in raw or []:
        try:
            if str(e.get("country", "")).upper() not in want_cur:
                continue
            if str(e.get("impact", "")).lower() not in want_imp:
                continue
            t = int(datetime.fromisoformat(str(e["date"])).timestamp())
        except (KeyError, ValueError, TypeError, AttributeError):
            continue
        out.append({"time": t, "title": str(e.get("title", "")).strip(),
                    "country": str(e.get("country", "")).upper()})
    return sorted(out, key=lambda x: x["time"])


class NewsFilter:
    def __init__(self, cfg: dict, cache: Path, fetch=None):
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.cache = cache
        self._fetch = fetch or self._download
        self.events: list[dict] = []
        self.loaded_at = 0.0
        self.warned = False

    @property
    def enabled(self) -> bool:
        return bool(self.cfg["enabled"])

    def _download(self) -> list:
        req = urllib.request.Request(self.cfg["url"], headers={"User-Agent": "TradeX/1.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))

    def refresh(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if self.events and now - self.loaded_at < self.cfg["refresh_hours"] * 3600:
            return
        raw = None
        try:
            raw = self._fetch()
            self.cache.write_text(json.dumps(raw), encoding="utf-8")
        except Exception as e:  # network down, rate limited, bad JSON
            try:
                raw = json.loads(self.cache.read_text(encoding="utf-8"))
            except (FileNotFoundError, ValueError):
                raw = None
            if not self.warned:
                print(f"โหลดปฏิทินข่าวไม่ได้ ({e})"
                      + (" ใช้ข้อมูลเก่าที่เก็บไว้แทน" if raw else " บอทจะทำงานต่อโดยไม่หยุดช่วงข่าว"),
                      flush=True)
                self.warned = True
        if raw is not None:
            self.events = parse_events(raw, self.cfg["currencies"], self.cfg["impact"])
            self.warned = False
        # try again in 30 minutes when nothing loaded, otherwise after refresh_hours
        self.loaded_at = now if self.events else now - self.cfg["refresh_hours"] * 3600 + 1800

    def blocking(self, t: float) -> dict | None:
        """The news event whose quiet window contains time t, if any."""
        if not self.enabled:
            return None
        self.refresh(t)
        before = self.cfg["minutes_before"] * 60
        after = self.cfg["minutes_after"] * 60
        for e in self.events:
            if e["time"] - before <= t <= e["time"] + after:
                return e
        return None
