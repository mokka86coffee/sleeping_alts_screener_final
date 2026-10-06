#!/usr/bin/env python3
"""ТРЁХМИНУТНАЯ СТУПЕНЬ (27.09, владелец: «зачем прогон для всех монет, если всплеск нужен только у тех, у кого был интерес за час —
раз в полчаса отбираем, каждые 3 минуты смотрим только их»). Книга «всплеск/вынос».
Короткий список — из архива получасовок (cq_v2/intraday, обновляется прогоном): монеты, у которых интерес за час ≥ FAST3_SHORT_OI1H %
(кандидаты на всплеск, лонг) и монеты с ходом от минимума 24 ч ≥ FAST3_SHORT_RUN24 % (кандидаты на вынос, шорт).
Каждые 3 минуты по списку — последняя закрытая трёхминутка Binance:
  всплеск (R39): объём ≥ FAST3_SPIKE_X × медианы 30 баров и ≥ FAST3_SPIKE_MINQ $, бар ≥ +FAST3_SPIKE_PCT → лонг; +5 / −5 / 2 ч;
  вынос (R21): бар ≥ +FAST3_CLIMAX_BAR и интерес на баре ≤ FAST3_CLIMAX_OI → шорт; −8 / +6 / 12 ч.
СЕССИИ (27.09 17:30, R40–R42, пороги FAST3_SES_* / FAST3_SKIP_DAYS): лонг-всплеск (не перевёрнутый) не берётся в первый час сессии,
в поздние минуты Сиднея и Нью-Йорка и в запрещённые дни; срок — до часа выхода сессии (Токио/Лондон/НЙ — открытие следующей, Сидней — 10:00).
Выходы своих позиций каждые 3 минуты. Журнал output/paper_fast3.jsonl (entry / exit_long / exit_short / follow), состояние output/paper_fast3.json.
    python3 fast_tier.py --loop      # запускает прогон один раз (PAPER_FAST3_ENABLED), живёт сам
    python3 fast_tier.py             # один проход без записи
"""
from __future__ import annotations
import re
import argparse, json, statistics as st, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json
from core_config import (FAST3_SIZE, FAST3_SPIKE_X, FAST3_SPIKE_MINQ, FAST3_SPIKE_PCT, FAST3_SPIKE_TP, FAST3_SPIKE_SL, FAST3_SPIKE_HOLD_MIN,
                         FAST3_CLIMAX_BAR, FAST3_CLIMAX_RUN, FAST3_CLIMAX_OI, FAST3_CLIMAX_TP, FAST3_CLIMAX_SL, FAST3_CLIMAX_HOLD_MIN,
                         FAST3_SHORT_OI1H, FAST3_SHORT_RUN24)
from paper_book_base import rows_of, ARCH
from book_fon import fon, coin_fon

BOOK = "всплеск/вынос"; FEE = 0.001
# 28.09: прогон поднимает fast_tier системным Python без пакетов проекта (playwright, websockets) — скрины падали «No module named playwright»;
# дочерние процессы (скрины, разборы, данные страницы, сервер, список ММ) запускаем Python'ом проекта, если он есть
PY = str(BASE_DIR / ".venv" / "bin" / "python") if (BASE_DIR / ".venv" / "bin" / "python").exists() else sys.executable
_CROWD = {"t": 0, "v": {}}      # 27.09 п.1: толпа по счетам (Binance globalLongShortAccountRatio), обновляется раз в 30 мин
STATE = BASE_DIR / "output" / "paper_fast3.json"; LOG = BASE_DIR / "output" / "paper_fast3.jsonl"
L = timezone.utc   # 06.10 владелец: «всё должно быть в utc везде, хоть в настройках бота»; «эта хрень где-то всплывёт с разницей в 3 часа — это конец сделки
                   # как минимум». До 06.10 здесь стояло UTC+3 и все часы правил были московские. Теперь все часы правил, сессии, дни недели и время в
                   # сообщениях бота — UTC. Местное время — только на экране сайта (его считает браузер). Равенство старых и новых ответов
                   # проверяет claude/research/utc_equiv.py (каждая минута двух недель).


def crowd_of(sym: str):
    """толпа по счетам, кэш 30 мин (27.09 п.1: ZEC — толпа 0.49 в шорте и интерес +9% за 6 ч, а за час +1.3% — список её не видел)"""
    if time.time() - _CROWD["t"] > 1800:
        _CROWD["v"] = {}; _CROWD["t"] = time.time()
    if sym not in _CROWD["v"]:
        g = get_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "15m", "limit": 1}, quiet_400=True) or [{}]
        try: _CROWD["v"][sym] = float(g[0].get("longShortRatio") or 0) or None
        except (TypeError, ValueError): _CROWD["v"][sym] = None
    return _CROWD["v"][sym]


_PERPS: dict = {"t": 0, "v": []}


def _bingx(ev: list) -> list[str]:
    """30.09 владелец «настрой торговлю на BingX»: события входа/выхода → ордера (bingx_trader.py; выключено, пока в bingx_config.json enabled: false); сбой бота не роняет"""
    try:
        import bingx_trader
        return bingx_trader.on_events(ev)
    except Exception as e:  # noqa: BLE001
        return [f"BingX: {type(e).__name__}: {e}"]


def _bub(sym: str):
    """30.09 владелец «заведи и проверь»: пузыри (дельта бара 3 мин дальше σ от нормы монеты) — только запись в журнал входа, в решения не входит (bubbles.py)"""
    try:
        import bubbles
        return bubbles.live(sym)
    except Exception:  # noqa: BLE001
        return None


_SPK: dict = {}; _BTC: dict = {"t": 0, "v": None}


def _pack() -> int:
    """30.09 владелец «менять правила без фона — по кругу»: только запись — сколько монет дали всплеск (R39) за последние 6 мин (пачка = ход доски, а не монеты)"""
    lim = (time.time() - 360) * 1000
    return sum(1 for t in list(_SPK.values()) if t >= lim)


def _btc():
    """только запись: BTC за 1 ч и 24 ч, % (фьючерс Binance, кэш 3 мин)"""
    if time.time() - _BTC["t"] > 180:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": "BTCUSDT", "interval": "1h", "limit": 25}, quiet_400=True) or []
        _BTC["v"] = dict(h1=round((float(k[-1][4]) / float(k[-2][4]) - 1) * 100, 2), h24=round((float(k[-1][4]) / float(k[0][4]) - 1) * 100, 2)) if len(k) >= 25 else None
        _BTC["t"] = time.time()
    return _BTC["v"]


def _all_perps() -> list[str]:
    """все торгуемые USDT-перпы Binance, кэш 1 ч"""
    if time.time() - _PERPS["t"] > 3600 or not _PERPS["v"]:
        ex = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
        try:
            from core_config import FAST3_MIN_LISTING_DAYS as _mind
        except ImportError:
            _mind = 180
        _now_ms = time.time() * 1000                                      # 03.10 владелец (牛来): «листинг больше полугода? … такое не торгуем вообще никогда» — моложе FAST3_MIN_LISTING_DAYS в список не берём
        v = [x["symbol"] for x in ex.get("symbols", []) if x.get("quoteAsset") == "USDT" and x.get("contractType") == "PERPETUAL" and x.get("status") == "TRADING"
             and (_now_ms - int(x.get("onboardDate") or 0)) / 86400_000 >= _mind]
        if v:
            _PERPS.update(t=time.time(), v=v)
    return _PERPS["v"]


def _too_young(sym: str):
    """03.10: подпись, если монета моложе FAST3_MIN_LISTING_DAYS на фьючерсах Binance (для ожиданий и позиций, созданных до правки), иначе None"""
    try:
        from core_config import FAST3_MIN_LISTING_DAYS as _mind
    except ImportError:
        _mind = 180
    a = listing_age_days().get(sym)
    return f"листинг {a:.0f} дн < {_mind} — не торгуем" if a is not None and a < _mind else None


def short_list(all_coins: bool = True) -> tuple[list[str], list[str], dict]:
    try:
        from core_config import FAST3_SHORT_CROWD_MAX as _cmax, FAST3_SHORT_OI6H as _oi6
    except ImportError:
        _cmax, _oi6 = 0.7, 5.0
    spike, climax, info = [], [], {}
    for p in ARCH.glob("*.jsonl"):
        sym = p.stem.upper() + "USDT"; r = rows_of(sym)
        if len(r) < 49:
            continue
        oi1, oi0, oi6b = r[-1].get("oi"), r[-3].get("oi"), r[-13].get("oi")
        oi1h = (float(oi1) / float(oi0) - 1) * 100 if oi1 and oi0 else None
        oi6h = (float(oi1) / float(oi6b) - 1) * 100 if oi1 and oi6b else None
        cf = coin_fon(r); info[sym] = dict(oi1h=oi1h, oi6h=oi6h, run24=cf.get("run24"), crowd=None)
        take = oi1h is not None and oi1h >= FAST3_SHORT_OI1H
        if not take and oi6h is not None and oi6h >= _oi6:               # п.1: деньги за 6 ч и толпа в шорте
            cr = crowd_of(sym); info[sym]["crowd"] = cr
            take = cr is not None and cr <= _cmax
        if take: spike.append(sym)
        if cf.get("run24") is not None and cf["run24"] >= FAST3_SHORT_RUN24: climax.append(sym)
    # 30.09 владелец «да» («у бота 5 сделок, он смотрит 19–27 монет из 527»): на всплеск проверяем ВСЕ USDT-перпы Binance (как сборщик), ворота без изменений
    try:
        from core_config import FAST3_ALL_COINS as _all
    except ImportError:
        _all = True
    if _all and all_coins:
        spike = sorted(set(spike) | set(_all_perps()))
    return spike, climax, info


def _oi_live(sym: str):
    """интерес за час и за последний закрытый 5-мин бар, % — по живым 5-минуткам Binance, как в «пробуждении» (28.09: «всплеск/вынос» брала
    интерес за час из получасового архива, он отстаёт — на NOM и CVX книги встали в разные стороны: шорт +4.9% против лонга −5.1%)"""
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 13}, quiet_400=True) or []
    ov = [float(x["sumOpenInterestValue"]) for x in oi if int(x["timestamp"]) <= time.time() * 1000]
    h1 = (ov[-1] / ov[0] - 1) * 100 if len(ov) >= 13 and ov[0] else None
    b5 = (ov[-1] / ov[-2] - 1) * 100 if len(ov) >= 2 and ov[-2] else None
    return h1, b5


def _oi_bar(sym: str):
    """изменение интереса за последний ЗАКРЫТЫЙ 5-минутный бар, % — только то, что известно в момент входа"""
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 3}, quiet_400=True) or []
    ov = [float(x["sumOpenInterest"]) for x in oi if int(x["timestamp"]) <= time.time() * 1000]
    return (ov[-1] / ov[-2] - 1) * 100 if len(ov) >= 2 and ov[-2] else None


def _crowd_live(sym: str):
    """толпа по счетам на последнем 5-мин баре — без кэша (решение о перевороте принимается по ней в момент входа)"""
    g = get_json("https://fapi.binance.com/futures/data/globalLongShortAccountRatio", {"symbol": sym, "period": "5m", "limit": 1}, quiet_400=True) or [{}]
    try:
        return float(g[0].get("longShortRatio") or 0) or None
    except (TypeError, ValueError, IndexError, AttributeError):
        return None


# 28.09 владелец (XLM): «здесь вынесли лонги, и не могло быть шорта» — после крупного выноса лонгов продавец тянет вверх (его первая стратегия),
# переворот всплеска в шорт тогда не берём, остаётся лонг. «Крупный» — по своей истории монеты: часовой вынос лонгов в текущей или прошлой
# сессии не меньше самого большого часового выноса этой монеты за всю доступную историю потока (до 90 дн; поток OKX+Bybit с 25.09,
# Binance в нём нет). Истории меньше 3 дн — правило молчит.
_LIQ = {"files": {}, "hourly": {}}


