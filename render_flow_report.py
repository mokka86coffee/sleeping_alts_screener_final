"""Отчёт стратегии FLOW · карточки вместо горизонтальной таблицы.

Вариант B, зафиксирован: свет из левого нижнего угла, кант затухает
вправо, цвет = статус строки. Применяется ТОЛЬКО к flow — у других
стратегий свои представления.
"""

from __future__ import annotations

from core_models import Candidate
from render_theme import esc
from analytics_momentum import oi_state
# Форматирование капитализации и выборка чисел карточки жили здесь
# и импортировались отсюда орбитой и дашбордом — рендер зависел от
# рендера. Ни там, ни там нет ни тега, ни esc(): это вычисление, и
# теперь оно берётся из слоя аналитики, как и всё остальное.
from analytics_metrics import card_data, fmt_cap
# Ключ подкейса и порядок отчёта — вычисление над списком монет,
# а не отрисовка: их спрашивают дашборд и орбита тоже, и раньше
# оба брали их отсюда, из соседнего рендера.
from analytics_flow import case_key, flow_order
from render_common import CASE_RU

# ── палитра статусов ──────────────────────────────────────────
# золото — топ прогона, зелёный — чисто, оранж — под вето.
#
# Четвёртого тона нет: он был заведён под «новичок прогона», а
# признака новизны в Candidate не существует — сравнение со
# снимком не реализовано. Тон без источника данных это мёртвая
# ветка, внешне неотличимая от рабочей.
TONE = {
    "top": ("gd", "#FFB020", "#FFD25E"),
    "ok": ("gr", "#22E08A", "#6BFFB4"),
    "veto": ("rd", "#FF6B35", "#FF9B6B"),
}

# ── состояние импульса · техдолг «Панель состояния импульса» ───
# Фильтр отбора считается по дневным полям и работает уже сейчас.
# Уровень по Vortex НЕ считается: внутридневной лестницы (1h–6h)
# в ядре нет, дневной Vortex на этот вопрос не отвечает.
#
# Пока источника нет, шкала гасится и подписывается «нет данных».
# Ставить уровень 1 по умолчанию нельзя: «продавец спокоен» и
# «мы не знаем» — разные утверждения, и подменять второе первым
# значит врать шкалой ровно в том месте, ради которого её завели.
IMPULSE_MIN_PCT = 30.0

# 4 уровня, 3 цвета: подъём линии продаж (2) и её устойчивый рост (3)
# делят один тон, потому что различие между ними количественное,
# а решение по ним одинаковое — насторожиться.
VORTEX_STATE = {
    1: ("flat", "продавец спокоен"),
    2: ("up", "давление растёт"),
    3: ("up", "давление растёт"),
    4: ("cross", "продавец перехватил"),
}


def _impulse(c: Candidate) -> str:
    """Состояние импульса: рост >30% за 1–3 дня плюс характер продаж.

    Окно берём самое короткое из тех, что уже перебрали порог: если
    30% набрались за сутки, импульс начался сутки назад, и мерить его
    трёхдневным окном значит растянуть событие, которого там нет.
    Длительность нужна для выбора масштаба, поэтому подменять её
    более удобным числом нельзя.

    Четырёхдневный случай (BEAT) теперь ловится: ch_4d считается
    той же pct_change(), что и остальные точки (Ч-6 тех.долга).
    """
    r = c.raw or {}
    d1 = float(r.get("ch_24h") or 0)
    d3 = float(r.get("ch_3d") or 0)
    d4 = float(r.get("ch_4d") or 0)

    if d1 >= IMPULSE_MIN_PCT:
        pct, days = d1, 1
    elif d3 >= IMPULSE_MIN_PCT:
        pct, days = d3, 3
    elif d4 >= IMPULSE_MIN_PCT:
        pct, days = d4, 4
    else:
        return '<span class="fr-imp-off">не в импульсе</span>'

    # Уровень продавца — impact.ratio (analytics_intraday), не
    # context.impulse: того поля не существует нигде в диспетчере, и
    # level был всегда 0 (Ч-5 тех.долга). ratio уже подключён к
    # звезде/карточке тем же приёмом (Ч-5 доп.: stance/impact), здесь
    # читается прямо из c.raw["intraday"] без нового расчёта.
    intra = (c.raw or {}).get("intraday") or {}
    ratio = (intra.get("impact") or {}).get("ratio")

    if ratio is None:
        level, tf = 0, ""
    elif ratio <= 0.8:
        level, tf = 1, "упругость растёт"
    elif ratio <= 1.2:
        level, tf = 2, "без изменений"
    elif ratio <= 1.8:
        level, tf = 3, "стакан тает"
    else:
        level, tf = 4, "стакан истончился"

    state, _label = VORTEX_STATE.get(level, ("none", "нет данных"))

    segs = "".join(
        f'<i class="{"on" if i < level else ""}"></i>' for i in range(4)
    )
    tail = f" · {esc(tf)}" if tf else ""
    return (f'<span class="fr-imp {state}">{segs}</span>'
            f'<span class="fr-impv">+{pct:.0f}% за {days}д{tail}</span>')


