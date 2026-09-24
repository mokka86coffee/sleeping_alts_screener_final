#!/usr/bin/env python3
"""ПОИСК ПРАВИЛ ПО ИСТОРИИ BINANCE (24.09, владелец: «зачем запускать трёхминутки, если можно всё прогнать по
истории и найти рабочую стратегию»; «гоняй, подразумевая фон — медиана доски, биткоин, рынки-сессии, выходные-будни;
просто гонять — всегда будет рандом»).

Два шага:
  --fetch   скачивает с Binance пятиминутки (цена, оборот, покупки по рынку) и историю фандинга за HIST_DAYS суток
            по монетам архива cq_v2/intraday (это выборка бота) и BTC. Кладёт в cq_v2/hist/, архив прогона не трогает.
            Повторный запуск дозабирает только новое.
  без флага ищет правила: на каждой закрытой получасовке (ритм бота) у каждой монеты считает фон и признаки монеты,
            проигрывает лонг и шорт по пятиминуткам с сеткой выходов и ищет сочетания до трёх условий, которые в
            плюсе и на ОБУЧЕНИИ (первые TRAIN_DAYS суток), и на ПРОВЕРКЕ (остальное). Выбор — только по обучению.

Фон на момент решения: медиана доски за час и за сутки, доля растущих за сутки, биткоин за час и за сутки, сессия
(Сидней 21, Токио 0, Лондон 7, Нью-Йорк 13 UTC), первый час после открытия сессии, выходные.
Монета: ход за полчаса, три часа, сутки; ход к доске; оборот к своей суточной норме; покупки к продажам по рынку;
место в суточном размахе; фандинг.
Границы «низко / высоко» у числовых признаков — трети распределения на ОБУЧЕНИИ, не мои числа.

Счёт честный: вход по открытию пятиминутки сразу после закрытия получасовки; цель и стоп по максимуму и минимуму
пятиминуток, бар, где задеты оба, — стоп; комиссия FEE и проскальзывание SLIP за круг; фандинг за время позиции
по истории (лонг при плюсовом фандинге платит). Одна позиция на монету — только в итоговом разборе лучших правил.

    python3 lab_history.py --fetch --only ONE     # проверить скачивание на одной монете
    python3 lab_history.py --fetch                # вся выборка (≈15 минут, общий лимитер)
    .venv/bin/python lab_history.py               # поиск (нужен numpy — он есть в .venv)
Пишет output/lab_history.txt (сводка) и output/lab_history.json (прошедшие правила).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

HIST_DIR = BASE_DIR / "cq_v2" / "hist"
LIVE_DIR = BASE_DIR / "cq_v2" / "intraday"
OUT = BASE_DIR / "output"

HIST_DAYS = 90                 # глубина истории; интерес Binance дальше 30 суток не отдаёт — поэтому его здесь нет
TRAIN_DAYS = 60                # обучение — первые 60 суток, проверка — последние 30
BAR = 300_000                  # пятиминутка, мс
DEC = 1_800_000                # решение — на закрытии получасовки, как у бота
FEE = 0.001                    # комиссия за круг, как SIGHT_FEE / PAPER_CROWD_FEE
SLIP = 0.001                   # МОЁ число: проскальзывание за круг на мелочи; проверить по стакану (depth_fetch)
TARGETS = (0.01, 0.02, 0.03, 0.05)
STOPS = (0.02, 0.05, None)
HOLDS = (12, 72, 288)          # 1 ч, 6 ч, 24 ч в пятиминутках
N_MIN_TRAIN = 300              # МОИ числа: меньше сделок — правило не рассматривается (шум);
N_MIN_TEST = 100               # 300 за 60 суток — пять в день, 100 за 30 суток — три в день
SESSIONS = (("Сидней", 21), ("Токио", 0), ("Лондон", 7), ("Нью-Йорк", 13))
THREADS = 6                    # как binance_fetch: шесть потоков через общий лимитер core_http


# ─────────────────────────── скачивание ───────────────────────────

def universe(only: str | None) -> list[str]:
    bases = sorted(p.stem for p in LIVE_DIR.glob("*.jsonl"))
    if "btc" not in bases:
        bases.append("btc")
    if only:
        bases = [b for b in bases if b == only.lower()] or [only.lower()]
    return [b.upper() + "USDT" for b in bases]


def _save_gz(path: Path, rows: list) -> None:
    """атомарно, как write_atomic, но в gzip: пишем рядом и переименовываем"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    os.replace(tmp, path)


