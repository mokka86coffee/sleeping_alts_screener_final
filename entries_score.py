#!/usr/bin/env python3
"""ЖУРНАЛ ЗАХОДОВ — считаем ТОЛЬКО первых и очередь (08.09).

Владелец: «выборка работает точно, нужно собирать, в какое время она не срабатывает, чтобы понять
почему, а мы сейчас пишем рандомные монеты и прогнозы, которые изменились» и «какой смысл мерить по
всем монетам, где нет объёма — их водит маркетмейкер как захочет».

Что было не так у forecast_score.py: событием считалась СМЕНА СЛОВЕСНОГО ШАБЛОНА по любой из ста
монет доски. Из-за этого:
  · SOPH 07.09 вёл весь день с одним шаблоном — одна запись, и та выпала из счёта;
  · десятки монет со сменами «стоит»/«неясно» разбавляли выборку до бессмыслицы (26%);
  · монеты без оборота, которые водит маркетмейкер, весили столько же, сколько наши первые.

Здесь считается другое. Единица счёта — ЗАХОД: непрерывный отрезок, пока монета была в первых
(места 1–3) или в очереди (места 4 и ниже). По каждому заходу:
  · когда вошла и по какой цене, сколько прогонов продержалась, когда вышла;
  · что было с ценой ПОСЛЕ входа: лучший ход, худшая просадка, ход на выходе из группы и через
    сутки; дошла ли до ближайшей полосы сверху раньше, чем до полосы снизу;
  · ФОН на момент входа: биткоин, ширина доски, поток, сессия, кто был лидером и с каким разрывом.

Тогда вопрос «когда выборка не срабатывает» считается прямо: берём заходы, где хода не было, и
смотрим, чем отличался их фон от тех, где ход был.

Запуск:  python3 entries_score.py --days 7 [--write]
Пишет:   output/entries_score.json
"""
from __future__ import annotations

import argparse
import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTD = BASE_DIR / "output"
INTRA = BASE_DIR / "cq_v2" / "intraday"

TOP_N = 3            # первые — места 1..3
LIMIT_H = 24.0       # горизонт наблюдения за заходом
MARKS = (0.5, 1, 2, 4, 6, 12, 24)


def _jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def _ts(v) -> datetime | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def _bars(sym: str) -> list[dict]:
    p = INTRA / f"{sym.replace('USDT', '').lower()}.jsonl"
    rows = _jsonl(p)
    rows.sort(key=lambda r: str(r.get("candle") or ""))
    return rows


def _bg_at(bgs: list[dict], at: datetime) -> dict:
    """Фон на момент входа — последняя строка не позже этого времени."""
    best = None
    for b in bgs:
        t = _ts(b.get("at"))
        if t and t <= at:
            best = b
        elif t and t > at:
            break
    if not best:
        return {}
    btc = best.get("btc") or {}
    br = best.get("breadth") or {}
    tk = best.get("taker") or {}
    tm = best.get("time") or {}
    ld = best.get("leader") or {}
    ours = best.get("ours") or {}
    live = [m.get("name") for m in (tm.get("markets") or []) if m.get("open")]
    # ФАЗА ТОРГОВ (08.09, владелец: «осталось выяснить, что ещё влияет — время торгов, чей рынок,
    # открытие, процесс, закрытие»). Состояние сессий уже пишется в фон, берём его как отдельный
    # признак: открылась / идёт / скоро закроется / межсессионье.
    phase = "межсессионье"
    for m in (tm.get("markets") or []):
        if m.get("open"):
            st = str(m.get("state") or "")
            phase = f"{m.get('name')}: {st}" if st else str(m.get("name"))
            break
    return {
        "btc_day_pct": btc.get("day_pct"),
        "risk_on": (best.get("risk_on") or {}).get("appetite"),
        "breadth_up": br.get("up"), "breadth_n": br.get("n"),
        "ours_up": ours.get("up"), "ours_n": ours.get("n"),
        "taker": tk.get("day"), "taker_side": tk.get("side"),
        # медиана доски — подтверждённый признак фона (08.09): «определяет полностью рынок»
        "median_pct": ((best.get("risk_on") or {}).get("median_pct")),
        "session": (", ".join(live) if live else "межсессионье"),
        "phase": phase,
        "weekday": tm.get("weekday"),
        "pulls": ld.get("pulls"), "lead_sym": ld.get("sym"), "lead_gap": ld.get("gap"),
        # СЫРОЙ СРЕЗ ЦЕЛИКОМ (09.09): журнал фильтрует по нему кнопками и ничего не теряет —
        # если завтра окажется важной премия, новость или что-то, о чём мы сейчас не думаем,
        # это уже лежит в данных и пересчитается на той же истории.
        "raw": best,
    }


