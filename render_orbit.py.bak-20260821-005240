"""Орбита · верхний экран дашборда.

Модуль самодостаточен: dashboard.py только вызывает render_orbit()
и вставляет результат в разметку страницы.

Часть помощников (_pick, _num, _tick, _read_json, _max_vol_ratio и
пороги FLOW_NODES / LEAD_X*) живёт в render.dashboard, а он импортирует
этот модуль — прямой импорт дал бы цикл. Поэтому импорт отложенный,
внутри функции: к моменту вызова dashboard уже загружен.

По-хорошему эти помощники стоит вынести в render/common.py и убрать
отложенный импорт — записано в тех долг.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone

from core_binance import get_btc_context
from core_config import (
    FROZEN_MAX_CHANGE_PCT, FROZEN_TAIL_MIN, FROZEN_TAIL_PCT, ORBIT_BG_SRC,
)
from core_models import Candidate, RunSnapshot
from render_theme import esc
from render_flow_report import case_key, CASE_RU, _cap, _data, flow_order
from analytics_indicators import median
from analytics_momentum import star_oi, star_late, star_pulse

ORBIT_COLORS = {
    "surge":  "var(--am)",
    "flow":   "var(--gd)",
    "lead":   "var(--am-l)",
    "setups": "var(--gr)",
    "hourly": "var(--bl)",
    "sector": "var(--vi)",
    "vetoed": "var(--ru)",
}


def _orbit_nodes(candidates: list[Candidate], snapshot: RunSnapshot,
                 slices: list[dict]) -> list[dict]:
    """Данные семи узлов. Считаются из тех же источников, что и блоки,
    чтобы орбита не разъезжалась с дашбордом под ней."""

    # Отложенный импорт: см. docstring модуля — иначе цикл с dashboard
    from render_dashboard import (_pick, _num, _tick, FLOW_NODES,
                                  RR_MIN, SURGE_NOTE, IMP_NOTE, _get)

    def items(sid: str) -> list[Candidate]:
        return _pick(slices, sid)["items"]

    def bars(pairs: list[tuple[str, str, float]]) -> list[list]:
        """Доля бара — от максимума в своей же тройке, а не от общего
        числа: иначе у слабых срезов все бары схлопываются в ноль."""
        peak = max((v for _, _, v in pairs), default=0) or 1
        return [[k, txt, round(v / peak * 100)] for k, txt, v in pairs]

    def spark(src: list[Candidate]) -> list[float]:
        """Точки мини-графика — то же, что в _blk_volume: распределение
        rvol_1h по монетам среза, а не временной ряд. Настоящей истории
        объёма нет, и рисовать вместо неё красивую кривую нельзя."""
        return [round(_num(c, "rvol_1h"), 2)
                for c in sorted(src, key=lambda c: _num(c, "rvol_1h"))][-40:]

    out: list[dict] = []

    # ОБЪЁМ · три монеты те же, что под графиком в блоке объёмов
    surge = items("surge")
    top = sorted(surge, key=lambda c: -_num(c, "rvol_1h"))[:3]
    out.append({
        "id": "surge", "name": "ОБЪЁМ", "val": str(len(surge)),
        "c": ORBIT_COLORS["surge"], "w": 0.6, "slice": "surge",
        "note": SURGE_NOTE, "spark": spark(surge),
        "rows": bars([(_tick(c), f'×{_num(c, "rvol_1h"):.1f}',
                       _num(c, "rvol_1h")) for c in top]),
    })

    # ПОТОК · две монеты с лучшим score.
    # Счётчики подкейсов отсюда убраны: «fuel 14» не говорит, стоит ли
    # туда смотреть — четырнадцать слабых сигналов хуже одного сильного.
    # Разбивка по подкейсам никуда не делась, она в кольцах строки FLOW.
    flow = [c for c in candidates if c.flow]
    ranked = sorted(flow, key=lambda c: -(getattr(c, "score", 0) or 0))[:2]
    lead = ranked[0] if ranked else None
    out.append({
        "id": "flow", "name": "ПОТОК", "val": str(len(flow)),
        "c": ORBIT_COLORS["flow"], "w": 0.7, "slice": "strat:flow",
        "note": (f"лидер прогона · {_tick(lead)}") if lead else "кто двигает рынок",
        # Шкала абсолютная, а не от максимума пары: при нормировке
        # по паре первая монета всегда упиралась бы в край и разрыв
        # между «сильной» и «чуть слабее» пропадал.
        "rows": [[_tick(c), str(round(getattr(c, "score", 0) or 0)),
                  min(100, round(getattr(c, "score", 0) or 0)),
                  case_key((c.flow or {}).get("case", "")) or ""]
                 for c in ranked],
    })

    # ЛИДЕРЫ · та же лента, что под рядом стратегий
    out.append(_orbit_leaders(candidates))

    # СЕТАП · топ-3 по R:R
    setups = items("setups")
    st = sorted(setups, key=lambda c: -(getattr(c, "rr", 0) or 0))[:3]
    out.append({
        "id": "setups", "name": "СЕТАП", "val": str(len(setups)),
        "c": ORBIT_COLORS["setups"], "w": 1.0, "slice": "setups",
        "note": f"из {len(candidates)} · r:r ≥ {RR_MIN}",
        "rows": bars([(_tick(c), f'1:{(getattr(c, "rr", 0) or 0):.1f}',
                       float(getattr(c, "rr", 0) or 0)) for c in st]),
    })

    # ИМПУЛЬС · те же монеты, что в блоке часового импульса
    hourly = items("hourly")
    hs = sorted(hourly, key=lambda c: -_num(c, "rvol_1h"))[:3]
    out.append({
        "id": "hourly", "name": "ИМПУЛЬС", "val": str(len(hourly)),
        "c": ORBIT_COLORS["hourly"], "w": 0.25, "slice": "hourly",
        "note": IMP_NOTE, "spark": spark(hourly),
        "rows": bars([(_tick(c), f'×{_num(c, "rvol_1h"):.1f}',
                       _num(c, "rvol_1h")) for c in hs]),
    })

    # СЕКТОР · ведёт в панель лидирующего сектора, как строка в блоке
    src = getattr(snapshot, "sectors", None) or []
    pairs = sorted(
        [(str(_get(r, "sector", "") or ""), float(_get(r, "avg_change_24h", 0) or 0))
         for r in src], key=lambda p: -p[1])[:3]
    out.append({
        "id": "sector", "name": "СЕКТОР", "val": (pairs[0][0] if pairs else "—"),
        "c": ORBIT_COLORS["sector"], "w": 0.45,
        "slice": (f"sector:{pairs[0][0]}" if pairs else ""),
        "note": "ротация за 24 часа",
        "rows": bars([(n, f"{v:+.1f}%", abs(v)) for n, v in pairs]),
    })

    # ВЕТО
    vetoed = items("vetoed")
    share = (len(vetoed) / len(candidates) * 100) if candidates else 0
    out.append({
        "id": "vetoed", "name": "ВЕТО", "val": str(len(vetoed)),
        "c": ORBIT_COLORS["vetoed"], "w": 0.3, "slice": "vetoed",
        "note": f"отсеяно риском · {share:.0f}% выборки",
        "rows": bars([(_tick(c), "—", 1.0) for c in vetoed[:3]]),
    })

    return out


def _orbit_flow_leader(candidates: list[Candidate]) -> Candidate | None:
    """Тот же отбор, что «ПОТОК» на орбите: лучший score среди
    FLOW-детектированных. Пересчитывается отдельно от _orbit_nodes,
    чтобы _orbit_market не зависел от порядка вызовов."""
    flow = [c for c in candidates if c.flow]
    return max(flow, key=lambda c: getattr(c, "score", 0) or 0, default=None)


def _orbit_flow_bigvol(candidates: list[Candidate]) -> list[dict]:
    """Монеты из выборки FLOW, у которых объём ≥ ×30 на любом ТФ.

    ×30 — не порог качества сигнала, а порог заметности объёма: та же
    величина, что читает карточка монеты (v1h/v4h/v1d из _data), а не
    отдельная метрика. Список отсортирован по максимальному множителю,
    он же и подписывается в строке.
    """
    from render_dashboard import _tick

    THRESHOLD = 30.0
    out = []
    for c in [c for c in candidates if c.flow]:
        d = _data(c)
        best = max(d.get("v1h") or 0, d.get("v4h") or 0, d.get("v1d") or 0)
        if best >= THRESHOLD:
            out.append({"t": _tick(c), "x": round(best, 1), "cap": _cap(d["cap"])})
    out.sort(key=lambda r: -r["x"])
    return out


def _orbit_leaders(candidates: list[Candidate]) -> dict:
    """Лента тикеров. Источники и пороги те же, что у _blk_leaders,
    иначе одна и та же монета была бы золотой внизу и серой на орбите.

    Узел не ведёт в панель: своего среза у этой ленты нет. Зато каждый
    тикер несёт data-coin и открывает карточку монеты — как в .lead-list.
    """
    from render_dashboard import (_read_json, _max_vol_ratio,
                                  LEADERS_PATH, ANOMALY_PATH,
                                  LEAD_X1, LEAD_X2, LEAD_X3)

    flow_j = _read_json(LEADERS_PATH)
    vol_j = _read_json(ANOMALY_PATH)
    flow_syms = [k for k in flow_j if not k.startswith("_")]
    vol_syms = [k for k in vol_j if not k.startswith("_")]

    ranked: dict[str, float] = {}
    for sym in flow_syms:
        ranked[sym] = _max_vol_ratio(flow_j.get(sym) or {})
    for sym in vol_syms:
        ranked.setdefault(sym, _max_vol_ratio(vol_j.get(sym) or {}))

    by_symbol = {c.symbol.upper(): c for c in candidates}

    def tier(x: float) -> int:
        if x >= LEAD_X3: return 3
        if x >= LEAD_X2: return 2
        if x >= LEAD_X1: return 1
        return 0

    # В карточку помещается около двух десятков: берём самые весомые,
    # а не первые попавшиеся. В ленте внизу порядок намеренно случайный,
    # но там виден весь список — здесь отбор, и он должен быть по весу.
    order = sorted(ranked, key=lambda s: -ranked[s])[:21]

    lst = []
    for sym in order:
        c = by_symbol.get(sym.upper())
        label = sym[:-4] if sym.endswith("USDT") else sym
        lst.append([label, tier(ranked[sym]), (c.symbol if c is not None else "")])

    return {
        "id": "lead", "name": "ЛИДЕРЫ", "val": str(len(ranked)),
        "c": ORBIT_COLORS["lead"], "w": 0.9, "slice": "",
        "note": "топ flow + аномальный объём", "list": lst,
    }



# Окно журнала лидеров — 14 дней, столько же живёт запись в leaders.py.
# Свежесть считается от него, чтобы шкала яркости совпадала со сроком
# хранения: монета гаснет ровно к моменту, когда выпадает из журнала.
STAR_WINDOW_DAYS = 14.0

# Порог «новой» звезды: попала в лидеры не позже двух суток назад.
# Признак бинарный и отдан мерцанию — размер несёт свежесть плавно,
# а мерцание отвечает на другой вопрос: что появилось недавно.
STAR_NEW_DAYS = 5.0

# Поля даты пробуем по очереди: точной схемы записи журнала я не знаю,
# а падать из-за отсутствующего ключа отчёт не должен. Если ни одного
# нет — свежесть берётся из порядка записей в файле (см. _orbit_stars).
STAR_TS_KEYS = ("first_seen", "added", "since", "created", "ts", "started")


def _star_age_days(rec: dict) -> float | None:
    """Возраст записи в днях или None, если даты в записи нет."""
    import datetime as _dt
    for key in STAR_TS_KEYS:
        raw = rec.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                # эпоха в секундах или миллисекундах
                ts = float(raw)
                if ts > 1e11:
                    ts /= 1000.0
                when = _dt.datetime.fromtimestamp(ts, _dt.timezone.utc)
            else:
                when = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if when.tzinfo is None:
                    when = when.replace(tzinfo=_dt.timezone.utc)
        except (ValueError, OSError, OverflowError):
            continue
        delta = _dt.datetime.now(_dt.timezone.utc) - when
        return max(0.0, delta.total_seconds() / 86400.0)
    return None



def _star_unlocks(raw: dict) -> dict:
    """Разлоки в звезду. Пусто — значит монету не заполняли.

    Ключей нет вовсе, а не нули: пробел на экране должен отличаться от
    «разлоков нет». Величины отдаются как есть, без вердикта — дни,
    доли и признак инсайдерского транша, а «опасно» решает человек.
    """
    u = (raw or {}).get("unlocks") or {}
    if not u:
        return {}

    out: dict = {}
    pairs = (
        ("unlockDays", "next_days"), ("unlockDate", "next_date"),
        ("unlockUsd", "next_usd"),
        # Размер транша — в токенах, двумя долями. Дни оборота отсюда
        # убраны: их знаменатель берётся из ТЕКУЩЕГО объёма, а карточку
        # смотрят на всплеске, когда объём выше нормы в десятки раз.
        # Тот же транш на пампе выглядел безобидным ровно тогда, когда
        # он опаснее всего — в этот всплеск и раздают.
        ("unlockPctSupply", "next_pct_supply"),
        ("unlockPctFloat", "next_pct_float"),
        ("unlockAfter", "next_after_days"),
        ("unlockInsShare", "next_insider_share"),
        ("floatPct", "circ_pct"), ("fdvRatio", "fdv_ratio"),
        ("insNow", "insiders_now"), ("insGrow", "insiders_grow"),
    )
    for star_key, src_key in pairs:
        if u.get(src_key) is not None:
            out[star_key] = u[src_key]
    if u.get("next_insider") is not None:
        out["unlockIns"] = bool(u["next_insider"])
    if u.get("inferred"):
        out["unlockInferred"] = True
    if u.get("next_rounds"):
        out["unlockRounds"] = list(u["next_rounds"])
    return out


def _star_intraday(raw: dict) -> dict:
    """Интрадей-величины для панели и карточки.

    Плоские ключи, а не вложенный словарь: JS читает звезду в дюжине
    мест, и `s.press` там читается, а `s.intraday.pressure.delta`
    ломается на первом же отсутствующем звене.

    Отсутствующая величина не подменяется нулём. Ноль откупов и
    «не мерили» — разные ответы, и подпись на карточке обязана их
    различать; поэтому ключа просто нет.

    h48 — часовые закрытия за двое суток, те самые, по которым
    считались метки крупных заявок. Позиции в marks отсчитаны от
    начала этого же хвоста, поэтому ряд и метки обязаны ехать вместе.
    """
    intra = (raw or {}).get("intraday") or {}
    if not intra:
        return {}

    out: dict = {}

    closes = [c for c in (raw.get("closes_1h") or []) if c]
    if len(closes) >= 8:
        out["h48"] = [round(float(c), 10) for c in closes[-48:]]

    big = intra.get("big") or {}
    if big:
        out["bigCount"] = int(big.get("count") or 0)
        out["bigBuys"] = int(big.get("buys") or 0)
        out["bigSells"] = int(big.get("sells") or 0)
        out["bigMax"] = float(big.get("max_x") or 0.0)
        marks = big.get("marks") or []
        if marks:
            out["bigMarks"] = [
                {"i": int(m["i"]), "s": str(m["side"]), "x": float(m["x"])}
                for m in marks[:24]
            ]

    pres = intra.get("pressure") or {}
    if pres:
        out["press"] = float(pres.get("delta") or 0.0)
        out["pressShare"] = float(pres.get("share") or 0.0)

    vx = intra.get("vortex") or {}
    if vx:
        out["vxDir"] = str(vx.get("dir") or "")
        out["vxAgo"] = int(vx.get("bars_ago", -1))

    if intra.get("range_pos") is not None:
        out["rangePos"] = float(intra["range_pos"])
    if intra.get("bg") is not None:
        out["volBg"] = float(intra["bg"])

    prom = intra.get("prom") or {}
    if prom.get("q"):
        out["q"] = float(prom["q"])
        out["qScale"] = str(intra.get("scale") or "")

    spd = intra.get("speed") or {}
    if spd.get("v"):
        out["speedV"] = float(spd["v"])
        out["speedAtr"] = float(spd.get("atr_move") or 0.0)

    # Последние часы против суток. Мелкая шкала предпочтительнее
    # часовой: на пятнадцати минутах крупная сделка меньше тонет в
    # среднем размере бара. Пятнадцатиминутки грузятся только для
    # монет журнала, поэтому у остальных остаётся часовой ответ, и
    # шкала едет рядом с числами — без неё одинаковые фразы с разных
    # монет означали бы разное.
    fine = (raw or {}).get("intraday_fine") or {}
    src = fine if (fine.get("shake") or {}) else intra
    shake = src.get("shake") or {}
    if shake:
        out["shakeScale"] = str(src.get("scale") or "")
        out["shakeHours"] = float(shake.get("hours") or 0)
        out["shakeX"] = float(shake.get("size_x") or 0.0)
        out["shakeP90"] = float(shake.get("size_p90") or 0.0)
        out["shakeMove"] = float(shake.get("move_pct") or 0.0)
        # Остальное приходит не всегда: перекос требует оборота с
        # обеих сторон, ход в ATR — ненулевого ATR, пробой низа —
        # предыдущего такого же окна. Ноль тут соврал бы.
        if shake.get("buy_pp") is not None:
            out["shakePP"] = float(shake["buy_pp"])
        if shake.get("buy_share") is not None:
            out["shakeShare"] = float(shake["buy_share"])
        if shake.get("move_atr") is not None:
            out["shakeAtr"] = float(shake["move_atr"])
        if shake.get("low_break") is not None:
            out["shakeLow"] = bool(shake["low_break"])

    # Что было за последние часы. Мелкая шкала предпочтительнее
    # часовой: сторона у big_trades берётся по доле тейкер-покупок
    # ВСЕГО бара, и крупная покупка внутри продавцового часа уходит в
    # нейтраль — именно тот случай, ради которого слой и заведён.
    # Пятнадцатиминутки грузятся только для монет журнала, поэтому у
    # остальных остаётся часовой ответ, и шкала едет рядом с числами:
    # без неё «две покупки» с разных монет означали бы разное.
    fine = (raw or {}).get("intraday_fine") or {}
    src = fine if (fine.get("shake") or {}) else intra
    shake = src.get("shake") or {}
    if shake:
        out["shakeScale"] = str(src.get("scale") or "")
        out["shakeHours"] = float(shake.get("hours") or 0)
        out["shakeBuys"] = int(shake.get("buys") or 0)
        out["shakeSells"] = int(shake.get("sells") or 0)
        out["shakeMax"] = float(shake.get("max_x") or 0.0)
        out["shakeMove"] = float(shake.get("move_pct") or 0.0)
        # Ход в ATR и пробой низа приходят не всегда: у монеты с
        # нулевым ATR первого нет, у короткого ряда нет второго.
        # Ноль здесь соврал бы — «цена стояла» вместо «не мерили».
        if shake.get("move_atr") is not None:
            out["shakeAtr"] = float(shake["move_atr"])
        if shake.get("low_break") is not None:
            out["shakeLow"] = bool(shake["low_break"])

    return out


def _quiet_days(rec: dict) -> int:
    """Сколько дней прошло с последнего события по записи журнала.

    Событие — срабатывание FLOW либо обновление аномального объёма;
    его момент пишет update_leaders в last_hit. У записей, заведённых
    до появления поля, берётся first_seen: судить по величине,
    которой не собирали, не о чем, и ноль здесь соврал бы сильнее.
    """
    import datetime as _dt

    raw = rec.get("last_hit") or rec.get("first_seen")
    if not raw:
        return 0
    try:
        when = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return 0
    if when.tzinfo is None:
        when = when.replace(tzinfo=_dt.timezone.utc)
    delta = _dt.datetime.now(_dt.timezone.utc) - when
    return max(0, int(delta.total_seconds() // 86400))


def _manual_gaps(rec: dict) -> list[str]:
    """Подписи незаполненных полей, которые считает человек.

    Подписи, а не ключи: список идёт прямо на экран, и `oi_base_m`
    там читалось бы хуже, чем «база OI». Порядок фиксирован в
    спецификации, чтобы пробелы у всех монет шли одинаково и глаз к
    нему привыкал.
    """
    from analytics_manual_fields import labels, missing

    return labels(missing(rec))


def _hits_by_day(rec: dict, days: int = 7) -> list[int]:
    """Попадания по дням, свежий день последний.

    Читается из карты, которую ведёт журнал. Дни без попаданий —
    честные нули, а не пропуски: провал в середине ряда сам по себе
    информация.

    Пустой список означает, что карты ещё нет: у записей, заведённых
    до появления поля, восстановить её неоткуда.
    """
    import datetime as _dt

    src = rec.get("hits_by_day")
    if not isinstance(src, dict) or not src:
        return []

    today = _dt.datetime.now(_dt.timezone.utc).date()
    out: list[int] = []
    for back in range(days - 1, -1, -1):
        key = (today - _dt.timedelta(days=back)).isoformat()
        try:
            out.append(int(src.get(key) or 0))
        except (TypeError, ValueError):
            out.append(0)
    return out


def _star_card(c: Candidate | None) -> dict:
    """Поля карточки монеты, всплывающей при наведении на звезду.

    Монеты из журнала, не попавшей в текущий прогон, у нас нет в
    candidates — тогда карточка покажет только тикер и журнальные
    поля. Это честнее, чем тянуть устаревшие числа из журнала.
    """
    if c is None:
        return {"score": 0, "sector": "—", "pattern": "—"}

    d = _data(c)
    cats = getattr(c, "categories", None) or []
    return {
        "score": int(getattr(c, "score", 0) or 0),
        "sector": (cats[0] if cats else "—").lower(),
        "cap": _cap(d["cap"]),
        "ath": round(d["ath"]),
        "pattern": CASE_RU.get(case_key(_flow_case(c)), "—"),
        "v1h": d["v1h"], "v4h": d["v4h"], "v1d": d["v1d"],
        "p1d": round(d["p1d"], 1),
        "p3d": round(d["p3d"], 1),
        "p7d": round(d["p7d"], 1),
        "fund": round(d["fund"], 4),
        "series": [round(float(v), 6) for v in (d["series"] or [])],
    }


def _flow_case(c: Candidate) -> str:
    return str((c.flow or {}).get("case", "") or "")


def _orbit_stars(candidates: list[Candidate]) -> list[dict]:
    """Лидер FLOW и монеты журнала лидеров — отдельными звёздами.

    На орбите они были бы восьмым узлом и спорили бы с категориями.
    Здесь другой смысл: не срез выборки, а история отбора, поэтому
    и место другое — поле вокруг кольца.

    Три признака, три разных свойства, чтобы они читались вместе:
      свежесть → размер и яркость
      объём ≥ x50 → цвет и второй луч с кольцом
      текущий лидер прогона → подпись тикером
    """
    from render_dashboard import (_read_json, _max_vol_ratio,
                                  LEADERS_PATH, ANOMALY_PATH,
                                  LEAD_X1, LEAD_X2, LEAD_X3)

    flow_j = _read_json(LEADERS_PATH)
    syms = [k for k in flow_j if not k.startswith("_")]
    if not syms:
        return []

    ages = {s: _star_age_days(flow_j.get(s) or {}) for s in syms}
    dated = [a for a in ages.values() if a is not None]

    lead = max((c for c in candidates if c.flow),
               key=lambda c: getattr(c, "score", 0) or 0, default=None)
    lead_sym = lead.symbol.upper() if lead is not None else ""
    by_symbol = {c.symbol.upper(): c for c in candidates}

    # Место монеты в текущем списке FLOW и размер этого списка.
    # Порядок берём у flow_order — той же функции, которой сортируется
    # сам отчёт, чтобы номер на карточке и строка в списке не разошлись.
    order = flow_order(candidates)
    fpos = {c.symbol.upper(): i + 1 for i, c in enumerate(order)}
    ftotal = len(order)

    out = []
    for i, sym in enumerate(syms):
        if ages[sym] is not None:
            fresh = max(0.0, min(1.0, 1.0 - ages[sym] / STAR_WINDOW_DAYS))
        elif dated:
            fresh = 0.5          # часть записей с датой, эта без — середина шкалы
        else:
            # Даты нет ни у кого: журнал дописывается в конец, поэтому
            # порядок ключей и есть порядок появления. Приближение, но
            # честное — и шкала не схлопывается в одинаковые точки.
            fresh = (i + 1) / len(syms)

        # Запись журнала связывается один раз: раньше она читалась
        # заново в двух местах.
        rec = flow_j.get(sym) or {}
        ratio = _max_vol_ratio(rec)
        c = by_symbol.get(sym.upper())

        # Стратегия, которой монета попала в журнал.
        #
        # Сначала текущий прогон, потом entry_case из журнала. Порядок
        # именно такой: фигура могла смениться с момента попадания, и
        # на экране должно стоять то, что видно сейчас. Но монеты из
        # журнала, выпавшие из текущей выборки, иначе остались бы
        # вовсе без цвета — для них entry_case единственный источник.
        #
        # Префикс flow_ снимается здесь, а не в JS: имя подкейса —
        # это ключ палитры, и разбирать его на стороне отрисовки
        # значит держать знание о формате имён в двух местах.
        case = ""
        if c is not None and c.flow:
            case = str(c.flow.get("case") or "")
        if not case:
            case = str(rec.get("entry_case") or "")
        st = case[5:] if case.startswith("flow_") else case
        label = sym[:-4] if sym.endswith("USDT") else sym
        # up_from_low / days_from_low — те же поля, что читает
        # _numbers() во flow_report. Для монет, которых нет в текущем
        # прогоне, роста не будет: raw есть только у кандидатов.
        raw = (getattr(c, "raw", None) or {}) if c is not None else {}
        # Вложенный drop текущего прогона: отсюда берётся first_run —
        # «первый разгон после ЭТОГО падения». Признак живёт в окне
        # DropContext (240 дней) и в журнале не хранится, поэтому
        # источник — только текущий прогон; для монеты вне прогона
        # его честно нет.
        # Вложенный контекст текущего прогона. drop лежит внутри
        # context — путь длинный, но читается один раз здесь, а не в
        # пяти местах JS.
        fctx = ((c.flow or {}).get("context") or {}) if c is not None else {}
        fdrop = fctx.get("drop") or {}
        # Если даты нет ни у кого, свежесть выведена из порядка ключей —
        # тогда и «новизну» считаем по той же шкале, а не по возрасту.
        if ages[sym] is not None:
            is_new = ages[sym] <= STAR_NEW_DAYS
        else:
            is_new = fresh >= 1.0 - STAR_NEW_DAYS / STAR_WINDOW_DAYS

        out.append({
            "t": label,
            "f": round(fresh, 3),
            "new": bool(is_new),
            "hot": bool(ratio >= LEAD_X1),
            "x": round(ratio),
            "st": st,
            # Возраст записи в журнале. Его читает rate() при расчёте
            # яркости, и без него ВСЕ звёзды получали одну и ту же
            # прозрачность 0.43: rate возвращал null, темп подменялся
            # серединой шкалы. Канал был мёртв с момента заведения.
            "days": (round(ages[sym]) if ages[sym] is not None else 0),
            "lead": sym.upper() == lead_sym,
            "coin": (c.symbol if c is not None else ""),
            "up": round(float(raw.get("up_from_low") or 0)),
            "updays": int(raw.get("days_from_low") or 0),
            # ── Поля журнала: их читает сводка при входе ──
            # px/stop оживляют строку «у уровня», streak — «в работе»,
            # hitCount/runsSeen — справку персистентности в рядах
            # отбора, chg — ход от входа в журнал. До этого сводка
            # читала px, stop, streak, firstRun — и ни одно поле сюда
            # не писалось: четыре её строки были мертвы с заведения.
            #
            # hitCount, а НЕ hits: под именем hits coinCard ждёт
            # список индексов в ряду спарклайна (метки попаданий), и
            # целое число там роняет .map — вместе со звёздами,
            # узлами и кометой, потому что падает вся сборка.
            "px": float(rec.get("price") or 0.0),
            "stop": float(rec.get("stop_hint") or 0.0),
            "streak": int(rec.get("streak") or 0),
            "hitCount": int(rec.get("hits") or 0),
            "runsSeen": int(rec.get("runs_seen") or 0),
            "chg": round(float(rec.get("change_pct") or 0.0), 1),
            "firstRun": bool(fdrop.get("first_run")),

            # ── Положение в цикле ──
            # Кратность от дна ЦИКЛА (окно 240 дней), а не от
            # локального минимума: up выше считается по окну в 60
            # дней, и у монеты, которая уже поехала, оно уползает
            # вверх следом за ценой. Две величины расходятся в разы,
            # и правило завершения считает именно по этой. Из
            # прогона, а при его отсутствии — из журнала, куда её
            # пишет update_leaders.
            "upX": round(float(fdrop.get("up_x")
                               or rec.get("up_x") or 0.0), 2),
            # Глубина от пика ЖИЗНИ контракта. Без неё кратность от
            # дна читается одинаково у ранней монеты и у отработавшей:
            # ×2 при −94% от пика и ×2 при −30% — разные монеты.
            "lifeDrop": round(float(fdrop.get("life_drop_pct") or 0.0), 1),
            "trendDone": bool(rec.get("trend_done")),

            # ── Живость ──
            # Отскоки, вернувшиеся на дно и не пробившие его, против
            # всех отработанных. Прямое выражение правила «первый
            # разгон — сквиз»: монета с тремя удержанными отскоками
            # уже показала спрос трижды.
            "rallies": int(fdrop.get("rallies") or 0),
            "heldRallies": int(fdrop.get("held_rallies") or 0),

            # Молчание в днях: сколько прошло с последнего события
            # (срабатывание FLOW либо аномальный объём). Возраст
            # записи больше ничего не значит — запись живёт, пока
            # события есть, поэтому на экран идёт тишина, а не срок.
            "quiet": _quiet_days(rec),

            # Чего в записи не хватает из того, что код узнать не
            # может. Не ошибка и не предупреждение: список того, что
            # заполняется руками с графика.
            "gaps": _manual_gaps(rec),

            # Плотность попаданий по дням: семь чисел, свежий день
            # последний. Отвечает «жива ли монета в эти сутки», в
            # отличие от hitCount, который отвечает «возвращается ли
            # она изо дня в день». Величины разные, и смешивать их
            # нельзя — иначе обе перестанут значить что-либо.
            "byDay": _hits_by_day(rec),

            # Вердикт подкейса. Единственное место, где монета
            # объясняет себя словами; крупная карточка его уже
            # рисует, а поля до сих пор не существовало.
            "verdict": str((c.flow or {}).get("verdict") or "")
                       if c is not None else "",

            # ── Интрадей: горизонт сутки-двое ──
            # Из метрик, а не из пейлоада: метрики считаются для всей
            # выборки, пейлоад — только для сработавших.
            **_star_intraday(raw),
            **_star_unlocks(raw),
            **star_oi(c),
            **star_late(c),
            **star_pulse(sym),
            # Место в текущем прогоне. У монеты журнала, выпавшей из
            # выборки, поля нет вовсе — экран тогда скажет «вне
            # выборки», а не нарисует нулевой номер, который выглядел
            # бы как первое место наоборот.
            **({"fpos": fpos[sym.upper()], "ftotal": ftotal}
               if sym.upper() in fpos else {}),

            # Числа карточки берём тем же _data(), что кормит карточки
            # отчёта: иначе одна монета показывала бы на орбите и в
            # отчёте разные цифры, и расхождение всплыло бы не сразу.
            **_star_card(c),
        })

    # Лидер рисуется последним — поверх остальных, если рядом окажется сосед
    out.sort(key=lambda s: (s["lead"], s["f"]))
    return out

# Торговая неделя привязана к Москве, а не к часовому поясу читателя:
# окно ликвидности задаёт биржа и её основной поток, а не то, откуда
# смотрят на отчёт. UTC+3 фиксированный, перевода часов нет.
MSK = timezone(timedelta(hours=3))


def _weekend_state(now: datetime | None = None) -> str:
    """Положение относительно выходных: 'soon', 'now' или пустая строка.

    Пятница — «выходные близко»: ликвидность начинает уходить уже к
    вечеру. Суббота и воскресенье — сами выходные.

    Единственная реализация на проект. Вторая жила в brief.py на JS и
    считала то же самое по своему часовому поясу.
    """
    moment = now or datetime.now(MSK)
    day = moment.astimezone(MSK).weekday()   # 0 пн … 6 вс
    if day == 4:
        return "soon"
    if day in (5, 6):
        return "now"
    return ""


def _market_breadth(candidates: list[Candidate]) -> dict:
    """Хвост распределения суточных изменений по всей выборке.

    Отвечает на вопрос «есть ли вообще куда ехать», на который доля
    зелёных не отвечает: рынок бывает зелёным на 60% при росте в
    пределах двух процентов, и это ровно замирание.

    Два числа, а не одно. Максимум говорит, был ли сегодня хоть один
    сильный ход; счётчик — единичный это выброс или движение рынка.
    Замиранием считаем, когда провалены оба: одна улетевшая монета
    при мёртвом остальном рынке движением не является.
    """
    from render_dashboard import _num

    changes = []
    for c in candidates:
        v = _num(c, "ch_24h")
        if v is not None:
            changes.append(float(v))

    if not changes:
        return {"frozen": False, "maxChange": None, "tail": 0}

    top = max(changes)
    tail = sum(1 for x in changes if x >= FROZEN_TAIL_PCT)

    return {
        "frozen": top < FROZEN_MAX_CHANGE_PCT and tail < FROZEN_TAIL_MIN,
        "maxChange": round(top, 1),
        "tail": tail,
        "tailPct": FROZEN_TAIL_PCT,
    }

def _day_ratios(vals: list) -> list[float]:
    """Кратности дневного объёма к собственной медиане ряда.

    Считается ЗДЕСЬ, а не в JS. Объём в этом проекте уже мерился
    тремя разными способами под одним словом (бар к медиане нормы,
    час к среднему за сутки, максимум по пяти масштабам), и четвёртое
    место расчёта — в браузере, вне досягаемости пробы — сделало бы
    расхождение неотлаживаемым.

    Медиана, а не среднее: один аномальный день в ряду задирает
    среднее так, что все остальные дни становятся «ниже нормы».
    """
    clean = [float(v) for v in vals if v and float(v) > 0]
    if len(clean) < 4:
        return []
    med = median(clean)
    if med <= 0:
        return []
    return [
        round(float(v) / med, 2) if v and float(v) > 0 else 0.0
        for v in vals
    ]


def _leader_chart(c: Candidate | None) -> dict:
    """Ряд цены лидера потока плюс уровни его фигуры.

    Уровень зоны идёт вместе с рядом не для украшения: без него
    график сообщает «монета росла» — ровно то, что уже сказано
    процентом в тексте. Фигура FLOW построена вокруг уровня, и
    только он делает график осмысленным.
    """
    if c is None:
        return {}
    s = [float(x) for x in (c.raw.get("spark_1d") or []) if x]
    if len(s) < 4:
        return {}

    f = c.flow or {}
    from analytics_metrics import fmt_price_short

    # Число уходит в JS дважды и в разных ролях: zone нужен как
    # величина (по нему считается шкала графика), stop и target —
    # только как подпись. Поэтому первое остаётся float, а вторые
    # форматируются здесь: у монеты за четыре цента полное float
    # представление это семнадцать знаков в строке.
    stop = float(f.get("stop_hint") or 0.0)
    target = float(f.get("target_hint") or 0.0)

    return {
        "series": s,
        "zone": float(f.get("zone_price") or 0.0),
        "stop": fmt_price_short(stop) if stop > 0 else "",
        "target": fmt_price_short(target) if target > 0 else "",
        "score": int(getattr(c, "score", 0) or 0),
        "case": ((f.get("case") or "").replace("flow_", "") or "—"),
        "horizonDays": int(f.get("horizon_days") or 0),
    }


def _vol_chart(candidates: list[Candidate]) -> dict:
    """Монета с наибольшей кратностью объёма и её дневной ряд.

    Кратностью, а не оборотом в долларах: абсолютный оборот каждый
    день выводит одни и те же ликвидные имена, то есть является
    константой и новостью не бывает.

    Максимум берётся по ПЯТИ масштабам сразу — всплеск бывает
    двухчасовым и суточным, и спрашивать один масштаб значит
    пропускать половину случаев.
    """
    from render_dashboard import _data, _tick

    best, best_x = None, 0.0
    for c in candidates:
        for x in (c.raw.get("vol_ratio") or {}).values():
            try:
                x = float(x)
            except (TypeError, ValueError):
                continue
            if x > best_x:
                best_x, best = x, c

    if best is None or best_x <= 0:
        return {}

    d = _data(best)
    return {
        "sym": _tick(best),
        "x": round(best_x),
        "cap": _cap(d["cap"]),
        "ratios": _day_ratios(best.raw.get("spark_vol") or []),
        "v1h": round(d.get("v1h") or 0, 1),
        "v4h": round(d.get("v4h") or 0, 1),
        "v1d": round(d.get("v1d") or 0, 1),
        "funding": round(float(best.raw.get("funding") or 0.0), 3),
    }

def _peak_volume(candidates: list[Candidate]) -> dict:
    """Монета с наибольшей кратностью объёма к своей норме.

    Именно кратностью, а не оборотом в долларах: абсолютный оборот
    каждый день выводит одни и те же ликвидные имена, то есть
    является константой и новостью не бывает. Кратность уже
    посчитана в collect_metrics — это тот же vol_ratio, что кормит
    корзину аномалий, сети здесь ноль.

    Берётся максимум по ПЯТИ масштабам сразу: всплеск бывает
    двухчасовым и суточным, и спрашивать только один масштаб значит
    пропускать половину случаев.
    """
    best_sym, best_x = "", 0.0

    for c in candidates:
        ratios = (c.raw.get("vol_ratio") or {}).values()
        for x in ratios:
            try:
                x = float(x)
            except (TypeError, ValueError):
                continue
            if x > best_x:
                best_x, best_sym = x, c.base

    if best_x <= 0:
        return {}
    return {"sym": best_sym, "x": round(best_x)}

def _orbit_dormant(candidates: list[Candidate],
                   leader: Candidate | None) -> list[dict]:
    """Монеты в спячке — для строки «Спят» в сводке.

    Единственное состояние ДО движения, и источник у него — кандидаты
    текущего прогона, а не журнал: в журнал попадают лидеры, а спячка
    по определению случается раньше лидерства. Лидер прогона
    исключается — если он сам dormant, его блок выше уже сообщил
    и имя, и фигуру, вторая строка сказала бы то же самое дважды.
    """
    from render_dashboard import _tick

    lead_sym = leader.symbol if leader is not None else ""
    out = []
    for c in candidates:
        f = c.flow or {}
        if (f.get("case") or "") != "flow_dormant" or c.symbol == lead_sym:
            continue
        out.append({
            "t": _tick(c),
            "cap": _cap(_data(c)["cap"]),
            "score": int(getattr(c, "score", 0) or 0),
        })
    out.sort(key=lambda d: -d["score"])
    return out[:3]


def _orbit_journal() -> dict:
    """Итог журнала лидеров — для хвоста сводки.

    Считается при чтении, потому что это агрегат по всему файлу, а не
    поле записи: лучший и худший ход имеют смысл только на фоне
    остальных. «Новые» — записи, заведённые текущим прогоном:
    since_run записи совпадает со счётчиком прогонов в _meta.
    Это честная замена мёртвой строке «новые в топ-3» — поле newTop3
    никто никогда не писал, а since_run пишется каждым прогоном.
    """
    from render_dashboard import _read_json, LEADERS_PATH

    j = _read_json(LEADERS_PATH)
    meta = j.get("_meta") or {}
    run_no = int(meta.get("runs") or 0)

    recs = {k: v for k, v in j.items()
            if not k.startswith("_") and isinstance(v, dict)}
    if not recs:
        return {}

    # Условный портфель считается в журнале, здесь только берётся:
    # правило вложения живёт рядом с записями, а не в отрисовке.
    from analytics_leaders import portfolio_stats
    from analytics_manual_fields import stats as manual_stats
    port = portfolio_stats(j)
    gaps = manual_stats(j)

    def _lbl(sym: str) -> str:
        return sym[:-4] if sym.endswith("USDT") else sym

    fresh = [_lbl(s) for s, r in recs.items()
             if run_no > 0 and int(r.get("since_run") or 0) == run_no]

    by_chg = sorted(recs.items(),
                    key=lambda kv: float(kv[1].get("change_pct") or 0.0))
    worst_sym, worst = by_chg[0]
    best_sym, best = by_chg[-1]

    return {
        "n": len(recs),
        "fresh": fresh[:3],
        "port": port,
        "gaps": gaps,
        "best": {"t": _lbl(best_sym),
                 "chg": round(float(best.get("change_pct") or 0.0), 1)},
        "worst": {"t": _lbl(worst_sym),
                  "chg": round(float(worst.get("change_pct") or 0.0), 1)},
    }


def _orbit_market(candidates: list[Candidate], snapshot: RunSnapshot,
                  slices: list[dict]) -> dict:
    """Строка рынка и связанные строки сводки при входе.

    Режим и аппетит лежат в snapshot.market_regime (словарь: label /
    appetite / text) — тот же источник, что читает _head() для капсулы
    в шапке дашборда. Раньше я пробовал их как плоские атрибуты
    snapshot.regime / snapshot.appetite, которых не существует.

    BTC.D — не прогонная величина, а константа BTC_D из dashboard.py
    (см. комментарий там: «источник предстоит найти»). Здесь она
    честно остаётся той же заглушкой, а не превращается в фальшивые
    «прогонные» данные.

    Изменения цены BTC за сутки и недельного ряда в системе нет вообще
    — ни под каким именем. Это не ошибка в названии поля, а отсутствие
    источника: поля просто отдаются пустыми, и сводка честно покажет
    «—» вместо выдуманного числа. Записано в тех долг.
    """
    from render_dashboard import _get, BTC_D

    reg = getattr(snapshot, "market_regime", None) or {}
    _btc = get_btc_context()
    _breadth = _market_breadth(candidates)
    # Один вызов на обе величины: плашка на орбите берёт из него имя
    # и кратность, брифинг — тот же расчёт плюс ряд для графика.
    # Раздельные вызовы позволили бы лидеру объёма разойтись между
    # двумя местами экрана.
    _vol = _vol_chart(candidates)

    label = str(reg.get("label", "risk-off"))
    try:
        appetite = int(reg.get("appetite", 0) or 0)
    except (TypeError, ValueError):
        appetite = 0

    src = getattr(snapshot, "sectors", None) or []
    top = sorted(
        [(str(_get(r, "sector", "") or ""), float(_get(r, "avg_change_24h", 0) or 0))
         for r in src], key=lambda p: -p[1])[:1]

    leader = _orbit_flow_leader(candidates)
    from render_dashboard import _pick, _num, _tick

    def top3(sid: str) -> list[dict]:
        items = sorted(_pick(slices, sid)["items"],
                       key=lambda c: -_num(c, "rvol_1h"))[:3]
        return [{"t": _tick(c), "x": round(_num(c, "rvol_1h"), 1),
                 "cap": _cap(_data(c)["cap"])} for c in items]

    hourly_items = _pick(slices, "hourly")["items"]

    return {
        # «спокойный» и «осторожный» — пересказ режима, а не прогноз
        "calm": label.upper().replace("-", "").startswith("RISKON"),
        "appetite": f"{appetite}/5",
        # Биткоин: отдельный запрос, в выборку он не входит (MAJOR_TOKENS).
        # Пустой словарь от загрузчика означает «данных нет», и поля
        # честно остаются None — сводка покажет «—», а не ноль.
        "btc": _btc.get("ch_24h"),
        "btcUp": (_btc.get("ch_24h") or 0) >= 0,
        "btc7d": _btc.get("ch_7d"),
        "dom": BTC_D,    # доминации в системе по-прежнему нет, константа
        "series": _btc.get("spark") or [],

        # Замирание рынка и положение относительно выходных.
        # Оба — состояние фона, а не оценка монеты, и место им здесь,
        # рядом с режимом.
        "frozen": _breadth["frozen"],
        "maxChange": _breadth["maxChange"],
        "tail": _breadth["tail"],
        "tailPct": _breadth.get("tailPct"),
        "weekend": _weekend_state(),
        # Сектор дня убран из плашки: усреднение по сектору живёт час,
        # деньги за это время уже в другом. Поле оставлено — его читает
        # брифинг ниже, где оно идёт одной фразой среди прочих, а не
        # претендует на роль признака.
        "sector": (f"{top[0][0]} {top[0][1]:+.1f}%" if top else "—"),

        # Кратность объёма: отвечает на то, чего не говорят цены —
        # есть ли вообще деньги в рынке. Стоящая цена при живом объёме
        # и стоящая цена при мёртвом это разные дни.
        # peakVol остаётся для плашки на орбите — там нужны только имя
        # и кратность. volChart — тот же расчёт плюс ряд для графика;
        # обе величины берутся из одного вызова, чтобы лидер объёма в
        # плашке и в брифинге не мог разойтись.
        "peakVol": {"sym": _vol.get("sym", ""), "x": _vol.get("x", 0)},
        "volChart": _vol,
        "leaderChart": _leader_chart(leader),
        "leader": ({"t": _tick(leader),
                    "score": round(getattr(leader, "score", 0) or 0),
                    "case": case_key((leader.flow or {}).get("case", "")) or "—",
                    "cap": _cap(_data(leader)["cap"])} if leader else {}),
        "topVol": top3("surge"),
        "hourly": {"n": len(hourly_items), "list": top3("hourly")},
        "flowVol": _orbit_flow_bigvol(candidates),
        # Спячка и итог журнала — читает только сводка при входе.
        # Спячка идёт из кандидатов (до лидерства журнала не бывает),
        # итог журнала — агрегат по файлу, не поле записи.
        "dormant": _orbit_dormant(candidates, leader),
        "journal": _orbit_journal(),
    }



def render_orbit(candidates: list[Candidate], snapshot: RunSnapshot,
                 slices: list[dict]) -> str:
    # Отложенный импорт: см. docstring модуля
    from render_dashboard import _pick

    nodes = _orbit_nodes(candidates, snapshot, slices)
    stars = _orbit_stars(candidates)

    # Данные уходят отдельным <script type="application/json">, а не
    # склеиваются в разметку: экранировать нужно только "<".
    # Словарь рынка считается ОДИН раз и в переменную: его читают двое —
    # JSON для брифинга и подстановки разметки ниже. Прежде он собирался
    # прямо внутри json.dumps, и разметка не имела к нему доступа вовсе:
    # орбита показывала PUMP ON над строкой «рынок замер» в брифинге.
    market = _orbit_market(candidates, snapshot, slices)

    # CASE_RU уходит в данные, а не дублируется в скрипте. Имя подкейса
    # уже названо один раз во flow_report и оттуда же попадает в чип
    # карточки; второй список в JS разошёлся с первым сразу — легенда
    # говорила «топливо сверху», карточка «путь свободен», и это про
    # одну и ту же монету на одном экране.
    blob = json.dumps({"nodes": nodes, "stars": stars, "market": market,
                       "names": CASE_RU},
                      ensure_ascii=False).replace("<", "\\u003c")

    # Тот же источник, что читает _head() для капсулы режима: см.
    # docstring _orbit_market — прежде это были несуществующие атрибуты.
    from render_dashboard import BTC_D
    reg = getattr(snapshot, "market_regime", None) or {}
    regime = esc(str(reg.get("label", "RISK-OFF")).upper())
    try:
        appetite = esc(f'{int(reg.get("appetite", 0) or 0)}/5')
    except (TypeError, ValueError):
        appetite = esc("—")
    btc_d = esc(str(BTC_D))
    viral_n = len(_pick(slices, "viral")["items"])
    soc = f"{viral_n} всплеск" if viral_n else "тихо"

    # ── Фон рынка ────────────────────────────────────────────
    _mk = market or {}
    _frozen = bool(_mk.get("frozen"))
    _wknd = _mk.get("weekend") or ""

    # Класс на .ob, а не на отдельный слой: состояние касается всего
    # экрана — от него красятся и кометы, и надпись режима.
    frozen_cls = " frozen" if _frozen else ""

    # Пилюли собираются списком, а не условной строкой: их может быть
    # ноль, одна или две, и склейка через «·» в четырёх ветках
    # выродилась бы в лестницу if-ов ради пунктуации.
    _pills = []
    if _frozen:
        _pills.append('<span class="ob-frost-t">рынок замер</span>')
    if _wknd == "soon":
        _pills.append('<span class="ob-frost-w">завтра выходные</span>')
    elif _wknd == "now":
        _pills.append('<span class="ob-frost-w">выходные</span>')
    frost_pills = "".join(_pills)

    _mx = _mk.get("maxChange")
    frost_max = f"+{_mx:.0f}%" if _mx is not None else "—"
    frost_tail = str(_mk.get("tail", 0))
    frost_tail_pct = f"{_mk.get('tailPct') or 20:.0f}"

    # Объёма может не быть вовсе — тогда не показываем ничего.
    # Прочерк на месте величины, которой не бывает, читается как
    # поломка, а не как отсутствие данных.
    _pv = _mk.get("peakVol") or {}
    frost_vol = (
        f'<span class="ob-frost-n">объём '
        f'<b class="sec">{esc(_pv["sym"])}</b> <b>×{_pv["x"]}</b></span>'
        if _pv.get("sym") else ""
    )

    # Биткоин: None означает «данных нет» и печатается прочерком.
    # Ноль был бы враньём — это не «не изменился», это «не знаем».
    def _btc_cell(v):
        if v is None:
            return "—", "mute"
        return f"{v:+.1f}%", ("up" if v >= 0 else "dn")

    btc_txt, btc_cls = _btc_cell(_mk.get("btc"))
    btc7_txt, btc7_cls = _btc_cell(_mk.get("btc7d"))

    return f"""
