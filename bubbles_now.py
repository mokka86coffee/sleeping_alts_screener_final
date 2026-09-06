#!/usr/bin/env python3
"""У кого сейчас есть пузыри рыночных заявок (бары за сутки с оборотом выше среднего на 2σ).
Читает output/coinglass_fetch.json — тот же ряд, что идёт на плиту журнала.
    python3 bubbles_now.py
"""
import json, statistics, time
from pathlib import Path
try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
d = json.loads((BASE_DIR / "output" / "coinglass_fetch.json").read_text(encoding="utf-8"))
out = []
for sym, c in (d.get("coins") or {}).items():
    ser = [b for b in ((c.get("fut") or {}).get("series") or []) if b.get("t") and b.get("b") is not None]
    if len(ser) < 8:
        continue
    vols = [float(b["b"] or 0) + float(b["s"] or 0) for b in ser]
    mu = statistics.mean(vols); sd = statistics.pstdev(vols)
    if not sd:
        continue
    for b, v in zip(ser, vols):
        if v >= mu + 2 * sd:
            side = "покупали" if float(b["b"] or 0) >= float(b["s"] or 0) else "продавали"
            out.append((v / mu, sym, time.strftime("%H:%M", time.gmtime(b["t"] / 1000)), v, side, abs(float(b["b"] or 0) - float(b["s"] or 0))))
out.sort(reverse=True)
if not out:
    print("пузырей нет: ни у кого бар не превысил среднее на 2σ")
for x, sym, hm, v, side, dl in out[:25]:
    print(f"{sym.replace('USDT',''):9s} {hm} UTC · оборот бара ${v/1e6:.1f}M (×{x:.1f} к среднему) · {side} на ${dl/1e6:.1f}M")
