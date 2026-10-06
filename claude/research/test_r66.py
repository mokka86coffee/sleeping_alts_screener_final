"""Проверка R66 (шорт сканера: цена стоит 6 часов → закрытие) и накопления свечей позиции (_k3_since); на биржу и в книги ничего не пишет."""
import sys, time, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
try:
    now = 2_000_000_000.0; B = 180_000; t0 = int(now * 1000) - 2000 * B          # позиция возрастом 100 часов: 2000 свечей
    allb = [[t0 + i * B, 1, 1.01, 0.99, 1, 0, 0, 0] for i in range(2000)]
    calls = []
    def gj(url, params=None, **kw):
        calls.append(params["startTime"]); return [b for b in allb if b[0] >= params["startTime"]][:params["limit"]]
    ft.get_json = gj; ft._K3C.clear()
    k = ft._k3_since("XUSDT", t0, int(now * 1000))
    assert len(k) == 2000 and len(calls) == 2 and k[-1][0] == allb[-1][0], (len(k), len(calls))          # раньше вернулась бы только первая тысяча
    allb.append([t0 + 2000 * B, 1, 1.01, 0.99, 1, 0, 0, 0]); calls.clear()
    k = ft._k3_since("XUSDT", t0, int(now * 1000) + B)
    assert len(k) == 2001 and len(calls) == 1 and calls[0] == t0 + 2000 * B, (len(k), calls)             # досылается только новая свеча
    # R66: шорт старше 6 ч, минимум не обновлялся 6 ч → минус закрыть, плюс — стоп в твх
    pos = dict(side=-1, at=now - 8 * 3600, px=1.0)
    n = 160                                                                                             # 8 часов свечей
    kb = lambda low_at: [[int((now - 8 * 3600) * 1000) + i * B, 1, 1.0, 0.95 if i == low_at else 0.97, 0.98] for i in range(n)]
    r = ft._stall_exit(pos, kb(10), now, 1.02); assert r and r[0] == "close" and "R66" in r[1], r         # цена выше входа → закрытие
    r = ft._stall_exit(pos, kb(10), now, 0.98); assert r and r[0] == "be", r                              # в плюсе → стоп в точку входа
    assert ft._stall_exit(dict(pos, stop_px=1.0), kb(10), now, 0.98) is None                            # стоп уже в точке входа → ничего
    r = ft._stall_exit(pos, kb(150), now, 1.02); assert r and r[0] == "close", r                         # минимум был полчаса назад, но шорту 8 часов и он в минусе → закрытие
    assert ft._stall_exit(dict(pos, at=now - 3 * 3600), kb(10)[:60], now, 1.02) is None                 # позиции меньше 6 часов → держим
    assert ft._stall_exit(dict(pos, pump_end=True), kb(10), now, 1.02) is None and ft._stall_exit(dict(pos, side=1), kb(10), now, 1.02) is None
    # R68: шорт закрыт на шестом часу в минусе → лонг от цены закрытия, стоп на минимуме часов шорта
    ft._slide = lambda s: (False, False, 0.0); ft._pump_ban = lambda s, n: None
    np_ = ft._stall_flip(dict(pos, sym="XUSDT", rule="R52 …"), kb(10), now, 1.02)
    assert np_ and np_["side"] == 1 and np_["px"] == 1.02 and np_["stop_px"] == 0.95 and np_["target"] == ft.FAST3_LONG_HOLD_TP and np_["held"] and np_["flip"] and np_["rule"].startswith("R68"), np_
    assert ft.long_walk(1.02, dict(np_), [[0, 1.02, 1.05, 1.0, 1.04]]) == (None, None) and ft.long_walk(1.02, dict(np_), [[0, 1.02, 1.03, 0.94, 0.95]])[1] == "стоп на низу удержания"
    ft._slide = lambda s: (True, False, -9.0)
    assert ft._stall_flip(dict(pos, sym="XUSDT"), kb(10), now, 1.02) is None                              # монета сползает → лонга нет
    # R69: окно без лонгов — с воскресенья 19:00 до вторника 14:00 UTC (06.10: все часы бота переведены на UTC; до этого 22:00 → 17:00 по UTC+3 — те же моменты)
    from datetime import datetime as _dt
    from datetime import timezone as _tz
    assert ft.L == _tz.utc                                                                                 # часы бота — UTC
    T = lambda d, hh, mm=0: _dt(2026, 10, d, hh, mm, tzinfo=_tz.utc).timestamp()
    assert _dt.fromtimestamp(T(4, 3), ft.L).weekday() == 6
    assert ft._long_window_closed(T(4, 18, 59)) is None and ft._long_window_closed(T(4, 19)) and ft._long_window_closed(T(5, 12)) and ft._long_window_closed(T(6, 13, 59))
    assert ft._long_window_closed(T(6, 14)) is None and ft._long_window_closed(T(3, 20)) is None and ft._long_window_closed(T(7, 0)) is None
    assert ft._sunday_close(dict(side=1, at=T(4, 9)), T(4, 19, 5)) and ft._sunday_close(dict(side=-1, at=T(3, 9)), T(5, 12)) is None and ft._sunday_close(dict(side=1, at=T(3, 9)), T(4, 12)) is None
    _real = ft._long_window_closed; ft._long_window_closed = lambda n: "окно"
    ft._slide = lambda s: (False, False, 0.0)
    assert ft._stall_flip(dict(pos, sym="XUSDT"), kb(10), now, 1.02) is None                              # в окне переворота в лонг нет
    ft._long_window_closed = _real
    print("R66: ок — свечи позиции копятся дальше 50 часов; шорт старше 6 ч: минус закрывается и переворачивается в лонг (R68), плюс — стоп в твх")
except Exception as ex:  # noqa: BLE001
    print("СБОЙ R66", type(ex).__name__, ex); traceback.print_exc()
