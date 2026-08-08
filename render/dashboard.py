"""Дашборд как единственный экран отчёта · вёрстка по макету SLEEPING ALTS.

Плашки кликабельны: каждая открывает таблицу своего среза, строка таблицы —
модалку с полной карточкой монеты.

ЭТАП: вёрстка. Часть значений — статика по макету, источники и TODO
расписаны в комментариях к каждому блоку.
"""

from __future__ import annotations
import json
from pathlib import Path
import random

from core.config import ANOMALY_PATH, LEADERS_PATH
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

# ─────────────────────────────────────────────────────────────
# Журналы наблюдения · output/*.json
# ─────────────────────────────────────────────────────────────
# Оба файла пишет прогон и живут они между прогонами, поэтому
# читаются здесь, а не приходят в snapshot: снимок описывает
# ОДИН прогон, а журнал — накопленную историю. Класть накопитель
# в снимок значило бы дублировать его в каждом файле runs/.

# Кратность, с которой объём считается взрывным. Хватает ОДНОГО
# таймфрейма из пяти: аномалия на двухчасовке и аномалия на
# дневке — разные события, но обе означают, что в монету пришли.
LEAD_HOT_X = 50.0

# Сколько тикеров помещается в правый край ленты FLOW.
LEAD_MAX = 7


def _read_json(path: Path) -> dict:
    """Журнал с диска. Отсутствие файла — не ошибка.

    Первый прогон на чистой машине их не находит, и падать
    из-за этого отчёт не должен: панель просто останется пустой.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _max_vol_ratio(rec: dict) -> float:
    """Максимальная кратность объёма по всем окнам записи.

    Максимум, а не среднее: усреднение по пяти окнам топит
    аномалию, живущую в одном из них. У 1000RATS дневка даёт
    ×31 при 2h ×0.34 — по среднему монета невидима, хотя
    событие произошло.
    """
    vr = rec.get("vol_ratio") or {}
    values = []
    for v in vr.values():
        try:
            values.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(values, default=0.0)

def _shuffle_key(sym: str) -> int:
    """Стабильный псевдослучайный ключ порядка.

    Порядок в панели не несёт смысла: вес монеты сказан цветом
    (объём) и кантом (отбор FLOW). Сортировка по кратности эту
    информацию дублировала и заодно расслаивала список — сверху
    сплошное золото, снизу сплошное белое. Читается как две
    ленты, а не как одна.

    Перемешивание даёт разнобой, но не случайное: ключ выведен
    из имени, поэтому между прогонами порядок один и тот же.
    Список, тасующийся при каждом обновлении, глаз перестаёт
    узнавать, и панель превращается в шум.

    FNV-1a, а не hash(): встроенный хеш строк рандомизирован
    солью процесса, и порядок менялся бы при каждом запуске.
    """
    h = 2166136261
    for ch in sym:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h

# ─────────────────────────────────────────────────────────────
# КАМЕННЫЙ КУБ · декор ряда стратегий
# Вставить в dashboard.py рядом с остальными _blk_* функциями
#
# Все id внутри SVG с префиксом cb-: отчёт это один документ,
# и id фильтров/градиентов в нём общие — без префикса они бы
# столкнулись с fl-base, fl-ring и прочими из блока FLOW.
# ─────────────────────────────────────────────────────────────
def _blk_cube() -> str:
    return """
