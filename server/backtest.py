"""Backtest the signal rules on past MT5 prices.

Run:  python -m server.backtest            (all symbols, about 1 year of M15)
      python -m server.backtest --bars 10000 --symbol XAUUSD

How a trade is simulated:
 - The rules run on each closed entry-TF bar, seeing only data up to that bar.
 - Entry at the NEXT bar's open, with the signal's SL and TP.
 - A bar that touches both SL and TP counts as a loss (worst case).
 - The spread is charged on every trade.
 - One trade at a time per symbol, at most max_trades_per_day per day.
Results are in R (1R = the amount risked on the trade).
"""
from __future__ import annotations

import argparse
import bisect
import csv
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .datasource import TF_SECONDS, Candle
from .signals import evaluate
from .smc import analyse, kill_zones

TH = timezone(timedelta(hours=7))


@dataclass
class Trade:
    symbol: str
    direction: str
    signal_time: int
    entry_time: int
    entry: float
    sl: float
    tp: float
    exit_time: int | None = None
    exit: float | None = None
    result: str = "open"      # win / loss / open
    r: float = 0.0
    kill_zone: str = ""
    cost_r: float = 0.0


def _closed_upto(bars: list[Candle], times: list[int], step: int, t_end: int) -> list[Candle]:
    """Bars of a higher TF that had fully closed by time t_end."""
    k = bisect.bisect_right(times, t_end - step)
    return bars[:k]


def run(symbol: str, d1: list[Candle], h1: list[Candle], ltf: list[Candle],
        scfg: dict, spread: float, max_per_day: int = 3, window: int = 400) -> list[Trade]:
    tf = scfg.get("entry_tf", "M15")
    step = TF_SECONDS[tf]
    d1_t = [c.time for c in d1]
    h1_t = [c.time for c in h1]
    kz = kill_zones(ltf[0].time, ltf[-1].time)
    kz_starts = [z["start"] for z in kz]

    def kz_name(t):
        i = bisect.bisect_right(kz_starts, t) - 1
        for z in kz[max(i - 1, 0):i + 1]:
            if z["start"] <= t < z["end"]:
                return z["name"]
        return None

    trades: list[Trade] = []
    per_day: dict[str, int] = defaultdict(int)
    busy_until = -1
    seen = set()
    cache_h1: dict = {}
    cache_d1: dict = {}
    for k in range(window, len(ltf) - 1):
        bar = ltf[k]
        if k <= busy_until:
            continue
        name = kz_name(bar.time)
        if scfg.get("require_kill_zone", True) and not name:
            continue
        day = datetime.fromtimestamp(bar.time, TH).strftime("%Y-%m-%d")
        if per_day[day] >= max_per_day:
            continue
        t_close = bar.time + step
        d1_c = _closed_upto(d1, d1_t, 86400, t_close)[-200:]
        h1_c = _closed_upto(h1, h1_t, 3600, t_close)[-window:]
        # H1/D1 only change once an hour/day: reuse their analysis
        hk, dk = (h1_c[-1].time if h1_c else 0), (d1_c[-1].time if d1_c else 0)
        if hk not in cache_h1:
            cache_h1.clear()
            cache_h1[hk] = analyse(h1_c, "H1") if len(h1_c) >= 30 else {"trend": "none"}
        if dk not in cache_d1:
            cache_d1.clear()
            cache_d1[dk] = analyse(d1_c, "D1") if len(d1_c) >= 10 else {"trend": "none"}
        if cache_h1[hk]["trend"] == "none":
            continue
        sig = evaluate(symbol, d1_c, h1_c, ltf[k - window:k + 1], scfg,
                       a_d1=cache_d1[dk], a_h1=cache_h1[hk])
        if not sig or sig.key in seen:
            continue
        seen.add(sig.key)

        nxt = ltf[k + 1]
        buy = sig.direction == "buy"
        entry = nxt.open
        if (buy and not (sig.sl < entry < sig.tp)) or (not buy and not (sig.tp < entry < sig.sl)):
            continue  # gapped past a level before we could enter
        risk = abs(entry - sig.sl)
        cost_r = spread / risk if risk else 0
        tr = Trade(symbol, sig.direction, bar.time, nxt.time, entry, sig.sl, sig.tp,
                   kill_zone=name or "", cost_r=cost_r)
        j = k + 1
        while j < len(ltf):
            b = ltf[j]
            hit_sl = b.low <= sig.sl if buy else b.high >= sig.sl
            hit_tp = b.high >= sig.tp if buy else b.low <= sig.tp
            if hit_sl:
                tr.result, tr.exit, tr.r = "loss", sig.sl, -1.0 - cost_r
            elif hit_tp:
                tr.result, tr.exit = "win", sig.tp
                tr.r = abs(sig.tp - entry) / risk - cost_r
            if hit_sl or hit_tp:
                tr.exit_time = b.time
                break
            j += 1
        busy_until = j
        per_day[day] += 1
        trades.append(tr)
    return trades


