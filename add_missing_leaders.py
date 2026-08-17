#!/usr/bin/env python3
"""Возврат в журнал двух записей, потерянных при доработках.

Почему скриптом, а не заменой файла целиком: leaders.json переписывается
каждым прогоном, и присланная копия устаревает через полчаса. Скрипт
правит живой файл на месте и добавляет только отсутствующее — повторный
запуск ничего не портит и говорит «уже есть».

Запуск (сухой прогон, ничего не пишет):
    cd /Users/evgenijminko/Work/random/python && python3 add_missing_leaders.py

Запуск с записью (делает leaders.json.bak рядом):
    cd /Users/evgenijminko/Work/random/python && python3 add_missing_leaders.py --apply
"""

import json
import shutil
import sys
from pathlib import Path

PATH = Path("/Users/evgenijminko/Work/random/python/leaders.json")

# Момент возврата. В last_seen пишется он, в last_hit — дата входа:
# «видели запись» и «сработало семейство» это разные вопросы, и вторым
# распоряжается срок бездействия. Даты входа сняты с перекрестья на
# графиках (UTC+3 переведён в UTC).
TOUCHED_AT = "2026-08-17T19:37:12+00:00"

# Ниже — только то, что читается с графика или считается из него.
# Величины прогона (vol_ratio, up_x, зоны) перезапишутся на первом же
# запуске run.py, поэтому здесь стоят нейтральные значения, а не
# правдоподобные выдумки: vol_ratio это рекорды-максимумы, ноль они
# поднимут сами.
NEW = {
    "BLESSUSDT": {
        "first_seen": "2026-08-02T05:00:00+00:00",
        "entry_price": 0.012496,
        "price": 0.008154,
        "max_price": 0.0304,     # вершина 10-часовой свечи 2 августа
        "min_price": 0.008154,   # минимум после входа — текущая цена
        "last_hit": "2026-08-02T05:00:00+00:00",
        "entry_case": "flow_fuel",
        "hits": 1,
        "up_x": 1.02,            # от минимума окна ≈0.0080
        "max_up_x": 3.80,
        "horizon_days": 25,
        "horizon_tf": "недели",
    },
    "PROMUSDT": {
        "first_seen": "2026-08-09T13:00:00+00:00",
        "entry_price": 2.103,
        "price": 2.005,
        "max_price": 3.45,       # вершина двухдневной свечи 12 августа
        "min_price": 1.95,       # провал перед разгоном 11 августа
        "last_hit": "2026-08-09T13:00:00+00:00",
        "entry_case": "flow_fuel",
        "hits": 8,
        "up_x": 1.91,            # от минимума окна ≈1.05
        "max_up_x": 3.29,
        "horizon_days": 25,
        "horizon_tf": "недели",
    },
}


def build(sym: str, src: dict, runs: int) -> dict:
    """Полная запись журнала из снятых с графика величин.

    Ключи и их порядок повторяют существующие записи, чтобы отрисовка не
    спотыкалась на отсутствующем поле. Подсказки считаются по той же
    формуле, что и в коде: стоп 0.965 от зоны, цель 1.12 — проверено по
    всем тридцати записям файла.
    """
    entry = src["entry_price"]
    zone = entry  # настоящий уровень зоны восстановить нечем
    rec = {
        "first_seen": src["first_seen"],
        "entry_price": entry,
        "price": src["price"],
        "change_pct": round((src["price"] / entry - 1) * 100, 2),
        "max_price": src["max_price"],
        "max_change_pct": round((src["max_price"] / entry - 1) * 100, 2),
        "min_price": src["min_price"],
        "min_change_pct": round((src["min_price"] / entry - 1) * 100, 2),
        "vol_ratio": {"2h": 0.0, "6h": 0.0, "12h": 0.0, "4h": 0.0, "1d": 0.0},
        "last_seen": TOUCHED_AT,
        "entry_case": src["entry_case"],
        "zone_price": zone,
        "stop_hint": zone * 0.965,
        "target_hint": zone * 1.12,
        "horizon_days": src["horizon_days"],
        "horizon_tf": src["horizon_tf"],
        "streak": 1,
        # Счётчик прогонов моложе обеих записей (156 прогонов ≈ 3,5 суток),
        # поэтому since_run=1 и runs_seen=runs — ровно как у остальных
        # дореестровых монет журнала.
        "runs_seen": runs,
        "hit_rate": round(src["hits"] / runs, 3) if runs else 0.0,
        "last_hit": src["last_hit"],
        "hits": src["hits"],
        "since_run": 1,
        "up_x": src["up_x"],
        "max_up_x": src["max_up_x"],
        "trend_done": False,
        "now_up_x": src["up_x"],
        # Флаг ручного добавления: ни правило завершения цикла, ни срок
        # бездействия такие записи не трогают. Без него BLESS снесёт при
        # первом же прогоне — её вход был 15 дней назад.
        "added_manually": True,
    }
    return rec


def main() -> int:
    apply = "--apply" in sys.argv
    store = json.loads(PATH.read_text())
    runs = int((store.get("_meta") or {}).get("runs") or 0)

    added = []
    for sym, src in NEW.items():
        if sym in store:
            print(f"уже есть  {sym}")
            continue
        store[sym] = build(sym, src, runs)
        added.append(sym)
        rec = store[sym]
        print(f"добавляю  {sym}: вход {rec['entry_price']} от "
              f"{rec['first_seen'][:10]}, сейчас {rec['change_pct']}%, "
              f"ход был {rec['max_change_pct']}%, hits {rec['hits']}")

    if not added:
        print("\nничего делать не нужно")
        return 0
    if not apply:
        print("\nсухой прогон, файл не тронут. Повтори с --apply")
        return 0

    shutil.copy2(PATH, PATH.with_suffix(".json.bak"))
    PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2))
    print(f"\nзаписано, копия в {PATH.with_suffix('.json.bak').name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