<div class="g-cube" aria-hidden="true">
  <svg class="cb" viewBox="0 0 600 600">
    <defs>
      <linearGradient id="cb-top" x1="0" y1="0" x2="1" y2="0.4">
        <stop offset="0"   stop-color="var(--cb-dark)"/>
        <stop offset="0.6" stop-color="var(--cb-rock)"/>
        <stop offset="1"   stop-color="var(--cb-lit)"/>
      </linearGradient>
      <linearGradient id="cb-left" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#0b0b0e"/>
        <stop offset="1" stop-color="var(--cb-dark)"/>
      </linearGradient>
      <linearGradient id="cb-right" x1="0" y1="0.2" x2="0.9" y2="1">
        <stop offset="0" stop-color="var(--cb-rock)"/>
        <stop offset="1" stop-color="var(--cb-dark)"/>
      </linearGradient>
      <radialGradient id="cb-hot" cx="88%" cy="48%" r="44%">
        <stop offset="0"    stop-color="var(--cb-lit)"  stop-opacity=".58"/>
        <stop offset="0.35" stop-color="var(--cb-glow)" stop-opacity=".32"/>
        <stop offset="1"    stop-color="var(--cb-glow)" stop-opacity="0"/>
      </radialGradient>

      <!-- Рельеф породы. Анизотропная частота (по X редко, по Y часто)
           кладёт шум слоями — получается слоистый камень, а не шагрень.
           Свет считает feDiffuseLighting прямо по этому шуму. -->
      <filter id="cb-rock" x="-12%" y="-12%" width="124%" height="124%">
        <feTurbulence type="fractalNoise" baseFrequency="0.01 0.075"
                      numOctaves="6" seed="5" result="n"/>
        <feDiffuseLighting in="n" surfaceScale="5" diffuseConstant="1.25"
                           lighting-color="#e8dcc4" result="dif">
          <feDistantLight azimuth="215" elevation="52"/>
        </feDiffuseLighting>
        <feSpecularLighting in="n" surfaceScale="5" specularConstant="1.15"
                            specularExponent="16"
                            lighting-color="var(--cb-spec)" result="spec">
          <fePointLight x="500" y="300" z="90"/>
        </feSpecularLighting>
        <feBlend in="dif" in2="SourceGraphic" mode="multiply" result="base"/>
        <feComposite in="base" in2="SourceGraphic" operator="in" result="base2"/>
        <feComposite in="spec" in2="SourceGraphic" operator="in" result="spec2"/>
        <feComposite in="spec2" in2="base2" operator="arithmetic"
                     k1="0" k2="1" k3="1" k4="0"/>
      </filter>

      <!-- Скол граней: крупный шум рвёт силуэт кусками,
           мелкий добавляет крошку по краю -->
      <filter id="cb-chip" x="-25%" y="-25%" width="150%" height="150%">
        <feTurbulence type="fractalNoise" baseFrequency="0.006"
                      numOctaves="3" seed="11" result="t1"/>
        <feDisplacementMap in="SourceGraphic" in2="t1" scale="44"
                           xChannelSelector="R" yChannelSelector="G" result="d1"/>
        <feTurbulence type="fractalNoise" baseFrequency="0.05"
                      numOctaves="2" seed="4" result="t2"/>
        <feDisplacementMap in="d1" in2="t2" scale="9"
                           xChannelSelector="R" yChannelSelector="G"/>
      </filter>

      <filter id="cb-bloom" x="-100%" y="-100%" width="300%" height="300%">
        <feGaussianBlur stdDeviation="26"/>
      </filter>
      <filter id="cb-rim" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="7"/>
      </filter>
    </defs>

    <g transform="rotate(-16 300 330)">
      <path d="M460 240 L460 420 L300 510 L300 330 Z" fill="var(--cb-glow)"
            filter="url(#cb-bloom)" opacity=".45"/>

      <g filter="url(#cb-chip)">
        <path d="M300 150 L460 240 L300 330 L140 240 Z"
              fill="url(#cb-top)"   filter="url(#cb-rock)"/>
        <path d="M140 240 L300 330 L300 510 L140 420 Z"
              fill="url(#cb-left)"  filter="url(#cb-rock)"/>
        <path d="M460 240 L460 420 L300 510 L300 330 Z"
              fill="url(#cb-right)" filter="url(#cb-rock)"/>

        <path d="M140 240 L300 330 L300 510 L140 420 Z" fill="#050508" opacity=".55"/>
        <path d="M300 150 L460 240 L300 330 L140 240 Z" fill="#0a0806" opacity=".28"/>
        <path d="M300 150 L460 240 L460 420 L300 510 L140 420 L140 240 Z"
              fill="url(#cb-hot)"/>
      </g>

      <path d="M300 150 L460 240 L460 420 L300 510" fill="none"
            stroke="var(--cb-lit)" stroke-width="3"
            filter="url(#cb-rim)" opacity=".7"/>
    </g>
  </svg>
