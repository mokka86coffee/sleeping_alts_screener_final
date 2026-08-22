"""Эталонный реплей FLOW по биткоину (Р-24). Проверка с известным ответом.

Запуск:
    python flow_replay_btc.py                # шаг 3 дня, весь кэш
    python flow_replay_btc.py --step 1       # каждый день (дольше)
    python flow_replay_btc.py --symbol ETHUSDT   # реплей по другой монете

Что делает. Идёт по дневкам символа срезами: на каждую дату детекторы
видят ТОЛЬКО бары до неё — как видели бы, живи прогон в тот день.
На каждый срез зовётся боевой detect_flow, результат пишется строкой:
дата, цена, победивший кейс, скор, вердикт.

Почему подменой источника, а не копией логики. Скрипт подменяет
detectors_flow.klines_1d / klines_1w на срезы заранее загруженной
истории и вызывает НЕИЗМЕНЁННЫЙ диспетчер: выбор победителя,
потолки, вето цикла, подтверждение вторым подкейсом — всё родное.
Скопируй мы логику в реплей — через месяц проверялось бы не то, что
торгуется, и расхождение никто бы не заметил.

ОГРАНИЧЕНИЯ, названные честно:
- Сетевые подкейсы выключены (allow_network=False): leverage в
  реплее не участвует — историю OI и фандинга на прошлые даты биржа
  не отдаёт. Реплей проверяет ценовые/объёмные фигуры.
- Недельки режутся по времени открытия бара: недозакрытая неделя на
  дату среза входит частично, как входила бы вживую.
- RunCache должен быть тёплым (обычный прогон уже сделал его таким);
  сам реплей сеть не трогает вовсе.

ИЗВЕСТНЫЕ ОТВЕТЫ, против которых читать выдачу (для BTCUSDT):
- Октябрь 2025, вершина 126 198: скринер обязан МОЛЧАТЬ или давать
  «цикл отработан» — раздача, за которой −43%. Сигнал входа здесь —
  дорогая ошибка.
- Июнь-июль 2026, дно 55–60 тыс.: накопление размечено независимо
  (белые пузыри, киты на $1.2 млрд) — здесь список обязан был монету
  ДЕРЖАТЬ. Молчание здесь — ошибка чувствительности.
Первая ошибка дороже второй: ложный вход стоит денег, поздний вход —
только части хода.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone

import detectors_flow as df
from core_binance import K_CLOSE, K_OPEN_TIME, klines_1d, klines_1w


def _fmt_day(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def replay(symbol: str, step: int, out_path: str) -> int:
    full_d = klines_1d(symbol)
    full_w = klines_1w(symbol)
    if not full_d or len(full_d) <= df.MIN_BARS:
        print(f"✗ дневок {len(full_d or [])} — меньше MIN_BARS={df.MIN_BARS}")
        return 1

    print(f"→ {symbol}: дневок {len(full_d)}, недель {len(full_w or [])}, "
          f"шаг {step}, окно от {df.MIN_BARS}")

    # Подмена источников. Атрибуты модуля, а не sys.modules: детекторы
    # берут klines_* из СВОЕГО пространства имён (from ... import), и
    # менять надо ровно там, где читают.
    orig_1d, orig_1w = df.klines_1d, df.klines_1w
    rows: list[dict] = []
    try:
        for i in range(df.MIN_BARS, len(full_d) + 1, step):
            cut_d = full_d[:i]
            asof_ms = float(cut_d[-1][K_OPEN_TIME])
            cut_w = [k for k in (full_w or [])
                     if float(k[K_OPEN_TIME]) <= asof_ms]

            df.klines_1d = lambda s, _c=cut_d: _c
            df.klines_1w = lambda s, _c=cut_w: _c

            try:
                sig = df.detect_flow(symbol, allow_network=False)
            except Exception as exc:  # одна дата не роняет реплей
                rows.append({"date": _fmt_day(asof_ms), "close": "",
                             "case": "ОШИБКА", "score": "",
                             "verdict": f"{type(exc).__name__}: {exc}",
                             "rejects": ""})
                continue

            close = float(cut_d[-1][K_CLOSE])
            rows.append({
                "date": _fmt_day(asof_ms),
                "close": f"{close:.0f}",
                # case по контракту FlowSignal равен "none" при
                # недетекте — в CSV это пустая ячейка, а не слово.
                "case": (sig.case if sig.detected and sig.case != "none"
                         else ""),
                "score": f"{sig.score:.0f}" if sig.detected else "",
                # Вердикт есть и у молчания: «цикл отработан» и
                # «мало данных» — разные молчания, и различать их
                # при чтении против известных ответов обязательно.
                "verdict": (sig.verdict or "")[:120],
                # Причины отказов — тем более: первый прогон показал,
                # что «почему молчал август-2026» из файла не
                # прочесть было вовсе. У сработавшего среза колонка
                # пуста — отказы там есть тоже, но читают их у
                # молчания.
                "rejects": ("" if sig.detected else "; ".join(
                    f"{k}={v}" for k, v in sorted(
                        (sig.rejects or {}).items()))[:200]),
            })
    finally:
        df.klines_1d, df.klines_1w = orig_1d, orig_1w

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["date", "close", "case",
                                          "score", "verdict", "rejects"])
        w.writeheader()
        w.writerows(rows)

    # ── Сводка по месяцам: где скринер говорил и что ──
    by_month: dict[str, dict] = {}
    for r in rows:
        m = r["date"][:7]
        d = by_month.setdefault(m, {"n": 0, "fired": 0, "cases": {}})
        d["n"] += 1
        if r["case"] and r["case"] != "ОШИБКА":
            d["fired"] += 1
            d["cases"][r["case"]] = d["cases"].get(r["case"], 0) + 1

    print(f"\n{'месяц':<9}{'срезов':>7}{'сигналов':>9}  кейсы")
    for m in sorted(by_month):
        d = by_month[m]
        cases = " ".join(f"{k}×{v}" for k, v in
                         sorted(d["cases"].items(), key=lambda x: -x[1]))
        print(f"{m:<9}{d['n']:>7}{d['fired']:>9}  {cases}")

    print(f"\n✓ построчно: {out_path} ({len(rows)} срезов)")
    print("Читать против известных ответов из шапки: октябрь-2025 — "
          "молчание/«цикл отработан», июнь-июль-2026 — сигнал набора.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Реплей FLOW срезами истории")
    p.add_argument("--symbol", default="BTCUSDT")
    p.add_argument("--step", type=int, default=3,
                   help="шаг среза в барах (днях), по умолчанию 3")
    p.add_argument("--out", default="",
                   help="путь CSV; по умолчанию flow_replay_<symbol>.csv")
    a = p.parse_args()
    out = a.out or f"flow_replay_{a.symbol.lower()}.csv"
    return replay(a.symbol.upper(), max(1, a.step), out)


if __name__ == "__main__":
    sys.exit(main())
