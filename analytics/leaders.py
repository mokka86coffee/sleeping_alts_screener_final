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

from core.config import (
    ANOMALY_PATH, ANOMALY_RATIO_MIN, LEADERS_ARCHIVE_PATH,
    LEADERS_MAX_AGE_DAYS, LEADERS_PATH,
)
from core.http import log
from core.models import Candidate, RunSnapshot
from sources.storage import ensure_dirs, write_atomic

# Символ прошлого лидера — иначе streak не отличить от «монета снова
# стала лидером через неделю тишины».
#
# Здесь же счётчик прогонов: без него частота попаданий не считается.
# Пять попаданий за двое суток и пять за двадцать — разные монеты, а
# по одному счётчику hits они неотличимы.
_META_KEY = "_meta"


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


def _new_record(
    now: datetime,
    price: float,
    ratios: dict[str, float],
    run_no: int = 0,
) -> dict:
    return {
        "first_seen": now.isoformat(),
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
    kept: dict[str, dict] = {}
    for symbol, rec in store.items():
        if datetime.fromisoformat(rec["first_seen"]) >= cutoff:
            kept[symbol] = rec
        else:
            _archive(archive_path, symbol, rec, reason=f"max_age:{basket}", now=now)
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

    Потолка на добавку нет намеренно. Журнал ограничен сверху сроком
    жизни записи (LEADERS_MAX_AGE_DAYS), а любое усечение выкинуло бы
    из выборки именно ту звезду, ради которой всё и делается.

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
            rec["vol_ratio"] = _merge_max(
                rec.get("vol_ratio", {}), leader.raw.get("vol_ratio", {}),
            )

            prev = meta.get("last_leader")
            rec["streak"] = (rec.get("streak", 0) + 1) if prev == leader.symbol else 1

            # Попадание в лидеры. Отдельно от streak: streak меряет
            # непрерывность и обнуляется, как только лидером стала
            # другая монета, а hits копится за всё время жизни записи.
            #
            # Монета, дважды за день ставшая лидером с перерывом,
            # по streak неотличима от разовой — по hits отличима.
            rec["hits"] = int(rec.get("hits", 0)) + 1
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
            rec["vol_ratio"] = _merge_max(rec.get("vol_ratio", {}), ratios)
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

    # ── цена и MFE/MAE — всем в обеих выборках, кого видно в этом прогоне ──
    for store in (flow_store, anomaly_store):
        for symbol, rec in store.items():
            c = by_symbol.get(symbol)
            if c is None:
                continue
            price = float(c.raw.get("price") or 0.0)
            if price > 0:
                _touch_price(rec, price, now)

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
