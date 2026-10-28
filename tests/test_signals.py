from server.datasource import SimSource
from server.notify import format_signal
from server.signals import evaluate


def replay(sym, bars=1500):
    src = SimSource({"symbols": {sym: sym}})
    m15 = src._build(sym, "M15", bars)
    h1 = src._build(sym, "H1", 600)
    d1 = src._build(sym, "D1", 200)
    out = {}
    for k in range(300, len(m15)):
        t = m15[k].time
        s = evaluate(sym, [c for c in d1 if c.time < t - 86400],
                     [c for c in h1 if c.time <= t - 3600][-400:], m15[k - 400:k + 1])
        if s:
            out.setdefault(s.key, s)
    return list(out.values())


def test_signals_are_well_formed():
    sigs = replay("XAUUSD")
    assert sigs, "sim data should produce at least one setup"
    for s in sigs:
        if s.direction == "buy":
            assert s.sl < s.entry < s.tp
        else:
            assert s.tp < s.entry < s.sl
        assert s.rr >= 2.0
        assert any("Kill zone" in r for r in s.reasons)


def test_format_contains_levels():
    s = replay("XAUUSD")[0]
    text = format_signal(s)
    assert str(s.entry) in text and str(s.sl) in text and str(s.tp) in text


from datetime import datetime, timezone
from server.datasource import Candle
from server.signals import asia_range, find_sweep


def test_asia_range_uses_new_york_evening():
    # 2026-10-28 is EDT: Asia range = 00:00–04:00 UTC
    base = int(datetime(2026, 10, 28, 0, tzinfo=timezone.utc).timestamp())
    c = [Candle(base + i * 900, 10, 11 + (i == 3), 9 - (i == 5), 10) for i in range(24)]
    a = asia_range(c, base + 6 * 3600)
    assert a and a["high"] == 12 and a["low"] == 8


def test_sweep_needs_close_back_inside():
    lv = [{"name": "swing low", "price": 100.0, "ready": 0}]
    swept = [Candle(i, 101, 102, 99 if i == 2 else 100.5, 101) for i in range(5)]
    assert find_sweep(swept, 0, 4, "bull", lv)["i"] == 2
    broke = [Candle(i, 101, 102, 99 if i == 2 else 100.5, 99.5 if i in (2, 3) else 101) for i in range(5)]
    assert find_sweep(broke, 0, 4, "bull", lv) is None


def test_v2_sweep_signals_are_well_formed():
    cfg = {"require_sweep": True, "sl_mode": "sweep", "tp_mode": "fixed", "fixed_rr": 3.0}
    src = SimSource({"symbols": {"XAUUSD": "XAUUSD"}})
    m15 = src._build("XAUUSD", "M15", 3000)
    h1 = src._build("XAUUSD", "H1", 900)
    d1 = src._build("XAUUSD", "D1", 200)
    found = 0
    for k in range(400, len(m15)):
        t = m15[k].time
        s = evaluate("XAUUSD", [c for c in d1 if c.time < t - 86400],
                     [c for c in h1 if c.time <= t - 3600][-400:], m15[k - 400:k + 1], cfg)
        if s:
            found += 1
            assert any("กวาด" in r for r in s.reasons)
            assert abs(s.rr - 3.0) < 0.01
            assert (s.sl < s.entry < s.tp) if s.direction == "buy" else (s.tp < s.entry < s.sl)
    assert found
