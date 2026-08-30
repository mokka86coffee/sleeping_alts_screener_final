#!/usr/bin/env python3
"""Врезка CryptoQuant в run.py — версия с конфигом (30.08, ночь).

Двурежимный: на чистом run.py ставит врезку целиком; на run.py с
уже накатанной первой версией — добавляет в неё чтение config.json.
Повторный запуск безвреден: скажет, что всё на месте.

Смысл врезки: прогон ежечасный, дневка кванта одна в сутки, поэтому
встраивается проверка свежести (ensure_fresh тянет дозабор, только
когда архиву cq_v2 больше двадцати часов). Ключи — из config.json
рядом с run.py (модуль config.py), явный export главнее файла.

Рядом с run.py должны лежать: config.py, cq_scheduler.py,
cryptoquant_fetch.py, config.json (по образцу config.example.json).
Запуск: python3 patch_run_cq.py
"""
import ast

s = open("run.py", encoding="utf-8").read()

CFG = '''        try:                                  # ключи из config.json,
            from config import load as _cfg  # export главнее файла
            _cfg()
        except Exception:
            pass
'''
TOKEN_CHECK = '        if not _os.environ.get("CQ_TOKEN", "").strip():'

if "CryptoQuant v2 (30.08)" in s:
    # режим Б: врезка есть — доложить конфиг, если его ещё нет
    if "from config import load" in s:
        print("врезка уже с конфигом — делать нечего")
        raise SystemExit(0)
    assert s.count(TOKEN_CHECK) == 1, "врезка есть, а якорь проверки — нет"
    s = s.replace(TOKEN_CHECK, CFG + TOKEN_CHECK)
    open("run.py", "w", encoding="utf-8").write(s)
    ast.parse(s)
    print("врезка обновлена: ключи теперь из config.json")
    raise SystemExit(0)

# режим А: чистый run.py — полная врезка
anchor = '''        log(f"→ Coinglass пропущен: {type(e).__name__}: {e}")

    # ── Ручные контуры — по своим отрезкам, не каждый прогон ──'''
assert s.count(anchor) == 1, "якорь Coinglass→Ручные не найден или не один"

insert = '''        log(f"→ Coinglass пропущен: {type(e).__name__}: {e}")

    # CryptoQuant v2 (30.08): суточный дозабор деривативов журнала
    # в архив cq_v2/ (funding, OI, ликвидации, свечи, тейкеры — по
    # <base>_all). Прогон ежечасный, а дневка кванта одна в сутки,
    # поэтому здесь не сбор, а проверка свежести: ensure_fresh
    # тянет только если архиву больше двадцати часов — правило
    # «от свежести файла, не по кругу». Ключи — config.json рядом
    # с run.py (модуль config), явный export главнее; нет токена
    # или сбой — лог и пропуск, как почта.
    try:
        import os as _os
''' + CFG + '''        if not _os.environ.get("CQ_TOKEN", "").strip():
            log("→ CryptoQuant пропущен: нет CQ_TOKEN (config.json?)")
        else:
            from pathlib import Path as _P
            from cq_scheduler import ensure_fresh as _cq_fresh
            _base = _P(__file__).resolve().parent
            _j = _base / "output" / "leaders.json"
            if not _j.exists():
                _j = _base / "leaders.json"
            _ok = _cq_fresh(str(_j), _base / "cq_v2")
            log("→ CryptoQuant: архив свеж" if _ok
                else "→ CryptoQuant: дозабор не удался (см. cq_v2/_fetch.log)")
    except Exception as e:
        log(f"→ CryptoQuant пропущен: {type(e).__name__}: {e}")

    # ── Ручные контуры — по своим отрезкам, не каждый прогон ──'''

s = s.replace(anchor, insert)
open("run.py", "w", encoding="utf-8").write(s)
ast.parse(s)
print("врезка CryptoQuant с конфигом легла")
