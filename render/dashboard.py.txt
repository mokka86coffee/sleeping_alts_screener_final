"""Дашборд как единственный экран отчёта.

Плашки кликабельны: каждая открывает таблицу своего среза, строка таблицы —
модалку с полной карточкой монеты. Стили и поведение держатся внутри файла,
чтобы не разносить правки по всему пакету.
"""

from __future__ import annotations

from core.models import Candidate, RunSnapshot
from render.card import render_card
from render.theme import esc


# ─────────────────────────────────────────────────────────────
# Отбор срезов
# ─────────────────────────────────────────────────────────────
def _num(c: Candidate, key: str, default: float = 0.0) -> float:
    try:
        return float((c.raw or {}).get(key) or default)
    except (TypeError, ValueError):
        return default

def _get(obj, key: str, default=None):
    """Читает поле и у словаря, и у датакласса."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)

def _actionable(c: Candidate) -> bool:
    lv = getattr(c.strategy, "levels", None)
    return bool(lv and getattr(lv, "entry", 0) > 0)


def _tradable(c: Candidate) -> bool:
    return bool(getattr(c, "tradable", False))


def build_slices(candidates: list[Candidate], snapshot: RunSnapshot) -> list[dict]:
    """Срезы дашборда. Каждый становится плашкой и таблицей."""
    # =====================================================================
    #          ОБЪЁМЫ · вёрстка по новому дизайну, данные пока статикой.
    #          TODO: добавить функционал из прошлой реализации (блок surge):
    #            · крупное число — количество монет, прошедших порог
    #            · порог в подписи: было ≥3×, теперь ≥4× — согласовать с детектором
    #            · выноска "> ×4" и подпись "на дневке" — сейчас константы
    #            · спарклайн — источник данных не определён
    #            · ТРИ МОНЕТЫ ВНИЗУ ПЛАШКИ = ТОП-3 из таблицы прошлой реализации
    #              (сортировка по множителю объёма, формат "тикер ×N.N",
    #               в старом отчёте это первые три строки списка "АНОМАЛЬНЫЕ ОБЪЁМЫ")
    surge = [c for c in candidates if c.surge]
    # =====================================================================

    # =====================================================================
    # СОЦСЕТИ · ВСПЛЕСК ВНИМАНИЯ
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `viral`) — как в блоке
    # "объёмы": сначала верстаем, данные подключаем отдельным шагом.
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · число в центре кольца — количество монет в срезе `viral`
    #   · заполнение кольца — доля/прогресс, источник не определён,
    #     в старой реализации такого индикатора не было
    #   · пилюля внизу ("pepe ×9.2") — ЛИДЕР СПИСКА из таблицы прошлой
    #     реализации: первая строка по множителю упоминаний,
    #     формат "тикер ×N.N"
    #   · порог всплеска в старом блоке — уточнить и вынести в подпись,
    #     если решим её показывать
    #
    # Клик по плашке ведёт в таблицу этого среза (общее правило дашборда).
    # Старый код `viral` не трогаем и не удаляем.
    # =====================================================================
    viral = [c for c in candidates if c.is_viral]
    # =====================================================================

    # =====================================================================
    # ПАТТЕРНЫ · 4 СТРОКИ
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ — как в блоках "объёмы"
    # и "соцсети": сначала вёрстка, данные подключаем отдельным шагом.
    #
    # СОСТАВ СТРОК (порядок сверху вниз) и источники:
    #   1) taiko   ← срез `taiko`   (HTF reversal)      — данные есть
    #   2) dexe    ← срез `dexe`    (post-pump)         — данные есть
    #   3) strong  ← бывш. "база",  (high-confidence)   — ПЕРЕИМЕНОВАНО
    #   4) good    ← бывш. "vortex",(tradable setups)   — ПЕРЕИМЕНОВАНО
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
    #   · цвет шкалы и числа закреплён за строкой, из макета, не меняем
    #
    # Подпись "после фильтра качества базы" — ОСТАВЛЯЕМ КАК ЕСТЬ, константа.
    # Клик по строке ведёт в таблицу соответствующего среза.
    # Старый код срезов не трогаем и не удаляем.
    # ==================================================
    taiko = [c for c in candidates if c.taiko]
    dexe = [c for c in candidates if c.dexe]
    base = [c for c in candidates if (c.phase or {}).get("num", 0) == 2]
    # =====================================================================

    # =====================================================================
    # РИСК · ПОД ВЕТО
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `vetoed`) — как в
    # блоках "объёмы", "соцсети", "паттерны": сначала вёрстка, данные
    # подключаем отдельным шагом.
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · крупное число + подпись "монет" — размер среза `vetoed`
    #   · разбивка внизу: squeeze / фандинг / ликвид. — счётчики по
    #     причинам вето из прошлой реализации; сумма причин может быть
    #     больше общего числа (у монеты бывает несколько вето)
    #   · боковые дуги слева/справа (squeeze, фандинг) — индикаторы
    #     давления по этим причинам, шкала из макета
    #   · орбита/точка по кольцу — декор, данными не управляется
    #
    # КАПСУЛА НАД БЛОКОМ:
    #   "13% · доля выборки" — доля отсеянных вето от общего числа
    #   просканированных монет (all / total прошлой реализации).
    #   Сейчас константа, стрелка ведёт в таблицу среза.
    #
    # Клик по плашке ведёт в таблицу этого среза (общее правило дашборда).
    # Старый код `vetoed` не трогаем и не удаляем.
    # =====================================================================
    vetoed = [c for c in candidates if c.vetoed]
    # =====================================================================

    # =====================================================================
    # СЕТАПЫ · "сетапы 6 из 176 · rr ≥ 2"
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `setups`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · заголовок "сетапы N из M · rr ≥ K" — N: размер среза,
    #     M: общее число просканированных монет, K: порог risk/reward
    #   · список строк — ТОП-3 сетапа из таблицы прошлой реализации,
    #     сортировка по rr по убыванию
    #   · в строке: тикер, под ним — вход / стоп / цель мелким шрифтом,
    #     кольцевой индикатор + значение "1:X.X" (risk/reward),
    #     справа — "вход 0.XXXX"
    #   · заполнение кольца — нормировка rr по максимуму в списке
    #
    # Клик по строке ведёт в модалку монеты, клик по плашке — в таблицу среза.
    # Старый код `setups` не трогаем и не удаляем.
    # =====================================================================
    setups = [c for c in candidates if _tradable(c)]
    # =====================================================================

    # =====================================================================
    # ИМПУЛЬС ЗА ЧАС
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (срез `hourly`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · крупная цифра по центру — количество монет в срезе `hourly`
    #   · подпись под цифрой "рост ≥ X% за час" — порог детектора
    #   · гистограмма снизу — распределение по часам суток;
    #     подсвеченный столбец = текущий час.
    #     ВНИМАНИЕ: в прошлой реализации почасовой истории нет —
    #     источник данных для гистограммы нужно определить отдельно,
    #     до этого рисуем статикой по макету
    #   · нижняя подпись "пик N · след. срез" — уточнить смысл
    #
    # Клик по плашке ведёт в таблицу этого среза.
    # Старый код `hourly` не трогаем и не удаляем.
    # =====================================================================
    hourly = [c for c in candidates if _num(c, "rvol_1h") >= 3.0]
    # =====================================================================

    # =====================================================================
    # СЕКТОРА ЗА 24 ЧАСА
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (блок `_sectors`).
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · 5 строк — сектора, отсортированные по изменению за 24ч
    #     (сверху лучший, снизу худший)
    #   · в строке: название сектора, горизонтальный бар, значение "+X.X%"
    #   · длина бара — модуль изменения, нормировка по максимуму
    #   · цвет: рост — зелёный, падение — оранжевый/красный, из макета
    #   · количество строк фиксировано (5): топ-N и анти-топ по макету
    #
    # Клик по строке — фильтр таблицы по сектору (если был в прошлой
    # реализации; иначе не кликабельно).
    # Старый код `_sectors` не трогаем и не удаляем.
    # =====================================================================
    planned = [c for c in candidates if _actionable(c)]
    # =====================================================================

    return [
        {"id": "all", "label": "ВСЯ ВЫБОРКА", "note": "все монеты прогона, без фильтров",
         "items": list(candidates), "tone": "neu", "size": "sm"},
        {"id": "surge", "label": "ОБЪЁМЫ АНОМАЛЬНЫЕ", "note": "против среднего за 30 дней",
         "items": surge, "tone": "vol", "size": "lg"},
        {"id": "viral", "label": "ВСПЛЕСК ВНИМАНИЯ", "note": "внимание и объём вместе",
         "items": viral, "tone": "soc", "size": "lg"},
        {"id": "taiko", "label": "TAIKO", "note": "разворот на старшем ТФ",
         "items": taiko, "tone": "pat", "size": "sm"},
        {"id": "dexe", "label": "DEXE", "note": "отскок после дампа",
         "items": dexe, "tone": "pat", "size": "sm"},
        {"id": "base", "label": "БАЗА", "note": "накопление, фаза 2",
         "items": base, "tone": "pat", "size": "sm"},
        {"id": "setups", "label": "СЕТАПЫ К РАБОТЕ", "note": "R:R подтверждён, вето пройдено",
         "items": setups, "tone": "act", "size": "lg"},
        {"id": "hourly", "label": "ИМПУЛЬС ЗА ЧАС", "note": "RVOL 1H ≥ 3",
         "items": hourly, "tone": "vol", "size": "sm"},
        {"id": "planned", "label": "ЕСТЬ ПЛАН", "note": "уровни построены",
         "items": planned, "tone": "neu", "size": "sm"},
        {"id": "vetoed", "label": "ПОД ВЕТО", "note": "отсеяны фильтром риска",
         "items": vetoed, "tone": "veto", "size": "sm"},
    ]


# ─────────────────────────────────────────────────────────────
# Плашки
# ─────────────────────────────────────────────────────────────
def _spark(items: list[Candidate]) -> str:
    """Мини-гистограмма по скорам среза."""
    if not items:
        return ""
    top = sorted(items, key=lambda c: -c.score)[:14]
    bars = "".join(
        f'<i style="height:{max(8, min(100, int(c.score)))}%"></i>' for c in top
    )
    return f'<div class="dw-spark">{bars}</div>'


def _tile(s: dict) -> str:
    empty = " empty" if not s["items"] else ""
    lead = sorted(s["items"], key=lambda c: -c.score)[:3]
    chips = "".join(
        f'<span class="dw-chip">{esc(c.symbol.replace("USDT", ""))}</span>'
        for c in lead
    )
    return f"""
