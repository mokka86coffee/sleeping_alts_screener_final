#!/usr/bin/env python3
"""АРХИВ ВНУТРИДНЕВНЫХ РЯДОВ (16.09, владелец: «давай intraday архивировать, а то квант только дневки
отдаёт, а всё, что было за день, ниоткуда не взять»).

Что восстановимо задним числом, а что нет:
  • ЦЕНА внутри дня — восстановима всегда (Binance отдаёт получасовки за месяцы назад), беречь не нужно;
  • ИНТЕРЕС, ФАНДИНГ, ТЕЙКЕР, ДЕЛЬТА, ЛИКВИДАЦИИ по альтам — НЕ восстановимы: Coinglass на тарифе
    Startup отдаёт короткое окно, CryptoQuant по альтам не даёт вовсе;
  • СТАКАН (стены) — не восстановим ни у кого.
Поэтому архивируем ровно cq_v2/intraday и cq_v2/depth — то, что исчезнет навсегда.

Раз в сутки складывает ЗАКРЫТЫЕ дни в cq_v2/archive/<ГГГГ-ММ>/<ГГГГ-ММ-ДД>.jsonl.gz — по одному файлу
на день, все монеты вместе, строка как в источнике плюс поле sym. Сегодняшний день не трогает.
Из живых файлов строки старше ARCHIVE_KEEP_DAYS суток удаляются — иначе они растут без предела;
всё удалённое уже лежит в архиве. Ничего не удаляется, пока архив за этот день не записан и не прочитан
обратно (проверка чтением).

`python3 archive_intraday.py` — показать, что будет сделано; `--write` — сделать; `--keep 5` — своё окно.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import ARCHIVE_KEEP_DAYS
except ImportError:
    ARCHIVE_KEEP_DAYS = 4

SRC = (("intraday", "candle"), ("depth", "t"))
ARCH = BASE_DIR / "cq_v2" / "archive"


def _day_of(row: dict, field: str) -> str | None:
    v = row.get(field)
    if v is None:
        return None
    try:
        if isinstance(v, (int, float)):                     # depth: миллисекунды
            return datetime.fromtimestamp(float(v) / 1000, timezone.utc).strftime("%Y-%m-%d")
        return str(v)[:10]                                   # intraday: ISO-строка
    except (TypeError, ValueError, OSError):
        return None


def collect(kind: str, field: str) -> dict:
    """день → список строк (с добавленным sym); и карта файл → строки, чтобы потом подрезать"""
    base = BASE_DIR / "cq_v2" / kind
    by_day: dict[str, list] = defaultdict(list)
    per_file: dict[Path, list] = {}
    for p in sorted(base.glob("*.jsonl")):
        sym = p.stem.upper() + "USDT"
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows.append(r)
            d = _day_of(r, field)
            if d:
                by_day[d].append(dict(r, sym=r.get("sym") or sym))
        per_file[p] = rows
    return {"by_day": by_day, "per_file": per_file, "field": field, "kind": kind}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--keep", type=int, default=ARCHIVE_KEEP_DAYS, help="сколько последних суток оставлять в живых файлах")
    a = ap.parse_args()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    total_rows = total_days = 0
    for kind, field in SRC:
        base = BASE_DIR / "cq_v2" / kind
        if not base.exists():
            print(f"{kind}: папки нет — пропускаю")
            continue
        got = collect(kind, field)
        days = sorted(d for d in got["by_day"] if d < today)          # сегодняшний день не архивируем
        if not days:
            print(f"{kind}: закрытых дней нет")
            continue
        for d in days:
            rows = got["by_day"][d]
            out = ARCH / kind / d[:7] / f"{d}.jsonl.gz"
            if out.exists():
                continue
            print(f"{kind}: {d} — {len(rows)} строк → {out.relative_to(BASE_DIR)}")
            total_rows += len(rows)
            total_days += 1
            if not a.write:
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            tmp = out.with_suffix(".tmp")
            with gzip.open(tmp, "wt", encoding="utf-8") as f:
                for r in sorted(rows, key=lambda x: (str(x.get("sym") or ""), str(x.get(field) or ""))):
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            # проверка чтением: архив открывается и строки на месте
            n = sum(1 for _ in gzip.open(tmp, "rt", encoding="utf-8"))
            if n != len(rows):
                tmp.unlink(missing_ok=True)
                print(f"   ✗ архив за {d} не сошёлся: записано {n} из {len(rows)} — живые файлы не трогаю")
                continue
            tmp.replace(out)
        # подрезка живых файлов: оставляем последние --keep суток
        if a.write:
            keep_from = sorted(set(list(got["by_day"].keys()) + [today]))[-max(1, a.keep):][0]
            cut = 0
            for p, rows in got["per_file"].items():
                left = [r for r in rows if (_day_of(r, field) or today) >= keep_from]
                if len(left) == len(rows):
                    continue
                archived = all((ARCH / kind / (_day_of(r, field) or today)[:7] /
                                f"{_day_of(r, field)}.jsonl.gz").exists()
                               for r in rows if (_day_of(r, field) or today) < keep_from)
                if not archived:
                    continue                                   # без архива не режем
                tmp = p.with_suffix(".tmp")
                tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in left), encoding="utf-8")
                tmp.replace(p)
                cut += len(rows) - len(left)
            if cut:
                print(f"{kind}: из живых файлов убрано {cut} строк старше {keep_from} — они в архиве")
    if not a.write:
        print(f"\nбудет заархивировано дней {total_days}, строк {total_rows} · запуск с --write, чтобы сделать")
    else:
        print(f"\nархив: дней {total_days}, строк {total_rows} · {ARCH.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
