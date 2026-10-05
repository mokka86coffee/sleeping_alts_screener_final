"""Проверка R65 (сползающая монета: лонгов нет, шорт только на отскоке) на собранных случаях; на биржу и в книги ничего не пишет. Печатает «R65: ок» или «СБОЙ …»."""
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
try:
    down = [100 - i * 0.3 for i in range(72)]; bounce = [100 - i * 0.4 for i in range(48)] + [81 + i * 0.3 for i in range(24)]
    up = [100 + i * 0.3 for i in range(72)]; flat = [100 + (i % 3) * 0.2 for i in range(72)]
    assert ft._slide_calc(down)[:2] == (True, False) and ft._slide_calc(bounce)[:2] == (True, True) and ft._slide_calc(up)[0] is False and ft._slide_calc(flat)[:2] == (False, False)
    now = time.time(); t_bar = int(now * 1000) // 180_000 * 180_000 - 180_000
    ft._own_mm = lambda: set(); ft.ses_gate = lambda now_, t_bar_, side=1: (True, "проверка", 600)
    # 1) сползает → всплеск и есть отскок: шорт в ожидание вершины (суточной мерки отскока больше нет)
    ft._slide = lambda s: (True, False, -15.0); st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "XUSDT", "всплеск", t_bar, now, m) is True and st["pending"]["XUSDT"].get("slide"), (st, m)   # отскок — сам всплеск: суточная мерка убрана
    # 2) сползает и отскок → шорт в ожидание вершины с пометкой slide
    ft._slide = lambda s: (True, True, -12.0); st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "XUSDT", "всплеск", t_bar, now, m) is True and st["pending"]["XUSDT"].get("slide") and st["pending"]["XUSDT"]["why"].startswith("R65"), (st, m)
    # 2а) монета из ручного списка лестницы: сползает → ни лонга, ни шорта
    import core_config as _cc
    st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, _cc.FAST3_NO_SHORT_MANUAL[0], "всплеск", t_bar, now, m) is True and not st.get("pending") and "R45" in m[0], (st, m)
    # 3) не сползает → правило не вмешивается
    ft._slide = lambda s: (False, True, 3.0); st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "XUSDT", "всплеск", t_bar, now, m) is False and not st.get("pending") and not m
    # 4) вход ждущего шорта R65: стоп 10 %, цели нет, срок 16 ч, пометка slide; «лестница» не мешает
    ft._slide = lambda s: (True, True, -12.0)
    t0 = t_bar - 6 * 180_000
    bars = [[t0 + i * 180_000, 1.00 + i * 0.01, 1.012 + i * 0.01, 0.999 + i * 0.01, 1.01 + i * 0.01, 0, 0, 0] for i in range(5)]   # пять баров вверх
    bars.append([t0 + 5 * 180_000, 1.045, 1.047, 1.03, 1.035, 0, 0, 0])                                                         # бар без нового максимума, закрытие вниз
    ft.get_json = lambda url, params=None, **kw: [list(map(str, b)) for b in bars] if "klines" in url else []
    ft._liq_hourly = lambda: {}; ft._no_short = lambda s, px: "лестница"; ft._too_young = lambda s: None; ft.london_gate = lambda s, n, w: None
    ft._rate_ok = lambda n, note=False: None; ft._run90 = lambda s: None; ft._flat_target = lambda s, px, tg: (tg, ""); ft.fon = lambda: {}; ft._bub = lambda s: None
    st = {"open": {}, "last_exit": {}, "pending": {"XUSDT": dict(why="R65 сползание → шорт на отскоке · всплеск", t_ms=t0, at=now, expire=now + 3600, start_low=None, slide=True)}}
    ev = []; m = []
    ft.pending_step(st, ft.BOOK, now, ev, m, False)
    p = st["open"].get("XUSDT")
    assert p and p["side"] == -1 and p["stop"] == 0.1 and p["target"] == 0 and p["hold_min"] == 960 and p.get("slide") and len(ev) == 1, (p, m)
    # 5) ведение: цели нет, после хода 5 % стоп в точку входа; вершина входа и вынос лонгов шорт не закрывают
    e = 1.0
    assert ft._short_tgt(p) == 0.0 and ft._ladder_top("XUSDT", p) is None and ft.fuel_exit("XUSDT", dict(p, px=1.0, t_ms=0), now, 0.9) is None
    k1 = [[0, 1, 1.01, 0.93, 0.94]]                                               # ход −7 %: цель не срабатывает, стоп переносится
    assert ft.short_walk(e, 0.1, ft._short_tgt(p), k1, None) == (None, None)
    k2 = k1 + [[1, 0.94, 1.001, 0.94, 0.99]]                                       # возврат к входу → стоп в безубыток
    assert ft.short_walk(e, 0.1, ft._short_tgt(p), k2, None)[1] == "стоп в безубыток"
    assert ft.short_walk(e, 0.1, ft._short_tgt(p), [[0, 1, 1.11, 0.99, 1.1]], None)[1] == "стоп"
    # 6) 05.10 зоны от вершины 30 дн: до 30 % — как было; 30–60 % — цель 10 %, стоп 10 %; глубже 60 % — сделок нет
    ft._hi90 = lambda s: 2.0
    assert ft._slide_zone("XUSDT", 1.5)[0] == 1 and ft._slide_zone("XUSDT", 1.0)[0] == 2 and ft._slide_zone("XUSDT", 0.7)[0] == 3 and ft._slide_zone("XUSDT", 0.0) == (1, None)
    st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "XUSDT", "всплеск", t_bar, now, m, px=0.7) is True and not st.get("pending") and "глубже 60" in m[0], (st, m)
    st = {"open": {}, "last_exit": {}}; m = []
    assert ft._slide_gate(st, "XUSDT", "всплеск", t_bar, now, m, px=1.0) is True and st["pending"]["XUSDT"].get("slide"), (st, m)
    ft._hi90 = lambda s: 2.0                                                      # вход по ~1.035 при вершине 2.0 → на 48 % ниже → зона 2
    st = {"open": {}, "last_exit": {}, "pending": {"XUSDT": dict(why="R65 сползание → шорт на отскоке · всплеск", t_ms=t0, at=now, expire=now + 3600, start_low=None, slide=True)}}
    ev = []; m = []; ft.pending_step(st, ft.BOOK, now, ev, m, False); p2 = st["open"].get("XUSDT")
    assert p2 and p2["target"] == 0.1 and p2["stop"] == 0.1 and p2["hold_min"] == _cc.FAST3_SLIDE_ZONE2_HOLD_MIN == 4320 and p2.get("slide") and p2.get("slide_tp") and ft._short_tgt(p2) == 0.1, (p2, m)
    assert ft.short_walk(1.0, 0.1, ft._short_tgt(p2), [[0, 1, 1.01, 0.89, 0.9]], None)[1] == "цель", ft.short_walk(1.0, 0.1, ft._short_tgt(p2), [[0, 1, 1.01, 0.89, 0.9]], None)
    ft._hi90 = lambda s: 10.0                                                     # вход глубже 60 % от вершины — ожидание снимается без сделки
    st = {"open": {}, "last_exit": {}, "pending": {"XUSDT": dict(why="R65 сползание → шорт на отскоке · всплеск", t_ms=t0, at=now, expire=now + 3600, start_low=None, slide=True)}}
    ev = []; m = []; ft.pending_step(st, ft.BOOK, now, ev, m, False)
    assert not st["open"] and not st["pending"] and not ev and any("глубже 60" in x for x in m), (st, m)
    print("R65: ок — мерка сползания, лонгов нет, шорт на отскоке (всплеск) через ожидание вершины, стоп 10 % / без цели / 16 ч, ведение")
except Exception as ex:  # noqa: BLE001
    print("СБОЙ R65", type(ex).__name__, ex); traceback.print_exc()