def _load_gz(path: Path) -> list:
    if not path.exists():
        return []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def fetch_one(sym: str) -> str:
    from core_config import BINANCE_FAPI
    from core_http import get_json
    base = sym.replace("USDT", "").lower()
    now = int(time.time() * 1000)
    start_all = now - HIST_DAYS * 86_400_000
    # свечи: [время открытия, o, h, l, c, оборот $, покупки по рынку $]
    kp = HIST_DIR / f"{base}_5m.jsonl.gz"
    rows = [r for r in _load_gz(kp) if r[0] >= start_all]
    start = (rows[-1][0] + BAR) if rows else start_all
    added = 0
    while start < now - BAR:
        page = get_json(f"{BINANCE_FAPI}/fapi/v1/klines",
                        {"symbol": sym, "interval": "5m", "startTime": start, "limit": 1000}, weight=5)
        if not page:
            break
        for k in page:
            t = int(k[0])
            if t + BAR > now:                       # незакрытая
                continue
            rows.append([t, float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7]), float(k[10])])
            added += 1
        nxt = int(page[-1][0]) + BAR
        if nxt <= start or len(page) < 1000:
            break
        start = nxt
    rows.sort(key=lambda r: r[0])
    dedup = []
    for r in rows:
        if not dedup or r[0] != dedup[-1][0]:
            dedup.append(r)
    if dedup:
        _save_gz(kp, dedup)
    # фандинг: [время, ставка долей]
    fp = HIST_DIR / f"{base}_funding.json"
    fund = json.loads(fp.read_text()) if fp.exists() else []
    fund = [f for f in fund if f[0] >= start_all]
    fstart = (fund[-1][0] + 1) if fund else start_all
    while True:
        page = get_json(f"{BINANCE_FAPI}/fapi/v1/fundingRate",
                        {"symbol": sym, "startTime": fstart, "limit": 1000}, weight=1)
        if not page:
            break
        for f in page:
            fund.append([int(f["fundingTime"]), float(f["fundingRate"])])
        if len(page) < 1000:
            break
        fstart = int(page[-1]["fundingTime"]) + 1
    fund = sorted({f[0]: f for f in fund}.values())
    tmp = fp.with_suffix(".tmp")
    tmp.write_text(json.dumps(fund))
    os.replace(tmp, fp)
    first = datetime.fromtimestamp(dedup[0][0] / 1000, timezone.utc).strftime("%d.%m") if dedup else "—"
    return f"{sym}: свечей {len(dedup)} (+{added}) с {first} · фандинг {len(fund)}"


def do_fetch(only: str | None) -> int:
    HIST_DIR.mkdir(parents=True, exist_ok=True)
    syms = universe(only)
    t0 = time.time()
    with ThreadPoolExecutor(THREADS) as ex:
        futs = {ex.submit(fetch_one, s): s for s in syms}
        for i, f in enumerate(as_completed(futs), 1):
            try:
                print(f"  [{i}/{len(syms)}] {f.result()}", flush=True)
            except Exception as e:                 # сбой одной монеты не останавливает остальные
                print(f"  [{i}/{len(syms)}] {futs[f]}: сбой {type(e).__name__}: {e}", flush=True)
    print(f"готово за {time.time() - t0:.0f} с · {HIST_DIR}")
    return 0


# ─────────────────────────── поиск ───────────────────────────

def load(np):
    coins = {}
    for p in sorted(HIST_DIR.glob("*_5m.jsonl.gz")):
        base = p.name[:-len("_5m.jsonl.gz")]
        rows = _load_gz(p)
        if len(rows) < 2 * 288:
            continue
        a = np.array(rows, dtype=np.float64)
        fp = HIST_DIR / f"{base}_funding.json"
        fund = np.array(json.loads(fp.read_text()) if fp.exists() else [], dtype=np.float64).reshape(-1, 2)
        coins[base.upper()] = dict(t=a[:, 0].astype(np.int64), o=a[:, 1], h=a[:, 2], l=a[:, 3], c=a[:, 4],
                                   qv=a[:, 5], tb=a[:, 6], fund=fund)
    return coins


