#!/usr/bin/env python3
"""ПРОВЕРКА НА РАВЕНСТВО ПРИ ПЕРЕВОДЕ ЧАСОВ БОТА НА UTC (06.10, владелец: «всё должно быть в utc везде, хоть в настройках бота»;
«эта хрень где-то всплывёт с разницей в 3 часа — это конец сделки как минимум»). Правила по времени спрашиваются на каждую минуту
двух недель: сессия и срок (ses_gate, обе стороны), час перед сессией, окно без лонгов R69, Лондон, ожидание вершины, окно выносов
«с прошлой сессии», сессия сайта и журнала всплесков. Сравниваются МОМЕНТЫ (секунды), а не подписи.
    .venv/bin/python claude/research/utc_equiv.py save ФАЙЛ   — снять эталон с текущего кода
    .venv/bin/python claude/research/utc_equiv.py check ФАЙЛ  — сравнить текущий код с эталоном (выход 1 при расхождении)"""
import sys, json, pickle, tempfile, re
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import core_config as cc
import fast_tier as ft
import fast_state as fs
import surge_journal as sj

mode, ref = sys.argv[1], Path(sys.argv[2])
T0 = datetime(2026, 9, 28, 0, 0, tzinfo=timezone.utc).timestamp()          # понедельник 00:00 UTC, две недели
tmp = Path(tempfile.mkdtemp()); (tmp / "output").mkdir()
ft.BASE_DIR = tmp; ft._oi7 = lambda sym: 1.0
cc.FAST3_LONDON_MAX = 0                                                    # ворота Лондона отвечают отказом ровно тогда, когда ограничение действует
SES = ("Сидней", "Токио", "Лондон", "Нью-Йорк")

def cat(ok, sw):
    s = str(sw)
    if ok: return "ok:" + next((x for x in SES if s.startswith(x)), "?")
    return "нет:" + ("стык" if "за час до открытия" in s else "день" if s.startswith("день") else "первый час" if "первый час" in s else "поздно" if "поздно" in s else s[:20])

def row(now):
    out = {}
    for side in (1, -1):
        ok, sw, hold = ft.ses_gate(now, int(now * 1000) - 180_000, side)
        out[f"gate{side}"] = (cat(ok, sw), hold)
    out["r69"] = bool(ft._long_window_closed(now))
    out["london"] = bool(ft.london_gate("AAAUSDT", now, "всплеск: бар +2% на объёме ×20.0 (100K$)"))
    st = {}; ft.to_pending(st, "AAAUSDT", "w", int(now * 1000), now, None); out["pending"] = int(st["pending"]["AAAUSDT"]["expire"])
    m = fs.meta(now); out["site"] = (m.get("ses"), m.get("ses_start"), m.get("ses_end"), m.get("exit_at"))
    out["journal_ses"] = sj._ses(now)
    return out

def flush_w0(now):
    """начало окна «с прошлой сессии» у _flush: самый ранний час, вынос в который бот ещё считает «в окне»"""
    h_now = int(now // 3600) * 3600
    base = {(h_now - k * 3600) * 1000: 1.0 for k in range(24 * 5, 24 * 10)}
    first = None
    for k in range(40, -1, -1):
        H = (h_now - k * 3600) * 1000
        hs = dict(base); hs[H] = 100.0
        ft._liq_hourly = lambda hs=hs: {("AAAUSDT", "long"): hs}
        if ft._flush("AAAUSDT", now, "long"):
            first = H; break
    return first

tab = {}
for i in range(14 * 1440):
    now = T0 + i * 60 + 7
    r = row(now)
    if i % 20 == 0: r["flush_w0"] = flush_w0(now)
    tab[int(now)] = r
if mode == "save":
    pickle.dump(tab, open(ref, "wb")); print(f"эталон снят: {len(tab)} минут, пояс бота {ft.L}"); sys.exit(0)
old = pickle.load(open(ref, "rb")); bad = []
for t, r in tab.items():
    o = old[t]
    for k in o:
        if o[k] != r.get(k):
            bad.append((t, k, o[k], r.get(k)))
fmt = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%a %d.%m %H:%M UTC")
print(f"сравнено минут: {len(tab)} · пояс бота {ft.L} · расхождений: {len(bad)}")
by = {}
for t, k, a, b in bad: by.setdefault(k, []).append((t, a, b))
for k, v in by.items():
    print(f"  {k}: {len(v)} · первое {fmt(v[0][0])}: было {v[0][1]} стало {v[0][2]} · последнее {fmt(v[-1][0])}: было {v[-1][1]} стало {v[-1][2]}")
print("РАВЕНСТВО: ок" if not bad else "РАВЕНСТВО: НЕТ")
sys.exit(1 if bad else 0)
