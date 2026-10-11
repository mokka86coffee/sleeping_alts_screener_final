#!/usr/bin/env python3
"""ПЕРЕСЧЁТ СДЕЛОК БОТА ПО НОВЫМ ПРАВИЛАМ (11.10 02:20 UTC, владелец: «пересчитай все сделки бота по новым правилам, пусть они рисуются сразу по новой»).

Берёт все бумажные сделки трёх книг (закрытые — из журналов output/paper_*.jsonl, открытые — из книг output/paper_*.json) и для каждой, открытой ДО того,
как правило заработало в боте, решает, взял бы её бот сейчас:
  R84 — котёл больших ростов: полный — лонг не берётся; красная метка — лонг только по монете, чей большой рост ещё идёт (до 11.10 00:44:38 UTC);
  R86 — шорт не берётся, когда цена входа не выше «минимум дневных свечей за 60 суток + 20 %» (до 11.10 02:16:17 UTC);
  «свой ММ» — монеты ручного списка OWN_MM_MANUAL (ARPA добавлена 11.10).
Сделки, которые по новым правилам не берутся, пишутся в output/recount_new_rules.json (skip: {«книга|монета|секунда входа»: причина}); страница бота
(fast_state.positions) их не показывает и в итоги не считает. Журналы и книги бота не меняются — снять пересчёт можно, удалив файл.

Круги котла: до начала нынешнего круга (cycle_from в output/pump_pot.json) — счёт от начала архива, с него — нынешний круг, как на экране (выбор мой:
так прошлое совпадает с тем, что котёл показывает сейчас). Дно за 60 суток — дневные свечи TradingView (claude/research/tvd) и получасовки архива
(cq_v2); монета без дневных свечей TradingView правилом R86 не проверяется и остаётся. С биржи ничего не запрашивается.

    .venv/bin/python claude/research/recount_new_rules.py            # посчитать и записать
    .venv/bin/python claude/research/recount_new_rules.py --dry      # только показать счёт
"""
from __future__ import annotations

import bisect
import collections
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import core_config  # noqa: E402
import pump_pot as pp  # noqa: E402

U = timezone.utc
OUT = ROOT / "output" / "recount_new_rules.json"
TVD = ROOT / "claude" / "research" / "tvd"
R84_ON = datetime(2026, 10, 11, 0, 44, 38, tzinfo=U).timestamp()      # с этой секунды бот сам слушает котёл
R86_ON = datetime(2026, 10, 11, 2, 16, 17, tzinfo=U).timestamp()      # с этой секунды бот сам не шортит дно
BOOKS = (("всплеск/вынос", "paper_fast3"), ("пробуждение", "paper_wake"), ("очередь", "paper_queue"))
LOW_D = int(getattr(core_config, "MANUAL_BY_USER_SHORT_LOW_DAYS", 60))
LOW_P = float(getattr(core_config, "MANUAL_BY_USER_SHORT_LOW_PCT", 20))
OWN = set(getattr(core_config, "OWN_MM_MANUAL", []))


