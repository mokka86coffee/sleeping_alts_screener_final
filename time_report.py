#!/usr/bin/env python3
"""ОТЧЁТ ПО ВРЕМЕНИ ВХОДА (30.09, владелец: «ворота скроют, где сделки уходят в минус — время только записываем и смотрим по данным»).
Все закрытые сделки обоих книг (по каждой отдельно) с фоном входа (`fon`: час, сессия, день недели — пишет бот): результат по часу, сессии и дню недели, отдельно лонги и шорты.
Ничего не решает и в бота не влияет. Показывать группы n ≥ 10; выводы по дням и сессиям — не раньше ~14.10 (слово владельца).
    .venv/bin/python time_report.py   → output/time_report.md"""
import json, collections
from pathlib import Path
from datetime import datetime, timezone, timedelta
ROOT = Path(__file__).resolve().parent; L = timezone(timedelta(hours=3))
R = []
for b, f in (("всплеск/вынос", "paper_fast3.jsonl"), ("пробуждение", "paper_wake.jsonl")):
    R += [(b, json.loads(l)) for l in open(ROOT / "output" / f)]
ent = {(b, r["sym"], round(r["at"], 1)): r for b, r in R if r.get("kind") == "entry"}
D = []
for b, r in R:
    if str(r.get("kind", "")).startswith("exit"):
        e = ent.get((b, r["sym"], round(r["opened_at"], 1)))
        if e:
            t = datetime.fromtimestamp(r["opened_at"], L); fon = e.get("fon") or {}
            bd = fon.get("board24"); bd = None if bd is None else ("доска 24 ч < −1%" if bd < -1 else "доска 24 ч −1…0%" if bd < 0 else "доска 24 ч 0…+1%" if bd < 1 else "доска 24 ч ≥ +1%")
            D.append(dict(b=b, side=r["side"], res=r["result_pct"], usd=r["usd"], bd=bd, h=t.hour, wd=fon.get("wd") or ("пн", "вт", "ср", "чт", "пт", "сб", "вс")[t.weekday()],
                          ses=("Сидней" if t.hour < 3 else "Токио" if t.hour < 10 else "Лондон" if t.hour < 16 else "Нью-Йорк")))   # сессия — по часу входа UTC+3 (поле fon.sessions пишет список пересекающихся сессий — не годится)
def line(g):
    if len(g) < 10: return f"n={len(g)} — мало"
    return f"n={len(g)} · в плюсе {sum(1 for d in g if d['res'] > 0) * 100 // len(g)}% · {sum(d['usd'] for d in g):+.0f} $ · средняя {sum(d['res'] for d in g) / len(g):+.2f}%"
md = [f"# Результат по времени входа ({datetime.now(L):%d.%m %H:%M}) — {len(D)} закрытых сделок", "", "Только запись. Группы n ≥ 10. Сессии/дни недели — разбор ~14.10.", ""]
D2 = D; D = [d for d in D if d["bd"] is not None]
md += ["## Доска за 24 ч на входе (медиана всех монет; по лидерам: их старты — при доске −, вершины — при доске +)", "", "| группа | все | лонги | шорты |", "|---|---|---|---|"]
for k in ("доска 24 ч < −1%", "доска 24 ч −1…0%", "доска 24 ч 0…+1%", "доска 24 ч ≥ +1%"):
    g = [d for d in D if d["bd"] == k]
    md.append(f"| {k} | {line(g)} | {line([d for d in g if d['side'] == 1])} | {line([d for d in g if d['side'] == -1])} |")
md.append(""); D = D2
for title, key in (("Сессия входа", "ses"), ("День недели", "wd"), ("Час входа (UTC+3)", "h")):
    md += [f"## {title}", "", "| группа | все | лонги | шорты |", "|---|---|---|---|"]
    for k in sorted({d[key] for d in D}, key=lambda x: (str(x).zfill(2) if key == "h" else str(x))):
        g = [d for d in D if d[key] == k]
        md.append(f"| {k} | {line(g)} | {line([d for d in g if d['side'] == 1])} | {line([d for d in g if d['side'] == -1])} |")
    md.append("")
(ROOT / "output" / "time_report.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md[:24]))
