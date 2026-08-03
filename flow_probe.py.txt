"""Диагностический прогон FLOW по всем монетам.

Не фильтрует и не отбирает: задача — собрать сырой срез, по которому
видно, где подкейсы недобирают. Пишет CSV для сводных цифр и JSON
с полным разбором сработавших монет.

Запуск:
    python flow_probe.py              полный прогон, сеть включена
    python flow_probe.py --no-net     без funding и OI, быстрее
    python flow_probe.py --limit 50   первые 50 монет по обороту
    python flow_probe.py --with-tokenized   не отсеивать акции и сырьё
"""

from __future__ import annotations

import csv
import json
import sys
import time
import traceback
from collections import Counter
from datetime import datetime

from core.binance import drop_symbol_cache, get_futures_tickers
from detectors.flow import MIN_RAW_SCORE, detect_flow

MIN_QUOTE_VOLUME = 5_000_000  # ниже этого монета неторгуема, шум в статистике

# Сколько монет сохранить с полным контекстом.
#
# Поднято с 25: при сорока срабатываниях наблюдаемые монеты из WATCH
# вытеснялись сработавшими и в JSON не попадали, а именно ради них
# список и заводился.
DEEP_DUMP_LIMIT = 80

# Подкейсы в порядке зрелости. Одно место, из которого берутся и
# колонки CSV, и разделы сводки: добавление модуля — одна строка.
CASES = ("hidden", "spring", "churn", "taker", "fuel", "leverage")

# Монеты, разбор которых сохраняется в JSON независимо от того,
# сработали они или нет. Нужен, чтобы видеть ПРИЧИНУ молчания:
# в CSV попадают только итоговые числа, а отказ происходит внутри
# подкейса — на плато, на тирах, на возрасте зоны. Без контекста
# молчащей монеты калибровать пороги можно только вслепую.
WATCH = {
    "COTIUSDT",
    "KOMAUSDT",
    "MMTUSDT",
    "AKEUSDT",
    "EPICUSDT",
    "LDOUSDT",
}

# ─────────────────────────────────────────────────────────────
# Некриптовые инструменты
# ─────────────────────────────────────────────────────────────
# Токенизированные акции, ETF, металлы, сырьё и стейблкоины торгуются
# на бирже теми же парами к USDT, но живут по другому календарю:
# выходные, клиринг, гэпы на открытии. Ряд дневных баров у них рваный,
# из-за чего наклоны дельты и цены считаются по несопоставимым
# промежуткам, плато меряется в календарных днях вместо торговых, а
# growth_x ловит гэп вместо движения.
#
# Пороги семейства калибруются по круглосуточному рынку, поэтому такие
# инструменты дают систематический перекос — в последнем срезе именно
# они наполнили fuel слабыми срабатываниями (CL, BZ, IBM, COPPER,
# BABA при девяти-двадцати событиях).
#
# Список ведётся перечислением, а не эвристикой по имени: тикеры вроде
# MUUSDT (Micron) и MUSDT (крипта) различаются одной буквой, и любое
# правило по подстроке будет резать живые монеты. Состав меняется
# медленно, дополнять руками дешевле, чем отлаживать угадывание.
NON_CRYPTO = {
    # Акции США
    "AAPLUSDT", "MSFTUSDT", "NVDAUSDT", "TSLAUSDT", "AMZNUSDT",
    "GOOGLUSDT", "METAUSDT", "AMDUSDT", "INTCUSDT", "MUUSDT",
    "MRVLUSDT", "AVGOUSDT", "QCOMUSDT", "IBMUSDT", "ORCLUSDT",
    "DELLUSDT", "WDCUSDT", "SNDKUSDT", "AXTIUSDT", "AAOIUSDT",
    "NOKUSDT", "GLWUSDT", "FLNCUSDT", "RKLBUSDT", "IRENUSDT",
    "NBISUSDT", "CRWVUSDT", "CRCLUSDT", "COINUSDT", "HOODUSDT",
    "MSTRUSDT", "PLTRUSDT", "BMNRUSDT", "SPCXUSDT", "RIVERUSDT",
    "TSMUSDT", "ASMLUSDT", "ARMUSDT", "BABAUSDT", "HK1810USDT",
    "SAMSUNGUSDT", "SKHYNIXUSDT", "SKHYUSDT", "KORUUSDT",
    "MUUUSDT", "SNXXUSDT", "STXXUSDT", "MVLLUSDT", "CBRSUSDT",
    "ZHIPUUSDT", "MINIMAXUSDT", "GRAMUSDT", "BEUSDT", "BZUSDT",
    # ETF и индексы
    "QQQUSDT", "TQQQUSDT", "SQQQUSDT", "SPYUSDT", "SOXLUSDT",
    "SOXSUSDT", "EWYUSDT",
    # Металлы, сырьё, энергия
    "XAUUSDT", "XAGUSDT", "XPTUSDT", "COPPERUSDT", "NATGASUSDT",
    "CLUSDT", "DRAMUSDT",
    # Обёртки золота и стейблкоины: движения нет по построению
    "PAXGUSDT", "XAUTUSDT", "USDCUSDT",
}

