#!/usr/bin/env python3
"""Врезка экрана-потока в run.py (утро 30.08).

После пересчёта репутаций прогон собирает flow.html — экран-поток
в утверждённой коже — рядом с остальными документами, чтобы кнопка
AI в зале всегда имела живую цель. Монета выбирается сама: самая
громкая касса дня из output/reputation.json (наибольший |перевес
покупок-продаж|); если файла репутаций нет — bless. Сборка — вызов
make_flow.py тем же интерпретатором; сбой — лог и пропуск, зал
живёт, кнопка ведёт на прошлую версию.

Рядом с run.py должны лежать make_flow.py и архив cq_v2.
Запуск рядом с run.py:  python3 patch_run_flow.py
"""
import ast

s = open("run.py", encoding="utf-8").read()

if "Экран-поток" in s:
    print("врезка потока уже стоит — делать нечего")
    raise SystemExit(0)

anchor = '''    except Exception as e:
        log(f"→ Репутации пропущены: {type(e).__name__}: {e}")'''
assert s.count(anchor) == 1, "якорь блока репутаций не найден"

s = s.replace(anchor, anchor + '''

    # Экран-поток (30.08): flow.html собирается каждым прогоном —
    # цель кнопки AI в зале. Монета — самая громкая касса дня из
    # репутаций (наибольший перевес в стакане по модулю); нет
    # файла — bless. Сбой — лог и пропуск, кнопка ведёт на
    # прошлую сборку.
    try:
        import json as _json3
        import subprocess as _sp
        import sys as _sys
        from pathlib import Path as _P3
        _base3 = _P3(__file__).resolve().parent
        _coin = "bless"
        try:
            _rep3 = _json3.loads((_P3("output") / "reputation.json")
                                 .read_text(encoding="utf-8"))
            _loud = max((v for k, v in _rep3.items()
                         if k != "_meta" and isinstance(v, dict)
                         and (v.get("today") or {}).get("delta_usd")),
                        key=lambda v: abs(v["today"]["delta_usd"]),
                        default=None)
            if _loud:
                _coin = next(k for k, v in _rep3.items()
                             if v is _loud)[:-4].lower()
        except Exception:
            pass
        _r3 = _sp.run([_sys.executable, str(_base3 / "make_flow.py"),
                       "--coin", _coin,
                       "--archive", str(_base3 / "cq_v2"),
                       "--out", str(_base3 / "flow.html")],
                      capture_output=True, text=True, timeout=120)
        if _r3.returncode == 0:
            log(f"→ Экран-поток: flow.html собран ({_coin.upper()})")
        else:
            _tl = (_r3.stderr or _r3.stdout).strip().splitlines()[-1:]
            log(f"→ Экран-поток пропущен: {_tl[0] if _tl else 'сбой'}")
    except Exception as e:
        log(f"→ Экран-поток пропущен: {type(e).__name__}: {e}")''')

open("run.py", "w", encoding="utf-8").write(s)
ast.parse(s)
print("поток собирается каждым прогоном, монета — громкая касса дня")
