#!/usr/bin/env python3
"""СКРИН COINGLASS В ТЕЛЕГРАМ НА ВХОДЕ И ВЫХОДЕ БЫСТРЫХ СДЕЛОК (27.09, владелец: «для быстрых сделок на открытии и на закрытии присылай
такой скрин с коингласс в телеграм и с этими же индикаторами — только не Bybit, а Binance»: coinglass.com/tv/Binance_<монета>).

Индикаторы (объём SMA 9, ликвидации, CVD фьючерсов и спота, фандинг, интерес, дельта заявок, базис, соотношение заявок) Coinglass хранит
в браузере/аккаунте — поэтому свой профиль Chromium output/cg_profile. Один раз:
    .venv/bin/python cg_shot.py --setup            # окно с графиком: войти в Coinglass / добавить индикаторы, 3 мин, закрыть окно
Дальше без окна:
    .venv/bin/python cg_shot.py PENGUUSDT --caption "текст"     # снимок и фото в телеграм
    .venv/bin/python cg_shot.py PENGUUSDT --no-send             # только снимок → output/cg_shots/
fast_tier зовёт его отдельным процессом (не ждёт). Один снимок за раз — замок output/cg_shots/.lock.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
import urllib.request
import uuid
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

PROFILE = BASE_DIR / "output" / "cg_profile"
SHOTS = BASE_DIR / "output" / "cg_shots"
URL = "https://www.coinglass.com/tv/Binance_{sym}"
VIEW = {"width": 1600, "height": 1500}
WAIT_S = 12            # графику и панелям индикаторов нужно время дорисоваться


def _interval(pg, iv: str) -> None:
    """таймфрейм — через меню у кнопки «1D» в верхней строке Coinglass (3m в быстрых кнопках нет)"""
    try:
        d = pg.get_by_text("1D", exact=True).first.bounding_box()
        pg.mouse.click(d["x"] + d["width"] + 14, d["y"] + d["height"] / 2)
        pg.wait_for_timeout(1200)
        pg.get_by_text(iv, exact=True).first.click()
        pg.wait_for_timeout(1500)
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: таймфрейм {iv} не выставлен: {type(e).__name__}")


def shot(sym: str) -> Path | None:
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / f"{sym}_{time.strftime('%Y%m%d_%H%M%S')}.png"
    with open(SHOTS / ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)                     # профиль Chromium не открыть двумя процессами сразу
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=True, viewport=VIEW)
            try:
                pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                pg.goto(URL.format(sym=sym), wait_until="domcontentloaded", timeout=60_000)
                pg.wait_for_timeout(8000)
                _interval(pg, "3m")
                pg.wait_for_timeout(WAIT_S * 1000 - 8000 if WAIT_S > 8 else 3000)
                box = (pg.query_selector("iframe") or pg).bounding_box() if pg.query_selector("iframe") else None
                clip = {"x": 0, "y": 0, "width": box["x"] + box["width"], "height": VIEW["height"]} if box else None
                pg.mouse.move(VIEW["width"] - 5, VIEW["height"] - 5)   # убрать перекрестие с графика
                pg.wait_for_timeout(500)
                pg.screenshot(path=str(out), clip=clip)          # без правой панели рынков
            finally:
                ctx.close()
    return out if out.exists() else None


def send_photo(path: Path, caption: str) -> bool:
    from send_brief_telegram import load_config
    cfg = load_config()
    if not cfg:
        return False
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(cfg["chat_id"])), ("caption", caption[:1000])):
        parts.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    parts.append(f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="{path.name}"\r\nContent-Type: image/png\r\n\r\n'.encode())
    body = b"".join(parts) + path.read_bytes() + f"\r\n--{b}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['bot_token']}/sendPhoto", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: телеграм не принял фото: {type(e).__name__}: {e}")
        return False


def setup() -> int:
    from playwright.sync_api import sync_playwright
    PROFILE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=False, viewport=VIEW)
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(URL.format(sym="PENGUUSDT"), wait_until="domcontentloaded", timeout=60_000)
        print("cg_shot: окно открыто — войдите в Coinglass или добавьте индикаторы, потом закройте окно")
        try:
            pg.wait_for_event("close", timeout=0)
        except Exception:  # noqa: BLE001
            pass
        ctx.close()
    print("cg_shot: профиль сохранён в output/cg_profile")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sym", nargs="?")
    ap.add_argument("--caption", default="")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--setup", action="store_true")
    a = ap.parse_args()
    if a.setup:
        return setup()
    if not a.sym:
        ap.error("нужна монета, например PENGUUSDT")
    sym = a.sym.upper() if a.sym.upper().endswith("USDT") else a.sym.upper() + "USDT"
    try:
        path = shot(sym)
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: снимок {sym} не вышел: {type(e).__name__}: {e}")
        return 1
    if not path:
        print(f"cg_shot: снимок {sym} не вышел")
        return 1
    print(f"cg_shot: {path}")
    if not a.no_send and not send_photo(path, a.caption or sym):
        return 1
    for old in sorted(SHOTS.glob("*.png"))[:-200]:          # храним последние 200
        old.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