</div>
"""

# Ступени взрывного объёма. Одного порога мало: x50 и x200 —
# события разного веса, а одним цветом они сливаются в «жёлтое».
# Три ступени дают шкалу, читаемую без чисел.
LEAD_X1 = 50.0
LEAD_X2 = 100.0
LEAD_X3 = 150.0


def _blk_leaders(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    """Кто двигает рынок — правый край строки FLOW.

    Два источника. leaders.json — лидеры выборки FLOW: подкейс
    сработал, план построен. anomaly_volume.json — журнал
    аномальных объёмов, факт без интерпретации.

    Порядок ОБЩИЙ и задан кратностью объёма, а не источником.
    Раньше список склеивался встык — сначала весь FLOW, потом
    весь объём, — и читался как две несвязанные ленты, где
    верхняя половина всегда одного цвета. Источник кодируется
    кантом, поэтому в порядке он не нужен.

    Лидер FLOW без записи в журнале объёмов получает 0 и уходит
    в хвост: про его объём мы ничего не знаем, и притворяться,
    что знаем, нельзя. Из списка он не выпадает — держит кант.

    Классы:
      lead-f  — лидер выборки FLOW (кант под первой буквой)
      lead-g1/g2/g3 — объём выше x50 / x100 / x200

    Признаки не исключают друг друга: цвет отдан объёму, кант —
    отбору, и монета с обоими видна как самый сильный случай.
    """
    flow_j = _read_json(LEADERS_PATH)
    vol_j = _read_json(ANOMALY_PATH)

    # Служебные ключи журналов (last_leader и прочее) не монеты.
    # Фильтр по префиксу, а не по имени: их может стать больше.
    flow_syms = [k for k in flow_j if not k.startswith("_")]
    vol_syms = [k for k in vol_j if not k.startswith("_")]

    ranked: dict[str, float] = {}
    for sym in flow_syms:
        ranked[sym] = _max_vol_ratio(flow_j.get(sym) or {})
    for sym in vol_syms:
        ranked.setdefault(sym, _max_vol_ratio(vol_j.get(sym) or {}))

    # Порядок — разнобой. Никакого рейтинга: вес монеты уже сказан
    # цветом (объём) и кантом (лидер FLOW), и дублировать его
    # позицией незачем. Сортировка по кратности вдобавок расслаивала
    # панель — сверху сплошное золото, снизу сплошное белое, — и она
    # читалась как две ленты вместо одной.
    order = list(ranked)
    random.shuffle(order)

    def _tier(sym: str) -> int:
        x = ranked[sym]
        if x >= LEAD_X3: return 3
        if x >= LEAD_X2: return 2
        if x >= LEAD_X1: return 1
        return 0

    # Первая колонка (7 монет) — единственное, что видно без наведения.
    # Золотые не должны зависеть от того, куда их бросил shuffle: меняем
    # местами с нетиерными в её пределах. Порядок внутри каждой части
    # всё равно вперемешку — полосатости, от которой уже отказались
    # раньше (сплошное золото сверху/снизу), это не создаёт.
    # Потолок на промоушен: без него, если тиерных монет в выборке
    # много, они вытесняют ВСЕ нетиерные из семёрки — та же полосатость,
    # от которой уже отказались раньше, просто внутри одной видимой
    # колонки вместо всей ленты. LEAD_PROMOTE_MAX держит контраст даже
    # когда почти весь прогон золотой.
    LEAD_PROMOTE_MAX = 2
    visible, rest = order[:7], order[7:]
    promoted = 0
    for sym in [s for s in rest if _tier(s) > 0]:
        if promoted >= LEAD_PROMOTE_MAX:
            break
        demote = next((s for s in visible if _tier(s) == 0), None)
        if demote is None:
            break
        vi, ri = visible.index(demote), rest.index(sym)
        visible[vi], rest[ri] = rest[ri], visible[vi]
        promoted += 1
    order = visible + rest

    by_symbol = {c.symbol.upper(): c for c in candidates}

    items = ""
    for i, sym in enumerate(order):
        cls = ["lead-t"]
        if i >= 7:
            cls.append("lead-x")
        if sym in flow_j:
            cls.append("lead-f")
        x = ranked[sym]
        if x >= LEAD_X3:
            cls.append("lead-g3")
        elif x >= LEAD_X2:
            cls.append("lead-g2")
        elif x >= LEAD_X1:
            cls.append("lead-g1")

        c = by_symbol.get(sym.upper())
        # Клик открывает карточку только если монета есть в этом
        # прогоне: журнал переживает прогоны, модалки — нет.
        attr = f' data-coin="{esc(c.symbol)}"' if c is not None else ""
        label = sym[:-4] if sym.endswith("USDT") else sym
        title = f' title="×{x:.0f}"' if x else ""
        items += (
            f'<span class="{" ".join(cls)}"{attr}{title}>{esc(label)}</span>'
        )

    if not items:
        items = '<span class="lead-t off">нет данных</span>'

    return f"""
