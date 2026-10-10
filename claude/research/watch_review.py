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
        print(f"итог по звёздам старше часа: {len(old)} · в плюсе сейчас {up} · доходили до +5 % {big} · медиана сейчас {sorted(s['last_pct'] for s in old)[len(old) // 2]:+.1f} %")


if __name__ == "__main__":
    main()
