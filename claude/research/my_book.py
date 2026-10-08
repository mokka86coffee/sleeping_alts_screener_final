#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА CLAUDE (08.10, владелец: «мониторь рынок, выбирай монеты, которые считаешь надо брать в шорт / в лонг, и бери сам их в сделку»,
«каждые полчаса мониторь, 10% профит закрываешь»).
Только бумага: ордеров на бирже эта книга не ставит и к ключам не обращается — выставлять сделки на бирже (и на демо тоже) Claude не может,
это закрыто правилами приложения. Цена входа и ведение — открытая цена и 15-минутные свечи BingX (публичные, без ключей).
Правила: выход по цели +TARGET % (слова владельца), по стопу, который Claude называет при входе (его мерка — уровень, где чтение сломано),
или руками командой close. Комиссия FEE % на круг. Время — UTC. Бота, зеркало и его книги не трогает.
    .venv/bin/python claude/research/my_book.py open SYM long|short СТОП_% "почему (фон первым)"
    .venv/bin/python claude/research/my_book.py check          # раз в полчаса: цены, цель, стоп
    .venv/bin/python claude/research/my_book.py close SYM "почему"
    .venv/bin/python claude/research/my_book.py status
Файлы: claude/research/my_book.json (открытые), claude/research/my_book.jsonl (журнал входов и выходов)."""
import json, sys, time, urllib.request, datetime as dt
from pathlib import Path
R = Path(__file__).parent; ST = R / "my_book.json"; LOG = R / "my_book.jsonl"; U = dt.timezone.utc
TARGET, FEE, USD, MAX_OPEN = 10.0, 0.1, 100.0, 5          # цель — слова владельца; комиссия, условные 100 $ на сделку и не больше 5 открытых — мерки Claude
API = "https://open-api.bingx.com/openApi/swap"


def _get(path: str) -> dict:
    with urllib.request.urlopen(urllib.request.Request(API + path, headers={"User-Agent": "Mozilla/5.0"}), timeout=15) as r:
        return json.loads(r.read())


def bx(sym: str) -> str:
    s = sym.upper().replace("USDT", "").replace("-", "")
    return s + "-USDT"


def price(sym: str) -> float:
    d = _get(f"/v2/quote/price?symbol={bx(sym)}")
    p = float(((d.get("data") or {}).get("price")) or 0)
    if not p:
        raise SystemExit(f"цена {bx(sym)} на BingX недоступна: {d.get('msg')}")
    return p


def bars(sym: str, t0: float) -> list:
    """15-минутные свечи BingX с момента t0: [(t, high, low, close)]"""
    d = _get(f"/v3/quote/klines?symbol={bx(sym)}&interval=15m&startTime={int(t0 * 1000)}&limit=500")
    return sorted((int(x["time"]) / 1000, float(x["high"]), float(x["low"]), float(x["close"])) for x in (d.get("data") or []))


def load() -> dict:
    return json.loads(ST.read_text(encoding="utf-8")) if ST.exists() else {}


def save(s: dict) -> None:
    ST.write_text(json.dumps(s, ensure_ascii=False, indent=1), encoding="utf-8")


def log(e: dict) -> None:
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(e, ensure_ascii=False) + "\n")


def f_t(t: float) -> str:
    return dt.datetime.fromtimestamp(t, U).strftime("%d.%m %H:%M UTC")


def do_open(sym: str, side: str, stop_pct: float, why: str) -> None:
    s = load(); key = bx(sym)
    if key in s:
        raise SystemExit(f"{key} уже открыта")
    if len(s) >= MAX_OPEN:
        raise SystemExit(f"открыто {len(s)} из {MAX_OPEN} — новую не беру")
    sd = 1 if side.lower().startswith("l") else -1
    p = price(sym); now = time.time()
    pos = dict(sym=key, side=sd, px=p, at=now, stop_pct=float(stop_pct), target_pct=TARGET, why=why,
               stop_px=p * (1 - sd * float(stop_pct) / 100), target_px=p * (1 + sd * TARGET / 100))
    s[key] = pos; save(s); log(dict(pos, kind="entry"))
    print(f"ВХОД {key} {'лонг' if sd == 1 else 'шорт'} {p:.6g} · цель {pos['target_px']:.6g} (+{TARGET:g}%) · стоп {pos['stop_px']:.6g} (−{stop_pct:g}%) · {f_t(now)}")


def _exit(s: dict, key: str, px: float, why: str, t: float) -> None:
    pos = s.pop(key); res = (px / pos["px"] - 1) * 100 * pos["side"] - FEE
    log(dict(kind="exit", sym=key, side=pos["side"], px_in=pos["px"], px_out=px, opened_at=pos["at"], at=t, result_pct=round(res, 2), usd=round(USD * res / 100, 2), why_exit=why, why=pos["why"]))
    print(f"ВЫХОД {key} {'лонг' if pos['side'] == 1 else 'шорт'} {pos['px']:.6g} → {px:.6g}: {res:+.2f}% ({USD * res / 100:+.2f} $ на {USD:g} $) · {why} · {f_t(t)}")


def do_check() -> None:
    s = load(); now = time.time()
    if not s:
        print("открытых нет")
    for key in list(s):
        pos = s[key]; sd = pos["side"]; done = False
        for t, h, l, c in bars(key, pos.get("seen", pos["at"])):
            if t + 900 <= pos["at"]:
                continue
            hit_stop = (l <= pos["stop_px"]) if sd == 1 else (h >= pos["stop_px"])
            hit_tgt = (h >= pos["target_px"]) if sd == 1 else (l <= pos["target_px"])
            if hit_stop:                                                  # в одной свече и стоп, и цель — считаем стоп
                _exit(s, key, pos["stop_px"], "стоп", t + 900); done = True; break
            if hit_tgt:
                _exit(s, key, pos["target_px"], f"цель +{pos['target_pct']:g}%", t + 900); done = True; break
        if done:
            continue
        p = price(key); pos["seen"] = now - 900; pos["last"] = p
        print(f"{key} {'лонг' if sd == 1 else 'шорт'} с {f_t(pos['at'])} · вход {pos['px']:.6g} · сейчас {p:.6g} ({(p / pos['px'] - 1) * 100 * sd:+.2f}%) · цель {pos['target_px']:.6g} · стоп {pos['stop_px']:.6g}")
        time.sleep(0.3)
    save(s)


def do_status() -> None:
    do_check()
    n = w = 0; tot = 0.0
    if LOG.exists():
        for l in LOG.read_text(encoding="utf-8").splitlines():
            e = json.loads(l)
            if e.get("kind") == "exit":
                n += 1; w += e["result_pct"] > 0; tot += e["usd"]
    print(f"закрыто сделок: {n} · в плюс {w} · итог {tot:+.2f} $ (по {USD:g} $ на сделку, бумага)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or a[0] == "status":
        do_status()
    elif a[0] == "check":
        do_check()
    elif a[0] == "open" and len(a) >= 5:
        do_open(a[1], a[2], float(a[3]), a[4])
    elif a[0] == "close" and len(a) >= 2:
        s = load(); key = bx(a[1])
        if key not in s:
            raise SystemExit(f"{key} не открыта")
        _exit(s, key, price(key), "руками: " + (a[2] if len(a) > 2 else ""), time.time()); save(s)
    else:
        print(__doc__)
