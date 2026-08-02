"""Единая точка конфигурации проекта.

Все пороги, лимиты и списки исключений живут здесь. Ни один другой модуль
не должен содержать магических чисел — только импорт отсюда.
"""

from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────────
# Пути
# ─────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
RUNS_DIR = OUTPUT_DIR / "runs"
REPORT_PATH = BASE_DIR / "index.html"
LATEST_JSON = OUTPUT_DIR / "latest.json"

RUNS_KEEP = 60

# ─────────────────────────────────────────────────────────────
# Планировщик
# ─────────────────────────────────────────────────────────────

LOOP_INTERVAL_SEC = 3 * 60 * 60      # 3 часа
GIT_TIMEOUT_SEC = 120
COMMIT_MSG = "new"
GIT_ADD_ALL_CHANGED = "."
GIT_ADD_HTML_ONLY = "index.html"

# ─────────────────────────────────────────────────────────────
# Эндпоинты
# ─────────────────────────────────────────────────────────────
BINANCE_FAPI = "https://fapi.binance.com"
BINANCE_SPOT = "https://api.binance.com"

# ─────────────────────────────────────────────────────────────
# HTTP
# ─────────────────────────────────────────────────────────────
REQUEST_TIMEOUT = (10, 30)
HTTP_RETRIES = 4
HTTP_BACKOFF_BASE = 0.8

USER_AGENT = "sleeping-alts-screener/3.0"

WEIGHT_CAPACITY = 1200
WEIGHT_REFILL_PER_SEC = 30.0
WEIGHT_SOFT_LIMIT = 1900
WEIGHT_PENALTY_SEC = 3.0

# ─────────────────────────────────────────────────────────────
# Отбор монет
# ─────────────────────────────────────────────────────────────
MAX_SYMBOLS = 200
MIN_QUOTE_VOLUME_24H = 5_000_000
MIN_HISTORY_DAYS = 30

MAX_WORKERS = 6

# ─────────────────────────────────────────────────────────────
# Пороги индикаторов
# ─────────────────────────────────────────────────────────────
RVOL_HOT = 3.0
RVOL_WARM = 1.8
RVOL_COOL = 1.2

OBV_ACCUMULATION = 20.0
OBV_STRONG = 50.0

SURGE_STRONG = 10.0

# ── Объём к медиане: колонка отчёта и метрика кандидата ──
# Окно нормы. Медиана, а не среднее: один памп в выборке
# задирает среднее так, что последующие всплески перестают
# быть всплесками.
VOL_MEDIAN_WINDOW = 30

# Ниже этой доли набранного времени текущий бар в расчёт
# не идёт. Заниженное значение хуже отсутствующего: оно
# выглядит как факт.
#
# Число совпадает с PARTIAL_BAR_MIN_FILL в flow_config, но
# константы независимы — семейство FLOW наружу ничего не
# отдаёт. При изменении править оба места.
MIN_BAR_FILL = 0.35

# ─────────────────────────────────────────────────────────────
# Пороги вето
# ─────────────────────────────────────────────────────────────
# Фандинг за период. 0.08% за 8ч это около 87% годовых — уже явный перегрев.
# Прежние 0.05% отсекали слишком много живых трендов.
VETO_FUNDING_ABS = 0.08

# Открытый интерес. При обороте от $5M в сутки OI ниже $500K означает,
# что позицию некуда закрыть без проскальзывания.
VETO_MIN_OI_USD = 500_000

VETO_MAX_ATR_PCT = 25.0

# Доля спота в общем обороте. Полное отсутствие спота — сигнал,
# но severity low: сам по себе вход не блокирует.
VETO_MIN_SPOT_RATIO = 0.02

VETO_BLOCKING_SEVERITY = ("high", "mid")

# ─────────────────────────────────────────────────────────────
# Пороги R:R и бакетов
# ─────────────────────────────────────────────────────────────
# Цели строятся от структуры рынка, поэтому R:R теперь величина
# измеряемая, а не заданная. 1.8 — минимум, при котором серия сделок
# с винрейтом около 40% остаётся прибыльной.
MIN_RR_TRADABLE = 1.8

