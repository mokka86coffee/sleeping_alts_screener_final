#!/usr/bin/env python3
"""Пробник CryptoQuant под тариф Advanced (30.08.2026).

Не гадает по докам — ИЗМЕРЯЕТ доступ твоего токена и строит карту
покрытия журнала. Тратит считанные кредиты: по одному-два запроса
на класс данных.

ЗАПУСК (из каталога проекта, рядом с leaders.json):
  1. Токен: cryptoquant.com → профиль → вкладка API → скопировать.
  2. export CQ_TOKEN="..."   (или set CQ_TOKEN=... на Windows)
  3. python3 cryptoquant_probe.py
  4. Прислать мне вывод консоли + файлы cq_catalog.json и
     cq_coverage.json (лягут рядом).

Что делает:
  ШАГ 1. Качает публичный каталог метрик /catalog/catalog.json.
  ШАГ 2. v2 Market: списки бирж и символов → пересечение с
         журналом (65 тикеров) — кто покрыт рыночными данными.
  ШАГ 3. Пробные вызовы по классам (1 точка данных каждый):
         BTC netflow, стейблы netflow, ERC20 inflow (ENA),
         v2 funding (ENA) — по кодам ответов видно, что открыто
         на Advanced: 200 — наш; 401/403 — не наш тариф;
         404 — нет такого актива.
  ШАГ 4. Сводка + файлы.
"""
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

TOKEN = os.environ.get("CQ_TOKEN", "").strip()
BASE_V1 = "https://api.cryptoquant.com/v1"
BASE_V2 = "https://api.cryptoquant.com/v2"
DOCS = "https://docs.cryptoquant.com"

JOURNAL = Path("leaders.json")


def get(url: str, auth: bool = True, timeout: int = 25):
    req = urllib.request.Request(url, headers={
        "User-Agent": "sleeping-alts-probe/1.0",
        **({"Authorization": f"Bearer {TOKEN}"} if auth and TOKEN else {}),
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:  # сеть/таймаут
        return -1, str(e).encode()


def jload(body: bytes):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:
        return None


def main() -> int:
    if not TOKEN:
        print("нет CQ_TOKEN в окружении — см. шапку файла")
        return 1

    journal = []
    if JOURNAL.exists():
        raw = json.loads(JOURNAL.read_text())
        journal = sorted(k[:-4] for k in raw
                         if k != "_meta" and k.endswith("USDT"))
    print(f"журнал: {len(journal)} тикеров")

    # ── ШАГ 1: публичный каталог метрик ──
    st, body = get(f"{DOCS}/catalog/catalog.json", auth=False)
    catalog = jload(body) if st == 200 else None
    if catalog is not None:
        Path("cq_catalog.json").write_bytes(body)
        n = (len(catalog) if isinstance(catalog, list)
             else sum(len(v) if isinstance(v, list) else 1
                      for v in catalog.values()))
        print(f"ШАГ 1 каталог: скачан ({n} записей верхнего уровня) "
              f"→ cq_catalog.json")
    else:
        print(f"ШАГ 1 каталог: не скачался (HTTP {st}) — не беда, "
              f"пробуем API напрямую")

    coverage = {"v2_symbols": {}, "probes": {}}

    # ── ШАГ 2: v2 market — биржи и символы (пути из таблицы
    # docs/guides/plans-and-limits: /v2/market/info/{exchanges,symbols}
    # с обязательными origin, instrument, metric) ──
    st, body = get(f"{BASE_V2}/market/info/exchanges"
                   "?origin=cq&instrument=swap&metric=open-interest")
    print(f"ШАГ 2 v2 биржи: HTTP {st}")
    st, body = get(f"{BASE_V2}/market/info/symbols"
                   "?origin=cq&instrument=swap&metric=open-interest")
    if st == 200:
        try:
            syms = [x if isinstance(x, str) else
                    (x.get("symbol") or x.get("name") or "")
                    for x in (body.get("result") or {}).get("data", body)
                    ] if isinstance(body, dict) else list(body)
        except Exception:
            syms = []
        syms = [str(x).lower() for x in syms if x]
        js = {t.lower() for t in journal}
        inter = sorted({s0 for s0 in syms
                        for t in js if s0.replace("_", "").startswith(t)})
        coverage["v2_symbols"] = {"total": len(syms),
                                  "journal_hits": inter[:80]}
        print(f"ШАГ 2 v2 символов всего: {len(syms)} · "
              f"пересечение с журналом: {len(inter)}")
        print("  " + ", ".join(inter[:40]) if inter else "  пусто")
    else:
        print(f"ШАГ 2 v2 символы: HTTP {st} — "
              f"{json.dumps(body)[:160] if body else ''}")
    # ── ШАГ 3: пробы классов (по одной точке) ──
    probes = [
        ("btc_netflow", f"{BASE_V1}/btc/exchange-flows/netflow"
         "?exchange=all_exchange&window=day&limit=1"),
        ("stable_netflow", f"{BASE_V1}/stablecoin/exchange-flows/netflow"
         "?token=usdt_eth&exchange=all_exchange&window=day&limit=1"),
        ("erc20_inflow_ENA", f"{BASE_V1}/erc20/exchange-flows/inflow"
         "?token=ena&exchange=all_exchange&window=day&limit=1"),
        ("v2_funding_ENA", f"{BASE_V2}/market/cq/swap/funding-rate"
         "?exchange=binance&symbol=ENAUSDT&window=day&limit=1"),
    ]
    verdict = {200: "ОТКРЫТО", 401: "нет доступа (токен?)",
               402: "не в тарифе", 403: "не в тарифе",
               404: "нет актива/эндпоинта", 429: "лимит", -1: "сеть"}
    for name, url in probes:
        st, body = get(url)
        note = verdict.get(st, f"HTTP {st}")
        head = (body[:100].decode("utf-8", "replace")
                if isinstance(body, bytes) else str(body)[:100])
        coverage["probes"][name] = {"status": st, "head": head}
        print(f"ШАГ 3 {name}: {st} · {note}")

    Path("cq_coverage.json").write_text(
        json.dumps(coverage, ensure_ascii=False, indent=1))
    print("сводка → cq_coverage.json · пришли мне вывод и оба файла")
    return 0


if __name__ == "__main__":
    sys.exit(main())
