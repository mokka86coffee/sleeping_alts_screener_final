"""Пульс-детекторы топлива: заряд, разряд, перегрев, поглощение.

Файл начинался как детектор заряда (С-2) и вырос в дом для всех
детекторов, читающих производные из пульса: заряд на сжим, разряд
после него (С-4), перегрев лонгов (Т-4) и поглощение у дна (Т-3).
Общее у них одно — ноль сетевых запросов: всё считается из уже
записанных точек пульса.

Заряд на сжим (техдолг «сжим на тонком флоате», С-2 и флаг С-1).

Предвестник, а не след: отрицательный фандинг несколько баров подряд
ПРИ растущей цене означает, что коротких больше, чем длинных, и они
уже в убытке — их вынос и есть сжим. Считается целиком из пульса,
ноль новых запросов (С-2). Отдельным флагом — условие тонкого флоата
из С-1 (floatPct < 15 при fdvRatio > 5): сочетание сильнее каждого
по отдельности, но в ОТБОР ни то ни другое отсюда не идёт — порог
объявлен обсуждаемым, решение об отборе за человеком.

По рамке проекта это ЗАРЯД ВВЕРХ, не предупреждение: фандинг
симметричен, шорт-перекос — топливо сжима (та же симметрия, что в
разрешении рынка). Скор не трогается — правило всех техдолгов.

SKYAI (готовый размеченный пример из С-5) в текущем окне пульса
детектор честно НЕ отмечает: там послесжимовое остывание — фандинг
положителен, OI сдувается. Заряд был до пампа, а рабочее окно
пульса — неделя; глубже недели такие случаи проверяются архивом
пульса (pulse_archive/, до 30 дней, analytics_pulse.read_history)
(решение об архиве уже висит — теперь на нём и С-4/С-5).
"""

from __future__ import annotations

import json

from analytics_pulse import PULSE_PATH

# Сколько подряд минусовых баров считаются зарядом. Три бара пульса —
# около трёх часов: разовый минус на перекосе одной сделки отсеивается,
# устойчивый перекос коротких — нет. Порог поведения не меняет ничьего
# скора и калибруется отдельно, когда появится архив.
SQUEEZE_NEG_BARS = 3

# Условие тонкого флоата из С-1 — как флаг рядом с зарядом.
THIN_FLOAT_PCT = 15.0
THIN_FDV_RATIO = 5.0


def charge_from_rows(rows: list[dict],
                     neg_bars: int = SQUEEZE_NEG_BARS) -> dict:
    """Заряд по ряду точек пульса одной монеты.

    Возвращает {"negRun", "pxChg", "charged", "note"}. negRun — сколько
    подряд последних баров фандинг отрицателен; pxChg — ход цены за эти
    бары в процентах (цена последнего бара к цене перед серией);
    charged — negRun >= neg_bars И цена выше, чем перед серией. note —
    готовая тёплая строка для показа, None если заряда нет.
    """
    out = {"negRun": 0, "pxChg": None, "charged": False, "note": None,
           "capped": False}
    if not rows:
        return out
    run = 0
    for r in reversed(rows):
        f = r.get("funding")
        if f is not None and f < 0:
            run += 1
        else:
            break
    out["negRun"] = run
    if run == 0:
        return out
    # Серия может покрывать всё окно пульса (неделя): бара «перед
    # серией» тогда просто нет в хранимом ряду. Это не повод молчать —
    # хронический шорт-перекос интереснее разового. Сравниваем цену с
    # первой точкой окна и честно помечаем серию усечённой («48+»).
    capped = run >= len(rows)
    out["capped"] = capped
    base = (rows[0] if capped else rows[-(run + 1)]).get("price")
    last = rows[-1].get("price")
    if not base or not last:
        return out
    chg = (last / base - 1.0) * 100.0
    out["pxChg"] = round(chg, 1)
    if run >= neg_bars and chg > 0:
        out["charged"] = True
        shown = f"{run}+" if capped else f"{run}"
        out["note"] = (f"заряжен: фандинг минус {shown} "
                       f"{_bars_word(run)} при росте {chg:+.1f}% — "
                       f"шорты платят и уже в убытке")
    return out


