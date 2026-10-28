from datetime import datetime, timezone

from server.datasource import Candle, SimSource
from server.smc import analyse, fvgs, kill_zones, structure, swings


def bars(closes, start=1_700_000_000, step=900):
    out = []
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        out.append(Candle(start + i * step, o, max(o, c) + 0.1, min(o, c) - 0.1, c))
        prev = c
    return out


def test_swing_high_and_low_found():
    c = bars([1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 5, 6])
    sw = swings(c, n=3)
    assert any(s["kind"] == "high" and s["i"] == 4 for s in sw)
    assert any(s["kind"] == "low" and s["i"] == 8 for s in sw)


def test_choch_then_bos():
    # up to 5, down to 1, then rally through 5 (first break = CHoCH),
    # pull back, then through the next high (same direction = BOS)
    seq = [1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3, 4, 5.5, 6, 7, 6, 5, 4.5, 5, 6, 7.5, 8, 9]
    c = bars(seq)
    ev, trend = structure(c, swings(c, 3), 3)
    kinds = [(e["kind"], e["dir"]) for e in ev]
    assert kinds[0] == ("CHoCH", "bull")
    assert ("BOS", "bull") in kinds
    assert trend == "bull"


def test_fvg_bull_and_fill():
    c = [Candle(0, 10, 11, 9.5, 10.8), Candle(1, 10.8, 14, 10.7, 13.8),
         Candle(2, 13.8, 15, 12, 14.5), Candle(3, 14.5, 14.6, 10.5, 10.6)]
    g = fvgs(c)
    assert g[0]["dir"] == "bull" and g[0]["bottom"] == 11 and g[0]["top"] == 12
    assert g[0]["filled"] is True


def test_kill_zones_follow_new_york_dst():
    # Wed 2026-10-28: NY on EDT (UTC-4) -> London KZ 06:00-09:00 UTC
    t = int(datetime(2026, 10, 28, 12, tzinfo=timezone.utc).timestamp())
    kz = [k for k in kill_zones(t - 12 * 3600, t) if k["name"] == "London"]
    starts = {datetime.fromtimestamp(k["start"], timezone.utc).strftime("%m-%d %H:%M") for k in kz}
    assert "10-28 06:00" in starts
    # Wed 2026-11-04: NY on EST (UTC-5) -> 07:00 UTC
    t2 = int(datetime(2026, 11, 4, 12, tzinfo=timezone.utc).timestamp())
    starts2 = {datetime.fromtimestamp(k["start"], timezone.utc).strftime("%m-%d %H:%M")
               for k in kill_zones(t2 - 12 * 3600, t2) if k["name"] == "London"}
    assert "11-04 07:00" in starts2


def test_analyse_on_sim_data_runs():
    src = SimSource({"symbols": {"XAUUSD": "XAUUSD"}})
    out = analyse(src.candles("XAUUSD", "M15", 500), "M15")
    assert out["trend"] in ("bull", "bear", "none")
    assert out["swings"]
