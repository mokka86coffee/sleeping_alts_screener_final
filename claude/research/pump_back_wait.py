#!/usr/bin/env python3
"""ВЫХОД «ПАМП ВЕРНУЛСЯ»: СРАЗУ ИЛИ ЧЕРЕЗ 3 БАРА (06.10, владелец по ORCA: «давай вот такой отскок не закрывать сразу», «закрытие должно при возврате
цены по истечении 3 прогонов, то есть 9 минут, а не 1-го», «иначе мы просто заходим на пампе, который 99 % отскочит и вернётся»).
Все лонги из журнала бота, закрытые по «памп вернулся», проигрываются заново по 3-минутным свечам BingX (открытые данные) двумя способами:
выход на первом закрытии ниже открытия бара всплеска (как было) и на третьем подряд. Ведение — копия long_walk из fast_tier.py: стоп, цель, срок 2 ч,
удержание (цель +10 %, стоп на низу), потолок 16 ч. Цены BingX: уровень «открытие бара всплеска» переносится долей от входа бота.
    .venv/bin/python claude/research/pump_back_wait.py"""
import json, sys, time, urllib.request, collections, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft, bingx_trader as bx
from core_config import FAST3_LONG_HOLD_MIN, FAST3_LONG_HOLD_TP, FAST3_MAX_HOLD_MIN, FAST3_SIZE
U = dt.timezone.utc


def walk(e, po, stop, target, k, need):
    n1 = FAST3_LONG_HOLD_MIN // 3; below = 0
    for i, x in enumerate(k[:n1]):
        h, l, c = x[2], x[3], x[4]
        if l <= e * (1 - stop): return -stop, "стоп", i
        if h >= e * (1 + target): return target, "цель", i
        below = below + 1 if (po and c < po) else 0
        if below >= need: return c / e - 1, "памп вернулся", i
    if len(k) < n1: return k[-1][4] / e - 1, "данных нет дальше", len(k) - 1
    c_end = k[n1 - 1][4]
    if c_end < e: return c_end / e - 1, "срок 2 ч", n1 - 1
    low = min(x[3] for x in k[:n1]); cap = FAST3_MAX_HOLD_MIN // 3
    for i, x in enumerate(k[n1:cap], n1):
        if x[3] <= low: return low / e - 1, "стоп на низу удержания", i
        if x[2] >= e * (1 + FAST3_LONG_HOLD_TP): return FAST3_LONG_HOLD_TP, "цель +10 %", i
    j = min(len(k), cap) - 1
    return k[j][4] / e - 1, "потолок 16 ч", j


ent, ex = {}, []
for fn in ("output/paper_fast3.jsonl", "output/paper_wake.jsonl"):
    for l in open(fn, encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("kind") == "entry": ent[(r["sym"], round(float(r["at"])))] = r
        elif str(r.get("kind", "")).startswith("exit") and "памп вернулся" in str(r.get("why_exit") or ""): ex.append(r)
seen, rows = set(), []
CT = bx.contracts()
for r in sorted(ex, key=lambda r: r["at"]):
    key = (r["sym"], round(float(r["opened_at"]) / 180))
    if key in seen: continue                                             # одна монета в двух книгах — один вход
    seen.add(key)
    en = ent.get((r["sym"], round(float(r["opened_at"])))) or {}
    e_bot = float(r["px_in"]); po_bot = ft._pump_open(e_bot, en.get("rule") or r.get("rule") or "")
    ct = CT.get(r["sym"])
    if not ct or not po_bot: print("пропуск", r["sym"], "нет на BingX" if not ct else "нет уровня в правиле"); continue
    t0 = int(float(r["opened_at"]) // 180 * 180)
    url = f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={ct['symbol']}&interval=3m&startTime={(t0 - 360) * 1000}&endTime={(t0 + FAST3_MAX_HOLD_MIN * 60 + 600) * 1000}&limit=400"
    try:
        d = json.load(urllib.request.urlopen(url, timeout=20)).get("data") or []
    except Exception as e_:
        print("пропуск", r["sym"], type(e_).__name__); continue
    time.sleep(0.6)
    kb = sorted(([int(x["time"]) // 1000, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])] for x in d))
    pre = [x for x in kb if x[0] < t0]
    k = [x for x in kb if x[0] >= t0]
    if not pre or len(k) < 3: print("пропуск", r["sym"], "свечей нет"); continue
    e = pre[-1][4]; po = e * po_bot / e_bot
    a = walk(e, po, float(en.get("stop") or 0.10), float(en.get("target") or 0.05), k, 1)
    b = walk(e, po, float(en.get("stop") or 0.10), float(en.get("target") or 0.05), k, 3)
    rows.append((r, a, b))
tot = lambda i: sum(x[i][0] for x in rows) * FAST3_SIZE
print(f"\nлонгов с выходом «памп вернулся»: {len(rows)} (без повторов по книгам)")
print(f"выход сразу (как было):      {tot(1):+.0f} $ | в плюс {sum(1 for x in rows if x[1][0] > 0)}")
print(f"выход на третьем баре подряд: {tot(2):+.0f} $ | в плюс {sum(1 for x in rows if x[2][0] > 0)}")
c = collections.Counter(x[2][1] for x in rows); print("чем кончились при ожидании:", dict(c))
day = collections.defaultdict(lambda: [0, 0.0, 0.0])
for r, a, b in rows:
    d_ = dt.datetime.fromtimestamp(r["at"], U).strftime("%d.%m"); day[d_][0] += 1; day[d_][1] += a[0] * FAST3_SIZE; day[d_][2] += b[0] * FAST3_SIZE
print("по дням (сделок, сразу $, через 3 бара $):", {k_: (v[0], round(v[1]), round(v[2])) for k_, v in day.items()})
better = sum(1 for x in rows if x[2][0] > x[1][0] + 1e-9); worse = sum(1 for x in rows if x[2][0] < x[1][0] - 1e-9)
print(f"лучше при ожидании: {better} · хуже: {worse} · одинаково: {len(rows) - better - worse}")
print("\nсделки: дата монета | сразу % | через 3 бара % и чем кончилось (минут от входа)")
for r, a, b in rows:
    print(f"{dt.datetime.fromtimestamp(r['opened_at'], U):%d.%m %H:%M} {r['sym'][:-4]:9s} | {a[0] * 100:+.1f} | {b[0] * 100:+.1f} {b[1]} ({(b[2] + 1) * 3})")
