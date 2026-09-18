#!/usr/bin/env python3
"""ПРОФИЛЬ ЛИДЕРА (17.09, владелец: «показывай только такие звёзды, убираем очередь и прочее, снимаем ограничения
про одного лидера и медиану»). Из lab_leaders на 22 стартах за 30 дней: пошедших на иксы от отданных отличали
семь вещей. Здесь они считаются каждый прогон по каждой монете с ходом за сутки от PROFILE_LEAD_PCT — это
лидеры дня — и лидер с PROFILE_MIN_MARKS и больше отметками становится звездой. Ничего не отбирает и не
ранжирует, кроме числа отметок; в журнал очереди не пишет.
Отметки:
  очередь   — в первой тройке очереди час назад (доля пар 0.29: пошедшие были на 3-м, отданные — не в очереди)
  держит    — первое место в очереди в двух из последних четырёх прогонов (0.77)
  со дна    — от минимума 30 дней меньше PROFILE_BOTTOM_DAYS суток (0.19, самый сильный)
  шорты платят — фандинг ниже нуля (0.29) и минимум за сутки ниже −PROFILE_FUND_MIN
  выносят шортов — ликвидации шортов к лонгам за сутки от PROFILE_LIQ_RATIO (0.72)
  одна      — лидеров на доске не больше PROFILE_MAX_LEADERS, считая её (0.30)
  сверху есть куда — до максимума 30 дней от PROFILE_ROOM_PCT (0.68)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import (PROFILE_LEAD_PCT, PROFILE_MIN_MARKS, PROFILE_BOTTOM_DAYS, PROFILE_FUND_MIN,
                             PROFILE_LIQ_RATIO, PROFILE_MAX_LEADERS, PROFILE_ROOM_PCT)
except ImportError:
    PROFILE_LEAD_PCT, PROFILE_MIN_MARKS, PROFILE_BOTTOM_DAYS = 20.0, 5, 1.0
    PROFILE_FUND_MIN, PROFILE_LIQ_RATIO, PROFILE_MAX_LEADERS, PROFILE_ROOM_PCT = 0.1, 2.0, 2, 5.0
try:
    from core_config import PROFILE_STAR_MARKS
except ImportError:
    # ЗВЕЗДА — ТОЛЬКО ПО ОЧЕРЕДИ (18.09, перемер на 248 стартах за 30 дней: дно, фандинг, ликвидации, число лидеров,
    # место до максимума — доля пар 0.41…0.59, ничего; держится только очередь: место ≤3 за час до старта — 0.27,
    # первое место в два часа после — 0.84). Остальные отметки считаются и пишутся как наблюдение.
    PROFILE_STAR_MARKS = ("очередь", "держит")
try:
    from core_config import PROFILE_LOW_WINDOW_D
except ImportError:
    PROFILE_LOW_WINDOW_D = 7        # окно дна и максимума: лаборатория мерила на архиве с 11.09 — шесть дней, не тридцать
try:
    from core_config import PROFILE_MAX_DAYS, PROFILE_RETIRE_DD, PROFILE_RETIRE_OI_RUNS
except ImportError:
    # 18.09, владелец: выбывание — только откат от вершины больше 60%; «интерес четыре прогона» — это два часа стыка
    # сессий (час до открытия и час подхвата), по нему лидер вылетал ровно на переходе. Смена сессии и обгон — не выход.
    PROFILE_MAX_DAYS, PROFILE_RETIRE_DD, PROFILE_RETIRE_OI_RUNS = 3.0, 60.0, 0

BAR = 1800
MARKS = ("очередь", "держит", "со дна", "шорты платят", "выносят шортов", "одна", "сверху есть куда")


def _queue_recent(hours: float = 3.0) -> dict:
    """sym → [(t, место)] из живого журнала очереди за последние часы"""
    p = BASE_DIR / "output" / "queue_log.jsonl"
    since = datetime.now(timezone.utc).timestamp() - hours * 3600
    out: dict = {}
    try:
        lines = p.read_text(encoding="utf-8").splitlines()[-40000:]
    except OSError:
        return out
    for line in lines:
        try:
            r = json.loads(line)
            t = datetime.strptime(r["at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
        except (ValueError, KeyError, TypeError):
            continue
        if t >= since and r.get("sym"):
            out.setdefault(str(r["sym"]).upper(), []).append((t, r.get("place")))
    return {k: sorted(v) for k, v in out.items()}


def _rows(base: str, days: int = 31) -> list[dict]:
    """получасовки монеты за окно: живой файл и дневные gz — через lab_junctions"""
    try:
        import lab_junctions as lj
    except ImportError:
        return []
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    by = lj.archive_index({base}, since).get(base) or {}
    return [dict(by[t], t=t) for t in sorted(by) if by[t].get("px") and by[t].get("h") and by[t].get("l")]


def _m24(rows: list[dict], i: int) -> float | None:
    """ход за сутки на баре i — к ближайшему бару на 24 ч раньше (дыры архива допустимы)"""
    t0 = rows[i]["t"] - 48 * BAR
    j = next((k for k in range(i, -1, -1) if rows[k]["t"] <= t0), None)
    if j is None or rows[i]["t"] - rows[j]["t"] > 60 * BAR:
        return None
    return (float(rows[i]["px"]) / float(rows[j]["px"]) - 1) * 100


def retired(rows: list[dict], i0: int) -> tuple[str | None, dict]:
    """ВЫБЫВАНИЕ ЛИДЕРА — ПО ПЛЕЧУ, НЕ ПО ЦЕНЕ (правило 13.09, здесь то же): интерес падает PROFILE_RETIRE_OI_RUNS
    прогонов подряд при нерастущей цене И откат от вершины с момента старта больше PROFILE_RETIRE_DD.
    Возвращает причину (или None — лидер жив) и числа: откат от вершины, баров интереса вниз"""
    seg = rows[i0:]
    peak = max(float(x["h"]) for x in seg)
    c = float(rows[-1]["px"])
    dd = (1 - c / peak) * 100
    run = 0
    for k in range(len(rows) - 1, i0, -1):
        a, b = rows[k], rows[k - 1]
        if a.get("oi") and b.get("oi") and float(a["oi"]) < float(b["oi"]) and float(a["px"]) <= float(b["px"]):
            run += 1
        else:
            break
    num = {"откат от вершины %": round(dd, 1), "интерес вниз баров": run}
    if dd >= PROFILE_RETIRE_DD:
        return f"отдала {dd:.0f}% от вершины", num
    return None, num


def start_index(rows: list[dict], now: float) -> int | None:
    """старт лидера: первый бар за последние PROFILE_MAX_DAYS суток, где ход за сутки перевалил PROFILE_LEAD_PCT
    снизу; если всё окно был выше — самый ранний бар окна"""
    lo = next((k for k, r in enumerate(rows) if now - r["t"] <= PROFILE_MAX_DAYS * 86400), None)
    if lo is None:
        return None
    prev = _m24(rows, lo - 1) if lo >= 1 else None
    for k in range(lo, len(rows)):
        m = _m24(rows, k)
        if m is not None and m >= PROFILE_LEAD_PCT and (prev is None or prev < PROFILE_LEAD_PCT):
            return k
        if m is not None:
            prev = m
    return None


def marks_for(rows: list[dict], i0: int, q: list[tuple], n_lead_start: int) -> dict:
    """семь отметок НА БАРЕ СТАРТА i0 — как в lab_leaders (17.09: считать «на сейчас» неверно — AVA стартовала в
    02:00 с шестью отметками, а к 18:00 из очереди вышла и лидеров стало трое). q — очередь за окно старта."""
    r = rows[i0]
    t0 = r["t"]
    c = float(r["px"])
    m: dict = {}
    num: dict = {}
    # ОКНО 7 ДНЕЙ, НЕ 30 (18.09: после дозабора у AVA «30-дневное» дно уехало на 6 дней назад, а таблица лидеров
    # считалась на архиве с 11.09 — её «30 дней» были шестью днями; мерка должна быть той же)
    w0 = next((k for k in range(i0, -1, -1) if t0 - rows[k]["t"] >= PROFILE_LOW_WINDOW_D * 86400), 0)
    lo_k = max(range(w0, i0 + 1), key=lambda k: -float(rows[k]["l"]))
    days = (t0 - rows[lo_k]["t"]) / 86400
    num["дней от мин"] = round(days, 1)
    m["со дна"] = days <= PROFILE_BOTTOM_DAYS
    hi30 = max(float(x["h"]) for x in rows[w0:i0 + 1])
    num["до макс 30д %"] = round((hi30 / c - 1) * 100, 1)
    m["сверху есть куда"] = num["до макс 30д %"] >= PROFILE_ROOM_PCT
    # НЕИЗВЕСТНОЕ НЕ СЧИТАЕТСЯ ПРОТИВ (17.09, ONE: старт в дозабранном архиве — фандинга, ликвидаций и очереди там
    # нет; отметка None — «посчитать нельзя», и порог берётся долей от известных)
    fund = r.get("funding")
    fs = [x.get("funding") for x in rows[max(0, i0 - 48):i0 + 1] if x.get("funding") is not None]
    num["фандинг"] = fund
    m["шорты платят"] = None if fund is None else (fund < 0 and bool(fs) and min(fs) <= -PROFILE_FUND_MIN)
    lq = r.get("liq24") or {}
    ratio = (float(lq["short"]) / float(lq["long"])) if (lq.get("long") and lq.get("short") is not None and float(lq["long"])) else None
    num["ликв шортов к лонгам"] = round(ratio, 1) if ratio is not None else None
    m["выносят шортов"] = None if ratio is None else (ratio >= PROFILE_LIQ_RATIO)
    num["лидеров на доске"] = n_lead_start
    m["одна"] = n_lead_start <= PROFILE_MAX_LEADERS
    covered = any(t0 - 5400 <= t <= t0 + 2 * 3600 for t, p in q)          # журнал очереди вообще покрывает старт
    before = [(t, p) for t, p in q if t0 - 5400 <= t <= t0 - 1800 and p is not None]
    num["место за час до старта"] = before[-1][1] if before else None
    m["очередь"] = None if not covered else (bool(before) and before[-1][1] <= 3)
    after = [p for t, p in q if t0 <= t <= t0 + 2 * 3600]
    num["первых мест за 2 ч"] = sum(1 for p in after if p == 1)
    m["держит"] = None if not covered else (num["первых мест за 2 ч"] >= 2)
    lit = sum(1 for v in m.values() if v)
    known = sum(1 for v in m.values() if v is not None)
    return {"marks": m, "num": num, "n": lit, "known": known}


try:
    from core_config import PROFILE_TAIL_H
except ImportError:
    PROFILE_TAIL_H = 12.0            # выбывший лидер держится на экране ещё столько часов, тусклее, с причиной


def _live_leaders() -> dict:
    """ЛИДЕРЫ — ИЗ ЖУРНАЛА ЛИДЕРОВ (18.09, владелец: «вчера пошли AVA, ONE, SYN, никаких PLAY, BULLA, IOST не было»):
    записи pump_leaders.json — та же мерка, что «тянут N» на экране; выбывание — там же, по плечу.
    Возвращает база → None (живой) или момент выбывания (UTC, секунды), если выбыл не раньше PROFILE_TAIL_H назад"""
    try:
        from core_config import PUMP_LEADERS_PATH as _pl
    except ImportError:
        _pl = BASE_DIR / "output" / "pump_leaders.json"
    try:
        recs = json.loads(Path(_pl).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    now = datetime.now(timezone.utc).timestamp()
    out: dict = {}
    for r in (recs.values() if isinstance(recs, dict) else recs):
        if not (isinstance(r, dict) and r.get("symbol")):
            continue
        base = str(r["symbol"]).upper().replace("USDT", "")
        ra = r.get("retired_at")
        if not ra:
            out[base] = None
            continue
        try:
            t = datetime.fromisoformat(str(ra).replace("Z", "+00:00")).timestamp()
        except ValueError:
            continue
        if now - t <= PROFILE_TAIL_H * 3600:
            out[base] = t
    return out


def profile_all() -> list[dict]:
    """живые лидеры с отметками на их старте, по убыванию числа отметок"""
    try:
        import lab_junctions as lj
    except ImportError:
        return []
    now = datetime.now(timezone.utc).timestamp()
    since = int(now) - 31 * 86400
    idx = lj.archive_index(None, since)
    q = _queue_recent(hours=54)
    coins = {}
    for base, by in idx.items():
        rows = [dict(by[t], t=t) for t in sorted(by) if by[t].get("px") and by[t].get("h") and by[t].get("l")]
        if len(rows) < 60 or now - rows[-1]["t"] > 4 * 3600:
            continue
        coins[base] = rows
    # лидеры дня — ход за сутки от порога на последнем баре ИЛИ старт за последние сутки (после отката тоже видна)
    lead_now = {b: _m24(r, len(r) - 1) for b, r in coins.items()}
    out = []
    for base, rows in coins.items():
        i0 = start_index(rows, now)                             # старт за последние PROFILE_MAX_DAYS суток — любая монета
        if i0 is None:
            continue
        why_out, lv = retired(rows, i0)
        t0 = rows[i0]["t"]
        n_lead_start = 0
        for b2, r2 in coins.items():
            k = next((j for j in range(len(r2) - 1, -1, -1) if r2[j]["t"] <= t0), None)
            if k is not None and t0 - r2[k]["t"] <= 2 * BAR:
                mm = _m24(r2, k)
                if mm is not None and mm >= PROFILE_LEAD_PCT:
                    n_lead_start += 1
        sym = base + "USDT"
        res = marks_for(rows, i0, q.get(sym, []), max(1, n_lead_start))
        now_place = next((p for t, p in reversed(q.get(sym, [])) if now - t <= 2400), None)
        out.append({"sym": sym, "n": res["n"], "known": res["known"], "marks": res["marks"], "num": res["num"],
                    "start": datetime.fromtimestamp(t0, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "move24": round(lead_now.get(base) or 0, 1), "place_now": now_place,
                    "retired": why_out, "live": lv})
    out.sort(key=lambda x: (-x["n"], -x["move24"]))
    return out


def stars() -> list[dict]:
    """ЗВЁЗДЫ — ТОЛЬКО ПО ПРИЗНАКАМ (18.09, владелец: «монеты с теми признаками должны быть на экране, а остальных не
    должно; лидер — просто тот, кто первый в очереди; условные лидеры не должны пропадать»): монета со стартом за трое
    суток, которую очередь вела (PROFILE_STAR_MARKS), и которая не отдала PROFILE_RETIRE_DD от вершины. Видна с момента
    старта — не когда обогнала лидера — и не гаснет ни на стыке сессий, ни при обгоне."""
    out = []
    for x in profile_all():
        x["led"] = all(x["marks"].get(k) is True for k in PROFILE_STAR_MARKS)
        if x["led"] and not x.get("retired"):
            out.append(x)
    return out


if __name__ == "__main__":
    for x in profile_all():
        lit = " · ".join(k for k, v in x["marks"].items() if v)
        off = " · ".join(k for k, v in x["marks"].items() if v is False)
        unk = " · ".join(k for k, v in x["marks"].items() if v is None)
        print(f"{x['sym'][:-4]:9s} {x['n']} из {x['known']} известных" + (f" (нет данных: {unk})" if unk else "")
              + f" · старт {x['start'][5:16]} · сейчас {x['move24']:+.0f}% за сутки, место {x['place_now'] or '—'}, "
              + f"от вершины −{x['live']['откат от вершины %']}%, интерес вниз {x['live']['интерес вниз баров']} б."
              + (f" · ВЫБЫЛА: {x['retired']}" if x.get('retired') else "")
              + f" · горит: {lit or '—'} · нет: {off or '—'} · {x['num']}")
