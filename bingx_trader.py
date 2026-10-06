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
import os
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


_TOFF = {"t": 0.0, "ms": 0.0}


def _time_off(c: dict) -> float:
    """разница «время сервера BingX − часы компьютера», мс; обновляется раз в 10 минут, при сбое остаётся прежней"""
    if time.time() - _TOFF["t"] > 600:
        try:
            t0 = time.time()
            with urllib.request.urlopen(f"{HOST[c['mode']]}/openApi/swap/v2/server/time", timeout=8) as r:
                srv = float(json.loads(r.read().decode("utf-8"))["data"]["serverTime"])
            _TOFF.update(t=time.time(), ms=srv - (t0 + time.time()) / 2 * 1000)
        except Exception:  # noqa: BLE001
            _TOFF["t"] = time.time() - 540                                # повторить через минуту
    return _TOFF["ms"]


def request(method: str, path: str, params: dict | None = None, c: dict | None = None, signed: bool = True) -> dict:
    """подписанный запрос BingX: подпись — HMAC-SHA256 от строки параметров, ключ в заголовке X-BX-APIKEY"""
    c = c or cfg()
    p = {k: v for k, v in (params or {}).items() if v is not None}
    if signed:
        p["timestamp"] = int(time.time() * 1000 + _time_off(c))          # 03.10 20:50: часы компьютера отставали от сервера BingX на ~2 с, вместе с задержкой сети запросы
        p.setdefault("recvWindow", 20000)                                #   отклонялись «109400 timestamp is invalid» (PUMP, AIN, AT 03.10) — берём время сервера и шире окно
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



def position_info(bx: str, ps: str, hedge: bool, c: dict):
    """(объём, средняя цена) позиции на бирже; (0, 0) — позиции нет (03.10: для проверки цены исполнения против цены бота)"""
    pr = request("GET", "/openApi/swap/v2/user/positions", {"symbol": bx}, c)
    amt = 0.0; avg = 0.0
    for x in (pr.get("data") or []):
        if (not hedge) or str(x.get("positionSide")) == ps:
            a = abs(float(x.get("availableAmt") or x.get("positionAmt") or 0)); amt += a
            try:
                avg = float(x.get("avgPrice") or 0) or avg
            except (TypeError, ValueError):
                pass
    return amt, avg


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


# 05.10 04:20 владелец по NOM (бот вошёл по 0.002674, лимит на BingX исполнился по 0.002665; стоп «в твх» встал на цену бота — на бирже это −3.55 $, а не ноль),
# на предложение «брать цену входа из исполнения биржи и ставить стоп в твх от неё, с учётом комиссии» — «делай». Комиссия BingX за исполнение по рынку
# 0.05 % с каждой стороны (видно в исполнениях: 0.498 $ с 996 $); безубыток = цена исполнения × (1 ± 2 × комиссия).
FEE_RATE = 0.0005


def real_breakeven(fill: float, side: int) -> float:
    """цена, на которой позиция с входом fill закрывается в ноль с учётом комиссии входа и выхода (лонг — чуть выше входа, шорт — чуть ниже)"""
    return fill * (1 + side * 2 * FEE_RATE)


