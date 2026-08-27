"""Отслеживание двух выборок: лидер прогона FLOW и аномальные объёмы.

Обе выборки читают уже готовые данные кандидатов (raw["vol_ratio"],
flow, score, price) — без сети. Пишутся одним шагом в конце прогона,
рядом с построением основного отчёта.

Приоритет за FLOW: если монета попадает в обе выборки одновременно —
живёт только в leaders.json, из anomaly_volume.json переносится
(история сохраняется, не создаётся заново). Обратного переноса нет.

«Лидер прогона» — не все монеты со сработавшим FLOW, а одна: та же,
что дашборд подписывает «лидер прогона» в _blk_flow (max по
candidate.score среди сработавших).

«Аномальный объём» — любой кандидат вне лидера, у которого хотя бы
один из пяти ratio ≥ ANOMALY_RATIO_MIN.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core_config import (
    ANOMALY_PATH, ANOMALY_RATIO_MIN, LEADERS_ARCHIVE_PATH,
    LEADERS_MAX_AGE_DAYS, LEADERS_PATH,
)
# Пороги завершения цикла живут в конфиге семейства — там же, где их
# читает сам детектор. Импорт наружу из слоя analytics осознанный:
# альтернатива это две копии одного числа в двух файлах, а они
# однажды разойдутся и никто не заметит. Переехать обоим в
# core/config стоит вместе с прочими LEADERS_*.
from detectors_flow_config import (
    CYCLE_COMPLETE_X, CYCLE_TREND_DONE_X, cycle_done,
)
from core_http import log
from core_models import Candidate, RunSnapshot
from sources_storage import ensure_dirs, write_atomic

# Символ прошлого лидера — иначе streak не отличить от «монета снова
# стала лидером через неделю тишины».
#
# Здесь же счётчик прогонов: без него частота попаданий не считается.
# Пять попаданий за двое суток и пять за двадцать — разные монеты, а
# по одному счётчику hits они неотличимы.
_META_KEY = "_meta"

# ── НАБЛЮДЕНИЕ ЗА ЛИДЕРСТВОМ (27.08) ──
# Раньше от лидерства оставался только `_meta["last_leader"]` — кто был
# лидером вчера в три утра, восстановить было нельзя. Отсюда два
# вопроса без ответа: с какой ЧАСТОТОЙ монета берёт первое место (это
# про момент пампа и про то, находим мы его до или после) и в какое
# ВРЕМЯ суток (крипта торгуется круглосуточно, и час подсказывает, где
# искать причину — корейское окно, европейское утро).
#
# Поэтому каждое лидерство записывается меткой. Ничего на её основе не
# решается: поля не входят в скор, пороги и отбор. Подробности и
# список будущих проверок — в NABLUDENIE_LIDEROV.md.
#
# Окна ВЕЗДЕ скользящие, от момента прогона назад. Календарные сутки
# не годятся: прогон в 00:10 иначе видел бы «вчера» пустым.
LEAD_DAY_HOURS = 24        # окно «за сутки»
LEAD_WINDOW_HOURS = 72     # окно непрерывности: три отрезка по суткам
LEAD_TOP_DAY = 2           # сколько монет показывать в топе за сутки


def _now(snapshot: RunSnapshot) -> datetime:
    """Момент прогона, не отдельный datetime.now() — одна временная
    точка на весь прогон, синхронно со снимком.
    """
    try:
        return datetime.fromisoformat(snapshot.timestamp)
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _is_anomalous(ratios: dict[str, float]) -> bool:
    return any(r >= ANOMALY_RATIO_MIN for r in (ratios or {}).values())


def _merge_max(old: dict[str, float], new: dict[str, float]) -> dict[str, float]:
    """Обновление «только если стало больше» — по каждому масштабу
    отдельно, а не по сумме или последнему значению.
    """
    out = dict(old)
    for label, v in (new or {}).items():
        out[label] = max(out.get(label, 0.0), v)
    return out


# ── Правила входа ────────────────────────────────────────────
# Рост от дна, выше которого вход на выходных не делается даже на
# плоском дне. Пятьдесят процентов — граница из описания стратегии:
# отскок от базы, а не уже состоявшийся разгон.
SKIP_WEEKEND_UP_MAX = 50.0



def _entry_rules(now: datetime, raw: dict, flow: dict) -> dict:
    """Взяли бы позицию по правилам или пропустили, и почему.

    Записывается в момент заведения, а не считается потом: `first_run`
    и рост от дна к следующему прогону уже другие, и восстановить их
    задним числом нечем.

    Пропуск не мешает вести запись. Монета остаётся в журнале и
    наблюдается как обычно — правило влияет только на условный
    портфель, то есть на оценку, а не на само наблюдение.
    """
    drop = (flow.get("context") or {}).get("drop") or {}
    case = str(flow.get("case") or "")

    if drop.get("first_run"):
        return {"skip": "первый разгон"}

    # Пятница считается будним днём: суббота и воскресенье — 5 и 6.
    if now.weekday() >= 5:
        try:
            up = float(raw.get("up_from_low") or 0.0)
        except (TypeError, ValueError):
            up = 0.0
        flat_base = case.endswith("dormant")
        if not (flat_base and up <= SKIP_WEEKEND_UP_MAX):
            return {"skip": "выходные"}

    return {}


def _new_record(
    now: datetime,
    price: float,
    ratios: dict[str, float],
    run_no: int = 0,
    rules: dict | None = None,
) -> dict:
    base = dict(rules or {})
    return {
        **base,
        "first_seen": now.isoformat(),
        # Момент последнего СОБЫТИЯ: срабатывание FLOW либо обновление
        # аномального объёма. По нему считается выбытие.
        #
        # Отдельное поле, а не last_seen, и это не педантизм:
        # tracked_symbols возвращает журнальные монеты в выборку
        # каждый прогон, и last_seen обновляется у всех и всегда.
        # Чистка по нему не сработала бы ни разу — молча, как и
        # положено ошибке этого класса.
        "last_hit": now.isoformat(),
        # Номер прогона, на котором запись заведена. Частота попаданий
        # считается от него: hits / (текущий прогон − since_run).
        # Хранится номер, а не дата, потому что интервал прогонов
        # меняется (--loop с любым --interval), и пересчёт из дат дал
        # бы разное число для одинакового поведения.
        "since_run": run_no,
        # Сколько прогонов монета была лидером (для flow) либо
        # держалась в корзине (для аномалий). Считает ПОПАДАНИЯ, а не
        # непрерывность — этим отличается от streak.
        "hits": 0,
        "entry_price": price,
        "price": price,
        "change_pct": 0.0,
        "max_price": price,
        "max_change_pct": 0.0,
        "min_price": price,
        "min_change_pct": 0.0,
        "vol_ratio": dict(ratios or {}),
        "last_seen": now.isoformat(),
        # ── лидерства: метки и счётчик ──
        # Список меток, по одной на каждое первое место. Не обрезается:
        # при ~50 прогонах в сутки метка около 120 байт даёт меньше
        # 2.5 МБ в год на весь журнал, а искать закономерности по
        # времени можно только на длинном ряде.
        "lead_at": [],
        # Всего лидерств за всю жизнь записи. Растёт вместе со списком
        # и держится отдельно, чтобы не считать длину каждый раз.
        "lead_hits": 0,
    }


def _cycle_up_x(c: Candidate) -> float:
    """Кратность от дна цикла из пейлоада FLOW.

    Читается защитно: у монеты, на которой семейство не отработало,
    словаря может не быть вовсе, и это нормальное состояние, а не
    сбой. Ноль означает «мерки нет» — и тогда проверка порога ниже
    просто не срабатывает. Направление отказа выбрано намеренно:
    запись остаётся, а не выбывает по величине, которой мы не
    получили.
    """
    flow = getattr(c, "flow", None) or {}
    drop = (flow.get("context") or {}).get("drop") or {}
    try:
        from_flow = float(drop.get("up_x") or 0.0)
    except (TypeError, ValueError):
        from_flow = 0.0
    if from_flow > 0:
        return from_flow

    # Запасной путь: рост от минимума окна метрик. Считается для
    # каждой монеты выборки, а журнальные монеты возвращает в неё
    # tracked_symbols — значит величина есть всегда.
    #
    # Окно короче (60 дней против 240), поэтому при дне цикла старше
    # двух месяцев кратность выходит заниженной, и выбытие сработает
    # позже. Ошибаться в эту сторону безопаснее: заниженная величина
    # монету сохраняет.
    raw = getattr(c, "raw", None) or {}
    try:
        up_pct = float(raw.get("up_from_low") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return 1.0 + up_pct / 100.0 if up_pct > 0 else 0.0


def _cycle_peak_age(c: Candidate) -> float | None:
    """Давность вершины хода в днях из пейлоада FLOW.

    None означает «не знаем, когда»: у монеты без срабатывания
    семейства пейлоада нет, а −1 из ядра значит то же самое.
    Восстановить давность из истории записи нельзя — max_price
    помнит уровень, но не помнит дату, — поэтому запасного пути
    здесь нет и быть не может.
    """
    flow = getattr(c, "flow", None) or {}
    drop = (flow.get("context") or {}).get("drop") or {}
    try:
        age = float(drop.get("peak_up_age"))
    except (TypeError, ValueError):
        return None
    return age if age >= 0 else None


def _cycle_peak_x(c: Candidate) -> tuple[float, float]:
    """Вершина хода и текущее положение — обе от минимума окна.

    Пара, а не одно число: правило завершения читает и высоту, и
    отданную от неё долю, и обе обязаны меряться от одного дна.

    Нули означают «не мерили»: у монеты без срабатывания семейства
    пейлоада нет вовсе. Восстановлением из цены занимается
    _touch_cycle — там для этого есть история записи.
    """
    flow = getattr(c, "flow", None) or {}
    drop = (flow.get("context") or {}).get("drop") or {}
    try:
        return (float(drop.get("peak_up_x") or 0.0),
                float(drop.get("now_up_x") or 0.0))
    except (TypeError, ValueError):
        return 0.0, 0.0


def _touch_cycle(rec: dict, up_x: float, peak_x: float = 0.0,
                 now_x: float = 0.0, peak_age: float | None = None,
                 bars_passed: float = 0.0) -> None:
    """Где цена сейчас и до какой высоты доходила — обе от дна цикла.

    Решение о выбытии читает пару: вершина задаёт масштаб хода,
    текущая кратность — сколько от него отдано. Одной текущей мало,
    одной вершины тоже: монета, стоящая на ×20, и монета, отдавшая
    ход с ×20 до ×3, — разные состояния.

    Вершина берётся из пейлоада, если семейство отработало. Если
    нет — восстанавливается из max_price, которую _touch_price ведёт
    с первого дня записи: дно выводится из текущей пары price / up_x,
    и максимум цены переводится в кратность тем же дном. Так вынос,
    случившийся и отыгравшийся между прогонами, не теряется.
    """
    if up_x <= 0 and now_x <= 0:
        return
    if up_x > 0:
        rec["up_x"] = round(up_x, 2)

    # Текущее положение для правила: из пейлоада, если он есть, иначе
    # up_x из метрик. Обе меряют «где цена относительно базы», просто
    # с разной точностью окна.
    now = float(now_x or 0.0) or float(up_x or 0.0)
    rec["now_up_x"] = round(now, 2)

    # Вершина только из пейлоада или из ранее записанной.
    #
    # Вывод из max_price убран намеренно. У такой величины нет
    # давности — цена помнит уровень, но не помнит дату, — а правило
    # завершения без срока не работает. Плюс поле пачкается: у PROM
    # там лежало 12.28 при входе 2.08, и вершина выходила ×13.7 на
    # монете, которая за всю жизнь записи ходила от 2 до 3.
    prev_peak = float(rec.get("max_up_x") or 0.0)
    peak = max(prev_peak, float(peak_x or 0.0), now)

    # Давность стареет вместе с записью: пик, записанный неделю
    # назад, сегодня на неделю старше. Свежая давность из пейлоада
    # принимается только вместе со своей вершиной — иначе к старому
    # пику приписался бы новый возраст.
    if peak_x and peak_x >= prev_peak and peak_age is not None:
        rec["peak_up_age"] = round(float(peak_age), 1)
    elif "peak_up_age" in rec and bars_passed > 0:
        rec["peak_up_age"] = round(float(rec["peak_up_age"]) + bars_passed, 1)

    rec["max_up_x"] = round(peak, 2)
    rec["trend_done"] = peak >= CYCLE_TREND_DONE_X


# Сколько суток держим в карте плотности. Семи хватает, чтобы
# увидеть разгон, и мало, чтобы карта не росла в записи бесконечно.
DENSITY_DAYS = 7

# ── Разметка добора ──────────────────────────────────────────
# Условный портфель, который здесь считался (PORT_STAKE/PORT_ADD,
# portfolio_stats), снят 23.08: рядом жил второй расчёт того же —
# analytics_portfolio с книгами HOLD и трейдинга, и два источника
# одной истины однажды разошлись бы. Потолок находок и список
# «разобрать» переехали туда же (_journal_extras). Здесь осталась
# только РАЗМЕТКА добора: _maybe_add пишет add_price в запись —
# это данные журнала, а не расчёт, и владеет ими этот модуль.

# Насколько глубоко монета должна была просесть, чтобы возврат
# считался подтверждением. По разбросу журнала 16 августа: медиана
# просадки −13.8%, первая четверть −25.1%. Двадцать проходят между
# ними и отделяют обычный шум от настоящего провала.
PORT_DIP_PCT = 20.0


def _touch_density(rec: dict, now: datetime) -> None:
    """Отмечает попадание в карте по дням и подрезает хвост.

    Ключ — календарная дата в UTC, а не «сутки назад»: при часовых
    прогонах скользящее окно давало бы разное число в зависимости от
    момента замера, и сравнивать дни между собой стало бы нельзя.

    Подрезка на каждом попадании, а не отдельной уборкой: карта
    маленькая, а забытая уборка означала бы запись, растущую весь
    срок жизни монеты.
    """
    day = now.date().isoformat()
    src = rec.get("hits_by_day")
    if not isinstance(src, dict):
        src = {}

    try:
        src[day] = int(src.get(day) or 0) + 1
    except (TypeError, ValueError):
        src[day] = 1

    cutoff = (now.date() - timedelta(days=DENSITY_DAYS - 1)).isoformat()
    rec["hits_by_day"] = {
        k: v for k, v in src.items() if isinstance(k, str) and k >= cutoff
    }


def _days_since(stamp: str | None, now: datetime) -> float:
    """Сколько дней прошло с отметки. Ноль, если отметки нет.

    Ноль здесь безопасен: он означает «не старим», то есть вершина
    остаётся той же свежести. Ошибка в эту сторону монету сохраняет.
    """
    if not stamp:
        return 0.0
    try:
        when = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return 0.0
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return max(0.0, (now - when).total_seconds() / 86400.0)


def _touch_exit(rec: dict, raw: dict, price: float, now: datetime) -> None:
    """Выход по крупной продаже на дневном баре.

    Красный пузырь на пампе означает, что разгон встретил предложение.
    Проверяются два последних дневных бара: метка появляется на баре, а
    прогон идёт каждый час, и требовать попадания ровно в текущий бар
    значило бы ловить событие в одном прогоне из двадцати четырёх.

    Условие «монета выше входа» обязательно: продажа на падающей
    монете ничего не завершает, там и завершать нечего.

    Выход один и окончательный. Позиция закрыта — дальнейшие движения
    цены её не касаются, иначе метрика перестала бы отвечать на
    вопрос «сколько бы взяли по правилам».
    """
    if rec.get("exit_price") or rec.get("skip"):
        return
    if price <= 0:
        return
    try:
        if float(rec.get("change_pct") or 0.0) <= 0:
            return
    except (TypeError, ValueError):
        return

    big = (raw or {}).get("daily_big") or {}
    marks = big.get("marks") or []
    if not marks:
        return

    tail = int(big.get("tail") or 48)
    for m in marks:
        try:
            fresh = int(m.get("i", -1)) >= tail - 2
        except (TypeError, ValueError):
            continue
        if fresh and m.get("side") == "sell":
            rec["exit_price"] = price
            rec["exit_at"] = now.isoformat()
            rec["exit_why"] = "крупная продажа на пампе"
            return


def _touch_portfolio(rec: dict, price: float, now: datetime,
                     run_no: int) -> None:
    """Добор, если монета вернулась выше входа после просадки.

    Вызывается ПОСЛЕ _touch_price: тот уже обновил change_pct и
    min_change_pct, и здесь читаются свежие величины.

    Условие проверяется на каждом прогоне, а срабатывает один раз —
    дальше поле add_price занято и путь закрыт. Повторные доборы
    превратили бы метрику в усреднение убытка, а она измеряет
    подтверждение разворота.

    Момент фиксируется ценой ТОГО прогона, где условие впервые
    выполнилось, а не ценой входа. Разница невелика — пересечение
    происходит около входа, — но подставлять вход значило бы
    записать догадку там, где есть замер.
    """
    if rec.get("add_price"):
        return
    if price <= 0:
        return

    try:
        dip = float(rec.get("min_change_pct") or 0.0)
        chg = float(rec.get("change_pct") or 0.0)
    except (TypeError, ValueError):
        return

    if dip <= -PORT_DIP_PCT and chg > 0:
        rec["add_price"] = price
        rec["add_run"] = int(run_no)
        rec["add_at"] = now.isoformat()


def read_store(path: Path) -> dict:
    """Журнал с диска как есть, вместе с _meta. Отсутствие файла — не ошибка.

    Первый прогон на чистой машине журналов не находит, и падать
    из-за этого отчёт не должен: панель просто останется пустой.

    Публичная и живёт здесь, а не в помощниках рендера, где лежала
    раньше (_read_json в render_common.py). Причина не стилистическая:
    оба файла, которые ею читают, — leaders и anomaly — пишет ИМЕННО
    этот модуль, а после разделения слоёв аналитике нельзя импортировать
    рендер вовсе, и звёздам понадобилось читать журнал из аналитики.

    Отличие от _load(): тот снимает _meta со словаря и отдаёт отдельно,
    потому что пишущей стороне нужны записи без служебного ключа.
    Читающей чаще нужен файл целиком.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def journal_expectancy(symbol: str,
                       path: Path = LEADERS_PATH,
                       archive_path: Path = LEADERS_ARCHIVE_PATH) -> dict | None:
    """Ожидание монеты по эпизодам журнала: средний ход вверх против
    среднего отката, а не частота попаданий.

    Перенос из оценки трейдеров (DropsTab по Hyperliquid): кошелёк
    может выигрывать в 57% сделок и терять деньги, если средний
    убыток больше среднего выигрыша. Реактивные метрики (частота,
    попадания) подтверждают результат; поведенческие (ожидание)
    говорят, повторится ли он. Живой пример из нашего журнала:
    ALPINE попадала в 97% прогонов — и в минусе.

    Эпизод = запись журнала (живая или архивная): max_change_pct =
    сколько монета дала вверх после попадания, min_change_pct =
    сколько откатила. Возврат: {"avgUp", "avgDown", "expPct", "n"}
    или None, когда эпизодов нет. В решения не входит; показ — Э-7.
    """
    ups: list[float] = []
    downs: list[float] = []

    def _eat(rec: dict) -> None:
        try:
            ups.append(float(rec.get("max_change_pct") or 0.0))
            downs.append(abs(float(rec.get("min_change_pct") or 0.0)))
        except (TypeError, ValueError):
            pass

    recs, _meta = _load(path)
    rec = recs.get(symbol)
    if isinstance(rec, dict):
        _eat(rec)
    if archive_path.exists():
        # Архивные строки плоские: {"symbol", "archived_at", **запись}.
        for line in archive_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if entry.get("symbol") == symbol:
                _eat(entry)
    if not ups:
        return None
    avg_up = sum(ups) / len(ups)
    avg_dn = sum(downs) / len(downs) if downs else 0.0
    return {"avgUp": round(avg_up, 2), "avgDown": round(avg_dn, 2),
            "expPct": round(avg_up - avg_dn, 2), "n": len(ups)}


