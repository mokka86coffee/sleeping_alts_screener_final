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


def _at_target(sym_usdt: str) -> bool:
    """Монета «у цели» по репутации (07.09, владелец: «мы же определили, что ACU и CL у цели —
    значит можем понять, что пузыри не сработают»). У цели покупка рыночными приходит В ПЛИТУ,
    её принимают: CL 15:00 — пузырь на максимуме дня, через два часа −0.7%; ACU 04:30 — через
    два часа −0.9%. Читаем готовый шаблон, ничего нового не считаем."""
    try:
        rep_ = json.loads((BASE_DIR / "output" / "reputation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    r = (rep_.get(sym_usdt) or rep_.get(sym_usdt.replace("USDT", "")) or {})
    return "у цели" in str(r.get("plot") or "").lower()


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
    # ПУСТЫЕ БАРЫ ВОН (07.09): Coinglass иногда отдаёт интерес без сделок — в архиве fut: null и
    # пометка missing: ["fut_bar"] (09:00 сегодня у всех монет разом). Такой бар в сумме дельты даёт
    # ноль и занижает день, а в доминирующем типе голосует своим oi_type — считаем только полные.
    skipped = [r for r in rows if not (r.get("fut") or {}).get("tk")]
    full = [r for r in rows if (r.get("fut") or {}).get("tk")]
    if len(full) < 4:
        return None
    d = sum(((r.get("fut") or {}).get("d") or 0) for r in full)
    b = sum(((r.get("fut") or {}).get("b") or 0) for r in full)
    sl = sum(((r.get("fut") or {}).get("s") or 0) for r in full)
    oi0 = next((r.get("oi") for r in rows if r.get("oi")), None)
    oi1 = next((r.get("oi") for r in reversed(rows) if r.get("oi")), None)
    types: dict = {}
    for r in full:
        t = r.get("oi_type")
        if t and t != "flat":
            types[t] = types.get(t, 0) + 1
    dom = max(types, key=types.get) if types else None
    oi_chg = (oi1 / oi0 - 1) if oi0 and oi1 else None
    # НАБИРАЮТ / ВЫХОДЯТ (07.09, владелец: «что значит выходят, но при этом в первых?»):
    # набирают — дельта в плюс ИЛИ интерес за день +10% и больше (принимающий берёт лимитками,
    # дельта при этом отрицательная — так было у DOOD: −0.13M дельты при +54% интереса);
    # выходят — интерес ушёл на 5% и больше вместе с падением цены (FLOCK −13% при −8%,
    # RAYSOL −16% при −7%). Такие в очередь на вход не идут.
    px0 = next((r.get("px") for r in rows if r.get("px")), None)
    px1 = next((r.get("px") for r in reversed(rows) if r.get("px")), None)
    px_chg = (px1 / px0 - 1) if px0 and px1 else None
    buying = (d > 0 and (oi_chg is None or oi_chg >= -0.02)) or (oi_chg is not None and oi_chg >= 0.10 and (px_chg is None or px_chg >= -0.02))
    leaving = (oi_chg is not None and oi_chg <= -0.05 and (px_chg is not None and px_chg < 0))
    # КОРРЕКЦИЯ ИЛИ КОНЕЦ (07.09, владелец: «убрав их, можно пропустить добор»): «выходят» само по
    # себе не решает. Конец — был БАР СОВПАДЕНИЯ: дельта в минус и интерес упал в тот же час, и цена
    # ниже последнего удержанного минимума (ENA 07:30: −7.5M дельты и −18M интереса разом).
    # Коррекция — интерес уходит, но минимум держится и совпадения не было (BLESS: −8% интереса при
    # дельте −0.24M и двух барах покупок). Коррекция остаётся в очереди с пометкой, конец — в «у цели».
    hit = False
    prev_oi = None
    for r in rows:
        dd = (r.get("fut") or {}).get("d")
        oo = r.get("oi")
        if dd is not None and oo and prev_oi and dd < 0 and (oo / prev_oi - 1) <= -0.02:
            hit = True
        if oo:
            prev_oi = oo
    lows = [r.get("px") for r in rows if r.get("px")]
    held = (min(lows) if lows else None)
    # ОТКАТ ОТ МАКСИМУМА И НАПРАВЛЕНИЕ ПОСЛЕДНИХ ЧАСОВ (07.09, владелец: «DOOD весь день провисел
    # в первых, хотя падал почти с утра»). Дневная мерка «выходят» его не видела: интерес за СУТКИ
    # оставался в плюсе (вырос ночью), а падение шло ОТ ВЕРШИНЫ дня. Считаем два числа отдельно:
    #   drawdown_pct — сколько цена отдала от максимума дня (DOOD к вечеру −11% от вершины);
    #   oi_trend_pct — куда идёт интерес за последние 6 баров (три часа), в процентах.
    # ЧЕМ ОПЛАЧЕН ХОД — ПЛЕЧОМ ИЛИ ДЕНЬГАМИ (07.09, по числам кванта за выходные): 03.09 биткоин
    # +5.1% за сессию, открытый интерес +9.2%, а реализованная капитализация +0.04% — ход сделали
    # деривативы, и через сутки плечо сняли (самое резкое снятие с 2023). У монеты то же самое
    # считается своими числами: прирост интереса в долларах против дельты рыночных заявок за день.
    #   дельта мала против прироста интереса → ход на ПЛЕЧЕ: позиции есть, денег нет;
    #   дельта соизмерима с приростом → ход на ДЕНЬГАХ: за ход заплатили.
    # Мерка — та же, что у кванта: НАСКОЛЬКО БЫСТРЕЕ растут позиции, чем цена. Сравнивать дельту с
    # приростом интереса нельзя: дельта — чистый перекос заявок, интерес — весь номинал позиций,
    # у альтов первое всегда в разы меньше второго и всё выходило бы «на плече».
    #   плечо растёт вровень с ценой (до полутора раз) → ход НА ДЕНЬГАХ (ACU 07.09: +7.2% при +7.7%);
    #   вчетверо и быстрее → ход НА ПЛЕЧЕ (DOOD ×5.8, CL ×20.7) — за него не заплатили, снимется так же;
    #   между — поровну. Дельта идёт рядом как подтверждение, но решает соотношение.
    oi_add_usd = (oi1 - oi0) if (oi0 and oi1) else None
    paid = None
    if oi_chg is not None and px_chg not in (None, 0) and abs(px_chg * 100) >= 0.5:
        paid = (oi_chg * 100) / (px_chg * 100)
    move_paid = None
    if paid is not None and paid > 0 and px_chg and px_chg > 0:
        # мерка применима ТОЛЬКО к росту: при падении то же соотношение значит выход позиций,
        # а не «оплату» хода (FLOCK 07.09: −15% цены при −21% интереса — это не «на деньгах»)
        move_paid = "на деньгах" if paid <= 1.5 else "на плече" if paid >= 4.0 else "поровну"
    day_hi_px = max(lows) if lows else None
    drawdown = ((px1 / day_hi_px - 1) * 100) if (day_hi_px and px1) else None
    _oi_tail = [r.get("oi") for r in rows[-7:] if r.get("oi")]
    oi_trend = ((_oi_tail[-1] / _oi_tail[0] - 1) * 100) if len(_oi_tail) >= 3 and _oi_tail[0] else None
    # БЕЛЫЙ ПУЗЫРЬ ОТМЕНЯЕТ «КОНЕЦ» (07.09, владелец: «у FLOCK продолжение, там белые пузыри»):
    # пузырь — факт (кто-то отдал деньги рыночной заявкой), уход интереса — надежда выходящих;
    # факт весит больше. Бар с покупкой выше 2σ по обороту дня → это коррекция, не конец.
    # ПУЗЫРЬ — ПО ДЕЛЬТЕ, НЕ ПО ОБОРОТУ (07.09, случай FLOCK): по обороту «покупкой» считался бар
    # 00:30 с оборотом 6.5M и дельтой +23K — это приняли чужую продажу, а не купили. Пузырь = кто-то
    # реально отдал деньги рыночной заявкой: дельта выше 2σ по дельте дня.
    dl = [((r.get("fut") or {}).get("d") or 0) for r in full]
    mu_d = sum(dl) / len(dl) if dl else 0.0
    sd_d = (sum((x - mu_d) ** 2 for x in dl) / len(dl)) ** 0.5 if len(dl) > 3 else 0.0
    bub_buy_bars = [r["candle"][11:16] for r, x in zip(full, dl) if sd_d and x > mu_d + 2 * sd_d]
    bub_sell_bars = [r["candle"][11:16] for r, x in zip(full, dl) if sd_d and x < mu_d - 2 * sd_d]
    bubble_buy = bool(bub_buy_bars)
    # КАРТОЧКА ПУЗЫРЯ (07.09, владелец: «как различать, какие пузыри сработают, а какие нет; CL —
    # главный контрпример»). На семи пузырях покупки 07.09 разделило ОДНО число — место в дневном
    # диапазоне: сработавшие стояли ниже 40% (NAORIS 11% → +4.5%, FLOCK 9% → 0, SOPH 34% → +6.6%,
    # STRK 39% → +0.8%), провалившиеся — выше 92% (DOOD 92% → −3.0%, FLOCK 92% → −2.9%, CL 100% →
    # −0.7%). Расстояние до полосы сверху и тип бара НЕ разделили. Семь случаев — гипотеза, не
    # правило: пишем числа, вывод сделает журнал. Ничего не решаем этими полями.
    day_lo = min(lows) if lows else None
    day_hi = max(lows) if lows else None
    # ОБОРОТ БАРА К НОРМЕ ДНЯ — для различения «выбор» и «моментум» (07.09, по июньскому дну
    # биткоина): 11.06 агрессия покупателей вошла в верхний 1% за 2354 дня, а оборот был ОБЫЧНЫЙ —
    # 0.975 от тридцатидневной нормы. Такой пузырь означает, что кто-то сознательно выбрал сторону
    # на обычной глубине. Пузырь на всплеске оборота — это моментум, он слабее: толпа бежит следом.
    vols_d = [(((r.get("fut") or {}).get("b") or 0) + ((r.get("fut") or {}).get("s") or 0)) for r in full]
    vol_med = statistics.median([v for v in vols_d if v]) if any(vols_d) else 0.0
    bubbles = []
    for i, (r, x) in enumerate(zip(full, dl)):
        if not sd_d or abs(x - mu_d) < 2 * sd_d:
            continue
        p_ = r.get("px")
        if not p_:
            continue
        z = r.get("zones") or {}
        up = sorted([q for q, _w in (z.get("up") or []) if q and q > p_])
        dn = sorted([q for q, _w in (z.get("down") or []) if q and q < p_], reverse=True)
        oi_prev = full[i - 1].get("oi") if i else r.get("oi")
        after = {}
        for k, step in (("m30", 1), ("h2", 4), ("h6", 12)):
            nx = full[i + step].get("px") if i + step < len(full) else None
            if nx:
                after[k] = round((nx / p_ - 1) * 100, 2)
        _pos = round((p_ - day_lo) / (day_hi - day_lo) * 100, 0) if (day_hi and day_lo and day_hi > day_lo) else None
        # РОЛЬ ПУЗЫРЯ (07.09, владелец: «у CL и ACU есть и второй момент — красный пузырь у дна,
        # который тоже не сработал»). Правило не про цвет: работает тот, кто бьёт по рынку в ту же
        # сторону, что и край дня, у которого он стоит.
        #   покупка внизу  → продолжение вверх  (NAORIS 11% → +4.5%, BLESS 8% → +3.1%, SOPH 34% → +6.6%)
        #   продажа наверху → продолжение вниз   (COTI 92% → −10.6%, 66% → −7.5%)
        #   покупка наверху → ПОГЛОЩЕНА, отдали  (CL 100% → −0.7%, PROM 100% → −3.4%, «4» 100% → −15.5%)
        #   продажа внизу   → ПОГЛОЩЕНА, приняли (CL 20% → +1.9%, ACU 36% → +4.4%, BLESS 19% → +3.7%,
        #                                          ENA 15:30 на минимуме дня → +1.9%)
        # Поглощённая продажа внизу — признак лимитного покупателя: снизу стоял и принял.
        _role = None
        if _pos is not None:
            _up, _dn = _pos >= 70, _pos <= 40
            if x > 0:
                _role = "продолжение" if _dn else ("поглощён" if _up else "середина")
            else:
                _role = "продолжение" if _up else ("поглощён" if _dn else "середина")
        _vol = vols_d[i]
        _vr = (_vol / vol_med) if (vol_med and _vol) else None
        # «выбор» — оборот обычный (до полутора норм); «моментум» — всплеск оборота
        _how = None if _vr is None else ("выбор" if _vr <= 1.5 else "моментум")
        bubbles.append({
            "at": r["candle"][11:16], "side": "buy" if x > 0 else "sell", "usd": round(x, 0),
            "role": _role, "pos_pct": _pos, "vol_ratio": round(_vr, 2) if _vr else None, "how": _how,
            "to_up_pct": round((up[0] / p_ - 1) * 100, 2) if up else None,
            "to_dn_pct": round((dn[0] / p_ - 1) * 100, 2) if dn else None,
            "oi_bar_pct": round(((r.get("oi") or 0) / oi_prev - 1) * 100, 2) if oi_prev else None,
            "oi_type": r.get("oi_type"), "after": after,
        })
    # ПУЗЫРЬ-СИГНАЛ — НЕ ЛЮБОЙ (07.09, случаи CL, ACU, DOOD, PROM): покупка рыночными считается
    # сбором, только если стоит в НИЖНЕЙ трети дневного диапазона и монета не «у цели». У цели и
    # на максимуме дня рыночная покупка — это тот, кому отдают: CL 100% дня → −0.7% за 2 ч,
    # PROM 100% → −3.4%, DOOD 92% → −3.0%, FLOCK 92% → −2.9%; внизу наоборот: NAORIS 11% → +4.5%,
    # SOPH 34% → +6.6%, BLESS 8% → +3.1%. Остальные пузыри пишутся в журнал, но решений не меняют.
    at_target = _at_target(sym_usdt)
    low_buy = [b for b in bubbles if b["side"] == "buy" and b.get("role") == "продолжение"]
    # пузырь-ВЫБОР (покупка внизу дня на обычном обороте) — самый сильный вид: так выглядело дно
    # биткоина 11.06. Пузырь-моментум на всплеске оборота остаётся сигналом, но слабее.
    low_buy_choice = [b for b in low_buy if b.get("how") == "выбор"]
    high_sell = [b for b in bubbles if b["side"] == "sell" and b.get("role") == "продолжение"]
    absorbed = [b for b in bubbles if b.get("role") == "поглощён"]
    # сигнал вверх — покупка внизу и не «у цели» (у цели рыночную покупку принимают в плиту);
    # сигнал вниз — продажа наверху; поглощённые балл не двигают, но пишутся в журнал
    bubble_signal = bool(low_buy) and not at_target
    bubble_choice = bool(low_buy_choice) and not at_target
    bubble_down = bool(high_sell)
    kind = None
    if leaving:
        kind = "коррекция" if (bubble_signal or not hit) else "конец"
    return {"bars": len(rows), "delta": round(d, 0), "taker": round(b / sl, 3) if sl else None,
            "oi_chg_pct": round(oi_chg * 100, 1) if oi_chg is not None else None,
            "px_chg_pct": round(px_chg * 100, 1) if px_chg is not None else None, "dominant": dom,
            "px": px1, "leaving_kind": kind, "day_low": held, "hit_bar": hit, "bubble_buy": bubble_buy,
            "move_paid": move_paid, "paid_ratio": round(paid, 3) if paid is not None else None,
            "oi_add_usd": round(oi_add_usd, 0) if oi_add_usd is not None else None,
            "drawdown_pct": round(drawdown, 2) if drawdown is not None else None,
            "oi_trend_pct": round(oi_trend, 2) if oi_trend is not None else None,
            "bub_buy": bub_buy_bars, "bub_sell": bub_sell_bars, "skipped": len(skipped),
            "bubble_signal": bubble_signal, "bubble_choice": bubble_choice, "bubble_down": bubble_down,
            "absorbed": len(absorbed), "at_target": at_target,
            "bubbles": bubbles,
            # ХОД БЕЗ ПУЗЫРЯ (07.09, случай ACU): у монеты может идти чистый ход вовсе без всплесков —
            # там различает не пузырь, а во сколько раз интерес растёт быстрее цены за день.
            # ACU: плечо +7.2% при цене +7.7% — один к одному, толпы нет; DOOD: +72% при +17% — набивка.
            "oi_to_px": (round((oi_chg * 100) / (px_chg * 100), 2)
                         if (oi_chg is not None and px_chg not in (None, 0) and abs(px_chg * 100) >= 0.5) else None),
            "today": ("выходят · " + kind) if leaving else ("набирают сегодня" if buying else "стоит")}


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
    # ТРИ ДВИГАТ�еЛЯ, НЕ ОДИН (07.09, случай SOPH: 4/5, не хватило только шортов — а их на ней
    # никогда и не было; ход на спросе). Шорты — признак СКВИЗА; если их нет, но интерес растёт
    # быстрее цены и сбор удержан, это СПРОС — засчитываем пятым признаком с пометкой двигателя.
    engine = "сквиз" if sh >= max(SHORT_MIN_USD, SHORT_MIN_OI * oi_now) else None
    if engine is None and grow >= 1.15 and hv and nums.get("from_harvest_high", -100) >= -10:
        engine = "спрос"
        score += 1
        why.append(f"двигатель: спрос (шортов нет, плечо ×{grow:.2f} при цене у максимума сбора)")
    nums["engine"] = engine or "нет"
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
        out[g + "_buying"] = [s2 for s2 in out[g] if (out["coins"][s2].get("today") or {}).get("today") == "набирают сегодня"]
        out[g + "_selling"] = [s2 for s2 in out[g] if (out["coins"][s2].get("today") or {}).get("today") == "выходят сегодня"]
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
        _tk_q = (v.get("today") or {}).get("leaving_kind")
        b_score = 1.0 if td == "набирают сегодня" else 0.5 if td == "стоит" else 0.25 if _tk_q == "коррекция" else 0.0
        # ЧЕТВЁРТОЕ ЧИСЛО — ТЕМП (07.09, владелец: «важно понять, какая быстрее пойдёт»): очередь
        # мерила накопленное — срок и плечо, — и первыми вставали стоящие (STRK: плечо ×1.1, «стоит»)
        # и те, из кого выходят (FLOCK, RAYSOL — «коррекция»), а DOOD с +16% за сутки был четвёртым.
        # Ход цены за сегодня: кто уже идёт, тот и пойдёт раньше. Пятнадцать процентов — полный балл.
        _tv = v.get("today") or {}
        _px_chg = _tv.get("px_chg_pct")
        m_score = min(1.0, max(0.0, (float(_px_chg) / 15.0))) if _px_chg is not None else 0.0
        # ОТКАТ ОТ ВЕРШИНЫ ДНЯ — В БАЛЛ (07.09): темп по цене за день не отличает того, кто идёт,
        # от того, кто уже сходил и отдаёт. DOOD 07.09: +7% за сутки и −11% от вершины — по дневному
        # темпу он оставался первым весь день. Полный балл темпа только у того, кто держится у своего
        # максимума; отдал десятую часть хода — темп обнуляется.
        _dd = _tv.get("drawdown_pct")
        if _dd is not None:
            m_score *= max(0.0, 1.0 - abs(min(0.0, _dd)) / 10.0)
        score = round(0.25 * t_score + 0.25 * g_score + 0.20 * b_score + 0.30 * m_score, 3)
        # НАПРАВЛЕНИЕ ИНТЕРЕСА ЗА ПОСЛЕДНИЕ ТРИ ЧАСА: растёт — усиливает, падает — ослабляет.
        # Это ответ на «кто пойдёт СЕЙЧАС», а не «у кого вчера был сбор».
        _tr = _tv.get("oi_trend_pct")
        if _tr is not None:
            score *= 1.10 if _tr >= 2 else (0.75 if _tr <= -3 else 1.0)
        # ХОД НА ПЛЕЧЕ ОСЛАБЛЯЕТ, ХОД НА ДЕНЬГАХ УСИЛИВАЕТ (07.09): это правило по САМОЙ монете,
        # а не фон — считается её приростом интереса и её же дельтой. Ход, за который не заплатили
        # рыночными заявками, снимается так же быстро, как набран.
        _mp = _tv.get("move_paid")
        if _mp == "на плече":
            score *= 0.80
        elif _mp == "на деньгах":
            score *= 1.10
        # ПУЗЫРЬ — МНОЖИТЕЛЕМ, НЕ СЛАГАЕМЫМ (07.09): как слагаемое он вынес наверх стоящий STRK
        # (единственный пузырь дня — 128K в 04:00, при этом цена за день −0.3% и дельта в минус).
        # Факт покупки усиливает того, кто и так идёт, и не поднимает того, кто стоит.
        # МНОЖИТЕЛЬ ПО РОЛИ ПУЗЫРЯ (07.09): вверх усиливает, вниз ослабляет, поглощённый —
        # нейтрален. Раньше любая продажа наказывала монету, а у CL и ACU продажи внизу были
        # ПРИНЯТЫ и цена после них росла — за это наказывать нельзя.
        _bb, _bs = _tv.get("bub_buy") or [], _tv.get("bub_sell") or []
        score *= (1.25 if _tv.get("bubble_choice") else 1.15) if _tv.get("bubble_signal") \
            else (0.85 if _tv.get("bubble_down") else 1.0)
        # КОРРЕКЦИЯ — ТОЖЕ МНОЖИТЕЛЕМ: интерес сегодня уходит вместе с ценой — монета временно не про
        # «кто раньше»; из очереди не выбрасываем (белый пузырь вернёт), но вперёд не пускаем.
        if _tk_q == "коррекция":
            score *= 0.6
        if (v.get("today") or {}).get("leaving_kind") == "конец":
            continue                # конец: интерес ушёл вместе с ценой на одном баре — вон из очереди
        _mode = n.get("mode")
        if _mode == "парабола":
            score *= 0.45          # парабола: первая тряска — выход, а не покупка (07.09)
        elif _mode == "лестница":
            score *= 1.15
        score = round(score, 3)
        v["queue"] = {"days_since_harvest": days, "score": score, "today": td, "mode": _mode,
                      "px_chg_pct": _px_chg,
                      "bubble": (("покупка внизу, выбор " if _tv.get("bubble_choice") else "покупка внизу ") + _bb[-1])
                                if _tv.get("bubble_signal")
                                else ("продажа вверху " + _bs[-1]) if _tv.get("bubble_down")
                                else (f"поглощён ×{_tv.get('absorbed')}") if _tv.get("absorbed")
                                else "тихо",
                      "at_target": _tv.get("at_target"), "move_paid": _tv.get("move_paid")}
        queue.append((score, s2))
    queue.sort(reverse=True)
    out["queue"] = [s2 for _, s2 in queue]
    return out


# ФОН В РЕШЕНИЯХ НЕ УЧАСТВУЕТ (07.09, владелец: «мы пока не умеем читать фон — он не должен
# влиять на то, что умеем»). Балл очереди считается ТОЛЬКО по монете: срок после сбора, рост плеча,
# что по её барам, темп с поправкой на откат от вершины, направление её интереса, роль её пузыря,
# режим. Ни risk on, ни ход биткоина, ни сессия, ни лидеры биржи, ни тейкер по доске в балл не
# входят и входить не должны: пока не посчитано, при каком фоне прогнозы сбывались, любой
# множитель оттуда — догадка, которая портит работающую часть. Фон пишется рядом (market_bg.py)
# и разрезает ЖУРНАЛ задним числом, но не решения.


def log_queue(res: dict) -> int:
    """ИСТОРИЯ ОЧЕРЕДИ (07.09, владелец: «историю стоит писать обязательно, причём каждый прогон»):
    output/queue_log.jsonl — по строке на монету очереди за прогон. near_move.json переписывается
    каждый прогон, и вчерашние места нигде не оставались: за 07.09 на втором месте побывали NAORIS,
    STRK, SOPH и XAN, а проверить, держится место или скачет, было не по чему.

    В строке: время и свеча, место и балл, три числа балла (срок, плечо, бары), пузырь дня,
    режим и двигатель, цена и интерес на этот момент — чтобы вечером считать, какое число
    различало заранее, а какое шум. Куда это выводить на экране — решаем отдельно."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    candle = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
    p = BASE_DIR / "output" / "queue_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, sym in enumerate(res.get("queue") or [], 1):
        v = (res.get("coins") or {}).get(sym) or {}
        q = v.get("queue") or {}
        n = v.get("nums") or {}
        t = v.get("today") or {}
        rows.append({
            "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "candle": candle.strftime("%Y-%m-%dT%H:%M:00Z"),
            "sym": sym, "place": i, "score": q.get("score"),
            "days_since_harvest": q.get("days_since_harvest"), "oi_grow": n.get("oi_grow"),
            "today": q.get("today"), "bubble": q.get("bubble"), "move_pct": q.get("px_chg_pct"),
            # карточки пузырей и плечо к цене (07.09) — сырьём в журнал, выводы делает считалка
            "move_paid": (v.get("today") or {}).get("move_paid"),
            "paid_ratio": (v.get("today") or {}).get("paid_ratio"),
            "drawdown_pct": (v.get("today") or {}).get("drawdown_pct"),
            "oi_trend_pct": (v.get("today") or {}).get("oi_trend_pct"),
            "bubbles": (v.get("today") or {}).get("bubbles"),
            "oi_to_px": (v.get("today") or {}).get("oi_to_px"),
            "mode": q.get("mode"), "engine": n.get("engine"), "group": v.get("group"),
            "px": t.get("px") or n.get("px_now"), "oi_chg_pct": t.get("oi_chg_pct"),
            "px_chg_pct": t.get("px_chg_pct"), "delta": t.get("delta"),
            "skipped_bars": t.get("skipped"),
        })
    if not rows:
        return 0
    with p.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(rows)


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
        _nq = log_queue(res)
        print(f"история очереди: +{_nq} строк → output/queue_log.jsonl")
        p = BASE_DIR / "output" / "near_move.json"
        p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        print(f"near_move: записано {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
