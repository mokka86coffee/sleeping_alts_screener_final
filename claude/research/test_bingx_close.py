"""Проверка выхода на BingX (04.10, после SOON): ошибка запроса позиций не считается «позиции нет»; выход помечается и повторяется. На биржу ничего не уходит — запросы подменены."""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bingx_trader as bx
try:
    ST = {"open": {"XUSDT": dict(bx="X-USDT", side=1, qty=10.0, entry=1.0, ps="LONG", hedge=True, stop=0.9, stop_ids=["1"], stop_qty=10.0)}, "pnl": {}}
    calls = []; mode = {"pos": "fail"}
    def req(method, path, params=None, c=None, signed=True):
        calls.append((method, path.rsplit("/", 1)[-1]))
        if path.endswith("/user/positions"):
            return {"code": 109400, "msg": "timestamp is invalid", "data": {}} if mode["pos"] == "fail" else {"code": 0, "data": [{"positionSide": "LONG", "availableAmt": "10"}]}
        if path.endswith("/trade/order") and method == "POST":
            return {"code": 0, "data": {"order": {"avgPrice": "1.1"}}}
        return {"code": 0, "data": {}}
    bx.request = req; bx.state = lambda: ST; bx.save = lambda s: None; bx.ready = lambda c: None; bx.jlog = lambda *a, **k: None; bx.time.sleep = lambda x: None
    bx.cfg = lambda: {"enabled": True}; bx.sync_stops = lambda c: []
    r = bx.close_position("XUSDT", 1.1, "проверка", c={})
    assert not r["ok"] and "XUSDT" in ST["open"] and ST["open"]["XUSDT"].get("exit_pending") and ("DELETE", "allOpenOrders") not in calls, ("ошибка запроса", r, calls)
    import os; _mt = os.path.getmtime; os.path.getmtime = lambda p: 0
    try:
        mode["pos"] = "ok"; calls.clear(); out = bx.on_events([])
    finally:
        os.path.getmtime = _mt
    assert "XUSDT" not in ST["open"] and ("DELETE", "allOpenOrders") in calls and ("POST", "order") in calls and any("повтор" in m and "ok" in m for m in out), ("повтор выхода", out, calls)
    # лимит на вход, не исполнившийся за 10 минут, снимается; при ошибке запроса ордера — не трогаем
    import importlib, time as _t
    bx2 = importlib.reload(bx)
    ST2 = {"open": {"ZUSDT": dict(bx="Z-USDT", side=1, qty=5.0, entry=1.0, ps="LONG", hedge=True, stop=0.9, stop_ids=[], stop_qty=0.0, stop_ok=False, limit=True, limit_px=1.01, order_id="77", t=_t.time() - 3600)}, "pnl": {}}
    calls2 = []; ordst = {"v": {}}
    def req2(method, path, params=None, c=None, signed=True):
        calls2.append((method, path.rsplit("/", 1)[-1]))
        if path.endswith("/user/positions"): return {"code": 0, "data": []}
        if path.endswith("/trade/order") and method == "GET": return ordst["v"]
        return {"code": 0, "data": {}}
    bx2.request = req2; bx2.state = lambda: ST2; bx2.save = lambda s: None; bx2.jlog = lambda *a, **k: None; bx2.contracts = lambda: {}
    ordst["v"] = {"code": 109400, "msg": "timestamp is invalid"}
    bx2.sync_stops({"exchange_stop": True, "stop_pct": 0.1}); assert "ZUSDT" in ST2["open"] and ("DELETE", "order") not in calls2, calls2
    ordst["v"] = {"code": 0, "data": {"order": {"status": "PENDING", "executedQty": "0.00"}}}
    out2 = bx2.sync_stops({"exchange_stop": True, "stop_pct": 0.1}); assert "ZUSDT" not in ST2["open"] and ("DELETE", "order") in calls2 and any("вход отменён" in m for m in out2), (out2, calls2)
    print("ВЫХОД BINGX: ок — ошибка запроса не теряет позицию, выход повторяется; неисполненный лимит на вход снимается")
except Exception as e:  # noqa: BLE001
    print("СБОЙ выхода BingX", type(e).__name__, e); traceback.print_exc()
