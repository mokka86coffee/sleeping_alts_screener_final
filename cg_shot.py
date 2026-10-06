#!/usr/bin/env python3
"""СКРИН COINGLASS В ТЕЛЕГРАМ НА ВХОДЕ И ВЫХОДЕ БЫСТРЫХ СДЕЛОК (27.09, владелец: «для быстрых сделок на открытии и на закрытии присылай
такой скрин с коингласс в телеграм и с этими же индикаторами — только не Bybit, а Binance»: coinglass.com/tv/Binance_<монета>).

Шесть индикаторов Coinglass показывает сам (объём SMA 9, CVD фьючерсов и спота, фандинг, интерес, дельта заявок); ликвидации, базис и
соотношение заявок в профиле не сохранились (владелец 27.09) — _indicators() добавляет их на каждом снимке. Профиль output/cg_profile:
    .venv/bin/python cg_shot.py --setup            # окно с графиком: войти в Coinglass / добавить индикаторы, 3 мин, закрыть окно
Дальше без окна:
    .venv/bin/python cg_shot.py PENGUUSDT --caption "текст"     # снимок и фото в телеграм
    .venv/bin/python cg_shot.py PENGUUSDT --no-send             # только снимок → output/cg_shots/
    ... --entry 0.0101 --target 0.0106 --stop 0.0096 [--exit 0.0104] --t-in <сек> [--t-out <сек>]   # линии сделки на графике
fast_tier зовёт его отдельным процессом (не ждёт). Один снимок за раз — замок output/cg_shots/.lock.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import sys
import time
from core_time import msg_hm   # 06.10: подписи — в поясе владельца, не машины
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
VIEW = {"width": 1600, "height": 1600}   # 7 панелей индикаторов под графиком
WAIT_S = 16            # графику и панелям индикаторов нужно время дорисоваться


ADD = ("Aggregated Liquidations", "Basis")
DROP = ("Bid & Ask Delta", "Bid & Ask Ratio")      # 27.09 22:00 владелец: «убери со скринов bid and ask ratio и delta»   # в профиле не сохраняются (владелец 27.09) — добавляем на каждом снимке


def _indicators(pg) -> None:
    """к шести индикаторам Coinglass по умолчанию — ликвидации, базис, соотношение заявок (меню «CoinGlass - Indicators»)"""
    for n in ADD:
        try:
            m = pg.get_by_text(n, exact=True)
            if not m.count() or not m.first.is_visible():
                pg.get_by_text("CoinGlass - Indicators", exact=True).first.click()
                pg.wait_for_timeout(1500)
            pg.get_by_text(n, exact=True).first.click()
            pg.wait_for_timeout(1200)
        except Exception as e:  # noqa: BLE001
            print(f"cg_shot: индикатор «{n}» не добавлен: {type(e).__name__}")
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(800)


def _drop(pg) -> None:
    """снять индикаторы DROP (дельта заявок стоит у Coinglass по умолчанию) — через API графика во фрейме"""
    fr = next((f for f in pg.frames if f != pg.main_frame), None)
    if not fr:
        return
    try:
        fr.evaluate("""(D) => { const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();
          for (const s of c.getAllStudies()) if (D.some(d => String(s.name).indexOf(d) >= 0)) c.removeEntity(s.id); }""", list(DROP))
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: индикаторы не сняты: {type(e).__name__}")


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


def _draw(pg, lines: dict) -> None:
    """линии сделки на графике (API графика TradingView внутри Coinglass, tradingViewApi во фрейме): вход, цель, стоп, выход — горизонтали
    с подписью; время входа/выхода — вертикали. 27.09 владелец: «нет целей»."""
    if not lines:
        return
    fr = next((f for f in pg.frames if f != pg.main_frame), None)
    if not fr:
        print("cg_shot: фрейм графика не найден — без линий")
        return
    js = """(L) => { const a = window.tradingViewApi; if (!a) return 'нет api';
      const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart(); const now = Math.floor(Date.now() / 1000);
      const h = (price, color, txt) => c.createShape({time: now, price: price}, {shape: 'horizontal_line', lock: true, disableSelection: true,
          text: txt, overrides: {linecolor: color, linewidth: 2, showLabel: true, textcolor: color, horzLabelsAlign: 'left', fontsize: 14}});
      const v = (t, color) => c.createShape({time: t}, {shape: 'vertical_line', lock: true, disableSelection: true,
          overrides: {linecolor: color, linewidth: 1, linestyle: 2}});
      for (const x of L.h) h(x[0], x[1], x[2]);
      try {                                              // шкала цены — чтобы все линии были в кадре
        const ps = c.getPanes()[0].getMainSourcePriceScale(); const r = ps.getVisiblePriceRange();
        const P = L.h.map(x => x[0]); const lo = Math.min(r.from, ...P), hi = Math.max(r.to, ...P), pad = (hi - lo) * 0.10;
        if (lo < r.from || hi > r.to) ps.setVisiblePriceRange({from: lo - pad, to: hi + pad});
      } catch (e) { }
      for (const x of L.v) v(x[0], x[1]);
      return 'ok'; }"""
    try:
        r = fr.evaluate(js, lines)
        if r != "ok":
            print(f"cg_shot: линии не нарисованы: {r}")
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: линии не нарисованы: {type(e).__name__}")


def _lines(a) -> dict:
    """из аргументов — горизонтали (цена, цвет, подпись) и вертикали (время, цвет)"""
    def fmt(v):
        return f"{v:.6g}"
    h, v = [], []
    if a.entry:
        h.append([a.entry, "#f5a623", f"вход {fmt(a.entry)}"])
    if a.target:
        h.append([a.target, "#26a69a", f"цель {fmt(a.target)}"])
    if a.stop:
        h.append([a.stop, "#ef5350", f"стоп {fmt(a.stop)}"])
    if a.exit:
        h.append([a.exit, "#e0e0e0", f"выход {fmt(a.exit)}"])
    if a.t_in:
        v.append([int(a.t_in), "#f5a623"])
    if a.t_out:
        v.append([int(a.t_out), "#e0e0e0"])
    return {"h": h, "v": v} if (h or v) else {}


PRICE_VIEW = {"width": 1600, "height": 1000}


def _price_only(pg, lines: dict) -> None:
    """второй скрин на входе (27.09 владелец: «только график и линии цель, вход, стоп»): снять все индикаторы — цена на всю высоту,
    шкала заново под линии сделки"""
    fr = next((f for f in pg.frames if f != pg.main_frame), None)
    if not fr:
        return
    js_rm = """() => { const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();
      const s = c.getAllStudies(); if (s.length) c.removeEntity(s[0].id); return c.getAllStudies().length; }"""
    for _ in range(15):
        try:
            if not fr.evaluate(js_rm):
                break
        except Exception:  # noqa: BLE001
            break
        pg.wait_for_timeout(400)
    pg.set_viewport_size(PRICE_VIEW)
    pg.wait_for_timeout(1500)
    if lines and lines.get("h"):
        try:
            fr.evaluate("""(P) => { const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();
              const ps = c.getPanes()[0].getMainSourcePriceScale(); const r = ps.getVisiblePriceRange();
              const lo = Math.min(r.from, ...P), hi = Math.max(r.to, ...P), pad = (hi - lo) * 0.10; ps.setVisiblePriceRange({from: lo - pad, to: hi + pad}); }""",
                        [x[0] for x in lines["h"]])
        except Exception:  # noqa: BLE001
            pass
    pg.wait_for_timeout(1500)


def shot(sym: str, lines: dict | None = None, price: bool = False) -> list[Path]:
    from playwright.sync_api import sync_playwright
    SHOTS.mkdir(parents=True, exist_ok=True)
    out = SHOTS / f"{sym}_{time.strftime('%Y%m%d_%H%M%S', time.gmtime())}.png"
    with open(SHOTS / ".lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)                     # профиль Chromium не открыть двумя процессами сразу
        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(str(PROFILE), headless=True, viewport=VIEW)
            try:
                pg = ctx.pages[0] if ctx.pages else ctx.new_page()
                pg.goto(URL.format(sym=sym), wait_until="domcontentloaded", timeout=60_000)
                pg.wait_for_timeout(8000)
                _indicators(pg)
                _drop(pg)
                _interval(pg, "3m")
                pg.wait_for_timeout(2000)
                _draw(pg, lines or {})
                pg.wait_for_timeout(WAIT_S * 1000 - 8000 if WAIT_S > 8 else 3000)
                box = (pg.query_selector("iframe") or pg).bounding_box() if pg.query_selector("iframe") else None
                clip = {"x": 0, "y": 0, "width": box["x"] + box["width"], "height": VIEW["height"]} if box else None
                pg.mouse.move(VIEW["width"] - 5, VIEW["height"] - 5)   # убрать перекрестие с графика
                pg.wait_for_timeout(500)
                pg.screenshot(path=str(out), clip=clip)          # без правой панели рынков
                outs = [out]
                if price:
                    out2 = out.with_name(out.stem + "_price.png")
                    _price_only(pg, lines or {})
                    pg.mouse.move(PRICE_VIEW["width"] - 5, PRICE_VIEW["height"] - 5)
                    pg.screenshot(path=str(out2), clip={"x": 0, "y": 0, "width": clip["width"], "height": PRICE_VIEW["height"]} if clip else None)
                    outs.append(out2)
            finally:
                ctx.close()
    return [x for x in outs if x.exists()]


QUEUE = BASE_DIR / "output" / "tg_queue.jsonl"   # 28.09: что не ушло в телеграм — досылаем при следующей отправке


def _queue_add(item: dict) -> None:
    with open(QUEUE, "a", encoding="utf-8") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(item, ensure_ascii=False) + "\n")


def flush_queue(cfg: dict) -> None:
    """28.09 (владелец: «в тг последняя сделка в 10 утра» — телеграм с этого компа не отвечал с ~11:40 до ~21:00, сделки терялись):
    досылаем очередь по порядку; первая неудача — связи нет, остальное ждёт следующего раза; старше суток — выбрасываем"""
    from send_brief_telegram import _send_to
    if not QUEUE.exists():
        return
    with open(QUEUE, "r+", encoding="utf-8") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            return                                                    # другой cg_shot уже досылает
        items = [json.loads(ln) for ln in f if ln.strip()]
        keep, down = [], False
        for it in items:
            if time.time() - it["at"] > 86400:
                continue
            if down:
                keep.append(it); continue
            cap = f"⏳ не ушло в {msg_hm(it['at'])}\n" + it["caption"]
            if it["kind"] == "text":
                ok = _send_to(cap, cfg, it["chat"])
            else:
                paths = [Path(x) for x in it["paths"] if Path(x).exists()]
                if not paths:
                    continue
                ok = _photo_to(paths[0], cap, cfg, it["chat"]) if len(paths) == 1 else _album_to(paths, cap, cfg, it["chat"])
            if not ok:
                keep.append(it); down = True
        f.seek(0); f.truncate()
        f.writelines(json.dumps(x, ensure_ascii=False) + "\n" for x in keep)


def send_photo(path, caption: str) -> bool:
    """в основной чат и всем подписчикам; два снимка — одним альбомом (подпись у первого). True — ушло в основной"""
    from send_brief_telegram import load_config, chat_ids
    cfg = load_config()
    if not cfg:
        return False
    paths = path if isinstance(path, list) else [path]
    oks = []
    for c in chat_ids(cfg):
        ok = _photo_to(paths[0], caption, cfg, c) if len(paths) == 1 else _album_to(paths, caption, cfg, c)
        if not ok:
            _queue_add(dict(kind="photo", chat=c, caption=caption, paths=[str(x) for x in paths], at=time.time()))
        oks.append(ok)
    return oks[0]


def send_text(caption: str) -> None:
    """текст сделки — сразу, до снимка (снимок ~20 с и тяжёлый; при медленном телеграме текст доходит, фото — нет)"""
    from send_brief_telegram import load_config, chat_ids, _send_to
    cfg = load_config()
    if not cfg:
        return
    flush_queue(cfg)
    for c in chat_ids(cfg):
        if not _send_to(caption, cfg, c):
            _queue_add(dict(kind="text", chat=c, caption=caption, at=time.time()))


def _album_to(paths: list, caption: str, cfg: dict, chat) -> bool:
    b = uuid.uuid4().hex
    media = [{"type": "photo", "media": f"attach://p{i}", **({"caption": caption[:1000]} if i == 0 else {})} for i in range(len(paths))]
    body = b""
    for k, v in (("chat_id", str(chat)), ("media", json.dumps(media, ensure_ascii=False))):
        body += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
    for i, pth in enumerate(paths):
        body += f'--{b}\r\nContent-Disposition: form-data; name="p{i}"; filename="{pth.name}"\r\nContent-Type: image/png\r\n\r\n'.encode() + pth.read_bytes() + b"\r\n"
    body += f"--{b}--\r\n".encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{cfg['bot_token']}/sendMediaGroup", data=body,
                                 headers={"Content-Type": f"multipart/form-data; boundary={b}"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return bool(json.loads(r.read().decode("utf-8")).get("ok"))
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: телеграм не принял альбом: {type(e).__name__}: {e}")
        return False


def _photo_to(path: Path, caption: str, cfg: dict, chat) -> bool:
    b = uuid.uuid4().hex
    parts = []
    for k, v in (("chat_id", str(chat)), ("caption", caption[:1000])):
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
    for k in ("entry", "target", "stop", "exit"):
        ap.add_argument(f"--{k}", type=float, default=None)          # цены линий сделки
    ap.add_argument("--t-in", type=float, default=None)                # время входа, сек (вертикаль)
    ap.add_argument("--t-out", type=float, default=None)               # время выхода, сек
    ap.add_argument("--price", action="store_true")                     # второй снимок: только цена и линии (на входе)
    a = ap.parse_args()
    if a.setup:
        return setup()
    if not a.sym:
        ap.error("нужна монета, например PENGUUSDT")
    sym = a.sym.upper() if a.sym.upper().endswith("USDT") else a.sym.upper() + "USDT"
    if not a.no_send and a.caption:
        send_text(a.caption)
    try:
        path = shot(sym, _lines(a), a.price)
    except Exception as e:  # noqa: BLE001
        print(f"cg_shot: снимок {sym} не вышел: {type(e).__name__}: {e}")
        return 1
    if not path:
        print(f"cg_shot: снимок {sym} не вышел")
        return 1
    print(f"cg_shot: {', '.join(str(x) for x in path)}")
    if not a.no_send and not send_photo(path, f"{sym[:-4]} · Coinglass" if a.caption else sym):
        return 1
    # 28.09 владелец «поднимай»: храним CG_SHOTS_KEEP последних; удаляем самые старые по времени файла (было — по алфавиту имени,
    # стирались свежие снимки монет на 0–A, а старые на P–Z оставались)
    try:
        from core_config import CG_SHOTS_KEEP as keep
    except ImportError:
        keep = 2000
    for old in sorted(SHOTS.glob("*.png"), key=lambda f: f.stat().st_mtime)[:-keep]:
        old.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
