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
L = timezone(timedelta(hours=3))


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


def _all_perps() -> list[str]:
    """все торгуемые USDT-перпы Binance, кэш 1 ч"""
    if time.time() - _PERPS["t"] > 3600 or not _PERPS["v"]:
        ex = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
        v = [x["symbol"] for x in ex.get("symbols", []) if x.get("quoteAsset") == "USDT" and x.get("contractType") == "PERPETUAL" and x.get("status") == "TRADING"]
        if v:
            _PERPS.update(t=time.time(), v=v)
    return _PERPS["v"]


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
    from core_config import FAST3_SHORT_TP, FAST3_SHORT_SL, FAST3_SHORT_HOLD_MIN
except ImportError:
    FAST3_SHORT_TP, FAST3_SHORT_SL, FAST3_SHORT_HOLD_MIN = 1.0, 0.10, 240


def _run90(sym: str):
    t, v = _D90.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 90}, quiet_400=True) or []
        v = float(k[-1][4]) / min(float(x[3]) for x in k) if len(k) >= 30 and min(float(x[3]) for x in k) > 0 else None
        _D90[sym] = (time.time(), v)
    return v


_H90: dict = {}; _SP7: dict = {}


def _hi90(sym: str):
    """максимум 90 дн (фьючерс Binance, дневки; кэш 1 ч)"""
    t, v = _H90.get(sym, (0, None))
    if time.time() - t > 3600:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "1d", "limit": 90}, quiet_400=True) or []
        v = max(float(x[2]) for x in k) if len(k) >= 30 else None
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
    if sd == 1 and top:                                               # 29.09 владелец «да вноси»: А расширена — лонг у вершины 90 дн не берём, спот не смотрим
        cv = _spot_cvd7(sym)                                          # (сделки 27–28.09: лонги у вершины 34 шт., 32% в плюс, −318 $ при 1000 $; сигналы канала 29.09: у вершины 3 из 21 вверх первыми, 7 из 21 вниз)
        return f"А: лонг у вершины 90 дн ({(px / hi - 1) * 100:+.1f}% от максимума)" + (f", спот за 7 дн {cv / 1e6:+.0f}M$" if cv is not None else "") + " — раздача"
    if sd == -1 and not top:
        return f"Б: шорт не у вершины 90 дн ({(px / hi - 1) * 100:+.1f}% от максимума) — середина/низ диапазона"
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
    up_ok = lambda: (lambda r: f"монета ×{r:.1f} от минимума 90 дн — её продавец тянет вверх" if r and r >= run_x else None)(_run90(sym))  # noqa: E731
    if sd == 1:                                                       # 29.09 владелец «да вноси»: Д убрана — лонг после выноса шортов берём (цель +5%);
        fl = _flush(sym, now, "short")                                # бот 27–28.09: 8 таких лонгов, 5 в плюс, +116 $; сигналы канала: 5 из 8 вверх первыми (не проверено)
        return 1, (f"вынос шортов на всплеске: {fl} · " + why if fl else why), start_low
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
        stop, tgt = FAST3_SHORT_SL, FAST3_SHORT_TP
        del state["pending"][sym]
        t_bar = int(last[0]); ok, sw, _h = ses_gate(now, t_bar, -1)
        hold = FAST3_SHORT_HOLD_MIN
        if not ok:
            msgs.append(f"{sym[:-4]} шорт после вершины пропущен: {sw}"); continue
        why = p["why"] + f" · вход после вершины {top:.6g} ({sq}): стоп +{stop * 100:.0f}%, выход по выносу лонгов, срок {hold} мин · сессия {sw}"
        pos = dict(sym=sym, side=-1, px=c, t_ms=t_bar, at=now, target=round(tgt, 5), stop=round(stop, 5), hold_min=hold, rule=why, last_px=c, bars=0)
        state["open"][sym] = pos
        ev.append(dict(book=book, sym=sym, kind="entry", side=-1, px=c, at=now, usd_in=FAST3_SIZE, rule=why, target=pos["target"], stop=pos["stop"],
                       hold_min=hold, fon=fon(), bub=_bub(sym)))
        msgs.append(f"{sym[:-4]} шорт вход {c:.6g} · стоп +{stop * 100:.0f}% · выход по выносу лонгов / {hold} мин")
        if write:
            cg(sym, *cg_caption(book, sym, pos))


