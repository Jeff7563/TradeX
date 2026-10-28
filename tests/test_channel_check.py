from server.channel_check import Post, parse_page, parse_signal, replay
from server.datasource import Candle

PAGE = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
 <div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="tradeforex112233/501" data-view="x">
  <div class="tgme_widget_message_bubble">
   <div class="tgme_widget_message_text js-message_text" dir="auto">GOLD Buy 4116-4112<br/>TP 4122<br/>TP 4130<br/>TP 4150<br/>SL 4103</div>
   <div class="tgme_widget_message_footer"><a class="tgme_widget_message_date" href="#"><time datetime="2026-10-28T19:27:31+00:00" class="time">02:27</time></a></div>
  </div>
 </div>
</div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
 <div class="tgme_widget_message js-widget_message" data-post="tradeforex112233/502">
   <div class="tgme_widget_message_text js-message_text" dir="auto">GOLD Buy &amp; HIT TP 1</div>
   <time datetime="2026-10-28T20:35:00+00:00" class="time">03:35</time>
 </div>
</div>
"""


def test_parse_page_reads_posts():
    posts = parse_page(PAGE)
    assert [p.id for p in posts] == [501, 502]
    assert "TP 4130" in posts[0].text and "\n" in posts[0].text
    assert posts[1].text == "GOLD Buy & HIT TP 1"


def test_parse_signal():
    s = parse_signal(parse_page(PAGE)[0])
    assert (s.symbol, s.direction, s.entry_lo, s.entry_hi, s.tps, s.sl) == \
        ("XAUUSD", "buy", 4112, 4116, [4122, 4130, 4150], 4103)
    assert parse_signal(Post(1, 0, "GOLD Buy 4116")) is None


def bar(t, o, h, l, c):
    return Candle(t, o, h, l, c)


def sig():
    return parse_signal(Post(1, 1000, "GOLD Buy 4116-4112 TP 4122 TP 4130 TP 4150 SL 4103"))


def test_replay_hits_two_tps_then_sl():
    bars = [bar(1020, 4115, 4116, 4114, 4115),   # enter at 4115 (in range)
            bar(1080, 4115, 4123, 4114, 4122),   # TP1
            bar(1140, 4122, 4131, 4120, 4128),   # TP2
            bar(1200, 4128, 4129, 4100, 4101)]   # SL
    o = replay(sig(), bars, spread=0)
    assert o.entry == 4115 and o.tp_hit == 2 and o.status == "tp2 then sl"
    assert abs(o.r_tp1 - 7 / 12) < 1e-9          # (4122-4115)/(4115-4103)
    assert abs(o.r_split - (7 / 12 + 15 / 12 - 1) / 3) < 1e-9


def test_replay_waits_for_range_and_sl_first_on_same_bar():
    bars = [bar(1020, 4120, 4121, 4118, 4119),   # above range: wait
            bar(1080, 4119, 4119, 4116, 4117),   # touches 4116 -> filled at 4116
            bar(1140, 4117, 4125, 4100, 4110)]   # touches TP1 and SL: count SL
    o = replay(sig(), bars, spread=0)
    assert o.entry == 4116 and o.status == "sl" and o.r_tp1 == -1


def test_replay_not_filled_when_price_runs_away():
    bars = [bar(1020, 4120, 4121, 4118, 4119), bar(1080, 4119, 4125, 4119, 4124)]
    assert replay(sig(), bars, spread=0).status == "not filled"


def test_reply_quote_is_not_part_of_post():
    page = """<div class="tgme_widget_message js-widget_message" data-post="c/9">
      <a class="tgme_widget_message_reply"><div class="tgme_widget_message_text js-message_reply_text">GOLD Buy 4116 TP 4122 SL 4103</div></a>
      <div class="tgme_widget_message_text js-message_text">HIT TP1 +60 pips</div>
      <time datetime="2026-10-28T20:35:00+00:00">03:35</time></div>"""
    posts = parse_page(page)
    assert posts[0].text == "HIT TP1 +60 pips"
    assert parse_signal(posts[0]) is None
