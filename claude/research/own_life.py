#!/usr/bin/env python3
"""МОНЕТЫ СО СВОИМ ММ — ЖИВУТ СВОЕЙ ЖИЗНЬЮ (27.09, владелец: «не только Q, а вообще те, что своей жизнью живут и не подходят ни к одному
правилу; Q просто показывает слом правил, хотя он и есть фон со своим мм — это отдельный кейс; по другим тоже такие находить и помечать,
что у них свой мм со своими стратегиями, а не ломать на них правила»).

Три признака за 30 дней (выборка — перпы Binance, которые может взять быстрый бот):
  1. связь с доской — корреляция получасовых ходов монеты с медианой хода всех монет выборки; доля её крупных ходов (топ-2% |хода|),
     когда доска стояла (|медиана| меньше своей медианы модуля);
  2. проколы одной свечой — из mm_flush.json (глубже 10%, выкуп половины за 6 ч);
  3. правила на монете — rules_trades.json (995 сделок 9 правил) + быстрые книги: сумма и доля в плюс на монете против той же доли
     по правилу в целом.
Порогов нет — распределения и таблица монет; список own_life.json собирает владелец по порогам из этого счёта.

    .venv/bin/python claude/research/own_life.py      # (после mm_flush.py) → own_life.md, own_life_stats.json
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from core_http import get_json  # noqa: E402

HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))


def k30(sym: str) -> list[list]:
    return get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "30m", "limit": 1440}, quiet_400=True, weight=10) or []


def corr(a, b):
    n = len(a)
    if n < 50:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a); vb = sum((y - mb) ** 2 for y in b)
    if not va or not vb:
        return None
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (va * vb) ** .5


def main() -> int:
    t0 = time.time()
    fl = json.loads((HERE / "mm_flush.json").read_text())
    import mm_flush
    syms = mm_flush.universe()
    K = {}
    with ThreadPoolExecutor(4) as ex:
        for s, k in zip(syms, ex.map(k30, syms)):
            if len(k) > 200:
                K[s] = {int(x[0]): float(x[4]) for x in k}
    # доска: медиана хода по всем монетам на каждой получасовке
    ts = sorted({t for v in K.values() for t in v})
    board = {}
    for a, b in zip(ts, ts[1:]):
        r = [v[b] / v[a] - 1 for v in K.values() if a in v and b in v and v[a]]
        if len(r) >= 30:
            board[b] = st.median(r)
    bmed = st.median(abs(x) for x in board.values())
    sign1 = {}
    for s, v in K.items():
        tt = sorted(v)
        pairs = [(v[b] / v[a] - 1, board[b]) for a, b in zip(tt, tt[1:]) if b in board and v[a]]
        if len(pairs) < 200:
            continue
        rc, rb = [p[0] for p in pairs], [p[1] for p in pairs]
        thr = sorted(abs(x) for x in rc)[int(len(rc) * .98)]
        big = [(x, y) for x, y in pairs if abs(x) >= thr]
        sign1[s] = dict(corr=round(corr(rc, rb) or 0, 2), own_big=round(sum(1 for x, y in big if abs(y) < bmed) / len(big) * 100) if big else None)
    # признак 2 — проколы
    fc = {c["sym"]: c for c in fl["coins"]}
    # признак 3 — правила на монете
    trades = defaultdict(list); rule_all = defaultdict(list)
    for r in json.loads((HERE / "rules_trades.json").read_text()):
        trades[r["sym"]].append((r["rule"], float(r["res"]))); rule_all[r["rule"]].append(float(r["res"]))
    for f, name in (("paper_fast3.jsonl", "быстрые: всплеск/вынос"), ("paper_wake.jsonl", "быстрые: пробуждение")):
        for ln in (ROOT / "output" / f).open(encoding="utf-8"):
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if str(r.get("kind", "")).startswith("exit") and r.get("result_pct") is not None:
                trades[r["sym"]].append((name, float(r["result_pct"]))); rule_all[name].append(float(r["result_pct"]))
    wr = {k: sum(1 for x in v if x > 0) / len(v) for k, v in rule_all.items() if v}
    sign3 = {}
    for s, g in trades.items():
        exp = st.mean(wr[r] for r, _ in g)                   # доля в плюс, которую правила дают в среднем
        sign3[s] = dict(n=len(g), win=round(sum(1 for _, x in g if x > 0) / len(g) * 100), exp=round(exp * 100), sum=round(sum(x for _, x in g), 1),
                        rules=len({r for r, _ in g}))
    rows = []
    for s in syms:
        a, b, c = sign1.get(s), fc.get(s), sign3.get(s)
        if not a:
            continue
        rows.append(dict(sym=s, corr=a["corr"], own_big=a["own_big"], worst=b["worst"] if b else None, n20=b["n20"] if b else 0,
                         rec=b["rec"] if b else None, rec_h=b["rec_h"] if b else None,
                         n=c["n"] if c else 0, win=c["win"] if c else None, exp=c["exp"] if c else None, sum=c["sum"] if c else None))
    (HERE / "own_life_stats.json").write_text(json.dumps(dict(at=int(time.time()), rows=rows), ensure_ascii=False))
    q = lambda v, p: sorted(v)[int(len(v) * p)]  # noqa: E731
    cs = [r["corr"] for r in rows]; ob = [r["own_big"] for r in rows if r["own_big"] is not None]
    Lm = [f"# Монеты со своим ММ — три признака ({datetime.now(L):%d.%m %H:%M})", "",
          f"Выборка: {len(rows)} монет (быстрый бот может взять), 30 дн. Порогов нет — выбирает владелец.", "",
          "## Признак 1 — связь с доской", "",
          f"корреляция получасовых ходов с медианой доски: 10% монет ниже {q(cs, .1):.2f}, медиана {st.median(cs):.2f}, 90% ниже {q(cs, .9):.2f}",
          f"доля своих крупных ходов (топ-2% |хода| при стоящей доске): медиана {st.median(ob):.0f}%, 90% монет ниже {q(ob, .9):.0f}%", "",
          "## Признак 2 — проколы одной свечой (mm_flush.md)", "",
          f"монет с проколом глубже 20% за 30 дн: {sum(1 for r in rows if r['worst'] is not None and r['worst'] <= -20)}, глубже 30%: "
          f"{sum(1 for r in rows if r['worst'] is not None and r['worst'] <= -30)}", "",
          "## Признак 3 — правила на монете (≥ 5 сделок)", "",
          "доля в плюс на монете против той, что те же правила дают в среднем (ожидание):", ""]
    r3 = [r for r in rows if r["n"] >= 5]
    for lo, hi, lab in ((-100, -20, "ниже ожидания на 20+ п."), (-20, -10, "ниже на 10–20 п."), (-10, 10, "около ожидания ±10 п."), (10, 100, "выше на 10+ п.")):
        g = [r for r in r3 if lo <= r["win"] - r["exp"] < hi]
        Lm.append(f"- {lab}: {len(g)} монет, сумма сделок {sum(r['sum'] for r in g):+.0f}%")
    Lm += ["", "## Монеты, выбившиеся хотя бы по одному признаку (корреляция в нижних 10%, прокол ≤ −20%, правила ниже ожидания на 20+ п. при ≥ 5 сделках)", "",
           "| монета | корр. с доской | свои крупные ходы | худший прокол | проколов ≤ −20% | выкуп за 6 ч / часов | сделок · в плюс / ожидание · сумма | признаков |",
           "|---|---|---|---|---|---|---|---|"]
    c10 = q(cs, .1)
    out = []
    for r in rows:
        f1 = r["corr"] <= c10
        f2 = r["worst"] is not None and r["worst"] <= -20
        f3 = r["n"] >= 5 and r["win"] is not None and r["win"] - r["exp"] <= -20
        k = f1 + f2 + f3
        if k:
            out.append((k, r, f1, f2, f3))
    out.sort(key=lambda x: (-x[0], x[1]["worst"] or 0))
    for k, r, f1, f2, f3 in out[:80]:
        Lm.append(f"| {r['sym'][:-4]} | {r['corr']:.2f}{' ◆' if f1 else ''} | {r['own_big']}% | {(str(round(r['worst'])) + '%') if r['worst'] is not None else '—'}{' ◆' if f2 else ''} | {r['n20']} | "
                  f"{(str(r['rec']) + '% / ' + str(r['rec_h'])) if r['rec'] is not None else '—'} | "
                  f"{(str(r['n']) + ' · ' + str(r['win']) + '% / ' + str(r['exp']) + '% · ' + format(r['sum'], '+.1f') + '%') if r['n'] else '—'}{' ◆' if f3 else ''} | {k} |")
    Lm += ["", f"По признакам: только 1-й {sum(1 for x in out if x[2] and x[0] == 1)}, только 2-й {sum(1 for x in out if x[3] and x[0] == 1)}, только 3-й "
           f"{sum(1 for x in out if x[4] and x[0] == 1)}, два {sum(1 for x in out if x[0] == 2)}, все три {sum(1 for x in out if x[0] == 3)}.",
           f"_Посчитано за {time.time() - t0:.0f} с._"]
    (HERE / "own_life.md").write_text("\n".join(Lm) + "\n", encoding="utf-8")
    print("\n".join(Lm[:26])); print("…"); print("\n".join(Lm[-3:]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