def _lead_marks(rec: dict) -> list[dict]:
    """Метки лидерства записи, только пригодные к разбору."""
    out = []
    for m in (rec.get("lead_at") or []):
        if isinstance(m, dict) and m.get("t"):
            out.append(m)
    return out


def _hours_ago(stamp: str, now: datetime) -> float | None:
    """Сколько часов назад была метка. Разбор мимо — None, не ноль:
    «не знаем» и «только что» это разные ответы."""
    try:
        d = datetime.fromisoformat(str(stamp))
    except (TypeError, ValueError):
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now - d).total_seconds() / 3600.0


def lead_stats(recs: dict, now: datetime) -> dict:
    """Три взгляда на лидерство, все окна СКОЛЬЗЯЩИЕ от `now`.

    Календарные сутки здесь не годятся принципиально: прогон в 00:10
    видел бы «вчера» почти пустым, а в 23:50 — полным, при одном и том
    же поведении рынка. Поэтому ни одно окно не смотрит на дату, только
    на разницу во времени.

    Возвращает три списка, каждый может быть пустым — это законный
    ответ, а не сбой: первые трое суток после запуска истории просто
    нет.

    day  — топ по числу лидерств за последние 24 часа.
    hold — монеты, у которых есть хотя бы одно лидерство в КАЖДОМ из
           трёх суточных отрезков последних 72 часов. Пропуск в любом
           отрезке исключает монету целиком: смысл строки — не «часто
           мелькала», а «держится третьи сутки подряд».
    top  — одна монета с наибольшим ростом от дна 60 дней среди тех,
           кто был лидером за 72 часа, с датами первого и последнего
           появления в журнале.
    """
    day: list[dict] = []
    hold: list[dict] = []
    best: tuple[float, str, dict] | None = None

    for sym, rec in recs.items():
        if sym.startswith("_") or not isinstance(rec, dict):
            continue
        marks = _lead_marks(rec)
        if not marks:
            continue

        ages = [h for h in (_hours_ago(m.get("t"), now) for m in marks)
                if h is not None and h >= 0]
        if not ages:
            continue

        n_day = sum(1 for h in ages if h < LEAD_DAY_HOURS)
        n_win = sum(1 for h in ages if h < LEAD_WINDOW_HOURS)
        lbl = sym[:-4] if sym.endswith("USDT") else sym

        if n_day:
            day.append({"t": lbl, "n": n_day})

        if n_win:
            # Три отрезка по суткам: [0..24), [24..48), [48..72).
            # Нужен непустой каждый — отсюда all(), а не any().
            slots = [
                any(lo <= h < lo + LEAD_DAY_HOURS for h in ages)
                for lo in (0, LEAD_DAY_HOURS, LEAD_DAY_HOURS * 2)
            ]
            if all(slots):
                hold.append({"t": lbl, "n": n_win})

            # Рост от дна берём из САМОЙ СВЕЖЕЙ метки окна, а не из
            # записи: в записи величина сегодняшняя, а нам нужна та,
            # что была в момент лидерства.
            fresh = min(
                (m for m in marks
                 if (_hours_ago(m.get("t"), now) or 1e9) < LEAD_WINDOW_HOURS),
                key=lambda m: _hours_ago(m.get("t"), now) or 1e9,
                default=None,
            )
            up = float((fresh or {}).get("up") or 0.0)
            if up > 0 and (best is None or up > best[0]):
                best = (up, lbl, rec)

    day.sort(key=lambda x: (-x["n"], x["t"]))
    hold.sort(key=lambda x: (-x["n"], x["t"]))

    out = {"day": day[:LEAD_TOP_DAY], "hold": hold}
    if best is not None:
        up, lbl, rec = best
        out["top"] = {
            "t": lbl,
            "up": round(up, 1),
            "first": str(rec.get("first_seen") or ""),
            "last": str(rec.get("last_seen") or ""),
        }
    return out


