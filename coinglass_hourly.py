#!/usr/bin/env python3
"""Часовые свечи Coinglass за 180 дней по монетам журнала (02.09).

ЗАЧЕМ. Сводка «когда растёт»: в какие дни и часы больше монет идёт
вверх. Дневки архива на это не отвечают, пульс копится только с 31.08.
Тариф Startup отдаёт часовую историю на 180 дней — ровно то, что нужно.

СКОЛЬКО ЗАПРОСОВ. 180 дней × 24 = 4320 свечей на монету. Лимит одного
ответа у Coinglass обычно 1000–4500 — берём страницами по endTime.
Семьдесят монет × 2–5 страниц ≈ 250 запросов, около шести минут на
сорока четырёх в минуту. Делать РАЗ, потом только дописывать хвост
(--update берёт с последней сохранённой свечи).

ЭНДПОИНТ. Путь к часовым свечам в v4 у меня без ключа не проверить —
поэтому --probe пробует три кандидата и печатает, какой отвечает.
Первый запуск: python3 coinglass_hourly.py --probe

    python3 coinglass_hourly.py --probe          # какой путь живой
    python3 coinglass_hourly.py                  # всё, 180 дней
    python3 coinglass_hourly.py --update         # только хвост
    python3 coinglass_hourly.py --only SOL ENA   # выборочно

Пишет hourly/<coin>.json: список {"t": мс, "o","h","l","c","v"}.
"""
import argparse
import json
import time
from pathlib import Path

from coinglass_fetch import get, _key, _journal_coins, PAUSE_SEC

OUT = Path("hourly")
DAYS = 180
# Кандидаты пути. Первый живой становится рабочим.
# Пробник 02.09: живой только /futures/price/history, и он требует
# параметр exchange. Остальные два — 404, сняты.
CANDIDATES = ["/futures/price/history"]
EXCHANGE = "Binance"
STEP_MS = 3600 * 1000
PAGE = 1000                                 # свечей за запрос
END_PARAM = "endTime"                       # ставится из --probe
END_SECONDS = False


def probe_paging(key: str, path: str) -> str | None:
    """Первый сбор дал ровно 1000 свечей у всех — окно не листалось.
    Пробуем имена параметра конца окна и единицы времени; живой тот,
    после которого последняя свеча ответа старше сорока дней."""
    import datetime as _dt
    cut = int(time.time()) - 40 * 86400
    trials = [("endTime", cut * 1000), ("endTime", cut),
              ("end_time", cut * 1000), ("end_time", cut),
              ("endTs", cut), ("to", cut)]
    for name, val in trials:
        code, body = get(path, {"exchange": EXCHANGE, "symbol": "BTCUSDT",
                                "interval": "1h", "limit": 5, name: val}, key)
        rows = [x for x in (_norm(r) for r in _rows(body)) if x]
        time.sleep(PAUSE_SEC)
        if not rows:
            print(f"  {name}={val}: пусто")
            continue
        last = max(r["t"] for r in rows) / 1000
        age = (time.time() - last) / 86400
        print(f"  {name}={val}: последняя свеча {age:.0f} дн назад")
        if age >= 30:
            return name if val == cut * 1000 else name + ":s"
    return None


def probe(key: str) -> str | None:
    for path in CANDIDATES:
        # Пробник 02.09, второй заход: биржа принята, но «BTC» — «пара
        # не существует». Значит символ нужен парой: BTCUSDT.
        code, body = get(path, {"exchange": EXCHANGE, "symbol": "BTCUSDT",
                                "interval": "1h", "limit": 5}, key)
        rows = _rows(body)
        print(f"  {path:36} {code} · строк {len(rows)}"
              + ("" if rows else f" · {str(body)[:70]}"))
        if rows:
            print("  первая строка:", str(rows[0])[:160])
            print("  разобрана как:", _norm(rows[0]))
        time.sleep(PAUSE_SEC)
        if code == 200 and rows:
            return path
    return None


def _rows(body) -> list:
    if not isinstance(body, dict):
        return []
    d = body.get("data")
    if isinstance(d, list):
        return d
    if isinstance(d, dict):
        for k in ("list", "rows", "data"):
            if isinstance(d.get(k), list):
                return d[k]
    return []


def _norm(r: dict) -> dict | None:
    """Разные имена полей у разных точек — сводим к одному."""
    t = r.get("t") or r.get("time") or r.get("ts") or r.get("timestamp")
    if t is None:
        return None
    t = int(t)
    if t < 1e12:
        t *= 1000                              # секунды → миллисекунды
    def f(*names):
        for n in names:
            v = r.get(n)
            if v is not None:
                try:
                    return float(v)
                except (TypeError, ValueError):
                    pass
        return None
    o, h, l, c = f("o", "open"), f("h", "high"), f("l", "low"), f("c", "close")
    if None in (o, h, l, c):
        return None
    return {"t": t, "o": o, "h": h, "l": l, "c": c,
            "v": f("v", "volume_usd", "volume", "volumeUsd") or 0.0}