def _flow(c: Candidate, key: str, default=None):
    return (c.flow or {}).get(key, default)


def _tone(c: Candidate, idx: int) -> str:
    if c.vetoed:
        return "veto"
    return "top" if idx == 0 else "ok"


def _arc(pct: float, r: float) -> str:
    circ = 2 * 3.14159265 * r
    on = circ * max(0.0, min(100.0, pct)) / 100
    return f"{on:.2f} {circ - on:.2f}"


def _spark(values: list[float], w: float = 154.0,
           h: float = 46.0) -> tuple[str, float, float]:
    """Ломаная цены с автомасштабом. Возвращает (points, x, y последней)."""
    n = len(values)
    if n < 2:
        y = h / 2
        return f"0,{y:.1f} {w:.0f},{y:.1f}", w, y
    lo, hi = min(values), max(values)
    span = hi - lo
    top, bottom, step = 5.0, h - 5.0, w / (n - 1)
    pts = []
    for i, v in enumerate(values):
        k = 0.5 if span < 1e-9 else (v - lo) / span
        pts.append((i * step, bottom - k * (bottom - top)))
    return (" ".join(f"{x:.1f},{y:.1f}" for x, y in pts),
            pts[-1][0], pts[-1][1])


# ── формат ────────────────────────────────────────────────────
def _mult(v) -> str:
    """Кратность медиане: ×0.4 · ×2.1 · ×12. Прочерк — недобор бара."""
    if v is None or v <= 0:
        return "—"
    return f"×{v:.0f}" if v >= 10 else f"×{v:.1f}"


def _background(c: Candidate) -> tuple[int, str]:
    """Фон торговли и характер потока — три уровня.

    Величина унаследована от buzz.build_buzz и доработана внутри
    семейства: те же две оси, но rvol заменён на rel_volume
    (медиана к медиане, только по полным барам), а obv_slope — на
    фактический taker-поток, нормированный на оборот.

    Сам buzz.py не импортируется: FLOW от действующих стратегий
    не зависит. Уровень «соцсети» из него не используется — до
    появления настоящего источника лучше не иметь данных, чем
    иметь недостоверные.

    Верхний уровень требует совпадения двух осей, как hot в buzz:
    объём выше нормы И поток односторонний вверх. Порознь ни то
    ни другое ничего не значит.

    Пороги из семейства: churn требует от 1.3, spring — не выше
    0.9, между ними зазор, где не собирается ни один подкейс.
    """
    ctx = ((c.flow or {}).get("context") or {}).get("flow") or {}
    rel = float(ctx.get("rel_volume") or 0)
    slope = float(ctx.get("delta_slope") or 0)

    if rel <= 0:
        return 0, "—"
    if rel >= 1.3:
        return (3, "разгон") if slope > 0 else (2, "шумно")
    if rel >= 0.9:
        return 2, "обычно"
    return 1, "тихо"


def _vol_rows(d: dict) -> str:
    """Три масштаба в столбик. Ярче тот, что сильнее медианы."""
    out = ""
    for label, key in (("1ч", "v1h"), ("4ч", "v4h"), ("1д", "v1d")):
        v = d[key]
        if v is None:
            # Бар набран меньше порога — прочерк, а не число.
            # Заниженное значение хуже отсутствующего: оно
            # выглядит как факт.
            out += (f'<span class="fr-vr off"><i>{label}</i>'
                    f'<b>—</b><s></s></span>')
            continue
        lvl = "hot" if v >= 4 else ("warm" if v >= 2 else "")
        out += (f'<span class="fr-vr {lvl}">'
                f'<i>{label}</i><b>{_mult(v)}</b>'
                f'<s style="width:{min(100, v / 8 * 100):.0f}%"></s></span>')
    return out

