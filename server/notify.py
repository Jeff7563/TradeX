"""Send signals out: LINE (Messaging API push) and the console."""
from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timedelta, timezone

from .signals import Signal

LINE_PUSH = "https://api.line.me/v2/bot/message/push"
TH = timezone(timedelta(hours=7))


def format_signal(s: Signal, tf: str = "M15") -> str:
    arrow = "🟢 BUY" if s.direction == "buy" else "🔴 SELL"
    t = datetime.fromtimestamp(s.time, TH).strftime("%d/%m %H:%M")
    lines = [
        f"{arrow} {s.symbol} ({tf})  {t} น.",
        f"Entry  {s.entry}",
        f"SL     {s.sl}",
        f"TP     {s.tp}   (RR 1:{s.rr})",
        "",
        "เหตุผล:",
        *[f"• {r}" for r in s.reasons],
        "",
        "สัญญาณอัตโนมัติจากกฎ ICT/SMC v1 ใช้ประกอบการตัดสินใจเท่านั้น",
    ]
    return "\n".join(lines)


def send_line(text: str, token: str, to: str, timeout: float = 10) -> None:
    body = json.dumps({"to": to, "messages": [{"type": "text", "text": text[:5000]}]}).encode()
    req = urllib.request.Request(LINE_PUSH, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if r.status != 200:
            raise RuntimeError(f"LINE push failed: HTTP {r.status}")


class Notifier:
    def __init__(self, cfg: dict):
        line = cfg.get("line", {})
        self.token = line.get("channel_access_token", "")
        self.to = line.get("user_id", "")

    @property
    def line_ready(self) -> bool:
        return bool(self.token and self.to)

    def send(self, text: str) -> None:
        print(text, flush=True)
        print("-" * 40, flush=True)
        if self.line_ready:
            try:
                send_line(text, self.token, self.to)
            except Exception as e:  # keep scanning even if LINE is down
                print(f"[LINE] ส่งไม่สำเร็จ: {e}", flush=True)
