#!/usr/bin/env python3
"""КОПИР СИГНАЛОВ «РОМАНТИКА» (14.11, владелец: «напиши чтобы что-то брало у него сделки из открытого канала»; «сидеть следить за каждым сообщением я не хочу»).

Читает Telegram ТВОИМ аккаунтом (Telethon, userbot) — видит и частные группы, куда ты вступил по ссылке. Каждое новое сообщение:
  разбор → команда (вход / тейк / стоп / стоп в ТВХ / фикс N% / докупил / закрыл / закрыл всё) → исполнение на BingX → уведомление в твой бот.

Источники — config/romantic_config.json → sources: [{"chat": "...", "mode": "trade" | "record"}]
  trade  — исполняет на бирже (exec.mode: demo | live) или на бумаге (exec.mode: paper);
  record — только записывает и считает «что было бы» на бумаге (закрытый канал).
Размер задаёшь ТЫ, не он: exec.size_usd — позиция в $ на сделку; «low risk» — × low_risk_mult; «докупил» — + add_mult × size, не больше max_adds раз.
Пока его стопа нет — свой защитный стоп −default_stop_pct от входа. Плечо и тип маржи на аккаунте не трогаем (как bingx_trader).

Ключи BingX — из bingx_config.json через bingx_trader.cfg() (не печатаются). api_id/api_hash Telegram — в config/romantic_config.json, берутся на my.telegram.org.
Журнал всех сообщений и действий — output/romantic_signals.jsonl; состояние — output/romantic_state.json; файл-флаг romantic_stop — новых входов нет.

    .venv/bin/pip install telethon
    .venv/bin/python romantic_copier.py --chats     # первый запуск: вход по номеру и коду, список твоих чатов (чтобы вписать нужный в sources)
    .venv/bin/python romantic_copier.py --history 30  # история за 30 дней: тексты + картинки сделок в output/romantic_history/ — для разбора плюсов и минусов
    .venv/bin/python romantic_copier.py --test      # прогон разбора на примерах, без Telegram и биржи
    .venv/bin/python romantic_copier.py             # работа
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CFG = BASE_DIR / "config" / "romantic_config.json"
TG_CFG = BASE_DIR / "config" / "telegram_config.json"
LOG = BASE_DIR / "output" / "romantic_signals.jsonl"
STATE = BASE_DIR / "output" / "romantic_state.json"
STOP_FLAG = BASE_DIR / "romantic_stop"

TEMPLATE = {
    "api_id": 0, "api_hash": "", "session": "romantic",
    "sources": [{"chat": "впиши название канала как в --chats или его id", "mode": "trade"},
                {"chat": "закрытый канал", "mode": "record"}],
    "exec": {"enabled": False, "mode": "paper", "size_usd": 500, "low_risk_mult": 0.5, "add_mult": 0.5, "max_adds": 2,
             "default_stop_pct": 0.03, "max_open": 6, "daily_loss_limit_usd": 150},
    "notify": True,
    "_note": "mode: paper — без ордеров, считает по цене BingX; demo — демо-счёт BingX (VST); live — реальные деньги. enabled: false — только журнал.",
}

# ───────────────────────── разбор сообщений ─────────────────────────
NUM = r"([0-9]+(?:[.,][0-9]+)?)"
SIDE = {"long": 1, "лонг": 1, "short": -1, "шорт": -1}
RE_ENTRY = re.compile(r"^\s*#?\$?([A-Za-z0-9]{2,15})\s+(long|short|лонг|шорт)\b(.*)$", re.I)
RE_TAKE = re.compile(r"\b(?:take|тейк|тп|tp)\b\s*[:=]?\s*" + NUM, re.I)
RE_STOP = re.compile(r"\b(?:stop|стоп|sl)\b(?:\s+[^\d\s]+){0,2}?\s*[:=]?\s*" + NUM, re.I)   # «стоп 0.017», «стоп передвинул 0.0161»
RE_BE = re.compile(r"(?:стоп|stop)\w*\s*(?:в|на|to|in)?\s*(?:твх|тв|бу|безубыт\w*|be\b|breakeven)", re.I)
RE_FIX = re.compile(r"(?:фикс\w*|fix\w*|зафикс\w*)\s*(\d{1,3})\s*%", re.I)
RE_ADD = re.compile(r"\b(докупил\w*|добрал\w*|долил\w*|усредн\w*|добавил\w*)", re.I)
RE_CLOSE_ALL = re.compile(r"(закрыл\w*|закрываю|closed?)\s+(все|всё|all|всю)", re.I)
RE_CLOSE = re.compile(r"\b(закрыл\w*|закрываю|closed?|вышел|выхожу)\b", re.I)
RE_REPORT = re.compile(r"статистик|итог\w* за|общий профит|за \d+ (торговых )?дн", re.I)
RE_PCT_LINE = re.compile(r"[+−-]\s*\d[\d\s.,]*%")
STOPWORDS = {"LONG", "SHORT", "TAKE", "STOP", "LOW", "RISK", "ALL", "BE", "TP", "SL", "USDT", "THE", "AND", "IN", "TO"}


def parse(text: str) -> list[dict]:
    """текст сообщения → список команд. Монета в командах без неё = None (берётся из ответа/контекста). Отчёты со статистикой пропускаются."""
    t = (text or "").strip()
    if not t:
        return []
    lines = [x for x in t.splitlines() if x.strip()]
    if RE_REPORT.search(t) or sum(1 for x in lines if RE_PCT_LINE.search(x)) >= 3:
        return [{"cmd": "skip", "why": "отчёт/статистика"}]
    out: list[dict] = []
    low = bool(re.search(r"low\s*risk|лоу\s*риск|малый\s*риск", t, re.I))
    for ln in lines:
        m = RE_ENTRY.match(ln)
        if m and not RE_PCT_LINE.search(ln) and m.group(1).upper() not in STOPWORDS:
            rest = m.group(3)
            out.append({"cmd": "open", "coin": m.group(1).upper(), "side": SIDE[m.group(2).lower()], "low": low or bool(re.search(r"low\s*risk", rest, re.I))})
    coin_hdr = None
    m0 = re.match(r"^\s*#?\$?([A-Za-z][A-Za-z0-9]{1,14})\b", t)
    if m0 and m0.group(1).upper() not in STOPWORDS and not RE_CLOSE.match(t) and not RE_ADD.match(t):
        coin_hdr = m0.group(1).upper()
    tk = RE_TAKE.search(t)
    if tk:
        out.append({"cmd": "take", "coin": coin_hdr if not out else out[-1]["coin"], "px": float(tk.group(1).replace(",", "."))})
    if RE_BE.search(t):
        out.append({"cmd": "stop_be", "coin": coin_hdr if not out else None})
    else:
        sp = RE_STOP.search(t)
        if sp:
            out.append({"cmd": "stop", "coin": coin_hdr if not out else out[-1]["coin"], "px": float(sp.group(1).replace(",", "."))})
    fx = RE_FIX.search(t)
    if fx:
        out.append({"cmd": "fix", "coin": None, "pct": min(100, int(fx.group(1)))})
    if RE_ADD.search(t):
        out.append({"cmd": "add", "coin": coin_hdr})
    if RE_CLOSE_ALL.search(t):
        out.append({"cmd": "close_all"})
    elif RE_CLOSE.search(t) and not fx:
        before = RE_CLOSE.split(t)[0]
        coins = [c.upper() for c in re.findall(r"\b([A-Za-z][A-Za-z0-9]{1,14})\b", before) if c.upper() not in STOPWORDS]
        if coins:
            out += [{"cmd": "close", "coin": c} for c in coins]
        else:
            out.append({"cmd": "close", "coin": None})
    return out


# ───────────────────────── журнал и состояние ─────────────────────────
def jlog(kind: str, **kw) -> None:
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"t": round(time.time(), 1), "kind": kind, **kw}, ensure_ascii=False) + "\n")


def load(p: Path, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def save_state(s: dict) -> None:
    STATE.parent.mkdir(exist_ok=True); tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8"); tmp.replace(STATE)


def cfg() -> dict:
    if not CFG.exists():
        CFG.parent.mkdir(exist_ok=True); CFG.write_text(json.dumps(TEMPLATE, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"создан шаблон {CFG} — впиши api_id, api_hash и sources"); sys.exit(1)
    c = load(CFG, {}); e = {**TEMPLATE["exec"], **(c.get("exec") or {})}
    return {**TEMPLATE, **c, "exec": e}


def notify(text: str) -> None:
    c = load(TG_CFG, {})
    if not (cfg().get("notify") and c.get("bot_token") and c.get("chat_id")):
        return
    try:
        urllib.request.urlopen(urllib.request.Request(f"https://api.telegram.org/bot{c['bot_token']}/sendMessage",
                               json.dumps({"chat_id": c["chat_id"], "text": "🎯 " + text}).encode(), headers={"Content-Type": "application/json"}), timeout=10).close()
    except Exception as e:  # noqa: BLE001
        jlog("notify_error", msg=str(e)[:200])


# ───────────────────────── биржа ─────────────────────────
import bingx_trader as bt  # noqa: E402  (ключи, подпись, контракты, точность объёма — общие с основным ботом)


def bx_cfg(mode: str) -> dict:
    return {**bt.cfg(), "mode": mode}


def contract(coin: str) -> dict | None:
    ct = bt.contracts()
    for k in (coin + "USDT", "1000" + coin + "USDT", coin.replace("1000", "") + "USDT"):
        if k in ct:
            return ct[k]
    return None


def price(sym_bx: str) -> float:
    try:
        return float(((json.load(urllib.request.urlopen(f"{bt.HOST['live']}/openApi/swap/v2/quote/price?symbol={sym_bx}", timeout=10)).get("data") or {}).get("price")) or 0)
    except Exception:  # noqa: BLE001
        return 0.0


class Book:
    """позиции одного источника. mode: paper (без ордеров, по цене BingX) | demo | live (ордера на BingX). Ключ позиции — монета."""

    def __init__(self, src: str, mode: str, e: dict):
        self.src, self.mode, self.e = src, mode, e
        self.c = bx_cfg(mode) if mode in ("demo", "live") else None

    # --- состояние
    def st(self) -> dict:
        s = load(STATE, {})
        return s.setdefault(self.src, {"open": {}, "closed": [], "pnl": {}, "last": None, "msg": {}})

    def put(self, b: dict) -> None:
        s = load(STATE, {}); s[self.src] = b; save_state(s)

    # --- ордера (только demo/live)
    def _order(self, body: dict) -> dict:
        return bt.request("POST", "/openApi/swap/v2/trade/order", body, self.c)

    def _ps(self, side: int) -> str:
        return ("LONG" if side == 1 else "SHORT") if bt.hedge_mode(self.c) else "BOTH"

    def _cancel(self, p: dict, key: str) -> None:
        for oid in p.get(key) or []:
            bt.request("DELETE", "/openApi/swap/v2/trade/order", {"symbol": p["bx"], "orderId": oid}, self.c)
        p[key] = []

    def _protect(self, p: dict, kind: str, px: float) -> None:
        """поставить/заменить стоп (STOP_MARKET) или тейк (TAKE_PROFIT_MARKET) на весь текущий объём"""
        p[kind] = px
        if not self.c:
            return
        key = "stop_ids" if kind == "stop" else "tp_ids"
        self._cancel(p, key)
        r = self._order({"symbol": p["bx"], "side": "SELL" if p["side"] == 1 else "BUY", "positionSide": p["ps"],
                         "type": "STOP_MARKET" if kind == "stop" else "TAKE_PROFIT_MARKET", "quantity": p["qty"], "stopPrice": px, "workingType": "MARK_PRICE"})
        if r.get("code") == 0:
            p[key] = [str((((r.get("data") or {}).get("order") or {}).get("orderId")) or "")]
        else:
            jlog("protect_fail", src=self.src, coin=p["coin"], kind=kind, px=px, code=r.get("code"), msg=str(r.get("msg"))[:200])

    def _market(self, p: dict, side: int, qty: float, reduce: bool) -> float:
        """рыночный ордер; → цена исполнения (paper — текущая цена BingX)"""
        if not self.c:
            return price(p["bx"])
        body = {"symbol": p["bx"], "side": ("BUY" if side == 1 else "SELL"), "positionSide": p["ps"], "type": "MARKET", "quantity": qty}
        if reduce and p["ps"] == "BOTH":
            body["reduceOnly"] = "true"
        r = self._order(body)
        if r.get("code") != 0:
            raise RuntimeError(f"ордер не принят: {r.get('code')} {r.get('msg')}")
        o = (r.get("data") or {}).get("order") or r.get("data") or {}
        return float(o.get("avgPrice") or 0) or price(p["bx"])

    # --- команды
    def open(self, coin: str, side: int, low: bool) -> str:
        b = self.st()
        if self.c and STOP_FLAG.exists():
            return "стоит romantic_stop — новых входов нет"
        if coin in b["open"]:
            return f"{coin}: уже открыта"
        if len(b["open"]) >= int(self.e["max_open"]):
            return f"открыто {len(b['open'])} из {self.e['max_open']}"
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self.e.get("daily_loss_limit_usd") and b["pnl"].get(today, 0) <= -abs(float(self.e["daily_loss_limit_usd"])):
            return f"дневной лимит потерь ({b['pnl'][today]:+.0f} $)"
        ct = contract(coin)
        if not ct:
            return f"{coin}: нет на BingX"
        bx = ct["symbol"]; px = price(bx)
        if not px:
            return f"{coin}: нет цены BingX"
        size = float(self.e["size_usd"]) * (float(self.e["low_risk_mult"]) if low else 1)
        q = bt.qty_for(ct, px, size)
        if not q:
            return f"{coin}: объём не посчитался"
        p = dict(coin=coin, bx=bx, side=side, qty=q, entry=px, t=time.time(), adds=0, low=low, ps="BOTH", stop_ids=[], tp_ids=[], pp=int(ct.get("pricePrecision", 6)), ct=ct)
        if self.c:
            p["ps"] = self._ps(side)
            try:
                p["entry"] = self._market(p, side, q, False)
            except RuntimeError as e:
                return f"{coin}: {e}"
        self._protect(p, "stop", round(p["entry"] * (1 - side * float(self.e["default_stop_pct"])), p["pp"]))
        p.pop("ct"); b["open"][coin] = p; b["last"] = coin; self.put(b)
        return f"вошёл {coin} {'LONG' if side == 1 else 'SHORT'} {q * p['entry']:.0f} $ по {p['entry']} · стоп {p['stop']}{' · low risk' if low else ''}"

    def add(self, coin: str) -> str:
        b = self.st(); p = b["open"].get(coin)
        if not p:
            return f"{coin}: нечего докупать"
        if p["adds"] >= int(self.e["max_adds"]):
            return f"{coin}: докупок уже {p['adds']} — предел"
        ct = contract(coin); px = price(p["bx"]); q = bt.qty_for(ct, px, float(self.e["size_usd"]) * float(self.e["add_mult"])) if ct and px else None
        if not q:
            return f"{coin}: докупка не посчиталась"
        try:
            fill = self._market(p, p["side"], q, False)
        except RuntimeError as e:
            return f"{coin}: {e}"
        p["entry"] = round((p["entry"] * p["qty"] + fill * q) / (p["qty"] + q), p["pp"]); p["qty"] = round(p["qty"] + q, 8); p["adds"] += 1
        if p.get("stop"):
            self._protect(p, "stop", p["stop"])
        if p.get("take"):
            self._protect(p, "take", p["take"])
        self.put(b)
        return f"докупил {coin} +{q * fill:.0f} $ · средняя {p['entry']}"

    def protect(self, coin: str, kind: str, px: float | None) -> str:
        b = self.st(); p = b["open"].get(coin)
        if not p:
            return f"{coin}: позиции нет"
        if px is None:                                                   # стоп в ТВХ: цена входа с комиссией входа и выхода
            px = round(bt.real_breakeven(p["entry"], p["side"]), p["pp"])
        self._protect(p, kind, px); self.put(b)
        return f"{coin}: {'стоп' if kind == 'stop' else 'тейк'} {px}"

    def close(self, coin: str, pct: int = 100, why: str = "") -> str:
        b = self.st(); p = b["open"].get(coin)
        if not p:
            return f"{coin}: позиции нет"
        q = p["qty"] if pct >= 100 else round(p["qty"] * pct / 100, 8)
        if self.c:
            prec = int((contract(coin) or {}).get("quantityPrecision", 6)); q = round(q, prec) if pct < 100 else bt.position_amt(p["bx"], p["ps"], p["ps"] != "BOTH", self.c) or q
        try:
            out = self._market(p, -p["side"], q, True)
        except RuntimeError as e:
            return f"{coin}: {e}"
        pnl = (out - p["entry"]) * p["side"] * q - 2 * bt.FEE_RATE * out * q
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d"); b["pnl"][today] = round(b["pnl"].get(today, 0) + pnl, 2)
        if pct >= 100 or q >= p["qty"]:
            if self.c:
                bt.request("DELETE", "/openApi/swap/v2/trade/allOpenOrders", {"symbol": p["bx"]}, self.c)
            b["closed"].append({"coin": coin, "side": p["side"], "entry": p["entry"], "exit": out, "pnl": round(pnl, 2), "t0": p["t"], "t1": time.time(), "why": why})
            del b["open"][coin]
        else:
            p["qty"] = round(p["qty"] - q, 8)
            for k in ("stop", "take"):
                if p.get(k):
                    self._protect(p, k, p[k])
        self.put(b)
        return f"{'закрыл' if pct >= 100 else f'фикс {pct}%'} {coin} по {out} · {pnl:+.2f} $ · за день {b['pnl'][today]:+.2f} $"

    def sync(self) -> list[str]:
        """раз в минуту: позиции, которые закрыла биржа (стоп/тейк) или пробила цена на бумаге — переносим в закрытые"""
        b = self.st(); msgs = []
        for coin, p in list(b["open"].items()):
            if self.c:
                if bt.position_amt(p["bx"], p["ps"], p["ps"] != "BOTH", self.c) > 0:
                    continue
                out = price(p["bx"]); why = "закрыта биржей (стоп/тейк)"
            else:
                px = price(p["bx"]); hit = None
                if px and p.get("stop") and (px - p["stop"]) * p["side"] <= 0:
                    hit = ("стоп", p["stop"])
                elif px and p.get("take") and (px - p["take"]) * p["side"] >= 0:
                    hit = ("тейк", p["take"])
                if not hit:
                    continue
                why, out = f"бумага: {hit[0]}", hit[1]
            pnl = (out - p["entry"]) * p["side"] * p["qty"] - 2 * bt.FEE_RATE * out * p["qty"]
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d"); b["pnl"][today] = round(b["pnl"].get(today, 0) + pnl, 2)
            b["closed"].append({"coin": coin, "side": p["side"], "entry": p["entry"], "exit": out, "pnl": round(pnl, 2), "t0": p["t"], "t1": time.time(), "why": why})
            del b["open"][coin]; msgs.append(f"{coin}: {why} по {out} · {pnl:+.2f} $")
        if msgs:
            self.put(b)
        return msgs


# ───────────────────────── обработка сообщения ─────────────────────────
def handle(book: Book, msg_id: int, reply_to: int | None, text: str) -> list[str]:
    cmds = parse(text); b = book.st(); res = []
    ctx = b["msg"].get(str(reply_to)) if reply_to else None              # монета из сообщения, на которое ответ
    for c in cmds:
        if c["cmd"] == "skip":
            continue
        coin = c.get("coin") or ctx or b.get("last")
        try:
            if c["cmd"] == "open":
                r = book.open(c["coin"], c["side"], c["low"]); coin = c["coin"]
            elif c["cmd"] == "close_all":
                r = "; ".join(book.close(k, 100, "закрыл всё") for k in list(book.st()["open"])) or "закрывать нечего"
            elif not coin:
                r = f"{c['cmd']}: не понял, к какой монете"
            elif c["cmd"] == "take":
                r = book.protect(coin, "take", c["px"])
            elif c["cmd"] == "stop":
                r = book.protect(coin, "stop", c["px"])
            elif c["cmd"] == "stop_be":
                r = book.protect(coin, "stop", None)
            elif c["cmd"] == "fix":
                r = book.close(coin, c["pct"], "фикс")
            elif c["cmd"] == "add":
                r = book.add(coin)
            elif c["cmd"] == "close":
                r = book.close(coin, 100, "закрыл")
            else:
                r = ""
        except Exception as e:  # noqa: BLE001
            r = f"{c['cmd']} {coin}: ошибка {type(e).__name__}: {e}"
        if coin:
            b = book.st(); b["msg"][str(msg_id)] = coin; book.put(b)
        res.append(r)
    jlog("msg", src=book.src, mode=book.mode, id=msg_id, reply_to=reply_to, text=text[:500], cmds=cmds, res=res)
    return res


# ───────────────────────── история за N дней ─────────────────────────
async def history(client, c: dict, days: int) -> None:
    """--history N: все сообщения источников за N дней (текст, дата, ответ на) + картинки сделок → output/romantic_history/<канал>/;
    сводка — output/romantic_history/<канал>/messages.jsonl. По ней потом считается, где был плюс и где минус."""
    from datetime import timedelta
    since = datetime.now(timezone.utc) - timedelta(days=days)
    async for d in client.iter_dialogs(limit=400):
        for s in c["sources"]:
            if not (str(s["chat"]) in (str(d.id), d.name) or str(s["chat"]).lstrip("@").lower() == str(getattr(d.entity, "username", "") or "").lower()):
                continue
            folder = BASE_DIR / "output" / "romantic_history" / re.sub(r"[^\w\-]+", "_", d.name)[:40]
            folder.mkdir(parents=True, exist_ok=True); n = ph = 0
            with (folder / "messages.jsonl").open("w", encoding="utf-8") as f:
                async for m in client.iter_messages(d.id, offset_date=None, reverse=False):
                    if m.date < since:
                        break
                    img = None
                    if m.photo:
                        img = f"{m.id}.jpg"
                        if not (folder / img).exists():
                            await client.download_media(m, file=str(folder / img)); ph += 1
                    f.write(json.dumps({"id": m.id, "date": m.date.astimezone().isoformat(timespec="minutes"), "reply_to": m.reply_to.reply_to_msg_id if m.reply_to else None,
                                        "text": m.message or "", "img": img, "cmds": parse(m.message or "")}, ensure_ascii=False) + "\n"); n += 1
            print(f"{d.name}: {n} сообщений, картинок {ph} → {folder}")


# ───────────────────────── Telegram ─────────────────────────
async def run(list_only: bool = False) -> None:
    from telethon import TelegramClient, events
    c = cfg()
    if not c["api_id"] or not c["api_hash"]:
        print(f"впиши api_id и api_hash в {CFG} (my.telegram.org → API development tools)"); return
    client = TelegramClient(str(BASE_DIR / "config" / c["session"]), int(c["api_id"]), c["api_hash"])
    await client.start()
    if "--history" in sys.argv:
        i = sys.argv.index("--history"); days = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 30
        await history(client, c, days); return
    if list_only:
        async for d in client.iter_dialogs(limit=200):
            print(f"{d.id:>16}  {'канал' if d.is_channel else 'чат  '}  {d.name}")
        return
    e = c["exec"]; books = {}
    async for d in client.iter_dialogs(limit=400):
        for s in c["sources"]:
            if str(s["chat"]) in (str(d.id), d.name) or str(s["chat"]).lstrip("@").lower() == str(getattr(d.entity, "username", "") or "").lower():
                mode = ("paper" if not e["enabled"] else e["mode"]) if s["mode"] == "trade" else "paper"
                books[d.id] = Book(d.name, mode, e)
    if not books:
        print("ни один источник из sources не найден среди твоих чатов — смотри --chats"); return
    print("слушаю:", ", ".join(f"{bk.src} [{bk.mode}]" for bk in books.values()))
    notify("копир запущен: " + ", ".join(f"{bk.src} [{bk.mode}]" for bk in books.values()))

    @client.on(events.NewMessage(chats=list(books)))
    async def on_msg(ev):  # noqa: ANN001
        bk = books.get(ev.chat_id)
        if not bk:
            return
        rt = ev.message.reply_to.reply_to_msg_id if ev.message.reply_to else None
        res = await asyncio.to_thread(handle, bk, ev.message.id, rt, ev.message.message or "")
        res = [r for r in res if r]
        if res:
            print(f"{datetime.now():%H:%M:%S} [{bk.src}] " + " | ".join(res), flush=True)
            notify(f"[{bk.src} · {bk.mode}] " + "\n".join(res))

    async def ticker():
        while True:
            await asyncio.sleep(60)
            for bk in books.values():
                try:
                    msgs = await asyncio.to_thread(bk.sync)
                except Exception as ex:  # noqa: BLE001
                    jlog("sync_error", src=bk.src, msg=str(ex)[:200]); msgs = []
                for m in msgs:
                    notify(f"[{bk.src} · {bk.mode}] {m}")

    asyncio.create_task(ticker())
    await client.run_until_disconnected()


TESTS = [
    "Evaa long low risk", "Take 1.6601", "Aria Take 0.25051 Stop 0.17614", "Night long\nKite long", "Arb Aave закрыл",
    "Закрыл все, знаю большие минуса и неприятно по депозиту", "Тут делаю фикс 35% и стоп в твх ставим", "Закрыл в +18% чистого",
    "AKE LONG Открываем на копейку", "докупил, стоп передвинул 0.0161", "Stop 0.0179", "Pieverse +10% чистого",
    "Статистика за 10 торговых дней\n\nAria long +1800%\nEvaa long +1300%\nAin long -400%\n\nОбщий профит составляет +11.800%",
    "Hana Long Заходим", "Up можем рассмотреть", "13% чистого\n\nЗакрыл полностью",
]

if __name__ == "__main__":
    if "--test" in sys.argv:
        for t in TESTS:
            print(f"{t!r:70.70} → {parse(t)}")
    else:
        asyncio.run(run(list_only="--chats" in sys.argv))