def _liq_hourly() -> dict:
    """монета → {час (мс): $ ликвидированных лонгов}; файлы потока перечитываются только при изменении"""
    changed = False
    for p in sorted((BASE_DIR / "cq_v2" / "liq").glob("*.jsonl"))[-90:]:
        mt = p.stat().st_mtime
        if _LIQ["files"].get(p.name, (None,))[0] == mt:
            continue
        per, seen = {}, set()
        for ln in p.open(encoding="utf-8", errors="ignore"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            sd_ = r.get("side")
            if sd_ not in ("long", "short"):
                continue
            k = (r.get("t"), r.get("sym"), sd_, r.get("usd"), r.get("src"))
            if k in seen:
                continue
            seen.add(k)
            h = int(r["t"]) // 3_600_000 * 3_600_000
            d_ = per.setdefault((r["sym"], sd_), {})
            d_[h] = d_.get(h, 0.0) + float(r.get("usd") or 0)
        _LIQ["files"][p.name] = (mt, per); changed = True
    if changed:
        agg = {}
        for _, per in _LIQ["files"].values():
            for sym, hs in per.items():
                d = agg.setdefault(sym, {})
                for h, v in hs.items():
                    d[h] = d.get(h, 0.0) + v
        _LIQ["hourly"] = agg
    return _LIQ["hourly"]


def _flush(sym: str, now: float, side: str = "long", since_ms: int | None = None):
    """вынос стороны side (long / short) с начала прошлой сессии (или с since_ms) — крупнейший часовой в истории монеты? → причина или None"""
    try:
        hs = _liq_hourly().get((sym, side)) or {}
    except Exception:  # noqa: BLE001
        return None
    if not hs:
        return None
    d = datetime.fromtimestamp(now, L)
    i = next(j for j, x in enumerate(SES_WIN) if x[1] <= d.hour < x[2])
    pn, pa, _ = SES_WIN[i - 1]
    w0 = d.replace(hour=pa, minute=0, second=0, microsecond=0) - (timedelta(days=1) if i == 0 else timedelta(0))
    if since_ms:
        w0 = datetime.fromtimestamp(since_ms // 3_600_000 * 3_600 , L)
    w0ms = int(w0.timestamp() * 1000)
    past = [v for h, v in hs.items() if h < w0ms]
    if not past or (w0ms - min(hs)) < 3 * 86_400_000:
        return None
    win = max((v for h, v in hs.items() if h >= w0ms), default=0.0)
    top = max(past)
    if win > 0 and win >= top:
        return f"вынос {'лонгов' if side == 'long' else 'шортов'} {win / 1e3:.0f}K$ за час с {w0:%H:%M} — крупнейший в истории монеты (было {top / 1e3:.0f}K$)"
    return None


def _flush_record(sym: str, side: str, after_ms: int = 0):
    """R49/R52 (03.10 владелец): «рекордный за 24 часа вынос на часовой свече… вход в течение максимум 30 минут после закрытия часовой свечи».
    Только что закрытый час: вынос стороны side ≥ FAST3_FLUSH_X × максимума часа этой стороны за предыдущие сутки и больше любого часа
    противоположной стороны за сутки (поток OKX+Bybit). → (час мс, вынос $, прежний максимум $) или None"""
    try:
        from core_config import FAST3_FLUSH_X as _x, FAST3_FLUSH_WINDOW_MIN as _wm
    except ImportError:
        _x, _wm = 1.3, 30
    try:
        hs = _liq_hourly().get((sym, side)) or {}; ho = _liq_hourly().get((sym, "long" if side == "short" else "short")) or {}
    except Exception:  # noqa: BLE001
        return None
    if not hs:
        return None
    now_ms = int(time.time() * 1000); now_h = now_ms // 3_600_000 * 3_600_000
    if now_ms - now_h > _wm * 60_000:
        return None
    hm = now_h - 3_600_000
    if hm <= after_ms or hm not in hs:
        return None
    win = hs[hm]; prev = [v for h, v in hs.items() if hm - 86_400_000 <= h < hm]
    other = max((v for h, v in ho.items() if hm - 86_400_000 <= h <= hm), default=0.0)
    if not prev or win <= 0 or win <= other:
        return None
    try:
        from core_config import FAST3_FLUSH_X2 as _x2
    except ImportError:
        _x2 = 2.0
    mx = max(prev); mean = sum(prev) / len(prev)
    # R61 (03.10 владелец): «вынос рекордным должен быть за 24 часа, ×2 минимум от любого другого выноса, при условии что выносы были практически одинаковыми за 24 часа;
    # если выносы ×2+ к общему среднему уже были, то +30 % от него» — среднее по часам суток, где выносы этой стороны были
    need = _x * mx if (len(prev) > 1 and mx >= 2 * mean) else max(_x, _x2) * mx
    if win >= need:
        return hm, win, mx
    return None


def _short_flush_record(sym: str, after_ms: int = 0):
    return _flush_record(sym, "short", after_ms)


def _move_10h(sym: str, hm: int):
    """R52 (03.10 владелец): «ход за 24 часа, минимумы каждой часовой свечи… сначала проверить, что размах часовой свечи выноса больше 20 %, потом смотреть
    минимумы часовых свеч за 24 часа до выноса: росли или падали; пила/отскоки 5–10 часов или флэт внутри — нормально».
    → (направление +1 рост / −1 падение / 0 нет, ход минимумов %, размах свечи выноса %)"""
    try:
        from core_config import FAST3_FLUSH_MOVE_H as _mh, FAST3_FLUSH_BAR_RANGE as _rng
    except ImportError:
        _mh, _rng = 24, 20.0
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1h", "endTime": hm + 3_599_999, "limit": 49}, quiet_400=True) or []
    if len(k) < _mh + 1 or int(k[-1][0]) != hm:
        return 0, 0.0, 0.0, {}
    bar = k[-1]; rng = (float(bar[2]) / float(bar[3]) - 1) * 100 if float(bar[3]) > 0 else 0.0
    lows_all = [float(x[3]) for x in k[:-1]]; lows = lows_all[-_mh:]     # 24 часа до часа выноса
    n = len(lows) // 3; first, last = lows[:n], lows[-n:]
    a1, a2 = sum(first) / n, sum(last) / n; mv = (a2 / a1 - 1) * 100
    # R58 (03.10 владелец): «смотрим минимумы часовых свечей за последние 48 часов… максимум на часовой свече выноса и минимум на часовой за 48 часов: больше 60 % — памп, 40 — просто рост»
    inf = dict(open=float(bar[1]), high=float(bar[2]), low=float(bar[3]), close=float(bar[4]), rising48=False, rise48=None)
    if len(lows_all) >= 48:
        l48 = lows_all[-48:]; f3, l3 = l48[:16], l48[-16:]
        inf["rising48"] = min(l3) > min(f3) and sum(l3) > sum(f3)
        inf["rise48"] = (float(bar[2]) / min(l48) - 1) * 100 if min(l48) > 0 else None
    if min(last) > min(first) and a2 > a1:                               # минимумы росли (флэт/отскоки внутри допустимы)
        return 1, mv, rng, inf
    if max(last) < max(first) and a2 < a1:                               # минимумы падали
        return -1, mv, rng, inf
    return 0, mv, rng, inf


def _pump_end_all() -> dict:
    """R58/R60: когда по монете был сквиз «конец роста» (секунды) — общий для обеих книг файл output/pump_end.json"""
    try:
        return json.loads((BASE_DIR / "output" / "pump_end.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _pump_end_set(sym: str, now: float) -> None:
    d = {k: v for k, v in _pump_end_all().items() if now - float(v) < 3 * 86400}; d[sym] = now
    try:
        (BASE_DIR / "output" / "pump_end.json").write_text(json.dumps(d), encoding="utf-8")
    except OSError:
        pass


def _pump_ban(sym: str, now: float):
    """R60 (03.10 владелец: «лонги тут после выноса брать нельзя — именно их и будут выносить, причём достаточно долго»; «лонг берётся минимум через 6 часов») → подпись отказа или None"""
    try:
        from core_config import FAST3_FLUSH_NEW as _on, FAST3_PUMP_END_LONG_BAN_H as _bh
    except ImportError:
        _on, _bh = True, 6
    t = _pump_end_all().get(sym) if _on else None
    if t and 0 <= now - float(t) < _bh * 3600:
        return f"лонг не взят: сквиз в конце роста был {(now - float(t)) / 3600:.1f} ч назад — лонг в этой монете не раньше чем через {_bh:g} ч (R60)"
    return None


_RATE_F = BASE_DIR / "output" / "fast_entry_times.json"                 # 03.10 15:58: возвращено вместе с _rate_ok (потеряно при правке R52 в 04:30 — каждый вход падал с NameError)


# ── R54–R56 (03.10 16:20, владелец: «делай все» на три предложения по счёту TradingView, claude/research/leaders_tv.md) ──────────────────────────────
_BOARD = {"t": 0.0, "v": None}
_BOARD_F = BASE_DIR / "output" / "board_now.json"
_FUND7 = {"t": 0.0, "v": None, "busy": False}
_FUND7_F = BASE_DIR / "output" / "fund7_cache.json"


def _board_set(tk: list) -> None:
    """доска за 24 ч по всем перпам Binance из общего тикера: медиана хода, доля монет в плюсе, BTC; пишется в output/board_now.json (сайт)"""
    try:
        from core_config import FAST3_FLUSH_BOARD_UP as _up
    except ImportError:
        _up = 1.0
    try:
        ch = {x["symbol"]: float(x["priceChangePercent"]) for x in tk if x.get("symbol", "").endswith("USDT") and float(x.get("quoteVolume") or 0) > 0}
        if len(ch) < 100:
            return
        v = sorted(ch.values()); med = v[len(v) // 2]
        try:
            from core_config import FAST3_BOARD_FLAT as _flat, FAST3_BOARD_DEEP as _deep
        except ImportError:
            _flat, _deep = 1.0, 3.0
        sf = _board_short_flush()                                        # рекордный вынос шортов по всей доске за последние 6 ч (время часа, $) или None
        # 03.10 18:30 владелец «вноси» (счёт tv_board_turn.py): выше +3 % — рост продолжается (лонг); ровная — сползает (шорт); ниже −3 % — ждать отскок; +1…+3 и −3…−1 — шум;
        # рекордный вынос шортов по всей доске — местная вершина (следующие 6 ч вниз в 3 случаях из 4)
        zone = "рост" if med > _up else ("отскок" if med < -_deep else ("ровная" if abs(med) <= _flat else "шум"))
        lean = "шорт" if sf else {"рост": "лонг", "отскок": "ждать отскок", "ровная": "шорт", "шум": "нет перевеса"}[zone]
        mode = {"рост": "растёт сильно", "отскок": "глубокое падение", "ровная": "ровная — сползает", "шум": "шум"}[zone]
        b = dict(at=time.time(), board24=round(med, 2), up=round(sum(1 for x in v if x > 0) / len(v) * 100, 1), n=len(v), btc=round(ch.get("BTCUSDT", 0.0), 2), up_level=_up,
                 flat=_flat, deep=_deep, zone=zone, lean=lean, mode=mode, short_flush_at=sf[0] if sf else None, short_flush_usd=round(sf[1]) if sf else None,
                 flush_side="лонг" if med > _up else "шорт")
        _BOARD["v"], _BOARD["t"] = b, time.time()
        tmp = _BOARD_F.with_suffix(".tmp"); tmp.write_text(json.dumps(b, ensure_ascii=False), encoding="utf-8"); tmp.replace(_BOARD_F)
    except Exception:  # noqa: BLE001
        pass


def _board_short_flush():
    """сумма выноса шортов по всем монетам потока за закрытый час ≥ максимума такой суммы за прошлые 7 дней — в последние 6 часов → (час, сек; $) или None"""
    try:
        tot: dict = {}
        for (sym_, sd_), hs in _liq_hourly().items():
            if sd_ != "short":
                continue
            for h, v_ in hs.items():
                tot[h] = tot.get(h, 0.0) + v_
        now_h = int(time.time() * 1000) // 3_600_000 * 3_600_000; best = None
        for h in range(now_h - 6 * 3_600_000, now_h, 3_600_000):          # закрытые часы за последние 6 ч
            prev = [v_ for hh, v_ in tot.items() if h - 7 * 86_400_000 <= hh < h]
            if len(prev) >= 72 and tot.get(h, 0.0) > 0 and tot[h] >= max(prev):
                best = (h // 1000, tot[h])
        return best
    except Exception:  # noqa: BLE001
        return None


def _board24():
    """→ dict(board24, up, n, btc, mode) не старше 6 минут или None (нет данных — правило R54 не применяется, остаётся шорт)"""
    if _BOARD["v"] is None or time.time() - _BOARD["t"] > 360:
        _board_set(get_json("https://fapi.binance.com/fapi/v1/ticker/24hr", weight=40) or [])
    b = _BOARD["v"]
    return b if b and time.time() - b["at"] <= 900 else None


def _fund7_refresh() -> None:
    """средний фандинг за 7 дней по всем перпам: /fapi/v1/fundingRate без символа, страницами по 1000 (≈20 запросов), в фоне, раз в FAST3_FUND7_REFRESH_H часов"""
    try:
        st_ms = int((time.time() - 7 * 86400) * 1000); by: dict = {}
        for _ in range(60):
            r = get_json("https://fapi.binance.com/fapi/v1/fundingRate", {"startTime": st_ms, "limit": 1000}, quiet_400=True) or []
            if not r:
                break
            for x in r:
                by.setdefault(x["symbol"], []).append(float(x["fundingRate"]))
            st_ms = int(r[-1]["fundingTime"]) + 1
            if len(r) < 1000:
                break
            time.sleep(0.5)
        mean = {s_: sum(v) / len(v) * 100 for s_, v in by.items() if s_.endswith("USDT") and len(v) >= 3}
        if len(mean) >= 100:
            d = dict(at=time.time(), mean=mean)
            tmp = _FUND7_F.with_suffix(".tmp"); tmp.write_text(json.dumps(d), encoding="utf-8"); tmp.replace(_FUND7_F)
            _FUND7["v"], _FUND7["t"] = d, time.time()
    except Exception:  # noqa: BLE001
        pass
    finally:
        _FUND7["busy"] = False


def _fund_rank(sym: str):
    """R55: место монеты на доске по среднему фандингу за 7 дней (0 — самый низкий, 1 — самый высокий) → (место, средний фандинг %) или None.
    Кэш в файле; старше FAST3_FUND7_REFRESH_H часов — обновляется в фоне; старше 24 ч или нет монеты — None"""
    try:
        from core_config import FAST3_FUND7_REFRESH_H as _rh
    except ImportError:
        _rh = 4
    d = _FUND7["v"]
    if d is None:
        try:
            d = json.loads(_FUND7_F.read_text(encoding="utf-8")); _FUND7["v"], _FUND7["t"] = d, float(d.get("at") or 0)
        except (OSError, ValueError):
            d = None
    age = time.time() - float(d.get("at") or 0) if d else 1e12
    if age > _rh * 3600 and not _FUND7["busy"]:
        import threading
        _FUND7["busy"] = True; threading.Thread(target=_fund7_refresh, daemon=True).start()
    if not d or age > 86400 or sym not in d["mean"]:
        return None
    uni = set(_all_perps()); vals = sorted(v for s_, v in d["mean"].items() if s_ in uni) or sorted(d["mean"].values()); m = d["mean"][sym]
    return sum(1 for v in vals if v < m) / max(1, len(vals) - 1), m


def _spike_short_plan(sym: str, px: float):
    """R53 + R55: всплеск берём в шорт 5/5, если монета не из лестницы (R47) и её фандинг за 7 дней в нижней половине доски.
    → (вход будет шортом?, причина «не входить» или None, подпись)"""
    try:
        from core_config import FAST3_SPIKE_SHORT as _ss, FAST3_SPIKE_SHORT_FUND_RANK as _fr
    except ImportError:
        _ss, _fr = True, 0.5
    if not _ss or _no_short(sym, px):
        return False, None, ""
    if not _fr:
        return True, None, ""
    r = _fund_rank(sym)
    if r is None:
        return True, "всплеск → шорт не взят: фандинг монеты за 7 дн неизвестен (R55)", ""
    rank, mean = r
    if rank >= _fr:
        return True, f"всплеск → шорт не взят: фандинг монеты в верхней половине доски (7 дн {mean:+.4f}%, место {rank * 100:.0f} из 100) (R55)", ""
    return True, None, f"фандинг 7 дн {mean:+.4f}% — место {rank * 100:.0f} из 100, нижняя половина доски (R55)"


def _rate_ok(now: float, note: bool = False):
    """03.10 владелец: «запрет на открытие ботом больше 5 сделок за 20 минут» — общий счётчик входов обеих книг (файл, переживает перезапуск).
    note=True — записать вход. → None, если можно, иначе подпись отказа"""
    try:
        from core_config import FAST3_MAX_ENTRIES as _mx, FAST3_MAX_ENTRIES_MIN as _wm
    except ImportError:
        _mx, _wm = 5, 20
    try:
        ts = [float(x) for x in json.loads(_RATE_F.read_text(encoding="utf-8"))]
    except (OSError, ValueError):
        ts = []
    ts = [t for t in ts if now - t < _wm * 60]
    if note:
        ts.append(now)
        try:
            _RATE_F.write_text(json.dumps(ts), encoding="utf-8")
        except OSError:
            pass
        return None
    return None if len(ts) < _mx else f"лимит входов: {len(ts)} за {_wm} мин (максимум {_mx})"


def _open_short_now(state: dict, ev: list, msgs: list, sym: str, c: float, t_bar: int, now: float, why: str, book: str, write: bool, side: int = -1, mode: str = "", tgt_abs=None) -> bool:
    """03.10 (R49/R52): позиция по рынку сейчас против хода — стоп 10 %, цель 10 %, безубыток после 5 %, выход по выносу противоположной стороны; ворота — только сессии владельца"""
    nm = "лонг" if side == 1 else "шорт"
    ok, sw, _h = ses_gate(now, t_bar, side)
    if not ok:
        msgs.append(f"{sym[:-4]} {nm} на выносе пропущен: {sw}"); return False
    _rl = _rate_ok(now)
    if _rl:
        msgs.append(f"{sym[:-4]} {nm} на выносе пропущен: {_rl}"); return False
    hold = 7 * 1440                                                      # 03.10 владелец: «выход либо прибыль 10 %, либо вынос лонгов; как только позиция выходит в +5 % — стоп в твх»
    stop, tgt = FAST3_SHORT_SL, FAST3_SHORT_TP
    extra = {}
    if mode == "pump_end":                                               # R58: шорт «конец роста» — цели нет, стоп 10 % не переносится, закрытие по времени
        try:
            from core_config import FAST3_PUMP_END_HOLD_MIN as _ph
        except ImportError:
            _ph = 960
        hold, tgt = _ph, 0.0; extra = dict(pump_end=True)
        why = why + f": цели нет, стоп {stop * 100:.0f}%, после 5 % стоп в твх; через 6 ч стоп в твх или закрытие, если цена выше входа; выход через {_ph // 60} ч · сессия {sw}"
    elif mode == "flat_long":                                            # R70: лонг лимиткой от линии флэта — цель на верх флэта, стоп 10 % (владелец 04.10)
        try:
            from core_config import FAST3_FLAT_LONG_SL as _fsl
        except ImportError:
            _fsl = 0.10
        tgt, stop = float(tgt_abs) / c - 1, _fsl; extra = dict(flat_long=True)
        why = why + f": вход на линии {c:.6g}, цель — верх флэта {float(tgt_abs):.6g} (+{tgt * 100:.1f}%), стоп −{stop * 100:.0f}%, после 5 % стоп в твх, без срока · сессия {sw}"
    elif mode == "long_back":                                            # R59: лонг на выносе лонгов при росте, цена вернулась — цель +5 %, стоп −10 %
        try:
            from core_config import FAST3_LONG_FLUSH_TP as _ltp, FAST3_LONG_FLUSH_SL as _lsl
        except ImportError:
            _ltp, _lsl = 0.05, 0.10
        tgt, stop = _ltp, _lsl
        why = why + f": цель +{tgt * 100:.0f}%, стоп −{stop * 100:.0f}%, без срока · сессия {sw}"
    else:
        _fn = ""
        if side == -1:
            tgt, _fn = _flat_target(sym, c, tgt)                         # R62: во флэте цель шорта — низ флэта
        why = why + f": стоп {stop * 100:.0f}%, цель {tgt * 100:.1f}%, после 5 % стоп в твх, выход по выносу противоположной стороны, без срока · сессия {sw}" + (" · " + _fn if _fn else "")
    pos = dict(sym=sym, side=side, px=c, t_ms=t_bar, at=now, target=round(tgt, 5), stop=round(stop, 5), stop_px=None, hold_min=hold, rule=why, last_px=c, bars=0, flush_short=(side == -1), flush=True, **extra)
    state["open"][sym] = pos
    ev.append(dict(book=book, sym=sym, kind="entry", side=side, px=c, at=now, usd_in=FAST3_SIZE, rule=why, target=pos["target"], stop=pos["stop"], hold_min=hold, fon=fon(), bub=_bub(sym)))
    _rate_ok(now, note=True)
    msgs.append(f"{sym[:-4]} {nm} вход {c:.6g} на выносе · стоп {stop * 100:.0f}% · " + (f"цель {tgt * 100:.0f}%" if tgt else f"без цели, выход через {hold // 60} ч"))
    if write:
        cg(sym, *cg_caption(book, sym, pos))
    return True


def pump_end_walk(e: float, pos: dict, k: list):
    """R58 (03.10 21:50 владелец): шорт «конец роста» — стоп 10 %; после −5 % стоп в точку входа; через FAST3_PUMP_END_BE_MIN (6 ч) — если стоп ещё не в точке входа:
    цена выше входа → закрытие, иначе стоп в точку входа; цели нет (выход по сроку — в step). → (результат без комиссии, причина) или (None, None)"""
    try:
        from core_config import FAST3_PUMP_END_BE_MIN as _bm
    except ImportError:
        _bm = 360
    be = False; stop = float(pos.get("stop") or FAST3_SHORT_SL); n6 = max(1, _bm // 3)
    for n, x in enumerate(k, 1):
        h_, l_, c_ = float(x[2]), float(x[3]), float(x[4])
        if h_ >= (e if be else e * (1 + stop)):
            return (0.0, "стоп в безубыток") if be else (-stop, "стоп")
        if not be and FAST3_SHORT_BE_AT and l_ <= e * (1 - FAST3_SHORT_BE_AT):
            be = True
        if n >= n6 and not be:
            if c_ > e:
                return 1 - c_ / e, f"{_bm // 60} ч после входа цена выше входа — закрытие"
            be = True
    if be:
        pos["stop_px"] = e                                                # мост BingX переставит стоп в точку входа
    return None, None


def pump_end_wait_step(state: dict, book: str, now: float, ev: list, msgs: list, write: bool) -> None:
    """R58 (03.10 21:45 владелец: «поставь брать цену практически на верхе свечи сквиза и всё»; «от чего зависит 4 часа… завтра будет 3, и бот будет всегда на низах шортить»):
    после сквиза «конец роста» шорт берётся не по рынку, а когда цена вернулась к максимуму свечи сквиза — вход по этой цене. Ждём FAST3_PUMP_END_WAIT_H часов.
    Счёт pump_end_r58.py (Binance, месяц, 62 сигнала): вход сразу +0.4 $ на сделку, вход на максимуме свечи +20.6 $ (обе половины месяца), входит 50 из 62."""
    w = state.setdefault("pe_wait", {}); now_ms = int(now * 1000)
    for sym, q in list(w.items()):
        if now > float(q["until"]):
            msgs.append(f"{sym[:-4]} шорт «конец роста»: цена за {int((q['until'] - q['at']) // 3600)} ч не вернулась к верху свечи сквиза {q['level']:.6g} — ожидание снято"); del w[sym]; continue
        if sym in state["open"]:
            continue
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(q["chk"]), "limit": 500}, quiet_400=True) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k:
            continue
        hit = next((x for x in k if float(x[2]) >= float(q["level"])), None)
        q["chk"] = int(k[-1][0]) + 180_000
        if not hit:
            continue
        if _open_short_now(state, ev, msgs, sym, float(q["level"]), int(hit[0]), now, q["why"] + f" · вход на верхе свечи сквиза {q['level']:.6g}", book, write, side=-1, mode="pump_end"):
            del w[sym]


def _manual_no_short(sym: str) -> bool:
    """R47 (02.10 владелец): ручной список лестницы FAST3_NO_SHORT_MANUAL — шорт в этих монетах бот не берёт (и сканером выносов тоже, 04.10)"""
    try:
        from core_config import FAST3_NO_SHORT_MANUAL as _man
    except ImportError:
        _man = []
    return sym in _man


def flush_entries(state: dict, book: str, now: float, ev: list, msgs: list, write: bool) -> None:
    """R52 (03.10 владелец): «если цена больше 10 часов шла в направлении, которое вынесли в итоге сквизом (на росте вынесли лонги, на падении вынесли шорты),
    в такие сделки нужно заходить в обратном направлении»; вместе с R49 (рост + вынос шортов → шорт; падение + вынос лонгов → лонг) — вход ВСЕГДА против хода
    за 10 ч, на рекордном за 24 ч часовом выносе любой стороны, в первые 30 минут после закрытия часа. Открытая позиция по монете закрывается по рынку.
    Один вход на один рекордный час (state["flush_hour"])."""
    seen = state.setdefault("flush_hour", {}); uni = set(_all_perps()); own = _own_mm()
    try:
        pump_end_wait_step(state, book, now, ev, msgs, write)             # R58: ждущие шорты «конец роста» — вход, когда цена вернулась к верху свечи сквиза
    except Exception as e:  # noqa: BLE001
        msgs.append(f"ожидание шорта «конец роста»: сбой {type(e).__name__}: {e}")
    try:
        hs_all = _liq_hourly()
    except Exception:  # noqa: BLE001
        return
    t_bar = int(now * 1000) // 180_000 * 180_000 - 180_000
    for (sym, side) in list(hs_all.keys()):
        if side not in ("short", "long") or sym not in uni or sym in own or _too_young(sym):
            continue
        rec = _flush_record(sym, side, int(seen.get(sym) or 0))
        if not rec:
            continue
        hm, win, prev = rec
        seen[sym] = hm
        p = state["open"].get(sym)
        if p and int(p.get("t_ms") or 0) >= hm:
            continue
        mv, mvp, rng, inf = _move_10h(sym, hm)
        try:
            from core_config import FAST3_FLUSH_BAR_RANGE as _rng
        except ImportError:
            _rng = 20.0
        if _rng and rng < _rng:                                          # 03.10 04:55 владелец: «давай не будем ставить порог разницы цен на свече выноса» — FAST3_FLUSH_BAR_RANGE = 0, порог выключен
            msgs.append(f"{sym[:-4]} вынос {'шортов' if side == 'short' else 'лонгов'} {win / 1e3:.0f}K$ — размах свечи {rng:.1f}% < {_rng:g}%, пропуск"); continue
        try:
            from core_config import FAST3_FLUSH_BAR_MAX as _rmx
        except ImportError:
            _rmx = 8.0
        try:
            from core_config import (FAST3_FLUSH_NEW as _fn, FAST3_PUMP_RISE as _pr, FAST3_GROW_RISE as _gr, FAST3_PUMP_END_MEMORY_H as _pm, FAST3_LONG_FLUSH_BACK as _lb)
        except ImportError:
            _fn, _pr, _gr, _pm, _lb = True, 60.0, 40.0, 24, 5.0
        tk = get_json("https://fapi.binance.com/fapi/v1/ticker/price", {"symbol": sym}, quiet_400=True) or {}
        try:
            c = float(tk.get("price") or 0)
        except (TypeError, ValueError):
            c = 0.0
        if not c:
            continue
        lab = f"вынос {'шортов' if side == 'short' else 'лонгов'} {win / 1e3:.0f}K$"
        kind = ""                                                        # "" — обычная клетка (R52/R54/R57), pump_end — R58, long_back — R59
        p_pe = bool(p and p.get("pump_end") and int(p.get("side", 0)) == -1)
        pe_t = _pump_end_all().get(sym) if _fn else None
        pe_age = (now - float(pe_t)) / 3600 if pe_t else None
        rise = inf.get("rise48") if inf else None
        back = (c / inf["open"] - 1) * 100 if inf and inf.get("open") else None
        if _fn and p_pe:                                                 # открыт шорт «конец роста»: держим до времени, другие выносы его не закрывают и не переворачивают
            if side == "short" and inf.get("rising48") and rise is not None and rise >= _pr:
                _pump_end_set(sym, now)
            msgs.append(f"{sym[:-4]} {lab}: открыт шорт «конец роста» — держим до выхода по времени, сигнал пропущен (R58)"); continue
        if _fn and side == "short" and inf.get("rising48") and rise is not None and rise >= _gr:
            if rise >= _pr:                                              # R58: рост и памп → рекордный вынос шортов = конец движения
                if _manual_no_short(sym):                                # 04.10 20:20 поломка: сканер взял шорт MON (ручной список лестницы, R47 «шорт в этих монетах бот больше не берёт») — в пути сканера списка не было
                    msgs.append(f"{sym[:-4]} {lab}: шорт «конец роста» не взят — монета из списка лестницы владельца (R47)"); continue
                _pump_end_set(sym, now)
                try:
                    from core_config import FAST3_PUMP_END_WAIT_H as _wh
                except ImportError:
                    _wh = 24
                _why = (f"R58 конец роста → шорт: минимумы за 48 ч росли, максимум свечи выноса выше минимума за 48 ч на {rise:.0f}% (памп от {_pr:g}%) · {lab} за час с "
                        f"{datetime.fromtimestamp(hm / 1000, L):%H:%M} UTC — ×{win / prev:.1f} к максимуму часа за сутки ({prev / 1e3:.0f}K$), свеча {rng:.0f}%")
                if p and int(p.get("side", 0)) == 1:                     # в монете открыт лонг — закрыть: движение кончилось
                    e_ = float(p["px"]); res_ = (c / e_ - 1) - FEE; wx = "рекордный вынос шортов в конце роста — лонг закрыт (R58)"
                    ev.append(dict(book=book, sym=sym, kind="exit_long", side=1, px_in=e_, px_out=round(c, 8), opened_at=p["at"], at=now, result_pct=round(res_ * 100, 2), usd=round(FAST3_SIZE * res_, 2), why_exit=wx, rule=p["rule"], size=1.0))
                    msgs.append(f"{sym[:-4]} лонг выход {wx} {res_ * 100:+.2f}%"); state["last_exit"][sym] = now; del state["open"][sym]
                    if write:
                        cg(sym, *cg_caption(book, sym, p, c, wx, res_))
                elif p:
                    msgs.append(f"{sym[:-4]} {lab}: сквиз в конце роста, шорт уже открыт — уровень ожидания не ставим (R58)"); continue
                state.setdefault("pending", {}).pop(sym, None)
                state.setdefault("pe_wait", {})[sym] = dict(level=float(inf["high"]), at=now, until=now + _wh * 3600, chk=hm + 3_600_000, hm=hm, why=_why)
                msgs.append(f"{sym[:-4]} {lab}: конец роста (+{rise:.0f}% за 48 ч) — шорт ждёт возврата цены к верху свечи сквиза {inf['high']:.6g} (сейчас {c:.6g}), до {_wh} ч (R58)"); continue
            else:
                msgs.append(f"{sym[:-4]} {lab}: рост за 48 ч {rise:+.0f}% — просто рост, ждём пампа с выносом (меньше {_pr:g}%), шорт не берём (R58)"); continue
        elif _fn and side == "long" and mv == 1 and back is not None:    # R59: вынос лонгов на росте — смотрим, вернулась ли цена
            if back >= -_lb:
                ban = _pump_ban(sym, now)
                if ban:
                    msgs.append(f"{sym[:-4]} {lab}: {ban}"); continue
                kind = "long_back"
            elif pe_age is not None and pe_age <= _pm and not (p and int(p.get("side", 0)) == -1):
                kind = "pump_end"                                        # цена не вернулась, шорты были выбиты, шорта у бота нет — берём шорт сейчас
            else:
                msgs.append(f"{sym[:-4]} {lab} на росте: цена не вернулась ({back:+.1f}% к цене до выноса, порог −{_lb:g}%), сквиза в конце роста не было — пропуск (R59)"); continue
        if not kind:
            if _rmx and rng >= _rmx:                                     # R57 (03.10 владелец «делай»; LYN 18:00: шорт на дне свечи 29 %): свеча выноса шире 8 % — не входим
                msgs.append(f"{sym[:-4]} {lab} — свеча выноса {rng:.0f}% ≥ {_rmx:g}%, пропуск (R57)"); continue
            if mv == 0:
                msgs.append(f"{sym[:-4]} {lab} (свеча {rng:.0f}%) — минимумы за 24 ч ни росли, ни падали, пропуск"); continue
        new_side = -1 if kind == "pump_end" else (1 if kind == "long_back" else -mv)   # обычная клетка — против хода: рост → шорт, падение → лонг
        if _fn and new_side == 1 and not kind:
            ban = _pump_ban(sym, now)                                    # R60: после сквиза в конце роста лонг не раньше чем через 6 ч
            if ban:
                msgs.append(f"{sym[:-4]} {lab}: {ban}"); continue
        _bnote = ""
        try:
            from core_config import FAST3_FLUSH_BOARD_LONG as _bl, FAST3_FLUSH_BOARD_UP as _bu
        except ImportError:
            _bl, _bu = True, 1.0
        if _bl and new_side == -1 and not kind:                                       # R54 (03.10 владелец: «при росте доски заменяй шорт на лонг»; «делай все»): доска за 24 ч выше +1 % — после выноса на росте лонг, не шорт
            _b = _board24()                                              #   счёт TradingView: часовые 06.09–03.10 шорт −35/−30 $, лонг +26/+24 $ на сделку; 4-часовые 22.06–03.10 −18/−10 и +14/+4; нет данных доски — остаётся шорт
            if _b and _b.get("board24") is not None and _b["board24"] > _bu:
                new_side = 1; _bnote = f" · доска за 24 ч {_b['board24']:+.1f}% (в плюсе {_b['up']:.0f}% монет) растёт → лонг вместо шорта (R54)"
        if new_side == -1 and _manual_no_short(sym):                      # 04.10 20:20: то же для шорта против хода после выноса лонгов на росте и шорта вдогонку (R47, ручной список)
            msgs.append(f"{sym[:-4]} {lab}: шорт не взят — монета из списка лестницы владельца (R47)"); continue
        if new_side == -1 and not kind:
            _ff = _flat5(sym, c)
            if _ff[0]:                                                   # R67: шорт на флэте не берём
                msgs.append(f"{sym[:-4]} {lab}: шорт не взят — флэт, {_flat_txt(sym, _ff)} (R67)")
                _flat_long_set(state, sym, now, msgs, lab); continue      # R70
        if new_side == 1 and _long_window_closed(now):                    # R69
            msgs.append(f"{sym[:-4]} {lab}: лонг не взят — {_long_window_closed(now)}"); continue
        if new_side == 1 and _slide(sym)[0]:                              # R65: минимумы часовых свечей за 3 дня падают — лонг не берём (и сканером тоже)
            msgs.append(f"{sym[:-4]} {lab}: лонг не взят — минимумы часовых свечей за 3 дня падают ({_slide(sym)[2]:+.0f}%), это отскок на сползании (R65)"); continue
        if new_side == 1 and _top72_block(sym, c):                        # R72
            msgs.append(f"{sym[:-4]} {lab}: {_top72_block(sym, c)}"); continue
        note = (f"вынос {'шортов' if side == 'short' else 'лонгов'} {win / 1e3:.0f}K$ за час с {datetime.fromtimestamp(hm / 1000, L):%H:%M} UTC — ×{win / prev:.1f} к максимуму часа за сутки ({prev / 1e3:.0f}K$), "
                f"свеча {rng:.0f}%, минимумы за 24 ч {mvp:+.1f}% → {'шорт' if new_side == -1 else 'лонг'} {'по ходу' if _bnote else 'против хода'}" + _bnote)
        head = "R52 вынос → против хода: "
        if kind == "pump_end" and side == "short":
            head = f"R58 конец роста → шорт: минимумы за 48 ч росли, максимум свечи выноса выше минимума за 48 ч на {rise:.0f}% (памп от {_pr:g}%) · "
        elif kind == "pump_end":
            head = f"R58 конец роста → шорт вдогонку: сквиз был {pe_age:.1f} ч назад, цена после выноса лонгов не вернулась ({back:+.1f}%) · "
        elif kind == "long_back":
            head = f"R59 вынос лонгов на росте → лонг: цена вернулась ({back:+.1f}% к цене до выноса, порог −{_lb:g}%) · "
        if p:                                                            # 04.10 16:25 (BOME: в 16:05 лонг закрыт «перезаходом» по выносу на 3K$, а новый вход не состоялся — окно 15–17 закрыто;
            _gok, _gsw, _ = ses_gate(now, t_bar, new_side)               # позиция закрылась впустую): если новый вход сейчас невозможен (час без входов, лимит входов) — открытую не трогаем
            _grl = None if not _gok else _rate_ok(now)
            if not _gok or _grl:
                msgs.append(f"{sym[:-4]} {lab}: новый вход сейчас закрыт ({_gsw if not _gok else _grl}) — открытую позицию не трогаем"); continue
        if p:
            sd, e = int(p["side"]), float(p["px"]); res = (c / e - 1) * sd - FEE
            why = "рекордный вынос — позиция закрыта" + (" (перезаход)" if sd == new_side else " (разворот)") + ": " + note
            ev.append(dict(book=book, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(c, 8), opened_at=p["at"], at=now,
                           result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * res, 2), why_exit=why, rule=p["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            if write:
                cg(sym, *cg_caption(book, sym, p, c, why, res))
            state["last_exit"][sym] = now; del state["open"][sym]
        state.setdefault("pending", {}).pop(sym, None)
        _open_short_now(state, ev, msgs, sym, c, t_bar, now, head + note, book, write, side=new_side, mode=kind)


def _long_flush(sym: str, now: float):
    return _flush(sym, now, "long")


# ── 28.09 владелец «вноси все правки» (разбор убыточных сделок на Coinglass) — картина вокруг всплеска. Всё не проверено на истории.
#    Г: монета уже кратно выросла от минимума 90 дн (US +656% за 180 дн) — её продавец тянет вверх, шорт от пампа не берём.
#    Базис — снят 29.09 (владелец «базис нахер»): CELO 13:48 — базис −0.16% запретил шорт, а памп и был выносом этих шортов, дальше −10%.
#    Е: «всплеск» — отскок после обвала (SKYAI: −12% за 15 мин до входа) — шорт не берём.
#    Д: на всплеске только что вынесли шорты (SAGA) — лонг не берём; продавец разворачивает — берём шорт (если нет Г).
_D90: dict = {}
try:
    from core_config import FAST3_LONG_TP, FAST3_LONG_SL, FAST3_LONG_HOLD_MIN
except ImportError:
    FAST3_LONG_TP, FAST3_LONG_SL, FAST3_LONG_HOLD_MIN = 0.05, 0.10, 120
try:
    from core_config import FAST3_B_SKIP
except ImportError:
    FAST3_B_SKIP = True
try:                                                                     # 03.10 16:55: флаг R56 не был подключён — NameError на первом всплеске у вершины (поймано пересчётом дня)
    from core_config import FAST3_ZH_OFF_FOR_SPIKE_SHORT
except ImportError:
    FAST3_ZH_OFF_FOR_SPIKE_SHORT = True
try:
    from core_config import FAST3_SHORT_TP, FAST3_SHORT_SL, FAST3_SHORT_HOLD_MIN
    try:
        from core_config import FAST3_SHORT_BE_AT
    except ImportError:
        FAST3_SHORT_BE_AT = 0.05
    try:
        from core_config import FAST3_SHORT_HOLD_BY_SESSION
    except ImportError:
        FAST3_SHORT_HOLD_BY_SESSION = True
except ImportError:
    FAST3_SHORT_TP, FAST3_SHORT_SL, FAST3_SHORT_HOLD_MIN = 0.10, 0.10, 240
    FAST3_SHORT_BE_AT = 0.05
    FAST3_SHORT_HOLD_BY_SESSION = True
try:
    from core_config import FAST3_PUMP_BACK_EXIT, FAST3_LONG_HOLD_TP, FAST3_LONG_HOLD_EXT_MIN, FAST3_FLIP_HOLD_MIN, FAST3_FLIP_HELD_PCT
except ImportError:
    FAST3_PUMP_BACK_EXIT, FAST3_LONG_HOLD_TP, FAST3_LONG_HOLD_EXT_MIN, FAST3_FLIP_HOLD_MIN, FAST3_FLIP_HELD_PCT = True, 0.10, 1440, 360, 0.02


def _run90(sym: str):
    t, v = _D90.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 90}, quiet_400=True) or []
        v = float(k[-1][4]) / min(float(x[3]) for x in k) if len(k) >= 30 and min(float(x[3]) for x in k) > 0 else None
        _D90[sym] = (time.time(), v)
    return v


_H90: dict = {}; _SP7: dict = {}


try:
    from core_config import FAST3_TOP_DAYS as _TOPD
except ImportError:
    _TOPD = 90


def _hi90(sym: str):
    """вершина монеты: максимум за FAST3_TOP_DAYS дней (05.10 владелец: «90 дней это несколько движений уже», «уменьши до 30 дней»; было 90) —
    фьючерс Binance, дневки; кэш 1 ч. Имя функции прежнее."""
    t, v = _H90.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": int(_TOPD)}, quiet_400=True) or []
        v = max(float(x[2]) for x in k) if len(k) >= min(30, int(_TOPD)) else None
        _H90[sym] = (time.time(), v)
    return v


def _spot_cvd7(sym: str):
    """CVD спота Binance за 7 дн, $: сумма (покупки тейкера − продажи тейкера) по 4h-свечам; нет спота — None (кэш 1 ч).
    Coinglass берёт спот всех бирж — здесь только Binance (приближение)."""
    t, v = _SP7.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://api.binance.com/api/v3/klines", {"symbol": sym, "interval": "4h", "limit": 42}, quiet_400=True) or []
        v = sum(2 * float(x[10]) - float(x[7]) for x in k) if len(k) >= 30 else None
        _SP7[sym] = (time.time(), v)
    return v


_LAD: dict = {}


def _ladder_calc(kd: list, px: float):
    """R47 чистый счёт по закрытым дневным барам (последний — вчера): рост ≥ FAST3_LADDER_GROWTH, цена не ушла (px ≥ HOLD·макс30), флэт последних FLAT_DAYS дней ≤ FLAT_MAX.
    → подпись признака или None"""
    try:
        from core_config import FAST3_LADDER_GROWTH as g, FAST3_LADDER_HOLD as hd, FAST3_LADDER_FLAT_DAYS as fd, FAST3_LADDER_FLAT_MAX as fm
    except ImportError:
        g, hd, fd, fm = 1.3, 0.85, 5, 0.20
    if len(kd) < 10 or not px:
        return None
    hi = max(float(x[2]) for x in kd); imax = max(range(len(kd)), key=lambda i: float(kd[i][2]))
    lo = min(float(x[3]) for x in kd[:imax + 1])                       # 02.10 13:40 (проверка): минимум ДО максимума — рост, а не падение с отскоком
    last = kd[-fd:]; flat = max(float(x[2]) for x in last) / min(float(x[3]) for x in last) - 1
    if lo > 0 and hi / lo >= g and px >= hi * hd and flat <= fm:
        return f"R47: рост ×{hi / lo:.2f} за 30 дн, цена держится ({px / hi * 100:.0f}% от максимума), флэт {fd} дн {flat * 100:.0f}% — после роста и флэта шорт не берём"
    return None


def _ladder(sym: str, px: float):
    """R47 (02.10 владелец: «после роста/пампа и флэта цены шорт не берём»): дневные бары раз в час на монету"""
    t, kd = _LAD.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 31}, quiet_400=True) or []
        kd = k[:-1] if len(k) >= 2 else []
        _LAD[sym] = (time.time() if len(kd) >= 10 else time.time() - 3600 + 300, kd)   # 02.10 13:45 (проверка): пустой/битый ответ не держим час — повтор через 5 мин (нет данных ≠ разрешение)
    return _ladder_calc(kd or [], px)


_SLD: dict = {}
_SLH: dict = {}   # R72: максимум часовых свечей за FAST3_SLIDE_H часов (заполняется вместе с _SLD)


def _slide_calc(lows: list):
    """R65 чистый счёт: lows — минимумы закрытых часовых свечей (самые свежие в конце). → (сползание 72 ч?, отскок 24 ч?, ход минимумов за 72 ч %)
    Мерка та же, что у сканера (_move_10h): первая треть против последней — «падают», если и самый высокий, и средний минимум последней трети ниже, чем у первой;
    «растут» — если и самый низкий, и средний минимум последней трети выше."""
    try:
        from core_config import FAST3_SLIDE_H as _sh, FAST3_SLIDE_BOUNCE_H as _bh
    except ImportError:
        _sh, _bh = 72, 24
    if len(lows) < _sh:
        return False, False, 0.0
    w = lows[-_sh:]; n = _sh // 3; f, l = w[:n], w[-n:]; a1, a2 = sum(f) / n, sum(l) / n
    slide = max(l) < max(f) and a2 < a1
    b = lows[-_bh:]; m = _bh // 3; bf, bl = b[:m], b[-m:]
    bounce = min(bl) > min(bf) and sum(bl) > sum(bf)
    return slide, bounce, (a2 / a1 - 1) * 100 if a1 else 0.0


def _slide(sym: str):
    """R65 (04.10 владелец по BR: «брать историю монеты за 3 последних дня на часовых свечах и смотреть лои: если постепенное падение — не брать лонги; это просто отскоки,
    пока не снесёт всех»; «на таких монетах надо брать только шорты на отскоках со стопом 10 % и только на отскоках, не на падении или флэте»).
    → (сползание?, отскок?, ход минимумов %); часовые свечи раз в час на монету; нет данных — (False, False, 0)"""
    try:
        from core_config import FAST3_SLIDE_ON as _on, FAST3_SLIDE_H as _sh
    except ImportError:
        _on, _sh = True, 72
    if not _on:
        return False, False, 0.0
    t, v = _SLD.get(sym, (0, None))
    if time.time() - t > 3600 or v is None:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1h", "limit": _sh + 1}, quiet_400=True) or []
        lows = [float(x[3]) for x in k[:-1]]                             # только закрытые часы
        _SLH[sym] = max([float(x[2]) for x in k[:-1]] or [0.0])
        v = _slide_calc(lows) if len(lows) >= _sh else (False, False, 0.0)
        _SLD[sym] = (time.time() if len(lows) >= _sh else time.time() - 3600 + 300, v)
    return v


def _top72_block(sym: str, px: float) -> str:
    """R72 (06.10 владелец «делай»; счёт 265 лонгов бота 27.09–03.10 по часовым свечам TradingView: цена ближе 20 % к максимуму 72 ч — 71–74 % в минус в обеих половинах недели,
    сумма −155 %; глубже 20 % — в плюс, +42 %): лонг не берём, пока слива от максимума 3 суток нет хотя бы на FAST3_TOP72_PCT %. Нет данных — не блокируем.
    → текст отказа или ''"""
    try:
        from core_config import FAST3_TOP72_ON as _on, FAST3_TOP72_PCT as _pc
    except ImportError:
        _on, _pc = True, 20.0
    if not _on or not px:
        return ""
    _slide(sym)                                                          # прогревает _SLH (тот же запрос часовых свечей, кэш час)
    hi = _SLH.get(sym) or 0.0
    if hi <= 0:
        return ""
    d = (1 - px / hi) * 100
    if d < _pc:
        return f"лонг не взят — цена на {max(d, 0):.0f}% ниже максимума 72 ч ({hi:.6g}), слива на {_pc:g}% ещё не было (R72)"
    return ""


def _slide_zone(sym: str, px: float):
    """зона шорта на сползании по расстоянию цены от вершины FAST3_TOP_DAYS дней (05.10 владелец: «от вершины до 30 % шорт закрывается через 16 часов,
    от 30 до 60 % только шорт на отскоке с целью 10 % и стопом 10 %», «ниже уже никаких сделок»). → (зона 1 / 2 / 3, на сколько % цена ниже вершины);
    вершина неизвестна или цены нет — зона 1 (как было до правки)."""
    try:
        from core_config import FAST3_SLIDE_ZONE1_PCT as _z1, FAST3_SLIDE_ZONE2_PCT as _z2
    except ImportError:
        _z1, _z2 = 30.0, 60.0
    hi = _hi90(sym) if px else None
    if not hi:
        return 1, None
    d = (1 - px / hi) * 100
    return (1 if d <= _z1 else (2 if d <= _z2 else 3)), d


def _slide_gate(state: dict, sym: str, why: str, t_bar: int, now: float, msgs: list, book_note: str = "", px: float = 0.0) -> bool:
    """R65 для сигналов всплеска/выноса на свече (обе книги): монета сползает 3 дня → лонг не берём вовсе; шорт — только на отскоке (отскок — сам всплеск) и только
    через ожидание вершины (как все шорты после вершины): стоп FAST3_SLIDE_SHORT_SL (10 %), цели нет, после хода 5 % стоп в точку входа, выход через FAST3_SLIDE_HOLD_MIN
    (16 ч) — владелец 04.10: «закрытие также через 16 часов, стоп в бу при подходе цены на 5 %». На падении и во флэте — ни лонга, ни шорта. Правило главнее «лестницы» и переворотов. → True, если сигнал обработан здесь (дальше по цепочке не идёт)."""
    sl, bn, mv = _slide(sym)
    if not sl:
        return False
    if sym in _own_mm():
        msgs.append(f"{sym[:-4]} пропущен: свой ММ (список own_mm)"); return True
    # 04.10 05:00 владелец на мою мерку «минимумы суток растут»: «какие растущие минимумы за сутки… отскок это 2–3 часа максимум, а то полчаса: отскочило, лонги зашли,
    # и сквиз для выноса или медленное падение… какие нах сутки» — суточная мерка убрана: отскок — это сам всплеск (свеча вверх на объёме), шорт берётся после его вершины
    try:
        from core_config import FAST3_NO_SHORT_MANUAL as _man
    except ImportError:
        _man = []
    if sym in _man:                                                      # 04.10 08:20 (MEGA: R65 поставил шорт в ожидание в монете из ручного списка лестницы владельца): ручной запрет шорта главнее R65
        msgs.append(f"{sym[:-4]} не взят: монета сползает ({mv:+.0f}% за 3 дня) — лонга нет (R65), а шорт в монетах ручного списка лестницы не берём (R45)"); return True
    _zn, _zd = _slide_zone(sym, px)
    if _zn == 3:                                                         # 05.10: глубже 60 % от вершины — «ниже уже никаких сделок»
        msgs.append(f"{sym[:-4]} не взят: монета сползает ({mv:+.0f}% за 3 дня), цена на {_zd:.0f}% ниже вершины {_TOPD} дн — глубже 60 % сделок нет (R65)"); return True
    _ff = _flat5(sym, 0.0)
    if _ff[0]:                                                           # R67: во флэте шорт не берём, а лонга в сползающей монете нет — сигнал пропускается
        msgs.append(f"{sym[:-4]} не взят: монета сползает ({mv:+.0f}% за 3 дня), лонга нет, а шорт на флэте не берём — {_flat_txt(sym, _ff)} (R65, R67)"); return True
    ok, sw, _ = ses_gate(now, t_bar, -1)
    if not ok:
        msgs.append(f"{sym[:-4]} всплеск пропущен: {sw}"); return True
    if sym not in state.setdefault("pending", {}):
        w = f"R65 сползание 3 дня (минимумы {mv:+.0f}%) → шорт на отскоке, после вершины всплеска · " + why + book_note
        msgs.append(to_pending(state, sym, w, t_bar, now, None)); state["pending"][sym]["slide"] = True
    return True


_H1: dict = {}; _FLATK: dict = {}


def _h1(sym: str) -> list:
    """закрытые часовые свечи монеты (49 штук), раз в час на монету; нет данных — []"""
    t, v = _H1.get(sym, (0, None))
    if time.time() - t > 3600 or v is None:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1h", "limit": 50}, quiet_400=True) or []
        v = k[:-1]
        _H1[sym] = (time.time() if len(v) >= 48 else time.time() - 3600 + 300, v)
    return v or []


def _flat24(sym: str):
    """R70 (04.10 владелец по ENJ — двое суток в коридоре после пампа, бот взял шорт 5/5: «снова шорт на флэте», «должен был быть лонг лимиткой на линии флэта, а не шорт на
    пике»; на предложенную мерку и вход — «да, цель на верх флэта, стоп 10 %»): флэт по суткам — последние 24 закрытых часа целиком внутри диапазона предыдущих 24 часов
    (максимум не выше, минимум не ниже). Линия флэта — минимум последних суток, верх — их максимум. → (флэт?, линия, верх)"""
    k = _h1(sym)
    if len(k) < 48:
        return False, 0.0, 0.0
    a, b = k[-48:-24], k[-24:]
    hi0, lo0 = max(float(x[2]) for x in a), min(float(x[3]) for x in a); hi, lo = max(float(x[2]) for x in b), min(float(x[3]) for x in b)
    return (lo > 0 and hi <= hi0 and lo >= lo0), lo, hi


def _flat_txt(sym: str, ff) -> str:
    """подпись флэта для строки отказа: какой меркой он найден"""
    k = _FLATK.get(sym)
    if k and k[0] == "сутки":
        return f"последние сутки {k[1]:.6g}–{k[2]:.6g} внутри диапазона предыдущих (размах {ff[1] * 100:.0f}%)"
    return f"размах 5 дневных свечей {ff[1] * 100:.0f}%"


def _flat_long_set(state: dict, sym: str, now: float, msgs: list, src: str) -> None:
    """R70: вместо шорта во флэте по суткам ставится ожидание лонга на линии флэта (лимитка): цена коснулась линии — лонг по ней, цель — верх флэта, стоп FAST3_FLAT_LONG_SL.
    Ожидание живёт FAST3_FLAT_LONG_WAIT_H часов. Не ставится в окне без лонгов (R69), в сползающей монете (R65), в «своём ММ» и у молодых листингов."""
    try:
        from core_config import FAST3_FLAT_LONG as _on, FAST3_FLAT_LONG_WAIT_H as _wh
    except ImportError:
        _on, _wh = True, 24
    if not _on or sym in state["open"] or sym in state.setdefault("flat_wait", {}):
        return
    fl, lo, hi = _flat24(sym)
    if not fl or hi <= lo or _long_window_closed(now) or _slide(sym)[0] or sym in _own_mm() or _too_young(sym) or _top72_block(sym, lo):   # R72
        return
    state["flat_wait"][sym] = dict(level=lo, top=hi, at=now, until=now + _wh * 3600, chk=int(now * 1000) // 180_000 * 180_000,
                                   why=f"R70 флэт по суткам ({lo:.6g}–{hi:.6g} внутри диапазона предыдущих суток) → лонг лимиткой от линии флэта {lo:.6g} вместо шорта · сигнал: {src[:120]}")
    msgs.append(f"{sym[:-4]} лонг лимиткой ждёт на линии флэта {lo:.6g} (верх {hi:.6g}, +{(hi / lo - 1) * 100:.1f}%), до {_wh} ч (R70)")


def flat_wait_step(state: dict, book: str, now: float, ev: list, msgs: list, write: bool) -> None:
    """R70: ждущие лонги от линии флэта — вход, когда 3-минутная свеча коснулась линии (цена входа — сама линия, как у лимитного ордера)"""
    w = state.setdefault("flat_wait", {}); now_ms = int(now * 1000)
    for sym, q in list(w.items()):
        if now > float(q["until"]):
            msgs.append(f"{sym[:-4]} лонг от линии флэта: цена не пришла к {q['level']:.6g} — ожидание снято (R70)"); del w[sym]; continue
        if sym in state["open"]:
            continue
        if _long_window_closed(now) or _slide(sym)[0]:
            msgs.append(f"{sym[:-4]} лонг от линии флэта снят: {_long_window_closed(now) or 'монета сползает (R65)'}"); del w[sym]; continue
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(q["chk"]), "limit": 500}, quiet_400=True) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k:
            continue
        hit = next((x for x in k if float(x[3]) <= float(q["level"])), None)
        q["chk"] = int(k[-1][0]) + 180_000
        if not hit:
            continue
        _open_short_now(state, ev, msgs, sym, float(q["level"]), int(hit[0]), now, q["why"], book, write, side=1, mode="flat_long", tgt_abs=float(q["top"]))
        del w[sym]                                                        # коснулась — либо вошли, либо вход был закрыт (час без входов, лимит): уровень отработан


def _flat5(sym: str, px: float):
    """R67 (04.10 владелец по SOLV и INIT — шорты, закрытые в минус правилом шести часов: «вот они и пошли минусы», «туда же», «убери вообще шорты на флэте»):
    флэт — та же мерка, что в R47 и R62: размах FAST3_LADDER_FLAT_DAYS закрытых дневных свечей (максимум / минимум − 1) не больше FAST3_LADDER_FLAT_MAX.
    Во флэте шорт не берётся никакой, кроме «конец роста» (R58). → (флэт?, размах долей); нет данных — (False, 0)"""
    try:
        from core_config import FAST3_NO_FLAT_SHORT as _on, FAST3_LADDER_FLAT_DAYS as fd, FAST3_LADDER_FLAT_MAX as fm
    except ImportError:
        _on, fd, fm = True, 5, 0.25
    if not _on:
        return False, 0.0
    _ladder(sym, px)                                                   # дневные бары в кэше _LAD (раз в час на монету)
    kd = (_LAD.get(sym) or (0, None))[1] or []
    rng = None
    if len(kd) >= fd:
        last = kd[-fd:]; hi = max(float(x[2]) for x in last); lo = min(float(x[3]) for x in last)
        rng = hi / lo - 1 if lo > 0 else None
    if rng is not None and rng <= fm:
        _FLATK[sym] = ("5 дн", None, None)
        return True, rng
    f24, lo24, hi24 = _flat24(sym)                                     # 04.10 17:45 (ENJ): флэт и по суткам — последние 24 часа внутри диапазона предыдущих
    if f24:
        _FLATK[sym] = ("сутки", lo24, hi24)
        return True, hi24 / lo24 - 1
    return False, rng or 0.0


def _flat_target(sym: str, px: float, tgt: float):
    """R62 (04.10 владелец по 1000CAT: шорт во флэте 0.0021–0.0024, цель бота −10 % = 0.00205 ниже дна флэта — «цена ниже флэта и при каких условиях туда дойдём…
    почему тогда цель такая далёкая», «вноси»): если монета во флэте (размах FAST3_LADDER_FLAT_DAYS закрытых дневных свечей ≤ FAST3_LADDER_FLAT_MAX — та же мерка, что в R47),
    вход выше низа флэта и низ ближе обычной цели — цель шорта ставится на низ флэта. НЕ ПРОВЕРЕНО вне выборки; счёт claude/research/flat_target.py на 191 закрытом шорте
    27.09–03.10: правило применимо к 90, до своей цели не дошёл ни один, до низа флэта 4; итог +474 → +517 $, по дням хуже не стало (01.10 +582 → +598, 02.10 −109 → −82).
    → (цель долей, подпись)"""
    try:
        from core_config import FAST3_FLAT_TP as _on, FAST3_LADDER_FLAT_DAYS as fd, FAST3_LADDER_FLAT_MAX as fm
    except ImportError:
        _on, fd, fm = True, 5, 0.25
    if not _on or not px or not tgt:
        return tgt, ""
    _ladder(sym, px)                                                   # дневные бары в кэше _LAD (раз в час на монету)
    kd = (_LAD.get(sym) or (0, None))[1] or []
    if len(kd) < fd:
        return tgt, ""
    last = kd[-fd:]; hi = max(float(x[2]) for x in last); lo = min(float(x[3]) for x in last)
    if lo <= 0 or hi / lo - 1 > fm or px <= lo or lo <= px * (1 - tgt):
        return tgt, ""
    nt = round(1 - lo / px, 5)
    return nt, f"цель — низ флэта {fd} дн {lo:.6g} (−{nt * 100:.1f}%) вместо −{tgt * 100:.0f}% (R62)"


def _no_short(sym: str, px: float):
    """почему шорт в монете не берём: Г (×2+ от минимума 90 дн) · R47 (рост + флэт) · ручной список лестницы. → подпись или None"""
    try:
        from core_config import FAST3_RUN90_X as _rx
    except ImportError:
        _rx = 2.0
    r = _run90(sym)
    if r and r >= _rx:
        return f"монета ×{r:.1f} от минимума 90 дн — её продавец тянет вверх"
    try:
        from core_config import FAST3_NO_SHORT_MANUAL as _man
    except ImportError:
        _man = []
    if sym in _man:
        return "монета из списка лестницы владельца (R45) — шорт не берём"
    return _ladder(sym, px)


def _flip_recheck() -> bool:
    """R64: проверять ли перевёрнутый шорт правилом Б (FAST3_FLIP_RECHECK, по умолчанию да)"""
    try:
        from core_config import FAST3_FLIP_RECHECK as _on
    except ImportError:
        _on = True
    return bool(_on)


def gate_ab(sym: str, sd: int, px: float):
    """29.09 владелец «вноси» — правки А и Б по разбору 125 сделок на Coinglass (НЕ ПРОВЕРЕНО, счёт на тех же днях 27–28.09):
    А: лонг у вершины 90 дн (≤ FAST3_TOP90_PCT% ниже максимума) при споте, продающем 7 дн — не брать (13 сделок, 2 в плюс, −126 $; 27.09 −94, 28.09 −33);
    Б: шорт только у вершины 90 дн; в середине/внизу диапазона — не брать (26 сделок, 10 в плюс, −101 $; 27.09 −81, 28.09 −19).
    → причина «не входить» или None"""
    try:
        from core_config import FAST3_TOP90_PCT as pct
    except ImportError:
        pct = 10.0
    hi = _hi90(sym)
    if not hi:
        return None
    top = px >= hi * (1 - pct / 100)
    if sd == 1:                                                       # 01.10 владелец (MINA, ARK, STX, CAP): Г главнее А/А2 — монета ×2+ от минимума 90 дн, продавец тянет вверх: лонг не переворачиваем (15 А-шортов в таких монетах −122 $, 4 стопа; остальные 22 +192 $)
        try:
            from core_config import FAST3_RUN90_X as _rx
        except ImportError:
            _rx = 2.0
        _r = _run90(sym)
        if _r and _r >= _rx:
            return None
        if _no_short(sym, px):                                        # 02.10 владелец (SAND, MINA, ALICE, LITE): R47 рост+флэт и ручной список лестницы — лонг в шорт не переворачиваем
            return None
    if sd == 1 and top:                                               # 29.09 владелец «да вноси»: А расширена — лонг у вершины 90 дн не берём, спот не смотрим
        cv = _spot_cvd7(sym)                                          # (сделки 27–28.09: лонги у вершины 34 шт., 32% в плюс, −318 $ при 1000 $; сигналы канала 29.09: у вершины 3 из 21 вверх первыми, 7 из 21 вниз)
        return f"А: лонг у вершины {_TOPD} дн ({(px / hi - 1) * 100:+.1f}% от максимума)" + (f", спот за 7 дн {cv / 1e6:+.0f}M$" if cv is not None else "") + " — раздача"
    if sd == 1 and not top:                                           # 30.09 владелец «да»: А расширена — лонг при падающем споте CVD за 7 дн (Binance) тоже переворачивается в шорт
        cv = _spot_cvd7(sym)                                          # (claude/research/trade_facts, 176 сделок 27–30.09, НЕ ПРОВЕРЕНО: 48 таких лонгов −302 $ против +90 $ как шорты, 66% в плюсе)
        if cv is not None and cv < 0:
            return f"А2: лонг при падающем споте за 7 дн ({cv / 1e6:+.1f}M$) — продавцы на споте"
    if sd == -1 and not top:
        return f"Б: шорт не у вершины {_TOPD} дн ({(px / hi - 1) * 100:+.1f}% от максимума) — середина/низ диапазона"
    return None


_OI7: dict = {}; _H30: dict = {}


def _oi7(sym: str):
    """рост интереса Binance (в монетах) за ~7 дн, % (4h-точки openInterestHist; кэш 1 ч); нет данных — None"""
    t, v = _OI7.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "4h", "limit": 43}, quiet_400=True) or []
        try:
            a, b = float(k[0]["sumOpenInterest"]), float(k[-1]["sumOpenInterest"])
            v = (b / a - 1) * 100 if len(k) >= 36 and a > 0 else None
        except (IndexError, KeyError, ValueError):
            v = None
        _OI7[sym] = (time.time(), v)
    return v