<div class="ob{frozen_cls}" id="ob">
    <svg viewBox="0 0 1000 563" preserveAspectRatio="xMidYMid slice">
    <defs>
      <radialGradient id="ob-sky" cx="62%" cy="72%" r="78%">
        <stop offset="0" stop-color="#1a1508"/>
        <stop offset="0.45" stop-color="#0e0e14"/>
        <stop offset="1" stop-color="#08080b"/>
      </radialGradient>
      <radialGradient id="ob-haze" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="#F5A623" stop-opacity=".13"/>
        <stop offset="0.6" stop-color="#F5A623" stop-opacity=".04"/>
        <stop offset="1" stop-color="#F5A623" stop-opacity="0"/>
      </radialGradient>

      <!-- Дальний край семейства растворяется: одна маска на всю группу
           дешевле, чем прозрачность на каждой из сотни дуг -->
      <linearGradient id="ob-fadeg" x1="0.1" y1="0.9" x2="0.95" y2="0.05">
        <stop offset="0" stop-color="#fff" stop-opacity=".9"/>
        <stop offset="0.5" stop-color="#fff" stop-opacity=".45"/>
        <stop offset="1" stop-color="#fff" stop-opacity=".06"/>
      </linearGradient>
      <mask id="ob-fade"><rect width="1000" height="563" fill="url(#ob-fadeg)"/></mask>

      <radialGradient id="ob-bandg" cx="34%" cy="70%" r="40%">
        <stop offset="0" stop-color="#fff" stop-opacity="1"/>
        <stop offset="0.55" stop-color="#fff" stop-opacity=".45"/>
        <stop offset="1" stop-color="#fff" stop-opacity="0"/>
      </radialGradient>
      <mask id="ob-band"><rect width="1000" height="563" fill="url(#ob-bandg)"/></mask>
    <!-- Пыль: три тона. Тёплый над плотной частью диска, холодный
           по краям, нейтральный для середины. Однотонное облако
           ложится как запотевшее стекло — разнотонное читается как
           расстояние. -->
      <radialGradient id="ob-cl-w">
        <stop offset="0"   stop-color="#C9A76B" stop-opacity=".16"/>
        <stop offset="0.5" stop-color="#8A7550" stop-opacity=".07"/>
        <stop offset="1"   stop-color="#5A4A32" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="ob-cl-c">
        <stop offset="0"   stop-color="#6E8FC8" stop-opacity=".13"/>
        <stop offset="0.5" stop-color="#48608F" stop-opacity=".06"/>
        <stop offset="1"   stop-color="#2A3A5C" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="ob-cl-n">
        <stop offset="0"   stop-color="#9AA4B4" stop-opacity=".10"/>
        <stop offset="0.5" stop-color="#6A7382" stop-opacity=".045"/>
        <stop offset="1"   stop-color="#3E4653" stop-opacity="0"/>
      </radialGradient>
      <filter id="ob-glow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="5"/>
      </filter>
      <filter id="ob-spark" x="-300%" y="-300%" width="700%" height="700%">
        <feGaussianBlur stdDeviation="4"/>
      </filter>
      <filter id="ob-soft" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="34"/>
      </filter>
      <!-- Заливка лучей: белое ядро, цвет в середине, прозрачность
           на остриях. Сплошной цвет делал звезду плоской наклейкой —
           у настоящей вспышки яркость падает к концам. -->
      <radialGradient id="ob-starG">
        <stop offset="0" stop-color="#FFFBF0"/>
        <stop offset="0.22" stop-color="#FFE3AE"/>
        <stop offset="0.55" stop-color="#FFC46B" stop-opacity=".75"/>
        <stop offset="1" stop-color="#FFB347" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="ob-starS">
        <stop offset="0" stop-color="#FFFFFF"/>
        <stop offset="0.18" stop-color="#DCEBFF"/>
        <stop offset="0.5" stop-color="#7FB4FF" stop-opacity=".8"/>
        <stop offset="1" stop-color="#4A86E8" stop-opacity="0"/>
      </radialGradient>
      <!-- Ореол вокруг ядра: тоже градиентом, а не размытием —
           падение мягче, чем у гауссова блюра, и считается дешевле -->
      <!-- Холодный ореол — база. Золотой ниже достаётся только тем,
           у кого объём ≥ x50: иначе золотит всю сцену и признак
           перестаёт быть признаком. -->
      <radialGradient id="ob-starHc">
        <stop offset="0" stop-color="#FFFFFF" stop-opacity=".9"/>
        <stop offset="0.13" stop-color="#B7D6FF" stop-opacity=".5"/>
        <stop offset="0.4" stop-color="#5C93E8" stop-opacity=".16"/>
        <stop offset="1" stop-color="#3F72C8" stop-opacity="0"/>
      </radialGradient>
      <radialGradient id="ob-starH">
        <stop offset="0" stop-color="#FFFDF5" stop-opacity=".85"/>
        <stop offset="0.14" stop-color="#FFE3AE" stop-opacity=".5"/>
        <stop offset="0.42" stop-color="#FFC46B" stop-opacity=".15"/>
        <stop offset="1" stop-color="#FFC46B" stop-opacity="0"/>
      </radialGradient>

      <!-- Лёгкое размытие лучей. Идеально острые векторные грани
           читаются как корпус аппарата, а не как свет: у настоящей
           звезды край всегда мягкий. Ядро под фильтр не попадает. -->
      <filter id="ob-starBlur" x="-30%" y="-30%" width="160%" height="160%">
        <feGaussianBlur stdDeviation="0.4"/>
      </filter>

      <filter id="ob-grain">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3"/>
      </filter>
    </defs>

    <image x="0" y="0" width="1000" height="563"
           preserveAspectRatio="xMidYMid slice" href="{ORBIT_BG_SRC}"/>
    <ellipse cx="500" cy="281" rx="430" ry="220" fill="url(#ob-haze)"
             class="ob-breathe"/>

    <!-- Встречный слой: спицы и редкие дуги, идут в другую сторону
         и медленнее — параллакс вместо плоского кольца -->
    <g class="ob-spin-back" opacity=".5">
      <g id="ob-spokes" stroke="#cbd3da" opacity=".05"></g>
      <g id="ob-arcsBack" fill="none" opacity=".5"></g>
    </g>

    <g class="ob-spin">
      <g id="ob-arcs" fill="none" mask="url(#ob-fade)"></g>
      <g mask="url(#ob-band)">
        <g id="ob-arcsB" fill="none" filter="url(#ob-glow)" opacity=".5"></g>
        <g id="ob-arcsS" fill="none"></g>
      </g>
    </g>

    <g id="ob-cloud" class="ob-cloud"></g>

    <g id="ob-dust" class="ob-dust"></g>
    <g id="ob-links"></g>
    <g id="ob-orbit"></g>
    <g id="ob-nodes"></g>

    <!-- Звёзды идут последними, поверх зерна и дымки: стоя раньше них,
         они припудривались обоими слоями и тонули на светлых участках
         ленты. Это передний план сцены, а не часть фона. -->
        <g id="ob-stars"></g>
        <g id="ob-comets"></g>
  </svg>

