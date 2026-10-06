#!/usr/bin/env python3
"""ШОРТ НА ВСПЛЕСКЕ ВМЕСТО ЛОНГА (06.10, владелец: «если лонги на всплесках не работают, почему бы не поставить шорты», «делай»).
Все лонги на всплеске из журнала бота (обе книги, без повторов) проигрываются по 3-минутным свечам BingX (открытые данные) как ШОРТ в той же точке:
  стоп — цена выше входа на S % (3, 5, 10); выход с прибылью — «памп вернулся»: 3-мин закрытие ниже открытия бара всплеска; срок 2 часа — выход по закрытию.
В баре сначала проверяется стоп. Для сверки тем же способом считается сам лонг (цель +5 %, стоп −10 %, «памп вернулся», срок 2 ч). 500 $ на сделку, комиссия 0,2 % на круг.
    .venv/bin/python claude/research/spike_short_mirror.py"""
import json, sys, time, urllib.request, collections, datetime as dt
from pathlib import Path
B = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(B))
import fast_tier as ft, bingx_trader as bx
U = dt.timezone.utc; SIZE, FEE, N = 500.0, 0.002, 40


def klines(sym_bx, t0):
    url = f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={sym_bx}&interval=3m&startTime={(t0 - 540) * 1000}&endTime={(t0 + N * 180 + 360) * 1000}&limit=60"
    for att in range(4):
        try:
            j = json.load(urllib.request.urlopen(url, timeout=20))
        except Exception:
            time.sleep(2); continue
        if j.get("data"): return sorted(([int(x["time"]) // 1000, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])] for x in j["data"]))
        if str(j.get("code")) == "109429": time.sleep(4); continue
        return []
    return []


def short(e, po, k, stop):
    for i, x in enumerate(k[:N]):
        if x[2] >= e * (1 + stop): return -stop, "стоп"
        if x[4] < po: return 1 - x[4] / e, "памп вернулся"
    return (1 - k[min(len(k), N) - 1][4] / e, "срок 2 ч") if k else (None, None)


def long_(e, po, k):
    for x in k[:N]:
        if x[3] <= e * 0.90: return -0.10, "стоп"
        if x[2] >= e * 1.05: return 0.05, "цель"
        if x[4] < po: return x[4] / e - 1, "памп вернулся"
    return (k[min(len(k), N) - 1][4] / e - 1, "срок 2 ч") if k else (None, None)


ent, seen = [], set()
for fn in ("output/paper_fast3.jsonl", "output/paper_wake.jsonl"):
    for l in open(B / fn, encoding="utf-8"):
        try: e = json.loads(l)
        except ValueError: continue
        r = str(e.get("rule") or "")
        if e.get("kind") != "entry" or e.get("side") != 1 or "всплеск" not in r or any(z in r for z in ("R52", "R59", "флэт", "переворот")): continue
        key = (e["sym"], int(float(e["at"]) // 180))
        if key in seen: continue
        seen.add(key); ent.append(e)
CT = bx.contracts(); rows = []; skip = collections.Counter()
for e in sorted(ent, key=lambda e: e["at"]):
    ct = CT.get(e["sym"]); e_bot = float(e["px"]); po_bot = ft._pump_open(e_bot, e.get("rule") or "")
    if not ct: skip["нет на BingX"] += 1; continue
    if not po_bot: skip["нет уровня открытия бара"] += 1; continue
    t0 = int(float(e["at"]) // 180 * 180)
    kb = klines(ct["symbol"], t0); time.sleep(0.4)
    pre = [x for x in kb if x[0] < t0]; k = [x for x in kb if x[0] >= t0]
    if not pre or len(k) < 5: skip["свечей нет"] += 1; continue
    eb = pre[-1][4]; po = eb * po_bot / e_bot
    rows.append((e, long_(eb, po, k), {s: short(eb, po, k, s) for s in (.03, .05, .10)}))
json.dump([dict(sym=e["sym"], at=e["at"], long=l, short={str(k_): v for k_, v in s_.items()}) for e, l, s_ in rows],
          open(Path(__file__).parent / "spike_short_mirror_rows.json", "w"), ensure_ascii=False)          # по сделкам — для разбивки по сессиям и объёму
day = lambda e: dt.datetime.fromtimestamp(e["at"], U).strftime("%d.%m")
print(f"лонгов на всплеске в журнале: {len(ent)} · проиграно: {len(rows)} · пропущено: {dict(skip)}")
def line(name, get):
    v = [(e, get(l, s)) for e, l, s in rows]; v = [(e, r) for e, r in v if r[0] is not None]
    usd = lambda g: sum((r[0] - FEE) * SIZE for _, r in g)
    by = collections.defaultdict(list)
    for e, r in v: by[day(e)].append((e, r))
    ds = {d: round(usd(g)) for d, g in sorted(by.items(), key=lambda kv: (kv[0][3:], kv[0][:2]))}
    c = collections.Counter(r[1] for _, r in v)
    print(f"\n{name}: сделок {len(v)} · в плюс {sum(1 for _, r in v if r[0] - FEE > 0)} · итог {usd(v):+.0f} $ · на сделку {usd(v) / max(1, len(v)):+.1f} $")
    print(f"   чем кончались: {dict(c)}")
    print(f"   по дням: {ds} · плюсовых дней {sum(1 for x in ds.values() if x > 0)} из {len(ds)} · худший день {min(ds.values())} $")
line("ЛОНГ (как в боте, для сверки)", lambda l, s: l)
for st in (.03, .05, .10):
    line(f"ШОРТ в той же точке, стоп {st * 100:.0f} %", lambda l, s, st=st: s[st])
