#!/usr/bin/env python3
"""investors.json по монетам книги (31.08, формат сверен по живому).

Поиск Arkham отдаёт arkhamEntities (сущности) и arkhamAddresses
(их кошельки с сетью). Берём адреса сущности проекта — это команда,
казна, операционные кошельки — и складываем по монетам.

Сторож в arkham_fetch --watch следит: эти адреса отправили токены
НА БИРЖУ. Между переводом и продажей обычно часы — это ранний выход.

Запуск:  python3 arkham_book.py            # BLESS ENA ONG BMT AIO
         python3 arkham_book.py ENA HYPE   # свой список
"""
import json
import sys
import time
from pathlib import Path

import arkham_fetch as A

# Имя монеты → как её зовут в базе Arkham (сверено по выводу поиска)
ALIAS = {"BLESS": "Bless", "ENA": "Ethena", "BMT": "Bubblemaps",
         "AIO": "OlaXBT", "ONG": "Ontology Gas",
         "RIVER": "River Protocol", "AKE": "Akedo"}
SKIP = ("binance", "okx", "bybit", "gate", "kucoin", "mexc", "bitget",
        "htx", "coinbase", "kraken", "upbit", "bithumb", "hyperliquid",
        "wintermute", "bridge", "null", "burn")
BOOK = sys.argv[1:] or ["BLESS", "ENA", "ONG", "BMT", "AIO"]


def entities_and_addresses(query):
    d, c = A.get("/intelligence/search", query=query)
    if c != 200:
        return [], []
    ents = [e for e in (d.get("arkhamEntities") or [])
            if not any(s in (e.get("name") or "").lower() for s in SKIP)]
    addrs = []
    for a in (d.get("arkhamAddresses") or []):
        ent = (a.get("arkhamEntity") or {})
        nm = (ent.get("name") or "").lower()
        if any(s in nm for s in SKIP):
            continue
        if a.get("address"):
            addrs.append({"addr": a["address"],
                          "chain": a.get("chain", ""),
                          "name": ent.get("name") or "неизвестный"})
    return ents, addrs


def main():
    book, report = {}, []
    for sym in BOOK:
        q = ALIAS.get(sym.upper(), sym)
        ents, addrs = entities_and_addresses(q)
        time.sleep(A.PAUSE)
        # добор: если по названию проекта адресов мало — ищем и по тикеру
        if len(addrs) < 3 and q != sym:
            e2, a2 = entities_and_addresses(sym)
            time.sleep(A.PAUSE)
            seen = {x["addr"] for x in addrs}
            addrs += [x for x in a2 if x["addr"] not in seen]
            ents += e2
        book[sym] = {
            "query": q,
            "entities": [{"id": e.get("id"), "name": e.get("name"),
                          "type": e.get("type")} for e in ents[:6]],
            "addresses": [x["addr"] for x in addrs[:15]],
            "holders": addrs[:15]}
        names = ", ".join(sorted({x["name"] for x in addrs[:6]}))
        report.append(f"{sym} ({q}): адресов {len(addrs)}"
                      + (f" · {names}" if names else " · именных нет"))

    Path("investors.json").write_text(
        json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    print("investors.json записан")
    print("\n".join(report))
    print("\nдальше: python3 arkham_fetch.py --watch")


if __name__ == "__main__":
    if not A.KEY:
        print("нет ключа — см. arkham_fetch.py")
        raise SystemExit(1)
    main()