def _path_after(sym: str, at: datetime, p0: float, zones: dict | None) -> dict:
    """Что было с ценой после входа: путь, границы, отметки."""
    rows = [r for r in _bars(sym) if (_ts(r.get("candle")) or datetime.min.replace(tzinfo=timezone.utc)) >= at]
    if len(rows) < 2 or not p0:
        return {}
    up = sorted([q for q, _w in ((zones or {}).get("up") or []) if q and q > p0])
    dn = sorted([q for q, _w in ((zones or {}).get("down") or []) if q and q < p0], reverse=True)
    tp = up[0] if up else None
    sl = dn[0] if dn else None
    mfe = mae = 0.0
    hit = "срок"
    hit_h = None
    curve: dict[str, float] = {}
    nxt = list(MARKS)
    for r in rows:
        t = _ts(r.get("candle"))
        px = r.get("px")
        if not t or not px:
            continue
        h = (t - at).total_seconds() / 3600
        if h > LIMIT_H:
            break
        mv = (px / p0 - 1) * 100
        mfe, mae = max(mfe, mv), min(mae, mv)
        while nxt and h >= nxt[0]:
            curve[str(nxt.pop(0))] = round(mv, 3)
        if hit == "срок":
            if tp and px >= tp:
                hit, hit_h = "цель", round(h, 2)
            elif sl and px <= sl:
                hit, hit_h = "стоп", round(h, 2)
    last = next((r["px"] for r in reversed(rows) if r.get("px")), None)
    return {
        "mfe": round(mfe, 2), "mae": round(mae, 2),
        "hit": hit, "hit_h": hit_h,
        "now_pct": round((last / p0 - 1) * 100, 2) if last else None,
        "curve": curve,
        "to_up_pct": round((tp / p0 - 1) * 100, 2) if tp else None,
        "to_dn_pct": round((sl / p0 - 1) * 100, 2) if sl else None,
    }


