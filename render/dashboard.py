"""Дашборд как единственный экран отчёта · вёрстка по макету SLEEPING ALTS.

Плашки кликабельны: каждая открывает таблицу своего среза, строка таблицы —
модалку с полной карточкой монеты.

ЭТАП: вёрстка. Часть значений — статика по макету, источники и TODO
расписаны в комментариях к каждому блоку.
"""

from __future__ import annotations

from core.models import Candidate, RunSnapshot
from render.card import render_card
from render.table import render_slice_pane
from render.theme import esc
from render.flow_report import case_key, render_flow_report

# ─────────────────────────────────────────────────────────────
# Хелперы
# ─────────────────────────────────────────────────────────────
def _num(c: Candidate, key: str, default: float = 0.0) -> float:
    try:
        return float((c.raw or {}).get(key) or default)
    except (TypeError, ValueError):
        return default


def _get(obj, key: str, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _actionable(c: Candidate) -> bool:
    lv = getattr(c.strategy, "levels", None)
    return bool(lv and getattr(lv, "entry", 0) > 0)


def _tradable(c: Candidate) -> bool:
    return bool(getattr(c, "tradable", False))


def _tick(c: Candidate) -> str:
    return esc(c.symbol.replace("USDT", ""))


def _pick(slices: list[dict], sid: str) -> dict:
    for s in slices:
        if s["id"] == sid:
            return s
    return {"id": sid, "label": sid, "note": "", "items": []}


def _price(v: float) -> str:
    if not v:
        return "—"
    return f"{v:.4f}" if v < 100 else f"{v:,.2f}".replace(",", " ")


def _arc(pct: float, r: float) -> str:
    """dasharray для кольца: длина дуги и остаток."""
    circ = 2 * 3.14159265 * r
    on = circ * max(0.0, min(100.0, pct)) / 100
    return f"{on:.2f} {circ - on:.2f}"


def _spark(values: list[float], w: float = 236.0,
           h: float = 48.0, pad: float = 6.0) -> tuple[str, float, float]:
    """Точки для линии с АВТОМАСШТАБОМ по фактическому диапазону.

    Раньше ось строилась по score с жёсткой шкалой 0..100: реальный разброс
    (напр. 57..62) давал 2px амплитуды, и линия выглядела прямой. Теперь
    минимум серии прижимается к низу, максимум — к верху, поэтому любой
    разброс раскрывается на всю высоту блока.

    Возвращает (points, x последней точки, y последней точки).
    """
    n = len(values)
    if n == 0:
        return "", w, h / 2
    if n == 1:
        y = h / 2
        return f"0,{y:.1f} {w:.0f},{y:.1f}", w, y

    lo, hi = min(values), max(values)
    span = hi - lo
    top, bottom = pad, h - pad
    step = w / (n - 1)

    pts = []
    for i, v in enumerate(values):
        # нулевой разброс — ровная линия по центру, это честное "нет данных"
        k = 0.5 if span < 1e-9 else (v - lo) / span
        y = bottom - k * (bottom - top)
        pts.append((i * step, y))

    coords = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    return coords, pts[-1][0], pts[-1][1]


# Срезы, которые больше НЕ выводятся плашками на первом экране.
# Код и таблицы сохранены: их числа уходят в узлы воронки,
# а клик по узлу открывает соответствующую панель.
HIDDEN_TILES = {"all", "planned"}


# ─────────────────────────────────────────────────────────────
# Отбор срезов
# ─────────────────────────────────────────────────────────────
def build_slices(candidates: list[Candidate], snapshot: RunSnapshot) -> list[dict]:
    """Срезы дашборда. Каждый становится блоком и таблицей."""

    # =====================================================================
    # ОБЪЁМЫ · вёрстка по новому дизайну, данные пока статикой.
    # TODO: добавить функционал из прошлой реализации (блок surge):
    #   · крупное число — количество монет, прошедших порог
    #   · порог в подписи: было ≥3×, теперь ≥4× — согласовать с детектором.
    #     Сам порог живёт в детекторе, здесь только флаг c.surge
    #   · выноска "> ×4" и подпись "на дневке" — сейчас константы
    #     (SURGE_MULT / SURGE_TF), в макете на их месте было "×2.3"
    #     и "к вчерашнему дню"
    #   · линейный график — СТРОИТСЯ ПО rvol_1h среза с автомасштабом.
    #     Настоящей истории объёма нет, это распределение по монетам,
    #     а не временной ряд. Когда появится история — заменить values
    #     в _blk_volume на неё, _spark менять не нужно
    #   · ТРИ МОНЕТЫ ПОД ГРАФИКОМ = ТОП-3 из таблицы прошлой реализации
    #     (сортировка по множителю объёма, формат "тикер ×N.N")
    # =====================================================================
    surge = [c for c in candidates if c.surge]

    # =====================================================================
    # СОЦСЕТИ · ВСПЛЕСК ВНИМАНИЯ
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `viral`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · число в центре кольца — количество монет в срезе `viral`
    #   · заполнение кольца — доля/прогресс, источник не определён,
    #     в старой реализации такого индикатора не было
    #   · подпись "hot N · warm N" — разбивка по уровням внимания,
    #     сейчас константа SOC_SUB
    #   · пилюля внизу ("pepe ×9.2") — ЛИДЕР СПИСКА из таблицы прошлой
    #     реализации: первая строка по множителю упоминаний
    #
    # Клик по блоку ведёт в таблицу этого среза (общее правило дашборда).
    # Старый код `viral` не трогаем и не удаляем.
    # =====================================================================
    viral = [c for c in candidates if c.is_viral]

    # =====================================================================
    # ПАТТЕРНЫ · 4 СТРОКИ
    # Вёрстка по новому дизайну. ФУНКЦИОНАЛ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ.
    #
    # СОСТАВ СТРОК (порядок сверху вниз) и источники:
    #   1) taiko   ← срез `taiko` (HTF reversal)      — данные есть
    #   2) dexe    ← срез `dexe`  (post-pump)         — данные есть
    #   3) strong  ← бывш. "база",  (high-confidence) — ПЕРЕИМЕНОВАНО
    #   4) good    ← бывш. "vortex",(tradable setups) — ПЕРЕИМЕНОВАНО
    #
    # ВАЖНО ПО ПЕРЕИМЕНОВАНИЮ:
    #   меняются ТОЛЬКО подписи в вёрстке. Строка "база" теперь выводит
    #   счётчик strong, строка "vortex" — счётчик good; оба берутся из
    #   прошлой реализации (плашки STRONG / GOOD старого отчёта).
    #   Отдельного детектора vortex по-прежнему нет.
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · число справа в каждой строке — счётчик соответствующего среза
    #   · заполнение шкалы — доля строки от суммы всех четырёх
    #   · "N сигнал" в заголовке — сумма четырёх счётчиков
    #   · цвет шкалы и числа закреплён за строкой (p-taiko … p-good),
    #     из макета, не меняем
    #   · СТРОКА `good` пока без источника: детектора нет, срез пустой,
    #     поэтому строка гасится классом `off`
    #
    # Подпись "после фильтра качества базы" — ОСТАВЛЯЕМ КАК ЕСТЬ, константа.
    # Клик по строке ведёт в таблицу соответствующего среза.
    # Старый код срезов не трогаем и не удаляем.
    # =====================================================================
    taiko = [c for c in candidates if c.taiko]
    dexe = [c for c in candidates if c.dexe]
    strong = [c for c in candidates if (c.phase or {}).get("num", 0) == 2]
    good: list[Candidate] = []

    # =====================================================================
    # РИСК · ПОД ВЕТО
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `vetoed`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · крупное число + подпись "монет" — размер среза `vetoed`
    #   · разбивка внизу: squeeze / фандинг / ликвид. — счётчики по
    #     причинам вето; сумма причин может быть больше общего числа
    #     (у монеты бывает несколько вето). Сейчас RISK_LEGS — константы
    #   · боковые дуги слева/справа (squeeze, фандинг) — индикаторы
    #     давления по этим причинам, шкала из макета, пока статика
    #   · эллиптическая орбита и точка на ней — декор, данными не управляется
    #
    # КАПСУЛА НАД БЛОКОМ:
    #   "13% · доля выборки" — доля отсеянных вето от общего числа
    #   просканированных монет. Считается от len(candidates).
    #
    # Клик по блоку ведёт в таблицу этого среза.
    # Старый код `vetoed` не трогаем и не удаляем.
    # =====================================================================
    vetoed = [c for c in candidates if c.vetoed]

    # =====================================================================
    # СЕТАПЫ
    # Вёрстка по новому дизайну. ФУНКЦИОНАЛ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (`setups`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · заголовок "сетапы N из M · r:r ≥ K" — N: размер среза,
    #     M: общее число просканированных, K: порог (константа RR_MIN)
    #   · список строк — ТОП-3 по rr из таблицы прошлой реализации
    #   · в строке: тикер, подпись "паттерн · объём ×N.N", кольцо,
    #     значение "1:X.X", справа "вход 0.XXXX"
    #   · заполнение кольца — нормировка rr по максимуму в списке
    #   · цвет кольца и значения: зелёный при rr ≥ 3, иначе янтарный
    #     (порог RR_GOOD, из макета)
    #
    # Клик по строке ведёт в модалку монеты, клик по заголовку — в таблицу.
    # Старый код `setups` не трогаем и не удаляем.
    # =====================================================================
    setups = [c for c in candidates if _tradable(c)]

    # =====================================================================
    # ИМПУЛЬС ЗА ЧАС
    # Вёрстка по новому дизайну. ФУНКЦИОНАЛ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (`hourly`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · крупная цифра — количество монет в срезе `hourly`
    #   · подпись под цифрой — порог детектора (константа IMP_NOTE)
    #   · гистограмма из 7 столбцов — распределение по последним часам,
    #     подсвеченный столбец = пик.
    #     ВНИМАНИЕ: почасовой истории в прошлой реализации НЕТ,
    #     источник нужно определить отдельно. Пока IMP_BARS / IMP_PEAK —
    #     константы по макету; при пустом срезе гистограмма гасится
    #     классом `dim`, чтобы декор не спорил с нулём
    #   · нижняя подпись "пик был N часа назад" — из той же истории
    #
    # Клик по блоку ведёт в таблицу этого среза.
    # Старый код `hourly` не трогаем и не удаляем.
    # =====================================================================
    hourly = [c for c in candidates if _num(c, "rvol_1h") >= 3.0]

    # =====================================================================
    # ЕСТЬ ПЛАН · СКРЫТЫЙ СРЕЗ
    # Отдельным блоком на первом экране НЕ выводится (HIDDEN_TILES).
    # Число переехало в узел воронки, таблица среза сохранена
    # и открывается кликом по этому узлу.
    # Код детектора не трогаем и не удаляем.
    # =====================================================================
    planned = [c for c in candidates if _actionable(c)]

    return [
        {"id": "all", "label": "ВСЯ ВЫБОРКА",
         "note": "все монеты прогона, без фильтров", "items": list(candidates)},
        {"id": "surge", "label": "ОБЪЁМЫ АНОМАЛЬНЫЕ",
         "note": "против среднего за 30 дней", "items": surge},
        {"id": "viral", "label": "ВСПЛЕСК ВНИМАНИЯ",
         "note": "внимание и объём вместе", "items": viral},
        {"id": "taiko", "label": "TAIKO",
         "note": "разворот на старшем ТФ", "items": taiko},
        {"id": "dexe", "label": "DEXE",
         "note": "отскок после дампа", "items": dexe},
        {"id": "strong", "label": "STRONG",
         "note": "накопление, фаза 2", "items": strong},
        {"id": "good", "label": "GOOD",
         "note": "рабочие сетапы", "items": good},
        {"id": "setups", "label": "СЕТАПЫ К РАБОТЕ",
         "note": "R:R подтверждён, вето пройдено", "items": setups},
        {"id": "hourly", "label": "ИМПУЛЬС ЗА ЧАС",
         "note": "RVOL 1H ≥ 3", "items": hourly},
        {"id": "planned", "label": "ЕСТЬ ПЛАН",
         "note": "уровни построены", "items": planned},
        {"id": "vetoed", "label": "ПОД ВЕТО",
         "note": "отсеяны фильтром риска", "items": vetoed},
    ]


# ═════════════════════════════════════════════════════════════
# КОНСТАНТЫ ВЁРСТКИ · всё, что пока не приходит из данных
# ═════════════════════════════════════════════════════════════
TITLE = "SLEEPING ALTS"
SURGE_NOTE = "монет · surge ≥ 4×"        # было "surge ≥ 3×"
SURGE_MULT = "&gt; ×4"                    # было "×2.3"
SURGE_TF = "на дневке"                    # было "к вчерашнему дню"
SOC_SUB = "hot 3 · warm 4"
PAT_FOOT = "после фильтра качества базы"
RR_MIN = "2"
RR_GOOD = 3.0                             # порог зелёного кольца в сетапах
IMP_NOTE = "rvol ≥ 2.2× сейчас"
IMP_BARS = [18, 26, 36, 48, 30, 16, 10]
IMP_PEAK = 3
IMP_FOOT = "пик был 2 часа назад"
IMP_EMPTY = "импульса в этом прогоне нет"
RISK_LEGS = [("squeeze", 9, "ru"), ("фандинг", 6, "gl"), ("ликвид.", 8, "st")]
BTC_D = "58%"
FN_FOOT_R = "медиана от ath −71% · rvol 0.7×"

FUNNEL_FALLBACK = [
    ("вся выборка", 176, "all"),
    ("прошли объём", 58, None),
    ("структура ок", 41, None),
    ("после вето", 18, "vetoed"),
    ("r:r ≥ 2", 11, "planned"),
    ("к работе", 6, "setups"),
]
SECTOR_FALLBACK = [("ai", 12.4), ("gamefi", 4.1), ("meme", -3.8),
                   ("defi", -7.2), ("l1/l2", -8.0)]

FN_TONE = ["#C8DCE8", "#F5A623", "#D9B84A", "#C4703A", "#8FA0B0", "#4FCF8A"]

ICONS = {
    "vol": '<path d="M-9 6 L-3 -2 L2 3 L9 -8" fill="none" stroke="#FFD98A" '
           'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>',
    "soc": '<path d="M-8 -5 h16 v10 h-9 l-4 4 v-4 h-3 z" fill="none" '
           'stroke="#BFE4FF" stroke-width="1.8" stroke-linejoin="round"/>',
    "pat": '<path d="M-8 6 v-8 M-2 6 v-12 M4 6 v-6 M10 6 v-10" fill="none" '
           'stroke="#FFEFB0" stroke-width="2" stroke-linecap="round"/>',
    "set": '<path d="M-8 4 L-2 -4 L4 1 L9 -6 M9 -6 h-5 M9 -6 v5" fill="none" '
           'stroke="#A8F0C8" stroke-width="1.8" stroke-linecap="round" '
           'stroke-linejoin="round"/>',
    "imp": '<path d="M1 -9 L-7 2 h6 l-2 8 L7 -1 h-6 z" fill="none" '
           'stroke="#FFD98A" stroke-width="1.8" stroke-linejoin="round"/>',
    "sec": '<path d="M-8 5 h16 M-8 5 v-4 M-3 5 v-8 M2 5 v-11 M7 5 v-6" fill="none" '
           'stroke="#D8C0F8" stroke-width="1.8" stroke-linecap="round"/>',
}


def _icon(key: str) -> str:
    return (f'<span class="b-ic"><svg viewBox="-13 -13 26 26">{ICONS[key]}</svg></span>')


def _title(main: str, sub: str) -> str:
    return f'<div class="b-t">{esc(main)} <span>{esc(sub)}</span></div>'


# ─────────────────────────────────────────────────────────────
# Фон
# ─────────────────────────────────────────────────────────────
def _bg() -> str:
    return """
<div class="bg">
  <svg viewBox="0 0 1200 810" preserveAspectRatio="xMidYMid slice">
    <g stroke="#15151b" fill="none" stroke-width="1">
      <circle cx="1080" cy="140" r="200"/>
      <circle cx="1080" cy="140" r="290"/>
      <circle cx="140" cy="700" r="240"/>
    </g>
  </svg>
</div>"""


# ─────────────────────────────────────────────────────────────
# Шапка
# ─────────────────────────────────────────────────────────────
def _head(snapshot: RunSnapshot) -> str:
    # =====================================================================
    # КАПСУЛА РЕЖИМА · статика по макету.
    # Источник — snapshot.market_regime (dict: label / appetite / text).
    # Любое поле может отсутствовать, всё через .get с дефолтом.
    #
    # ЧТО УЧЕСТЬ ПРИ ПОДКЛЮЧЕНИИ:
    #   1) label выводится как есть в верхнем регистре (RISK-OFF).
    #      Цвет в макете единый, отдельного класса под метку не нужно
    #   2) шкала аппетита — 5 сегментов, знаменатель захардкожен
    #   3) text (длинное пояснение) в капсулу не помещается: тултип
    #      или отдельная строка — решить отдельно
    #   4) BTC.D в market_regime НЕТ, источник предстоит найти.
    #      Сейчас константа BTC_D
    # =====================================================================
    reg = getattr(snapshot, "market_regime", None) or {}
    label = str(reg.get("label", "risk-off")).upper()
    try:
        appetite = int(reg.get("appetite", 2) or 0)
    except (TypeError, ValueError):
        appetite = 0
    ts = str(getattr(snapshot, "generated_at", "") or "")

    dots = "".join(
        f'<i class="{"on" if i < appetite else ""}"></i>' for i in range(5)
    )
    ring = _arc(appetite / 5 * 100, 12)

    return f"""
<div class="hd">
  <div>
    <h1 class="hd-t">{esc(TITLE)}</h1>
    <div class="hd-d">{esc(ts)}</div>
  </div>
  <div class="cap">
    <svg width="30" height="30" viewBox="-15 -15 30 30">
      <circle r="12" fill="none" stroke="#252c33" stroke-width="3"/>
      <circle r="12" fill="none" stroke="#D8E4EE" stroke-width="3"
              stroke-linecap="round" stroke-dasharray="{ring}"
              transform="rotate(-90)"/>
      <circle r="3" fill="#D8E4EE"/>
    </svg>
    <div>
      <div class="cap-k">режим рынка</div>
      <div class="cap-v">{esc(label)}</div>
    </div>
    <div class="cap-g">
      <span class="cap-dots">{dots}</span>
      <span class="cap-ap">аппетит {appetite}/5</span>
    </div>
    <div class="cap-btc">
      <span class="cap-k">btc.d</span>
      <b>{BTC_D}</b>
    </div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · объёмы
# ─────────────────────────────────────────────────────────────
def _blk_volume(s: dict) -> str:
    items = s["items"]

    # ГРАФИК. Ось Y — множитель объёма (rvol_1h), НЕ score: score почти
    # не разбросан внутри среза и давал визуально прямую линию.
    # Точки идут по возрастанию, поэтому маркер на конце = лидер по объёму.
    # Дублирование хвоста убрано: сколько монет, столько и точек.
    chart = sorted(items, key=lambda c: _num(c, "rvol_1h"))
    values = [_num(c, "rvol_1h") for c in chart]
    coords, last_x, last_y = _spark(values)

    # ТОП-3 по объёму, но выводим по ВОЗРАСТАНИЮ — чтобы порядок слева направо
    # совпадал с направлением линии над легендой (лидер под маркером справа).
    lead = sorted(items, key=lambda c: -_num(c, "rvol_1h"))[:3][::-1]
    legend = "".join(
        f'<span>{_tick(c)} ×{_num(c, "rvol_1h"):.1f}</span>' for c in lead
    ) or '<span>нет данных</span>'

    flat = len(values) < 2
    line = "" if not coords else (
        f'<polygon points="{coords} 236,52 0,52" fill="url(#vf)"/>'
        f'<polyline points="{coords}" fill="none" stroke="#F5A623" '
        f'stroke-width="1.4" vector-effect="non-scaling-stroke"/>'
        f'<circle cx="{last_x:.0f}" cy="{last_y:.0f}" r="2.5" fill="#FFE0A0"/>'
    )
    cls = "b c-am g-vol" + ("" if items else " empty")

    return f"""
<div class="{cls}" data-slice="{esc(s['id'])}">
  <span class="halo"></span>
  <div class="b-in">
    <div class="vol-call"><b>{SURGE_MULT}</b><i>{SURGE_TF}</i></div>
    <svg class="vol-hook" viewBox="0 0 52 32" fill="none">
      <path d="M50 4 H20 a10 10 0 0 0 -10 10 v10" stroke="#26262e"/>
      <path d="M6 22 l4 6 l4 -6" stroke="#F5A623" stroke-width="1.2"
            stroke-linecap="round"/>
    </svg>
    {_icon('vol')}
    {_title('объёмы', 'аномальные')}
    <span class="big">{len(items)}</span>
    <span class="big-u">{SURGE_NOTE}</span>
    <div class="vol-chart{' dim' if flat else ''}">
      <svg viewBox="0 0 236 52" preserveAspectRatio="none">
        <defs>
          <linearGradient id="vf" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stop-color="#F5A623" stop-opacity="0"/>
            <stop offset="1" stop-color="#F5A623" stop-opacity=".22"/>
          </linearGradient>
        </defs>
        {line}
      </svg>
    </div>
    <div class="hr"></div>
    <div class="vol-legend">{legend}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · соцсети
# ─────────────────────────────────────────────────────────────
def _blk_social(s: dict, total: int) -> str:
    items = s["items"]
    pct = min(100, round(len(items) / total * 100)) if total >= 10 else 0
    lead = max(items, key=lambda c: c.score, default=None)
    pill_txt = (f'{_tick(lead)} ×{max(_num(lead, "rvol_1h"), 2.0):.1f}'
                if lead is not None else "нет всплесков")
    # пустой срез: карточка гаснет, чтобы нулевое кольцо не читалось как дыра
    cls = "b b-card c-bl g-soc" + ("" if items else " empty")

    return f"""
<div class="{cls}" data-slice="{esc(s['id'])}">
  <span class="halo"></span>
  <div class="b-in">
    {_icon('soc')}
    {_title('соцсети', 'всплеск')}
    <svg class="dial" viewBox="-32 -32 64 64">
      <circle r="28" fill="none" stroke="#1d2127" stroke-width="5"/>
      <circle r="28" fill="none" stroke="#3E9BE0" stroke-width="5"
              stroke-linecap="round" stroke-dasharray="{_arc(pct, 28)}"
              transform="rotate(-90)"/>
      <text class="dial-v" y="9" text-anchor="middle">{len(items)}</text>
    </svg>
    <div class="soc-sub">{SOC_SUB}</div>
    <div class="pill"><i></i><b>{pill_txt}</b></div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · паттерны
# ─────────────────────────────────────────────────────────────
def _blk_patterns(slices: list[dict]) -> str:
    src = [("taiko", "taiko", "p-taiko"),
           ("dexe", "dexe", "p-dexe"),
           ("strong", "strong", "p-strong"),
           ("good", "good", "p-good")]
    data = [(lbl, cls, _pick(slices, sid)) for sid, lbl, cls in src]
    total = sum(len(d[2]["items"]) for d in data)
    peak = max((len(d[2]["items"]) for d in data), default=0) or 1

    # строка без данных гасится: пустая шкала иначе читается как баг вёрстки
    rows = "".join(
        f'<div class="brow {cls}{"" if sl["items"] else " off"}" '
        f'data-slice="{esc(sl["id"])}">'
        f'<span class="brow-n">{esc(lbl)}</span>'
        f'<span class="brow-t"><i style="width:{len(sl["items"]) / peak * 100:.0f}%"></i></span>'
        f'<span class="brow-v">{len(sl["items"])}</span></div>'
        for lbl, cls, sl in data
    )

    return f"""
<div class="b c-gd g-pat">
  <span class="halo"></span>
  <div class="b-in">
    {_icon('pat')}
    {_title('паттерны', f'{total} сигнал')}
    <div class="rows">{rows}</div>
    <div class="hr"></div>
    <div class="note">{PAT_FOOT}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · риск
# ─────────────────────────────────────────────────────────────
def _blk_risk(s: dict, total: int) -> str:
    items = s["items"]
    share = round(len(items) / total * 100) if total else 0
    legs = "".join(
        f'<span>{esc(k)}<b class="{tone}">{n}</b></span>'
        for k, n, tone in RISK_LEGS
    )

    return f"""
<div class="b b-glass g-pool c-wh g-risk" data-slice="{esc(s['id'])}">
  <span class="halo"></span>
  <div class="b-in">
    <div class="risk-cap">
      <span><b>{share}<i>%</i></b><s>доля выборки</s></span>
      <svg viewBox="0 0 14 8" fill="none">
        <path d="M0 4 h12 m-4 -3.5 l4 3.5 l-4 3.5" stroke="#C8DCE8"
              stroke-opacity=".45" stroke-linecap="round"
              stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="b-t wide">риск · под вето</div>
    <div class="risk-arc l">
      <svg viewBox="0 0 34 78" fill="none">
        <path d="M26 8 q-13 31 0 62" stroke="#C4703A" stroke-opacity=".5"
              stroke-width="1.4" stroke-linecap="round"/>
        <path d="M16 16 q-9 23 0 46" stroke="#C4703A" stroke-opacity=".22"
              stroke-linecap="round"/>
      </svg>
      <span>squeeze</span>
    </div>
    <div class="risk-arc r">
      <svg viewBox="0 0 34 78" fill="none">
        <path d="M8 8 q13 31 0 62" stroke="#B8C6D2" stroke-opacity=".45"
              stroke-width="1.4" stroke-linecap="round"/>
        <path d="M18 16 q9 23 0 46" stroke="#B8C6D2" stroke-opacity=".18"
              stroke-linecap="round"/>
      </svg>
      <span>фандинг</span>
    </div>
    <div class="risk-mid">
      <svg class="risk-orbit" viewBox="0 0 276 46" preserveAspectRatio="none">
        <defs>
          <linearGradient id="orb" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stop-color="#C8DCE8" stop-opacity=".05"/>
            <stop offset=".25" stop-color="#DCEAF4" stop-opacity=".5"/>
            <stop offset=".5" stop-color="#F0F8FF" stop-opacity=".7"/>
            <stop offset=".75" stop-color="#DCEAF4" stop-opacity=".4"/>
            <stop offset="1" stop-color="#C8DCE8" stop-opacity=".04"/>
          </linearGradient>
        </defs>
        <ellipse cx="138" cy="23" rx="132" ry="19" fill="none"
                 stroke="url(#orb)" stroke-width="1.2"
                 vector-effect="non-scaling-stroke"/>
        <ellipse cx="138" cy="23" rx="96" ry="11" fill="none" stroke="#C8DCE8"
                 stroke-opacity=".07" vector-effect="non-scaling-stroke"/>
        <circle cx="6" cy="23" r="2" fill="#DCEAF4" opacity=".55"/>
      </svg>
      <div class="risk-k">монет</div>
      <div class="risk-v">{len(items)}</div>
    </div>
    <div class="risk-legs">{legs}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · сетапы
# ─────────────────────────────────────────────────────────────
def _blk_setups(s: dict, total: int) -> str:
    items = sorted(s["items"], key=lambda c: -(getattr(c, "rr", 0) or 0))[:3]

    rows = ""
    for c in items:
        rr = getattr(c, "rr", 0) or 0
        lv = getattr(c.strategy, "levels", None)
        entry = float(getattr(lv, "entry", 0) or 0)
        tone = "gr" if rr >= RR_GOOD else "am"
        color = "#4FCF8A" if rr >= RR_GOOD else "#F5A623"
        fill = min(100, rr / 5 * 100)
        phase = str((c.phase or {}).get("label", "—")).lower()

        rows += (
            f'<div class="set-row" data-coin="{esc(c.symbol)}">'
            f'<div><div class="set-sym">{esc(c.symbol)}</div>'
            f'<div class="set-sub">{esc(phase)} · объём '
            f'×{_num(c, "rvol_1h"):.1f}</div></div>'
            f'<svg class="set-dial" viewBox="-15 -15 30 30">'
            f'<circle r="13" fill="none" stroke="#fff" stroke-opacity=".07" '
            f'stroke-width="2.5"/>'
            f'<circle r="13" fill="none" stroke="{color}" stroke-width="2.5" '
            f'stroke-linecap="round" stroke-dasharray="{_arc(fill, 13)}" '
            f'transform="rotate(-90)"/></svg>'
            f'<span class="set-rr {tone}">1:{rr:.1f}</span>'
            f'<span class="set-in">вход {_price(entry)}</span>'
            f'</div>'
        )

    if not rows:
        rows = '<div class="set-empty">сетапов в этом прогоне нет</div>'

    return f"""
<div class="b b-glass gl-gr c-gr g-set">
  <span class="halo"></span>
  <div class="b-in">
    {_icon('set')}
    <div class="b-t" data-slice="{esc(s['id'])}">сетапы
      <span>{len(s['items'])} из {total} · r:r ≥ {RR_MIN}</span></div>
    <div class="set-list">{rows}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · импульс
# ─────────────────────────────────────────────────────────────
def _blk_impulse(s: dict) -> str:
    # Гистограмма — статика (истории по часам нет). Если срез пуст, гасим её
    # и снимаем подсветку пика: живой декор рядом с нулём выглядит ошибкой.
    n = len(s["items"])
    peak = max(IMP_BARS) or 1
    bars = "".join(
        f'<i class="{"on" if (i == IMP_PEAK and n) else ""}" '
        f'style="height:{v / peak * 100:.0f}%"></i>'
        for i, v in enumerate(IMP_BARS)
    )
    foot = IMP_FOOT if n else IMP_EMPTY
    cls = "b c-am g-imp" + ("" if n else " empty")

    return f"""
<div class="{cls}" data-slice="{esc(s['id'])}">
  <span class="halo"></span>
  <div class="b-in">
    {_icon('imp')}
    {_title('импульс', 'за час')}
    <span class="big">{n}</span>
    <span class="big-u">{IMP_NOTE}</span>
    <div class="imp-bars{'' if n else ' dim'}">{bars}</div>
    <div class="hr"></div>
    <div class="note mid">{esc(foot)}</div>
  </div>
</div>"""


# ─────────────────────────────────────────────────────────────
# Блок · сектора
# ─────────────────────────────────────────────────────────────
def _blk_sectors(snapshot: RunSnapshot) -> str:
    # =====================================================================
    # СЕКТОРА ЗА 24 ЧАСА
    # ФУНКЦИОНАЛ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (`_sectors`): 5 строк, сортировка
    # по изменению за 24ч, бар расходится от центра (рост вправо, падение
    # влево), нормировка по максимуму модуля.
    # Раньше выводилось до 8 строк — по новому макету ровно 5.
    # Если данных нет, показываем SECTOR_FALLBACK, чтобы вёрстка была видна;
    # в этом режиме строки не кликабельны.
    # =====================================================================
    src = getattr(snapshot, "sectors", None) or []
    if src:
        pairs = [(str(_get(r, "sector", "") or ""),
                  float(_get(r, "avg_change_24h", 0) or 0)) for r in src]
        pairs.sort(key=lambda p: -p[1])
        pairs, live = pairs[:5], True
    else:
        pairs, live = list(SECTOR_FALLBACK), False

    peak = max((abs(v) for _, v in pairs), default=1) or 1

    rows = ""
    for name, val in pairs:
        cls = "up" if val >= 0 else "dn"
        attr = f' data-slice="sector:{esc(name)}"' if live else ""
        rows += (
            f'<div class="srow"{attr}>'
            f'<span class="srow-n">{esc(name)}</span>'
            f'<span class="srow-t"><i class="{cls}" '
            f'style="width:{abs(val) / peak * 50:.0f}%"></i></span>'
            f'<span class="srow-v {cls}">{val:+.1f}%</span></div>'
        )

    return f"""
<div class="b b-card c-vi g-sect">
  <span class="halo"></span>
  <div class="b-in">
    {_icon('sec')}
    {_title('сектора', 'за 24 часа')}
    <div class="rows">{rows}</div>
  </div>
</div>"""


# ═════════════════════════════════════════════════════════════
# СТРАТЕГИИ · ряд между первым и вторым экраном блоков.
# Пока одна: FLOW. Лента зафиксирована (золото, компактная,
# по центру). Клик по ленте или по узлу открывает отчёт
# стратегии — карточки, вариант B, только для flow.
#
# ЧТО ПОДКЛЮЧЕНО:
#  · число слева — монеты со сработавшим flow
#  · размер узла и число над ним — счётчик подкейса
#  · лидер справа — максимальный score среди flow
#
# ЧТО ПРЕДСТОИТ:
#  · вторая и третья стратегия встанут в тот же ряд .row-s
#  · «свежесть» узла (пунктирный ореол) — нужна память прогонов
# ═════════════════════════════════════════════════════════════

# порядок узлов на ленте фиксирован макетом, cx пересчитаны
# из холста 1200×950 в локальный viewBox (сдвиг x−352, y−410)
FLOW_NODES = [
    ("hidden",   124, 22.0, "скрытый набор",        True),
    ("spring",   165, 16.0, "сжатие в тишине",      False),
    ("churn",    221, 35.0, "объём есть, цена стоит", True),
    ("fuel",     287, 26.0, "сверху пусто",         True),
    ("taker",    335, 19.0, "сменился агрессор",    False),
    ("lever", 373, 13.0, "шорты перегружены",    False),
]


def _blk_flow(candidates: list[Candidate]) -> str:
    flow = [c for c in candidates if c.flow]
    by_case: dict[str, int] = {}
    for c in flow:
        case = case_key((c.flow or {}).get("case", ""))
        by_case[case] = by_case.get(case, 0) + 1

    lead = max(flow, key=lambda c: getattr(c, "score", 0) or 0, default=None)

    nodes = ""
    for case, cx, rx, _sub, underline in FLOW_NODES:
        n = by_case.get(case, 0)
        ry = rx * 0.317
        dim = "" if n else " off"
        big = " big" if case == "churn" else ""
        # число немного приподнято над кольцом
        dy = -14 if case == "churn" else (-8 if rx >= 22 else -6)
        line = (f'<path d="M{-rx * 0.7:.0f} 47 H{rx * 0.7:.0f}" '
                f'stroke="url(#fl-und)" stroke-width="1"/>' if underline else "")
        nodes += f"""
    <g class="fl-node{dim}{big}" transform="translate({cx},56)"
       data-slice="strat:flow">
      <text class="fl-n" y="{dy}" text-anchor="middle">{n}</text>
      <ellipse rx="{rx + 4:.1f}" ry="{ry + 1.3:.1f}" class="fl-glow"/>
      <ellipse rx="{rx:.1f}" ry="{ry:.1f}" fill="url(#fl-disc)"/>
      <ellipse rx="{rx:.1f}" ry="{ry:.1f}" fill="none" stroke="url(#fl-ring)"
               stroke-width="1.3"/>
      <ellipse rx="{rx + 6:.1f}" ry="{ry + 2:.1f}" fill="none" stroke="#D9A441"
               stroke-opacity=".24" stroke-width=".8"/>
      <path d="M{-rx:.1f} 0 A{rx:.1f} {ry:.1f} 0 0 0 {rx:.1f} 0" fill="none"
            stroke="#FFEBB8" stroke-opacity=".8" stroke-width="1.4"/>
      <text class="fl-c" y="42" text-anchor="middle">{case.upper()}</text>
      {line}
    </g>"""

    lead_html = ""
    if lead is not None:
        lead_html = (
            f'<text class="fl-lk" x="440" y="28">лидер прогона</text>'
            f'<text class="fl-lv" x="440" y="48">{_tick(lead)}</text>'
            f'<text class="fl-ls" x="520" y="48" text-anchor="end">'
            f'{int(getattr(lead, "score", 0) or 0)}</text>'
        )

    cls = "strat c-fl" + ("" if flow else " empty")
    return f"""
<div class="{cls}" data-slice="strat:flow">
  <span class="halo"></span>
  <svg class="fl" viewBox="-14 0 560 130">
    <defs>
      <linearGradient id="fl-base" x1="0" x2="1">
        <stop offset="0" stop-color="#B8860B" stop-opacity="0"/>
        <stop offset=".12" stop-color="#D9A441" stop-opacity=".5"/>
        <stop offset=".5" stop-color="#FFEBB8" stop-opacity=".9"/>
        <stop offset=".88" stop-color="#D9A441" stop-opacity=".5"/>
        <stop offset="1" stop-color="#B8860B" stop-opacity="0"/>
      </linearGradient>
      <linearGradient id="fl-ring" x1="0" x2="1">
        <stop offset="0" stop-color="#B8860B" stop-opacity=".15"/>
        <stop offset=".3" stop-color="#FFD98A" stop-opacity=".95"/>
        <stop offset=".7" stop-color="#FFD98A" stop-opacity=".95"/>
        <stop offset="1" stop-color="#B8860B" stop-opacity=".15"/>
      </linearGradient>
      <linearGradient id="fl-und" x1="0" x2="1">
        <stop offset="0" stop-color="#D9A441" stop-opacity="0"/>
        <stop offset=".5" stop-color="#FFEBB8" stop-opacity=".85"/>
        <stop offset="1" stop-color="#D9A441" stop-opacity="0"/>
      </linearGradient>
      <radialGradient id="fl-disc" cx="50%" cy="35%" r="65%">
        <stop offset="0" stop-color="#D9A441" stop-opacity=".18"/>
        <stop offset="1" stop-color="#33260B" stop-opacity=".45"/>
      </radialGradient>
    </defs>

    <g class="fl-left">
      <ellipse cx="0" cy="56" rx="11" ry="3.7" fill="none" stroke="#FFD98A"
               stroke-opacity=".35"/>
      <ellipse cx="0" cy="56" rx="6.5" ry="2.2" fill="none" stroke="#FFEBB8"
               stroke-opacity=".55"/>
      <circle cx="0" cy="56" r="1.6" fill="#FFF4D8"/>
      <text class="fl-lk" x="22" y="49">FLOW</text>
      <text class="fl-tot" x="22" y="71">{len(flow)}</text>
    </g>
    <line x1="80" y1="26" x2="80" y2="86" stroke="#B8860B" stroke-opacity=".16"/>

    <path d="M94 56 H404" stroke="url(#fl-base)" stroke-width="6"
          class="fl-blur" opacity=".35"/>
    <path d="M94 56 H404" stroke="url(#fl-base)" stroke-width="1"/>
    {nodes}

    <line x1="416" y1="26" x2="416" y2="86" stroke="#B8860B" stroke-opacity=".16"/>
    {lead_html}
    <text class="fl-note" x="440" y="102">КТО ДВИГАЕТ РЫНОК</text>
  </svg>
</div>"""

# ─────────────────────────────────────────────────────────────
# Воронка
# ─────────────────────────────────────────────────────────────
def _funnel(snapshot: RunSnapshot) -> str:
    # =====================================================================
    # ВОРОНКА · "путь отбора N → M"
    # ФУНКЦИОНАЛ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (`_funnel`).
    #   · числа в кругах — счётчики этапов
    #   · ПЕРВЫЙ УЗЕЛ = скрытый срез `all`, отдельного блока у него нет
    #   · скрытый срез `planned` вынесен в узел "r:r ≥ 2"
    #   · дуга на круге — доля от ПРЕДЫДУЩЕГО этапа
    #   · между узлами — дельта отсева (−N); при нулевой дельте вместо
    #     "−0" ставим точку, иначе выглядит как мусор
    #   · последний узел крупнее, со свечением и пунктирным кольцом
    #   · "конверсия N%" справа сверху — последний / первый
    # Если snapshot.funnel пуст, показываем FUNNEL_FALLBACK по макету.
    # =====================================================================
    src = getattr(snapshot, "funnel", None) or []
    clickable = {"вся выборка": "all", "есть план": "planned",
                 "r:r ≥ 2": "planned", "после вето": "vetoed",
                 "к работе": "setups"}

    if src:
        nodes = []
        for r in src:
            name = str(_get(r, "label", None) or _get(r, "name", "") or "")
            nodes.append((name, int(_get(r, "count", 0) or 0),
                          clickable.get(name.lower().strip())))
    else:
        nodes = list(FUNNEL_FALLBACK)

    if not nodes:
        return ""

    first, last = nodes[0][1] or 1, nodes[-1][1]
    conv = last / first * 100 if first else 0

    out, prev = "", nodes[0][1] or 1
    for i, (name, count, target) in enumerate(nodes):
        if i:
            drop = max(0, prev - count)
            out += f'<div class="fn-gap">{"−" + str(drop) if drop else "·"}</div>'
        pct = min(100, count / prev * 100) if prev else 0
        prev = count or prev

        tone = FN_TONE[min(i, len(FN_TONE) - 1)]
        attr = f' data-slice="{target}"' if target else ""
        is_last = i == len(nodes) - 1
        r = 28 if is_last else 24

        extra = (f'<circle r="36" fill="none" stroke="#4FCF8A" stroke-opacity=".12" '
                 f'stroke-dasharray="1 5"/>' if is_last else "")
        arc = ("" if (i == 0 or is_last) else
               f'<circle r="{r}" fill="none" stroke="{tone}" stroke-opacity=".5" '
               f'stroke-width="1.4" stroke-linecap="round" '
               f'stroke-dasharray="{_arc(pct, r)}" transform="rotate(-90)"/>')

        out += (
            f'<div class="fn-node{" last" if is_last else ""}"{attr}>'
            f'<svg width="{r * 2 + 20}" height="{r * 2 + 20}" '
            f'viewBox="-{r + 10} -{r + 10} {r * 2 + 20} {r * 2 + 20}">'
            f'{extra}'
            f'<circle r="{r}" fill="#0d0f12" fill-opacity=".6"/>'
            f'<circle r="{r}" fill="none" stroke="{tone}" stroke-opacity=".2"/>'
            f'{arc}'
            f'<text class="fn-v" y="6" text-anchor="middle">{count}</text></svg>'
            f'<span class="fn-l">{esc(name)}</span></div>'
        )

    return f"""
<div class="fn">
  <span class="halo" style="width:840px;height:80px;top:-6px"></span>
  <div class="fn-cap">путь отбора · {first} → {last}</div>
  <div class="fn-in">
    <div class="fn-line"></div>
    <div class="fn-nodes">{out}</div>
    <div class="fn-foot">
      <b>конверсия {conv:.1f}%</b>
      <b>{FN_FOOT_R}</b>
    </div>
  </div>
</div>"""

def _sector_panes(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    out = ""
    for r in (getattr(snapshot, "sectors", None) or [])[:5]:
        name = str(_get(r, "sector", "") or "")
        out += render_slice_pane({
            "id": f"sector:{name}",
            "label": f"сектор · {name}",
            "note": "все монеты сектора",
            "items": [c for c in candidates if (c.sector or "OTHER") == name],
        })
    return out


def _modals(candidates: list[Candidate]) -> str:
    """Карточки монет: рендерятся один раз, показываются по клику."""
    out = ""
    for c in candidates:
        out += (
            f'<div class="modal" data-coin="{esc(c.symbol)}">'
            f'<div class="modal-bd"></div><div class="modal-in">'
            f'<button class="modal-x">✕</button>{render_card(c)}</div></div>'
        )
    return out


# ─────────────────────────────────────────────────────────────
# Сборка
# ─────────────────────────────────────────────────────────────
def render_dashboard_page(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    slices = build_slices(candidates, snapshot)
    total = len(candidates)

    row1 = "".join([
        _blk_volume(_pick(slices, "surge")),
        _blk_social(_pick(slices, "viral"), total),
        _blk_patterns(slices),
        _blk_risk(_pick(slices, "vetoed"), total),
    ])
    row2 = "".join([
        _blk_setups(_pick(slices, "setups"), total),
        _blk_impulse(_pick(slices, "hourly")),
        _blk_sectors(snapshot),
    ])

    # ряд стратегий между блоками и вторым рядом
    strat = f'<div class="row row-s">{_blk_flow(candidates)}</div>'

    # Панели-таблицы строим для ВСЕХ срезов, включая скрытые:
    # на них ведут узлы воронки.
    panes = ("".join(render_slice_pane(s) for s in slices)
             + _sector_panes(candidates, snapshot)
             + render_flow_report(candidates))     # ← новый отчёт

    return f"""
{_bg()}
<div class="screen" id="dash">
  {_head(snapshot)}
  <div class="row row-1">{row1}</div>
  {strat}
  <div class="row row-2">{row2}</div>
  {_funnel(snapshot)}
</div>
<div class="screen hide" id="panes">{panes}</div>
{_modals(candidates)}
{DASH_JS}"""


DASH_JS = """
<script>
(function () {
  var dash = document.getElementById('dash');
  var panes = document.getElementById('panes');

  function showPane(id) {
    var target = document.querySelector('[data-pane="' + id + '"]');
    if (!target) return;
    document.querySelectorAll('.pane').forEach(function (p) {
      p.classList.remove('on');
    });
    target.classList.add('on');
    dash.classList.add('hide');
    panes.classList.remove('hide');
    panes.classList.add('on');
    window.scrollTo(0, 0);
  }

  function backToDash() {
    panes.classList.remove('on');
    panes.classList.add('hide');
    dash.classList.remove('hide');
    document.querySelectorAll('.pane').forEach(function (p) {
      p.classList.remove('on');
    });
  }

  function openCoin(sym) {
    var m = document.querySelector('.modal[data-coin="' + sym + '"]');
    if (!m) return;
    m.classList.add('on');
    document.body.style.overflow = 'hidden';
  }

  function closeCoin() {
    document.querySelectorAll('.modal.on').forEach(function (m) {
      m.classList.remove('on');
    });
    document.body.style.overflow = '';
  }

  document.addEventListener('click', function (e) {
    if (e.target.closest('.modal-x') || e.target.closest('.modal-bd')) {
      closeCoin();
      return;
    }
    if (e.target.closest('.pane-back')) {
      backToDash();
      return;
    }
    var coin = e.target.closest('[data-coin]');
    if (e.target.closest('a')) { return; }
    if (coin && !coin.closest('.modal')) {
      openCoin(coin.getAttribute('data-coin'));
      return;
    }
    var slice = e.target.closest('[data-slice]');
    if (slice) {
      showPane(slice.getAttribute('data-slice'));
    }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (document.querySelector('.modal.on')) {
      closeCoin();
    } else if (panes.classList.contains('on')) {
      backToDash();
    }
  });
})();
</script>
"""
