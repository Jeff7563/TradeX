"""Check a public Telegram signal channel against real MT5 prices.

Reads the channel's public web page (t.me/s/<channel>), no Telegram login.
Each post with a direction, entry, TP and SL is replayed on M1 bars:
 - Entry: if the price is inside the entry range when posted, enter at once;
   otherwise wait up to entry_wait_hours for the price to reach the range.
 - Then see which comes first: SL or TP1 / TP2 / TP3 (a bar touching both
   counts as SL first). Spread is charged.
 - Results in R (1R = entry to SL).

Run:  python -m server.channel_check tradeforex112233
      python -m server.channel_check tradeforex112233 --days 120
"""
from __future__ import annotations

import argparse
import csv
import html
import re
import time
import unicodedata
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser

TH = timezone(timedelta(hours=7))
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TradeX channel check"

SYMBOLS = {"GOLD": "XAUUSD", "XAUUSD": "XAUUSD", "XAU": "XAUUSD",
           "BTC": "BTCUSD", "BTCUSD": "BTCUSD", "BITCOIN": "BTCUSD"}


# ---- reading the channel ---------------------------------------------------

@dataclass
class Post:
    id: int
    time: int        # UTC epoch
    text: str


class _PageParser(HTMLParser):
    """Pulls (post id, datetime, text) out of a t.me/s/ page."""

    def __init__(self):
        super().__init__()
        self.posts: list[Post] = []
        self._id = None
        self._time = None
        self._in_text = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class", "") or ""
        if "data-post" in a and "tgme_widget_message" in cls:
            self._flush()
            try:
                self._id = int(a["data-post"].rsplit("/", 1)[1])
            except (ValueError, IndexError):
                self._id = None
            self._time, self._buf = None, []
        elif tag == "div" and "tgme_widget_message_text" in cls and "reply" not in cls:
            self._in_text = 1
        elif self._in_text and tag == "div":
            self._in_text += 1
        elif self._in_text and tag == "br":
            self._buf.append("\n")
        elif tag == "time" and a.get("datetime") and self._id is not None:
            try:
                self._time = int(datetime.fromisoformat(a["datetime"]).timestamp())
            except ValueError:
                pass

    def handle_endtag(self, tag):
        if self._in_text and tag == "div":
            self._in_text -= 1
            if not self._in_text:
                self._buf.append("\n")

    def handle_data(self, data):
        if self._in_text:
            self._buf.append(data)

    def _flush(self):
        if self._id is not None and self._time is not None:
            text = html.unescape("".join(self._buf)).strip()
            if text:
                self.posts.append(Post(self._id, self._time, text))

    def close(self):
        super().close()
        self._flush()
        self._id = None


def parse_page(page: str) -> list[Post]:
    p = _PageParser()
    p.feed(page)
    p.close()
    return p.posts


def fetch_posts(channel: str, days: int, pause: float = 1.0, log=print) -> list[Post]:
    """Walk back through the channel until posts are older than `days`."""
    cutoff = time.time() - days * 86400
    posts: dict[int, Post] = {}
    before = None
    for _ in range(500):
        url = f"https://t.me/s/{channel}" + (f"?before={before}" if before else "")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            page = r.read().decode("utf-8", "replace")
        got = parse_page(page)
        if not got:
            break
        for p in got:
            posts[p.id] = p
        oldest = min(got, key=lambda p: p.id)
        log(f"  อ่านถึงโพสต์ {datetime.fromtimestamp(oldest.time, TH):%d/%m/%Y} ({len(posts)} โพสต์)")
        if oldest.time < cutoff or (before is not None and oldest.id >= before):
            break
        before = oldest.id
        time.sleep(pause)
    return sorted((p for p in posts.values() if p.time >= cutoff), key=lambda p: p.id)


# ---- understanding a post --------------------------------------------------

@dataclass
class ChannelSignal:
    post_id: int
    time: int
    symbol: str
    direction: str
    entry_lo: float
    entry_hi: float
    tps: list
    sl: float
    text: str = ""


NUM = r"(\d{2,6}(?:\.\d+)?)"


def normalize(text: str) -> str:
    # fancy bold letters (𝗚𝗢𝗟𝗗) -> plain ASCII, then upper case
    return unicodedata.normalize("NFKC", text).upper()