def journal_summary(path: Path = LEADERS_PATH) -> dict:
    """Итог журнала целиком — для хвоста сводки.

    Считается при чтении, потому что это агрегат по всему файлу, а не
    поле записи: лучший и худший ход имеют смысл только на фоне
    остальных. «Новые» — записи, заведённые текущим прогоном:
    since_run записи совпадает со счётчиком прогонов в _meta.
    Это честная замена мёртвой строке «новые в топ-3» — поле newTop3
    никто никогда не писал, а since_run пишется каждым прогоном.

    Живёт здесь, а не в орбите, где лежала раньше: ни одно из этих
    чисел не относится к конкретной звезде и к тому, как она
    рисуется, — это журнал целиком, схемой которого владеет именно
    этот модуль (_new_record/_touch_*). Читает своим же _load(),
    без чтения json на стороне рендера.
    """
    recs, meta = _load(path)
    run_no = int(meta.get("runs") or 0)

    recs = {k: v for k, v in recs.items()
            if not k.startswith("_") and isinstance(v, dict)}
    if not recs:
        return {}

    # Пробелы ручных полей считаются своим владельцем, здесь только
    # собираются: правило живёт рядом с записями, а не в отрисовке.
    # Портфель отсюда уехал (23.08) — оба счёта и потолок находок
    # теперь в analytics_portfolio, единственном месте про деньги.
    from analytics_manual_fields import stats as manual_stats
    gaps = manual_stats(recs)

    def _lbl(sym: str) -> str:
        return sym[:-4] if sym.endswith("USDT") else sym

    fresh = [_lbl(s) for s, r in recs.items()
             if run_no > 0 and int(r.get("since_run") or 0) == run_no]

    by_chg = sorted(recs.items(),
                    key=lambda kv: float(kv[1].get("change_pct") or 0.0))
    worst_sym, worst = by_chg[0]
    best_sym, best = by_chg[-1]

    # Момент отсчёта — сейчас, а не время последнего прогона: сводка
    # читается и открывается позже, чем собиралась, и окна должны
    # считаться от чтения.
    lead = lead_stats(recs, datetime.now(timezone.utc))

    return {
        "n": len(recs),
        "fresh": fresh[:3],
        "gaps": gaps,
        # Наблюдение за лидерством (27.08). Пустые ключи не кладём:
        # экран сам не покажет то, чего нет.
        **({"leadDay": lead["day"]} if lead.get("day") else {}),
        **({"leadHold": lead["hold"]} if lead.get("hold") else {}),
        **({"leadTop": lead["top"]} if lead.get("top") else {}),
        "best": {"t": _lbl(best_sym),
                 "chg": round(float(best.get("change_pct") or 0.0), 1)},
        "worst": {"t": _lbl(worst_sym),
                  "chg": round(float(worst.get("change_pct") or 0.0), 1)},
    }


