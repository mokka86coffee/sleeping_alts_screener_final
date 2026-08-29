"""Приток к капитализации (Г-3): спотовые деньги числом.

Запуск из каталога проекта (сеть нужна, ключ в COINGLASS_KEY):
    python netflow_coinglass.py             # показать
    python netflow_coinglass.py --write     # записать срез

ЗАЧЕМ. Клетка «деньги» дневного среза: чистый СПОТОВЫЙ приток за
сутки и неделю долей капитализации. Спот — живые деньги; фьючерсную
дельту сюда не мешаем, она уже считается своим срезом (coinglass_fetch)
по ногам объёма. В скор не входит.

УСТРОЙСТВО — ЛИСТ ПЕРВЫМ, адресные хвостом:
  1) /spot/netflow-list — ОДИН запрос, все горизонты разом по топу
     рынка, капитализация в строке; параметр interval точка молча
     игнорирует (проверено), лист всегда полный;
  2) кого из журнала в листе нет — адресная /spot/coin/netflow
     (путь с КОСОЙ ЧЕРТОЙ; вариант через дефис — 404, проверено).

УРОКИ ЖИВОЙ ФОРМЫ (29.08, crowd_probe.txt — не переоткрывать):
  - в ЛИСТЕ числа числами, готовой доли к капе нет — считаем сами
    от market_cap той же строки;
  - в АДРЕСНОЙ числа СТРОКАМИ, зато доля к капе готовая
    (net_flow_usd_24h_market_cap_ratio, В ПРОЦЕНТАХ) и есть
    change_percent к прошлому окну;
  - горизонты листа: 5m…30d; адресной: 5m…30d с другой сеткой.

ЦЕНА: 1 запрос листа + адресные только по недостающим (обычно
меньше десятка); контур суточный.

Сеть, ключ, отказ внутри кода 200 — ИЗ coinglass_fetch.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from coinglass_fetch import (BASE_DIR, Denied, PAUSE_SEC, _body,
                             _journal_coins, _key, get)

OUT_PATH = BASE_DIR / "output" / "coinglass_netflow.json"


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _pct(flow, cap):
    f, c = _num(flow), _num(cap)
    if f is None or not c:
        return None
    return round(f / c * 100, 3)


def parse_list_row(row: dict) -> dict | None:
    """Строка листа → приток за сутки и неделю долей капы."""
    cap = _num(row.get("market_cap"))
    if not cap:
        return None
    out = {"capUsd": cap}
    d = _pct(row.get("net_flow_usd_24h"), cap)
    w = _pct(row.get("net_flow_usd_7d"), cap)
    if d is not None:
        out["pctCap24h"] = d
        out["usd24h"] = round(_num(row.get("net_flow_usd_24h")), 0)
    if w is not None:
        out["pctCap7d"] = w
    return out if len(out) > 1 else None


def parse_coin(doc: dict) -> dict | None:
    """Адресный ответ → то же чтение; доля к капе тут ГОТОВАЯ."""
    d = doc.get("data") or {}
    if not isinstance(d, dict):
        return None
    out: dict = {}
    v = _num(d.get("net_flow_usd_24h_market_cap_ratio"))
    if v is not None:
        out["pctCap24h"] = round(v, 3)
        u = _num(d.get("net_flow_usd_24h"))
        if u is not None:
            out["usd24h"] = round(u, 0)
    v = _num(d.get("net_flow_usd_7d_market_cap_ratio"))
    if v is not None:
        out["pctCap7d"] = round(v, 3)
    return out or None


def collect(symbols: list[str] | None = None, *, key: str | None = None,
            verbose: bool = True) -> dict:
    key = key if key is not None else _key()
    if not key:
        return {"error": "нет ключа: export COINGLASS_KEY=… в этом окне"}
    coins = symbols if symbols else _journal_coins()[0]
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "coins": {}, "absent": [], "errors": {}, "requests": 0}
    want = set(coins) | {"BTC"}
    try:
        doc = _body(*get("/spot/netflow-list", {}, key))
        state["requests"] += 1
        for row in doc.get("data") or []:
            sym = row.get("symbol")
            if sym in want:
                parsed = parse_list_row(row)
                if parsed:
                    parsed["src"] = "list"
                    state["coins"][sym] = parsed
    except Denied as e:
        state["errors"]["netflow-list"] = str(e)
    time.sleep(PAUSE_SEC)
    for coin in sorted(want - set(state["coins"])):
        try:
            parsed = parse_coin(_body(*get("/spot/coin/netflow",
                                           {"symbol": coin}, key)))
            if parsed:
                parsed["src"] = "coin"
                state["coins"][coin] = parsed
            else:
                state["absent"].append(coin)
        except Denied:
            state["absent"].append(coin)
        state["requests"] += 1
        time.sleep(PAUSE_SEC)
    if verbose:
        for sym in ("BTC",) + tuple(sorted(set(coins))[:4]):
            c = state["coins"].get(sym)
            if c:
                print(f"  {sym}: сутки {c.get('pctCap24h'):+.3f}% капы",
                      file=sys.stderr)
    return state


_SCREENS_CACHE: dict = {"mtime": None, "data": {}}


def for_screens() -> dict[str, dict]:
    """Срез для показа: тикер → {pctCap24h, pctCap7d} без сети."""
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
    out = {}
    for sym, c in (raw.get("coins") or {}).items():
        rec = {k: c[k] for k in ("pctCap24h", "pctCap7d") if c.get(k) is not None}
        if rec:
            out[sym] = rec
    _SCREENS_CACHE.update(mtime=mt, data=out)
    return out


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для врезки в run.py."""
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
    btc = state["coins"].get("BTC") or {}
    return (f"монет {len(state['coins'])}, вне покрытия "
            f"{len(state['absent'])}, запросов {state['requests']}"
            + (f" · BTC сутки {btc.get('pctCap24h'):+.3f}% капы"
               if btc.get("pctCap24h") is not None else ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="Приток к капе (Г-3)")
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
    hot = sorted(state["coins"].items(),
                 key=lambda kv: abs(kv[1].get("pctCap24h") or 0), reverse=True)
    for sym, c in hot:
        print(f"  {sym:<9} сутки {c.get('pctCap24h', 0):+.3f}% капы"
              f" · неделя {c.get('pctCap7d', 0):+.3f}%"
              f"  [{c.get('src')}]")
    if state["absent"]:
        print("  вне покрытия:", " ".join(state["absent"]))
    for what, why in state["errors"].items():
        print(f"  ✗ {what}: {why}")
    if a.write:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                            encoding="utf-8")
        print(f"записано: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
