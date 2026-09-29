#!/usr/bin/env python3
"""СИГНАЛЫ КАНАЛА «Volume Spikes» 29.09 НА COINGLASS BINANCE (владелец 29.09: «все заново — смотри только коингласс на тех же тф с теми же индикаторами,
по 10 за раз и дальше жди «да»»; биржа Bybit в подписях канала — рефка автора, вся активность на Binance). Те же снимки, что у сделок бота:
1D / 6h / 1h / 30m, «мои» индикаторы + ликвидации + базис, вертикаль — время поста в канале (UTC+3), горизонталь — цена Binance на баре поста.
    .venv/bin/python claude/research/spikes/cg_signals.py 0 10      # сигналы 0..9 → spikes/shots/*.png и cgx/
"""
import json, sys, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
HERE = Path(__file__).parent; sys.path.insert(0, str(HERE.parent))
import cg_review as R
L = timezone(timedelta(hours=3))
a, b = int(sys.argv[1]), int(sys.argv[2])
S = json.load(open(HERE / "signals.json"))[a:b]
B = []
for s in S:
    sym = s["sym"] + "USDT"
    h, m = map(int, s["time"].split(":"))
    t = datetime(2026, 9, 29, h, m, tzinfo=L).timestamp()
    try:
        k = json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=3m&startTime={int(t*1000-1800e3)}&endTime={int(t*1000+180e3)}&limit=20", timeout=20))
    except Exception as e:
        print(sym, "нет на Binance futures:", str(e)[:50]); continue
    bar = max((x for x in k if x[0] + 180_000 <= t * 1000 + 30_000), key=lambda x: x[0])
    B.append(dict(sym=sym, side=1, t_in=t, t_out=t + 1, px_in=float(bar[4]), px_out=0, res=0, why="сигнал", book="канал", rule="", label=f"СИГНАЛ {s['time']} {s['chg']}% ×{s['volx']}"))
json.dump(B, open(HERE / f"sig_{a}_{b}.json", "w"), ensure_ascii=False, indent=0)
R.trades = lambda: B
R.RD = HERE / "shots"
R.PROF = R.ROOT / "output" / f"cg_profile_sig_{a}"
sys.argv = [sys.argv[0]]
raise SystemExit(R.main())