<button class="dw t-{s['tone']} s-{s['size']}{empty}" data-slice="{esc(s['id'])}">
  <span class="dw-l">{esc(s['label'])}</span>
  <span class="dw-v">{len(s['items'])}</span>
  <span class="dw-n">{esc(s['note'])}</span>
  {_spark(s['items'])}
  <span class="dw-chips">{chips}</span>
</button>"""


def _regime(snapshot: RunSnapshot) -> str:
    # =====================================================================
    # ВРЕМЕННО СКРЫТ (перенос на новый дашборд).
    # Блок "режим рынка" больше не выводится отдельной плашкой: он переехал
    # в капсулу шапки справа вверху и на текущем этапе свёрстан СТАТИКОЙ
    # по макету. Код namеренно сохранён целиком — вернёмся к нему, когда
    # будем подключать капсуле реальные данные.
    #
    # ЧТО ЗДЕСЬ ЕСТЬ И ЧТО УЧЕСТЬ ПРИ ВОЗВРАТЕ:
    #
    #  1) ИСТОЧНИК ДАННЫХ — snapshot.market_regime. Это обычный dict,
    #     не типизированная структура, ключи: label / appetite / text.
    #     Все обращения идут через .get(...) с дефолтом "—", то есть по
    #     факту любое поле может отсутствовать. При переносе решить:
    #     показывать капсулу с прочерками или скрывать её целиком.
    #
    #  2) LABEL ПРЕВРАЩАЕТСЯ В CSS-КЛАСС.
    #     "risk-off" -> lower() + удаление "-" и " " -> "riskoff" -> "r-riskoff".
    #     Значит в css лежит отдельное правило под каждое значение метки,
    #     и незнакомая метка молча останется без стиля (без ошибки).
    #     При вёрстке капсулы набор допустимых label зафиксировать явно.
    #
    #  3) APPETITE выводится как "n/5" — знаменатель 5 захардкожен прямо
    #     в разметке, в данных его нет. Если шкала изменится, править тут.
    #
    #  4) TEXT — длинное текстовое пояснение к режиму. В капсулу макета
    #     оно не помещается. Решить отдельно: тултип, строка ниже,
    #     или не показывать вовсе.
    #
    #  5) BTC.D присутствует в макете капсулы, но в market_regime его НЕТ.
    #     Источник предстоит найти отдельно (вероятно, другой раздел
    #     snapshot либо внешний провайдер).
    # =====================================================================
    reg = getattr(snapshot, "market_regime", None) or {}
    label = str(reg.get("label", "—"))
    appetite = reg.get("appetite", "—")
    text = str(reg.get("text", ""))
    tone = label.lower().replace("-", "").replace(" ", "") or "neutral"
    return f"""
