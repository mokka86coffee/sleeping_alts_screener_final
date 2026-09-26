#!/usr/bin/env python3
"""Разбор выгрузки data_get_study_values (TradingView + Coinglass-индикаторы владельца) и запись 10-минутной проверки в 3m_journal.json.
    python3 claude/research/tv_check.py <файл выгрузки> <ключ позиции scan:SYM> <цена> <vs_entry> <oi_30m> <crowd> <taker_5m> <вердикт>"""
import sys, json, datetime as dt
f, key, price, vs, oi30, crowd, taker, verdict = sys.argv[1:9]
t = open(f).read(); i = t.find("{"); d = json.loads(t[i:])
keep = {"Funding Rate": "funding", "Open Interest": "oi", "Liquidations": "liq", "Top traders long/short ratio positions": "tops",
        "CVD Divergence Insights": "cvd_div", "ADX and DI for v4": "adx", "Vortex Indicator": "vortex", "Volume Aggregated Spot & Futures": "vol_agg"}
tv = {}
for s in d.get("studies", []):
    n = s.get("name") or s.get("title")
    if n in keep:
        v = s.get("values") or s.get("plots") or {}
        tv[keep[n]] = {k: v[k] for k in list(v)[:4]}
scan, sym = key.rsplit(":", 1)
j = json.load(open("claude/research/3m_journal.json"))
rec = j[scan][sym]
chk = {"at": dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime("%H:%M"), "price": float(price), "vs_entry": vs, "oi_30m": oi30,
       "crowd": float(crowd), "taker_5m": taker, "tv": tv, "verdict": verdict}
rec.setdefault("checks", []).append(chk)
json.dump(j, open("claude/research/3m_journal.json", "w"), ensure_ascii=False, indent=2)
print(json.dumps(tv, ensure_ascii=False)[:500]); print("check записан:", key)
