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


def positions(now: float) -> tuple[list, list, list]:
    day0 = datetime.fromtimestamp(now, L).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    RV = reviews()
    op, cl, hist = [], [], []
    for book, stem in BOOKS:
        stt = _read(BASE_DIR / "output" / f"{stem}.json", {})
        R = _rows(BASE_DIR / "output" / f"{stem}.jsonl")
        ent = {(r.get("sym"), round(float(r.get("at") or 0), 3)): r for r in R if r.get("kind") == "entry"}
        for sym, p in (stt.get("open") or {}).items():
            e, sd = float(p["px"]), int(p["side"])
            er = ent.get((sym, round(float(p["at"]), 3))) or {}
            op.append(dict(book=book, sym=sym, side=sd, entry=e, target=(None if float(p["target"]) >= 0.9 else e * (1 + sd * float(p["target"]))), stop=e * (1 - sd * float(p["stop"])),
                           tp=float(p["target"]), sl=float(p["stop"]), t_in=float(p["at"]),
                           exit_at=(int(p["t_ms"]) + B3) / 1000 + int(p.get("hold_min") or 0) * 60, px=p.get("last_px"), rule=p.get("rule") or "",
                           oi1h_in=er.get("oi1h"), board6_in=(er.get("fon") or {}).get("board6")))
        for r in R:
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("at") or 0) < day0 - HIST_DAYS * 86400:
                continue
            key = f"{book}|{r['sym']}|{int(float(r['at']))}"
            (cl if float(r["at"]) >= day0 else hist).append(dict(book=book, sym=r["sym"], side=int(r.get("side") or 1), entry=float(r["px_in"]), exit=float(r.get("px_out") or 0),
                           t_in=float(r.get("opened_at") or 0), t_out=float(r["at"]), why=r.get("why_exit") or "", res=float(r["result_pct"]),
                           usd=round(float(r["usd"]) if r.get("usd") is not None else float(r["result_pct"]) * 5, 2),   # 29.09: сумма сделки берётся из записи (было 500 $ → 1000 $)
                            rule=r.get("rule") or "", review=RV.get(key)))
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


def score(cl: list[dict]) -> dict:
    out = {}
    for book, _ in BOOKS:
        g = [x for x in cl if x["book"] == book]
        out[book] = dict(n=len(g), win=sum(1 for x in g if x["res"] > 0), usd=round(sum(x["usd"] for x in g), 1))
    return out


def build() -> dict:
    now = time.time()
    op, cl, hist = positions(now)
    ent = candidates()
    # графики: открытые (кольцо «вход») и закрытые сегодня (кольцо «выход» и лента); кандидаты на странице не показываются
    syms = list(dict.fromkeys([p["sym"] for p in op] + [c["sym"] for c in cl]))[:40]
    return dict(meta=meta(now), entry=ent, open=op, closed=cl, closed_hist=hist, charts=charts(syms), score=score(cl))


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
