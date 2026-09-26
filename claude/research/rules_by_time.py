#!/usr/bin/env python3
"""ВСЕ ВХОДЫ РЕЕСТРА НА ТРЁХМИНУТКАХ ЛИДЕРОВ ЗА 14 ДН, ПО ВРЕМЕНИ (26.09, владелец: «прогони все известные стратегии кроме
"три подряд"; где работает — пиши время, где нет — тоже; таблица по дням недели и датам»; «входы, выходы, стопы решай сам»).
Данные: cq_v2/hist3m/<монета>.json (hist3m.py): [t, o, h, l, c, qv, taker_buy_q, oi_usd, funding_pct, crowd_ls, top_ls] по 3 мин.
Правила и мои выходы (обоснование — счёт реестра, claude/research/rules.md):
  R34 интерес   — интерес +15% за 3 ч при цене не ниже, чем 3 ч назад, толпа < 1.5 → лонг; цель +10% (R34: мерная цель), стоп −5%, 24 ч
  R39 всплеск   — 3м объём ≥ ×5 медианы 30 баров и ≥ 50K$, бар ≥ +1%, интерес за час растёт → лонг; цель +5%, стоп −5%, 2 ч (класс владельца)
  R27 слом      — ход 48 ч ≥ +70%, закрытие ≤ 0.85 × макс 24 ч (первый бар) → шорт; цель 0.75 × макс 24 ч (R4), стоп +12% (медиана встряски), 48 ч
  R21 вынос     — бар ≥ +4% при ходе 24 ч ≥ +30% и интерес на баре −2% (шорты сгорели) → шорт; цель −8%, стоп +6%, 12 ч
  R36 фандинг+  — фандинг ≥ +0.05% при ходе 24 ч ≥ +15% → шорт на выплате; цель −6% (медиана R36), стоп +8%, 48 ч
  R14 фандинг−  — фандинг ≤ −0.30% и цена выше минимума 6 ч (отскок держится) → лонг; цель +10%, стоп −6%, 24 ч
  R38 второй    — первая нога (макс 14 дн ≥ +40% от минимума 7 дн до него), база ≥ 1 дн, −15…−50% от вершины, выше минимума после ×1.03,
                  |медиана фандинга 24 ч| ≤ 0.02, интерес сдулся ≥ 20% от вершины и +5% за час, покупатели 6 баров > 50% → лонг; цель +20%, без стопа, 4 дн
  R18 сползание — медиана фандинга 24 ч ≤ −0.05, цена ≤ 0.8 × макс 72 ч, отскок ≥ 5% от минимума 90 мин и закрытие ниже прошлого → шорт; цель −8%, стоп +6%, 24 ч
  R32 дивергенция — новый максимум 24 ч при интересе ≤ 0.8 × интереса на прошлом максимуме (≥ 6 ч назад) → лонг; цель +10%, стоп −5%, 24 ч
Одна позиция на правило и монету, пауза 2 ч после выхода. Время — UTC+3 (владелец).
    python3 claude/research/rules_by_time.py      # → claude/research/rules_by_time.md + rules_trades.json
"""
from __future__ import annotations
import json, statistics as st, datetime as dt
from pathlib import Path
from collections import defaultdict
BASE = Path(__file__).resolve().parents[2]
H = BASE / "cq_v2" / "hist3m"
L = dt.timezone(dt.timedelta(hours=3))
B = 20                                   # баров в часе
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]

RULES = {
    "R34 интерес":   dict(side=1,  tp=0.10, sl=0.05, hold=24 * B),
    "R39 всплеск":   dict(side=1,  tp=0.05, sl=0.05, hold=2 * B),
    "R27 слом":      dict(side=-1, tp=None, sl=0.12, hold=48 * B),
    "R21 вынос":     dict(side=-1, tp=0.08, sl=0.06, hold=12 * B),
    "R36 фандинг+":  dict(side=-1, tp=0.06, sl=0.08, hold=48 * B),
    "R14 фандинг−":  dict(side=1,  tp=0.10, sl=0.06, hold=24 * B),
    "R38 второй":    dict(side=1,  tp=0.20, sl=None, hold=96 * B),
    "R18 сползание": dict(side=-1, tp=0.08, sl=0.06, hold=24 * B),
    "R32 дивергенция": dict(side=1, tp=0.10, sl=0.05, hold=24 * B),
}


