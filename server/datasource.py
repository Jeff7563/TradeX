"""Where candles come from.

MT5Source reads live prices from the MetaTrader 5 terminal running on this PC.
SimSource makes fake random candles so the chart can be tried without MT5.
SimSource prices are NOT real market prices.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, asdict

TF_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800,
              "H1": 3600, "H4": 14400, "D1": 86400}


@dataclass
class Candle:
    time: int      # UTC epoch seconds, start of the bar
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


class MT5Source:
    name = "mt5"

    def __init__(self, cfg: dict):
        import MetaTrader5 as mt5  # Windows only
        self.mt5 = mt5
        self.symbols: dict = cfg["symbols"]
        self.server_offset = int(cfg.get("server_utc_offset_hours", 0)) * 3600
        m = cfg.get("mt5", {})
        kwargs = {}
        if m.get("path"):
            kwargs["path"] = m["path"]
        if m.get("login"):
            kwargs.update(login=int(m["login"]), password=m.get("password", ""),
                          server=m.get("server", ""))
        if not mt5.initialize(**kwargs):
            raise RuntimeError(f"MT5 initialize failed: {mt5.last_error()}")
        for broker_sym in self.symbols.values():
            if not mt5.symbol_select(broker_sym, True):
                raise RuntimeError(f"Symbol {broker_sym} not found at broker. "
                                   "Check the names in config.json.")
        self._tf = {"M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5,
                    "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
                    "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
                    "D1": mt5.TIMEFRAME_D1}

    def candles(self, symbol: str, tf: str, count: int) -> list[Candle]:
        rates = self.mt5.copy_rates_from_pos(self.symbols[symbol], self._tf[tf], 0, count)
        if rates is None:
            raise RuntimeError(f"No data for {symbol} {tf}: {self.mt5.last_error()}")
        return [Candle(int(r["time"]) - self.server_offset, float(r["open"]),
                       float(r["high"]), float(r["low"]), float(r["close"]),
                       float(r["tick_volume"])) for r in rates]

    def candles_range(self, symbol: str, tf: str, start: int, end: int) -> list[Candle]:
        """Bars between two UTC epoch times (used to replay old signals)."""
        from datetime import datetime, timezone
        a = datetime.fromtimestamp(start + self.server_offset, timezone.utc)
        b = datetime.fromtimestamp(end + self.server_offset, timezone.utc)
        rates = self.mt5.copy_rates_range(self.symbols[symbol], self._tf[tf], a, b)
        if rates is None:
            return []
        return [Candle(int(r["time"]) - self.server_offset, float(r["open"]),
                       float(r["high"]), float(r["low"]), float(r["close"]),
                       float(r["tick_volume"])) for r in rates]

    def tick(self, symbol: str) -> dict | None:
        t = self.mt5.symbol_info_tick(self.symbols[symbol])
        if t is None:
            return None
        return {"bid": t.bid, "ask": t.ask, "time": int(t.time) - self.server_offset}


class SimSource:
    """Random-walk candles for testing. Not real prices."""
    name = "sim"
    BASE = {"XAUUSD": 4000.0, "BTCUSD": 100000.0}

    def __init__(self, cfg: dict):
        self.symbols = cfg["symbols"]
        self._cache: dict[tuple, list[Candle]] = {}

    def _build(self, symbol: str, tf: str, count: int) -> list[Candle]:
        step = TF_SECONDS[tf]
        rng = random.Random(f"{symbol}-{tf}")
        price = self.BASE.get(symbol, 100.0)
        vol = price * 0.0015 * (step / 900) ** 0.5
        now = int(time.time()) // step * step
        out = []
        for i in range(count):
            t = now - (count - 1 - i) * step
            o = price
            drift = vol * 0.6 * (1 if (i // 40) % 2 == 0 else -1)
            c = o + rng.gauss(drift * 0.1, vol)
            h = max(o, c) + abs(rng.gauss(0, vol * 0.5))
            l = min(o, c) - abs(rng.gauss(0, vol * 0.5))
            out.append(Candle(t, round(o, 2), round(h, 2), round(l, 2), round(c, 2)))
            price = c
        return out

    def candles(self, symbol: str, tf: str, count: int) -> list[Candle]:
        key = (symbol, tf)
        step = TF_SECONDS[tf]
        bars = self._cache.get(key)
        if not bars or len(bars) < count:
            bars = self._build(symbol, tf, count)
        now = int(time.time()) // step * step
        last = bars[-1]
        vol = last.close * 0.0004
        if now > last.time:  # new bar opened
            bars.append(Candle(now, last.close, last.close, last.close, last.close))
        else:  # wiggle the live bar
            c = round(last.close + random.gauss(0, vol), 2)
            last.close, last.high, last.low = c, max(last.high, c), min(last.low, c)
        self._cache[key] = bars[-max(count, 1000):]
        return self._cache[key][-count:]

    def candles_range(self, symbol: str, tf: str, start: int, end: int) -> list[Candle]:
        step = TF_SECONDS[tf]
        n = max(int((end - start) // step), 1)
        rng = random.Random(f"{symbol}-{tf}-{start}")
        price = self.BASE.get(symbol, 100.0)
        out, t = [], start // step * step
        for _ in range(n):
            o = price
            c = o + rng.gauss(0, price * 0.0004)
            out.append(Candle(t, o, max(o, c) + abs(rng.gauss(0, price * 0.0002)),
                              min(o, c) - abs(rng.gauss(0, price * 0.0002)), c))
            price, t = c, t + step
        return out

    def tick(self, symbol: str) -> dict | None:
        bars = self._cache.get((symbol, "M5")) or self.candles(symbol, "M5", 2)
        p = bars[-1].close
        return {"bid": p, "ask": round(p + 0.2, 2), "time": int(time.time())}


def make_source(cfg: dict):
    if cfg.get("source") == "mt5":
        return MT5Source(cfg)
    return SimSource(cfg)
