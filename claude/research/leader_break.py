"""Что делает доска после слома лидера (вопрос владельца 26.09: «лидер очень сильно улетел и начнёт падать — сколько денег уйдёт,
проверить по медиане и по количеству растущих монет: как долго рынок стоит или падает после сильного движения лидера»).
Второй вопрос (26.09): пойдёт ли монета №2 очереди после слома лидера (ARK при PHA)? Гипотеза владельца: в переходном рынке деньги
только переходят — после падения лидера доска стоит или падает, №2 не идёт.

Данные: cq_v2/hist/tops/<SYM>.json (получасовки Binance за 30 дней, 154 монеты; обновить: .venv/bin/python lab_tops.py --fetch),
output/queue_log.jsonl (журнал очереди с 16.09: места, фон доски).
Лидер: монета с самым большим ходом за 48 ч, если ход ≥ LEAD_MIN (100% — «ярус A», 70–100% — «ярус B»). Слом: первый бар, где закрытие
на 15% ниже максимума последних 24 ч (мерки для разметки, не правила; повтор по той же монете — после нового максимума выше прошлого и не раньше чем через 12 ч).
По каждому слому: медиана доски и доля растущих (без лидера) за 24 ч ДО и на 6/12/24/48 ч ПОСЛЕ; ход самого лидера после; монета №2 —
2-е место очереди по журналу на свече слома (если лидер сам на 2-м — берём 1-е; до 16.09 журнала нет — второй по ходу за 48 ч, помечено «≈»)
и её ход через 6/12/24/48 ч плюс максимум за 48 ч. Вид события: «слом» — лидер через 48 ч ниже точки слома; «встряска» — выше
(15% от максимума ловит и встряски внутри хода, R24); «?» — 48 ч ещё не прошло.
    .venv/bin/python claude/research/leader_break.py
"""
import json, statistics as st
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "cq_v2" / "hist" / "tops"
LEAD_MIN = 0.7
kl = {p.stem: {k[0]: k for k in json.loads(p.read_text())["kl"]} for p in P.glob("*.json") if p.stem != "BTCUSDT"}
ts_all = sorted(set().union(*[set(m) for m in kl.values()]))
H = 3600000

