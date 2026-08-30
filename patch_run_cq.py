#!/usr/bin/env python3
"""Врезка CryptoQuant в run.py (30.08.2026, ночь).

Прогон крутится каждый час (--loop --interval 3600); квантовому
архиву нужна одна дневка в сутки. Поэтому в прогон встаёт не сбор,
а ПРОВЕРКА СВЕЖЕСТИ: ensure_fresh из cq_scheduler смотрит возраст
cq_v2/_summary.json и тянет дозабор только если архив старше
двадцати часов — то есть реально раз в сутки, остальные двадцать
три вызова стоят одну проверку mtime. Точно по правилу владельца
29.08: «всё ручное заводится в прогон, но запускается ОТ СВЕЖЕСТИ
имеющегося файла, а не по кругу».

Требования: cq_scheduler.py и cryptoquant_fetch.py лежат РЯДОМ с
run.py; CQ_TOKEN в окружении процесса (нет токена — лог и пропуск,
как у Coinglass с его ключом). Журнал берётся из output/leaders.json,
архив — в cq_v2 рядом с run.py (куда лёг годовой прогон).

Запуск рядом с run.py:  python3 patch_run_cq.py
"""
import ast

s = open("run.py", encoding="utf-8").read()

anchor = '''        log(f"→ Coinglass пропущен: {type(e).__name__}: {e}")

    # ── Ручные контуры — по своим отрезкам, не каждый прогон ──'''
assert s.count(anchor) == 1, "якорь Coinglass→Ручные не найден или не один"

insert = '''        log(f"→ Coinglass пропущен: {type(e).__name__}: {e}")

    # CryptoQuant v2 (30.08): суточный дозабор деривативов журнала
    # в архив cq_v2/ (funding, OI, ликвидации, свечи, тейкеры — по
    # <base>_all). Прогон ежечасный, а дневка кванта одна в сутки,
    # поэтому здесь не сбор, а проверка свежести: ensure_fresh
    # тянет только если архиву больше двадцати часов — правило
    # «от свежести файла, не по кругу». Токен ТОЛЬКО из окружения
    # CQ_TOKEN; нет токена или сбой — лог и пропуск, как почта.
    try:
        import os as _os
        if not _os.environ.get("CQ_TOKEN", "").strip():
            log("→ CryptoQuant пропущен: нет CQ_TOKEN в окружении")
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
print("врезка CryptoQuant легла; прогон сам держит архив свежим")