def _hi30h(sym: str):
    """максимум последних 30 ч по часовым свечам фьючерса Binance (включая текущий час; кэш 5 мин)"""
    t, v = _H30.get(sym, (0, None))
    if time.time() - t > 300:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1h", "limit": 31}, quiet_400=True) or []
        v = max(float(x[2]) for x in k) if len(k) >= 24 else None
        _H30[sym] = (time.time(), v)
    return v


def gate_new(sym: str, sd: int, px: float):
    """30.09 владелец «делай» (разбор 25 закрытых сделок; НЕ ПРОВЕРЕНО вне выборки) — по итоговой стороне после А/А2:
    шорт при росте интереса за 7 дн ≥ FAST3_SHORT_OI7_MAX % — не брать; лонг ближе FAST3_LONG_NEAR_HI30_PCT % к максимуму 30 ч — не брать.
    → причина «не входить» или None (нет данных — не запрещаем)"""
    try:
        from core_config import FAST3_SHORT_OI7_MAX as oi_max, FAST3_LONG_NEAR_HI30_PCT as near
    except ImportError:
        oi_max, near = 50.0, 3.0
    if sd == -1 and oi_max:
        o = _oi7(sym)
        if o is not None and o >= oi_max:
            return f"В: шорт при росте интереса за 7 дн {o:+.0f}% — ход тянет покупатель"
    if sd == 1 and near:
        h = _hi30h(sym)
        if h and px >= h * (1 - near / 100):
            return f"Ж: лонг у максимума 30 ч ({(px / h - 1) * 100:+.1f}%) — покупка на вершине хода"
    return None


