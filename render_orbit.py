"""Орбита · верхний экран дашборда.

Модуль самодостаточен: dashboard.py только вызывает render_orbit()
и вставляет результат в разметку страницы.

Помощники и константы, общие с render_dashboard.py (_pick, _num,
_tick и т.д.),
раньше доставались отложенным (внутрифункционным) импортом прямо
из render_dashboard.py — тот файл импортирует orbit на уровне
модуля, и обратный импорт на уровне модуля дал бы цикл.

Теперь они в render_common.py — третьем модуле без зависимостей ни
от dashboard, ни от orbit — и импортируются здесь на уровне модуля,
как обычно. Ч-8 тех.долга закрыт.
"""
from __future__ import annotations
import json

from core_binance import get_btc_context, get_btc_dominance
from core_config import ORBIT_BG_SRC, LEADERS_PATH, ANOMALY_PATH
from core_models import Candidate, RunSnapshot
from render_theme import esc
from analytics_flow import (
    CASE_RU, big_volume, case_key, case_of, flow_leader, flow_order,
)
from analytics_momentum import (
    star_oi, star_late, star_pulse, star_cycle, star_divergence,
)
# Фон рынка, ряды для графиков и форматирование чисел — из аналитики,
# не из соседнего рендера. Раньше половина этого считалась прямо здесь,
# а сводка забирала результат через window.ORB — глобальную переменную
# в общем документе. В отдельных iframe общего документа нет: каждый
# экран зовёт эти функции сам при сборке своего файла.
from analytics_metrics import (
    LEAD_X1, LEAD_X2, LEAD_X3,
    base_symbol, card_data, fmt_cap, max_vol_ratio,
    leader_chart, market_breadth, vol_chart, weekend_state,
)
from analytics_leaders import journal_summary, read_store
from analytics_permission import altseason_share, market_permission
# Звёзды считаются один раз на два экрана: их показывает и орбита, и
# сводка, а после переезда в отдельные iframe передать готовое между
# документами нечем. Здесь остаётся только раскладка и отрисовка.
from analytics_stars import build_stars
from render_common import (
    _pick, _num, _get, _tick,
    CASE_STRAT, RR_MIN, SURGE_NOTE, IMP_NOTE,
)
from core_config import LEADERS_MAX_AGE_DAYS

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
    order = flow_order(candidates)
    ranked = order[:2]
    lead = ranked[0] if ranked else None
    out.append({
        "id": "flow", "name": "ПОТОК", "val": str(len(order)),
        "c": ORBIT_COLORS["flow"], "w": 0.7, "slice": "strat:flow",
        "note": (f"лидер прогона · {_tick(lead)}") if lead else "кто двигает рынок",
        # Шкала абсолютная, а не от максимума пары: при нормировке
        # по паре первая монета всегда упиралась бы в край и разрыв
        # между «сильной» и «чуть слабее» пропадал.
        "rows": [[_tick(c), str(round(getattr(c, "score", 0) or 0)),
                  min(100, round(getattr(c, "score", 0) or 0)),
                  case_key(case_of(c)) or ""]
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


def _orbit_leaders(candidates: list[Candidate]) -> dict:
    """Лента тикеров. Источники и пороги те же, что у _blk_leaders,
    иначе одна и та же монета была бы золотой внизу и серой на орбите.

    Узел не ведёт в панель: своего среза у этой ленты нет. Зато каждый
    тикер несёт data-coin и открывает карточку монеты — как в .lead-list.
    """
    flow_j = read_store(LEADERS_PATH)
    vol_j = read_store(ANOMALY_PATH)
    flow_syms = [k for k in flow_j if not k.startswith("_")]
    vol_syms = [k for k in vol_j if not k.startswith("_")]

    ranked: dict[str, float] = {}
    for sym in flow_syms:
        ranked[sym] = max_vol_ratio(flow_j.get(sym) or {})
    for sym in vol_syms:
        ranked.setdefault(sym, max_vol_ratio(vol_j.get(sym) or {}))

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
        lst.append([base_symbol(sym), tier(ranked[sym]),
                    (c.symbol if c is not None else "")])

    return {
        "id": "lead", "name": "ЛИДЕРЫ", "val": str(len(ranked)),
        "c": ORBIT_COLORS["lead"], "w": 0.9, "slice": "",
        "note": "топ flow + аномальный объём", "list": lst,
    }



def _orbit_dormant(candidates: list[Candidate],
                   leader: Candidate | None) -> list[dict]:
    """Монеты в спячке — для строки «Спят» в сводке.

    Единственное состояние ДО движения, и источник у него — кандидаты
    текущего прогона, а не журнал: в журнал попадают лидеры, а спячка
    по определению случается раньше лидерства. Лидер прогона
    исключается — если он сам dormant, его блок выше уже сообщил
    и имя, и фигуру, вторая строка сказала бы то же самое дважды.
    """
    lead_sym = leader.symbol if leader is not None else ""
    out = []
    for c in candidates:
        f = c.flow or {}
        if (f.get("case") or "") != "flow_dormant" or c.symbol == lead_sym:
            continue
        out.append({
            "t": _tick(c),
            "cap": fmt_cap(card_data(c)["cap"]),
            "score": int(getattr(c, "score", 0) or 0),
        })
    out.sort(key=lambda d: -d["score"])
    return out[:3]


def orbit_market(candidates: list[Candidate], snapshot: RunSnapshot,
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
    reg = getattr(snapshot, "market_regime", None) or {}
    _btc = get_btc_context()
    _breadth = market_breadth(candidates)
    # Один вызов на обе величины: плашка на орбите берёт из него имя
    # и кратность, брифинг — тот же расчёт плюс ряд для графика.
    # Раздельные вызовы позволили бы лидеру объёма разойтись между
    # двумя местами экрана.
    _vol = vol_chart(candidates)

    label = str(reg.get("label", "risk-off"))
    try:
        appetite = int(reg.get("appetite", 0) or 0)
    except (TypeError, ValueError):
        appetite = 0

    src = getattr(snapshot, "sectors", None) or []
    top = sorted(
        [(str(_get(r, "sector", "") or ""), float(_get(r, "avg_change_24h", 0) or 0))
         for r in src], key=lambda p: -p[1])[:1]

    leader = flow_leader(candidates)

    def top3(sid: str) -> list[dict]:
        items = sorted(_pick(slices, sid)["items"],
                       key=lambda c: -_num(c, "rvol_1h"))[:3]
        return [{"t": _tick(c), "x": round(_num(c, "rvol_1h"), 1),
                 "cap": fmt_cap(card_data(c)["cap"])} for c in items]

    hourly_items = _pick(slices, "hourly")["items"]

    return {
        # Момент самого прогона, а не момент открытия страницы браузером.
        # Раньше этого поля не было вовсе ни под каким именем, и брифинг
        # был вынужден брать new Date() в JS — честная замена мёртвому
        # полю, а не опечатка в имени.
        "ts": str(getattr(snapshot, "timestamp", "") or ""),
        # «спокойный» и «осторожный» — пересказ режима, а не прогноз
        "calm": label.upper().replace("-", "").startswith("RISKON"),
        "appetite": f"{appetite}/5",
        # Биткоин: отдельный запрос, в выборку он не входит (MAJOR_TOKENS).
        # Пустой словарь от загрузчика означает «данных нет», и поля
        # честно остаются None — сводка покажет «—», а не ноль.
        "btc": _btc.get("ch_24h"),
        "btcUp": (_btc.get("ch_24h") or 0) >= 0,
        "btc7d": _btc.get("ch_7d"),

        # Р-1 минимальным составом и Р-19 на коротких окнах. Лежат в
        # словаре рынка, а не отдельным каналом: словарь и так едет во
        # все три экрана, и строка разрешения обязана быть одной и той
        # же на брифе, орбите и в зале.
        "permission": market_permission(candidates, _btc),
        "altShare": altseason_share(candidates, _btc),

        # Палитра стадий и срок журнала — В ДАННЫХ, а не в JS каждого
        # экрана. Хендофф записал замену зашитых «14» через ORB.maxAge;
        # ORB умер при переезде на отдельные документы, и подпись «из
        # 14 дней» в зале врала при сроке 26. Теперь канал — словарь
        # рынка: он и так едет во все экраны.
        "strat": CASE_STRAT,
        "maxAge": LEADERS_MAX_AGE_DAYS,
        # Ч-9 тех.долга закрыт: раньше здесь была константа-заглушка.
        "dom": get_btc_dominance(),
        "series": _btc.get("spark") or [],

        # Замирание рынка и положение относительно выходных.
        # Оба — состояние фона, а не оценка монеты, и место им здесь,
        # рядом с режимом.
        "frozen": _breadth["frozen"],
        "maxChange": _breadth["maxChange"],
        "tail": _breadth["tail"],
        "tailPct": _breadth.get("tailPct"),
        "weekend": weekend_state(),
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
        "leaderChart": leader_chart(leader),
        "leader": ({"t": _tick(leader),
                    "score": round(getattr(leader, "score", 0) or 0),
                    "case": case_key(case_of(leader)) or "—",
                    "cap": fmt_cap(card_data(leader)["cap"])} if leader else {}),
        "topVol": top3("surge"),
        "hourly": {"n": len(hourly_items), "list": top3("hourly")},
        "flowVol": big_volume(candidates),
        # Спячка и итог журнала — читает только сводка при входе.
        # Спячка идёт из кандидатов (до лидерства журнала не бывает),
        # итог журнала — агрегат по файлу, не поле записи.
        "dormant": _orbit_dormant(candidates, leader),
        "journal": journal_summary(),
    }



def render_orbit(candidates: list[Candidate], snapshot: RunSnapshot,
                 slices: list[dict], market: dict,
                 stars: list[dict]) -> str:
    """Разметка и данные орбиты.

    Строка рынка и звёзды приходят готовыми, а не считаются здесь.
    Их показывают три экрана, и собирает их один раз render_page:
    иначе три независимых прохода по выборке и три возможности
    разойтись — а расхождение здесь уже случалось (см. комментарий про
    PUMP ON над строкой «рынок замер» ниже).
    """
    nodes = _orbit_nodes(candidates, snapshot, slices)

    # Данные уходят отдельным <script type="application/json">, а не
    # склеиваются в разметку: экранировать нужно только "<".
    # Словарь рынка приходит аргументом и читается двумя местами — JSON
    # ниже и подстановки в разметку. Прежде он собирался прямо внутри
    # json.dumps, и разметка не имела к нему доступа вовсе: орбита
    # показывала PUMP ON над строкой «рынок замер» в брифинге.

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
    reg = getattr(snapshot, "market_regime", None) or {}
    regime = esc(str(reg.get("label", "RISK-OFF")).upper())
    try:
        appetite = esc(f'{int(reg.get("appetite", 0) or 0)}/5')
    except (TypeError, ValueError):
        appetite = esc("—")
    _dom = market.get("dom")
    btc_d = esc(f"{_dom:.0f}%" if _dom is not None else "—")
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

    # Р-1: предупреждения разрешения рынка — те же пилюли, тот же ряд.
    # Выходные НЕ дублируются: их пилюля уже стоит выше, и правило
    # одно — у каждой причины ровно одно место на экране. Отсюда
    # добавляются только рывок биткоина и перекос фандинга.
    _perm = (_mk.get("permission") or {}).get("parts") or {}
    if (_perm.get("btc") or {}).get("warn"):
        _pills.append('<span class="ob-frost-t">рывок btc · окно каскада</span>')
    if (_perm.get("funding") or {}).get("warn"):
        _pills.append('<span class="ob-frost-t">толпа в лонге · фандинг+</span>')
    elif (_perm.get("funding") or {}).get("side") == "short":
        # Не предупреждение — состояние заряда. Пилюля календарного
        # тона (как выходные), а не тревожного: топливо вверх.
        _pills.append('<span class="ob-frost-w">толпа в шорте · заряд вверх</span>')
    if (_perm.get("oi") or {}).get("warn"):
        _pills.append('<span class="ob-frost-t">OI раздут · топливо каскада</span>')
    _cal = (_perm.get("calendar") or {}).get("items") or []
    if _cal:
        _it = _cal[0]
        _when = ("идёт" if _it["running"] else
                 "сегодня" if _it["days"] == 0 else
                 "завтра" if _it["days"] == 1 else f"через {_it['days']} дн")
        # Тон по знаку: риск и разлок тревожным классом, поддержка и
        # фон — календарным. Событие показывается ОДНО: частокол в
        # оверлее превратился бы в ленту новостей.
        _cls = ("ob-frost-t" if _it["kind"] in ("risk", "unlock")
                else "ob-frost-w")
        _pills.append(f'<span class="{_cls}">{_it["title"]} · {_when}</span>')
    if (_perm.get("cascade") or {}).get("warn"):
        _pills.append('<span class="ob-frost-t">каскад идёт · движок закрывает счета</span>')
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

    # Р-19: доля выборки, обошедшая биткоин. Окно — в подписи (7д),
    # и с публичным 90-дневным индексом это число несравнимо, см.
    # техдолг. Нет данных — нет ячейки: прочерк на месте величины,
    # которой не бывает, читается как поломка.
    _as = _mk.get("altShare") or {}
    alt_cell = (f' · альты&gt;btc <b>{_as["d7"]}%</b> за 7д'
                if _as.get("d7") is not None else "")

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
      <b class="{btc7_cls}">{btc7_txt}</b> · btc.d <b>{btc_d}</b>{alt_cell}</div>

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
  /* Дерево фаз БОЛЬШЕ ЗДЕСЬ НЕ СЧИТАЕТСЯ. Правило и его пороги живут
     в analytics_stars.star_phase(), результат приезжает готовым в
     самой звезде. Здесь остался только доступ — чтобы места вызова
     не менялись и чтобы наружу по-прежнему отдавалась функция, а не
     сырое поле.

     Почему так, а не оставить порог в JS: тот же порог был выписан
     ещё и в сводке, которая брала эту функцию через window.ORB. Два
     документа, одно правило — при первой правке они разъезжаются
     молча. Заодно расчёт возвращается туда, где до него дотягивается
     проба: в браузере его не проверить ничем. */
  function phase(s) {
    return s.phase || { a: '', k: 'wait' };
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

  /* Тоже посчитано в питоне (analytics_stars.stop_pct) и приезжает
     полем stopPct. Функция сохранена ради мест вызова и ради сводки,
     которая ждёт снаружи именно функцию. */
  function toStop(s) {
    return s.stopPct || 0;
  }

  /* Риск не заменяет действие, а стоит рядом: подмена вывода была бы
     решением за человека, а пометка оставляет выбор ему. */
  function act(s) {
    var p = phase(s), risks = [];
    if (s.firstRun) risks.push('первый разгон');
    if (s.topBubble) risks.push('пузырь на вершине');
    if (s.oiState === 'held') risks.push('плечо не проверено');
    if (s.late) risks.push('фигура уже отыграна');
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

    var p = phase(s), risks = [];
    if (s.firstRun) risks.push('первый разгон');
    if (s.topBubble) risks.push('пузырь на вершине');
    // Плечо не проверено (GPS перед обвалом) / фигура уже отыграна —
    // те же поля, что уже показывают подвал карточки и зал.
    if (s.oiState === 'held') risks.push('плечо не проверено');
    if (s.late) risks.push('фигура уже отыграна');

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
          /* Н-7 тех.долга: FDV/капитализация — число, не вердикт.
             Величина двусторонняя (малый флоат = и потенциал хода, и
             риск на разлоке, см. Н-5), поэтому без «хорошо/плохо» —
             решает человек. Поля нет вовсе, если не измерено (Н-7,
             star_card), а не ноль или прочерк. */
          (s.fdv
            ? '<span class="ob-sc-tag">FDV/кап <u>×' + s.fdv + '</u></span>'
            : '') +
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
        /* Полоса жизни — из s.f, свежести, посчитанной аналитикой
           (1 − возраст/окно). Прежний пересчёт «(14 − days)/14» дублировал
           STAR_WINDOW_DAYS литералом и разошёлся бы молча при смене окна. */
        '<div class="ob-sc-life"><u style="width:' +
          Math.round((s.f || 0) * 100) + '%"></u></div>' +
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
  /* Таблица приходит с данными (render_common.CASE_STRAT); встроенная
     копия — запасная и обязана совпадать со словарём в Python. */
  var STRAT = (DATA.market && DATA.market.strat) || {
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




  /* window.ORB отсюда УБРАН. Он был мостом к сводке, пока та жила в
     этом же документе; теперь у сводки свой, и общего окна между
     ними не существует — переменная не могла бы до неё доехать и
     осталась бы просто мусором в глобальной области. */

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
