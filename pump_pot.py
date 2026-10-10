#!/usr/bin/env python3
"""КОТЁЛ БОЛЬШИХ РОСТОВ (10.10 ~23:30 UTC, владелец: «нужно писать каждый большой рост и отнимать из 600 млн капитализации, условно раз в прогон
проверять монету, которая дала больше 50% за 24 часа, и следить, до какой капы она дойдёт, и вычитать из 600 отношение между тем, что было, до
момента пика цены»; «как только доходит до 600 — только шорты на выносе шортов у лидеров»; «через 3.5 суток обнуляется»).

Раз в прогон (зовёт market_bg.py, отдельный процесс) по получасовому архиву cq_v2/intraday:
  • большой рост монеты начинается, когда её цена выше цены WIN_H часов назад на TRIG (50 % за 3 дня — «считай рост за 3 дня», владелец 10.10);
    «что было» — низ за это окно (капитализация до роста);
  • дальше следим за вершиной: капитализация на вершине = монеты в обороте × максимум цены; рост закончен, когда цена отдала половину роста
    (мерка Claude); новый рост той же монеты — только после того, как условие «+50 % за окно» сначала пропало;
  • из котла POT_USD (600 млн $) вычитается «вершина минус что было» по всем ростам круга (рост относится к кругу, в котором он начался);
  • вычтено дошло до котла — круг ПОЛНЫЙ: «только шорты на выносе шортов у лидеров»; через RESET_D (3,5) суток после этого счёт обнуляется и
    начинается новый круг — в него идут только росты, начавшиеся после обнуления.
Начало первого круга — начало архива (или сохранённое начало круга из output/pump_pot.json, чтобы счёт не съезжал, когда архив подрезают).
Монеты в обороте — output/circ_supply.json (сверена ценой; claude/research/circ_table.py). Время — UTC. Ничего не решает и в бота не идёт:
журнал output/pump_pot.jsonl (строка на прогон) и снимок output/pump_pot.json.
    .venv/bin/python pump_pot.py                 # сейчас
    .venv/bin/python pump_pot.py --history       # все круги по архиву с его начала
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

def _owner(name: str, default):
    """мерка владельца из общего конфига (core_config.py, блок «РУЧНЫЕ МЕРКИ ВЛАДЕЛЬЦА», 10.10 23:20 UTC: «перенеси в общий конфиг… чтобы я сам их мог задавать»)"""
    try:
        import core_config
        v = getattr(core_config, name, None)
        return default if v is None else v
    except Exception:  # noqa: BLE001
        return default


POT_USD = float(_owner("MANUAL_BY_USER_POT_MAX_MLN", 600)) * 1e6     # котёл: «отнимать из 600 млн капитализации» (владелец 10.10)
TRIG = float(_owner("MANUAL_BY_USER_POT_TRIG_PCT", 50)) / 100         # «монету, которая дала больше 50%…» (владелец 10.10)
WIN_H = int(round(float(_owner("MANUAL_BY_USER_POT_WIN_DAYS", 3)) * 24))          # окно роста в часах: «считай рост за 3 дня» (владелец 10.10 ~22:50 UTC; до этого было 24 — STRK с ходом +46 % за сутки и +438 млн $ в котёл не попадала)
W = WIN_H * 2       # то же в получасовках
WARM_D = 20         # запас архива до начала круга для разгона счёта ростов, суток
RESET_D = float(_owner("MANUAL_BY_USER_POT_RESET_DAYS", 3.5))       # «через 3.5 суток обнуляется» (владелец 10.10) — от момента, когда вычтенное дошло до котла
WARN_USD = float(_owner("MANUAL_BY_USER_POT_WARN_MLN", 400)) * 1e6    # «после достижения 400 уже гореть красным какая-то метка на экране, т.е. ход остался только у тех, кто идёт сейчас» (владелец 10.10)
SKIP = {"BTC", "ETH"}
INTRA = BASE_DIR / "cq_v2" / "intraday"
TAB = BASE_DIR / "output" / "circ_supply.json"
LOG = BASE_DIR / "output" / "pump_pot.jsonl"
NOW = BASE_DIR / "output" / "pump_pot.json"
FMT = "%Y-%m-%dT%H:%M:%SZ"
FULL_TXT = "котёл полный — только шорты на выносе шортов у лидеров"
WARN_TXT = "ход остался только у тех, кто идёт сейчас"


def _t(s: str) -> datetime:
    return datetime.strptime(s, FMT).replace(tzinfo=timezone.utc)


def _flow(cap: float) -> int:
    """поток по капитализации (границы владельца 10.10): 1 — от 500 млн $, 2 — 100–500 млн $, 3 — ниже 100 млн $"""
    lo, hi = _owner("MANUAL_BY_USER_FLOW_MARKS_MLN", (100, 500))
    return 1 if cap >= float(hi) * 1e6 else (2 if cap >= float(lo) * 1e6 else 3)


def _rows(p: Path, t_from: str, t_to: str) -> list:
    out = []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        c = r.get("candle")
        if not c or c < t_from or c > t_to or not (r.get("px") and r.get("h") and r.get("l")):
            continue
        out.append((c, float(r["px"]), float(r["h"]), float(r["l"])))
    return out


def coin_events(sym: str, rows: list, circ: float) -> tuple[list, list]:
    """большие росты монеты и события «вершина выросла»: ([рост…], [(время, id роста, добавлено $)…]); рост: {id, sym, t0, t_trig, t_peak, base, peak, done}"""
    moves = []; ev = []; act = None; armed = True
    for i in range(W, len(rows)):
        c, px, h, l = rows[i]
        hot = px >= rows[i - W][1] * (1 + TRIG)
        if act is None:
            if not hot:
                armed = True
            elif armed:
                j = min(range(i - W, i + 1), key=lambda k: rows[k][3])
                act = dict(id=f"{sym}|{c}", sym=sym, t0=rows[j][0], t_trig=c, t_peak=c, base=rows[j][3], peak=h, done=False, circ=circ)
                moves.append(act); ev.append((c, act["id"], circ * (h - act["base"])))
        else:
            if h > act["peak"]:
                act["peak"], act["t_peak"] = h, c
                ev.append((c, act["id"], circ * (h - act["base"])))
            if l <= act["peak"] - 0.5 * (act["peak"] - act["base"]):
                act["done"] = True; act["t_done"] = c; act = None; armed = False
    return moves, ev


def load(asof: datetime, t_from: str | None) -> tuple[dict, list, str, str]:
    """→ (росты по id, события по времени, последняя свеча, первая свеча архива)"""
    try:
        tab = json.loads(TAB.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        tab = {}
    # разгон: росты одной монеты зависят от её прежних ростов (новый — только после того, как условие пропало), поэтому архив читается
    # с запасом WARM_D суток до начала круга — иначе счёт от сохранённого начала расходится со счётом по всему архиву (10.10: RLC и ORCA менялись местами)
    lo = (_t(t_from) - timedelta(days=WARM_D)).strftime(FMT) if t_from else "0"
    hi = asof.strftime(FMT)
    allm = {}; evs = []; last = ""; first = "9"
    for p in sorted(INTRA.glob("*.jsonl")):
        base = p.stem.upper(); t = tab.get(base + "USDT")
        if base in SKIP or not t or not t.get("circ"):
            continue
        circ = float(t["circ"]) / (1000 if base.startswith("1000") else 1)
        rows = _rows(p, lo, hi)
        if len(rows) < W + 12:
            continue
        last = max(last, rows[-1][0]); first = min(first, rows[0][0])
        ms, ev = coin_events(base + "USDT", rows, circ)
        for m in ms:
            m["cap_now"] = circ * rows[-1][1]; allm[m["id"]] = m
        evs += ev
    evs.sort()
    return allm, evs, last, first


def cycles(allm: dict, evs: list, start: str, asof: datetime) -> list:
    """круги котла от start до asof: [{from, full_at, reset_at, added: {id: $}}]; последний — текущий"""
    out = [dict(**{"from": start}, full_at=None, reset_at=None, added={})]
    def roll(until: str) -> None:                                   # обнуления, наступившие до момента until
        while out[-1]["reset_at"] and out[-1]["reset_at"] <= until:
            out.append(dict(**{"from": out[-1]["reset_at"]}, full_at=None, reset_at=None, added={}))
    for t, mid, add in evs:
        roll(t)
        cur = out[-1]
        if allm[mid]["t_trig"] < cur["from"]:
            continue                                                 # рост начался в прошлом круге — в этот не идёт
        cur["added"][mid] = add
        if cur["full_at"] is None and sum(cur["added"].values()) >= POT_USD:
            cur["full_at"] = t; cur["reset_at"] = (_t(t) + timedelta(days=RESET_D)).strftime(FMT)
    roll(asof.strftime(FMT))
    return out


def build(asof: datetime | None = None, history: bool = False):
    asof = asof or datetime.now(timezone.utc)
    start = None
    if not history:
        try:
            _sv = json.loads(NOW.read_text(encoding="utf-8")) or {}
            if (_sv.get("trig_pct"), _sv.get("win_h"), _sv.get("reset_days"), _sv.get("pot_usd")) == (TRIG * 100, WIN_H, RESET_D, round(POT_USD)):
                start = _sv.get("cycle_from")                          # мерки те же — продолжаем сохранённый круг; изменились — круги пересчитываются с начала архива
        except (OSError, ValueError):
            start = None
    allm, evs, last, first = load(asof, start)
    cyc = cycles(allm, evs, (start or (_t(first) + timedelta(hours=WIN_H)).strftime(FMT)) if first != "9" else asof.strftime(FMT), asof)
    if history:
        return allm, cyc
    cur = cyc[-1]
    moves = []
    for mid, add in cur["added"].items():
        m = allm[mid]; c0, c1 = m["circ"] * m["base"], m["circ"] * m["peak"]
        moves.append(dict(sym=m["sym"], t0=m["t0"], t_trig=m["t_trig"], t_peak=m["t_peak"], done=m["done"], x=round(m["peak"] / m["base"], 2),
                          cap_before=round(c0), cap_peak=round(c1), added=round(add), cap_now=round(m["cap_now"]), flow_before=_flow(c0), flow_peak=_flow(c1)))
    moves.sort(key=lambda m: -m["added"])
    used = sum(m["added"] for m in moves)
    by_flow = {str(k): round(sum(m["added"] for m in moves if m["flow_before"] == k)) for k in (1, 2, 3)}   # сколько вычтено ростами из каждого потока (по капитализации до роста)
    return {"by_flow_usd": by_flow, "at": asof.strftime(FMT), "candle": last or None, "pot_usd": round(POT_USD), "used_usd": round(used), "left_usd": round(POT_USD - used),
            "cycle_from": cur["from"], "full_at": cur["full_at"], "reset_at": cur["reset_at"], "full": bool(cur["full_at"]),
            "state": FULL_TXT if cur["full_at"] else (WARN_TXT if used >= WARN_USD else "котёл набирается"), "warn": bool(used >= WARN_USD), "warn_usd": round(WARN_USD),
            "n": len(moves), "active": sum(1 for m in moves if not m["done"]),
            "reset_days": RESET_D, "trig_pct": TRIG * 100, "win_h": WIN_H, "moves": moves}


def write(res: dict) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    tmp = NOW.with_suffix(".tmp"); tmp.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8"); tmp.replace(NOW)


def _ms(moves: list, n: int = 8) -> str:
    return ", ".join(f"{m['sym'][:-4]} +{m['added'] / 1e6:.0f} ({m['cap_before'] / 1e6:.0f}→{m['cap_peak'] / 1e6:.0f}{'' if m['done'] else ', идёт'})" for m in moves[:n])


def line(res: dict) -> str:
    head = f"круг с {res['cycle_from'][5:16].replace('T', ' ')} UTC · вычтено {res['used_usd'] / 1e6:.0f} из {res['pot_usd'] / 1e6:.0f} млн $ · осталось {res['left_usd'] / 1e6:.0f}"
    if res.get("warn") and not res["full"]:
        head += f" · КРАСНАЯ МЕТКА (от {res['warn_usd'] / 1e6:.0f} млн $): {WARN_TXT}"
    if res["full"]:
        head += f" · ПОЛНЫЙ с {res['full_at'][5:16].replace('T', ' ')}: только шорты на выносе шортов у лидеров · обнуление {res['reset_at'][5:16].replace('T', ' ')} UTC"
    bf = res.get("by_flow_usd") or {}
    head += f" · по потокам до роста: 1-й {bf.get('1', 0) / 1e6:.0f}, середина {bf.get('2', 0) / 1e6:.0f}, 3-й {bf.get('3', 0) / 1e6:.0f}"
    return head + f" · ростов {res['n']} (идут {res['active']})" + (" · " + _ms(res["moves"]) if res["moves"] else "")


def main() -> int:
    ap = argparse.ArgumentParser(description="котёл больших ростов")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--history", action="store_true", help="все круги по архиву с его начала")
    a = ap.parse_args()
    if a.history:
        allm, cyc = build(history=True)
        for c in cyc:
            ms = sorted(((add, allm[mid]) for mid, add in c["added"].items()), key=lambda x: -x[0])
            tot = sum(x[0] for x in ms)
            print(f"круг с {c['from'][5:16].replace('T', ' ')} · " + (f"полный {c['full_at'][5:16].replace('T', ' ')} · обнуление {c['reset_at'][5:16].replace('T', ' ')}" if c["full_at"] else "набирается")
                  + f" · всего за круг {tot / 1e6:.0f} млн $ · ростов {len(ms)} · " + ", ".join(f"{m['sym'][:-4]} +{a_ / 1e6:.0f}" for a_, m in ms[:9]))
        return 0
    res = build(); print(line(res))
    if a.write:
        write(res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
