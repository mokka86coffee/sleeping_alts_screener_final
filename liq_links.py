"""Ссылки на карты ликвидаций Coinglass по монетам журнала.

Карта Model 3 читается только глазами: данные приезжают в браузер
закрытым запросом, а программный доступ к ней у Coinglass открыт с
тарифа Professional (см. sources_coinglass). Пока тарифа нет —
руками, но список пусть собирает прогон, а не человек.

Правило чтения карты, выведенное на первом живом примере (BLESS):
две плиты вокруг цены — верхняя это шорты (топливо вверх), нижняя
это лонги (магнит вниз). Ярче и шире — сильнее. Пустая карта у
спящей монеты не «нет данных», а подтверждение фигуры: плечо ушло
со сломом, наш портрет пустого плеча перед пампом.

    python liq_links.py            # список по журналу
    python liq_links.py --md       # markdown (в письмо/телеграм)
    python liq_links.py PROM BLESS # руками по тикерам
"""

from __future__ import annotations

BASE = "https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3"

# Индексы и синтетика: карты у них нет, показывать ссылку — врать.
SKIP = {"BTCDOM", "DEFI", "USDT", "USDC"}

# Мультипликаторные тикеры Binance к монете Coinglass.
PREFIXES = ("1000000", "10000", "1000")


def coin(symbol: str) -> str:
    """BTCUSDT → BTC, 1000LUNCUSDT → LUNC."""
    s = symbol.upper().strip()
    for tail in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(tail) and len(s) > len(tail):
            s = s[: -len(tail)]
            break
    for pref in PREFIXES:
        if s.startswith(pref) and len(s) > len(pref):
            s = s[len(pref):]
            break
    return s


def link(symbol: str) -> str:
    return f"{BASE}?coin={coin(symbol)}&type=pair"


def links_for(symbols: list[str]) -> list[tuple[str, str]]:
    """Пары (монета, ссылка) без дублей и без индексов."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for sym in symbols:
        c = coin(sym)
        if not c or c in SKIP or c in seen:
            continue
        seen.add(c)
        out.append((c, link(c)))
    return out


# Разделы Coinglass, у которых есть адрес НА МОНЕТУ. Остальные
# (фандинг, накопленный фандинг, комиссии, CME) — глобальные
# таблицы с поиском внутри, монете свой адрес не положен.
SECTIONS = {
    "карта ликвидаций": BASE + "?coin={c}&type=pair",
    "открытый интерес": "https://www.coinglass.com/open-interest/{c}",
}

GLOBAL_PAGES = {
    "фандинг всех монет": "https://www.coinglass.com/FundingRate",
    "накопленный фандинг": "https://www.coinglass.com/AccumulatedFundingRate",
    "тепловая карта фандинга": "https://www.coinglass.com/FundingRateHeatMap",
    "уплаченные комиссии": "https://www.coinglass.com/funding-fees",
    "перп к споту": "https://www.coinglass.com/pro/perpteual-spot-volume",
    "позиции CME и CFTC": "https://www.coinglass.com/pro/cme/cftc",
}


def dossier(symbol: str) -> list[tuple[str, str]]:
    """Все помонетные разделы для одного тикера."""
    c = coin(symbol)
    return [(name, tpl.format(c=c)) for name, tpl in SECTIONS.items()]


def journal_links(markdown: bool = False) -> str:
    try:
        from analytics_leaders import tracked_symbols
        syms = sorted(tracked_symbols())
    except Exception as e:
        return f"журнал не прочитан ({type(e).__name__}) — передайте тикеры аргументами"
    pairs = links_for(syms)
    if not pairs:
        return "журнал пуст"
    if markdown:
        return "\n".join(f"[{c}]({u})" for c, u in pairs)
    return "\n".join(f"{c:<10} {u}" for c, u in pairs)


if __name__ == "__main__":
    import sys
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        for c, u in links_for(args):
            print(f"{c:<10} {u}")
    else:
        print(journal_links(markdown="--md" in sys.argv))
