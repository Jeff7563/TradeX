"""ICT/SMC setup finder.

A signal needs ALL of these:
 1. Bias: H1 structure trend (last BOS/CHoCH). D1 must not point the other way.
 2. Time: the entry bar is inside the London or New York kill zone.
 3. Entry timeframe (M15 by default): a recent BOS/CHoCH in the bias direction.
 4. (optional, require_sweep) Before that break, price swept liquidity on the
    other side: took out an earlier swing low/high, the Asia range, or the
    previous day's low/high, and closed back inside within one bar.
 5. The move left an unfilled FVG or unbroken order block in the bias direction
    (after the sweep, when a sweep is required), in discount for buys or
    premium for sells.
 6. Price has come back into that zone on the latest bar.
 7. Stop beyond the zone (or beyond the sweep wick, sl_mode="sweep").
    Target: nearest opposite liquidity (tp_mode="liquidity") or a fixed
    reward/risk (tp_mode="fixed"). Reward/risk must be at least min_rr.

All options live in config.json under "signals". The defaults are rules v1.
These are mechanical rules for alerts and testing, not trade advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .datasource import Candle
from .smc import analyse

NY = ZoneInfo("America/New_York")

DEFAULTS = {
    "entry_tf": "M15",
    "max_bars_since_break": 24,   # how old the BOS/CHoCH may be on the entry TF
    "min_rr": 2.0,
    "sl_buffer_pct": 0.0005,      # extra room beyond the zone (0.05% of price)
    "require_kill_zone": True,
    "require_sweep": False,       # v2: liquidity sweep before the break
    "sweep_lookback": 30,         # bars before the break to look for the sweep
    "zones": ["FVG", "OB"],       # which zones may be used for entry
    "tp_mode": "liquidity",       # "liquidity" or "fixed"
    "fixed_rr": 2.0,              # target when tp_mode = "fixed"
    "sl_mode": "zone",            # "zone" or "sweep"
}


@dataclass
class Signal:
    symbol: str
    direction: str          # "buy" / "sell"
    entry: float
    sl: float
    tp: float
    rr: float
    time: int               # UTC epoch of the bar that triggered
    zone: dict
    reasons: list = field(default_factory=list)

    @property
    def key(self) -> str:
        """Same zone = same signal, so it is only sent once."""
        return f"{self.symbol}-{self.direction}-{self.zone['kind']}-{self.zone['time']}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["key"] = self.key
        return d


def _in_kill_zone(t: int, zones: list[dict]) -> str | None:
    for z in zones:
        if z["start"] <= t < z["end"]:
            return z["name"]
    return None


def asia_range(c: list[Candle], t: int) -> dict | None:
    """ICT Asia range: 20:00–00:00 New York time, the session before time t."""
    ny = datetime.fromtimestamp(t, NY)
    midnight = datetime(ny.year, ny.month, ny.day, tzinfo=NY)
    start = int((midnight - timedelta(hours=4)).astimezone(timezone.utc).timestamp())
    end = int(midnight.astimezone(timezone.utc).timestamp())
    bars = [b for b in c if start <= b.time < end]
    if len(bars) < 2 or t < end:
        return None
    return {"high": max(b.high for b in bars), "low": min(b.low for b in bars), "end": end}


def liquidity_levels(c: list[Candle], swings: list[dict], d1: list[Candle],
                     side: str, before_t: int, n: int, step: int) -> list[dict]:
    """Resting liquidity below lows (side='low') or above highs (side='high')."""
    lv = [{"name": f"swing {side}", "price": s["price"], "ready": s["time"] + (n + 1) * step}
          for s in swings if s["kind"] == side]
    a = asia_range(c, before_t)
    if a:
        lv.append({"name": f"Asia {side}", "price": a[side], "ready": a["end"]})
    if d1:
        prev = d1[-1]
        lv.append({"name": "PDL" if side == "low" else "PDH",
                   "price": prev.low if side == "low" else prev.high,
                   "ready": prev.time + 86400})
    return lv


def find_sweep(c: list[Candle], start: int, stop: int, bias: str, levels: list[dict]) -> dict | None:
    """Latest bar in [start, stop] that ran a level and closed back within one bar."""
    found = None
    for j in range(max(start, 0), min(stop, len(c) - 1) + 1):
        b = c[j]
        nxt = c[j + 1] if j + 1 < len(c) else b
        for lv in levels:
            if lv["ready"] > b.time:
                continue
            p = lv["price"]
            if bias == "bull" and b.low < p and (b.close > p or nxt.close > p):
                if not found or j >= found["i"]:
                    found = {"i": j, "time": b.time, "extreme": b.low, **lv}
            if bias == "bear" and b.high > p and (b.close < p or nxt.close < p):
                if not found or j >= found["i"]:
                    found = {"i": j, "time": b.time, "extreme": b.high, **lv}
    return found


def evaluate(symbol: str, d1: list[Candle], h1: list[Candle], ltf: list[Candle],
             cfg: dict | None = None, a_d1: dict | None = None,
             a_h1: dict | None = None) -> Signal | None:
    cfg = {**DEFAULTS, **(cfg or {})}
    if len(ltf) < 30 or len(h1) < 30:
        return None
    if a_d1 is None:
        a_d1 = analyse(d1, "D1") if len(d1) >= 10 else {"trend": "none"}
    if a_h1 is None:
        a_h1 = analyse(h1, "H1")
    reasons = []

    # 1. bias
    bias = a_h1["trend"]
    if bias not in ("bull", "bear"):
        return None
    if a_d1["trend"] in ("bull", "bear") and a_d1["trend"] != bias:
        return None

    # 2. time (cheap check before the entry-TF analysis)
    a = analyse(ltf, cfg["entry_tf"])
    last = ltf[-1]
    kz = _in_kill_zone(last.time, a["kill_zones"])
    if cfg["require_kill_zone"] and not kz:
        return None
    reasons.append(f"H1 {'ขาขึ้น' if bias == 'bull' else 'ขาลง'}"
                   + (f", D1 {'ขาขึ้น' if a_d1['trend'] == 'bull' else 'ขาลง'}"
                      if a_d1["trend"] != "none" else ""))
    if kz:
        reasons.append(f"อยู่ใน Kill zone {kz}")

    # 3. recent break on entry TF in bias direction
    breaks = [e for e in a["structure"] if e["dir"] == bias]
    if not breaks or a["structure"][-1]["dir"] != bias:
        return None
    brk = breaks[-1]
    if len(ltf) - 1 - brk["i"] > cfg["max_bars_since_break"]:
        return None
    reasons.append(f"{cfg['entry_tf']} {brk['kind']} {'ขึ้น' if bias == 'bull' else 'ลง'} ที่ {brk['price']}")

    # 4. liquidity sweep before the break
    sweep = None
    if cfg["require_sweep"]:
        step = ltf[1].time - ltf[0].time
        side = "low" if bias == "bull" else "high"
        start = brk["i"] - cfg["sweep_lookback"]
        levels = liquidity_levels(ltf, a["swings"], d1, side, ltf[max(start, 0)].time, 3, step)
        sweep = find_sweep(ltf, start, brk["i"], bias, levels)
        if not sweep:
            return None
        reasons.append(f"กวาด {sweep['name']} {sweep['price']} ก่อนเกิด {brk['kind']}")

    # 5. zone left by the move, on the right side of the dealing range
    rng = a["range"]
    zones = []
    if "FVG" in cfg["zones"]:
        zones += [{"kind": "FVG", **g} for g in a["fvgs"] if g["dir"] == bias]
    if "OB" in cfg["zones"]:
        zones += [{"kind": "OB", **o} for o in a["order_blocks"] if o["dir"] == bias]
    lo_i = sweep["i"] if sweep else brk["from_i"] - 3
    zones = [z for z in zones if lo_i <= z["i"] <= brk["i"] + 3]
    if rng:
        if bias == "bull":
            zones = [z for z in zones if z["bottom"] <= rng["eq"]]
        else:
            zones = [z for z in zones if z["top"] >= rng["eq"]]
    if not zones:
        return None

    # 6. price back in the zone now (newest zone first)
    zone = None
    for z in sorted(zones, key=lambda z: z["i"], reverse=True):
        if z["i"] >= len(ltf) - 2:
            continue  # zone must already exist before the touching bar
        touched = last.low <= z["top"] if bias == "bull" else last.high >= z["bottom"]
        still_valid = last.close >= z["bottom"] if bias == "bull" else last.close <= z["top"]
        if touched and still_valid:
            zone = z
            break
    if not zone:
        return None
    reasons.append(f"ราคากลับมาแตะ {zone['kind']} {zone['bottom']}–{zone['top']}"
                   + (" ในโซน Discount" if bias == "bull" else " ในโซน Premium"))

    # 7. stop, target, reward/risk
    buf = last.close * cfg["sl_buffer_pct"]
    entry = last.close
    use_sweep_sl = cfg["sl_mode"] == "sweep" and sweep
    if bias == "bull":
        sl = (sweep["extreme"] if use_sweep_sl else zone["bottom"]) - buf
        risk = entry - sl
        targets = sorted(s["price"] for s in a["swings"] if s["kind"] == "high" and s["price"] > entry)
    else:
        sl = (sweep["extreme"] if use_sweep_sl else zone["top"]) + buf
        risk = sl - entry
        targets = sorted((s["price"] for s in a["swings"] if s["kind"] == "low" and s["price"] < entry),
                         reverse=True)
    if risk <= 0:
        return None
    if cfg["tp_mode"] == "fixed":
        rr = float(cfg["fixed_rr"])
        tp = entry + rr * risk if bias == "bull" else entry - rr * risk
        reasons.append(f"เป้า RR คงที่ 1:{rr:g}")
    else:
        far = [t for t in targets if abs(t - entry) / risk >= cfg["min_rr"]]
        if not far:
            return None
        tp = far[0]
        rr = abs(tp - entry) / risk
        reasons.append(f"เป้า = liquidity ที่ swing {'high' if bias == 'bull' else 'low'} {tp}")
    if rr < cfg["min_rr"]:
        return None

    return Signal(symbol=symbol, direction="buy" if bias == "bull" else "sell",
                  entry=round(entry, 2), sl=round(sl, 2), tp=round(tp, 2),
                  rr=round(rr, 2), time=last.time,
                  zone={"kind": zone["kind"], "top": zone["top"],
                        "bottom": zone["bottom"], "time": zone["time"]},
                  reasons=reasons)