def signals(rows):
    """для каждого бара i — список (правило, целевая цена для R27) по данным ≤ i"""
    n = len(rows)
    T = [r[0] for r in rows]; C = [r[4] for r in rows]; Hh = [r[2] for r in rows]; Lw = [r[3] for r in rows]
    QV = [r[5] for r in rows]; TB = [r[6] for r in rows]; OI = [r[7] for r in rows]; F = [r[8] for r in rows]; CR = [r[9] for r in rows]
    out = defaultdict(list)
    # префиксы
    med30 = [None] * n
    for i in range(31, n):
        med30[i] = st.median(QV[i - 30:i])
    last_fund_t = None
    for i in range(96 * B, n):
        oi, c = OI[i], C[i]
        if not oi or not c:
            continue
        run24 = c / C[i - 24 * B] - 1 if C[i - 24 * B] else 0
        run48 = c / C[i - 48 * B] - 1 if C[i - 48 * B] else 0
        hi24 = max(Hh[i - 24 * B:i + 1]); lo6 = min(Lw[i - 6 * B:i + 1])
        cr = CR[i]
        # R34
        oi3 = OI[i - 3 * B]
        if oi3 and oi / oi3 - 1 >= 0.15 and c >= C[i - 3 * B] and (cr is None or cr < 1.5):
            out[i].append(("R34 интерес", None))
        # R39
        if med30[i] and QV[i] >= 5 * med30[i] and QV[i] >= 50_000 and C[i - 1] and c / C[i - 1] - 1 >= 0.01 and OI[i - B] and oi >= OI[i - B] * 1.01:
            out[i].append(("R39 всплеск", None))
        # R27
        if run48 >= 0.70 and c <= 0.85 * hi24 and C[i - 1] > 0.85 * max(Hh[i - 24 * B - 1:i]):
            out[i].append(("R27 слом", hi24 * 0.75))
        # R21
        if run24 >= 0.30 and C[i - 1] and c / C[i - 1] - 1 >= 0.04 and OI[i - 1] and oi / OI[i - 1] - 1 <= -0.02:
            out[i].append(("R21 вынос", None))
        # R36 / R14 — на баре смены фандинга
        f = F[i]
        if f is not None and F[i - 1] is not None and f != F[i - 1]:
            if f >= 0.05 and run24 >= 0.15:
                out[i].append(("R36 фандинг+", None))
            if f <= -0.30 and c > lo6 * 1.02:
                out[i].append(("R14 фандинг−", None))
        # R38 второй ход
        j0 = max(0, i - 14 * 24 * B)
        jm = max(range(j0, i + 1), key=lambda j: Hh[j])
        if i - jm >= 24 * B and jm - 7 * 24 * B >= 0:
            lo_before = min(Lw[jm - 7 * 24 * B:jm])
            top = Hh[jm]
            if lo_before and top / lo_before - 1 >= 0.40 and 0.50 <= c / top <= 0.85 and c >= min(Lw[jm:i + 1]) * 1.03:
                fm = [x for x in F[i - 24 * B:i + 1] if x is not None]
                oi_top = max(x for x in OI[max(0, jm - B):jm + B + 1] if x) if any(OI[max(0, jm - B):jm + B + 1]) else None
                if fm and abs(st.median(fm)) <= 0.02 and oi_top and min(x for x in OI[jm:i + 1] if x) <= oi_top * 0.8 and OI[i - B] and oi / OI[i - B] - 1 >= 0.05:
                    tb6 = sum(TB[i - 5:i + 1]); q6 = sum(QV[i - 5:i + 1])
                    if q6 and tb6 / q6 > 0.5:
                        out[i].append(("R38 второй", None))
        # R18 сползание
        fm24 = [x for x in F[i - 24 * B:i + 1] if x is not None]
        hi72 = max(Hh[i - 72 * B:i + 1]) if i >= 72 * B else hi24
        lo90 = min(Lw[i - 30:i])
        if fm24 and st.median(fm24) <= -0.05 and c <= 0.8 * hi72 and lo90 and C[i - 1] / lo90 - 1 >= 0.05 and c < C[i - 1]:
            out[i].append(("R18 сползание", None))
        # R32 дивергенция
        if Hh[i] >= hi24 and Hh[i] > max(Hh[i - 24 * B:i]):
            # прошлый максимум 24 ч не ближе 6 ч
            jprev = max(range(i - 24 * B, i - 6 * B), key=lambda j: Hh[j])
            if OI[jprev] and oi <= 0.8 * OI[jprev]:
                out[i].append(("R32 дивергенция", None))
    return out


