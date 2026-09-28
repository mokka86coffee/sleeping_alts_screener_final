#!/usr/bin/env python3
"""ФАКТЫ COINGLASS ПО КАЖДОЙ ЗАКРЫТОЙ СДЕЛКЕ БЫСТРОГО БОТА (29.09, владелец: «важен разбор всех сделок быстрого бота через коингласс —
и убыточных, и прибыльных — и предложение правок»). Цифры — выгрузка графика Coinglass (cg_review.py → cgx/<монета>_<тф>.json), все биржи.

По сделке (всё — до входа, кроме «после»):
  90д: цена входа к минимуму 90 дн (×) и к максимуму 90 дн (%); ход за 30 дн (%)          — стадия монеты (1D)
  7д: CVD фьючерсов, CVD спота, интерес — изменение за 7 дн (6h)                           — кто набирал
  базис и фандинг — медиана за 24 ч (15m)
  выносы: лонгов / шортов за 6 ч до входа и за 6 ч после — в долях от крупнейшего часа монеты за 10 дн (15m, по часам)
  итог сделки, выход.

    .venv/bin/python claude/research/trade_facts.py        # → trade_facts.json + trade_facts.md
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
L = timezone(timedelta(hours=3))


def load(sym: str, tf: str) -> list[dict]:
    f = HERE / "cgx" / f"{sym}_{tf}.json"
    if not f.exists():
        return []
    R = [r for r in json.load(open(f))["rows"] if r.get("c")]
    for r in R:
        for k in ("liq_long", "liq_short", "basis", "fund", "cvd_f", "cvd_s", "oi"):
            v = r.get(k)
            r[k] = v if isinstance(v, (int, float)) and v == v else None
    return R


def at(R: list[dict], t: float, k: str):
    """последнее значение k на барах, начатых до t"""
    v = [r[k] for r in R if r["t"] < t and r.get(k) is not None]
    return v[-1] if v else None


def hourly(R: list[dict], k: str) -> dict:
    h: dict = {}
    for r in R:
        h[int(r["t"] // 3600 * 3600)] = h.get(int(r["t"] // 3600 * 3600), 0) + (r.get(k) or 0)
    return h


def main() -> int:
    T = json.load(open(HERE / "cgr" / "trades.json"))
    out = []
    for x in T:
        s, t0 = x["sym"], x["t_in"]
        D, H6, M15 = load(s, "1D"), load(s, "360"), load(s, "15")
        f = dict(tid=f"{s[:-4]}_{datetime.fromtimestamp(t0, L):%m%d_%H%M}", sym=s, side=x["side"], res=x["res"], why=x["why"],
                 rule=x["rule"].split(" · ")[0], t_in=t0, t_out=x["t_out"], px_in=x["px_in"])
        d90 = [r for r in D if t0 - 90 * 86400 <= r["t"] < t0]
        if d90:
            f["x90"] = round(x["px_in"] / min(r["l"] for r in d90), 2)
            f["from_hi90"] = round((x["px_in"] / max(r["h"] for r in d90) - 1) * 100, 1)
        d30 = [r for r in D if r["t"] < t0 - 30 * 86400]
        if d30:
            f["ch30"] = round((x["px_in"] / d30[-1]["c"] - 1) * 100, 1)
        for k in ("cvd_f", "cvd_s", "oi"):
            a, b = at(H6, t0 - 7 * 86400, k), at(H6, t0, k)
            if a is not None and b is not None:
                f[k + "7"] = round(b - a) if k != "oi" else round((b / a - 1) * 100, 1) if a else None
        day = [r for r in M15 if t0 - 86400 <= r["t"] < t0]
        for k in ("basis", "fund"):
            v = [r[k] for r in day if r.get(k) is not None]
            if v:
                f[k] = st.median(v)
        for side in ("long", "short"):
            h = hourly(M15, "liq_" + side)
            top = max((v for t, v in h.items() if t < t0 - 6 * 3600), default=0)
            pre = sum(v for t, v in h.items() if t0 - 6 * 3600 <= t < t0)
            post = sum(v for t, v in h.items() if t0 <= t < t0 + 6 * 3600)
            f[side + "_top"] = round(top)
            f[side + "_pre"] = round(pre / top, 2) if top else None     # доля от крупнейшего часа за историю (≈10 дн)
            f[side + "_post"] = round(post / top, 2) if top else None
        out.append(f)
    json.dump(out, open(HERE / "trade_facts.json", "w"), ensure_ascii=False, indent=0)
    md = ["# Факты Coinglass по сделкам быстрого бота", "",
          "×90 — цена входа к минимуму 90 дн; от макс — % от максимума 90 дн; 30д — ход за 30 дн; CVD ф/с 7д — изменение CVD фьючерсов/спота за 7 дн "
          "(+ покупали, − продавали); OI 7д — интерес за 7 дн %; базис/фанд — медиана за сутки; вын. Л/Ш до/после — вынос лонгов/шортов за 6 ч "
          "до/после входа в долях от крупнейшего часа монеты за ~10 дн (≥1 — вынос крупнее любого часа истории).", "",
          "| сделка | сторона | итог | правило | ×90 | от макс | 30д | CVD ф 7д | CVD с 7д | OI 7д | базис | вын.Л до/после | вын.Ш до/после |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    fm = lambda v, p="": "—" if v is None else (f"{v / 1e6:+.1f}M" if p == "M" else f"{v:g}")  # noqa: E731
    for f in sorted(out, key=lambda f: f["t_in"]):
        md.append(f"| {f['tid']} | {'Л' if f['side'] == 1 else 'Ш'} | {f['res']:+.1f}% | {f['rule'][:28]} | {fm(f.get('x90'))} | {fm(f.get('from_hi90'))} | "
                  f"{fm(f.get('ch30'))} | {fm(f.get('cvd_f7'), 'M')} | {fm(f.get('cvd_s7'), 'M')} | {fm(f.get('oi7'))} | "
                  f"{'—' if f.get('basis') is None else f'{f['basis']:+.5f}'} | {fm(f.get('long_pre'))}/{fm(f.get('long_post'))} | {fm(f.get('short_pre'))}/{fm(f.get('short_post'))} |")
    (HERE / "trade_facts.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(len(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