def parse_signal(post: Post) -> ChannelSignal | None:
    t = re.sub(r"(?<=\d),(?=\d{3})", "", normalize(post.text))
    sym = next((v for k, v in SYMBOLS.items() if re.search(rf"\b{k}\b", t)), None)
    m = re.search(rf"\b(BUY|SELL)\b(?:\s*(?:NOW|LIMIT|STOP))?\s*(?:@|AT|:)?\s*{NUM}(?:\s*[-–~/]\s*{NUM})?", t)
    sl = re.search(rf"\bSL\b\s*[:@=]?\s*{NUM}", t)
    # "TP 4122", "TP1 4122", "TP 2: 4130" (the small digit is the TP number)
    tps = [float(x) for x in re.findall(
        rf"\bTP(?:\s*\d(?=\s*[:@=.)]?\s+\d{{3}}|\s*[:@=.)]\s*\d{{3}}))?\s*[:@=.)]?\s*{NUM}", t)]
    if not (sym and m and sl and tps):
        return None
    direction = m.group(1).lower()
    a = float(m.group(2))
    b = float(m.group(3)) if m.group(3) else a
    lo, hi = min(a, b), max(a, b)
    slv = float(sl.group(1))
    tps = [x for x in tps if abs(x - lo) < lo * 0.2]
    if direction == "buy":
        tps = sorted(x for x in tps if x > hi)
        ok = slv < lo and tps
    else:
        tps = sorted((x for x in tps if x < lo), reverse=True)
        ok = slv > hi and tps
    if not ok:
        return None
    return ChannelSignal(post.id, post.time, sym, direction, lo, hi, tps[:3], slv, post.text)


# ---- replay on real prices -------------------------------------------------

@dataclass
class Outcome:
    sig: ChannelSignal
    status: str = "not filled"     # not filled / sl / tp1 / tp2 / tp3 / open
    entry: float | None = None
    entry_time: int | None = None
    exit_time: int | None = None
    tp_hit: int = 0                # how many TPs were reached before SL
    r_tp1: float = 0.0             # close all at TP1
    r_split: float = 0.0           # 1/3 at each TP, SL on the rest
    notes: list = field(default_factory=list)


def replay(sig: ChannelSignal, bars: list, spread: float, entry_wait_hours: float = 4) -> Outcome:
    out = Outcome(sig)
    buy = sig.direction == "buy"
    i = 0
    while i < len(bars) and bars[i].time < sig.time - 59:
        i += 1
    if i >= len(bars):
        out.status = "no data"
        return out
    # entry: at once if the price is already at or better than the range,
    # otherwise wait for it to come back to the range (limit order)
    deadline = sig.time + entry_wait_hours * 3600
    o = bars[i].open
    if (buy and sig.sl < o <= sig.entry_hi) or (not buy and sig.entry_lo <= o < sig.sl):
        out.entry, out.entry_time = o, bars[i].time
    else:
        level = sig.entry_hi if buy else sig.entry_lo
        for j in range(i, len(bars)):
            b = bars[j]
            if b.time > deadline:
                break
            if (b.low <= level) if buy else (b.high >= level):
                out.entry, out.entry_time, i = level, b.time, j
                break
            if (b.high >= sig.tps[0]) if buy else (b.low <= sig.tps[0]):
                break  # ran to the target without us
        if out.entry is None:
            return out
    risk = abs(out.entry - sig.sl)
    if risk <= 0:
        out.status = "bad levels"
        return out
    cost = spread / risk
    hit = 0
    status = "open"
    for b in bars[i:]:
        sl_hit = b.low <= sig.sl if buy else b.high >= sig.sl
        if sl_hit:
            status = "sl"
            out.exit_time = b.time
            break
        while hit < len(sig.tps) and (b.high >= sig.tps[hit] if buy else b.low <= sig.tps[hit]):
            hit += 1
        if hit == len(sig.tps):
            status = f"tp{hit}"
            out.exit_time = b.time
            break
    out.tp_hit = hit
    if status == "sl" and hit:
        status = f"tp{hit} then sl"
    elif status == "open" and hit:
        status = f"tp{hit} (open)"
    out.status = status
    rr = [abs(tp - out.entry) / risk for tp in sig.tps]
    out.r_tp1 = (rr[0] if hit >= 1 else (-1.0 if "sl" in status else 0.0)) - cost
    parts = len(sig.tps)
    out.r_split = sum(rr[k] if k < hit else (-1.0 if "sl" in status else 0.0)
                      for k in range(parts)) / parts - cost
    return out