def build(days: int = 7) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = [r for r in _jsonl(OUTD / "queue_log.jsonl")
         if r.get("at") and (_ts(r["at"]) or datetime.min.replace(tzinfo=timezone.utc)) >= since]
    bgs = [b for b in _jsonl(OUTD / "market_bg.jsonl") if b.get("at")]
    bgs.sort(key=lambda b: str(b.get("at")))

    runs = sorted({r["at"] for r in q})
    by_run: dict[str, dict] = {}
    for r in q:
        by_run.setdefault(r["at"], {})[r["sym"]] = r

    # ── СБОРКА ЗАХОДОВ: непрерывный отрезок в одной группе (первые / очередь)
    open_now: dict[tuple[str, str], dict] = {}
    entries: list[dict] = []

    def group_of(place) -> str | None:
        if not place:
            return None
        return "первые" if place <= TOP_N else "очередь"

    for t in runs:
        at = _ts(t)
        seen = by_run[t]
        # закрываем те, кто выпал или сменил группу
        for key in list(open_now):
            sym, grp = key
            row = seen.get(sym)
            g_now = group_of((row or {}).get("place"))
            if g_now != grp:
                e = open_now.pop(key)
                e["left_at"] = t
                entries.append(e)
        # открываем новые
        for sym, row in seen.items():
            g = group_of(row.get("place"))
            if not g:
                continue
            key = (sym, g)
            if key not in open_now:
                open_now[key] = {
                    "sym": sym, "group": g, "at": t, "place": row.get("place"),
                    "px": row.get("px"), "score": row.get("score"),
                    "stage": row.get("stage"), "mode": row.get("mode"),
                    "engine": row.get("engine"), "bubble": row.get("bubble"),
                    "oi_to_px": row.get("oi_to_px"), "move_paid": row.get("move_paid"),
                    "after_harvest": row.get("after_harvest"),
                    "bubble_sure": row.get("bubble_sure"),
                    "bubble_vs_plot": row.get("bubble_vs_plot"),
                    "liq_side": row.get("liq_side"), "liq_ok": row.get("liq_ok"),
                    "runs": 0, "zones": None,
                    "bg": _bg_at(bgs, at) if at else {},
                }
            open_now[key]["runs"] += 1
            open_now[key]["place_best"] = min(open_now[key].get("place_best") or 99, row.get("place") or 99)
    for key, e in open_now.items():
        e["left_at"] = None            # ещё в группе
        entries.append(e)

    # ── ИСХОД ПО КАЖДОМУ ЗАХОДУ
    for e in entries:
        at = _ts(e["at"])
        if not at or not e.get("px"):
            continue
        zones = None
        for r in _bars(e["sym"]):
            t = _ts(r.get("candle"))
            if t and t <= at and (r.get("zones") or {}).get("up") is not None:
                zones = r.get("zones")
            elif t and t > at:
                break
        e.update(_path_after(e["sym"], at, e["px"], zones))
        e["hours"] = round(e["runs"] * 0.5, 1)

    def agg(items: list[dict]) -> dict:
        """ДВА РАЗНЫХ СЧЁТА (08.09, владелец: «нужно чётко разделять — либо за день монета выросла,
        либо была точка максимума от точки входа»):
          · сбылось по закрытию — цена НА КОНЕЦ ДНЯ выше входа хотя бы на 2%: это то, что реально
            осталось бы в позиции, если держать до вечера;
          · сбылось по максимуму — от входа была ТОЧКА, где цена давала 2% и больше, даже если
            потом всё вернулось: это то, что можно было взять, выйдя вовремя.
        NAORIS 08.09: по максимуму +13.5% (сбылось), по закрытию +3.1% (нет). Разница между двумя
        числами и есть цена выхода — сколько теряется на том, что не вышли на вершине.
        """
        got = [x for x in items if x.get("mfe") is not None]
        if not got:
            return {"n": 0}
        by_max = [x for x in got if (x.get("mfe") or 0) >= 2]
        by_end = [x for x in got if (x.get("now_pct") or 0) >= 2]
        return {
            "n": len(got),
            # по максимуму: была ли точка, где давало от 2%
            "по_максимуму": len(by_max),
            "доля_максимум": round(len(by_max) / len(got) * 100, 1),
            # по закрытию: осталось ли от 2% к концу дня
            "по_закрытию": len(by_end),
            "доля_закрытие": round(len(by_end) / len(got) * 100, 1),
            # цена выхода — сколько теряется, если не выйти на вершине
            "цена_выхода": round(statistics.median([(x.get("mfe") or 0) - (x.get("now_pct") or 0) for x in got]), 2),
            "mfe_med": round(statistics.median([x["mfe"] for x in got]), 2),
            "end_med": round(statistics.median([(x.get("now_pct") or 0) for x in got]), 2),
            "mae_med": round(statistics.median([x["mae"] for x in got]), 2),
            "цель": sum(1 for x in got if x.get("hit") == "цель"),
            "стоп": sum(1 for x in got if x.get("hit") == "стоп"),
            # совместимость со старыми полями
            "пошли": len(by_max), "доля": round(len(by_max) / len(got) * 100, 1),
        }

    cuts: dict[str, dict] = {}

    def cut(name: str, fn) -> None:
        grp: dict[str, list] = {}
        for x in entries:
            if x.get("mfe") is None:
                continue
            k = fn(x)
            if k is None:
                continue
            grp.setdefault(str(k), []).append(x)
        res = {k: agg(v) for k, v in sorted(grp.items())}
        if res:
            cuts[name] = res

    cut("группа", lambda x: x.get("group"))
    cut("стадия", lambda x: x.get("stage"))
    cut("режим", lambda x: x.get("mode"))
    cut("двигатель", lambda x: x.get("engine"))
    cut("чем оплачен ход", lambda x: x.get("move_paid"))
    # откат без раздачи (08.09): USELESS ×0.54 ожил, DOOD ×3.55 раздали — проверяем разрезом
    cut("после сбора", lambda x: x.get("after_harvest"))
    # СПОРНЫЕ ПУЗЫРИ — ОТДЕЛЬНАЯ ГРУППА (08.09, владелец: «спорные должны учитываться как спорные,
    # а не считать анализ неверным»): пузырь, об который закрывались, — не промах правила, а другой
    # случай. Считаем три группы отдельно, в общий счёт идут ясные.
    cut("пузырь", lambda x: x.get("bubble_sure"))
    # ПУЗЫРИ ПРОТИВ ПРОГНОЗА (08.09): сходятся ли факт дня и словесный шаблон. Ждём, что «против»
    # даст заметно худшую долю — тогда признак пойдёт в правило, а не только в наблюдение.
    cut("пузыри и прогноз", lambda x: x.get("bubble_vs_plot"))
    # ФЛАГ «СНИМУТ» (08.09): сам по себе 32% верных на 319 случаях; подтверждённый ясным пузырём —
    # 9 из 9. Разрез покажет, держится ли это на своей выборке.
    cut("флаг снимут", lambda x: None if not x.get("liq_side")
        else ("подтверждён пузырём" if x.get("liq_ok") else "без подтверждения"))
    # часы в группе пишем, но признаком пока не считаем: NAORIS 08.09 висел в первых почти 12 часов
    # и не пошёл, а SOPH 07.09 пошёл из очереди. Проверяем разрезом, а не правилом.
    cut("часов в группе", lambda x: "до 2 ч" if (x.get("hours") or 0) < 2 else ("2–6 ч" if x["hours"] < 6 else "больше 6 ч"))
    # ── ФОН на момент входа
    cut("тянет одна", lambda x: None if (x["bg"] or {}).get("pulls") is None
        else ("да · " + str(x["bg"].get("lead_sym", "")).replace("USDT", "") if x["bg"]["pulls"] else "нет"))
    cut("биткоин", lambda x: None if (x["bg"] or {}).get("btc_day_pct") is None
        else ("вниз" if x["bg"]["btc_day_pct"] < -0.5 else ("вверх" if x["bg"]["btc_day_pct"] > 0.5 else "стоит")))
    # ПОДЪЁМ БЕЗ РОСТА СВОЕГО БАЛЛА (09.09): проверено на 23 подъёмах — с ростом балла 58%
    # случаев дали ≥3% (медиана +6.1%), без роста 25% (+2.7%). Монету сдвинули соседи, а не её
    # собственные числа.
    cut("подъём", lambda x: None if x.get("own_up") is None
        else ("свой балл вырос" if x["own_up"] else "сдвинули соседи"))
    cut("медиана доски", lambda x: None if (x["bg"] or {}).get("median_pct") is None
        else ("падает" if x["bg"]["median_pct"] < -0.3
              else ("рост" if x["bg"]["median_pct"] > 0.3 else "ровно")))
    cut("ширина", lambda x: None if not (x["bg"] or {}).get("breadth_n")
        else ("растёт больше половины" if x["bg"]["breadth_up"] * 2 >= x["bg"]["breadth_n"] else "растёт меньше половины"))
    cut("поток", lambda x: (x["bg"] or {}).get("taker_side"))
    cut("сессия", lambda x: (x["bg"] or {}).get("session"))
    cut("фаза торгов", lambda x: (x["bg"] or {}).get("phase"))
    cut("день недели", lambda x: (x["bg"] or {}).get("weekday"))
    cut("аппетит", lambda x: (x["bg"] or {}).get("risk_on"))

    # ФОН ПИШЕМ СЫРЫМ, НЕ РЕЖЕМ (09.09, владелец: «ты знаешь, какие есть фоны вообще — новости,
    # что Трамп скажет через пять минут? И я не знаю»). Была попытка нарезать ленту на отрезки по
    # своей классификации — биткоин стоит/давит, доска узкая/широкая. Это отсечение фактов: границы
    # поставлены по трём дням, что видел, и всё, не влезшее в рамки, теряется. То же правило, что
    # у пузырей: факты не отсекаются, отсекать можно только толкование. Поэтому здесь — сырая
    # лента фона на каждый заход, а деление на состояния сделано КНОПКАМИ в журнале: фильтр
    # показывает срез тех же данных и ничего не теряет.
    entries.sort(key=lambda e: str(e.get("at")))
    return {
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": days, "runs": len(runs),
        "все": agg(entries),
        "первые": agg([e for e in entries if e["group"] == "первые"]),
        "очередь": agg([e for e in entries if e["group"] == "очередь"]),
        "cuts": cuts,
        "entries": entries,
    }