# ---- statistics -----------------------------------------------------------

def max_drawdown(rs: list[float]) -> float:
    peak = eq = dd = 0.0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dd


def longest_losing_streak(rs: list[float]) -> int:
    best = cur = 0
    for r in rs:
        cur = cur + 1 if r < 0 else 0
        best = max(best, cur)
    return best


def stats(trades: list[Trade]) -> dict:
    closed = [t for t in trades if t.result != "open"]
    rs = [t.r for t in closed]
    wins = [t for t in closed if t.result == "win"]
    gross_win = sum(r for r in rs if r > 0)
    gross_loss = -sum(r for r in rs if r < 0)
    return {
        "trades": len(closed),
        "open": len(trades) - len(closed),
        "wins": len(wins),
        "win_rate": len(wins) / len(closed) * 100 if closed else 0.0,
        "total_r": sum(rs),
        "avg_r": sum(rs) / len(rs) if rs else 0.0,
        "profit_factor": gross_win / gross_loss if gross_loss else float("inf") if gross_win else 0.0,
        "max_dd_r": max_drawdown(rs),
        "losing_streak": longest_losing_streak(rs),
    }


def monte_carlo(rs: list[float], runs: int = 2000, seed: int = 1) -> dict:
    """Shuffle the trade order many times: how bad could the drawdown get by luck?"""
    if len(rs) < 5:
        return {}
    rng = random.Random(seed)
    dds, streaks = [], []
    for _ in range(runs):
        s = rs[:]
        rng.shuffle(s)
        dds.append(max_drawdown(s))
        streaks.append(longest_losing_streak(s))
    dds.sort()
    streaks.sort()
    return {"dd_median": dds[runs // 2], "dd_95": dds[int(runs * 0.95)],
            "streak_95": streaks[int(runs * 0.95)]}


def report(symbol: str, trades: list[Trade], trades_x2: list[Trade],
           first: int, last: int, risk_pct: float) -> str:
    s = stats(trades)
    d0 = datetime.fromtimestamp(first, TH).strftime("%d/%m/%Y")
    d1 = datetime.fromtimestamp(last, TH).strftime("%d/%m/%Y")
    out = [f"=== {symbol}  {d0} – {d1} ===",
           f"จำนวนเทรด     {s['trades']}  (ยังไม่จบ {s['open']})"]
    if not s["trades"]:
        out.append("ไม่มีสัญญาณในช่วงนี้")
        return "\n".join(out)
    out += [
        f"ชนะ           {s['wins']} ครั้ง  ({s['win_rate']:.1f}%)",
        f"กำไรรวม       {s['total_r']:+.1f}R  (≈ {s['total_r'] * risk_pct:+.1f}% ถ้าเสี่ยง {risk_pct}%/ไม้)",
        f"เฉลี่ยต่อไม้   {s['avg_r']:+.2f}R",
        f"Profit factor {s['profit_factor']:.2f}",
        f"Drawdown สูงสุด {s['max_dd_r']:.1f}R  | แพ้ติดกันสูงสุด {s['losing_streak']} ไม้",
    ]
    # split in half: does it hold up in both periods?
    closed = [t for t in trades if t.result != "open"]
    half = len(closed) // 2
    if half >= 3:
        a, b = stats(closed[:half]), stats(closed[half:])
        out.append(f"ครึ่งแรก/ครึ่งหลัง  {a['total_r']:+.1f}R ({a['win_rate']:.0f}%) / "
                   f"{b['total_r']:+.1f}R ({b['win_rate']:.0f}%)")
    s2 = stats(trades_x2)
    out.append(f"ถ้าสเปรดกว้างขึ้น 2 เท่า  {s2['total_r']:+.1f}R  (PF {s2['profit_factor']:.2f})")
    mc = monte_carlo([t.r for t in closed])
    if mc:
        out.append(f"Monte Carlo: drawdown ปกติ {mc['dd_median']:.1f}R, แย่สุด 5% {mc['dd_95']:.1f}R, "
                   f"แพ้ติดกันได้ถึง {mc['streak_95']} ไม้")
    by_kz = defaultdict(list)
    for t in closed:
        by_kz[t.kill_zone].append(t)
    for name, ts in sorted(by_kz.items()):
        k = stats(ts)
        out.append(f"  {name or '-':9} {k['trades']:3} ไม้  {k['win_rate']:5.1f}%  {k['total_r']:+.1f}R")
    by_month = defaultdict(float)
    for t in closed:
        by_month[datetime.fromtimestamp(t.entry_time, TH).strftime("%Y-%m")] += t.r
    out.append("รายเดือน: " + "  ".join(f"{m} {r:+.1f}R" for m, r in sorted(by_month.items())))
    return "\n".join(out)


def save_trades(path, trades: list[Trade]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "direction", "entry_time_th", "entry", "sl", "tp",
                    "exit_time_th", "exit", "result", "r", "kill_zone"])
        fmt = lambda t: datetime.fromtimestamp(t, TH).strftime("%Y-%m-%d %H:%M") if t else ""
        for t in trades:
            w.writerow([t.symbol, t.direction, fmt(t.entry_time), t.entry, t.sl, t.tp,
                        fmt(t.exit_time), t.exit, t.result, round(t.r, 3), t.kill_zone])