def trades() -> list[dict]:
    out = {}
    for book, stem in BOOKS:
        jl = ROOT / "output" / f"{stem}.jsonl"
        if jl.exists():
            for ln in jl.open(encoding="utf-8"):
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                if not str(r.get("kind", "")).startswith("exit") or not r.get("opened_at"):
                    continue
                k = f"{book}|{r['sym']}|{int(float(r['opened_at']))}"
                t = out.setdefault(k, dict(key=k, book=book, sym=r["sym"], side=int(r.get("side") or 1), t_in=float(r["opened_at"]), px=float(r["px_in"]), usd=0.0,
                                           rule=r.get("rule") or "", open=False, t_out=float(r["at"])))
                t["usd"] += float(r["usd"]) if r.get("usd") is not None else float(r.get("result_pct") or 0) * 5
                t["t_out"] = max(t["t_out"], float(r["at"]))
        try:
            st = json.loads((ROOT / "output" / f"{stem}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st = {}
        for sym, p in (st.get("open") or {}).items():
            k = f"{book}|{sym}|{int(float(p['at']))}"
            out.setdefault(k, dict(key=k, book=book, sym=sym, side=int(p["side"]), t_in=float(p["at"]), px=float(p["px"]), usd=0.0, rule=p.get("rule") or "", open=True, t_out=None))
    return sorted(out.values(), key=lambda x: x["t_in"])


class Pot:
    def __init__(self) -> None:
        asof = datetime.now(U)
        self.allm, evs, _last, first = pp.load(asof, None)
        self.evs = sorted(evs)
        self.start = (pp._t(first) + timedelta(hours=pp.WIN_H)).strftime(pp.FMT)
        try:
            self.live_from = json.loads(pp.NOW.read_text(encoding="utf-8")).get("cycle_from") or self.start
        except (OSError, ValueError):
            self.live_from = self.start

    def at(self, ts: float):
        """→ (состояние, вычтено $, монеты с идущим ростом)"""
        t = datetime.fromtimestamp(ts, U).strftime(pp.FMT)
        start = self.live_from if t >= self.live_from else self.start
        cur = dict(frm=start, full_at=None, reset_at=None, added={})

        def roll(until: str) -> None:
            nonlocal cur
            while cur["reset_at"] and cur["reset_at"] <= until:
                cur = dict(frm=cur["reset_at"], full_at=None, reset_at=None, added={})
        for et, mid, add in self.evs:
            if et > t:
                break
            if et < start:
                continue
            roll(et)
            if self.allm[mid]["t_trig"] < cur["frm"]:
                continue
            cur["added"][mid] = add
            if cur["full_at"] is None and sum(cur["added"].values()) >= pp.POT_USD:
                cur["full_at"] = et; cur["reset_at"] = (pp._t(et) + timedelta(days=pp.RESET_D)).strftime(pp.FMT)
        roll(t)
        used = sum(cur["added"].values())
        going = {self.allm[m]["sym"] for m in cur["added"] if not (self.allm[m].get("t_done") and self.allm[m]["t_done"] <= t)}
        return ("полный" if cur["full_at"] else "красная метка" if used >= pp.WARN_USD else "свободен"), used, going


class Lows:
    """дно монеты за LOW_D суток на момент входа: дневные свечи TradingView + получасовки архива (архив читается один раз на все монеты)"""
    def __init__(self) -> None:
        self.d1: dict = {}
        rows = pp.hist_rows(pp.HIST_FROM, datetime.now(U).strftime(pp.FMT))
        self.hh = {b + "USDT": [(pp._t(r[0]).timestamp(), float(r[3])) for r in v if float(r[3]) > 0] for b, v in rows.items()}

    def _load(self, sym: str) -> None:
        if sym in self.d1:
            return
        try:
            bars = json.loads((TVD / f"{sym}.P_1D.json").read_text(encoding="utf-8")).get("bars") or []
            self.d1[sym] = [(float(b[0]), float(b[3])) for b in bars if float(b[3]) > 0]
        except (OSError, ValueError):
            self.d1[sym] = []

    def low(self, sym: str, ts: float):
        self._load(sym)
        if not self.d1[sym]:
            return None
        lo = ts - LOW_D * 86400
        v = [l for t, l in self.d1[sym] if lo <= t + 86400 and t <= ts] + [l for t, l in self.hh.get(sym, []) if lo <= t <= ts]
        return min(v) if v else None


def main() -> int:
    T = trades(); pot = Pot(); lows = Lows(); skip = {}
    for x in T:
        why = None
        if x["sym"] in OWN and x["sym"] == "ARPAUSDT":                    # остальные монеты ручного списка бот и раньше не брал
            why = "свой ММ: монета в ручном списке владельца (11.10)"
        if not why and x["t_in"] < R84_ON:
            st, used, going = pot.at(x["t_in"])
            if x["side"] == 1 and st == "полный":
                why = f"R84: котёл полный ({used / 1e6:.0f} из {pp.POT_USD / 1e6:.0f} млн $) — лонг не берётся"
            elif x["side"] == 1 and st == "красная метка" and x["sym"] not in going:
                why = f"R84: красная метка котла ({used / 1e6:.0f} млн $) — лонг только по идущей монете"
        if not why and x["side"] == -1 and x["t_in"] < R86_ON and LOW_P:
            lo = lows.low(x["sym"], x["t_in"])
            if lo and x["px"] <= lo * (1 + LOW_P / 100):
                why = f"R86: шорт у дна — вход {x['px']:.6g} не выше {LOW_P:g}% над минимумом за {LOW_D} дн ({lo:.6g})"
        x["skip"] = why
        if why:
            skip[x["key"]] = why
    cl = [x for x in T if not x["open"]]

    def agg(L: list) -> str:
        return f"{len(L)} сделок, в плюс {sum(x['usd'] > 0 for x in L)}, {sum(x['usd'] for x in L):+.0f} $"
    print("закрытых сделок:", agg(cl)); print("по новым правилам остаётся:", agg([x for x in cl if not x["skip"]])); print("не берётся:", agg([x for x in cl if x["skip"]]))
    for k, n in collections.Counter(x["skip"].split(":")[0] + (" лонг" if x["side"] == 1 else " шорт") for x in cl if x["skip"]).most_common():
        print("   ", k, "—", agg([x for x in cl if x["skip"] and x["skip"].split(":")[0] + (" лонг" if x["side"] == 1 else " шорт") == k]))
    for sd, nm in ((1, "лонг"), (-1, "шорт")):
        print(f"  {nm}: было {agg([x for x in cl if x['side'] == sd])} → остаётся {agg([x for x in cl if x['side'] == sd and not x['skip']])}")
    days = collections.defaultdict(lambda: [0.0, 0.0])
    for x in cl:
        d = datetime.fromtimestamp(x["t_in"], U).strftime("%m-%d"); days[d][0] += x["usd"]; days[d][1] += 0 if x["skip"] else x["usd"]
    print("по дням входа, было → стало:", " · ".join(f"{d} {a:+.0f}→{b:+.0f}" for d, (a, b) in sorted(days.items())))
    print("открытых сейчас:", sum(1 for x in T if x["open"]), "| из них по новым правилам не берётся:", [(x["sym"][:-4], x["skip"][:40]) for x in T if x["open"] and x["skip"]])
    nolow = sorted({x["sym"][:-4] for x in T if x["side"] == -1 and not lows.d1.get(x["sym"])})
    print("шорты без дневных свечей TradingView (R86 не проверен):", len(nolow), " ".join(nolow)[:300])
    if "--dry" not in sys.argv:
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(at=datetime.now(U).strftime(pp.FMT), rules="R84, R86, свой ММ (ARPA)", n_all=len(T), n_skip=len(skip), skip=skip), ensure_ascii=False), encoding="utf-8")
        tmp.replace(OUT); print("записано:", OUT, len(skip))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
