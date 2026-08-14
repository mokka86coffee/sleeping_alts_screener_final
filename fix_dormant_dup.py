#!/usr/bin/env python3
"""Убирает неполную копию блока flow_dormant в flow_config.py.

Копий оказалось две: первая от patch-dormant.md, вторая — она же плюс
константы из patch-dormant-flush.md. Значения в общей части совпадают,
поэтому ничего не ломается, но CAP_DORMANT и DORMANT_SCORE_BASE
объявлены дважды, а это ровно тот случай, когда правка одного из двух
мест расходится молча.

Патчем не делаю: копии почти одинаковы, и якорь «было» для любой
нашёлся бы в обеих. Скрипт режет по границам блока и оставляет ту
копию, где есть константы второго патча.

    python3 fix_dormant_dup.py /путь/к/репозиторию            проверка
    python3 fix_dormant_dup.py /путь/к/репозиторию --apply    запись
"""

from __future__ import annotations

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

MARK = "# ─────────────────────────────────────────────────────────────\n# flow_dormant\n"
# Константа, которая есть только в полной копии.
FULL = "DORMANT_BOUNCE_MIN"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    root = Path(sys.argv[1]).resolve()
    apply = "--apply" in sys.argv
    path = root / "detectors" / "flow_config.py"

    if not path.exists():
        print(f"файла нет: {path}")
        return 2

    text = path.read_text(encoding="utf-8")
    starts = [m.start() for m in re.finditer(re.escape(MARK), text)]

    if len(starts) <= 1:
        print(f"копий блока: {len(starts)} — чистить нечего")
        return 0

    # Границы: каждая копия тянется до начала следующей, последняя —
    # до конца файла.
    bounds = []
    for i, a in enumerate(starts):
        b = starts[i + 1] if i + 1 < len(starts) else len(text)
        bounds.append((a, b))

    keep = [i for i, (a, b) in enumerate(bounds) if FULL in text[a:b]]
    if len(keep) != 1:
        print(f"полных копий {len(keep)} вместо одной — не трогаю, "
              f"разбирайся руками")
        return 1

    k = keep[0]
    out = text
    # Режем с конца, чтобы индексы не поехали.
    for i in sorted(range(len(bounds)), reverse=True):
        if i == k:
            continue
        a, b = bounds[i]
        print(f"удаляется копия {i + 1}: {text[a:b].count(chr(10))} строк")
        out = out[:a] + out[b:]

    # Проверка на выстрел в ногу.
    for key in ("CAP_DORMANT = ", "DORMANT_SCORE_BASE = ",
                "DORMANT_BOUNCE_MIN = ", "DORMANT_WAKE_X = "):
        n = out.count(key)
        if n != 1:
            print(f"после правки '{key.strip()}' встречается {n} раз — отменяю")
            return 1

    try:
        compile(out, str(path), "exec")
    except SyntaxError as e:
        print(f"после правки синтаксис сломан (строка {e.lineno}) — отменяю")
        return 1

    print(f"остаётся копия {k + 1}, в ней константы обоих патчей")

    if not apply:
        print("\nПроверка. Повторить с --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, str(path) + f".bak-{stamp}")
    path.write_text(out, encoding="utf-8")
    print(f"\nЗаписано. Копия: flow_config.py.bak-{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
