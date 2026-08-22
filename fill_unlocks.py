"""Заполнение постоянных полей unlocks.json по журналу лидеров.

Запуск (нужна сеть):
    python fill_unlocks.py                 # покажет и запишет
    python fill_unlocks.py --dry           # только показать

Что заполняет и почему именно это. В unlocks.json две породы данных:
ПОСТОЯННЫЕ величины монеты (доля обращения, отношение FDV к
капитализации, вершина и дно всей жизни) и СОБЫТИЯ — даты и объёмы
траншей. Первые меняются каждый день и обязаны обновляться машиной;
вторые приходят из документов проекта и остаются ручными.

Почему разлоки остаются руками (проверено 22.08). Секция Unlocks на
карточке токена DeFiLlama закрыта подпиской, эндпоинты emissions в
API — тоже (Pro, $300/мес). Бесплатная страница defillama.com/unlocks
показывает только ближайшие дни по всему рынку и наших монет обычно
не содержит. Значит: даты вносим сами, когда монета там появляется,
а числа, которые считаются из supply, берём отсюда.

Источник постоянных величин — открытый рынковый эндпоинт CoinGecko
(без ключа): circulating/total/max supply, market cap, FDV, ATH и ATL
с датами. Один запрос на все 43 монеты.

СЛИЯНИЕ, а не перезапись. Скрипт трогает только те ключи, которые
считает сам, и НИКОГДА не касается events: ручная работа не должна
пропадать от запуска автомата. Записи монет, которых нет в журнале,
остаются в файле нетронутыми.

Ограничение сопоставления. Тикеры не уникальны: на CoinGecko под
символом ACE живёт несколько токенов. Выбирается запись с наибольшей
капитализацией среди совпавших, и в поле source остаётся её
идентификатор — чтобы ошибку сопоставления можно было увидеть
глазами, а не подозревать. Монеты, где совпадений нет, печатаются
списком: их заполняем руками или не заполняем вовсе.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CG_LIST = "https://api.coingecko.com/api/v3/coins/list"
CG_MARKETS = ("https://api.coingecko.com/api/v3/coins/markets"
              "?vs_currency=usd&per_page=250&sparkline=false&ids=")

# Множительные префиксы Binance: 1000CAT торгуется тысячами, токен
# называется CAT. Тот же список, что в fundamental_revenue.py.
MULT_PREFIXES = ("1000000", "10000", "1000")

# Ключи, которые считает ЭТОТ скрипт. Всё остальное в записи — чужое
# и переживает запуск без изменений. Список явный, а не «всё, кроме
# events»: так добавление нового ручного поля не потребует правки
# слияния.
OWNED_KEYS = ("circ_pct", "fdv_ratio", "ath_usd", "ath_date",
              "atl_usd", "atl_date", "source", "checked_at")


def _get(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "screener/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def base_ticker(symbol: str) -> str:
    t = symbol.upper().removesuffix("USDT")
    for p in MULT_PREFIXES:
        if t.startswith(p) and len(t) > len(p):
            return t[len(p):]
    return t


def main() -> int:
    ap = argparse.ArgumentParser(description="Постоянные поля unlocks.json")
    ap.add_argument("--leaders", default="output/leaders.json")
    ap.add_argument("--out", default="unlocks.json")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    lead_path = Path(a.leaders)
    if not lead_path.is_file():
        print(f"✗ журнала {lead_path} нет")
        return 1
    symbols = [k for k in json.loads(lead_path.read_text(encoding="utf-8"))
               if not k.startswith("_")]
    want = {base_ticker(s): s for s in symbols}
    print(f"→ монет в журнале: {len(symbols)}")

    try:
        listing = _get(CG_LIST)
    except Exception as exc:
        print(f"✗ список монет недоступен: {type(exc).__name__}: {exc}")
        return 1

    ids_by_ticker: dict[str, list[str]] = {}
    for row in listing if isinstance(listing, list) else []:
        sym = str(row.get("symbol") or "").upper()
        if sym in want:
            ids_by_ticker.setdefault(sym, []).append(str(row.get("id")))
    all_ids = [i for ids in ids_by_ticker.values() for i in ids]
    print(f"→ кандидатов на сопоставление: {len(all_ids)} "
          f"по {len(ids_by_ticker)} тикерам")

    rows: list[dict] = []
    for i in range(0, len(all_ids), 250):
        chunk = urllib.parse.quote(",".join(all_ids[i:i + 250]))
        try:
            rows += _get(CG_MARKETS + chunk) or []
        except Exception as exc:
            print(f"⚠ пачка {i // 250 + 1} не пришла: {type(exc).__name__}")

    # Тикер → запись с наибольшей капитализацией среди совпавших.
    best: dict[str, dict] = {}
    for r in rows:
        sym = str(r.get("symbol") or "").upper()
        if sym not in want:
            continue
        cap = float(r.get("market_cap") or 0.0)
        if cap >= float((best.get(sym) or {}).get("market_cap") or -1):
            best[sym] = r

    out_path = Path(a.out)
    try:
        data = json.loads(out_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    before = len(data)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filled, missing = [], []
    for ticker, symbol in sorted(want.items()):
        r = best.get(ticker)
        if not r:
            missing.append(ticker)
            continue
        circ = float(r.get("circulating_supply") or 0.0)
        total = float(r.get("max_supply") or r.get("total_supply") or 0.0)
        mcap = float(r.get("market_cap") or 0.0)
        fdv = float(r.get("fully_diluted_valuation") or 0.0)

        rec = dict(data.get(symbol) or {})     # ручное сохраняется
        if circ > 0 and total > 0:
            rec["circ_pct"] = round(circ / total * 100, 1)
        if mcap > 0 and fdv > 0:
            rec["fdv_ratio"] = round(fdv / mcap, 2)
        if r.get("ath") is not None:
            rec["ath_usd"] = float(r["ath"])
            rec["ath_date"] = str(r.get("ath_date") or "")[:10]
        if r.get("atl") is not None:
            rec["atl_usd"] = float(r["atl"])
            rec["atl_date"] = str(r.get("atl_date") or "")[:10]
        rec["source"] = f"coingecko:{r.get('id')}"
        rec["checked_at"] = now
        data[symbol] = rec
        filled.append((symbol, rec))

    filled.sort(key=lambda p: p[1].get("circ_pct") or 999)
    hdr = f"{'монета':<12}{'флоат':>8}{'FDV/MC':>8}{'ATH':>12}{'дата ATH':>12}"
    print("\n" + hdr)
    print("─" * len(hdr))
    for symbol, rec in filled:
        fl = rec.get("circ_pct")
        fr = rec.get("fdv_ratio")
        print(f"{symbol.replace('USDT',''):<12}"
              f"{(f'{fl:.1f}%' if fl is not None else '—'):>8}"
              f"{(f'×{fr:.1f}' if fr is not None else '—'):>8}"
              f"{(f'${rec["ath_usd"]:.4g}' if rec.get('ath_usd') else '—'):>12}"
              f"{rec.get('ath_date', '—'):>12}")
    if missing:
        print(f"\nне сопоставлены ({len(missing)}): {', '.join(sorted(missing))}")
        print("  — заполнять руками или оставить пустыми: пробел честнее догадки")

    if a.dry:
        print("\n(--dry: файл не тронут)")
        return 0
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"\n✓ {out_path}: было записей {before}, стало {len(data)}; "
          f"обновлено {len(filled)}, events не тронуты")
    return 0


if __name__ == "__main__":
    sys.exit(main())
