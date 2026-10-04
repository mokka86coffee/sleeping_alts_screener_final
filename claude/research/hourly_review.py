#!/usr/bin/env python3
"""ЧАСОВОЙ РАЗБОР СДЕЛОК БОТА (03.10 16:35, владелец: «каждый час проверяй сделки бота и пиши сюда разбор», «открытые, закрытые, все»; «прогон был на тебе всё это время»).
Собирает факты за последний час (или N минут) для разбора в чате — сам ничего не меняет:
  входы и выходы обеих книг (журналы output/paper_fast3.jsonl, paper_wake.jsonl), все открытые позиции с текущим результатом (один запрос цен по всему Binance),
  зеркало BingX (output/bingx_state.json), итог дня (закрытые / открытые / отдельно ошибочная пачка сканера 03.10), сбои в логе бота, причины отсечения всплесков за период, доска.
    .venv/bin/python claude/research/hourly_review.py [минут=60]"""
import json, re, sys, time, urllib.request, collections
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; L = timezone(timedelta(hours=3)); MIN = int(sys.argv[1]) if len(sys.argv) > 1 else 60
now = time.time(); t0 = now - MIN * 60; d0 = datetime.now(L).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
f = lambda t: datetime.fromtimestamp(t, L).strftime("%H:%M"); fd = lambda t: datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M")
ev = []; allev = []   # 04.10: окно через полночь — входы и выходы окна берутся из allev (48 ч), итог дня из ev
for book, p in (("всплеск/вынос", "paper_fast3.jsonl"), ("пробуждение", "paper_wake.jsonl")):
    for l in open(ROOT / "output" / p, encoding="utf-8"):
        try: r = json.loads(l)
        except ValueError: continue
        if r.get("at", 0) >= now - 48 * 3600: r["_book"] = book; allev.append(r)
        if r.get("at", 0) >= d0: ev.append(r)
ev.sort(key=lambda r: r["at"]); allev.sort(key=lambda r: r["at"])
try: px = {x["symbol"]: float(x["price"]) for x in json.load(urllib.request.urlopen("https://fapi.binance.com/fapi/v1/ticker/price", timeout=20))}
except Exception: px = {}
print(f"ЧАСОВОЙ РАЗБОР · {fd(now)} · окно {MIN} мин (с {f(t0)})")
try:
    b = json.load(open(ROOT / "output" / "board_now.json")); print(f"ДОСКА 24 ч {b['board24']:+.1f}% ({b['mode']}), в плюсе {b['up']:.0f}% монет, BTC {b['btc']:+.1f}% · сканер при выносе на росте: {b['flush_side']} · данные {f(b['at'])}")
except Exception: print("ДОСКА: нет данных")
ent = [r for r in allev if r.get("kind") == "entry" and r["at"] >= t0]; ex = [r for r in allev if r.get("kind") in ("exit_long", "exit_short") and r["at"] >= t0]
print(f"\nВХОДЫ ЗА ОКНО: {len(ent)}")
for r in ent: print(f"  {f(r['at'])} {r['sym'][:-4]} {'ЛОНГ' if r.get('side') == 1 else 'ШОРТ'} {r.get('px')} · цель {r.get('target')} стоп {r.get('stop')} срок {r.get('hold_min')} мин · {r['_book']} · {str(r.get('rule'))[:260]}")
print(f"\nВЫХОДЫ ЗА ОКНО: {len(ex)} · {sum(r.get('usd', 0) for r in ex):+.0f} $")
for r in ex: print(f"  {fd(r.get('opened_at', 0))} → {f(r['at'])} {r['sym'][:-4]} {'ЛОНГ' if r['kind'] == 'exit_long' else 'ШОРТ'} {r.get('px_in')} → {r.get('px_out')} · {r.get('result_pct'):+.2f}% {r.get('usd', 0):+.0f}$ · выход: {str(r.get('why_exit'))[:120]} · вход по: {str(r.get('rule'))[:160]}")
print("\nОТКРЫТЫЕ:"); tot_open = 0.0
try: bx = json.load(open(ROOT / "output" / "bingx_state.json")).get("open", {})
except Exception: bx = {}
for book, p in (("всплеск/вынос", "paper_fast3.json"), ("пробуждение", "paper_wake.json")):
    try: st = json.load(open(ROOT / "output" / p)).get("open", {})
    except Exception: st = {}
    for sym, v in st.items():
        c = px.get(sym); sd = int(v["side"]); e = float(v["px"]); res = (c / e - 1) * sd * 100 if c else None; tot_open += (res or 0) * 10
        print(f"  {sym[:-4]} {'ЛОНГ' if sd == 1 else 'ШОРТ'} вход {e:g} ({fd(v.get('at', 0))}) · сейчас {c} · {'%+.2f%%' % res if res is not None else 'нет цены'} · цель {v.get('target')} стоп {v.get('stop')}{' стоп-цена ' + str(v.get('stop_px')) if v.get('stop_px') else ''} · срок {v.get('hold_min')} мин · {book} · BingX: {'есть' if sym in bx else 'нет'} · {str(v.get('rule'))[:150]}")
