"""Расстановка толпы (Г-4): кто в лонге — счета и позиции топов.

Запуск из каталога проекта (сеть нужна, ключ в COINGLASS_KEY):
    python crowd_coinglass.py             # показать
    python crowd_coinglass.py --write     # записать срез
    python crowd_coinglass.py ENA BTC     # только названные

ДВЕ ПЕРСПЕКТИВЫ на монету, обе парой symbol+USDT на Binance:
  - глобальные СЧЕТА (толпа головами): доля лонг-счетов среди всех;
  - ПОЗИЦИИ топов (крупные деньгами): доля лонга в объёме позиций
    верхних двадцати процентов по марже.
Расхождение перспектив — само по себе чтение: толпа в лонге, топы
разгружаются — классический перекос перед сквизом. Точка top-account
(топы головами) пропущена сознательно: макет просил «топ и счета»,
а три точки на монету — это семьдесят пять запросов вместо пятидесяти.

УРОКИ ЖИВОЙ ФОРМЫ (29.08, crowd_probe.txt — не переоткрывать):
  - путь /futures/{global-long-short-account|top-long-short-position}-
    ratio/history; exchange, symbol (ПАРА вида ENAUSDT) и interval
    ОБЯЗАТЕЛЬНЫ; тариф Startup пускает интервал от 4h;
  - числа ЧИСЛАМИ (редкость у Coinglass); поля с префиксом
    global_account_* / top_position_*;
  - монета без пары на Binance ответит отказом — это «вне покрытия»,
    профиль MAGMA, не ошибка сборки.

ЧТО СЧИТАЕТСЯ: последняя точка каждой перспективы + сдвиг за сутки
(шесть баров по 4 часа назад) — «толпа набирает» или «толпа сдаёт».
В скор не входит; поле знания для карточки и дневного среза.

ЦЕНА: 2 запроса на монету, журнал+BTC ~52; контур суточный.

Сеть, ключ, отказ внутри кода 200 — ИЗ coinglass_fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from coinglass_fetch import (BASE_DIR, Denied, PAUSE_SEC, _base_coin,
                             _body, _journal_coins, _key, get)

OUT_PATH = BASE_DIR / "output" / "coinglass_crowd.json"

EXCHANGE = "Binance"
INTERVAL = "4h"
BARS = 8                       # ~32 часа: последняя точка + сутки назад
DAY_BACK = 6                   # шесть баров по 4 часа = сутки


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def parse_side(doc: dict, prefix: str) -> dict | None:
    """Ряд одной перспективы → последняя доля лонга и сдвиг за сутки."""
    rows = [r for r in (doc.get("data") or []) if isinstance(r, dict)]
    if not rows:
        return None
    last = _num(rows[-1].get(prefix + "_long_percent"))
    if last is None:
        return None
    out = {"longPct": round(last, 1)}
    if len(rows) > DAY_BACK:
        prev = _num(rows[-1 - DAY_BACK].get(prefix + "_long_percent"))
        if prev is not None:
            out["chg1d"] = round(last - prev, 1)
    return out


def collect(symbols: list[str] | None = None, *, key: str | None = None,
            verbose: bool = True) -> dict:
    key = key if key is not None else _key()
    if not key:
        return {"error": "нет ключа: export COINGLASS_KEY=… в этом окне"}
    coins = [_base_coin(s) for s in symbols] if symbols else None
    if coins is None:
        coins, _note = _journal_coins()
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "exchange": EXCHANGE, "interval": INTERVAL,
                   "coins": {}, "absent": [], "errors": {}, "requests": 0}
    plan = [("global-long-short-account-ratio", "global_account", "crowd"),
            ("top-long-short-position-ratio", "top_position", "top")]
    for coin in coins:
        pair = coin + "USDT"
        rec: dict = {}
        dead = False
        for path, prefix, field in plan:
            try:
                doc = _body(*get(f"/futures/{path}/history",
                                 {"exchange": EXCHANGE, "symbol": pair,
                                  "interval": INTERVAL, "limit": str(BARS)},
                                 key))
                side = parse_side(doc, prefix)
                if side:
                    rec[field] = side
            except Denied:
                dead = True
            state["requests"] += 1
            time.sleep(PAUSE_SEC)
            if dead:
                break
        if rec:
            state["coins"][coin] = rec
        elif dead:
            state["absent"].append(coin)
        if verbose and coin in state["coins"]:
            c = state["coins"][coin]
            print(f"  {coin}: толпа {c.get('crowd', {}).get('longPct')}% лонг"
                  f" · топы {c.get('top', {}).get('longPct')}%", file=sys.stderr)
    return state


def for_screens() -> dict[str, dict]:
    """Срез для показа: тикер → {crowd, top, crowdChg} из готового
    файла, без сети, кеш по mtime."""
    try:
        mt = OUT_PATH.stat().st_mtime
    except OSError:
        return {}
    if _SCREENS_CACHE["mtime"] == mt:
        return _SCREENS_CACHE["data"]
    try:
        raw = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for sym, c in (raw.get("coins") or {}).items():
        rec = {}
        if c.get("crowd", {}).get("longPct") is not None:
            rec["crowd"] = c["crowd"]["longPct"]
            if c["crowd"].get("chg1d") is not None:
                rec["crowdChg"] = c["crowd"]["chg1d"]
        if c.get("top", {}).get("longPct") is not None:
            rec["top"] = c["top"]["longPct"]
        if rec:
            out[sym] = rec
    _SCREENS_CACHE.update(mtime=mt, data=out)
    return out


_SCREENS_CACHE: dict = {"mtime": None, "data": {}}


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для врезки в run.py — правило владельца про
    отрезки: свежий файл — пропуск без сети."""
    try:
        age_h = (time.time() - OUT_PATH.stat().st_mtime) / 3600
        if age_h < max_age_hours:
            return f"срез свеж ({age_h:.0f} ч) — пропуск"
    except OSError:
        pass
    state = collect(verbose=False)
    if state.get("error"):
        return "✗ " + state["error"]
    try:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    except OSError as e:
        return f"✗ срез собран, но не записался: {e}"
    return (f"монет {len(state['coins'])}, вне покрытия "
            f"{len(state['absent'])}, запросов {state['requests']}, "
            f"ошибок {len(state['errors'])}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Расстановка толпы (Г-4)")
    ap.add_argument("symbols", nargs="*", help="монеты вместо журнала")
    ap.add_argument("--write", action="store_true",
                    help=f"записать срез в {OUT_PATH}")
    a = ap.parse_args()
    state = collect(a.symbols or None)
    if state.get("error"):
        print("✗", state["error"])
        return 1
    print(f"\nмонет: {len(state['coins'])} · вне покрытия: "
          f"{len(state['absent'])} · запросов: {state['requests']}")
    for coin, c in state["coins"].items():
        cr, tp = c.get("crowd") or {}, c.get("top") or {}
        line = f"  {coin:<9}"
        if cr:
            line += f" толпа {cr.get('longPct')}% лонг"
            if cr.get("chg1d") is not None:
                line += f" ({cr['chg1d']:+.1f} за сутки)"
        if tp:
            line += f" · топы позициями {tp.get('longPct')}%"
            gap = (cr.get("longPct") or 0) - (tp.get("longPct") or 0)
            if cr and abs(gap) >= 8:
                line += f" · РАСХОЖДЕНИЕ {gap:+.0f} пп"
        print(line)
    if state["absent"]:
        print("  вне покрытия пары Binance:", " ".join(state["absent"]))
    if a.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"записано: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
