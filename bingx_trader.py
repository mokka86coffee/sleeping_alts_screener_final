#!/usr/bin/env python3
"""ТОРГОВЛЯ НА BINGX (30.09, владелец: «настрой торговлю в реале на BingX через субаккаунт»; «5 ордеров со стопами на 2 доллара на позицию»).
Бот (fast_tier) зовёт `on_events(ev)` после каждого прохода: вход → рыночный ордер + стоп на бирже (STOP_MARKET) на сумму `size_usd`;
выход бота → рыночное закрытие + снятие оставшихся ордеров. ВЫКЛЮЧЕНО по умолчанию (`enabled: false`), режим по умолчанию — демо-счёт BingX (VST, виртуальные деньги).
Ключи и настройки — bingx_config.json (вне git, права ключа — только торговля, без вывода); ключи в чат/журнал/логи не пишутся.

Безопасность: файл-флаг `bingx_stop` в папке проекта — новых входов нет; дневной лимит потерь `daily_loss_limit_usd`; максимум открытых `max_open`; в режиме live без явных
size_usd / max_open / daily_loss_limit_usd (не null) торговли нет; одна позиция на монету (две книги бота на одной монете — только первая); монет, которых нет на BingX, пропускаем.
Каждый запрос и ответ (без подписи и ключа) — output/bingx_orders.jsonl. Эндпоинты — BingX Swap v2: POST /openApi/swap/v2/trade/order, /trade/leverage, /trade/marginType,
DELETE /trade/allOpenOrders, GET /openApi/swap/v1/positionSide/dual, /openApi/swap/v2/user/positions.
    .venv/bin/python bingx_trader.py --check      # без ордеров: проверка ключа, режима позиций, баланса, контрактов
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CFG = BASE_DIR / "bingx_config.json"
STOP_FLAG = BASE_DIR / "bingx_stop"
JOURNAL = BASE_DIR / "output" / "bingx_orders.jsonl"
STATE = BASE_DIR / "output" / "bingx_state.json"
HOST = {"live": "https://open-api.bingx.com", "demo": "https://open-api-vst.bingx.com"}
DEFAULTS = dict(enabled=False, mode="demo", api_key="", api_secret="", size_usd=None, leverage=3, max_open=None, daily_loss_limit_usd=None, stop_pct=0.10, exchange_stop=False,
                entry_slip_pct=0.01)   # 02.10 владелец: «ставь у лимиток вход +1 %» — лимит лонга выше цены бота на 1 %, шорта ниже; «если цена уже выше и этого — не входим»
_CT: dict = {"t": 0, "v": {}}
ALIAS = {"RAYSOLUSDT": "RAY-USDT", "METUSDT": "METEORA-USDT"}          # вручную: Binance → BingX; остальное сопоставляется по displayName


def cfg() -> dict:
    try:
        c = json.loads(CFG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {}
    return {**DEFAULTS, **c}


def jlog(kind: str, **kw) -> None:
    JOURNAL.parent.mkdir(exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 1), "kind": kind, **kw}, ensure_ascii=False) + "\n")


def request(method: str, path: str, params: dict | None = None, c: dict | None = None, signed: bool = True) -> dict:
    """подписанный запрос BingX: подпись — HMAC-SHA256 от строки параметров, ключ в заголовке X-BX-APIKEY"""
    c = c or cfg()
    p = {k: v for k, v in (params or {}).items() if v is not None}
    if signed:
        p["timestamp"] = int(time.time() * 1000)
    qs = urllib.parse.urlencode(sorted(p.items()))
    if signed:
        sig = hmac.new(c["api_secret"].encode(), qs.encode(), hashlib.sha256).hexdigest()
        qs += "&signature=" + sig
    req = urllib.request.Request(f"{HOST[c['mode']]}{path}?{qs}", method=method, headers={"X-BX-APIKEY": c["api_key"]} if signed else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            out = json.loads(r.read().decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        out = {"code": -1, "msg": f"{type(e).__name__}: {e}"}
    jlog("req", mode=c["mode"], method=method, path=path, params={k: v for k, v in p.items() if k != "timestamp"}, code=out.get("code"), msg=str(out.get("msg"))[:200],
         data=str(out.get("data"))[:300])
    return out


def contracts() -> dict:
    """контракты BingX (публично, боевой хост), кэш 1 ч: 'ARXUSDT' → {symbol 'ARX-USDT', qty precision, min qty, min USDT, price precision}"""
    if time.time() - _CT["t"] > 3600 or not _CT["v"]:
        try:
            d = json.load(urllib.request.urlopen(f"{HOST['live']}/openApi/swap/v2/quote/contracts", timeout=20))["data"]
            v = {}
            for x in d:
                if x.get("status") != 1:
                    continue
                v.setdefault(x["symbol"].replace("-", ""), x)
                v.setdefault(str(x.get("displayName") or "").replace("-", ""), x)          # 30.09: MONAD-USDT показывается как MON, NOMINA как NOM, WOTAMALAILE как 我踏马来了
            for b_sym, bx_sym in ALIAS.items():                                            # имя на Binance ≠ имя на BingX (владелец: «RAYSOL на BingX называется RAY»)
                for x in d:
                    if x["symbol"] == bx_sym and x.get("status") == 1:
                        v[b_sym] = x
            _CT.update(t=time.time(), v=v)
        except Exception as e:  # noqa: BLE001
            jlog("contracts_error", msg=str(e)[:200])
    return _CT["v"]


def qty_for(ct: dict, px: float, size_usd: float) -> float | None:
    """количество в монете на сумму size_usd (не меньше tradeMinUSDT и tradeMinQuantity), округление ВВЕРХ до точности контракта"""
    prec = int(ct.get("quantityPrecision", 0)); step = 10 ** -prec
    usd = max(size_usd, float(ct.get("tradeMinUSDT") or 0))
    q = max(usd / px, float(ct.get("tradeMinQuantity") or 0))
    # 02.10: округление ВНИЗ — VTHO отклонён BingX (101209: «максимум позиции 1000 USDT»), вверх давало 1000.0003 $;
    # вверх только если вниз получается меньше минимума контракта
    q_dn = math.floor(q / step + 1e-9) * step
    q = q_dn if q_dn * px >= float(ct.get("tradeMinUSDT") or 0) and q_dn >= float(ct.get("tradeMinQuantity") or 0) and q_dn > 0 else math.ceil(q / step - 1e-9) * step
    return round(q, prec) if q > 0 else None


def state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"open": {}, "pnl": {}}


def save(s: dict) -> None:
    STATE.parent.mkdir(exist_ok=True); tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)


def hedge_mode(c: dict) -> bool:
    r = request("GET", "/openApi/swap/v1/positionSide/dual", c=c)
    return str((r.get("data") or {}).get("dualSidePosition", "true")).lower() == "true"


def ready(c: dict) -> str | None:
    """причина, по которой торговать нельзя, или None"""
    if not c["enabled"]:
        return "торговля выключена (enabled: false)"
    if not c["api_key"] or not c["api_secret"]:
        return "нет ключей в bingx_config.json"
    if c["mode"] not in HOST:
        return f"неизвестный режим {c['mode']}"
    if c["mode"] == "live" and any(c[k] is None for k in ("size_usd", "max_open", "daily_loss_limit_usd")):
        return "live: не заданы size_usd / max_open / daily_loss_limit_usd"
    if c["size_usd"] is None:
        return "не задан size_usd"
    return None



def position_amt(bx: str, ps: str, hedge: bool, c: dict) -> float:
    """фактический объём позиции на бирже по символу и стороне (availableAmt), 0 — позиции нет"""
    pr = request("GET", "/openApi/swap/v2/user/positions", {"symbol": bx}, c)
    amt = 0.0
    for x in (pr.get("data") or []):
        if (not hedge) or str(x.get("positionSide")) == ps:
            amt += abs(float(x.get("availableAmt") or x.get("positionAmt") or 0))
    return amt


def bot_stop(sym: str, side: int, entry: float, stop_pct: float):
    """текущий стоп бота по монете: stop_px из состояния книг (безубыток, низ удержания, переворот) или −stop_pct от входа"""
    for f in ("paper_fast3.json", "paper_wake.json"):
        try:
            pos = (json.loads((BASE_DIR / "output" / f).read_text(encoding="utf-8")).get("open") or {}).get(sym)
        except (OSError, ValueError):
            pos = None
        if pos and int(pos.get("side", 0)) == side:
            if pos.get("stop_px"):
                return float(pos["stop_px"])
            return float(pos["px"]) * (1 - side * float(pos.get("stop") or stop_pct))
    return entry * (1 - side * stop_pct)


def bot_target(sym: str, side: int, entry: float):
    """текущая цель бота по монете: px*(1+side*target) из состояния книг (лонг +5 % / удержанный +10 % / шорт −10 %); None — цели нет"""
    for f in ("paper_fast3.json", "paper_wake.json"):
        try:
            pos = (json.loads((BASE_DIR / "output" / f).read_text(encoding="utf-8")).get("open") or {}).get(sym)
        except (OSError, ValueError):
            pos = None
        if pos and int(pos.get("side", 0)) == side:
            t = float(pos.get("target") or 0)
            return float(pos["px"]) * (1 + side * t) if 0 < t < 0.5 else None
    return None


def _place_tp(p: dict, want: float, qty: float, c: dict) -> dict:
    return request("POST", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "side": "SELL" if p["side"] == 1 else "BUY", "positionSide": p["ps"], "type": "TAKE_PROFIT_MARKET",
                                                            "quantity": round(qty, 6), "stopPrice": want, "workingType": "MARK_PRICE"}, c)


def sync_stops(c: dict) -> list[str]:
    """01.10 владелец «все стопы один в один»: стоп на бирже = текущий стоп бота; при смене уровня (безубыток, низ удержания) старый стоп снимается, ставится новый;
    непокрытый объём (лимит исполнился позже/частично) — досылается"""
    out = []
    if not c.get("exchange_stop"):
        return out
    s = state(); changed = False
    for sym, p in s["open"].items():
        amt = position_amt(p["bx"], p["ps"], p["hedge"], c)
        if amt <= 0:
            continue
        want = bot_stop(sym, int(p["side"]), float(p["entry"]), float(c["stop_pct"]))
        pp = int((contracts().get(sym) or {}).get("pricePrecision", 6)); want = round(want, pp)
        covered = float(p.get("stop_qty") or 0)
        moved = abs(want - float(p["stop"])) > abs(float(p["stop"])) * 5e-4
        if moved:
            for oid in p.get("stop_ids") or []:
                request("DELETE", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "orderId": oid}, c)
            covered = 0.0; p["stop_ids"] = []
        if amt - covered <= covered * 0.01 + 1e-9:
            continue
        sr = request("POST", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "side": "SELL" if p["side"] == 1 else "BUY", "positionSide": p["ps"], "type": "STOP_MARKET",
                                                              "quantity": round(amt - covered, 6), "stopPrice": want, "workingType": "MARK_PRICE"}, c)
        if sr.get("code") == 0:
            oid = str((((sr.get("data") or {}).get("order") or {}).get("orderId")) or "")
            p["stop_ids"] = (p.get("stop_ids") or []) + ([oid] if oid else []); p["stop_qty"] = amt; p["stop"] = want; p["stop_ok"] = True; changed = True
            out.append(f"BingX {sym[:-4]} стоп {want}{' (переставлен)' if moved else ''} на {round(amt - covered, 4)} ok")
        else:
            out.append(f"BingX {sym[:-4]} стоп не поставлен: {sr.get('msg')}")
    for sym, p in s["open"].items():                                     # 01.10 владелец «а где тп?»: цель бота — TAKE_PROFIT_MARKET на бирже, переставляется при смене (удержание +10 %)
        amt = position_amt(p["bx"], p["ps"], p["hedge"], c)
        if amt <= 0:
            continue
        want = bot_target(sym, int(p["side"]), float(p["entry"]))
        if want is None:
            continue
        pp = int((contracts().get(sym) or {}).get("pricePrecision", 6)); want = round(want, pp)
        covered = float(p.get("tp_qty") or 0); cur = float(p.get("tp") or 0)
        moved = cur and abs(want - cur) > abs(cur) * 5e-4
        if moved:
            for oid in p.get("tp_ids") or []:
                request("DELETE", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "orderId": oid}, c)
            covered = 0.0; p["tp_ids"] = []
        if amt - covered <= covered * 0.01 + 1e-9:
            continue
        tr = _place_tp(p, want, amt - covered, c)
        if tr.get("code") == 0:
            oid = str((((tr.get("data") or {}).get("order") or {}).get("orderId")) or "")
            p["tp_ids"] = (p.get("tp_ids") or []) + ([oid] if oid else []); p["tp_qty"] = amt; p["tp"] = want; changed = True
            out.append(f"BingX {sym[:-4]} цель {want}{' (переставлена)' if moved else ''} на {round(amt - covered, 4)} ok")
        else:
            out.append(f"BingX {sym[:-4]} цель не поставлена: {tr.get('msg')}")
    if changed:
        save(s)
    return out


def open_position(sym: str, side: int, px: float, why: str = "", c: dict | None = None, size_usd: float | None = None) -> dict:
    """вход: ЛИМИТНЫЙ ордер по цене бота + STOP_MARKET на бирже (01.10 владелец); плечо и тип маржи не трогаем. side: 1 лонг / −1 шорт. → {ok, ...}"""
    c = c or cfg(); why0 = ready(c)
    if why0:
        return {"ok": False, "why": why0}
    if STOP_FLAG.exists():
        return {"ok": False, "why": "стоит файл bingx_stop"}
    ct = contracts().get(sym)
    if not ct:
        return {"ok": False, "why": f"{sym} нет на BingX"}
    if str(ct.get("apiStateOpen")).lower() != "true":                     # 145 контрактов BingX закрыты для торговли по API (apiStateOpen: false — например ARX)
        return {"ok": False, "why": f"{ct['symbol']}: торговля по API закрыта (apiStateOpen=false)"}
    s = state()
    if sym in s["open"]:
        return {"ok": False, "why": "позиция по монете уже открыта"}
    if c["max_open"] is not None and len(s["open"]) >= int(c["max_open"]):
        return {"ok": False, "why": f"открыто {len(s['open'])} из {c['max_open']}"}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if c["daily_loss_limit_usd"] is not None and s["pnl"].get(today, 0.0) <= -abs(float(c["daily_loss_limit_usd"])):
        return {"ok": False, "why": f"дневной лимит потерь достигнут ({s['pnl'].get(today, 0):+.2f} $)"}
    try:                                                                 # защита от неверного сопоставления имён и множителей (1000X): цена BingX против сигнала не дальше 5%
        bp = float(((json.load(urllib.request.urlopen(f"{HOST['live']}/openApi/swap/v2/quote/price?symbol={ct['symbol']}", timeout=10)).get("data") or {}).get("price")) or 0)
    except Exception:  # noqa: BLE001
        bp = 0.0
    if bp and px and abs(bp / px - 1) > 0.05:
        return {"ok": False, "why": f"цена {ct['symbol']} на BingX {bp} не совпадает с сигналом {px} (вероятно другой актив/множитель)"}
    q = qty_for(ct, px, float(size_usd or c["size_usd"]))
    if not q:
        return {"ok": False, "why": "количество не посчиталось"}
    bx = ct["symbol"]; hedge = hedge_mode(c); ps = ("LONG" if side == 1 else "SHORT") if hedge else "BOTH"
    # 01.10 владелец: «плечи не регулируешь, ничего кроме позиций, стопов и сигналов открытия/закрытия; покупка лимитным ордером по цене бота, стоп-лосс, продавать можно по рынку»
    # 01.10 владелец: «не меняешь ни плечи, ни маржу — ничего кроме открытия/закрытия позиций, стопов, рыночных закрытий»: плечо и тип маржи берутся с аккаунта как есть
    pp = int(ct.get("pricePrecision", 6)); slip = float(c.get("entry_slip_pct") or 0)
    lim = round(float(px) * (1 + side * slip), pp)                       # 02.10 владелец: лимит на вход = цена бота +1 % (лонг) / −1 % (шорт); «твх и стоп-лосс те же» — стоп и тейк от цены бота
    if bp and slip and ((side == 1 and bp > lim) or (side == -1 and bp < lim)):   # 02.10 владелец: «если цена уже выше и этого — не входим в сделку»
        return {"ok": False, "why": f"цена BingX {bp} уже дальше лимита {lim} (бот {px} {'+' if side == 1 else '−'}{slip*100:g} %) — не входим"}
    body = {"symbol": bx, "side": "BUY" if side == 1 else "SELL", "positionSide": ps, "type": "LIMIT", "price": lim, "quantity": q, "timeInForce": "GTC"}
    r = request("POST", "/openApi/swap/v2/trade/order", body, c)
    if r.get("code") != 0:
        return {"ok": False, "why": f"лимитный ордер не принят: {r.get('code')} {r.get('msg')}"}
    o = (r.get("data") or {}).get("order") or r.get("data") or {}
    stop = round(float(px) * (1 - side * float(c["stop_pct"])), pp)      # 02.10: от цены входа бота, не от лимита
    time.sleep(1.5)
    q_pos = position_amt(bx, ps, hedge, c)                               # 01.10: лимит мог исполниться частично/позже — стоп ставим на фактический объём, остальное досылает sync_stops
    if c.get("exchange_stop") and q_pos <= 0:
        sr = {"code": -1, "msg": "лимит ещё не исполнен — стоп поставит sync_stops после исполнения"}
    elif c.get("exchange_stop"):                                         # 01.10 владелец «не надо пока никаких отдельных правил на бирже»: стоп на бирже выключен (exchange_stop: false) — все выходы, включая стопы, даёт бот своим сигналом закрытия
        sr = request("POST", "/openApi/swap/v2/trade/order", {"symbol": bx, "side": "SELL" if side == 1 else "BUY", "positionSide": ps, "type": "STOP_MARKET",
                                                              "quantity": q_pos, "stopPrice": stop, "workingType": "MARK_PRICE"}, c)
    else:
        sr = {"code": 0, "msg": "стоп на бирже выключен"}
    sid = str((((sr.get("data") or {}).get("order") or {}).get("orderId")) or "") if sr.get("code") == 0 and c.get("exchange_stop") else ""
    s["open"][sym] = dict(bx=bx, side=side, qty=q, entry=round(float(px), pp), limit_px=lim, stop=stop, t=time.time(), ps=ps, hedge=hedge, mode=c["mode"], why=why[:120], stop_ok=(sr.get("code") == 0),
                          order_id=str(o.get("orderId") or ""), limit=True, stop_qty=(q_pos if sr.get("code") == 0 else 0.0), stop_ids=([sid] if sid else []))
    save(s)
    return {"ok": True, "qty": q, "entry": round(float(px), pp), "limit_px": lim, "stop": stop, "order_id": str(o.get("orderId") or ""), "stop_ok": sr.get("code") == 0, "stop_msg": sr.get("msg") if sr.get("code") != 0 else ""}


def order_info(bx: str, oid: str, c: dict) -> dict:
    """ордер по orderId: {status, avgPrice, executedQty, ...} или {} (02.10: чтобы отличать «лимит не исполнился» от «биржа закрыла стопом»)"""
    r = request("GET", "/openApi/swap/v2/trade/order", {"symbol": bx, "orderId": str(oid)}, c)
    return ((r.get("data") or {}).get("order") or r.get("data") or {}) if r.get("code") == 0 else {}


def close_position(sym: str, exit_px: float | None = None, why: str = "", c: dict | None = None) -> dict:
    c = c or cfg(); s = state(); p = s["open"].get(sym)
    if not p:
        return {"ok": False, "why": "позиции нет в состоянии"}
    if ready(c) and ready(c) != "торговля выключена (enabled: false)":
        return {"ok": False, "why": ready(c)}
    request("DELETE", "/openApi/swap/v2/trade/allOpenOrders", {"symbol": p["bx"]}, c)                                   # снять лимит (если не исполнился) и стоп
    pr = request("GET", "/openApi/swap/v2/user/positions", {"symbol": p["bx"]}, c)
    amt = 0.0
    for x in (pr.get("data") or []):
        if (not p["hedge"]) or str(x.get("positionSide")) == p["ps"]:
            amt += abs(float(x.get("availableAmt") or x.get("positionAmt") or 0))
    if amt <= 0:                                                       # позиции нет: либо лимит не исполнился, либо биржа уже закрыла её стопом/тейком
        # 02.10 владелец по SAND («всмысле не было в демо? было»): стоп на бирже сработал в 10:04, бот вышел в 10:11 — журнал писал «позиции не было», −135 $ терялись
        fill = None
        for oid, tag in [(o, "стопом") for o in (p.get("stop_ids") or [])] + [(o, "тейком") for o in (p.get("tp_ids") or [])]:
            oi = order_info(p["bx"], oid, c)
            if oi and str(oi.get("status", "")).upper() == "FILLED" and float(oi.get("avgPrice") or 0) > 0:
                fill = (float(oi["avgPrice"]), tag, float(oi.get("executedQty") or p["qty"])); break
        if fill:
            out, tag, qf = fill
            pnl = (out / p["entry"] - 1) * p["side"] * p["entry"] * qf
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d"); s["pnl"][today] = round(s["pnl"].get(today, 0.0) + pnl, 4)
            del s["open"][sym]; save(s)
            return {"ok": True, "exit": out, "pnl_usd": round(pnl, 4), "why": f"закрыта на бирже {tag} по {out} до сигнала бота"}
        del s["open"][sym]; save(s)
        return {"ok": True, "exit": None, "pnl_usd": 0.0, "why": "лимит не исполнился — ордера сняты, позиции не было"}
    body = {"symbol": p["bx"], "side": "SELL" if p["side"] == 1 else "BUY", "positionSide": p["ps"], "type": "MARKET", "quantity": amt}
    if not p["hedge"]:
        body["reduceOnly"] = "true"
    r = request("POST", "/openApi/swap/v2/trade/order", body, c)
    if r.get("code") != 0 and "not exist" not in str(r.get("msg", "")).lower():
        return {"ok": False, "why": f"закрытие не принято: {r.get('code')} {r.get('msg')}"}
    o = (r.get("data") or {}).get("order") or r.get("data") or {}
    out = float(o.get("avgPrice") or 0) or (exit_px or p["entry"])
    pnl = (out / p["entry"] - 1) * p["side"] * p["entry"] * p["qty"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d"); s["pnl"][today] = round(s["pnl"].get(today, 0.0) + pnl, 4)
    del s["open"][sym]; save(s)
    return {"ok": True, "exit": out, "pnl_usd": round(pnl, 4)}


def on_events(ev: list[dict]) -> list[str]:
    """вызывается ботом после прохода: события entry / exit_* → ордера на BingX; любые сбои — только в журнал, бота не роняют"""
    msgs = []
    try:
        c = cfg()
        if not c["enabled"]:
            return msgs
        msgs += sync_stops(c)                                            # 01.10: дослать стопы на исполнившиеся лимиты
        for e in ev:
            k = str(e.get("kind", ""))
            if k == "entry":
                r = open_position(e["sym"], int(e["side"]), float(e["px"]), why=e.get("rule") or "", c=c)
                jlog("entry", sym=e["sym"], book=e.get("book"), side=e["side"], **r)
                msgs.append(f"BingX {e['sym'][:-4]} вход: {'ok' if r['ok'] else r['why']}")
            elif k.startswith("exit"):
                sp = state()["open"].get(e["sym"])
                if sp and sp["side"] == int(e["side"]):
                    r = close_position(e["sym"], float(e.get("px_out") or 0) or None, why=str(e.get("why_exit")), c=c)
                    jlog("exit", sym=e["sym"], book=e.get("book"), **r)
                    msgs.append(f"BingX {e['sym'][:-4]} выход: {'ok' if r['ok'] else r['why']}")
    except Exception as ex:  # noqa: BLE001
        jlog("error", msg=f"{type(ex).__name__}: {ex}"[:300])
    return msgs


def check() -> int:
    c = cfg()
    print("режим:", c["mode"], "| включено:", c["enabled"], "| ключи:", "есть" if c["api_key"] and c["api_secret"] else "НЕТ", "| size_usd:", c["size_usd"], "| стоп:", c["stop_pct"])
    ct = contracts(); print("контрактов BingX:", len(ct))
    if not (c["api_key"] and c["api_secret"]):
        print("вставь ключи в bingx_config.json (ключ создаётся в субаккаунте, права — только торговля)"); return 1
    r = request("GET", "/openApi/swap/v3/user/balance", c=c); print("баланс:", str(r.get("data"))[:300] if r.get("code") == 0 else f"ошибка {r.get('code')} {r.get('msg')}")
    print("режим позиций (hedge):", hedge_mode(c))
    return 0


if __name__ == "__main__":
    raise SystemExit(check() if "--check" in sys.argv else 0)