UNFILLED_MIN = 10   # минут: входной лимит без исполнения дольше этого снимается (техническая граница зеркала, не торговая)


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
    # 04.10 14:20 (TRB: лимит на вход 20.295 провисел на демо 10 часов без исполнения — цена демо-рынка BingX была на 2.9 % выше настоящей; в состоянии зеркала позиция числилась
    # «открытой», стопа не было): входной лимит, не исполнившийся за UNFILLED_MIN минут, снимается, запись из состояния убирается. Снимаем только когда биржа прямо ответила,
    # что ордер ждёт и исполнено 0; при любой ошибке запроса ничего не трогаем.
    for sym, p in list(s["open"].items()):
        if p.get("exit_pending") or not p.get("limit") or float(p.get("stop_qty") or 0) > 0 or time.time() - float(p.get("t") or 0) < UNFILLED_MIN * 60:
            continue
        if position_amt(p["bx"], p["ps"], p["hedge"], c) > 0 or not p.get("order_id"):
            continue
        oi = order_info(p["bx"], p["order_id"], c)
        try:
            pending = str(oi.get("status", "")).upper() in ("PENDING", "NEW") and float(oi.get("executedQty") or 0) == 0
        except (TypeError, ValueError):
            pending = False
        if not pending:
            continue
        dr = request("DELETE", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "orderId": p["order_id"]}, c)
        if dr.get("code") == 0:
            del s["open"][sym]; changed = True
            jlog("entry_unfilled", sym=sym, limit_px=p.get("limit_px"), mins=round((time.time() - float(p.get("t") or 0)) / 60))
            out.append(f"BingX {sym[:-4]} вход отменён: лимит {p.get('limit_px')} не исполнился за {UNFILLED_MIN} мин — ордер снят")
    for sym, p in s["open"].items():
        if p.get("exit_pending"):
            continue
        amt, avg = position_info(p["bx"], p["ps"], p["hedge"], c)
        if amt <= 0:
            continue
        if avg and abs(avg - float(p.get("fill") or 0)) > avg * 1e-9:     # 05.10: настоящая цена входа — средняя цена позиции на бирже (после добора R63 она меняется)
            p["fill"] = avg; changed = True
        want = bot_stop(sym, int(p["side"]), float(p["entry"]), float(c["stop_pct"])); want_bot = None
        pp = int((contracts().get(sym) or {}).get("pricePrecision", 6))
        if p.get("fill") and abs(want / float(p["entry"]) - 1) < 1e-6:    # бот перенёс стоп в свою точку входа → на бирже стоп в НАСТОЯЩИЙ безубыток: от цены исполнения, с комиссией
            want_bot = round(want, pp); want = real_breakeven(float(p["fill"]), int(p["side"]))
        want = round(want, pp)
        covered = float(p.get("stop_qty") or 0)
        moved = abs(want - float(p["stop"])) > abs(float(p["stop"])) * 5e-4
        if moved:
            for oid in p.get("stop_ids") or []:
                request("DELETE", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "orderId": oid}, c)
            covered = 0.0; p["stop_ids"] = []
        if amt - covered <= covered * 0.01 + 1e-9:
            continue
        _sb = {"symbol": p["bx"], "side": "SELL" if p["side"] == 1 else "BUY", "positionSide": p["ps"], "type": "STOP_MARKET", "quantity": round(amt - covered, 6), "stopPrice": want, "workingType": "MARK_PRICE"}
        sr = request("POST", "/openApi/swap/v2/trade/order", _sb, c); _note = ""
        if sr.get("code") != 0 and want_bot is not None and want_bot != want:   # настоящий безубыток биржа не приняла (цена уже за ним) — позиция не остаётся без стопа: ставим уровень бота
            sr = request("POST", "/openApi/swap/v2/trade/order", dict(_sb, stopPrice=want_bot), c); _note = f" (безубыток по исполнению {want} не принят — стоит уровень бота {want_bot})"
        if sr.get("code") == 0:
            oid = str((((sr.get("data") or {}).get("order") or {}).get("orderId")) or "")
            p["stop_ids"] = (p.get("stop_ids") or []) + ([oid] if oid else []); p["stop_qty"] = amt; p["stop"] = want; p["stop_ok"] = True; changed = True
            out.append(f"BingX {sym[:-4]} стоп {want}{' (переставлен)' if moved else ''} на {round(amt - covered, 4)} ok{_note}")
        else:
            out.append(f"BingX {sym[:-4]} стоп не поставлен: {sr.get('msg')}")
    for sym, p in s["open"].items():                                     # 01.10 владелец «а где тп?»: цель бота — TAKE_PROFIT_MARKET на бирже, переставляется при смене (удержание +10 %)
        if p.get("exit_pending"):
            continue
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
    # 05.10 10:25 владелец («towns magma не открыты», «а откуда уверенность что по апи на реальном не открывается?», пробный ордер на демо — «да», «убери конечно»):
    # проверка apiStateOpen убрана. Поле в списке контрактов у 144 монет false, но пробный ордер MAGMA-USDT на демо 05.10 биржа приняла (открытие и закрытие);
    # отказов биржи «закрыто для API» в журнале не было ни разу. Если биржа ордер не примет — её отказ вернётся ниже как «лимитный ордер не принят».
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
    if not bp:                                                           # 03.10 (牛来: запрос цены пустой → проверка расхождения пропущена → лимит исполнился на 18 % выше цены бота, стоп биржа отклонила): без цены BingX не входим
        return {"ok": False, "why": f"цена {ct['symbol']} на BingX недоступна — расхождение с Binance не проверить, не входим"}
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
    q_pos, avg_px = position_info(bx, ps, hedge, c)                      # 01.10: лимит мог исполниться частично/позже — стоп ставим на фактический объём, остальное досылает sync_stops
    if q_pos > 0 and avg_px and px and abs(avg_px / px - 1) > 0.05:      # 03.10 (牛来 0.10518 против 0.08931): исполнение далеко от цены бота — рынок BingX другой, закрываем по рынку сразу
        request("DELETE", "/openApi/swap/v2/trade/allOpenOrders", {"symbol": bx}, c)
        rr = request("POST", "/openApi/swap/v2/trade/order", {"symbol": bx, "side": "SELL" if side == 1 else "BUY", "positionSide": ps, "type": "MARKET", "quantity": q_pos}, c)
        return {"ok": False, "why": f"исполнение {avg_px} далеко от цены бота {px} ({(avg_px / px - 1) * 100:+.1f} %) — позиция закрыта по рынку ({'ok' if rr.get('code') == 0 else rr.get('msg')})"}
    if c.get("exchange_stop") and q_pos <= 0:
        sr = {"code": -1, "msg": "лимит ещё не исполнен — стоп поставит sync_stops после исполнения"}
    elif c.get("exchange_stop"):                                         # 01.10 владелец «не надо пока никаких отдельных правил на бирже»: стоп на бирже выключен (exchange_stop: false) — все выходы, включая стопы, даёт бот своим сигналом закрытия
        sr = request("POST", "/openApi/swap/v2/trade/order", {"symbol": bx, "side": "SELL" if side == 1 else "BUY", "positionSide": ps, "type": "STOP_MARKET",
                                                              "quantity": q_pos, "stopPrice": stop, "workingType": "MARK_PRICE"}, c)
    else:
        sr = {"code": 0, "msg": "стоп на бирже выключен"}
    sid = str((((sr.get("data") or {}).get("order") or {}).get("orderId")) or "") if sr.get("code") == 0 and c.get("exchange_stop") else ""
    s["open"][sym] = dict(bx=bx, side=side, qty=q, entry=round(float(px), pp), limit_px=lim, stop=stop, t=time.time(), ps=ps, hedge=hedge, mode=c["mode"], why=why[:120], stop_ok=(sr.get("code") == 0),
                          order_id=str(o.get("orderId") or ""), limit=True, stop_qty=(q_pos if sr.get("code") == 0 else 0.0), stop_ids=([sid] if sid else []),
                          fill=(avg_px if q_pos > 0 and avg_px else None))   # 05.10: цена исполнения на бирже (лимит ещё не исполнен — допишет sync_stops)
    save(s)
    return {"ok": True, "qty": q, "entry": round(float(px), pp), "limit_px": lim, "stop": stop, "order_id": str(o.get("orderId") or ""), "stop_ok": sr.get("code") == 0, "stop_msg": sr.get("msg") if sr.get("code") != 0 else ""}