def main() -> None:
    from .app import CFG, ROOT, SOURCE

    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=25000, help="entry-TF bars to test (M15: ~25000 ≈ 1 year)")
    ap.add_argument("--symbol", help="test one symbol only, e.g. XAUUSD")
    ap.add_argument("--spread", type=float, help="spread in price units (default: current spread)")
    args = ap.parse_args()

    scfg = CFG.get("signals", {})
    tcfg = CFG.get("trading", {})
    tf = scfg.get("entry_tf", "M15")
    risk_pct = float(tcfg.get("risk_percent", 0.5))
    max_day = int(tcfg.get("max_trades_per_day", 3))
    symbols = [args.symbol] if args.symbol else list(CFG["symbols"])
    if SOURCE.name != "mt5":
        print("คำเตือน: ใช้ราคาจำลอง (sim) ผลไม่ได้สะท้อนตลาดจริง\n")
    all_trades = []
    for sym in symbols:
        print(f"กำลังโหลดราคา {sym} ...", flush=True)
        ltf = SOURCE.candles(sym, tf, args.bars)[:-1]
        span_days = (ltf[-1].time - ltf[0].time) // 86400 + 30
        h1 = SOURCE.candles(sym, "H1", min(span_days * 24 + 500, 100000))[:-1]
        d1 = SOURCE.candles(sym, "D1", span_days + 250)[:-1]
        tick = SOURCE.tick(sym) or {}
        spread = args.spread if args.spread is not None else \
            max(float(tick.get("ask", 0)) - float(tick.get("bid", 0)), 0.0)
        print(f"ทดสอบ {len(ltf)} แท่ง {tf} (สเปรด {spread:g}) ...", flush=True)
        trades = run(sym, d1, h1, ltf, scfg, spread, max_day)
        trades_x2 = [Trade(**{**t.__dict__, "r": t.r - t.cost_r}) for t in trades]
        print(report(sym, trades, trades_x2, ltf[0].time, ltf[-1].time, risk_pct) + "\n", flush=True)
        all_trades += trades
    out = ROOT / "backtest_trades.csv"
    save_trades(out, all_trades)
    print(f"รายละเอียดทุกไม้บันทึกที่ {out}")
    print("หมายเหตุ: ผลย้อนหลังไม่ได้รับประกันผลในอนาคต")


if __name__ == "__main__":
    main()
