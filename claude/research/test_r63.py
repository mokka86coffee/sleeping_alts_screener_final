"""Проверка R63 (одна монета — одна позиция на обе книги) на собранных случаях; ничего не пишет в книги и на биржу. Печатает «R63: ок» или «СБОЙ …»."""
import sys, copy, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
import bingx_trader as bx
S = ft.FAST3_SIZE; FEE = ft.FEE
def mk(side, px, at=1000.0, **kw):
    d = dict(sym="XUSDT", side=side, px=px, t_ms=0, at=at, target=0.05, stop=0.1, stop_px=None, hold_min=120, rule="первая", last_px=px, bars=0); d.update(kw); return d
def run(first, second_side, second_px, x2=False):
    """первая позиция лежит в книге «всплеск/вынос», вторая только что открыта в «пробуждении»"""
    a = {"open": {"XUSDT": copy.deepcopy(first)}, "last_exit": {}}; b = {"open": {"XUSDT": mk(second_side, second_px, at=2000.0, rule="вторая", target=0.1)}, "last_exit": {}}
    if x2: a["x2"] = {"XUSDT": dict(px0=first["px"] * 0.99, at0=1.0, book0=ft.WAKE_BOOK)}
    ev = [dict(book=ft.WAKE_BOOK, sym="XUSDT", kind="entry", side=second_side, px=second_px, at=2000.0, usd_in=S, rule="вторая", target=0.1, stop=0.1, hold_min=120)]
    msgs = []; ft._OTHER.clear(); ft._OTHER[ft.WAKE_BOOK] = dict(state=a, book=ft.BOOK); ft._OTHER[ft.BOOK] = dict(state=b, book=ft.WAKE_BOOK)
    ft._one_position(b, ft.WAKE_BOOK, ev, msgs, 2000.0, False)
    return a, b, ev, msgs
try:
    # 1) та же сторона, цена ушла на 1 % → слияние: первая книга пуста, вторая ведёт позицию ×2 со своей целью
    a, b, ev, m = run(mk(1, 100.0), 1, 101.0)
    assert "XUSDT" not in a["open"] and b["open"]["XUSDT"]["size"] == 2.0 and b["open"]["XUSDT"]["target"] == 0.1 and b["x2"]["XUSDT"]["px0"] == 100.0, ("слияние", a, b)
    assert len(ev) == 1 and ev[0].get("x2") and ev[0]["size"] == 2.0, ev
    # выход удвоенной: вторая половина +5 % от 101, первая — от 100 до той же цены
    out = 101.0 * 1.05; x = dict(book=ft.WAKE_BOOK, sym="XUSDT", kind="exit_long", side=1, px_in=101.0, px_out=out, opened_at=2000.0, at=3000.0, result_pct=5.0, usd=S * .05, why_exit="цель", rule="вторая", size=1.0)
    del b["open"]["XUSDT"]; ft._x2_exits(b, [x])
    want = S * (0.05 + (out / 100.0 - 1))
    assert abs(x["usd"] - want) < 0.02 and x["size"] == 2.0 and "XUSDT" not in b.get("x2", {}), (x, want)
    # 2) та же сторона, цена ушла на 3 % → новый вход отменён, первая позиция на месте
    a, b, ev, m = run(mk(-1, 100.0), -1, 97.0)
    assert "XUSDT" in a["open"] and "XUSDT" not in b["open"] and not ev and "не добран" in m[0], ("дальше 2 %", a, b, ev, m)
    # 3) та же сторона, но первая уже ×2 → отмена
    a, b, ev, m = run(mk(1, 100.0), 1, 100.5, x2=True)
    assert "XUSDT" in a["open"] and "XUSDT" not in b["open"] and not ev and "уже ×2" in m[0], ("уже ×2", m)
    # 4) встречный сигнал → первая закрыта по цене нового входа, новая остаётся
    a, b, ev, m = run(mk(1, 100.0), -1, 98.0)
    assert "XUSDT" not in a["open"] and "XUSDT" in b["open"] and len(ev) == 1 and a["last_exit"]["XUSDT"] == 2000.0 and "встречным" in m[0], ("встречный", a, b, m)
    # 5) зеркало: вход с пометкой x2 идёт в добор, обычный — в открытие, выход — в закрытие
    calls = []
    bx.cfg = lambda: {"enabled": True}; bx.sync_stops = lambda c: []; bx.jlog = lambda *a_, **k_: None
    bx.state = lambda: {"open": {"XUSDT": {"side": 1}}}
    bx.add_position = lambda sym, side, px, c=None, size_usd=None: (calls.append(("add", sym)), {"ok": True})[1]
    bx.open_position = lambda sym, side, px, why="", c=None, size_usd=None: (calls.append(("open", sym)), {"ok": True})[1]
    bx.close_position = lambda sym, exit_px=None, why="", c=None: (calls.append(("close", sym)), {"ok": True})[1]
    import os; _mt = os.path.getmtime; os.path.getmtime = lambda p: 0   # заморозка после правки (R51) в этой проверке не участвует
    try:
        out_ = bx.on_events([dict(kind="entry", sym="XUSDT", side=1, px=1.0, x2=True), dict(kind="entry", sym="YUSDT", side=1, px=1.0), dict(kind="exit_long", sym="XUSDT", side=1, px_out=1.0)])
    finally:
        os.path.getmtime = _mt
    assert calls == [("add", "XUSDT"), ("open", "YUSDT"), ("close", "XUSDT")], (calls, out_)
    print("R63: ок — слияние ×2, отмена дальше 2 %, отмена при ×2, встречный сигнал, зеркало BingX")
except Exception as e:  # noqa: BLE001
    print("СБОЙ R63", type(e).__name__, e); traceback.print_exc()
