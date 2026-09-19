"""ЛАБОРАТОРИЯ СТОРОНЫ (19.09, владелец: «это чисто твои наблюдения по истории и только твоя реализация»).

Наблюдение по журналам paper_crowd и paper_end за 16–19.09: из 357 закрытых у «толпы» 343 шорта на −143% и
14 лонгов на +19.5%; «конец» — 22 шорта, −33%. Три дня бот шортил рынок, в котором биткоин шёл с 75 на 80 и
жгли шортов в десятки раз к норме. Правила не плохие — сторона против фона.

Что прогоняется на тех же сделках, ничего не меняя в них:
  1. СТОРОНА ОТ ФОНА: шорт открывается только когда по биткоину сожгли лонгов больше, чем шортов; лонг — наоборот.
     Фон берётся по бару входа из cq_v2/intraday/btc.jsonl (liq24 — ликвидации за сутки по сторонам).
  2. ДВА ПРАВИЛА ВЫКЛЮЧЕНЫ: «рост на выносе» (0 из 9) и «спайк на выносе» — оба шортят ход лидера в первый час.
  3. ПОТОЛОК ПО МОНЕТЕ: два стопа по монете за день — монета до следующего дня закрыта (AVA взята 22 раза).

Печатает: было / стало по каждому шагу и вместе, по книгам и по дням. Ничего не устанавливает.
    python3 lab_side.py
"""
from __future__ import annotations

import json
import statistics as st
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import SIDE_LIQ_RATIO, SIDE_STOPS_PER_DAY, SIDE_RULES_OFF
except ImportError:
    SIDE_LIQ_RATIO = 1.5              # сожгли одной стороны больше другой во столько раз — фон задаёт сторону
    SIDE_STOPS_PER_DAY = 2            # столько стопов по монете за день — монета закрыта до завтра
    SIDE_RULES_OFF = ("рост на выносе", "спайк на выносе")

BOOKS = ("paper_crowd", "paper_end")


def _load(name: str) -> list[dict]:
    out = []
    for p in (BASE_DIR / "output" / f"{name}.jsonl", BASE_DIR / f"{name}.jsonl", Path("output") / f"{name}.jsonl", Path(f"{name}.jsonl")):
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    return out


def _btc() -> list[tuple[int, float, float]]:
    """бары биткоина: (t_ms, сожжено шортов за сутки, сожжено лонгов за сутки)"""
    for p in (BASE_DIR / "cq_v2" / "intraday" / "btc.jsonl", Path("cq_v2") / "intraday" / "btc.jsonl"):
        if not p.exists():
            continue
        rows = []
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            liq = r.get("liq24") or {}
            if r.get("candle") and liq.get("short") is not None and liq.get("long") is not None:
                t = int(datetime.fromisoformat(r["candle"].replace("Z", "+00:00")).timestamp() * 1000)
                rows.append((t, float(liq["short"]), float(liq["long"])))
        rows.sort()
        return rows
    return []


def side_of_bg(btc: list, t_ms: int) -> int:
    """+1 — фон за лонги (жгут шортов), −1 — за шорты (жгут лонгов), 0 — ровно; берётся последний бар до входа"""
    row = None
    for b in btc:
        if b[0] <= t_ms:
            row = b
        else:
            break
    if not row:
        return 0
    s, l = row[1], row[2]
    if s >= SIDE_LIQ_RATIO * max(l, 1):
        return +1
    if l >= SIDE_LIQ_RATIO * max(s, 1):
        return -1
    return 0


def main() -> None:
    btc = _btc()
    if not btc:
        print("нет cq_v2/intraday/btc.jsonl — сторону фона восстановить не из чего")
        return
    print(f"бары биткоина: {len(btc)} · {datetime.fromtimestamp(btc[0][0] / 1000, timezone.utc):%d.%m %H:%M} — {datetime.fromtimestamp(btc[-1][0] / 1000, timezone.utc):%d.%m %H:%M} UTC\n")
    total = defaultdict(lambda: defaultdict(float))
    counts = defaultdict(lambda: defaultdict(int))
    for book in BOOKS:
        rows = _load(book)
        closed = [r for r in rows if r.get("kind") == "follow" and r.get("result_pct") is not None and r.get("side")]
        closed.sort(key=lambda r: r.get("opened_at") or r["at"])
        stops_day: dict = defaultdict(int)
        print(f"── {book}: закрытых {len(closed)}")
        print("  вариант                                N     сумма    медиана   попаданий")
        variants = {"как было": [], "1 · сторона от фона": [], "2 · без двух правил": [], "3 · потолок по монете": [], "1+2+3 вместе": []}
        for r in closed:
            t_ms = int((r.get("opened_at") or r["at"]) * 1000)
            bg = side_of_bg(btc, t_ms)
            rule = str(r.get("rule") or "")
            day = datetime.fromtimestamp(t_ms / 1000, timezone.utc).strftime("%d.%m")
            key = (r.get("sym"), day)
            stopped = str(r.get("why_exit") or "").startswith("стоп")
            cap_ok = stops_day[key] < SIDE_STOPS_PER_DAY
            side_ok = (bg == 0) or (bg == r["side"])
            rule_ok = not any(rule.startswith(x) for x in SIDE_RULES_OFF)
            res = float(r["result_pct"])
            variants["как было"].append(res)
            if side_ok:
                variants["1 · сторона от фона"].append(res)
            if rule_ok:
                variants["2 · без двух правил"].append(res)
            if cap_ok:
                variants["3 · потолок по монете"].append(res)
            if side_ok and rule_ok and cap_ok:
                variants["1+2+3 вместе"].append(res)
            if stopped:
                stops_day[key] += 1
        for name, v in variants.items():
            if not v:
                print(f"  {name:38s}{0:5d}   сделок нет")
                continue
            hit = sum(1 for x in v if x > 0) / len(v) * 100
            print(f"  {name:38s}{len(v):5d} {sum(v):9.1f}% {st.median(v):8.2f}% {hit:9.0f}%")
            total[name]["sum"] += sum(v); counts[name]["n"] += len(v); counts[name]["hit"] += sum(1 for x in v if x > 0)
        # сторона против фона: сколько сделок было ПРОТИВ и сколько они стоили
        against = [float(r["result_pct"]) for r in closed if side_of_bg(btc, int((r.get("opened_at") or r["at"]) * 1000)) not in (0, r["side"])]
        print(f"  сделок против фона: {len(against)} · их итог {sum(against):.1f}%\n")
    print("── ОБЕ КНИГИ")
    for name in ("как было", "1 · сторона от фона", "2 · без двух правил", "3 · потолок по монете", "1+2+3 вместе"):
        n = counts[name]["n"]
        if n:
            print(f"  {name:38s}{n:5d} {total[name]['sum']:9.1f}%   попаданий {counts[name]['hit'] / n * 100:.0f}%")


if __name__ == "__main__":
    main()
