#!/usr/bin/env python3
"""Врезка китов в run.py (31.08): каждым прогоном свежий
output/whales.json из Coinglass Hyperliquid — корм пузырям схемы.
Рядом должен лежать whales_coinglass.py. Сбой — лог и пропуск.
Запуск рядом с run.py:  python3 patch_run_whales.py"""
import ast

s = open("run.py", encoding="utf-8").read()
if "Киты Coinglass" in s:
    print("врезка китов уже стоит — делать нечего")
    raise SystemExit(0)
anchor = '''    except Exception as e:
        log(f"→ Репутации пропущены: {type(e).__name__}: {e}")'''
assert s.count(anchor) == 1, "якорь блока репутаций не найден"
s = s.replace(anchor, anchor + '''

    # Киты Coinglass (31.08): свежие действия и позиции китов
    # Hyperliquid → output/whales.json; пузыри схемы читают файл.
    try:
        from whales_coinglass import collect as _wh_collect
        log(f"→ Киты: {_wh_collect(write=True)}")
    except Exception as e:
        log(f"→ Киты пропущены: {type(e).__name__}: {e}")''')
open("run.py", "w", encoding="utf-8").write(s)
ast.parse(s)
print("киты собираются каждым прогоном")