STAMP = datetime.now().strftime("%Y%m%d_%H%M")
CSV_PATH = f"flow_probe_{STAMP}.csv"
JSON_PATH = f"flow_probe_{STAMP}.json"

FIELDS = [
    "symbol", "detected", "score", "case", "strength",
    "horizon_days", "horizon_tf",
    *CASES,
    "zone_price", "events", "zones", "zones_conf",
    "vortex_scale", "vortex_spread",
    "collapsing", "growth_x", "failures", "error",
]


def load_universe(limit: int = 0, skip_tokenized: bool = True) -> list[tuple[str, float]]:
    """Символы с объёмом, отсортированные по убыванию ликвидности."""
    out: list[tuple[str, float]] = []
    for t in get_futures_tickers():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if skip_tokenized and sym in NON_CRYPTO:
            continue
        try:
            qv = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if qv >= MIN_QUOTE_VOLUME:
            out.append((sym, qv))
    out.sort(key=lambda x: -x[1])
    return out[:limit] if limit else out


def _case_score(cases: dict, short: str) -> float:
    """Скор подкейса по короткому имени. 0, если не сработал."""
    row = cases.get(f"flow_{short}") or cases.get(short) or {}
    try:
        return round(float(row.get("score", 0.0)), 1)
    except (TypeError, ValueError):
        return 0.0


