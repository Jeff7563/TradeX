"""Compare many rule settings without fooling ourselves.

Each setting is backtested on the whole history, then its trades are split in
time: the FIRST half is where we pick the best settings ("train"), the SECOND
half is data the choice never saw ("test"). Only settings that also make money
in the test half are worth trying on demo.

Run:  python -m server.optimize               (about 10–20 minutes)
      python -m server.optimize --symbol XAUUSD
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import time

from .backtest import run, stats

TF_MULT = {"M15": 1, "M5": 3}  # M5 needs 3x the bars and 3x the bar-count limits


def grid() -> list[dict]:
    out = []
    for tf, zones, (tp_mode, rr) in itertools.product(
            ["M15", "M5"], [["FVG"], ["OB"], ["FVG", "OB"]],
            [("liquidity", 2.0), ("fixed", 2.0), ("fixed", 3.0)]):
        base = {"entry_tf": tf, "zones": zones, "tp_mode": tp_mode, "fixed_rr": rr, "min_rr": 2.0,
                "max_bars_since_break": 24 * TF_MULT[tf], "sweep_lookback": 30 * TF_MULT[tf]}
        out.append({**base, "require_sweep": False, "sl_mode": "zone"})
        for sl in ("zone", "sweep"):
            out.append({**base, "require_sweep": True, "sl_mode": sl})
    return out


def describe(c: dict) -> str:
    tp = "TP liquidity" if c["tp_mode"] == "liquidity" else f"TP {c['fixed_rr']:g}R"
    sweep = f"sweep+SL {c['sl_mode']}" if c["require_sweep"] else "no sweep"
    return f"{c['entry_tf']:3} {'+'.join(c['zones']):6} {tp:12} {sweep}"


def main() -> None:
    from .app import CFG, ROOT, SOURCE

    ap = argparse.ArgumentParser()
    ap.add_argument("--bars", type=int, default=25000, help="M15 bars of history (M5 uses 3x)")
    ap.add_argument("--symbol")
    ap.add_argument("--min-trades", type=int, default=15, help="ignore settings with fewer train trades")
    args = ap.parse_args()

    tcfg = CFG.get("trading", {})
    max_day = int(tcfg.get("max_trades_per_day", 3))
    symbols = [args.symbol] if args.symbol else list(CFG["symbols"])
    combos = grid()
    rows = []
    for sym in symbols:
        print(f"\nกำลังโหลดราคา {sym} ...", flush=True)
        data = {"M15": SOURCE.candles(sym, "M15", args.bars)[:-1]}
        data["M5"] = SOURCE.candles(sym, "M5", args.bars * 3)[:-1]
        first = max(data["M15"][0].time, data["M5"][0].time)
        last = data["M15"][-1].time
        span_days = (last - first) // 86400 + 30
        h1 = SOURCE.candles(sym, "H1", min(span_days * 24 + 500, 100000))[:-1]
        d1 = SOURCE.candles(sym, "D1", span_days + 250)[:-1]
        # same period for both entry timeframes so results compare fairly
        data = {tf: [b for b in bars if b.time >= first] for tf, bars in data.items()}
        mid = first + (last - first) // 2
        tick = SOURCE.tick(sym) or {}
        spread = max(float(tick.get("ask", 0)) - float(tick.get("bid", 0)), 0.0)
        print(f"ช่วง train/test แบ่งที่ {time.strftime('%d/%m/%Y', time.gmtime(mid))} | "
              f"ทดสอบ {len(combos)} ชุดกฎ ...", flush=True)
        t0 = time.time()
        for n, c in enumerate(combos, 1):
            trades = run(sym, d1, h1, data[c["entry_tf"]], c, spread, max_day)
            tr = [t for t in trades if t.entry_time < mid]
            te = [t for t in trades if t.entry_time >= mid]
            rows.append({"symbol": sym, "rules": describe(c), "cfg": c,
                         "train": stats(tr), "test": stats(te)})
            if n % 6 == 0:
                print(f"  {n}/{len(combos)} ({time.time() - t0:.0f} วินาที)", flush=True)

    for sym in symbols:
        rs = [r for r in rows if r["symbol"] == sym and r["train"]["trades"] >= args.min_trades]
        rs.sort(key=lambda r: r["train"]["total_r"], reverse=True)
        print(f"\n=== {sym}: 10 ชุดที่ดีที่สุดในครึ่งแรก แล้วดูว่าครึ่งหลังรอดไหม ===")
        print(f"{'กฎ':42} | {'ครึ่งแรก (train)':26} | {'ครึ่งหลัง (test)':26}")
        for r in rs[:10]:
            a, b = r["train"], r["test"]
            ok = "✓" if b["trades"] >= 10 and b["total_r"] > 0 and b["profit_factor"] > 1.1 else " "
            print(f"{r['rules']:42} | {a['trades']:3} ไม้ {a['win_rate']:4.0f}% {a['total_r']:+6.1f}R PF{a['profit_factor']:4.2f} "
                  f"| {b['trades']:3} ไม้ {b['win_rate']:4.0f}% {b['total_r']:+6.1f}R PF{b['profit_factor']:4.2f} {ok}")
        good = [r for r in rs[:10] if r["test"]["trades"] >= 10 and r["test"]["total_r"] > 0
                and r["test"]["profit_factor"] > 1.1]
        if good:
            print("\nชุดที่ผ่านทั้งสองครึ่ง (✓) ตัวแรก ใส่ใน config.json ส่วน \"signals\" ได้แบบนี้:")
            print(json.dumps({k: v for k, v in good[0]["cfg"].items()}, ensure_ascii=False))
        else:
            print("\nไม่มีชุดไหนผ่านครึ่งหลัง: ยังไม่ควรใช้กฎเหล่านี้เทรดจริง")

    out = ROOT / "optimize_results.csv"
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "rules", "train_trades", "train_win%", "train_R", "train_PF",
                    "test_trades", "test_win%", "test_R", "test_PF", "config"])
        for r in rows:
            a, b = r["train"], r["test"]
            w.writerow([r["symbol"], r["rules"], a["trades"], round(a["win_rate"], 1), round(a["total_r"], 2),
                        round(a["profit_factor"], 2), b["trades"], round(b["win_rate"], 1),
                        round(b["total_r"], 2), round(b["profit_factor"], 2), json.dumps(r["cfg"])])
    print(f"\nผลทุกชุดบันทึกที่ {out}")
    print("หมายเหตุ: ยิ่งลองหลายชุด ยิ่งมีโอกาสเจอชุดที่ดีเพราะโชค ให้เชื่อเฉพาะผลครึ่งหลังและต้องทดสอบบน Demo ต่อ")


if __name__ == "__main__":
    main()