def simulate(sym, rows):
    sig = signals(rows)
    n = len(rows); trades = []
    open_ = {}; last_exit = {}
    for i in range(n):
        # выходы
        for rule, pos in list(open_.items()):
            cfg = RULES[rule]; e, sd = pos["e"], cfg["side"]
            h, l, c = rows[i][2], rows[i][3], rows[i][4]
            res = why = None
            if sd == 1:
                if cfg["sl"] and l <= e * (1 - cfg["sl"]): res, why = -cfg["sl"], "стоп"
                elif cfg["tp"] and h >= e * (1 + cfg["tp"]): res, why = cfg["tp"], "цель"
            else:
                tp_px = pos["tp_px"] if pos.get("tp_px") else (e * (1 - cfg["tp"]) if cfg["tp"] else None)
                if cfg["sl"] and h >= e * (1 + cfg["sl"]): res, why = -cfg["sl"], "стоп"
                elif tp_px and l <= tp_px: res, why = e / tp_px - 1, "цель"
            if res is None and i - pos["i"] >= cfg["hold"]:
                res, why = (c / e - 1) * sd, "срок"
            if res is not None:
                t = dt.datetime.fromtimestamp(rows[pos["i"]][0] / 1000, L)
                trades.append(dict(rule=rule, sym=sym, t=t.strftime("%Y-%m-%d %H:%M"), date=t.strftime("%d.%m"), wd=WD[t.weekday()], hour=t.hour,
                                   side="лонг" if sd == 1 else "шорт", res=round(res * 100, 2), why=why, bars=i - pos["i"],
                                   crowd=rows[pos["i"]][9], fund=rows[pos["i"]][8]))
                last_exit[rule] = i; del open_[rule]
        for rule, tp_px in sig.get(i, []):
            if rule in open_ or i - last_exit.get(rule, -10**9) < 2 * B:
                continue
            open_[rule] = dict(i=i, e=rows[i][4], tp_px=tp_px)
    return trades