def _stats(values: list[float]) -> str:
    """Медиана и края по ненулевым значениям."""
    live = sorted(v for v in values if v > 0)
    if not live:
        return "нет срабатываний"
    med = live[len(live) // 2]
    return (
        f"ненулевых {len(live):3d}  "
        f"мин {live[0]:5.1f}  медиана {med:5.1f}  макс {live[-1]:5.1f}"
    )


def main() -> None:
    allow_network = "--no-net" not in sys.argv
    skip_tokenized = "--with-tokenized" not in sys.argv
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            limit = 0

    symbols = load_universe(limit, skip_tokenized=skip_tokenized)
    net = "включена" if allow_network else "выключена"
    filt = "крипта" if skip_tokenized else "всё, включая акции и сырьё"
    print(f"Монет к прогону: {len(symbols)}, сеть для leverage: {net}")
    print(f"Состав выборки: {filt}")

    rows: list[dict] = []
    deep: list[dict] = []
    fail_counter: Counter[str] = Counter()
    fail_samples: dict[str, str] = {}
    started = time.time()

    for i, (symbol, qv) in enumerate(symbols, 1):
        row = {k: "" for k in FIELDS}
        row["symbol"] = symbol
        row["detected"] = 0
        row["score"] = 0
        for c in CASES:
            row[c] = 0.0

        try:
            sig = detect_flow(symbol, qv, allow_network=allow_network)
            d = sig.to_dict()
            cases = d.get("cases") or {}
            ctx = d.get("context") or {}
            parts = d.get("parts") or []
            flow = ctx.get("flow") or {}
            drop = ctx.get("drop") or {}
            vortex = ctx.get("vortex") or {}
            fails = d.get("failures") or {}

            row.update(
                detected=int(bool(d.get("detected"))),
                score=d.get("score", 0),
                case=d.get("case", ""),
                strength=d.get("strength_label", ""),
                horizon_days=d.get("horizon_days", 0),
                horizon_tf=d.get("horizon_tf", ""),
                events=ctx.get("events_total", ""),
                zones=len(ctx.get("zones") or []),
                zones_conf=ctx.get("zones_confirmed", 0),
                vortex_scale=vortex.get("scale", ""),
                vortex_spread=vortex.get("spread", ""),
                collapsing=int(bool(flow.get("collapsing"))),
                growth_x=drop.get("growth_x", ""),
                zone_price=(parts[0].get("zone_price") if parts else ""),
                failures=";".join(sorted(fails)),
            )
            for c in CASES:
                row[c] = _case_score(cases, c)

            for mod, text in fails.items():
                fail_counter[mod] += 1
                fail_samples.setdefault(mod, text)

            if (d.get("detected") or symbol in WATCH) and len(deep) < DEEP_DUMP_LIMIT:
                deep.append(d)

        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        finally:
            drop_symbol_cache(symbol)

        rows.append(row)
        if i % 25 == 0:
            el = time.time() - started
            hits = sum(r["detected"] == 1 for r in rows)
            print(f"  {i}/{len(symbols)}  срабатываний {hits}  {el:.0f}с")

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    with open(JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(deep, f, ensure_ascii=False, indent=2)

    # ── Сводка ──
    total = len(rows)
    ok = [r for r in rows if not r["error"]]
    hits = [r for r in ok if r["detected"] == 1]
    errs = [r for r in rows if r["error"]]

    print("\n" + "=" * 52)
    print(f"Всего монет:          {total}")
    print(f"Прошло без ошибок:    {len(ok)}")
    print(f"Ошибок:               {len(errs)}")
    print(f"Срабатываний:         {len(hits)} ({len(hits) / max(total, 1) * 100:.1f}%)")

    print("\nПобедители:")
    by_case = Counter(r["case"] for r in hits)
    for name, n in by_case.most_common():
        print(f"  {name:16s} {n}")

    # ── Поимённый разбор по стратегиям ──
    # Сводные числа показывают, сколько сработало, но не ЧТО именно.
    # Без имён каждый разбор начинается с ручной выборки из CSV, а
    # глазами по срезу видно сразу: попала ли монета в тот подкейс,
    # который ей соответствует по смыслу, и какой ценой — за счёт
    # собственной силы или подтверждения соседом.
    print("\n" + "─" * 52)
    print("Кто в какую стратегию попал")
    for case_name, _ in by_case.most_common():
        group = [r for r in hits if r["case"] == case_name]
        group.sort(key=lambda x: -x["score"])
        print(f"\n  {case_name}  ({len(group)})")
        for r in group:
            short = case_name.replace("flow_", "")
            own = r.get(short, 0.0)
            # Подкейсы, которые тоже собрались на этой монете, —
            # подтверждение победителя другим прочтением картины.
            support = [
                f"{c}{r[c]:.0f}"
                for c in CASES
                if c != short and isinstance(r[c], (int, float)) and r[c] > 0
            ]
            tail = ("  + " + " ".join(support)) if support else ""
            print(
                f"    {r['symbol']:16s} {r['score']:3d}  "
                f"{short} {own:5.1f}  "
                f"{r['horizon_days']:>2}д  "
                f"зон {r['zones']:>2}  соб {str(r['events']):>3}"
                f"{tail}"
            )

    print("\nШкалы подкейсов (сырой скор до сведения):")
    for c in CASES:
        vals = [r[c] for r in ok if isinstance(r[c], (int, float))]
        print(f"  {c:9s} {_stats(vals)}")

    # ── Тихие падения ──
    # Подкейс, который ни разу не сработал, может быть либо честно
    # молчащим, либо сломанным. Различить можно только здесь:
    # flow.py ловит исключения, чтобы не ронять прогон, и без этого
    # раздела опечатка выглядит как свойство рынка.
    if fail_counter:
        print("\nИсключения в подкейсах:")
        for mod, n in fail_counter.most_common():
            print(f"  {mod:16s} {n:3d}  {fail_samples[mod]}")
    else:
        print("\nИсключений в подкейсах нет.")

    silent = [
        c for c in CASES
        if not any(r[c] for r in ok if isinstance(r[c], (int, float)))
    ]
    if silent:
        print(f"Ни разу не собрались: {', '.join(silent)}")

    # ── Недобор ──
    near = [
        r for r in ok
        if r["detected"] == 0 and r["score"] >= MIN_RAW_SCORE - 10
    ]
    print(f"\nНедобрали до порога в пределах 10 баллов: {len(near)}")
    for r in sorted(near, key=lambda x: -x["score"])[:15]:
        parts = " ".join(f"{c[0]}{r[c]:5.1f}" for c in CASES)
        print(f"  {r['symbol']:14s} {r['score']:3d}  {parts}")

    # ── Наблюдаемые ──
    # Монеты из WATCH, которые не сработали. Их разбор лежит в JSON,
    # здесь — только напоминание, что смотреть.
    watched_quiet = [
        r for r in ok if r["symbol"] in WATCH and r["detected"] == 0
    ]
    if watched_quiet:
        print("\nНаблюдаемые, оставшиеся молчать (контекст в JSON):")
        for r in watched_quiet:
            parts = " ".join(f"{c[0]}{r[c]:5.1f}" for c in CASES)
            print(
                f"  {r['symbol']:14s} зон {r['zones']:>2}  "
                f"соб {str(r['events']):>3}  "
                f"обвал {r['collapsing']}  {parts}"
            )

    # ── Контекстные вето ──
    # Не срабатывания, а причины молчания. Нужны, чтобы понимать,
    # что именно рубит выборку: обвал дельты, отсутствие зон или
    # экстремальный рост.
    quiet = [r for r in ok if r["detected"] == 0]
    collapsing = sum(1 for r in quiet if r["collapsing"] == 1)
    no_zones = sum(1 for r in quiet if r["zones"] == 0)
    print(
        f"\nСреди молчащих: обвал дельты {collapsing}, "
        f"без живых зон {no_zones}, всего {len(quiet)}"
    )

    if errs:
        print("\nОшибки:")
        for r in errs[:10]:
            print(f"  {r['symbol']:14s} {r['error']}")

    print(f"\nФайлы: {CSV_PATH}, {JSON_PATH}")


if __name__ == "__main__":
    main()
