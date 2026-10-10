#!/usr/bin/env python3
"""СЛЕЖЕНИЕ РАЗ В 10 МИНУТ (10.10 03:35 UTC, владелец: «вот мониторь эти монеты каждые 10 минут»). Список — WATCH (менять словом владельца).
По каждой: цена BingX, ход с прошлой проверки, за 1 ч, за 24 ч, объём последней 15-мин свечи к среднему за сутки, интерес и фандинг из пульса
скринера (раз в ~35 мин), позиция бота. Состояние прошлой проверки — watch10.json. Печатает только числа.
    .venv/bin/python claude/research/watch10.py
"""
import json, time, urllib.request, datetime as dt
from pathlib import Path
R = Path(__file__).parent; BASE = R.parents[1]; ST = R / "watch10.json"
WATCH = ["STRKUSDT", "JCTUSDT", "PIXELUSDT", "MAGICUSDT", "GMTUSDT", "BIGTIMEUSDT", "BTRUSDT", "USUSDT", "RLCUSDT", "ZKUSDT"]   # 10.10 владелец: «10 монет что могут пойти»
ALERT = 2.0   # ход с прошлой проверки, % — отмечается стрелкой (мерка Claude)


def kl(sym, iv, n):
    u = f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={sym[:-4]}-USDT&interval={iv}&limit={n}"
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
        d = json.loads(r.read())
    return sorted((int(x["time"]) / 1000, float(x["open"]), float(x["high"]), float(x["low"]), float(x["close"]), float(x["volume"])) for x in (d.get("data") or []))


def main():
    now = time.time(); prev = json.loads(ST.read_text()) if ST.exists() else {}
    try:
        pulse = json.load(open(BASE / "pulse.json"))
    except Exception:  # noqa: BLE001
        pulse = {}
    try:
        fs = json.load(open(BASE / "output" / "fast_state.json")); opens = {p["sym"]: p for p in fs.get("open", [])}; stars = {s["sym"] for s in fs.get("stars", [])}
        marks = {q["sym"]: q.get("mark") for q in fs.get("queue", [])}
    except Exception:  # noqa: BLE001
        opens, stars, marks = {}, set(), {}
    b = kl("BTCUSDT", "15m", 100); bc = b[-1][4]
    print(f"{dt.datetime.fromtimestamp(now, dt.timezone.utc):%H:%M} UTC · BTC {bc:,.0f} · за 1 ч {(bc / b[-5][4] - 1) * 100:+.2f} % · за 24 ч {(bc / b[-97][4] - 1) * 100:+.2f} %" + (f" · с прошлой {(bc / prev['BTCUSDT'] - 1) * 100:+.2f} %" if prev.get("BTCUSDT") else ""))
    cur = {"BTCUSDT": bc}
    for s in WATCH:
        k = []
        for _try in range(3):                                             # 10.10 07:15: BingX через раз отдаёт пусто — до трёх попыток с паузой
            try:
                k = kl(s, "15m", 100)
            except Exception:  # noqa: BLE001
                k = []
            if len(k) >= 97:
                break
            time.sleep(1.0)
        if len(k) < 97:                                                   # 10.10 04:15: BingX вернул пусто по GMT (а по PIXEL — 98–99 свечей вместо 100) — скрипт падал, остальные монеты не выводились
            print(f"- {s[:-4]}: цен BingX нет сейчас"); time.sleep(0.3); continue
        c = k[-1][4]; cur[s] = c
        vol = [x[5] for x in k[:-1]]; vx = k[-1][5] / (sum(vol) / len(vol)) if vol else 0
        d_prev = (c / prev[s] - 1) * 100 if prev.get(s) else None
        p = pulse.get(s, [])[-2:]
        pz = (f"интерес {p[-1]['oi_usd'] / p[-1]['price'] / 1e6:.0f} млн монет" + (f" ({(p[-1]['oi_usd'] / p[-1]['price']) / (p[0]['oi_usd'] / p[0]['price']) * 100 - 100:+.1f} % за прогон)" if len(p) == 2 else "")
              + f" · фандинг {p[-1].get('funding')} ({dt.datetime.fromtimestamp(p[-1]['t'], dt.timezone.utc):%H:%M})") if p else "пульса нет"
        op = opens.get(s); pos = f" · бот {'лонг' if op['side'] == 1 else 'шорт'} с {op['entry']:.5g}" if op else ""
        tag = (" · звезда" if s in stars else "") + (f" · очередь «{marks[s]}»" if s in marks else "")
        arrow = (" ▲" if d_prev >= ALERT else " ▼" if d_prev <= -ALERT else "") if d_prev is not None else ""
        print(f"- {s[:-4]} {c:.5g}{arrow} · с прошлой {d_prev:+.1f} %" if d_prev is not None else f"- {s[:-4]} {c:.5g} · первая проверка", end="")
        print(f" · за 1 ч {(c / k[-5][4] - 1) * 100:+.1f} % · за 24 ч {(c / k[-97][4] - 1) * 100:+.1f} % · объём 15м ×{vx:.1f} · {pz}{pos}{tag}")
        time.sleep(0.15)
    cur["_at"] = now; ST.write_text(json.dumps(cur))


if __name__ == "__main__":
    main()