def picture(sym: str, sd: int, why: str, now: float, t_bar: int):
    """→ (сторона: 1 / -1 / 0 — не входить, причина, минимум 20 баров до всплеска — начало пампа)"""
    try:
        from core_config import FAST3_RUN90_X as run_x
    except ImportError:
        run_x = 2.0
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "endTime": t_bar + 179_999, "limit": 22}, quiet_400=True) or []
    pre = [x for x in k if int(x[0]) < t_bar][-20:]
    sp = next((x for x in k if int(x[0]) == t_bar), None)
    start_low = min(float(x[3]) for x in pre) if pre else None
    up_ok = lambda: _no_short(sym, float(sp[4]) if sp else (float(pre[-1][4]) if pre else 0.0))   # noqa: E731  — Г · R47 рост+флэт (02.10) · ручной список лестницы
    if sd == 1:
        fl = _flush(sym, now, "short")
        if fl:                                                        # 03.10 владелец: «вынос шортов — это конец в любом случае лонга… это всегда шорт»; сам шорт даёт flush_entries (рекорд ≥ ×1.3 за сутки)
            return 0, f"лонг не взят: вынос шортов на всплеске ({fl}) — шорт берёт сканер выносов (R49) · " + why, start_low
        return 1, why, start_low
    if sd == -1:
        no = up_ok()
        if no:
            return 1, f"шорт не взят: {no} · " + why, start_low
        if pre and sp and max(float(x[2]) for x in pre) / float(sp[1]) - 1 >= FAST3_SPIKE_SL:
            return 0, f"шорт не взят: всплеск — отскок после обвала (−{(max(float(x[2]) for x in pre) / float(sp[1]) - 1) * 100:.1f}% за час до него) · " + why, start_low
    return sd, why, start_low


