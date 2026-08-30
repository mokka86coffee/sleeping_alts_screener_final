#!/usr/bin/env python3
"""Киты Hyperliquid через Coinglass (31.08): сводки как в телеге.

Два эндпоинта тарифа: whale-alert (свежие действия) и
whale-position (все крупные позиции). Пишет output/whales.json:
  alerts: человеческие строки «КИТ: открыл лонг BTC $1.0M @ 78620»
  by_coin: суммарный расклад китов по монетам ЖУРНАЛА (лонг/шорт $)
Схема читает файл и кормит нижнюю ленту пузырями kind="whale".
Запуск руками: python3 whales_coinglass.py · в прогоне — врезкой.
"""
import json
import os
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

try:
    from config import load as _cfg
    _cfg()
except Exception:
    pass

BASE = "https://open-api-v4.coinglass.com/api"
ACT = {1: "открыл", 2: "закрыл", 3: "нарастил", 4: "урезал"}


def _get(path, **prm):
    url = BASE + path + ("?" + urllib.parse.urlencode(prm) if prm else "")
    req = urllib.request.Request(url, headers={
        "CG-API-KEY": os.environ.get("COINGLASS_KEY", ""),
        "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        d = json.loads(r.read().decode())
    if str(d.get("code")) != "0":
        raise RuntimeError(f"{path}: code={d.get('code')} {d.get('msg')}")
    return d.get("data") or []


def _usd(x):
    x = float(x or 0)
    return (f"${x/1e9:.2f}B" if x >= 1e9 else
            f"${x/1e6:.1f}M" if x >= 1e6 else f"${x/1e3:.0f}K")


def collect(write=True):
    out = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "alerts": [], "by_coin": {}}
    # свежие действия — лента
    for a in _get("/hyperliquid/whale-alert", size=30):
        side = "лонг" if float(a.get("position_size") or 0) >= 0 else "шорт"
        act = ACT.get(a.get("position_action"), "движение")
        t = (f"КИТ: {act} {side} {a.get('symbol')} "
             f"{_usd(a.get('position_value_usd'))} @ {a.get('entry_price')}")
        out["alerts"].append({
            "title": t,
            "note": f"кошелёк {str(a.get('user'))[:10]}… · "
                    f"ликвидация {a.get('liq_price')}",
            "ts": a.get("create_time")})
    # позиции — расклад по монетам журнала
    coins = set()
    jp = Path("output") / "reputation.json"
    if jp.exists():
        coins = {k[:-4] for k in json.loads(jp.read_text())
                 if k != "_meta"}
    agg = {}
    for p in _get("/hyperliquid/whale-position", size=1500):
        sym = p.get("symbol")
        if coins and sym not in coins and sym not in ("BTC", "ETH", "SOL"):
            continue
        v = float(p.get("position_value_usd") or 0)
        sgn = 1 if float(p.get("position_size") or 0) >= 0 else -1
        a = agg.setdefault(sym, {"long": 0.0, "short": 0.0, "n": 0})
        a["long" if sgn > 0 else "short"] += abs(v)
        a["n"] += 1
    for sym, a in sorted(agg.items(),
                         key=lambda kv: -(kv[1]["long"] + kv[1]["short"])):
        out["by_coin"][sym] = {
            "line": f"{sym}: киты лонг {_usd(a['long'])} · "
                    f"шорт {_usd(a['short'])} · позиций {a['n']}",
            "long": round(a["long"]), "short": round(a["short"]),
            "n": a["n"]}
    if write:
        Path("output").mkdir(exist_ok=True)
        (Path("output") / "whales.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return f"алертов {len(out['alerts'])}, монет {len(out['by_coin'])}"


if __name__ == "__main__":
    print("киты:", collect())