def _touch_price(rec: dict, price: float, now: datetime) -> None:
    entry = rec["entry_price"]
    rec["price"] = price
    rec["change_pct"] = round((price / entry - 1) * 100, 2) if entry > 0 else 0.0
    if price > rec.get("max_price", entry):
        rec["max_price"] = price
        rec["max_change_pct"] = rec["change_pct"]
    if price < rec.get("min_price", entry):
        rec["min_price"] = price
        rec["min_change_pct"] = rec["change_pct"]
    rec["last_seen"] = now.isoformat()


def _load(path: Path) -> tuple[dict[str, dict], dict]:
    if not path.exists():
        return {}, {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        log(f"⚠ {path.name} повреждён, начинаю заново: {e}")
        return {}, {}
    meta = data.pop(_META_KEY, {})
    return data, meta


def _archive(path: Path, symbol: str, rec: dict, reason: str, now: datetime) -> None:
    """Дописывает выбывшую запись в лог вместо того, чтобы её терять."""
    entry = {"symbol": symbol, "archived_at": now.isoformat(),
              "reason": reason, **rec}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _sweep(
    store: dict, archive_path: Path, basket: str, cutoff: datetime, now: datetime,
) -> dict:
    """Две ОТМЕТКИ выбытия — но не удаление (правило 22.08).

    Прежде эти два правила выбрасывали запись из журнала. Теперь они
    только помечают её (retired_at / retired_why) и кладут копию в
    архив: стратегия выхода — гипотеза, и судить её можно лишь по
    записям, дожившим до исхода. Удаляет из журнала человек.


    Отработала. Цена ушла от дна цикла в CYCLE_COMPLETE_X раз —
    монета сделала свою волну, ловить в ней начало движения больше
    нечего. Проверяется первой: у такой записи может быть свежее
    событие, и по бездействию она не выбыла бы никогда.

    Затихла. С последнего события прошло больше срока. Считается по
    last_hit, а не по first_seen: календарный возраст записи годился
    для fuel, но не для подкейсов у дна — у dormant, hidden и spring
    тезис в том и состоит, что монета лежит на базе месяцами. Пока
    у неё обновляются аномальные объёмы или срабатывает семейство,
    наблюдение продолжается; замолчала — выбывает.

    Причины в архиве разные, и это не украшение: корзину «отработала»
    потом читают, чтобы проверить сам порог — ушла ли выброшенная
    монета дальше или встала. По общей причине этот вопрос не
    задать.

    Старые записи без last_hit получают first_seen: до этой правки
    поля не существовало, и судить по нему задним числом не о чем.
    """
    kept: dict[str, dict] = {}
    for symbol, rec in store.items():
        # Добавленную руками монету не трогаем ни одним правилом.
        # Её добавили именно затем, чтобы следить, и решать за
        # человека, что наблюдение окончено, нечем.
        if rec.get("added_manually"):
            kept[symbol] = rec
            continue

        # ЖУРНАЛ НЕ ЧИСТИТСЯ КОДОМ (правило 22.08). Стратегия выхода
        # пока гипотеза: она не посчитана и не проверена. Проверить её
        # можно ТОЛЬКО на записях, доживших до исхода, — а запись,
        # удалённая правилом за три дня до движения, уносит с собой
        # ответ на вопрос, ради которого затевалась.
        # Поэтому обе прежние причины выбытия («отработала», «затихла»)
        # больше не удаляют, а ПОМЕЧАЮТ: копия уходит в архив как
        # раньше, запись остаётся в журнале с отметкой и датой.
        # Убирает из журнала только человек.

        now_x = float(rec.get("now_up_x") or rec.get("up_x") or 0.0)
        peak_x = float(rec.get("max_up_x") or 0.0)
        peak_age = rec.get("peak_up_age")
        if cycle_done(now_x, peak_x, peak_age):
            # Причина в архиве различает два случая: вершина сама по
            # себе против отданного хода. Корзину потом читают, чтобы
            # проверить пороги, и по общей причине этот вопрос не
            # задать.
            top = max(peak_x, now_x)
            if top >= CYCLE_COMPLETE_X:
                why = f"completed:{CYCLE_COMPLETE_X:g}x:{basket}"
            else:
                why = f"giveback:{top:.0f}x→{now_x:.1f}x:{basket}"
            _archive(archive_path, symbol, rec, reason=why, now=now)
            rec.setdefault("retired_at", now.isoformat())
            rec["retired_why"] = why
            kept[symbol] = rec
            continue

        last = rec.get("last_hit") or rec.get("first_seen")
        try:
            quiet_since = datetime.fromisoformat(last)
        except (TypeError, ValueError):
            # Дата не разобралась — запись оставляем. Потерять монету
            # из-за битого поля хуже, чем подержать лишнюю.
            kept[symbol] = rec
            continue

        if quiet_since >= cutoff:
            kept[symbol] = rec
        else:
            _archive(archive_path, symbol, rec, reason=f"stale:{basket}", now=now)
            rec.setdefault("retired_at", now.isoformat())
            rec["retired_why"] = f"stale:{basket}"
            kept[symbol] = rec
    return kept


# ─────────────────────────────────────────────────────────────
# Состав наблюдения
# ─────────────────────────────────────────────────────────────
def tracked_symbols(flow_path: Path = LEADERS_PATH) -> set[str]:
    """Символы, за которыми журнал лидеров уже следит.

    Только журнал FLOW. Корзина аномалий сюда НЕ входит и входить не
    должна: она заведена для разбора постфактум, звёздами на орбите
    не становится (_orbit_stars читает один LEADERS_PATH) и потому в
    выборку прогона не просится. Первая редакция читала оба файла и
    добавляла 120 монет вместо единиц — почти всё это была корзина.

    Нужны отбору, а не отчёту, и потому читают файл напрямую: вызов
    происходит до того, как кандидаты вообще существуют.

    Зачем: монета попадает в журнал на всплеске, через несколько дней
    затихает и выпадает из топа по обороту. Данных по ней в прогоне
    нет, запись замирает с последними известными числами — и звезда
    на орбите рисует прочерки ровно тогда, когда наблюдение стало
    интересным. У BULLA vol_ratio в журнале лежит в 0.66..1.33:
    оборот вернулся к норме, монета ушла из выборки, карточка пустая.

    Потолка на добавку нет намеренно. Журнал ограничен сверху не
    возрастом записи, а окном бездействия: запись живёт, пока у
    монеты обновляются аномальные объёмы или срабатывает семейство
    (см. _sweep). Живых монет конечное число, поэтому выборка не
    растёт бесконечно — а любое усечение по количеству выкинуло бы
    из неё именно ту звезду, ради которой всё и делается.

    Возвращается множество, а не список: единственный вопрос к
    результату — «есть ли символ внутри», порядок ничего не значит.
    """
    store, _ = _load(flow_path)
    return {s for s in store if s != _META_KEY}


def update_leaders(
    candidates: list[Candidate],
    snapshot: RunSnapshot,
    flow_path: Path = LEADERS_PATH,
    anomaly_path: Path = ANOMALY_PATH,
    archive_path: Path = LEADERS_ARCHIVE_PATH,
    max_age_days: int = LEADERS_MAX_AGE_DAYS,
) -> tuple[Path, Path]:
    """Обновляет обе выборки и пишет их на диск раздельно.

    Вызывается рядом с render_report — у candidates на этот момент уже
    есть готовый raw["vol_ratio"] (посчитан в collect_metrics), сеть
    здесь не нужна вообще.
    """
    ensure_dirs()   # готовит OUTPUT_DIR — все три пути этого модуля под ним

    now = _now(snapshot)
    flow_store, meta = _load(flow_path)
    anomaly_store, _ = _load(anomaly_path)

    # Номер прогона. Увеличивается один раз за вызов, до всякой
    # записи: если считать его после, первая запись прогона получила
    # бы номер предыдущего.
    run_no = int(meta.get("runs", 0)) + 1
    meta["runs"] = run_no

    by_symbol = {c.symbol: c for c in candidates}

    # ── flow: лидер прогона ──
    flow_pool = [c for c in candidates if c.flow]
    leader = max(flow_pool, key=lambda c: c.score or 0, default=None)

    if leader is not None:
        price = float(leader.raw.get("price") or 0.0)
        if price > 0:
            if leader.symbol not in flow_store:
                moved = anomaly_store.pop(leader.symbol, None)
                flow_store[leader.symbol] = moved or _new_record(
                    now, price, {}, run_no,
                    _entry_rules(now, leader.raw or {}, leader.flow or {}),
                )
                log(
                    f"  → leaders: {leader.symbol} перенесена из аномальных в flow"
                    if moved else f"  → leaders: новый лидер {leader.symbol} @ {price:g}"
                )

            rec = flow_store[leader.symbol]
            f = leader.flow or {}
            rec["entry_case"] = rec.get("entry_case") or f.get("case", "")
            rec["zone_price"] = rec.get("zone_price") or float(f.get("zone_price") or 0.0)
            rec["stop_hint"] = rec.get("stop_hint") or float(f.get("stop_hint") or 0.0)
            rec["target_hint"] = rec.get("target_hint") or float(f.get("target_hint") or 0.0)
            rec["horizon_days"] = rec.get("horizon_days") or int(f.get("horizon_days") or 0)
            rec["horizon_tf"] = rec.get("horizon_tf") or f.get("horizon_tf", "")
            prev = meta.get("last_leader")
            rec["streak"] = (rec.get("streak", 0) + 1) if prev == leader.symbol else 1

            # Попадание в лидеры больше не считается здесь отдельно
            # (Ч-6/К-6 тех.долга): hits теперь растёт в общем цикле
            # ниже, тем же условием, что уже двигает hits_by_day —
            # «flow.detected на этом прогоне», а не «стал ли именно
            # текущим единственным лидером». Раньше монета, которая
            # продолжает срабатывать, но не выигрывает сравнение
            # каждый раз, копила плотность по дням при hits=0 — у
            # HEI 96 попаданий за четыре дня при частоте 0.0.
            # ── МЕТКА ЛИДЕРСТВА ──
            # Пишем момент, номер прогона и то, чем монета была В ЭТУ
            # МИНУТУ: цену, скор, подкейс и рост от дна. Все четыре
            # величины позже меняются, а метка должна отвечать на
            # вопрос «что было, когда она стала первой», а не «что у
            # неё сейчас».
            #
            # `up` — рост от минимума 60 дней (BOTTOM_WINDOW в
            # analytics_metrics). Окно короткое сознательно: монета за
            # три года могла вырасти четырежды, и рост от абсолютного
            # дна ничего не сказал бы о сегодняшнем движении. У монет
            # короче окна величина не измеряется и приходит нулём —
            # такие в строку роста не попадут, и это правильно.
            mark = {
                "t": now.isoformat(),
                "run": run_no,
                "px": round(price, 10),
                "score": int(leader.score or 0),
                "case": f.get("case", ""),
                "up": round(float((leader.raw or {}).get("up_from_low") or 0.0), 1),
                "up_days": int((leader.raw or {}).get("days_from_low") or 0),
            }
            marks = rec.get("lead_at")
            if not isinstance(marks, list):
                marks = []
            marks.append(mark)
            rec["lead_at"] = marks
            rec["lead_hits"] = int(rec.get("lead_hits", 0)) + 1

            rec.setdefault("since_run", run_no)
            meta["last_leader"] = leader.symbol
    else:
        meta["last_leader"] = None   # прогон без лидера рвёт цепочку стрика

    # ── аномальные объёмы: весь прогон, кроме тех, кто уже в flow ──
    for c in candidates:
        if c.symbol in flow_store:
            continue
        price = float(c.raw.get("price") or 0.0)
        if price <= 0:
            continue
        ratios = c.raw.get("vol_ratio") or {}
        if c.symbol in anomaly_store:
            rec = anomaly_store[c.symbol]
            # Попадание засчитывается только когда объём аномален
            # СЕЙЧАС. Запись живёт до LEADERS_MAX_AGE_DAYS независимо
            # от текущего объёма, и считать присутствие в файле за
            # попадание значило бы мерить возраст записи, а не рынок.
            if _is_anomalous(ratios):
                rec["hits"] = int(rec.get("hits", 0)) + 1
            rec.setdefault("since_run", run_no)
        elif _is_anomalous(ratios):
            anomaly_store[c.symbol] = _new_record(now, price, ratios, run_no)
            anomaly_store[c.symbol]["hits"] = 1
            hit = ", ".join(k for k, v in ratios.items() if v >= ANOMALY_RATIO_MIN)
            log(f"  → leaders: новая аномалия объёма {c.symbol} ({hit})")

    # ── цена, MFE/MAE и рекорд объёма — всем, кого видно в прогоне ──
    #
    # Рекорд объёма обновляется ЗДЕСЬ, а не только у лидера.
    #
    # Прежде слияние стояло внутри ветки лидера, и запись переставала
    # набирать объём в тот момент, когда лидером становилась другая
    # монета. Поле называлось рекордом, а хранило последнее значение
    # на момент лидерства: у HEMI на карточке стоял «рекорд ×143» при
    # текущем объёме ×249, то есть рекорд был меньше текущего —
    # арифметически невозможное состояние для максимума.
    for store in (flow_store, anomaly_store):
        for symbol, rec in store.items():
            c = by_symbol.get(symbol)
            if c is None:
                continue
            price = float(c.raw.get("price") or 0.0)
            if price > 0:
                _touch_price(rec, price, now)
                # Строго после _touch_price: добор и выход читают
                # свежие change_pct и min_change_pct, которые тот и
                # пишет.
                _touch_portfolio(rec, price, now, run_no)
                _touch_exit(rec, c.raw or {}, price, now)
                # Строго после _touch_price: добор и выход читают
                # свежие change_pct и min_change_pct, которые тот и
                # пишет.
                _touch_portfolio(rec, price, now, run_no)
                _touch_exit(rec, c.raw or {}, price, now)
            ratios = c.raw.get("vol_ratio") or {}
            rec["vol_ratio"] = _merge_max(rec.get("vol_ratio", {}), ratios)

            # Кратность и вершина от дна цикла — мерка выбытия,
            # одна на проект.
            peak_x, now_x = _cycle_peak_x(c)
            # Сколько дней прошло с прошлого прогона — на столько же
            # постарела записанная вершина.
            passed = _days_since(rec.get("last_seen"), now)
            _touch_cycle(rec, _cycle_up_x(c), peak_x, now_x,
                         _cycle_peak_age(c), passed)

            # Событие продлевает жизнь записи. Условие ШИРЕ, чем
            # попадание в журнал: попасть сюда может только лидер
            # прогона, а удержаться — любая монета, на которой
            # сработало семейство либо обновился аномальный объём.
            # Иначе монета, честно отработавшая подкейсом, но не
            # ставшая лидером ни разу, выбывала бы по тишине, которой
            # на самом деле не было.
            alive = bool((getattr(c, "flow", None) or {}).get("detected"))
            if alive or _is_anomalous(ratios):
                rec["last_hit"] = now.isoformat()
                _touch_density(rec, now)
                # Тем же условием, что и density: К-6 тех.долга —
                # hits раньше рос только у текущего единственного
                # лидера прогона (flow_store) и расходился с
                # hits_by_day, который растёт для любого детекта.
                #
                # Только для flow_store: у anomaly_store hits уже
                # считается верно чуть выше своим отдельным циклом
                # (там же, где заводится новая запись) — прибавление
                # здесь без разбора хранилища задвоило бы счётчик.
                if store is flow_store:
                    rec["hits"] = int(rec.get("hits", 0)) + 1

            # Р-25: жизнь ФИГУРЫ отдельно от жизни записи. last_hit
            # смешивает детект и аномалию объёма — по нему нельзя
            # ответить «признаки держатся или распались»: всплеск
            # объёма на трупе фигуры обновил бы last_hit и труп
            # выглядел бы живым. last_alive пишется ТОЛЬКО по
            # flow.detected, и разрыв от него — то различение из
            # Р-25: держатся = ожидание повода, распались = смерть.
            # Поле начинает копиться с этого прогона; у старых
            # записей его нет, и читатель обязан отличать «нет
            # поля» от «давно не жива».
            if store is flow_store and alive:
                rec["last_alive"] = now.isoformat()

    # ── чистка по возрасту, с архивом вместо тихой потери ──
    cutoff = now - timedelta(days=max_age_days)
    flow_store = _sweep(flow_store, archive_path, "flow", cutoff, now)
    anomaly_store = _sweep(anomaly_store, archive_path, "anomaly", cutoff, now)

    # Частота попаданий. Считается при записи, а не при чтении:
    # потребителю иначе пришлось бы знать про meta и номера прогонов,
    # и каждый читатель посчитал бы её по-своему.
    for store in (flow_store, anomaly_store):
        for symbol, rec in store.items():
            span = max(1, run_no - int(rec.get("since_run", run_no)) + 1)
            rec["runs_seen"] = span
            rec["hit_rate"] = round(int(rec.get("hits", 0)) / span, 3)

    flow_store[_META_KEY] = meta
    write_atomic(flow_path, json.dumps(flow_store, ensure_ascii=False, indent=2))
    write_atomic(anomaly_path, json.dumps(anomaly_store, ensure_ascii=False, indent=2))
    return flow_path, anomaly_path
