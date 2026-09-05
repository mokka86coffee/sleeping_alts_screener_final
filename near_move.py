#!/usr/bin/env python3
"""БЛИЗКИЕ К ХОДУ (05.09) — фильтр по дневкам cq_v2, правило-кандидат из разбора
«почему пошли 4 и ARB (и CHIP), а BLESS/RIVER/BICO/SKYAI нет»:

  1. был СБОР за последние 1–5 дней: день с оборотом ≥ HARVEST_X норм (норма — медиана
     тридцати дней);
  2. оборот в затишье НЕ УПАЛ: медиана последних трёх дней ≥ LULL_X норм;
  3. плечо РАСТЁТ в ход: интерес сейчас ≥ интерес три дня назад × OI_GROW;
  4. есть кого выносить: шортов сгорело за три дня ≥ max(SHORT_MIN_USD, SHORT_MIN_OI × интерес);
  5. сбор УДЕРЖАН: закрытие не ниже (1 − GIVEBACK) от максимума сбора.

RIVER — контрпример к одному только первому признаку: три нормы оборота были продавца
(дельта минус каждый день, интерес сжимался, новое дно) — поэтому признаки берутся вместе.
Скор — сколько из пяти; «близкая» — все пять. Пишет output/near_move.json:
  {"at":…, "rule":…, "coins": {"4USDT": {"score":5, "near":true, "why":[…], "nums":{…}}}}

    python3 near_move.py --only 4,arb,bless     # печать по монетам
    python3 near_move.py --write                # все монеты архива → output/near_move.json
Пороги — наверху, калибруются по накопленным случаям (внутридневной архив).
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

HARVEST_X = 5.0      # сбор: оборот дня ≥ 5 норм
HARVEST_DAYS = 5     # в последние N дней
LULL_X = 2.5         # затишье: медиана оборота трёх дней ≥ 2.5 норм
OI_GROW = 1.10       # интерес сейчас ≥ ×1.10 к трём дням назад
SHORT_MIN_USD = 100_000.0
SHORT_MIN_OI = 0.005  # или ≥ 0.5% интереса
GIVEBACK = 0.35      # удержание: закрытие ≥ 65% от максимума сбора


def _rows(d: dict, key: str) -> list:
    rows = d.get(key) or []
    return sorted([r for r in rows if isinstance(r, dict) and r.get("datetime")], key=lambda r: r["datetime"])


def judge(d: dict) -> dict | None:
    o = _rows(d, "ohlcv")
    if len(o) < 35:
        return None
    oi = {r["datetime"][:10]: r for r in _rows(d, "oi")}
    lq = {r["datetime"][:10]: r for r in _rows(d, "liq")}
    vols = [float(r.get("quote_volume") or 0) for r in o]
    norm = statistics.median(vols[-40:-10]) or 0.0
    if not norm:
        return None
    last = o[-1]
    days = o[-HARVEST_DAYS:]
    why: list[str] = []
    nums: dict = {}
    # 1. сбор
    hv = [(r, float(r["quote_volume"]) / norm) for r in days if float(r["quote_volume"]) / norm >= HARVEST_X]
    if hv:
        hday, hx = max(hv, key=lambda t: t[1])
        why.append(f"сбор {hday['datetime'][5:10]} на ×{hx:.0f} норм")
        nums["harvest_x"] = round(hx, 1)
        nums["harvest_day"] = hday["datetime"][:10]
    # 2. затишье
    lull = statistics.median([float(r["quote_volume"]) / norm for r in o[-3:]])
    nums["lull_x"] = round(lull, 1)
    if lull >= LULL_X:
        why.append(f"оборот в затишье ×{lull:.1f} норм")
    # 3. плечо
    k_now, k_3 = last["datetime"][:10], o[-4]["datetime"][:10]
    oi_now = float((oi.get(k_now) or {}).get("open_interest") or 0)
    oi_3 = float((oi.get(k_3) or {}).get("open_interest") or 0)
    grow = (oi_now / oi_3) if oi_3 else 0.0
    nums["oi_grow"] = round(grow, 2)
    if grow >= OI_GROW:
        why.append(f"плечо ×{grow:.2f} за три дня")
    # 4. шорты
    sh = sum(float((lq.get(r["datetime"][:10]) or {}).get("short_liquidations_usd") or 0) for r in o[-3:])
    nums["shorts_3d_usd"] = round(sh, 0)
    if sh >= max(SHORT_MIN_USD, SHORT_MIN_OI * oi_now):
        why.append(f"шортов сгорело за три дня ${sh / 1e3:.0f}K")
    # 5. удержание
    if hv:
        # максимум сбора — по ЗАКРЫТИЯМ, не по теням: у ARB 03.09 в архиве тень 0.55 при цене 0.14,
        # и «удержание» уходило в минус семьдесят шесть на глюке одной свечи
        hi = max(float(r.get("close") or 0) for r in days)
        held = float(last["close"]) >= hi * (1 - GIVEBACK)
        nums["from_harvest_high"] = round((float(last["close"]) / hi - 1) * 100, 1) if hi else None
        if held:
            why.append(f"сбор удержан ({nums['from_harvest_high']:+.0f}% от максимума)")
    score = len(why)
    return {"score": score, "near": score >= 5, "why": why, "nums": nums, "close": float(last["close"]), "day": k_now}


def build(only: list[str] | None = None) -> dict:
    arch = BASE_DIR / "cq_v2"
    files = ([arch / f"{b.lower()}.json" for b in only] if only else
             sorted(p for p in arch.glob("*.json") if not p.name.startswith("_")))
    out = {"at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
           "rule": {"harvest_x": HARVEST_X, "harvest_days": HARVEST_DAYS, "lull_x": LULL_X, "oi_grow": OI_GROW,
                    "short_min_usd": SHORT_MIN_USD, "short_min_oi": SHORT_MIN_OI, "giveback": GIVEBACK},
           "coins": {}}
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        j = judge(d)
        if j:
            out["coins"][p.stem.upper() + "USDT"] = j
    out["near"] = sorted([s for s, v in out["coins"].items() if v["near"]],
                         key=lambda s: -(out["coins"][s]["nums"].get("lull_x") or 0))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    res = build([x.strip() for x in a.only.split(",")] if a.only else None)
    for sym, v in sorted(res["coins"].items(), key=lambda kv: -kv[1]["score"]):
        if a.only or v["score"] >= 4:
            print(f"{sym}: {v['score']}/5 {'БЛИЗКАЯ' if v['near'] else ''} · " + " · ".join(v["why"]) + f" · {v['nums']}")
    print(f"близких: {len(res['near'])} — {', '.join(res['near'])}")
    if a.write:
        p = BASE_DIR / "output" / "near_move.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"near_move: записано {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
