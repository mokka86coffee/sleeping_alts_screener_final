#!/usr/bin/env python3
"""Чинит ReferenceError: twoOpen is not defined (31.08).

Остаток двухколоночной вёрстки: строку закрытия `if (twoOpen)`
оставили, а объявление `var twoOpen` ушло вместе с колонками при
переходе на три полосы-горизонта. Карточка монеты падала при
наведении на строку зала.

Скрипт: если объявления нет — убирает осиротевшую строку; если
объявление есть (старая версия файла) — не трогает ничего.
Запуск рядом с render_podium.py:  python3 patch_podium_twoopen.py
"""
import ast

p = "render_podium.py"
s = open(p, encoding="utf-8").read()

orphan = "    if (twoOpen) h += '</div></div>';\n"
has_decl = "var twoOpen" in s

if orphan not in s:
    print("строки `if (twoOpen)` нет — чинить нечего")
    raise SystemExit(0)
if has_decl:
    print("объявление на месте — это старая версия, не трогаю")
    raise SystemExit(0)

s = s.replace(orphan, "")
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
assert "twoOpen" not in s, "остались упоминания twoOpen"
print("осиротевшая строка убрана — карточка монеты откроется")