def _print(r: dict) -> None:
    print(f"заходов за {r['days']} дн · прогонов {r['runs']}")
    for name in ("первые", "очередь"):
        a = r[name]
        if not a.get("n"):
            continue
        print(f"── {name}: {a['n']} заходов")
        print(f"     по максимуму (была точка ≥2% от входа): {a['по_максимуму']} · {a['доля_максимум']}% · медиана {a['mfe_med']}%")
        print(f"     по закрытию (осталось ≥2% к концу дня): {a['по_закрытию']} · {a['доля_закрытие']}% · медиана {a['end_med']}%")
        print(f"     цена выхода (сколько теряется, если не выйти на вершине): {a['цена_выхода']}%")
        print(f"     просадка медиана {a['mae_med']}% · цель {a['цель']} · стоп {a['стоп']}")
    print("\nразрезы (что различало):")
    for name, grp in r["cuts"].items():
        line = " · ".join(f"{k}: {v['доля']}% из {v['n']} (MFE {v['mfe_med']}%)"
                          for k, v in grp.items() if v.get("n"))
        if line:
            print(f"  {name}: {line}")
    print("\nзаходы:")
    for e in r["entries"]:
        if e.get("mfe") is None:
            continue
        print(f"  {e['at'][5:16]} {e['sym'].replace('USDT',''):9s} {e['group']:8s} место {e.get('place_best')} · "
              f"{e['hours']:>4} ч · вход {e['px']:.6g} · лучший {e['mfe']:+.1f}% · просадка {e['mae']:+.1f}% · "
              f"сейчас {e.get('now_pct')}% · {e.get('hit')}"
              + (f" · тянет {str(e['bg'].get('lead_sym','')).replace('USDT','')}" if (e.get("bg") or {}).get("pulls") else ""))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    r = build(a.days)
    _print(r)
    if a.write:
        OUTD.mkdir(parents=True, exist_ok=True)
        (OUTD / "entries_score.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\nзаписано {OUTD / 'entries_score.json'}")


if __name__ == "__main__":
    main()
