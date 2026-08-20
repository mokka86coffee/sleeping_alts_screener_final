"""Точка входа скринера.

Оркестрация прогона: отбор символов, параллельный анализ, сборка воронки,
сохранение снимка и генерация отчёта.

Запуск:
    python run.py                            полный прогон
    python run.py --limit 20                 только 20 монет, для отладки
    python run.py --symbols MYX,ZEC          конкретные монеты
    python run.py --no-html                  только JSON, без отчёта
    python run.py --workers 3                другое число потоков
    python run.py                            разовый прогон, отчёт + git push
    python run.py --loop                     бесконечно, каждые 3 часа
    python run.py --loop --interval 3600     каждый час
    python run.py --no-git                   без публикации
"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import os
import signal
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from analytics_leaders import update_leaders
# import pulse
from analytics_candidate import build_candidate
from core_binance import get_futures_tickers
from core_config import (
    EXCLUDE_TOKENS, MAX_SYMBOLS, MAX_WORKERS,
    MIN_QUOTE_VOLUME_24H, RVOL_WARM, STABLECOINS,
    LOOP_INTERVAL_SEC, REPORT_PATH, BASE_DIR, GIT_ADD_ALL_CHANGED,
    GIT_TIMEOUT_SEC, COMMIT_MSG,
)
from analytics_leaders import tracked_symbols
from core_http import log
from core_models import Candidate, FunnelStage, RunSnapshot
from sources_storage import compare_with_previous, save_snapshot, write_atomic

# ─────────────────────────────────────────────────────────────
# Отбор символов
# ─────────────────────────────────────────────────────────────
def select_symbols(
    limit: int = MAX_SYMBOLS,
    with_journal: bool = True,
) -> tuple[list[tuple[str, float]], dict]:
    """Отбирает USDT-перпы по обороту.

    Возвращает список пар (символ, оборот) и статистику отсева
    для первого узла воронки.

    with_journal управляет добавкой монет журнала сверх лимита.
    Отдельным флагом, а не сравнением limit с MAX_SYMBOLS внутри:
    сравнение угадывало бы намерение вызывающего, а решает его он.
    """
    tickers = get_futures_tickers()
    # Обороты всех USDT-пар, включая отсеянные. Нужен для добавки
    # журнала ниже: там встречаются монеты, не дошедшие до picked.
    vol_seen: dict[str, float] = {}
    stats = {
        "total_pairs": len(tickers),
        "not_usdt": 0,
        "excluded": 0,
        "low_volume": 0,
        "selected": 0,
    }

    if not tickers:
        return [], stats

    picked: list[tuple[str, float]] = []

    for t in tickers:
        symbol = t.get("symbol", "")

        if not symbol.endswith("USDT"):
            stats["not_usdt"] += 1
            continue

        base = symbol[:-4]
        if not base.isascii():
            stats["not_usdt"] += 1
            continue

        if base in STABLECOINS or base in EXCLUDE_TOKENS:
            stats["excluded"] += 1
            continue

        try:
            qvol = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            qvol = 0.0

        # Оборот запоминается ДО отсечки. Монета журнала выпадает
        # обычно именно здесь — она затихла, — а оборот у неё всё
        # равно нужен: build_candidate принимает его вторым аргументом
        # и без него посчитает долю спота от нуля.
        vol_seen[symbol] = qvol

        if qvol < MIN_QUOTE_VOLUME_24H:
            stats["low_volume"] += 1
            continue

        picked.append((symbol, qvol))

    # Самые ликвидные вперёд
    picked.sort(key=lambda x: -x[1])
    picked = picked[:limit]

    # ── Монеты журнала ──────────────────────────────────────
    # Добавляются сверх лимита и сверх порога по обороту.
    #
    # Иначе наблюдение обрывается на самом интересном месте: монета
    # попадает в журнал на всплеске, через несколько дней затихает,
    # выпадает из топа — и запись замирает с последними известными
    # числами. Карточка на орбите честно рисует прочерки, но чинить
    # надо не отображение, а состав выборки: журнал заведён ровно для
    # того, чтобы смотреть, чем кончилось.
    #
    # Стоимость ограничена сверху размером журнала: записи живут не
    # дольше LEADERS_MAX_AGE_DAYS, и пересечение с топом велико —
    # реальная добавка это единицы монет, а не сотня.
    #
    # Пара, а не голый символ: analyze_all распаковывает элементы
    # списка как (символ, оборот).
    have = {s for s, _ in picked}
    extra: list[tuple[str, float]] = []
    if with_journal:
        extra = [
            (s, vol_seen.get(s, 0.0))
            for s in sorted(tracked_symbols())
            if s not in have and s.endswith("USDT")
        ]
    if extra:
        picked.extend(extra)
        log(f"  → отбор: +{len(extra)} из журнала сверх лимита")

    stats["selected"] = len(picked)
    # Сколько монет пришло из журнала сверх лимита. Отдельным числом:
    # в «отобрано N» они неотличимы от прошедших по обороту, и рост
    # выборки выглядел бы как оживление рынка.
    stats["from_journal"] = len(extra)

    return picked, stats


# ─────────────────────────────────────────────────────────────
# Параллельный анализ
# ─────────────────────────────────────────────────────────────
def analyze_all(
    symbols: list[tuple[str, float]],
    workers: int = MAX_WORKERS,
) -> tuple[list[Candidate], list[tuple[str, str]]]:
    """Обрабатывает монеты в пуле потоков."""
    results: list[Candidate] = []
    errors: list[tuple[str, str]] = []
    total = len(symbols)
    done = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(build_candidate, sym, 0, qvol): sym
            for sym, qvol in symbols
        }

        for future in as_completed(futures):
            sym = futures[future]
            done += 1
            try:
                candidate = future.result()
                if candidate:
                    results.append(candidate)
                    marks = []
                    if candidate.is_viral:
                        marks.append("viral")
                    if candidate.vetoed:
                        marks.append("вето")
                    if candidate.rr > 0:
                        flag = "✓" if candidate.rr_ok else "·"
                        marks.append(f"rr {candidate.rr:.1f}{flag}")
                    suffix = f" · {' · '.join(marks)}" if marks else ""
                    log(f"  [{done}/{total}] {sym} · score {candidate.score} · "
                        f"{candidate.bucket}{suffix}")
                else:
                    log(f"  [{done}/{total}] {sym} · пропуск, мало данных")
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                errors.append((sym, msg))
                log(f"  [{done}/{total}] {sym} · ОШИБКА {msg}")
                traceback.print_exc()

    # Сильные вперёд, ранг присваивается после сортировки
    results.sort(key=lambda c: -c.score)
    for i, c in enumerate(results, 1):
        c.rank = f"#{i:03d}"

    return results, errors


# ─────────────────────────────────────────────────────────────
# Воронка отбора
# ─────────────────────────────────────────────────────────────
def build_funnel(
    total_scanned: int,
    candidates: list[Candidate],
) -> list[FunnelStage]:
    """Строит путь отбора от всей выборки до монет в работе.

    Каждый узел — реальное подмножество предыдущего. Последний узел
    обязан совпадать с candidate.tradable, иначе воронка врёт.
    """
    passed_volume = [
        c for c in candidates
        if (c.surge and c.surge.get("detected"))
        or c.metric_num("rvol_1h") >= RVOL_WARM
    ]
    has_structure = [
        c for c in passed_volume
        if c.taiko or c.dexe or c.phase.get("num", 0) >= 2
    ]
    actionable = [c for c in has_structure if c.strategy.actionable]
    after_veto = [c for c in actionable if not c.vetoed]
    tradable = [c for c in after_veto if c.rr_ok]

    raw = [
        ("all", "вся выборка", total_scanned),
        ("volume", "прошли объём", len(passed_volume)),
        ("structure", "структура ок", len(has_structure)),
        ("plan", "есть план", len(actionable)),
        ("veto", "после вето", len(after_veto)),
        ("tradable", "к работе", len(tradable)),
    ]

    stages: list[FunnelStage] = []
    base = total_scanned or 1
    prev_count = total_scanned

    for code, label, count in raw:
        dropped = max(prev_count - count, 0) if code != "all" else 0
        pass_pct = (count / prev_count * 100) if prev_count > 0 and code != "all" else 100.0
        stages.append(FunnelStage(
            code=code,
            label=label,
            count=count,
            dropped=dropped,
            pass_pct=round(pass_pct, 1),
            share_pct=round(count / base * 100, 1),
        ))
        prev_count = count

    return stages

# ─────────────────────────────────────────────────────────────
# Сектора
# ─────────────────────────────────────────────────────────────
def build_sectors(candidates: list[Candidate]) -> list[dict]:
    """Средняя динамика за сутки по секторам."""
    groups: dict[str, list[float]] = {}
    for c in candidates:
        sector = c.sector or "OTHER"
        ch = c.raw.get("ch_24h")
        if ch is None:
            continue
        groups.setdefault(sector, []).append(float(ch))

    out: list[dict] = []
    for sector, values in groups.items():
        if not values:
            continue
        out.append({
            "sector": sector,
            "count": len(values),
            "avg_change_24h": round(sum(values) / len(values), 2),
            "best": round(max(values), 2),
            "worst": round(min(values), 2),
        })

    out.sort(key=lambda x: -x["avg_change_24h"])
    return out


# ─────────────────────────────────────────────────────────────
# Сектора
# ─────────────────────────────────────────────────────────────
def build_veto_stats(candidates: list[Candidate]) -> list[dict]:
    """Частота причин вето: видно, какой фильтр режет больше всего."""
    counter: dict[str, dict] = {}
    for c in candidates:
        for v in c.veto:
            entry = counter.setdefault(v.code, {
                "code": v.code,
                "label": v.label,
                "severity": v.severity,
                "count": 0,
            })
            entry["count"] += 1

    out = list(counter.values())
    out.sort(key=lambda x: -x["count"])
    return out


# ─────────────────────────────────────────────────────────────
# Режим рынка
# ─────────────────────────────────────────────────────────────
def build_market_regime(candidates: list[Candidate], sectors: list[dict]) -> dict:
    """Оценка общего аппетита к риску по выборке."""
    if not candidates:
        return {"regime": "unknown", "appetite": 0, "note": "нет данных"}

    changes = [
        float(c.raw.get("ch_24h") or 0)
        for c in candidates
        if c.raw.get("ch_24h") is not None
    ]
    if not changes:
        return {"regime": "unknown", "appetite": 0, "note": "нет данных"}

    green_share = sum(1 for ch in changes if ch > 0) / len(changes)
    median_change = sorted(changes)[len(changes) // 2]
    tradable_share = (
        sum(1 for c in candidates if c.tradable) / len(candidates)
    )

    # Аппетит по пятибалльной шкале
    appetite = 1
    if green_share > 0.65:
        appetite = 5
    elif green_share > 0.55:
        appetite = 4
    elif green_share > 0.45:
        appetite = 3
    elif green_share > 0.35:
        appetite = 2

    if appetite >= 4:
        regime, note = "risk-on", "широкий рост, альты в фаворе"
    elif appetite == 3:
        regime, note = "neutral", "смешанная картина, чёткого потока нет"
    else:
        regime, note = "risk-off", "давление на альты, деньги уходят"

    return {
        "regime": regime,
        "appetite": appetite,
        "green_share": round(green_share * 100, 1),
        "median_change_24h": round(median_change, 2),
        "tradable_share": round(tradable_share * 100, 1),
        "leading_sector": sectors[0]["sector"] if sectors else "",
        "lagging_sector": sectors[-1]["sector"] if sectors else "",
        # green_share считается в build_market_regime и лежит в снимке,
        # но наружу до сих пор не выходил — как и median_change_24h,
        # tradable_share, leading_sector, lagging_sector.
        "greenShare": green_share,
        "note": note,
    }


# ─────────────────────────────────────────────────────────────
# Сборка снимка
# ─────────────────────────────────────────────────────────────
def build_snapshot(
    candidates: list[Candidate],
    total_scanned: int,
    duration: float,
    errors: int,
) -> RunSnapshot:
    sectors = build_sectors(candidates)

    counts = {
        "total": len(candidates),
        "viral": sum(1 for c in candidates if c.is_viral),
        "taiko": sum(1 for c in candidates if c.taiko),
        "dexe": sum(1 for c in candidates if c.dexe),
        "surge": sum(1 for c in candidates if c.surge),
        "vetoed": sum(1 for c in candidates if c.vetoed),
        "tradable": sum(1 for c in candidates if c.tradable),
        "strong": sum(1 for c in candidates if c.bucket == "strong"),
        "good": sum(1 for c in candidates if c.bucket == "good"),
        "scout": sum(1 for c in candidates if c.bucket == "scout"),
        "watch": sum(1 for c in candidates if c.bucket == "watch"),
    }

    return RunSnapshot(
        timestamp=RunSnapshot.now_iso(),
        total_scanned=total_scanned,
        duration_sec=duration,
        errors=errors,
        counts=counts,
        funnel=build_funnel(total_scanned, candidates),
        sectors=sectors,
        market_regime=build_market_regime(candidates, sectors),
        veto_stats=build_veto_stats(candidates),
        candidates=[c.to_dict() for c in candidates],
    )


# ─────────────────────────────────────────────────────────────
# Отчёт
# ─────────────────────────────────────────────────────────────
def render_report(candidates: list[Candidate], snapshot: RunSnapshot) -> bool:
    """Генерирует HTML в корень проекта. Отсутствие рендера не роняет прогон."""
    try:
        from render_page import build_page
    except ImportError as e:
        log(f"Рендер недоступен, отчёт не собран: {e}")
        return False

    try:
        html = build_page(candidates, snapshot)
        write_atomic(REPORT_PATH, html)
        return True
    except Exception as e:
        log(f"Ошибка сборки отчёта: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


# ─────────────────────────────────────────────────────────────
# Публикация в git
# ─────────────────────────────────────────────────────────────
def _git(*cmd: str) -> tuple[int, str]:
    """Запускает git-команду в корне проекта.

    Возвращает (код возврата, объединённый вывод). Исключения не пробрасывает:
    сбой публикации не должен ронять прогон и тем более планировщик.
    """
    try:
        proc = subprocess.run(
            ("git", *cmd),
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        return 127, "git не найден в PATH"
    except subprocess.TimeoutExpired:
        return 124, f"git {' '.join(cmd)} — таймаут {GIT_TIMEOUT_SEC}с"

    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out.strip()


def git_publish() -> bool:
    """add → commit → push. Пустой коммит не создаётся."""
    if not (BASE_DIR / ".git").exists():
        log("→ git: репозиторий не найден, публикация пропущена")
        return False

    code, out = _git("add", GIT_ADD_ALL_CHANGED) # GIT_ADD_HTML_ONLY | GIT_ADD_ALL_CHANGED
    if code != 0:
        log(f"✗ git add: {out}")
        return False

    # Нечего коммитить — не ошибка, просто данные не изменились
    code, _ = _git("diff", "--cached", "--quiet")
    if code == 0:
        log("→ git: изменений нет, коммит не нужен")
        return True

    code, out = _git("commit", "-nm", COMMIT_MSG)
    if code != 0:
        log(f"✗ git commit: {out}")
        return False

    code, out = _git("push")
    if code != 0:
        log(f"✗ git push: {out}")
        return False

    log("✓ Опубликовано в git")
    return True

# ─────────────────────────────────────────────────────────────
# Аргументы
# ─────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sleeping Alts Screener")
    p.add_argument("--limit", type=int, default=MAX_SYMBOLS,
                   help="сколько монет обрабатывать")
    p.add_argument("--symbols", type=str, default="",
                   help="конкретные монеты через запятую, например MYX,ZEC")
    p.add_argument("--workers", type=int, default=MAX_WORKERS,
                   help="число параллельных потоков")
    p.add_argument("--no-html", action="store_true",
                   help="не собирать HTML, только JSON")
    p.add_argument("--no-save", action="store_true",
                   help="не сохранять снимок прогона")
    p.add_argument("--loop", action="store_true",
                  help="повторять прогон бесконечно с интервалом --interval")
    p.add_argument("--interval", type=int, default=LOOP_INTERVAL_SEC,
                  help="интервал между прогонами в секундах, по умолчанию 3 часа")
    p.add_argument("--no-git", action="store_true",
                  help="не публиковать результат в git")
    return p.parse_args()


def resolve_explicit_symbols(raw: str) -> list[tuple[str, float]]:
    """Разбирает список монет из аргумента командной строки."""
    out: list[tuple[str, float]] = []
    for part in raw.split(","):
        sym = part.strip().upper()
        if not sym:
            continue
        if not sym.endswith("USDT"):
            sym += "USDT"
        out.append((sym, 0.0))
    return out



# ─────────────────────────────────────────────────────────────
# PREV MAIN
# ─────────────────────────────────────────────────────────────
def run_once(args: argparse.Namespace) -> int:
    """Один полный прогон. Возвращает код возврата."""
    started = time.monotonic()
    started = time.monotonic()

    # ── Отбор ──
    if args.symbols:
        symbols = resolve_explicit_symbols(args.symbols)
        select_stats = {"selected": len(symbols), "explicit": True}
        log(f"→ Явно заданы {len(symbols)} монет")
    else:
        log("→ Загружаю тикеры Binance Futures")
        # Журнал добавляется только на полном прогоне. Явный --limit
        # в докстроке файла описан как «только N монет, для отладки»,
        # то есть означает «столько и ни одной больше» — добавка
        # сверх него превращала прогон на одной монете в сотню.
        symbols, select_stats = select_symbols(
            args.limit, with_journal=(args.limit >= MAX_SYMBOLS),
        )
        if not symbols:
            log("✗ Не удалось получить тикеры")
            return 1
        log(f"→ Из {select_stats['total_pairs']} пар отобрано {len(symbols)}: "
            f"исключено {select_stats['excluded']}, "
            f"мало объёма у {select_stats['low_volume']}")

    # ── Анализ ──
    log(f"→ Обрабатываю в {args.workers} потоках")
    candidates, errors = analyze_all(symbols, args.workers)

    duration = time.monotonic() - started

    if errors:
        log(f"\n⚠ Ошибок: {len(errors)} из {len(symbols)}")
        for sym, err in errors[:10]:
            log(f"   {sym}: {err}")

    if not candidates:
        log("✗ Ни одной монеты не удалось проанализировать")
        return 1

    # ── Снимок ──
    snapshot = build_snapshot(candidates, len(symbols), duration, len(errors))

    log("\n→ Воронка отбора")
    for stage in snapshot.funnel:
        bar = "█" * max(1, int(stage.share_pct / 3))
        log(f"   {stage.label:<16} {stage.count:>4}  {bar} {stage.share_pct:>5.1f}%")

    if snapshot.veto_stats:
        log("\n→ Причины вето")
        for v in snapshot.veto_stats:
            log(f"   {v['label']:<16} {v['count']:>3}  ({v['severity']})")

    regime = snapshot.market_regime
    log(f"\n→ Режим рынка: {regime.get('regime', '—').upper()} · "
        f"аппетит {regime.get('appetite', 0)}/5 · "
        f"{regime.get('note', '')}")

    if snapshot.sectors:
        top = snapshot.sectors[0]
        bottom = snapshot.sectors[-1]
        log(f"→ Сектора: лидер {top['sector']} {top['avg_change_24h']:+.1f}%, "
            f"аутсайдер {bottom['sector']} {bottom['avg_change_24h']:+.1f}%")

    # ── Сравнение с прошлым прогоном ──
    if not args.no_save:
        diff = compare_with_previous(snapshot)
        if diff.get("has_previous"):
            if diff["new"]:
                log(f"→ Новые в работе: {', '.join(diff['new'][:8])}")
            if diff["gone"]:
                log(f"→ Выбыли из работы: {', '.join(diff['gone'][:8])}")

        path = save_snapshot(snapshot)
        log(f"→ Снимок сохранён: {path}")

    # Лидер прогона FLOW и аномальные объёмы — накопительные файлы
    # в output/ (analytics/leaders.py), не часть самого отчёта.
    #
    # Пишется ДО git_publish(): он коммитит output/ через `git add .`,
    # и если leaders/anomaly лягут после коммита — уедут в git только
    # со следующего прогона, на один run позже самого отчёта.
    flow_leaders_path, anomaly_path = update_leaders(candidates, snapshot)
    log(f"→ Лидер FLOW: {flow_leaders_path}")
    log(f"→ Аномальные объёмы: {anomaly_path}")

    # Пульс: показания всей выборки за последние двое суток. Рядом с
    # журналом и по той же причине — здесь у кандидатов уже посчитаны
    # метрики, сеть не нужна, а публикация ещё впереди.
    #
    # Пишется по ВСЕЙ выборке, а не по лидерам: монета попадает в журнал
    # ровно в тот момент, когда её карточку смотрят впервые, и без
    # предыстории эта карточка окажется без единой дельты — то есть без
    # ответа на вопрос, ради которого её открыли.
    #     log(f"→ Пульс: {pulse.record(candidates)}")

    # ── Отчёт ──
    published = False
    if not args.no_html:
        if render_report(candidates, snapshot):
            log(f"✓ Отчёт готов: {REPORT_PATH}")
            if not args.no_git:
                published = git_publish()

    log(f"\n✓ Прогон завершён за {duration:.0f}с · "
        f"{snapshot.counts['tradable']} монет к работе "
        f"из {len(candidates)} проанализированных"
        f"{' · опубликовано' if published else ''}")
    return 0

# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
def main() -> int:
    args = parse_args()

    if not args.loop:
        return run_once(args)

    interval = max(60, args.interval)
    log(f"→ Режим цикла: прогон каждые {interval // 3600}ч "
        f"{interval % 3600 // 60}мин · Ctrl+C для остановки")

    runs = 0
    while True:
        runs += 1
        log(f"\n{'═' * 60}\n→ Прогон #{runs} · "
            f"{datetime.now():%d.%m.%Y %H:%M:%S}\n{'═' * 60}")

        try:
            run_once(args)
        except Exception as e:
            # Падение одного прогона не должно убивать планировщик
            log(f"✗ Прогон #{runs} упал: {type(e).__name__}: {e}")
            traceback.print_exc()

        nxt = datetime.now() + timedelta(seconds=interval)
        log(f"\n→ Следующий прогон в {nxt:%H:%M:%S}")

        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            log("\n✗ Цикл остановлен")
            return 130


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n✗ Прервано пользователем")
        sys.exit(130)