<div class="g-lead">
  <div class="lead-list">{items}</div>
  <div class="lead-hd">объём · flow</div>
</div>"""

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
# ОРБИТА · верхний экран дашборда
# Вставить в dashboard.py рядом с остальными _blk_* функциями.
# json уже импортирован в шапке файла.
#
# Клик по узлу устроен как клик по блоку: на узле и подписи стоит
# data-slice, дальше срабатывает общий делегат из DASH_JS. Своего
# обработчика клика у орбиты нет намеренно — иначе логика показа
# панелей жила бы в двух местах и разъезжалась при правках.
# ─────────────────────────────────────────────────────────────

# Цвета берём из токенов, а не хардкодом: узел орбиты и раздел под ним
# должны совпадать по цвету, а токены — единственное место, где он живёт.
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

    # ПОТОК · разбивка по подкейсам, как в кольцах строки FLOW
    flow = [c for c in candidates if c.flow]
    by_case: dict[str, int] = {}
    for c in flow:
        k = case_key((c.flow or {}).get("case", "")) or "—"
        by_case[k] = by_case.get(k, 0) + 1
    lead = max(flow, key=lambda c: getattr(c, "score", 0) or 0, default=None)
    out.append({
        "id": "flow", "name": "ПОТОК", "val": str(len(flow)),
        "c": ORBIT_COLORS["flow"], "w": 0.7, "slice": "strat:flow",
        "note": (f"лидер прогона · {_tick(lead)}") if lead else "кто двигает рынок",
        "rows": bars([(case, str(by_case.get(case, 0)),
                       float(by_case.get(case, 0)))
                      for case, *_ in FLOW_NODES]),
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

        ratio = _max_vol_ratio(flow_j.get(sym) or {})
        c = by_symbol.get(sym.upper())
        label = sym[:-4] if sym.endswith("USDT") else sym
        out.append({
            "t": label,
            "f": round(fresh, 3),
            "hot": bool(ratio >= LEAD_X1),
            "x": round(ratio),
            "lead": sym.upper() == lead_sym,
            "coin": (c.symbol if c is not None else ""),
        })

    # Лидер рисуется последним — поверх остальных, если рядом окажется сосед
    out.sort(key=lambda s: (s["lead"], s["f"]))
    return out


def _blk_orbit(candidates: list[Candidate], snapshot: RunSnapshot,
               slices: list[dict]) -> str:
    nodes = _orbit_nodes(candidates, snapshot, slices)
    stars = _orbit_stars(candidates)

    # Данные уходят отдельным <script type="application/json">, а не
    # склеиваются в разметку: экранировать нужно только "<".
    blob = json.dumps({"nodes": nodes, "stars": stars},
                      ensure_ascii=False).replace("<", "\\u003c")

    regime = esc(str(getattr(snapshot, "regime", "") or "RISK-OFF"))
    appetite = esc(str(getattr(snapshot, "appetite", "") or "—"))
    btc_d = esc(str(getattr(snapshot, "btc_dominance", "") or "—"))
    viral_n = len(_pick(slices, "viral")["items"])
    soc = f"{viral_n} всплеск" if viral_n else "тихо"

    return f"""
