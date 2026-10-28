"""Signal scanner: checks every symbol on a timer and sends new setups to LINE.

Run:          python -m server.scanner
Test LINE:    python -m server.scanner --test-line
Every signal is also appended to signals.csv so we can measure hit rate later.
"""
from __future__ import annotations

import argparse
import csv
import json
import time
from pathlib import Path

from .app import CFG, ROOT, SOURCE
from .executor import Executor
from .notify import Notifier, format_signal
from .signals import evaluate

LOG = ROOT / "signals.csv"
SEEN = ROOT / "signals_seen.json"
TRADES = ROOT / "trades.csv"


def log_signal(sig) -> None:
    new = not LOG.exists()
    with LOG.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "symbol", "direction", "entry", "sl", "tp", "rr", "zone", "key"])
        w.writerow([sig.time, sig.symbol, sig.direction, sig.entry, sig.sl, sig.tp,
                    sig.rr, sig.zone["kind"], sig.key])


def load_seen() -> set:
    try:
        return set(json.loads(SEEN.read_text()))
    except (FileNotFoundError, ValueError):
        return set()


def scan_once(notifier: Notifier, seen: set, scfg: dict, executor: Executor | None = None) -> int:
    sent = 0
    tf = scfg.get("entry_tf", "M15")
    for sym in CFG["symbols"]:
        try:
            d1 = SOURCE.candles(sym, "D1", 200)
            h1 = SOURCE.candles(sym, "H1", 500)
            ltf = SOURCE.candles(sym, tf, 500)
        except Exception as e:
            print(f"[{sym}] ดึงราคาไม่ได้: {e}", flush=True)
            continue
        # judge on closed bars only: drop the bar that is still forming
        sig = evaluate(sym, d1[:-1], h1[:-1], ltf[:-1], scfg)
        if sig and sig.key not in seen:
            seen.add(sig.key)
            SEEN.write_text(json.dumps(sorted(seen)[-500:]))
            log_signal(sig)
            notifier.send(format_signal(sig, tf))
            sent += 1
            if executor:
                ok, msg = executor.place(sig)
                notifier.send(("✅ " if ok else "⏸ ") + msg)
    return sent


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-line", action="store_true", help="send one test message and exit")
    ap.add_argument("--once", action="store_true", help="scan one time and exit")
    args = ap.parse_args()
    notifier = Notifier(CFG)
    scfg = CFG.get("signals", {})

    if args.test_line:
        if not notifier.line_ready:
            print("ยังไม่ได้ใส่ line.channel_access_token / line.user_id ใน config.json")
            return
        notifier.send("✅ TradeX เชื่อมต่อ LINE สำเร็จ")
        return

    print(f"TradeX scanner | source={SOURCE.name} | symbols={list(CFG['symbols'])} | "
          f"LINE={'on' if notifier.line_ready else 'off'}", flush=True)
    if SOURCE.name != "mt5":
        print("คำเตือน: ใช้ราคาจำลอง (sim) สัญญาณไม่ใช่ของจริง", flush=True)
    executor = None
    tcfg = CFG.get("trading", {})
    if tcfg.get("enabled"):
        if SOURCE.name != "mt5":
            print("trading.enabled = true แต่ไม่ได้ต่อ MT5 จึงไม่เข้าออเดอร์", flush=True)
        else:
            executor = Executor(SOURCE.mt5, tcfg, CFG["symbols"], TRADES)
            print(f"เทรดอัตโนมัติ: เปิด | เสี่ยง {executor.cfg['risk_percent']}% ต่อไม้ | "
                  f"สูงสุด {executor.cfg['max_trades_per_day']} ไม้/วัน | "
                  f"หยุดเมื่อขาดทุน {executor.cfg['daily_loss_limit_percent']}%/วัน", flush=True)
    seen = load_seen()
    every = int(scfg.get("scan_every_seconds", 30))
    while True:
        scan_once(notifier, seen, scfg, executor)
        if args.once:
            break
        time.sleep(every)


if __name__ == "__main__":
    main()
