#!/usr/bin/env python3
"""СЕРВЕР ЖИВОЙ СТРАНИЦЫ БЫСТРОГО БОТА (27.09, владелец: «отдельный сайт, обновление по сокету, сервер на моём компе, только из дома —
надёжнее и безопаснее; в гит только сам сайт, без данных»).

http://<мак>:8765/            — страница fast_site/index.html
http://<мак>:8765/state.json  — данные output/fast_state.json (запасной путь, если сокета нет)
ws://<мак>:8765/ws            — сокет: при подключении — текущие данные, дальше — каждый раз, как fast_tier перепишет файл (раз в 3 мин)
Слушает домашнюю сеть (0.0.0.0) — мак и планшет в той же Wi-Fi; снаружи роутер не пускает. Порт занят — второй не стартует.
fast_tier поднимает его сам, если не жив (FAST_SERVER_PORT в core_config). Лог output/fast_server.log.

    .venv/bin/python fast_server.py
"""
from __future__ import annotations

import asyncio
import http
import json
import socket
import sys
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import FAST_SERVER_PORT as PORT
except ImportError:
    PORT = 8765

from websockets.asyncio.server import serve, broadcast  # noqa: E402
from websockets.datastructures import Headers  # noqa: E402
from websockets.http11 import Response  # noqa: E402

SITE = BASE_DIR / "fast_site" / "index.html"
STATE = BASE_DIR / "output" / "fast_state.json"
CLIENTS: set = set()


def _resp(code: int, body: bytes, ctype: str) -> Response:
    h = Headers([("Content-Type", ctype), ("Content-Length", str(len(body))), ("Cache-Control", "no-store")])
    return Response(code, http.HTTPStatus(code).phrase, h, body)


def process_request(connection, request):
    path = request.path.split("?")[0]
    if path == "/ws":
        return None                                          # сокет — дальше обычное рукопожатие
    if path in ("/", "/index.html"):
        try:
            return _resp(200, SITE.read_bytes(), "text/html; charset=utf-8")
        except OSError:
            return _resp(404, b"no page", "text/plain")
    if path == "/state.json":
        try:
            return _resp(200, STATE.read_bytes(), "application/json; charset=utf-8")
        except OSError:
            return _resp(404, b"{}", "application/json")
    if path == "/coin.html":                                 # 09.10 владелец: из панели звезды/очереди имя монеты ведёт в карточку coin.html#ТИКЕР
        try:
            return _resp(200, (BASE_DIR / "coin.html").read_bytes(), "text/html; charset=utf-8")
        except OSError:
            return _resp(404, b"no coin page", "text/plain")
    return _resp(404, b"not found", "text/plain")


async def handler(ws):
    CLIENTS.add(ws)
    try:
        try:
            await ws.send(STATE.read_text(encoding="utf-8"))
        except OSError:
            pass
        async for _ in ws:                                   # страница ничего не шлёт — просто держим связь
            pass
    finally:
        CLIENTS.discard(ws)


async def watch():
    last = None
    while True:
        try:
            m = STATE.stat().st_mtime
            if m != last:
                if last is not None and CLIENTS:
                    data = STATE.read_text(encoding="utf-8")
                    json.loads(data)                         # недописанный файл не шлём (fast_state пишет через .tmp → replace)
                    broadcast(CLIENTS, data)
                last = m
        except (OSError, ValueError):
            pass
        await asyncio.sleep(2)


async def main():
    async with serve(handler, "0.0.0.0", PORT, process_request=process_request, max_size=None, ping_interval=20):
        ip = "?"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); ip = s.getsockname()[0]; s.close()
        except OSError:
            pass
        print(f"fast_server: http://localhost:{PORT}/ · в домашней сети http://{ip}:{PORT}/", flush=True)
        await watch()


if __name__ == "__main__":
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", PORT))
    except OSError:
        print(f"fast_server: порт {PORT} занят — сервер уже работает", flush=True)
        raise SystemExit(0)
    finally:
        s.close()
    asyncio.run(main())