def to_pending(state: dict, sym: str, why: str, t_bar: int, now: float, start_low) -> str:
    """шорт не сразу — в ожидание вершины до конца текущей сессии"""
    d = datetime.fromtimestamp(now, L)
    _, a, b = next(x for x in SES_WIN if x[1] <= d.hour < x[2])
    end = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=b)
    state.setdefault("pending", {})[sym] = dict(why=why, t_ms=t_bar, at=now, expire=end.timestamp(), start_low=start_low)
    return f"{sym[:-4]} шорт — ждём вершину пампа (до {end:%H:%M})"


def fuel_exit(sym: str, pos: dict, now: float, c: float):
    """выход по картине (28.09 MUBARAK): лонг — когда вынесли шорты (топливо сожжено), шорт — когда вынесли лонги; только в плюсе"""
    sd, e = int(pos["side"]), float(pos["px"])
    if sd == 1:                                                       # 29.09: лонг — цель +5% / стоп / 2 ч, без выхода по выносу (счёт)
        return None
    if (c - e) * sd <= 0:
        return None
    fl = _flush(sym, now, "short" if sd == 1 else "long", since_ms=int(pos["t_ms"]))
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
    end = datetime.fromtimestamp((int(pos["t_ms"]) + 180_000) / 1000 + int(pos.get("hold_min") or 0) * 60, L)
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
        body = [f"💵 вход:   {e:.6g}  ·  {t_in:%H:%M}", f"🏁 выход:  {px_out:.6g}  ·  {datetime.now(L):%H:%M}"]
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


SES_WIN = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
WDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def ses_gate(now: float, t_bar: int, side: int = 1):
    """R40–R42 для лонга-всплеска: (можно ли входить, причина/сессия, срок в минутах от закрытия бара входа до часа выхода сессии)"""
    try:
        from core_config import FAST3_SES_WAIT_MIN as _w, FAST3_SES_LATE_SKIP_MIN as _late, FAST3_SES_EXIT_H as _ex, FAST3_SKIP_DAYS as _days
    except ImportError:
        return True, "", None
    d = datetime.fromtimestamp(now, L)
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
    return (hold >= 3), f"{name}, выход {end:%d.%m %H:%M} ({lab})", hold


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
    return sym, c[-1], int(k[-1][0]), out