def summarize(outs: list[Outcome]) -> list[str]:
    filled = [o for o in outs if o.entry is not None and o.status not in ("no data", "bad levels")]
    done = [o for o in filled if "open" not in o.status]
    lines = [f"ซิกทั้งหมดที่อ่านได้   {len(outs)}",
             f"ราคาไม่มาถึงจุดเข้า    {sum(o.status == 'not filled' for o in outs)}",
             f"เข้าได้และจบแล้ว       {len(done)}  (ยังวิ่งอยู่ {len(filled) - len(done)})"]
    if not done:
        return lines
    n = len(done)
    for k in (1, 2, 3):
        has = [o for o in done if len(o.sig.tps) >= k]
        if has:
            c = sum(o.tp_hit >= k for o in has)
            lines.append(f"ชน TP{k} ก่อน SL         {c}/{len(has)} ({c / len(has) * 100:.0f}%)")
    sl_first = sum(o.tp_hit == 0 and "sl" in o.status for o in done)
    lines.append(f"โดน SL ก่อนถึง TP1     {sl_first} ({sl_first / n * 100:.0f}%)")
    r1 = sum(o.r_tp1 for o in done)
    rs = sum(o.r_split for o in done)
    lines.append(f"ถ้าปิดทั้งหมดที่ TP1     {r1:+.1f}R  (เฉลี่ย {r1 / n:+.2f}R/ไม้)")
    lines.append(f"ถ้าแบ่งปิด TP1/2/3      {rs:+.1f}R  (เฉลี่ย {rs / n:+.2f}R/ไม้)")
    return lines


def main() -> None:
    from .app import CFG, ROOT, SOURCE

    ap = argparse.ArgumentParser()
    ap.add_argument("channel", help="channel name, e.g. tradeforex112233")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--wait", type=float, default=4, help="hours to wait for price to reach the entry")
    ap.add_argument("--hold-days", type=float, default=5, help="max days to follow a trade")
    args = ap.parse_args()

    print(f"กำลังอ่านช่อง @{args.channel} ย้อนหลัง {args.days} วัน ...", flush=True)
    posts = fetch_posts(args.channel, args.days)
    sigs = [s for s in (parse_signal(p) for p in posts) if s and s.symbol in CFG["symbols"]]
    print(f"พบ {len(posts)} โพสต์, เป็นซิกที่อ่านได้ {len(sigs)} อัน", flush=True)
    if SOURCE.name != "mt5":
        print("คำเตือน: ใช้ราคาจำลอง (sim) ผลไม่ได้สะท้อนตลาดจริง", flush=True)

    outs: list[Outcome] = []
    for n, s in enumerate(sigs, 1):
        end = min(s.time + int(args.hold_days * 86400), int(time.time()))
        bars = SOURCE.candles_range(s.symbol, "M1", s.time - 120, end)
        tick = SOURCE.tick(s.symbol) or {}
        spread = max(float(tick.get("ask", 0)) - float(tick.get("bid", 0)), 0.0)
        outs.append(replay(s, bars, spread, args.wait))
        if n % 20 == 0:
            print(f"  ตรวจแล้ว {n}/{len(sigs)}", flush=True)

    report = [f"=== @{args.channel}  ย้อนหลัง {args.days} วัน ==="]
    for sym in sorted({s.symbol for s in sigs}):
        report.append(f"\n[{sym}]")
        report += summarize([o for o in outs if o.sig.symbol == sym])
    report.append("\nหมายเหตุ: ตรวจได้เฉพาะโพสต์ที่ยังอยู่ในช่อง ถ้าห้องลบโพสต์ที่แพ้ ผลจริงจะแย่กว่านี้")
    text = "\n".join(report)
    print("\n" + text)
    (ROOT / "channel_report.txt").write_text(text + "\n", encoding="utf-8")
    with open(ROOT / "channel_trades.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["post_time_th", "symbol", "direction", "entry_range", "tps", "sl",
                    "entry", "status", "r_tp1", "r_split", "link"])
        for o in outs:
            s = o.sig
            w.writerow([datetime.fromtimestamp(s.time, TH).strftime("%Y-%m-%d %H:%M"), s.symbol,
                        s.direction, f"{s.entry_lo}-{s.entry_hi}", "/".join(f"{x:g}" for x in s.tps),
                        s.sl, o.entry, o.status, round(o.r_tp1, 2), round(o.r_split, 2),
                        f"https://t.me/{args.channel}/{s.post_id}"])
    print(f"\nรายละเอียดทุกซิก: {ROOT / 'channel_trades.csv'}")


if __name__ == "__main__":
    main()