# Короткие ярлыки: строка ссылок стоит над тикером и не должна
# перетягивать внимание с самой карточки. Полные названия сайтов
# занимали четверть ширины и не сообщали ничего сверх иконки.
SITES = (
    ("tv", "https://www.tradingview.com/chart/?symbol=BINANCE:{sym}.P", True),
    ("bnc", "https://www.binance.com/en/futures/{sym}", False),
    ("tw", "https://twitter.com/search?q=%24{base}", False),
)


def _links(c: Candidate) -> str:
    """Внешние ссылки, каждая — на саму монету.

    CoinGecko идёт отдельно: их id приходит из c.links и по тикеру
    не восстанавливается. Нет ссылки — чип гасится, а не ведёт на
    главную. Переход в никуда хуже отсутствия перехода.
    """
    base = c.symbol.replace("USDT", "")
    out = ""
    for label, tpl, pri in SITES:
        url = tpl.format(sym=c.symbol, base=base)
        cls = "fr-lnk pri" if pri else "fr-lnk"
        out += (f'<a class="{cls}" href="{url}" target="_blank" '
                f'rel="noopener">{label}<i>↗</i></a>')

    cg = next((str(l.get("url") or "") for l in (c.links or [])
               if "coingecko.com/en/coins/" in str(l.get("url") or "")), "")
    out += (f'<a class="fr-lnk" href="{esc(cg)}" target="_blank" '
            f'rel="noopener">cg<i>↗</i></a>' if cg
            else '<span class="fr-lnk off">cg</span>')
    return out

def _horizon(c: Candidate) -> str:
    """Срок, на который рассчитан сигнал.

    Диспетчер выбирает горизонт по масштабу, на котором собралась
    фигура: скрытый набор разряжается дольше, чем перекос в плече.
    Без этой величины score сравнивает несравнимое — сигнал на
    неделю и сигнал на два месяца стоят рядом с одним числом.
    """
    days = int((c.flow or {}).get("horizon_days") or 0)
    if days <= 0:
        return '<span class="fr-hz off">—</span>'
    return f'<span class="fr-hz"><b>{days}</b><s>дней</s></span>'


def _fund_bar(pct: float) -> str:
    """Биполярный бар от центра. Вправо — лонги платят, влево — шорты."""
    fill = min(50.0, abs(pct) / 1.0 * 50)          # ±1% = край шкалы
    side = "pos" if pct >= 0 else "neg"
    style = (f"left:50%;width:{fill:.0f}%" if pct >= 0
             else f"right:50%;width:{fill:.0f}%")
    return (f'<span class="fr-fund"><s></s>'
            f'<i class="{side}" style="{style}"></i></span>'
            f'<span class="fr-fv {side}">{pct:+.3f}%</span>')

def _state_row(c: Candidate) -> str:
    """Плечо/поздно/скидка — то же определение состояния, что уже
    показывают карточка и зал (analytics_momentum.oi_state(),
    cases[..]["late"], cases[..]["mults"]["up_discount"]). Отчёт
    читает те же поля context/cases, поэтому вызывает ту же функцию,
    а не пересчитывает признак заново.

    Пусто, если ни один из трёх флагов не сработал — карточка отчёта
    не обязана нести пустую строку там, где сказать нечего.
    """
    flow = c.flow or {}
    ctx = flow.get("context") or {}
    oi = ctx.get("oi_hist") or {}
    state = oi_state(oi)

    case = case_key(flow.get("case") or "")
    info = (flow.get("cases") or {}).get(flow.get("case") or "") or {}
    late = bool(info.get("late"))
    up_mult = float((info.get("mults") or {}).get("up_discount") or 1.0)

    bits: list[str] = []
    if state and state["label"] in ("held", "repeat"):
        word = "не проверено" if state["label"] == "held" else \
            f"цикл {int(state.get('cycles', 0)) + 1}"
        bits.append(
            f'<span class="fr-state hot">плечо ×{state["rise_x"]:.1f} · {esc(word)}</span>'
        )
    if late:
        bits.append('<span class="fr-state hot">фигура уже отыграна</span>')
    if up_mult < 1.0:
        bits.append(
            f'<span class="fr-state warm">скидка ×{up_mult:.2f} за уход от дна</span>'
        )
    if not bits:
        return ""
    return f'<div class="fr-c fr-state-row">{"".join(bits)}</div>'


