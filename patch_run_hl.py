#!/usr/bin/env python3
"""Снос Hyperliquid из run.py (30.08, приговор приведён).

Контур падал каждым прогоном (AttributeError: их API сменил формат
ответа) и первой строкой лога мусорил месяц. Coinglass кроет тот же
вопрос шестьюдесятью восемью монетами без единой ошибки — чинить
мёртвое незачем, выносим. Блок заменяется одной строкой-памяткой,
чтобы место в логике не потерялось: захотим китов — вернём через
живой источник (Arkham/Coinalyze), не через сломанный.

Повторный запуск безвреден. Запуск рядом с run.py:
    python3 patch_run_hl.py
"""
import ast

s = open("run.py", encoding="utf-8").read()

if "Hyperliquid снят" in s:
    print("Hyperliquid уже снят — делать нечего")
    raise SystemExit(0)

anchor = '''    # Киты Hyperliquid (Т-1): срез позиций отслеживаемых адресов из'''
assert s.count(anchor) == 1, "якорь блока Hyperliquid не найден"
i = s.index(anchor)
tail = '''        log(f"→ Hyperliquid пропущен: {type(e).__name__}: {e}")'''
j = s.index(tail, i) + len(tail)

s = s[:i] + '''    # Hyperliquid снят (30.08): их API сменил формат, контур падал
    # каждым прогоном и мусорил лог. Китов при нужде вернём живым
    # источником (Arkham по адресам из unlocks.json), не починкой
    # мёртвого. Файл sources_hyperliquid.py оставлен на диске.''' + s[j:]

open("run.py", "w", encoding="utf-8").write(s)
ast.parse(s)
print("Hyperliquid вынесен; лог станет чище на одну ошибку")
