#!/usr/bin/env python3
"""ВСПЛЕСКИ ОБЪЁМА НА 3-МИНУТКЕ, BINANCE (26.09, владелец: «можем ли мы определять то же самое?», «сгенерируй ссылки на coinglass»).
Как у чужого бота: последняя закрытая трёхминутка с объёмом ≥ X × медианы предыдущих 30 трёхминуток и ценой ≥ +P% к прошлому закрытию.
Рядом — наши признаки, без которых всплеск не вход (R39): интерес за час и за 6 ч, фандинг, тейкер-покупки, ход за 8 ч.
    python3 claude/research/spike3m.py            # скан всех USDT-перпов Binance, ссылки coinglass
"""
from __future__ import annotations
import sys, time, statistics as stt
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
from core_http import get_json                                     # noqa: E402

X, P, MINQ, LOOK = 10.0, 1.5, 50_000, 20      # LOOK — сколько последних трёхминуток смотрим (20 = час)


def scan(sym):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": 52}, quiet_400=True, weight=1) or []
    if len(k) < 52:
        return None
    k = k[:-1]                                              # закрытые; ищем последний всплеск за LOOK трёхминуток
    qv = [float(x[7]) for x in k]; c = [float(x[4]) for x in k]
    for i in range(len(k) - 1, len(k) - 1 - LOOK, -1):
        med = stt.median(qv[max(0, i - 30):i])
        if med <= 0 or qv[i] < MINQ or qv[i] < X * med:
            continue
        chg = (c[i] / c[i - 1] - 1) * 100
        if chg < P:
            continue
        tb = float(k[i][10]) / (qv[i] or 1) * 100
        return dict(sym=sym, x=qv[i] / med, chg=chg, qv=qv[i], tb=tb, t=int(k[i][0]), ago=(len(k) - 1 - i) * 3,
                    since=(c[-1] / c[i] - 1) * 100)
    return None


def confirm(r):
    s = r["sym"]
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": s, "period": "15m", "limit": 25}, quiet_400=True) or []
    ov = [float(x["sumOpenInterestValue"]) for x in oi]
    r["oi1h"] = (ov[-1] / ov[-5] - 1) * 100 if len(ov) >= 5 and ov[-5] else None
    r["oi6h"] = (ov[-1] / ov[0] - 1) * 100 if len(ov) >= 25 and ov[0] else None
    pr = get_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": s}, quiet_400=True) or {}
    r["fund"] = float(pr.get("lastFundingRate") or 0) * 100
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": s, "interval": "1h", "limit": 9}, quiet_400=True) or []
    r["h8"] = (float(k[-1][4]) / float(k[0][4]) - 1) * 100 if len(k) >= 9 else None
    return r


def main():
    info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
    syms = [s["symbol"] for s in info.get("symbols", []) if s["symbol"].endswith("USDT") and s.get("status") == "TRADING"]
    t0 = time.time()
    with ThreadPoolExecutor(8) as ex:
        hits = [r for r in ex.map(scan, syms) if r]
    hits.sort(key=lambda r: -r["x"])
    with ThreadPoolExecutor(4) as ex:
        hits = list(ex.map(confirm, hits))
    ts = time.strftime("%H:%M UTC", time.gmtime())
    print(f"скан {ts} · перпов {len(syms)} · всплесков за последний час (объём ≥ ×{X:.0f}, цена ≥ +{P}%): {len(hits)} · {time.time() - t0:.0f} с")
    for r in hits:
        f = lambda v, d=1: "—" if v is None else f"{v:+.{d}f}%"
        print(f"  https://www.coinglass.com/tv/Binance_{r['sym']}  {r['sym'][:-4]:10} {r['ago']:2d} мин назад: 3м {r['chg']:+.2f}% · объём ×{r['x']:.1f} ({r['qv'] / 1e3:.0f}K$) · с тех пор {r['since']:+.1f}% · "
              f"покупатели {r['tb']:.0f}% · интерес 1ч {f(r['oi1h'])} · 6ч {f(r['oi6h'])} · фандинг {r['fund']:+.3f}% · за 8ч {f(r['h8'])}")


if __name__ == "__main__":
    main()