BUCKET_STRONG = 55
BUCKET_GOOD = 35
BUCKET_SCOUT = 20

# ─────────────────────────────────────────────────────────────
# Исключения из выборки
# ─────────────────────────────────────────────────────────────
STABLECOINS = {
    "USDT", "USDC", "BUSD", "DAI", "TUSD", "FDUSD",
    "USDP", "USDD", "UST", "PYUSD", "USDE", "USDS", "USDX",
}

STOCK_PERPS = {
    "TSLA", "MRVL", "NVDA", "AAPL", "MSFT", "AMZN", "META", "GOOGL",
    "COIN", "MSTR", "HOOD", "PLTR", "AMD", "INTC", "NFLX", "BABA",
    "SPY", "QQQ", "GLD", "SLV", "ON", "SNDK", "SKHYNIX", "SOXL",
    "MU", "TSM", "ASML", "AVGO", "ORCL", "SMCI", "ARM", "DELL",
    "IBM", "CRM", "UBER", "ABNB", "SHOP", "GME", "AMC", "BB",
    "NOK", "LCID", "RIVN", "NIO", "XPEV", "BRKB", "JPM", "V",
    "MA", "WMT", "COST", "DIS", "PYPL", "COINBASE", "CRCL",
    "FIGR", "BMNR", "SBET",
    "NBIS", "CRWV", "RKLB", "AAOI", "IREN", "SAMSUNG", "SKHY",
    "ZHIPU", "MVLL", "GLW", "EWY", "SNXX", "MINIMAX", "STRC",
    "GRAM", "TQQQ", "SQQQ", "SOXS", "SPCX", "LITE", "BILL",
}

COMMODITY_PERPS = {
    "XAU", "XAG", "XAUT", "PAXG", "XPT", "XPD",
    "NATGAS", "OIL", "WTI", "BRENT",
}

MAJOR_TOKENS = {
    "BTC", "ETH", "XRP", "FARTCOIN", "NEAR", "LTC",
    "ETC", "ADA", "BNB", "DOGE", "SOL",
}

EXCLUDE_TOKENS = STABLECOINS | MAJOR_TOKENS | STOCK_PERPS | COMMODITY_PERPS

# ─────────────────────────────────────────────────────────────
# Классификация нарративов
# ─────────────────────────────────────────────────────────────
VIRAL_SECTOR_KEYWORDS = [
    "meme", "dog", "cat", "frog", "pepe", "inu", "shib", "wif",
    "bonk", "floki", "broccoli", "farto", "useless",
    "game", "gaming", "gamefi", "play-to-earn", "metaverse", "virtual",
    "artificial intelligence", " ai ", "ai agent", "agent",
    "machine learning", "deai", "ai & big data", "depin",
    "solana meme", "bnb chain ecosystem", "base ecosystem", "pump.fun",
]

MEME_TICKER_HINTS = [
    "PEPE", "SHIB", "DOGE", "FLOKI", "BONK", "WIF", "BROCCOLI",
    "FARTCOIN", "USELESS", "NEIRO", "GIGGLE", "TRUMP", "MELANIA",
    "MOG", "TURBO", "POPCAT", "MEW", "BOME", "PENGU", "SPX",
]

SECTOR_MAP = {
    "AI": ["artificial intelligence", "ai agent", "ai & big data",
           "machine learning", "deai", "depin"],
    "GAMEFI": ["gaming", "gamefi", "play-to-earn", "metaverse", "virtual"],
    "MEME": ["meme", "dog", "cat", "frog", "pepe", "inu", "shib"],
    "DEFI": ["defi", "dex", "lending", "yield", "derivatives", "liquid staking"],
    "L1/L2": ["smart contract platform", "layer 1", "layer 2",
              "rollup", "scaling", "ethereum ecosystem"],
    "RWA": ["real world assets", "rwa", "tokenized"],
    "INFRA": ["oracle", "storage", "infrastructure", "interoperability",
              "bridge", "privacy"],
}
