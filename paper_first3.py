#!/usr/bin/env python3
"""БУМАЖНАЯ КНИГА «3 В ПЕРВЫХ ПОДРЯД» (24.09, владелец: «бери монеты только из звёзд, которые три раза подряд первые:
как только монета становится первой третий раз подряд — входим на 500 $ и держим»; уточнения того же дня: выход +40%,
после +20% стоп в точку входа, повторный вход не раньше 48 часов при тех же условиях).

Правила (числа в core_config, FIRST3_*):
  • вход — монета первая в очереди (output/queue_log.jsonl, place == 1) FIRST3_STREAK получасовок подряд; лонг на
    FIRST3_SIZE $ по живой цене Binance в момент прогона;
  • выход — цена коснулась +FIRST3_TARGET (лимитка, по максимуму трёхминутки);
  • коснулась +FIRST3_BE — со следующей трёхминутки стоп в точку входа (выход в ноль); до этого стопа нет, срока нет;
  • не больше FIRST3_MAX_OPEN сделок сразу (размер = депозит / слоты), срок FIRST3_HOLD_H ч — по нему выход по цене
    (26.09, claude/research/first3_money.py: без срока капитал сидит в минусовых, стоп до +20% режет итог);
  • одна позиция на монету; после выхода по ней — не раньше FIRST3_PAUSE_H часов и только на новой серии.
Цель и стоп проверяются по трёхминуткам Binance, дозабранным от последней проверки: книге не нужен живой сборщик,
и монета, выпавшая из выборки прогона, не зависает. Комиссия FEE за круг вычитается из итога.

    python3 paper_first3.py                 # что сделал бы сейчас, без записи
    python3 paper_first3.py --write         # прогон: входы, выходы, запись журнала (так зовёт run.py)
    python3 paper_first3.py --replay        # те же правила задним числом по всему журналу очереди, без записи
Журнал output/paper_first3.jsonl (entry / armed / exit / follow), состояние output/paper_first3.json.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import FIRST3_STREAK, FIRST3_SIZE, FIRST3_TARGET, FIRST3_BE, FIRST3_PAUSE_H
except ImportError:
    FIRST3_STREAK, FIRST3_SIZE, FIRST3_TARGET, FIRST3_BE, FIRST3_PAUSE_H = 3, 500.0, 0.40, 0.20, 48
try:
    from core_config import FIRST3_END_RUN, FIRST3_END_VERTICAL
except ImportError:
    FIRST3_END_RUN, FIRST3_END_VERTICAL = 200.0, 0.15
try:
    from core_config import FIRST3_MAX_OPEN, FIRST3_HOLD_H
except ImportError:
    FIRST3_MAX_OPEN, FIRST3_HOLD_H = 4, 48

BOOK = "3 в первых подряд"
QUEUE = BASE_DIR / "output" / "queue_log.jsonl"
STATE = BASE_DIR / "output" / "paper_first3.json"
LOG = BASE_DIR / "output" / "paper_first3.jsonl"
FEE = 0.001                    # круг, как SIGHT_FEE / PAPER_CROWD_FEE
BAR3 = 180_000
HALF = 1800


def _ts(iso: str) -> int:
    return int(datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp())


def _hm(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%d.%m %H:%M")


# Журнал очереди до 16.09 отложен при переводе на UTC; его метки на час впереди — сверено по ценам записей с
# архивом получасовок (24.09: 75 из 85 проверок совпали при сдвиге −1 ч). Нужен только --replay.
OLD_QUEUE = BASE_DIR / "_old_runs_20260916_1936UTC" / "output" / "queue_log.jsonl"
OLD_SHIFT = -3600


def leaders(with_old: bool = False) -> dict[int, dict[str, int]]:
    """{время свечи: {монета: когда прогон впервые записал её первой}}; дубли двойного прогона схлопываются"""
    out: dict[int, dict[str, int]] = defaultdict(dict)
    files = ([(OLD_QUEUE, OLD_SHIFT)] if with_old else []) + [(QUEUE, 0)]
    for path, shift in files:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            s = str(r.get("sym") or "")
            if r.get("place") != 1 or not s or s.startswith("_") or not r.get("candle") or not r.get("at"):
                continue
            c, at = _ts(r["candle"]) + shift, _ts(r["at"]) + shift
            out[c][s] = min(at, out[c].get(s, at))
    return out


def signals(ld: dict[int, dict[str, int]]) -> list[tuple[int, str, int]]:
    """[(момент, монета, начало серии)] — момент, когда монета стала первой FIRST3_STREAK-й раз подряд"""
    res, streak, start, prev = [], {}, {}, None
    for c in sorted(ld):
        cont = prev is not None and c - prev == HALF
        new, nst = {}, {}
        for s, at in ld[c].items():
            new[s] = streak.get(s, 0) + 1 if cont else 1
            nst[s] = start.get(s, c) if cont and s in streak else c
            if new[s] == FIRST3_STREAK:
                res.append((at, s, nst[s]))
        streak, start, prev = new, nst, c
    return res


_PRE: dict[str, list[tuple]] = {}      # --replay: трёхминутки монеты скачаны один раз на весь отрезок


def klines3(sym: str, start_ms: int, end_ms: int) -> list[tuple]:
    """закрытые трёхминутки Binance [(открытие мс, o, h, l, c)] с start_ms по end_ms"""
    if sym in _PRE:
        from bisect import bisect_left
        bars = _PRE[sym]
        i = bisect_left(bars, (start_ms,))
        out = []
        while i < len(bars) and bars[i][0] + BAR3 <= end_ms:
            out.append(bars[i])
            i += 1
        return out
    from core_config import BINANCE_FAPI
    from core_http import get_json
    out, st = [], start_ms
    while st < end_ms:
        page = get_json(f"{BINANCE_FAPI}/fapi/v1/klines",
                        {"symbol": sym, "interval": "3m", "startTime": st, "limit": 1500}, weight=10)
        if not page:
            break
        for k in page:
            t = int(k[0])
            if t + BAR3 > end_ms:
                break
            out.append((t, float(k[1]), float(k[2]), float(k[3]), float(k[4])))
        nxt = int(page[-1][0]) + BAR3
        if nxt <= st or len(page) < 1500:
            break
        st = nxt
    return out


def price_now(sym: str) -> float | None:
    from core_config import BINANCE_FAPI
    from core_http import get_json
    r = get_json(f"{BINANCE_FAPI}/fapi/v1/ticker/price", {"symbol": sym}, weight=1)
    try:
        return float(r["price"])
    except (TypeError, KeyError, ValueError):
        return None


def advance(pos: dict, now_ms: int) -> list[dict]:
    """прогнать позицию по трёхминуткам от последней проверки; вернуть события armed / exit"""
    ev = []
    e = float(pos["px"])
    for t, o, h, l, c in klines3(pos["sym"], int(pos["checked_ms"]), now_ms):
        pos["checked_ms"] = t + BAR3
        pos["last_px"] = c
        pos["max_px"] = max(float(pos.get("max_px") or e), h)
        if pos.get("armed") and l <= e:
            pos["closed"] = dict(at=(t + BAR3) / 1000, px=e, res=0.0, why="стоп в точке входа")
        elif h >= e * (1 + FIRST3_TARGET):
            pos["closed"] = dict(at=(t + BAR3) / 1000, px=e * (1 + FIRST3_TARGET), res=FIRST3_TARGET,
                                 why=f"цель +{FIRST3_TARGET * 100:.0f}%")
        if pos.get("closed"):
            cl = pos["closed"]
            ev.append(dict(kind="exit", why_exit=cl["why"], px_out=cl["px"], result_pct=round(cl["res"] * 100, 2),
                           usd=round(FIRST3_SIZE * (cl["res"] - FEE), 2), at=cl["at"]))
            break
        if not pos.get("armed") and h >= e * (1 + FIRST3_BE):
            pos["armed"] = True
            ev.append(dict(kind="armed", px=h, at=(t + BAR3) / 1000,
                           why=f"коснулась +{FIRST3_BE * 100:.0f}% — стоп в точку входа"))
        if FIRST3_HOLD_H and (t + BAR3) / 1000 - float(pos["at"]) >= FIRST3_HOLD_H * 3600:     # 26.09: срок сделки
            pos["closed"] = dict(at=(t + BAR3) / 1000, px=c, res=c / e - 1, why=f"срок {FIRST3_HOLD_H} ч")
            cl = pos["closed"]
            ev.append(dict(kind="exit", why_exit=cl["why"], px_out=cl["px"], result_pct=round(cl["res"] * 100, 2),
                           usd=round(FIRST3_SIZE * (cl["res"] - FEE), 2), at=cl["at"]))
            break
    return ev


def end_exit(sym: str) -> str | None:
    """ВЫХОД ПО КОНЦУ ХОДА (26.09, владелец «правь пока только бота»; R29/R21 из claude/research/rules.md):
    • R29 — при ходе ≥ FIRST3_END_RUN% от минимума 7 дн (near_move run_from_low7) объём последней получасовки — максимум за сутки
      (рекордный объём в далеко зашедшем ходе: через 6 ч ниже 14/19);
    • R21 — последняя получасовка ≥ +FIRST3_END_VERTICAL (вертикаль) и вынос шортов за час — максимум за сутки по потоку output/liq_sides.json
      (пик выноса шортов = вершина: LSK 13.09, PHA 26.09, ARK 26.09). Данные: cq_v2/intraday/<монета>.jsonl."""
    try:
        nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
        run = float(((((nm.get("coins") or {}).get(sym) or {}).get("nums") or {}).get("run_from_low7")) or 0)
    except Exception:  # noqa: BLE001
        run = 0.0
    rows = []
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines()[-49:]:
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    if len(rows) < 10:
        return None
    qv = [float(((r.get("kv") or {}).get("qv")) or 0) for r in rows]
    if run >= FIRST3_END_RUN and qv[-1] > 0 and qv[-1] >= max(qv[:-1]):
        return f"рекордный объём получасовки за сутки при ходе +{run:.0f}% от минимума 7 дн (R29)"
    c = [float(r.get("px") or 0) for r in rows]
    if len(c) >= 2 and c[-2] and c[-1] / c[-2] - 1 >= FIRST3_END_VERTICAL:
        try:
            ls = json.loads((BASE_DIR / "output" / "liq_sides.json").read_text(encoding="utf-8"))
            v = (ls.get("coins") or {}).get(sym) or {}
            bars = v.get("bars") or []
            if v.get("short1h") and len(bars) >= 2:
                m1h = max(float(bars[i][2]) + float(bars[i + 1][2]) for i in range(len(bars) - 1))
                if float(v["short1h"]) >= m1h * 0.999:
                    return f"вынос шортов за час {float(v['short1h']) / 1e3:.0f}K$ — максимум за сутки на вертикали +{(c[-1] / c[-2] - 1) * 100:.0f}% (R21)"
        except Exception:  # noqa: BLE001
            pass
    return None


def step(state: dict, sigs: list[tuple], now: float, px_of, window: float = 2 * HALF) -> list[dict]:
    """один шаг книги к моменту now: выходы по открытым, потом входы по сигналам последних window секунд —
    сигнал живёт только в свой прогон (запас на один пропущенный), иначе вход встал бы позже по старой цене"""
    events = []
    now_ms = int(now * 1000)
    for sym, pos in list(state["open"].items()):
        for e in advance(pos, now_ms):
            events.append(dict(book=BOOK, sym=sym, px_in=pos["px"], opened_at=pos["at"], **e))
        if not pos.get("closed") and not _PRE:                      # 26.09: выход по концу хода (R29/R21), не в --replay
            _we = end_exit(sym)
            if _we:
                _px = float(pos.get("last_px") or pos["px"]); _res = _px / float(pos["px"]) - 1
                pos["closed"] = dict(at=now, px=_px, res=_res, why=_we)
                events.append(dict(book=BOOK, sym=sym, px_in=pos["px"], opened_at=pos["at"], kind="exit", why_exit=_we, px_out=_px,
                                   result_pct=round(_res * 100, 2), usd=round(FIRST3_SIZE * (_res - FEE), 2), at=now))
        if pos.get("closed"):
            state["last_exit"][sym] = pos["closed"]["at"]
            del state["open"][sym]
    for at, sym, st in sigs:
        if at > now or at <= now - window or sym in state["open"] or state["used"].get(sym) == st:
            continue
        if now - float(state["last_exit"].get(sym) or 0) < FIRST3_PAUSE_H * 3600:
            continue
        if FIRST3_MAX_OPEN and len(state["open"]) >= FIRST3_MAX_OPEN:          # 26.09: слоты — депозит / K
            state["used"][sym] = st
            events.append(dict(kind="skip", book=BOOK, sym=sym, at=at, why=f"слотов нет: открыто {len(state['open'])} из {FIRST3_MAX_OPEN}"))
            continue
        px = px_of(sym, at)
        if not px:
            continue
        state["used"][sym] = st
        t0 = (int(at * 1000) // BAR3 + 1) * BAR3                 # проверка — с первой трёхминутки после входа
        state["open"][sym] = dict(sym=sym, px=px, at=at, checked_ms=t0, armed=False, max_px=px, last_px=px,
                                  streak_from=st)
        events.append(dict(kind="entry", book=BOOK, sym=sym, px=px, at=at, usd_in=FIRST3_SIZE,
                           rule=f"первая {FIRST3_STREAK} получасовки подряд с {_hm(st)}"))
    return events


def summary(state: dict, closed: list[dict]) -> str:
    won = [x for x in closed if x["result_pct"] > 0]
    zero = [x for x in closed if x["result_pct"] <= 0]
    op = list(state["open"].values())
    unreal = sum(FIRST3_SIZE * (float(p["last_px"]) / float(p["px"]) - 1) for p in op)
    real = sum(x["usd"] for x in closed)
    return (f"{BOOK}: открыто {len(op)} на {unreal:+.0f} $ · взято +{FIRST3_TARGET * 100:.0f}%: {len(won)} · "
            f"в ноль: {len(zero)} · взято {real:+.0f} $ · итог {real + unreal:+.0f} $")


def replay() -> int:
    ld = leaders(with_old=True)
    sigs = signals(ld)
    if not sigs:
        print("в журнале очереди нет серий")
        return 0
    state = {"open": {}, "last_exit": {}, "used": {}}
    closed = []
    first = min(a for a, _, _ in sigs)
    now = time.time()
    t = first
    since: dict[str, float] = {}
    for a, s, _ in sigs:
        since[s] = min(a, since.get(s, a))
    print(f"сигналов {len(sigs)} по {len(since)} монетам с {_hm(first)} · качаю трёхминутки…", flush=True)
    for s, a in since.items():
        _PRE[s] = klines3(s, int(a * 1000) // BAR3 * BAR3, int(now * 1000))

    def px_of(sym, at):                                        # вход — открытие первой трёхминутки после записи
        k = klines3(sym, int(at * 1000), int(at * 1000) + 10 * BAR3)
        return k[0][1] if k else None

    while t <= now:
        for e in step(state, sigs, t, px_of, window=HALF):
            if e["kind"] == "exit":
                closed.append(e)
            if e["kind"] in ("entry", "exit"):
                what = (f"вход {e['px']:.6g}" if e["kind"] == "entry"
                        else f"выход {e['why_exit']} {e['result_pct']:+.0f}% ({e['usd']:+.0f} $)")
                print(f"  {_hm(e['at'])} {e['sym'][:-4]:8s} {what}")
        t += HALF
    step(state, [], now, px_of)
    for p in sorted(state["open"].values(), key=lambda p: p["at"]):
        print(f"  висит {p['sym'][:-4]:8s} с {_hm(p['at'])} · {(p['last_px'] / p['px'] - 1) * 100:+.0f}%"
              f"{' · стоп в точке входа' if p.get('armed') else ''}")
    print(summary(state, closed))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--replay", action="store_true")
    a = ap.parse_args()
    if a.replay:
        return replay()
    try:
        state = json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("open", {})
    state.setdefault("last_exit", {})
    state.setdefault("used", {})
    if "since" not in state:                                   # книга начинается с первого прогона, прошлое — в --replay
        state["since"] = time.time()
    now = time.time()
    sigs = [s for s in signals(leaders()) if s[0] >= float(state["since"]) - 2 * HALF]
    events = step(state, sigs, now, lambda sym, at: price_now(sym))       # окно — два прогона
    closed = []
    if LOG.exists():
        for line in LOG.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "exit":
                closed.append(r)
    closed += [e for e in events if e["kind"] == "exit"]
    for p in state["open"].values():
        events.append(dict(kind="follow", book=BOOK, sym=p["sym"], px_in=p["px"], px=p["last_px"], opened_at=p["at"],
                           result_pct=round((float(p["last_px"]) / float(p["px"]) - 1) * 100, 2),
                           armed=bool(p.get("armed")), at=now, open=True))
    for e in events:
        if e["kind"] == "entry":
            print(f"paper_first3: {e['sym']} · вход лонг {e['px']:.6g} на {FIRST3_SIZE:.0f} $ · {e['rule']}")
        elif e["kind"] == "exit":
            print(f"paper_first3: {e['sym']} · выход {e['why_exit']} {e['result_pct']:+.0f}% ({e['usd']:+.0f} $)")
        elif e["kind"] == "armed":
            print(f"paper_first3: {e['sym']} · {e['why']}")
    print("paper_first3: " + summary(state, closed))
    if a.write:
        from sources_storage import write_atomic
        with LOG.open("a", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e, ensure_ascii=False) + "\n")
        write_atomic(STATE, json.dumps(state, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
