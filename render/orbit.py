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

from core.models import Candidate, RunSnapshot
from render.theme import esc
from render.flow_report import case_key, CASE_RU, _cap, _data


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
    from render.dashboard import (_pick, _num, _tick, FLOW_NODES,
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
    from render.dashboard import _tick

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
    from render.dashboard import (_read_json, _max_vol_ratio,
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
    from render.dashboard import (_read_json, _max_vol_ratio,
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
        # up_from_low / days_from_low — те же поля, что читает
        # _numbers() во flow_report. Для монет, которых нет в текущем
        # прогоне, роста не будет: raw есть только у кандидатов.
        raw = (getattr(c, "raw", None) or {}) if c is not None else {}
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
            "lead": sym.upper() == lead_sym,
            "coin": (c.symbol if c is not None else ""),
            "up": round(float(raw.get("up_from_low") or 0)),
            "updays": int(raw.get("days_from_low") or 0),
            # Числа карточки берём тем же _data(), что кормит карточки
            # отчёта: иначе одна монета показывала бы на орбите и в
            # отчёте разные цифры, и расхождение всплыло бы не сразу.
            **_star_card(c),
        })

    # Лидер рисуется последним — поверх остальных, если рядом окажется сосед
    out.sort(key=lambda s: (s["lead"], s["f"]))
    return out



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
    from render.dashboard import _get, BTC_D

    reg = getattr(snapshot, "market_regime", None) or {}
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
    from render.dashboard import _pick, _num, _tick

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
        "btc": None,     # источника нет — см. docstring и тех долг
        "btcUp": True,
        "dom": BTC_D,    # константа, не прогонное значение
        "series": [],
        "sector": (f"{top[0][0]} {top[0][1]:+.1f}%" if top else "—"),
        "leader": ({"t": _tick(leader),
                    "score": round(getattr(leader, "score", 0) or 0),
                    "case": case_key((leader.flow or {}).get("case", "")) or "—",
                    "cap": _cap(_data(leader)["cap"])} if leader else {}),
        "topVol": top3("surge"),
        "hourly": {"n": len(hourly_items), "list": top3("hourly")},
        "flowVol": _orbit_flow_bigvol(candidates),
    }



def render_orbit(candidates: list[Candidate], snapshot: RunSnapshot,
                 slices: list[dict]) -> str:
    # Отложенный импорт: см. docstring модуля
    from render.dashboard import _pick

    nodes = _orbit_nodes(candidates, snapshot, slices)
    stars = _orbit_stars(candidates)

    # Данные уходят отдельным <script type="application/json">, а не
    # склеиваются в разметку: экранировать нужно только "<".
    blob = json.dumps({"nodes": nodes, "stars": stars,
                       "market": _orbit_market(candidates, snapshot, slices)},
                      ensure_ascii=False).replace("<", "\\u003c")

    # Тот же источник, что читает _head() для капсулы режима: см.
    # docstring _orbit_market — прежде это были несуществующие атрибуты.
    from render.dashboard import BTC_D
    reg = getattr(snapshot, "market_regime", None) or {}
    regime = esc(str(reg.get("label", "RISK-OFF")).upper())
    try:
        appetite = esc(f'{int(reg.get("appetite", 0) or 0)}/5')
    except (TypeError, ValueError):
        appetite = esc("—")
    btc_d = esc(str(BTC_D))
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
    <g id="ob-links"></g>
    <g id="ob-orbit"></g>
    <g id="ob-nodes"></g>

    <!-- Зерно: статичный слой, пересчёта на кадр нет -->
    <rect width="1000" height="640" filter="url(#ob-grain)" opacity=".05"
          style="pointer-events:none"/>
    <ellipse cx="820" cy="140" rx="330" ry="240" fill="#2a2418"
             opacity=".5" filter="url(#ob-soft)"/>

    <!-- Звёзды идут последними, поверх зерна и дымки: стоя раньше них,
         они припудривались обоими слоями и тонули на светлых участках
         ленты. Это передний план сцены, а не часть фона. -->
    <g id="ob-stars"></g>
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

  function starSpot(sym, idx) {
    var h = hash(sym);
    for (var k = 0; k < 60; k++) {
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
        if (Math.hypot(np.x - x, np.y - y) < 128) { nearNode = true; break; }
      }
      /* И не ближе 78 к уже поставленной звезде: без этой проверки две
         соседние подписи накладываются и обе становятся нечитаемыми. */
      var tooClose = false;
      for (var m = 0; m < PLACED.length; m++) {
        if (Math.hypot(PLACED[m].x - x, PLACED[m].y - y) < 78) { tooClose = true; break; }
      }
      if (band > 0.18 && !inCard && !nearNode && !tooClose &&
          x > 95 && x < 905 && y > 115 && y < 545) {
        PLACED.push({ x: x, y: y });
        return { x: x, y: y };
      }
      h = (h * 16777619 + 1) >>> 0;
    }
    /* Место не нашлось: раскладываем по запасной дуге с шагом от индекса,
       иначе все «лишние» звёзды сели бы в одну точку друг на друга. */
    var fb = { x: 120 + (idx % 6) * 130, y: 130 + Math.floor(idx / 6) * 46 };
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
        '<span class="ob-sc-chip">' + (s.pattern || '—') + '</span>' +
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

  function buildStars() {
    var host = document.getElementById('ob-stars');
    STARS.forEach(function (s, idx) {
      var p = starSpot(s.t, idx);
      var f = s.f;                              // свежесть 0..1
      /* Диапазон сжат: было 4..15, стало 3..8. Разброс всё ещё читается,
         но свежая звезда больше не спорит по весу с узлом категории. */
      var r = (s.lead ? 4 : 2.4) + f * 2.1;
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
            var op = 0.18 + rateNorm * 0.5;

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
      var col = s.hot ? '#FFD98A' : '#BFDCFF';
      var grad = s.hot ? 'url(#ob-starG)' : 'url(#ob-starS)';
      var accent = 'url(#ob-starG)';

      /* Ореол ярче и плотнее у центра: именно он читается как свечение,
         лучи только задают характер. */
      g.appendChild(el('circle', { r: r * 2.2,
        fill: s.hot ? 'url(#ob-starH)' : 'url(#ob-starHc)',
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

      var t = el('text', {
        class: 'ob-star-lbl' + (s.lead ? ' lead' : ''),
        x: dx, y: s.up ? -0.6 : 1.8, 'text-anchor': anchor,
        fill: s.hot || s.lead ? '#FFD98A' : '#DCE6F2', opacity: '.95'
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

  /* На мобильных орбиту не просто прячем стилями, а убираем узел из
     документа: скрытый SVG всё равно занимал бы память, а getTotalLength
     и getPointAtLength на display:none элементе в части браузеров
     бросают исключение. Условие то же, что в CSS. */
  if (window.matchMedia('(pointer: coarse)').matches ||
      window.matchMedia('(max-width: 1100px)').matches) {
    orb.remove();
    var blob = document.getElementById('ob-data');
    if (blob) blob.remove();
    return;
  }

  buildArcs();
  buildBack();
  buildDust();
  buildStars();
  build();
  requestAnimationFrame(frame);
})();
</script>
"""
