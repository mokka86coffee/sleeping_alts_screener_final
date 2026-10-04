#!/usr/bin/env python3
"""ДАННЫЕ ЖИВОЙ СТРАНИЦЫ БЫСТРОГО БОТА (27.09, владелец: «два круга — вход и в работе, из круга всплеском монета и цена-цель / цена для
входа; при наведении весь разбор как в телеграме и график, похожий на коингласс; страница обновляется сама, только из дома»).

build() → dict, пишется в output/fast_state.json (fast_tier каждые 3 мин; сервер fast_server.py рассылает странице по сокету).
  meta     — сессия (UTC+3: Сидней 00–03, Токио 03–10, Лондон 10–16, НЙ 16–24), ожидание первого часа, запрет дня, час выхода (R40–R42)
  entry    — кандидаты короткого списка fast_tier: цена сейчас, уровень входа = закрытие прошлой трёхминутки × (1 + FAST3_SPIKE_PCT),
             объём текущего бара к порогу (× FAST3_SPIKE_X медианы 30), интерес за час
  open     — открытые позиции обеих книг: вход, цель, стоп, выход по сроку, цена сейчас, итог
  closed   — закрытые с полуночи UTC+3: вход→выход, причина, итог, разбор (fast_reviews.jsonl)
  charts   — по монетам в работе и закрытым сегодня: трёхминутки 6 ч (цена, объём, CVD фьючерсов), CVD спота, интерес 5 м, фандинг,
             ликвидации по сторонам (наш поток cq_v2/liq)
  score    — счёт дня по книгам

    .venv/bin/python fast_state.py            # собрать и записать output/fast_state.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json  # noqa: E402
import core_config as cc  # noqa: E402

L = timezone(timedelta(hours=3))
OUT = BASE_DIR / "output" / "fast_state.json"
WIN = (("Сидней", 0, 3), ("Токио", 3, 10), ("Лондон", 10, 16), ("Нью-Йорк", 16, 24))
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
BOOKS = (("всплеск/вынос", "paper_fast3"), ("пробуждение", "paper_wake"))
B3 = 180_000
BOARD_STEP = 900   # шаг точек линий доски на странице, секунд (15 минут)
CHART_H = 6


def _read(p: Path, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def _rows(p: Path) -> list[dict]:
    out = []
    try:
        for ln in p.open(encoding="utf-8"):
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def meta(now: float) -> dict:
    d = datetime.fromtimestamp(now, L)
    name, a, b = next(x for x in WIN if x[1] <= d.hour < x[2])
    o = d.replace(hour=a, minute=0, second=0, microsecond=0)
    end = o + timedelta(hours=b - a)
    ex = d.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=cc.FAST3_SES_EXIT_H.get(name, b))
    mins = (d - o).total_seconds() / 60
    wd = WD[d.weekday()]
    late = (b - a) * 60 - mins <= cc.FAST3_SES_LATE_SKIP_MIN.get(name, 0)
    why = ("день " + wd + " (R42)") if wd in cc.FAST3_SKIP_DAYS else ("первый час сессии (R40)" if mins < cc.FAST3_SES_WAIT_MIN
                                                                        else ("поздно в сессии" if late else ""))
    return dict(t=int(now), ses=name, ses_start=int(o.timestamp()), ses_end=int(end.timestamp()), exit_at=int(ex.timestamp()),
                wd=wd, open_gate=not why, gate_why=why,
                gate_until=int((o + timedelta(minutes=cc.FAST3_SES_WAIT_MIN)).timestamp()) if mins < cc.FAST3_SES_WAIT_MIN else None)


def _k3(sym: str, limit: int) -> list[list]:
    return get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": limit}, quiet_400=True,
                    weight=1 if limit <= 100 else 2) or []


def candidates() -> list[dict]:
    try:
        import fast_tier
        spike, _climax, info = fast_tier.short_list(all_coins=False)   # 30.09: для страницы — короткий список (все 528 монет тормозили сборку до 84 с)
    except Exception:  # noqa: BLE001
        return []

    def one(sym):
        k = _k3(sym, 33)
        if len(k) < 33:
            return None
        cl = k[:-1]; cur = k[-1]
        med = st.median(float(x[7]) for x in cl[-30:])
        prev_c = float(cl[-1][4]); px = float(cur[4]); lvl = prev_c * (1 + cc.FAST3_SPIKE_PCT)
        need_q = max(cc.FAST3_SPIKE_X * med, cc.FAST3_SPIKE_MINQ)
        return dict(sym=sym, px=px, level=lvl, dist=round((lvl / px - 1) * 100, 2) if px else None,
                    vol_x=round(float(cur[7]) / need_q, 2) if need_q else None, bar=round((px / prev_c - 1) * 100, 2),
                    oi1h=(info.get(sym) or {}).get("oi1h"), flip=((info.get(sym) or {}).get("oi1h") or 0) >= cc.FAST3_FLIP_OI1H)
    with ThreadPoolExecutor(4) as ex:
        out = [r for r in ex.map(one, spike) if r]
    return sorted(out, key=lambda r: (r["dist"] if r["dist"] is not None else 99))


def reviews() -> dict:
    return {r["key"]: r for r in _rows(BASE_DIR / "output" / "fast_reviews.jsonl")}


HIST_DAYS = 6   # 28.09 владелец: «стрелки по бокам с переключением на предыдущий день» — лента показывает сделки прошлых дней (6 дн)


# 04.10 22:30 владелец: «давай заменим, так будет честнее, + комиссия биржи»; «на бумаге все сделки пусть остаются как есть в боте, в итог
# только реальное число попадает» (до этого час стоял вычет 20 $ / 8 $ на сделку — «8$ это просто цифра с потолка»). Бумажный результат сделки
# (usd, res) остаётся как в журнале бота. Рядом поле real — что эта сделка дала на BingX по данным самой биржи: исполнения ордеров
# (продано минус куплено) плюс комиссии; фандинг не входит (за 02–04.10 это −2 $). Сделки, которых на бирже не было, — real = None, в итог дня не идут. Сделки, которые были
# на бирже, а в журнале бота их нет (пачка сканера 03.10), добавляются книгой «только BingX», чтобы итог дня равнялся бирже.
BX_FILLS = BASE_DIR / "output" / "bingx_fills.json"
BX_ONLY_BOOK = "только BingX"


def _bx_fills(now: float, since: float) -> list[dict]:
    """исполнения ордеров на BingX (цена, объём, комиссия каждого исполнения) — /trade/allFillOrders, кэш в output/bingx_fills.json, дочитывается
    с последнего запроса по суткам. Выбраны исполнения, а не /user/income: доход биржа отдаёт с опозданием на часы (04.10 в 22:30 кончался на 10:00)."""
    cache = _read(BX_FILLS, {}) or {}
    rows = {r["id"]: r for r in cache.get("rows") or []}
    start = max(since, float(cache.get("last") or 0) - 3600)
    try:
        import bingx_trader as bx
        c = bx.cfg(); a = start
        while a < now:
            b = min(a + 86400, now)
            r = bx.request("GET", "/openApi/swap/v2/trade/allFillOrders", {"startTs": int(a * 1000), "endTs": int(b * 1000), "tradingUnit": "COIN"}, c) or {}
            if r.get("code") != 0:
                raise RuntimeError(f"{r.get('code')} {r.get('msg')}")
            d = r.get("data") or {}
            for x in (d.get("fill_orders") if isinstance(d, dict) else d) or []:
                t = datetime.fromisoformat(str(x.get("filledTime"))).timestamp()
                k = f"{x.get('orderId')}|{x.get('filledTime')}|{x.get('price')}|{x.get('volume')}"
                rows[k] = dict(id=k, sym=x.get("symbol"), side=x.get("side"), ps=x.get("positionSide"), px=float(x.get("price") or 0), qty=float(x.get("volume") or 0),
                               amt=float(x.get("amount") or 0), fee=float(x.get("commission") or 0), t=t)
            a = b
        out = sorted(rows.values(), key=lambda r: r["t"])
        tmp = BX_FILLS.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(last=now, rows=out), ensure_ascii=False), encoding="utf-8"); tmp.replace(BX_FILLS)
        return out
    except Exception as e:  # noqa: BLE001
        print(f"исполнения BingX: сбой {type(e).__name__}: {e} — беру кэш")
        return sorted(rows.values(), key=lambda r: r["t"])


def _bx_book() -> tuple[list, set]:
    """журнал зеркала BingX → сделки биржи: [{sym, bx, side, t_in, t_out, px_in, px_out, dead}], dead — лимит не исполнился, позиции не было;
    и монеты, открытые на бирже сейчас. Имя монеты на BingX берётся из запроса ордера рядом со входом."""
    trades, last_req, cur = [], {}, {}
    try:
        with open(BASE_DIR / "output" / "bingx_orders.jsonl", encoding="utf-8") as f:
            for ln in f:
                if '"kind": "req"' in ln:
                    if '"POST"' in ln and "/trade/order" in ln:
                        try:
                            e = json.loads(ln)
                        except ValueError:
                            continue
                        last_req = dict(t=float(e.get("t") or 0), bx=(e.get("params") or {}).get("symbol"))
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                k, sym, t = e.get("kind"), e.get("sym"), float(e.get("t") or 0)
                if k == "entry" and e.get("ok"):
                    bxs = last_req.get("bx") if last_req and t - last_req.get("t", 0) < 30 else None
                    if sym in cur:                                        # добор к открытой позиции (R63) — та же сделка
                        continue
                    cur[sym] = dict(sym=sym, bx=bxs or (sym[:-4] + "-USDT"), side=int(e.get("side") or 1), t_in=t, t_out=None, px_in=float(e.get("entry") or 0), px_out=None, dead=False)
                    trades.append(cur[sym])
                elif k in ("exit", "exit_manual") and sym in cur:
                    tr = cur.pop(sym); tr["t_out"] = t; tr["px_out"] = e.get("exit")
                    tr["dead"] = "лимит не исполнился" in str(e.get("why") or "")
                elif k == "entry_unfilled" and sym in cur:
                    tr = cur.pop(sym); tr["t_out"] = t; tr["dead"] = True
    except OSError:
        pass
    return trades, set((_read(BASE_DIR / "output" / "bingx_state.json", {}).get("open") or {}).keys())


def _bx_real(trades: list, fills: list) -> None:
    """каждой сделке биржи — её деньги по исполнениям: продано минус куплено по монете и стороне позиции за время жизни сделки, плюс комиссии
    (каждое исполнение идёт только в одну сделку). Объёмы входа и выхода не сошлись или исполнений нет — real остаётся None."""
    by = {}
    for r in fills:
        by.setdefault(r["sym"], []).append(r)
    used = set()
    for tr in sorted(trades, key=lambda x: x["t_in"]):
        tr["real"], tr["fee"] = None, 0.0
        if tr["dead"] or not tr["t_out"]:
            continue
        ps = "LONG" if tr["side"] == 1 else "SHORT"
        got = [r for r in by.get(tr["bx"], []) if r["id"] not in used and r["ps"] in (ps, "BOTH") and tr["t_in"] - 30 <= r["t"] <= tr["t_out"] + 120]
        buy = [r for r in got if r["side"] == "BUY"]; sell = [r for r in got if r["side"] == "SELL"]
        qb, qs = sum(r["qty"] for r in buy), sum(r["qty"] for r in sell)
        if not buy or not sell or abs(qb - qs) > 1e-9 * max(qb, qs, 1) + 1e-12:
            continue
        used.update(r["id"] for r in got)
        tr["fee"] = round(sum(r["fee"] for r in got), 2)
        tr["real"] = round(sum(r["amt"] for r in sell) - sum(r["amt"] for r in buy) + tr["fee"], 2)
        opn, cls = (buy, sell) if tr["side"] == 1 else (sell, buy)
        tr["fill_in"] = sum(r["amt"] for r in opn) / sum(r["qty"] for r in opn); tr["fill_out"] = sum(r["amt"] for r in cls) / sum(r["qty"] for r in cls)


def positions(now: float) -> tuple[list, list, list]:
    day0 = datetime.fromtimestamp(now, L).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    RV = reviews(); BXT, BXO = _bx_book()
    _bx_real(BXT, _bx_fills(now, day0 - (HIST_DAYS + 1) * 86400))
    for _t in BXT:
        _t["paired"] = False
    op, cl, hist = [], [], []
    for book, stem in BOOKS:
        stt = _read(BASE_DIR / "output" / f"{stem}.json", {})
        R = _rows(BASE_DIR / "output" / f"{stem}.jsonl")
        ent = {(r.get("sym"), round(float(r.get("at") or 0), 3)): r for r in R if r.get("kind") == "entry"}
        for sym, p in (stt.get("open") or {}).items():
            e, sd = float(p["px"]), int(p["side"])
            er = ent.get((sym, round(float(p["at"]), 3))) or {}
            op.append(dict(book=book, sym=sym, side=sd, entry=e, target=(None if not 0 < float(p.get("target") or 0) < 0.9 else e * (1 + sd * float(p["target"]))),   # 04.10: у позиции без цели (0 — шорты R58 и R65) цель не показываем, раньше рисовалась на цене входа
                           stop=(float(p["stop_px"]) if p.get("stop_px") else e * (1 - sd * float(p["stop"]))),      # 04.10: стоп, перенесённый в твх или на низ удержания, показываем как есть
                           tp=float(p["target"]), sl=float(p["stop"]), t_in=float(p["at"]), goal=_goal(p, e, sd),
                           exit_at=(int(p["t_ms"]) + B3) / 1000 + int(p.get("hold_min") or 0) * 60, px=p.get("last_px"), rule=p.get("rule") or "",
                           oi1h_in=er.get("oi1h"), board6_in=(er.get("fon") or {}).get("board6"), bx=sym in BXO))
        for r in R:
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("at") or 0) < day0 - HIST_DAYS * 86400:
                continue
            key = f"{book}|{r['sym']}|{int(float(r['at']))}"
            t_in = float(r.get("opened_at") or 0)
            tr = next((x for x in BXT if x["sym"] == r["sym"] and not x["paired"] and abs(x["t_in"] - t_in) < 1200), None)
            if tr:
                tr["paired"] = True
            (cl if float(r["at"]) >= day0 else hist).append(dict(book=book, sym=r["sym"], side=int(r.get("side") or 1), entry=float(r["px_in"]), exit=float(r.get("px_out") or 0),
                           t_in=t_in, t_out=float(r["at"]), why=r.get("why_exit") or "", res=float(r["result_pct"]),
                           usd=round(float(r["usd"]) if r.get("usd") is not None else float(r["result_pct"]) * 5, 2),   # 29.09: сумма сделки берётся из записи; это БУМАЖНЫЙ результат, как в журнале бота
                           bx=bool(tr and not tr["dead"]), real=(tr or {}).get("real"), fee=(tr or {}).get("fee"),    # 04.10: real — деньги этой сделки на BingX с комиссией (None — на бирже не было или биржа ещё не отдала)
                           rule=r.get("rule") or "", review=RV.get(key)))
    for tr in BXT:                                                        # были на бирже, а в журнале бота сделки нет — в итог дня идут по данным биржи
        if tr["paired"] or tr["dead"] or tr.get("real") is None or tr["t_out"] < day0 - HIST_DAYS * 86400:
            continue
        pi, po = float(tr.get("fill_in") or tr["px_in"]), float(tr.get("fill_out") or tr["px_out"] or 0)
        (cl if tr["t_out"] >= day0 else hist).append(dict(book=BX_ONLY_BOOK, sym=tr["sym"], side=tr["side"], entry=pi, exit=po or pi, t_in=tr["t_in"], t_out=tr["t_out"],
                       why="закрыта на бирже", res=round((po / pi - 1) * tr["side"] * 100, 2) if pi and po else 0.0, usd=0.0, bx=True, real=tr["real"], fee=tr["fee"],
                       rule="сделка была на BingX, в журнале бота её нет", review=None))
    cl.sort(key=lambda x: -x["t_out"])
    hist.sort(key=lambda x: -x["t_out"])
    return op, cl, hist


def _liq(syms: set, t0: float) -> dict:
    """ликвидации по сторонам из нашего потока (OKX + Bybit), по трёхминуткам; сторона — кого вынесли"""
    out = {s: {} for s in syms}
    seen = set()
    for d in {datetime.fromtimestamp(t0, timezone.utc).date(), datetime.now(timezone.utc).date()}:
        for r in _rows(BASE_DIR / "cq_v2" / "liq" / f"{d}.jsonl"):
            s = r.get("sym")
            if s not in out or r.get("t", 0) < t0 * 1000:
                continue
            k = (r["t"], s, r.get("side"), r.get("usd"), r.get("src"))
            if k in seen:
                continue
            seen.add(k)
            b = int(r["t"]) // B3 * B3
            cell = out[s].setdefault(b, [0.0, 0.0])
            cell[0 if r.get("side") == "long" else 1] += float(r.get("usd") or 0)
    return out


def charts(syms: list[str]) -> dict:
    n = CHART_H * 20

    def one(sym):
        k = _k3(sym, n)
        if not k:
            return sym, None
        sk = get_json("https://api.binance.com/api/v3/klines", {"symbol": sym, "interval": "3m", "limit": n}, quiet_400=True, weight=2) or []
        oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": CHART_H * 12},
                      quiet_400=True) or []
        pi = get_json("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": sym}, quiet_400=True) or {}
        cvd = 0.0; bars = []
        for x in k:
            q, tb = float(x[7]), float(x[10]); cvd += 2 * tb - q
            bars.append([int(x[0]), float(x[1]), float(x[2]), float(x[3]), float(x[4]), round(q), round(cvd)])
        scvd, spot = 0.0, {}
        for x in sk:
            q, tb = float(x[7]), float(x[10]); scvd += 2 * tb - q
            spot[int(x[0])] = round(scvd)
        return sym, dict(bars=bars, spot=[spot.get(b[0]) for b in bars] if spot else None,
                         oi=[[int(x["timestamp"]), round(float(x["sumOpenInterestValue"]))] for x in oi],
                         funding=round(float(pi.get("lastFundingRate") or 0) * 100, 4) if pi else None)
    with ThreadPoolExecutor(4) as ex:
        res = dict(r for r in ex.map(one, syms) if r[1])
    if res:
        t0 = min(v["bars"][0][0] for v in res.values()) / 1000
        lq = _liq(set(res), t0)
        for s, v in res.items():
            v["liq"] = [lq.get(s, {}).get(b[0], [0.0, 0.0]) for b in v["bars"]]
    return res


def _goal(p: dict, e: float, sd: int) -> str:
    """04.10 владелец по карточке AGT («цели нет: выход по выносу лонгов, стопу или сроку» — «какой срок?», «надо дописывать: цели нет в философии, в боте цель есть всегда,
    просто это может быть не конкретная цена»): подпись цели для позиции без цены-цели — что именно её закроет и когда."""
    t = float(p.get("target") or 0)
    if 0 < t < 0.9:
        return ""
    ex = datetime.fromtimestamp((int(p["t_ms"]) + 180_000) / 1000 + int(p.get("hold_min") or 0) * 60, L)
    hrs = int(p.get("hold_min") or 0) / 60
    be = bool(p.get("stop_px")) and abs(float(p["stop_px"]) / e - 1) < 1e-6
    stp = "стоп в точке входа" if be else f"стоп {float(p.get('stop') or 0) * 100:.0f}%, после хода 5% — в точку входа"
    if p.get("slide") or p.get("pump_end"):
        return f"цель — выход по времени {ex:%d.%m %H:%M} ({hrs:.0f} ч от входа) · {stp}"
    if sd == -1:
        return f"цель — вынос лонгов или срок {ex:%d.%m %H:%M} · {stp}"
    return f"цель — срок {ex:%d.%m %H:%M} · {stp}"


def score(cl: list[dict]) -> dict:
    out = {}
    for book, _ in BOOKS:
        g = [x for x in cl if x["book"] == book]
        out[book] = dict(n=len(g), win=sum(1 for x in g if x["res"] > 0), usd=round(sum(x["usd"] for x in g), 1))
    return out


# 03.10 23:30 владелец: «разобьём на 3 сводки за каждые 3 часа», «рост / нейтрально / падение» — вместо линий по 3 минуты на странице восемь трёхчасовых блоков на каждую из трёх строк.
# Граница «нейтрально» — типичный ход строки за 3 часа (медиана модуля по часовым данным TradingView 12.09–03.10, 220 блоков): доска 0.31 %, все монеты 0.42 %, BTC 0.27 %;
# при таких границах половина блоков нейтральные, по четверти — рост и падение.
# 04.10 03:50 владелец: «поставь пороги 0,57 и 0,59» — после смены состава (только крипто) и расчёта (медиана ходов за блок) прежние 0.31 / 0.42 давали треть нейтральных блоков;
# медиана модуля хода за блок на 23 днях часовых данных (10.09–02.10, 184 блока): доска 0.57 %, все монеты 0.59 %. Порог BTC прежний (про него владелец не говорил).
NEUTRAL_3H = (0.57, 0.59, 0.27)
_B3H: dict = {}

# ── СОСТАВ ДОСКИ (04.10 03:40, владелец: «в доску и все монеты должны входить ТОЛЬКО крипто-монеты… всё некриптовое отбрасываем»; «делай правки медиан и доски и акций, золота»;
#    «всё, что я прислал, принимаю»). Делим по разметке самой Binance (fapi/v1/exchangeInfo): крипто = contractType PERPETUAL и underlyingType COIN. Всё остальное — не доска:
#    акции и ETF (EQUITY, HK_/KR_/CN_EQUITY), бумаги до размещения (PREMARKET), сырьё и металлы (COMMODITY), валюта (FX), индексы (INDEX: BTCDOM, ALL).
#    Поверх разметки — явный список BOARD_EXCLUDE: то, что Binance числит монетой, а по решению владельца в доску не входит.
#    Справочник читается раз в сутки и кладётся в output/board_universe.json (keep — состав, drop — кто отброшен и почему); не скачался — берётся прошлый файл.
BOARD_EXCLUDE = {"USDCUSDT": "стейблкоин", "PAXGUSDT": "золото (токен)", "XAUTUSDT": "золото (токен)"}
BOARD_TYPE_WHY = {"EQUITY": "акция или ETF США", "HK_EQUITY": "бумага Гонконга", "KR_EQUITY": "бумага Кореи", "CN_EQUITY": "бумага Китая", "PREMARKET": "компания до размещения",
                  "COMMODITY": "сырьё или металл", "FX": "валютная пара", "INDEX": "индекс, не монета"}
SNAP_LATE = 600   # снимок цен на начало 3-часового блока годится, если сборка успела за 10 минут от начала блока (техническая граница, не торговая)


def board_universe(now: float):
    """→ множество символов крипто-состава доски или None (справочника нет ни с биржи, ни в файле — тогда доска считается по всем, как раньше)"""
    f = BASE_DIR / "output" / "board_universe.json"; u = _read(f, {})
    day = datetime.fromtimestamp(now, L).strftime("%Y-%m-%d")
    if u.get("day") != day or not u.get("keep"):
        try:
            ex = get_json("https://fapi.binance.com/fapi/v1/exchangeInfo") or {}
            keep, drop = [], {}
            for x in ex.get("symbols", []):
                s_ = str(x.get("symbol", ""))
                if not s_.endswith("USDT") or x.get("status") != "TRADING":
                    continue
                if s_ in BOARD_EXCLUDE:
                    drop[s_] = BOARD_EXCLUDE[s_]
                elif x.get("contractType") == "PERPETUAL" and x.get("underlyingType") == "COIN":
                    keep.append(s_)
                else:
                    drop[s_] = BOARD_TYPE_WHY.get(str(x.get("underlyingType")), f"не крипто ({x.get('contractType')}/{x.get('underlyingType')})")
            if len(keep) >= 100:
                u = {"day": day, "t": now, "keep": sorted(keep), "drop": dict(sorted(drop.items()))}
                f.write_text(json.dumps(u, ensure_ascii=False), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
    return set(u["keep"]) if u.get("keep") else None


def _blocks_old(day: str, rows: list, now: float) -> list:
    """прежний расчёт (до 04.10) — ход самого ряда между двумя моментами; остаётся запасным для блоков, где нет снимков цен"""
    d0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=L).timestamp(); out = []
    def at(t):                                                            # значение на момент t: последняя точка не позже t (до первой точки — ноль, это 00:00)
        v = [0.0, 0.0, 0.0]
        for r in rows:
            if r[0] <= t + 90: v = r[1:4]
            else: break
        return v
    last_t = rows[-1][0] if rows else d0
    for k in range(8):
        t0, t1 = d0 + k * 10800, d0 + (k + 1) * 10800
        if last_t < t0 + 90 or t0 > now:
            out.append(None); continue
        a, b = at(t0), at(min(t1, last_t))
        out.append([round(((1 + b[j] / 100) / (1 + a[j] / 100) - 1) * 100, 2) for j in range(3)])
    return out


def _blocks_3h(day: str, rows: list, now: float, snaps: dict | None = None, nxt: dict | None = None) -> list:
    """восемь трёхчасовых блоков дня: [[доска %, все монеты %, BTC %], …], None — блок ещё не начался.
    04.10 владелец: доска = медиана ходов крипто-монет ЗА БЛОК (цена конца блока / цена начала блока − 1), все монеты = среднее тех же ходов, BTC = его ход за блок
    (раньше брался ход самой медианы от 00:00 между двумя моментами: разность медиан ≠ медиана разностей). Снимки цен на начало блоков — snaps {"0".."7": {t, px}, "last": {t, px}};
    конец блока — снимок начала следующего (у последнего блока дня — снимок 00:00 следующего дня, nxt), у текущего — последняя точка. Монеты, которых нет в обоих снимках, пропускаются.
    Блок без снимков (старые дни, пропуск сборки) считается прежним способом по ряду rows."""
    old = _blocks_old(day, rows, now)
    if not snaps:
        return old
    d0 = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=L).timestamp(); out = []
    for k in range(8):
        if old[k] is None:
            out.append(None); continue
        t1 = d0 + (k + 1) * 10800
        a = snaps.get(str(k))
        b = (snaps.get(str(k + 1)) if k < 7 else nxt) if now >= t1 else snaps.get("last")
        if now >= t1 and not b:
            b = snaps.get("last") if abs((snaps.get("last") or {}).get("t", 0) - t1) <= SNAP_LATE else None   # следующего снимка нет — годится последняя точка дня, только если она у самого конца блока
        try:
            pa, pb = a["px"], b["px"]
            mv = [(pb[s_] / pa[s_] - 1) * 100 for s_ in pa if pa[s_] > 0 and pb.get(s_)]
            if len(mv) < 100 or not pa.get("BTCUSDT") or not pb.get("BTCUSDT") or b["t"] <= a["t"]:
                raise ValueError
            out.append([round(st.median(mv), 2), round(sum(mv) / len(mv), 2), round((pb["BTCUSDT"] / pa["BTCUSDT"] - 1) * 100, 2)])
        except (TypeError, KeyError, ValueError):
            out.append(old[k])
    return out


def board_day(now: float) -> dict:
    """03.10 владелец: «добавим медиану доски линией, цену биткоина линией и общее движение всех монет линией… важно не текущее положение, а что было в течение дня».
    Раз в сборку (3 мин) один запрос цен по всему Binance: ход каждой КРИПТО-монеты (board_universe) от её цены в 00:00 (UTC+3) → медиана доски, среднее по всем монетам, BTC, в %.
    output/board_base.json — цены на начало суток; output/board_day.jsonl — точки [t, медиана, среднее, BTC] по дням; output/board_base_3h.json — снимки цен крипто-состава на начало
    каждого 3-часового блока и последняя точка дня ({день: {"0".."7"/"last": {t, px}}}, 9 дней). → {день: [[t, med, avg, btc], …]} за 8 дней"""
    base_f = BASE_DIR / "output" / "board_base.json"; day_f = BASE_DIR / "output" / "board_day.jsonl"; snap_f = BASE_DIR / "output" / "board_base_3h.json"
    dt = datetime.fromtimestamp(now, L); day = dt.strftime("%Y-%m-%d")
    d0 = dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    snaps_all = _read(snap_f, {})
    try:
        tk = get_json("https://fapi.binance.com/fapi/v1/ticker/price", weight=2) or []
        px = {x["symbol"]: float(x["price"]) for x in tk if str(x.get("symbol", "")).endswith("USDT") and float(x.get("price") or 0) > 0}
        if len(px) >= 100:
            uni = board_universe(now)
            base = _read(base_f, {})
            if base.get("day") != day:
                base = {"day": day, "t": now, "px": px}; base_f.write_text(json.dumps(base), encoding="utf-8")
            pc = {s_: v for s_, v in px.items() if uni is None or s_ in uni}       # только крипто-состав
            ch = [(pc[s_] / base["px"][s_] - 1) * 100 for s_ in pc if base["px"].get(s_)]
            if len(ch) >= 100 and "BTCUSDT" in px and base["px"].get("BTCUSDT"):
                row = [int(now), round(st.median(ch), 3), round(sum(ch) / len(ch), 3), round((px["BTCUSDT"] / base["px"]["BTCUSDT"] - 1) * 100, 3)]
                with day_f.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"day": day, "r": row}) + "\n")
            if len(pc) >= 100:                                                     # снимки цен по блокам
                sd = snaps_all.setdefault(day, {})
                if "0" not in sd and base.get("day") == day and float(base.get("t") or 0) - d0 <= SNAP_LATE:
                    sd["0"] = {"t": base["t"], "px": {s_: v for s_, v in base["px"].items() if uni is None or s_ in uni}}
                k = int((now - d0) // 10800)
                if str(k) not in sd and now - (d0 + k * 10800) <= SNAP_LATE:
                    sd[str(k)] = {"t": now, "px": pc}
                sd["last"] = {"t": now, "px": pc}
                keep9 = {(dt - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(9)}
                for d_ in [d_ for d_ in snaps_all if d_ not in keep9]:
                    del snaps_all[d_]
                tmp = snap_f.with_suffix(".tmp"); tmp.write_text(json.dumps(snaps_all, separators=(",", ":")), encoding="utf-8"); tmp.replace(snap_f)
    except Exception:  # noqa: BLE001
        pass
    out: dict = {}
    try:
        keep = {(datetime.fromtimestamp(now, L) - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(8)}
        for ln in day_f.open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("day") in keep:
                out.setdefault(r["day"], []).append(r["r"])
        for d_ in out:
            out[d_].sort()
            nd = (datetime.strptime(d_, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
            _B3H[d_] = _blocks_3h(d_, out[d_], now, snaps_all.get(d_), (snaps_all.get(nd) or {}).get("0"))
            # 03.10 23:20 владелец: «давай может не рисовать графики за каждые 3 минуты» — на страницу отдаётся одна точка на 15 минут (последняя в интервале и самая свежая);
            # в файле output/board_day.jsonl остаются все точки
            thin: dict = {}
            for r in out[d_]:
                thin[int(r[0]) // BOARD_STEP] = r
            rows = [thin[k] for k in sorted(thin)]
            if rows and rows[-1] is not out[d_][-1]:
                rows.append(out[d_][-1])
            out[d_] = rows
    except OSError:
        pass
    return out


def build() -> dict:
    now = time.time()
    op, cl, hist = positions(now)
    ent = candidates()
    # графики: открытые (кольцо «вход») и закрытые сегодня (кольцо «выход» и лента); кандидаты на странице не показываются
    syms = list(dict.fromkeys([p["sym"] for p in op] + [c["sym"] for c in cl]))[:40]
    try:                                                                 # 03.10 владелец: «сюда выводи информацию о доске» (правый верхний круг сайта) — output/board_now.json пишет fast_tier (R54)
        board = json.loads((BASE_DIR / "output" / "board_now.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        board = None
    return dict(meta=meta(now), entry=ent, open=op, closed=cl, closed_hist=hist, charts=charts(syms), score=score(cl), board=board, board_day=board_day(now), board_3h=dict(blocks=dict(_B3H), neutral=list(NEUTRAL_3H)))


def write() -> Path:
    s = build()
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    return OUT


if __name__ == "__main__":
    import fcntl
    _lk = open(OUT.with_suffix(".lock"), "w")
    try:
        fcntl.flock(_lk, fcntl.LOCK_EX | fcntl.LOCK_NB)     # fast_tier зовёт каждые 3 мин, сборка ~40 с — второй раз не запускаем
    except OSError:
        raise SystemExit(0)
    t = time.time()
    p = write()
    d = json.loads(p.read_text())
    print(f"fast_state: вход {len(d['entry'])}, в работе {len(d['open'])}, закрыто {len(d['closed'])}, графиков {len(d['charts'])}, "
          f"{p.stat().st_size // 1024} КБ, {time.time() - t:.0f} с")
    # 04.10 04:15 владелец: «давай только в журнал сделок тогда писать и всё», «делай» — страница журнала сделок на сайте (book.html, render_book.py) собирается здесь же,
    # каждые 3 минуты (сборка ~1 с); на сайт уходит вместе с прогоном — он выкладывает все изменившиеся файлы. Ни прогон, ни бот для этого не перезапускаются.
    try:
        import render_book
        _bk = BASE_DIR / "book.html"; _tmp = _bk.with_suffix(".tmp")
        _tmp.write_text(render_book.render_book(), encoding="utf-8"); _tmp.replace(_bk)
        print(f"книга: book.html {_bk.stat().st_size // 1024} КБ")
    except Exception as e:  # noqa: BLE001
        print(f"книга: не собралась — {type(e).__name__}: {e}")
