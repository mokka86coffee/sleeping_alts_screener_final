#!/usr/bin/env python3
"""РАЗБОР ЖУРНАЛА ВСПЛЕСКОВ (29.09, spike_collector.py): исход за 1/2/4 ч по группам фона и по монетам. → output/spike_report.md
Всплеск — бар ≥ +1% и ×10 объёма (Binance); исход — от цены закрытия бара. «Первым +5%» — за окно цена дошла до +5% раньше, чем до −5%.
Сессии и дни недели здесь НЕ разбираются (владелец 30.09: только записываем, разбор через ~2 недели; поля ses и wd пишутся в журнал). Группа считается только при n ≥ 5 (меньше — «мало»). Расчёт по группам, не проверено; по монетам — отдельной таблицей."""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parent; L = timezone(timedelta(hours=3))
H = int(sys.argv[1]) if len(sys.argv) > 1 else 4
sp, oc = {}, {}
if not (ROOT / "output" / "spike_log.jsonl").exists():
    print("журнала всплесков ещё нет"); raise SystemExit(0)
for ln in open(ROOT / "output" / "spike_log.jsonl"):
    r = json.loads(ln)
    (sp if r["kind"] == "spike" else oc)[(r["sym"], r["t_ms"]) if r["kind"] == "spike" else (r["sym"], r["t_ms"], r["h"])] = r
rows = []
for k, s in sp.items():
    o = oc.get((k[0], k[1], H))
    if o: rows.append({**s, **{"up": o["up"], "dn": o["dn"], "cl": o["cl"], "first": o["first"]}})
def stat(g):
    if len(g) < 5: return f"n={len(g)} — мало"
    up = sum(1 for r in g if r["first"] == "+5"); dn = sum(1 for r in g if r["first"] == "-5"); med = sorted(r["cl"] for r in g)[len(g) // 2]
    return f"n={len(g)} · первым +5%: {up} ({up * 100 // len(g)}%) · −5%: {dn} ({dn * 100 // len(g)}%) · медиана закрытия {med:+.1f}% · ср. макс. вверх {sum(r['up'] for r in g) / len(g):+.1f}% / вниз {sum(r['dn'] for r in g) / len(g):+.1f}%"
G = (("все", lambda r: True),
     ("у вершины 90 дн (≥ −10% от макс.)", lambda r: (r.get("hi90") is not None) and r["hi90"] >= -10), ("не у вершины 90 дн", lambda r: (r.get("hi90") is not None) and r["hi90"] < -10),
     ("×90 ≥ 2", lambda r: (r.get("x90") or 0) >= 2), ("×90 < 2", lambda r: r.get("x90") is not None and r["x90"] < 2),
     ("ход за 30 дн ≥ +30%", lambda r: (r.get("ch30") or -999) >= 30), ("ход за 30 дн < +30%", lambda r: r.get("ch30") is not None and r["ch30"] < 30),
     ("спот CVD 7 дн растёт", lambda r: (r.get("spot_cvd7") or 0) > 0), ("спот CVD 7 дн падает", lambda r: r.get("spot_cvd7") is not None and r["spot_cvd7"] < 0),
     ("интерес за час ≥ +3%", lambda r: (r.get("oi1h") or -999) >= 3), ("интерес за час < +3%", lambda r: r.get("oi1h") is not None and r["oi1h"] < 3),
     ("интерес на баре (5 мин) ≤ 0", lambda r: r.get("oi5") is not None and r["oi5"] <= 0),
     ("фандинг < 0 (толпа шортов)", lambda r: r.get("fund") is not None and r["fund"] < 0), ("фандинг ≥ 0.03%", lambda r: (r.get("fund") or 0) >= 0.03),
     ("толпа по счетам < 1 (шорты)", lambda r: r.get("crowd") is not None and r["crowd"] < 1), ("толпа ≥ 1.5 (лонги)", lambda r: (r.get("crowd") or 0) >= 1.5),
     ("на часе вынос шортов ≥ макс. часа монеты", lambda r: bool(r.get("liq_short_top")) and r["liq_short_now"] >= r["liq_short_top"]),
     ("на часе вынос лонгов ≥ макс. часа монеты", lambda r: bool(r.get("liq_long_top")) and r["liq_long_now"] >= r["liq_long_top"]),
     ("бар ≥ +3%", lambda r: r["bar"] >= 3), ("бар < +3%", lambda r: r["bar"] < 3), ("объём ×10 и больше", lambda r: r["x"] >= 10), ("объём ×5–10", lambda r: r["x"] < 10), ("объём ≥ ×30", lambda r: r["x"] >= 30))
md = [f"# Журнал всплесков — исход через {H} ч ({datetime.now(L):%d.%m %H:%M})", "", f"Всплесков с исходом: {len(rows)} из {len(sp)}. Первый сбор — 29.09. Расчёт по группам, не проверено.", "", "| группа | итог |", "|---|---|"]
for nm, fn in G: md.append(f"| {nm} | {stat([r for r in rows if fn(r)])} |")
d = defaultdict(list)
for r in rows: d[r["sym"][:-4]].append(r)
md += ["", "## По монетам (≥ 2 всплеска)", "", "| монета | итог |", "|---|---|"]
for k, v in sorted(d.items(), key=lambda kv: -len(kv[1])):
    if len(v) >= 2: md.append(f"| {k} | " + stat(v).replace(" — мало", f" (мало) · " + ", ".join(f"{datetime.fromtimestamp(x['t_ms'] / 1000, L):%d.%m %H:%M}:{x['first']}" for x in v)) + " |")
(ROOT / "output" / "spike_report.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md[:34]))