def add_position(sym: str, side: int, px: float, c: dict | None = None, size_usd: float | None = None) -> dict:
    """R63 (04.10 владелец: «если 2 стратегии одновременно — позиция ×2», «добираем с целью 2-й сделки»): добор к открытой позиции той же стороны — ещё один ЛИМИТНЫЙ ордер
    того же размера по цене бота; плечо и маржу не трогаем. Стоп и цель на новый объём и новые уровни доставит sync_stops (берёт их из книги бота). Один раз на позицию."""
    c = c or cfg(); why0 = ready(c)
    if why0:
        return {"ok": False, "why": why0}
    if STOP_FLAG.exists():
        return {"ok": False, "why": "стоит файл bingx_stop"}
    s = state(); p = s["open"].get(sym)
    if not p or int(p["side"]) != side:
        return {"ok": False, "why": "позиции той же стороны на бирже нет — добирать не к чему"}
    if p.get("x2"):
        return {"ok": False, "why": "позиция уже добрана"}
    ct = contracts().get(sym)
    if not ct:                                                           # 05.10: проверка apiStateOpen убрана и здесь (см. open_position)
        return {"ok": False, "why": f"{sym}: контракт недоступен"}
    try:
        bp = float(((json.load(urllib.request.urlopen(f"{HOST['live']}/openApi/swap/v2/quote/price?symbol={ct['symbol']}", timeout=10)).get("data") or {}).get("price")) or 0)
    except Exception:  # noqa: BLE001
        bp = 0.0
    if not bp or (px and abs(bp / px - 1) > 0.05):
        return {"ok": False, "why": f"цена {ct['symbol']} на BingX {bp or 'недоступна'} против сигнала {px} — не добираем"}
    q = qty_for(ct, px, float(size_usd or c["size_usd"]))
    if not q:
        return {"ok": False, "why": "количество не посчиталось"}
    pp = int(ct.get("pricePrecision", 6)); slip = float(c.get("entry_slip_pct") or 0); lim = round(float(px) * (1 + side * slip), pp)
    if slip and ((side == 1 and bp > lim) or (side == -1 and bp < lim)):
        return {"ok": False, "why": f"цена BingX {bp} уже дальше лимита {lim} — не добираем"}
    r = request("POST", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "side": "BUY" if side == 1 else "SELL", "positionSide": p["ps"], "type": "LIMIT", "price": lim, "quantity": q, "timeInForce": "GTC"}, c)
    if r.get("code") != 0:
        return {"ok": False, "why": f"лимитный ордер добора не принят: {r.get('code')} {r.get('msg')}"}
    o = (r.get("data") or {}).get("order") or r.get("data") or {}
    p.update(x2=True, entry0=p["entry"], add_px=round(float(px), pp), add_qty=q, add_order_id=str(o.get("orderId") or ""),
             entry=round((float(p["entry"]) * float(p["qty"]) + float(px) * q) / (float(p["qty"]) + q), pp), qty=float(p["qty"]) + q)
    save(s)
    return {"ok": True, "qty": q, "entry": p["entry"], "limit_px": lim, "order_id": p["add_order_id"]}