def pending_step(state: dict, book: str, now: float, ev: list, msgs: list, write: bool) -> None:
    """ждущие шорты (Б, 28.09): после всплеска ждём вершину — первый закрытый бар, который не обновил максимум и закрылся вниз.
    Вход по его закрытию; стоп — вершина + FAST3_TOP_PAD; цель — начало пампа. Цель ближе стопа — не входим. Ждём до конца сессии всплеска;
    цена ушла ниже начала пампа без нас — ожидание снимаем."""
    try:
        from core_config import FAST3_TOP_PAD as pad
    except ImportError:
        pad = 0.001
    now_ms = int(now * 1000)
    for sym, p in list(state.setdefault("pending", {}).items()):
        if sym in state["open"] or now > p["expire"]:
            del state["pending"][sym]; continue
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(p["t_ms"]), "limit": 200}, quiet_400=True) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if len(k) < 2:
            continue
        top = max(float(x[2]) for x in k); last = k[-1]
        o, h, lo, c = float(last[1]), float(last[2]), float(last[3]), float(last[4])
        if p.get("start_low") and lo <= p["start_low"]:
            msgs.append(f"{sym[:-4]} ожидание шорта снято: цена дошла до начала пампа без входа"); del state["pending"][sym]; continue
        if not (h < top and c < o):
            continue
        # 28.09 владелец (AZTEC, MUBARAK; скрины 27.09): вершину отмечает вынос шортов — продавец добил шорты и разворачивает.
        # С начала всплеска вынесли шортов не меньше, чем самый крупный часовой вынос шортов монеты за сутки до всплеска (поток OKX+Bybit).
        hs = (_liq_hourly().get((sym, "short")) or {})
        t0h = int(p["t_ms"]) // 3_600_000 * 3_600_000
        before = [v for h_, v in hs.items() if t0h - 86_400_000 <= h_ < t0h]
        since = sum(v for h_, v in hs.items() if h_ >= t0h)
        if hs and before and since < max(before):
            continue                                                     # шорты ещё не вынесли — ждём
        sq = (f"вынос шортов {since / 1e3:.1f}K$ с начала всплеска (максимум за сутки до него {max(before) / 1e3:.1f}K$)" if hs and before
              else "ликвидаций по монете в потоке нет — вход только по свече")
        # 29.09 владелец «да»: шорт — стоп +FAST3_SHORT_SL, без цели, срок FAST3_SHORT_HOLD_MIN, выход по выносу лонгов (fuel_exit); стоп за вершиной убран (unified_exit.py)
        stop, tgt = FAST3_SHORT_SL, FAST3_SHORT_TP; _tpnote = ""
        _sld = bool(p.get("slide"))                                       # R65: шорт на отскоке в сползающей монете — стоп и цель свои, «лестница» не запрещает
        if _sld:
            try:
                from core_config import FAST3_SLIDE_SHORT_SL as _ssl65, FAST3_SLIDE_HOLD_MIN as _hold65
            except ImportError:
                _ssl65, _hold65 = 0.10, 960
            stop, tgt = _ssl65, 0.0                                       # 04.10 владелец: «закрытие также через 16 часов, стоп в бу при подходе цены на 5 %» — цели нет
            try:
                from core_config import FAST3_NO_SHORT_MANUAL as _man65
            except ImportError:
                _man65 = []
            if sym in _man65:                                             # ручной список лестницы главнее R65 (ожидания, поставленные до правки 08:20)
                msgs.append(f"{sym[:-4]} шорт на отскоке не взят: монета из ручного списка лестницы владельца (R45)"); del state["pending"][sym]; continue
            if not _slide(sym)[0]:                                        # за время ожидания монета перестала сползать — шорт на отскоке не берём
                msgs.append(f"{sym[:-4]} шорт на отскоке не взят: минимумы за 3 дня больше не падают (R65)"); del state["pending"][sym]; continue
            _zn65, _zd65 = _slide_zone(sym, c)                            # 05.10: зона по цене входа
            if _zn65 == 3:
                msgs.append(f"{sym[:-4]} шорт на отскоке не взят: цена на {_zd65:.0f}% ниже вершины {_TOPD} дн — глубже 60 % сделок нет (R65)"); del state["pending"][sym]; continue
        _flush_short = _sld or "вынос шортов на всплеске → шорт" in p.get("why", "")   # 03.10 владелец (CAP, ALICE «вот тоже»): вынос шортов = конец лестницы — такой шорт идёт мимо Г / R47 / ручного списка
        _ns = (None if _flush_short else _no_short(sym, c)) or _too_young(sym)   # 02.10 13:40 (проверка): перепроверка в момент входа; 03.10: листинг < 180 дн — всегда
        if _ns:
            msgs.append(f"{sym[:-4]} шорт после вершины не взят: {_ns}"); del state["pending"][sym]; continue
        _ff = _flat5(sym, c)
        if _ff[0]:                                                        # R67
            msgs.append(f"{sym[:-4]} шорт после вершины не взят: флэт — {_flat_txt(sym, _ff)} (R67)"); del state["pending"][sym]
            _flat_long_set(state, sym, now, msgs, str(p.get("why", ""))); continue   # R70
        try:                                                              # 02.10 владелец: монета после пампа/роста держит уровень (×2+ от минимума 90 дн) — цель шорта 5 %, не 10 %
            from core_config import FAST3_SHORT_TP_PULLUP as _tp5, FAST3_RUN90_X as _rx
            _r90 = _run90(sym)
            if _r90 and _r90 >= _rx:
                tgt = min(tgt, _tp5); _tpnote = f" · цель 5%: монета ×{_r90:.1f} от минимума 90 дн, продавец тянет вверх"   # 02.10 13:40: раньше здесь было why = why + … до присваивания why → UnboundLocalError (нашла проверка)
        except ImportError:
            pass
        tgt, _fn = _flat_target(sym, c, tgt)                              # R62: во флэте цель шорта — низ флэта
        if _fn: _tpnote += " · " + _fn
        del state["pending"][sym]
        t_bar = int(last[0]); ok, sw, _h = ses_gate(now, t_bar, -1)
        # 30.09 владелец «вноси» (after_exit.py: шорты у вершины 90 дн — после выхода по сроку цена шла ещё +6.2% вперёд, у 65% ≥ 3% за 2 ч; по сроку +21.5%, держать ещё 2 ч +114.6% на 23 сделках, НЕ ПРОВЕРЕНО):
        # срок по часам убран — держим до выноса лонгов (fuel_exit) или стопа; время — только стык сессий (час выхода следующей сессии из ses_gate, R41); FAST3_SHORT_HOLD_MIN — запас, если ses_gate не дал срок
        hold = _h if (_h and FAST3_SHORT_HOLD_BY_SESSION) else FAST3_SHORT_HOLD_MIN
        if _sld and _zn65 == 2:                                           # 05.10: от 30 до 60 % ниже вершины — цель 10 %, стоп 10 % (подтяжки цели R62 и «×2 от минимума» сюда не идут)
            try:
                from core_config import FAST3_SLIDE_ZONE2_TP as _tp65, FAST3_SLIDE_ZONE2_HOLD_MIN as _h65b
            except ImportError:
                _tp65, _h65b = 0.10, 4320
            tgt = _tp65; hold = _h65b
            _tpnote = f" · R65: цена на {_zd65:.0f}% ниже вершины {_TOPD} дн (зона 30–60 %) — цель {_tp65 * 100:.0f} %, стоп {stop * 100:.0f} %, после 5 % стоп в твх, вынос лонгов не закрывает"
        elif _sld:
            hold = _hold65; _tpnote += (f" · R65: цена на {_zd65:.0f}% ниже вершины {_TOPD} дн (зона до 30 %)" if _zd65 is not None else " · R65") + f": цели нет, после 5 % стоп в твх, выход через {_hold65 // 60} ч, вынос лонгов не закрывает"
        if not ok:
            msgs.append(f"{sym[:-4]} шорт после вершины пропущен: {sw}"); continue
        why = p["why"] + f" · вход после вершины {top:.6g} ({sq}): стоп +{stop * 100:.0f}%, выход по выносу лонгов, срок {hold} мин · сессия {sw}" + _tpnote
        _lg = london_gate(sym, now, why)                                     # 02.10 владелец: Лондон — максимум 5 самых надёжных (и для шортов после вершины)
        if _lg:
            msgs.append(f"{sym[:-4]} шорт после вершины пропущен: {_lg}"); continue
        _rl = _rate_ok(now)
        if _rl:
            msgs.append(f"{sym[:-4]} шорт после вершины пропущен: {_rl}"); continue
        stop, _spx, _snote = _range_stop(sym, -1, c, stop)                # 02.10: для шортов возвращает обычный +10 % (FAST3_RANGE_STOP_SHORT=False — владелец по SAND: «с поднятым выше стопом»)
        if _snote: why = why + " · " + _snote
        pos = dict(sym=sym, side=-1, px=c, t_ms=t_bar, at=now, target=round(tgt, 5), stop=round(stop, 5), stop_px=_spx, hold_min=hold, rule=why, last_px=c, bars=0, top=top)
        if _sld: pos["slide"] = True
        if _sld and _zn65 == 2: pos["slide_tp"] = True                    # у шорта на сползании в зоне 30–60 % цель есть
        state["open"][sym] = pos
        ev.append(dict(book=book, sym=sym, kind="entry", side=-1, px=c, at=now, usd_in=FAST3_SIZE, rule=why, target=pos["target"], stop=pos["stop"],
                       hold_min=hold, fon=fon(), bub=_bub(sym)))
        _rate_ok(now, note=True)
        msgs.append(f"{sym[:-4]} шорт вход {c:.6g} · стоп +{stop * 100:.0f}% · выход по выносу лонгов / {hold} мин")
        if write:
            cg(sym, *cg_caption(book, sym, pos))


def to_pending(state: dict, sym: str, why: str, t_bar: int, now: float, start_low) -> str:
    """шорт не сразу — в ожидание вершины до конца текущей сессии"""
    d = datetime.fromtimestamp(now, L)
    _, a, b = next(x for x in SES_WIN if x[1] <= d.hour < x[2])
    end = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=b)
    state.setdefault("pending", {})[sym] = dict(why=why, t_ms=t_bar, at=now, expire=end.timestamp(), start_low=start_low)
    return f"{sym[:-4]} шорт — ждём вершину пампа (до {end:%H:%M} UTC)"


def fuel_exit(sym: str, pos: dict, now: float, c: float):
    """выход по картине (28.09 MUBARAK): лонг — когда вынесли шорты (топливо сожжено), шорт — когда вынесли лонги; только в плюсе"""
    sd, e = int(pos["side"]), float(pos["px"])
    if sd == 1:                                                       # 29.09: лонг — цель +5% / стоп / 2 ч, без выхода по выносу (счёт)
        return None
    if (c - e) * sd <= 0:
        return None
    if str(pos.get("rule", "")).startswith("всплеск → шорт 5/5"):          # 03.10: шорт на всплеске — только цель 5 %, стоп 5 %, срок 24 ч (как в счёте)
        return None
    if pos.get("pump_end") or pos.get("slide"):                          # R58 и R65: шорт «конец роста» и шорт на отскоке вынос лонгов не закрывает — выход по времени
        return None
    since = int(pos["t_ms"])
    if pos.get("flush"):                                                 # 03.10 05:00 (NIGHT 04:00: шорт закрыт через 12 мин «топливом» того же часа, где был сам сквиз): для позиций сканера выносов — только часы ПОСЛЕ часа входа
        since = (since // 3_600_000 + 1) * 3_600_000
    fl = _flush(sym, now, "short" if sd == 1 else "long", since_ms=since)
    return f"топливо сожжено: {fl}" if fl else None


def flip_spike(sd: int, why: str, tp: float, sl: float, hold: int, oi1h, oi_bar=None, crowd=None, flush=None):
    """ПЕРЕВЁРНУТЫЙ ВСПЛЕСК (27.09 владелец: «брать позицию в обратную сторону просто»): всплеск вверх, перед которым интерес за час вырос
    на FAST3_FLIP_OI1H % и больше — толпа уже внутри, всплеск это её выход. Счёт 27.09: 10 таких лонгов −14.8 % (3 в плюс), шорт на тех же
    барах +13.8 % (7 в плюс); остальные 35 лонгов +35 %. Шорт: цель −5 %, стоп +5 %, срок 2 ч."""
    # 28.09 (владелец: «брать обратную сторону»; счёт claude/research/spike_flip.md, 66 лонгов-всплесков 27.09 без заглядывания в будущее):
    # интерес за час ≥ FAST3_FLIP_OI1H (3%) ИЛИ последний закрытый 5-мин бар интереса ≤ FAST3_FLIP_OIBAR_MAX (0) — 44 сделки: лонг −41.8%,
    # шорт +35.1%; остальные 22: лонг +7.4%, шорт −16.0%
    try:
        from core_config import FAST3_FLIP_OI1H as _thr
    except ImportError:
        _thr = 3.0
    try:
        from core_config import FAST3_FLIP_CROWD_MIN as _cmin
    except ImportError:
        _cmin = 1.0
    # 28.09 владелец «все да»: переворот по 5-мин бару интереса ≤ 0 убран (моё правило из ENA/NOM; 9 сделок, 1 в плюс, −74 $; HBAR 06:39 —
    # шорт на старте хода: спот начал покупать, шорты копились неделями, выноса не было) — такой всплеск остаётся лонгом
    flip = sd == 1 and oi1h is not None and oi1h >= _thr
    if flip and flush:                                               # 28.09: лонги только что вынесли — продавец тянет вверх, шорт не берём
        return sd, f"переворот не взят: {flush} · " + why, tp, sl, hold, False
    # 28.09 (QNT 00:27: шорт при толпе 0.60 — интерес набирали шорты, стоп −5.1%, дальше +65% против; счёт spike_flip.md: из 44 переворотов
    # при толпе ≥ 1 — 37, лонг −38.8% / шорт +33.5%; при толпе < 1 — 7, лонг −3.0% / шорт +1.7% — ни одна сторона): переворот только при
    # толпе ≥ FAST3_FLIP_CROWD_MIN, иначе не входим вовсе (sd = 0)
    if flip and crowd is not None and crowd < _cmin:                 # 30.09 владелец: фильтр не закрывает вход — остаётся исходная сторона (лонг)
        return sd, f"переворот отменён: толпа {crowd:.2f} < {_cmin:g} — рост интереса это шорты, остаёмся в лонге · " + why, tp, sl, hold, False
    if sd == 1 and oi1h is not None and oi1h >= _thr:
        return -1, f"перевёрнутый всплеск: интерес +{oi1h:.1f}% за час — толпа уже внутри · " + why, tp, sl, hold, True
    return sd, why, tp, sl, hold, False


RULE_ICON = (("перевёрнутый", "🔄"), ("всплеск", "⚡️"), ("вынос", "💥"), ("сессия", "🕐"), ("пробуждение", "🔎"))


def _rule_lines(rule: str) -> list[str]:
    out = []
    for part in [x.strip() for x in str(rule or "").split(" · ") if x.strip()]:
        ic = next((i for k, i in RULE_ICON if part.lower().startswith(k)), "•")
        out.append(f"{ic} {part}")
    return out


def cg_caption(book: str, sym: str, pos: dict, px_out: float | None = None, why_out: str = "", res: float | None = None) -> tuple[str, list[str]]:
    """подпись скрина и аргументы линий (27.09 владелец: «заголовок ВХОД / ВЫХОД и дальше текст с отступами, смайлами — простыня
    не читаемая»; вход, цель, стоп — отдельными строками)"""
    e, sd = float(pos["px"]), int(pos["side"])
    tgt = e * (1 + sd * float(pos["target"])) if pos.get("target") else None
    stp = e * (1 - sd * float(pos["stop"])) if pos.get("stop") else None
    end = datetime.fromtimestamp((int(pos["t_ms"]) + 180_000) / 1000 + _hold_lim(pos) * 60, L)
    side = "ЛОНГ" if sd == 1 else "ШОРТ"
    t_in = datetime.fromtimestamp(pos["at"], L)
    if px_out is None:
        head = [f"{'🟢' if sd == 1 else '🔻'} ВХОД · {side} · {sym[:-4]}", f"📘 {book}", ""]
        body = [f"💵 вход:   {e:.6g}  ·  {t_in:%H:%M}"]
        if tgt: body.append(f"🎯 цель:   {tgt:.6g}  ({sd * float(pos['target']) * 100:+.1f}%)")
        if stp: body.append(f"🛑 стоп:   {stp:.6g}  ({-sd * float(pos['stop']) * 100:+.1f}%)")
        body.append(f"⏳ срок:   до {end:%H:%M}")
    else:
        mins = int((time.time() - float(pos["at"])) / 60)
        ok = (res or 0) > 0
        head = [f"{'✅' if ok else '❌'} ВЫХОД · {side} · {sym[:-4]} · {res * 100:+.2f}% ({FAST3_SIZE * res:+.0f} $)", f"📘 {book} · {why_out}", ""]
        body = [f"💵 вход:   {e:.6g}  ·  {t_in:%H:%M} UTC", f"🏁 выход:  {px_out:.6g}  ·  {datetime.now(L):%H:%M} UTC"]
        if tgt: body.append(f"🎯 цель:   {tgt:.6g}")
        if stp: body.append(f"🛑 стоп:   {stp:.6g}")
        body.append(f"⏱ в сделке: {mins} мин")
    txt = "\n".join(head + body + [""] + _rule_lines(pos.get("rule") or ""))
    args = ["--entry", f"{e}", "--t-in", f"{pos['at']}"]
    if tgt: args += ["--target", f"{tgt}"]
    if stp: args += ["--stop", f"{stp}"]
    if px_out is not None: args += ["--exit", f"{px_out}", "--t-out", f"{time.time()}"]
    else: args += ["--price"]                       # на входе второй снимок: только цена и линии
    return txt, args


def cg(sym: str, caption: str, extra: list[str] | None = None) -> None:
    """скрин Coinglass (Binance, 3m) в телеграм — отдельным процессом, цикл не ждёт (27.09 владелец; FAST3_CG_SHOTS)"""
    try:
        from core_config import FAST3_CG_SHOTS as _on
    except ImportError:
        _on = True
    if not _on:
        return
    import subprocess
    try:
        lg = open(BASE_DIR / "output" / "cg_shot.log", "a")
        subprocess.Popen([PY, "cg_shot.py", sym, "--caption", caption] + (extra or []), cwd=BASE_DIR, stdout=lg, stderr=subprocess.STDOUT,
                         start_new_session=True)
    except Exception as e:  # noqa: BLE001
        print(f"скрин Coinglass {sym}: {type(e).__name__}: {e}", flush=True)


SES_WIN = (("Токио", 0, 7), ("Лондон", 7, 13), ("Нью-Йорк", 13, 21), ("Сидней", 21, 24))   # часы UTC (06.10; до этого UTC+3: Сидней 0–3, Токио 3–10, Лондон 10–16, Нью-Йорк 16–24)
WDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def ses_gate(now: float, t_bar: int, side: int = 1):
    """R40–R42 для лонга-всплеска: (можно ли входить, причина/сессия, срок в минутах от закрытия бара входа до часа выхода сессии)"""
    try:
        from core_config import FAST3_SES_WAIT_MIN as _w, FAST3_SES_LATE_SKIP_MIN as _late, FAST3_SES_EXIT_H as _ex, FAST3_SKIP_DAYS as _days
    except ImportError:
        return True, "", None
    d = datetime.fromtimestamp(now, L)
    try:
        from core_config import FAST3_NO_ENTRY_HOURS as _nh
    except ImportError:
        _nh = []
    try:
        from core_config import FAST3_NO_ENTRY_SHORTS_TOO as _nst
    except ImportError:
        _nst = False
    for _a, _b in _nh:                                                # 01.10 владелец: час до открытия Лондона (09–10) и НЙ (15–16), UTC+3 — новых входов нет
        if side == -1 and not _nst:                                   # R75 (06.10 владелец: «стыки это сливы, там не шорты нельзя брать, а лонги»): запрет часа перед сессией — только лонгам
            break
        if _a <= d.hour < _b:
            return False, f"торговля выключена за час до открытия сессии ({_a:02d}–{_b:02d} UTC, владелец 01.10)", None
    name, a, b = next(x for x in SES_WIN if x[1] <= d.hour < x[2])
    o = d.replace(hour=a, minute=0, second=0, microsecond=0)
    mins = (d - o).total_seconds() / 60
    if WDAYS[d.weekday()] in _days:
        return False, f"день {WDAYS[d.weekday()]} (R42)", None
    if mins < _w:
        return False, f"первый час сессии {name} (R40)", None
    if (b - a) * 60 - mins <= _late.get(name, 0):
        return False, f"поздно в сессии {name}", None
    end = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=_ex.get(name, b))
    lab = "R41"
    if side:   # 28.09 (KAS): «шорты не должны выходить перед стыком сессий»; (MUBARAK) «выход не по часам, а по картине» — и лонги через стык
        nd = end                                                  # стык: сессия, которая на нём начинается, и её час выхода
        nn = next(x for x in SES_WIN if x[1] <= nd.hour < x[2])
        end = nd.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=_ex.get(nn[0], nn[2]))
        if end <= nd:
            end += timedelta(days=1)
        lab = "R41, через стык сессий"
    hold = int((end.timestamp() * 1000 - (t_bar + 180_000)) // 60_000)
    return (hold >= 3), f"{name}, выход {end:%d.%m %H:%M} UTC ({lab})", hold


def scan(sym: str, want_spike: bool, want_climax: bool):
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": 33}, quiet_400=True) or []
    if len(k) < 33:
        return None
    k = k[:-1]; qv = [float(x[7]) for x in k]; c = [float(x[4]) for x in k]; med = st.median(qv[:-1]); bar = c[-1] / c[-2] - 1
    out = []
    if want_spike and med > 0 and qv[-1] >= FAST3_SPIKE_X * med and qv[-1] >= FAST3_SPIKE_MINQ and bar >= FAST3_SPIKE_PCT:
        out.append((1, f"всплеск: бар {bar * 100:+.2f}% на объёме ×{qv[-1] / med:.1f} ({qv[-1] / 1e3:.0f}K$) (R39)", FAST3_SPIKE_TP, FAST3_SPIKE_SL, FAST3_SPIKE_HOLD_MIN))
    if want_climax and bar >= FAST3_CLIMAX_BAR:
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 3}, quiet_400=True) or []
        ov = [float(x["sumOpenInterestValue"]) for x in oi]
        if len(ov) >= 2 and ov[-1] / ov[-2] - 1 <= FAST3_CLIMAX_OI:
            out.append((-1, f"вынос: бар {bar * 100:+.1f}% и интерес на баре {(ov[-1] / ov[-2] - 1) * 100:+.1f}% — шорты сгорели (R21)", FAST3_CLIMAX_TP, FAST3_CLIMAX_SL, FAST3_CLIMAX_HOLD_MIN))
    if any(o[0] == 1 for o in out):
        _SPK[sym] = int(k[-1][0]) + 180_000                              # 30.09: только запись — метка всплеска для размера пачки
    return sym, c[-1], int(k[-1][0]), out


def _hold_lim(pos: dict) -> int:
    """R74 (06.10 05:30, владелец по ZAMA, висевшей 42 ч: «не должны сделки висеть больше 16 часов»; «3-е суток нужно только от вершины
    пампа оставлять, остальное 16 часов»; на моё прочтение «вторая зона сползания» — «именно его», то есть шорт «конец роста»): срок
    любой позиции не длиннее FAST3_MAX_HOLD_MIN; исключение — шорт «конец роста» от вершины пампа (R58, pump_end), у него свой срок
    3 дня. Зона 30–60 % сползания (R71) — под потолком, 16 ч. 0 в настройке — потолка нет. → срок позиции в минутах"""
    h = int(pos.get("hold_min") or 0)
    try:
        from core_config import FAST3_MAX_HOLD_MIN as cap
    except ImportError:
        cap = 960
    return h if (not cap or pos.get("pump_end")) else min(h, int(cap))


