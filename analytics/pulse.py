"""Пульс: показания каждой монеты за последние двое суток.

Зачем это есть. Всё, что показывает карточка, — уровни: «покупка 1.4»,
«объём ×16», «в диапазоне 93%». Уровень не говорит ничего. Решение
принимается по ИЗМЕНЕНИЮ: «покупка 1.4, час назад была 3.1» — это
сигнал, а «покупка 1.4» — просто число. Между прогонами у проекта не
оставалось ничего, кроме журнала лидеров, поэтому сравнивать было не с
чем, и карточка физически не могла сказать, что происходит сейчас.

Разбор PORTAL и GPS показал цену этого. У обеих в момент выдачи стояло
зелёное «всё хорошо», а падение началось в тот же час. В кадре при этом
были все нужные факты — вортекс шёл вверх тринадцать баров, объём стоял
у исторического рекорда, — но каждый показывал сам себя, и ни один не
показывал, куда он движется.

Чем это НЕ является. Не журнал лидеров: тот держит две недели, пишет
только отобранных и отвечает на вопрос «как часто эта монета всплывает».
Здесь другой срок, другая частота и другой вопрос — «что изменилось за
последние часы». Смешивать их в одном файле значит связать два разных
времени жизни: чистка журнала выбросила бы половину пульса, а частота
пульса раздула бы журнал.

Три правила, и они важнее формата.

1. Пишем ВСЮ выборку, а не только лидеров. Иначе в момент, когда монета
   впервые попадает в журнал — самый интересный момент, — истории у неё
   ноль, и первая же карточка окажется без дельт. Из этого правила
   следует, откуда берутся числа: из метрик кандидата, которые есть у
   каждой монеты, а не из контекста FLOW, которого нет ни у кого вне
   семейства. Контекст добавляется сверху, если он есть.

2. Окно скользящее: последние двое суток, всё старше выбрасывается при
   записи. Это не архив, а короткая память. Дальше двух суток вопрос
   «что изменилось за последние часы» не смотрит, а на длинном сроке уже
   работают столбы карточки.

3. Меньше двух снимков — дельт нет ВООБЩЕ. Отдаётся пустой словарь,
   отрисовка показывает пробел. «Не с чем сравнить» и «не изменилось»
   обязаны выглядеть по-разному: ноль здесь соврал бы ровно так же, как
   ноль в незаполненном разлоке.

Путь к файлу держится здесь, а не в core.config, по той же причине, что
у manual_fields и unlocks: это собственные данные модуля, а не настройка
поведения.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core.models import Candidate
from sources.storage import ensure_dirs, write_atomic

# Файл лежит рядом с модулем и ходит вместе с кодом.
PULSE_PATH = Path(__file__).resolve().parent / "pulse.json"

# Глубина окна. Двое суток — это ~16 снимков при трёхчасовом прогоне и
# ~48 при часовом: хватает и на «прошлый прогон», и на «вчера в это же
# время».
WINDOW_HOURS = 48

# Потолок на монету. Защита от прогонов чаще часа: без него отладочный
# минутный цикл за сутки положит в файл полторы тысячи записей.
MAX_POINTS = 120

_CACHE: dict = {"mtime": None, "data": {}}


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _load() -> dict:
    """Содержимое файла. Любая ошибка означает «истории нет»."""
    try:
        mtime = PULSE_PATH.stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        try:
            raw = json.loads(PULSE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # Битый файл — не повод падать: пульс вспомогательный слой,
            # без него карточка теряет дельты, но остаётся рабочей.
            return _CACHE["data"]
        _CACHE["data"] = {k: v for k, v in raw.items() if not k.startswith("_")}
        _CACHE["mtime"] = mtime
    return _CACHE["data"]


def _num(v):
    """Число или None. Строки и NaN отсекаются здесь, а не в отрисовке."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def snapshot(c: Candidate) -> dict:
    """Один снимок показаний монеты.

    Берём только то, что меняется за часы. Глубина от пика жизни, доля
    инсайдеров, расписание разлоков сюда не идут: они не успевают
    измениться между прогонами, и хранить их значило бы копировать
    неизменное сорок восемь раз подряд.
    """
    raw = c.raw or {}
    out = {"t": round(_now())}

    # Базовый набор — из метрик, они есть у каждой монеты выборки.
    for key, val in (
        ("price", raw.get("price")),
        ("vol_1h", raw.get("vol_x_1h")),
        ("vol_4h", raw.get("vol_x_4h")),
        ("vol_1d", raw.get("vol_x_1d")),
        ("rvol_1h", raw.get("rvol_1h")),
        ("atr_pct", raw.get("atr_pct")),
        ("obv", raw.get("obv_slope")),
        ("funding", raw.get("funding")),
        ("oi_usd", raw.get("oi_usd")),
        ("up_low", raw.get("up_from_low")),
        ("ch_24h", raw.get("ch_24h")),
    ):
        n = _num(val)
        if n is not None:
            out[key] = round(n, 6)

    # Фаза вортекса живёт в метриках у всех, а не только у FLOW.
    vp = raw.get("vortex_4h") or {}
    n = _num(vp.get("vi_plus"))
    if n is not None:
        out["vi_p"] = round(n, 4)
    n = _num(vp.get("vi_minus"))
    if n is not None:
        out["vi_m"] = round(n, 4)

    # Контекст FLOW — сверху и только если он есть. Без этой развилки
    # половина выборки писала бы пустые снимки.
    ctx = (c.flow or {}).get("context") or {}
    flow = ctx.get("flow") or {}
    vortex = ctx.get("vortex") or {}
    oi = ctx.get("oi_hist") or {}
    for key, val in (
        ("buy_share", flow.get("buy_share")),
        ("delta_slope", flow.get("delta_slope")),
        ("vx_strength", vortex.get("strength")),
        ("oi_x", oi.get("x")),
        ("oi_held", oi.get("held_pct")),
        ("rel_vol", ctx.get("rel_vol")),
    ):
        n = _num(val)
        if n is not None:
            out[key] = round(n, 6)

    # Направление вортекса — не число, но без него сила бессмысленна:
    # 0.2 вверх и 0.2 вниз это противоположные состояния.
    if vortex.get("direction"):
        out["vx_dir"] = str(vortex["direction"])
    if c.score:
        out["score"] = int(c.score)
    return out