<!-- Легенда рисуется скриптом из той же таблицы STRAT, что красит
     звёзды. Подписи руками однажды разойдутся с палитрой, а легенда,
     которая врёт про цвет, хуже отсутствующей. -->
<div class="ob-leg" id="ob-leg"></div>

<div class="ob-core">
    <div class="ob-core-k">РЕЖИМ РЫНКА</div>

    <!-- PUMP ON / OFF описывает ФАКТ: идут пампы или нет. Прежние
         RISK-ON/RISK-OFF были оценкой, и оценка расходилась — для
         рынка замирание плохо, для этой стратегии наоборот. С
         фактическим словом спорить нечему, а «хорошо это или плохо»
         говорят подсветка и плашка ниже.

         Слово считается из тех же двух чисел, что и плашка. Раньше
         оно приходило из доли зелёных, а плашка из хвоста
         распределения, и они могли противоречить: «RISK-ON» над
         «аппетит 2/5», где двойка означает risk-off.

         Побочно: расчётный режим из run.py и аппетит на экран больше
         не выводятся. Это и была дублирующая статистика — доля
         зелёных, разложенная по пяти ступеням и названная словом. -->
    <div class="ob-core-v v-live">PUMP ON</div>
    <div class="ob-core-v v-frost">PUMP OFF</div>

    <div class="ob-core-s">btc <b class="{btc_cls}">{btc_txt}</b> · неделя
      <b class="{btc7_cls}">{btc7_txt}</b> · btc.d <b>{btc_d}</b></div>

    <!-- Замирание и выходные — две отдельные пилюли, а не строка
         через точку: независимые причины с одинаковым следствием, и
         слитый текст через месяц не даст понять, что из двух было в
         тот день. Цвета разные — замирание это состояние рынка,
         выходные это календарь.

         Три числа рядом отвечают на разные вопросы: максимум дня —
         далеко ли ушла цена, счётчик — многие ли, объём — есть ли
         деньги в рынке вообще. PUMP OFF при объёме ×1954 и PUMP OFF
         при ×3 — принципиально разные дни. -->
    <div class="ob-frost">
      {frost_pills}
      <span class="ob-frost-n">максимум дня <b>{frost_max}</b></span>
      <span class="ob-frost-n">выше +{frost_tail_pct}% — <b>{frost_tail}</b></span>
      {frost_vol}
    </div>
  </div>

  <div class="ob-wrap" id="ob-wrap"></div>