def _short_tgt(pos: dict) -> float:
    """цель шорта при ведении: у шорта на отскоке R65 цели нет (0), у остальных — своя или общая FAST3_SHORT_TP"""
    return 0.0 if (pos.get("slide") and not pos.get("slide_tp")) else float(pos.get("target") or FAST3_SHORT_TP)


def short_walk(e: float, stop: float, tgt: float, k: list, top=None, be_on: bool = True):
    """01.10 владелец «ставь цель 10% или вынос лонгов, при уходе в +5% стоп в вх»: шорт по 3-мин барам от входа по порядку —
    стоп +stop → цель −tgt → после касания −FAST3_SHORT_BE_AT стоп переносится на вход (безубыток). → (результат от входа без комиссии, причина) или (None, None)"""
    be = False
    try:
        from core_config import FAST3_SHORT_EXIT_ABOVE_TOP as _above
    except ImportError:
        _above = True
    for x in k:
        h_, l_, c_ = float(x[2]), float(x[3]), float(x[4])
        if h_ >= (e if be else e * (1 + stop)):
            return (0.0, "стоп в безубыток") if be else (-stop, "стоп")
        if _above and top and c_ > top:                                   # 02.10 владелец (SAND): «цена пошла выше — сразу закрытие, не ждём стопов»
            return 1 - c_ / e, f"цена выше вершины входа {top:.6g}"
        if tgt and l_ <= e * (1 - tgt):
            return tgt, "цель"
        if be_on and not be and FAST3_SHORT_BE_AT and l_ <= e * (1 - FAST3_SHORT_BE_AT):
            be = True
    return None, None


def _ladder_top(sym: str, pos: dict):
    """02.10 владелец («по таким шортам … цена пошла выше — сразу закрытие, не ждём стопов»): вершина входа для выхода шорта — только в монетах лестницы
    (Г / R47 рост+флэт / ручной список), т.е. для шортов, открытых до правки; на всех шортах счёт 110 сделок: +606 → +135 $ (sim_top2.py) — шире не применяем"""
    try:
        if pos.get("slide"):                                             # R65: шорт на отскоке держит свой стоп 10 %, вершина входа его не закрывает
            return None
        if pos.get("ladder") or _no_short(sym, float(pos.get("px") or 0)):
            return _top_of(pos)
    except Exception:  # noqa: BLE001
        return None
    return None


def flush_long_walk(e: float, pos: dict, k: list):
    """R52 (03.10): лонг против падения на рекордном выносе — стоп −stop, цель +target, после +FAST3_SHORT_BE_AT стоп в точку входа"""
    be = False; stop = float(pos.get("stop") or FAST3_SHORT_SL); tgt = float(pos.get("target") or FAST3_SHORT_TP)
    for x in k:
        h_, l_ = float(x[2]), float(x[3])
        if l_ <= (e if be else e * (1 - stop)):
            return (0.0, "стоп в безубыток") if be else (-stop, "стоп")
        if h_ >= e * (1 + tgt):
            return tgt, "цель"
        if not be and FAST3_SHORT_BE_AT and h_ >= e * (1 + FAST3_SHORT_BE_AT):
            be = True; pos["stop_px"] = e
    return None, None


def _top_of(pos: dict):
    """вершина, после которой взят шорт: pos["top"] или число из подписи «вход после вершины X» (позиции до 02.10)"""
    if pos.get("top"):
        return float(pos["top"])
    m = re.search(r"вход после вершины ([0-9.eE+-]+)", str(pos.get("rule", "")))
    try:
        return float(m.group(1)) if m else None
    except ValueError:
        return None


_RNG: dict = {}


def _range_stop(sym: str, side: int, e: float, default_pct: float):
    """02.10 владелец (COAI: «стоп должен быть 0.266 — там, где ты хотел, стоят стопы других»): входной стоп — за пределами диапазона FAST3_STOP_RANGE_DAYS дней:
    лонг — низ диапазона × (1 − FAST3_STOP_RANGE_MARGIN), шорт — максимум × (1 + …). Если край диапазона дальше FAST3_STOP_RANGE_MAX от входа — обычный стоп default_pct.
    → (доля стопа от входа, цена стопа, подпись)"""
    try:
        from core_config import FAST3_STOP_RANGE_DAYS as nd, FAST3_STOP_RANGE_MARGIN as mg, FAST3_STOP_RANGE_MAX as mx
    except ImportError:
        nd, mg, mx = 30, 0.027, 0.25
    try:
        from core_config import FAST3_RANGE_STOP_SHORT as _rss
    except ImportError:
        _rss = False
    if side == -1 and not _rss:                                        # 02.10 владелец (SAND −13.5 %: «ещё и с поднятым выше стопом»): шорт — обычный стоп, за диапазон не выносим (и без запроса дневок)
        return default_pct, e * (1 - side * default_pct), ""
    t, v = _RNG.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": nd + 1}, quiet_400=True) or []
        v = (min(float(x[3]) for x in k[:-1]), max(float(x[2]) for x in k[:-1])) if len(k) >= 8 else None
        _RNG[sym] = (time.time(), v)
    if not v:
        return default_pct, e * (1 - side * default_pct), ""
    lo, hi = v
    edge = lo * (1 - mg) if side == 1 else hi * (1 + mg)
    dist = (e - edge) / e if side == 1 else (edge - e) / e
    if dist <= 0 or dist > mx:
        return default_pct, e * (1 - side * default_pct), ""
    return round(dist, 5), edge, f"стоп за диапазоном {nd} дн: {edge:.6g} ({'низ' if side == 1 else 'верх'} {lo if side == 1 else hi:.6g} {'−' if side == 1 else '+'}{mg * 100:.1f}%)"


_LON = {"day": "", "n": 0}


def london_gate(sym: str, now: float, why: str):
    """02.10 владелец: «на Лондоне максимум 5 сделок самых надёжных» → в FAST3_LONDON_HOURS (UTC+3) вход только если объём всплеска ≥ ×FAST3_LONDON_SPIKE_X медианы
    и интерес за 7 дн ≥ 0, и входов за эту сессию (обе книги) < FAST3_LONDON_MAX. → причина отказа или None; счётчик — output/london_count.json"""
    import re
    try:
        from core_config import FAST3_LONDON_HOURS as hh, FAST3_LONDON_MAX as mx, FAST3_LONDON_SPIKE_X as sx
    except ImportError:
        hh, mx, sx = (11, 15), 5, 10.0
    d = datetime.fromtimestamp(now, L)
    if not (hh[0] <= d.hour < hh[1]):
        return None
    try:
        from core_config import FAST3_LONDON_DAYS as _ld
    except ImportError:
        _ld = ["пн", "вт"]
    if _ld and WDAYS[d.weekday()] not in _ld:                          # 06.10 владелец: «максимум 5 входов на лондоне в понедельник и вторник» — в остальные дни лондонского ограничения нет
        return None
    m = re.search(r"объёме ×([\d.]+)", why or "")
    x = float(m.group(1)) if m else 0.0
    if x < sx:
        return f"Лондон: всплеск ×{x:.1f} < ×{sx:g} — не из самых надёжных"
    o7 = _oi7(sym)
    if o7 is not None and o7 < 0:
        return f"Лондон: интерес за 7 дн {o7:+.0f}% — не из самых надёжных"
    p = BASE_DIR / "output" / "london_count.json"
    try:
        c = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        c = {"day": "", "n": 0}
    if c.get("day") != d.strftime("%Y-%m-%d"):
        c = {"day": d.strftime("%Y-%m-%d"), "n": 0}
    if c["n"] >= mx:
        return f"Лондон: уже {c['n']} входов из {mx}"
    c["n"] += 1
    try:
        p.write_text(json.dumps(c), encoding="utf-8")
    except OSError:
        pass
    return None


def _pump_open(e: float, rule: str):
    """открытие бара всплеска по записи входа («бар +1.44%»): цена входа — закрытие этого бара"""
    import re
    m = re.search(r"бар \+([\d.]+)%", rule or "")
    return e / (1 + float(m.group(1)) / 100) if m else None