def fetch_coin(coin: str, path: str, key: str, since_ms: int | None,
               verbose: bool) -> list[dict]:
    # Coinglass ждёт ПАРУ: BTCUSDT, не BTC (пробник 02.09).
    sym = coin if coin.endswith("USDT") else coin + "USDT"
    return _fetch_pages(sym, path, key, since_ms, verbose)


def _fetch_pages(coin: str, path: str, key: str, since_ms: int | None,
                 verbose: bool) -> list[dict]:
    end = int(time.time() * 1000)
    floor = since_ms or (end - DAYS * 86400 * 1000)
    out: list[dict] = []
    pages = 0
    while end > floor and pages < 12:
        _endv = end // 1000 if END_SECONDS else end
        code, body = get(path, {"exchange": EXCHANGE, "symbol": coin,
                                "interval": "1h", "limit": PAGE,
                                END_PARAM: _endv}, key)
        pages += 1
        rows = [x for x in (_norm(r) for r in _rows(body)) if x]
        time.sleep(PAUSE_SEC)
        if code != 200 or not rows:
            if verbose:
                print(f"  {coin}: стр.{pages} код {code}, строк 0 — стоп")
            break
        rows.sort(key=lambda x: x["t"])
        oldest = rows[0]["t"]
        if out and oldest >= out[0]["t"]:
            if verbose:
                print(f"  {coin}: окно не сдвинулось — параметр конца "
                      "не работает, стоп")
            break
        out = rows + out
        if oldest <= floor or len(rows) < PAGE:
            break
        end = oldest - STEP_MS
    # склейка без дублей
    seen, uniq = set(), []
    for r in out:
        if r["t"] in seen or r["t"] < floor:
            continue
        seen.add(r["t"]); uniq.append(r)
    return uniq


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--update", action="store_true",
                    help="дописать с последней сохранённой свечи")
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--path", default=None, help="путь, если известен")
    ap.add_argument("-q", action="store_true")
    ap.add_argument("--end-param", default=None,
                    help="имя параметра конца окна из --probe, "
                         "например endTime или endTime:s")
    a = ap.parse_args()
    key = _key()
    if not key:
        print("нет COINGLASS_KEY")
        return 1
    if a.probe:
        print("пробую пути к часовым свечам:")
        p = probe(key)
        print("рабочий:", p or "НЕ НАЙДЕН — пришли ответ, подберу")
        if p:
            print("пробую параметр конца окна (нужен для 180 дней):")
            pg = probe_paging(key, p)
            print("параметр:", pg or "НИ ОДИН — пришли вывод")
        return 0
    path = a.path or probe(key)
    if not path:
        print("живого пути нет — запусти --probe и пришли вывод")
        return 1
    global END_PARAM, END_SECONDS
    ep = a.end_param or probe_paging(key, path)
    if not ep:
        print("параметр конца окна не найден — соберётся только "
              "последняя тысяча свечей (~6 недель)")
        ep = "endTime"
    END_SECONDS = ep.endswith(":s")
    END_PARAM = ep.split(":")[0]
    print(f"конец окна: {END_PARAM} в "
          f"{'секундах' if END_SECONDS else 'миллисекундах'}")
    coins = [c.upper() for c in a.only] if a.only else _journal_coins()[0]
    OUT.mkdir(exist_ok=True)
    ok = bad = 0
    t0 = time.time()
    for c in coins:
        f = OUT / f"{c.lower()}.json"
        old: list[dict] = []
        since = None
        if a.update and f.exists():
            try:
                old = json.loads(f.read_text(encoding="utf-8"))
                since = (old[-1]["t"] + STEP_MS) if old else None
            except (ValueError, KeyError, IndexError):
                old = []
        rows = fetch_coin(c, path, key, since, not a.q)
        if not rows and not old:
            bad += 1
            continue
        merged = old + [r for r in rows if not old or r["t"] > old[-1]["t"]]
        f.write_text(json.dumps(merged, separators=(",", ":")),
                     encoding="utf-8")
        ok += 1
        if not a.q:
            print(f"  {c:8} свечей {len(merged):5} · новых {len(rows):4}")
    print(f"готово: монет {ok}, пусто {bad}, {time.time()-t0:.0f} с · "
          f"папка {OUT}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
