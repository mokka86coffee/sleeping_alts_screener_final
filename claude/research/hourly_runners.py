#!/usr/bin/env python3
"""ЧАСОВАЯ СВЕРКА БЕГУНОВ (27.09, владелец: «проверяй раз в час монеты с биржи, у которых ход больше 40% за 24 часа, попали они к нам или
нет, если нет — дорабатывай»). По каждому USDT-перпу Binance с ходом ≥ +40% за сутки:
  старт хода — первый час после минимума 30 ч до максимума, где цена ≥ минимума × 1.10;
  видели ли мы монету ДО старта (или в первые 30 мин после) — выборка экрана (архив cq_v2/intraday), очередь (output/queue_log.jsonl, место ≤ 5),
  книги (entry во всех output/paper_*.jsonl); время первой встречи и сколько хода уже прошло к ней;
  если пропустили — что отсекло: оборот суток до старта (< 5M$), возраст листинга (< 180 дн экран / < 100 дн «пробуждение»), не было в выборке,
  или была, но не прошла правила; признаки до старта: интерес 1/3/6 ч, фандинг, толпа, доля покупателей, объём часа старта к медиане суток.
Пишет claude/research/missed.md (дописывает), состояние claude/research/hourly_runners_state.json (монету разбираем раз в сутки).
    python3 claude/research/hourly_runners.py
"""
from __future__ import annotations
import json, sys, time, statistics as st, datetime as dt
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                   # noqa: E402
L = dt.timezone(dt.timedelta(hours=3)); H = 3600_000
MD = BASE / "claude/research/missed.md"; ST = BASE / "claude/research/hourly_runners_state.json"


def hm(ms): return dt.datetime.fromtimestamp(ms / 1000, L).strftime("%d.%m %H:%M")


def sightings(sym):
    out = []
    p = BASE / "cq_v2/intraday" / f"{sym[:-4].lower()}.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines()[-400:]:
            try:
                r = json.loads(line); t = int(dt.datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() * 1000)
                out.append(("журнал (архив книг)", t, None))
            except Exception: pass
    for line in (BASE / "output/queue_log.jsonl").read_text(encoding="utf-8").splitlines()[-60000:]:
        if f'"{sym}"' not in line: continue
        try: r = json.loads(line)
        except ValueError: continue
        if r.get("in_queue") and r.get("place") and int(r["place"]) <= 5:
            out.append((f"очередь, место {r['place']}", int(dt.datetime.strptime(r["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp() * 1000), None))
    for p in (BASE / "output").glob("paper_*.jsonl"):
        for line in p.read_text(encoding="utf-8").splitlines()[-5000:]:
            if f'"{sym}"' not in line or '"entry"' not in line: continue
            try: r = json.loads(line)
            except ValueError: continue
            if r.get("kind") == "entry" and r.get("sym") == sym:
                out.append((f"книга «{r.get('book') or p.stem}»", int(float(r["at"]) * 1000), r.get("px")))
    return out


def analyse(sym, age_days):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "15m", "limit": 200}, quiet_400=True, weight=5) or []
    if len(k) < 150: return None
    t = [int(x[0]) for x in k]; c = [float(x[4]) for x in k]; h = [float(x[2]) for x in k]; l = [float(x[3]) for x in k]; qv = [float(x[7]) for x in k]; tb = [float(x[10]) for x in k]
    ihi = max(range(len(h)), key=lambda i: h[i]); j0 = max(0, ihi - 120)
    ilo = min(range(j0, ihi + 1), key=lambda i: l[i]); lo = l[ilo]
    ist = next((i for i in range(ilo, ihi + 1) if c[i] >= lo * 1.10), ihi)
    t_start = t[ist]; move = (h[ihi] / lo - 1) * 100
    qv24_before = sum(qv[max(0, ist - 96):ist])
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "15m", "limit": 200}, quiet_400=True) or []
    om = {int(x["timestamp"]): float(x["sumOpenInterestValue"]) for x in oi}
    def oi_at(ts): 
        ks = [kk for kk in om if kk <= ts]; return om[max(ks)] if ks else None
    o0 = oi_at(t_start); o1, o3, o6 = oi_at(t_start - H), oi_at(t_start - 3 * H), oi_at(t_start - 6 * H)
    fr = get_json("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": sym, "endTime": t_start, "limit": 3}, quiet_400=True) or []
    ls = get_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "15m", "endTime": t_start, "limit": 1}, quiet_400=True) or [{}]
    vol_x = (sum(qv[ist - 3:ist + 1]) / 4) / (st.median(qv[max(0, ist - 96):ist]) or 1) if ist >= 4 else None
    buy = sum(tb[ist - 3:ist + 1]) / max(sum(qv[ist - 3:ist + 1]), 1) * 100 if ist >= 4 else None
    seen = sightings(sym)
    before = [s for s in seen if s[1] <= t_start + 30 * 60_000]
    after = sorted([s for s in seen if s[1] > t_start + 30 * 60_000], key=lambda s: s[1])
    first_after = after[0] if after else None
    gain_at = None
    if first_after:
        i2 = max((i for i in range(len(t)) if t[i] <= first_after[1]), default=None)
        gain_at = (c[i2] / lo - 1) * 100 if i2 is not None else None
    cut = []
    if qv24_before < 5e6: cut.append(f"оборот суток до старта {qv24_before / 1e6:.1f}M$ < 5M$ (порог экрана)")
    if age_days is not None and age_days < 180: cut.append(f"листинг {age_days:.0f} дн < 180 (экран)" + (" и < 100 («пробуждение»)" if age_days < 100 else ""))
    in_universe = any(s[0] == "журнал (архив книг)" and s[1] <= t_start for s in seen)
    if not cut and not in_universe: cut.append("прошла бы пороги экрана, но не была в журнале к старту: книги видят только leaders/pump_leaders/near_move, а туда монета попадает после хода")
    if in_universe and not before: cut.append("была в выборке, но ни очередь, ни книги не взяли до старта")
    signs = dict(oi_1h=(o0 / o1 - 1) * 100 if o0 and o1 else None, oi_3h=(o0 / o3 - 1) * 100 if o0 and o3 else None, oi_6h=(o0 / o6 - 1) * 100 if o0 and o6 else None,
                 fund=[round(float(x["fundingRate"]) * 100, 3) for x in fr], crowd=ls[0].get("longShortRatio"), buy=buy, vol_x=vol_x)
    return dict(sym=sym, move=move, t_lo=t[ilo], t_start=t_start, t_hi=t[ihi], before=before, first_after=first_after, gain_at=gain_at, cut=cut, signs=signs, qv24_before=qv24_before, age=age_days)


