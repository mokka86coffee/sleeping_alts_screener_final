"""ЛАБОРАТОРИЯ ВЕРШИН: «подхват без нового максимума» (19.09, случай LSK).

Правило владельца, прочитанное на LSK и поправленное на ONE (19.09): пока подхват стыка ставит новый максимум —
лестница. Подхват с ПЛЮСОВОЙ дельтой без нового максимума — раздача в спрос: деньги приходят, рука отдаёт в каждого,
кто откупает стык. Два таких за сутки — хедж (LSK: Сидней 13.09 и Токио 14.09 — за 8–13 часов до слива). Стык без
максимума с МИНУСОВОЙ дельтой — не раздача, а пауза: покупателей нет, раздавать некому, рука ждёт (ONE 18.09 —
три паузы подряд, потом второй акт +36%; по старому правилу «два подряд» ONE хеджировалась бы утром 18.09 и
пропустила бы второй акт). Дельта должна быть ЗНАЧИМОЙ — не меньше PICK_DELTA_NORM_X обычных баров монеты (норма —
медиана бара за неделю до стыка): у AKE 17.09 два стыка с +6K и +27K считались раздачей, и по грубому правилу она
хеджировалась бы перед +30%; к норме бара это ×0.09 и ×0.01, у LSK — ×4.4 и ×4.0, у ONE — ×5.6.

Считает по всему архиву получасовок: каждое открытие сессии — подхватила ли сессия (три бара: оборот от нормы,
цена вверх, плечо ИЛИ дельта) и поставила ли новый максимум до следующего открытия. Дальше по каждому событию —
что цена сделала через 6, 12 и 24 бара и против медианы доски, отдельно для «подхват без максимума ×1», «×2 подряд»,
«×3+», «подхват с максимумом», «не подхватил». Ничего не ставит в правила — печатает таблицу.

    python3 lab_pick_top.py --only LSK
    python3 lab_pick_top.py
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import PICK_DELTA_NORM_X
except ImportError:
    PICK_DELTA_NORM_X = 1.0   # раздача — если дельта стыка не меньше стольких обычных баров монеты (AKE 19.09: +6K и +27K — шум)
ARCH = next((p for p in (BASE_DIR / "cq_v2" / "intraday", Path("cq_v2") / "intraday") if p.exists()), None)
SESS = [(21, "Сидней"), (0, "Токио"), (7, "Лондон"), (13, "Нью-Йорк")]
H = [6, 12, 24]


def load(sym):
    p = ARCH / f"{sym.lower()}.jsonl"
    rows = []
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("px") and r.get("candle"):
            r["t"] = datetime.fromisoformat(r["candle"].replace("Z", "+00:00"))
            rows.append(r)
    rows.sort(key=lambda r: r["t"])
    return rows


qv = lambda x: float((x.get("kv") or {}).get("qv") or 0)
dl = lambda x: float((x.get("fut") or {}).get("d") or 0)
med = lambda v: st.median(v) if v else None


def events(rows):
    """по каждому открытию сессии: (t, i, label, streak)"""
    if len(rows) < 100:
        return []
    idx = {x["t"]: i for i, x in enumerate(rows)}
    opens = []
    d0 = rows[0]["t"].replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    while d0 <= rows[-1]["t"]:
        for h, nm in SESS:
            opens.append((d0 + timedelta(hours=h), nm))
        d0 += timedelta(days=1)
    opens = sorted(o for o in opens if rows[0]["t"] < o[0] < rows[-1]["t"])
    out = []
    streak = 0
    for k, (t, nm) in enumerate(opens):
        i = idx.get(t)
        if i is None or i < 50 or i + 3 >= len(rows):
            continue
        nxt = opens[k + 1][0] if k + 1 < len(opens) else rows[-1]["t"]
        prev_hi = max(float(x["px"]) for x in rows[max(0, i - 48):i])
        seg = rows[i:i + 3]
        px0, px1 = float(rows[i - 1]["px"]), float(seg[-1]["px"])
        norm = med([qv(x) for x in rows[max(0, i - 336):i] if qv(x) > 0]) or 0
        volx = (sum(qv(x) for x in seg) / (3 * norm)) if norm else 0
        delta = sum(dl(x) for x in seg)
        oi0, oi1 = float(rows[i - 1].get("oi") or 0), float(seg[-1].get("oi") or 0)
        oich = (oi1 / oi0 - 1) * 100 if oi0 and oi1 else 0
        pxch = (px1 / px0 - 1) * 100
        ok = volx >= 1 and pxch > 0 and (oich > 0 or delta > 0)
        sess_hi = max(float(x.get("h") or x["px"]) for x in rows if t <= x["t"] < nxt)
        newhi = sess_hi > prev_hi
        # раздача считается за СУТКИ (четыре стыка), а не подряд: паузы между раздачами их не обнуляют
        recent = [e for e in out if (t - e["t"]).total_seconds() <= 24 * 3600 and e["kind"] == "раздача"]
        if newhi and ok:
            kind = "лестница"
        elif ok and delta >= PICK_DELTA_NORM_X * norm:
            kind = "раздача"
        elif ok and delta > 0:
            kind = "пауза"                                        # подхват есть, но дельта пустая — шум, не раздача
        elif not newhi and delta <= 0:
            kind = "пауза"
        else:
            kind = "не подхватил"
        n_day = len(recent) + (1 if kind == "раздача" else 0)
        label = {"лестница": "лестница: подхват с максимумом", "пауза": "пауза: без максимума, дельта не тянет",
                 "не подхватил": "не подхватил"}.get(kind) or ("раздача ×1 за сутки" if n_day == 1 else "раздача ×2 за сутки → хедж" if n_day == 2 else "раздача ×3+ за сутки")
        base3 = min(float(x["px"]) for x in rows[max(0, i - 144):i + 1])     # основание за трое суток — чтобы делить по ходу
        run = (float(rows[i]["px"]) / base3 - 1) * 100 if base3 else 0
        out.append(dict(t=t, i=i + 2, sess=nm, kind=kind, label=label, streak=n_day if kind == "раздача" else 0, pxch=pxch, delta=delta, oich=oich, volx=volx, run=run, dnorm=(delta / norm if norm else 0)))
    return out


# СЛОВА НА ЭКРАНЕ (19.09, владелец): лестница = «подхватили», пауза = «ожидание», не подхватил = «не подхватили»,
# раздача — как есть. Внутри модуля kind остаётся прежним, наружу — WORD. Объяснение каждого — EXPLAIN, при наведении.
WORD = {"лестница": "подхватили", "раздача": "раздача", "пауза": "ожидание", "не подхватил": "не подхватили"}
EXPLAIN = {
    "лестница": "сессия приняла пробу: оборот от нормы, цена вверх и новый максимум — ведут дальше",
    "раздача": "сессия приняла деньгами (дельта не меньше обычного бара монеты), но максимума нет — рука отдаёт в каждого, кто откупает стык; число — сколько денег к обычному бару",
    "пауза": "максимума нет и денег не пришло — рука ждёт, цену отпустили до следующего открытия",
    "не подхватил": "оборот ниже нормы или цена вниз — сессия пробу не приняла",
}
# ЧТО ДЕЛАТЬ (вторая строка): по последнему стыку, правилами владельца; числа лаборатории — в NUMBERS, при наведении
ACTION = {
    ("лестница", True): "держать · тряска после ступени — покупка, по ней не хеджировать",
    ("лестница", False): "подхватили · смотреть, поставит ли следующая сессия максимум",
    ("раздача", 1): "следить · вторая раздача за сутки — хедж на часть",
    ("раздача", 2): "хедж на часть · снять, когда сессия подхватит с новым максимумом",
    ("пауза", True): "хедж до следующего стыка · снять, если подхватят",
    ("пауза", False): "цену отпустили до следующего открытия · ждать стык",
    ("не подхватил", True): "цену отпустили до следующего открытия · ждать стык",
    ("не подхватил", False): "цену отпустили до следующего открытия · ждать стык",
}
NUMBERS = {   # по лаборатории 19.09 (16 608 стыков; на ходу — 71/101/82): ход к доске за 3/6/12 ч · худшая · доля глубже −10%
    ("лестница", False): "по доске +0.4…+0.6% к доске, худшая −2.5%",
    ("лестница", True): "на ходу +0.8…+3.3% к доске, но худшая точка −12% и половина случаев за сутки уходит глубже −10",
    ("раздача", False): "−0.6…−1.0% к доске; вторая за сутки — −3% и каждый шестой случай глубже −10",
    ("раздача", True): "на ходу случаев мало (11), читать как по доске",
    ("пауза", False): "по доске ноль",
    ("пауза", True): "на ходу −2…−3.5% к доске, 40–54% случаев глубже −10",
    ("не подхватил", False): "по доске +0.3%",
    ("не подхватил", True): "на ходу +1.8…+2% к доске, худшая −8%",
}


def word(kind: str) -> str:
    return WORD.get(kind, kind)


def action(kind: str, run: float, streak: int = 0, run_min: float = 60.0) -> str:
    if kind == "раздача":
        return ACTION[("раздача", 2 if streak >= 2 else 1)]
    return ACTION.get((kind, run >= run_min), "")


def numbers(kind: str, run: float, run_min: float = 60.0) -> str:
    return NUMBERS.get((kind, run >= run_min), "")


def expect(kind: str, run: float, run_min: float = 60.0) -> str:
    """совместимость: раньше одна строка с числами — теперь то же, что numbers()"""
    return numbers(kind, run, run_min)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--min-n", type=int, default=20)
    ap.add_argument("--leaders", action="store_true", help="только стыки на ходу: цена от основания за трое суток ≥ RUN_MIN")
    ap.add_argument("--run-min", type=float, default=60.0)
    a = ap.parse_args()
    if ARCH is None:
        print("нет cq_v2/intraday"); return
    syms = ([x.strip().upper().replace("USDT", "") for x in a.only.split(",")] if a.only
            else sorted(p.stem.upper() for p in ARCH.glob("*.jsonl")))
    allev = {}; series = {}
    for s in syms:
        try:
            rows = load(s)
        except OSError:
            continue
        ev = events(rows)
        if a.leaders:
            ev = [e for e in ev if e["run"] >= a.run_min]          # разрез по лидерам (11.09: индикаторы считать на ходах, не на всей истории)
        if not ev:
            continue
        for e in ev:
            for n in H:
                j = e["i"] + n
                e[f"fwd{n}"] = (float(rows[j]["px"]) / float(rows[e["i"]]["px"]) - 1) * 100 if j < len(rows) else None
                e[f"max{n}"] = (max(float(x.get("h") or x["px"]) for x in rows[e["i"] + 1:j + 1]) / float(rows[e["i"]]["px"]) - 1) * 100 if j < len(rows) else None
                e[f"min{n}"] = (min(float(x.get("l") or x["px"]) for x in rows[e["i"] + 1:j + 1]) / float(rows[e["i"]]["px"]) - 1) * 100 if j < len(rows) else None
        allev[s] = ev
    if a.only:
        for s, ev in allev.items():
            print(f"── {s}")
            for e in ev[-16:]:
                print(f"  {e['t']:%d.%m %H:%M} {e['sess']:9s} ход {e['pxch']:+6.1f}% · дельта {e['delta'] / 1e3:+7.0f}K (×{e['dnorm']:.1f} нормы) · плечо {e['oich']:+6.1f}% · оборот ×{e['volx']:4.1f}  → {e['label']}"
                      + (f" · через 12 б {e['fwd12']:+.1f}%" if e.get('fwd12') is not None else ""))
        if len(allev) == 1:
            return
    # контроль — медиана доски по каждому открытию и горизонту
    board = {}
    for s, ev in allev.items():
        for e in ev:
            for n in H:
                if e.get(f"fwd{n}") is not None:
                    board.setdefault((e["t"], n), []).append(e[f"fwd{n}"])
    board = {k: st.median(v) for k, v in board.items() if len(v) >= 8}
    groups = {}
    for s, ev in allev.items():
        for e in ev:
            groups.setdefault(e["label"], []).append(e)
    print(f"\nмонет {len(allev)} · открытий сессий {sum(len(v) for v in allev.values())}" + (f" · только на ходу от +{a.run_min:.0f}% за трое суток" if a.leaders else "") + "\n")
    head = f"  {'случай':36s}{'N':>6s}" + "".join(f"{'ход ' + str(n) + 'б':>9s}{'vs доски':>9s}{'худшая':>8s}{'≤−10%':>7s}" for n in H)
    print(head)
    for label in ("лестница: подхват с максимумом", "раздача ×1 за сутки", "раздача ×2 за сутки → хедж", "раздача ×3+ за сутки", "пауза: без максимума, дельта не тянет", "не подхватил"):
        g = groups.get(label) or []
        if len(g) < a.min_n:
            print(f"  {label:36s}{len(g):6d}   мало случаев"); continue
        line = f"  {label:36s}{len(g):6d}"
        for n in H:
            f = [e[f"fwd{n}"] for e in g if e.get(f"fwd{n}") is not None]
            rel = [e[f"fwd{n}"] - board[(e["t"], n)] for e in g if e.get(f"fwd{n}") is not None and (e["t"], n) in board]
            mn = [e[f"min{n}"] for e in g if e.get(f"min{n}") is not None]
            bad = sum(1 for x in mn if x <= -10) / len(mn) * 100 if mn else 0
            line += f"{(med(f) or 0):>8.2f}%{(med(rel) or 0):>8.2f}%{(med(mn) or 0):>7.1f}%{bad:>6.0f}%"
        print(line)
    print("\n  читать: «vs доски» — против медианы всех открытий того же часа; «худшая» — медиана худшей точки за окно; «≤−10%» — доля, где худшая точка ушла на десять и больше")


if __name__ == "__main__":
    main()
