#!/usr/bin/env python3
"""Пробник держателей Arkham: печатает КОД И ТЕЛО каждого ответа.

arkham_holders.py перебрал пять путей и все промолчали — а почему,
не видно. Здесь то же, но с ответом сервера: 404 «нет пути», 400
«не тот параметр», 403 «не в тарифе» — это три разных дела.

    python3 arkham_probe_holders.py RIVER
"""
import sys
import time

import arkham_fetch as A
from arkham_holders import CONTRACTS

sym = (sys.argv[1] if len(sys.argv) > 1 else "RIVER").upper()
chain, ca = CONTRACTS[sym]
print(f"{sym} · {chain} · {ca}\nключ: …{A.KEY[-4:] if A.KEY else 'НЕТ'}\n")

# сначала — что Arkham вообще знает про этот контракт
for path, prm in (
    (f"/intelligence/address/{ca}", {}),
    (f"/intelligence/address/{ca}", {"chain": chain}),
    (f"/balances/address/{ca}", {}),
    ("/intelligence/search", {"query": ca}),
    ("/intelligence/search", {"query": "River Protocol"}),
):
    d, c = A.get(path, **prm)
    body = str(d)[:220].replace("\n", " ")
    print(f"{c}  {path}  {prm or ''}\n     {body}\n")
    time.sleep(A.PAUSE)

# теперь — пути держателей, с телами
print("── держатели ──")
for path, prm in (
    (f"/token/holders/{chain}/{ca}", {"limit": 10}),
    (f"/token/holders/{ca}", {"limit": 10}),
    (f"/token/top_holders/{chain}/{ca}", {}),
    (f"/token/holders/{chain}:{ca}", {}),
    ("/token/holders", {"chain": chain, "address": ca}),
    (f"/token/{chain}/{ca}/holders", {}),
    (f"/token/top_flow/{ca}", {"timeLast": "7d"}),
    (f"/token/top_flow/{chain}:{ca}", {"timeLast": "7d"}),
):
    d, c = A.get(path, **prm)
    body = str(d)[:220].replace("\n", " ")
    print(f"{c}  {path}  {prm or ''}\n     {body}\n")
    time.sleep(A.PAUSE)
