#!/usr/bin/env python3
"""ПРОВЕРКА: бот сам снимает отметку «биткоин падает» (fast_tier.btc_fall_step, 14.10 22:00 UTC владелец: «если он поднялся на 2% и цена держится
более 2ч, если цена +3% и больше — не ждём, сразу ставим падение кончилось», «и дату сквиза»). Работает на копиях во временной папке.
    .venv/bin/python claude/research/test_btc_fall.py"""
import json, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft

errs = []
def chk(c, m):
    if not c:
        errs.append(m)

D = Path(tempfile.mkdtemp())
CFG = 'MANUAL_BY_USER_BTC_SQUEEZE_AT = "2026-10-14 12:30"   # старое\nX = 1\nMANUAL_BY_USER_BTC_FALLING = True   # стоит\n'
def setup(falling=True):
    (D / "c.py").write_text(CFG, encoding="utf-8"); (D / "f.json").write_text("{}", encoding="utf-8")
    (D / "k.json").write_text(json.dumps({"falling": falling, "squeeze": {"at": "2026-10-14T12:30:00Z"}}), encoding="utf-8")
def run(now, bars):
    return ft.btc_fall_step(now, clock_path=D / "k.json", cfg_path=D / "c.py", fall_path=D / "f.json", bars=bars)
T0 = 1_792_000_000 // 180 * 180
def mk(closes, lows=None):
    return [(T0 + i * 180, c, (lows or closes)[i]) for i, c in enumerate(closes)]

setup()                                                             # +2.5 % от минимума, держится 1 ч — рано
b = mk([100] * 5 + [98] + [100.5] * 20); r = run(T0 + 26 * 180, b)
chk(r == [], f"держится 1 ч — ещё рано: {r}")
chk("True" in (D / "c.py").read_text(encoding="utf-8"), "файл настроек не должен меняться")
setup()                                                             # +2.5 % держится больше 2 ч — конец
b = mk([100] * 5 + [98] + [100.5] * 45); r = run(T0 + 51 * 180, b)
t = (D / "c.py").read_text(encoding="utf-8")
chk(r and "кончилось" in r[0], f"держится 2,25 ч — падение кончилось: {r}")
chk("MANUAL_BY_USER_BTC_FALLING = False" in t, "отметка не снята")
chk('MANUAL_BY_USER_BTC_SQUEEZE_AT = "2026-10-' in t and '"2026-10-14 12:30"' not in t, f"дата сквиза не записана: {t}")
k = json.loads((D / "k.json").read_text(encoding="utf-8")); chk(k["falling"] is False and k["squeeze"]["at"] != "2026-10-14T12:30:00Z", f"часы не обновлены: {k}")
chk("X = 1" in t, "остальной файл должен остаться")
setup()                                                             # провал ниже +2 % внутри двух часов — отсчёт заново
b = mk([100] * 5 + [98] + [100.5] * 20 + [99.5] + [100.5] * 20); r = run(T0 + 47 * 180, b)
chk(r == [], f"закрытие ниже +2 % обнуляет отсчёт: {r}")
setup()                                                             # +3 % — сразу
b = mk([100] * 5 + [98] + [101] * 2); r = run(T0 + 8 * 180, b)
chk(r and "не ждём" in r[0], f"+3 % — сразу: {r}")
setup(False)                                                        # отметки нет — ничего не делает
b = mk([100] * 5 + [98] + [101] * 2); r = run(T0 + 8 * 180, b)
chk(r == [] and "True" in (D / "c.py").read_text(encoding="utf-8"), f"без отметки ничего не меняет: {r}")
print("конец падения BTC: ок" if not errs else "СБОЙ конец падения BTC: " + "; ".join(errs))
sys.exit(1 if errs else 0)
