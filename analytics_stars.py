"""Звёзды · данные для карты долгостроя. Один расчёт на два экрана.

Что здесь. Отбор монет журнала, их возраст, свежесть, пробелы ручных
полей, плотность подтверждений и карточка каждой звезды — то есть всё,
из чего складывается СПИСОК звёзд. Разметки нет ни одной: функции
отдают словари, которые уходят в JSON и дальше в отрисовку.

Почему не в render_orbit.py, где это лежало. Пока сводка и орбита
жили в одном документе, сводка брала готовые звёзды из window.ORB —
глобальной переменной, которую орбита выставляла рядом. Это и был
довод за то, что звёзды принадлежат орбите: она их считала, а сводка
пользовалась соседством.

Соседства больше нет. Экраны переезжают в отдельные iframe, у каждого
своё окно, и window.ORB в документе сводки просто не существует.
Остаётся выбор из двух: сводка импортирует функции орбиты — то есть
рендер зависит от рендера, чего мы только что избавились, — или
звёзды перестают быть частью одного экрана и становятся тем, чем по
факту являются: одними данными, которые два экрана показывают
по-разному. Здесь выбрано второе.

Что при этом ОСТАЛОСЬ в орбите и осталось правильно: раскладка звёзд
по холсту, их размеры, мерцание, порядок отрисовки — всё, что
отвечает на вопрос «как выглядит», а не «что показываем».
"""

from __future__ import annotations

import math

from core_config import LEADERS_PATH
from core_models import Candidate
from analytics_calendar import calendar_state
from analytics_flow import CASE_RU, case_key, case_of, flow_leader, flow_order
from analytics_leaders import read_store
from analytics_action import decide as decide_action
from analytics_actionlog import log_actions
from analytics_decisions import load_decisions
from analytics_exit import exit_watch
from analytics_size import position_size
from analytics_link import unlock_leverage_link
from analytics_metrics import (
    LEAD_X1, base_symbol, card_data, fmt_cap, max_vol_ratio,
    relative_moves, sample_medians,
)
from analytics_momentum import (
    star_oi, star_late, star_pulse, star_cycle, star_divergence,
)


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


