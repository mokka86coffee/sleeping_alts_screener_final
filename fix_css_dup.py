#!/usr/bin/env python3
"""Убирает повторные копии блока стилей экрана лидеров в css.py.

Зачем отдельный скрипт, а не патч: копии отличаются друг от друга
несколькими строками, и якорь «было» для любой из них найдётся в
обеих. Скрипт режет по границам блока, а не по совпадению текста.

Копии появились из-за того, что patch-podium.md правился на месте под
одним именем. Проверка «уже применено» в apply_patch.py сравнивает
текст «стало»; он менялся от версии к версии, поэтому скрипт не
узнавал собственную вставку и добавлял её заново.

Оставляется ПОСЛЕДНЯЯ копия: правки дописывались в конец очереди, и
последняя всегда самая полная.

    python3 fix_css_dup.py /путь/к/репозиторию            проверка
    python3 fix_css_dup.py /путь/к/репозиторию --apply    запись
"""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

MARK = "/* ── Экран лидеров ─"
STOP = ".obf-foot,.obf-bar{opacity:0"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    root = Path(sys.argv[1]).resolve()
    apply = "--apply" in sys.argv
    path = root / "render" / "css.py"

    if not path.exists():
        print(f"файла нет: {path}")
        return 2

    text = path.read_text(encoding="utf-8")

    starts = []
    i = text.find(MARK)
    while i != -1:
        starts.append(i)
        i = text.find(MARK, i + 1)

    if len(starts) <= 1:
        print(f"копий блока: {len(starts)} — чистить нечего")
        return 0

    stop = text.find(STOP, starts[-1])
    if stop == -1:
        print("не найден конец блока (.obf-foot,.obf-bar) — не трогаю")
        return 1

    # Каждая копия тянется до начала следующей, последняя — до STOP.
    # Режем всё, кроме последней: она самая полная.
    cut_from, cut_to = starts[0], starts[-1]
    removed = text[cut_from:cut_to]
    out = text[:cut_from] + text[cut_to:]

    print(f"копий блока: {len(starts)}")
    print(f"удаляется: {removed.count(chr(10))} строк, {len(removed)} байт")
    print(f"остаётся последняя, {stop - starts[-1]} байт")

    # Проверка на выстрел в ногу: в остатке блок обязан быть ровно один.
    if out.count(MARK) != 1:
        print("после правки копий не одна — отменяю")
        return 1
    # Ключи выбраны так, чтобы каждый встречался ровно один раз.
    # Короткие селекторы вроде '.ob-podium{' не годятся: они есть и в
    # медиазапросе, то есть законно повторяются — первая редакция
    # проверки на этом и отменила запись.
    for key in (".ob-podium{position:fixed", "@keyframes pd-rise{",
                "@keyframes pd-draw{", ".obp-in{"):
        if out.count(key) != 1:
            print(f"после правки '{key}' встречается {out.count(key)} раз — отменяю")
            return 1

    if not apply:
        print("\nПроверка. Повторить с --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, str(path) + f".bak-{stamp}")
    path.write_text(out, encoding="utf-8")
    print(f"\nЗаписано. Копия: css.py.bak-{stamp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