</div>
<script type="application/json" id="ob-data">{blob}</script>
{ORBIT_JS}"""


ORBIT_JS = """
<script>

(function () {
  var NS = 'http://www.w3.org/2000/svg';
  var orb = document.getElementById('ob');
  if (!orb) return;

  var DATA = JSON.parse(document.getElementById('ob-data').textContent);
  var BLOCKS = DATA.nodes || [], STARS = DATA.stars || [];
  if (!BLOCKS.length) return;

  var CX = 500, CY = 281, RX = 372, RY = 148, TILT = -9;
  var NODE_LEN = [], cometEl = null, TOTAL_LEN = 0;
  var cometHead = null, cometHalo = null;

  /* Иконки категорий: пути в локальных координатах узла (±5).
     Кольцо-обводка рисуется отдельно и от иконки не зависит —
     размер и толщина настраиваются независимо друг от друга. */
  var ICON = {
    surge:  { d:'M-4.4 3.4 V-1.2 M0 3.4 V-4.4 M4.4 3.4 V0.4', s:1 },
    flow:   { d:'M-4.8 1.2 C-3 -2.6 -1.2 2.8 0.6 -0.8 C2 -3.4 3.6 -1 4.8 -2.2', s:1 },
    lead:   { d:'M0 -4.8 L1.25 -1.4 L4.8 -1.4 L1.95 0.85 L3 4.4 L0 2.25 '
               + 'L-3 4.4 L-1.95 0.85 L-4.8 -1.4 L-1.25 -1.4 Z' },
    setups: { d:'M0 -4.4 A4.4 4.4 0 1 1 -0.01 -4.4 M0 -1.5 A1.5 1.5 0 1 1 -0.01 -1.5', s:1 },
    hourly: { d:'M1.6 -4.8 L-3.2 0.7 H-0.4 L-1.6 4.8 L3.2 -0.9 H0.4 Z' },
    sector: { d:'M0 -4.4 A4.4 4.4 0 1 1 -0.01 -4.4 M0 0 L0 -4.4 A4.4 4.4 0 0 1 3.8 2.2 Z', s:1 },
    vetoed: { d:'M0 -4.4 A4.4 4.4 0 1 1 -0.01 -4.4 M-3.1 3.1 L3.1 -3.1', s:1 }
  };

  function el(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  /* Эллипс двумя дугами вместо <ellipse>: наклон задаётся параметром
     дуги, и не нужен отдельный transform на каждую из сотни линий. */
  function ellipsePath(cx, cy, a, b, rot) {
    var r = rot * Math.PI / 180;
    var dx = a * Math.cos(r), dy = a * Math.sin(r);
    return 'M' + (cx - dx).toFixed(1) + ' ' + (cy - dy).toFixed(1) +
           'A' + a.toFixed(1) + ' ' + b.toFixed(1) + ' ' + rot.toFixed(1) +
           ' 0 1 ' + (cx + dx).toFixed(1) + ' ' + (cy + dy).toFixed(1) +
           'A' + a.toFixed(1) + ' ' + b.toFixed(1) + ' ' + rot.toFixed(1) +
           ' 0 1 ' + (cx - dx).toFixed(1) + ' ' + (cy - dy).toFixed(1);
  }

  /* Семейство дуг. Толщина и прозрачность идут волной, а не линейно:
     при линейной прогрессии лента читается плоской штриховкой. */
  function buildArcs() {
    var N = 190, A0 = 82, A1 = 430, T0 = TILT - 23, T1 = TILT + 17;
    var host = document.getElementById('ob-arcs');
    var gb = document.getElementById('ob-arcsB');
    var gs = document.getElementById('ob-arcsS');

    for (var i = 0; i < N; i++) {
      var t = i / (N - 1);
      var a = A0 + (A1 - A0) * t;
      var b = a * (0.30 + 0.17 * t);
      var rot = T0 + (T1 - T0) * t;
      var wave = Math.pow(Math.sin(t * Math.PI), 0.6);
      var d = ellipsePath(CX, CY, a, b, rot);

      host.appendChild(el('path', { d: d, stroke: '#cbd3da',
        'stroke-width': (0.28 + 0.42 * wave).toFixed(2),
        opacity: (0.05 + 0.17 * wave).toFixed(3) }));

    // Ядро диска: узкая полоса около i=118. Спад степенной, а не
      // линейный — у резкой границы лента читается наклейкой.
      var k = 1 - Math.abs(i - 118) / 18;
      if (k > 0) {
        k = Math.pow(k, 0.75);
        var gold = { d: d, stroke: '#FFC46B',
          'stroke-width': (0.28 + 1.05 * k).toFixed(2),
          opacity: (0.10 + 0.52 * k).toFixed(3) };
        gs.appendChild(el('path', gold));
        gb.appendChild(el('path', gold));
      }
    }
  }

  /* Спицы и редкие встречные дуги: фон, а не рисунок — задают
     радиальную сетку, из-за которой кольцо перестаёт быть плоским. */
  function buildBack() {
    var sp = document.getElementById('ob-spokes');
    for (var i = 0; i < 24; i++) {
      var a = i / 24 * Math.PI * 2;
      sp.appendChild(el('line', {
        x1: (CX + Math.cos(a) * 70).toFixed(1),
        y1: (CY + Math.sin(a) * 28).toFixed(1),
        x2: (CX + Math.cos(a) * 470).toFixed(1),
        y2: (CY + Math.sin(a) * 186).toFixed(1), 'stroke-width': .5 }));
    }
    var back = document.getElementById('ob-arcsBack');
    for (var j = 0; j < 14; j++) {
      var t = j / 13, a2 = 120 + 310 * t;
      back.appendChild(el('path', {
        d: ellipsePath(CX, CY, a2, a2 * (0.5 - 0.14 * t), 26 - 30 * t),
        stroke: '#9fb0c8', 'stroke-width': .4,
        opacity: (0.10 + 0.10 * t).toFixed(2) }));
    }
  }

  /* Пылинки: глубина без фильтров и перерисовки — только прозрачность */
  function buildDust() {
    var host = document.getElementById('ob-dust');
    for (var i = 0; i < 46; i++) {
      var ang = Math.random() * Math.PI * 2;
      var rad = 0.35 + Math.random() * 0.75;
      var c = el('circle', {
        cx: (CX + Math.cos(ang) * RX * rad * 1.15).toFixed(1),
        cy: (CY + Math.sin(ang) * RY * rad * 1.5).toFixed(1),
        r: (0.6 + Math.random() * 1.3).toFixed(2),
        fill: Math.random() > 0.6 ? '#FFD98A' : '#dfe6ec' });
      c.style.animation = 'ob-twinkle ' + (3 + Math.random() * 6).toFixed(1) +
                          's ease-in-out ' + (Math.random() * 5).toFixed(1) +
                          's infinite';
      host.appendChild(c);
    }
  }

  /* Пылевое облако. Содержимое рисуется дважды: на месте и со сдвигом
       на ширину кадра влево. Группа едет вправо ровно на 1000 (см.
       ob-cloudrun в css.py) — в конце цикла вторая копия занимает место
       первой, и склейки не видно.

       Все пятна умещаются по ширине в один период. Шире периода пятно
       обрезалось бы при сдвиге, и шов стал бы заметен.

       Наклон -9° тот же, что у кольца: пыль лежит в плоскости диска,
       а не поперёк него. */
    var CLOUD = [
      { x: 120, y: 210, rx: 250, ry: 130, g: 'ob-cl-c', o: 1.00 },
      { x: 330, y: 330, rx: 300, ry: 155, g: 'ob-cl-n', o: 0.85 },
      { x: 560, y: 250, rx: 270, ry: 120, g: 'ob-cl-w', o: 1.00 },
      { x: 760, y: 360, rx: 230, ry: 140, g: 'ob-cl-w', o: 0.75 },
      { x: 900, y: 190, rx: 210, ry: 110, g: 'ob-cl-c', o: 0.80 },
      { x: 450, y: 460, rx: 320, ry: 105, g: 'ob-cl-n', o: 0.65 }
    ];

    function buildCloud() {
      var host = document.getElementById('ob-cloud');
      [-1000, 0].forEach(function (shift) {
        CLOUD.forEach(function (c) {
          host.appendChild(el('ellipse', {
            cx: c.x + shift, cy: c.y, rx: c.rx, ry: c.ry,
            fill: 'url(#' + c.g + ')', opacity: c.o,
            transform: 'rotate(-9 ' + (c.x + shift) + ' ' + c.y + ')' }));
        });
      });
    }

    /* Градиенты хвоста и головы. Собираются здесь, а не в разметке:
         четыре кометы это шестнадцать определений, и держать их руками
         значит править цвет в четырёх местах вместо одного.
         cols — тройка [светлый, средний, глубокий]. */
      function cometGrads(id, cols) {
        var defs = document.querySelector('#ob defs');

        function lin(sfx, stops) {
          var g = el('linearGradient', { id: id + sfx, x1: '0', y1: '0',
                                         x2: '1', y2: '0' });
          stops.forEach(function (s) {
            g.appendChild(el('stop', { offset: s[0], 'stop-color': s[1],
                                       'stop-opacity': s[2] }));
          });
          defs.appendChild(g);
        }

        lin('1', [[0, cols[0], .95], [0.28, cols[1], .55], [1, cols[2], 0]]);
        lin('2', [[0, cols[1], .70], [0.50, cols[1], .30], [1, cols[2], 0]]);
        lin('3', [[0, cols[0], .50], [1, cols[2], 0]]);

        // Ореол головы градиентом, а не размытием: фильтр на летящем
        // объекте пересчитывается каждый кадр, градиент — ни разу.
        var hd = el('radialGradient', { id: id + 'h' });
        [[0, '#FFFFFF', 1], [0.22, cols[0], .8],
         [0.55, cols[1], .28], [1, cols[2], 0]].forEach(function (s) {
          hd.appendChild(el('stop', { offset: s[0], 'stop-color': s[1],
                                      'stop-opacity': s[2] }));
        });
        defs.appendChild(hd);
      }

      /* Одна комета. Голова в нуле, хвост уходит в +X, вся группа
         развёрнута под угол полёта — поэтому направление задаётся одним
         числом, а не пересчётом координат каждой пряди.

         Прядей три: длинная тусклая, средняя яркая и короткая почти
         белая у самой головы. Разная длина и есть то, что отличает свет
         от нарисованной стрелки: одна градиентная полоса выглядит
         плоской, сколько её ни подкрашивай. */
    function comet(cfg, risk) {
        var host = document.getElementById('ob-comets');
        cometGrads(cfg.id, cfg.cols);

        var outer = el('g', { transform: 'translate(' + cfg.x + ' ' + cfg.y + ')' });
        // Признак вешается на ВНЕШНЮЮ группу, а не на движущуюся: скрывать
        // надо комету целиком, вместе с поворотом и хвостом.
        if (risk) outer.setAttribute('class', 'ob-comet-risk');
        var mover = el('g', { class: 'ob-comet' });
        mover.style.setProperty('--dx', cfg.dx + 'px');
        mover.style.setProperty('--dy', cfg.dy + 'px');
        mover.style.setProperty('--dly', cfg.dly + 's');

        var rot = el('g', { transform: 'rotate(' + cfg.ang + ')' });
        var len = cfg.len, w = cfg.w;

        // [доля длины, доля ширины, номер градиента]
        [[1.00, 1.00, '1'], [0.62, 0.55, '2'], [1.35, 0.32, '3']]
          .forEach(function (s) {
            var L = len * s[0], W = w * s[1];
            rot.appendChild(el('path', {
              d: 'M0 ' + (-W) + ' L' + L + ' ' + (-W * 0.14) +
                 ' L' + L + ' ' + (W * 0.14) + ' L0 ' + W + ' Z',
              fill: 'url(#' + cfg.id + s[2] + ')' }));
          });

        rot.appendChild(el('circle', { r: w * 4.2,
          fill: 'url(#' + cfg.id + 'h)', opacity: '.85' }));
        rot.appendChild(el('circle', { r: w * 0.72, fill: '#FFFFFF' }));

        mover.appendChild(rot);
        outer.appendChild(mover);
        host.appendChild(outer);
      }

      /* Четыре кометы с четырёх сторон, сдвинутые на четверть цикла.
         Одинаковое направление у всех читалось бы как метеорный поток из
         одной точки — здесь нужен случайный трафик, а не дождь.

         ang — угол хвоста, он равен направлению, обратному движению:
         хвост тянется туда, откуда комета пришла. Считается от вектора
         (dx, dy), а не подбирается на глаз. */
      function buildComets() {
        [
          { id: 'obcV', x: 1230, y: -90,  ang: -45,    dx: -450, dy:  450,
            len: 150, w: 2.4, dly: 0,
            cols: ['#EDE4FF', '#A78BFA', '#7C3AED'] },

          { id: 'obcA', x: 1200, y:  650, ang:  41.5,  dx: -430, dy: -380,
            len: 128, w: 2.0, dly: -6.5,
            cols: ['#FFF3DC', '#FFC46B', '#B36A10'] },

          { id: 'obcB', x: -190, y: -70,  ang: -139.6, dx:  470, dy:  400,
            len: 138, w: 2.1, dly: -13,
            cols: ['#E6F2FF', '#7FB4FF', '#3E9BE0'] },

          { id: 'obcG', x: 1220, y:  200, ang: -15.9,  dx: -560, dy:  160,
            len: 165, w: 1.7, dly: -19.5,
            cols: ['#FFF8E7', '#E0C060', '#8A6A14'] }
            // Обёртка обязательна: forEach передаёт колбэку (элемент, индекс,
          // массив), и при прямой передаче comet вторым аргументом уезжает
          // индекс. Для comet второй аргумент — признак «красная», поэтому
          // все кометы кроме нулевой помечались красными и исчезали с
          // живого рынка.
          ].forEach(function (cfg) { comet(cfg, false); });
      }

      /* Кометы замершего рынка. Четыре сверх обычных, с красными хвостами
           и своими направлениями: вместе с базовыми выходит пролёт примерно
           раз в три секунды против шести с половиной. Учащение трафика
           читается раньше, чем глаз доберётся до чисел в центре, поэтому
           отдельной подписи у него нет.

           Направления намеренно не повторяют базовые: пойди красные теми же
           трассами, они выглядели бы перекрашенными теми же кометами, а не
           дополнительными. */
        function buildRiskComets() {
          [
            { id: 'obcR1', x: -170, y:  620, ang:  138.8, dx:  480, dy: -420,
              len: 142, w: 2.2, dly: -3,
              cols: ['#FFE3E0', '#E8746A', '#8A2320'] },

            { id: 'obcR2', x:  600, y: -120, ang:  -58,   dx: -300, dy:  480,
              len: 134, w: 2.0, dly: -9.5,
              cols: ['#FFD9E2', '#D9536E', '#7A1E33'] },

            { id: 'obcR3', x: 1210, y:   60, ang:  -30,   dx: -520, dy:  300,
              len: 158, w: 1.9, dly: -16,
              cols: ['#FFE3E0', '#E8746A', '#8A2320'] },

            { id: 'obcR4', x:  300, y:  660, ang:  136.4, dx:  420, dy: -400,
              len: 126, w: 2.1, dly: -22.5,
              cols: ['#FFD9E2', '#D9536E', '#7A1E33'] }
          ].forEach(function (cfg) { comet(cfg, true); });
        }


  /* FNV-1a от тикера: положение звезды не должно прыгать между
     прогонами, иначе поле перестаёт узнаваться глазом. Тот же приём,
     что у _shuffle_key в отчёте. */
  function hash(str) {
    var h = 2166136261;
    for (var i = 0; i < str.length; i++) {
      h = (h ^ str.charCodeAt(i)) * 16777619 >>> 0;
    }
    return h;
  }

  /* Луч звезды: четырёхконечная вспышка. Тонкие «иглы» вместо кружка —
     кружков на сцене и так хватает, а вспышка читается как объект
     другого рода, не как ещё один узел. */
  /* Луч — треугольная игла: остриё на конце, основание в центре.
     Прежний ромб был толще всего в середине луча, и звезда читалась
     как значок. У настоящей вспышки ширина максимальна у ядра и
     сходит в точку — форма из четырёх таких игл даёт нужный силуэт. */
  function spikes(len, w, count) {
    var d = '';
    for (var i = 0; i < count; i++) {
      var a = i * (360 / count);
      d += 'M0 ' + (-len).toFixed(2) + 'L' + w.toFixed(2) + ' 0L' +
           (-w).toFixed(2) + ' 0Z';
      if (a) { /* повороты применяем через отдельные пути ниже */ }
    }
    return d;
  }

  /* Один луч, дальше группа поворачивается — так путь остаётся коротким,
     а количество и угол лучей задаются параметром. */
  function spike(len, w) {
    return 'M0 ' + (-len).toFixed(2) + 'L' + w.toFixed(2) + ' 0L0 ' +
           (w * 0.5).toFixed(2) + 'L' + (-w).toFixed(2) + ' 0Z';
  }

  function cross(g, len, w, grad, op, rot, count) {
    for (var i = 0; i < count; i++) {
      g.appendChild(el('path', { class: 'ob-ray', d: spike(len, w),
        fill: grad, opacity: op,
        transform: 'rotate(' + (rot + i * (360 / count)) + ')' }));
    }
  }

  /* Звёзды стоят вне кольца узлов: точка отвергается, если попала
     в полосу орбиты или в центральный прямоугольник, где всплывает
     карточка. Сдвиг детерминированный, поэтому перебор не случайный. */
  var PLACED = [];

  /* Поле, в котором вообще могут стоять звёзды. Значения те же, что
       стояли в проверке ниже, но теперь это ещё и область выборки. */
    var SKY = { x0: 95, x1: 905, y0: 100, y1: 479 };

  function starSpot(sym, idx) {
    var h = hash(sym);
    for (var k = 0; k < 60; k++) {
      /* Точка берётся прямо из прямоугольника кадра, а не как угол на
         эллипсе. Прежняя выборка была равномерной по УГЛУ, а не по
         месту, и это давало горизонтальные ряды: у сплюснутого эллипса
         dy/da обращается в ноль на верхней и нижней точках, поэтому
         широкий диапазон углов там укладывается почти в одну высоту.
         При RX = 372 против RY * 1.35 ≈ 200 сгущение неизбежно при
         любом наборе тикеров — дело не в хешах. */
      var x = SKY.x0 + ((h >>> (k % 8)) % 1000) / 1000 * (SKY.x1 - SKY.x0);
      var y = SKY.y0 + ((h >>> ((k + 3) % 12)) % 1000) / 1000 * (SKY.y1 - SKY.y0);

      /* Полоса орбиты теперь считается ОТ точки, а не задаёт её:
         единица — само кольцо, band — отклонение в любую сторону. */
      var rr = Math.hypot((x - CX) / RX, (y - CY) / (RY * 1.35));
      var band = Math.abs(rr - 1);
      var inCard = Math.abs(x - CX) < 185 && Math.abs(y - CY) < 140;
      /* И подальше от узлов с подписями: звезда, севшая на «ЛИДЕРЫ 46»,
         читается как часть этой категории, хотя смысл у неё другой. */
      var nearNode = false;
      for (var n = 0; n < BLOCKS.length; n++) {
        var np = pos(n);
        if (Math.hypot(np.x - x, np.y - y) < 104) { nearNode = true; break; }
      }
      /* И не ближе 78 к уже поставленной звезде: без этой проверки две
         соседние подписи накладываются и обе становятся нечитаемыми. */
      var tooClose = false;
      for (var m = 0; m < PLACED.length; m++) {
        if (Math.hypot(PLACED[m].x - x, PLACED[m].y - y) < 96) { tooClose = true; break; }
      }
      /* Порог расстояния поднят с 78 до 96 вместе с размером звезды:
         прежний ставился под радиус 4.5, при 7.6 подписи снова
         наезжают. Считается в tooClose выше по функции. */
      if (band > 0.18 && !inCard && !nearNode && !tooClose) {
        PLACED.push({ x: x, y: y });
        return { x: x, y: y };
      }
      h = (h * 16777619 + 1) >>> 0;
    }
    /* Место не нашлось. Раскладываем по золотому углу: шаг 2.39996
       радиан не укладывается ни в какую долю оборота, поэтому точки
       не выстраиваются в лучи и кольца — сетка 6 в ряд выдавала себя
       мгновенно. Радиус берём заведомо снаружи кольца и зажимаем в
       границы поля. */
    /* Запасная раскладка теперь тоже разводит соседей. Прежняя ставила
       точку по золотому углу и возвращала её как есть — а попадали
       сюда именно те звёзды, которым не нашлось места, то есть на
       плотном поле их несколько, и ложились они друг на друга.
       Спираль расширяется, пока не найдёт свободное место либо не
       упрётся в потолок попыток. */
    var fb = null;
    for (var t = 0; t < 40; t++) {
      var ga = (idx + t * 7) * 2.39996;
      var fr = 1.22 + ((idx + t) % 3) * 0.16 + t * 0.03;
      var cand = {
        x: Math.min(SKY.x1, Math.max(SKY.x0, CX + Math.cos(ga) * RX * fr)),
        y: Math.min(SKY.y1, Math.max(SKY.y0, CY + Math.sin(ga) * RY * 1.35 * fr))
      };
      var busy = false;
      for (var u = 0; u < PLACED.length; u++) {
        if (Math.hypot(PLACED[u].x - cand.x, PLACED[u].y - cand.y) < 84) {
          busy = true; break;
        }
      }
      if (!busy) { fb = cand; break; }
    }
    if (!fb) {
      var gz = idx * 2.39996;
      fb = {
        x: Math.min(SKY.x1, Math.max(SKY.x0, CX + Math.cos(gz) * RX * 1.3)),
        y: Math.min(SKY.y1, Math.max(SKY.y0, CY + Math.sin(gz) * RY * 1.35 * 1.3))
      };
    }
    PLACED.push(fb);
    return fb;
  }

  /* Разметка карточки монеты. Держится отдельно от отрисовки звезды:
     блок большой, и внутри отрисовки его было бы не найти. */
  /* Дерево фаз. Три состояния, каждое даёт действие, а не оценку.
     Гейт по ath — пороговый: глубже 80% разница уже ничего не решает. */
  function phase(s) {
    if ((s.ath || 0) > -80) return { a: 'вне зоны дна', k: 'wait' };
    if ((s.up || 0) < 150) return { a: 'первая фаза · брать', k: 'go' };
    return s.saw
      ? { a: 'пила · брать у нижней границы', k: 'go' }
      : { a: 'ровный рост · ждать сквиза', k: 'wait' };
  }

  /* Темп: сколько процента от дна приходится на один день наблюдения.
       Отвечает на «продолжение» из тех долга (14) — не «сколько прогресса
       набежало», а «набегает ли он вообще, или монета топчется». Ниже
       двух дней темп ещё не показателен (один хороший час раздувает
       число до абсурда) — тогда null, а не выдуманная цифра. */
    function rate(s) {
      var d = s.days || 0;
      if (d < 2) return null;
      return (s.up || 0) / d;
    }

  function toStop(s) {
    if (!s.stop || !s.px) return 0;
    return Math.round((s.px - s.stop) / s.px * 100);
  }

  /* Риск не заменяет действие, а стоит рядом: подмена вывода была бы
     решением за человека, а пометка оставляет выбор ему. */
  function act(s) {
    var p = phase(s), risks = [];
    if (s.firstRun) risks.push('первый разгон');
    if (s.topBubble) risks.push('пузырь на вершине');
    return '<div class="ob-sc-act ' + p.k + '">' + p.a + '</div>' +
      (risks.length
        ? '<div class="ob-sc-risk">' + risks.map(function (r) {
            return '<span>' + r + '</span>'; }).join('') + '</div>'
        : '');
  }

  function coinCard(s) {
    // Знак задаёт класс, а не цвет в разметке: цвета живут в стилях
    function sg(v) { return (v || 0) >= 0 ? 'up' : 'dn'; }
    function num(v) { return ((v || 0) >= 0 ? '+' : '') + (v || 0); }

    var R = 17, C = 2 * Math.PI * R;
    var dash = (C * Math.min(100, s.score || 0) / 100).toFixed(1);

    // Логарифм: между x3 и x709 линейная полоса делает первую невидимой
    function vfmt(v) { return v >= 10 ? Math.round(v) : v.toFixed(1); }
    function pct(v) { return Math.min(100, Math.log10(v) / Math.log10(1000) * 100); }

    // Ссылка на TradingView. Если символа нет (звезда из журнала без
    // текущего кандидата) — тикер остаётся обычным текстом, не битой
    // ссылкой в никуда.
    function tvLink(sym, inner) {
      if (!sym) return inner;
      var url = 'https://www.tradingview.com/chart/?symbol=BINANCE%3A' + sym + '.P';
      return '<a href="' + url + '" target="_blank" rel="noopener" ' +
             'class="ob-tv" onclick="event.stopPropagation()">' + inner + '</a>';
    }

    /* Две величины в одной колонке: крупно — объём сейчас, риской на
       дорожке и подписью снизу — объём на момент попадания в журнал.
       Сравнение отвечает на вопрос, разгоняется монета или затухает,
       и его нельзя получить ни из одного из чисел по отдельности. */
    function vol(label, v, was) {
      if (!v) return '<span class="ob-sc-v off"><i>' + label +
                     '</i><b>—</b><s></s></span>';
      var mark = was
        ? '<e style="left:' + pct(was).toFixed(0) + '%"></e>' : '';
      var arrow = '', cls = '';
      if (was) {
        var up = v >= was * 1.1, down = v <= was * 0.9;
        arrow = up ? '<span>↑</span>' : (down ? '<span>↓</span>' : '');
        cls = up ? ' gain' : (down ? ' fade' : '');
      }
      return '<span class="ob-sc-v' + cls + '"><i>' + label + '</i><b>×' +
             vfmt(v) + arrow + '</b><s><u style="width:' + pct(v).toFixed(0) +
             '%"></u>' + mark + '</s>' +
             (was ? '<em>было ×' + vfmt(was) + '</em>' : '') + '</span>';
    }

    /* Недельный график вместо трёх процентов. Все три горизонта —
       про форму, а не про величину: пилу от ровного роста процентом
       не отличить, «+76%» выглядит одинаково в обоих случаях.
       Поэтому одна фигура с разметкой: последние 3 дня выделены,
       последний день — точкой, горизонталь — уровень инвалидации. */
    var ser = s.series || [], spark = '';
    if (ser.length > 1) {
      var W = 128, H = 40, n = ser.length;
      var lo = Math.min.apply(null, ser), hi = Math.max.apply(null, ser);
      if (s.stop) lo = Math.min(lo, s.stop);
      var rng = (hi - lo) || 1;
      var X = function (i) { return (i / (n - 1) * W).toFixed(1); };
      var Y = function (v) { return (H - 2 - (v - lo) / rng * (H - 5)).toFixed(1); };
      var pts = ser.map(function (v, i) { return X(i) + ' ' + Y(v); });
      var col = (s.p7d || 0) >= 0 ? 'var(--up)' : 'var(--dn)';
      // хвост последних трёх дней рисуется поверх, ярче и толще
      var tail = pts.slice(Math.max(0, n - 4)).join(' ');

      var stopLine = '';
      if (s.stop) {
        var sy = Y(s.stop);
        stopLine = '<line class="stop" x1="0" y1="' + sy + '" x2="' + W +
                   '" y2="' + sy + '"/>';
      }
      /* Метки попаданий в журнал: по ним видно, поднимались ли точки
         входа. Возрастающая серия — стратегия взяла дно, а не боковик. */
      var hits = (s.hits || []).map(function (i) {
        return i >= 0 && i < n
          ? '<circle class="hit" cx="' + X(i) + '" cy="' + Y(ser[i]) + '" r="2"/>'
          : '';
      }).join('');

      spark = '<svg class="ob-sc-spark" viewBox="0 0 ' + W + ' ' + H + '">' +
        stopLine +
        '<polyline class="wk" points="' + pts.join(' ') +
          '" stroke="' + col + '"/>' +
        '<polyline class="d3" points="' + tail + '" stroke="' + col + '"/>' +
        hits +
        '<circle class="last" cx="' + X(n - 1) + '" cy="' + Y(ser[n - 1]) +
          '" r="2.2" fill="' + col + '"/>' +
      '</svg>';
    }

    var fund = s.fund || 0;
    var fx = Math.max(2, Math.min(94, 50 + fund / 0.2 * 50));
    var left = Math.max(0, 14 - (s.days || 0));

    var p = phase(s), risks = [];
    if (s.firstRun) risks.push('первый разгон');
    if (s.topBubble) risks.push('пузырь на вершине');

    /* Краткий вид: только то, что нужно для решения — что делать, как
       выглядит движение, сколько до уровня. Подробности прячутся за
       клик: постоянно держать их на экране значит заставлять читать
       двадцать чисел там, где решают три. */
    var brief =
      '<div class="ob-sc-brief">' +
        '<div class="ob-b-t">' + tvLink(s.coin, s.t) + '</div>' +
        '<div class="ob-b-act ' + p.k + '">' + p.a + '</div>' +
        spark +
        '<div class="ob-b-lvl">до уровня <b>' +
          (s.stop ? '−' + toStop(s) + '%' : '—') + '</b></div>' +
        (risks.length
          ? '<div class="ob-sc-risk">' + risks.map(function (r) {
              return '<span>' + r + '</span>'; }).join('') + '</div>'
          : '') +
        '<div class="ob-b-more">подробнее</div>' +
      '</div>';

    return brief +
      '<div class="ob-sc-det">' +
      '<div class="ob-sc-id">' +
        '<div class="ob-sc-hd">' +
          '<span style="flex:1 1 auto;min-width:0">' +
            '<span class="ob-sc-t">' + tvLink(s.coin, s.t) + '</span>' +
            '<span class="ob-sc-sec">' + (s.sector || '—') + '</span></span>' +
          '<svg class="ob-sc-ring" viewBox="-22 -22 44 44">' +
            '<circle class="trk" r="' + R + '"/>' +
            '<circle class="val" r="' + R + '" transform="rotate(-90)" ' +
              'stroke-dasharray="' + dash + ' ' + C.toFixed(1) + '"/>' +
            '<text y="4" text-anchor="middle">' + (s.score || '—') + '</text>' +
          '</svg>' +
        '</div>' +
        '<div class="ob-sc-tags">' +
          '<span class="ob-sc-tag"><u>' + (s.cap || '—') + '</u> кап</span>' +
          /* Глубже 80% от ATH разница ничего не решает — это гейт, а не
             величина. Поэтому там, где гейт пройден, число не выводим
             вообще: «−92%» и «−98%» означают одно и то же «у дна», а
             цифра заставляет вглядываться в несущественное. Число
             остаётся только когда гейт НЕ пройден — там оно работает. */
          ((s.ath || 0) <= -80
            ? '<span class="ob-sc-tag low">у дна</span>'
            : '<span class="ob-sc-tag ath"><u>' + (s.ath || 0) +
              '%</u> от ath</span>') +
          /* Рост от дна информативен до 150%: до порога вход открыт,
             выше — риск, и точное значение уже не меняет решения.
             Поэтому там показываем не число, а сам факт превышения. */
          ((s.up || 0) > 150
            ? '<span class="ob-sc-tag over">&gt;150% от дна · ' +
              (s.updays || 0) + ' дн</span>'
            : '<span class="ob-sc-tag up">+' + (s.up || 0) + '% от дна · ' +
              (s.updays || 0) + ' дн</span>') +
        '</div>' +
        '<span class="ob-sc-chip"><i class="ob-sc-dot" style="background:' +
          stratOf(s).c + ';color:' + stratOf(s).c + '"></i>' +
          (s.pattern || '—') + '</span>' +
        act(s) +
      '</div>' +

      '<div class="ob-sc-st">' +
        '<div class="ob-sc-vols">' + vol('1Ч', s.v1h, s.e1h) +
          vol('4Ч', s.v4h, s.e4h) +
          vol('1Д', s.v1d, s.e1d) + '</div>' +
        '<div class="ob-sc-row">' +
          '<span><span class="ob-sc-p7 ' + sg(s.p7d) + '">' + num(s.p7d) +
            '%</span>' +
          '<div class="ob-sc-pd">неделя · до уровня <b class="' +
            (toStop(s) <= 10 ? 'dn' : '') + '">' +
            (s.stop ? '−' + toStop(s) + '%' : '—') + '</b></div></span>' +
          spark +
        '</div>' +
        '<div class="ob-sc-foot">' +
          '<span class="ob-sc-fund ' + (fund >= 0 ? 'pos' : 'neg') +
            '">фандинг<s><u style="left:' + fx.toFixed(0) +
            '%"></u></s><b>' + (fund >= 0 ? '+' : '') + fund.toFixed(3) +
            '%</b></span>' +
          /* «В топе» убрано: раз монета нарисована звездой, она уже в топе,
             и повторять это значит тратить строку на известное. Счётчик
             попаданий переименован в признак тренда: сама по себе цифра
             «3×» ничего не сообщает, а накопленный процент читается как
             мера подтверждённости. Каждое попадание даёт +5%. */
          '<span>тренд <b>' + Math.min(100, (s.streak || 1) * 5) +
            '%</b></span>' +
          /* Тот же принцип, что и в оверлее (14.2): показываем факт,
                       не вердикт. «−» вместо числа при days<2 — честнее, чем
                       раздутый темп по одному часу наблюдения. */
                    '<span>в журнале <b>' + (s.days || 0) + '</b> дн · темп <b>' +
                      (rate(s) === null ? '—' : (rate(s) >= 0 ? '+' : '') +
                        rate(s).toFixed(1) + '%/д') + '</b></span>' +
        '</div>' +
        '<div class="ob-sc-life"><u style="width:' +
          Math.round(left / 14 * 100) + '%"></u></div>' +
      '</div>' +
      '</div>';
  }

  /* ── Стратегии ───────────────────────────────────────────────
     Цвет звезды несёт подкейс, семейство цвета — стадию движения:
     холодные у предполагаемого дна, тёплые пока движение идёт,
     догорающий когда состоялось.

     Почему не шесть произвольных цветов: семь узлов орбиты уже
     занимают янтарь, золото, зелёный, синий, фиолетовый и ржавый.
     Шесть независимых оттенков сверху дали бы тринадцать значащих
     цветов и два разных языка на одном экране — фиолетовая звезда
     читалась бы как «сектор». Температурная логика отличает звёзды
     от узлов правилом, а не подбором хексов.

     Стадия здесь выражена ТОЛЬКО цветом. Радиусом её выразить
     нельзя: starSpot запрещает полосу ±0.18 вокруг кольца, и на
     три пояса поля не хватает (см. шапку патча). */
  /* Здесь только цвет и стадия. Имя приходит из CASE_RU через данные:
     оно уже названо в одном месте и попадает в чип карточки, а второй
     список рядом гарантированно разойдётся с первым. */
  var NAMES = DATA.names || {};
  var STRAT = {
    dormant:  { c: '#7E9AB5', stage: 0 },
    hidden:   { c: '#7FE3D4', stage: 0 },
    spring:   { c: '#6FC9E8', stage: 0 },
    churn:    { c: '#F0B85C', stage: 1 },
    taker:    { c: '#FFD98A', stage: 1 },
    leverage: { c: '#E89AB0', stage: 1 },
    fuel:     { c: '#C4703A', stage: 2 }
  };
  function stratName(k) { return NAMES[k] || k; }

  /* Монета из журнала, выпавшая из текущей выборки и не имеющая
     entry_case. Серый, а не цвет какой-нибудь стратегии: неизвестное
     обязано выглядеть неизвестным, иначе оно читается как факт. */
  var STRAT_NONE = { c: '#8D97A6', stage: -1 };

  var STAGE = [
    'у предполагаемого дна',
    'движение идёт',
    'движение состоялось'
  ];

  /* Градиенты под каждую стратегию делаются скриптом, а не руками в
     defs: шесть подкейсов на два градиента — двенадцать блоков,
     которые пришлось бы править синхронно с палитрой. Здесь цвет
     живёт в одном месте. */
  function tintGrad(id, c, halo) {
    if (document.getElementById(id)) return id;
    /* defs берётся у того же SVG, в котором лежат звёзды, а не первым
       попавшимся в документе: карточки монет тоже рисуют инлайновые
       SVG со спарклайнами, и querySelector нашёл бы их, если бы они
       оказались раньше по разметке. Здесь связь прямая. */
    var stars = document.getElementById('ob-stars');
    var scene = stars && stars.ownerSVGElement;
    if (!scene) return id;
    var defs = scene.querySelector('defs');
    if (!defs) {
      defs = el('defs', {});
      scene.insertBefore(defs, scene.firstChild);
    }
    var g = el('radialGradient', { id: id });
    var stops = halo
      ? [[0, '#FFFDF6', .85], [0.14, c, .48], [0.42, c, .14], [1, c, 0]]
      : [[0, '#FFFDF6', 1], [0.20, c, 1], [0.55, c, .74], [1, c, 0]];
    stops.forEach(function (st) {
      g.appendChild(el('stop', {
        offset: st[0], 'stop-color': st[1], 'stop-opacity': st[2] }));
    });
    defs.appendChild(g);
    return id;
  }

  function stratOf(s) { return STRAT[s.st] || STRAT_NONE; }

  /* Легенда строится только по тем стратегиям, которые в прогоне
     реально сработали. Полный список из шести объяснял бы цвета,
     которых на экране нет, и заставлял бы искать несуществующее. */
  function buildLegend() {
    var host = document.getElementById('ob-leg');
    if (!host) return;
    var live = {};
    STARS.forEach(function (s) { if (STRAT[s.st]) live[s.st] = 1; });
    var keys = Object.keys(live);
    if (!keys.length) { host.style.display = 'none'; return; }

    /* Шапка живёт всегда и в свёрнутом виде остаётся единственным,
       что видно: ряд цветных точек. Когда открыта карточка монеты,
       легенда мешает — но исчезать ей нельзя, иначе цвет звезды под
       карточкой становится нечитаемым. Поэтому сворачивается, а не
       прячется, и раскрывается наведением. */
    var dots = keys.map(function (k) {
      return '<i class="ob-leg-d" style="background:' + STRAT[k].c +
             ';color:' + STRAT[k].c + '"></i>';
    }).join('');
    var html = '<div class="ob-leg-h"><span>стратегии</span>' +
               '<span class="ob-leg-dots">' + dots + '</span></div>' +
               '<div class="ob-leg-body">';

    STAGE.forEach(function (title, i) {
      var inStage = keys.filter(function (k) { return STRAT[k].stage === i; });
      if (!inStage.length) return;
      html += '<div class="ob-leg-g"><div class="ob-leg-s">' + title + '</div>';
      inStage.forEach(function (k) {
        /* Тикеры, а не счётчик. Сколько монет в стадии — видно по
           самим звёздам; чего по ним не видно, так это КТО именно,
           потому что подписи мелкие и разбросаны по всему полю. */
        var syms = STARS.filter(function (s) { return s.st === k; })
                        .map(function (s) { return s.t; });
        html += '<div class="ob-leg-r">' +
          '<span class="ob-leg-d" style="background:' + STRAT[k].c +
          ';color:' + STRAT[k].c + '"></span>' +
          '<span class="ob-leg-n">' + stratName(k) + '</span></div>' +
          '<div class="ob-leg-c" style="color:' + STRAT[k].c + '">' +
          syms.join(' · ') + '</div>';
      });
      html += '</div>';
    });
    host.innerHTML = html + '</div>';
  }

  function buildStars() {
    var host = document.getElementById('ob-stars');
    /* Список занятых мест чистится при каждой сборке. Без этого
       повторный рендер видел все прежние точки занятыми, перебор
       упирался в лимит и уходил в запасную раскладку — где проверки
       на соседей нет вовсе. */
    PLACED.length = 0;
    Object.keys(STRAT).forEach(function (k) {
      tintGrad('ob-sg-' + k, STRAT[k].c, false);
      tintGrad('ob-sh-' + k, STRAT[k].c, true);
    });
    tintGrad('ob-sg-none', STRAT_NONE.c, false);
    tintGrad('ob-sh-none', STRAT_NONE.c, true);
    buildLegend();

    STARS.forEach(function (s, idx) {
      var sc = stratOf(s);
      var sid = STRAT[s.st] ? s.st : 'none';
      var p = starSpot(s.t, idx);
      var f = s.f;                              // свежесть 0..1
      /* Диапазон сжат: было 4..15, стало 3..8. Разброс всё ещё читается,
         но свежая звезда больше не спорит по весу с узлом категории. */
      /* Было 2.4..4.5 у обычной звезды. При поле 1000×563 это точка в
         три пикселя с подписью в 5.7 — цвет на такой площади не
         различается вовсе, а именно цвет теперь несёт стратегию.
         Увеличено примерно вдвое; коллизии разводит starSpot, у
         которого порог расстояния поднят тем же патчем. */
      var r = (s.lead ? 6.2 : 4.2) + f * 3.4;
            /* Яркость отдана темпу, а не свежести: свежесть уже несёт размер,
               дублировать её в яркости — терять канал впустую. Звезда, которая
               быстро набирает %, должна светить ярче звезды, которая столько
               же дней топчется у дна, даже если обе одного размера (14.4).
               RATE_REF — не порог качества, а просто ориентир «здорового»
               темпа по паре примеров вечера (ARC/BLESS ≈19%/д); при желании
               подвинуть одной константой. */
            var RATE_REF = 20;
            var rt = rate(s);
            var rateNorm = rt === null ? 0.5 : Math.max(0, Math.min(1, rt / RATE_REF));
            /* Нижняя граница поднята с 0.18 до 0.46. Прежняя ставилась
               в расчёте на живой темп, но rate() читал s.days, которого
               в звезде не было — величина всегда возвращала null, и
               ВСЕ звёзды садились на 0.43. Теперь days приходит, темп
               считается, и пол нужен другой: даже самая медленная
               звезда обязана читаться цветом. */
            var op = 0.46 + rateNorm * 0.42;

      var g = el('g', { class: 'ob-star' + (s.new ? ' fresh' : '') });
      if (s.coin) g.dataset.coin = s.coin;      // клик откроет карточку монеты
      g.setAttribute('transform', 'translate(' + p.x.toFixed(1) + ' ' +
                                  p.y.toFixed(1) + ')');
      // фаза мерцания своя у каждой — иначе восемь звёзд пульсируют в такт
      if (s.new) g.style.animationDelay = (hash(s.t) % 3600) + 'ms';


      /* Цвет отдан объёму: золото у x50 и выше, холодное серебро ниже.
         Свежесть уже сказана размером и яркостью — двум признакам
         одного свойства не хватило бы. */
      /* Синий — база, золото целиком достаётся тем, у кого объём ≥ x50.
         Признак должен читаться цветом самой звезды, а не деталью:
         подсветка одними короткими лучами терялась при нитевидных лучах. */
      /* Цвет отдан стратегии. Прежде его нёс объём: золото у ×50 и
         выше, холодное серебро ниже — то есть «горячая» и «золотая»
         были одним и тем же признаком. Кратность объёма при этом
         никуда не делась: она осталась вспышкой и кольцом ниже, а
         цвет освободился под то, чего на экране не было вовсе, —
         под то, КАКАЯ фигура сработала. */
      var col = sc.c;
      var grad = 'url(#ob-sg-' + sid + ')';
      var accent = grad;

      /* Ореол ярче и плотнее у центра: именно он читается как свечение,
         лучи только задают характер. */
      g.appendChild(el('circle', { r: r * 2.2,
        fill: 'url(#ob-sh-' + sid + ')',
        opacity: op.toFixed(2) }));

      /* Каждая звезда чуть повёрнута по своему хешу: одинаковый наклон
         у всех восьми читался как повторённая наклейка. */
      var tilt = (hash(s.t) % 22) - 11;

      /* Лучи живут в своей группе под фильтром размытия, ядро — снаружи:
         размывать пересвеченную точку нельзя, она и держит центр. */
      var rays = el('g', { filter: 'url(#ob-starBlur)' });

      // длинные тонкие иглы — основной крест
      cross(rays, r * 3.8, r * 0.085, grad, op.toFixed(2), tilt, 4);
      // короткие под 45° — у x50 золотом, это и есть подсветка признака
      cross(rays, r * 1.35, r * 0.055, s.hot ? accent : grad,
            (op * (s.hot ? 0.8 : 0.5)).toFixed(2), tilt + 45, 4);
      /* Веер коротких лучиков вокруг ядра: на референсе именно он
         отличает источник света от нарисованного креста. */
      cross(rays, r * 0.95, r * 0.03, grad, (op * 0.35).toFixed(2), tilt + 22, 12);

      if (s.hot) {
        /* Блик-растяжка поперёк: даёт объектив, а не рисунок.
           Только у x50 — на всех сразу читался бы как дефект. */
        rays.appendChild(el('ellipse', { rx: r * 4.6, ry: Math.max(.25, r * 0.022),
          fill: accent, opacity: (op * 0.5).toFixed(2),
          transform: 'rotate(' + tilt + ')' }));
        var halo = el('circle', { class: 'ob-star-ring', r: r * 1.35 });
        halo.style.transformOrigin = '0 0';
        halo.style.animationDelay = (hash(s.t) % 4000) + 'ms';
        g.appendChild(halo);
      }

      g.appendChild(rays);

      // ядро: маленькое и почти белое, оно и создаёт ощущение свечения
      g.appendChild(el('circle', { r: Math.max(.75, r * 0.22), fill: '#FFFFFF',
        opacity: '1' }));

      /* Подпись у каждой звезды: без тикера объект опознать нельзя,
         а тултип требует навести курсор и найти нужную точку.
         Иерархию держит не наличие подписи, а её вес — прозрачность
         идёт по свежести, поэтому свежие читаются сразу, а старые
         не превращают поле в список. */
      /* Подпись сбоку, а не под звездой: луч вытянут по вертикали,
         и текст снизу ложился бы прямо на него. У правого края
         сторона меняется, иначе подпись уходит за кадр. */
      var right = p.x < 640;
      var dx = right ? r * 1.7 + 5 : -(r * 1.7 + 5);
      var anchor = right ? 'start' : 'end';
      /* Подпись читается сразу и одинаково у всех звёзд. Свежесть уже
         сказана размером и яркостью самой звезды — гасить ещё и текст
         значит прятать то единственное, ради чего он тут есть. */

      /* Подпись красится стратегией, а не признаком объёма: тикер и
         звезда обязаны читаться как одно целое, иначе цвет придётся
         сопоставлять глазами. Лидер прогона сохраняет своё золото —
         это про место в прогоне, а не про фигуру. */
      var t = el('text', {
        class: 'ob-star-lbl' + (s.lead ? ' lead' : ''),
        x: dx, y: s.up ? -0.6 : 1.8, 'text-anchor': anchor,
        fill: s.lead ? '#FFD98A' : col, opacity: '.95'
      });
      t.textContent = s.t;
      g.appendChild(t);

      // Рост от дна: величина, ради которой монета попала в журнал
      if (s.up) {
        /* Светлый тёплый, а не зелёный и не приглушённый: зелёный поверх
           золотых дуг режет глаз и читается как статус, а песочный впотьмах
           сливался с фоном. Здесь нужна читаемость — это и есть величина,
           ради которой монета попала в журнал. Иерархию с тикером держит
           кегль и трекинг, а не яркость. */
        var u = el('text', { class: 'ob-star-up', x: dx, y: 6.2,
          'text-anchor': anchor, fill: '#EDE6D8', opacity: '.95' });
        u.textContent = '+' + s.up + '%' + (s.updays ? ' · ' + s.updays + 'д' : '');
        g.appendChild(u);
      }

      /* Карточка монеты. Стоит по ту же сторону, что и подпись, но дальше:
         так она не накрывает саму звезду и не уходит за край кадра. */
      var side = p.x < 640 ? 1 : -1;
      var cx = Math.max(215, Math.min(785, p.x + side * 215));
      var cy = Math.max(120, Math.min(520, p.y));

      var card = document.createElement('div');
      card.className = 'ob-scard brief';
      // Тон по score, как в отчёте: 90+ золото, ниже зелёный
      card.style.setProperty('--tone', (s.score || 0) >= 90 ? '#FFB020' : '#22E08A');
      card.innerHTML = coinCard(s);
      orb.appendChild(card);

      /* Наведение вешаем на группу звезды, а не на карточку: карточка
         сама pointer-events:none, иначе она перехватывала бы курсор
         и мигала бы при каждом входе-выходе. */
      /* Облёт на время останавливаем: иначе комета продолжает
         переключать карточки категорий под открытой карточкой монеты. */
      /* Клик по звезде разворачивает карточку и закрепляет её:
         в подробном виде по ней надо водить глазами, а не терять
         её при первом же движении мыши. */
      g.addEventListener('click', function (e) {
        e.stopPropagation();
        var full = card.classList.toggle('full');
        card.classList.toggle('brief', !full);
        card.style.pointerEvents = full ? 'auto' : 'none';
        pinned = full ? s.t : null;
      });

      g.addEventListener('pointerenter', function () {
        card.classList.add('on');
        g.classList.add('hot');
        orb.classList.add('starred');
        paused = true;
      });
      g.addEventListener('pointerleave', function () {
        if (card.classList.contains('full')) return;   // развёрнутую не прячем
        card.classList.remove('on');
        g.classList.remove('hot');
        orb.classList.remove('starred');
        paused = false;
      });

      host.appendChild(g);
    });
  }

  function pos(i) {
    var ang = -Math.PI / 2 + i * (2 * Math.PI / BLOCKS.length);
    var x = Math.cos(ang) * RX, y = Math.sin(ang) * RY;
    var r = TILT * Math.PI / 180;
    return { x: CX + x * Math.cos(r) - y * Math.sin(r),
             y: CY + x * Math.sin(r) + y * Math.cos(r) };
  }

  function sparkSVG(vals, color) {
    if (!vals || vals.length < 2) return '';
    var hi = Math.max.apply(null, vals) || 1;
    var pts = vals.map(function (v, i) {
      return (i / (vals.length - 1) * 280).toFixed(1) + ' ' +
             (26 - v / hi * 24).toFixed(1);
    }).join(' ');
    return '<svg class="ob-card-spark" viewBox="0 0 280 26" ' +
           'preserveAspectRatio="none"><polyline points="' + pts +
           '" fill="none" stroke="' + color + '" stroke-width="1.1"/></svg>';
  }

  function build() {
    var orbitG = document.getElementById('ob-orbit');
    var linkG = document.getElementById('ob-links');
    var nodeG = document.getElementById('ob-nodes');
    var wrap = document.getElementById('ob-wrap');
    var ringPath = ellipsePath(CX, CY, RX, RY, TILT);

    orbitG.appendChild(el('path', { d: ringPath, fill: 'none',
      stroke: '#2e2a20', 'stroke-width': .5, opacity: '.9' }));

    var comet = el('path', { d: ringPath, fill: 'none', stroke: '#FFE9C0',
      'stroke-width': .6, 'stroke-linecap': 'round', pathLength: 1000,
      'stroke-dasharray': '22 978', filter: 'url(#ob-spark)', opacity: '.95' });
    orbitG.appendChild(comet);
    cometEl = comet;

    /* Голова кометы. Штрих через stroke-dasharray сам по себе даёт
       ровный хвост без явного начала — точка возвращает направление
       движения. Позиция берётся из getPointAtLength того же пути,
       поэтому голова не может разъехаться с хвостом. */
    cometHead = el('circle', { r: 1.7, fill: '#FFF3DC', opacity: '.95' });
    cometHalo = el('circle', { r: 4.5, fill: '#FFD98A', opacity: '.5',
      filter: 'url(#ob-spark)' });
    orbitG.appendChild(cometHalo);
    orbitG.appendChild(cometHead);

    /* Попутные частицы на чистом CSS: их позицию читать не нужно,
       в отличие от кометы — она одна ведётся из JS. */
    [[19000, 0], [31000, -320], [44000, -640]].forEach(function (m) {
      var mote = el('path', { d: ringPath, fill: 'none', stroke: '#cbd3da',
        'stroke-width': .35, 'stroke-linecap': 'round', pathLength: 1000,
        'stroke-dasharray': '7 993', opacity: '.6' });
      mote.setAttribute('class', 'ob-mote');
      mote.style.animationDuration = m[0] + 'ms';
      mote.style.strokeDashoffset = m[1];
      orbitG.appendChild(mote);
    });

    /* Длина дуги эллипса не пропорциональна углу, поэтому позицию
       сегмента ищем по самому пути. Иначе цветные дуги уезжают от узлов. */
    var probe = el('path', { d: ringPath });
    orbitG.appendChild(probe);
    TOTAL_LEN = probe.getTotalLength();
    var SAMPLES = [];
    for (var q = 0; q <= 720; q++) {
      var L = TOTAL_LEN * q / 720;
      SAMPLES.push({ L: L, p: probe.getPointAtLength(L) });
    }
    probe.remove();

    function lengthAt(pt) {
      var best = 0, bd = Infinity;
      SAMPLES.forEach(function (s) {
        var d = (s.p.x - pt.x) * (s.p.x - pt.x) + (s.p.y - pt.y) * (s.p.y - pt.y);
        if (d < bd) { bd = d; best = s.L; }
      });
      return best;
    }

    var SEG = TOTAL_LEN / BLOCKS.length;

    BLOCKS.forEach(function (b, i) {
      var p = pos(i);

      /* Доля категории — цветной сегмент на самой орбите: длина дуги
         пропорциональна величине, и кольцо читается как распределение. */
      var shown = SEG * 0.82 * (b.w || 0.5);
      var seg = el('path', { class: 'ob-seg', d: ringPath, fill: 'none',
        stroke: b.c, 'stroke-width': .5, 'stroke-linecap': 'round',
        opacity: '.95',
        'stroke-dasharray': shown.toFixed(1) + ' ' + TOTAL_LEN.toFixed(1),
        'stroke-dashoffset': (-(lengthAt(p) - shown / 2)).toFixed(1) });
      seg.dataset.id = b.id;
      orbitG.appendChild(seg);

      var link = el('line', { class: 'ob-link', x1: p.x, y1: p.y,
        x2: CX, y2: CY, stroke: b.c, 'stroke-width': .6 });
      link.dataset.id = b.id;
      linkG.appendChild(link);

      var g = el('g', { class: 'ob-node' });
      g.dataset.id = b.id;
      if (b.slice) g.dataset.slice = b.slice;   // клик подхватит DASH_JS
      g.style.setProperty('--c', b.c);

      var ping = el('circle', { class: 'ob-ping', cx: p.x, cy: p.y, r: 13,
        fill: 'none', stroke: b.c, 'stroke-width': 1 });
      ping.style.transformOrigin = p.x + 'px ' + p.y + 'px';
      g.appendChild(ping);
      g.appendChild(el('circle', { class: 'ob-glow', cx: p.x, cy: p.y, r: 12,
        fill: b.c, filter: 'url(#ob-spark)' }));
      g.appendChild(el('circle', { class: 'ob-ring', cx: p.x, cy: p.y, r: 13,
        stroke: b.c }));
      var ic = ICON[b.id] || ICON.surge;
      g.appendChild(el('path', { class: 'ob-ic', d: ic.d,
        transform: 'translate(' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ')',
        fill: ic.s ? 'none' : b.c, stroke: b.c,
        'stroke-width': ic.s ? 1.1 : 0,
        'stroke-linecap': 'round', 'stroke-linejoin': 'round' }));
      nodeG.appendChild(g);

      var vx = p.x - CX, vy = p.y - CY, len = Math.hypot(vx, vy) || 1;
      var lab = document.createElement('div');
      lab.className = 'ob-lab';
      lab.dataset.id = b.id;
      if (b.slice) lab.dataset.slice = b.slice;
      lab.style.setProperty('--c', b.c);
      lab.innerHTML = '<div class="ob-lab-n">' + b.name + '</div>' +
                      '<div class="ob-lab-v">' + b.val + '</div>';
      /* Отступ по нормали на постоянное расстояние, а не умножением
         радиуса: орбита сплюснута вдвое, и при пропорциональном отступе
         верхний с нижним узлы прилипали бы к линии. */
      lab.style.left = ((p.x + vx / len * 54) / 1000 * 100) + '%';
      lab.style.top  = ((p.y + vy / len * 54) / 563 * 100) + '%';
      orb.appendChild(lab);

      var card = document.createElement('div');
      card.className = 'ob-card';
      card.dataset.id = b.id;
      card.style.setProperty('--c', b.c);
      var html = '<div class="ob-card-h"><span class="ob-card-n">' + b.name +
                 '</span><span class="ob-card-v">' + b.val + '</span></div>' +
                 '<div class="ob-card-note">' + b.note + '</div>';
      if (b.list) {
        /* Тикеров два десятка: строка с баром на каждый превратила бы
           карточку в простыню, поэтому лента чипов. */
        html += '<div class="ob-chips">';
        b.list.forEach(function (c) {
          html += '<span class="ob-chip t' + c[1] + '"' +
                  (c[2] ? ' data-coin="' + c[2] + '"' : '') + '>' + c[0] + '</span>';
        });
        html += '</div>';
      } else {
        var rowsHTML = function (rows) {
          var h = '';
          (rows || []).forEach(function (r) {
            /* Четвёртый элемент строки, если есть, — подпись под ключом.
               Тот же приём, что <s> в отчёте. */
            h += '<div class="ob-card-r"><span class="ob-card-k">' + r[0] +
                 (r[3] ? '<s>' + r[3] + '</s>' : '') +
                 '</span><span class="ob-card-bar"><i style="width:' + r[2] +
                 '%"></i></span><span class="ob-card-x">' + r[1] + '</span></div>';
          });
          return h;
        };
        if (b.groups) {
          // сгруппированная карточка: подкейс, под ним его сильнейшие монеты
          b.groups.forEach(function (grp) {
            html += '<div class="ob-card-g">' + grp.g + '</div>' +
                    rowsHTML(grp.rows);
          });
        } else {
          html += rowsHTML(b.rows) + sparkSVG(b.spark, b.c);
        }
      }
      card.innerHTML = html;
      wrap.appendChild(card);

      NODE_LEN.push({ id: b.id, L: lengthAt(p) });
    });
  }

  /* ── Облёт ────────────────────────────────────────────────
     Комету ведёт JS, а не CSS: по её длине вдоль пути определяется,
     над какой категорией она сейчас, и по этому же значению всплывает
     карточка. У CSS-анимации позицию не спросить. */
  /* Круг за 78 секунд вместо 26: окно показа карточки задано долей
     оборота, поэтому замедление кометы втрое продлевает и чтение. */
  var LAP = 78000, HOLD = 0.055;
  var paused = false, pinned = null, lastHit = null;

  function setActive(id) {
    orb.classList.toggle('picked', !!id);
    orb.classList.toggle('showing', !!id);
    orb.querySelectorAll('.ob-node,.ob-lab,.ob-card,.ob-link,.ob-seg')
       .forEach(function (n) { n.classList.toggle('on', n.dataset.id === id); });
  }

  function frame(now) {
    if (!paused) {
      var prog = (now % LAP) / LAP;
      cometEl.setAttribute('stroke-dashoffset', (-prog * 1000).toFixed(2));
      var hp = cometEl.getPointAtLength(prog * TOTAL_LEN + 22);
      cometHead.setAttribute('cx', hp.x.toFixed(1));
      cometHead.setAttribute('cy', hp.y.toFixed(1));
      cometHalo.setAttribute('cx', hp.x.toFixed(1));
      cometHalo.setAttribute('cy', hp.y.toFixed(1));
      if (!pinned) {
        var L = prog * TOTAL_LEN, hit = null;
        NODE_LEN.forEach(function (n) {
          /* Расстояние по кольцу, а не по прямой: узел у нулевой отметки
             иначе не срабатывал бы при подходе кометы с другой стороны. */
          var d = Math.abs(n.L - L);
          d = Math.min(d, TOTAL_LEN - d);
          if (d < TOTAL_LEN * HOLD) hit = n.id;
        });
        if (hit !== lastHit) { setActive(hit); lastHit = hit; }
      }
    }
    requestAnimationFrame(frame);
  }

  /* Наведение перехватывает управление: иначе карточка уезжает
     из-под курсора ровно тогда, когда начинаешь её читать. */
  orb.addEventListener('pointerover', function (e) {
    var t = e.target.closest ? e.target.closest('.ob-node,.ob-lab') : null;
    if (!t) return;
    pinned = t.dataset.id; paused = true;
    setActive(pinned); lastHit = pinned;
  });
  orb.addEventListener('pointerout', function (e) {
    var from = e.target.closest ? e.target.closest('.ob-node,.ob-lab') : null;
    var to = e.relatedTarget && e.relatedTarget.closest
             ? e.relatedTarget.closest('.ob-node,.ob-lab') : null;
    if (from && !to) { pinned = null; paused = false; }
  });

  /* Клик по пустому месту сворачивает развёрнутые карточки */
  orb.addEventListener('click', function () {
    orb.querySelectorAll('.ob-scard.full').forEach(function (c) {
      c.classList.remove('full', 'on');
      c.classList.add('brief');
      c.style.pointerEvents = 'none';
    });
    orb.classList.remove('starred');
    orb.querySelectorAll('.ob-star.hot').forEach(function (n) {
      n.classList.remove('hot');
    });
    paused = false;
  });


  /* ── Сводка при входе ─────────────────────────────────────
     Три группы — это те же три состояния дерева фаз, а не отдельный
     список. «В работе» отделяется не фазой, а тем, что монета давно
     в журнале и подтверждалась не раз: именно так выглядит позиция,
     в которой уже сидишь. */




  /* Единственная точка связи с модулем сводки: наружу отдаём данные и
     две функции чтения фазы. Сводка не лезет во внутренности орбиты и
     не дублирует пороги — иначе они разъедутся при первой же правке. */
  window.ORB = { stars: STARS, market: DATA.market || {},
                 phase: phase, toStop: toStop };

  /* На тач-устройствах орбиту не просто прячем стилями, а убираем
     узел из документа: скрытый SVG всё равно занимал бы память, а
     getTotalLength и getPointAtLength на display:none элементе в
     части браузеров бросают исключение. Условие то же, что в CSS.

     Тип указателя здесь стоит как признак УСТРОЙСТВА, а не способа
     ввода. Попытка оставить орбиту планшетам провалилась на
     производительности: сотни SVG-узлов плюс покадровая анимация
     кладут весь отчёт, а не только этот экран. Экран лидеров при
     этом остаётся — там статичная раскладка. */
  if (window.matchMedia('(pointer: coarse)').matches ||
      window.matchMedia('(max-width: 1100px)').matches) {
    orb.remove();
    var blob = document.getElementById('ob-data');
    if (blob) blob.remove();
    return;
  }

    buildArcs();
    buildBack();
    buildCloud();
    buildDust();
    buildStars();
    build();
    buildComets();
    buildRiskComets();
    requestAnimationFrame(frame);
})();
</script>
"""