def _alive_gap_days(rec: dict) -> float | None:
    """Дни с последнего подтверждения фигуры детектором (Р-25).

    Считает от last_alive — поля, которое журнал пишет только по
    flow.detected. last_hit сюда не годится: он обновляется и
    аномалией объёма, а всплеск на трупе фигуры не делает труп живым.
    None — поле ещё не накопилось (записи старше 22.08).
    """
    import datetime as _dt
    raw = rec.get("last_alive")
    if not raw:
        return None
    try:
        when = _dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if when.tzinfo is None:
            when = when.replace(tzinfo=_dt.timezone.utc)
    except ValueError:
        return None
    gap = (_dt.datetime.now(_dt.timezone.utc) - when).total_seconds() / 86400
    return round(max(0.0, gap), 1)


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
        # Сила перекреста, а не только сторона — vortex_cross() её уже
        # считает (vi_plus − vi_minus), но раньше терялась здесь же.
        # Направление без силы неотличимо между «едва развернулся» и
        # «разошлись уверенно» — тот же пробел, что был у OI до
        # появления состояния held/repeat/cleared.
        if vx.get("spread") is not None:
            out["vxSpread"] = float(vx["spread"])

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

    # Вердикт цена+дельта+OI вместе — то, чем разбирались все кейсы
    # вручную (GPS/PORTAL/ONG/BLESS). Пусто по построению, если OI не
    # передан или тройка не сложилась ни в один из четырёх случаев —
    # это честное «нечего сказать», а не пропуск.
    st = intra.get("stance") or {}
    if st.get("verdict"):
        out["stanceVerdict"] = str(st["verdict"])
        out["stancePricePct"] = float(st.get("price_pct") or 0.0)
        out["stanceOiPct"] = float(st.get("oi_pct") or 0.0)

    # Упругость: та же продажа двигает цену слабее или сильнее, чем в
    # прошлый раз. Меньше единицы — сопротивление растёт (та же
    # продажа даёт меньший сдвиг), больше — стакан истончается.
    imp = intra.get("impact") or {}
    if imp.get("ratio") is not None:
        out["impactRatio"] = float(imp["ratio"])

    # Раздача/поглощение по всему окну, без OI (в отличие от stance):
    # цена и дельта разошлись — кто-то стоял против агрессии. Раздача
    # — покупали агрессивно, а цена всё равно ушла вниз (приняли
    # пассивные шорты). Поглощение — обратное, бычий знак.
    bal = intra.get("balance") or {}
    if bal.get("window"):
        out["balanceWindow"] = str(bal["window"])
        if bal.get("share") is not None:
            out["balanceShare"] = float(bal["share"])

    # Средняя цена крупных покупок против текущей: опора снизу или
    # навес сверху. Опора — крупный покупатель в плюсе, не спешит.
    # Навес — он в минусе и ждёт безубытка, то есть сам является
    # будущим предложением.
    lv = intra.get("big_levels") or {}
    if lv.get("kind"):
        out["bigLevelKind"] = str(lv["kind"])
        out["bigLevelPct"] = float(lv.get("vs_price_pct") or 0.0)

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

    d = card_data(c)
    cats = getattr(c, "categories", None) or []
    out = {
        "score": int(getattr(c, "score", 0) or 0),
        "sector": (cats[0] if cats else "—").lower(),
        "cap": fmt_cap(d["cap"]),
        "ath": round(d["ath"]),
        "pattern": CASE_RU.get(case_key(case_of(c)), "—"),
        "v1h": d["v1h"], "v4h": d["v4h"], "v1d": d["v1d"],
        "p1d": round(d["p1d"], 1),
        "p3d": round(d["p3d"], 1),
        "p7d": round(d["p7d"], 1),
        "fund": round(d["fund"], 4),
        "series": [round(float(v), 6) for v in (d["series"] or [])],
    }
    # Н-7 тех.долга: FDV/капитализация уже считается в candidate.py
    # (raw["fdv_ratio"]) и нигде не читалась — ни в скоринге, ни на
    # экране. Величина двусторонняя (малый флоат = и потенциал хода,
    # и риск на разлоке — см. Н-5), поэтому отдаётся числом, а не
    # вердиктом; решение остаётся за человеком.
    #
    # 0.0 в candidate.py означает «капитализация неизвестна», то есть
    # честное «не измерено», а не «флоат полный» — ключ поэтому не
    # добавляется вовсе, как и у остальных величин в этой функции.
    fdv = float((getattr(c, "raw", None) or {}).get("fdv_ratio") or 0.0)
    if fdv > 0:
        out["fdv"] = round(fdv, 2)
    return out


# ── Дерево фаз и расстояние до стопа ──────────────────────────
# Оба правила считались в JS орбиты, а сводка брала их оттуда
# функциями через window.ORB — это и была «единственная точка связи с
# модулем сводки». Точка исчезает: в отдельных iframe брать неоткуда,
# а порог, дважды выписанный в двух документах, разъезжается при
# первой же правке. Правило одно, считается один раз, результат едет
# в данных звезды.
#
# В проекте это уже сформулировано в day_ratios(): «считается ЗДЕСЬ, а
# не в JS» — в браузере расчёт вне досягаемости пробы.

# Глубже этого от ATH разница уже ничего не решает — гейт пороговый.
PHASE_ATH_GATE = -80.0
# Ниже этой кратности от дна разгон считается первым.
PHASE_FIRST_UP = 150.0


def star_phase(star: dict) -> dict:
    """Дерево фаз: три состояния, каждое даёт действие, а не оценку.

    Ключ k читает отбор («go» — брать), строка a показывается.

    ВНИМАНИЕ на ветку «пила». Она выбирается по признаку saw, которого
    в словаре звезды НЕ существует: ни build_stars, ни журнал такого
    поля не пишут — здесь оно ровно так же отсутствует, как отсутствовало
    в JS. То есть третья ветка недостижима, и монета с пилой всегда
    получает «ровный рост · ждать сквиза». Канал мёртв с заведения, как
    были мертвы days и px до починки. Поведение сохранено дословно, а не
    исправлено заодно: починка меняет то, что видно на экране, и должна
    быть отдельным решением.
    """
    if float(star.get("ath") or 0.0) > PHASE_ATH_GATE:
        return {"a": "вне зоны дна", "k": "wait"}
    if float(star.get("up") or 0.0) < PHASE_FIRST_UP:
        return {"a": "первая фаза · брать", "k": "go"}
    if star.get("saw"):
        return {"a": "пила · брать у нижней границы", "k": "go"}
    return {"a": "ровный рост · ждать сквиза", "k": "wait"}


