#!/usr/bin/env python3
"""Врезка репутаций в run.py (30.08, ночь, шаг два-с-половиной).

После квантового блока прогон пересчитывает output/reputation.json
из архива cq_v2 — каждый прогон, потому что стоит секунды (чтение
66 локальных файлов, ноль сети), а свежий отпечаток покупателя
в карточках важнее экономии на спичках. Сбой — лог и пропуск.

Рядом с run.py должен лежать reputation_cq.py.
Запуск рядом с run.py:  python3 patch_run_rep.py
"""
import ast

s = open("run.py", encoding="utf-8").read()

if "Репутации усилий" in s:
    print("врезка репутаций уже стоит — делать нечего")
    raise SystemExit(0)

anchor = '''    except Exception as e:
        log(f"→ CryptoQuant пропущен: {type(e).__name__}: {e}")'''
assert s.count(anchor) == 1, "якорь квантового блока не найден"

s = s.replace(anchor, anchor + '''

    # Репутации усилий (Р-2, 30.08): пересчёт output/reputation.json
    # из архива cq_v2 — отпечаток покупателя и счёт раздач в карточки
    # зала. Локальное чтение, секунды, поэтому каждый прогон; свежее
    # квантовой дневки данные всё равно не станут. Сбой — лог и
    # пропуск, зал живёт без строк, не падает.
    try:
        from reputation_cq import build as _rep_build
        from pathlib import Path as _P2
        import json as _json2
        _arch = _P2(__file__).resolve().parent / "cq_v2"
        if _arch.exists():
            _rep = _rep_build(_arch)
            _dst = _P2("output") / "reputation.json"
            _dst.parent.mkdir(exist_ok=True)
            _tmp = _dst.with_suffix(".tmp")
            _tmp.write_text(_json2.dumps(_rep, ensure_ascii=False))
            _tmp.replace(_dst)
            _n = sum(1 for k in _rep if k != "_meta")
            log(f"→ Репутации: монет {_n} → output/reputation.json")
        else:
            log("→ Репутации пропущены: нет архива cq_v2")
    except Exception as e:
        log(f"→ Репутации пропущены: {type(e).__name__}: {e}")''')

open("run.py", "w", encoding="utf-8").write(s)
ast.parse(s)
print("репутации считаются каждым прогоном")
