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

Запуск:  python3 arkham_holders.py          # все контракты
         python3 arkham_holders.py RIVER    # одна монета
Пишет:   investors.json (адреса для сторожа) + печать топа
"""
import json
import time
from pathlib import Path

import arkham_fetch as A

CONTRACTS = {
    "ENA":   ("ethereum", "0x57e114B691Db790C35207b2e685D4A43181e6061"),
    # 03.09 — позиции владельца
    "RIVER": ("bsc",      "0xda7ad9dea9397cffddae2f8a052b82f1484252b3"),  # CoinGecko
    "AKE":   ("bsc",      "0x2c3a8Ee94dDD97244a93Bc48298f97d2C412F7Db"),  # Bitget
    # дописать по мере появления:
    # "BMT":   ("bsc",      "0x..."),
    # "BLESS": ("ethereum", "0x..."),
    # "ONG":   ("ethereum", "0x..."),
}
SKIP = ("binance", "okx", "bybit", "gate", "kucoin", "mexc", "bitget",
        "htx", "coinbase", "kraken", "upbit", "bithumb", "bridge",
        "null", "burn", "lock", "vesting")


PRICING = {}                                   # chain:addr → pricingID


def holders(chain, addr):
    """Перебор возможных путей — печатаем тот, что ответил 200."""
    tries = [
        (f"/token/holders/{chain}/{addr}", {"limit": 25}),      # живой, 03.09
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
        # Пробник 03.09 по RIVER: живой путь /token/holders/{chain}/{addr},
        # ответ в ключе addressTopHolders (ещё есть entityTopHolders —
        # те же держатели, сгруппированные по сущностям). И pricingID
        # в token.identifier — имя монеты для /token/top_flow.
        if isinstance(d.get("token"), dict):
            pid = ((d["token"].get("identifier") or {}).get("pricingID"))
            if pid:
                print(f"   pricingID: {pid} · supply {d.get('totalSupply')}")
                PRICING[chain + ":" + addr.lower()] = pid
        for key in ("addressTopHolders", "entityTopHolders", "holders",
                    "balances", "data", "addresses", "results"):
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
    import sys
    only = {x.upper() for x in sys.argv[1:]}      # python3 arkham_holders.py RIVER
    book = {}
    if Path("investors.json").exists():
        try:
            book = json.loads(Path("investors.json").read_text("utf-8"))
        except Exception:
            book = {}
    for sym, (chain, ca) in CONTRACTS.items():
        if only and sym not in only:
            continue
        print(f"{sym} · {chain} · {ca[:10]}…")
        rows = holders(chain, ca)
        if not rows:
            print("   держатели не отдались ни по одному пути")
            continue
        out = []
        print("   первая строка сырая:", str(rows[0])[:200])
        for r in rows:
            if not isinstance(r, dict):
                continue
            # Живой формат 03.09 (RIVER): address — ВЛОЖЕННЫЙ словарь
            # {address, chain, arkhamLabel{name}, arkhamEntity{name}},
            # рядом balance / usd / pctOfCap. Разбираем оба случая.
            ad = r.get("address")
            info = ad if isinstance(ad, dict) else (r.get("addressInfo") or r)
            a = (ad if isinstance(ad, str) else (info.get("address")
                 or (r.get("owner") or {}).get("address")))
            ent = info.get("arkhamEntity") or r.get("arkhamEntity") or r.get("entity") or {}
            lab = info.get("arkhamLabel") or r.get("arkhamLabel") or {}
            nm = (ent.get("name") or lab.get("name") or r.get("label") or "").strip()
            usd = (r.get("usd") or r.get("balanceUSD") or r.get("value") or 0)
            bal = r.get("balance") or r.get("amount")
            pct = (r.get("pctOfCap") or r.get("pctOfSupply")
                   or r.get("percentOfSupply") or r.get("pct"))
            is_contract = bool(info.get("contract"))
            if not a or (nm and any(s in nm.lower() for s in SKIP)):
                continue
            out.append({"addr": str(a), "name": nm or "неизвестный", "usd": usd,
                        "bal": bal, "pct": pct, "contract": is_contract})
        book[sym] = {"contract": ca, "chain": chain,
                     "addresses": [x["addr"] for x in out[:15]],
                     "holders": out[:15]}
        for h in out[:12]:
            u = h["usd"]
            try:
                u = f"${float(u)/1e6:.2f}M" if u else "—"
            except (TypeError, ValueError):
                u = str(u)[:12]
            try:
                pc = f" · {float(h['pct']):.1f}%" if h.get("pct") is not None else ""
            except (TypeError, ValueError):
                pc = ""
            try:
                b_ = f" · {float(h['bal'])/1e6:.2f}M шт" if h.get("bal") else ""
            except (TypeError, ValueError):
                b_ = ""
            tag = " [контракт]" if h.get("contract") else ""
            print(f"   {h['name'][:26]:28s} {u}{pc}{b_}{tag}   {h['addr'][:12]}…")
    Path("investors.json").write_text(
        json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\ninvestors.json обновлён · дальше: python3 arkham_fetch.py --watch")


if __name__ == "__main__":
    if not A.KEY:
        print("нет ключа"); raise SystemExit(1)
    main()