def record(candidates: list[Candidate], path: Path = PULSE_PATH) -> Path:
    """Дописать снимки по всей выборке и обрезать окно.

    Вызывается раз за прогон, рядом с update_leaders: там у кандидатов
    уже посчитаны метрики, и сеть не нужна вообще.

    Ошибка записи молча проглатывается: пульс не должен ронять прогон,
    ради которого он существует.
    """
    ensure_dirs()
    data = dict(_load())
    edge = _now() - WINDOW_HOURS * 3600

    for c in candidates:
        if not getattr(c, "symbol", ""):
            continue
        pts = [
            p for p in (data.get(c.symbol) or [])
            if _num(p.get("t")) is not None and p["t"] >= edge
        ]
        pts.append(snapshot(c))
        data[c.symbol] = pts[-MAX_POINTS:]

    # Монеты, выпавшие из выборки, дочищаются здесь же: иначе файл растёт
    # вечно за счёт тех, кого больше не считают.
    data = {k: v for k, v in data.items() if v}

    payload = {
        "_meta": {
            "what": "показания монет за последние двое суток, шаг — прогон",
            "why": "карточка сравнивает не уровни, а изменения",
            "window_hours": WINDOW_HOURS,
            "symbols": len(data),
            "written_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        },
        **data,
    }
    try:
        write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=1))
    except OSError:
        return path
    _CACHE["mtime"] = None
    return path


def _pick(pts: list[dict], hours: float) -> dict | None:
    """Ближайший снимок не новее, чем «столько-то часов назад».

    Именно не новее, а не «ближайший по модулю»: при пропущенном прогоне
    сравнение с точкой из будущего дало бы дельту с обратным знаком.
    """
    edge = _now() - hours * 3600
    older = [p for p in pts if _num(p.get("t")) is not None and p["t"] <= edge]
    return older[-1] if older else None


# Величины, по которым считаются разницы. Остальное в снимке лежит для
# будущих потребителей, но в дельты не идёт: разница цены полезна,
# разница фандинга — нет, он и так меняется ступеньками.
DELTA_KEYS = (
    "price", "vol_1h", "vol_4h", "vol_1d", "rvol_1h", "atr_pct",
    "up_low", "buy_share", "oi_x", "oi_usd", "vx_strength", "rel_vol",
    "score",
)


def for_symbol(symbol: str) -> dict:
    """Изменения показаний монеты. Пустой словарь — сравнивать не с чем.

    Отдаём три горизонта: прошлый прогон, шесть часов, сутки. Меньше
    двух точек — ничего, даже нулей.
    """
    pts = (_load() or {}).get(symbol) or []
    if len(pts) < 2:
        return {}

    now = pts[-1]
    out: dict = {"points": len(pts), "age_min": round((_now() - now["t"]) / 60)}

    for name, ref in (("prev", pts[-2]), ("h6", _pick(pts, 6)), ("h24", _pick(pts, 24))):
        if not ref:
            continue
        d = {}
        for key in DELTA_KEYS:
            a, b = _num(now.get(key)), _num(ref.get(key))
            if a is None or b is None:
                continue
            d[key] = round(a - b, 6)
            if key == "price" and b:
                d["price_pct"] = round((a / b - 1) * 100, 2)
        if d:
            d["ago_min"] = round((now["t"] - ref["t"]) / 60)
            out[name] = d

    # Разворот направления вортекса — единственное, что читается сразу и
    # без величины: сменился знак хода, а не его размер.
    prev_dir = pts[-2].get("vx_dir")
    if prev_dir and now.get("vx_dir") and prev_dir != now["vx_dir"]:
        out["vx_flip"] = {"from": prev_dir, "to": now["vx_dir"]}

    return out