<div class="ob" id="ob">
  <svg viewBox="0 0 1000 640" preserveAspectRatio="xMidYMid slice">
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
      <mask id="ob-fade"><rect width="1000" height="640" fill="url(#ob-fadeg)"/></mask>

      <radialGradient id="ob-bandg" cx="34%" cy="70%" r="40%">
        <stop offset="0" stop-color="#fff" stop-opacity="1"/>
        <stop offset="0.55" stop-color="#fff" stop-opacity=".45"/>
        <stop offset="1" stop-color="#fff" stop-opacity="0"/>
      </radialGradient>
      <mask id="ob-band"><rect width="1000" height="640" fill="url(#ob-bandg)"/></mask>

      <filter id="ob-glow" x="-40%" y="-40%" width="180%" height="180%">
        <feGaussianBlur stdDeviation="5"/>
      </filter>
      <filter id="ob-spark" x="-300%" y="-300%" width="700%" height="700%">
        <feGaussianBlur stdDeviation="4"/>
      </filter>
      <filter id="ob-soft" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="34"/>
      </filter>
      <filter id="ob-grain">
        <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="3"/>
      </filter>
    </defs>

    <rect width="1000" height="640" fill="url(#ob-sky)"/>
    <ellipse cx="500" cy="320" rx="430" ry="250" fill="url(#ob-haze)"
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

    <g id="ob-dust" class="ob-dust"></g>
    <g id="ob-stars"></g>
    <g id="ob-links"></g>
    <g id="ob-orbit"></g>
    <g id="ob-nodes"></g>

    <!-- Зерно: статичный слой, пересчёта на кадр нет -->
    <rect width="1000" height="640" filter="url(#ob-grain)" opacity=".05"
          style="pointer-events:none"/>
    <ellipse cx="820" cy="140" rx="330" ry="240" fill="#2a2418"
             opacity=".5" filter="url(#ob-soft)"/>
  </svg>

  <div class="ob-core">
    <div class="ob-core-k">РЕЖИМ РЫНКА</div>
    <div class="ob-core-v">{regime}</div>
    <div class="ob-core-s">аппетит <b>{appetite}</b> · btc.d <b>{btc_d}</b>
      · соцсети <b>{soc}</b></div>
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

  var CX = 500, CY = 320, RX = 372, RY = 168, TILT = -9;
  var NODE_LEN = [], cometEl = null, TOTAL_LEN = 0;

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
    var N = 104, A0 = 90, A1 = 452, T0 = TILT - 22, T1 = TILT + 16;
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

      var k = 1 - Math.abs(i - 62) / 15;
      if (k > 0) {
        var gold = { d: d, stroke: '#FFC46B',
          'stroke-width': (0.3 + 0.95 * k).toFixed(2),
          opacity: (0.12 + 0.42 * k).toFixed(3) };
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
        y1: (CY + Math.sin(a) * 32).toFixed(1),
        x2: (CX + Math.cos(a) * 470).toFixed(1),
        y2: (CY + Math.sin(a) * 212).toFixed(1), 'stroke-width': .5 }));
    }
    var back = document.getElementById('ob-arcsBack');
    for (var j = 0; j < 14; j++) {
      var t = j / 13, a2 = 130 + 330 * t;
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
  function rayPath(r, w) {
    return 'M0 ' + (-r) + ' Q' + w + ' ' + (-w) + ' ' + r + ' 0 Q' + w + ' ' + w +
           ' 0 ' + r + ' Q' + (-w) + ' ' + w + ' ' + (-r) + ' 0 Q' + (-w) + ' ' +
           (-w) + ' 0 ' + (-r) + ' Z';
  }

  /* Звёзды стоят вне кольца узлов: точка отвергается, если попала
     в полосу орбиты или в центральный прямоугольник, где всплывает
     карточка. Сдвиг детерминированный, поэтому перебор не случайный. */
  function starSpot(sym) {
    var h = hash(sym);
    for (var k = 0; k < 24; k++) {
      var a = ((h >>> (k % 8)) % 3600) / 3600 * Math.PI * 2;
      var rr = 0.28 + ((h >>> ((k + 3) % 12)) % 1000) / 1000 * 1.05;
      var x = CX + Math.cos(a) * RX * rr;
      var y = CY + Math.sin(a) * RY * rr * 1.35;
      var band = Math.abs(rr - 1);
      var inCard = Math.abs(x - CX) < 185 && Math.abs(y - CY) < 140;
      /* И подальше от узлов с подписями: звезда, севшая на «ЛИДЕРЫ 46»,
         читается как часть этой категории, хотя смысл у неё другой. */
      var nearNode = false;
      for (var n = 0; n < BLOCKS.length; n++) {
        var np = pos(n);
        if (Math.hypot(np.x - x, np.y - y) < 86) { nearNode = true; break; }
      }
      if (band > 0.18 && !inCard && !nearNode &&
          x > 40 && x < 960 && y > 40 && y < 600) {
        return { x: x, y: y };
      }
      h = (h * 16777619 + 1) >>> 0;
    }
    return { x: CX + RX * 1.2, y: CY - RY * 1.1 };
  }

  function buildStars() {
    var host = document.getElementById('ob-stars');
    STARS.forEach(function (s) {
      var p = starSpot(s.t);
      var f = s.f;                              // свежесть 0..1
      var r = (s.lead ? 9 : 4) + f * 6;         // размер несёт свежесть
      var op = 0.28 + f * 0.62;

      var g = el('g', { class: 'ob-star' });
      if (s.coin) g.dataset.coin = s.coin;      // клик откроет карточку монеты
      g.setAttribute('transform', 'translate(' + p.x.toFixed(1) + ' ' +
                                  p.y.toFixed(1) + ')');

      var tip = document.createElementNS(NS, 'title');
      tip.textContent = s.t + (s.x ? ' · ×' + s.x : '') +
                        (s.lead ? ' · лидер прогона' : '');
      g.appendChild(tip);

      /* Цвет отдан объёму: золото у x50 и выше, холодное серебро ниже.
         Свежесть уже сказана размером и яркостью — двум признакам
         одного свойства не хватило бы. */
      var col = s.hot ? '#FFD98A' : '#cfdae6';

      g.appendChild(el('circle', { class: 'ob-glow', r: r * 1.5, fill: col,
        filter: 'url(#ob-spark)', opacity: (op * 0.5).toFixed(2) }));
      g.appendChild(el('path', { class: 'ob-ray', d: rayPath(r, r * 0.13),
        fill: col, opacity: op.toFixed(2) }));

      if (s.hot) {
        /* Доп. элемент для x50: второй луч под 45° даёт восьмиконечную
           вспышку, плюс расходящееся кольцо. Событие редкое — заметность
           здесь важнее сдержанности. */
        g.appendChild(el('path', { class: 'ob-ray', d: rayPath(r * 0.62, r * 0.1),
          fill: col, opacity: (op * 0.8).toFixed(2),
          transform: 'rotate(45)' }));
        var halo = el('circle', { class: 'ob-star-ring', r: r * 1.6 });
        halo.style.transformOrigin = '0 0';
        halo.style.animationDelay = (hash(s.t) % 4000) + 'ms';
        g.appendChild(halo);
      }

      g.appendChild(el('circle', { r: Math.max(1, r * 0.16), fill: '#fff',
        opacity: op.toFixed(2) }));

      // Подпись только у текущего лидера: у всех сразу поле стало бы списком
      if (s.lead) {
        var t = el('text', { class: 'ob-star-lbl', x: 0, y: r + 12,
          'text-anchor': 'middle' });
        t.textContent = s.t;
        g.appendChild(t);
      }

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
      lab.style.top  = ((p.y + vy / len * 54) / 640 * 100) + '%';
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
        (b.rows || []).forEach(function (r) {
          html += '<div class="ob-card-r"><span class="ob-card-k">' + r[0] +
                  '</span><span class="ob-card-bar"><i style="width:' + r[2] +
                  '%"></i></span><span class="ob-card-x">' + r[1] + '</span></div>';
        });
        html += sparkSVG(b.spark, b.c);
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
  var LAP = 26000, HOLD = 0.055;
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

  buildArcs();
  buildBack();
  buildDust();
  buildStars();
  build();
  requestAnimationFrame(frame);
})();
</script>
"""

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

    # ряд стратегий между блоками и вторым рядом.
    # Куб идёт между FLOW и лидерами: в .row-s он встаёт справа от ленты,
    # а на узких экранах ряд переносится и куб скрывается медиазапросом.
    strat = (
        f'{_blk_flow(candidates)}'
        f'{_blk_leaders(candidates, snapshot)}'
    )

    # Панели-таблицы строим для ВСЕХ срезов, включая скрытые:
    # на них ведут узлы воронки.
    panes = ("".join(render_slice_pane(s) for s in slices)
             + _sector_panes(candidates, snapshot)
             + render_flow_report(candidates))     # ← новый отчёт

    # Орбита лежит ВНУТРИ #dash, сразу под шапкой. Это не косметика:
    # showPane() в DASH_JS вешает .hide на #dash целиком, поэтому при
    # открытии панели среза орбита уезжает вместе с дашбордом сама.
    # Снаружи её пришлось бы прятать отдельной правкой в DASH_JS.
    return f"""
    {_bg()}
    <div class="screen" id="dash">
      {_head(snapshot)}
      {_blk_orbit(candidates, snapshot, slices)}
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
