"""Интеграция CoinGecko и DefiLlama для фундаментального контекста.

Ключевое отличие от однопоточной версии: запросы к CoinGecko сериализуются
глобальным лимитером. Free tier не переживает шесть параллельных воркеров,
поэтому здесь стоит очередь с минимальным интервалом между вызовами.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from core_config import BASE_DIR

log = logging.getLogger(__name__)

CACHE_DIR = BASE_DIR / "cache" / "fundamental"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFILLAMA_BASE = "https://api.llama.fi"

REQUEST_TIMEOUT = 15
PROTOCOLS_TIMEOUT = 120
MAX_RETRIES = 1

# Минимальный интервал между обращениями к CoinGecko, секунд.
# Free tier допускает порядка 30 запросов в минуту.
COINGECKO_MIN_INTERVAL = 2.2
COINGECKO_PENALTY = 15.0

COINS_LIST_TTL_HOURS = 24
PROTOCOLS_TTL_HOURS = 24
COIN_DATA_TTL_HOURS = 12


# ─────────────────────────────────────────────────────────────
# Лимитер внешних API
# ─────────────────────────────────────────────────────────────
class ExternalLimiter:
    """Сериализует обращения к внешнему API с минимальным интервалом."""

    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def wait(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                if now >= self._next_allowed:
                    self._next_allowed = now + self.min_interval
                    return
                delay = self._next_allowed - now
            time.sleep(min(delay, 5.0))

    def penalize(self, seconds: float) -> None:
        with self._lock:
            target = time.monotonic() + seconds
            if target > self._next_allowed:
                self._next_allowed = target


CG_LIMITER = ExternalLimiter(COINGECKO_MIN_INTERVAL)

_MEMORY_CACHE: dict[str, Any] = {}
_MEMORY_LOCK = threading.Lock()

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": "sleeping-alts-screener/3.0",
    "Accept": "application/json",
})


# ─────────────────────────────────────────────────────────────
# Модель
# ─────────────────────────────────────────────────────────────
@dataclass
class CoinFundamentals:
    symbol: str
    coingecko_id: str | None = None
    name: str = ""

    mcap_usd: float = 0.0
    mcap_rank: int | None = None
    fdv_usd: float = 0.0

    categories: list[str] = field(default_factory=list)
    description_short: str = ""

    ath_price_usd: float = 0.0
    ath_change_pct: float = 0.0
    price_change_7d: float = 0.0
    price_change_30d: float = 0.0
    price_change_1y: float = 0.0

    twitter_followers: int = 0
    telegram_users: int = 0
    reddit_subscribers: int = 0
    community_score: float = 0.0
    developer_score: float = 0.0
    sentiment_up_pct: float = 0.0
    sentiment_down_pct: float = 0.0

    homepage: str = ""
    twitter_handle: str = ""

    tvl_usd: float = 0.0
    tvl_change_1d: float = 0.0
    tvl_change_7d: float = 0.0
    tvl_change_30d: float = 0.0
    defillama_slug: str | None = None
    defillama_category: str = ""

    def has_data(self) -> bool:
        return self.coingecko_id is not None or self.defillama_slug is not None


# ─────────────────────────────────────────────────────────────
# HTTP и кэш
# ─────────────────────────────────────────────────────────────
def _http_get_json(url: str, params: dict | None = None, limiter: ExternalLimiter | None = None) -> Any:
    for attempt in range(MAX_RETRIES + 1):
        if limiter:
            limiter.wait()
        try:
            resp = _SESSION.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 429:
                if limiter:
                    limiter.penalize(COINGECKO_PENALTY)
                else:
                    time.sleep(10)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(3 * (attempt + 1))
            else:
                log.debug(f"Запрос не удался {url}: {e}")
    return None


def _cache_read(name: str, ttl_hours: float) -> Any | None:
    path = CACHE_DIR / name
    if not path.exists():
        return None
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    if age > timedelta(hours=ttl_hours):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _cache_write(name: str, data: Any) -> None:
    path = CACHE_DIR / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        tmp.replace(path)
    except Exception as e:
        log.debug(f"Не удалось записать кэш {name}: {e}")


# ─────────────────────────────────────────────────────────────
# Карта символов CoinGecko
# ─────────────────────────────────────────────────────────────
EXCLUDED_CG_IDS = {
    "wrapped-usdt", "wrapped-usdc", "wrapped-bitcoin", "wrapped-ethereum",
    "binance-peg-bitcoin", "binance-peg-ethereum", "usdc-wormhole",
}


def _load_coins_map() -> dict[str, str]:
    """Карта тикер → coingecko id.

    Список не отсортирован по капитализации, поэтому при коллизии берётся
    первое вхождение. Для значимых монет это лечится списком SYMBOL_OVERRIDES,
    который имеет приоритет над картой.
    """
    with _MEMORY_LOCK:
        if "coins" in _MEMORY_CACHE:
            return _MEMORY_CACHE["coins"]

        cached = _cache_read("coins_list.json", COINS_LIST_TTL_HOURS)
        if cached is not None:
            _MEMORY_CACHE["coins"] = cached
            return cached

        log.info("Загружаю список монет CoinGecko")
        data = _http_get_json(f"{COINGECKO_BASE}/coins/list", limiter=CG_LIMITER)
        if not isinstance(data, list):
            _MEMORY_CACHE["coins"] = {}
            return {}

        coins_map: dict[str, str] = {}
        for item in data:
            sym = str(item.get("symbol", "")).upper()
            cid = str(item.get("id", ""))
            if not sym or not cid or cid in EXCLUDED_CG_IDS:
                continue
            if sym not in coins_map:
                coins_map[sym] = cid

        _cache_write("coins_list.json", coins_map)
        _MEMORY_CACHE["coins"] = coins_map
        log.info(f"CoinGecko: {len(coins_map)} символов в карте")
        return coins_map


# ─────────────────────────────────────────────────────────────
# Протоколы DefiLlama
# ─────────────────────────────────────────────────────────────
def _load_protocols_map() -> dict[str, dict]:
    with _MEMORY_LOCK:
        if "protocols" in _MEMORY_CACHE:
            return _MEMORY_CACHE["protocols"]

        cached = _cache_read("protocols_list.json", PROTOCOLS_TTL_HOURS)
        if cached:
            _MEMORY_CACHE["protocols"] = cached
            return cached

        log.info("Загружаю протоколы DefiLlama")
        try:
            resp = _SESSION.get(f"{DEFILLAMA_BASE}/protocols", timeout=PROTOCOLS_TIMEOUT)
            data = resp.json()
        except Exception as e:
            log.warning(f"DefiLlama недоступен: {e}")
            _MEMORY_CACHE["protocols"] = {}
            return {}

        protocols_map: dict[str, dict] = {}
        for item in (data if isinstance(data, list) else []):
            if not isinstance(item, dict):
                continue
            sym_raw = item.get("symbol")
            slug = str(item.get("slug", "") or "").strip()
            if sym_raw is None or not slug:
                continue
            sym = str(sym_raw).upper().strip()
            if not sym or sym in ("-", "NONE", "NULL"):
                continue

            try:
                tvl = float(item.get("tvl") or 0)
            except (TypeError, ValueError):
                tvl = 0.0

            # При коллизии символов побеждает протокол с большим TVL
            if sym in protocols_map and protocols_map[sym]["tvl"] >= tvl:
                continue

            def _f(key: str) -> float:
                try:
                    return float(item.get(key) or 0)
                except (TypeError, ValueError):
                    return 0.0

            protocols_map[sym] = {
                "slug": slug,
                "category": str(item.get("category") or ""),
                "tvl": tvl,
                "change_1d": _f("change_1d"),
                "change_7d": _f("change_7d"),
            }

        _cache_write("protocols_list.json", protocols_map)
        _MEMORY_CACHE["protocols"] = protocols_map
        log.info(f"DefiLlama: {len(protocols_map)} символов")
        return protocols_map


# ─────────────────────────────────────────────────────────────
# Соответствие тикеров
# ─────────────────────────────────────────────────────────────
SYMBOL_OVERRIDES: dict[str, str] = {
    "1000SHIB": "shiba-inu", "1000PEPE": "pepe", "1000BONK": "bonk",
    "1000FLOKI": "floki", "1000SATS": "sats-ordinals", "1000RATS": "rats-ordinals",
    "1000CAT": "simon-s-cat", "1000CHEEMS": "cheems",
    "1000WHY": "why-do-only-fans-love-me", "1000X": "x-empire",
    "1000BEER": "beercoin-2",

    "PEPE": "pepe", "SHIB": "shiba-inu", "SOL": "solana", "ETH": "ethereum",
    "BTC": "bitcoin", "ARB": "arbitrum", "OP": "optimism", "DOGE": "dogecoin",
    "AVAX": "avalanche-2", "ADA": "cardano", "TRX": "tron", "LINK": "chainlink",
    "XRP": "ripple", "TON": "the-open-network", "MATIC": "matic-network",
    "POL": "matic-network", "S": "sonic-3", "SUI": "sui", "APT": "aptos",
    "SEI": "sei-network", "NEAR": "near", "INJ": "injective-protocol",
    "TIA": "celestia", "DIA": "dia-data",

    "WIF": "dogwifcoin", "BOME": "book-of-meme", "BONK": "bonk", "FLOKI": "floki",
    "TRUMP": "official-trump", "MELANIA": "melania-meme",

    "AAVE": "aave", "UNI": "uniswap", "CRV": "curve-dao-token", "LDO": "lido-dao",
    "MKR": "maker", "COMP": "compound-governance-token", "SNX": "havven",
    "PENDLE": "pendle", "ENA": "ethena", "ETHFI": "ether-fi",
    "EIGEN": "eigenlayer", "FLUID": "fluid",
    "JUP": "jupiter-exchange-solana", "GMX": "gmx", "DYDX": "dydx-chain",
    "JTO": "jito-governance-token",

    "AXS": "axie-infinity", "SAND": "the-sandbox", "MANA": "decentraland",
    "APE": "apecoin", "ILV": "illuvium",

    "PYTH": "pyth-network", "TRB": "tellor", "BAND": "band-protocol",
    "FIL": "filecoin", "AR": "arweave", "GRT": "the-graph",
    "THETA": "theta-token", "HNT": "helium", "IOTX": "iotex",

    "ONDO": "ondo-finance", "PLUME": "plume",

    "TAO": "bittensor", "FET": "fetch-ai", "RENDER": "render-token",
    "RNDR": "render-token", "WLD": "worldcoin-wld", "VIRTUAL": "virtual-protocol",
    "AIXBT": "aixbt", "AI16Z": "ai16z", "GRASS": "grass", "KAITO": "kaito",

    "ICP": "internet-computer", "BERA": "berachain-bera", "MOVE": "movement",
    "MANTA": "manta-network", "STRK": "starknet", "TAIKO": "taiko",
    "ZK": "zksync", "BLAST": "blast", "SCROLL": "scroll-2", "EUL": "euler",

    "DEXE": "dexe", "SYRUP": "maple", "USUAL": "usual", "MYX": "myx-finance",
    "HEMI": "hemi", "SYN": "synapse-2", "BAS": "basedai",
    "TA": "trias-token-new", "MMT": "momentum", "ZAMA": "zama",
    "EPIC": "epic-cash", "TUT": "tutorial", "BEAT": "beat-generation",
}


def base_ticker(symbol: str) -> str:
    """Убирает котируемую валюту из тикера, префикс 1000 сохраняется."""
    s = symbol.upper()
    for suffix in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(suffix):
            return s[:-len(suffix)]
    return s


def resolve_coingecko_id(symbol: str) -> str | None:
    ticker = base_ticker(symbol)

    if ticker in SYMBOL_OVERRIDES:
        return SYMBOL_OVERRIDES[ticker]
    if ticker.startswith("1000") and ticker[4:] in SYMBOL_OVERRIDES:
        return SYMBOL_OVERRIDES[ticker[4:]]

    coins_map = _load_coins_map()
    if ticker in coins_map:
        return coins_map[ticker]
    if ticker.startswith("1000") and ticker[4:] in coins_map:
        return coins_map[ticker[4:]]
    return None


# ─────────────────────────────────────────────────────────────
# Детали монеты
# ─────────────────────────────────────────────────────────────
def _fetch_coingecko_detail(coingecko_id: str, deep: bool = True) -> dict | None:
    cache_name = f"cg_{coingecko_id}.json"
    cached = _cache_read(cache_name, COIN_DATA_TTL_HOURS)
    if cached is not None:
        # Пустой словарь — закэшированный промах, повторно не запрашиваем
        return cached or None

    # Монета не дошла до отбора: сетевой запрос не окупается.
    # Если данные появятся в кэше позже — подхватим на следующем прогоне.
    if not deep:
        return None

    data = _http_get_json(
        f"{COINGECKO_BASE}/coins/{coingecko_id}",
        params={
            "localization": "false",
            "tickers": "false",
            "market_data": "true",
            "community_data": "true",
            "developer_data": "true",
            "sparkline": "false",
        },
        limiter=CG_LIMITER,
    )

    if data is None:
        _cache_write(cache_name, {})
        return None

    _cache_write(cache_name, data)
    return data


def _shorten_description(desc: str) -> str:
    if not desc:
        return ""
    desc = desc.replace("\r", " ").replace("\n", " ").strip()
    if len(desc) <= 300:
        return desc
    dot = desc.find(". ", 150, 350)
    return desc[:dot + 1] if dot > 0 else desc[:300] + "…"


def get_fundamentals(symbol: str, deep: bool = True) -> CoinFundamentals:
    """Фундаментальный профиль монеты из CoinGecko и DefiLlama.

    При deep=False обращение к CoinGecko за деталями не делается: берётся
    только дисковый кэш и DefiLlama. Это экономит секунды на монетах,
    которые всё равно не попадут в отчёт.
    """

    ticker = base_ticker(symbol)
    result = CoinFundamentals(symbol=ticker)

    def _f(v: Any) -> float:
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0

    def _i(v: Any) -> int:
        try:
            return int(v or 0)
        except (TypeError, ValueError):
            return 0

    # ── CoinGecko ──
    cg_id = resolve_coingecko_id(symbol)
    if cg_id:
        detail = _fetch_coingecko_detail(cg_id, deep=deep)
        if detail:
            result.coingecko_id = cg_id
            result.name = str(detail.get("name", ""))

            md = detail.get("market_data") or {}
            result.mcap_usd = _f((md.get("market_cap") or {}).get("usd"))
            result.mcap_rank = detail.get("market_cap_rank")
            result.fdv_usd = _f((md.get("fully_diluted_valuation") or {}).get("usd"))
            result.ath_price_usd = _f((md.get("ath") or {}).get("usd"))
            result.ath_change_pct = _f((md.get("ath_change_percentage") or {}).get("usd"))
            result.price_change_7d = _f(md.get("price_change_percentage_7d"))
            result.price_change_30d = _f(md.get("price_change_percentage_30d"))
            result.price_change_1y = _f(md.get("price_change_percentage_1y"))

            result.categories = [c for c in (detail.get("categories") or []) if c][:5]
            result.description_short = _shorten_description(
                (detail.get("description") or {}).get("en", "") or ""
            )

            cd = detail.get("community_data") or {}
            result.twitter_followers = _i(cd.get("twitter_followers"))
            result.telegram_users = _i(cd.get("telegram_channel_user_count"))
            result.reddit_subscribers = _i(cd.get("reddit_subscribers"))
            result.sentiment_up_pct = _f(detail.get("sentiment_votes_up_percentage"))
            result.sentiment_down_pct = _f(detail.get("sentiment_votes_down_percentage"))
            result.community_score = _f(detail.get("community_score"))
            result.developer_score = _f(detail.get("developer_score"))

            links = detail.get("links") or {}
            homepages = links.get("homepage") or [""]
            result.homepage = homepages[0] if homepages else ""
            result.twitter_handle = links.get("twitter_screen_name") or ""

    # ── DefiLlama ──
    protocols_map = _load_protocols_map()
    if ticker in protocols_map:
        p = protocols_map[ticker]
        result.defillama_slug = p["slug"]
        result.defillama_category = p["category"]
        result.tvl_usd = p["tvl"]
        result.tvl_change_1d = p["change_1d"]
        result.tvl_change_7d = p["change_7d"]

    return result


# ─────────────────────────────────────────────────────────────
# Текстовая интерпретация
# ─────────────────────────────────────────────────────────────
def _fmt_usd(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.2f}B"
    if v >= 1e6:
        return f"${v/1e6:.1f}M"
    if v >= 1e3:
        return f"${v/1e3:.0f}K"
    return f"${v:.0f}"


def _fmt_int(v: int) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)


def guess_project_type(f: CoinFundamentals) -> str:
    """Определяет тип проекта по категориям."""
    cats = [c.lower() for c in f.categories]
    dfl = (f.defillama_category or "").lower()

    def has(*keys: str) -> bool:
        return (
            any(k in c for c in cats for k in keys)
            or any(k in dfl for k in keys)
        )

    if has("meme"):
        return "MEME"
    if has("liquid staking", "liquid restaking"):
        return "LST/LRT"
    if has("lending", "cdp"):
        return "DeFi Lending"
    if has("dexes", "dex", "amm"):
        return "DEX"
    if has("derivatives", "perp"):
        return "Perp DEX"
    if has("yield"):
        return "Yield"
    if has("bridge"):
        return "Bridge"
    if has("real world asset", "rwa"):
        return "RWA"
    if has("oracle"):
        return "Oracle"
    if has("layer 1", "layer-1"):
        return "Layer-1"
    if has("layer 2", "layer-2", "rollup"):
        return "Layer-2"
    if has("gaming", "gamefi", "nft"):
        return "Gaming/NFT"
    if has("artificial intelligence", "ai"):
        return "AI"
    if has("depin"):
        return "DePIN"
    if has("privacy"):
        return "Privacy"
    if has("storage"):
        return "Storage"
    if has("data"):
        return "Data"
    if f.defillama_slug:
        return "DeFi Protocol"
    return "Crypto Asset"


SECTOR_VERDICTS = {
    "MEME": "Чистая спекуляция: играется на новостях и вирусности, фундамента нет.",
    "LST/LRT": "Сектор с реальным денежным потоком, но токен часто отстаёт от роста TVL.",
    "DeFi Lending": "Смотреть на utilization rate и риски оракула, здесь случаются чёрные лебеди.",
    "DEX": "Оценивать по реальным комиссиям и доле объёма, а не по TVL самому по себе.",
    "Perp DEX": "Прямая конкуренция с Hyperliquid, выживают только с оборотом от $100M в день.",
    "Yield": "Агрегаторы доходности уязвимы к смене доминирующей стратегии.",
    "Bridge": "Мостовые токены исторически отстают, риск эксплойта высокий.",
    "RWA": "Один из сильнейших долгосрочных нарративов, но короткие движения непредсказуемы.",
    "Oracle": "Утилита есть, связь с ценой токена слабая, конкуренция с Chainlink давит.",
    "Layer-1": "Ставка на экосистему: если разработчики уходят, токен идёт в ноль.",
    "Layer-2": "Сектор перенасыщен, каждая новая сеть каннибализирует предыдущие.",
    "Gaming/NFT": "Много мёртвых проектов, вход только при активной аудитории.",
    "AI": "Самый горячий нарратив: движения кратные, коррекции жестокие.",
    "DePIN": "Тонкий сектор, проверять реальное использование, цифры часто маркетинговые.",
    "Privacy": "Держать с оглядкой на регуляторные новости, делистинг — главный риск.",
    "Storage": "Утилита стабильная, токен растёт в основном на общем ралли.",
    "Data": "Специфический сектор, без внешних триггеров движения скромные.",
    "DeFi Protocol": "Смотреть на реальную выручку протокола, а не только на TVL.",
    "Crypto Asset": "Нужна ручная проверка: что делает проект и есть ли реальные пользователи.",
}


def build_fundamental_take_live(f: CoinFundamentals) -> str:
    """Связный текст о проекте на основе живых данных."""
    if not f.has_data():
        return (
            f"Данных о {f.symbol} нет ни в CoinGecko, ни в DefiLlama — вероятно, "
            "свежий листинг или узкоспециальный токен. Перед входом нужна ручная "
            "проверка команды, документации, графика разлоков и структуры держателей."
        )

    parts: list[str] = []
    project_type = guess_project_type(f)
    name_part = f.name if f.name else f.symbol
    parts.append(f"{name_part} — {project_type}.")

    if f.description_short:
        parts.append(f.description_short)

    # ── Финансовый профиль ──
    fin: list[str] = []
    if f.mcap_rank:
        cap = _fmt_usd(f.mcap_usd)
        if f.mcap_rank <= 50:
            fin.append(f"Топ-{f.mcap_rank} по капитализации, {cap}, это голубая фишка")
        elif f.mcap_rank <= 200:
            fin.append(f"Ранг {f.mcap_rank}, {cap}, средняя капитализация")
        elif f.mcap_rank <= 500:
            fin.append(f"Ранг {f.mcap_rank}, {cap}, малая капитализация")
        else:
            fin.append(f"Ранг {f.mcap_rank}, {cap}, микрокап")
    elif f.mcap_usd > 0:
        fin.append(f"Капитализация {_fmt_usd(f.mcap_usd)}")

    if f.fdv_usd > 0 and f.mcap_usd > 0:
        ratio = f.fdv_usd / f.mcap_usd
        if ratio > 3:
            fin.append(
                f"FDV к капитализации {ratio:.1f}×, впереди крупные разлоки "
                "и структурное давление на цену"
            )
        elif ratio > 1.8:
            fin.append(f"FDV к капитализации {ratio:.1f}×, заметный навес эмиссии")

    if fin:
        parts.append(". ".join(fin) + ".")

    # ── Динамика ──
    dyn: list[str] = []
    if abs(f.price_change_1y) > 5:
        dyn.append(f"за год {f.price_change_1y:+.0f}%")
    if abs(f.price_change_30d) > 5:
        if f.price_change_30d > 20:
            dyn.append(f"за 30 дней {f.price_change_30d:+.0f}%, сильный откат от дна")
        else:
            dyn.append(f"за 30 дней {f.price_change_30d:+.0f}%")
    if f.ath_change_pct < -80:
        dyn.append(f"цена ниже исторического максимума на {abs(f.ath_change_pct):.0f}%")
    if dyn:
        parts.append("Динамика: " + "; ".join(dyn) + ".")

    # ── TVL ──
    if f.tvl_usd > 0:
        tvl: list[str] = []
        if f.tvl_usd >= 1e9:
            tvl.append(f"TVL {_fmt_usd(f.tvl_usd)}, крупный протокол")
        elif f.tvl_usd >= 100e6:
            tvl.append(f"TVL {_fmt_usd(f.tvl_usd)}, заметная доля рынка")
        elif f.tvl_usd >= 10e6:
            tvl.append(f"TVL {_fmt_usd(f.tvl_usd)}, средний размер")
        else:
            tvl.append(f"TVL {_fmt_usd(f.tvl_usd)}, маленький протокол")

        if f.tvl_change_7d > 20:
            tvl.append(f"за неделю {f.tvl_change_7d:+.0f}%, быстрый приток")
        elif f.tvl_change_7d < -20:
            tvl.append(f"за неделю {f.tvl_change_7d:+.0f}%, отток средств")
        elif abs(f.tvl_change_7d) > 5:
            tvl.append(f"за неделю {f.tvl_change_7d:+.0f}%")

        parts.append(", ".join(tvl) + ".")

    # ── Комьюнити ──
    social: list[str] = []
    if f.twitter_followers >= 1_000_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)}, огромный охват")
    elif f.twitter_followers >= 100_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)}, сильная аудитория")
    elif f.twitter_followers >= 20_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)}")
    elif 0 < f.twitter_followers < 5000:
        social.append(f"Twitter всего {_fmt_int(f.twitter_followers)}, внимания мало")

    if f.telegram_users >= 100_000:
        social.append(f"Telegram {_fmt_int(f.telegram_users)}")
    if f.reddit_subscribers >= 50_000:
        social.append(f"Reddit {_fmt_int(f.reddit_subscribers)}")
    if social:
        parts.append("Комьюнити: " + ", ".join(social) + ".")

    # ── Настроение ──
    total_votes = f.sentiment_up_pct + f.sentiment_down_pct
    if f.sentiment_up_pct > 0 and total_votes > 0:
        if f.sentiment_up_pct >= 80:
            parts.append(
                f"Настроение {f.sentiment_up_pct:.0f}% бычье — толпа предельно "
                "оптимистична, что работает как контриндикатор."
            )
        elif f.sentiment_up_pct <= 30:
            parts.append(
                f"Настроение {f.sentiment_up_pct:.0f}% бычье — рынок пессимистичен, "
                "такое часто предшествует развороту."
            )
        elif f.sentiment_up_pct >= 60:
            parts.append(f"Настроение {f.sentiment_up_pct:.0f}% бычье.")

    parts.append(SECTOR_VERDICTS.get(project_type, SECTOR_VERDICTS["Crypto Asset"]))
    return " ".join(parts)
