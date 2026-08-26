"""Пульс: показания монет — рабочее окно неделя + архив 30 дней.

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

Путь к файлу держится здесь, а не в core_config, по той же причине, что
у manual_fields и unlocks: это собственные данные модуля, а не настройка
поведения.
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core_models import Candidate
from sources_storage import ensure_dirs, write_atomic

# Файл лежит рядом с модулем и ходит вместе с кодом.
PULSE_PATH = Path(__file__).resolve().parent / "pulse.json"

# Глубина рабочего окна. Неделя ([stated] 24.08: «окно с 48ч до
# недели, дальше в архив») — при часовом прогоне ~168 снимков:
# хватает на ретро-проверки внутри недели (случай сквиза 19.08,
# когда среда выпала из 48ч, больше не повторится). Всё старше
# уезжает в АРХИВ (ниже), не выбрасывается.
WINDOW_HOURS = 168

# Потолок на монету. Неделя часовых прогонов с запасом; защита от
# отладочных минутных циклов остаётся — потолок отрезает лишнее.
MAX_POINTS = 200

# ── Архив пульса ──
# Точки старше рабочего окна доливаются в дневные файлы
# pulse_archive/ГГГГ-ММ-ДД.jsonl.gz (строка = {"sym": ..., точка}).
# Дозапись — конкатенацией gzip-членов: это валидный gzip, читается
# одним потоком. Закрытые дни больше не меняются — git хранит один
# блоб на день (~сотни КБ). Ротация: файлы старше ARCHIVE_DAYS
# удаляются при записи ([stated]: «архив хранит до 30 дней, иначе
# гит меня выкинет»). Честная оговорка: история git помнит и
# удалённые блобы, репозиторий прирастает ~5–10 МБ в месяц навсегда;
# если станет тесно — архив переезжает в output/ одной строкой пути.
ARCHIVE_DIR = Path(__file__).resolve().parent / "pulse_archive"
ARCHIVE_DAYS = 30

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


def _utc_hour(ts: int | float) -> int | None:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).hour
    # TypeError в списке не для красоты: если в t попадёт строка,
    # fromtimestamp падает именно им, и без него одна битая метка
    # уронила бы запись всей точки.
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def _utc_dow(ts: int | float) -> int | None:
    try:
        return datetime.fromtimestamp(ts, tz=timezone.utc).weekday()
    except (OverflowError, OSError, TypeError, ValueError):
        return None


def snapshot(c: Candidate) -> dict:
    """Один снимок показаний монеты.

    Берём только то, что меняется за часы. Глубина от пика жизни, доля
    инсайдеров, расписание разлоков сюда не идут: они не успевают
    измениться между прогонами, и хранить их значило бы копировать
    неизменное сорок восемь раз подряд.
    """
    raw = c.raw or {}
    ts = round(_now())
    out = {"t": ts}

    # ── Окно суток и день недели (разбор 26.08) ──
    # Оба разгона августа — ONG 19-го и BTR 26-го — пришлись на
    # азиатское окно, оба в среду. Две точки ничего не доказывают,
    # но проверить это можно только на архиве, а для архива величину
    # надо начать писать СЕЙЧАС. Две строки на точку, сети ноль.
    #
    # Границы окон грубые и перекрываются намеренно: рынки не
    # открываются по звонку, а ликвидность перетекает. Задача поля —
    # различить «кто-то торгует» и «не торгует никто», а не расписать
    # биржевые сессии.
    hour = _utc_hour(ts)
    if hour is not None:
        out["hour"] = hour
        out["dow"] = _utc_dow(ts)          # 0 — понедельник
        win = []
        if 0 <= hour < 8:
            win.append("asia")
        if 6 <= hour < 16:
            win.append("eu")
        if 13 <= hour < 21:
            win.append("us")
        out["sess"] = "+".join(win) if win else "dead"

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
        ("basis", raw.get("basis_pct")),
        ("spot_share", raw.get("spot_ratio")),
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

    # Тот же вортекс, что рисует карточка: intraday.vortex, часовой
    # vortex_cross() из analytics_intraday.py. Разбор ONG 21 августа —
    # именно этот индикатор сближался несколько прогонов подряд ДО
    # разворота, но раньше его нигде не сохраняли между прогонами:
    # vi_p/vi_m выше — другой расчёт (4h-фаза), vx_dir ниже — третий
    # (дневной VortexState из ядра FLOW, и только если оно сработало).
    # Имена с префиксом ivx_, чтобы не столкнуться с этими двумя.
    ivx = (raw.get("intraday") or {}).get("vortex") or {}
    n = _num(ivx.get("vi_plus"))
    if n is not None:
        out["ivx_p"] = round(n, 4)
    n = _num(ivx.get("vi_minus"))
    if n is not None:
        out["ivx_m"] = round(n, 4)
    n = _num(ivx.get("spread"))
    if n is not None:
        out["ivx_spread"] = round(n, 4)
    if ivx.get("dir"):
        out["ivx_dir"] = str(ivx["dir"])

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
        ("oi_cycles", oi.get("cycles")),
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
    # Корзина детекторов (перенос из копитрейдинга: «корзина вместо
    # одного источника»): сколько подкейсов FLOW сработало разом, а не
    # только победитель. Пишется только при FLOW — как весь контекст.
    fired = len(((c.flow or {}).get("cases")) or {})
    if fired:
        out["flow_fired"] = fired
    return out


def _archive_write(spill: dict[str, list[str]]) -> None:
    """Долить строки в дневные .jsonl.gz и удалить файлы старше
    ARCHIVE_DAYS. Дозапись — конкатенацией gzip-членов (валидна для
    чтения одним потоком); ошибка молча глотается, как у пульса."""
    if not spill:
        _rotate_archive()
        return
    try:
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        for day, lines in spill.items():
            blob = gzip.compress(("\n".join(lines) + "\n").encode("utf-8"))
            with open(ARCHIVE_DIR / f"{day}.jsonl.gz", "ab") as f:
                f.write(blob)
    except OSError:
        return
    _rotate_archive()


def _rotate_archive() -> None:
    """Стереть дневные файлы старше ARCHIVE_DAYS ([stated]: держим
    до 30 дней, иначе репозиторий распухнет)."""
    try:
        edge = (datetime.now(timezone.utc).date()
                - timedelta(days=ARCHIVE_DAYS)).isoformat()
        for f in ARCHIVE_DIR.glob("*.jsonl.gz"):
            if f.stem.split(".")[0] < edge:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def load_archive(days_back: int = ARCHIVE_DAYS) -> dict[str, list[dict]]:
    """История из архива за N дней: символ → точки по возрастанию t.
    Для ретро-проверок (С-4, С-5, Р-26, Р-9): склейка с рабочим окном
    — read_history(). Битые строки и файлы пропускаются молча."""
    out: dict[str, list[dict]] = {}
    if not ARCHIVE_DIR.exists():
        return out
    edge = (datetime.now(timezone.utc).date()
            - timedelta(days=days_back)).isoformat()
    for f in sorted(ARCHIVE_DIR.glob("*.jsonl.gz")):
        if f.stem.split(".")[0] < edge:
            continue
        try:
            text = gzip.open(f, "rt", encoding="utf-8").read()
        except (OSError, EOFError):
            continue
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            sym = row.pop("sym", None)
            if sym:
                out.setdefault(sym, []).append(row)
    for pts in out.values():
        pts.sort(key=lambda p: p.get("t") or 0)
    return out


def read_history(symbol: str, days_back: int = ARCHIVE_DAYS) -> list[dict]:
    """Архив + рабочее окно одной лентой для одной монеты."""
    pts = load_archive(days_back).get(symbol, [])
    pts += _load().get(symbol) or []
    pts.sort(key=lambda p: p.get("t") or 0)
    return pts


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

    spill: dict[str, list[str]] = {}   # дата → строки jsonl для архива

    def _spill(sym: str, p: dict) -> None:
        t = _num(p.get("t"))
        if t is None:
            return
        day = datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%d")
        spill.setdefault(day, []).append(
            json.dumps({"sym": sym, **p}, ensure_ascii=False))

    live_syms = {getattr(c, "symbol", "") for c in candidates}
    for c in candidates:
        if not getattr(c, "symbol", ""):
            continue
        keep: list[dict] = []
        for p in (data.get(c.symbol) or []):
            t = _num(p.get("t"))
            if t is None:
                continue
            if t >= edge:
                keep.append(p)
            else:
                _spill(c.symbol, p)
        keep.append(snapshot(c))
        data[c.symbol] = keep[-MAX_POINTS:]

    # Монеты, выпавшие из выборки: их хвост тоже уходит в архив,
    # а не в мусор — иначе история рвётся на смене состава.
    for sym in list(data.keys()):
        if sym not in live_syms:
            for p in data[sym]:
                _spill(sym, p)
            del data[sym]

    _archive_write(spill)

    payload = {
        "_meta": {
            "what": "показания монет за последнюю неделю, шаг — прогон; "
                    "старше — в pulse_archive/ (до 30 дн)",
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
# vol_1h/vol_4h/rvol_1h убраны: они мерят возраст текущего бара, а не
# рынок, и дельта по ним отвечает не на тот вопрос (см. Ч-2 тех.долга).
# funding и oi_held добавлены — их снимок уже пишет, дельты не было.
DELTA_KEYS = (
    "price", "vol_1d", "atr_pct", "funding",
    "up_low", "buy_share", "oi_x", "oi_held", "oi_usd", "vx_strength",
    # Тренд перекоса перп/спот: растёт доля спота — приходит реальный
    # покупатель; падает при растущей цене — едут на одном плече.
    "spot_share",
    "rel_vol", "score",
    # Спред часового вортекса карточки — непрерывная величина, а не
    # только флип: разбор ONG 21 августа, VI+ формально ещё выше VI−
    # несколько прогонов подряд, но разрыв заметно сжимался. Дельта
    # ловит СБЛИЖЕНИЕ до флипа, а не только сам факт смены стороны.
    "ivx_spread",
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

    for name, ref in (("prev", pts[-2]), ("h6", _pick(pts, 6)),
                      ("h24", _pick(pts, 24)), ("h168", _pick(pts, 168))):
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

    # Согласованность трёх окон (перенос из оценки трейдеров: верить
    # тому, кто держится на 24 часах, неделе и месяце разом). Наши
    # горизонты: шесть часов, сутки, неделя. Совпадение ЗНАКА хода
    # цены на всех трёх сильнее любого одного; поле пишется только
    # при полном комплекте и единогласии.
    signs = []
    for span in ("h6", "h24", "h168"):
        pp = (out.get(span) or {}).get("price_pct")
        if pp is None or pp == 0:
            signs = []
            break
        signs.append(1 if pp > 0 else -1)
    if len(signs) == 3 and len(set(signs)) == 1:
        out["aligned"] = {"dir": "up" if signs[0] > 0 else "down",
                          "spans": ["h6", "h24", "h168"]}

    # Разворот направления вортекса — единственное, что читается сразу и
    # без величины: сменился знак хода, а не его размер.
    prev_dir = pts[-2].get("vx_dir")
    if prev_dir and now.get("vx_dir") and prev_dir != now["vx_dir"]:
        out["vx_flip"] = {"from": prev_dir, "to": now["vx_dir"]}

    # Тот же флип, но для часового вортекса карточки (ivx_*), а не
    # для дневного FLOW-вортекса выше. Разные источники, разные флаги:
    # смешать их в один значило бы потерять то, какой именно вортекс
    # развернулся — карточка показывает часовой, не дневной.
    prev_ivx = pts[-2].get("ivx_dir")
    if prev_ivx and now.get("ivx_dir") and prev_ivx != now["ivx_dir"]:
        out["ivx_flip"] = {"from": prev_ivx, "to": now["ivx_dir"]}

    return out
