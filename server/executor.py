"""Places orders in MT5 for signals, with risk limits.

Safety rules (all checked before every order):
 - Only a DEMO account, unless trading.allow_live is true in config.json.
 - Lot size from risk_percent of balance and the stop distance.
 - At most max_positions_per_symbol open TradeX positions per symbol.
 - At most max_trades_per_day new TradeX trades per day.
 - Stop for the day once today's TradeX loss reaches daily_loss_limit_percent.
"""
from __future__ import annotations

import csv
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .signals import Signal

DEFAULTS = {
    "enabled": False,
    "allow_live": False,
    "risk_percent": 0.5,
    "max_positions_per_symbol": 1,
    "max_trades_per_day": 3,
    "daily_loss_limit_percent": 2.0,
    "max_slippage_points": 30,
    "magic": 770077,
}


def lot_size(balance: float, risk_percent: float, entry: float, sl: float,
             tick_size: float, tick_value: float, vol_min: float, vol_max: float,
             vol_step: float) -> float:
    """Lots so that hitting the stop loses about risk_percent of balance (rounded down)."""
    risk_money = balance * risk_percent / 100
    loss_per_lot = abs(entry - sl) / tick_size * tick_value
    if loss_per_lot <= 0:
        return 0.0
    raw = risk_money / loss_per_lot
    lots = math.floor(raw / vol_step + 1e-9) * vol_step
    lots = min(lots, vol_max)
    if lots < vol_min:
        return 0.0
    decimals = max(0, -int(math.floor(math.log10(vol_step)))) if vol_step < 1 else 0
    return round(lots, decimals)


class Executor:
    def __init__(self, mt5, cfg: dict, symbols: dict, log_path: Path):
        self.mt5 = mt5
        self.cfg = {**DEFAULTS, **cfg}
        self.symbols = symbols
        self.log_path = log_path

    # ---- checks ---------------------------------------------------------
    def _is_demo(self) -> bool:
        acc = self.mt5.account_info()
        return acc is not None and acc.trade_mode == self.mt5.ACCOUNT_TRADE_MODE_DEMO

    def _today_start(self) -> datetime:
        now = datetime.now(timezone.utc)
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    def _today_deals(self) -> list:
        deals = self.mt5.history_deals_get(self._today_start(),
                                           datetime.now(timezone.utc) + timedelta(hours=1))
        return [d for d in (deals or []) if d.magic == self.cfg["magic"]]

    def check(self, sig: Signal) -> str | None:
        """Reason the trade is blocked, or None if it may go ahead."""
        if not self.cfg["enabled"]:
            return "การเทรดอัตโนมัติปิดอยู่ (trading.enabled = false)"
        if not self._is_demo() and not self.cfg["allow_live"]:
            return "บัญชีนี้ไม่ใช่ Demo บอทจึงไม่เข้าออเดอร์"
        broker_sym = self.symbols[sig.symbol]
        open_pos = [p for p in (self.mt5.positions_get(symbol=broker_sym) or [])
                    if p.magic == self.cfg["magic"]]
        if len(open_pos) >= self.cfg["max_positions_per_symbol"]:
            return f"มีออเดอร์ {sig.symbol} เปิดอยู่แล้ว"
        deals = self._today_deals()
        opened = [d for d in deals if d.entry == self.mt5.DEAL_ENTRY_IN]
        if len(opened) >= self.cfg["max_trades_per_day"]:
            return f"ครบ {self.cfg['max_trades_per_day']} ไม้ของวันนี้แล้ว"
        pnl = sum(d.profit + d.commission + d.swap for d in deals)
        acc = self.mt5.account_info()
        if pnl < 0 and -pnl >= acc.balance * self.cfg["daily_loss_limit_percent"] / 100:
            return f"ขาดทุนวันนี้ถึงลิมิต {self.cfg['daily_loss_limit_percent']}% แล้ว หยุดเทรดถึงพรุ่งนี้"
        return None

    # ---- order ------------------------------------------------------------
    def _filling(self, info) -> int:
        mode = getattr(info, "filling_mode", 0)
        if mode & 1:
            return self.mt5.ORDER_FILLING_FOK
        if mode & 2:
            return self.mt5.ORDER_FILLING_IOC
        return self.mt5.ORDER_FILLING_RETURN

    def place(self, sig: Signal) -> tuple[bool, str]:
        blocked = self.check(sig)
        if blocked:
            return False, blocked
        mt5 = self.mt5
        sym = self.symbols[sig.symbol]
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if info is None or tick is None:
            return False, f"ไม่พบข้อมูลสัญลักษณ์ {sym}"
        buy = sig.direction == "buy"
        price = tick.ask if buy else tick.bid
        # price moved past the stop or the target since the signal: skip
        if (buy and not (sig.sl < price < sig.tp)) or (not buy and not (sig.tp < price < sig.sl)):
            return False, "ราคาวิ่งเลย SL/TP ไปแล้ว ไม่เข้าออเดอร์"
        acc = mt5.account_info()
        lots = lot_size(acc.balance, self.cfg["risk_percent"], price, sig.sl,
                        info.trade_tick_size, info.trade_tick_value,
                        info.volume_min, info.volume_max, info.volume_step)
        if lots <= 0:
            return False, "SL กว้างเกินไปสำหรับความเสี่ยงที่ตั้งไว้ (lot ต่ำกว่าขั้นต่ำ)"
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": lots,
            "type": mt5.ORDER_TYPE_BUY if buy else mt5.ORDER_TYPE_SELL,
            "price": price,
            "sl": round(sig.sl, info.digits),
            "tp": round(sig.tp, info.digits),
            "deviation": self.cfg["max_slippage_points"],
            "magic": self.cfg["magic"],
            "comment": "TradeX v1",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._filling(info),
        }
        res = mt5.order_send(req)
        if res is None or res.retcode != mt5.TRADE_RETCODE_DONE:
            code = getattr(res, "retcode", None)
            note = getattr(res, "comment", mt5.last_error())
            return False, f"ส่งออเดอร์ไม่สำเร็จ ({code}: {note})"
        self._log(sig, lots, res)
        return True, f"เปิด {sig.direction.upper()} {sig.symbol} {lots} lot ที่ {res.price} (ticket {res.order})"

    def _log(self, sig: Signal, lots: float, res) -> None:
        new = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "symbol", "direction", "lots", "price", "sl", "tp", "ticket", "signal_key"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), sig.symbol,
                        sig.direction, lots, res.price, sig.sl, sig.tp, res.order, sig.key])
