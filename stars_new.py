#!/usr/bin/env python3
"""ЗВЁЗДЫ «НОВЫЕ» (06.10.2026, владелец после RLC: «запиши это как главный признак для звёзд», «пусть все они будут в новых, все остальное
убери с экрана», «и звезды также должны приходить с причиной»).

Два признака, монета с любым из них — звезда «новые» (счёт на 456 монетах за пять недель — claude/research/movers_sign.md):
  1. ГЛАВНЫЙ: за окно STARS_NEW_FUEL_H часов интерес в МОНЕТАХ вырос от STARS_NEW_FUEL_OI_MIN % (с 10.10 01:54 UTC — 10 %) при цене не ниже начала окна.
     Условие по фандингу выключено (STARS_NEW_FUEL_FUND_ON); если фандинг всё окно в минусе — признак называется «шорты — топливо», иначе «интерес растёт».
  2. СКАЧОК ИНТЕРЕСА: интерес в монетах к тому, что был 5 дней назад, — от STARS_NEW_OI5D_X раз.
Источник — пульс скринера (pulse.json: неделя, шаг — прогон; старше — pulse_archive/). Интерес в монетах = oi_usd / price. Время — UTC (секунды эпохи).
Экран (render_intro.collect_items) и Телеграм (send_brief_telegram._new_soon) берут список отсюда; выключатель — STARS_NEW_ONLY в core_config.
    .venv/bin/python stars_new.py            # список сейчас, с причинами
"""
from __future__ import annotations

import gzip
import json
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

STARS_OFF = True            # 10.10 UTC, владелец: «убери звезды вообще свои» — звёзды «новые» не собираются: collect() даёт пустой список,
                            # экран «новые», Телеграм и кристаллы сайта пусты. За сутки 10.10 по признаку было 19 звёзд, медиана −2 %, до ×2 ни одной.
                            # False — вернуть как было. Прежние звёзды («скоро / могут») этим не возвращаются (STARS_NEW_ONLY в core_config).
FRESH_S = 3 * 3600          # показание старше — монета из пульса выпала, не судим
JUMP_ALONE = False          # 07.10 владелец по LYN на экране (−30 % за сутки, «раздача после пика», а стоит звездой за один скачок интереса): «снова шансы 20 из 100»,
                            # «как казино»; до этого: «идем в точность и в уменьшение количества». Один скачок интереса звездой не делает — звезда только с главным
                            # признаком (шорты — топливо: интерес в монетах растёт, фандинг в минусе, цена не падает). Скачок остаётся пометкой у такой звезды.
                            # Счёт: в списке 06.10 07:15 UTC +10 % за день дали 4 из 9 монет с главным признаком и 0 из 3 с одним скачком; за пять недель скачок
                            # при стоящей цене — ×2 в 3 случаях из 76. True — вернуть, как было 06.10 (любой из двух признаков)
D = 86400


def _cfg() -> tuple[float, float, set]:
    try:
        from core_config import STARS_NEW_FUEL_H as h, STARS_NEW_OI5D_X as x, STARS_NEW_SKIP as sk
    except ImportError:
        h, x, sk = 8, 1.16, []
    return float(h), float(x), {str(s).upper() for s in sk}


def _fuel_min() -> tuple[float, float, bool]:
    """10.10 владелец: порог роста интереса за окно (%), порог фандинга (%, по модулю) и нужен ли фандинг вообще (с 10.10 01:54 UTC — нет)"""
    try:
        from core_config import STARS_NEW_FUEL_OI_MIN as a, STARS_NEW_FUEL_FUND_MIN as b, STARS_NEW_FUEL_FUND_ON as c
    except ImportError:
        a, b, c = 10.0, 0.03, False
    return float(a), float(b), bool(c)


def _rows(rs: list) -> list[tuple]:
    """(время, интерес в монетах, цена, фандинг) — только показания с интересом и ценой"""
    return [(float(r["t"]), float(r["oi_usd"]) / float(r["price"]), float(r["price"]), r.get("funding"))
            for r in rs if r.get("oi_usd") and r.get("price") and r.get("t")]