def stop_pct(star: dict) -> int:
    """Насколько цена выше стопа, в процентах. Нет стопа — ноль.

    Округление СПЕЦИАЛЬНО не через round(). Питоновский round()
    отправляет ровную половину к чётному (22.5 → 22), а Math.round в
    JS — всегда вверх (22.5 → 23). Пока правило жило в браузере,
    работал второй вариант; перенеси его дословно через round() — и
    число у части монет поменялось бы на единицу, без падения и без
    следа в логе. Величины ровно в половину здесь не экзотика: их
    даёт любой стоп, отстоящий на аккуратную долю цены.
    """
    px = float(star.get("px") or 0.0)
    stop = float(star.get("stop") or 0.0)
    if not px or not stop:
        return 0
    return math.floor((px - stop) / px * 100 + 0.5)


def build_stars(candidates: list[Candidate],
                permission: dict | None = None) -> list[dict]:
    """Лидер FLOW и монеты журнала лидеров — отдельными звёздами.

    permission приходит АРГУМЕНТОМ, а не считается здесь: разрешение
    рынка уже посчитано для словаря рынка, оно требует контекста
    биткоина и сетевых величин, и второй вызов дал бы и лишнюю
    работу, и второй источник тех же чисел. Без него ступень размера
    учтёт только монетные признаки — это честное поведение при
    неполном входе, а не ошибка.

    На орбите они были бы восьмым узлом и спорили бы с категориями.
    Здесь другой смысл: не срез выборки, а история отбора, поэтому
    и место другое — поле вокруг кольца.

    Три признака, три разных свойства, чтобы они читались вместе:
      свежесть → размер и яркость
      объём ≥ x50 → цвет и второй луч с кольцом
      текущий лидер прогона → подпись тикером
    """
    flow_j = read_store(LEADERS_PATH)
    syms = [k for k in flow_j if not k.startswith("_")]
    if not syms:
        return []

    ages = {s: _star_age_days(flow_j.get(s) or {}) for s in syms}
    dated = [a for a in ages.values() if a is not None]

    lead = flow_leader(candidates)
    lead_sym = lead.symbol.upper() if lead is not None else ""
    by_symbol = {c.symbol.upper(): c for c in candidates}

    # Место монеты в текущем списке FLOW и размер этого списка.
    # Порядок берём у flow_order — той же функции, которой сортируется
    # сам отчёт, чтобы номер на карточке и строка в списке не разошлись.
    order = flow_order(candidates)
    fpos = {c.symbol.upper(): i + 1 for i, c in enumerate(order)}
    ftotal = len(order)

    # Р-5: знаменатель прилива. Считается ОДИН раз на прогон — он общий
    # для всех звёзд, а внутри цикла пересчитывался бы двести раз.
    medians = sample_medians(candidates)

    # Макродаты частокола (Р-7) — один раз на прогон, как и медианы.
    cal_items = (calendar_state() or {}).get("items") or []

    # Какие монеты мы ДЕРЖИМ — из журнала решений (Р-14): вход без
    # последующего выхода. Без журнала множество пусто, и зал честно
    # покажет все монеты в «брать»: скринер не знает, чем мы владеем,
    # и придумывать это за человека нельзя.
    held_syms = set()
    for rec in (load_decisions() or []):
        sym = str(rec.get("symbol") or "").upper().replace("USDT", "")
        act = str(rec.get("action") or "")
        if not sym:
            continue
        if act == "вход":
            held_syms.add(sym)
        elif act == "выход":
            held_syms.discard(sym)



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
        ratio = max_vol_ratio(rec)
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
        case = case_of(c) if c is not None else ""
        if not case:
            case = str(rec.get("entry_case") or "")
        st = case_key(case)
        label = base_symbol(sym)
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

            # Р-25: сколько дней фигура не подтверждалась детектором.
            # 0 или около — признаки держатся (ожидание повода);
            # большой разрыв — распались (смерть фигуры). None —
            # поле ещё не копилось: last_alive пишется с 22.08, и у
            # старых записей отличать «нет данных» от «давно мертва»
            # обязан читатель, а не ноль-враньё.
            "aliveGapDays": _alive_gap_days(rec),
            "runsSeen": int(rec.get("runs_seen") or 0),
            "chg": round(float(rec.get("change_pct") or 0.0), 1),

            # Р-5: опережение выборки в ПУНКТАХ по окнам d1/d7/d30.
            # Пусто у монеты, выпавшей из текущей выборки: хода нет —
            # нечего и сравнивать, а ноль читался бы как «шла вровень».
            "rel": relative_moves(getattr(c, "raw", None), medians),
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

            # Ручное поле характера истории — в звезду плоским ключом:
            # его читает правило размера (Р-15), а у распила «упала на
            # 96%» не означает «пережила цикл».
            **({"listingKind": str(rec["listing_kind"])}
               if rec.get("listing_kind") else {}),

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
            **star_cycle(rec.get("max_up_x"), rec.get("up_x")),
            **star_divergence(c),
            # Место в текущем прогоне. У монеты журнала, выпавшей из
            # выборки, поля нет вовсе — экран тогда скажет «вне
            # выборки», а не нарисует нулевой номер, который выглядел
            # бы как первое место наоборот.
            **({"fpos": fpos[sym.upper()], "ftotal": ftotal}
               if sym.upper() in fpos else {}),

            # Числа карточки берём тем же card_data(), что кормит карточки
            # отчёта: иначе одна монета показывала бы на орбите и в
            # отчёте разные цифры, и расхождение всплыло бы не сразу.
            **_star_card(c),
        })

    # Фаза и расстояние до стопа кладутся В ДАННЫЕ, а не считаются
    # каждым экраном у себя: раньше это были две функции в JS орбиты,
    # которые сводка получала через window.ORB. Считаем после сборки
    # словаря — обоим правилам нужны уже готовые поля (ath, up, px,
    # stop), и повторять их выборку незачем.
    for s in out:
        s["phase"] = star_phase(s)
        s["stopPct"] = stop_pct(s)
        # Р-12: связка плеча и транша. Считается ЗДЕСЬ, а не внутри
        # сборки, по той же причине, что фаза: ей нужны уже готовые
        # поля обеих половин (unlockDays от _star_unlocks, oiRise и
        # oiHeld от star_oi). Пустой словарь — ключей не добавится.
        s.update(unlock_leverage_link(s))
        # Р-11/Р-17: правило выхода. Здесь же, по готовым полям —
        # календарь монеты, поток из пульса, крупные сделки. Макродаты
        # приходят аргументом: они общие для всей выборки, и читать их
        # заново на каждую звезду значило бы открывать один файл
        # двести раз за прогон.
        # Р-4/Р-15: ступень размера. Считается ПОСЛЕ связки и до
        # показа: ей нужны и монетные признаки (флоат, транш, связка),
        # и рыночные из разрешения — единственного источника истины
        # для окна выборки.
        s["size"] = position_size(s, permission)

        # Р-27: действие и его группа — из готовых полей звезды плюс
        # разрешение рынка. Считается ПОСЛЕ размера: ступень входит в
        # причину «брать половиной».
        s["act"] = decide_action(s, permission, bool(held_syms and
                                                    s.get("t") in held_syms))

        ex = exit_watch(s, cal_items)
        if ex["watch"]:
            s["exitWhy"] = ex["why"]
            if ex["deadlineDays"] is not None:
                s["exitDeadline"] = ex["deadlineDays"]

    # Р-28: предложения записываются ЗАРАНЕЕ, до всякого показа.
    # Стратегия выхода — гипотеза; проверить её можно только по логу,
    # сделанному до исхода. Пишется лишь смена предложения, ошибка
    # записи прогон не роняет: это материал замера, а не работа.
    try:
        log_actions(out)
    except Exception:
        pass

    # Лидер рисуется последним — поверх остальных, если рядом окажется сосед
    out.sort(key=lambda s: (s["lead"], s["f"]))
    return out

