"""Диагностический прогон FLOW по всем монетам.

Не фильтрует и не отбирает: задача — собрать сырой срез, по которому
видно, где подкейсы недобирают. Пишет CSV для сводных цифр и JSON
с полным разбором первых сработавших монет.

Запуск:  python flow_probe.py
"""

from __future__ import annotations

import csv
import json
import time
import traceback
from datetime import datetime

from core.binance import drop_symbol_cache, get_futures_tickers
from detectors.flow import MIN_SCORE, detect_flow

MIN_QUOTE_VOLUME = 5_000_000  # ниже этого монета неторгуема, шум в статистике


def load_universe() -> list[tuple[str, float]]:
    """Символы с объёмом, отсортированные по убыванию ликвидности."""
    out: list[tuple[str, float]] = []
    for t in get_futures_tickers():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        try:
            qv = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if qv >= MIN_QUOTE_VOLUME:
            out.append((sym, qv))
    out.sort(key=lambda x: -x[1])
    return out

# Сколько монет с detected сохранить с полным контекстом
DEEP_DUMP_LIMIT = 25

STAMP = datetime.now().strftime("%Y%m%d_%H%M")
CSV_PATH = f"flow_probe_{STAMP}.csv"
JSON_PATH = f"flow_probe_{STAMP}.json"

FIELDS = [
    "symbol", "detected", "score", "case", "strength",
    "horizon_days", "horizon_tf", "horizon_readable",
    "spring", "churn", "fuel",
    "zone_price", "plateau_bars", "scale", "error",
]


def _case_score(cases: dict, name: str) -> float:
    row = cases.get(name) or cases.get(f"flow_{name}") or {}
    return round(row.get("score", 0.0), 1)


def main() -> None:
    symbols = load_universe()
    print(f"Монет к прогону: {len(symbols)}")

    rows: list[dict] = []
    deep: list[dict] = []
    started = time.time()

    for i, (symbol, qv) in enumerate(symbols, 1):
        row = {k: "" for k in FIELDS}
        row["symbol"] = symbol
        try:
            sig = detect_flow(symbol, qv)
            d = sig.to_dict()
            cases = d.get("cases") or {}
            ctx = d.get("context") or {}
            parts = d.get("parts") or []

            row.update(
                detected=int(bool(d.get("detected"))),
                score=d.get("score", 0),
                case=d.get("case", ""),
                strength=d.get("strength_label", ""),
                horizon_days=d.get("horizon_days", 0),
                horizon_tf=d.get("horizon_tf", ""),
                horizon_readable=int(bool(d.get("horizon_readable"))),
                spring=_case_score(cases, "spring"),
                churn=_case_score(cases, "churn"),
                fuel=_case_score(cases, "fuel"),
                scale=ctx.get("scale", ""),
                plateau_bars=ctx.get("plateau_bars", ""),
                zone_price=(parts[0].get("zone_price") if parts else ""),
            )

            if d.get("detected") and len(deep) < DEEP_DUMP_LIMIT:
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

    print("\n" + "=" * 46)
    print(f"Всего монет:        {total}")
    print(f"Прошло без ошибок:  {len(ok)}")
    print(f"Ошибок:             {len(errs)}")
    print(f"Срабатываний:       {len(hits)}  ({len(hits) / max(total, 1) * 100:.1f}%)")

    by_case: dict[str, int] = {}
    for r in hits:
        by_case[r["case"]] = by_case.get(r["case"], 0) + 1
    for name, n in sorted(by_case.items(), key=lambda x: -x[1]):
        print(f"   {name:10s} {n}")

    for name in ("spring", "churn", "fuel"):
        vals = [r[name] for r in ok if isinstance(r[name], (int, float))]
        live = [v for v in vals if v > 0]
        if live:
            live.sort()
            print(
                f"{name:8s} ненулевых {len(live):3d}  "
                f"медиана {live[len(live) // 2]:5.1f}  макс {live[-1]:5.1f}"
            )

    near = [r for r in ok if r["detected"] == 0 and r["score"] >= MIN_SCORE - 10]
    print(f"\nНедобрали до порога в пределах 10 баллов: {len(near)}")
    for r in sorted(near, key=lambda x: -x["score"])[:15]:
        print(f"   {r['symbol']:14s} {r['score']:3d}  s{r['spring']:5.1f} c{r['churn']:5.1f} f{r['fuel']:5.1f}")

    if errs:
        print("\nОшибки:")
        for r in errs[:10]:
            print(f"   {r['symbol']:14s} {r['error']}")

    print(f"\nФайлы: {CSV_PATH}, {JSON_PATH}")


if __name__ == "__main__":
    main()
