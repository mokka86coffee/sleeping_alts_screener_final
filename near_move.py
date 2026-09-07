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


def _load_live() -> dict:
    """Живой день — из ОБЩЕГО модуля live_day (06.09): один код на репутацию, фильтр и всё,
    что смотрит «сейчас»; здесь только вызов."""
    try:
        from live_day import load_live
        return load_live()
    except ImportError:
        return {}


def _live_row(sym_usdt: str, src: dict) -> dict | None:
    try:
        from live_day import live_rows
        return live_rows(sym_usdt, src)
    except ImportError:
        return None


def _rows(d: dict, key: str) -> list:
    rows = d.get(key) or []
    return sorted([r for r in rows if isinstance(r, dict) and r.get("datetime")], key=lambda r: r["datetime"])


def _today_bars(sym_usdt: str) -> dict | None:
    """СЕГОДНЯ ПО БАРАМ (06.09, случай FLOCK против 4/ZEN/UNI/CHIP): из внутридневного архива —
    дельта дня, ход интереса с первого бара, доминирующий тип часа. Это то, чего дневки не видят:
    из одной группы «брать» утром покупают одну, продают три."""
    from datetime import datetime, timezone
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym_usdt.replace('USDT', '').lower()}.jsonl"
    if not p.exists():
        return None
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines()[-80:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("candle", ""))[:10] == today:
            rows.append(r)
    if len(rows) < 4:
        return None
    d = sum(((r.get("fut") or {}).get("d") or 0) for r in rows)
    b = sum(((r.get("fut") or {}).get("b") or 0) for r in rows)
    sl = sum(((r.get("fut") or {}).get("s") or 0) for r in rows)
    oi0 = next((r.get("oi") for r in rows if r.get("oi")), None)
    oi1 = next((r.get("oi") for r in reversed(rows) if r.get("oi")), None)
    types: dict = {}
    for r in rows:
        t = r.get("oi_type")
        if t and t != "flat":
            types[t] = types.get(t, 0) + 1
    dom = max(types, key=types.get) if types else None
    oi_chg = (oi1 / oi0 - 1) if oi0 and oi1 else None
    buying = d > 0 and (oi_chg is None or oi_chg >= 0) and dom in (None, "long_open", "short_close")
    selling = d < 0 and (oi_chg is not None and oi_chg < 0 or dom in ("long_close", "short_open"))
    return {"bars": len(rows), "delta": round(d, 0), "taker": round(b / sl, 3) if sl else None,
            "oi_chg_pct": round(oi_chg * 100, 1) if oi_chg is not None else None, "dominant": dom,
            "today": "покупают сегодня" if buying else ("продают сегодня" if selling else "стоит")}


