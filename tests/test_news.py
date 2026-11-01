import json
from datetime import datetime, timezone

from server.news import NewsFilter, parse_events

RAW = [
    {"title": "CPI m/m", "country": "USD", "date": "2026-11-12T08:30:00-05:00", "impact": "High"},
    {"title": "Retail Sales", "country": "USD", "date": "2026-11-13T08:30:00-05:00", "impact": "Medium"},
    {"title": "ECB Press", "country": "EUR", "date": "2026-11-12T08:45:00+01:00", "impact": "High"},
    {"title": "broken", "country": "USD", "date": "not a date", "impact": "High"},
]
CPI = int(datetime(2026, 11, 12, 13, 30, tzinfo=timezone.utc).timestamp())


def test_parse_keeps_usd_high_only():
    ev = parse_events(RAW, ["USD"], ["High"])
    assert [e["title"] for e in ev] == ["CPI m/m"]
    assert ev[0]["time"] == CPI


def test_window(tmp_path):
    nf = NewsFilter({"minutes_before": 30, "minutes_after": 30}, tmp_path / "c.json", fetch=lambda: RAW)
    assert nf.blocking(CPI - 31 * 60) is None
    assert nf.blocking(CPI - 30 * 60)["title"] == "CPI m/m"
    assert nf.blocking(CPI + 30 * 60)["title"] == "CPI m/m"
    assert nf.blocking(CPI + 31 * 60) is None
    assert json.loads((tmp_path / "c.json").read_text()) == RAW


def test_disabled(tmp_path):
    nf = NewsFilter({"enabled": False}, tmp_path / "c.json", fetch=lambda: RAW)
    assert nf.blocking(CPI) is None


def test_download_fails_uses_cache(tmp_path):
    cache = tmp_path / "c.json"
    cache.write_text(json.dumps(RAW))

    def boom():
        raise OSError("offline")
    nf = NewsFilter({}, cache, fetch=boom)
    assert nf.blocking(CPI)["title"] == "CPI m/m"


def test_download_fails_no_cache_keeps_running(tmp_path):
    def boom():
        raise OSError("offline")
    nf = NewsFilter({}, tmp_path / "none.json", fetch=boom)
    assert nf.blocking(CPI) is None
