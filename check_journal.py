#!/usr/bin/env python3
"""СЧИТАЛКА ЖУРНАЛА ОЧЕРЕДИ (15.09; правило владельца 11.09: журнал заходов смотреть ВКУПЕ С ФОНОМ, фон первым —
сначала делить заходы по состоянию фона, признаки монеты читать внутри каждого состояния).

По output/queue_log.jsonl: для каждой записи с ценой — ход за FWD_H часов (из следующих записей той же монеты),
минус медиана доски в тот же прогон (строка _BG, если есть; нет — считается по монетам прогона). Фон — по
биткоину за сутки из строки _BG: «рынок вниз» (< −1%), «ровно», «вверх» (> +1%); нет строки — «фон неизвестен».
Внутри каждого фона — срезы по признакам: место, серия первых, режим, деньги, вортекс, хедж, приток, подхват,
быстрые против, наблюдения obs (streak6, ladder_20_50, overheat, parabola, place2_fresh).
Печатает таблицы: n, медиана хода к доске, доля ≥ HIT_PCT. Ничего не пишет.
Запуск: `python3 check_journal.py`, `--hours 12`, `--days 7`, `--min 10` (минимум записей в срезе).
"""
from __future__ import annotations

import argparse
import bisect
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
HIT_PCT = 8.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=24)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min", type=int, default=10)
    a = ap.parse_args()
    p = BASE_DIR / "output" / "queue_log.jsonl"
    if not p.exists():
        p = BASE_DIR / "queue_log.jsonl"
    recs = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except ValueError:
            continue
    recs.sort(key=lambda r: r["at"])
    T = lambda s: datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
    since = datetime.now(timezone.utc).timestamp() - a.days * 86400
    recs = [r for r in recs if T(r["at"]) >= since]
    bg = {r["at"]: r for r in recs if r.get("sym") == "_BG"}
    coins = [r for r in recs if r.get("sym") != "_BG"]
    bysym = defaultdict(list)
    for r in coins:
        if r.get("px"):
            bysym[r["sym"]].append((T(r["at"]), float(r["px"])))
    for s in bysym:
        bysym[s].sort()

    def px_after(sym, t, h):
        arr = bysym.get(sym, [])
        tt = t + h * 3600
        i = bisect.bisect_left(arr, (tt, 0.0))
        return arr[i][1] if i < len(arr) and arr[i][0] - tt < 3 * 3600 else None

    rows = []
    for r in coins:
        if not r.get("px"):
            continue
        t = T(r["at"])
        pa = px_after(r["sym"], t, a.hours)
        if pa is None:
            continue
        rows.append(dict(r, fwd=(pa / float(r["px"]) - 1) * 100))
    board = defaultdict(list)
    for r in rows:
        board[r["at"]].append(r["fwd"])
    bmed = {k: st.median(v) for k, v in board.items() if len(v) >= 6}
    for r in rows:
        r["rel"] = r["fwd"] - bmed[r["at"]] if r["at"] in bmed else None
    rows = [r for r in rows if r["rel"] is not None]

    def fon(r):
        b = bg.get(r["at"]) or {}
        v = b.get("btc_24h")
        if v is None:
            v = r.get("btc_24h")
        if v is None:
            return "фон неизвестен"
        return "рынок вниз" if v < -1 else "рынок вверх" if v > 1 else "рынок ровно"

    print(f"записей с форвардом {a.hours}ч к доске: {len(rows)} · прогонов с фоном биткоина: {sum(1 for b in bg.values() if b.get('btc_24h') is not None)} из {len(bg)}")
    cuts = [
        ("место", lambda r: min(r.get("place") or 99, 6) if r.get("place") else "вне очереди"),
        ("серия первых", lambda r: "1–2" if (r.get("first_streak") or 1) <= 2 else "3–5" if r["first_streak"] <= 5 else "6+"),
        ("режим", lambda r: r.get("mode")),
        ("деньги", lambda r: (r.get("money") or "—")[:36]),
        ("вортекс", lambda r: r.get("vortex_side")),
        ("хедж", lambda r: (r.get("vortex_hedge") or {}).get("kind") or "нет"),
        ("приток плеча", lambda r: "≥20" if (r.get("oi_inflow") or 0) >= 20 else "5–20" if (r.get("oi_inflow") or 0) >= 5 else "нет"),
        ("подхват", lambda r: "подхватил" if "подхватил:" in str(r.get("sess_pickup")) else "не подхватил" if "не подхватил" in str(r.get("sess_pickup")) else None),
        ("быстрые против", lambda r: "против" if r.get("fast_against") else "нет"),
        ("ход от дна 7д", lambda r: "<20" if (r.get("run_from_low7") or 0) < 20 else "20–50" if r["run_from_low7"] < 50 else ">50"),
        ("obs · streak6", lambda r: (r.get("obs") or {}).get("streak6")),
        ("obs · ladder_20_50", lambda r: (r.get("obs") or {}).get("ladder_20_50")),
        ("obs · overheat", lambda r: (r.get("obs") or {}).get("overheat")),
        ("obs · parabola", lambda r: (r.get("obs") or {}).get("parabola")),
        ("obs · place2_fresh", lambda r: (r.get("obs") or {}).get("place2_fresh")),
    ]
    for f in ("рынок вниз", "рынок ровно", "рынок вверх", "фон неизвестен"):
        sub = [r for r in rows if fon(r) == f]
        if len(sub) < a.min:
            continue
        print(f"\n════ {f.upper()} · n={len(sub)} · медиана хода доски за {a.hours}ч: {st.median([bmed[r['at']] for r in sub]):+.1f}%")
        for name, key in cuts:
            g = defaultdict(list)
            for r in sub:
                k = key(r)
                if k is None:
                    continue
                g[k].append(r["rel"])
            items = [(k, v) for k, v in g.items() if len(v) >= a.min]
            if len(items) < 2 and not name.startswith("obs"):
                continue
            if not items:
                continue
            print(f"  ── {name}")
            for k, v in sorted(items, key=lambda kv: -len(kv[1])):
                print(f"     {str(k):<36} n={len(v):>4}  к доске {st.median(v):+6.1f}%  ≥+{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x >= HIT_PCT) / len(v):4.0f}%")
    # ── ВЗЯТЫЕ ПРОТИВ ОТКЛОНЁННЫХ (16.09, мысль из P34: телеметрия честная, только если видны исходы и тех, кого
    #    не взяли). Новый журнал пишет всю сводку — сравниваем очередь и не-очередь, звёзд и остальных.
    if any("in_queue" in r for r in rows):
        print(f"\n════ ВЗЯТЫЕ ПРОТИВ ОТКЛОНЁННЫХ · ход за {a.hours}ч к доске")
        g = defaultdict(list)
        for r in rows:
            if "in_queue" not in r:
                continue
            firsts = set((bg.get(r["at"]) or {}).get("first") or [])
            k = "звезда" if r["sym"] in firsts else ("в очереди" if r.get("in_queue") else "вне очереди")
            g[k].append(r["rel"])
        for k in ("звезда", "в очереди", "вне очереди"):
            v = g.get(k) or []
            if len(v) >= a.min:
                print(f"     {k:<14} n={len(v):>5}  к доске {st.median(v):+6.1f}%  ≥+{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x >= HIT_PCT) / len(v):4.0f}%  ≤−{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x <= -HIT_PCT) / len(v):4.0f}%")
    # ── БУМАЖНЫЕ БОТЫ: что накопилось
    for name, pth in (("бот на быстрых", BASE_DIR / "output" / "paper_fast.jsonl"), ("бот против толпы", BASE_DIR / "output" / "paper_crowd.jsonl"), ("бот по концу", BASE_DIR / "output" / "paper_end.jsonl")):
        if not pth.exists():
            continue
        ex = []
        for line in pth.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") == "exit" and r.get("result_pct") is not None:
                ex.append(r)
        if len(ex) >= 5:
            v = [float(r["result_pct"]) for r in ex]
            print(f"\n════ {name.upper()} · сделок {len(v)} · попаданий {100 * sum(1 for x in v if x > 0) / len(v):.0f}% · средняя {st.mean(v):+.2f}% · медиана {st.median(v):+.2f}% · худшая {min(v):+.1f}%")
            byrule = defaultdict(list)
            for r in ex:
                byrule[r.get("rule") or r.get("why") or "—"].append(float(r["result_pct"]))
            for k, vv in sorted(byrule.items(), key=lambda kv: -len(kv[1])):
                if len(vv) >= 5:
                    print(f"     {str(k)[:48]:<48} n={len(vv):>3}  попаданий {100 * sum(1 for x in vv if x > 0) / len(vv):3.0f}%  средняя {st.mean(vv):+.2f}%")
    # ── ВЕРДИКТ → ХОД (15.09): output/verdict_log.jsonl — вердикт карточки на монету за прогон; форвард по цене
    #    из тех же строк через a.hours; к доске — минус медиана всех монет того же прогона.
    vp = BASE_DIR / "output" / "verdict_log.jsonl"
    if not vp.exists():
        vp = BASE_DIR / "verdict_log.jsonl"
    if vp.exists():
        vrecs = []
        for line in vp.read_text(encoding="utf-8").splitlines():
            try:
                vrecs.append(json.loads(line))
            except ValueError:
                continue
        vrecs = [r for r in vrecs if r.get("px") and T(r["at"]) >= since]
        vby = defaultdict(list)
        for r in vrecs:
            vby[r["sym"]].append((T(r["at"]), float(r["px"])))
        for k in vby:
            vby[k].sort()
        def vpx_after(sym, t, h):
            arr = vby.get(sym, [])
            tt = t + h * 3600
            i = bisect.bisect_left(arr, (tt, 0.0))
            return arr[i][1] if i < len(arr) and arr[i][0] - tt < 3 * 3600 else None
        vrows = []
        for r in vrecs:
            pa = vpx_after(r["sym"], T(r["at"]), a.hours)
            if pa:
                vrows.append(dict(r, fwd=(pa / float(r["px"]) - 1) * 100))
        vb = defaultdict(list)
        for r in vrows:
            vb[r["at"]].append(r["fwd"])
        vmed = {k: st.median(v) for k, v in vb.items() if len(v) >= 6}
        vrows = [dict(r, rel=r["fwd"] - vmed[r["at"]]) for r in vrows if r["at"] in vmed]
        if vrows:
            print(f"\n════ ВЕРДИКТ → ХОД за {a.hours}ч к доске · n={len(vrows)}")
            g = defaultdict(list)
            for r in vrows:
                g[r.get("verdict")].append(r["rel"])
            for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
                if len(v) >= a.min:
                    print(f"     {str(k):<24} n={len(v):>4}  к доске {st.median(v):+6.1f}%  ≥+{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x >= HIT_PCT) / len(v):4.0f}%  ≤−{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x <= -HIT_PCT) / len(v):4.0f}%")
            g2 = defaultdict(list)
            for r in vrows:
                g2[(r.get("verdict"), r.get("group"))].append(r["rel"])
            print("  ── вердикт · группа")
            for k, v in sorted(g2.items(), key=lambda kv: -len(kv[1])):
                if len(v) >= a.min:
                    print(f"     {str(k[0]) + ' · ' + str(k[1]):<32} n={len(v):>4}  к доске {st.median(v):+6.1f}%  ≥+{HIT_PCT:.0f}%: {100 * sum(1 for x in v if x >= HIT_PCT) / len(v):4.0f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
