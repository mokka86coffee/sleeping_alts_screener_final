#!/usr/bin/env python3
"""R79 (06.10): размер входа по уверенности — клетка → сумма; проверочный вход вне клеток; события входа и выхода получают долю; зеркало берёт сумму из события."""
import sys, time, inspect
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft, bingx_trader as bx, core_config as cc
bad = []
def chk(name, cond):
    if not cond: bad.append(name)
now = time.time(); real = ft._session_regime
_cfg_real = (cc.FAST3_PROBE_USD, cc.FAST3_SIZE_TIERS)
# 08.10 владелец: «все сделки поставь по 900$» — в настройках все ступени и проверочный вход 900 $; сам механизм клеток проверяем на прежних суммах
for _side in (1, -1):
    for _r in (dict(), dict(dp=0.2), dict(dp=-0.9), dict(rv=1.2), dict(h=0.5)):
        ft._session_regime = (lambda rr: (lambda _n: dict(dict(ses="Лондон", t0=now - 7200, t_last=now, n=200, h=2.0, dp=0.8, rv=0.7), **rr)))(_r)
        chk(f"настройки 08.10: любой вход 900 $ (сторона {_side}, режим {_r})", ft._conf_usd(_side, now)[0] == 900.0)
ft._session_regime = lambda _n: {}; chk("настройки 08.10: пульса нет — тоже 900 $", ft._conf_usd(-1, now)[0] == 900.0)
ft._session_regime = real
cc.FAST3_PROBE_USD, cc.FAST3_SIZE_TIERS = 20.0, [(80.0, 900.0), (65.0, 500.0), (50.0, 100.0)]
def reg(**k): return lambda _n: dict(dict(ses="Лондон", t0=now - 7200, t_last=now, n=200, h=2.0, dp=0.8, rv=0.7), **k)
try:
    ft._session_regime = reg();                    chk("шорт, без объёма, рынок +0,8 % → 500", ft._conf_usd(-1, now)[0] == 500.0)
    ft._session_regime = reg(dp=0.2);              chk("шорт, рынок +0,2 % → 100", ft._conf_usd(-1, now)[0] == 100.0)
    ft._session_regime = reg(dp=-0.3);             chk("шорт, рынок −0,3 % → 100", ft._conf_usd(-1, now)[0] == 100.0)
    ft._session_regime = reg(dp=-0.9);             chk("шорт, рынок −0,9 % → проверка 20", ft._conf_usd(-1, now)[0] == 20.0)
    ft._session_regime = reg();                    chk("лонг в той же клетке → проверка 20", ft._conf_usd(1, now)[0] == 20.0)
    ft._session_regime = reg(rv=1.2);              chk("сессия с объёмом → проверка 20", ft._conf_usd(-1, now)[0] == 20.0)
    ft._session_regime = reg(h=0.5);               chk("первый час сессии → проверка 20", ft._conf_usd(-1, now)[0] == 20.0)
    ft._session_regime = lambda _n: {};            chk("пульса нет → проверка 20", ft._conf_usd(-1, now)[0] == 20.0)
    ft._session_regime = reg()
    st = {"open": {"AUSDT": {"side": -1}, "BUSDT": {"side": 1}}}
    ev = [dict(kind="entry", sym="AUSDT", side=-1, book=ft.BOOK, usd_in=500.0), dict(kind="entry", sym="BUSDT", side=1, book=ft.BOOK, usd_in=500.0)]
    ft._size_events(st, ev, now, ft.BOOK)
    chk("вход шорта: 500 $", ev[0]["usd_in"] == 500.0 and st["open"]["AUSDT"]["k"] == 1.0 and ev[0]["reg"]["win"] == 77.0)
    chk("вход лонга: 20 $", ev[1]["usd_in"] == 20.0 and st["open"]["BUSDT"]["k"] == 0.04)
    ev2 = [dict(kind="exit_long", sym="BUSDT", side=1, book=ft.BOOK, usd=-50.0), dict(kind="exit_short", sym="CUSDT", side=-1, book=ft.BOOK, usd=30.0),
           dict(kind="exit_short", sym="DUSDT", side=-1, book=ft.WAKE_BOOK, usd=-10.0, k_pos=0.2)]
    ft._size_events(st, ev2, now, ft.BOOK)
    chk("выход проверочного лонга: −50 → −2 $", ev2[0]["usd"] == -2.0)
    chk("выход старой сделки без доли — полной суммой", ev2[1]["usd"] == 30.0)
    chk("выход позиции другой книги — по её доле", ev2[2]["usd"] == -2.0)
    keep = cc.FAST3_SIZE_BY_CONF; cc.FAST3_SIZE_BY_CONF = False
    chk("выключатель: всё по полной сумме", ft._conf_usd(1, now)[0] == float(ft.FAST3_SIZE)); cc.FAST3_SIZE_BY_CONF = keep
finally:
    ft._session_regime = real
    cc.FAST3_PROBE_USD, cc.FAST3_SIZE_TIERS = _cfg_real
src = inspect.getsource(bx.on_events)
chk("зеркало берёт сумму из события (вход и добор)", src.count('size_usd=e.get("usd_in")') == 2)
for fn in (ft.step, ft.wake_step):
    t = inspect.getsource(fn); t = t[t.rindex("if write:"):]
    chk(f"{fn.__name__}: размер ставится до ордеров", 0 <= t.find("_size_events(") < t.find("_bingx(ev)"))
print("R79: " + ("ок — в настройках с 08.10 любой вход 900 $; механизм клеток (500 / 100 / 20 $ на прежних суммах), события и зеркало получают сумму" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