<div class="reg r-{esc(tone)}">
  <div class="reg-l">{esc(label)}</div>
  <div class="reg-a">{esc(str(appetite))}<i>/5</i></div>
  <div class="reg-d">{esc(text)}</div>
</div>"""


def _sectors(snapshot: RunSnapshot) -> str:
    rows = getattr(snapshot, "sectors", None) or []
    if not rows:
        return ""
    peak = max(
        (abs(float(_get(r, "avg_change_24h", 0) or 0)) for r in rows), default=1
    ) or 1
    out = ""
    for r in rows[:8]:
        name = str(_get(r, "sector", "") or "")
        val = float(_get(r, "avg_change_24h", 0) or 0)
        width = min(100, abs(val) / peak * 100)
        cls = "up" if val >= 0 else "dn"
        out += (
            f'<button class="sct-row" data-slice="sector:{esc(name)}">'
            f'<span class="sct-n">{esc(name)}</span>'
            f'<span class="sct-bar"><i class="{cls}" style="width:{width:.0f}%"></i></span>'
            f'<span class="sct-v {cls}">{val:+.1f}%</span></button>'
        )
    return f'<div class="secs"><div class="blk-h">СЕКТОРА</div>{out}</div>'


def _funnel(snapshot: RunSnapshot) -> str:
    # =====================================================================
    # ВОРОНКА · "путь отбора 176 → 6"
    # Вёрстка по новому дизайну, значения пока СТАТИКА по макету.
    # ФУНКЦИОНАЛ БЕРЁМ ИЗ ПРОШЛОЙ РЕАЛИЗАЦИИ (блок `_funnel`).
    #
    # СОСТАВ: 6 узлов-кругов слева направо, каждый — этап отсева:
    #   176 (все монеты) → 58 → 41 → 18 → 11 → 6 (финал)
    #   под каждым кругом — подпись этапа мелким шрифтом.
    #
    # ЧТО ПРЕДСТОИТ ПОДКЛЮЧИТЬ:
    #   · числа в кругах — счётчики этапов из прошлей реализации
    #   · ПЕРВЫЙ УЗЕЛ = скрытый срез `all` (общее число просканированных);
    #     отдельной плашки у него больше нет, только этот узел
    #   · скрытый срез `planned` также вынесен в узел воронки
    #   · подпись сверху "путь отбора N → M" — первый и последний счётчик
    #   · последний узел выделен акцентным цветом — финальный отбор
    #   · заполнение обводки круга — доля от предыдущего этапа
    #
    # Клик по узлу ведёт в таблицу соответствующего этапа.
    # Старый код `_funnel` не трогаем и не удаляем.
    # =====================================================================
    rows = getattr(snapshot, "funnel", None) or []
    if not rows:
        return ""
    total = max((int(_get(r, "count", 0) or 0) for r in rows), default=1) or 1
    clickable = {"есть план": "planned", "после вето": "vetoed", "к работе": "setups"}
    out = ""
    for r in rows:
        name = str(_get(r, "label", None) or _get(r, "name", "") or "")
        count = int(_get(r, "count", 0) or 0)
        pct = count / total * 100
        target = clickable.get(name.lower().strip())
        tag = "button" if target else "div"
        attr = f' data-slice="{target}"' if target else ""
        out += (
            f'<{tag} class="fn-node{" hot" if target else ""}"{attr}>'
            f'<span class="fn-v">{count}</span>'
            f'<span class="fn-l">{esc(name)}</span>'
            f'<span class="fn-p">{pct:.0f}%</span></{tag}>'
        )
    return f'<div class="fn"><div class="blk-h">ПУТЬ ОТБОРА</div><div class="fn-in">{out}</div></div>'


# ─────────────────────────────────────────────────────────────
# Таблицы срезов
# ─────────────────────────────────────────────────────────────
def _table(s: dict) -> str:
    if not s["items"]:
        body = '<div class="tb-empty">В этом срезе монет нет</div>'
    else:
        rows = ""
        for c in sorted(s["items"], key=lambda x: -x.score):
            ch = _num(c, "ch_24h")
            cls = "up" if ch >= 0 else "dn"
            rvol = _num(c, "rvol_1h")
            lv = getattr(c.strategy, "levels", None)
            rr = getattr(c, "rr", 0) or 0
            rr_txt = f"{rr:.1f}" if rr else "—"
            rows += (
                f'<tr data-coin="{esc(c.symbol)}">'
                f'<td class="tb-s">{esc(c.symbol.replace("USDT", ""))}</td>'
                f'<td class="tb-sc"><i style="--p:{min(int(c.score), 100)}"></i>{c.score}</td>'
                f'<td class="{cls}">{ch:+.1f}%</td>'
                f'<td>{rvol:.1f}×</td>'
                f'<td>{rr_txt}</td>'
                f'<td class="tb-ph">{esc(str((c.phase or {}).get("label", "—")).lower())}</td>'
                f'</tr>'
            )
        body = (
            '<table class="tb"><thead><tr>'
            '<th>МОНЕТА</th><th>SCORE</th><th>24H</th><th>RVOL</th><th>R:R</th><th>ФАЗА</th>'
            f'</tr></thead><tbody>{rows}</tbody></table>'
        )
    return f"""