def long_walk(e: float, pos: dict, k: list):
    """01.10 владелец (NIGHT, CBRS): лонг по 3-мин барам от входа.
    Фаза 1 (первые FAST3_LONG_HOLD_MIN мин): стоп −FAST3_LONG_SL → цель +FAST3_LONG_TP → памп вернулся (закрытие бара ниже открытия бара всплеска) → выход сразу.
    На исходе фазы 1: закрытие ≥ входа → удержался: цель FAST3_LONG_HOLD_TP, стоп — низ первых 2 ч, срок FAST3_LONG_HOLD_EXT_MIN; иначе — выход «срок», как было.
    Фаза 2 (и сразу — для лонга-переворота, pos["held"]): стоп на низу удержания → цель. → (результат от входа без комиссии, причина) или (None, None)."""
    n1 = max(1, int(pos.get("hold1_min") or FAST3_LONG_HOLD_MIN) // 3)
    i0 = 0 if pos.get("flip") else n1                                  # удержанный лонг: фаза 2 — только бары ПОСЛЕ окна удержания (его низ = стоп); переворот — бары идут от бара переворота
    if not pos.get("held"):
        po = pos.get("pump_open") or _pump_open(e, pos.get("rule", ""))
        for x in k[:n1]:
            h_, l_, c_ = float(x[2]), float(x[3]), float(x[4])
            if l_ <= e * (1 - pos["stop"]):
                return -pos["stop"], "стоп"
            if h_ >= e * (1 + pos["target"]):
                return pos["target"], "цель"
            if FAST3_PUMP_BACK_EXIT and po and c_ < po:
                return c_ / e - 1, "памп вернулся"
        if len(k) < n1:
            return None, None
        c_end = float(k[n1 - 1][4])
        if c_end < e:
            return c_end / e - 1, f"срок {n1 * 3} мин"
        lowest = min(float(x[3]) for x in k[:n1])
        pos.update(held=True, hold1_min=n1 * 3, stop_px=lowest, stop=round(max(1e-6, 1 - lowest / e), 5), target=FAST3_LONG_HOLD_TP, hold_min=FAST3_LONG_HOLD_EXT_MIN,
                   rule=pos.get("rule", "") + f" · удержался {n1 * 3} мин: цель +{FAST3_LONG_HOLD_TP * 100:.0f}%, стоп на низу {lowest:.6g}")
        i0 = n1
    sp = float(pos.get("stop_px") or e * (1 - pos["stop"]))
    for x in k[i0:]:
        h_, l_ = float(x[2]), float(x[3])
        if l_ <= sp:
            return sp / e - 1, "стоп на низу удержания"
        if h_ >= e * (1 + pos["target"]):
            return pos["target"], "цель"
    return None, None


def flip_check(e: float, pos: dict, k: list, now: float):
    """01.10 владелец (ALICE, CAP): шорт, в который А/А2 перевернули лонг у вершины, держится FAST3_FLIP_HOLD_MIN — цена ни разу не ушла ниже входа на FAST3_FLIP_HELD_PCT
    и стоп/цель/безубыток за окно не сработали → шорт закрыт по закрытию последнего бара окна, новый лонг с целью FAST3_LONG_HOLD_TP и стопом на низу окна.
    → (результат шорта, причина, новая позиция) или (None, None, None)"""
    nf = max(1, FAST3_FLIP_HOLD_MIN // 3)
    if _top72_block(pos["sym"], float(k[min(len(k), nf) - 1][4]) if k else 0.0):           # R72: слива от максимума 72 ч ещё не было — шорт в лонг не переворачиваем
        return None, None, None
    if _slide(pos["sym"])[0] or _long_window_closed(now):                # R65: монета сползает — переворота шорта в лонг нет; R69: и в окне без лонгов
        return None, None, None
    if pos.get("flip") or not str(pos.get("rule", "")).startswith("А") or len(k) < nf:
        return None, None, None
    r, _ = short_walk(e, pos["stop"], _short_tgt(pos), k[:nf], _ladder_top(pos["sym"], pos))
    if r is not None:
        return None, None, None
    lowest = min(float(x[3]) for x in k[:nf])
    if lowest <= e * (1 - FAST3_FLIP_HELD_PCT):
        return None, None, None
    c_f = float(k[nf - 1][4])
    newpos = dict(sym=pos["sym"], side=1, px=c_f, t_ms=int(k[nf - 1][0]), at=now, target=FAST3_LONG_HOLD_TP, stop=round(max(1e-6, 1 - lowest / c_f), 5), stop_px=lowest,
                  hold_min=FAST3_LONG_HOLD_EXT_MIN, held=True, flip=True, last_px=c_f, bars=0,
                  rule=f"переворот: шорт держался {nf * 3} мин (цена не уходила ниже входа на {FAST3_FLIP_HELD_PCT * 100:.0f}%) — лонг, цель +{FAST3_LONG_HOLD_TP * 100:.0f}%, стоп на низу {lowest:.6g} · было: " + str(pos.get("rule", ""))[:220])
    return 1 - c_f / e, f"переворот в лонг: шорт держится {nf * 3} мин", newpos


_K3C: dict = {}


def _k3_since(sym: str, t_ms: int, now_ms: int) -> list:
    """закрытые 3-мин свечи позиции от t_ms до сейчас. 04.10 (поломка кода, найдена при внесении R66): раньше брался ОДИН запрос на 1000 свечей от входа — это 50 часов;
    у позиции старше 50 часов новые свечи в ответ не попадали, и стоп, цель, срок и цена «сейчас» переставали обновляться (сканерные позиции держатся до 7 дней).
    Теперь закрытые свечи копятся в памяти, каждый проход досылаются только новые (и запросы к Binance стали легче)."""
    key = (sym, int(t_ms)); c = _K3C.get(key) or []
    for _ in range(6):
        start = (int(c[-1][0]) + 180_000) if c else int(t_ms)
        if start + 180_000 > now_ms:
            break
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": start, "limit": 1000}, quiet_400=True, weight=5) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms and int(x[0]) >= start]
        if not k:
            break
        c = c + k
        if len(k) < 900:
            break
    if c:
        _K3C[key] = c
        if len(_K3C) > 300:                                              # закрытые позиции из кэша уходят сами: держим последние
            for kk in list(_K3C)[:100]:
                _K3C.pop(kk, None)
    return [x for x in c if int(x[0]) + 180_000 <= now_ms]


def _stall_exit(pos: dict, k: list, now: float, c: float):
    """R66 (04.10 владелец по SUPER, NIGHT, NMR: «такие шорты надо закрывать, если после выноса цена стоит больше 6 часов»; «все шорты, что висят больше 6 часов, уже под
    вопросом, а если ещё цена стояла практически во флэте (в случае NIGHT вернулась после небольшого падения) — это закрытие сразу по рынку, если минус, если плюс — то стоп
    в твх»): шорт старше FAST3_STALL_H часов, минимум с входа не обновлялся столько же часов («цена стоит») → в минусе закрывается по рынку, в плюсе стоп переносится в точку
    входа. Все шорты, кроме «конец роста» (R58 — у него такое же своё правило шести часов). С 06:00 возраст минимума не проверяется: достаточно, что шорту 6 часов.
    → ("close", причина) / ("be", подпись) / None"""
    try:
        from core_config import FAST3_STALL_H as _sh
    except ImportError:
        _sh = 6
    if not _sh or not k or int(pos.get("side", 0)) != -1 or pos.get("pump_end"):
        return None
    if now - float(pos.get("at") or now) < _sh * 3600:
        return None
    # 04.10 06:00 (MUBARAK: вход 23:00, минимум в 23:57, дальше цена стояла выше входа; моё добавочное условие «минимум не обновлялся 6 часов» отложило закрытие с 05:00
    # до 05:57, а там случился вынос — −6.1 % вместо примерно −3 %): условия про возраст минимума больше нет. Шорту исполнилось 6 часов → в минусе закрытие, в плюсе стоп в твх —
    # как сказал владелец и как у шорта «конец роста» (R58).
    i = min(range(len(k)), key=lambda j: float(k[j][3])); t_low = int(k[i][0]) / 1000 + 180
    e = float(pos["px"]); tail = f"лучшая цена {float(k[i][3]):.6g} была {datetime.fromtimestamp(t_low, L):%d.%m %H:%M} UTC"
    if c > e:
        return "close", f"шорт висит больше {_sh:g} ч и в минусе ({tail}) — закрытие по рынку (R66)"
    if pos.get("be_from") or (pos.get("stop_px") and abs(float(pos["stop_px"]) / e - 1) < 1e-9):
        return None                                                      # стоп уже в точке входа
    return "be", f"шорт висит больше {_sh:g} ч, позиция в плюсе ({tail}) — стоп в точку входа (R66)"


def _long_window_closed(now: float):
    """R69 (04.10 владелец, окончательно: «давай даже не так: в воскресенье лонги закрываем за 2 часа до закрытия Нью-Йорка, открывать лонги можно только со вторника через час
    после открытия Нью-Йорка»; до этого — «все лонги закрывать на Сиднее через 2 часа после начала сессии в воскресенье», «не должны открываться до понедельника…»):
    по часам бота (с 06.10 — UTC: воскресенье 19:00 → вторник 14:00; ниже слова владельца в московских часах) с воскресенья 22:00 (Нью-Йорк закрывается в 24:00, минус FAST3_SUNDAY_CLOSE_BEFORE_NY_END_H) до вторника 17:00 (Нью-Йорк открывается в 16:00, плюс
    FAST3_LONG_OPEN_AFTER_NY_H) лонгов нет: открытые закрываются по рынку, новые не берутся (всплеск, сканер, перевороты шорта в лонг). Шорты не затронуты.
    На истории не считалось. → подпись окна или None"""
    try:
        from core_config import FAST3_SUNDAY_LONG_CLOSE as _on, FAST3_SUNDAY_CLOSE_BEFORE_NY_END_H as _h, FAST3_LONG_OPEN_AFTER_NY_H as _m
    except ImportError:
        _on, _h, _m = True, 2, 1
    if not _on:
        return None
    d = datetime.fromtimestamp(now, L); hh = d.hour + d.minute / 60
    ny = next(x for x in SES_WIN if x[0] == "Нью-Йорк"); a = ny[2] - _h; b = ny[1] + _m
    if (d.weekday() == 6 and hh >= a) or d.weekday() == 0 or (d.weekday() == 1 and hh < b):
        return f"лонги закрыты с воскресенья {int(a):02d}:00 до вторника {int(b):02d}:00 UTC (R69)"
    return None


def _sunday_close(pos: dict, now: float):
    """R69: открытый лонг в окне «воскресенье 22:00 → вторник 17:00» закрывается по рынку. → причина выхода или None"""
    if int(pos.get("side", 0)) != 1:
        return None
    w = _long_window_closed(now)
    return f"все лонги закрываются: {w}" if w else None


def _stall_flip(pos: dict, k: list, now: float, c: float):
    """R68 (04.10 владелец по MUBARAK — шорт сканера 6 часов не шёл и закрыт в минус, а цена ушла дальше вверх: «надо такие шорты в лонги переворачивать», «сделать ещё правило
    для лонгов по этому принципу, по тому что брались шорты»; 14:20 «ты сделал, чтобы шорты переворачивались в лонги?»): шорт, закрытый правилом шести часов в минусе (R66),
    переворачивается в лонг по той же цене. Параметры — как у уже существующего переворота шорта у вершины (flip_check, владелец 01.10): цель FAST3_LONG_HOLD_TP (+10 %),
    стоп на минимуме часов, пока висел шорт, срок FAST3_LONG_HOLD_EXT_MIN (сутки). Лонга нет, если монета сползает (R65) или после сквиза «конец роста» не прошло 6 часов (R60).
    Счёт claude/research/short6h_flip.py (26 шортов, три дня): закрыть на шестом часу −495 $, лонг после закрытия +551 $ (шорты А/А2 19 сделок +667 $, прочие 7 сделок −115 $).
    → новая позиция или None"""
    try:
        from core_config import FAST3_STALL_FLIP as _on
    except ImportError:
        _on = True
    sym = pos["sym"]
    if not _on or not k or _slide(sym)[0] or _pump_ban(sym, now) or _long_window_closed(now) or _top72_block(sym, c):   # R72
        return None
    lowest = min(float(x[3]) for x in k)
    if lowest <= 0 or c <= lowest:
        return None
    return dict(sym=sym, side=1, px=c, t_ms=int(k[-1][0]), at=now, target=FAST3_LONG_HOLD_TP, stop=round(max(1e-6, 1 - lowest / c), 5), stop_px=lowest,
                hold_min=FAST3_LONG_HOLD_EXT_MIN, held=True, flip=True, last_px=c, bars=0,
                rule=f"R68 переворот: шорт висел больше 6 ч и был в минусе — лонг от цены закрытия, цель +{FAST3_LONG_HOLD_TP * 100:.0f}%, стоп на минимуме этих часов {lowest:.6g} · было: " + str(pos.get("rule", ""))[:220])


_OTHER = {}   # R63: книга → вторая книга (её состояние и имя); заполняется в main


def _x2_exits(state: dict, ev: list) -> None:
    """R63: выход по удвоенной позиции — результат считается по двум половинам: вторая (ведущая) — как посчитал выход, первая — от своего входа px0 до той же цены выхода"""
    x2 = state.get("x2") or {}
    for r in ev:
        if str(r.get("kind", "")).startswith("exit") and r.get("sym") in x2:
            a = x2.pop(r["sym"]); sd = int(r["side"]); e0 = float(a["px0"]); out = float(r["px_out"]); r1 = float(r["result_pct"]) / 100
            r0 = (out / e0 - 1) * sd                                      # комиссия уже сидит в px_out
            r.update(usd=round(FAST3_SIZE * (r1 + r0), 2), result_pct=round((r1 + r0) / 2 * 100, 2), size=2.0, usd_in=FAST3_SIZE * 2, px_in0=e0,
                     px_in=round((float(r["px_in"]) + e0) / 2, 10), res_first=round(r0 * 100, 2), res_second=round(r1 * 100, 2), book0=a.get("book0"))
    for s_ in [s_ for s_ in x2 if s_ not in state["open"]]:
        x2.pop(s_)


def _one_position(state: dict, book: str, ev: list, msgs: list, now: float, write: bool) -> None:
    """R63 (04.10 владелец по AIN: «не должно быть 2-х одинаковых сделок, если 2 стратегии одновременно — позиция ×2»; «если сделка открывается следующая в противоположном
    направлении, то закрываем текущую и открываем новую»; «если 2 в одном направлении, то смотрим по цене: если не ушла более чем на 2 %, то добираем с целью 2-й сделки,
    а не 1-й»): одна монета — одна позиция на обе книги. Вызывается в конце прохода книги по её новым входам, когда во второй книге монета уже открыта:
      • в другую сторону — позиция второй книги закрывается по цене нового входа, новая остаётся;
      • в ту же сторону и цена от первого входа ушла не больше FAST3_ADD_MAX_MOVE (2 %) — позиции сливаются: дальше её ведёт новая (вторая) сделка со своей целью, стопом
        и сроком, размер ×2 (первая половина — по цене первого входа, state["x2"]); из первой книги позиция уходит событием merge без результата;
      • в ту же сторону, но цена ушла дальше, или позиция уже ×2 — новый вход отменяется.
    НЕ ПРОВЕРЕНО на истории: счёта нет, это устройство позиции по слову владельца."""
    try:
        from core_config import FAST3_ONE_POSITION as _on, FAST3_ADD_MAX_MOVE as _mv
    except ImportError:
        _on, _mv = True, 0.02
    o = _OTHER.get(book)
    if not _on or not o:
        return
    ost, obook = o["state"], o["book"]; oev = []
    for r in [r for r in ev if r.get("kind") == "entry"]:
        sym = r["sym"]; op = ost["open"].get(sym); pos = state["open"].get(sym)
        if not op or not pos:
            continue
        sd = int(r["side"]); px = float(r["px"]); e0 = float(op["px"]); osd = int(op["side"]); nm = "лонг" if sd == 1 else "шорт"
        if osd != sd:                                                     # встречный сигнал: старую закрываем, новая остаётся
            res = (px / e0 - 1) * osd - FEE
            x = dict(book=obook, sym=sym, kind="exit_long" if osd == 1 else "exit_short", side=osd, px_in=e0, px_out=round(e0 * (1 + res * osd), 8), opened_at=op["at"], at=now,
                     result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * res, 2), why_exit=f"встречный сигнал: «{book}» открывает {nm} (R63)", rule=op["rule"], size=1.0)
            del ost["open"][sym]; ost.setdefault("last_exit", {})[sym] = now
            _x2_exits(ost, [x]); oev.append(x)
            msgs.append(f"{sym[:-4]} {nm}: в «{obook}» был {'лонг' if osd == 1 else 'шорт'} — закрыт встречным сигналом {res * 100:+.2f}% (R63)")
            continue
        mv = abs(px / e0 - 1)
        if (ost.get("x2") or {}).get(sym) or float(op.get("size") or 1) >= 2 or mv > _mv:
            del state["open"][sym]; ev.remove(r)
            why_ = "позиция уже ×2" if mv <= _mv else f"цена ушла от входа {e0:.6g} на {mv * 100:.1f}% (больше {_mv * 100:g}%)"
            msgs.append(f"{sym[:-4]} {nm} не добран: в «{obook}» уже открыт {nm}, {why_} (R63)")
            continue
        note = f"R63: добор к {nm}у «{obook}» (вход {e0:.6g}, цена ушла на {mv * 100:.1f}%) — размер ×2, цель и стоп этой сделки"
        pos["size"] = 2.0; pos["px0"] = e0; pos["at0"] = op["at"]; pos["rule"] = str(pos.get("rule") or "") + " · " + note
        state.setdefault("x2", {})[sym] = dict(px0=e0, at0=op["at"], book0=obook, rule0=op.get("rule"))
        r["x2"] = True; r["px0"] = e0; r["size"] = 2.0; r["rule"] = pos["rule"]
        oev.append(dict(book=obook, sym=sym, kind="merge", side=sd, px_in=e0, px=px, opened_at=op["at"], at=now, to=book, rule=op.get("rule")))
        del ost["open"][sym]; (ost.get("x2") or {}).pop(sym, None)
        msgs.append(f"{sym[:-4]} {nm}: добор к позиции «{obook}» (вход {e0:.6g}) — размер ×2, цель этой сделки (R63)")
    if oev and write:
        olog, ofile = (WAKE_LOG, WAKE_STATE) if obook == WAKE_BOOK else (LOG, STATE)
        with olog.open("a", encoding="utf-8") as f:
            for x in oev:
                f.write(json.dumps(x, ensure_ascii=False) + "\n")
        tmp = ofile.with_suffix(".tmp"); tmp.write_text(json.dumps(ost, ensure_ascii=False), encoding="utf-8"); tmp.replace(ofile)
        msgs += _bingx([x for x in oev if str(x["kind"]).startswith("exit")])   # выход на бирже — раньше нового входа


def step(state: dict, write: bool) -> list[str]:
    now = time.time(); now_ms = int(now * 1000); ev = []; msgs = []
    # выходы
    for sym, pos in list(state["open"].items()):
        k = _k3_since(sym, int(pos["t_ms"]) + 180_000, now_ms)        # 04.10: свечи позиции копятся, а не берутся одним запросом на 1000 штук
        if not k:
            continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4])
        res = why = None
        newpos = None
        if sd == 1 and pos.get("flush"):                                 # R52: лонг на выносе — цель +10 %, стоп −10 %, после +5 % стоп в твх
            res, why = flush_long_walk(e, pos, k)
        elif sd == 1:
            res, why = long_walk(e, pos, k)                              # 01.10 владелец: памп вернулся → выход; удержался 2 ч → цель +10%, стоп на низу
        else:
            res, why, newpos = flip_check(e, pos, k, now)                # 01.10 владелец (ALICE, CAP): А-шорт держится 6 ч → закрыт, лонг
            if res is None:
                _pe = bool(pos.get("pump_end"))                         # R58: шорт «конец роста» — цели нет, стоп не переносится, выход по времени
                if _pe:
                    res, why = pump_end_walk(e, pos, k)
                else:
                    res, why = short_walk(e, pos["stop"], _short_tgt(pos), k, _ladder_top(sym, pos))   # шорт — цель, стоп, безубыток после −5%; 02.10: в монетах лестницы — выход выше вершины входа
                if res is None and not _pe and FAST3_SHORT_BE_AT and min(float(x[3]) for x in k) <= e * (1 - FAST3_SHORT_BE_AT):
                    pos["stop_px"] = e                                     # 01.10: стоп в безубытке — записываем, мост BingX переставит стоп на бирже
        if res is None:
            fx = fuel_exit(sym, pos, now, c)
            if fx: res, why = (c / e - 1) * sd, fx
        if res is None and sd == -1:
            if pos.get("be_from") and any(int(x[0]) >= int(pos["be_from"]) and float(x[2]) >= e for x in k):   # R66: стоп в точке входа, поставленный на шестом часу
                res, why = 0.0, "стоп в безубыток (R66)"
            else:
                _stl = _stall_exit(pos, k, now, c)                         # R66: шорт старше 6 ч, цена стоит → минус закрыть, плюс — стоп в твх
                if _stl and _stl[0] == "close":
                    res, why = (c / e - 1) * sd, _stl[1]
                    newpos = _stall_flip(pos, k, now, c)                   # R68: шорт не пошёл за 6 часов → лонг
                elif _stl:
                    pos["stop_px"] = e; pos["be_from"] = int(k[-1][0]) + 180_000; pos["rule"] = str(pos.get("rule") or "") + " · " + _stl[1]
                    msgs.append(f"{sym[:-4]} {_stl[1]}")
        if res is None and sd == 1:
            _sun = _sunday_close(pos, now)                                 # R69: воскресенье, Сидней + 2 ч — лонги закрываются
            if _sun: res, why = (c / e - 1) * sd, _sun
        if res is None and len(k) * 3 >= _hold_lim(pos): res, why = (c / e - 1) * sd, f"срок {_hold_lim(pos)} мин"   # R74: потолок 16 ч
        pos["last_px"] = c; pos["bars"] = len(k)
        if res is not None:
            res -= FEE
            ev.append(dict(book=BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"],
                           at=now, result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * res, 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            if write:
                cg(sym, *cg_caption(BOOK, sym, pos, e * (1 + res * sd), why, res))
            state["last_exit"][sym] = now; del state["open"][sym]
            if newpos:                                                    # переворот: на месте шорта встаёт лонг
                state["open"][sym] = newpos
                ev.append(dict(book=BOOK, sym=sym, kind="entry", side=1, px=newpos["px"], at=now, usd_in=FAST3_SIZE, rule=newpos["rule"], target=newpos["target"], stop=newpos["stop"], hold_min=newpos["hold_min"], flip=True))
                msgs.append(f"{sym[:-4]} лонг-переворот вход {newpos['px']:.6g} · цель +{newpos['target'] * 100:.0f}%, стоп {newpos['stop_px']:.6g}")
        else:
            ev.append(dict(book=BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    # входы: сначала ждущие шорты (Б)
    pending_step(state, BOOK, now, ev, msgs, write)
    try:
        flat_wait_step(state, BOOK, now, ev, msgs, write)                 # R70: ждущие лонги от линии флэта
    except Exception as e:  # noqa: BLE001
        msgs.append(f"ожидание лонга от линии флэта: сбой {type(e).__name__}: {e}")
    flush_entries(state, BOOK, now, ev, msgs, write)                      # 03.10 владелец (R49): рекордный вынос шортов → шорт по рынку (закрыв, что было)
    spike, climax, info = short_list()
    todo = sorted(set(spike) | set(climax))
    with ThreadPoolExecutor(12) as ex:
        res_all = [r for r in ex.map(lambda s: scan(s, s in spike, s in climax), todo) if r]
    bg = fon()
    for sym, px, t_bar, outs in res_all:
        for sd, why, tp, sl, hold in outs:
            if sym in state["open"] or now - state["last_exit"].get(sym, 0) < 2 * 3600:
                continue
            if _slide_gate(state, sym, why, t_bar, now, msgs, px=px):     # R65: монета сползает 3 дня — лонгов нет, шорт только на отскоке (зоны от вершины — 05.10)
                continue
            o1h, o5 = _oi_live(sym) if sd == 1 else (None, None)
            if o1h is None:
                o1h = info.get(sym, {}).get("oi1h")                    # живых данных нет — как раньше, по архиву
            sd, why, tp, sl, hold, _flip = flip_spike(sd, why, tp, sl, hold, o1h, o5, _crowd_live(sym) if sd == 1 else None,
                                                      _long_flush(sym, now) if sd == 1 else None)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            if sym in _own_mm():                                          # 27.09: монеты со своим ММ — бот в них не входит (own_mm.py)
                msgs.append(f"{sym[:-4]} пропущен: свой ММ (список own_mm)"); continue
            sd, why, start_low = picture(sym, sd, why, now, t_bar)       # 28.09: картина вокруг всплеска (Г, Д, Е)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            ab = None if why.startswith("шорт не взят") else gate_ab(sym, sd, px)   # 01.10 владелец (CAP, MOVR): Г главнее А — продавец тянет вверх, А не переворачивает в шорт; 29.09: А и Б
            if ab and ab.startswith("Б") and FAST3_B_SKIP:                # 30.09 владелец «верни не входить»: Б (шорт не у вершины 90 дн) — не входить, а не лонг (вживую 12 сделок −189 $, 1 в плюс)
                msgs.append(f"{sym[:-4]} не взят: {ab}"); continue
            if ab:
                sd = -sd; why = f"{ab} → сторона перевёрнута · " + why
                msgs.append(f"{sym[:-4]} {ab.split(':')[0]}: сторона перевёрнута → {'шорт' if sd == -1 else 'лонг'}")
                if sd == -1 and FAST3_B_SKIP and _flip_recheck():          # R64 (04.10 владелец по SAGA: «сделай обязательно проверку при перевороте»): шорт, в который А/А2
                    ab2 = gate_ab(sym, sd, px)                             # перевернули лонг, проходит ту же проверку Б, что и обычный шорт (не у вершины 90 дн — не входим)
                    if ab2 and ab2.startswith("Б"):
                        msgs.append(f"{sym[:-4]} не взят: {ab.split(':')[0]} перевернул лонг в шорт, но {ab2} (R64)"); continue
            _ws, _wskip, _wnote = _spike_short_plan(sym, px) if sd == 1 else (False, None, "")   # 03.10 16:20: этот всплеск будет шортом 5/5 (R53)?
            if sd == -1 or _ws:                                           # R67: шорт на флэте не берём
                _ff = _flat5(sym, px)
                if _ff[0]:
                    msgs.append(f"{sym[:-4]} не взят: шорт на флэте — {_flat_txt(sym, _ff)} (R67)")
                    _flat_long_set(state, sym, now, msgs, why); continue      # R70: вместо шорта — лонг лимиткой от линии флэта
            gn = gate_new(sym, sd, px)                                    # 30.09 владелец «делай»: В (шорт при интересе +50% за 7 дн) и Ж (лонг у максимума 30 ч) — не входить
            if gn and gn.startswith("Ж") and _ws and FAST3_ZH_OFF_FOR_SPIKE_SHORT:   # R56 (03.10 владелец «делай все»): Ж писался для лонга («покупка на вершине»); вход теперь шорт — вершина ему не помеха
                why = why + " · у максимума 30 ч — Ж не применён, вход шортом (R56)"; gn = None
            if gn:
                msgs.append(f"{sym[:-4]} не взят: {gn}"); continue
            if sd == -1:                                                  # Б: шорт — после вершины пампа
                ok, sw, _ = ses_gate(now, t_bar, sd)
                if not ok:
                    msgs.append(f"{sym[:-4]} всплеск пропущен: {sw}"); continue
                if sym not in state.setdefault("pending", {}):
                    msgs.append(to_pending(state, sym, why, t_bar, now, start_low))
                continue
            # 29.09 владелец «делай, стоп передвинь на 10%»: лонг +5% / −10% / 2 ч, без держания через стык (счёт long_rules_check.py)
            tp, sl, hold = FAST3_LONG_TP, FAST3_LONG_SL, FAST3_LONG_HOLD_MIN
            if True:                                                      # R40–R42 для обеих сторон (28.09: шорт QNT вошёл в первый час Сиднея)
                ok, sw, h2 = ses_gate(now, t_bar, sd)
                if not ok:
                    msgs.append(f"{sym[:-4]} всплеск пропущен: {sw}"); continue
            _lg = london_gate(sym, now, why)                                 # 02.10 владелец: Лондон — максимум 5 самых надёжных
            if _lg:
                msgs.append(f"{sym[:-4]} не взят: {_lg}"); continue
            if sd == 1 and not _ws:
                _lw = _long_window_closed(now)                            # R69: с воскресенья 22:00 до вторника 17:00 лонги не берём
                if _lw:
                    msgs.append(f"{sym[:-4]} лонг не взят: {_lw}"); continue
            if sd == 1 and not _ws:
                _pb = _pump_ban(sym, now)                                 # R60 (03.10 владелец): после сквиза в конце роста лонг в монете не раньше чем через 6 ч
                if _pb:
                    msgs.append(f"{sym[:-4]} {_pb}"); continue
            if sd == 1 and not _ws and _top72_block(sym, px):             # R72 (06.10): слива от максимума 72 ч ещё не было — лонг не берём
                msgs.append(f"{sym[:-4]} {_top72_block(sym, px)}"); continue
            if _ws and _wskip:                                            # R55 (03.10 владелец «делай все»): шорт по всплеску только у монет с фандингом в нижней половине доски
                msgs.append(f"{sym[:-4]} {_wskip}"); continue                #   на 266 входах недели: нижняя половина 107 входов +1547 $, верхняя 159 входов −3 $ (одна неделя, не проверено)
            _rl = _rate_ok(now)
            if _rl:
                msgs.append(f"{sym[:-4]} не взят: {_rl}"); continue
            try:                                                           # 03.10 владелец «делай»: всплеск берём в ШОРТ, а не в лонг — цель 5 %, стоп 5 %, вход по той же цене
                from core_config import FAST3_SPIKE_SHORT as _ss, FAST3_SPIKE_SHORT_TP as _stp, FAST3_SPIKE_SHORT_SL as _ssl, FAST3_SPIKE_SHORT_HOLD_MIN as _shm
            except ImportError:
                _ss, _stp, _ssl, _shm = True, 0.05, 0.05, 1440
            if _ws:                                                       # в монетах лестницы (Г / R47 / ручной список) шорт не берём — там остаётся лонг по прежним правилам
                sd, tp, sl, hold = -1, _stp, _ssl, _shm
                why = f"всплеск → шорт 5/5 (03.10: на 301 входе недели лонг −1632 $, шорт 5/5 +1958 $) · " + (_wnote + " · " if _wnote else "") + why
            sl, _spx, _snote = _range_stop(sym, sd, px, sl)                 # 02.10 владелец: стоп за диапазоном 30 дн
            if _snote: why = why + " · " + _snote
            if sd == -1:                                                   # R62: во флэте цель шорта — низ флэта
                tp, _fn = _flat_target(sym, px, tp)
                if _fn: why = why + " · " + _fn
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, stop_px=_spx, hold_min=hold, rule=why, last_px=px, bars=0, pump_open=_pump_open(px, why))
            state["open"][sym] = pos
            ev.append(dict(book=BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=why, target=tp, stop=sl, hold_min=hold,
                           oi1h=o1h if sd != 0 else None, oi5=o5, run24=info.get(sym, {}).get("run24"), fon=bg, bub=_bub(sym), pack=_pack(), btc=_btc()))
            _rate_ok(now, note=True)
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {why}")
            if write:
                cg(sym, *cg_caption(BOOK, sym, pos))
    _x2_exits(state, ev); _one_position(state, BOOK, ev, msgs, now, write)   # R63: одна монета — одна позиция на обе книги
    if write:
        with LOG.open("a", encoding="utf-8") as f:
            for r in ev:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)
        msgs += _bingx(ev)
    msgs.append(f"список: всплеск {len(spike)}, вынос {len(climax)} · открыто {len(state['open'])}")
    return msgs


# ── КНИГА «ПРОБУЖДЕНИЕ» (27.09 07:30, владелец: QNT/Q/SOON/US/IN/2Z прошли мимо — выборка экрана обновляется раз в полчаса, старт
#    приходится на первые полчаса; «листинг от 100 дней, 5 млн оставляй»). Каждые 3 мин один запрос тикера по всему Binance: прирост
#    оборота за интервал ≥ WAKE_X × нормы (оборот суток / 480) и цена ≥ +WAKE_PCT % → только по таким качаем трёхминутки и интерес.
#    Вход по правилам всплеска/выноса этой же книги; журнал отдельный output/paper_wake.jsonl.
WAKE_BOOK = "пробуждение"; WAKE_STATE = BASE_DIR / "output" / "paper_wake.json"; WAKE_LOG = BASE_DIR / "output" / "paper_wake.jsonl"
_TK = {"t": 0, "v": {}}; _AGE = {"t": 0, "v": {}}


def listing_age_days() -> dict:
    if time.time() - _AGE["t"] > 6 * 3600:
        info = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
        now = time.time() * 1000
        _AGE["v"] = {s["symbol"]: (now - int(s.get("onboardDate") or 0)) / 86400_000 for s in info.get("symbols", []) if s["symbol"].endswith("USDT") and s.get("status") == "TRADING"}
        _AGE["t"] = time.time()
    return _AGE["v"]


def wake_candidates() -> list[dict]:
    try:
        from core_config import WAKE_X, WAKE_PCT, WAKE_MIN_QV, WAKE_MIN_AGE_DAYS
    except ImportError:
        WAKE_X, WAKE_PCT, WAKE_MIN_QV, WAKE_MIN_AGE_DAYS = 5.0, 1.0, 5_000_000, 100
    tk = get_json("https://fapi.binance.com/fapi/v1/ticker/24hr") or []
    _board_set(tk)                                                        # 03.10 16:20: тот же ответ тикера — доска за 24 ч (R54, сайт)
    now = {x["symbol"]: (float(x["quoteVolume"]), float(x["lastPrice"]), float(x["lowPrice"])) for x in tk if x["symbol"].endswith("USDT")}
    prev, t_prev = _TK["v"], _TK["t"]; _TK["v"], _TK["t"] = now, time.time()
    if not prev or time.time() - t_prev > 600:
        return []
    age = listing_age_days(); out = []
    dt_slots = max(1.0, (time.time() - t_prev) / 180)
    for s_, (qv, px, lo) in now.items():
        q0, p0, _ = prev.get(s_, (None, None, None))
        if not q0 or not p0 or qv < WAKE_MIN_QV or age.get(s_, 0) < WAKE_MIN_AGE_DAYS: continue
        d = qv - q0; norm = q0 / 480 * dt_slots; chg = (px / p0 - 1) * 100
        if norm > 0 and d >= WAKE_X * norm and chg >= WAKE_PCT:
            out.append(dict(sym=s_, chg=chg, x=d / norm, qv=qv, run24=(px / lo - 1) * 100 if lo else None))
    return out


def wake_step(state: dict, write: bool) -> list[str]:
    now = time.time(); now_ms = int(now * 1000); ev = []; msgs = []
    for sym, pos in list(state["open"].items()):                        # выходы — как у основной книги
        k = _k3_since(sym, int(pos["t_ms"]) + 180_000, now_ms)        # 04.10: свечи позиции копятся, а не берутся одним запросом на 1000 штук
        if not k: continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4]); res = why = None
        newpos = None
        if sd == 1 and pos.get("flush"):                                 # R52: лонг на выносе — цель +10 %, стоп −10 %, после +5 % стоп в твх
            res, why = flush_long_walk(e, pos, k)
        elif sd == 1:
            res, why = long_walk(e, pos, k)                              # 01.10 владелец: памп вернулся → выход; удержался 2 ч → цель +10%, стоп на низу
        else:
            res, why, newpos = flip_check(e, pos, k, now)                # 01.10 владелец (ALICE, CAP): А-шорт держится 6 ч → закрыт, лонг
            if res is None:
                res, why = short_walk(e, pos["stop"], _short_tgt(pos), k, _ladder_top(sym, pos))   # шорт — цель, стоп, безубыток после −5%; 02.10: в монетах лестницы — выход выше вершины входа
                if res is None and FAST3_SHORT_BE_AT and min(float(x[3]) for x in k) <= e * (1 - FAST3_SHORT_BE_AT):
                    pos["stop_px"] = e                                     # 01.10: стоп в безубытке — записываем, мост BingX переставит стоп на бирже
        if res is None:
            fx = fuel_exit(sym, pos, now, c)
            if fx: res, why = (c / e - 1) * sd, fx
        if res is None and sd == -1:
            if pos.get("be_from") and any(int(x[0]) >= int(pos["be_from"]) and float(x[2]) >= e for x in k):   # R66: стоп в точке входа, поставленный на шестом часу
                res, why = 0.0, "стоп в безубыток (R66)"
            else:
                _stl = _stall_exit(pos, k, now, c)                         # R66: шорт старше 6 ч, цена стоит → минус закрыть, плюс — стоп в твх
                if _stl and _stl[0] == "close":
                    res, why = (c / e - 1) * sd, _stl[1]
                    newpos = _stall_flip(pos, k, now, c)                   # R68: шорт не пошёл за 6 часов → лонг
                elif _stl:
                    pos["stop_px"] = e; pos["be_from"] = int(k[-1][0]) + 180_000; pos["rule"] = str(pos.get("rule") or "") + " · " + _stl[1]
                    msgs.append(f"{sym[:-4]} {_stl[1]}")
        if res is None and sd == 1:
            _sun = _sunday_close(pos, now)                                 # R69: воскресенье, Сидней + 2 ч — лонги закрываются
            if _sun: res, why = (c / e - 1) * sd, _sun
        if res is None and len(k) * 3 >= _hold_lim(pos): res, why = (c / e - 1) * sd, f"срок {_hold_lim(pos)} мин"   # R74: потолок 16 ч
        pos["last_px"] = c; pos["bars"] = len(k)
        if res is not None:
            res -= FEE
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"], at=now,
                           result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * (res), 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            if write:
                cg(sym, *cg_caption(WAKE_BOOK, sym, pos, e * (1 + res * sd), why, res))
            state["last_exit"][sym] = now; del state["open"][sym]
            if newpos:                                                    # переворот: на месте шорта встаёт лонг
                state["open"][sym] = newpos
                ev.append(dict(book=WAKE_BOOK, sym=sym, kind="entry", side=1, px=newpos["px"], at=now, usd_in=FAST3_SIZE, rule=newpos["rule"], target=newpos["target"], stop=newpos["stop"], hold_min=newpos["hold_min"], flip=True))
                msgs.append(f"{sym[:-4]} лонг-переворот вход {newpos['px']:.6g} · цель +{newpos['target'] * 100:.0f}%, стоп {newpos['stop_px']:.6g}")
        else:
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    pending_step(state, WAKE_BOOK, now, ev, msgs, write)                 # ждущие шорты (Б)
    try:
        flat_wait_step(state, WAKE_BOOK, now, ev, msgs, write)            # R70
    except Exception as e:  # noqa: BLE001
        msgs.append(f"ожидание лонга от линии флэта: сбой {type(e).__name__}: {e}")
    cands = wake_candidates()
    for cd in cands:
        sym = cd["sym"]
        if sym in state["open"] or now - state["last_exit"].get(sym, 0) < 2 * 3600: continue
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 13}, quiet_400=True) or []
        ov = [float(x["sumOpenInterestValue"]) for x in oi]; oi1h = (ov[-1] / ov[0] - 1) * 100 if len(ov) >= 13 and ov[0] else None
        oibar = (ov[-1] / ov[-2] - 1) if len(ov) >= 2 and ov[-2] else None
        cr = crowd_of(sym)
        r = scan(sym, True, (cd["run24"] or 0) >= FAST3_CLIMAX_RUN)
        if not r: continue
        _, px, t_bar, outs = r
        for sd, why, tp, sl, hold in outs:
            if _slide_gate(state, sym, why, t_bar, now, msgs, f" · пробуждение: оборот ×{cd['x']:.0f} за интервал", px=px):   # R65
                continue
            sd, why, tp, sl, hold, _flip = flip_spike(sd, why, tp, sl, hold, oi1h, oibar * 100 if oibar is not None else None,
                                                      _crowd_live(sym) if sd == 1 else None, _long_flush(sym, now) if sd == 1 else None)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            sd0 = sd
            sd, why, start_low = picture(sym, sd, why, now, t_bar)       # 28.09: картина вокруг всплеска (Г, Д, Е)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            ab = None if why.startswith("шорт не взят") else gate_ab(sym, sd, px)   # 01.10 владелец (CAP, MOVR): Г главнее А — продавец тянет вверх, А не переворачивает в шорт; 29.09: А и Б
            if ab and ab.startswith("Б") and FAST3_B_SKIP:                # 30.09 владелец «верни не входить»: Б (шорт не у вершины 90 дн) — не входить, а не лонг (вживую 12 сделок −189 $, 1 в плюс)
                msgs.append(f"{sym[:-4]} не взят: {ab}"); continue
            if ab:
                sd = -sd; why = f"{ab} → сторона перевёрнута · " + why
                msgs.append(f"{sym[:-4]} {ab.split(':')[0]}: сторона перевёрнута → {'шорт' if sd == -1 else 'лонг'}")
                if sd == -1 and FAST3_B_SKIP and _flip_recheck():          # R64 (04.10 владелец по SAGA: «сделай обязательно проверку при перевороте»): шорт, в который А/А2
                    ab2 = gate_ab(sym, sd, px)                             # перевернули лонг, проходит ту же проверку Б, что и обычный шорт (не у вершины 90 дн — не входим)
                    if ab2 and ab2.startswith("Б"):
                        msgs.append(f"{sym[:-4]} не взят: {ab.split(':')[0]} перевернул лонг в шорт, но {ab2} (R64)"); continue
            _ws, _wskip, _wnote = _spike_short_plan(sym, px) if sd == 1 else (False, None, "")   # 03.10 16:20: этот всплеск будет шортом 5/5 (R53)?
            if sd == -1 or _ws:                                           # R67: шорт на флэте не берём
                _ff = _flat5(sym, px)
                if _ff[0]:
                    msgs.append(f"{sym[:-4]} не взят: шорт на флэте — {_flat_txt(sym, _ff)} (R67)")
                    _flat_long_set(state, sym, now, msgs, why); continue      # R70: вместо шорта — лонг лимиткой от линии флэта
            gn = gate_new(sym, sd, px)                                    # 30.09 владелец «делай»: В (шорт при интересе +50% за 7 дн) и Ж (лонг у максимума 30 ч) — не входить
            if gn and gn.startswith("Ж") and _ws and FAST3_ZH_OFF_FOR_SPIKE_SHORT:   # R56 (03.10 владелец «делай все»): Ж писался для лонга («покупка на вершине»); вход теперь шорт — вершина ему не помеха
                why = why + " · у максимума 30 ч — Ж не применён, вход шортом (R56)"; gn = None
            if gn:
                msgs.append(f"{sym[:-4]} не взят: {gn}"); continue
            if sd != sd0:
                _flip = sd == -1
            if sd == 1 and not ((oi1h is not None and oi1h >= FAST3_SHORT_OI1H) or (cr is not None and cr <= 0.7)):
                continue                                                  # всплеск без интереса и без шортов в топливе — не вход (R39)
            if sd == -1 and not _flip and not (oibar is not None and oibar <= FAST3_CLIMAX_OI):
                continue
            if sym in _own_mm():                                          # 27.09: свой ММ — не входим
                msgs.append(f"{sym[:-4]} пропущен: свой ММ (список own_mm)"); continue
            if sd == -1:                                                  # Б: шорт — после вершины пампа
                ok, sw, _ = ses_gate(now, t_bar, sd)
                if not ok:
                    msgs.append(f"{sym[:-4]} всплеск пропущен: {sw}"); continue
                if sym not in state.setdefault("pending", {}):
                    msgs.append(to_pending(state, sym, why + f" · пробуждение: оборот ×{cd['x']:.0f} за интервал", t_bar, now, start_low))
                continue
            tp, sl, hold = FAST3_LONG_TP, FAST3_LONG_SL, FAST3_LONG_HOLD_MIN   # 29.09: лонг +5% / −10% / 2 ч
            if True:                                                      # R40–R42 для обеих сторон (28.09)
                ok, sw, h2 = ses_gate(now, t_bar, sd)
                if not ok:
                    msgs.append(f"{sym[:-4]} всплеск пропущен: {sw}"); continue
            _lg = london_gate(sym, now, why)                                 # 02.10 владелец: Лондон — максимум 5 самых надёжных
            if _lg:
                msgs.append(f"{sym[:-4]} не взят: {_lg}"); continue
            if sd == 1 and not _ws:
                _lw = _long_window_closed(now)                            # R69: с воскресенья 22:00 до вторника 17:00 лонги не берём
                if _lw:
                    msgs.append(f"{sym[:-4]} лонг не взят: {_lw}"); continue
            if sd == 1 and not _ws:
                _pb = _pump_ban(sym, now)                                 # R60 (03.10 владелец): после сквиза в конце роста лонг в монете не раньше чем через 6 ч
                if _pb:
                    msgs.append(f"{sym[:-4]} {_pb}"); continue
            if sd == 1 and not _ws and _top72_block(sym, px):             # R72 (06.10): слива от максимума 72 ч ещё не было — лонг не берём
                msgs.append(f"{sym[:-4]} {_top72_block(sym, px)}"); continue
            if _ws and _wskip:                                            # R55 (03.10 владелец «делай все»): шорт по всплеску только у монет с фандингом в нижней половине доски
                msgs.append(f"{sym[:-4]} {_wskip}"); continue                #   на 266 входах недели: нижняя половина 107 входов +1547 $, верхняя 159 входов −3 $ (одна неделя, не проверено)
            _rl = _rate_ok(now)
            if _rl:
                msgs.append(f"{sym[:-4]} не взят: {_rl}"); continue
            try:                                                           # 03.10 владелец «делай»: всплеск берём в ШОРТ, а не в лонг — цель 5 %, стоп 5 %, вход по той же цене
                from core_config import FAST3_SPIKE_SHORT as _ss, FAST3_SPIKE_SHORT_TP as _stp, FAST3_SPIKE_SHORT_SL as _ssl, FAST3_SPIKE_SHORT_HOLD_MIN as _shm
            except ImportError:
                _ss, _stp, _ssl, _shm = True, 0.05, 0.05, 1440
            if _ws:                                                       # в монетах лестницы (Г / R47 / ручной список) шорт не берём — там остаётся лонг по прежним правилам
                sd, tp, sl, hold = -1, _stp, _ssl, _shm
                why = f"всплеск → шорт 5/5 (03.10: на 301 входе недели лонг −1632 $, шорт 5/5 +1958 $) · " + (_wnote + " · " if _wnote else "") + why
            sl, _spx, _snote = _range_stop(sym, sd, px, sl)                 # 02.10 владелец: стоп за диапазоном 30 дн
            if _snote: why = why + " · " + _snote
            if sd == -1:                                                   # R62: во флэте цель шорта — низ флэта
                tp, _fn = _flat_target(sym, px, tp)
                if _fn: why = why + " · " + _fn
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, stop_px=_spx, hold_min=hold, rule=why + f" · пробуждение: оборот ×{cd['x']:.0f} за интервал", last_px=px, bars=0, pump_open=_pump_open(px, why))
            state["open"][sym] = pos
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=pos["rule"], target=tp, stop=sl, hold_min=hold,
                           oi1h=oi1h, crowd=cr, wake_x=round(cd["x"], 1), wake_chg=round(cd["chg"], 2), qv24=round(cd["qv"]), fon=fon(), bub=_bub(sym), pack=_pack(), btc=_btc()))
            _rate_ok(now, note=True)
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {pos['rule']}")
            if write:
                cg(sym, *cg_caption(WAKE_BOOK, sym, pos))
    _x2_exits(state, ev); _one_position(state, WAKE_BOOK, ev, msgs, now, write)   # R63
    if write:
        with WAKE_LOG.open("a", encoding="utf-8") as f:
            for r_ in ev: f.write(json.dumps(r_, ensure_ascii=False) + "\n")
        tmp = WAKE_STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(WAKE_STATE)
        msgs += _bingx(ev)
    msgs.append(f"пробуждений {len(cands)}" + (": " + ", ".join(c['sym'][:-4] for c in cands[:8]) if cands else "") + f" · открыто {len(state['open'])}")
    return msgs


