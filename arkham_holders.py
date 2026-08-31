#!/usr/bin/env python3
"""Держатели монет книги по АДРЕСУ КОНТРАКТА (31.08).

Поиск по названию давал однофамильцев (OnRe вместо ONG, Ola Finance
вместо OlaXBT). Контракт однозначен, поэтому идём от него.

CONTRACTS ниже: тикер → (сеть, адрес контракта). Дописывай сам —
адрес берётся в обозревателе сети или на странице токена
CoinMarketCap/CoinGecko («Contracts»).

Скрипт перебирает несколько возможных путей API и печатает, какой
сработал: у Arkham точка держателей называется по-разному в разных
версиях, а гадать мы больше не будем.

Запуск:  python3 arkham_holders.py
Пишет:   investors.json (адреса для сторожа) + печать топа
"""
import json
import time
from pathlib import Path

import arkham_fetch as A

CONTRACTS = {
    "ENA": ("ethereum", "0x57e114B691Db790C35207b2e685D4A43181e6061"),
    # дописать по мере появления:
    # "BMT":   ("bsc",      "0x..."),
    # "BLESS": ("ethereum", "0x..."),
    # "AIO":   ("bsc",      "0x..."),
    # "ONG":   ("ethereum", "0x..."),
}
SKIP = ("binance", "okx", "bybit", "gate", "kucoin", "mexc", "bitget",
        "htx", "coinbase", "kraken", "upbit", "bithumb", "bridge",
        "null", "burn", "lock", "vesting")


def holders(chain, addr):
    """Перебор возможных путей — печатаем тот, что ответил 200."""
    tries = [
        (f"/token/holders/{chain}/{addr}", {"limit": 25}),
        (f"/token/holders/{addr}", {"limit": 25}),
        (f"/token/top_holders/{chain}/{addr}", {"limit": 25}),
        (f"/balances/token/{chain}/{addr}", {"limit": 25}),
        ("/token/holders", {"chain": chain, "address": addr, "limit": 25}),
    ]
    for path, prm in tries:
        d, c = A.get(path, **prm)
        time.sleep(A.PAUSE)
        if c != 200 or not isinstance(d, dict):
            continue
        for key in ("holders", "balances", "data", "addresses", "results"):
            rows = d.get(key)
            if isinstance(rows, list) and rows:
                print(f"   путь сработал: {path} → {key}:{len(rows)}")
                return rows
            if isinstance(rows, dict) and rows:
                flat = []
                for v in rows.values():
                    if isinstance(v, list):
                        flat += v
                    elif isinstance(v, dict):
                        flat += list(v.values())
                if flat:
                    print(f"   путь сработал: {path} → {key} (вложенный)")
                    return flat
    return []


def main():
    book = {}
    if Path("investors.json").exists():
        try:
            book = json.loads(Path("investors.json").read_text("utf-8"))
        except Exception:
            book = {}
    for sym, (chain, ca) in CONTRACTS.items():
        print(f"{sym} · {chain} · {ca[:10]}…")
        rows = holders(chain, ca)
        if not rows:
            print("   держатели не отдались ни по одному пути")
            continue
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            a = r.get("address") or (r.get("owner") or {}).get("address")
            ent = r.get("arkhamEntity") or r.get("entity") or {}
            nm = (ent.get("name") or r.get("label") or "").strip()
            usd = r.get("usd") or r.get("balanceUSD") or r.get("value")
            if not a or (nm and any(s in nm.lower() for s in SKIP)):
                continue
            out.append({"addr": a, "name": nm or "неизвестный", "usd": usd})
        book[sym] = {"contract": ca, "chain": chain,
                     "addresses": [x["addr"] for x in out[:15]],
                     "holders": out[:15]}
        for h in out[:6]:
            u = h["usd"]
            u = f"${float(u)/1e6:.2f}M" if u else "—"
            print(f"   {h['name'][:28]:30s} {u}")
    Path("investors.json").write_text(
        json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\ninvestors.json обновлён · дальше: python3 arkham_fetch.py --watch")


if __name__ == "__main__":
    if not A.KEY:
        print("нет ключа"); raise SystemExit(1)
    main()