def discharge_from_rows(rows: list[dict],
                        back: int = 6,
                        oi_drop_pct: float = 8.0) -> dict:
    """С-4: заменитель ликвидаций — РАЗРЯД после сжима.

    Настоящий поток ликвидаций недоступен (Binance закрыл, агрегаторы
    платные). Заменитель из пульса: на отрезке последних `back` баров
    фандинг переходит из минуса в плюс (шорты вынесены), а OI падает
    от пика отрезка не меньше oi_drop_pct (позиции закрыты силой).

    НА ЭКРАН НЕ ВЫВОДИТЬ: документ требует сперва проверить на
    истории, насколько заменитель совпадает с настоящими
    ликвидациями, а истории нет до архива пульса. Функция готова к
    этой проверке — и только к ней.
    """
    out = {"discharged": False, "oiDropPct": None, "fundingFrom": None}
    if len(rows) < back + 1:
        return out
    seg = rows[-(back + 1):]
    funds = [r.get("funding") for r in seg]
    ois = [r.get("oi_usd") for r in seg]
    if any(v is None for v in funds) or any(not v for v in ois):
        return out
    f_min, f_now = min(funds[:-1]), funds[-1]
    peak, now = max(ois), ois[-1]
    drop = (1.0 - now / peak) * 100.0 if peak else 0.0
    out["fundingFrom"] = f_min
    out["oiDropPct"] = round(drop, 1)
    out["discharged"] = f_min < 0 <= f_now and drop >= oi_drop_pct
    return out


def _bars_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "бар"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "бара"
    return "баров"


def absorption_for(symbol: str) -> dict:
    """Поглощение у дна для одной монеты по текущему пульсу."""
    rows = _pulse().get(symbol)
    return absorption_from_rows(rows if isinstance(rows, list) else [])


def thin_float(unlock_state: dict | None) -> bool:
    """Флаг С-1: тонкий флоат при высоком FDV, из уже посчитанного."""
    u = unlock_state or {}
    fp, fr = u.get("floatPct"), u.get("fdvRatio")
    try:
        return (fp is not None and fr is not None and
                float(fp) < THIN_FLOAT_PCT and float(fr) > THIN_FDV_RATIO)
    except (TypeError, ValueError):
        return False


_PULSE_CACHE: dict = {"mtime": None, "data": {}}


def _pulse() -> dict:
    """Пульс с кешем на процесс: сборка звёзд зовёт детекторы на
    каждую монету, и без кеша файл в мегабайты перечитывался бы
    десятки раз за прогон. Ключ свежести — mtime файла."""
    try:
        mtime = PULSE_PATH.stat().st_mtime
    except OSError:
        return {}
    if _PULSE_CACHE["mtime"] != mtime:
        try:
            with open(PULSE_PATH, encoding="utf-8") as f:
                _PULSE_CACHE["data"] = json.load(f)
            _PULSE_CACHE["mtime"] = mtime
        except (OSError, ValueError):
            return _PULSE_CACHE["data"] or {}
    return _PULSE_CACHE["data"]


# Порог перегрева лонгов (Т-4): фандинг в пульсе лежит в процентах,
# ставка за период ≥ 0.03% считается экстремальной — толпа в лонге
# платит заметные деньги за удержание, и это топливо ПРОТИВ позиции.
HOT_FUNDING_PCT = 0.03
HOT_BARS = 3