def to_30m(np, d):
    """получасовки из пятиминуток: только полные (шесть баров); время — ЗАКРЫТИЕ получасовки"""
    g = d["t"] // DEC
    start = np.r_[0, np.flatnonzero(np.diff(g)) + 1]
    cnt = np.diff(np.r_[start, len(g)])
    ok = cnt == 6
    s = start[ok]
    e = s + 5
    T = (g[s] + 1) * DEC
    return dict(T=T, c=d["c"][e], h=np.maximum.reduceat(d["h"], start)[ok], l=np.minimum.reduceat(d["l"], start)[ok],
                qv=np.add.reduceat(d["qv"], start)[ok], tb=np.add.reduceat(d["tb"], start)[ok])


def lag(np, T, x, k):
    """x[i-k], только если между барами ровно k получасовок, иначе nan"""
    out = np.full(len(x), np.nan)
    if len(x) > k:
        ok = (T[k:] - T[:-k]) == k * DEC
        out[k:][ok] = x[:-k][ok]
    return out


def features(np, coins):
    """кандидаты: по одной строке на монету и закрытую получасовку"""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    per = {}
    for sym, d in coins.items():
        m = to_30m(np, d)
        T, c = m["T"], m["c"]
        r30 = c / lag(np, T, c, 1) - 1
        r1h = c / lag(np, T, c, 2) - 1
        r3h = c / lag(np, T, c, 6) - 1
        r24 = c / lag(np, T, c, 48) - 1
        vol = np.full(len(c), np.nan)
        hi24 = np.full(len(c), np.nan)
        lo24 = np.full(len(c), np.nan)
        if len(c) > 49:
            med = np.median(swv(m["qv"], 48)[:-1], axis=1)       # норма — 48 получасовок ДО текущей
            vol[48:] = m["qv"][48:] / np.where(med > 0, med, np.nan)
            hi24[47:] = swv(m["h"], 48).max(axis=1)
            lo24[47:] = swv(m["l"], 48).min(axis=1)
        sell = m["qv"] - m["tb"]
        tk = np.where(sell > 0, m["tb"] / np.where(sell > 0, sell, 1), np.nan)
        pos = (c - lo24) / np.where(hi24 > lo24, hi24 - lo24, np.nan)
        f = d["fund"]
        if len(f):
            fi = np.searchsorted(f[:, 0], T, side="right") - 1
            fund = np.where(fi >= 0, f[np.clip(fi, 0, None), 1], np.nan)
        else:
            fund = np.full(len(c), np.nan)
        per[sym] = dict(T=T, r30=r30, r1h=r1h, r3h=r3h, r24=r24, vol=vol, tk=tk, pos=pos, fund=fund)
    # фон: медиана доски на каждой получасовке
    grid = np.unique(np.concatenate([v["T"] for v in per.values()]))
    alts = [s for s in per if s != "BTC"]
    M1 = np.full((len(alts), len(grid)), np.nan)
    M24 = np.full((len(alts), len(grid)), np.nan)
    for i, s in enumerate(alts):
        idx = np.searchsorted(grid, per[s]["T"])
        M1[i, idx] = per[s]["r1h"]
        M24[i, idx] = per[s]["r24"]
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore", RuntimeWarning)
        n24 = np.sum(~np.isnan(M24), axis=0)
        bg = dict(b1=np.nanmedian(M1, axis=0), b24=np.nanmedian(M24, axis=0),
                  share=np.where(n24 > 0, np.nansum(M24 > 0, axis=0) / np.maximum(n24, 1), np.nan), n=n24)
    btc = per.get("BTC")
    if btc:
        bi = np.searchsorted(btc["T"], grid)
        bi_ok = (bi < len(btc["T"])) & (btc["T"][np.clip(bi, 0, len(btc["T"]) - 1)] == grid)
        bg["btc1"] = np.where(bi_ok, btc["r1h"][np.clip(bi, 0, len(btc["T"]) - 1)], np.nan)
        bg["btc24"] = np.where(bi_ok, btc["r24"][np.clip(bi, 0, len(btc["T"]) - 1)], np.nan)
    else:
        bg["btc1"] = bg["btc24"] = np.full(len(grid), np.nan)
    return per, grid, bg


