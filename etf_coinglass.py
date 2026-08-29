"""Потоки фондов (Г-6): ETF BTC/ETH/SOL/XRP числом, без ручного поиска.

Запуск из каталога проекта (сеть нужна, ключ в COINGLASS_KEY):
    python etf_coinglass.py             # показать
    python etf_coinglass.py --write     # записать срез

ЧТО ДЕЛАЕТ. Пять запросов: четыре ленты дневных потоков (биткоин,
эфир, солана, рипл) и список биткоин-фондов ради ЗАПАСА монет. По
каждому активу берётся хвост: последний отчётный день, сумма за пять
отчётных дней, кто больше всех заводил и выводил в последний день.

УРОК 25.08 — В ЛОБ: поток ≠ переоценка активов. Эта точка даёт именно
ПОТОК — сколько денег зашло в обёртку, а не что рынок думает о цене.
Категория «фонды/ETF» дневного среза, поле знания; в скор не входит.

УРОКИ ЖИВОЙ ФОРМЫ (29.08, funds_probe.txt — не переоткрывать):
  - форма лент едина: data[] из {timestamp, flow_usd (сводный день),
    price_usd, etf_flows[{etf_ticker, flow_usd?}]};
  - ленты отдаются С НАЧАЛА ИСТОРИИ (биткоин — с января 2024) —
    читаем хвост, весь ряд не храним;
  - выходной/праздник приходит днём, где НИ У ОДНОГО фонда нет поля
    flow_usd — отбрасывать, как незакрытый бар; ноль у фонда в
    отчётный день — честный ноль, не дыра;
  - ПРЕМИЯ GRAYSCALE МЕРТВА: после конверсии трестов в ETF премия у
    всех фондов ±0.2% — сигнала нет. Вместо неё живое — изменение
    ЗАПАСА монет (asset_details.change_quantity_24h/7d в списке);
  - в списке фондов числа СТРОКАМИ (aum, капа) — приводить явно.

ЦЕНА: 5 запросов на обновление; контур суточный (auto_update) — потоки
фондов дневные, чаще обновлять нечего.

Сеть, ключ и отказ внутри кода 200 — ИЗ coinglass_fetch: один сетевой
слой на все инструменты Coinglass.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from coinglass_fetch import BASE_DIR, Denied, PAUSE_SEC, _body, _key, get

OUT_PATH = BASE_DIR / "output" / "coinglass_etf.json"

ASSETS = ("bitcoin", "ethereum", "solana", "xrp")
TAIL_DAYS = 5                    # отчётных дней в хвосте


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _d(ms) -> str:
    n = _num(ms)
    if not n:
        return "—"
    return datetime.fromtimestamp(n / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _reported(day: dict) -> bool:
    """Отчётный ли день: хоть у одного фонда есть поле потока.
    Выходной приходит строем фондов вовсе без flow_usd."""
    return any(_num(f.get("flow_usd")) is not None
               for f in day.get("etf_flows") or [])


def parse_flows(doc: dict) -> dict | None:
    """Лента одного актива → хвост числом."""
    rows = [r for r in (doc.get("data") or [])
            if isinstance(r, dict) and _reported(r)]
    if not rows:
        return None
    tail = rows[-TAIL_DAYS:]
    last = tail[-1]
    funds = [(f.get("etf_ticker"), _num(f.get("flow_usd")))
             for f in last.get("etf_flows") or []]
    funds = [(t, v) for t, v in funds if t and v is not None]
    out = {
        "lastDate": _d(last.get("timestamp")),
        "lastFlow": _num(last.get("flow_usd")),
        "priceUsd": _num(last.get("price_usd")),
        "sum5": round(sum(_num(r.get("flow_usd")) or 0 for r in tail), 0),
        "days5": len(tail),
    }
    if funds:
        top = max(funds, key=lambda x: x[1])
        low = min(funds, key=lambda x: x[1])
        if top[1] > 0:
            out["topIn"] = {"ticker": top[0], "usd": top[1]}
        if low[1] < 0:
            out["topOut"] = {"ticker": low[0], "usd": low[1]}
    return out


def parse_btc_list(doc: dict) -> dict | None:
    """Список биткоин-фондов → изменение ЗАПАСА монет (не премия).

    Складываются только фонды, у которых поле изменения ЕСТЬ: часть
    отчитывается с лагом (update_date у всех свой), и досчитывать за
    них — врать суммой."""
    rows = doc.get("data") or []
    chg24, chg7, n24, n7 = 0.0, 0.0, 0, 0
    for r in rows:
        ad = r.get("asset_details") or {}
        v = _num(ad.get("change_quantity_24h"))
        if v is not None:
            chg24 += v
            n24 += 1
        v = _num(ad.get("change_quantity_7d"))
        if v is not None:
            chg7 += v
            n7 += 1
    if not n24 and not n7:
        return None
    out = {"funds": len(rows)}
    if n24:
        out["holdChg24hBtc"] = round(chg24, 1)
        out["reported24h"] = n24
    if n7:
        out["holdChg7dBtc"] = round(chg7, 1)
        out["reported7d"] = n7
    return out


def collect(*, key: str | None = None, verbose: bool = True) -> dict:
    key = key if key is not None else _key()
    if not key:
        return {"error": "нет ключа: export COINGLASS_KEY=… в этом окне"}
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "assets": {}, "errors": {}, "requests": 0}
    for asset in ASSETS:
        try:
            doc = _body(*get(f"/etf/{asset}/flow-history", {}, key))
            parsed = parse_flows(doc)
            if parsed:
                state["assets"][asset] = parsed
            else:
                state["errors"][asset] = "отчётных дней в ленте нет"
        except Denied as e:
            state["errors"][asset] = str(e)
        state["requests"] += 1
        time.sleep(PAUSE_SEC)
    try:
        hold = parse_btc_list(_body(*get("/etf/bitcoin/list", {}, key)))
        if hold:
            state["assets"].setdefault("bitcoin", {})["holdings"] = hold
    except Denied as e:
        state["errors"]["bitcoin list"] = str(e)
    state["requests"] += 1
    if verbose:
        for a, v in state["assets"].items():
            print(f"  {a}: {v.get('lastDate')} · день "
                  f"{_usd(v.get('lastFlow'))} · 5 дн {_usd(v.get('sum5'))}",
                  file=sys.stderr)
    return state


def _usd(v) -> str:
    n = _num(v)
    if n is None:
        return "—"
    sg, a = ("−" if n < 0 else "+"), abs(n)
    if a >= 1e9:
        return f"{sg}${a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{sg}${a / 1e6:.1f}M"
    return f"{sg}${a / 1e3:.0f}K"


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для врезки в run.py — как у разлоков: свежий
    файл — пропуск без сети; правило владельца 29.08 про отрезки."""
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
    b = state["assets"].get("bitcoin") or {}
    return (f"активов {len(state['assets'])}, запросов {state['requests']}, "
            f"ошибок {len(state['errors'])} · BTC день {_usd(b.get('lastFlow'))}"
            f", 5 дн {_usd(b.get('sum5'))}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Потоки ETF числом (Г-6)")
    ap.add_argument("--write", action="store_true",
                    help=f"записать срез в {OUT_PATH}")
    a = ap.parse_args()
    state = collect()
    if state.get("error"):
        print("✗", state["error"])
        return 1
    print(f"\nактивов: {len(state['assets'])} · запросов: "
          f"{state['requests']} · ошибок: {len(state['errors'])}")
    for asset, v in state["assets"].items():
        line = (f"  {asset:<9} {v.get('lastDate')} · день "
                f"{_usd(v.get('lastFlow'))} · 5 дн {_usd(v.get('sum5'))}")
        if v.get("topIn"):
            line += f" · заводил {v['topIn']['ticker']} {_usd(v['topIn']['usd'])}"
        if v.get("topOut"):
            line += f" · выводил {v['topOut']['ticker']} {_usd(v['topOut']['usd'])}"
        h = v.get("holdings")
        if h:
            line += (f" · запас за 7 дн {h.get('holdChg7dBtc'):+,.0f} BTC"
                     f" ({h.get('reported7d')} фондов отчитались)")
        print(line)
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
