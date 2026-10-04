#!/usr/bin/env python3
"""ПЕРЕСЧЁТ ДНЯ, шаг 1 (03.10 16:45, владелец: «посчитай все сделки, как они бы были сегодня по новым правилам с самого начала суток, и внеси в бота»).
Трёхминутки Binance за ~50 часов по всем перпам бота (один запрос на монету, 6 потоков через общий ограничитель core_http) → pickle в scratchpad.
    .venv/bin/python claude/research/replay_fetch.py ПУТЬ.pkl [SYM ...]"""
import sys, pickle, time, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
out = Path(sys.argv[1]); syms = [s for s in sys.argv[2:]] or sorted(set(ft._all_perps()) | set(json.loads((ft.BASE_DIR / "output" / "paper_fast3.json").read_text()).get("open", {})) if False else set(ft._all_perps()))
import json
try: syms = sorted(set(syms) | set(json.loads((ft.BASE_DIR / "output" / "paper_fast3.json").read_text()).get("open", {})))
except Exception: pass
def one(s):
    k = ft.get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": s, "interval": "3m", "limit": int(os.environ.get("REPLAY_BARS", "1000"))}, quiet_400=True, weight=5) or []
    return s, k
t = time.time(); K = {}
with ThreadPoolExecutor(6) as ex:
    for s, k in ex.map(one, syms):
        if len(k) > 100: K[s] = k
old = {}
if out.exists() and len(sys.argv) > 2:
    old = pickle.load(open(out, "rb"))["K"]
old.update(K)
pickle.dump(dict(at=time.time(), K=old), open(out, "wb"))
print(f"монет {len(K)} из {len(syms)} за {time.time() - t:.0f} с; всего в файле {len(old)}")
