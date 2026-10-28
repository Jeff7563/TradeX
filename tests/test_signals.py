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
