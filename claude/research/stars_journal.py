#!/usr/bin/env python3
"""ЖУРНАЛ НОВЫХ ЗВЁЗД (10.10 01:20 UTC, владелец: «новые звёзды пусть тоже отдельно пишутся в журнал с итогом в каждый час»).
Звёзды — output/stars.json («шорты — топливо», считает stars_new.py по пульсу). Для каждой звезды: когда появилась (output/fast_stars_mem.json —
первое появление, его пишет fast_state), цена в этот момент, и итог на каждый полный час после появления — ход цены к часу, максимум и минимум
за всё время с появления. Цены — публичные 15-минутные свечи BingX (без ключей, без Binance); если свечей нет — показания пульса скринера.
Запуск любой частоты (идемпотентно): час дописывается один раз. Время — UTC.
Файлы (рядом): stars_journal.json (состояние), stars_journal.jsonl (события: star / hour / gone), stars_journal.md (читаемый итог).
    .venv/bin/python claude/research/stars_journal.py
"""
import json, time, urllib.request, datetime as dt
from pathlib import Path
R = Path(__file__).parent; BASE = R.parents[1]
ST, LOG, MD = R / "stars_journal.json", R / "stars_journal.jsonl", R / "stars_journal.md"
HOURS, KEEP_H = 24, 48          # итог по часам до 24 ч; из состояния убираем через 48 ч после появления (в jsonl остаётся всё)
U = dt.timezone.utc


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
        return json.loads(r.read())


def klines(sym, t0):
    """15-мин свечи BingX с t0−15 мин: [(t_open, o, h, l, c)]; пусто — нет монеты"""
    try:
        d = _get(f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={sym[:-4]}-USDT&interval=15m&startTime={int((t0 - 900) * 1000)}&limit=500")
        return sorted((int(x["time"]) / 1000, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"])) for x in (d.get("data") or []))
    except Exception:  # noqa: BLE001
        return []


def pulse_rows(sym):
    try:
        return [(float(r["t"]), float(r["price"])) for r in json.load(open(BASE / "pulse.json")).get(sym, []) if r.get("price")]
    except Exception:  # noqa: BLE001
        return []


def px_at(k, t):
    """закрытие последней свечи, закрывшейся не позже t"""
    c = [x for x in k if x[0] + 900 <= t]
    return c[-1][4] if c else None


def f_t(t):
    return dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M")


def log(e):
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def main():
    now = time.time()
    st = json.loads(ST.read_text(encoding="utf-8")) if ST.exists() else {}
    try:
        sj = json.loads((BASE / "output" / "stars.json").read_text(encoding="utf-8"))
        cur = {s["sym"]: (s.get("sub") or s.get("why") or "").split(" ‖ ")[0].strip() for s in sj.get("stars", []) if s.get("sym")}
    except Exception:  # noqa: BLE001
        cur = {}
    try:
        mem = json.loads((BASE / "output" / "fast_stars_mem.json").read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        mem = {}
    new = 0; hours_added = 0; gone = 0
    for sym, reason in cur.items():
        if sym in st and st[sym].get("gone") is None:
            continue
        t0 = float(mem.get(sym) or now)
        k = klines(sym, t0); src = "bingx"
        px0 = px_at(k, t0) or (k[0][1] if k else None)
        if px0 is None:
            pr = [p for t, p in pulse_rows(sym) if t <= t0 + 60]; px0 = pr[-1] if pr else None; src = "pulse"
        if px0 is None:
            continue
        st[sym] = dict(reason=reason, t0=t0, px0=px0, src=src, hours={}, hi=0.0, lo=0.0, gone=None, last=px0, last_pct=0.0)
        log(dict(kind="star", sym=sym, reason=reason, t0=t0, px0=px0, src=src, at=now)); new += 1
    for sym, s in st.items():
        if s.get("gone") is None and sym not in cur:
            s["gone"] = now; gone += 1
            log(dict(kind="gone", sym=sym, t0=s["t0"], at=now, pct=s.get("last_pct"), hi=s.get("hi"), lo=s.get("lo"), hours=int((now - s["t0"]) // 3600)))
    for sym, s in st.items():
        age_h = int((now - s["t0"]) // 3600)
        if age_h > KEEP_H:
            continue
        k = klines(sym, s["t0"]) if s.get("src") == "bingx" else []
        if not k:
            pr = pulse_rows(sym); k = [(t - 900, p, p, p, p) for t, p in pr if t >= s["t0"] - 60]
        if not k:
            continue
        win = [x for x in k if x[0] + 900 > s["t0"]]
        if win:
            s["hi"] = round((max(x[2] for x in win) / s["px0"] - 1) * 100, 2); s["lo"] = round((min(x[3] for x in win) / s["px0"] - 1) * 100, 2)
            s["last"] = win[-1][4]; s["last_pct"] = round((win[-1][4] / s["px0"] - 1) * 100, 2)
        for h in range(1, min(HOURS, age_h) + 1):
            if str(h) in s["hours"]:
                continue
            p = px_at(k, s["t0"] + h * 3600)
            if p is None:
                continue
            w = [x for x in k if x[0] + 900 > s["t0"] and x[0] + 900 <= s["t0"] + h * 3600]
            e = dict(kind="hour", sym=sym, t0=s["t0"], h=h, px=p, pct=round((p / s["px0"] - 1) * 100, 2),
                     hi=round((max(x[2] for x in w) / s["px0"] - 1) * 100, 2) if w else None, lo=round((min(x[3] for x in w) / s["px0"] - 1) * 100, 2) if w else None)
            s["hours"][str(h)] = e["pct"]; log(e); hours_added += 1
        time.sleep(0.25)
    st = {k: v for k, v in st.items() if now - v["t0"] <= KEEP_H * 3600 or v.get("gone") is None}
    ST.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Журнал новых звёзд («шорты — топливо») · обновлено {f_t(now)} UTC\n",
             "Ход в % от цены в момент появления; часы — итог на конец каждого полного часа; макс/мин — за всё время с появления.\n"]
    for sym, s in sorted(st.items(), key=lambda kv: -kv[1]["t0"]):
        hs = " ".join(f"{h}ч {s['hours'][str(h)]:+.1f}" for h in range(1, HOURS + 1) if str(h) in s["hours"])
        status = f"ушла {f_t(s['gone'])}" if s.get("gone") else "звезда сейчас"
        lines.append(f"- **{sym[:-4]}** · {s['reason']} · с {f_t(s['t0'])} UTC · {status} · сейчас {s['last_pct']:+.1f} % · макс {s['hi']:+.1f} % · мин {s['lo']:+.1f} %" + (f" · {hs}" if hs else ""))
    MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"журнал звёзд: звёзд в состоянии {len(st)} · новых {new} · ушло {gone} · часов дописано {hours_added} → {MD.name}")
    for ln in lines[2:]:
        print(ln)


if __name__ == "__main__":
    main()
