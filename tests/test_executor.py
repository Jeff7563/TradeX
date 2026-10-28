from types import SimpleNamespace as NS

from server.executor import Executor, lot_size
from server.signals import Signal


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_REAL = 0, 2
    DEAL_ENTRY_IN, DEAL_ENTRY_OUT = 0, 1
    TRADE_ACTION_DEAL, ORDER_TYPE_BUY, ORDER_TYPE_SELL = 1, 0, 1
    ORDER_FILLING_FOK, ORDER_FILLING_IOC, ORDER_FILLING_RETURN = 0, 1, 2
    ORDER_TIME_GTC, TRADE_RETCODE_DONE = 0, 10009

    def __init__(self, demo=True, balance=10_000, positions=(), deals=()):
        self.mode = 0 if demo else 2
        self.balance = balance
        self.positions = list(positions)
        self.deals = list(deals)
        self.sent = []

    def account_info(self):
        return NS(trade_mode=self.mode, balance=self.balance)

    def positions_get(self, symbol=None):
        return self.positions

    def history_deals_get(self, a, b):
        return self.deals

    def symbol_info(self, s):
        # gold-like: 0.01 price step worth $1 per lot
        return NS(trade_tick_size=0.01, trade_tick_value=1.0, volume_min=0.01,
                  volume_max=100, volume_step=0.01, digits=2, filling_mode=1)

    def symbol_info_tick(self, s):
        return NS(bid=4000.0, ask=4000.2)

    def order_send(self, req):
        self.sent.append(req)
        return NS(retcode=10009, price=req["price"], order=123, comment="done")

    def last_error(self):
        return (0, "")


SIG = Signal("XAUUSD", "buy", 4000.0, 3990.0, 4030.0, 3.0, 0,
             {"kind": "FVG", "top": 3995, "bottom": 3991, "time": 0}, [])
CFG = {"enabled": True, "risk_percent": 1.0}
SYMS = {"XAUUSD": "XAUUSDm"}


def test_lot_size_matches_risk():
    # $10k * 1% = $100 risk; 10.0 price stop = 1000 ticks * $1 = $1000 per lot -> 0.1 lot
    assert lot_size(10_000, 1.0, 4000, 3990, 0.01, 1.0, 0.01, 100, 0.01) == 0.1
    # stop too wide for minimum lot
    assert lot_size(100, 0.5, 4000, 3900, 0.01, 1.0, 0.01, 100, 0.01) == 0.0


def test_places_order_on_demo(tmp_path):
    mt5 = FakeMT5()
    ok, msg = Executor(mt5, CFG, SYMS, tmp_path / "t.csv").place(SIG)
    assert ok, msg
    req = mt5.sent[0]
    assert req["symbol"] == "XAUUSDm" and req["sl"] == 3990.0 and req["tp"] == 4030.0
    assert 0 < req["volume"] <= 0.1
    assert (tmp_path / "t.csv").exists()


def test_refuses_real_account(tmp_path):
    mt5 = FakeMT5(demo=False)
    ok, msg = Executor(mt5, CFG, SYMS, tmp_path / "t.csv").place(SIG)
    assert not ok and "Demo" in msg and not mt5.sent


def test_disabled_by_default(tmp_path):
    mt5 = FakeMT5()
    ok, _ = Executor(mt5, {}, SYMS, tmp_path / "t.csv").place(SIG)
    assert not ok and not mt5.sent


def test_blocks_when_position_open(tmp_path):
    mt5 = FakeMT5(positions=[NS(magic=770077)])
    ok, _ = Executor(mt5, CFG, SYMS, tmp_path / "t.csv").place(SIG)
    assert not ok and not mt5.sent


def test_daily_loss_limit(tmp_path):
    deals = [NS(magic=770077, entry=1, profit=-250, commission=0, swap=0)]
    mt5 = FakeMT5(deals=deals)  # -$250 on $10k = 2.5% > 2% limit
    ok, msg = Executor(mt5, CFG, SYMS, tmp_path / "t.csv").place(SIG)
    assert not ok and "ลิมิต" in msg


def test_max_trades_per_day(tmp_path):
    deals = [NS(magic=770077, entry=0, profit=0, commission=0, swap=0)] * 3
    ok, _ = Executor(FakeMT5(deals=deals), CFG, SYMS, tmp_path / "t.csv").place(SIG)
    assert not ok


def test_skips_if_price_already_past_target(tmp_path):
    sig = Signal("XAUUSD", "buy", 3980.0, 3970.0, 3999.0, 2.0, 0, SIG.zone, [])
    mt5 = FakeMT5()  # ask 4000.2 is above TP 3999
    ok, _ = Executor(mt5, CFG, SYMS, tmp_path / "t.csv").place(sig)
    assert not ok and not mt5.sent