def _zones(c: Candidate) -> str:
    """Ближайшая опора снизу и ближайший завал сверху.

    Роль зоны определяется положением цены, а не стороной событий:
    выше — там набирали и будут защищать, ниже — там застряли и
    будут выходить в ноль. Обе величины уже посчитаны ядром, здесь
    только выбор ближайших.

    tests — сколько раз уровень проверяли и он выдержал. Ноль
    тестов не порок, но и не подтверждение: зона может быть просто
    молодой.
    """
    ctx = (c.flow or {}).get("context") or {}
    price = float(ctx.get("price") or 0)
    zones = ctx.get("zones") or []
    if price <= 0 or not zones:
        return '<span class="fr-zn off">карты нет</span>'

    below = [z for z in zones if float(z.get("price") or 0) < price]
    above = [z for z in zones if float(z.get("price") or 0) > price]
    out = ""

    if above:
        z = min(above, key=lambda z: float(z["price"]))
        dist = (float(z["price"]) / price - 1) * 100
        out += (f'<span class="fr-zn up"><i>↑</i>'
                f'<b>+{dist:.0f}%</b><s>завал</s></span>')
    else:
        out += '<span class="fr-zn off"><i>↑</i><s>сверху чисто</s></span>'

    if below:
        z = max(below, key=lambda z: float(z["price"]))
        dist = (1 - float(z["price"]) / price) * 100
        t = int(z.get("tests") or 0)
        out += (f'<span class="fr-zn dn"><i>↓</i>'
                f'<b>−{dist:.0f}%</b>'
                f'<s>опора{f" · {t}т" if t else ""}</s></span>')
    else:
        out += '<span class="fr-zn off"><i>↓</i><s>опоры нет</s></span>'

    return out

