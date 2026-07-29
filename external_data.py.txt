"""
external_data.py — интеграция CoinGecko + DefiLlama для fundamental analysis.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)

CACHE_DIR = Path("./cache_fundamental")

# В начале файла, после CACHE_DIR
_MEMORY_CACHE: dict[str, Any] = {}

CACHE_DIR.mkdir(parents=True, exist_ok=True)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
DEFILLAMA_BASE = "https://api.llama.fi"
DEFILLAMA_COINS_BASE = "https://coins.llama.fi"

REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.5  # соблюдаем free-tier rate limit CoinGecko
MAX_RETRIES = 1

# Кэш TTL
COINS_LIST_TTL_HOURS = 24
PROTOCOLS_TTL_HOURS = 24
COIN_DATA_TTL_HOURS = 12


# ============================================================
# DATACLASSES
# ============================================================

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
    # DefiLlama
    tvl_usd: float = 0.0
    tvl_change_1d: float = 0.0
    tvl_change_7d: float = 0.0
    tvl_change_30d: float = 0.0
    defillama_slug: str | None = None
    defillama_category: str = ""

    def has_data(self) -> bool:
        return self.coingecko_id is not None or self.defillama_slug is not None


# ============================================================
# HTTP
# ============================================================

def _http_get_json(url: str, params: dict[str, Any] | None = None) -> Any:
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT,
                                headers={"User-Agent": "sleeping-alts-screener/1.0"})
            if resp.status_code == 429:
                # rate limit — ждём и повторяем
                time.sleep(10)
                continue
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(3 * (attempt + 1))
            else:
                log.debug(f"HTTP failed {url}: {e}")
                return None
    return None


# ============================================================
# КЭШ
# ============================================================

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
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, default=str)
    except Exception as e:
        log.debug(f"Cache write failed {name}: {e}")


# ============================================================
# COINS LIST (SYMBOL → coingecko_id)
# ============================================================

def _load_coins_map() -> dict[str, str]:
    """
    Строит карту SYMBOL → лучший coingecko_id.
    Приоритет: сначала монета с самым высоким market cap rank (проверяется отдельно),
    но здесь просто берём первое вхождение — большинство коллизий редки.
    """
    if "coins" in _MEMORY_CACHE:
        return _MEMORY_CACHE["coins"]

    cached = _cache_read("coins_list.json", COINS_LIST_TTL_HOURS)
    if cached is not None:
        _MEMORY_CACHE["coins"] = cached
        return cached

    log.info("Загружаем список монет CoinGecko...")
    data = _http_get_json(f"{COINGECKO_BASE}/coins/list")
    if not isinstance(data, list):
        return {}

    # Известные "плохие" копии для основных тикеров
    excluded_ids = {
        "wrapped-usdt", "wrapped-usdc", "wrapped-bitcoin", "wrapped-ethereum",
        "binance-peg-bitcoin", "binance-peg-ethereum", "usdc-wormhole",
    }

    coins_map: dict[str, str] = {}
    for item in data:
        sym = str(item.get("symbol", "")).upper()
        cid = str(item.get("id", ""))
        if not sym or not cid or cid in excluded_ids:
            continue
        # Не перезаписываем — берём первую (обычно основная монета идёт раньше форков)
        if sym not in coins_map:
            coins_map[sym] = cid

    _cache_write("coins_list.json", coins_map)
    _MEMORY_CACHE["coins"] = coins_map
    log.info(f"CoinGecko: {len(coins_map)} символов в карте")
    return coins_map


# ============================================================
# DEFILLAMA PROTOCOLS
# ============================================================

def _load_protocols_map() -> dict[str, dict[str, Any]]:
    if "protocols" in _MEMORY_CACHE:
        return _MEMORY_CACHE["protocols"]

    cached = _cache_read("protocols_list.json", PROTOCOLS_TTL_HOURS)
    if cached is not None and len(cached) > 0:
        _MEMORY_CACHE["protocols"] = cached
        return cached

    log.info("Загружаем протоколы DefiLlama...")
    try:
        resp = requests.get(
            "https://api.llama.fi/protocols",
            timeout=120,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
        )
        log.info(f"DefiLlama: HTTP {resp.status_code}, размер {len(resp.content)} байт")
        data = resp.json()
    except Exception as e:
        log.error(f"DefiLlama request failed: {e}")
        _MEMORY_CACHE["protocols"] = {}
        return {}

    log.info(f"DefiLlama raw records: {len(data) if isinstance(data, list) else 'NOT LIST'}")

    # ДИАГНОСТИКА — покажи что реально в первых 3 записях
    if isinstance(data, list) and len(data) > 0:
        for i, item in enumerate(data[:3]):
            log.info(f"  sample[{i}]: name={item.get('name')!r} "
                     f"symbol={item.get('symbol')!r} slug={item.get('slug')!r} "
                     f"tvl={item.get('tvl')} category={item.get('category')!r}")

    protocols_map: dict[str, dict[str, Any]] = {}
    stats = {"no_symbol": 0, "no_slug": 0, "empty_sym": 0, "ok": 0}

    for item in (data if isinstance(data, list) else []):
        if not isinstance(item, dict):
            continue
        sym_raw = item.get("symbol")
        slug = str(item.get("slug", "") or "").strip()

        if sym_raw is None:
            stats["no_symbol"] += 1
            continue
        sym = str(sym_raw).upper().strip()
        if not sym or sym in ("-", "NONE", "NULL"):
            stats["empty_sym"] += 1
            continue
        if not slug:
            stats["no_slug"] += 1
            continue

        tvl = float(item.get("tvl") or 0)
        if sym in protocols_map and protocols_map[sym]["tvl"] >= tvl:
            continue

        protocols_map[sym] = {
            "slug": slug,
            "category": str(item.get("category") or ""),
            "tvl": tvl,
            "change_1d": float(item.get("change_1d") or 0),
            "change_7d": float(item.get("change_7d") or 0),
        }
        stats["ok"] += 1

    log.info(f"DefiLlama parse stats: {stats}")
    log.info(f"DefiLlama: {len(protocols_map)} уникальных символов сохранено")

    _cache_write("protocols_list.json", protocols_map)
    _MEMORY_CACHE["protocols"] = protocols_map
    return protocols_map


# ============================================================
# COINGECKO — детальная информация о монете
# ============================================================

def _fetch_coingecko_detail(coingecko_id: str) -> dict[str, Any] | None:
    cache_name = f"cg_{coingecko_id}.json"
    cached = _cache_read(cache_name, COIN_DATA_TTL_HOURS)
    if cached is not None:
        # пустой словарь = закэшированный промах, не долбим API снова
        return cached or None

    time.sleep(REQUEST_DELAY)
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
    )
    if data is None:
        _cache_write(cache_name, {})   # негативный кэш на COIN_DATA_TTL_HOURS
        return None

    _cache_write(cache_name, data)
    return data


# ============================================================
# ПАБЛИЧНЫЙ API — get_fundamentals(symbol)
# ============================================================

# Известные "форки"/дубли — прямые override
SYMBOL_OVERRIDES: dict[str, str] = {
    # binance-symbol → coingecko-id
    "1000SHIB": "shiba-inu",
    "1000PEPE": "pepe",
    "1000BONK": "bonk",
    "1000FLOKI": "floki",
    "1000SATS": "sats-ordinals",
    "1000RATS": "rats-ordinals",
    "1000CAT": "simon-s-cat",
    "1000CHEEMS": "cheems",
    "1000WHY": "why-do-only-fans-love-me",
    "1000X": "x-empire",
    "1000BEER": "beercoin-2",
    "PEPE": "pepe",
    "SHIB": "shiba-inu",
    "SOL": "solana",
    "ETH": "ethereum",
    "BTC": "bitcoin",
    "ARB": "arbitrum",
    "OP": "optimism",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "ADA": "cardano",
    "TRX": "tron",
    "LINK": "chainlink",
    "XRP": "ripple",
    "TON": "the-open-network",
    "MATIC": "matic-network",
    "POL": "matic-network",
    "S": "sonic-3",
    "SUI": "sui",
    "APT": "aptos",
    "SEI": "sei-network",
    "NEAR": "near",
    "INJ": "injective-protocol",
    "TIA": "celestia",
    "DIA": "dia-data",
    "WIF": "dogwifcoin",
    "BOME": "book-of-meme",
    "BONK": "bonk",
    "FLOKI": "floki",
    "TRUMP": "official-trump",
    "MELANIA": "melania-meme",
    "AAVE": "aave",
    "UNI": "uniswap",
    "CRV": "curve-dao-token",
    "LDO": "lido-dao",
    "MKR": "maker",
    "COMP": "compound-governance-token",
    "SNX": "havven",
    "PENDLE": "pendle",
    "ENA": "ethena",
    "ETHFI": "ether-fi",
    "EIGEN": "eigenlayer",
    "FLUID": "fluid",
    "JUP": "jupiter-exchange-solana",
    "GMX": "gmx",
    "DYDX": "dydx-chain",
    "JTO": "jito-governance-token",
    "AXS": "axie-infinity",
    "SAND": "the-sandbox",
    "MANA": "decentraland",
    "APE": "apecoin",
    "ILV": "illuvium",
    "PYTH": "pyth-network",
    "TRB": "tellor",
    "BAND": "band-protocol",
    "FIL": "filecoin",
    "AR": "arweave",
    "GRT": "the-graph",
    "THETA": "theta-token",
    "HNT": "helium",
    "IOTX": "iotex",
    "ONDO": "ondo-finance",
    "PLUME": "plume",
    "TAO": "bittensor",
    "FET": "fetch-ai",
    "RENDER": "render-token",
    "RNDR": "render-token",
    "WLD": "worldcoin-wld",
    "VIRTUAL": "virtual-protocol",
    "AIXBT": "aixbt",
    "AI16Z": "ai16z",
    "GRASS": "grass",
    "KAITO": "kaito",
    "ICP": "internet-computer",
    "BERA": "berachain-bera",
    "MOVE": "movement",
    "MANTA": "manta-network",
    "STRK": "starknet",
    "TAIKO": "taiko",
    "ZK": "zksync",
    "BLAST": "blast",
    "SCROLL": "scroll-2",
    "EUL": "euler",
    "DEXE": "dexe",
    "SYRUP": "maple",
    "USUAL": "usual",
    "MYX": "myx-finance",
    "HEMI": "hemi",
    "SYN": "synapse-2",
    "BAS": "basedai",
    "TA": "trias-token-new",
    "MMT": "momentum",
    "ZAMA": "zama",
    "EPIC": "epic-cash",
    "TUT": "tutorial",
    "BEAT": "beat-generation",
}


def _base_ticker(symbol: str) -> str:
    s = symbol.upper()
    if s.startswith("1000"):
        # оставим префикс для override
        pass
    for suf in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(suf):
            s = s[: -len(suf)]
            break
    return s


def resolve_coingecko_id(symbol: str) -> str | None:
    ticker = _base_ticker(symbol)
    if ticker in SYMBOL_OVERRIDES:
        return SYMBOL_OVERRIDES[ticker]
    # для 1000-версий — снимаем префикс и пробуем еще
    if ticker.startswith("1000") and ticker[4:] in SYMBOL_OVERRIDES:
        return SYMBOL_OVERRIDES[ticker[4:]]

    coins_map = _load_coins_map()
    # Прямое совпадение
    if ticker in coins_map:
        return coins_map[ticker]
    # Если начинается с 1000 — пробуем без префикса
    if ticker.startswith("1000") and ticker[4:] in coins_map:
        return coins_map[ticker[4:]]
    return None


def get_fundamentals(symbol: str) -> CoinFundamentals:
    ticker = _base_ticker(symbol)
    result = CoinFundamentals(symbol=ticker)

    # 1. CoinGecko
    cg_id = resolve_coingecko_id(symbol)
    if cg_id:
        detail = _fetch_coingecko_detail(cg_id)
        if detail:
            result.coingecko_id = cg_id
            result.name = str(detail.get("name", ""))
            md = detail.get("market_data") or {}
            result.mcap_usd = float((md.get("market_cap") or {}).get("usd") or 0)
            result.mcap_rank = detail.get("market_cap_rank")
            result.fdv_usd = float((md.get("fully_diluted_valuation") or {}).get("usd") or 0)
            result.ath_price_usd = float((md.get("ath") or {}).get("usd") or 0)
            result.ath_change_pct = float((md.get("ath_change_percentage") or {}).get("usd") or 0)
            result.price_change_7d = float(md.get("price_change_percentage_7d") or 0)
            result.price_change_30d = float(md.get("price_change_percentage_30d") or 0)
            result.price_change_1y = float(md.get("price_change_percentage_1y") or 0)

            result.categories = [c for c in (detail.get("categories") or []) if c][:5]
            desc = (detail.get("description") or {}).get("en", "") or ""
            # Обрезаем описание до 250 символов, до первой точки
            if desc:
                desc = desc.replace("\r", " ").replace("\n", " ").strip()
                if len(desc) > 300:
                    dot = desc.find(". ", 150, 350)
                    desc = desc[: dot + 1] if dot > 0 else desc[:300] + "..."
                result.description_short = desc

            cd = detail.get("community_data") or {}
            result.twitter_followers = int(cd.get("twitter_followers") or 0)
            result.telegram_users = int(cd.get("telegram_channel_user_count") or 0)
            result.reddit_subscribers = int(cd.get("reddit_subscribers") or 0)
            result.sentiment_up_pct = float(detail.get("sentiment_votes_up_percentage") or 0)
            result.sentiment_down_pct = float(detail.get("sentiment_votes_down_percentage") or 0)
            result.community_score = float(detail.get("community_score") or 0)
            result.developer_score = float(detail.get("developer_score") or 0)

            links = detail.get("links") or {}
            result.homepage = ((links.get("homepage") or [""])[0]) or ""
            tw = links.get("twitter_screen_name") or ""
            if tw:
                result.twitter_handle = tw

    # 2. DefiLlama
    protocols_map = _load_protocols_map()
    if ticker in protocols_map:
        p = protocols_map[ticker]
        result.defillama_slug = p["slug"]
        result.defillama_category = p["category"]
        result.tvl_usd = float(p["tvl"])
        result.tvl_change_1d = float(p["change_1d"])
        result.tvl_change_7d = float(p["change_7d"])

    return result


# ============================================================
# ГЕНЕРАЦИЯ FUNDAMENTAL TAKE НА ОСНОВЕ ЖИВЫХ ДАННЫХ
# ============================================================

def _fmt_usd(v: float) -> str:
    if v >= 1e9: return f"${v/1e9:.2f}B"
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}"


def _fmt_int(v: int) -> str:
    if v >= 1_000_000: return f"{v/1_000_000:.1f}M"
    if v >= 1_000: return f"{v/1_000:.0f}K"
    return str(v)


def _guess_project_type(f: CoinFundamentals) -> str:
    """По категориям определяет тип проекта простым языком."""
    cats = [c.lower() for c in f.categories]
    dfl = (f.defillama_category or "").lower()

    def has(*keys):
        return any(k in c for c in cats for k in keys) or any(k in dfl for k in keys)

    if has("meme"): return "MEME"
    if has("liquid staking", "liquid restaking"): return "LST/LRT"
    if has("lending", "cdp"): return "DeFi Lending"
    if has("dexes", "dex", "amm"): return "DEX"
    if has("derivatives", "perp"): return "Perp DEX"
    if has("yield"): return "Yield"
    if has("bridge"): return "Bridge"
    if has("real world asset", "rwa"): return "RWA"
    if has("oracle"): return "Oracle"
    if has("layer 1", "layer-1"): return "Layer-1"
    if has("layer 2", "layer-2", "rollup"): return "Layer-2"
    if has("gaming", "gamefi", "nft"): return "Gaming/NFT"
    if has("artificial intelligence", "ai"): return "AI"
    if has("depin"): return "DePIN"
    if has("privacy"): return "Privacy"
    if has("storage"): return "Storage"
    if has("data"): return "Data"
    if f.defillama_slug: return "DeFi Protocol"
    return "Crypto Asset"


def build_fundamental_take_live(f: CoinFundamentals) -> str:
    """
    Генерирует fundamental take на основе живых данных CoinGecko + DefiLlama.
    Если данных нет — возвращает fallback.
    """
    if not f.has_data():
        return (
            f"Данных о {f.symbol} нет в CoinGecko/DefiLlama — вероятно, свежий листинг "
            "или узкоспециальный токен. Требуется ручная проверка команды, whitepaper, "
            "разлочек и структуры держателей перед входом."
        )

    parts: list[str] = []

    # 1. Название + категория
    project_type = _guess_project_type(f)
    name_part = f.name if f.name else f.symbol
    parts.append(f"{name_part} — {project_type}.")

    # 2. Описание (если есть)
    if f.description_short:
        parts.append(f.description_short)

    # 3. Финансовый профиль
    fin_parts = []
    if f.mcap_rank:
        if f.mcap_rank <= 50:
            fin_parts.append(f"Top-{f.mcap_rank} по капитализации ({_fmt_usd(f.mcap_usd)}) — это blue chip")
        elif f.mcap_rank <= 200:
            fin_parts.append(f"Ранг #{f.mcap_rank} ({_fmt_usd(f.mcap_usd)}) — средняя капа")
        elif f.mcap_rank <= 500:
            fin_parts.append(f"Ранг #{f.mcap_rank} ({_fmt_usd(f.mcap_usd)}) — smaller mid-cap")
        else:
            fin_parts.append(f"Ранг #{f.mcap_rank} ({_fmt_usd(f.mcap_usd)}) — микрокап")
    elif f.mcap_usd > 0:
        fin_parts.append(f"Капа {_fmt_usd(f.mcap_usd)}")

    if f.fdv_usd > 0 and f.mcap_usd > 0:
        fdv_ratio = f.fdv_usd / f.mcap_usd
        if fdv_ratio > 3:
            fin_parts.append(
                f"FDV/MCAP = {fdv_ratio:.1f}x — впереди огромные разлочки, "
                "структурное давление на цену"
            )
        elif fdv_ratio > 1.8:
            fin_parts.append(f"FDV/MCAP = {fdv_ratio:.1f}x — заметный overhang от эмиссии")

    if fin_parts:
        parts.append(". ".join(fin_parts) + ".")

    # 4. Ценовая динамика (недавняя)
    if f.price_change_1y != 0 or f.price_change_30d != 0:
        dyn = []
        if abs(f.price_change_1y) > 5:
            if f.price_change_1y > 100:
                dyn.append(f"за год +{f.price_change_1y:.0f}%")
            elif f.price_change_1y > 0:
                dyn.append(f"за год +{f.price_change_1y:.0f}%")
            else:
                dyn.append(f"за год {f.price_change_1y:.0f}%")
        if abs(f.price_change_30d) > 5:
            if f.price_change_30d > 20:
                dyn.append(f"за 30d +{f.price_change_30d:.0f}% (сильный откат от дна)")
            elif f.price_change_30d > 0:
                dyn.append(f"за 30d +{f.price_change_30d:.0f}%")
            else:
                dyn.append(f"за 30d {f.price_change_30d:.0f}%")
        if f.ath_change_pct < -80:
            dyn.append(f"текущая цена -{abs(f.ath_change_pct):.0f}% от ATH")

        if dyn:
            parts.append(f"Динамика: {'; '.join(dyn)}.")

    # 5. TVL (только если DeFi)
    if f.tvl_usd > 0:
        tvl_desc = []
        if f.tvl_usd >= 1e9:
            tvl_desc.append(f"TVL {_fmt_usd(f.tvl_usd)} — крупный DeFi-протокол")
        elif f.tvl_usd >= 100e6:
            tvl_desc.append(f"TVL {_fmt_usd(f.tvl_usd)} — заметная доля рынка")
        elif f.tvl_usd >= 10e6:
            tvl_desc.append(f"TVL {_fmt_usd(f.tvl_usd)} — средний размер")
        else:
            tvl_desc.append(f"TVL {_fmt_usd(f.tvl_usd)} — маленький протокол")

        if f.tvl_change_7d != 0:
            if f.tvl_change_7d > 20:
                tvl_desc.append(f"за неделю +{f.tvl_change_7d:.0f}% (быстрый рост)")
            elif f.tvl_change_7d > 5:
                tvl_desc.append(f"за неделю +{f.tvl_change_7d:.0f}%")
            elif f.tvl_change_7d < -20:
                tvl_desc.append(f"за неделю {f.tvl_change_7d:.0f}% (отток)")
            elif f.tvl_change_7d < -5:
                tvl_desc.append(f"за неделю {f.tvl_change_7d:.0f}%")

        parts.append(", ".join(tvl_desc) + ".")

    # 6. Соцсети
    social = []
    if f.twitter_followers >= 1_000_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)} (mega-influence)")
    elif f.twitter_followers >= 100_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)} (сильная аудитория)")
    elif f.twitter_followers >= 20_000:
        social.append(f"Twitter {_fmt_int(f.twitter_followers)}")
    elif 0 < f.twitter_followers < 5000:
        social.append(f"Twitter всего {_fmt_int(f.twitter_followers)} — низкое внимание")

    if f.telegram_users >= 100_000:
        social.append(f"TG {_fmt_int(f.telegram_users)}")
    if f.reddit_subscribers >= 50_000:
        social.append(f"Reddit {_fmt_int(f.reddit_subscribers)}")

    if social:
        parts.append("Комьюнити: " + ", ".join(social) + ".")

    # 7. Sentiment (голосования на CoinGecko)
    if f.sentiment_up_pct > 0 and (f.sentiment_up_pct + f.sentiment_down_pct) > 0:
        if f.sentiment_up_pct >= 80:
            parts.append(f"Sentiment {f.sentiment_up_pct:.0f}% bullish — толпа настроена очень оптимистично (контр-индикатор).")
        elif f.sentiment_up_pct >= 60:
            parts.append(f"Sentiment {f.sentiment_up_pct:.0f}% bullish.")
        elif f.sentiment_up_pct <= 30:
            parts.append(f"Sentiment {f.sentiment_up_pct:.0f}% bullish — рынок пессимистичен, что часто предшествует развороту.")

    # 8. Итоговая ремарка по типу
    verdicts = {
        "MEME": "Спекуляция чистой воды — играется на новостях и вирусности, фундаментала нет.",
        "LST/LRT": "Сектор с реальным денежным потоком, но токен часто отстаёт от роста TVL.",
        "DeFi Lending": "Слежу за utilization rate и oracle-рисками — здесь бывают black swan events.",
        "DEX": "Смотрю на реальные комиссии и share of volume, не на TVL сам по себе.",
        "Perp DEX": "Прямая конкуренция с Hyperliquid — выживают только с ежедневным volume $100M+.",
        "Yield": "Yield-агрегаторы всегда уязвимы к смене mainstream-стратегии.",
        "Bridge": "Bridge-токены исторически underperform — риск эксплойта высокий.",
        "RWA": "Один из сильнейших долгосрочных нарративов, но короткие движения непредсказуемы.",
        "Oracle": "Утилита есть, но связь с ценой токена слабая — конкуренция с Chainlink давит.",
        "Layer-1": "Ставка на экосистему — если разработчики уходят, токен идёт в ноль.",
        "Layer-2": "Сектор перенасыщен, каждая новая сеть каннибализирует старые.",
        "Gaming/NFT": "Слишком много zombie-проектов — вход только с активными DAU.",
        "AI": "Самый горячий narrative — движения кратные, но и коррекции жестокие. Следить за корреляцией с NVDA.",
        "DePIN": "Тонкий сектор — проверяй реальный uptake, часто цифры маркетинговые.",
        "Privacy": "Держать с оглядкой на регуляторные новости — делистинги главный риск.",
        "Storage": "Утилита стабильная, но токен растёт только на общем ралли.",
        "Data": "Специфический сектор, движения обычно скромные без внешних триггеров.",
        "DeFi Protocol": "Смотрю на реальную выручку протокола, а не только на TVL.",
        "Crypto Asset": "Требуется ручная проверка — что конкретно делает проект и есть ли реальные пользователи.",
    }
    parts.append(verdicts.get(project_type, verdicts["Crypto Asset"]))

    return " ".join(parts)