def outcomes(np, d, T, side):
    """результаты сделки для каждого момента T и каждого выхода: [len(T), len(TARGETS)*len(STOPS)*len(HOLDS)]"""
    t5 = d["t"]
    J = np.searchsorted(t5, T)
    maxh = max(HOLDS)
    ok = (J + maxh < len(t5))
    ok[ok] &= t5[J[ok]] == T[ok]
    ok[ok] &= (t5[J[ok] + maxh - 1] - t5[J[ok]]) == (maxh - 1) * BAR        # без дыр на сутки вперёд
    Jv = J[ok]
    e = d["o"][Jv]
    INF = 10 ** 9
    ft = {tg: np.full(len(Jv), INF) for tg in TARGETS}
    fs = {sl: np.full(len(Jv), INF) for sl in STOPS if sl}
    for k in range(maxh):
        hk, lk = d["h"][Jv + k], d["l"][Jv + k]
        fav = side * ((hk if side > 0 else lk) / e - 1)
        adv = side * ((lk if side > 0 else hk) / e - 1)
        for tg in TARGETS:
            hit = (fav >= tg) & (ft[tg] == INF)
            ft[tg][hit] = k
        for sl in fs:
            hit = (adv <= -sl) & (fs[sl] == INF)
            fs[sl][hit] = k
    # фандинг нарастающим итогом по пятиминуткам: ставка списывается в момент расчёта
    f = d["fund"]
    if len(f):
        fcum_t = np.cumsum(f[:, 1])
        fi = np.searchsorted(f[:, 0], t5, side="right") - 1
        fcum = np.where(fi >= 0, fcum_t[np.clip(fi, 0, None)], 0.0)
    else:
        fcum = np.zeros(len(t5))
    cols = []
    for tg in TARGETS:
        for sl in STOPS:
            for hold in HOLDS:
                t_hit = ft[tg] < hold
                if sl:
                    s_hit = fs[sl] < hold
                    stop_first = s_hit & (~t_hit | (fs[sl] <= ft[tg]))
                else:
                    stop_first = np.zeros(len(Jv), bool)
                close = side * (d["c"][Jv + hold - 1] / e - 1)
                res = np.where(stop_first, -(sl or 0), np.where(t_hit, tg, close))
                k_exit = np.where(stop_first, fs[sl] if sl else hold - 1, np.where(t_hit, ft[tg], hold - 1))
                res = res - side * (fcum[Jv + k_exit] - fcum[Jv]) - FEE - SLIP
                cols.append(res)
    out = np.full((len(T), len(cols)), np.nan, dtype=np.float32)
    out[ok] = np.stack(cols, axis=1).astype(np.float32)
    return out, ok


EXIT_NAMES = [f"цель {tg * 100:.0f}% стоп {'нет' if not sl else f'{sl * 100:.0f}%'} срок {h * 5 // 60} ч"
              for tg in TARGETS for sl in STOPS for h in HOLDS]


