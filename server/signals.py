"""ICT/SMC setup finder (rules v1).

A signal needs ALL of these:
 1. Bias: H1 structure trend (last BOS/CHoCH). D1 must not point the other way.
 2. Time: the entry bar is inside the London or New York kill zone.
 3. Entry timeframe (M15 by default): a recent BOS/CHoCH in the bias direction.
 4. That move left an unfilled FVG or unbroken order block in the bias direction,
    sitting in discount (buys) or premium (sells) of the entry-TF dealing range.
 5. Price has come back into that zone on the latest bar.
 6. Stop goes beyond the zone, target is the nearest opposite swing (liquidity),
    and the reward/risk is at least min_rr.

These are mechanical rules for alerts and testing, not trade advice.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

from .datasource import Candle
from .smc import analyse

DEFAULTS = {
    "entry_tf": "M15",
    "max_bars_since_break": 24,   # how old the BOS/CHoCH may be on the entry TF
    "min_rr": 2.0,
    "sl_buffer_pct": 0.0005,      # extra room beyond the zone (0.05% of price)
    "require_kill_zone": True,
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


def evaluate(symbol: str, d1: list[Candle], h1: list[Candle], ltf: list[Candle],
             cfg: dict | None = None) -> Signal | None:
    cfg = {**DEFAULTS, **(cfg or {})}
    if len(ltf) < 30 or len(h1) < 30:
        return None
    a_d1 = analyse(d1, "D1") if len(d1) >= 10 else {"trend": "none"}
    a_h1 = analyse(h1, "H1")
    a = analyse(ltf, cfg["entry_tf"])
    reasons = []

    # 1. bias
    bias = a_h1["trend"]
    if bias not in ("bull", "bear"):
        return None
    if a_d1["trend"] in ("bull", "bear") and a_d1["trend"] != bias:
        return None
    reasons.append(f"H1 {'ขาขึ้น' if bias == 'bull' else 'ขาลง'}"
                   + (f", D1 {'ขาขึ้น' if a_d1['trend'] == 'bull' else 'ขาลง'}"
                      if a_d1["trend"] != "none" else ""))

    # 2. time
    last = ltf[-1]
    kz = _in_kill_zone(last.time, a["kill_zones"])
    if cfg["require_kill_zone"] and not kz:
        return None
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

    # 4. zone left by the move, on the right side of the dealing range
    rng = a["range"]
    zones = [{"kind": "FVG", **g} for g in a["fvgs"] if g["dir"] == bias] + \
            [{"kind": "OB", **o} for o in a["order_blocks"] if o["dir"] == bias]
    zones = [z for z in zones if brk["from_i"] - 3 <= z["i"] <= brk["i"] + 3]
    if rng:
        if bias == "bull":
            zones = [z for z in zones if z["bottom"] <= rng["eq"]]
        else:
            zones = [z for z in zones if z["top"] >= rng["eq"]]
    if not zones:
        return None

    # 5. price back in the zone now (newest zone first)
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

    # 6. stop, target, reward/risk
    buf = last.close * cfg["sl_buffer_pct"]
    entry = last.close
    if bias == "bull":
        sl = zone["bottom"] - buf
        targets = [s["price"] for s in a["swings"] if s["kind"] == "high" and s["price"] > entry]
        tp = min(targets) if targets else None
        if tp is None:
            return None
        risk, reward = entry - sl, tp - entry
    else:
        sl = zone["top"] + buf
        targets = [s["price"] for s in a["swings"] if s["kind"] == "low" and s["price"] < entry]
        tp = max(targets) if targets else None
        if tp is None:
            return None
        risk, reward = sl - entry, entry - tp
    if risk <= 0:
        return None
    rr = reward / risk
    if rr < cfg["min_rr"]:
        # nearest liquidity too close: aim for the next one out if it exists
        far = sorted(targets, reverse=(bias == "bear"))
        far = [t for t in far if abs(t - entry) / risk >= cfg["min_rr"]]
        if not far:
            return None
        tp = far[0]
        rr = abs(tp - entry) / risk
    reasons.append(f"เป้า = liquidity ที่ swing {'high' if bias == 'bull' else 'low'} {tp}")

    return Signal(symbol=symbol, direction="buy" if bias == "bull" else "sell",
                  entry=round(entry, 2), sl=round(sl, 2), tp=round(tp, 2),
                  rr=round(rr, 2), time=last.time,
                  zone={"kind": zone["kind"], "top": zone["top"],
                        "bottom": zone["bottom"], "time": zone["time"]},
                  reasons=reasons)
