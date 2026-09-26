#!/usr/bin/env python3
"""СПАД ПОКУПОК КАК ВЫХОД (26.09, владелец: «ММ тянет, пока покупают, и раздаёт, когда видит спад покупок»).
На трёхминутках лидеров (cq_v2/hist3m): вершины = максимум за ±12 ч при ходе ≥ +30% от минимума 24 ч до неё.
Признак спада: доля покупателей по рынку за 6 баров (18 мин) < 50% при цене не ниже 3% от текущего максимума хода.
Считаем: (1) у скольких вершин признак был ДО вершины и за сколько минут; (2) сколько ложных: признак был, а потом новый максимум ≥ +5%;
(3) что даёт выход по признаку против выхода по вершине и против выхода через 2 ч после вершины (в % от вершины).
    python3 claude/research/demand_fade.py
"""
from __future__ import annotations
import json, statistics as st
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
H = BASE / "cq_v2" / "hist3m"; B = 20


def tops(rows):
    Hh = [r[2] for r in rows]; Lw = [r[3] for r in rows]; n = len(rows); out = []
    i = 24 * B
    while i < n - 12 * B:
        w0, w1 = max(0, i - 12 * B), min(n, i + 12 * B)
        if Hh[i] == max(Hh[w0:w1]):
            lo = min(Lw[i - 24 * B:i])
            if lo and Hh[i] / lo - 1 >= 0.30:
                out.append(i); i += 12 * B; continue
        i += 1
    return out


def main():
    res = []
    for f in sorted(H.glob("*.json")):
        if f.name.startswith("_"): continue
        rows = json.loads(f.read_text()); n = len(rows)
        if n < 2000: continue
        QV = [r[5] for r in rows]; TB = [r[6] for r in rows]; C = [r[4] for r in rows]; Hh = [r[2] for r in rows]; Lw = [r[3] for r in rows]
        for it in tops(rows):
            top = Hh[it]
            # начало ноги: минимум 24 ч до вершины
            j0 = it - 24 * B + min(range(24 * B), key=lambda k: Lw[it - 24 * B + k])
            first_sig = None; false_sigs = 0; run_max = 0
            for i in range(j0 + 6, it + 1):
                run_max = max(run_max, Hh[i])
                q = sum(QV[i - 5:i + 1]); b = sum(TB[i - 5:i + 1])
                if q and b / q < 0.5 and C[i] >= run_max * 0.97:
                    if first_sig is None: first_sig = i
                    # ложный: после сигнала новый максимум ≥ +5% выше run_max
                    if max(Hh[i + 1:it + 1] or [0]) >= run_max * 1.05:
                        false_sigs += 1; first_sig = None      # сбрасываем: настоящий «первый» — последний, за которым не было +5%
            after2h = C[min(n - 1, it + 2 * B)]
            res.append(dict(sym=f.stem.upper(), top=top, lead_min=(it - first_sig) * 3 if first_sig is not None else None,
                            px_sig=C[first_sig] / top - 1 if first_sig is not None else None, false=false_sigs,
                            after2h=after2h / top - 1))
    n = len(res); have = [r for r in res if r["lead_min"] is not None]
    print(f"вершин {n} по {len({r['sym'] for r in res})} монетам · признак спада покупок был до вершины у {len(have)} ({len(have)/n*100:.0f}%)")
    if have:
        print(f"  опережение: медиана {st.median(r['lead_min'] for r in have):.0f} мин, четверти {sorted(r['lead_min'] for r in have)[len(have)//4]:.0f}–{sorted(r['lead_min'] for r in have)[3*len(have)//4]:.0f} мин")
        print(f"  цена в момент признака к вершине: медиана {st.median(r['px_sig'] for r in have)*100:+.1f}%")
    print(f"  ложных признаков на ногу (после них ещё +5%): медиана {st.median(r['false'] for r in res):.0f}, среднее {st.mean(r['false'] for r in res):.1f}")
    print(f"  цена через 2 ч после вершины: медиана {st.median(r['after2h'] for r in res)*100:+.1f}% от вершины")
    print(f"  выход по признаку против выхода через 2 ч после вершины: медиана разницы {st.median((r['px_sig'] - r['after2h']) for r in have)*100:+.1f} п.")
    Path(BASE / "claude/research/demand_fade.json").write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
