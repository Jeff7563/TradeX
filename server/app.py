"""Local web server: serves the chart page and streams candles + SMC markings.

Run:  python -m uvicorn server.app:app --port 8000
Open: http://localhost:8000
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .datasource import TF_SECONDS, make_source
from .smc import analyse

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    path = Path(os.environ.get("TRADEX_CONFIG", ROOT / "config.json"))
    if not path.exists():
        path = ROOT / "config.example.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    if os.environ.get("TRADEX_SOURCE"):
        cfg["source"] = os.environ["TRADEX_SOURCE"]
    return cfg


CFG = load_config()
SOURCE = make_source(CFG)
app = FastAPI(title="TradeX")


def snapshot(symbol: str, tf: str, count: int) -> dict:
    if symbol not in CFG["symbols"]:
        raise HTTPException(404, f"unknown symbol {symbol}")
    if tf not in TF_SECONDS:
        raise HTTPException(400, f"unknown timeframe {tf}")
    candles = SOURCE.candles(symbol, tf, count)
    return {"symbol": symbol, "tf": tf, "source": SOURCE.name,
            "candles": [c.to_dict() for c in candles],
            "smc": analyse(candles, tf),
            "tick": SOURCE.tick(symbol)}


@app.get("/api/config")
def config():
    return {"symbols": list(CFG["symbols"]), "timeframes": CFG["timeframes"],
            "source": SOURCE.name,
            "timezone_offset_hours": CFG.get("timezone_offset_hours", 7)}


@app.get("/api/chart")
def chart(symbol: str, tf: str, count: int | None = None):
    return snapshot(symbol, tf, min(count or CFG.get("candles", 500), 5000))


@app.websocket("/ws")
async def ws(sock: WebSocket, symbol: str, tf: str):
    await sock.accept()
    count = CFG.get("candles", 500)
    try:
        while True:
            data = await asyncio.to_thread(snapshot, symbol, tf, count)
            await sock.send_json(data)
            await asyncio.sleep(1)
    except (WebSocketDisconnect, RuntimeError):
        pass


app.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")


@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")
