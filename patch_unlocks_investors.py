#!/usr/bin/env python3
"""Перенос инвесторов YZi Labs в ручной unlocks.json (29.08.2026).

Запускать из каталога, где лежит unlocks.json. Делает резервную
копию unlocks.json.bak, затем ДОПИСЫВАЕТ строки в поле investors
девяти монетам журнала, найденным в портфеле YZi Labs (категория
CoinGecko, обе страницы, снято 29.08). Ничего не перезаписывает:
существующие investors дополняются только отсутствующими строками,
прочие поля записи не трогаются, отсутствующие в файле монеты
перечисляются отдельно — их каркас решает владелец. Дом инвесторов
один — этот файл; отдельный investors.json упразднён.
"""

import json
import shutil
from pathlib import Path

PATH = Path("unlocks.json")

ROWS = {
    "ENAUSDT":  "YZi Labs (экс Binance Labs) — портфель CG; "
                "сид-инвесторов выкупил фонд Ethena 27.08.2026",
    "ACEUSDT":  "YZi Labs — портфель CG (Fusionist)",
    "BICOUSDT": "YZi Labs — портфель CG (Biconomy)",
    "GPSUSDT":  "YZi Labs — портфель CG (GoPlus)",
    "LUNCUSDT": "YZi Labs — портфель CG (наследие Terra)",
    "MOVEUSDT": "YZi Labs — портфель CG (Movement)",
    "MOVRUSDT": "YZi Labs — портфель CG (Moonriver)",
    "SHELLUSDT": "YZi Labs — портфель CG (MyShell)",
    "TREEUSDT": "YZi Labs — портфель CG (Treehouse)",
}


def main() -> None:
    if not PATH.exists():
        raise SystemExit("unlocks.json не найден — запускать рядом с ним")
    shutil.copy2(PATH, PATH.with_suffix(".json.bak"))
    data = json.loads(PATH.read_text(encoding="utf-8"))

    added, extended, absent = [], [], []
    for key, row in ROWS.items():
        rec = data.get(key)
        if rec is None:
            absent.append(key)
            continue
        inv = rec.setdefault("investors", [])
        if any("YZi" in str(x) for x in inv):
            continue                      # уже отмечен — не дублируем
        inv.append(row)
        (extended if len(inv) > 1 else added).append(key)

    PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    print(f"внесено новых: {len(added)} {added}")
    print(f"дополнено существующих: {len(extended)} {extended}")
    if absent:
        print(f"нет в файле (каркас за владельцем): {absent}")
    print("резервная копия: unlocks.json.bak")


if __name__ == "__main__":
    main()