def search(np) -> int:
    t0 = time.time()
    coins = load(np)
    if not coins:
        print("нет истории — сначала python3 lab_history.py --fetch")
        return 1
    per, grid, bg = features(np, coins)
    gpos = {int(t): i for i, t in enumerate(grid)}
    rows_T, rows_sym, feats, RES = [], [], [], {1: [], -1: []}
    for sym, f in per.items():
        if sym == "BTC":
            continue
        gi = np.array([gpos[int(t)] for t in f["T"]])
        X = np.column_stack([f["r30"], f["r3h"], f["r24"], f["r24"] - bg["b24"][gi], f["vol"], f["tk"], f["pos"],
                             f["fund"], bg["b1"][gi], bg["b24"][gi], bg["share"][gi], bg["btc1"][gi],
                             bg["btc24"][gi]])
        good = ~np.isnan(X[:, :7]).any(axis=1) & ~np.isnan(X[:, 8:11]).any(axis=1) & (bg["n"][gi] >= 30)
        rl, okl = outcomes(np, coins[sym], f["T"], 1)
        rs, oks = outcomes(np, coins[sym], f["T"], -1)
        keep = good & okl & oks
        rows_T.append(f["T"][keep])
        rows_sym += [sym] * int(keep.sum())
        feats.append(X[keep])
        RES[1].append(rl[keep])
        RES[-1].append(rs[keep])
    T = np.concatenate(rows_T)
    X = np.concatenate(feats)
    R = {s: np.concatenate(v) for s, v in RES.items()}
    syms = np.array(rows_sym)
    t_split = int(T.min()) + TRAIN_DAYS * 86_400_000
    tr, te = T < t_split, T >= t_split
    days_tr = (t_split - T.min()) / 86_400_000
    days_te = (T.max() - t_split) / 86_400_000
    print(f"кандидатов {len(T)} · монет {len(set(rows_sym))} · обучение {days_tr:.0f} сут · проверка {days_te:.0f} сут"
          f" · {time.time() - t0:.0f} с")

    # ── условия ──
    names = ["за полчаса", "за 3 ч", "за сутки", "к доске за сутки", "оборот к норме", "покупки к продажам",
             "место в суточном размахе"]
    preds = {}
    for j, nm in enumerate(names):
        lo, hi = np.nanquantile(X[tr, j], [1 / 3, 2 / 3])
        preds[f"{nm}: низко (<{lo:.3g})"] = (X[:, j] < lo, j)
        preds[f"{nm}: высоко (≥{hi:.3g})"] = (X[:, j] >= hi, j)
    fund = X[:, 7]
    fhi = np.nanquantile(fund[tr & ~np.isnan(fund)], 2 / 3)
    preds["фандинг < 0 (платят шорты)"] = (fund < 0, 7)
    preds[f"фандинг высокий (≥{fhi:.2g}, платят лонги)"] = (fund >= fhi, 7)
    preds["доска за час растёт"] = (X[:, 8] > 0, 8)
    preds["доска за час падает"] = (X[:, 8] < 0, 8)
    preds["доска за сутки растёт"] = (X[:, 9] > 0, 9)
    preds["доска за сутки падает"] = (X[:, 9] < 0, 9)
    slo, shi = np.nanquantile(X[tr, 10], [1 / 3, 2 / 3])
    preds[f"растущих на доске мало (<{slo:.0%})"] = (X[:, 10] < slo, 10)
    preds[f"растущих на доске много (≥{shi:.0%})"] = (X[:, 10] >= shi, 10)
    preds["биткоин за час вверх"] = (X[:, 11] > 0, 11)
    preds["биткоин за час вниз"] = (X[:, 11] < 0, 11)
    preds["биткоин за сутки вверх"] = (X[:, 12] > 0, 12)
    preds["биткоин за сутки вниз"] = (X[:, 12] < 0, 12)
    hour = (T // 3_600_000) % 24
    minute = (T // 60_000) % 1440
    for i, (nm, h0) in enumerate(SESSIONS):
        h1 = SESSIONS[(i + 1) % 4][1]
        inn = ((hour >= h0) & (hour < h1)) if h0 < h1 else ((hour >= h0) | (hour < h1))
        preds[f"сессия {nm}"] = (inn, 20)
    opens = np.array([h * 60 for _, h in SESSIONS])
    since = np.min((minute[:, None] - opens[None, :]) % 1440, axis=1)
    preds["первый час после открытия сессии"] = (since < 60, 21)
    wd = ((T // 86_400_000) + 3) % 7                              # 1970-01-01 — четверг; 5,6 — суббота, воскресенье
    preds["выходные"] = (wd >= 5, 22)
    preds["будни"] = (wd < 5, 22)
    pn = list(preds)
    P = np.stack([preds[k][0] for k in pn]).astype(np.float32)   # [условий, кандидатов]
    grp = [preds[k][1] for k in pn]
    rules = [(i,) for i in range(len(pn))]
    rules += [c for c in combinations(range(len(pn)), 2) if grp[c[0]] != grp[c[1]]]
    rules += [c for c in combinations(range(len(pn)), 3) if len({grp[i] for i in c}) == 3]
    print(f"условий {len(pn)} · правил {len(rules)} · выходов {len(EXIT_NAMES)} · сторон 2")

    # ── перебор: суммы и счётчики через матричное умножение ──
    out = []
    for side in (1, -1):
        Rs = np.nan_to_num(R[side])
        Rtr, Rte = Rs[tr], Rs[te]
        Wtr, Wte = (Rtr > 0).astype(np.float32), (Rte > 0).astype(np.float32)
        Ptr, Pte = P[:, tr], P[:, te]
        CH = 64                                                 # ~100 МБ на блок при 400 тыс. кандидатов
        for a in range(0, len(rules), CH):
            chunk = rules[a:a + CH]
            Mtr = np.stack([np.prod(Ptr[list(r)], axis=0) for r in chunk])
            Mte = np.stack([np.prod(Pte[list(r)], axis=0) for r in chunk])
            ntr, nte = Mtr.sum(axis=1), Mte.sum(axis=1)
            Str, Ste = Mtr @ Rtr, Mte @ Rte
            Htr, Hte = Mtr @ Wtr, Mte @ Wte
            for i, r in enumerate(chunk):
                if ntr[i] < N_MIN_TRAIN or nte[i] < N_MIN_TEST:
                    continue
                mtr = Str[i] / ntr[i]
                mte = Ste[i] / nte[i]
                for k in range(len(EXIT_NAMES)):
                    out.append((side, r, k, int(ntr[i]), float(mtr[k]), float(Htr[i, k] / ntr[i]),
                                int(nte[i]), float(mte[k]), float(Hte[i, k] / nte[i])))
    print(f"проверено сочетаний правило×выход×сторона: {len(out)} · {time.time() - t0:.0f} с")

    # ── честная мерка: выбор ТОЛЬКО по обучению, проверка лишь показывается ──
    out.sort(key=lambda x: -x[4])
    lines = []
    # что даёт вход без всяких условий — точка отсчёта
    for side in (1, -1):
        Rs = R[side]
        for k in (EXIT_NAMES.index("цель 3% стоп 5% срок 6 ч"), EXIT_NAMES.index("цель 5% стоп нет срок 24 ч")):
            a_tr, a_te = np.nanmean(Rs[tr, k]), np.nanmean(Rs[te, k])
            lines.append(f"БЕЗ УСЛОВИЙ {'ЛОНГ' if side > 0 else 'ШОРТ'} · {EXIT_NAMES[k]}: обучение {a_tr * 100:+.2f}%"
                         f" · проверка {a_te * 100:+.2f}% на сделку")
    top = out[:500]
    pos_te = sum(1 for x in top if x[7] > 0)
    lines.append(f"\nИз 500 лучших по ОБУЧЕНИЮ в плюсе на ПРОВЕРКЕ: {pos_te} ({pos_te / 5:.0f}%)."
                 f" Для сравнения, из всех {len(out)}: {sum(1 for x in out if x[7] > 0) / max(len(out), 1):.0%}.")
    both = [x for x in out if x[4] > 0 and x[7] > 0]          # порядок — по обучению, проверка только фильтрует

    def fmt(x):
        side, r, k, ntr, mtr, htr, nte, mte, hte = x
        cond = " + ".join(pn[i] for i in r)
        return (f"{'ЛОНГ' if side > 0 else 'ШОРТ'} · {cond} · {EXIT_NAMES[k]}\n"
                f"      обучение: {ntr} ({ntr / days_tr:.1f}/сут) · в плюсе {htr:.0%} · сделка {mtr * 100:+.2f}%"
                f"   | проверка: {nte} ({nte / days_te:.1f}/сут) · в плюсе {hte:.0%} · сделка {mte * 100:+.2f}%")

    lines.append(f"\nВ плюсе на обоих отрезках: {len(both)} сочетаний. Первые по обучению (одно правило — один выход;"
                 f" «в сутки» — сигналы, одна монета может дать их подряд):")
    seen = set()
    shown = 0
    for x in both:
        key = (x[0], x[1])                     # одно правило — один лучший выход, без повторов
        if key in seen:
            continue
        seen.add(key)
        lines.append(fmt(x))
        shown += 1
        if shown >= 30:
            break
    lines.append("\nЛучшие по обучению (для сравнения — что с ними стало на проверке):")
    for x in out[:10]:
        lines.append(fmt(x))
    txt = "\n".join(lines)
    print(txt)
    OUT.mkdir(exist_ok=True)
    (OUT / "lab_history.txt").write_text(txt, encoding="utf-8")
    js = [dict(side=x[0], rule=[pn[i] for i in x[1]], exit=EXIT_NAMES[x[2]], n_train=x[3], mean_train=x[4],
               win_train=x[5], n_test=x[6], mean_test=x[7], win_test=x[8]) for x in both[:300]]
    (OUT / "lab_history.json").write_text(json.dumps(js, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nзаписано: {OUT / 'lab_history.txt'} · {OUT / 'lab_history.json'} · {time.time() - t0:.0f} с")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--only")
    a = ap.parse_args()
    if a.fetch:
        return do_fetch(a.only)
    try:
        import numpy as np
    except ImportError:
        print("для поиска нужен numpy: .venv/bin/python lab_history.py")
        return 1
    return search(np)


if __name__ == "__main__":
    raise SystemExit(main())
