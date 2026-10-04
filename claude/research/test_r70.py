"""Проверка R70 (флэт по суткам → шорт не берём, лонг лимиткой от линии флэта: цель — верх флэта, стоп 10 %); в книги и на биржу ничего не пишет."""
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
try:
    hb = lambda lo, hi, n: [[i, 0, hi, lo, 0] for i in range(n)]
    ft._H1["FLATUSDT"] = (time.time(), hb(0.90, 1.20, 24) + hb(1.00, 1.10, 24))        # последние сутки 1.00–1.10 внутри предыдущих 0.90–1.20
    ft._H1["TRENDUSDT"] = (time.time(), hb(0.90, 1.00, 24) + hb(0.95, 1.10, 24))       # максимум выше прежнего — не флэт
    assert ft._flat24("FLATUSDT") == (True, 1.00, 1.10) and ft._flat24("TRENDUSDT")[0] is False and ft._flat24("NODATA")[0] is False
    ft._ladder = lambda s, px: None; ft._LAD.clear()
    assert ft._flat5("FLATUSDT", 1.05)[0] is True and "сутки" in ft._flat_txt("FLATUSDT", ft._flat5("FLATUSDT", 1.05)) and ft._flat5("TRENDUSDT", 1.05)[0] is False
    now = time.time(); ft._own_mm = lambda: set(); ft._too_young = lambda s: None; ft._slide = lambda s: (False, False, 0.0)
    _lw = ft._long_window_closed; ft._long_window_closed = lambda n: None
    st = {"open": {}, "last_exit": {}}; m = []
    ft._flat_long_set(st, "FLATUSDT", now, m, "всплеск")
    q = st["flat_wait"]["FLATUSDT"]; assert q["level"] == 1.00 and q["top"] == 1.10 and "R70" in m[0], (st, m)
    st2 = {"open": {}, "last_exit": {}}; ft._flat_long_set(st2, "TRENDUSDT", now, [], "всплеск"); assert not st2.get("flat_wait")
    ft._long_window_closed = lambda n: "окно"; st3 = {"open": {}, "last_exit": {}}; ft._flat_long_set(st3, "FLATUSDT", now, [], "всплеск"); assert not st3.get("flat_wait")
    ft._long_window_closed = lambda n: None
    # цена ещё не пришла к линии → ждём; пришла → лонг по линии, цель на верх флэта, стоп 10 %
    t0 = int(now * 1000) // 180_000 * 180_000 - 5 * 180_000; q["chk"] = t0
    bars = [[t0 + i * 180_000, 1.05, 1.06, 1.02, 1.04, 0, 0, 0] for i in range(3)]
    ft.get_json = lambda url, params=None, **kw: [list(map(str, b)) for b in bars]
    ft.ses_gate = lambda n, t, side=1: (True, "проверка", None); ft._rate_ok = lambda n, note=False: None; ft.fon = lambda: {}; ft._bub = lambda s: None
    ev = []; m = []; ft.flat_wait_step(st, ft.BOOK, now, ev, m, False)
    assert "FLATUSDT" in st["flat_wait"] and not st["open"] and not ev, (st, m)
    bars.append([t0 + 3 * 180_000, 1.02, 1.03, 0.995, 1.01, 0, 0, 0])
    ev = []; m = []; ft.flat_wait_step(st, ft.BOOK, now, ev, m, False)
    p = st["open"].get("FLATUSDT")
    assert p and p["side"] == 1 and p["px"] == 1.00 and abs(p["target"] - 0.10) < 1e-6 and p["stop"] == 0.1 and p.get("flush") and p.get("flat_long") and "FLATUSDT" not in st["flat_wait"] and len(ev) == 1, (p, m)
    assert ft.flush_long_walk(1.0, dict(p), [[0, 1.0, 1.101, 0.99, 1.1]]) == (p["target"], "цель") and ft.flush_long_walk(1.0, dict(p), [[0, 1.0, 1.01, 0.89, 0.9]])[1] == "стоп"
    # в окне без лонгов ожидание снимается
    st["open"].clear(); st["flat_wait"]["FLATUSDT"] = dict(q, until=now + 3600); ft._long_window_closed = lambda n: "окно"
    m = []; ft.flat_wait_step(st, ft.BOOK, now, [], m, False); assert "FLATUSDT" not in st["flat_wait"]
    ft._long_window_closed = _lw
    print("R70: ок — флэт по суткам, ожидание лонга на линии флэта, вход по линии, цель на верх флэта, стоп 10 %, окно без лонгов снимает ожидание")
except Exception as ex:  # noqa: BLE001
    print("СБОЙ R70", type(ex).__name__, ex); traceback.print_exc()