def _card(c: Candidate, idx: int) -> str:
    tone = _tone(c, idx)
    key, base, light = TONE[tone]
    sym = esc(c.symbol.replace("USDT", ""))
    score = int(getattr(c, "score", 0) or 0)

    # c.sector не читается: он приходит из buzz.resolve_sector,
    # а этот модуль семейство не использует. Категория CoinGecko —
    # первичный источник, берём её.
    cats = getattr(c, "categories", None) or []
    sector = esc((cats[0] if cats else "—").lower())

    case = case_key(_flow(c, "case", ""))
    phase_num = int((c.phase or {}).get("num", 0) or 0)
    steps = "".join(
        f'<i class="{"on" if i < phase_num else ""}"></i>' for i in range(4)
    )

    bg_lvl, bg_txt = _background(c)
    bars = "".join(
        f'<i class="{"on" if i < bg_lvl else ""}"></i>' for i in range(3)
    )

    d = card_data(c)
    coords, lx, ly = _spark(d["series"], w=150.0, h=40.0)
    # Ведущая величина карточки — неделя. Дневное изменение внутри
    # импульса скачет и на глаз сообщает меньше, чем форма недели.
    up = d["p7d"] >= 0
    col = "#22E08A" if up else "#FF6B35"

    # veto — список VetoReason, не словарь.
    veto_txt, veto_cls = "чисто", "ok"
    if c.vetoed:
        first = c.veto[0] if c.veto else None
        veto_txt = esc(getattr(first, "label", "") or "вето")
        veto_cls = "bad"

    return f"""
<div class="fr t-{key}" data-coin="{esc(c.symbol)}">
  <div class="fr-in">
    <div class="fr-c fr-c1">
        <span class="fr-lnks">{_links(c)}</span>
        <span class="fr-idx">{idx + 1:02d}</span>
            <a class="fr-sym" href="https://www.tradingview.com/chart/?symbol=BINANCE:{esc(c.symbol)}.P"
            target="_blank" rel="noopener">{sym}</a>
        <span class="fr-sec">{sector}</span>
        <span class="fr-caps">
            <b class="fr-tag">{fmt_cap(d['cap'])}</b>
            <b class="fr-tag gh">{d['ath']:+.0f}% ath</b>
            <b class="fr-tag up">+{d['up']:.0f}% от дна</b>
        </span>
    </div>

    <svg class="fr-ring" viewBox="-32 -32 64 64">
      <circle r="26" fill="none" stroke="#fff" stroke-opacity=".05" stroke-width="3"/>
      <circle r="26" fill="none" stroke="{light}" stroke-width="3" stroke-linecap="round"
              stroke-dasharray="{_arc(score, 26)}" transform="rotate(-90)"/>
      <text class="fr-ring-v" y="6" text-anchor="middle">{score}</text>
      <text class="fr-ring-l" y="44" text-anchor="middle">SCORE</text>
    </svg>

    <div class="fr-c">
      <span class="fr-k">ПАТТЕРН</span>
      <span class="fr-chip">{esc(CASE_RU.get(case, case) or "—")}</span>
      <span class="fr-k">ФАЗА</span>
      <span class="fr-steps">{steps}</span>
    </div>

    <div class="fr-c fr-vol">
      <span class="fr-k">ОБЪЁМ · К МЕДИАНЕ 30</span>
      {_vol_rows(d)}
    </div>

    <div class="fr-c fr-price">
      <span class="fr-k">ЦЕНА · 7Д</span>
      <span class="fr-big {'up' if up else 'dn'}">{d['p7d']:+.1f}%</span>
      <svg viewBox="0 0 150 40" preserveAspectRatio="none">
        <defs>
          <linearGradient id="fg{idx}" x1="0" y1="1" x2="0" y2="0">
            <stop offset="0" stop-color="{col}" stop-opacity="0"/>
            <stop offset="1" stop-color="{col}" stop-opacity=".22"/>
          </linearGradient>
        </defs>
        <polygon points="{coords} 150,40 0,40" fill="url(#fg{idx})"/>
        <polyline points="{coords}" fill="none" stroke="{col}"
                  stroke-width="1.5" vector-effect="non-scaling-stroke"/>
        <circle cx="{lx:.0f}" cy="{ly:.0f}" r="2.6" fill="{col}"/>
      </svg>
      <span class="fr-legs">
        <i>1д <b class="{'up' if d['p1d'] >= 0 else 'dn'}">{d['p1d']:+.0f}%</b></i>
        <i>3д <b class="{'up' if d['p3d'] >= 0 else 'dn'}">{d['p3d']:+.0f}%</b></i>
      </span>
    </div>

    <div class="fr-c">
      <span class="fr-k">ФАНДИНГ</span>
      {_fund_bar(d['fund'])}
      <span class="fr-k">R:R</span>
      <span class="fr-rr">1:{float(getattr(c, 'rr', 0) or 0):.1f}</span>
    </div>

    <div class="fr-c">
      <span class="fr-k">ЗОНЫ</span>
      {_zones(c)}
    </div>

    <div class="fr-c">
      <span class="fr-k">ВЕТО</span>
      <span class="fr-veto {veto_cls}">{veto_txt}</span>
      <span class="fr-k">ФОН</span>
      <span class="fr-bg">{bars}<b>{bg_txt}</b></span>
    </div>

    <div class="fr-c">
      <span class="fr-k">ГОРИЗОНТ</span>
      {_horizon(c)}
      <span class="fr-k">ИМПУЛЬС</span>
      {_impulse(c)}
    </div>
    {_state_row(c)}
  </div>
</div>"""


def render_flow_report(candidates: list[Candidate]) -> str:
    """Панель отчёта FLOW. Открывается кликом по ленте стратегии."""
    items = flow_order(candidates)
    if not items:
        body = '<div class="fr-empty">в этом прогоне flow не сработал</div>'
    else:
        body = "".join(_card(c, i) for i, c in enumerate(items))

    tail = (f'<div class="fr-tail">↓ ещё {len(items) - 12} монет</div>'
            if len(items) > 12 else "")

    return f"""
<div class="pane fr-pane" data-pane="strat:flow">
  <div class="pane-hd">
    <button class="pane-back">← НАЗАД</button>
    <span class="pane-t">FLOW · КТО ДВИГАЕТ РЫНОК</span>
    <span class="pane-c">{len(items)}</span>
    <span class="pane-n">сортировка по score · вето не скрыто, помечено цветом</span>
  </div>
  <div class="fr-list">{body}{tail}</div>
</div>"""