_OWN = {"t": 0, "v": set()}


def _own_mm() -> set:
    """монеты со своим ММ (output/own_mm.json, block=True); читаем раз в 5 мин; файлу больше OWN_MM_MAX_AGE_H — пересчёт отдельным процессом"""
    if time.time() - _OWN["t"] > 300:
        _OWN["t"] = time.time()
        p = BASE_DIR / "output" / "own_mm.json"
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            _OWN["v"] = {s for s, v in (d.get("coins") or {}).items() if v.get("block")}
            age_h = (time.time() - float(d.get("at") or 0)) / 3600
        except (OSError, ValueError):
            age_h = 1e9
        try:
            from core_config import OWN_MM_MAX_AGE_H as _mx
        except ImportError:
            _mx = 24
        if age_h > _mx:
            import subprocess
            subprocess.Popen([PY, "own_mm.py"], cwd=BASE_DIR, stdout=open(BASE_DIR / "output" / "own_mm.log", "a"),
                             stderr=subprocess.STDOUT, start_new_session=True)
        try:                                                              # 02.10 владелец: ручной список «свой ММ» (TRUTH: «такое говнище не торгуем»)
            from core_config import OWN_MM_MANUAL as _man
            _OWN["v"] = set(_OWN.get("v") or set()) | set(_man)
        except ImportError:
            pass
    return _OWN["v"]


def page_step() -> None:
    """ЖИВАЯ СТРАНИЦА (27.09 владелец: «отдельный сайт для быстрого бота, обновление по сокету, сервер на моём компе»): после прохода —
    сборка output/fast_state.json (fast_state.py, отдельным процессом, ~40 с) и сервер fast_server.py, если не отвечает на порту."""
    try:
        from core_config import FAST_PAGE_ENABLED as _on, FAST_SERVER_PORT as _port
    except ImportError:
        _on, _port = True, 8765
    if not _on:
        return
    import socket
    import subprocess
    try:
        subprocess.Popen([PY, "fast_state.py"], cwd=BASE_DIR, stdout=open(BASE_DIR / "output" / "fast_state.log", "a"),
                         stderr=subprocess.STDOUT, start_new_session=True)
        s = socket.socket(); s.settimeout(1)
        alive = s.connect_ex(("127.0.0.1", _port)) == 0; s.close()
        if not alive:
            subprocess.Popen([PY, "fast_server.py"], cwd=BASE_DIR, stdout=open(BASE_DIR / "output" / "fast_server.log", "a"),
                             stderr=subprocess.STDOUT, start_new_session=True)
            print(f"{datetime.now(L):%H:%M:%S} страница: сервер запущен, http://localhost:{_port}/", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"{datetime.now(L):%H:%M:%S} страница: {type(e).__name__}: {e}", flush=True)


_LOCK = None


def _paused_until() -> float:
    """секунд до конца паузы по output/fast_pause.json (прогон run.py), 0 — паузы нет"""
    try:
        d = json.loads((BASE_DIR / "output" / "fast_pause.json").read_text(encoding="utf-8"))
        return max(0.0, float(d.get("until", 0)) - time.time())
    except (OSError, ValueError, TypeError):
        return 0.0


def main() -> int:
    global _LOCK
    ap = argparse.ArgumentParser(); ap.add_argument("--loop", action="store_true"); a = ap.parse_args()
    if a.loop:                                  # 27.09: один fast_tier на машину — второй запуск не стартует (дубли входов, скринов, разборов)
        import fcntl
        _LOCK = open(BASE_DIR / "output" / "fast_tier.lock", "w")
        try:
            fcntl.flock(_LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(f"{datetime.now(L):%H:%M:%S} fast_tier уже работает — второй не запускаю", flush=True)
            return 0
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {"open": {}, "last_exit": {}}
    state.setdefault("open", {}); state.setdefault("last_exit", {})
    try:
        wstate = json.loads(WAKE_STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        wstate = {"open": {}, "last_exit": {}}
    wstate.setdefault("open", {}); wstate.setdefault("last_exit", {})
    _OTHER[BOOK] = dict(state=wstate, book=WAKE_BOOK); _OTHER[WAKE_BOOK] = dict(state=state, book=BOOK)   # R63
    while True:
        _pu = _paused_until()                                           # 01.10 владелец: прогон ставит бота на паузу (output/fast_pause.json), снимает через минуту после прохода по Binance
        if _pu:
            print(f"{datetime.now(L):%H:%M:%S} пауза: прогон идёт по Binance, ещё {_pu:.0f} с", flush=True)
            time.sleep(min(_pu, 30)); continue
        try:
            for m in step(state, a.loop):
                print(f"{datetime.now(L):%H:%M:%S} {BOOK}: {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} {BOOK}: сбой {type(e).__name__}: {e}", flush=True)
        try:
            for m in wake_step(wstate, a.loop):
                print(f"{datetime.now(L):%H:%M:%S} {WAKE_BOOK}: {m}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} {WAKE_BOOK}: сбой {type(e).__name__}: {e}", flush=True)
        if not a.loop:
            return 0
        page_step()
        try:                                    # 27.09 владелец: разбор выхода быстрых сделок через 2 ч — отдельным процессом (fast_review.py)
            import subprocess
            subprocess.Popen([PY, "fast_review.py", "--write"], cwd=BASE_DIR, stdout=open(BASE_DIR / "output" / "fast_review.log", "a"),
                             stderr=subprocess.STDOUT, start_new_session=True)
        except Exception as e:  # noqa: BLE001
            print(f"{datetime.now(L):%H:%M:%S} разбор выходов: {type(e).__name__}: {e}", flush=True)
        time.sleep(max(1, 180 - (time.time() % 180)))


if __name__ == "__main__":
    raise SystemExit(main())