def _oi_from_intraday(sym_usdt: str, days: int = 3) -> tuple | None:
    """Интерес из внутридневного архива: первый и последний за `days` дней (Coinglass)."""
    from datetime import datetime, timezone, timedelta
    if not sym_usdt:
        return None
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym_usdt.replace('USDT', '').lower()}.jsonl"
    if not p.exists():
        return None
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:00Z")
    vals = []
    for line in p.read_text(encoding="utf-8").splitlines()[-400:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if str(r.get("candle", "")) >= since and r.get("oi"):
            vals.append(float(r["oi"]))
    return (vals[0], vals[-1]) if len(vals) >= 2 else None


def judge(d: dict, live: dict | None = None) -> dict | None:
    o = _rows(d, "ohlcv")
    if len(o) < 35:
        return None
    oi = {r["datetime"][:10]: r for r in _rows(d, "oi")}
    lq = {r["datetime"][:10]: r for r in _rows(d, "liq")}
    if live and live["datetime"][:10] > o[-1]["datetime"][:10]:
        o = o + [live]
        oi[live["datetime"][:10]] = {"open_interest": live.get("open_interest")}
        lq[live["datetime"][:10]] = {"short_liquidations_usd": live.get("short_liquidations_usd")}
    vols = [float(r.get("quote_volume") or 0) for r in o]
    norm = statistics.median(vols[-40:-10]) or 0.0
    if not norm:
        return None
    last = o[-1]
    days = o[-HARVEST_DAYS:]
    why: list[str] = []
    nums: dict = {}
    # 1. сбор — оборот ≥ HARVEST_X норм ИЛИ ДНЕВНОЙ ПУЗЫРЬ (07.09, владелец: «у BLESS bubbles был
    #    на дне»): день за 14 дней с рыночной покупкой выше среднего на 2σ за 90 дней при цене в 15%
    #    от 90-дневного дна — крупная покупка у дна считается сбором, даже если оборот не в разы
    tr = {r["datetime"][:10]: r for r in _rows(d, "trade")}
    buys90 = [float((tr.get(r["datetime"][:10]) or {}).get("quote_buy_volume") or 0) for r in o[-90:]]
    mu_b = statistics.mean(buys90) if buys90 else 0.0
    sd_b = statistics.pstdev(buys90) if len(buys90) > 5 else 0.0
    low90 = min(float(r.get("low") or r["close"]) for r in o[-30:])   # «дно» — полка последнего месяца, не полугодовое
    bubble = None
    for r in o[-14:]:
        t = tr.get(r["datetime"][:10]) or {}
        bq = float(t.get("quote_buy_volume") or 0); sq = float(t.get("quote_sell_volume") or 0)
        if sd_b and bq >= mu_b + 2 * sd_b and bq > sq and float(r["close"]) <= low90 * 1.15:
            bubble = (r, bq / max(1.0, mu_b))
    if bubble:
        nums["bubble_day"] = bubble[0]["datetime"][:10]
        nums["bubble_x"] = round(bubble[1], 1)
    hv = [(r, float(r["quote_volume"]) / norm) for r in days if float(r["quote_volume"]) / norm >= HARVEST_X]
    if not hv and bubble and bubble[0] in days:
        hv = [(bubble[0], float(bubble[0]["quote_volume"]) / norm)]
        why.append(f"пузырь у дна {bubble[0]['datetime'][5:10]}: покупка ×{bubble[1]:.1f} к среднему")
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
    if not oi_now or not oi_3:
        # ПЛЕЧО ИЗ АРХИВА (06.09, случай RAYSOL: у кванта интерес пустой пять дней — фильтр
        # снял признак, а Coinglass видел ×4 за сутки): берём интерес из cq_v2/intraday —
        # первый за три дня и последний
        _ia = _oi_from_intraday(d.get("_sym") or "", days=3)
        if _ia:
            oi_3, oi_now = _ia
            nums["oi_src"] = "intraday"
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
    # РЕЖИМ ХОДА (07.09, владелец: FLOCK против BULLA) — в день сбора интерес рос вместе с ценой
    # («поднять и трясти», лестница: тряска — место покупки) или рухнул («поднять много и резко»,
    # парабола на выносе шортов: первая тряска — выход). Считаем по дню сбора: OI дня к OI накануне.
    mode = None
    if hv:
        hday = hv[0][0] if len(hv) == 1 else max(hv, key=lambda t: t[1])[0]
        idx = next((i for i, r in enumerate(o) if r["datetime"][:10] == hday["datetime"][:10]), None)
        if idx and idx > 0:
            oi_h = float((oi.get(o[idx]["datetime"][:10]) or {}).get("open_interest") or 0)
            oi_p = float((oi.get(o[idx - 1]["datetime"][:10]) or {}).get("open_interest") or 0)
            if oi_h and oi_p:
                r_oi = oi_h / oi_p
                nums["oi_on_harvest"] = round(r_oi, 2)
                if r_oi >= 1.15:
                    mode = "лестница"          # интерес рос вместе с ценой — набирали
                elif r_oi <= 0.75:
                    mode = "парабола"          # интерес рухнул — вынос шортов, не набор
                else:
                    mode = "неясно"
    score = len(why)          # счёт признаков — до пометки режима
    if mode:
        nums["mode"] = mode
        why.append("режим: " + mode + (" (интерес рос с ценой)" if mode == "лестница" else " (интерес рухнул — вынос шортов)" if mode == "парабола" else ""))
    # ЧЕТЫРЕ ГРУППЫ (06.09, владелец): одна подпись «близкая» смешивала тех, кто уже идёт, с теми,
    # у кого ход впереди. Делим по положению цены и плечу:
    #   going    — идёт: сбор вчера-сегодня и цена на максимуме (второй акт уже идёт);
    #   holding  — держат после сбора: сбор 1–5 дн назад, цена в пределах 10% от максимума,
    #              плечо и оборот приходят — ЭТО «близкие», ход впереди;
    #   pulled   — откатились: пять из пяти, но цена отдала 10–35% — откат или начало отдачи;
    #   giving   — отдают: сбор был, оборот и шорты есть, а плечо уходит (×<1) — второй акт не
    #              сложился, отскоки — кандидаты на шорт.
    grp = None
    fh = nums.get("from_harvest_high")
    if score >= 5:
        recent = (nums.get("harvest_day") or "") >= o[-2]["datetime"][:10]
        if fh is not None and fh >= -3 and recent:
            grp = "going"
        elif fh is not None and fh >= -10:
            grp = "holding"
        else:
            grp = "pulled"
    elif score == 4 and grow and grow < 1.0 and hv:
        grp = "giving"
    return {"score": score, "near": grp == "holding", "group": grp, "why": why, "nums": nums,
            "close": float(last["close"]), "day": k_now, "live": bool(last.get("_live"))}


def attach_today(sym_usdt: str, j: dict) -> dict:
    tb = _today_bars(sym_usdt)
    if tb:
        j["today"] = tb
        if j.get("group") in ("holding", "going", "pulled"):
            j["sub"] = tb["today"]          # «покупают сегодня» / «продают сегодня» / «стоит» — во всех живых группах
    return j


def build(only: list[str] | None = None) -> dict:
    arch = BASE_DIR / "cq_v2"
    files = ([arch / f"{b.lower()}.json" for b in only] if only else
             sorted(p for p in arch.glob("*.json") if not p.name.startswith("_")))
    out = {"at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
           "rule": {"harvest_x": HARVEST_X, "harvest_days": HARVEST_DAYS, "lull_x": LULL_X, "oi_grow": OI_GROW,
                    "short_min_usd": SHORT_MIN_USD, "short_min_oi": SHORT_MIN_OI, "giveback": GIVEBACK},
           "coins": {}}
    src = _load_live()
    for p in files:
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d["_sym"] = p.stem.upper() + "USDT"
        j = judge(d, _live_row(p.stem.upper() + "USDT", src))
        if j:
            out["coins"][p.stem.upper() + "USDT"] = attach_today(p.stem.upper() + "USDT", j)
    def _lst(g):
        return sorted([s for s, v in out["coins"].items() if v.get("group") == g],
                      key=lambda s: -(out["coins"][s]["nums"].get("lull_x") or 0))
    out["going"], out["holding"], out["pulled"], out["giving"] = _lst("going"), _lst("holding"), _lst("pulled"), _lst("giving")
    out["near"] = out["holding"]          # «близкие» = держат после сбора
    for g in ("holding", "going", "pulled"):
        out[g + "_buying"] = [s2 for s2 in out[g] if (out["coins"][s2].get("today") or {}).get("today") == "покупают сегодня"]
        out[g + "_selling"] = [s2 for s2 in out[g] if (out["coins"][s2].get("today") or {}).get("today") == "продают сегодня"]
    # ОЧЕРЕДЬ (07.09, владелец: «кто пойдёт раньше — туда размер»): по трём ходам недели второй акт
    # приходил через 1–5 дней после сбора у тех, у кого интерес продолжал расти, а в день хода бары
    # покупали. Балл: близость срока к 2–3 дням + рост интереса + покупают сегодня.
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).date()
    queue = []
    for s2 in out["holding"] + out["going"] + out["pulled"]:
        v = out["coins"][s2]; n = v.get("nums") or {}
        try:
            days = (today - datetime.strptime(n.get("harvest_day", ""), "%Y-%m-%d").date()).days
        except ValueError:
            days = None
        t_score = 1.0 if days in (2, 3) else 0.7 if days in (1, 4) else 0.4 if days == 5 else 0.2
        g_score = min(1.0, max(0.0, (float(n.get("oi_grow") or 1.0) - 1.0) / 1.5))
        td = (v.get("today") or {}).get("today")
        b_score = 1.0 if td == "покупают сегодня" else 0.5 if td == "стоит" else 0.0
        score = round(0.35 * t_score + 0.35 * g_score + 0.30 * b_score, 3)
        _mode = n.get("mode")
        if _mode == "парабола":
            score *= 0.45          # парабола: первая тряска — выход, а не покупка (07.09)
        elif _mode == "лестница":
            score *= 1.15
        score = round(score, 3)
        v["queue"] = {"days_since_harvest": days, "score": score, "today": td, "mode": _mode}
        queue.append((score, s2))
    queue.sort(reverse=True)
    out["queue"] = [s2 for _, s2 in queue]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    res = build([x.strip() for x in a.only.split(",")] if a.only else None)
    NM = {"going": "ИДЁТ", "holding": "БЛИЗКАЯ (держат после сбора)", "pulled": "ОТКАТИЛАСЬ", "giving": "ОТДАЮТ"}
    for sym, v in sorted(res["coins"].items(), key=lambda kv: -kv[1]["score"]):
        if a.only or v.get("group"):
            _td = v.get("today") or {}
            print(f"{sym}: {v['score']}/5 {NM.get(v.get('group'), '')}{' · с живым днём' if v.get('live') else ''}"
                  + (f" · СЕГОДНЯ: {_td['today']} (дельта {_td['delta'] / 1e6:+.1f}M, интерес {_td['oi_chg_pct']:+.0f}%, {_td['dominant']})" if _td else "")
                  + " · " + " · ".join(v["why"]) + f" · {v['nums']}")
    for g in ("going", "holding", "pulled", "giving"):
        print(f"{NM[g].lower()}: {len(res[g])} — {', '.join(res[g])}")
    print(f"близких: {len(res['near'])} — {', '.join(res['near'])}")
    if a.write:
        p = BASE_DIR / "output" / "near_move.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"near_move: записано {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
