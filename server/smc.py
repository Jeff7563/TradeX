"""ICT/SMC markings computed from candles.

Everything here is mechanical: swing points, BOS/CHoCH, fair value gaps,
order blocks, the current dealing range and the kill zones. It marks what
happened on the chart; it does not decide trades.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .datasource import Candle

NY = ZoneInfo("America/New_York")

# ICT kill zones in New York local time (start hour, end hour)
KILL_ZONES = {"London": (2, 5), "New York": (7, 10)}


def swings(c: list[Candle], n: int = 3) -> list[dict]:
    """Swing high/low: a bar whose high (low) is the extreme of n bars each side."""
    out = []
    for i in range(n, len(c) - n):
        left, right = c[i - n:i], c[i + 1:i + n + 1]
        # strictly beyond the left side, at least equal to the right side,
        # so equal highs/lows mark the first one only
        if c[i].high > max(b.high for b in left) and c[i].high >= max(b.high for b in right):
            out.append({"i": i, "time": c[i].time, "kind": "high", "price": c[i].high})
        if c[i].low < min(b.low for b in left) and c[i].low <= min(b.low for b in right):
            out.append({"i": i, "time": c[i].time, "kind": "low", "price": c[i].low})
    return out


def structure(c: list[Candle], sw: list[dict], n: int = 3) -> tuple[list[dict], str]:
    """BOS = break in the trend's direction, CHoCH = first break against it.

    A swing only counts once it is confirmed (n bars to its right), and a
    break needs a candle CLOSE beyond the level.
    """
    events, trend = [], "none"
    last_high = last_low = None
    pending = sorted(sw, key=lambda s: s["i"])
    p = 0
    for i, bar in enumerate(c):
        while p < len(pending) and pending[p]["i"] + n <= i:
            s = pending[p]
            if s["kind"] == "high":
                last_high = s
            else:
                last_low = s
            p += 1
        if last_high and bar.close > last_high["price"]:
            kind = "BOS" if trend == "bull" else "CHoCH"
            events.append({"kind": kind, "dir": "bull", "price": last_high["price"],
                           "from_time": last_high["time"], "from_i": last_high["i"],
                           "time": bar.time, "i": i})
            trend, last_high = "bull", None
        elif last_low and bar.close < last_low["price"]:
            kind = "BOS" if trend == "bear" else "CHoCH"
            events.append({"kind": kind, "dir": "bear", "price": last_low["price"],
                           "from_time": last_low["time"], "from_i": last_low["i"],
                           "time": bar.time, "i": i})
            trend, last_low = "bear", None
    return events, trend


def fvgs(c: list[Candle]) -> list[dict]:
    """3-candle imbalance. Marked filled once price trades through the whole gap."""
    out = []
    for i in range(2, len(c)):
        a, b = c[i - 2], c[i]
        if a.high < b.low:
            out.append({"dir": "bull", "top": b.low, "bottom": a.high,
                        "time": c[i - 1].time, "i": i - 1})
        elif a.low > b.high:
            out.append({"dir": "bear", "top": a.low, "bottom": b.high,
                        "time": c[i - 1].time, "i": i - 1})
    for g in out:
        g["filled"] = False
        for bar in c[g["i"] + 2:]:
            if (g["dir"] == "bull" and bar.low <= g["bottom"]) or \
                    (g["dir"] == "bear" and bar.high >= g["top"]):
                g["filled"] = True
                break
    return out


def order_blocks(c: list[Candle], events: list[dict]) -> list[dict]:
    """Last opposite candle before the move that broke structure."""
    out = []
    for e in events:
        want_bear = e["dir"] == "bull"  # bullish OB = last down candle
        for j in range(e["i"] - 1, max(e["from_i"] - 20, 0) - 1, -1):
            down = c[j].close < c[j].open
            if down == want_bear and c[j].close != c[j].open:
                ob = {"dir": e["dir"], "top": c[j].high, "bottom": c[j].low,
                      "time": c[j].time, "i": j, "from": e["kind"]}
                ob["broken"] = any(
                    (e["dir"] == "bull" and b.close < ob["bottom"]) or
                    (e["dir"] == "bear" and b.close > ob["top"])
                    for b in c[e["i"] + 1:])
                out.append(ob)
                break
    return out


def dealing_range(sw: list[dict]) -> dict | None:
    """Latest swing high and low; above the middle is premium, below is discount."""
    hi = next((s for s in reversed(sw) if s["kind"] == "high"), None)
    lo = next((s for s in reversed(sw) if s["kind"] == "low"), None)
    if not hi or not lo or hi["price"] <= lo["price"]:
        return None
    return {"high": hi["price"], "low": lo["price"],
            "eq": round((hi["price"] + lo["price"]) / 2, 5)}


def kill_zones(start: int, end: int) -> list[dict]:
    """Kill zone windows (UTC epoch) between start and end, DST handled by zoneinfo."""
    out = []
    day = datetime.fromtimestamp(start, NY).date() - timedelta(days=1)
    last = datetime.fromtimestamp(end, NY).date() + timedelta(days=1)
    while day <= last:
        if day.weekday() < 5:
            for name, (h0, h1) in KILL_ZONES.items():
                s = datetime(day.year, day.month, day.day, h0, tzinfo=NY)
                e = datetime(day.year, day.month, day.day, h1, tzinfo=NY)
                s_ts = int(s.astimezone(timezone.utc).timestamp())
                e_ts = int(e.astimezone(timezone.utc).timestamp())
                if e_ts >= start and s_ts <= end + 86400:
                    out.append({"name": name, "start": s_ts, "end": e_ts})
        day += timedelta(days=1)
    return out


def analyse(c: list[Candle], tf: str, n: int = 3) -> dict:
    if len(c) < 2 * n + 2:
        return {"swings": [], "structure": [], "trend": "none", "fvgs": [],
                "order_blocks": [], "range": None, "kill_zones": []}
    sw = swings(c, n)
    ev, trend = structure(c, sw, n)
    intraday = tf not in ("D1", "H4")
    return {
        "swings": sw,
        "structure": ev,
        "trend": trend,
        "fvgs": [g for g in fvgs(c) if not g["filled"]][-15:],
        "order_blocks": [o for o in order_blocks(c, ev) if not o["broken"]][-8:],
        "range": dealing_range(sw),
        "kill_zones": kill_zones(c[0].time, c[-1].time) if intraday else [],
    }
