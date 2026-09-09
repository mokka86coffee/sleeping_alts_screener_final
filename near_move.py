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


def _plot(sym_usdt: str) -> str:
    """Словесный прогноз монеты из репутации — тот же, что видно на карточке и в сводке."""
    try:
        rep_ = json.loads((BASE_DIR / "output" / "reputation.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    r = (rep_.get(sym_usdt) or rep_.get(sym_usdt.replace("USDT", "")) or {})
    return str(r.get("plot") or "")


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
    # ── СОСТОЯНИЕ ПО БАРАМ, А НЕ ПО ШАБЛОНУ (08.09, владелец: «у нас внутридневные мерки, которые
    # меняются каждые полчаса, это всё нужно использовать»). До сих пор «жив тренд или кончился»
    # решал словесный шаблон репутации на ДНЕВКАХ: у DOOD он не менялся 70 записей подряд, и на
    # карточке висело «тащит», когда по барам движение кончилось ещё накануне в 22:30 (дельта
    # −713K при падении интереса на 1M+). Теперь состояние считается здесь, по получасовым барам:
    #   кончилось  — был бар совпадения (дельта в минус и интерес −2% в один бар) ИЛИ три бара
    #                подряд «лонги закрывают» при падающем интересе ИЛИ откат от вершины больше
    #                половины хода дня при интересе вниз;
    #   идёт       — интерес и цена за последние часы в одну сторону вверх;
    #   стоит      — всё остальное.
    # Момент конца запоминается (ended_at) — это точка выхода, её же ставит карточка меткой.
    # ── СИЛА ВЫДЫХАЕТСЯ (10.09) ──────────────────────────────────────────────────────────────
    # Владелец увидел на графике, что Klinger разворачивается ДО вершины. Посчитать сам Klinger
    # нельзя — в архиве нет максимума и минимума бара, только цена, и формула вырождается в ноль.
    # Взяли его смысл своими средствами: направление даёт ДЕЛЬТА, а не размах бара. Быстрая
    # средняя дельты против медленной; пересечение вниз = сила ушла раньше цены.
    # Проверено на 22 ходах ≥8% за три дня: разворот случился до вершины в 21 случае (95%),
    # медианная фора 3 бара (1.5 часа), медианное падение после вершины −7.2%.
    # Крупные: SOPH 08.09 — 6 баров форы, дальше −47.5%; USELESS — 7 баров; DOOD — 3; PROM — 7.
    # В БАЛЛ НЕ ИДЁТ: 22 случая за три дня — мало. Метка-наблюдение рядом с событием конца.
    # Смысл по владельцу: не «выходи», а «начни выходить» — снять часть, остаток оставить.
    def _force_turn(bars: list) -> tuple:
        d = [((x.get("fut") or {}).get("d") or 0) for x in bars]
        if len(d) < 20:          # с 10:00 UTC уже считается, раньше данных мало
            return None, None

        def _ema(xs, n):
            k = 2 / (n + 1)
            out, e = [], None
            for x in xs:
                e = x if e is None else x * k + e * (1 - k)
                out.append(e)
            return out

        kv = [a2 - b2 for a2, b2 in zip(_ema(d, 12), _ema(d, 26))]
        sg = _ema(kv, 9)
        turn = None
        for i in range(len(kv) - 1, 0, -1):
            if kv[i] < sg[i] and kv[i - 1] >= sg[i - 1]:
                turn = i
                break
        if turn is None:
            return None, None
        return bars[turn].get("candle"), (len(bars) - 1 - turn)

    force_at, force_ago = _force_turn(full)

    day_hi_run = None
    ended_at = None
    ended_oi = None
    prev_oi2 = None
    closing = 0
    # МЕДЛЕННЫЙ ВЫХОД (08.09, случай NAORIS): прежняя мерка ловила только резкий — падение интереса
    # на 2% в ОДНОМ баре вместе с отрицательной дельтой. У NAORIS такого бара не было ни разу:
    # интерес сползал по мелочи (−27, −26, −19 тыс), но за три часа набежало −6.5% при цене на 4–9%
    # ниже вершины дня и тейкере ниже единицы в восьми барах подряд. Монета кончилась в 10:30–11:00,
    # а в первых висела до 17:00. Теперь конец засчитывается и так: скользящее окно шести баров —
    # интерес вниз от 3%, цена ниже вершины дня, и большинство баров с тейкером ниже единицы.
    win: list = []
    for r in rows:
        f = r.get("fut") or {}
        dd_, oo = f.get("d"), r.get("oi")
        typ = r.get("oi_type") or ""
        if r.get("px"):
            day_hi_run = max(day_hi_run or 0, r["px"])
        if typ == "long_close" and dd_ is not None and dd_ < 0:
            closing += 1
        elif typ != "long_close":
            closing = 0
        hard = (dd_ is not None and oo and prev_oi2 and dd_ < 0 and (oo / prev_oi2 - 1) <= -0.02)
        # окно шести баров: интерес, цена, тейкер
        win.append((oo, r.get("px"), (f.get("tk") if isinstance(f, dict) else None)))
        if len(win) > 6:
            win.pop(0)
        slow = False
        if len(win) == 6 and win[0][0] and oo:
            _oi_dn = (oo / win[0][0] - 1) * 100 <= -3.0
            _below = bool(day_hi_run and r.get("px") and r["px"] < day_hi_run * 0.985)
            _weak = sum(1 for _o, _p, _t in win if _t is not None and _t < 1.0) >= 4
            slow = _oi_dn and _below and _weak
        if (hard or closing >= 3 or slow) and ended_at is None:
            ended_at = r.get("candle")
            ended_oi = prev_oi2
        # ВОССТАНОВЛЕНИЕ ОТМЕНЯЕТ КОНЕЦ (08.09, случай SOPH): событие сработало в 05:30, а монета
        # потом удвоилась — интерес после него вырос с 72M до 95M. Значит, это была тряска, а не
        # конец. Конец засчитывается ТОЛЬКО если интерес после события не вернулся к уровню,
        # который был до него. Вернулся — событие снимается, и монета снова в игре.
        if ended_at and oo and ended_oi and oo >= ended_oi:
            ended_at = None
            ended_oi = None
            closing = 0
        if oo:
            prev_oi2 = oo
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
        # ЧТО ДЕЛАЛ ИНТЕРЕС НА САМОМ БАРЕ ПУЗЫРЯ (08.09, разбор NAORIS и SOPH): пузырь — это факт,
        # что кто-то отдал деньги рыночной заявкой. Но результат зависит от того, ОТКРЫЛИСЬ ли на
        # этом позиции или об эти заявки ЗАКРЫЛИСЬ:
        #   NAORIS 12:30 — покупка 112 тыс, интерес на баре −2.9%, тип «лонги закрывают»: покупали
        #     не входящие, а выходящие шорты; после этого цена −1.1%;
        #   SOPH 04:30 — покупка 5.41M, интерес +12.5%, «лонги открывают»: настоящий набор, после
        #     +11.3% и держалось весь день;
        #   SOPH 15:00 — продажа 3.35M, интерес −10.9%: об эти продажи закрывали лонги, дальше −20.8%.
        # Отсюда РОЛЬ по интересу: «набрали» (интерес вырос) · «закрылись» (интерес упал) · «ровно».
        _oi_bar = None
        if i > 0:
            _prev_oi = next((full[k].get("oi") for k in range(i - 1, -1, -1) if full[k].get("oi")), None)
            _now_oi = r.get("oi")
            if _prev_oi and _now_oi:
                _oi_bar = round((_now_oi / _prev_oi - 1) * 100, 2)
        _fill = None if _oi_bar is None else ("набрали" if _oi_bar >= 1.5 else
                                              "закрылись" if _oi_bar <= -1.5 else "ровно")
        _vol = vols_d[i]
        _vr = (_vol / vol_med) if (vol_med and _vol) else None
        # «выбор» — оборот обычный (до полутора норм); «моментум» — всплеск оборота
        _how = None if _vr is None else ("выбор" if _vr <= 1.5 else "моментум")
        bubbles.append({
            "at": r["candle"][11:16], "side": "buy" if x > 0 else "sell", "usd": round(x, 0),
            "role": _role, "pos_pct": _pos, "vol_ratio": round(_vr, 2) if _vr else None, "how": _how,
            "oi_bar_chg": _oi_bar, "fill": _fill, "bar_type": r.get("oi_type"),
            # ЧТО ЭТО БЫЛО, ОДНОЙ ФРАЗОЙ (08.09, владелец: «покупки были, но об них закрывались, и
            # такие пузыри нужно отображать иначе — как вчера у CL, где пузырь продаж был на дне и
            # его вынесли»): сторона + место в дне + что стало с интересом.
            "say": (
                "набрали внизу" if (x > 0 and _pos <= 40 and _fill == "набрали") else
                "об покупки закрылись" if (x > 0 and _fill == "закрылись") else
                "покупку приняли наверху" if (x > 0 and _pos >= 70) else
                "вынесли продавца" if (x < 0 and _pos <= 40 and _fill == "закрылись") else
                "продажу приняли внизу" if (x < 0 and _pos <= 40 and _fill == "набрали") else
                "продали наверху" if (x < 0 and _pos >= 70) else
                ("покупка" if x > 0 else "продажа") + " в середине дня"
            ),
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
    # ПУЗЫРИ НЕ ОТСЕКАЕМ, А ПОМЕЧАЕМ СОМНИТЕЛЬНЫЕ (08.09, владелец: «правку не применял; утром был
    # хороший кейс на SOPH, где по всей длине шли зелёные пузыри на росте, и это не сломать; пузыри
    # всё так же должны рисоваться, но сомнительный делать наполовину оранжевым — понятно, что
    # покупки есть, но цель у них может быть другая»).
    # Уверенность пузыря:
    #   ясный      — интерес на баре вырос: на эти заявки ОТКРЫВАЛИ позиции (SOPH 04:30, +12.5%);
    #   сомнительный — интерес упал или тип «лонги закрывают»: об заявки ЗАКРЫВАЛИСЬ (NAORIS 12:30);
    #   обычный    — интерес не изменился заметно.
    # В балл идут только ясные, но рисуются все — сомнительные своим цветом.
    for _b in bubbles:
        _b["sure"] = ("сомнительный" if (_b.get("fill") == "закрылись" or _b.get("bar_type") == "long_close")
                      else "ясный" if _b.get("fill") == "набрали" else "обычный")
    low_buy_sure = [b for b in low_buy if b.get("sure") != "сомнительный"]
    low_buy_choice = [b for b in low_buy_choice if b.get("sure") == "ясный"]
    high_sell = [b for b in bubbles if b["side"] == "sell" and b.get("role") == "продолжение"]
    absorbed = [b for b in bubbles if b.get("role") == "поглощён"]
    # сигнал вверх — покупка внизу и не «у цели» (у цели рыночную покупку принимают в плиту);
    # сигнал вниз — продажа наверху; поглощённые балл не двигают, но пишутся в журнал
    bubble_signal = bool(low_buy_sure) and not at_target
    bubble_choice = bool(low_buy_choice) and not at_target

    # ── ФЛАГ «СНИМУТ» И ЕГО ПОДТВЕРЖДЕНИЕ (08.09, проверка на 319 случаях): сам флаг — топливо в
    # полтора раза и тейкер в ту же сторону — даёт 32% верных, то есть чаще ошибается, и перевес
    # топлива не помогает (×1.5–2 → 29%, ×2–4 → 46%, ×4+ → 22%). Но если в ту же сторону был ЯСНЫЙ
    # пузырь, тот, на котором открывали позиции, — 9 верных из 9. Топливо есть всегда с обеих
    # сторон, оно меряет ожидание; пузырь — факт, что кто-то уже отдал деньги и ведёт.
    liq_side = None
    liq_ratio = None
    liq_ok = False
    _lastz = (rows[-1].get("zones") or {}) if rows else {}
    if px1 and _lastz:
        _up = sorted([(q, w) for q, w in (_lastz.get("up") or []) if q and q > px1],
                     key=lambda t: -(t[1] or 0))[:3]
        _dn = sorted([(q, w) for q, w in (_lastz.get("down") or []) if q and q < px1],
                     key=lambda t: -(t[1] or 0))[:3]
        _fa = sum(w or 0 for _q, w in _up)
        _fb = sum(w or 0 for _q, w in _dn)
        _tk = ((rows[-1].get("fut") or {}).get("tk"))
        if _fa and _fb and _tk:
            if _fb >= 1.5 * _fa and _tk < 1:
                liq_side, liq_ratio = "вниз", round(_fb / _fa, 1)
            elif _fa >= 1.5 * _fb and _tk > 1:
                liq_side, liq_ratio = "вверх", round(_fa / _fb, 1)
        if liq_side:
            _lb = next((b for b in reversed(bubbles) if b.get("sure") == "ясный"), None)
            if _lb:
                liq_ok = (_lb["side"] == "buy") if liq_side == "вверх" else (_lb["side"] == "sell")

    # ── ПУЗЫРИ ПРОТИВ ПРОГНОЗА (08.09, владелец: «свяжем логику пузырей с нашими прогнозами»).
    # Прогноз — словесный шаблон репутации, он живёт на дневках и меняется редко. Пузыри — факт
    # сегодняшнего дня. Сверяем их между собой и пишем согласие, ничего не отменяя:
    #   подтверждают  — прогноз на рост, и последний заметный пузырь покупки был с набором;
    #   против        — прогноз на рост, а пузыри дня либо продажи наверху, либо покупки, об
    #                   которые закрывались (NAORIS 12:30: шаблон «тащит», а на баре −2.9% интереса);
    #   молчат        — заметных пузырей нет или они спорные и слабые.
    _plt = _plot(sym_usdt).lower()
    _up_words = ("тащит", "начал тащить", "кит", "поглощает", "спрос", "разгон", "набирает")
    _dn_words = ("отпустил", "осечка", "отбой", "конец", "выходят", "раздач")
    _fc_side = 1 if any(w in _plt for w in _up_words) else (-1 if any(w in _plt for w in _dn_words) else 0)
    _last_buy = next((b for b in reversed(bubbles) if b["side"] == "buy"), None)
    _last_sell = next((b for b in reversed(bubbles) if b["side"] == "sell"), None)
    bubble_vs_plot = "молчат"
    if _fc_side == 1:
        if _last_buy and _last_buy.get("sure") == "ясный":
            bubble_vs_plot = "подтверждают"
        elif (_last_buy and _last_buy.get("sure") == "сомнительный") or \
             (_last_sell and (_last_sell.get("pos_pct") or 0) >= 70):
            bubble_vs_plot = "против"
    elif _fc_side == -1:
        if _last_sell and _last_sell.get("sure") == "ясный":
            bubble_vs_plot = "подтверждают"
        elif _last_buy and _last_buy.get("sure") == "ясный":
            bubble_vs_plot = "против"
    bubble_down = bool(high_sell)
    # КОНЕЦ ПО БАРАМ СИЛЬНЕЕ СУТОЧНОЙ МЕРКИ (08.09): было событие и интерес после него не вернулся —
    # значит «выходят», как бы ни выглядели сутки целиком (DOOD 08.09: за сутки интерес был в плюсе,
    # а по барам восемь баров подряд лонги закрывают).
    if ended_at and (oi_trend is not None and oi_trend <= 0):
        leaving = True
    kind = None
    if leaving:
        kind = "коррекция" if (bubble_signal or not hit) else "конец"
    return {"bars": len(rows), "delta": round(d, 0), "taker": round(b / sl, 3) if sl else None,
            # СИЛА ВЫДЫХАЕТСЯ (10.09): было записано ниже, после раннего возврата — не доезжало
            "force_turn_at": (force_at or "")[11:16] or None, "force_turn_ago": force_ago,
            "oi_chg_pct": round(oi_chg * 100, 1) if oi_chg is not None else None,
            "px_chg_pct": round(px_chg * 100, 1) if px_chg is not None else None, "dominant": dom,
            "px": px1, "leaving_kind": kind, "day_low": held, "hit_bar": hit, "bubble_buy": bubble_buy,
            "ended_at": ended_at, "closing_bars": closing,
            "move_paid": move_paid, "paid_ratio": round(paid, 3) if paid is not None else None,
            "oi_add_usd": round(oi_add_usd, 0) if oi_add_usd is not None else None,
            "drawdown_pct": round(drawdown, 2) if drawdown is not None else None,
            "oi_trend_pct": round(oi_trend, 2) if oi_trend is not None else None,
            "bub_buy": bub_buy_bars, "bub_sell": bub_sell_bars, "skipped": len(skipped),
            "bubble_signal": bubble_signal, "bubble_choice": bubble_choice, "bubble_down": bubble_down,
            "bubble_vs_plot": bubble_vs_plot, "plot": _plt or None,
            "liq_side": liq_side, "liq_ratio": liq_ratio, "liq_ok": liq_ok,
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
    # ХОД ОТ ПСИХОЛОГИЧЕСКОГО ДНА (08.09, владелец): минимум за последнюю НЕДЕЛЮ — «люди реагируют
    # на то, сколько прошло вчера, позавчера, сегодня». Отсюда меряется, насколько монета уже ушла:
    # за сутки мерить нельзя — ход длится два-три дня, и вчерашний подъём в сутки не попадает.
    # ── ПЛЕЧО КОПИТСЯ, ЦЕНА СТОИТ (09.09) ────────────────────────────────────────────────────
    # Владелец: «мы поймали три монеты почти на самом деле — подумай, что можно сделать, чтобы
    # ловить их раньше». По часам опережения нет: деньги и цена приходят вместе. А по ДНЯМ есть —
    # интерес за три дня прибавляет заметно раньше, чем цена уходит.
    # Проверено на 21 монете, 40 случаев: интерес за 3 дня от +30% при цене в пределах ±10% дал
    # ход ≥10% за следующие три дня в 45% случаев, медиана +9.8%. При интересе от +50% и цене
    # ±5% — три случая из четырёх, медиана +34% (SOPH 04.09 → +44.6%, PROM 11.08 → +88%,
    # BLESS 13.06 → +40.9%). Промахи там, где цена уже ушла заранее (XAN 02.06: цена +8.9% → −8%).
    # В балл НЕ идёт — только метка на звезде и в ленте, считаем на своей выборке.
    def _accum_at(k: int) -> dict | None:
        """Признак на день o[k]: интерес за три дня против цены за те же три дня."""
        if k < 3:
            return None
        _o0 = (oi.get(o[k - 3]["datetime"][:10]) or {}).get("open_interest")
        _o3 = (oi.get(o[k]["datetime"][:10]) or {}).get("open_interest")
        if not (_o0 and _o3):
            return None
        _oi3 = (_o3 / _o0 - 1) * 100
        _px3 = (float(o[k]["close"]) / float(o[k - 3]["close"]) - 1) * 100
        if _oi3 >= 30 and abs(_px3) <= 10:
            return {"oi3": round(_oi3), "px3": round(_px3, 1),
                    "strong": bool(_oi3 >= 50 and abs(_px3) <= 5),
                    "day": o[k]["datetime"][:10]}
        return None

    if len(o) >= 4:
        _o0 = (oi.get(o[-4]["datetime"][:10]) or {}).get("open_interest")
        _o3 = (oi.get(o[-1]["datetime"][:10]) or {}).get("open_interest")
        if _o0 and _o3:
            nums["oi_3d_pct"] = round((_o3 / _o0 - 1) * 100, 1)
            nums["px_3d_pct"] = round((float(o[-1]["close"]) / float(o[-4]["close"]) - 1) * 100, 1)
        _now = _accum_at(len(o) - 1)
        if _now:
            nums["accum"] = _now
            why.append(f"плечо копится: интерес +{_now['oi3']}% за три дня при цене {_now['px3']:+.1f}%")
        else:
            # БЫЛО НА ЭТОЙ НЕДЕЛЕ (09.09, владелец: «монеты с таким накоплением растут выше обычных,
            # давай у такого лидера тоже показывать спутник, но по истории»). Ход уже начался, и
            # текущее условие «цена стоит» не выполняется — но происхождение важно: такая монета
            # после отката уходит выше, и списывать её нельзя. Окно — неделя.
            for _k in range(len(o) - 2, max(2, len(o) - 8), -1):
                _was = _accum_at(_k)
                if _was:
                    _ago = len(o) - 1 - _k
                    nums["accum_past"] = dict(_was, ago=_ago)
                    why.append(f"плечо копилось {_ago} дн назад: интерес +{_was['oi3']}% при цене {_was['px3']:+.1f}%")
                    break

    _low7 = min(float(r.get("low") or r["close"]) for r in o[-7:]) if len(o) >= 3 else None
    if _low7:
        nums["low7"] = round(_low7, 10)
        nums["run_from_low7"] = round((float(o[-1]["close"]) / _low7 - 1) * 100, 1)
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
        # ── ОТКАТ БЕЗ РАЗДАЧИ (08.09, случай USELESS против DOOD; владелец: «пока ожили USELESS,
        # который не упал на дно, и VVV с большой капой»). После сбора монета либо откатывается на
        # затухающем обороте — продавать некому, полка держится, — либо её раздают: оборот на
        # откате выше, чем в день сбора. Числа за 04–08.09:
        #   USELESS: сбор 04.09 при $1925M, откат −16% при $556M и −30% от вершины → ×0.29 → ожил;
        #   DOOD:    сбор 06.09 при $84M, назавтра $298M при цене −3.6%          → ×3.55 → раздали.
        # Считаем отношение МАКСИМАЛЬНОГО оборота дней после сбора к обороту дня сбора.
        _hd = None
        if hv:
            _hd = (hv[0][0] if len(hv) == 1 else max(hv, key=lambda t: t[1])[0])
        if _hd:
            _hv_day = next((r for r in days if r.get("datetime", "")[:10] == _hd.get("datetime", "")[:10]), None)
            _after = [r for r in days if r.get("datetime", "") > (_hd.get("datetime") or "")]
            _hq = float((_hv_day or {}).get("quote_volume") or 0)
            _aq = max((float(r.get("quote_volume") or 0) for r in _after), default=0.0)
            if _hq > 0 and _after:
                _ratio = _aq / _hq
                nums["after_harvest_vol"] = round(_ratio, 2)
                nums["after_harvest"] = ("раздали" if _ratio >= 2 else
                                         "откат без раздачи" if _ratio <= 0.7 else "поровну")
                if nums["after_harvest"] == "откат без раздачи":
                    why.append(f"откат без раздачи (оборот после сбора ×{_ratio:.2f})")
                elif nums["after_harvest"] == "раздали":
                    why.append(f"раздали после сбора (оборот ×{_ratio:.2f})")
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
        # СОГЛАСИЕ ПУЗЫРЕЙ С ПРОГНОЗОМ (08.09): прогноз живёт на дневках, пузыри — факт дня.
        # Расходятся — ставим меньше, сходятся — больше. Мягко: признак новый, ждём журнала.
        _bvp = _tv.get("bubble_vs_plot")
        if _bvp == "против":
            score *= 0.85
        elif _bvp == "подтверждают":
            score *= 1.10
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
                      "at_target": _tv.get("at_target"), "move_paid": _tv.get("move_paid"),
                      # откат без раздачи / раздали — признак наблюдения (08.09), в балл пока не идёт
                      "after_harvest": v.get("nums", {}).get("after_harvest"),
                      "after_harvest_vol": v.get("nums", {}).get("after_harvest_vol")}
        # ── 1. КОНЧИЛОСЬ — ВОН ИЗ ОЧЕРЕДИ (08.09, владелец: «отделять монеты, которые точно пойдут,
        # от тех, что уже выпадают»): было событие конца по барам и интерес после него не растёт —
        # монета не участвует в отборе вовсе, пока интерес не пойдёт вверх вместе с ценой.
        # DOOD 08.09: событие в 05:30, восемь баров лонги закрывают, а он всё утро в первых.
        _ended = _tv.get("ended_at")
        _tr2 = _tv.get("oi_trend_pct")
        if _ended and (_tr2 is None or _tr2 <= 0):
            v["queue"]["out_reason"] = "кончилось " + str(_ended)[11:16]
            score = 0.0
            v["queue"]["score"] = 0.0

        # ── 2. ГОТОВА ИЛИ ИДЁТ (08.09): в одном списке лежали SOPH с +78% за день и NOM с +2.7% —
        # первому вход поздно, второму рано, а балл ставил первого выше. Делим по ходу дня:
        # «готова» — ход ещё не начался (до 8% за день), «идёт» — уже едет.
        v["queue"]["stage"] = "идёт" if (_px_chg is not None and _px_chg >= 8) else "готова"
        queue.append((score, s2))
    queue.sort(reverse=True)
    ordered = [s2 for _, s2 in queue if (out["coins"][s2].get("queue") or {}).get("score", 0) > 0]

    # ── 3. УСТОЙЧИВОСТЬ МЕСТА (08.09, владелец: «как исключить такие смены местами»): место скакало
    # от прогона к прогону, потому что у порога разница в сотые доли балла. Теперь монета входит в
    # первые, только продержавшись в верхних строках ДВА прогона подряд, и выходит из них тоже
    # через два. Держим короткую память в output/queue_state.json — только последний состав.
    TOP = 3
    prev = {}
    try:
        prev = json.loads((BASE_DIR / "output" / "queue_state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    was_top = set(prev.get("top") or [])
    cand = ordered[:TOP]
    stable = []
    for s2 in ordered:
        if len(stable) >= TOP:
            break
        if s2 in cand and (s2 in was_top or s2 in (prev.get("cand") or [])):
            stable.append(s2)          # держится второй прогон подряд — в первые
    for s2 in was_top:                 # тот, кто выпал впервые, остаётся ещё один прогон
        if len(stable) >= TOP:
            break
        if s2 in ordered and s2 not in stable:
            stable.append(s2)
    for s2 in ordered:                 # добираем, если мест не хватило
        if len(stable) >= TOP:
            break
        if s2 not in stable:
            stable.append(s2)
    # ── ТЯНЕТ ОДНА — РАЗМЕР, А НЕ БАЛЛ (08.09, владелец: «применим сразу к рейтингу, иначе выборка
    # ложная»). Подтверждено дважды: 07.09 SOPH +11.7% при медиане наших +0.5%, 08.09 SOPH +104%
    # при медиане +3.2% — вторые и третьи не дали ничего оба дня. Балл НЕ меняем: он мерит саму
    # точку входа, и если подмешать в него фон, журнал перестанет её измерять. Меняем РАЗМЕР:
    # пока лидер тянет и у него нет конца, остальные строки получают размер ноль и пометку почему.
    # Признак снимается сам, когда у лидера приходит событие конца.
    _moves = [((out["coins"][s2].get("today") or {}).get("px_chg_pct") or 0.0) for s2 in ordered]
    lead_sym = None
    lead_gap = 0.0
    lead_run7 = None
    if ordered and _moves:
        _top_i = max(range(len(ordered)), key=lambda i: _moves[i])
        _med = sorted(_moves)[len(_moves) // 2]
        _mv = _moves[_top_i]
        _gap = (abs(_mv) / abs(_med)) if abs(_med) >= 0.3 else (abs(_mv) / 0.3 if _mv else 0.0)
        _t_lead = out["coins"][ordered[_top_i]].get("today") or {}
        # ПОРОГ — ХОД ОТ ПСИХОЛОГИЧЕСКОГО ДНА (08.09, владелец: «за сутки лидера считать некорректно,
        # ликвидность уходит в монету, когда памп большой, и это не за день, а от дна»; окно 7 дней —
        # «люди реагируют на то, сколько прошло вчера, позавчера, сегодня»). Дно за 60 дней остаётся
        # для места в истории; лидер меряется от минимума последней недели — оттуда, откуда идёт
        # текущее движение. Ход за сутки — запасной, если недельных дневок нет.
        _run7 = ((out["coins"][ordered[_top_i]].get("nums") or {}).get("run_from_low7"))
        if _gap >= 5 and (_run7 if _run7 is not None else _mv) >= 50 and not _t_lead.get("ended_at"):
            lead_sym, lead_gap = ordered[_top_i], round(_gap, 1)
            lead_run7 = round(_run7) if _run7 is not None else None
    if lead_sym:
        for s2 in ordered:
            q = out["coins"][s2].get("queue") or {}
            if s2 == lead_sym:
                q["size"] = "основной"
                q["lead"] = True
            else:
                q["size"] = "ноль"
                q["hold_reason"] = f"тянет {lead_sym.replace('USDT','')} ×{lead_gap} к медиане наших"
    else:
        for i2, s2 in enumerate(ordered):
            q = out["coins"][s2].get("queue") or {}
            q["size"] = "основной" if i2 == 0 else ("четверть" if i2 < 3 else "—")

    rest = [s2 for s2 in ordered if s2 not in stable]
    out["queue"] = stable + rest
    out["first"] = stable
    out["pulls"] = {"sym": lead_sym, "gap": lead_gap, "run7": lead_run7} if lead_sym else None
    out["dropped"] = [s2 for s2 in (out["coins"] or {})
                      if (out["coins"][s2].get("queue") or {}).get("out_reason")]
    try:
        (BASE_DIR / "output" / "queue_state.json").write_text(
            json.dumps({"top": stable, "cand": cand}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
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
            "stage": q.get("stage"), "out_reason": q.get("out_reason"),
            "size": q.get("size"), "hold_reason": q.get("hold_reason"),
            "after_harvest": q.get("after_harvest"), "after_harvest_vol": q.get("after_harvest_vol"),
            "run_from_low7": (v.get("nums") or {}).get("run_from_low7"),
            "accum": (v.get("nums") or {}).get("accum"),
            "force_turn_ago": ((v.get("today") or {}).get("force_turn_ago")),
            "accum_past": (v.get("nums") or {}).get("accum_past"),
            "bubble_sure": ((v.get("today") or {}).get("bubbles") or [{}])[-1].get("sure"),
            "bubble_vs_plot": (v.get("today") or {}).get("bubble_vs_plot"),
            "liq_side": (v.get("today") or {}).get("liq_side"),
            "liq_ok": (v.get("today") or {}).get("liq_ok"),
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
