"""Таблица «монеты в обороте» по всем монетам доски, сверенная ценой: CoinGecko /coins/markets по тикеру, берётся та монета, чья цена
совпадает с нашей (±25 %). Итог — output/circ_supply.json: {SYM: {id, circ, cg_px, our_px, at}}."""
import json, glob, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone
from core_config import STARS_NEW_SKIP
ALIAS = {"RAYSOL": "ray", "BEAMX": "beam", "LUNA2": "luna", "BROCCOLI714": "broccoli", "1MBABYDOGE": "babydoge"}
coins = {}
for p in sorted(glob.glob("cq_v2/intraday/*.jsonl")):
    base = Path(p).stem.upper()
    if base in set(STARS_NEW_SKIP): continue
    try: px = json.loads(open(p).read().splitlines()[-1])["px"]
    except Exception: continue
    mult = 1000 if base.startswith("1000") else (1e6 if base.startswith("1M") else 1)
    tick = ALIAS.get(base) or (base[4:] if base.startswith("1000") else base).lower()
    coins[base] = (tick.lower(), px / mult)
ticks = sorted({t for t, _ in coins.values()})
got = []
for i in range(0, len(ticks), 40):
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&include_tokens=all&per_page=250&symbols=" + urllib.parse.quote(",".join(ticks[i:i + 40]))
    for attempt in range(3):
        try:
            got += json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "curl/8"}), timeout=30)); break
        except Exception as e:
            print("повтор", i, e); time.sleep(25)
    time.sleep(8)
by = {}
for c in got: by.setdefault(c["symbol"].lower(), []).append(c)
out = {}; miss = []
now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
for base, (tick, px) in coins.items():
    cand = [c for c in by.get(tick, []) if c.get("current_price") and c.get("circulating_supply") and 0.75 <= c["current_price"] / px <= 1.33]
    if not cand: miss.append(base); continue
    c = max(cand, key=lambda c: c.get("market_cap") or 0)
    out[base + "USDT"] = {"id": c["id"], "circ": float(c["circulating_supply"]), "cg_px": c["current_price"], "our_px": px, "mcap": c.get("market_cap"), "at": now}
Path("output/circ_supply.json").write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
print("монет доски:", len(coins), "· найдено по цене:", len(out), "· не найдено:", len(miss), miss)
