"""R75 (06.10): часы без входов перед сессией (06–08 и 12–14 UTC; до перевода на UTC — 09–11 и 15–17 по Москве) действуют только на лонги — «стыки это сливы, там не шорты нельзя брать, а лонги». Без сети."""
import sys, time
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import core_config as cc
import fast_tier as ft
ok = True
def chk(name, got, want):
    global ok
    if got != want:
        ok = False; print("СБОЙ R75:", name, "получили", got, "ждали", want)
def at(h, m=30):                                             # среда, часы UTC (с 06.10 все часы бота — UTC): вне окна без лонгов
    return datetime(2026, 10, 7, h, m, tzinfo=ft.L).timestamp()
def blocked(h, side):
    now = at(h); r = ft.ses_gate(now, int(now * 1000) - 180_000, side)
    return (not r[0]) and "за час до открытия" in str(r[1])
cc.FAST3_NO_ENTRY_HOURS = [(6, 8), (12, 14)]; cc.FAST3_NO_ENTRY_SHORTS_TOO = False
chk("лонг 06:30 UTC — стык, запрет", blocked(6, 1), True)
chk("лонг 12:30 UTC — стык, запрет", blocked(12, 1), True)
chk("шорт 06:30 UTC — стык шорту не запрет", blocked(6, -1), False)
chk("шорт 12:30 UTC — стык шорту не запрет", blocked(12, -1), False)
chk("лонг 10:30 UTC — не стык", blocked(10, 1), False)
cc.FAST3_NO_ENTRY_SHORTS_TOO = True
chk("выключатель: шорт 12:30 UTC снова под запретом", blocked(12, -1), True)
chk("в настройках: шорты в стыках берём", __import__("importlib").reload(cc).FAST3_NO_ENTRY_SHORTS_TOO, False)
chk("в настройках: порог пампа 40", cc.FAST3_PUMP_RISE, 40.0)
chk("в настройках: лондонского порога ×10 нет", cc.FAST3_LONDON_SPIKE_X, 0.0)
import re
_now = at(9); _p = ft.BASE_DIR / "output" / "london_count.json"
_keep = _p.read_text(encoding="utf-8") if _p.exists() else None
ft._oi7 = lambda sym: 1.0
_r = ft.london_gate("AAAUSDT", _now, "всплеск: бар +2% на объёме ×5.2 (100K$)")
if _keep is None:
    _p.unlink(missing_ok=True)
else:
    _p.write_text(_keep, encoding="utf-8")                       # счётчик Лондона возвращаем как был
chk("Лондон 12:30, всплеск ×5.2 — отказа по объёму нет", bool(_r and "всплеск" in _r), False)
import json as _js
def _lg(day, h, n):                                              # счётчик Лондона на этот день = n → что скажет ворота
    _t = datetime(2026, 10, day, h, 30, tzinfo=ft.L).timestamp()
    _p.write_text(_js.dumps({"day": datetime.fromtimestamp(_t, ft.L).strftime("%Y-%m-%d"), "n": n}), encoding="utf-8")
    return ft.london_gate("AAAUSDT", _t, "всплеск: бар +2% на объёме ×5.2 (100K$)")
try:
    chk("понедельник 05.10, Лондон 09:30 UTC, уже 5 входов — отказ", bool(_lg(5, 9, 5)), True)
    chk("вторник 06.10, Лондон 09:30 UTC, уже 5 входов — отказ", bool(_lg(6, 9, 5)), True)
    chk("среда 07.10, Лондон, уже 5 входов — ограничения нет", _lg(7, 9, 5), None)
    chk("суббота 10.10, Лондон, уже 9 входов — ограничения нет", _lg(10, 9, 9), None)
    chk("вторник 06.10, 15:30 UTC — не Лондон", _lg(6, 15, 5), None)
finally:
    if _keep is None:
        _p.unlink(missing_ok=True)
    else:
        _p.write_text(_keep, encoding="utf-8")
chk("в настройках: Лондон ограничен в пн и вт", cc.FAST3_LONDON_DAYS, ["пн", "вт"])
print("R75: ок" if ok else "R75: СБОЙ")
