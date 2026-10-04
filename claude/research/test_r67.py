"""Проверка R67 (во флэте шорт не берём): мерка флэта и отказ в ждущем шорте и у сползающей монеты; в книги и на биржу ничего не пишет."""
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
try:
    bars = lambda lo, hi: [[i, 0, hi, lo, 0] for i in range(30)]
    ft._ladder = lambda s, px: None
    ft._LAD["FLATUSDT"] = (time.time(), bars(1.0, 1.10)); ft._LAD["WIDEUSDT"] = (time.time(), bars(1.0, 1.40))
    assert ft._flat5("FLATUSDT", 1.0)[0] is True and ft._flat5("WIDEUSDT", 1.0)[0] is False and ft._flat5("NODATAUSDT", 1.0) == (False, 0.0)
    now = time.time(); t_bar = int(now * 1000) // 180_000 * 180_000 - 180_000
    ft._own_mm = lambda: set(); ft.ses_gate = lambda n, t, side=1: (True, "проверка", 600); ft._slide = lambda s: (True, False, -9.0)
    st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "FLATUSDT", "всплеск", t_bar, now, m) is True and not st.get("pending") and "R67" in m[0], (st, m)          # сползает + флэт → ни лонга, ни шорта
    st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "WIDEUSDT", "всплеск", t_bar, now, m) is True and st["pending"]["WIDEUSDT"].get("slide"), (st, m)            # сползает, не флэт → шорт на отскоке
    # ждущий шорт во флэте не входит
    t0 = t_bar - 6 * 180_000
    kb = [[t0 + i * 180_000, 1.00 + i * 0.01, 1.012 + i * 0.01, 0.999 + i * 0.01, 1.01 + i * 0.01, 0, 0, 0] for i in range(5)] + [[t0 + 5 * 180_000, 1.045, 1.047, 1.03, 1.035, 0, 0, 0]]
    ft.get_json = lambda url, params=None, **kw: [list(map(str, b)) for b in kb] if "klines" in url else []
    ft._liq_hourly = lambda: {}; ft._no_short = lambda s, px: None; ft._too_young = lambda s: None
    st = {"open": {}, "last_exit": {}, "pending": {"FLATUSDT": dict(why="А2: … → сторона перевёрнута · всплеск", t_ms=t0, at=now, expire=now + 3600, start_low=None)}}
    ev = []; m = []
    ft.pending_step(st, ft.BOOK, now, ev, m, False)
    assert not st["open"] and "FLATUSDT" not in st["pending"] and not ev and "R67" in m[0], (st, m)
    print("R67: ок — мерка флэта, шорт во флэте не берётся (всплеск, ждущий шорт, сползающая монета)")
except Exception as ex:  # noqa: BLE001
    print("СБОЙ R67", type(ex).__name__, ex); traceback.print_exc()
