#!/usr/bin/env python3
"""СЧИТАЛКА ТОЧНОСТИ (07.09) — что стало с каждым прогнозом и при каком фоне.

Владелец 07.09: «один прогноз из двадцати срабатывает… при заработке один к двадцати почти
казино». Спорить об этом было нечем: near_move.json переписывался каждый прогон, а «сбылось»
никто не считал. Теперь есть три ленты — forecasts.jsonl (шаблоны репутации), queue_log.jsonl
(места и числа очереди), market_bg.jsonl (фон) — и внутридневной архив, где видно, что было
дальше. Считалка сводит их вместе.

КАК СЧИТАЕМ (собрано из того, как это делают в алготрейдинге, 07.09):

1. ТРИ ГРАНИЦЫ (triple barrier, Лопес де Прадо). Фиксированный горизонт — плохая мерка: ход,
   измеренный на одну отметку в будущем, не видит пути. Цена могла дойти до цели и вернуться,
   могла сразу выбить стоп — метка одинаковая. Поэтому ставим три границы и записываем ту,
   которую задели ПЕРВОЙ:
     цель — ближайшая полоса ликвидаций СВЕРХУ (zones.up из архива; это адрес, а не процент),
     стоп — ближайшая полоса СНИЗУ (zones.down),
     срок — предел по времени.
   Полос нет — запасной вариант от дневной волатильности монеты: цель 2.5σ, стоп 1.0σ.

2. MFE и MAE. Доля сбывшихся описывает, чем кончилось, но не то, что было по дороге. MFE —
   лучшая бумажная прибыль за жизнь прогноза, MAE — худшая просадка. Их отношение читает
   качество ВХОДА отдельно от выхода. Если у большинства MFE около нуля — цена вообще не шла
   в нашу сторону, и чинить надо отбор; если MFE большой, а результат плохой — чинить выход.

3. КРИВАЯ ЗАТУХАНИЯ. Горизонт не угадываем: считаем средний ход на многих отметках
   (полчаса, час, два, четыре, шесть, двенадцать, сутки) и смотрим, где он максимален —
   это и есть настоящий срок жизни прогноза.

4. РАЗРЕЗ ПО ФОНУ. Одни и те же правила в разных режимах дают противоположный результат,
   поэтому итог режем по фону из market_bg.jsonl: risk on, ход биткоина, сессия и день недели,
   дни роста подряд, лидеры биржи не наши. Владелец: «нужен бэкграунд фон, который мешает
   прогнозам исполниться».

ВЫБОРКА. Меньше пятидесяти прогнозов — это ещё не статистика, а меньше ста — не распределение.
Считалка честно пишет, сколько записей в срезе, и не делает выводов на десяти.

    python3 forecast_score.py --only DOOD            # одна монета, проверка
    python3 forecast_score.py --days 7               # неделя, печать
    python3 forecast_score.py --days 7 --write       # + output/forecast_score.json для экрана
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

OUTD = BASE_DIR / "output"
INTRA = BASE_DIR / "cq_v2" / "intraday"
MARKS_H = (0.5, 1, 2, 4, 6, 12, 24)      # отметки кривой затухания, часы
LIMIT_H = 24                              # срок (третья граница)
FALLBACK_TP, FALLBACK_SL = 2.5, 1.0       # запасные границы в дневных σ, если полос нет
MIN_N = 50                                # ниже этого — не статистика

MAX_LAG_MIN = 30          # первый бар дальше получаса от события — данных нет, событие не считаем

# СТОРОНА ПРОГНОЗА (07.09, найдено на журнале): порядок проверки решает. Шаблон «кит поглощает
# слив» — БЫЧИЙ, но слово «слив» в нём есть; из-за этого 46 бычьих событий считались как «на конец»
# и давали ноль сбывшихся. Сначала ищем явные концовки целыми фразами, потом рост.
DOWN_WORDS = ("разгон отпустил", "отпустил", "осечка", "отбой", "конец тренда",
              "выходят", "лонги выходят", "раздача", "вынос идёт")
UP_WORDS = ("тащит", "разгон на", "набирает", "кит", "покупател", "у цели", "спрос", "лестниц", "поглощает")


def _jsonl(p: Path) -> list[dict]:
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _side(tpl: str) -> int:
    """+1 — прогноз на рост, −1 — на конец хода, 0 — непонятный (в счёт не идёт)."""
    t = (tpl or "").lower()
    if any(w in t for w in DOWN_WORDS):
        return -1
    if any(w in t for w in UP_WORDS):
        return 1
    return 0


def _bars(sym: str) -> list[dict]:
    rows = _jsonl(INTRA / f"{sym.replace('USDT', '').lower()}.jsonl")
    rows.sort(key=lambda r: r.get("candle") or "")
    return rows


def _sigma(rows: list[dict]) -> float:
    """Дневная волатильность монеты по её же барам — для запасных границ."""
    px = [r["px"] for r in rows if r.get("px")]
    if len(px) < 10:
        return 0.05
    rets = [abs(px[i] / px[i - 1] - 1) for i in range(1, len(px)) if px[i - 1]]
    return max(0.01, statistics.median(rets) * (48 ** 0.5))


def score_one(sym: str, at: datetime, tpl: str, rows: list[dict] | None = None) -> dict | None:
    """Один прогноз: три границы, MFE и MAE на отметках, чем кончилось."""
    rows = rows if rows is not None else _bars(sym)
    side = _side(tpl)
    if not rows or not side:
        return None
    fut = [r for r in rows if (_ts(r.get("candle")) or datetime.min.replace(tzinfo=timezone.utc)) >= at]
    if len(fut) < 2:
        return None
    # НЕТ БАРОВ РЯДОМ С СОБЫТИЕМ — НЕ СЧИТАЕМ (07.09): архив начинается 05.09 20:00, а события есть
    # и с ночи; путь считался от первого доступного бара через 18 часов — отсюда «MFE 38%».
    _first = _ts(fut[0].get("candle"))
    if not _first or (_first - at).total_seconds() > MAX_LAG_MIN * 60:
        return None
    # ЗАМЕРЗШАЯ ЦЕНА (06.09, найдено на архиве): до правки core_binance цена в барах не обновлялась
    # часами — 06.09 у монеты было 10 разных цен на 48 баров. По такому пути считать нельзя: ход
    # выходит нулевым на всех отметках, а потом одним прыжком. Меньше трёх разных цен за горизонт —
    # событие пропускаем.
    _pxs = {r.get("px") for r in fut[:48] if r.get("px")}
    if len(_pxs) < 3:
        return None
    p0 = next((r["px"] for r in fut if r.get("px")), None)
    if not p0:
        return None
    z = (fut[0].get("zones") or {})
    up = sorted([p for p, _ in (z.get("up") or []) if p > p0])
    dn = sorted([p for p, _ in (z.get("down") or []) if p < p0], reverse=True)
    sg = _sigma(rows)
    tp = up[0] if up else p0 * (1 + FALLBACK_TP * sg)
    sl = dn[0] if dn else p0 * (1 - FALLBACK_SL * sg)
    if side < 0:                       # прогноз на конец хода — границы зеркалим
        tp, sl = (dn[0] if dn else p0 * (1 - FALLBACK_TP * sg)), (up[0] if up else p0 * (1 + FALLBACK_SL * sg))
    tp_from_zone, sl_from_zone = bool(up if side > 0 else dn), bool(dn if side > 0 else up)

    hit, hit_h = "срок", None
    mfe = mae = 0.0
    curve: dict[str, float] = {}
    nxt = list(MARKS_H)
    for r in fut:
        t = _ts(r.get("candle"))
        px = r.get("px")
        if not t or not px:
            continue
        h = (t - at).total_seconds() / 3600
        if h > LIMIT_H:
            break
        move = (px / p0 - 1) * 100 * side          # ход В СТОРОНУ прогноза, в процентах
        mfe, mae = max(mfe, move), min(mae, move)
        while nxt and h >= nxt[0]:
            curve[str(nxt.pop(0))] = round(move, 3)
        if hit == "срок":
            if (side > 0 and px >= tp) or (side < 0 and px <= tp):
                hit, hit_h = "цель", round(h, 2)
            elif (side > 0 and px <= sl) or (side < 0 and px >= sl):
                hit, hit_h = "стоп", round(h, 2)
    last = next((r["px"] for r in reversed(fut) if r.get("px")), p0)
    return {"sym": sym, "at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "tpl": tpl, "side": side,
            "px": p0, "tp": round(tp, 10), "sl": round(sl, 10),
            "tp_zone": tp_from_zone, "sl_zone": sl_from_zone,
            "hit": hit, "hit_h": hit_h, "ok": hit == "цель",
            "mfe": round(mfe, 3), "mae": round(mae, 3),
            "mfe_mae": round(mfe / abs(mae), 2) if mae else None,
            "end": round((last / p0 - 1) * 100 * side, 3), "curve": curve}


def _bg_at(bgs: list[dict], at: datetime) -> dict:
    """Ближайшая строка фона не позже момента прогноза."""
    best = None
    for b in bgs:
        t = _ts(b.get("at"))
        if t and t <= at and (best is None or t > _ts(best["at"])):
            best = b
    if not best:
        return {}
    tm, ro, ld = best.get("time") or {}, best.get("risk_on") or {}, best.get("leaders") or {}
    btc = (best.get("btc") or {}).get("day_pct")
    tk = best.get("taker") or {}
    return {"appetite": ro.get("appetite"), "regime": ro.get("regime"),
            "btc_day": btc, "dow": tm.get("dow"), "weekend": tm.get("weekend"),
            "sessions": ",".join(tm.get("sessions") or []),
            "leaders_mine": ld.get("mine_n"), "leaders_fresh": ld.get("fresh_n"),
            "taker": tk.get("day"), "taker_side": tk.get("side")}


def _agg(items: list[dict]) -> dict:
    if not items:
        return {"n": 0}
    mfe = [x["mfe"] for x in items]
    mae = [x["mae"] for x in items]
    hits = {k: sum(1 for x in items if x["hit"] == k) for k in ("цель", "стоп", "срок")}
    went = sum(1 for x in items if x["mfe"] > 0.5)
    curve = {}
    for h in MARKS_H:
        vals = [x["curve"][str(h)] for x in items if str(h) in x["curve"]]
        if vals:
            curve[str(h)] = {"med": round(statistics.median(vals), 2), "n": len(vals)}
    best_h = max(curve.items(), key=lambda kv: kv[1]["med"])[0] if curve else None
    return {"n": len(items), "ok": hits["цель"], "ok_pct": round(hits["цель"] / len(items) * 100, 1),
            "hits": hits, "went_pct": round(went / len(items) * 100, 1),
            "mfe_med": round(statistics.median(mfe), 2), "mae_med": round(statistics.median(mae), 2),
            "mfe_mae": round(statistics.median(mfe) / abs(statistics.median(mae)), 2) if statistics.median(mae) else None,
            "curve": curve, "best_h": best_h,
            "enough": len(items) >= MIN_N}


def build(days: int = 7, only: list[str] | None = None) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    fc_all = [r for r in _jsonl(OUTD / "forecasts.jsonl")
              if (_ts(f"{r.get('at')}T{r.get('hm')}:00Z") or datetime.min.replace(tzinfo=timezone.utc)) >= since]
    # СЧИТАЕМ СОБЫТИЯ, А НЕ СТРОКИ (07.09): журнал пишет шаблон по каждой монете каждые полчаса, и
    # одна и та же мысль попадала в счёт по два десятка раз за день — 9927 записей против 1455 смен
    # (14.7%). Повторы смазывают всё: доля сбывшихся падает механически, кривая затухания
    # выравнивается в ноль. Берём ПЕРВУЮ запись каждого нового шаблона по монете — момент, когда
    # система впервые это сказала; повтор того же шаблона в счёт не идёт.
    fc, _prev = [], {}
    for r in sorted(fc_all, key=lambda r: (str(r.get("at") or ""), str(r.get("hm") or ""))):
        sym, tpl = r.get("sym"), r.get("tpl")
        if not sym:
            continue
        # ПЕРВАЯ ЗАПИСЬ ПО МОНЕТЕ — НЕ СОБЫТИЕ (07.09): это начало журнала, а не смена мысли.
        # Без этого 05.09 дал 104 «события» из 132 — все монеты разом в день старта архива.
        if sym in _prev and _prev[sym] != tpl:
            fc.append(r)
        _prev[sym] = tpl
    if only:
        keep = {s.replace("USDT", "").upper() for s in only}
        fc = [r for r in fc if str(r.get("sym", "")).replace("USDT", "").upper() in keep]
    bgs = _jsonl(OUTD / "market_bg.jsonl")
    ql = _jsonl(OUTD / "queue_log.jsonl")
    place = {(r.get("candle"), r.get("sym")): r.get("place") for r in ql}
    # карточки пузырей и плечо к цене из ленты очереди (07.09): гипотеза владельца — работает не
    # цвет пузыря, а его МЕСТО в дневном диапазоне (сработавшие 07.09 ниже 40%, провалы выше 92%).
    # Здесь только режем журнал по этим числам; решать будет накопленная выборка.
    qmeta = {(r.get("candle"), r.get("sym")): r for r in ql}
    cache: dict[str, list[dict]] = {}
    items = []
    for r in fc:
        sym = str(r.get("sym") or "")
        at = _ts(f"{r.get('at')}T{r.get('hm')}:00Z")
        if not sym or not at:
            continue
        cache.setdefault(sym, _bars(sym))
        s = score_one(sym, at, r.get("tpl") or "", cache[sym])
        if not s:
            continue
        s["bg"] = _bg_at(bgs, at)
        s["place"] = place.get((r.get("candle"), sym))
        s["candle"] = r.get("candle")
        items.append(s)
    by_day: dict[str, list] = {}
    by_hour: dict[str, list] = {}
    for x in items:
        by_day.setdefault(x["at"][:10], []).append(x)
        by_hour.setdefault(x["at"][:13], []).append(x)
    cuts = {}
    def cut(name, fn):
        grp: dict[str, list] = {}
        for x in items:
            k = fn(x)
            if k is not None:
                grp.setdefault(str(k), []).append(x)
        cuts[name] = {k: _agg(v) for k, v in sorted(grp.items())}
    cut("аппетит", lambda x: (x["bg"] or {}).get("appetite"))
    cut("день недели", lambda x: (x["bg"] or {}).get("dow"))
    cut("сессия", lambda x: (x["bg"] or {}).get("sessions"))
    cut("биткоин", lambda x: None if (x["bg"] or {}).get("btc_day") is None
        else ("растёт" if x["bg"]["btc_day"] > 0 else "падает"))
    cut("лидеры наши", lambda x: None if (x["bg"] or {}).get("leaders_mine") is None
        else ("да" if x["bg"]["leaders_mine"] else "нет"))
    # тейкер по доске (07.09): бьют по стакану в покупку или в продажу — свой, пересчитываемый
    cut("тейкер", lambda x: (x["bg"] or {}).get("taker_side"))
    def _bub_pos(x):
        q = qmeta.get((x.get("candle"), x["sym"])) or {}
        bs = [b for b in (q.get("bubbles") or []) if b.get("side") == "buy" and b.get("pos_pct") is not None]
        if not bs:
            return "без пузыря"
        pos = bs[-1]["pos_pct"]
        return "пузырь внизу дня" if pos <= 40 else "пузырь вверху дня" if pos >= 70 else "пузырь в середине"
    cut("место пузыря", _bub_pos)
    def _bub_role(x):
        q = qmeta.get((x.get("candle"), x["sym"])) or {}
        bs = [b for b in (q.get("bubbles") or []) if b.get("role") in ("продолжение", "поглощён")]
        if not bs:
            return None
        b = bs[-1]
        return ("покупка внизу" if b["side"] == "buy" else "продажа наверху") if b["role"] == "продолжение" \
            else ("покупка поглощена" if b["side"] == "buy" else "продажа поглощена")
    cut("роль пузыря", _bub_role)
    def _dd(x):
        v = (qmeta.get((x.get("candle"), x["sym"])) or {}).get("drawdown_pct")
        if v is None:
            return None
        return "у вершины дня" if v >= -3 else "отдал 3–10%" if v >= -10 else "отдал больше 10%"
    cut("откат от вершины", _dd)
    def _tr(x):
        v = (qmeta.get((x.get("candle"), x["sym"])) or {}).get("oi_trend_pct")
        if v is None:
            return None
        return "интерес растёт" if v >= 2 else "интерес падает" if v <= -3 else "интерес стоит"
    cut("интерес за 3 ч", _tr)
    def _lev(x):
        q = qmeta.get((x.get("candle"), x["sym"])) or {}
        v = q.get("oi_to_px")
        if v is None:
            return None
        return "плечо вровень с ценой" if v <= 2 else "плечо быстрее цены ×2–5" if v <= 5 else "плечо быстрее цены >×5"
    cut("плечо к цене", _lev)
    cut("место", lambda x: None if x.get("place") is None else ("первые 3" if x["place"] <= 3 else "дальше"))
    cut("сторона", lambda x: "на рост" if x["side"] > 0 else "на конец")
    return {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "days": days,
            "rows_total": len(fc_all), "events": len(fc),
            "all": _agg(items),
            "days_list": [{"d": k, **_agg(v)} for k, v in sorted(by_day.items(), reverse=True)],
            "hours_list": [{"h": k, **_agg(v)} for k, v in sorted(by_hour.items(), reverse=True)],
            "cuts": cuts, "items": items}


def _print(r: dict) -> None:
    a = r["all"]
    if not a.get("n"):
        print("нет прогнозов за период (нужны output/forecasts.jsonl и cq_v2/intraday/)")
        return
    if r.get("rows_total"):
        print(f"строк в журнале {r['rows_total']} → событий (смен шаблона) {r['events']}")
    print(f"за {r['days']} дн · прогнозов {a['n']}" + ("" if a["enough"] else f" — меньше {MIN_N}, это ещё не статистика"))
    print(f"цель {a['hits']['цель']} · стоп {a['hits']['стоп']} · срок {a['hits']['срок']} → сбылось {a['ok_pct']}%")
    print(f"пошли в нашу сторону хоть немного: {a['went_pct']}% · MFE медиана {a['mfe_med']}% · "
          f"MAE медиана {a['mae_med']}% · отношение {a['mfe_mae']}")
    if a["curve"]:
        print("кривая затухания (медиана хода):")
        for h, v in a["curve"].items():
            mark = "  ← пик" if h == a["best_h"] else ""
            print(f"   {h:>4} ч  {v['med']:+6.2f}%  (n={v['n']}){mark}")
    for name, grp in r["cuts"].items():
        line = " · ".join(f"{k}: {v['ok_pct']}% из {v['n']}" for k, v in grp.items() if v.get("n"))
        if line:
            print(f"{name}: {line}")
    print("\nпо дням:")
    for d in r["days_list"][:10]:
        print(f"  {d['d']} · {d['ok']} из {d['n']} ({d['ok_pct']}%) · MFE {d['mfe_med']}% MAE {d['mae_med']}%")


def main() -> int:
    ap = argparse.ArgumentParser(description="точность прогнозов: три границы, MFE/MAE, кривая, фон")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--only", help="монеты через запятую")
    ap.add_argument("--write", action="store_true", help="output/forecast_score.json для экрана")
    a = ap.parse_args()
    res = build(a.days, [x.strip() for x in a.only.split(",")] if a.only else None)
    _print(res)
    if a.write:
        OUTD.mkdir(parents=True, exist_ok=True)
        p = OUTD / "forecast_score.json"
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print("\n→", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