def heat_from_rows(rows: list[dict],
                   hot_bars: int = HOT_BARS,
                   thresh: float = HOT_FUNDING_PCT) -> dict:
    """Т-4: перегрев лонгов — фандинг у экстремума серию баров.

    Симметрия заряда: заряд — шорты платят при росте, перегрев —
    лонги платят экстремальную ставку. Смысл разный: заряд —
    топливо ВВЕРХ и тёплая строка, перегрев — топливо ПРОТИВ
    открытой позиции, и потребитель у него один — exitWhy (строку
    дописывает второй проход звёзд, только при позиции книги).
    """
    out = {"hotRun": 0, "hot": False, "note": None}
    run = 0
    for r in reversed(rows):
        f = r.get("funding")
        if f is not None and f >= thresh:
            run += 1
        else:
            break
    out["hotRun"] = run
    if run >= hot_bars:
        out["hot"] = True
        out["note"] = (f"фандинг перегрет: лонги платят "
                       f"{run} {_bars_word(run)} подряд — "
                       f"толпа на нашей стороне переполнена")
    return out


def absorption_from_rows(rows: list[dict],
                         press_bars: int = 3,
                         drop_pct: float = 5.0,
                         near_pct: float = 6.0) -> dict:
    """Т-3: поглощение у дна — самый надёжный сигнал дна по
    методологии трейдеров: вынос лонгов (цена и OI падают), после
    которого цена ДЕРЖИТСЯ при продолжающихся агрессивных продажах —
    спрос стоит под ценой и молча забирает предложение.

    Полного CVD у нас нет; приближение из пульса: (а) в окне был
    вынос — падение цены ≥ drop_pct при снижении OI от пика к лою;
    (б) после лоя прошло ≥ press_bars баров и нового минимума нет;
    (в) на последних press_bars барах давление продавцов не слабее
    покупателей (vi_m ≥ vi_p — без этих полей сигнала нет: держаться
    без продаж умеет любой отскок); (г) цена ещё у дна (не дальше
    near_pct от лоя). Скор и отбор не трогаются — поле знания.
    """
    out = {"absorbed": False, "lowAgoBars": None, "note": None}
    if len(rows) < press_bars + 3:
        return out
    px = [r.get("price") for r in rows]
    if any(not v for v in px):
        return out
    ilow = min(range(len(px)), key=lambda i: px[i])
    ago = len(px) - 1 - ilow
    out["lowAgoBars"] = ago
    if ago < press_bars:
        return out
    peak_before = max(px[:ilow + 1])
    if not peak_before or (1 - px[ilow] / peak_before) * 100 < drop_pct:
        return out
    ois = [r.get("oi_usd") for r in rows[:ilow + 1]]
    ois = [v for v in ois if v]
    if len(ois) >= 2 and ois[-1] >= max(ois):
        return out                      # OI не сдувался — выноса не было
    tail = rows[-press_bars:]
    vm = [r.get("vi_m") for r in tail]
    vp = [r.get("vi_p") for r in tail]
    if any(v is None for v in vm) or any(v is None for v in vp):
        return out
    if sum(vm) < sum(vp):
        return out                      # продавцы не давят — не абсорбция
    if min(px[ilow + 1:]) < px[ilow]:
        return out                      # новый минимум — дно не держится
    if px[-1] > px[ilow] * (1 + near_pct / 100):
        return out                      # цена уже уехала — не «у дна»
    out["absorbed"] = True
    out["note"] = (f"поглощение у дна: продавцы давят "
                   f"{press_bars} {_bars_word(press_bars)}, а нового "
                   f"минимума нет — спрос стоит под ценой")
    return out


def squeeze_for(symbol: str, unlock_state: dict | None = None) -> dict:
    """Заряд для одной монеты по текущему пульсу.

    Читает пульс сам, как это делает analytics_exit: пульс — общий
    файл, а не поле звезды. При недоступном пульсе — пустой заряд,
    сборка не падает.
    """
    pulse = _pulse()
    if not pulse:
        return {"negRun": 0, "pxChg": None, "charged": False,
                "note": None, "capped": False, "hotRun": 0,
                "hot": False, "hotNote": None,
                "thin": thin_float(unlock_state)}
    rows = pulse.get(symbol)
    # В пульсе рядом с монетами живут служебные ключи (не-списки);
    # заряд считается только по настоящему ряду.
    rows = rows if isinstance(rows, list) else []
    out = charge_from_rows(rows)
    # Т-4 едет тем же полем звезды: перегрев — та же шкала фандинга,
    # что и заряд, только другой конец; потребитель — exitWhy.
    heat = heat_from_rows(rows)
    out["hotRun"], out["hot"] = heat["hotRun"], heat["hot"]
    out["hotNote"] = heat["note"]
    # thin считается из переданного состояния, если оно есть; звёзды
    # передают его вторым проходом (см. analytics_stars) — там
    # floatPct/fdvRatio уже разложены, и хвост «флоат тонкий — сжиму
    # есть где разогнаться» дописывается именно там, один раз.
    out["thin"] = thin_float(unlock_state)
    return out

