#!/usr/bin/env python3
"""ПРОВЕРКА ПО МОНЕТАМ: ЧТО ГДЕ РАБОТАЕТ (30.09, владелец: «проверь, что и где работает, а что нет по монетам»).
По каждой монете из журнала сборщика и сделок быстрого бота — какие источники фона есть:
  liq_stream — поток ликвидаций OKX+Bybit за последние 3 дня (часы с событиями, крупнейший час) — на нём бот считает выход по выносу и вход в шорт;
  coinglass  — ликвидации Coinglass (все биржи) в выгрузке cgx/ — есть ли ненулевые бары;
  spot       — спот Binance (CVD 7 дн: у монет без спота None);
  hist90     — есть ≥ 30 дн дневной истории (иначе ×90, % от максимума не считаются);
  oi, fund, crowd — интерес, фандинг, толпа по счетам в момент всплеска (из журнала);
  bubble     — считается ли пузырь (дельта бара)
    .venv/bin/python coin_check.py     → output/coin_check.md"""
import json, sys
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parent; L = timezone(timedelta(hours=3))
sys.path.insert(0, str(ROOT))
def cl(v): return v if isinstance(v, (int, float)) and v == v else None
# 1) монеты
coins = defaultdict(lambda: {"spikes": [], "trades": 0})
for ln in open(ROOT / "output" / "spike_log.jsonl"):
    r = json.loads(ln)
    if r["kind"] == "spike": coins[r["sym"]]["spikes"].append(r)
tr = ROOT / "claude" / "research" / "cgr" / "trades.json"
if tr.exists():
    for x in json.load(open(tr)): coins[x["sym"]]["trades"] += 1
# 2) поток ликвидаций за 3 дня
import fast_tier as ft
hl = ft._liq_hourly(); now_h = int(datetime.now(timezone.utc).timestamp() // 3600 * 3600 * 1000)
def stream(sym):
    v = {}
    for side in ("long", "short"):
        d = hl.get((sym, side)) or {}
        v[side] = [(h, x) for h, x in d.items() if h >= now_h - 72 * 3_600_000]
    hrs = {h for s in v.values() for h, _ in s}
    return len(hrs), max([x for s in v.values() for _, x in s], default=0)
# 3) Coinglass
def cg(sym):
    f = ROOT / "claude" / "research" / "cgx" / f"{sym}_15.json"
    if not f.exists(): return None
    R = json.load(open(f))["rows"]; n = sum(1 for r in R if any(cl(r.get(k)) for k in ("liq_long", "liq_short")))
    return n, len(R)
rows = []
for sym, c in sorted(coins.items(), key=lambda kv: -len(kv[1]["spikes"]) - kv[1]["trades"]):
    sp = c["spikes"]; h, mx = stream(sym); g = cg(sym)
    def have(k): return sum(1 for r in sp if cl(r.get(k)) is not None)
    rows.append(dict(sym=sym[:-4], n=len(sp), tr=c["trades"], stream_h=h, stream_max=round(mx), cg=g,
                     spot=(have("spot_cvd7") if sp else None), hist90=(have("hi90") if sp else None), oi=(have("oi1h") if sp else None),
                     fund=(have("fund") if sp else None), crowd=(have("crowd") if sp else None), bub=(have("bub_dz") if sp else None)))
md = ["# Проверка по монетам: что где работает (%s)" % datetime.now(L).strftime("%d.%m %H:%M"), "",
      "n — всплесков сборщика; сд — закрытых сделок бота; поток — часов с ликвидациями OKX+Bybit за 3 дня (макс. час, $); CG — баров Coinglass с ликвидациями из всех; "
      "остальное — сколько из n всплесков имело поле (спот CVD, история 90 дн, интерес, фандинг, толпа, пузырь).", "",
      "| монета | n | сд | поток ч / макс $ | CG баров | спот | 90 дн | интерес | фанд | толпа | пузырь |", "|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    f = lambda v, n: "—" if v is None else f"{v}/{n}"
    md.append(f"| {r['sym']} | {r['n']} | {r['tr']} | {r['stream_h']} / {r['stream_max']} | {('—' if r['cg'] is None else str(r['cg'][0]) + '/' + str(r['cg'][1]))} | "
              f"{f(r['spot'], r['n'])} | {f(r['hist90'], r['n'])} | {f(r['oi'], r['n'])} | {f(r['fund'], r['n'])} | {f(r['crowd'], r['n'])} | {f(r['bub'], r['n'])} |")
tot = len(rows)
no_stream = [r["sym"] for r in rows if r["stream_h"] == 0]
no_spot = [r["sym"] for r in rows if r["n"] and r["spot"] == 0]
no_hist = [r["sym"] for r in rows if r["n"] and r["hist90"] == 0]
no_cg = [r["sym"] for r in rows if r["cg"] is None or r["cg"][0] == 0]
md += ["", f"**Итог по {tot} монетам:**", f"- без ликвидаций в потоке OKX+Bybit за 3 дня: {len(no_stream)} — {', '.join(no_stream[:40])}",
       f"- без спота Binance: {len(no_spot)} — {', '.join(no_spot[:40])}", f"- без 30 дн истории (нет ×90 и % от макс.): {len(no_hist)} — {', '.join(no_hist[:40])}",
       f"- без ликвидаций Coinglass в выгрузке: {len(no_cg)} — {', '.join(no_cg[:40])}"]
(ROOT / "output" / "coin_check.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md[-6:]))