# журнал очереди: места 1–2 по свечам
places = {}
with open(ROOT / "output" / "queue_log.jsonl") as f:
    for line in f:
        d = json.loads(line)
        if d.get("sym") != "_BG" and d.get("place") in (1, 2):
            c = int(datetime.strptime(d["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            places.setdefault(c, {})[d["place"]] = d["sym"]


def ret(sym, t, dt):
    m = kl[sym]; a, b = m.get(t), m.get(t + dt)
    return (b[3] / a[3] - 1) * 100 if a and b else None


def mx(sym, t, dt):
    m = kl[sym]; a = m.get(t)
    hs = [m[x][1] for x in range(t + 1800000, t + dt + 1, 1800000) if x in m]
    return (max(hs) / a[3] - 1) * 100 if a and hs else None


def board(t, dt, excl):
    r = [ret(s, t, dt) for s in kl if s not in excl]; r = [x for x in r if x is not None]
    return (st.median(r), sum(1 for x in r if x > 0) / len(r) * 100) if r else (None, None)


def second(t, leader):
    """монета №2: журнал (2-е место; если там лидер — 1-е), иначе второй по ходу за 48 ч (≈)"""
    for c in (t, t - 1800000, t + 1800000):
        p = places.get(c)
        if p:
            s = p.get(2) if p.get(2) != leader else p.get(1)
            if s and s in kl:
                return s, ""
    best = None
    for s, m in kl.items():
        if s != leader and t in m and t - 48 * H in m:
            r = m[t][3] / m[t - 48 * H][3] - 1
            if best is None or r > best[0]:
                best = (r, s)
    return (best[1], "≈") if best else (None, "")


L = lambda t: datetime.fromtimestamp(t / 1000 + 3 * 3600, timezone.utc).strftime("%d.%m %H:%M")
events, seen = [], {}
for t in ts_all:
    if t - ts_all[0] < 48 * H:
        continue
    best = None
    for s, m in kl.items():
        if t in m and t - 48 * H in m:
            r = m[t][3] / m[t - 48 * H][3] - 1
            if r >= LEAD_MIN and (best is None or r > best[0]):
                best = (r, s)
    if not best:
        continue
    r, s = best; m = kl[s]
    hi = max(m[x][1] for x in range(t - 24 * H, t + 1, 1800000) if x in m)
    if m[t][3] <= hi * 0.85 and (s not in seen or (hi > seen[s][0] and t - seen[s][1] >= 12 * H)):
        seen[s] = (hi, t); events.append((t, s, r))   # повтор по монете — после нового максимума и не раньше чем через 12 ч

base24 = []
for t in ts_all[::12]:
    if t + 24 * H <= ts_all[-1]:
        b = board(t, 24 * H, ())
        if b[0] is not None:
            base24.append(b[0])

f = lambda v: "  —  " if v is None else f"{v:+5.1f}"
print("Слом лидера (местное время). Доска = медиана и доля растущих без лидера и №2; база — медиана доски за 24 ч по всем моментам "
      f"{st.median(base24):+.1f}%\n")
print(f"{'лидер':<8}{'яр':<2}{'вид':<5}{'когда':<12}{'ход48':>6} | доска до 24ч | после: 6ч · 12ч · 24ч · 48ч (мед/доля↑) | лидер 24/48 | №2       6ч   12ч   24ч   48ч  макс48")
rows = []
for t, s, r in events:
    s2, mark = second(t, s)
    excl = (s, s2)
    m24, sh24 = board(t - 24 * H, 24 * H, excl)
    cols, after = [], {}
    for dt in (6, 12, 24, 48):
        if t + dt * H > ts_all[-1]:
            cols.append("   —   "); after[dt] = (None, None); continue
        m, sh = board(t, dt * H, excl); after[dt] = (m, sh); cols.append(f"{m:+5.1f}/{sh:3.0f}")
    l24, l48 = ret(s, t, 24 * H), ret(s, t, 48 * H)
    r2 = {dt: ret(s2, t, dt * H) for dt in (6, 12, 24, 48)} if s2 else {}
    x2 = mx(s2, t, 48 * H) if s2 else None
    tier = "A" if r >= 1.0 else "B"
    kind = "?" if l48 is None else ("слом" if l48 < 0 else "встр")
    print(f"{s[:-4]:<8}{tier:<2}{kind:<5}{L(t):<12}{r * 100:+5.0f}% | {m24:+5.1f}% {sh24:3.0f}% | " + " · ".join(cols)
          + f" | {f(l24)} {f(l48)} | {mark}{(s2 or '')[:-4]:<7} {f(r2.get(6))} {f(r2.get(12))} {f(r2.get(24))} {f(r2.get(48))}  {f(x2)}")
    rows.append(dict(t=t, s=s, r=r, tier=tier, kind=kind, m24=m24, sh24=sh24, after=after, l24=l24, l48=l48, s2=s2, mark=mark, r2=r2, x2=x2))

print("\nСВОДКА (без сведения в кучу — по фону доски до слома):")
def grp(name, sel):
    rs = [x for x in rows if sel(x) and x["after"][24][0] is not None]
    if not rs:
        return
    up = sum(1 for x in rs if x["after"][24][0] > x["m24"]); pos = sum(1 for x in rs if x["after"][24][0] > 0)
    up48 = [x for x in rs if x["after"][48][0] is not None]
    pos48 = sum(1 for x in up48 if x["after"][48][0] > 0)
    print(f"  {name}: n={len(rs)} · доска 24ч после выше, чем 24ч до — {up}/{len(rs)} · доска 24ч после >0 — {pos}/{len(rs)}"
          f" · 48ч после >0 — {pos48}/{len(up48)} · медиана доски после 24ч {st.median([x['after'][24][0] for x in rs]):+.1f}% (до: {st.median([x['m24'] for x in rs]):+.1f}%)")
grp("все события", lambda x: True)
grp("встряски (лидер через 48 ч выше)", lambda x: x["kind"] == "встр")
grp("СЛОМЫ (лидер через 48 ч ниже)", lambda x: x["kind"] == "слом")
grp("  сломы при доске до > +1% (доска ехала)", lambda x: x["kind"] == "слом" and x["m24"] > 1)
grp("  сломы при доске до −1…+1%", lambda x: x["kind"] == "слом" and -1 <= x["m24"] <= 1)
grp("  сломы при доске до < −1% (доска падала)", lambda x: x["kind"] == "слом" and x["m24"] < -1)
print("  лидер после слома: 24ч ниже — %d/%d, 48ч ниже — %d/%d" % (
    sum(1 for x in rows if x["l24"] is not None and x["l24"] < 0), sum(1 for x in rows if x["l24"] is not None),
    sum(1 for x in rows if x["l48"] is not None and x["l48"] < 0), sum(1 for x in rows if x["l48"] is not None)))
r2s = [x for x in rows if x["s2"] and x["r2"].get(24) is not None and x["kind"] == "слом"]
if r2s:
    print(f"  №2 ПОСЛЕ СЛОМА: через 24ч выше — {sum(1 for x in r2s if x['r2'][24] > 0)}/{len(r2s)}; максимум за 48ч ≥ +10% — "
          f"{sum(1 for x in r2s if x['x2'] is not None and x['x2'] >= 10)}/{len(r2s)}; ≥ +20% — {sum(1 for x in r2s if x['x2'] is not None and x['x2'] >= 20)}/{len(r2s)}; "
          f"медиана хода №2 за 24ч {st.median([x['r2'][24] for x in r2s]):+.1f}%")
    jr = [x for x in r2s if not x["mark"]]
    if jr:
        print(f"  из них по журналу (с 16.09): n={len(jr)} · 24ч выше {sum(1 for x in jr if x['r2'][24] > 0)}/{len(jr)} · макс48 ≥+10% {sum(1 for x in jr if x['x2'] is not None and x['x2'] >= 10)}/{len(jr)}")

# сейчас: лидеры по ходу за 48 ч на последнем баре и их расстояние от максимума суток
tl = ts_all[-1]
print(f"\nСЕЙЧАС (последний бар {L(tl)}): монеты с ходом за 48 ч ≥ +50% и расстояние закрытия от максимума 24 ч:")
cur = []
for s, m in kl.items():
    if tl in m and tl - 48 * H in m:
        r = m[tl][3] / m[tl - 48 * H][3] - 1
        if r >= 0.5:
            hi = max(m[x][1] for x in range(tl - 24 * H, tl + 1, 1800000) if x in m)
            cur.append((r, s, (m[tl][3] / hi - 1) * 100))
for r, s, d in sorted(cur, reverse=True):
    print(f"  {s[:-4]:<8} ход48 {r * 100:+5.0f}% · от максимума суток {d:+5.1f}%")
bm, bs = board(tl - 24 * H, 24 * H, ())
print(f"  доска за последние 24 ч: медиана {bm:+.1f}%, растущих {bs:.0f}%")
