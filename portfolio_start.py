#!/usr/bin/env python3
"""Старт условного портфеля на текущем составе журнала.

Правила входа записываются в момент заведения записи, поэтому у
двадцати восьми монет, заведённых до этой правки, их нет. Скрипт
проставляет то, что восстановимо, и честно оставляет пустым то, что
нет.

ВОССТАНОВИМО. День недели входа — из first_seen. Правило «на выходных
не заходим, кроме плоского длительного дна» применяется задним
числом полностью: и дата, и фигура входа в записи есть.

НЕ ВОССТАНОВИМО. Первый разгон: `first_run` считается по контексту
падения на момент срабатывания, и каким он был девять дней назад,
из записи не следует. Подставлять догадку в метрику, которой потом
верить, нельзя, поэтому по этому правилу старые записи считаются
взятыми. Разойдётся оно с механическим вариантом на новых.

Про исключение для выходных. Условие «рост от дна не выше 50%» на
момент входа тоже не восстановимо — в записи лежит сегодняшний
up_x, а не тогдашний. Поэтому для dormant-записей, зашедших на
выходных, позиция считается взятой: правило требовало ДВУХ условий,
одно проверено, второе неизвестно, и отказ по неизвестному выбросил
бы монету без основания.

Запуск из корня проекта:
    python3 portfolio_start.py output/leaders.json
    python3 portfolio_start.py output/leaders.json --apply
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path


def plan(data: dict) -> tuple[dict, list[str]]:
    out = json.loads(json.dumps(data))          # глубокая копия
    report: list[str] = []

    for symbol, rec in out.items():
        if symbol.startswith("_") or not isinstance(rec, dict):
            continue
        if "skip" in rec:
            continue

        stamp = rec.get("first_seen")
        if not stamp:
            continue
        try:
            when = dt.datetime.fromisoformat(str(stamp))
        except (TypeError, ValueError):
            continue

        case = str(rec.get("entry_case") or "").replace("flow_", "")
        weekend = when.weekday() >= 5

        if weekend and case != "dormant":
            rec["skip"] = "выходные"
            report.append(
                f"  {symbol:16s} пропуск · {when.strftime('%a')} "
                f"{str(stamp)[:10]} · {case or '?'} · "
                f"{float(rec.get('change_pct') or 0):+.1f}%"
            )
        else:
            why = ("будни" if not weekend else "выходные, но dormant")
            report.append(
                f"  {symbol:16s} берём   · {why:20s} · {case or '?'} · "
                f"{float(rec.get('change_pct') or 0):+.1f}%"
            )

    return out, report


def summary(store: dict, stake: float = 1000.0) -> None:
    """Два варианта портфеля рядом — иначе непонятно, что дало правило."""
    inv = val = r_inv = r_val = 0.0
    skipped = 0
    for symbol, rec in store.items():
        if symbol.startswith("_") or not isinstance(rec, dict):
            continue
        try:
            e = float(rec.get("entry_price") or 0.0)
            chg = float(rec.get("change_pct") or 0.0)
        except (TypeError, ValueError):
            continue
        if e <= 0:
            continue
        inv += stake
        val += stake * (1 + chg / 100)
        if rec.get("skip"):
            skipped += 1
        else:
            r_inv += stake
            r_val += stake * (1 + chg / 100)

    if inv <= 0:
        return
    print(f"\n  механически:  ${val:,.0f} из ${inv:,.0f}  "
          f"{(val / inv - 1) * 100:+.1f}%")
    if r_inv > 0:
        print(f"  по правилам:  ${r_val:,.0f} из ${r_inv:,.0f}  "
              f"{(r_val / r_inv - 1) * 100:+.1f}%   пропущено {skipped}")
    else:
        print(f"  по правилам:  пропущены все {skipped}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default="output/leaders.json")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"нет файла: {path}")
        return 2

    data = json.loads(path.read_text(encoding="utf-8"))
    before = [k for k in data if not k.startswith("_")]
    out, report = plan(data)
    after = [k for k in out if not k.startswith("_")]

    lost = set(before) - set(after)
    if lost:
        print(f"ОСТАНОВ: пропали записи {sorted(lost)}")
        return 1
    # Меняется ровно одно поле. Проверка до записи, а не после.
    for sym in before:
        for field, val in data[sym].items():
            if field != "skip" and out[sym].get(field) != val:
                print(f"ОСТАНОВ: {sym}.{field} изменено сверх разрешённого")
                return 1

    print(f"монет: {len(after)}\n")
    for line in sorted(report):
        print(line)
    summary(out)

    if not args.apply:
        print("\nСухой прогон. Повторить с --apply.")
        return 0

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, path.with_suffix(f".json.bak-{stamp}"))
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    print(f"\nЗаписано. Резервная копия: {path.name}.bak-{stamp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
