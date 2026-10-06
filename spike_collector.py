#!/usr/bin/env python3
"""СБОРЩИК ВСПЛЕСКОВ ОБЪЁМА (29.09, владелец: «у нас очень мало сделок для анализа, сделай такого же бота, который будет собирать всплески объёма
и рост цены +1%, чтобы было что анализировать, и дальше разбирай ход монет через пару часов»). Торговли нет, в телеграм не пишет, только журнал.

Раз в 3 минуты — все USDT-перпы Binance, последний закрытый 3-минутный бар: цена бара ≥ +SPIKE_LOG_PCT и объём ≥ SPIKE_LOG_X × медианы 30 баров
(минимумы из скринов канала «Volume Spikes»: 1.0% и ×10.06; своих порогов нет). Каждый всплеск → output/spike_log.jsonl (kind "spike"): монета, время,
цена, % бара, ×объёма, оборот бара, и ФОН на момент всплеска (Binance): положение в диапазоне 90 дн (×от минимума, % от максимума), ход за 30 дн,
спот CVD за 7 дн, интерес за час, фандинг, толпа по счетам, вынос шортов/лонгов на часе (поток OKX+Bybit) против крупнейшего часа монеты, сессия, день недели,
фон рынка (book_fon). Через 1, 2 и 4 часа после бара — kind "outcome": максимум вверх / минимум вниз / закрытие от цены всплеска и что раньше, +5% или −5%.
Состояние — output/spike_state.json (ждущие исходы). Разбор — spike_report.py.

    .venv/bin/python spike_collector.py --loop     # живёт сам (сторож run.py следит)
    .venv/bin/python spike_collector.py            # один проход с записью
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json  # noqa: E402

try:
    from core_config import SPIKE_LOG_X, SPIKE_LOG_PCT
except ImportError:
    SPIKE_LOG_X, SPIKE_LOG_PCT = 10.0, 0.01
LOG = BASE_DIR / "output" / "spike_log.jsonl"
STATE = BASE_DIR / "output" / "spike_state.json"
HORIZONS = (1, 2, 4)                                     # часы до записи исхода
L = timezone.utc   # 06.10 владелец: «всё должно быть в utc везде»; сессии берутся из fast_tier.SES_WIN, а они теперь в часах UTC (до этого UTC+3)
_ft = None


def ft():
    global _ft
    if _ft is None:
        import fast_tier as m
        _ft = m
    return _ft


def symbols() -> list[str]:
    ex = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
    return [s["symbol"] for s in ex.get("symbols", []) if s.get("quoteAsset") == "USDT" and s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"]


def scan(sym: str):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": 33}, quiet_400=True) or []
    if len(k) < 33:
        return None
    k = k[:-1]
    qv = [float(x[7]) for x in k]; c = [float(x[4]) for x in k]; o = float(k[-1][1])
    med = st.median(qv[:-1])
    if med <= 0 or c[-2] <= 0:
        return None
    bar = c[-1] / c[-2] - 1
    x = qv[-1] / med
    if bar >= SPIKE_LOG_PCT and x >= SPIKE_LOG_X:
        import bubbles                                                  # 30.09: пузыри как фон (bubbles.py) — дельта бара в σ, доля покупок, пузыри за 20 баров до
        return dict(sym=sym, t_ms=int(k[-1][0]), px=c[-1], px_open=o, bar=round(bar * 100, 3), x=round(x, 2), qv=round(qv[-1]), **{("bub_" + a if not a.startswith("bub") else a): b for a, b in (bubbles.feats(k) or {}).items()})
    return None


def background(r: dict) -> dict:
    """фон на момент всплеска; любая часть может быть None (нет данных) — не падаем"""
    m = ft(); sym, px, t_ms = r["sym"], r["px"], r["t_ms"]
    out = {}
    try:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 90}, quiet_400=True) or []
        if len(k) >= 30:
            lo = min(float(x[3]) for x in k); hi = max(float(x[2]) for x in k)
            out["x90"] = round(px / lo, 2) if lo > 0 else None
            out["hi90"] = round((px / hi - 1) * 100, 1)
            out["ch30"] = round((px / float(k[-31][4]) - 1) * 100, 1) if len(k) > 31 else None
    except Exception:  # noqa: BLE001
        pass
    try:
        cv = m._spot_cvd7(sym); out["spot_cvd7"] = None if cv is None else round(cv)
    except Exception:  # noqa: BLE001
        pass
    try:
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 13}, quiet_400=True) or []
        ov = [float(x["sumOpenInterestValue"]) for x in oi]
        out["oi1h"] = round((ov[-1] / ov[0] - 1) * 100, 2) if len(ov) >= 12 else None
        out["oi5"] = round((ov[-1] / ov[-2] - 1) * 100, 2) if len(ov) >= 2 else None
        ch = [(b / a_ - 1) * 100 for a_, b in zip(ov, ov[1:]) if a_ > 0]                  # 30.09: «вынос по интересу» — крайние изменения на 5-мин баре за час
        if len(ch) >= 6:
            out["oi5_min_1h"], out["oi5_max_1h"] = round(min(ch), 2), round(max(ch), 2)
    except Exception:  # noqa: BLE001
        pass
    try:
        pi = get_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": sym}, quiet_400=True) or {}
        out["fund"] = round(float(pi.get("lastFundingRate")) * 100, 4)
    except Exception:  # noqa: BLE001
        pass
    try:
        out["crowd"] = m.crowd_of(sym)
    except Exception:  # noqa: BLE001
        pass
    try:
        hl = m._liq_hourly()
        h0 = t_ms // 3_600_000 * 3_600_000
        for side in ("short", "long"):
            hs = hl.get((sym, side)) or {}
            past = [v for h, v in hs.items() if h < h0]
            out[f"liq_{side}_now"] = round(hs.get(h0, 0.0))
            out[f"liq_{side}_top"] = round(max(past)) if past else None
    except Exception:  # noqa: BLE001
        pass
    try:
        d = datetime.fromtimestamp(t_ms / 1000, L)
        out["ses"] = next(n for n, a, b in m.SES_WIN if a <= d.hour < b); out["wd"] = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")[d.weekday()]
    except Exception:  # noqa: BLE001
        pass
    return out


def append(rows: list[dict]) -> None:
    if not rows:
        return
    LOG.parent.mkdir(exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_state() -> dict:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"pending": [], "seen": {}}


def save_state(s: dict) -> None:
    tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)


def outcomes(state: dict) -> list[dict]:
    now_ms = int(time.time() * 1000); out = []; keep = []
    for p in state["pending"]:
        left = []
        for h in p["todo"]:
            end = p["t_ms"] + 180_000 + h * 3_600_000
            if now_ms < end + 60_000:
                left.append(h); continue
            k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": p["sym"], "interval": "3m", "startTime": p["t_ms"] + 180_000, "endTime": end - 1, "limit": 1000}, quiet_400=True) or []
            if not k:
                left.append(h); continue
            e = p["px"]; hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4])
            first = next(("+5" if float(x[2]) >= e * 1.05 else "-5" for x in k if float(x[2]) >= e * 1.05 or float(x[3]) <= e * 0.95), "нет")
            out.append(dict(kind="outcome", sym=p["sym"], t_ms=p["t_ms"], h=h, up=round((hi / e - 1) * 100, 2), dn=round((lo / e - 1) * 100, 2), cl=round((c / e - 1) * 100, 2), first=first))
        if left:
            p["todo"] = left; keep.append(p)
    state["pending"] = keep
    return out


def step(write: bool = True) -> list[str]:
    state = load_state(); now_ms = int(time.time() * 1000); msgs = []
    syms = symbols()
    with ThreadPoolExecutor(12) as ex:
        hits = [r for r in ex.map(scan, syms) if r]
    rows = []
    for r in hits:
        key = f"{r['sym']}|{r['t_ms']}"
        if key in state["seen"]:
            continue
        state["seen"][key] = now_ms
        r["kind"] = "spike"; r.update(background(r)); r["at"] = round(time.time(), 1)
        rows.append(r); state["pending"].append(dict(sym=r["sym"], t_ms=r["t_ms"], px=r["px"], todo=list(HORIZONS)))
        msgs.append(f"{r['sym'][:-4]} +{r['bar']}% ×{r['x']} · у вершины 90д {r.get('hi90')}% · интерес 1ч {r.get('oi1h')}")
    rows += outcomes(state)
    state["seen"] = {k: v for k, v in state["seen"].items() if now_ms - v < 86_400_000}
    if write:
        append(rows); save_state(state)
    msgs.append(f"монет {len(syms)} · всплесков {len(hits)} · исходов записано {sum(1 for x in rows if x['kind'] == 'outcome')} · ждут исхода {len(state['pending'])}")
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--loop", action="store_true"); a = ap.parse_args()
    while True:
        try:
            for m in step(True):
                print(f"{datetime.now(L):%H:%M:%S} {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} сбой {type(e).__name__}: {e}", flush=True)
        if not a.loop:
            return 0
        time.sleep(max(1, 180 - (time.time() % 180) + 5))


if __name__ == "__main__":
    raise SystemExit(main())
