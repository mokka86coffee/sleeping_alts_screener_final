#!/usr/bin/env python3
"""ПЕРЕВОД СТАРЫХ ЗАПИСЕЙ В UTC ПО ДАННЫМ, БЕЗ КОНСТАНТ (16.09, владелец: «никакой привязки ко времени машины
и к константам; время берём в UTC, вычисляем из машинных данных, на экран — только местное»).

До 16.09 журнал прогнозов (output/forecasts.jsonl) писал at + hm по часам компьютера, а пояс компьютера
менялся (страны, командировки, другой компьютер или сервер). Сдвиг записи не угадывается и не берётся из
настроек — он ВЫЧИСЛЯЕТСЯ. Строки одного прогона (одно at + hm) несут цены монет из пульса, а архив
получасовок (cq_v2/intraday и дневные файлы cq_v2/archive) хранит цены того же пульса с меткой свечи в UTC.
Сдвиг прогона — тот, при котором цены прогона совпадают с ценами архива на свече этого прогона.

  • совпало — строки получают tz=UTC, время в UTC и tz_src (чем подтверждено);
  • архива на это время нет — сдвиг берётся у соседних подтверждённых прогонов в файле, если соседи
    согласны между собой (пояс машины между соседними прогонами не меняется), tz_src — «соседи»;
  • не подтверждается ничем — tz=unknown: строка остаётся в файле (факты не удаляются), в расчёты по
    времени не идёт.
Копия файла до перевода — рядом (.pre_utc). Повторный запуск ничего не меняет: помеченные строки не трогаются.

Вызывается журналом прогнозов под его замком перед каждой записью — сам, без участия человека.
Руками: `python3 utc_migrate.py` — отчёт без записи; `--apply` — записать.
"""
from __future__ import annotations

import argparse
import gzip
import json
import shutil
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

UTC = timezone.utc
HALF = 1800
STEP = 900                      # поясной сдвиг кратен 15 минутам
OFFSETS = range(-12 * 4, 14 * 4 + 1)   # от UTC−12 до UTC+14, в четвертях часа


def _read(path: Path) -> list[dict]:
    out = []
    if not path.exists():
        return out
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return out


