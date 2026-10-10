#!/usr/bin/env python3
"""ПОЛУЧАСОВАЯ СВОДКА ДЛЯ РАЗБОРА (10.10 01:20 UTC, владелец: «проверяй первых в очереди и новые звёзды каждые полчаса, что пошло, что нет
и что можно улучшить, особенно в новых»). Ничего не решает — печатает числа: фон (BTC и доска), первые места очереди за сутки с ходом цены
от первого попадания, новые звёзды из stars_journal.json. Цены — публичные свечи BingX; места — output/queue_log.jsonl; метки — output/fast_state.json.
    .venv/bin/python claude/research/watch_review.py
"""
import json, time, calendar, urllib.request, datetime as dt
from pathlib import Path
R = Path(__file__).parent; BASE = R.parents[1]; U = dt.timezone.utc
WIN_H, QL_TAIL = 24, 14_000_000


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
        return json.loads(r.read())


def kl(sym, interval, start, limit=500):
    try:
        d = _get(f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={sym[:-4]}-USDT&interval={interval}&startTime={int(start * 1000)}&limit={limit}")
        return sorted((int(x["time"]) / 1000, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in (d.get("data") or []))
    except Exception:  # noqa: BLE001
        return []


def ts(s):
    return calendar.timegm(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))


def f_t(t):
    return dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")


def tail_lines(p, n):
    with p.open("rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size - n)); return f.read().decode("utf-8", "ignore").splitlines()[1:]


def main():
    now = time.time()
    # ── фон
    b = kl("BTCUSDT", "1h", now - 26 * 3600)
    if b:
        c = b[-1][4]
        def ago(h):
            x = [k for k in b if k[0] + 3600 <= now - h * 3600]
            return (c / x[-1][4] - 1) * 100 if x else float("nan")
        print(f"ФОН · BTC {c:,.0f}: за 1 ч {ago(1):+.2f} % · за 3 ч {ago(3):+.2f} % · за 24 ч {ago(24):+.2f} % · мин/макс 24 ч {min(k[3] for k in b[-24:]):,.0f}–{max(k[2] for k in b[-24:]):,.0f}")
    try:
        bd = json.loads((BASE / "output" / "board_now.json").read_text(encoding="utf-8"))
        print(f"ФОН · доска за 24 ч {bd.get('board24'):+.2f} % · в плюсе {bd.get('up'):.0f} % монет · режим «{bd.get('mode')}» · {f_t(bd.get('at', now))} UTC")
    except Exception:  # noqa: BLE001
        pass
    try:
        fs = json.loads((BASE / "output" / "fast_state.json").read_text(encoding="utf-8"))
        marks = {q["sym"]: q for q in fs.get("queue", [])}
        b3 = fs.get("board_3h") or {}
        print(f"ФОН · блоки доски по 3 ч (медиана, %): {b3.get('blocks', {}).get('board') or b3.get('blocks')}"[:300])
    except Exception:  # noqa: BLE001
        marks = {}
    # ── первые места очереди за сутки
    by_run = {}
    for ln in tail_lines(BASE / "output" / "queue_log.jsonl", QL_TAIL):
        if '"place": null' in ln or '"sym"' not in ln:
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("sym") and r.get("place") is not None and r.get("at") and now - ts(r["at"]) <= WIN_H * 3600:
            by_run.setdefault(r["at"], {})[r["sym"]] = r
    runs = sorted(by_run)
    print(f"\nПЕРВЫЕ ОЧЕРЕДИ за {WIN_H} ч · прогонов {len(runs)} ({f_t(ts(runs[0])) if runs else '—'} → {f_t(ts(runs[-1])) if runs else '—'} UTC)")
    firsts = {}
    for a in runs:
        for sym, r in by_run[a].items():
            if int(r["place"]) == 1 and sym not in firsts:
                firsts[sym] = (a, float(r.get("px") or 0))
    for sym, (a, px1) in sorted(firsts.items(), key=lambda kv: kv[1][0]):
        t1 = ts(a); k = kl(sym, "15m", t1 - 900)
        cur = next((by_run[x][sym] for x in reversed(runs) if sym in by_run[x]), None)
        places = [int(by_run[x][sym]["place"]) if sym in by_run[x] else None for x in runs if ts(x) >= t1]
        n1 = sum(1 for p in places if p == 1)
        if k and px1:
            w = [x for x in k if x[0] + 900 > t1]; c = w[-1][4] if w else k[-1][4]
            hi = max(x[2] for x in w) / px1 - 1 if w else 0; lo = min(x[3] for x in w) / px1 - 1 if w else 0
            res = f"сейчас {(c / px1 - 1) * 100:+.1f} % · макс {hi * 100:+.1f} % · мин {lo * 100:+.1f} %"
        else:
            res = "цены BingX нет"
        m = marks.get(sym); mk = f" · метка «{m.get('mark')}»" if m else ""
        last_pl = places[-1] if places else None
        print(f"- {sym[:-4]} · первой с {f_t(t1)} UTC ({(now - t1) / 3600:.1f} ч назад) · первой {n1} из {len(places)} прогонов · сейчас место {last_pl if last_pl else 'вне очереди'}{mk} · {res}")
        time.sleep(0.2)
    try:
        movers(now, by_run, runs, marks)
    except Exception as e:  # noqa: BLE001
        print("выросшие: сбой", type(e).__name__, e)
    try:
        quiet_accum()
    except Exception as e:  # noqa: BLE001
        print("тихий набор: сбой", type(e).__name__, e)
    # ── новые звёзды
    try:
        sj = json.loads((R / "stars_journal.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        sj = {}
    print(f"\nНОВЫЕ ЗВЁЗДЫ («шорты — топливо») в журнале: {len(sj)}")
    for sym, s in sorted(sj.items(), key=lambda kv: -kv[1]["t0"]):
        hs = " ".join(f"{h}ч {s['hours'][str(h)]:+.1f}" for h in range(1, 25) if str(h) in s["hours"])
        status = f"ушла {f_t(s['gone'])}" if s.get("gone") else "звезда"
        print(f"- {sym[:-4]} · с {f_t(s['t0'])} UTC ({(now - s['t0']) / 3600:.1f} ч) · {status} · сейчас {s['last_pct']:+.1f} % · макс {s['hi']:+.1f} % · мин {s['lo']:+.1f} %" + (f" · {hs}" if hs else ""))
    old = [s for s in sj.values() if now - s["t0"] >= 3600]
    if old:
        up = sum(1 for s in old if s["last_pct"] > 0); big = sum(1 for s in old if s["hi"] >= 5)
        x2 = sum(1 for s in sj.values() if "2" in (s.get("x") or {})); x3 = sum(1 for s in sj.values() if "3" in (s.get("x") or {}))
        print(f"итог по звёздам старше часа: {len(old)} · в плюсе сейчас {up} · доходили до +5 % {big} · медиана сейчас {sorted(s['last_pct'] for s in old)[len(old) // 2]:+.1f} % · дошли до ×2: {x2}, до ×3: {x3} (цель владельца: 2x норм, 3x идеально)")



def movers(now: float, by_run: dict, runs: list, marks: dict) -> None:
    """10.10 владелец: «следи просто, чтобы то, что выросло, попадало к нам как можно раньше» — монеты с ходом ≥ MOVE_PCT за сутки
    (получасовки cq_v2/intraday, 200+ монет): когда начался ход (первая получасовка, закрывшаяся выше максимума 24 ч до неё на 3 % —
    мерка Claude), когда монета впервые попала в первую тройку очереди и в звёзды (stars_journal), опоздание в часах."""
    MOVE_PCT, WIN = 20.0, 24 * 3600
    try:
        sj = json.loads((R / "stars_journal.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        sj = {}
    out = []
    for p in (BASE / "cq_v2" / "intraday").glob("*.jsonl"):
        sym = p.stem.upper() + "USDT"
        if sym in ("BTCUSDT", "ETHUSDT"):
            continue
        rows = []
        for ln in tail_lines(p, 40_000):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("px") and r.get("h") and r.get("candle"):
                rows.append((ts(r["candle"]) + 1800, float(r["o"] or r["px"]), float(r["h"]), float(r["px"])))
        rows.sort()
        day = [x for x in rows if x[0] > now - WIN]
        if len(day) < 10:
            continue
        lo = min(x[3] for x in day); hi = max(x[2] for x in day); last = day[-1][3]
        base = day[0][1]
        if hi / base - 1 < MOVE_PCT / 100:
            continue
        start = None
        for i, x in enumerate(rows):
            if x[0] <= now - WIN:
                continue
            prev = [y for y in rows if x[0] - 48 * 1800 <= y[0] < x[0]]
            if prev and x[3] >= max(y[2] for y in prev) * 1.03:
                start = x[0]; break
        top = next((ts(a) for a in runs if sym in by_run[a] and int(by_run[a][sym]["place"]) <= 3), None)
        st = sj.get(sym); t_star = st["t0"] if st else None
        out.append((sym, base, hi, last, start, top, t_star))
    out.sort(key=lambda o: -(o[2] / o[1]))
    print(f"\nВЫРОСЛИ ЗА СУТКИ (макс ≥ +{MOVE_PCT:.0f} % от цены сутки назад): {len(out)}")
    lag = []
    for sym, base, hi, last, start, top, t_star in out:
        s = f"старт {f_t(start)} UTC" if start else "старта по мерке нет"
        q = f"в тройке с {f_t(top)}" if top else "в тройке не была"
        z = f"звезда с {f_t(t_star)}" if t_star else "звездой не была"
        d = []
        if start and top: d.append(f"очередь +{(top - start) / 3600:.1f} ч"); lag.append((top - start) / 3600)
        if start and t_star: d.append(f"звезда {(t_star - start) / 3600:+.1f} ч")
        print(f"- {sym[:-4]} · макс +{(hi / base - 1) * 100:.0f} % · сейчас {(last / base - 1) * 100:+.0f} % · {s} · {q} · {z}" + (" · опоздание: " + ", ".join(d) if d else ""))
    seen = sum(1 for o in out if o[5] or o[6])
    print(f"итог: выросших {len(out)} · попали к нам (тройка или звезда) {seen} · не попали {len(out) - seen}" + (f" · медиана опоздания очереди {sorted(lag)[len(lag) // 2]:.1f} ч" if lag else ""))



def quiet_accum() -> None:
    """10.10 владелец: «объёмы идут на спросе, накопление идёт до спроса, но с той же целью» — тихий набор по дневкам кванта (все биржи):
    интерес в монетах за 14 дн ≥ +15 %, цена за 14 дн не выше +5 %, оборот 14 дн не выше ×1,5 нормы (пороги Claude). Печать для журнала."""
    import glob, statistics as st
    out = []
    for f in glob.glob(str(BASE / "cq_v2" / "*.json")):
        if Path(f).name.startswith("_"):
            continue
        try:
            d = json.loads(Path(f).read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        oh = sorted((r for r in d.get("ohlcv", []) if r.get("close") and r.get("quote_volume")), key=lambda r: r["datetime"])
        oi = sorted((r for r in d.get("oi", []) if r.get("open_interest")), key=lambda r: r["datetime"])
        if len(oh) < 60 or len(oi) < 45:
            continue
        px = {r["datetime"][:10]: r for r in oh}
        coins = [(r["datetime"][:10], r["open_interest"] / px[r["datetime"][:10]]["close"]) for r in oi if r["datetime"][:10] in px]
        if len(coins) < 45:
            continue
        c_now, c_14 = coins[-1][1], coins[-15][1]; p_now, p_14 = oh[-1]["close"], oh[-15]["close"]
        vol14 = st.median(r["quote_volume"] for r in oh[-14:]); vol_norm = st.median(r["quote_volume"] for r in oh[-60:-14])
        fu = [r.get("funding_rate") for r in sorted(d.get("funding", []), key=lambda r: r["datetime"])[-3:] if r.get("funding_rate") is not None]
        lo120 = min(r["low"] for r in oh[-120:]); hi120 = max(r["high"] for r in oh[-120:])
        if (c_now / c_14 - 1) * 100 >= 15 and (p_now / p_14 - 1) * 100 <= 5 and vol14 / vol_norm <= 1.5:
            out.append((Path(f).stem.upper(), (c_now / c_14 - 1) * 100, (p_now / p_14 - 1) * 100, vol14 / vol_norm, st.mean(fu) if fu else None, (p_now / lo120 - 1) * 100, (p_now / hi120 - 1) * 100, oh[-1]["datetime"][:10]))
    out.sort(key=lambda o: -o[1])
    print(f"\nТИХИЙ НАБОР (дневки кванта до {out[0][7] if out else '—'}; интерес 14 дн ≥ +15 %, цена ≤ +5 %, оборот ≤ ×1,5): {len(out)}")
    for o in out[:20]:
        print(f"- {o[0]} · интерес +{o[1]:.0f} % · цена {o[2]:+.1f} % · оборот ×{o[3]:.1f} · фандинг 3 дн {o[4] if o[4] is None else round(o[4], 3)} · от мин 120 дн {o[5]:+.0f} % · от макс {o[6]:+.0f} %")


if __name__ == "__main__":
    main()
