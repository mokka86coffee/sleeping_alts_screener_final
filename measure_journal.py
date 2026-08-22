"""Замеры по каталогу снимков: Р-23, Р-16, Р-22. Нулевой шаг порядка работ.

Запуск (из каталога проекта):
    python measure_journal.py                  # снимки в output/snapshots
    python measure_journal.py --dir path/to/snapshots
    python measure_journal.py --move 40        # порог «монета поехала», %

Что считает.

Р-23 «сигнал → ход»: для каждой монеты, которая после появления в
топе FLOW сделала ход не меньше порога, — сколько дней прошло от
ПОСЛЕДНЕГО сигнала до старта хода. Распределение сверяется со сроком
журнала LEADERS_MAX_AGE_DAYS: доля случаев, где запись выпала бы до
повода. Реплей по BTC дал один такой случай (29 дней при сроке 26,
выпадение за три дня до хода); здесь считается распределение.

Р-16 «пропущенные против взятых»: если рядом лежит decisions.json,
монеты делятся на взятые (действие «вход») и показанные-без-входа, и
сравнивается их ход за одинаковое окно от появления. Мера
ОТНОСИТЕЛЬНАЯ (Р-5): из хода монеты вычитается медианный ход всей
выборки за то же окно — иначе в дни прилива обе группы поедут, и
разница окажется шумом прилива.

Р-22 «в списке до повода»: для каждой поехавшей монеты — стояла ли
она в топе ДО старта хода, и за сколько дней. Доля «да» и есть
качество отбора, очищенное от решений человека и удачи.

Форматы снимков. Новые (с 22.08) несут блок nums с числами; старые
хранят цену и ходы только в экранных строках metrics — парсятся и
они, но парсер вёрстки хрупок по построению, о чём напоминает
предупреждение при первом же снимке без nums.

Все определения — в одном месте, чтобы спор о результате был спором
о правиле, а не о реализации:
- «в топе» = flow не пуст (сработал детектор семейства);
- «поехала» = максимум цены в последующих снимках превысил цену
  первого появления на порог --move (по умолчанию 40%);
- «старт хода» = первый снимок, где цена выше цены появления на
  четверть порога — начало движения, а не его вершина.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
import sys
from datetime import datetime
from pathlib import Path

try:
    from core_config import LEADERS_MAX_AGE_DAYS
except Exception:                      # запуск вне проекта
    LEADERS_MAX_AGE_DAYS = 26

# Каталог снимков — из конфига проекта, той же константой, которой
# пишет save_snapshot. Прежний дефолт "output/snapshots" был догадкой
# и не совпадал с реальностью. Дневной архив (RUNS_DIR/daily, один
# снимок в день, вне ротации prune_runs) предпочитается рабочему
# каталогу: рабочий держит лишь последние RUNS_KEEP прогонов.
try:
    from core_config import RUNS_DIR as _RUNS_DIR
    _daily = _RUNS_DIR / "daily"
    DEFAULT_DIR = str(_daily if _daily.is_dir() else _RUNS_DIR)
except Exception:
    DEFAULT_DIR = "output/runs"

PCT_RE = re.compile(r"([+-]?\d+(?:\.\d+)?)\s*%")
PRICE_RE = re.compile(r"\$?\s*([\d_]+(?:\.\d+)?)")

_warned_legacy = False


def _row(c: dict) -> dict | None:
    """Символ, цена и признак топа из кандидата снимка, оба формата."""
    global _warned_legacy
    sym = c.get("symbol")
    if not sym:
        return None
    nums = c.get("nums") or {}
    price = nums.get("price")
    if price is None:
        # Старый формат: цена в экранной строке. Хрупко по построению.
        if not _warned_legacy:
            print("⚠ снимок без блока nums — читаю цены из экранных "
                  "строк metrics; смена подписи сломает ретроспективу")
            _warned_legacy = True
        for m in (c.get("metrics") or []):
            if isinstance(m, dict) and m.get("key") == "Цена":
                pm = PRICE_RE.search(str(m.get("val", "")))
                if pm:
                    price = float(pm.group(1).replace("_", ""))
                break
    if not price or price <= 0:
        return None
    return {"sym": sym, "price": float(price),
            "in_top": bool(c.get("flow"))}


def load_snapshots(folder: Path) -> list[dict]:
    """Снимки каталога, отсортированные по времени. Каждый — дата и
    словарь монет. Битые файлы пропускаются с перечислением в конце:
    молчаливый пропуск превратил бы дыру в данных в «так и было»."""
    out, broken = [], []
    for p in sorted(folder.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            ts = datetime.fromisoformat(str(d["timestamp"]))
            coins = {}
            for c in d.get("candidates") or []:
                r = _row(c)
                if r:
                    coins[r["sym"]] = r
            if coins:
                out.append({"ts": ts, "coins": coins, "file": p.name})
        except Exception as exc:
            broken.append(f"{p.name}: {type(exc).__name__}")
    if broken:
        print(f"⚠ пропущено битых снимков: {len(broken)} "
              f"({'; '.join(broken[:3])}{'…' if len(broken) > 3 else ''})")
    out.sort(key=lambda s: s["ts"])
    return out


def daily(snaps: list[dict]) -> list[dict]:
    """Один снимок на календарный день — последний. Прогоны идут
    каждые ~3 часа, а разрешение всех трёх замеров — дни; восемь точек
    в дне только шумят статистикой «дней до»."""
    by_day: dict[str, dict] = {}
    for s in snaps:
        by_day[s["ts"].strftime("%Y-%m-%d")] = s
    return [by_day[k] for k in sorted(by_day)]


def measure(snaps: list[dict], move_pct: float, decisions: list[dict]):
    days = daily(snaps)
    if len(days) < 5:
        print(f"✗ дней со снимками: {len(days)} — распределение не из "
              "чего строить (нужно хотя бы ~2 недели)")
        return None

    # ── история каждой монеты ──
    hist: dict[str, list] = {}
    for i, s in enumerate(days):
        for sym, r in s["coins"].items():
            hist.setdefault(sym, []).append(
                (i, s["ts"], r["price"], r["in_top"]))

    # медианный ход выборки день-к-первому — знаменатель Р-5
    base_day = 0
    med_path: dict[int, float] = {}
    for i in range(len(days)):
        moves = []
        for sym, rows in hist.items():
            d = {j: p for j, _, p, _ in rows}
            if base_day in d and i in d and d[base_day] > 0:
                moves.append(d[i] / d[base_day] - 1)
        med_path[i] = statistics.median(moves) if moves else 0.0

    start_frac = 1 + move_pct / 400.0      # четверть порога — старт хода
    full_frac = 1 + move_pct / 100.0

    p23, p22, rows_csv = [], [], []
    for sym, rows in hist.items():
        tops = [(i, ts) for i, ts, _, in_top in rows if in_top]
        prices = {i: p for i, _, p, _ in rows}
        if not prices:
            continue
        first_i = rows[0][0]
        first_p = prices[first_i]
        peak_i, peak_p = max(prices.items(), key=lambda kv: kv[1])
        if peak_p < first_p * full_frac or peak_i <= first_i:
            continue                        # не поехала — не наш случай
        # старт хода: первый день выше четверти порога
        start_i = next((i for i in sorted(prices)
                        if i > first_i and prices[i] >= first_p * start_frac),
                       peak_i)
        move_day = days[start_i]["ts"]
        # Р-22: стояла ли в топе ДО старта
        before = [t for t in tops if t[0] < start_i]
        p22.append((sym, bool(before),
                    (move_day - before[-1][1]).days if before else None))
        # Р-23: от ПОСЛЕДНЕГО сигнала до старта
        if before:
            gap = (move_day - before[-1][1]).days
            p23.append((sym, gap))
            rows_csv.append({
                "symbol": sym, "signal_last": before[-1][1].date(),
                "move_start": move_day.date(), "gap_days": gap,
                "move_pct": round((peak_p / first_p - 1) * 100),
            })

    # ── Р-16: взятые против пропущенных, относительной мерой ──
    p16 = None
    if decisions:
        taken = {str(d.get("symbol", "")).upper()
                 for d in decisions if d.get("action") == "вход"}
        shown = {sym for sym, rows in hist.items()
                 if any(t for _, _, _, t in rows)}
        WINDOW = 14                          # дней от появления
        def rel_move(sym: str) -> float | None:
            rows = hist.get(sym) or []
            if not rows:
                return None
            d = {i: p for i, _, p, _ in rows}
            i0 = rows[0][0]
            i1 = min(i0 + WINDOW, max(d))
            if i0 not in d or i1 not in d or d[i0] <= 0 or i1 <= i0:
                return None
            raw = d[i1] / d[i0] - 1
            base = med_path.get(i1, 0.0) - med_path.get(i0, 0.0)
            return (raw - base) * 100
        g_taken = [v for s in (shown & taken)
                   if (v := rel_move(s)) is not None]
        g_missed = [v for s in (shown - taken)
                    if (v := rel_move(s)) is not None]
        if g_taken and g_missed:
            p16 = (statistics.median(g_taken), len(g_taken),
                   statistics.median(g_missed), len(g_missed), WINDOW)

    return days, p23, p22, p16, rows_csv


def main() -> int:
    ap = argparse.ArgumentParser(description="Замеры Р-23/Р-16/Р-22 по снимкам")
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--move", type=float, default=40.0,
                    help="порог «монета поехала», %% (по умолчанию 40)")
    ap.add_argument("--decisions", default="output/decisions.json")
    a = ap.parse_args()

    folder = Path(a.dir)
    if not folder.is_dir():
        print(f"✗ каталога {folder} нет")
        return 1
    snaps = load_snapshots(folder)
    print(f"→ снимков прочитано: {len(snaps)}")
    try:
        decisions = json.loads(Path(a.decisions).read_text(encoding="utf-8"))
    except Exception:
        decisions = []

    res = measure(snaps, a.move, decisions)
    if res is None:
        return 1
    days, p23, p22, p16, rows_csv = res
    span = (days[-1]["ts"] - days[0]["ts"]).days
    print(f"→ дней: {len(days)} ({days[0]['ts'].date()} — "
          f"{days[-1]['ts'].date()}, охват {span} дн), порог хода "
          f"{a.move:.0f}%\n")

    # ── Р-22 ──
    yes = sum(1 for _, ok, _ in p22 if ok)
    if p22:
        print(f"Р-22 «в списке до повода»: {yes} из {len(p22)} поехавших "
              f"стояли в топе до старта — {yes * 100 // len(p22)}%")
        lead = [d for _, ok, d in p22 if ok and d is not None]
        if lead:
            print(f"   упреждение (последний сигнал → старт): медиана "
                  f"{statistics.median(lead):.0f} дн, макс {max(lead)} дн")
    else:
        print("Р-22: поехавших монет в охвате нет — либо порог высок, "
              "либо охват короток")

    # ── Р-23 ──
    if p23:
        gaps = sorted(g for _, g in p23)
        late = sum(1 for g in gaps if g > LEADERS_MAX_AGE_DAYS)
        print(f"\nР-23 «сигнал → ход» против срока {LEADERS_MAX_AGE_DAYS} дн:")
        # Индекс перцентиля от len−1, не от len: на двух точках
        # int(n*0.9)−1 давал нулевой индекс и p90 ниже медианы.
        p90 = gaps[min(len(gaps) - 1, round(0.9 * (len(gaps) - 1)))]
        print(f"   случаев: {len(gaps)} | медиана "
              f"{statistics.median(gaps):.0f} дн | p90 {p90} дн")
        print(f"   ВЫПАЛИ БЫ из журнала до хода: {late} "
              f"({late * 100 // len(gaps)}%)")
        step = 7
        for lo in range(0, (max(gaps) // step + 1) * step, step):
            n = sum(1 for g in gaps if lo <= g < lo + step)
            print(f"   {lo:>3}–{lo + step - 1:<3} дн  {'█' * n}{n and '' or ''} {n or ''}")
    else:
        print("\nР-23: ни одного случая «сигнал до хода» — см. Р-22 выше")

    # ── Р-16 ──
    if p16:
        mt, nt, mm, nm, w = p16
        print(f"\nР-16 взятые против пропущенных (окно {w} дн, "
              f"относительно медианы выборки, Р-5):")
        print(f"   взятые:      медиана {mt:+.1f}% ({nt} шт)")
        print(f"   пропущенные: медиана {mm:+.1f}% ({nm} шт)")
        print("   " + ("пропущенные ходили ЛУЧШЕ — чинить решение о входе,"
                       " не поиск" if mm > mt else
                       "взятые не хуже пропущенных — решение о входе не"
                       " ухудшает отбор"))
    else:
        print("\nР-16: нет журнала решений с входами (decisions.json) — "
              "группы сравнивать не из чего")

    if rows_csv:
        out = "measure_journal.csv"
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(rows_csv[0]))
            w.writeheader()
            w.writerows(sorted(rows_csv, key=lambda r: -r["gap_days"]))
        print(f"\n✓ построчно: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