<div class="pane" data-pane="{esc(s['id'])}">
  <div class="pane-hd">
    <button class="pane-back">← НАЗАД</button>
    <span class="pane-t">{esc(s['label'])}</span>
    <span class="pane-c">{len(s['items'])}</span>
    <span class="pane-n">{esc(s['note'])}</span>
  </div>
  {body}
</div>"""


def _sector_panes(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    rows = getattr(snapshot, "sectors", None) or []
    out = ""
    for r in rows[:8]:
        name = str(_get(r, "sector", "") or "")
        items = [c for c in candidates if (c.sector or "OTHER") == name]
        out += _table({
            "id": f"sector:{name}", "label": f"СЕКТОР · {name}",
            "note": "все монеты сектора", "items": items,
        })
    return out


def _modals(candidates: list[Candidate]) -> str:
    """Карточки монет: рендерятся один раз, показываются по клику."""
    out = ""
    for c in candidates:
        out += (
            f'<div class="modal" data-coin="{esc(c.symbol)}">'
            f'<div class="modal-bd"></div>'
            f'<div class="modal-in">'
            f'<button class="modal-x">✕</button>'
            f'{render_card(c)}</div></div>'
        )
    return out


# ─────────────────────────────────────────────────────────────
# Сборка
# ─────────────────────────────────────────────────────────────
def render_dashboard_page(candidates: list[Candidate], snapshot: RunSnapshot) -> str:
    slices = build_slices(candidates, snapshot)
    tiles = "".join(_tile(s) for s in slices)
    panes = "".join(_table(s) for s in slices) + _sector_panes(candidates, snapshot)

    return f"""
<div class="screen" id="dash">
  <div class="dgrid">{tiles}</div>
  <div class="drow">{_regime(snapshot)}{_sectors(snapshot)}</div>
  {_funnel(snapshot)}
</div>
<div class="screen" id="panes">{panes}</div>
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
    panes.classList.add('on');
    window.scrollTo(0, 0);
  }

  function backToDash() {
    panes.classList.remove('on');
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
    var tile = e.target.closest('[data-slice]');
    if (tile) { showPane(tile.getAttribute('data-slice')); return; }

    if (e.target.closest('.pane-back')) { backToDash(); return; }

    if (e.target.closest('.modal-x') || e.target.closest('.modal-bd')) {
      closeCoin(); return;
    }

    var row = e.target.closest('tr[data-coin]');
    if (row) { openCoin(row.getAttribute('data-coin')); }
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (document.querySelector('.modal.on')) { closeCoin(); }
    else if (panes.classList.contains('on')) { backToDash(); }
  });
})();
</script>"""