def main():
    tk = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr") or []
    run = sorted([(x["symbol"], float(x["priceChangePercent"]), float(x["quoteVolume"])) for x in tk if x["symbol"].endswith("USDT") and float(x["priceChangePercent"]) >= 40], key=lambda x: -x[1])
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
    now = time.time() * 1000
    age = {s["symbol"]: (now - int(s.get("onboardDate") or 0)) / 86400_000 for s in info.get("symbols", [])}
    state = json.loads(ST.read_text()) if ST.exists() else {}
    stamp = dt.datetime.now(L).strftime("%d.%m %H:%M")
    lines, md = [], []
    for sym, pct, qv in run:
        r = analyse(sym, age.get(sym))
        if not r: continue
        f = lambda v, d=1: "—" if v is None else f"{v:+.{d}f}%"
        if r["before"]:
            b = min(r["before"], key=lambda s: s[1])
            lines.append(f"{sym[:-4]} +{pct:.0f}%: наша — {b[0]} в {hm(b[1])}, старт {hm(r['t_start'])}")
            continue
        fa = r["first_after"]
        late = f"увидели поздно: {fa[0]} в {hm(fa[1])}, уже +{r['gain_at']:.0f}% от минимума" if fa and r["gain_at"] is not None else "не увидели вообще"
        s = r["signs"]
        line = (f"{sym[:-4]} +{pct:.0f}% (ход {r['move']:.0f}%, старт {hm(r['t_start'])}, оборот {qv / 1e6:.0f}M$): ПРОПУСК — {late}; причина: "
                + ("; ".join(r["cut"]) or "не определена")
                + f"; до старта: интерес 1ч {f(s['oi_1h'])}, 3ч {f(s['oi_3h'])}, 6ч {f(s['oi_6h'])}, фандинг {s['fund']}, толпа {s['crowd']}, "
                  f"покупатели {('—' if s['buy'] is None else f'{s[chr(98)+chr(117)+chr(121)]:.0f}%')}, объём часа ×{(s['vol_x'] or 0):.1f}")
        lines.append(line)
        if state.get(sym, 0) < now - 20 * H:
            md.append(f"- **{stamp}** · {line} · https://www.coinglass.com/tv/Binance_{sym}")
            state[sym] = now
    if md:
        head = "" if MD.exists() else "# Пропущенные бегуны (hourly_runners.py, раз в час; ход ≥ +40% за сутки на Binance)\n\n"
        with MD.open("a", encoding="utf-8") as fh: fh.write(head + "\n".join(md) + "\n")
    ST.write_text(json.dumps(state))
    print(f"СВЕРКА {stamp}: бегунов {len(run)}, наших {sum(1 for x in lines if ': наша' in x)}, пропусков {sum(1 for x in lines if 'ПРОПУСК' in x)}")
    for x in lines: print("  " + x)


if __name__ == "__main__":
    main()