def main():
    trades = []
    files = sorted(H.glob("*.json"))
    for f in files:
        if f.name.startswith("_"): continue
        rows = json.loads(f.read_text())
        if len(rows) < 2000: continue
        trades += simulate(f.stem.upper() + "USDT", rows)
    (BASE / "claude/research/rules_trades.json").write_text(json.dumps(trades, ensure_ascii=False), encoding="utf-8")
    md = [f"# Правила по времени — трёхминутки {len([f for f in files if not f.name.startswith('_')])} лидеров за 14 дн (`rules_by_time.py`, {dt.datetime.now(L):%d.%m %H:%M})\n",
          "Время UTC+3. «Работает» = средний результат входов в этот час недели в плюс. Владелец 26.09: неправильных правил нет — правило описывает часть причин; "
          "час, где оно не сработало, значит, действовал фактор, которого в правиле нет (сессия, день, тема дня, праздник). Окна «не работает» — где искать этот фактор.\n"]
    def cell(tr):
        if not tr: return "—"
        avg = st.mean(x["res"] for x in tr); w = sum(1 for x in tr if x["res"] > 0)
        return f"{'✅' if avg > 0 else '❌'} {avg:+.1f}% ({w}/{len(tr)})"
    by_rule = defaultdict(list)
    for x in trades: by_rule[x["rule"]].append(x)
    md.append("## Сводка по правилам\n\n| правило | сделок | в плюс | средний | цель | стоп | срок |\n|---|---|---|---|---|---|---|")
    for r in RULES:
        tr = by_rule.get(r, [])
        if not tr: md.append(f"| {r} | 0 | — | — | — | — | — |"); continue
        md.append(f"| {r} | {len(tr)} | {sum(1 for x in tr if x['res']>0)} ({sum(1 for x in tr if x['res']>0)/len(tr)*100:.0f}%) | {st.mean(x['res'] for x in tr):+.2f}% | "
                  f"{sum(1 for x in tr if x['why']=='цель')} | {sum(1 for x in tr if x['why']=='стоп')} | {sum(1 for x in tr if x['why']=='срок')} |")
    # 26.09 23:40, владелец: «неправильных стратегий нет: работает хотя бы в 5% выборки — значит есть своё время; в стратегии берём то,
    # что в плюсе хотя бы 20% недели». Час недели = день × час; ячейка «работает», если средний результат входов в этот час > 0.
    md.append("\n## Доля недели, когда правило работает (час недели = день × час, по 14 дн)\n\n| правило | часов недели с входами | из них в плюсе | доля недели в плюсе | вердикт |\n|---|---|---|---|---|")
    verdict = {}
    for r in RULES:
        tr = by_rule.get(r, [])
        cells = defaultdict(list)
        for x in tr: cells[(x["wd"], x["hour"])].append(x["res"])
        good = [k for k, v in cells.items() if st.mean(v) > 0]
        share = len(good) / 168 * 100
        verdict[r] = "стратегия (≥20% недели)" if share >= 20 else "есть своё время (≥5%)" if share >= 5 else "мало данных" if len(cells) < 9 else "своего времени в эти 14 дн не нашло"
        md.append(f"| {r} | {len(cells)} | {len(good)} | {share:.0f}% | {verdict[r]} |")
    for r in RULES:
        tr = by_rule.get(r, [])
        if not tr: continue
        md.append(f"\n## {r} — {verdict.get(r, '')}\n")
        md.append("### По дням недели и часам входа (UTC+3), блоки по 4 часа\n\n| день | 00–04 | 04–08 | 08–12 | 12–16 | 16–20 | 20–24 |\n|---|---|---|---|---|---|---|")
        for wd in WD:
            row = [wd]
            for h0 in range(0, 24, 4):
                row.append(cell([x for x in tr if x["wd"] == wd and h0 <= x["hour"] < h0 + 4]))
            md.append("| " + " | ".join(row) + " |")
        cells = defaultdict(list)
        for x in tr: cells[(x["wd"], x["hour"])].append(x["res"])
        good = sorted([k for k, v in cells.items() if st.mean(v) > 0], key=lambda k: (WD.index(k[0]), k[1]))
        bad = sorted([k for k, v in cells.items() if st.mean(v) <= 0], key=lambda k: (WD.index(k[0]), k[1]))
        md.append("\n### Окна\n\n- **работает:** " + (", ".join(f"{d} {h:02d}:00" for d, h in good) or "—"))
        md.append("- **не работает:** " + (", ".join(f"{d} {h:02d}:00" for d, h in bad) or "—"))
        md.append("\n### По датам\n\n| дата | день | сделок | в плюс | средний | часы, когда работало | часы, когда нет |\n|---|---|---|---|---|---|---|")
        for d in sorted({x["date"] for x in tr}, key=lambda s: (s[3:], s[:2])):
            td = [x for x in tr if x["date"] == d]
            good = sorted({f"{x['hour']:02d}" for x in td if x["res"] > 0}); bad = sorted({f"{x['hour']:02d}" for x in td if x["res"] <= 0})
            md.append(f"| {d} | {td[0]['wd']} | {len(td)} | {sum(1 for x in td if x['res']>0)} | {st.mean(x['res'] for x in td):+.1f}% | {', '.join(good) or '—'} | {', '.join(bad) or '—'} |")
    (BASE / "claude/research/rules_by_time.md").write_text("\n".join(md), encoding="utf-8")
    print(f"сделок {len(trades)} по {len(by_rule)} правилам · claude/research/rules_by_time.md")
    for r in RULES:
        tr = by_rule.get(r, [])
        print(f"  {r:16} n={len(tr):4}  {cell(tr)}")


if __name__ == "__main__":
    main()