allx = [r for r in ev if r.get("kind") in ("exit_long", "exit_short")]; bug = [r for r in allx if "ошибка сканера" in str(r.get("why_exit"))]
print(f"\nИТОГ ДНЯ: закрыто {len(allx)} сделок {sum(r.get('usd', 0) for r in allx):+.0f} $ · из них ошибочная пачка сканера (моя ошибка, 01:50–03:03) {len(bug)} сделок {sum(r.get('usd', 0) for r in bug):+.0f} $ · остальные {len(allx) - len(bug)} сделок {sum(r.get('usd', 0) for r in allx) - sum(r.get('usd', 0) for r in bug):+.0f} $ · открытые сейчас {tot_open:+.0f} $")
last_e = max((r["at"] for r in allev if r.get("kind") == "entry"), default=None); print("последний вход:", fd(last_e) if last_e else "за 48 ч не было")
# лог бота за окно
Lg = open(ROOT / "output" / "fast_tier.log", encoding="utf-8", errors="replace").read().split("\n")[-4000:]; start = 0; prev = ""
for i, l in enumerate(Lg):
    if re.match(r"\d\d:\d\d:\d\d", l[:8]):
        if prev and l[:8] < prev and prev[:2] >= "22" and l[:2] <= "01": start = i
        prev = l[:8]
T = [l for l in Lg[start:] if re.match(r"\d\d:\d\d:\d\d", l[:8]) and l[:8] >= datetime.fromtimestamp(t0, L).strftime("%H:%M:%S")] if datetime.fromtimestamp(t0, L).date() == datetime.now(L).date() else Lg[start:]
bad = [l for l in T if "сбой" in l or "Traceback" in l or "Error" in l or "Exception" in l]; print(f"\nСБОИ В ЛОГЕ ЗА ОКНО: {len(bad)}"); [print("  " + l[:200]) for l in bad[:5]]
c = collections.Counter(); exm = {}
for l in T:
    m = re.match(r"\S+ (всплеск/вынос|пробуждение): (\S+) (.*)", l.strip())
    if not m or m.group(2) in ("список:", "пробуждений") or "перевёрнута" in l or " вход " in l or " выход " in l or "BingX" in l: continue
    rest = m.group(3); k = re.sub(r"\(.*", "", re.sub(r"[-+−]?\d[\d.,]*%?", "N", rest)).strip()[:70]; c[k] += 1; exm.setdefault(k, f"{l[:8]} {m.group(2)} {rest[:110]}")
print("ОТСЕЧЕНО ЗА ОКНО (причина · сколько раз · пример):")
for k, v in c.most_common(12): print(f"  {v:3d} · {exm[k]}")
# 04.10: расхождение бота и зеркала — позиция есть на BingX (bingx_state.json), а в книгах бота её нет (FHE висела сутки после слияния книги 03.10), и монета в обеих книгах в разные стороны
try:
    _bo = (json.load(open(ROOT / "output" / "bingx_state.json")).get("open") or {})
    _f = json.load(open(ROOT / "output" / "paper_fast3.json")).get("open") or {}; _w = json.load(open(ROOT / "output" / "paper_wake.json")).get("open") or {}
    _orph = [k for k in _bo if k not in _f and k not in _w]
    _opp = [k for k in _f if k in _w and _f[k].get("side") != _w[k].get("side")]
    _sd = [k for k in _bo if (k in _f or k in _w) and _bo[k].get("side") not in [x[k].get("side") for x in (_f, _w) if k in x]]
    print("РАСХОЖДЕНИЕ БОТ/BINGX: " + ("нет" if not (_orph or _opp or _sd) else " · ".join(([f"на BingX есть, в боте нет: {', '.join(k[:-4] for k in _orph)}"] if _orph else []) + ([f"в двух книгах в разные стороны: {', '.join(k[:-4] for k in _opp)}"] if _opp else []) + ([f"сторона на BingX не как в боте: {', '.join(k[:-4] for k in _sd)}"] if _sd else []))))
except Exception as _e:
    print("РАСХОЖДЕНИЕ БОТ/BINGX: не проверено", repr(_e)[:120])
bxl = [l for l in T if "BingX" in l]; print(f"BINGX строк за окно: {len(bxl)}"); [print("  " + l[:170]) for l in bxl[-6:]]