def step(state: dict, write: bool) -> list[str]:
    now = time.time(); now_ms = int(now * 1000); ev = []; msgs = []
    # выходы
    for sym, pos in list(state["open"].items()):
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(pos["t_ms"]) + 180_000, "limit": 1000}, quiet_400=True, weight=5) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k:
            continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4])
        res = why = None
        if sd == 1:
            if lo <= e * (1 - pos["stop"]): res, why = -pos["stop"], "стоп"
            elif hi >= e * (1 + pos["target"]): res, why = pos["target"], "цель"
        else:
            if hi >= e * (1 + pos["stop"]): res, why = -pos["stop"], "стоп"
            elif lo <= e * (1 - pos["target"]): res, why = pos["target"], "цель"
        if res is None:
            fx = fuel_exit(sym, pos, now, c)
            if fx: res, why = (c / e - 1) * sd, fx
        if res is None and len(k) * 3 >= pos["hold_min"]: res, why = (c / e - 1) * sd, f"срок {pos['hold_min']} мин"
        pos["last_px"] = c; pos["bars"] = len(k)
        if res is not None:
            res -= FEE
            ev.append(dict(book=BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"],
                           at=now, result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * res, 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            if write:
                cg(sym, *cg_caption(BOOK, sym, pos, e * (1 + res * sd), why, res))
            state["last_exit"][sym] = now; del state["open"][sym]
        else:
            ev.append(dict(book=BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    # входы: сначала ждущие шорты (Б)
    pending_step(state, BOOK, now, ev, msgs, write)
    spike, climax, info = short_list()
    todo = sorted(set(spike) | set(climax))
    with ThreadPoolExecutor(12) as ex:
        res_all = [r for r in ex.map(lambda s: scan(s, s in spike, s in climax), todo) if r]
    bg = fon()
    for sym, px, t_bar, outs in res_all:
        for sd, why, tp, sl, hold in outs:
            if sym in state["open"] or now - state["last_exit"].get(sym, 0) < 2 * 3600:
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
            ab = gate_ab(sym, sd, px)                                     # 29.09: А и Б; 30.09 владелец: «фильтрация должна работать в обратную сторону, а не закрывать входы»
            if ab:
                sd = -sd; why = f"{ab} → сторона перевёрнута · " + why
                msgs.append(f"{sym[:-4]} {ab.split(':')[0]}: сторона перевёрнута → {'шорт' if sd == -1 else 'лонг'}")
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
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, hold_min=hold, rule=why, last_px=px, bars=0)
            state["open"][sym] = pos
            ev.append(dict(book=BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=why, target=tp, stop=sl, hold_min=hold,
                           oi1h=o1h if sd != 0 else None, oi5=o5, run24=info.get(sym, {}).get("run24"), fon=bg, bub=_bub(sym)))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {why}")
            if write:
                cg(sym, *cg_caption(BOOK, sym, pos))
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
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": int(pos["t_ms"]) + 180_000, "limit": 1000}, quiet_400=True, weight=5) or []
        k = [x for x in k if int(x[0]) + 180_000 <= now_ms]
        if not k: continue
        e, sd = float(pos["px"]), int(pos["side"]); hi = max(float(x[2]) for x in k); lo = min(float(x[3]) for x in k); c = float(k[-1][4]); res = why = None
        if sd == 1:
            if lo <= e * (1 - pos["stop"]): res, why = -pos["stop"], "стоп"
            elif hi >= e * (1 + pos["target"]): res, why = pos["target"], "цель"
        else:
            if hi >= e * (1 + pos["stop"]): res, why = -pos["stop"], "стоп"
            elif lo <= e * (1 - pos["target"]): res, why = pos["target"], "цель"
        if res is None:
            fx = fuel_exit(sym, pos, now, c)
            if fx: res, why = (c / e - 1) * sd, fx
        if res is None and len(k) * 3 >= pos["hold_min"]: res, why = (c / e - 1) * sd, f"срок {pos['hold_min']} мин"
        pos["last_px"] = c; pos["bars"] = len(k)
        if res is not None:
            res -= FEE
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="exit_long" if sd == 1 else "exit_short", side=sd, px_in=e, px_out=round(e * (1 + res * sd), 8), opened_at=pos["at"], at=now,
                           result_pct=round(res * 100, 2), usd=round(FAST3_SIZE * (res), 2), why_exit=why, rule=pos["rule"], size=1.0))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} выход {why} {res * 100:+.2f}%")
            if write:
                cg(sym, *cg_caption(WAKE_BOOK, sym, pos, e * (1 + res * sd), why, res))
            state["last_exit"][sym] = now; del state["open"][sym]
        else:
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="follow", side=sd, px_in=e, px=c, result_pct=round((c / e - 1) * sd * 100, 2), at=now))
    pending_step(state, WAKE_BOOK, now, ev, msgs, write)                 # ждущие шорты (Б)
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
            sd, why, tp, sl, hold, _flip = flip_spike(sd, why, tp, sl, hold, oi1h, oibar * 100 if oibar is not None else None,
                                                      _crowd_live(sym) if sd == 1 else None, _long_flush(sym, now) if sd == 1 else None)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            sd0 = sd
            sd, why, start_low = picture(sym, sd, why, now, t_bar)       # 28.09: картина вокруг всплеска (Г, Д, Е)
            if sd == 0:
                msgs.append(f"{sym[:-4]} {why.split(' · ')[0]}"); continue
            ab = gate_ab(sym, sd, px)                                     # 29.09: А и Б; 30.09 владелец: «фильтрация должна работать в обратную сторону, а не закрывать входы»
            if ab:
                sd = -sd; why = f"{ab} → сторона перевёрнута · " + why
                msgs.append(f"{sym[:-4]} {ab.split(':')[0]}: сторона перевёрнута → {'шорт' if sd == -1 else 'лонг'}")
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
            pos = dict(sym=sym, side=sd, px=px, t_ms=t_bar, at=now, target=tp, stop=sl, hold_min=hold, rule=why + f" · пробуждение: оборот ×{cd['x']:.0f} за интервал", last_px=px, bars=0)
            state["open"][sym] = pos
            ev.append(dict(book=WAKE_BOOK, sym=sym, kind="entry", side=sd, px=px, at=now, usd_in=FAST3_SIZE, rule=pos["rule"], target=tp, stop=sl, hold_min=hold,
                           oi1h=oi1h, crowd=cr, wake_x=round(cd["x"], 1), wake_chg=round(cd["chg"], 2), qv24=round(cd["qv"]), fon=fon(), bub=_bub(sym)))
            msgs.append(f"{sym[:-4]} {'лонг' if sd == 1 else 'шорт'} вход {px:.6g} · {pos['rule']}")
            if write:
                cg(sym, *cg_caption(WAKE_BOOK, sym, pos))
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
    while True:
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
