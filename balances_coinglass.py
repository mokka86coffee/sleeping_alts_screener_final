"""Балансы бирж (Г-7): заводы и выводы монет журнала числом.

Запуск из каталога проекта (сеть нужна, ключ в COINGLASS_KEY):
    python balances_coinglass.py             # показать
    python balances_coinglass.py --write     # записать срез
    python balances_coinglass.py H HYPE      # только названные

ЗАЧЕМ. «Наблюдаемы действия, не намерения»: перевод на биржу —
подготовка продажи, вывод — уход в холод. Прямой датчик для кандидата
«ОТКУП РАЗЛОКА» (зеркало-правило кандидата не трогается: положительное
чтение — только поле знания) и категория «потоки бирж» дневного среза.
В скор не входит.

ЕДИНИЦЫ — МОНЕТЫ, не доллары: точка отдаёт балансы в штуках, и это
правильно для датчика — доллары шумят ценой, а «завели 30 тысяч BTC»
читается одинаково при любой цене.

УРОКИ ЖИВОЙ ФОРМЫ (29.08, chain_probe.txt — не переоткрывать):
  - параметр symbol ОБЯЗАТЕЛЕН (без него честный 400);
  - форма: data[] по биржам, у каждой total_balance и
    balance_change_{1d,7d,30d} абсолютом и процентом; числа числами;
  - ПОКРЫТИЕ микрокапов под вопросом: ENA дала code 500 «Server
    Error» ВНУТРИ HTTP 200 — это «монеты нет у точки», профиль
    MAGMA, помечаем «нет данных» и не считаем ошибкой сборки;
  - у части бирж изменения строго нулевые (Bitget) — похоже, там
    отслеживается только остаток; суммы это не ломает;
  - /exchange/chain/tx/list ОТЛОЖЕНА: пусто даже на BTC и ETH с
    порогом — форму не видели, на пустоте не строим.

ЦЕНА: 1 запрос на монету; журнал+BTC ~26 запросов, контур суточный.

Сеть, ключ, отказ внутри кода 200 — ИЗ coinglass_fetch: один сетевой
слой на все инструменты Coinglass.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone

from coinglass_fetch import (BASE_DIR, Denied, PAUSE_SEC, _base_coin, _body,
                             _journal_coins, _key, get)

OUT_PATH = BASE_DIR / "output" / "coinglass_balances.json"


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def parse_balances(doc: dict) -> dict | None:
    """Список бирж → сводка по монете.

    Складываем остаток и изменения по всем биржам; проценты считаем
    ОТ СУММАРНОЙ базы (остаток минус изменение), а не средним по
    биржам — среднее из процентов врало бы весами."""
    rows = [r for r in (doc.get("data") or []) if isinstance(r, dict)]
    if not rows:
        return None
    total = sum(_num(r.get("total_balance")) or 0 for r in rows)
    if total <= 0:
        return None
    out: dict = {"total": round(total, 1), "exchanges": len(rows)}
    for span in ("1d", "7d", "30d"):
        chg = sum(_num(r.get("balance_change_" + span)) or 0 for r in rows)
        base = total - chg
        out["chg" + span] = round(chg, 1)
        if base > 0:
            out["chg" + span + "Pct"] = round(chg / base * 100, 2)
    # самая заметная биржа суток — куда несут или откуда выносят
    mover = max(rows, key=lambda r: abs(_num(r.get("balance_change_1d")) or 0))
    mv = _num(mover.get("balance_change_1d")) or 0
    if mv:
        out["mover1d"] = {"exchange": mover.get("exchange_name"),
                          "chg": round(mv, 1)}
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
                   "coins": {}, "absent": [], "errors": {}, "requests": 0}
    for coin in coins:
        try:
            parsed = parse_balances(_body(*get("/exchange/balance/list",
                                               {"symbol": coin}, key)))
            if parsed:
                state["coins"][coin] = parsed
            else:
                state["absent"].append(coin)
        except Denied as e:
            # code 500 внутри 200 = «монеты нет у точки» — не ошибка
            if "500" in str(e) or "Server Error" in str(e):
                state["absent"].append(coin)
            else:
                state["errors"][coin] = str(e)
        state["requests"] += 1
        time.sleep(PAUSE_SEC)
        if verbose and coin in state["coins"]:
            c = state["coins"][coin]
            print(f"  {coin}: сутки {c.get('chg1dPct'):+.2f}% · неделя "
                  f"{c.get('chg7dPct'):+.2f}%", file=sys.stderr)
    return state


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для врезки в run.py — как у разлоков и фондов:
    свежий файл — пропуск без сети (правило владельца про отрезки)."""
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
    ap = argparse.ArgumentParser(description="Балансы бирж по журналу (Г-7)")
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
                 key=lambda kv: abs(kv[1].get("chg1dPct") or 0), reverse=True)
    for coin, c in hot[:10]:
        line = (f"  {coin:<9} сутки {c.get('chg1dPct'):+.2f}% "
                f"({c.get('chg1d'):+,.0f}) · неделя {c.get('chg7dPct'):+.2f}%")
        if c.get("mover1d"):
            line += (f" · {c['mover1d']['exchange']} "
                     f"{c['mover1d']['chg']:+,.0f}")
        print(line)
    if state["absent"]:
        print("  вне покрытия точки:", " ".join(state["absent"]))
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