# ── Т-6 · усилие против результата (школа потока ордеров) ──
# Профессионалы меряют не объём и не ход, а их ОТНОШЕНИЕ. Много
# усилия без результата — поглощение: кто-то держит уровень
# лимитками. Результат при иссякшем усилии — истощение. Это ответ
# на «rel_vol=10 у половины выборки ничего не различает»: rel_vol
# меряет только усилие; делённый на ход в ATR, он различает GPS
# (усилие ×10, ход +119% — отработало, ждать нечего) и BLESS
# (усилие есть, хода нет — льют и поглощают).
#
# Пороги — первая калибровка на глаз, ждут Р-9 как все.
EFFORT_MIN_RVOL = 4.0       # «усилие есть»: объём ×4 к своей норме
EFFORT_FLAT_ATR = 0.6       # «результата нет»: ход ≤ 0.6 дневного ATR
EFFORT_SPENT_ATR = 3.0      # «усилие отработало»: ход ≥ 3 ATR
EXHAUST_MIN_UP = 60.0       # истощение только НАВЕРХУ: ≥60% от дна окна
EXHAUST_MAX_RVOL = 1.2      # объём уже не приходит


def effort_state(raw: dict, flow: dict | None = None) -> dict | None:
    """Состояние «усилие против результата» из готовых полей.

    Ничего сетевого: rel_vol, atr_pct, ch_24h, up_from_low уже в
    метриках, delta_slope — в контексте FLOW, когда семейство
    отработало. Возврат None — состояния нет (обычный рынок), иначе
    {"ratio", "state", "note"} и опционально "divergence".

    Состояния взаимоисключающие; дивергенция дельты — независимый
    флаг поверх: цена наверху, а наклон накопленной дельты
    отрицательный — покупатели выдыхаются (признак GPS, которым
    никто не пользовался, теперь записан).
    """
    try:
        rel = float(raw.get("rel_vol") or 0.0)
        atr = float(raw.get("atr_pct") or 0.0)
        ch = float(raw.get("ch_24h") or 0.0)
        up = float(raw.get("up_from_low") or 0.0)
    except (TypeError, ValueError):
        return None
    if atr <= 0:
        return None

    result_atr = abs(ch) / atr
    ratio = round(rel / max(result_atr, 0.25), 1)

    state = note = None
    if rel >= EFFORT_MIN_RVOL and result_atr <= EFFORT_FLAT_ATR:
        state = "absorbing"
        note = (f"объём ×{rel:.1f} при ходе {result_atr:.1f} ATR — "
                f"льют и поглощают, уровень держат")
    elif rel >= EFFORT_MIN_RVOL and result_atr >= EFFORT_SPENT_ATR:
        state = "spent"
        note = (f"усилие ×{rel:.1f} отработало ходом {result_atr:.1f} ATR — "
                f"продолжения ждать не от чего")
    elif up >= EXHAUST_MIN_UP and rel <= EXHAUST_MAX_RVOL and ch >= 0:
        state = "exhausting"
        note = (f"цена высоко (+{up:.0f}% от дна), объём иссяк "
                f"(×{rel:.1f}) — истощение хода")

    dslope = None
    ctx = (flow or {}).get("context") or {}
    try:
        if ctx.get("delta_slope") is not None:
            dslope = float(ctx["delta_slope"])
    except (TypeError, ValueError):
        dslope = None
    divergence = bool(dslope is not None and dslope < 0
                      and up >= EXHAUST_MIN_UP)

    if state is None and not divergence:
        return None
    out = {"ratio": ratio, "state": state, "note": note}
    if divergence:
        out["divergence"] = True
        div_note = "дельта гаснет на верхах — покупатели выдыхаются"
        out["note"] = f"{note}; {div_note}" if note else div_note
    return out

