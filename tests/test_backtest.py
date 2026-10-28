from server.backtest import max_drawdown, longest_losing_streak, run, stats
from server.datasource import SimSource


def test_drawdown_and_streak():
    rs = [1, -1, -1, 2, -1, -1, -1, 3]
    assert max_drawdown(rs) == 3
    assert longest_losing_streak(rs) == 3


def test_run_on_sim_is_consistent():
    src = SimSource({"symbols": {"XAUUSD": "XAUUSD"}})
    ltf = src._build("XAUUSD", "M15", 4000)
    h1 = src._build("XAUUSD", "H1", 1200)
    d1 = src._build("XAUUSD", "D1", 300)
    trades = run("XAUUSD", d1, h1, ltf, {}, spread=0.2)
    assert trades
    for a, b in zip(trades, trades[1:]):
        assert a.exit_time is not None and b.entry_time > a.exit_time  # one trade at a time
    for t in trades:
        if t.result == "win":
            assert t.r > 0
        if t.result == "loss":
            assert t.r < -1  # -1R plus spread
    assert stats(trades)["trades"] == sum(t.result != "open" for t in trades)
