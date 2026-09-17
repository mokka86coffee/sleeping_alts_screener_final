#!/usr/bin/env python3
"""КТО ПОШЁЛ И ПОЧЕМУ (17.09, владелец: «взять всех лидеров за каждый день и всех сравнить — что отличает ту,
что пошла на иксы»). Ничего не придумывается: все лидеры из архива, признаки на момент старта, исход после.

Эпизод: монета впервые за сутки показала ход за 24 часа ≥ LEAD_MIN (пересечение снизу) — это её старт как лидера.
Исход: за следующие OUT_H часов — максимум от старта, минимум, закрытие; «пошла» = максимум ≥ WENT_PCT.
Признаки на баре старта, только из прошлого:
  место в истории: от минимума и максимума 30 дн (и 180 дн, если есть дневной архив), дней от минимума 30 дн;
  ход: за 24 ч, за 6 ч, число лидеров ≥ LEAD_MIN на доске в тот же час (тянет одна или заходят многие);
  плечо: интерес за 24 ч к цене за 24 ч, интерес от минимума 30 дн;
  деньги: фандинг на старте и минимум за 24 ч, тейкер 24 ч, дельта 24 ч к обороту, оборот 24 ч к норме 7 дн,
          доля спота, ликвидации шортов к лонгам за 24 ч;
  поток: сигнальная клингера растёт (баров подряд), KVO над сигнальной;
  сбор: дельта покупок за 30 дн из дневного архива против нормы по месяцам (месячный пузырь), если архив есть;
  время: сессия и день недели старта.
Печатает: таблицу эпизодов по убыванию максимума и по каждому признаку — медианы у «пошли» и «отдали» и долю
пар, где признак ставит пошедшую выше отданной (0.5 — не различает, 0.8 — различает сильно).
    python3 lab_leaders.py                      # 30 дней архива
    python3 lab_leaders.py --lead 0.4 --went 1.0
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
import lab_junctions as lj

BAR = 1800
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]


def sess(t: int) -> str:
    h = datetime.fromtimestamp(t, timezone.utc).hour
    return "Сидней" if h >= 21 else "Токио" if h < 7 else "Лондон" if h < 13 else "Нью-Йорк"


def daily(base: str) -> dict | None:
    for p in (BASE_DIR / "cq_v2" / f"{base.lower()}.json", BASE_DIR / "cq_v2" / "daily" / f"{base.lower()}.json"):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def queue_index() -> dict:
    """ОЧЕРЕДЬ (17.09, владелец показал карточку AVA: 23 → 15 → 2 → 1 за сорок минут и 27 прогонов на первом):
    sym → [(t прогона, место)] из живого output/queue_log.jsonl и старых журналов _old_runs_*/queue_log.jsonl
    и QUEUE_LOG_EXTRA из core_config (пути к старым журналам, если лежат отдельно)."""
    paths = [BASE_DIR / "output" / "queue_log.jsonl"] + sorted(BASE_DIR.glob("_old_runs_*/queue_log.jsonl")) \
        + sorted(BASE_DIR.glob("_old_runs_*/output/queue_log.jsonl"))
    try:
        from core_config import QUEUE_LOG_EXTRA
        paths += [Path(x) for x in QUEUE_LOG_EXTRA]
    except ImportError:
        pass
    out: dict = {}
    for p in paths:
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                r = json.loads(line)
                t = int(datetime.strptime(r["at"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
            except (ValueError, KeyError, TypeError):
                continue
            if r.get("sym"):
                out.setdefault(str(r["sym"]).upper().replace("USDT", ""), []).append((t, r.get("place")))
    return {k: sorted(v) for k, v in out.items()}


def queue_features(q: list[tuple], t0: int) -> dict:
    """место за час до старта; минут от первого появления в очереди до первой тройки (в окне 6 ч до старта — 2 ч
    после); прогонов на первом месте в первые 2 ч после старта; None — очередь этого времени не покрывает"""
    f = {"место за час до старта": None, "минут до топ-3": None, "прогонов на 1-м за 2 ч": None}
    if not q:
        return f
    win = [(t, p) for t, p in q if t0 - 6 * 3600 <= t <= t0 + 2 * 3600]
    if not win:
        return f
    before = [(t, p) for t, p in q if t0 - 5400 <= t <= t0 - 1800 and p is not None]
    f["место за час до старта"] = before[-1][1] if before else 40           # не в очереди — условно 40-е
    first_in = next((t for t, p in win if p is not None), None)
    top3 = next((t for t, p in win if p is not None and p <= 3), None)
    if first_in is not None and top3 is not None:
        f["минут до топ-3"] = (top3 - first_in) / 60
    f["прогонов на 1-м за 2 ч"] = sum(1 for t, p in win if t0 <= t <= t0 + 2 * 3600 and p == 1)
    return f


def load(days: int) -> dict:
    since = int(datetime.now(timezone.utc).timestamp()) - days * 86400
    idx = lj.archive_index(None, since)
    out = {}
    for base, by in idx.items():
        rows = [dict(by[t], t=t) for t in sorted(by) if by[t].get("px") and by[t].get("h") and by[t].get("l")]
        if len(rows) >= 100:
            out[base] = rows
    return out


def episodes(data: dict, lead: float) -> list[dict]:
    """старты лидеров: первое пересечение хода за 24 ч вверх через lead; следующий старт той же монеты — не раньше суток"""
    eps = []
    for b, rows in data.items():
        px = [float(r["px"]) for r in rows]
        last_start = -10 ** 9
        for i in range(48, len(rows)):
            m24 = px[i] / px[i - 48] - 1
            m24p = px[i - 1] / px[i - 49] - 1 if i >= 49 else 0
            if rows[i]["t"] - rows[i - 48]["t"] > 54 * BAR:
                continue                                        # дыра в архиве больше шести баров — ход за сутки не настоящий
            if m24 >= lead and m24p < lead and i - last_start >= 48:
                eps.append({"sym": b, "i": i, "t": rows[i]["t"]})
                last_start = i
    return eps


def leaders_at(data: dict, t: int, lead: float) -> int:
    n = 0
    for rows in data.values():
        idx = {r["t"]: k for k, r in enumerate(rows)}
        k = idx.get(t)
        if k is not None and k >= 48:
            if float(rows[k]["px"]) / float(rows[k - 48]["px"]) - 1 >= lead:
                n += 1
    return n


def features(rows: list[dict], i: int, base: str, n_lead: int) -> dict:
    r = rows[i]
    px = [float(x["px"]) for x in rows]
    c = px[i]
    f: dict = {}
    lo30 = min(float(x["l"]) for x in rows[max(0, i - 1440):i + 1])
    hi30 = max(float(x["h"]) for x in rows[max(0, i - 1440):i + 1])
    f["от мин 30д %"] = (c / lo30 - 1) * 100
    f["до макс 30д %"] = (hi30 / c - 1) * 100
    k_lo = max(range(max(0, i - 1440), i + 1), key=lambda k: -float(rows[k]["l"]))
    f["дней от мин 30д"] = (rows[i]["t"] - rows[k_lo]["t"]) / 86400
    f["ход 24ч %"] = (c / px[i - 48] - 1) * 100
    f["ход 6ч %"] = (c / px[i - 12] - 1) * 100 if i >= 12 else None
    f["лидеров в тот час"] = n_lead
    ois = [float(x["oi"]) for x in rows[max(0, i - 48):i + 1] if x.get("oi")]
    if len(ois) >= 2 and ois[0]:
        oi24 = (ois[-1] / ois[0] - 1) * 100
        f["интерес 24ч %"] = oi24
        f["интерес к цене 24ч"] = oi24 / f["ход 24ч %"] if f["ход 24ч %"] else None
    oi_lo = float(rows[k_lo]["oi"]) if rows[k_lo].get("oi") else None
    if oi_lo and r.get("oi"):
        f["интерес от мин 30д %"] = (float(r["oi"]) / oi_lo - 1) * 100
    fund = r.get("funding")
    f["фандинг"] = fund
    fs = [x.get("funding") for x in rows[max(0, i - 48):i + 1] if x.get("funding") is not None]
    f["фандинг мин 24ч"] = min(fs) if fs else None
    f["тейкер 24ч"] = r.get("taker24")
    vol24 = sum(float((x.get("fut") or {}).get("b") or 0) + float((x.get("fut") or {}).get("s") or 0) for x in rows[max(0, i - 47):i + 1])
    d24 = sum(float((x.get("fut") or {}).get("d") or 0) for x in rows[max(0, i - 47):i + 1])
    f["дельта 24ч к обороту %"] = (d24 / vol24 * 100) if vol24 else None
    if i >= 384:
        vols = [sum(float((x.get("fut") or {}).get("b") or 0) + float((x.get("fut") or {}).get("s") or 0) for x in rows[j - 47:j + 1])
                for j in range(i - 336, i - 47, 48)]
        med = st.median(vols) if vols else None
        f["оборот 24ч к норме 7д"] = (vol24 / med) if med else None
    sp = r.get("spot") or {}
    fu = r.get("fut") or {}
    sv, fv = float(sp.get("b") or 0) + float(sp.get("s") or 0), float(fu.get("b") or 0) + float(fu.get("s") or 0)
    f["доля спота %"] = (sv / (sv + fv) * 100) if (sv + fv) else None
    lq = r.get("liq24") or {}
    if lq.get("long") and lq.get("short") is not None:
        f["ликв шортов к лонгам"] = float(lq["short"]) / float(lq["long"]) if float(lq["long"]) else None
    bars = [(x["t"], float(x["h"]), float(x["l"]), float(x["px"]), float((x.get("fut") or {}).get("b") or 0) + float((x.get("fut") or {}).get("s") or 0)) for x in rows[:i + 1]]
    kl = lj.klinger_lines(bars)
    ts = [b[0] for b in bars]
    if ts[-1] in kl:
        k, s = kl[ts[-1]]
        f["KVO над сигнальной"] = 1 if k > s else 0
        n = 0
        for j in range(len(ts) - 1, 0, -1):
            if ts[j] in kl and ts[j - 1] in kl and kl[ts[j]][1] > kl[ts[j - 1]][1]:
                n += 1
            else:
                break
        f["сигнальная растёт, баров"] = n
    d = daily(base)
    if d:
        tr = sorted((x for x in (d.get("trade") or []) if x.get("datetime")), key=lambda x: x["datetime"])
        t0 = datetime.fromtimestamp(rows[i]["t"], timezone.utc).strftime("%Y-%m-%d")
        tr = [x for x in tr if x["datetime"][:10] < t0]
        if len(tr) >= 90:
            dd = [float(x.get("quote_buy_volume") or 0) - float(x.get("quote_sell_volume") or 0) for x in tr]
            months = [sum(dd[j:j + 30]) for j in range(len(dd) - 30, -1, -30)][::-1]
            if len(months) >= 3:
                cur, prev = months[-1], months[:-1]
                sd = st.pstdev(prev) or 1.0
                f["месячный пузырь σ"] = (cur - st.mean(prev)) / sd
        oh = sorted((x for x in (d.get("ohlcv") or []) if x.get("datetime") and x["datetime"][:10] < t0), key=lambda x: x["datetime"])
        if len(oh) >= 60:
            lo180 = min(float(x["low"]) for x in oh[-180:])
            hi180 = max(float(x["high"]) for x in oh[-180:])
            f["от мин 180д %"] = (c / lo180 - 1) * 100
            f["до макс 180д %"] = (hi180 / c - 1) * 100
    f["сессия"] = sess(rows[i]["t"])
    f["день"] = WD[datetime.fromtimestamp(rows[i]["t"], timezone.utc).weekday()]
    return f


def outcome(rows: list[dict], i: int, out_h: int) -> dict:
    c = float(rows[i]["px"])
    seg = rows[i + 1:i + 1 + out_h * 2]
    if len(seg) < 4:
        return {}
    return {"макс %": (max(float(x["h"]) for x in seg) / c - 1) * 100, "мин %": (min(float(x["l"]) for x in seg) / c - 1) * 100,
            "закрытие %": (float(seg[-1]["px"]) / c - 1) * 100, "часов": len(seg) / 2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--lead", type=float, default=0.20, help="ход за 24 ч, с которого монета — лидер")
    ap.add_argument("--went", type=float, default=0.50, help="максимум за исход, с которого «пошла»")
    ap.add_argument("--out-h", type=int, default=48)
    a = ap.parse_args()
    data = load(a.days)
    Q = queue_index()
    eps = episodes(data, a.lead)
    table = []
    for e in eps:
        rows = data[e["sym"]]
        o = outcome(rows, e["i"], a.out_h)
        if not o:
            continue
        f = features(rows, e["i"], e["sym"], leaders_at(data, e["t"], a.lead))
        f.update(queue_features(Q.get(e["sym"], []), e["t"]))
        table.append({"sym": e["sym"], "t": e["t"], "went": o["макс %"] >= a.went * 100, **o, **f})
    table.sort(key=lambda x: -x["макс %"])
    hm = lambda t: datetime.fromtimestamp(t, timezone.utc).strftime("%d.%m %H:%M")
    print(f"монет {len(data)} · лидеров-эпизодов {len(table)} · старт при ходе 24ч ≥ {a.lead * 100:.0f}% · «пошла» при максимуме ≥ {a.went * 100:.0f}% за {a.out_h} ч")
    cols = ["макс %", "мин %", "закрытие %", "ход 24ч %", "от мин 30д %", "до макс 30д %", "дней от мин 30д", "интерес 24ч %", "интерес к цене 24ч",
            "интерес от мин 30д %", "фандинг", "фандинг мин 24ч", "тейкер 24ч", "дельта 24ч к обороту %", "оборот 24ч к норме 7д", "доля спота %",
            "ликв шортов к лонгам", "сигнальная растёт, баров", "KVO над сигнальной", "лидеров в тот час", "месячный пузырь σ", "от мин 180д %", "до макс 180д %",
            "место за час до старта", "минут до топ-3", "прогонов на 1-м за 2 ч"]
    print("\nЭПИЗОДЫ")
    print(f"{'монета':9s} {'старт':12s} {'пошла':5s} " + " ".join(f"{c[:12]:>12s}" for c in cols) + "  сессия день")
    for x in table:
        cells = []
        for c in cols:
            v = x.get(c)
            cells.append(f"{v:12.1f}" if isinstance(v, (int, float)) else f"{'—':>12s}")
        print(f"{x['sym']:9s} {hm(x['t']):12s} {'ДА' if x['went'] else '·':5s} " + " ".join(cells) + f"  {x['сессия']} {x['день']}")
    went = [x for x in table if x["went"]]
    stay = [x for x in table if not x["went"]]
    print(f"\nПОШЛИ {len(went)} · ОТДАЛИ {len(stay)} · что отличает (медиана у пошедших / у отданных · доля пар, где признак ставит пошедшую выше)")
    sep = []
    for c in cols[3:]:
        a_ = [x[c] for x in went if isinstance(x.get(c), (int, float))]
        b_ = [x[c] for x in stay if isinstance(x.get(c), (int, float))]
        if len(a_) < 3 or len(b_) < 3:
            continue
        pairs = sum(1 for u in a_ for v in b_ if u > v) + 0.5 * sum(1 for u in a_ for v in b_ if u == v)
        auc = pairs / (len(a_) * len(b_))
        sep.append((abs(auc - 0.5), c, st.median(a_), st.median(b_), auc, len(a_), len(b_)))
    sep.sort(key=lambda x: -x[0])
    for _, c, ma, mb, auc, na, nb in sep:
        print(f"  {c:26s} {ma:10.2f} / {mb:10.2f} · {auc:.2f}  (n {na}/{nb})" + ("   ← различает" if abs(auc - 0.5) >= 0.2 else ""))
    for c in ("сессия", "день"):
        print(f"  {c}: пошли — " + ", ".join(f"{k} {v}" for k, v in sorted(((k, sum(1 for x in went if x[c] == k)) for k in set(x[c] for x in went)), key=lambda x: -x[1]))
              + " · отдали — " + ", ".join(f"{k} {v}" for k, v in sorted(((k, sum(1 for x in stay if x[c] == k)) for k in set(x[c] for x in stay)), key=lambda x: -x[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
