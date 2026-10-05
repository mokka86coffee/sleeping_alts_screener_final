"""05.10: стоп «в твх» на BingX ставится от цены исполнения входа с комиссией, а не от цены бота (NOM 04.10). Запуск: .venv/bin/python claude/research/test_bingx_be.py"""
import sys, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import bingx_trader as bx
try:
    # шорт: бот 0.002674, исполнение 0.002665; лонг: бот 1.00, исполнение 0.99
    ST = {"open": {"SUSDT": dict(bx="S-USDT", side=-1, qty=1000.0, entry=0.002674, ps="SHORT", hedge=True, stop=0.002941, stop_ids=["1"], stop_qty=1000.0),
                   "LUSDT": dict(bx="L-USDT", side=1, qty=10.0, entry=1.0, ps="LONG", hedge=True, stop=0.9, stop_ids=["2"], stop_qty=10.0)}, "pnl": {}}
    avg = {"S-USDT": ("SHORT", "0.002665", "1000"), "L-USDT": ("LONG", "0.99", "10")}; placed = []
    def req(method, path, params=None, c=None, signed=True):
        if path.endswith("/user/positions"):
            ps, a, q = avg[params["symbol"]]; return {"code": 0, "data": [{"positionSide": ps, "availableAmt": q, "avgPrice": a}]}
        if path.endswith("/trade/order") and method == "POST":
            placed.append((params["symbol"], params["type"], params.get("stopPrice"))); return {"code": 0, "data": {"order": {"orderId": "9"}}}
        return {"code": 0, "data": {}}
    bx.request = req; bx.state = lambda: ST; bx.save = lambda s: None; bx.jlog = lambda *a, **k: None; bx.contracts = lambda: {}; bx.bot_target = lambda *a: None
    C = {"exchange_stop": True, "stop_pct": 0.1}
    # 1) бот держит обычный стоп 10 % — на бирже он от цены бота, как был; цена исполнения записана
    bx.bot_stop = lambda sym, side, entry, sp: entry * (1 - side * sp)
    bx.sync_stops(C)
    assert ST["open"]["SUSDT"]["fill"] == 0.002665 and ST["open"]["LUSDT"]["fill"] == 0.99, ST
    assert not placed, ("стоп 10 % не должен переставляться", placed)
    # 2) бот перенёс стоп в свою точку входа — на бирже безубыток от исполнения с комиссией
    bx.bot_stop = lambda sym, side, entry, sp: entry
    bx.sync_stops(C)
    d = {s: px for s, t, px in placed if t == "STOP_MARKET"}
    assert abs(d["S-USDT"] - round(0.002665 * (1 - 0.001), 6)) < 1e-12 and d["S-USDT"] < 0.002665, ("шорт", d)
    assert abs(d["L-USDT"] - round(0.99 * (1 + 0.001), 6)) < 1e-12 and d["L-USDT"] > 0.99, ("лонг", d)
    # 3) стоп бота на другом уровне (низ удержания) — берётся как есть
    placed.clear(); bx.bot_stop = lambda sym, side, entry, sp: 0.95 if side == 1 else 0.0028
    bx.sync_stops(C); d = {s: px for s, t, px in placed if t == "STOP_MARKET"}
    assert d == {"S-USDT": 0.0028, "L-USDT": 0.95}, d
    # 3б) биржа не приняла настоящий безубыток (цена уже за ним) — ставится уровень бота, позиция не остаётся без стопа
    placed.clear(); bx.bot_stop = lambda sym, side, entry, sp: entry
    ST["open"]["SUSDT"]["stop"] = 0.0028; ST["open"]["LUSDT"]["stop"] = 0.95
    def req_rej(method, path, params=None, c=None, signed=True):
        if path.endswith("/user/positions"):
            ps, a, q = avg[params["symbol"]]; return {"code": 0, "data": [{"positionSide": ps, "availableAmt": q, "avgPrice": a}]}
        if path.endswith("/trade/order") and method == "POST":
            placed.append((params["symbol"], params.get("stopPrice")))
            ok = abs(params["stopPrice"] - ST["open"][params["symbol"].replace("-", "")]["entry"]) < 1e-12      # принимается только уровень бота
            return {"code": 0, "data": {"order": {"orderId": "9"}}} if ok else {"code": 1, "msg": "Stop Loss price should be greater than the current price"}
        return {"code": 0, "data": {}}
    bx.request = req_rej; out = bx.sync_stops(C)
    assert ("S-USDT", 0.002674) in placed and ("L-USDT", 1.0) in placed and all(ST["open"][s]["stop_ok"] for s in ST["open"]) and sum("не принят" in m for m in out) == 2, (placed, out)
    # 4) деньги выхода в журнале — от цены исполнения входа
    bx.ready = lambda c: None; bx.cfg = lambda: C
    def req2(method, path, params=None, c=None, signed=True):
        if path.endswith("/user/positions"): return {"code": 0, "data": [{"positionSide": "LONG", "availableAmt": "10", "avgPrice": "0.99"}]}
        if path.endswith("/trade/order") and method == "POST": return {"code": 0, "data": {"order": {"avgPrice": "1.01"}}}
        return {"code": 0, "data": {}}
    bx.request = req2
    r = bx.close_position("LUSDT", 1.01, "проверка", c=C)
    assert r["ok"] and abs(r["pnl_usd"] - (1.01 - 0.99) * 10) < 1e-6, r
    print("ТВХ BINGX: ок — цена исполнения записывается, стоп в твх от неё с комиссией (лонг выше, шорт ниже), прочие стопы как у бота, деньги выхода от исполнения")
except Exception as e:  # noqa: BLE001
    print("СБОЙ твх BingX", type(e).__name__, e); traceback.print_exc()
