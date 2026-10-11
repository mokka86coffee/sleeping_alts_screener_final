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


def _hold(p: dict) -> int:
    """срок позиции в минутах с потолком R74 (06.10: «не должны сделки висеть больше 16 часов», кроме шорта «конец роста» от вершины пампа — 3 дня) — как fast_tier._hold_lim"""
    h = int(p.get("hold_min") or 0); cap = int(getattr(cc, "FAST3_MAX_HOLD_MIN", 0) or 0)
    return h if (not cap or p.get("pump_end")) else min(h, cap)

U = timezone.utc                    # 06.10 владелец: «всё должно быть в utc везде» — сессии и время в подписях считаются по UTC
L = timezone(timedelta(hours=3))    # ТОЛЬКО граница суток для доски и дневных списков сайта: сутки начинаются в 21:00 UTC (как было до 06.10).
                                    # От машины не зависит. Перенос границы на 00:00 UTC меняет числа доски за день — ждёт слова владельца.
OUT = BASE_DIR / "output" / "fast_state.json"
WIN = (("Токио", 0, 7), ("Лондон", 7, 13), ("Нью-Йорк", 13, 21), ("Сидней", 21, 24))   # часы UTC (06.10), как fast_tier.SES_WIN
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
BOOKS = (("всплеск/вынос", "paper_fast3"), ("пробуждение", "paper_wake"), ("очередь", "paper_queue"))   # 10.10: + книга «очередь» (R83)
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
    d = datetime.fromtimestamp(now, U)
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
        if not tr["t_out"]:
            continue
        # 05.10 владелец: «буду руками сделки закрывать» — позицию, закрытую вручную на бирже, зеркало при выходе бота записывает как «лимит не исполнился,
        # позиции не было» (dead). Была она или нет, решают исполнения: есть вход и выход в равном объёме — сделка была, считаем её деньги.
        ps = "LONG" if tr["side"] == 1 else "SHORT"
        got = [r for r in by.get(tr["bx"], []) if r["id"] not in used and r["ps"] in (ps, "BOTH") and tr["t_in"] - 30 <= r["t"] <= tr["t_out"] + 120]
        buy = [r for r in got if r["side"] == "BUY"]; sell = [r for r in got if r["side"] == "SELL"]
        qb, qs = sum(r["qty"] for r in buy), sum(r["qty"] for r in sell)
        if not buy or not sell or abs(qb - qs) > 1e-9 * max(qb, qs, 1) + 1e-12:
            continue
        used.update(r["id"] for r in got)
        tr["dead"] = False
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
                           exit_at=(int(p["t_ms"]) + B3) / 1000 + _hold(p) * 60, px=p.get("last_px"), rule=p.get("rule") or "",
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
    if p.get("manual_exit_px"):                                          # 11.10: цена выхода, поставленная владельцем вручную
        return f"цель {float(p['manual_exit_px']):.6g} — поставлена владельцем вручную · выход по времени и стоп как были"
    ex = datetime.fromtimestamp((int(p["t_ms"]) + 180_000) / 1000 + _hold(p) * 60, U)
    hrs = _hold(p) / 60
    be = bool(p.get("stop_px")) and abs(float(p["stop_px"]) / e - 1) < 1e-6
    stp = "стоп в точке входа" if be else f"стоп {float(p.get('stop') or 0) * 100:.0f}%, после хода 5% — в точку входа"
    if p.get("pump_end"):                                                # R85 (11.10): шорт «конец роста» выходит ещё и у дна — числа владельца из общего конфига
        try:
            from core_config import MANUAL_BY_USER_PUMP_END_LOW_DAYS as _ld, MANUAL_BY_USER_PUMP_END_LOW_PCT as _lp
        except ImportError:
            _ld, _lp = 60, 20
        low = f" или цена не выше {_lp:g}% над дном за {_ld} дн" if _lp else ""
        return f"цель — выход по времени {ex:%d.%m %H:%M} UTC ({hrs:.0f} ч от входа){low} · {stp}"
    if p.get("slide"):
        return f"цель — выход по времени {ex:%d.%m %H:%M} UTC ({hrs:.0f} ч от входа) · {stp}"
    if sd == -1:
        return f"цель — вынос лонгов или срок {ex:%d.%m %H:%M} UTC · {stp}"
    return f"цель — срок {ex:%d.%m %H:%M} UTC · {stp}"


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
_P3H: dict = {}   # 08.10: {сегодня: {"k": номер идущего 3-часового блока, "n": сколько его получасов уже посчитано (1–5)}} — ширина ячейки на странице

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
        if now < t1:                                                      # 08.10 владелец: идущий блок — «из того что есть каждые полчаса… за 30 мин, на часе за весь час… завершается достигнув 3ч»:
            hf = snaps.get("half") or {}                                  #   ход с начала блока до последней получасовой отметки; до первой отметки (30 мин) ячейки нет
            if hf.get("k") == k and hf.get("n"):
                out.append(hf.get("v") or _blocks_old(day, [r for r in rows if r[0] <= hf["t"] + 90], now)[k])
            else:
                out.append(None)
            continue
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
                n = int((now - (d0 + k * 10800)) // 1800)                      # 08.10 владелец: «каждые полчаса должны обновляться данные… 30м 1ч 1ч30м 2ч 2ч30м и 3ч» — сколько получасов идущего блока прошло
                hf = sd.get("half") or {}
                if n >= 1 and (hf.get("k"), hf.get("n")) != (k, n):             # первая сборка после отметки: ход всех монет с начала блока (как у закрытого блока — медиана, среднее, BTC)
                    v, a0 = None, sd.get(str(k))
                    if a0:
                        mv = [(pc[s_] / a0["px"][s_] - 1) * 100 for s_ in a0["px"] if a0["px"][s_] > 0 and pc.get(s_)]
                        if len(mv) >= 100 and a0["px"].get("BTCUSDT") and pc.get("BTCUSDT"):
                            v = [round(st.median(mv), 2), round(sum(mv) / len(mv), 2), round((pc["BTCUSDT"] / a0["px"]["BTCUSDT"] - 1) * 100, 2)]
                    sd["half"] = {"k": k, "n": n, "t": now, "v": v}
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
            if d_ == day:
                hf = (snaps_all.get(d_) or {}).get("half") or {}; kk = int((now - d0) // 10800)
                _P3H.clear()
                if hf.get("k") == kk and hf.get("n"):
                    _P3H[d_] = {"k": kk, "n": int(hf["n"])}
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


BX_MISS_KEEP = 30 * 60        # 06.10 владелец: «надо чтобы флаг с невзятым на бирже висел дольше — до 30 минут с пометкой»
BX_UNCLOSED_AFTER = 200       # позиция на бирже без сделки бота дольше одного цикла (3 мин) — «не закрыто»; меньше — зеркало ещё могло не успеть
BX_WARN_MISS = "НЕ ВЗЯТО НА BINGX"
BX_WARN_OPEN = "НЕ ЗАКРЫТО НА BINGX"


def bx_warn(now: float, op: list, cl: list) -> list:
    """ПРЕДУПРЕЖДЕНИЯ ЗЕРКАЛА (06.10 владелец: «флаг с невзятым на бирже висел дольше — до 30 минут с пометкой», «то что не закрыто на бирже должно
    висеть всегда, пока ордер не закроется, и бот должен сам проверять, закрыто или нет»).
    Не взято — запись зеркала output/bingx_orders.jsonl: вход с отказом (ok false, причина в why) или вход, пропущенный заморозкой после правки бота.
    Открытой сделке бота без биржи метка ставится прямо в её запись (op); если бумажная сделка уже закрыта — отдельный флаг на 30 минут.
    Не закрыто — монета есть в output/bingx_state.json (зеркало сверяет позиции с биржей каждый цикл и повторяет выход), а у бота сделки по ней нет."""
    miss: dict = {}
    try:
        with open(BASE_DIR / "output" / "bingx_orders.jsonl", encoding="utf-8") as f:
            for ln in f:
                if '"kind": "req"' in ln[:80]:
                    continue
                try:
                    e = json.loads(ln)
                except ValueError:
                    continue
                t = float(e.get("t") or 0)
                if now - t > BX_MISS_KEEP + 1200:
                    continue
                if e.get("kind") == "entry" and not e.get("ok"):
                    miss[e.get("sym")] = dict(t=t, why=str(e.get("why") or "зеркало не вошло"), side=int(e.get("side") or 1))
                elif e.get("kind") == "entry" and e.get("ok"):
                    miss.pop(e.get("sym"), None)                          # вторая книга вошла — монета на бирже есть
                elif e.get("kind") == "freeze":
                    for sy in e.get("skipped") or []:
                        miss[sy] = dict(t=t, why=f"входы на BingX заморожены после правки бота (ещё {e.get('left_min')} мин)", side=None)
    except OSError:
        pass
    out, open_syms = [], {o["sym"] for o in op}
    for o in op:                                                          # открыта у бота, на бирже нет — метка в саму сделку
        if o.get("bx") is False:
            m = miss.get(o["sym"]) or {}
            o["warn"], o["warn_why"], o["keep"] = BX_WARN_MISS, m.get("why") or "на бирже позиции нет", BX_MISS_KEEP
    for c in cl:                                                          # бумажная сделка уже закрыта — причина в её запись и отдельный флаг до 30 минут от входа
        m = miss.get(c["sym"])
        if not m or c.get("bx") or c.get("book") == BX_ONLY_BOOK or abs(float(c["t_in"]) - m["t"]) > 1200:
            continue
        c["warn_why"] = m["why"]
        if now - float(c["t_in"]) < BX_MISS_KEEP and c["sym"] not in open_syms and not any(w["sym"] == c["sym"] for w in out):
            out.append(dict(kind_w="miss", sym=c["sym"], side=c["side"], book=c["book"], t_in=c["t_in"], entry=c["entry"], level=c["entry"], px=c.get("exit") or c["entry"],
                            dist=0.0, warn=BX_WARN_MISS, warn_why=m["why"] + f" · бот уже вышел: {c.get('res', 0):+.1f}%", keep=BX_MISS_KEEP, bx=False))
    last_out: dict = {}
    for c in cl:
        last_out[c["sym"]] = max(last_out.get(c["sym"], 0), float(c["t_out"]))
    for sym, st_ in ((_read(BASE_DIR / "output" / "bingx_state.json", {}) or {}).get("open") or {}).items():
        if sym in open_syms:
            continue
        t0 = last_out.get(sym) or float(st_.get("t") or now)
        if now - t0 < BX_UNCLOSED_AFTER:
            continue
        e = float(st_.get("fill") or st_.get("entry") or 0)
        out.append(dict(kind_w="unclosed", sym=sym, side=int(st_.get("side") or 1), book="BingX", t_in=t0, entry=e, level=e, px=e, dist=0.0, warn=BX_WARN_OPEN,
                        warn_why="бот из сделки вышел, позиция на бирже осталась — зеркало повторяет выход каждый цикл", keep=10 ** 12, bx=True))
    return out


def bx_warn_tg(s: dict, now: float) -> None:
    """отдельное предупреждение в Телеграм (06.10 владелец: «и в тг приходило отдельное предупреждение — не взято и не закрыто»): по одному разу на случай;
    когда «не закрыто» ушло — сообщение, что закрыто. Память — output/bx_warn_tg.json. Зовётся только из запуска файла (не из build), проверки бота его не трогают."""
    try:
        on = bool(getattr(cc, "FAST3_TG_BX_WARN", True))
    except Exception:  # noqa: BLE001
        on = True
    if not on:
        return
    mem_f = BASE_DIR / "output" / "bx_warn_tg.json"
    first = not mem_f.exists()
    sent = dict((_read(mem_f, {}) or {}).get("sent") or {})
    items = [o for o in (s.get("open") or []) if o.get("warn")] + list(s.get("bx_warn") or [])
    todo, live = [], set()
    for it in items:
        unclosed = it["warn"] == BX_WARN_OPEN
        key = f"unclosed|{it['sym']}" if unclosed else f"miss|{it['sym']}|{round(float(it['t_in']))}"
        live.add(key)
        if key in sent or (not unclosed and now - float(it["t_in"]) >= BX_MISS_KEEP):
            continue
        sent[key] = now
        side = "ЛОНГ" if int(it.get("side") or 1) == 1 else "ШОРТ"
        t_in = datetime.fromtimestamp(float(it["t_in"]), timezone.utc)
        body = ([f"⚠️ {BX_WARN_OPEN} · {side} · {it['sym'][:-4]}", "", "бот из сделки вышел, позиция на бирже осталась", "зеркало повторяет выход каждые 3 минуты"] if unclosed else
                [f"⚠️ {BX_WARN_MISS} · {side} · {it['sym'][:-4]}", f"📘 {it.get('book')}", "", f"причина: {it.get('warn_why')}", f"вход бота: {float(it['entry']):.6g} · {t_in:%H:%M} UTC"])
        todo.append((it["sym"], "\n".join(body)))
    for key in [k for k in sent if k.startswith("unclosed|") and k not in live]:
        sym = key.split("|")[1]
        todo.append((sym, f"✅ ЗАКРЫТО НА BINGX · {sym[:-4]}\n\nпозиции на бирже больше нет"))
        sent.pop(key, None)
    sent = {k: v for k, v in sent.items() if k in live or now - float(v) < 2 * 86400}
    if not first:                                                         # первый запуск — только запомнить, что уже висит
        try:
            import cg_shot
            for sym, txt in todo:
                cg_shot.send_text(txt + "\n\n" + cg_shot.links(sym))
        except Exception as e:  # noqa: BLE001
            print(f"предупреждения зеркала в Телеграм: {type(e).__name__}: {e}")
    try:
        tmp = mem_f.with_suffix(".tmp"); tmp.write_text(json.dumps(dict(sent=sent), ensure_ascii=False), encoding="utf-8"); tmp.replace(mem_f)
    except OSError:
        pass
    if todo:
        print(f"предупреждения зеркала: {len(todo)}" + (" (первый запуск — не отправлены)" if first else " → Телеграм"))



# ── ПРОГНОЗЫ · ЗВЁЗДЫ · ОЧЕРЕДЬ ДЛЯ СТРАНИЦЫ (09.10 17:20 UTC, владелец: «его тоже нужно будет обновлять из прогона основного без перезагрузки
#    страницы», промт из чата дизайна: поля STATE.forecasts / STATE.stars / STATE.queue; «звёзды из очереди в щите — те, что в первых 3 местах
#    больше 2 раз подряд, т.е. показываются, когда попадают 3-й раз»). Дизайн в fast_site/index.html не трогаем — только данные. Время — unix UTC.
FC_TAIL = 4_000_000          # хвост output/forecasts.jsonl, байт (≈ 6 дней прогонов) — мерка Claude
FC_WIN_H = 72                # окно линии цены и меток смен в панели — 3 дня получасовок cq_v2/intraday (без запросов к бирже)
QL_TAIL = 12_000_000         # хвост output/queue_log.jsonl, байт (≈ сутки прогонов); строки без места отбрасываются до разбора
Q_TOP, Q_RUNS = 3, 3         # владелец: первые 3 места, 3 прогона подряд
Q_RUNS_FIRST = 2             # 10.10 01:55 UTC владелец (OGN «1 (2) 03:41–04:11»): «про первых немного поменяем: если 2-й раз подряд, то показываем»
Q_SLIP = 2                   # владелец: смещение с закреплённого места терпим не больше 2 прогонов
Q_WIN_H = 24                 # окно прогонов для серий — скользящие сутки, не календарные UTC (10.10)
Q_PATH = 3                   # 09.10 владелец: «последние 3 и основное» — места трёх прошлых прогонов мелкими и закреплённое место в большом кристалле
KEEP_S = 24 * 3600           # сколько держать на реке: пока монета есть в массиве (сутки — чтобы решал массив, а не срок) — мерка Claude
STARS_MEM = BASE_DIR / "output" / "fast_stars_mem.json"


def _tail_lines(p: Path, nbytes: int) -> list[str]:
    try:
        with p.open("rb") as f:
            f.seek(0, 2); size = f.tell(); f.seek(max(0, size - nbytes))
            raw = f.read().decode("utf-8", "ignore")
    except OSError:
        return []
    ls = raw.splitlines()
    return ls[1:] if len(ls) > 1 else ls


def _unix(at: str, hm: str = "") -> float:
    s = at if len(at) >= 16 else f"{at}T{hm}:00"
    s = s.replace("Z", "")[:19]
    if len(s) == 16:
        s += ":00"
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp()


def _intraday_px(sym: str, t0: float) -> tuple[list, list]:
    """закрытия получасовок cq_v2/intraday с момента t0 → (цены, время unix)"""
    p = BASE_DIR / "cq_v2" / "intraday" / (sym[:-4].lower() + ".jsonl")
    cl, tm = [], []
    for ln in _tail_lines(p, 60_000) if p.exists() else []:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("px") and r.get("candle"):
            t = _unix(r["candle"]) + 1800
            if t >= t0:
                cl.append(float(r["px"])); tm.append(t)
    return cl, tm


def forecasts(now: float) -> list[dict]:
    """смены прогноза (tpl монеты отличается от её предыдущей записи) за последний прогон скринера, свежие первыми; в прогоне без смен —
    смены последнего прогона, где они были (чтобы запись не пустовала; мерка Claude). veto страница не читает — не фильтруем."""
    rows = []
    for ln in _tail_lines(BASE_DIR / "output" / "forecasts.jsonl", FC_TAIL):
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("sym") and r.get("tpl") and r.get("at"):
            rows.append(r)
    last_tpl: dict = {}; changes: dict = {}; per_run: dict = {}
    for r in rows:
        key = (r["at"], r.get("hm", "")); t = _unix(r["at"], r.get("hm", "00:00"))
        pv = last_tpl.get(r["sym"])
        if pv is not None and pv != r["tpl"]:
            c = dict(t=t, tpl=r["tpl"], px=float(r.get("px") or 0))
            changes.setdefault(r["sym"], []).append(c); per_run.setdefault(key, []).append((r["sym"], c))
        last_tpl[r["sym"]] = r["tpl"]
    runs = sorted(per_run)
    if not runs:
        return []
    picked = per_run[runs[-1]]
    out = []
    for sym, c in reversed(picked):
        cl, tm = _intraday_px(sym, now - FC_WIN_H * 3600)
        ch = []
        for q in changes.get(sym, []):
            if q["t"] < now - FC_WIN_H * 3600:
                continue
            i = min(range(len(tm)), key=lambda k: abs(tm[k] - q["t"])) if tm else None
            ch.append(dict(t=q["t"], tpl=q["tpl"], px=q["px"], i=i))
        out.append(dict(sym=sym, tpl=c["tpl"], t=c["t"], px=c["px"], closes=cl, times=tm, changes=ch))
    return out


def stars_now(now: float) -> list[dict]:
    """звёзды экрана «звёзды» (output/stars.json); t — когда монета впервые появилась среди звёзд (память output/fast_stars_mem.json)"""
    try:                                   # 10.10 владелец: «убери звезды вообще свои» — выключатель STARS_OFF в stars_new.py
        from stars_new import STARS_OFF as _off
    except ImportError:
        _off = False
    if _off:
        return []
    st = _read(BASE_DIR / "output" / "stars.json", {}) or {}
    mem = _read(STARS_MEM, {}) or {}
    cur = [s for s in (st.get("stars") or []) if s.get("sym")]
    syms = {s["sym"] for s in cur}
    mem = {k: v for k, v in mem.items() if k in syms}
    for s in cur:
        mem.setdefault(s["sym"], now)
    try:
        tmp = STARS_MEM.with_suffix(".tmp"); tmp.write_text(json.dumps(mem), encoding="utf-8"); tmp.replace(STARS_MEM)
    except OSError:
        pass
    return [dict(sym=s["sym"], reason=(s.get("sub") or s.get("why") or "").split(" ‖ ")[0].strip(), t=float(mem[s["sym"]]), keep=KEEP_S) for s in cur]


def _held_path(places: list) -> tuple:
    """правило кристаллов очереди (09.10 владелец, последняя формулировка: «показывать 3 подряд в 1-х; если смена места не больше 2 прогонов,
    то тоже первое; остальные, что были больше 2 раз в топе 1-2-3 с переменой мест, и выпали на 2 прогона — тоже кажем; если больше 2 прогонов
    дальше 4-го уходит — скрываем»; ранее: «1-1-1-2-3-1 — всегда 1-е, 3-3-3-7-8-3 — показываем, 3-3-3-8-8-10 — вылет»).
    «1»: Q_RUNS_FIRST (с 10.10 — 2) прогонов на 1-м месте подряд, уход с 1-го терпим Q_SLIP прогонов (счёт первых не сбрасывается), дольше — счёт первых с нуля.
    «★»: Q_RUNS прогонов в первых Q_TOP (места внутри тройки меняются свободно), выпадение из тройки терпим Q_SLIP прогонов, дольше — с экрана.
    → (метка 1 | "★" | None, индекс прогона, с которого метка такая, счёт прогонов за меткой)"""
    one_run = top_run = slip_one = slip_top = 0; mark = None; i_mark = None
    for i, p in enumerate(places):
        if p == 1:
            one_run += 1; slip_one = 0
        else:
            slip_one += 1
            if slip_one > Q_SLIP:
                one_run = 0
        if p is not None and p <= Q_TOP:
            top_run += 1; slip_top = 0
        else:
            slip_top += 1
            if slip_top > Q_SLIP:
                top_run = 0
        m = 1 if one_run >= Q_RUNS_FIRST else ("★" if top_run >= Q_RUNS else None)   # 10.10: первой — со 2-го прогона подряд, тройка — с 3-го
        if m != mark:
            mark, i_mark = m, i
    return mark, i_mark, (one_run if mark == 1 else top_run)


def queue_now(now: float) -> list[dict]:
    """кристаллы очереди на реке: «1» и «★» по _held_path (журнал output/queue_log.jsonl за скользящие сутки).
    ranks — места последних Q_PATH прогонов как есть и закреплённое место последним — страница рисует его внутри кристалла;
    res — ход цены от первого попадания в первые Q_TOP за сутки до последнего прогона, % (как «+N%» на экране точности); t — прогон последней смены закреплённого места; streak — сколько прогонов подряд на закреплённом месте."""
    by_run: dict = {}
    for ln in _tail_lines(BASE_DIR / "output" / "queue_log.jsonl", QL_TAIL):
        if '"place": null' in ln or '"sym"' not in ln:
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("sym") and r.get("place") is not None and r.get("at"):
            by_run.setdefault(r["at"], {})[r["sym"]] = r
    runs = sorted(by_run)
    if len(runs) < Q_RUNS:
        return []
    t_last = _unix(runs[-1]); runs = [a for a in runs if t_last - _unix(a) <= Q_WIN_H * 3600]   # скользящие сутки: 10.10 00:57 UTC владелец «нет ни одной
    if len(runs) < Q_RUNS:                                                                        # в первых» — по суткам UTC после полуночи прогонов 1–2, серий нет
        return []
    syms = {s for a in runs for s in by_run[a]}
    out = []
    for sym in syms:
        places = [int(by_run[a][sym]["place"]) if sym in by_run[a] else None for a in runs]
        mark, i_mark, streak = _held_path(places)
        if mark is None:
            continue
        raw = [p for p in places if p is not None]                      # 09.10 владелец: «последние 3 места»; «если 13 раз подряд 1-е, значит последние 3 — 1-1-1»:
        shown = 1 if mark == 1 else (places[-1] if places[-1] is not None else "—")   # 10.10 владелец: «вместо звезды текущее место» — в большом кристалле
        ranks = raw[-Q_PATH - 1:-1] + [shown]                             #   текущее место (вне очереди — «—»), у первой — 1; метка остаётся в поле mark
        i_top = next((k for k, p in enumerate(places) if p is not None and p <= Q_TOP), i_mark)
        cur = next((by_run[a][sym] for a in reversed(runs) if sym in by_run[a]), None)
        res = round(float(cur["px_chg_pct"]), 1) if (cur or {}).get("px_chg_pct") is not None else None   # как «+N%» на экране точности — ход с начала дня UTC
        if res is None:                                                   # на свече 00:00 UTC ход дня пуст — тогда от первого попадания в первые Q_TOP в окне
            p0 = float((by_run[runs[i_top]].get(sym) or {}).get("px") or 0); p1 = float((cur or {}).get("px") or 0)
            res = round((p1 / p0 - 1) * 100, 1) if p0 and p1 else 0.0
        out.append(dict(sym=sym, ranks=ranks, res=res, t=_unix(runs[i_mark]), keep=KEEP_S, place=(1 if mark == 1 else 2), now_place=places[-1],
                        streak=streak, since=_unix(runs[i_top]), mark=mark,
                        v2c=(cur or {}).get("vol_to_cap"), cap=(cur or {}).get("cap_now_usd")))   # 10.10 владелец: «надо соотношение объемов к капитализации показывать для лидеров в топе» — оборот фьючерсов Binance за 24 ч к капитализации по цене прогона (near_move)
    out.sort(key=lambda q: (q["place"], q["sym"]))                   # 1-е первым, дальше звёзды
    return out


def build() -> dict:
    now = time.time()
    op, cl, hist = positions(now)
    try:
        warn = bx_warn(now, op, cl)
    except Exception as e:  # noqa: BLE001
        print(f"предупреждения зеркала: {type(e).__name__}: {e}"); warn = []
    ent = candidates()
    # графики: открытые (кольцо «вход») и закрытые сегодня (кольцо «выход» и лента); кандидаты на странице не показываются
    syms = list(dict.fromkeys([p["sym"] for p in op] + [c["sym"] for c in cl]))[:40]
    try:                                                                 # 03.10 владелец: «сюда выводи информацию о доске» (правый верхний круг сайта) — output/board_now.json пишет fast_tier (R54)
        board = json.loads((BASE_DIR / "output" / "board_now.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        board = None
    fsq = {}
    for nm, fn in (("forecasts", forecasts), ("stars", stars_now), ("queue", queue_now)):   # 09.10: поля для дизайна «прогнозы · звёзды · очередь»; сбой одного не роняет состояние
        try:
            fsq[nm] = fn(now)
        except Exception as e:  # noqa: BLE001
            print(f"{nm}: сбой {type(e).__name__}: {e}"); fsq[nm] = []
    fsq["btc_clock"] = _read(BASE_DIR / "output" / "btc_clock.json", None)   # 10.10 владелец: «время в часах от сквиза биткоина и время во флэте +-10% хода от цены» (market_bg.btc_clock, раз в прогон)
    try:                                                                 # 10.10 владелец: «добавить общую капитализацию крипторынка и считать её изменение относительно 700 млрд» (market_bg.cap_total, строка на прогон)
        _cl = _tail_lines(BASE_DIR / "output" / "market_cap.jsonl", 20000)
        _cr = json.loads(_cl[-1]) if _cl else None
        fsq["cap"] = None if not _cr else {k: _cr.get(k) for k in ("at", "total_usd", "alt_usd", "tv_total_usd", "tv_total3_usd", "tv_btc_dom", "base_usd", "base_src", "over_base_usd", "over_base_pct",
                                                                     "over_base_chg_run_usd", "over_base_chg_d1_usd", "alt_chg_run_usd", "alt_chg_d1_usd", "zone", "zone_prev", "marks_usd")}
    except Exception as e:  # noqa: BLE001
        print(f"cap: сбой {type(e).__name__}: {e}"); fsq["cap"] = None
    try:                                                                 # 10.10 владелец: «после достижения 400 уже гореть красным какая-то метка на экране» — котёл больших ростов (pump_pot.py, пишет прогон)
        _pp = _read(BASE_DIR / "output" / "pump_pot.json", None)
        fsq["pot"] = None if not _pp else dict({k: _pp.get(k) for k in ("at", "pot_usd", "used_usd", "left_usd", "warn_usd", "warn", "full", "full_at", "reset_at", "cycle_from", "state", "n", "active")},
                                               moves=[dict(sym=m["sym"], added=m["added"], done=m["done"], cap_before=m["cap_before"], cap_peak=m["cap_peak"]) for m in (_pp.get("moves") or [])[:8]])
    except Exception as e:  # noqa: BLE001
        print(f"pot: сбой {type(e).__name__}: {e}"); fsq["pot"] = None
    return dict(**fsq, meta=meta(now), entry=ent, open=op, closed=cl, closed_hist=hist, charts=charts(syms), score=score(cl), board=board, board_day=board_day(now), board_3h=dict(blocks=dict(_B3H), neutral=list(NEUTRAL_3H), prog=dict(_P3H)), bx_warn=warn)


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
    try:
        bx_warn_tg(d, time.time())
    except Exception as e:  # noqa: BLE001
        print(f"предупреждения зеркала в Телеграм: {type(e).__name__}: {e}")
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
    # 05.10 владелец: «чтобы бот находил всплески, ты… делал выводы, разбирая эти монеты через два, четыре, шесть, восемь часов… можешь начинать» —
    # журнал всплесков (surge_journal.py): читает лог бота и уже записанные файлы, с Binance ничего не запрашивает, в торговлю не вмешивается
    try:
        import surge_journal
        print(surge_journal.update())
    except Exception as e:  # noqa: BLE001
        print(f"журнал всплесков: сбой {type(e).__name__}: {e}")