def _candle_s(c) -> int | None:
    try:
        return int(datetime.strptime(str(c), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp())
    except ValueError:
        return None


def price_index(syms: set[str], base: Path = BASE_DIR) -> dict:
    """(монета без USDT, начало свечи в секундах UTC) → цена, из живого архива и дневных файлов"""
    idx: dict = {}

    def put(sym, r):
        t = _candle_s(r.get("candle"))
        px = r.get("px")
        if t is not None and isinstance(px, (int, float)) and px:
            idx[(sym, t)] = float(px)

    live = base / "cq_v2" / "intraday"
    for s in syms:
        p = live / f"{s.lower()}.jsonl"
        if p.exists():
            for r in _read(p):
                put(s, r)
    arch = base / "cq_v2" / "archive"
    if arch.exists():
        for p in sorted(arch.glob("**/*.jsonl.gz")):
            if "depth" in p.parts:
                continue
            try:
                with gzip.open(p, "rt", encoding="utf-8") as f:
                    for ln in f:
                        try:
                            r = json.loads(ln)
                        except ValueError:
                            continue
                        s = str(r.get("sym") or "").upper().replace("USDT", "")
                        if s in syms:
                            put(s, r)
            except OSError:
                continue
    return idx


def _naive_s(at, hm) -> int | None:
    try:
        return int(datetime.strptime(f"{at} {hm or '00:00'}", "%Y-%m-%d %H:%M").replace(tzinfo=UTC).timestamp())
    except (TypeError, ValueError):
        return None


def _prefer(k: int) -> int:
    """при равном числе совпадений — целый час, потом полчаса, потом четверть (так устроены пояса мира)"""
    return 0 if k % 4 == 0 else (1 if k % 2 == 0 else 2)


def infer(groups: "OrderedDict", idx: dict) -> dict:
    """(at, hm) → (сдвиг в четвертях часа, источник) или None"""
    out: dict = {}
    for key, rows in groups.items():
        s0 = _naive_s(*key)
        pxs = {str(r.get("sym") or "").upper().replace("USDT", ""): float(r["px"])
               for r in rows if isinstance(r.get("px"), (int, float)) and r.get("px")}
        if s0 is None or not pxs:
            out[key] = None
            continue
        score = {}
        for k in OFFSETS:
            u = s0 - k * STEP                      # время записи в UTC при таком сдвиге
            # свеча прогона — последняя закрытая к моменту записи: запись идёт через 0–30 минут после
            # закрытия, поэтому соседние сдвиги на полчаса попадают в ДРУГУЮ свечу и не совпадают
            c1 = (u // HALF) * HALF - HALF
            hit = seen = 0
            for s, px in pxs.items():
                x = idx.get((s, c1))
                if not x:
                    continue
                seen += 1
                if abs(x / px - 1) < 1e-9:
                    hit += 1
            if hit:
                score[k] = (hit, seen)
        if not score:
            out[key] = None
            continue
        best = max(score.values(), key=lambda v: v[0])[0]
        tied = [k for k, v in score.items() if v[0] == best]
        k = min(tied, key=lambda x: (_prefer(x), abs(x)))
        seen = score[k][1]
        # запасные сдвиги с тем же числом совпадений допускаются только соседние (±15 мин — те же свечи)
        far = [x for x in tied if abs(x - k) > 1]
        if best >= max(3, 0.5 * seen) and not far:
            out[key] = (k, f"цены архива: {best} из {seen}")
        else:
            out[key] = None
    return out


def fill_by_neighbours(keys: list, found: dict) -> dict:
    """пустые — по соседним подтверждённым прогонам, если соседи слева и справа согласны"""
    res = dict(found)
    conf = [i for i, k in enumerate(keys) if found.get(k)]
    for i, k in enumerate(keys):
        if found.get(k):
            continue
        left = max((j for j in conf if j < i), default=None)
        right = min((j for j in conf if j > i), default=None)
        kl = found[keys[left]][0] if left is not None else None
        kr = found[keys[right]][0] if right is not None else None
        if kl is not None and kr is not None and kl == kr:
            res[k] = (kl, "соседи")
        elif kl is not None and kr is None:
            res[k] = (kl, "сосед слева")
        elif kr is not None and kl is None:
            res[k] = (kr, "сосед справа")
        else:
            res[k] = None
    return res


def migrate_rows(rows: list[dict], base: Path = BASE_DIR) -> Counter:
    """перевести строки без пометки на месте; вернуть счётчик: переведено / соседи / неизвестно / дозабор"""
    stat: Counter = Counter()
    groups: OrderedDict = OrderedDict()
    for r in rows:
        if not isinstance(r, dict):
            continue
        tz = str(r.get("tz") or "")
        if tz.upper() == "UTC" or tz == "unknown":
            continue
        if r.get("backfill"):                       # дозабор всегда писал UTC — только пометка
            r["tz"] = "UTC"
            stat["дозабор"] += 1
            continue
        groups.setdefault((r.get("at"), r.get("hm")), []).append(r)
    if not groups:
        return stat
    syms = {str(r.get("sym") or "").upper().replace("USDT", "") for g in groups.values() for r in g}
    found = infer(groups, price_index(syms, base))
    keys = list(groups)
    final = fill_by_neighbours(keys, found)
    for key, rows_g in groups.items():
        v = final.get(key)
        if not v:
            for r in rows_g:
                r["tz"] = "unknown"
            stat["неизвестно"] += len(rows_g)
            continue
        k, src = v
        s0 = _naive_s(*key)
        d = datetime.fromtimestamp(s0 - k * STEP, UTC)
        off = f"{'+' if k >= 0 else '−'}{abs(k) // 4}:{abs(k) % 4 * 15:02d}"
        for r in rows_g:
            r["at"], r["hm"], r["tz"] = d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), "UTC"
            r["tz_src"] = f"машина была UTC{off} · {src}"
        stat["соседи" if src.startswith("сосед") else "по ценам"] += len(rows_g)
        stat[f"UTC{off}"] += len(rows_g)
    return stat


def migrate_file(path: Path, rows: list[dict] | None = None, apply: bool = True,
                 write=None, base: Path = BASE_DIR) -> Counter:
    """перевести файл; копия до первой правки — рядом (.pre_utc); write — функция записи владельца файла"""
    rows = _read(path) if rows is None else rows
    stat = migrate_rows(rows, base)
    changed = sum(v for k, v in stat.items() if k in ("по ценам", "соседи", "неизвестно", "дозабор"))
    if apply and changed:
        bak = path.with_name(path.name + ".pre_utc")
        if path.exists() and not bak.exists():
            shutil.copy2(path, bak)
        if write:
            write(path, rows)
        else:
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8")
            tmp.replace(path)
    return stat


def main() -> int:
    ap = argparse.ArgumentParser(description="перевод старых строк журнала прогнозов в UTC по данным")
    ap.add_argument("--apply", action="store_true", help="записать (без ключа — только отчёт)")
    ap.add_argument("--path", default=str(BASE_DIR / "output" / "forecasts.jsonl"))
    a = ap.parse_args()
    p = Path(a.path)
    if a.apply:
        from core_lock import locked
        with locked(p):
            stat = migrate_file(p, apply=True)
    else:
        stat = migrate_file(p, apply=False)
    if not stat:
        print("строк без пометки нет — переводить нечего")
        return 0
    print(" · ".join(f"{k} {v}" for k, v in stat.most_common()))
    print("записано, копия до перевода — рядом (.pre_utc)" if a.apply else "это отчёт; записать — с ключом --apply")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
