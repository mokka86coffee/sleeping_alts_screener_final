#!/usr/bin/env python3
"""R77 (06.10): запрет повторного входа не ставится после сделки, закрытой за три прогона (9 мин); после более долгой — 2 ч. Заморозка зеркала после правки снята."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
import core_config as cc
now = time.time(); bad = []
def chk(name, cond):
    if not cond: bad.append(name)
for mins, ban in ((3.2, False), (6.4, False), (9.7, False), (12.3, True), (45, True)):
    st = {"open": {}, "last_exit": {}}
    ft._exit_mark(st, "XUSDT", now, now - mins * 60)
    chk(f"сделка {mins} мин → запрет {ban}", ft._reentry_banned(st, "XUSDT", now + 60) == ban)
st = {"last_exit": {}}; ft._exit_mark(st, "XUSDT", now, now - 3600)
chk("запрет держится 2 ч", ft._reentry_banned(st, "XUSDT", now + 119 * 60) and not ft._reentry_banned(st, "XUSDT", now + 121 * 60))
st = {"last_exit": {"XUSDT": now - 600}}; ft._exit_mark(st, "XUSDT", now, now - 200)
chk("быстрый выход не снимает прежний запрет", ft._reentry_banned(st, "XUSDT", now))
st = {}; ft._exit_mark(st, "XUSDT", now, None)
chk("время входа неизвестно → запрет", ft._reentry_banned(st, "XUSDT", now + 1))
chk("настройки", cc.FAST3_REENTRY_FAST_MIN == 9 and cc.FAST3_REENTRY_BAN_MIN == 120 and cc.BINGX_FREEZE_AFTER_EDIT_MIN == 0)
print("R77: " + ("ок — быстрый выход (до трёх прогонов) запрета не ставит, долгий — 2 ч, прежний запрет не снимается" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