def order_info(bx: str, oid: str, c: dict) -> dict:
    """ордер по orderId: {status, avgPrice, executedQty, ...} или {} (02.10: чтобы отличать «лимит не исполнился» от «биржа закрыла стопом»)"""
    r = request("GET", "/openApi/swap/v2/trade/order", {"symbol": bx, "orderId": str(oid)}, c)
    return ((r.get("data") or {}).get("order") or r.get("data") or {}) if r.get("code") == 0 else {}


def _positions(bx: str, c: dict, tries: int = 3):
    """позиции по символу; None — биржа не ответила (код ≠ 0) и после повторов: это «не знаем», а не «позиции нет»"""
    for i in range(tries):
        pr = request("GET", "/openApi/swap/v2/user/positions", {"symbol": bx}, c)
        if pr.get("code") == 0:
            return pr.get("data") or []
        time.sleep(1.0 + i)
    return None


def close_position(sym: str, exit_px: float | None = None, why: str = "", c: dict | None = None) -> dict:
    c = c or cfg(); s = state(); p = s["open"].get(sym)
    if not p:
        return {"ok": False, "why": "позиции нет в состоянии"}
    if ready(c) and ready(c) != "торговля выключена (enabled: false)":
        return {"ok": False, "why": ready(c)}
    # 04.10 (SOON: 03.10 18:28 запрос позиций вернул «109400 timestamp is invalid», пустой ответ был принят за «позиции нет» — лонг остался на бирже без пары в боте):
    # сначала читаем позицию (с повторами); биржа не ответила — ордера и состояние не трогаем, выход помечается и повторяется на следующих проходах (on_events)
    data = _positions(p["bx"], c)
    if data is None:
        p["exit_pending"] = dict(px=exit_px, why=str(why)[:80], t=time.time()); save(s)
        return {"ok": False, "why": "биржа не отдала позицию (ошибка запроса) — ордера не трогаю, выход повторю на следующем проходе"}
    request("DELETE", "/openApi/swap/v2/trade/allOpenOrders", {"symbol": p["bx"]}, c)                                   # снять лимит (если не исполнился) и стоп
    amt = 0.0
    for x in data:
        if (not p["hedge"]) or str(x.get("positionSide")) == p["ps"]:
            amt += abs(float(x.get("availableAmt") or x.get("positionAmt") or 0))
    if amt <= 0:                                                       # позиции нет: либо лимит не исполнился, либо биржа уже закрыла её стопом/тейком
        # 02.10 владелец по SAND («всмысле не было в демо? было»): стоп на бирже сработал в 10:04, бот вышел в 10:11 — журнал писал «позиции не было», −135 $ терялись
        fills = []                                                     # 02.10 13:45 (проверка): все исполненные стоп/тейк-ордера (стоп мог быть в двух частях), executedQty приходит строкой
        for oid, tag in [(o, "стопом") for o in (p.get("stop_ids") or [])] + [(o, "тейком") for o in (p.get("tp_ids") or [])]:
            oi = order_info(p["bx"], oid, c)
            if oi and str(oi.get("status", "")).upper() == "FILLED" and float(oi.get("avgPrice") or 0) > 0:
                try:
                    qx = float(oi.get("executedQty") or 0)
                except (TypeError, ValueError):
                    qx = 0.0
                fills.append((float(oi["avgPrice"]), tag, qx if qx > 0 else float(p["qty"])))
        if fills:
            qf = sum(q for _, _, q in fills) or float(p["qty"])
            out = sum(px_ * q for px_, _, q in fills) / qf; tag = "/".join(sorted({t_ for _, t_, _ in fills}))
            e0 = float(p.get("fill") or p["entry"]); pnl = (out / e0 - 1) * p["side"] * e0 * qf   # 05.10: от цены исполнения входа (BR 04.10: бот 0.5175, биржа 0.5038 — журнал писал −42.8 $ вместо −16.2 $)
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
        p["exit_pending"] = dict(px=exit_px, why=str(why)[:80], t=time.time()); p["stop_qty"] = 0.0; p["stop_ids"] = []; p["tp_qty"] = 0.0; p["tp_ids"] = []; save(s)   # 04.10: ордера уже сняты — выход повторится на следующем проходе
        return {"ok": False, "why": f"закрытие не принято: {r.get('code')} {r.get('msg')} — повторю на следующем проходе"}
    o = (r.get("data") or {}).get("order") or r.get("data") or {}
    out = float(o.get("avgPrice") or 0) or (exit_px or p["entry"])
    e0 = float(p.get("fill") or p["entry"]); pnl = (out / e0 - 1) * p["side"] * e0 * p["qty"]   # 05.10: от цены исполнения входа
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
        for sym_, p_ in list(state()["open"].items()):                    # 04.10: выходы, которые не дошли до биржи (ошибка запроса), повторяются каждый проход
            if p_.get("exit_pending"):
                r_ = close_position(sym_, (p_["exit_pending"] or {}).get("px"), why=str((p_["exit_pending"] or {}).get("why") or "повтор выхода"), c=c)
                jlog("exit_retry", sym=sym_, **r_)
                msgs.append(f"BingX {sym_[:-4]} выход (повтор): {'ok' if r_['ok'] else r_['why']}")
        msgs += sync_stops(c)                                            # 01.10: дослать стопы на исполнившиеся лимиты
        # 03.10 владелец: «после любой правки бота в течение 1 часа сделки только в журнале, на бирже сделки не открываются» —
        # правка = изменение fast_tier.py / core_config.py / bingx_trader.py (mtime); выходы по открытым позициям идут как обычно
        try:
            from core_config import BINGX_FREEZE_AFTER_EDIT_MIN as _fz
        except ImportError:
            _fz = 60
        _edited = max(os.path.getmtime(BASE_DIR / f) for f in ("fast_tier.py", "core_config.py", "bingx_trader.py") if (BASE_DIR / f).exists())
        _left = _fz * 60 - (time.time() - _edited)
        if _left > 0 and any(str(e.get("kind", "")) == "entry" for e in ev):
            msgs.append(f"BingX: входы заморожены после правки бота ещё {int(_left // 60) + 1} мин — сделки только в журнале")
            jlog("freeze", left_min=int(_left // 60) + 1, skipped=[e["sym"] for e in ev if str(e.get("kind", "")) == "entry"])
            ev = [e for e in ev if str(e.get("kind", "")) != "entry"]
        for e in ev:
            k = str(e.get("kind", ""))
            if k == "entry" and e.get("x2") and e["sym"] in state()["open"]:   # R63: вторая стратегия в ту же сторону — добор к открытой позиции
                r = add_position(e["sym"], int(e["side"]), float(e["px"]), c=c, size_usd=e.get("usd_in"))   # R79 (06.10): сумма входа приходит из события
                jlog("add", sym=e["sym"], book=e.get("book"), side=e["side"], **r)
                msgs.append(f"BingX {e['sym'][:-4]} добор: {'ok' if r['ok'] else r['why']}")
            elif k == "entry":
                r = open_position(e["sym"], int(e["side"]), float(e["px"]), why=e.get("rule") or "", c=c, size_usd=e.get("usd_in"))   # R79 (06.10): сумма входа по уверенности
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