def _archive(t_from: float, t_to: float) -> dict:
    """показания из архива пульса за дни, покрывающие [t_from, t_to] (UTC-сутки в имени файла)"""
    out: dict = {}
    d = int(t_from // D) * D
    while d <= t_to:
        f = BASE_DIR / "pulse_archive" / (datetime.fromtimestamp(d, timezone.utc).strftime("%Y-%m-%d") + ".jsonl.gz")
        d += D
        if not f.exists():
            continue
        try:
            with gzip.open(f, "rt", encoding="utf-8") as fh:
                for ln in fh:
                    try:
                        r = json.loads(ln)
                    except ValueError:
                        continue
                    if r.get("oi_usd") and r.get("price") and t_from <= float(r.get("t") or 0) <= t_to:
                        out.setdefault(r["sym"], []).append((float(r["t"]), float(r["oi_usd"]) / float(r["price"]), float(r["price"]), r.get("funding")))
        except OSError:
            continue
    return out


def collect(now: float | None = None) -> list[dict]:
    """звёзды «новые», ярчайшая первой; у каждой — sub (группы через « ‖ », как у прежних звёзд) и why (полный довод)"""
    if STARS_OFF:
        return []
    now = time.time() if now is None else now
    H, X, skip = _cfg()
    try:
        pulse = json.loads((BASE_DIR / "pulse.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    arch = None
    out = []
    for sym, rs in pulse.items():
        if sym == "_meta" or sym.replace("USDT", "").upper() in skip:
            continue
        r = _rows(rs)
        if len(r) < 3 or now - r[-1][0] > FRESH_S:
            continue
        t, oi, px, fu = r[-1]
        oi_min7 = min(x[1] for x in r)
        px_min7 = min(x[2] for x in r)
        # 1. шорты — топливо
        w = [x for x in r if x[0] >= t - H * 3600]
        _oi_min, _fu_min, _fu_on = _fuel_min()
        neg = len(w) >= 3 and all(x[3] is not None and x[3] < 0 for x in w)                       # фандинг всё окно в минусе — тогда это «шорты — топливо»
        fuel = (len(w) >= 3 and t - w[0][0] >= 0.75 * H * 3600 and oi > w[0][1] and px >= w[0][2]
                and (oi / w[0][1] - 1) * 100 >= _oi_min                                          # 10.10 владелец «да»: рост интереса за окно от 10 %
                and (not _fu_on or (neg and fu is not None and fu <= -_fu_min)))                 #   без условия по фандингу (STARS_NEW_FUEL_FUND_ON)
        # 2. скачок интереса за 5 дней: показание из окна [t−6 дн, t−5 дн+3 ч] — из пульса, иначе из архива
        old = [x for x in r if t - 6 * D <= x[0] <= t - 5 * D + 3 * 3600]
        if not old:
            if arch is None:
                arch = _archive(now - 6 * D - FRESH_S, now - 5 * D + 3 * 3600)
            old = sorted(x for x in arch.get(sym, []) if t - 6 * D <= x[0] <= t - 5 * D + 3 * 3600)
        oi5 = oi / old[-1][1] if old and old[-1][1] else None
        px5 = px / old[-1][2] if old and old[-1][2] else None
        jump = oi5 is not None and oi5 >= X
        if not (fuel or (jump and JUMP_ALONE)):
            continue
        name = sym.replace("USDT", "")
        head = " · ".join(n for n, ok in (("шорты — топливо" if neg else "интерес растёт", fuel), ("скачок интереса", jump)) if ok)
        g_oi = [f"×{oi / oi_min7:.1f} к минимуму недели"]
        if len(w) >= 2 and w[0][1]:
            g_oi.append(f"за {H:.0f} ч {(oi / w[0][1] - 1) * 100:+.0f}%")
        if oi5 is not None:
            g_oi.append(f"за 5 дн ×{oi5:.2f}")
        g_fu = [f"{fu:+.3f}%" if fu is not None else "—"]
        if fuel and neg:
            g_fu.append(f"в минусе все {H:.0f} ч")
        g_px = []
        if len(w) >= 2 and w[0][2]:
            g_px.append(f"за {H:.0f} ч {(px / w[0][2] - 1) * 100:+.0f}%")
        if px5 is not None:
            g_px.append(f"за 5 дн ×{px5:.2f}")
        g_px.append(f"от минимума недели ×{px / px_min7:.2f}")
        sub = " ‖ ".join([head, "интерес: " + " · ".join(g_oi), "фандинг: " + " · ".join(g_fu), "цена: " + " · ".join(g_px)])
        why = []
        if fuel and neg:
            why.append(f"шорты — топливо: за {H:.0f} ч интерес в монетах вырос на {(oi / w[0][1] - 1) * 100:+.0f}%, фандинг всё это время в минусе, цена не упала — новые позиции это шорты, их выкупают")
        elif fuel:
            why.append(f"интерес растёт: за {H:.0f} ч интерес в монетах вырос на {(oi / w[0][1] - 1) * 100:+.0f}% при цене не ниже начала окна (10.10: без условия по фандингу)")
        if jump:
            why.append(f"скачок интереса: в монетах ×{oi5:.2f} за 5 дней при цене ×{px5:.2f} (в счёте 06.10 такие дали ×2 в 15 случаях из 227 против 29 из 2040)")
        why.append(f"интерес ×{oi / oi_min7:.1f} к минимуму недели · фандинг {fu:+.3f}%" if fu is not None else f"интерес ×{oi / oi_min7:.1f} к минимуму недели")
        grow = (oi / w[0][1] - 1) * 100 if (len(w) >= 2 and w[0][1]) else 0.0
        out.append({"n": name, "sym": sym, "g": 0, "sub": sub, "why": " · ".join(why), "run": None, "dd": None, "fuel": fuel, "jump": jump,
                    "rel": grow if fuel else (oi5 or 0.0), "t": t})
    # порядок: главный признак (шорты — топливо) первым — с обоими признаками выше, внутри по росту интереса за окно; дальше одни скачки — по размеру скачка.
    # На экран идут первые MAX_NAMES; яркость — по месту, от 1.0 к 0.45.
    out.sort(key=lambda it: (not it["fuel"], not it["jump"] if it["fuel"] else False, -it["rel"]))
    for i, it in enumerate(out):
        it["bright"] = 1.0 if len(out) < 2 else max(0.45, 1.0 - 0.55 * i / 11)
    return out


if __name__ == "__main__":
    for it in collect():
        print(it["n"]); [print("   " + p) for p in it["sub"].split(" ‖ ")]
