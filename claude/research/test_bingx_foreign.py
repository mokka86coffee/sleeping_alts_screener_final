"""08.10: зеркало BingX не входит в монету, где на бирже уже есть позиция не бота (ручная сделка владельца на том же счёте), и ничего по ней не шлёт.
Запуск: .venv/bin/python claude/research/test_bingx_foreign.py"""
import sys, io, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bingx_trader as bx
bad = []
ST = {"open": {}, "pnl": {}}; calls = []; pos = {"v": []}
def req(method, path, params=None, c=None, signed=True):
    calls.append((method, path.rsplit("/", 1)[-1]))
    if path.endswith("/user/positions"): return {"code": 0, "data": pos["v"]}
    if path.endswith("/trade/order") and method == "POST": return {"code": 0, "data": {"order": {"orderId": "1"}}}
    return {"code": 0, "data": {}}
bx.request = req; bx.state = lambda: ST; bx.save = lambda s: None; bx.ready = lambda c: None; bx.jlog = lambda *a, **k: None; bx.time.sleep = lambda x: None
bx.contracts = lambda: {"SANDUSDT": {"symbol": "SAND-USDT", "pricePrecision": 5}}; bx.qty_for = lambda ct, px, usd: 100.0; bx.hedge_mode = lambda c: False
bx.urllib.request.urlopen = lambda *a, **k: io.BytesIO(json.dumps({"data": {"price": "0.0735"}}).encode())
class _NoFlag:
    def exists(self): return False
bx.STOP_FLAG = _NoFlag()
C = {"enabled": True, "mode": "demo", "max_open": None, "daily_loss_limit_usd": None, "size_usd": 500, "stop_pct": 0.10, "exchange_stop": False, "entry_slip_pct": 0.01}
# 1) на бирже уже есть шорт не бота — ордер не шлём, позицию и её ордера не трогаем
pos["v"] = [{"positionSide": "BOTH", "availableAmt": "128000", "avgPrice": "0.07818"}]
r = bx.open_position("SANDUSDT", -1, 0.0735, "проверка", c=C)
if r.get("ok") or "не бота" not in str(r.get("why")): bad.append(f"чужая позиция: вход не отклонён ({r})")
if ("POST", "order") in calls or ("DELETE", "allOpenOrders") in calls: bad.append(f"чужая позиция: зеркало послало ордера {calls}")
if "SANDUSDT" in ST["open"]: bad.append("чужая позиция записана в состояние зеркала")
# 2) позиции на бирже нет — вход идёт как раньше
calls.clear(); pos["v"] = []
r = bx.open_position("SANDUSDT", -1, 0.0735, "проверка", c=C)
if ("POST", "order") not in calls: bad.append(f"пустая биржа: ордер на вход не ушёл ({r}, {calls})")
print("ЗЕРКАЛО И ЧУЖАЯ ПОЗИЦИЯ: " + ("ок — в монету с ручной позицией на бирже зеркало не входит и ничего по ней не шлёт; без неё вход идёт как раньше" if not bad else "СБОЙ: " + "; ".join(bad)))
sys.exit(1 if bad else 0)