# ── Тест Вайкоффа: повторный заход к минимуму на МЕНЬШЕМ объёме ──
# Из разбора Вайкоффа (24.08): подтверждение накопления — не сама
# пружина, а ТЕСТ после неё. Цена прокалывает поддержку, возвращается,
# затем идёт повторно к минимуму, но удержать уровень требуется уже
# меньше усилия. Меньше усилия на тот же результат = продавец кончился.
# «Тест важнее самой пружины».
#
# Родня, но не дубль: absorption_from_rows читает удержание ПОСЛЕ
# выноса по давлению (vi), а здесь сравниваются два подхода к одному
# уровню по ОБЪЁМУ. Вайкоффу нужен именно объём, и именно
# относительный: не «фон тихий», а «на тесте тише, чем на проколе».
TEST_NEAR_PCT = 4.0      # «повторно к минимуму» — ближе этого к лою
TEST_VOL_RATIO = 0.7     # объём теста к объёму прокола
TEST_MIN_GAP = 2         # столько баров между проколом и тестом


def wyckoff_test_from_rows(rows: list[dict],
                           near_pct: float = TEST_NEAR_PCT,
                           vol_ratio: float = TEST_VOL_RATIO,
                           min_gap: int = TEST_MIN_GAP) -> dict:
    """Прошла ли монета тест после прокола минимума.

    Читает пульс: price и rvol_1h. Возврат: {"tested", "volRatio",
    "barsAfter", "note"}. tested=False, когда прокола не было, теста
    ещё не случилось или он пришёл на ТАКОМ ЖЕ объёме — последнее
    важнее всего: высокий объём на тесте означает, что предложение
    не иссякло, и вход преждевременен.

    Скор и отбор не трогаются — поле знания.
    """
    out = {"tested": False, "volRatio": None, "barsAfter": None, "note": None}
    px = [r.get("price") for r in rows]
    if len(px) < min_gap + 3 or any(not v for v in px):
        return out
    vols = [r.get("rvol_1h") for r in rows]

    ilow = min(range(len(px)), key=lambda i: px[i])
    low = px[ilow]
    if not low or ilow > len(px) - 1 - min_gap:
        return out                     # минимум только что — теста не было
    v_low = vols[ilow]
    if not v_low or v_low <= 0:
        return out                     # без объёма прокола сравнивать не с чем

    # Между проколом и тестом цена обязана ОТОЙТИ: заход к тому же
    # уровню без возврата — это не тест, а продолжение падения.
    away = max(px[ilow:])
    if not away or (away / low - 1) * 100 < near_pct:
        return out

    for i in range(ilow + min_gap, len(px)):
        if (px[i] / low - 1) * 100 > near_pct:
            continue                   # ещё не вернулись к минимуму
        v = vols[i]
        if not v or v <= 0:
            continue
        ratio = v / v_low
        out["volRatio"] = round(ratio, 2)
        out["barsAfter"] = i - ilow
        if ratio <= vol_ratio:
            out["tested"] = True
            out["note"] = (f"тест пройден: повторный заход к минимуму на "
                           f"объёме {ratio:.0%} от прокола — продавец иссяк")
        else:
            out["note"] = (f"тест НЕ пройден: у минимума объём {ratio:.0%} "
                           f"от прокола — предложение не иссякло, рано")
        return out
    return out


def wyckoff_test_for(symbol: str) -> dict:
    """Тест по текущему пульсу одной монеты."""
    rows = _pulse().get(symbol)
    return wyckoff_test_from_rows(rows if isinstance(rows, list) else [])
