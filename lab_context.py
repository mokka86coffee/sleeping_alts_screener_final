#!/usr/bin/env python3
"""ЧТО БЫЛО ДО И КАК ПОВЛИЯЛО (16.09; владелец: «рынок это не 2+2+2=6; если вт и ср росли, то чт-пт-сб скорее
сливные; если одна монета сделала ×5–10, дальше неделю тишина; памп в июле отличается от пампа в августе, потому
что месяц война в Иране и деньги идут мимо крипты»).

Здесь нет календарных окон. Каждый бар описывается ПРЕДЫСТОРИЕЙ, и считается, что бывает ПОСЛЕ такого состояния.

Что считается к каждому бару (только прошлое, без заглядывания вперёд):
  доска:      ход медианы за 1 / 3 / 7 / 14 дней; дней подряд вверх/вниз; размах недели против месячной нормы
              (истощение: неделя уже дала вдвое больше обычного?); доля растущих;
  концентрация: доля верхней монеты в суммарном росте доски за 3 и 7 дней — «тянет одна» (если одна забрала
              половину, доска пуста); сколько дней с последнего большого хода (≥40% за 3 дня у любой монеты);
  режим:      трое суток, |ход| / путь — флэт / рост / слив, и его длительность;
  биткоин:    ход за 1 / 7 / 14 дней, режим; отношение хода доски к ходу биткоина (альты сильнее или слабее);
  монета:     ход за 2 / 6 / 24 ч, за 3 и 7 дней, z-score, размах бара к норме, положение в своём диапазоне месяца.
ПЕРИОДЫ: полгода режется само — по недельным «отпечаткам» доски (тренд, размах, оборотная активность, доминация
одной монеты); границы печатаются с датами, чтобы владелец назвал, что было в мире.
ВЫВОД: для каждого состояния — что было ДАЛЬШЕ (12 ч / 1 день / 2 дня) для лонга и шорта, против контроля;
проверка на четырёх четвертях периода — то, что не держит знак в трёх из четырёх, отбрасывается молча;
и то же самое ВНУТРИ каждого размеченного периода — видно, меняется ли правило от состояния мира к состоянию.
Источник — hourly/*.json. `python3 lab_context.py --days 180`, `--min 200`, `--periods 6`.
"""
from __future__ import annotations

import argparse
import itertools
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

H = 3600000
D = 24 * H


def load_hourly(days: int):
    data = {}
    for p in (BASE_DIR / "hourly").glob("*.json"):
        try:
            arr = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        d = {int(b["t"]): (float(b["c"]), float(b.get("v") or 0)) for b in arr if isinstance(b, dict) and b.get("t") and b.get("c")}
        if len(d) < 400:
            continue
        keys = sorted(d)[-(days * 24 + 24 * 40):]
        data[p.stem.upper() + "USDT"] = {k: d[k] for k in keys}
    btc = data.pop("BTCUSDT", None)
    return data, btc


def reg(seq):
    """флэт / рост / слив по ряду: |ход| / путь"""
    if len(seq) < 6:
        return None
    net = seq[-1] - seq[0]
    path = sum(abs(seq[i] - seq[i - 1]) for i in range(1, len(seq))) or 1e-9
    return "флэт" if abs(net) / path < 0.25 else ("рост" if net > 0 else "слив")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--min", type=int, default=200)
    ap.add_argument("--edge", type=float, default=0.5)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--periods", type=int, default=6, help="на сколько кусков резать период по состоянию мира")
    a = ap.parse_args()
    data, btc = load_hourly(a.days)
    if not data:
        print("hourly/*.json пусто")
        return 0
    times = sorted(set(t for d in data.values() for t in d))
    px = {s: {t: v[0] for t, v in d.items()} for s, d in data.items()}
    vol = {s: {t: v[1] for t, v in d.items()} for s, d in data.items()}
    bpx = {t: v[0] for t, v in (btc or {}).items()}

    def r(d, t, hours):
        t0 = t - hours * H
        return (d[t] / d[t0] - 1) if (t in d and t0 in d) else None

    # ── ряды доски по часам
    board = {}
    for t in times:
        mv = [r(px[s], t, 24) for s in px]
        mv = [x for x in mv if x is not None]
        if len(mv) >= max(8, len(px) // 3):
            board[t] = (st.median(mv), 100 * sum(1 for x in mv if x > 0) / len(mv))
    bt_sorted = sorted(board)

    def board_ret(t, hours):
        """ход медианной монеты доски за hours: медиана поштучных ходов"""
        mv = [r(px[s], t, hours) for s in px]
        mv = [x for x in mv if x is not None]
        return st.median(mv) if len(mv) >= 8 else None

    def top_share(t, hours):
        """доля верхней монеты в суммарном РОСТЕ доски за hours — «тянет одна»"""
        gains = []
        for s in px:
            x = r(px[s], t, hours)
            if x is not None and x > 0:
                gains.append(x)
        if len(gains) < 5:
            return None
        gains.sort(reverse=True)
        return gains[0] / sum(gains)

    # ── дневные отпечатки для разметки периодов
    days_list = sorted(set(datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d") for t in times))
    day_feat = {}
    for day in days_list:
        t1 = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000) + D
        if t1 not in board:
            t1 = max((t for t in bt_sorted if t <= t1), default=None)
        if not t1:
            continue
        mv = [r(px[s], t1, 24) for s in px]
        mv = [x for x in mv if x is not None]
        if len(mv) < 8:
            continue
        day_feat[day] = {
            "доска": st.median(mv) * 100,
            "размах": (st.median([abs(x) for x in mv])) * 100,
            "растущих": 100 * sum(1 for x in mv if x > 0) / len(mv),
            "биткоин": (r(bpx, t1, 24) * 100 if bpx and r(bpx, t1, 24) is not None else 0.0),
            "одна тянет": (top_share(t1, 72) or 0) * 100,
        }
    # ── разметка периодов: недельные отпечатки, склейка похожих соседей до --periods кусков
    weeks = defaultdict(list)
    for day, f in day_feat.items():
        y, w, _ = datetime.strptime(day, "%Y-%m-%d").isocalendar()
        weeks[(y, w)].append((day, f))
    wk = []
    for key in sorted(weeks):
        days_w = weeks[key]
        wk.append({
            "нед": f"{key[0]}-{key[1]:02d}",
            "с": days_w[0][0], "по": days_w[-1][0],
            "доска": sum(d[1]["доска"] for d in days_w),
            "биткоин": sum(d[1]["биткоин"] for d in days_w),
            "размах": st.median([d[1]["размах"] for d in days_w]),
            "одна тянет": st.median([d[1]["одна тянет"] for d in days_w]),
            "растущих": st.median([d[1]["растущих"] for d in days_w]),
        })
    # склейка: пока кусков больше --periods, объединяем пару соседей с самой близкой характеристикой
    groups = [[i] for i in range(len(wk))]

    def gfeat(g):
        return (sum(wk[i]["доска"] for i in g) / len(g), sum(wk[i]["биткоин"] for i in g) / len(g),
                sum(wk[i]["размах"] for i in g) / len(g), sum(wk[i]["одна тянет"] for i in g) / len(g))

    while len(groups) > a.periods:
        best, bi = None, 0
        for i in range(len(groups) - 1):
            f1, f2 = gfeat(groups[i]), gfeat(groups[i + 1])
            dist = sum(abs(x - y) / (abs(x) + abs(y) + 1e-9) for x, y in zip(f1, f2))
            if best is None or dist < best:
                best, bi = dist, i
        groups[bi] = groups[bi] + groups[bi + 1]
        del groups[bi + 1]
    print(f"монет {len(px)} · дней {len(day_feat)} · периодов {len(groups)}\n")
    print("── ПЕРИОДЫ (машина режет сама по недельным отпечаткам; чем они были в мире — за владельцем):")
    periods = []
    for g in groups:
        s_, e_ = wk[g[0]]["с"], wk[g[-1]]["по"]
        f = gfeat(g)
        periods.append((s_, e_))
        print(f"  {s_} → {e_}  ({len(g)} нед)  доска за неделю {f[0]:+6.1f}%  биткоин {f[1]:+6.1f}%  размах дня {f[2]:.1f}%  верхняя монета берёт {f[3]:.0f}% роста")

    # ── состояния к каждому бару + что было дальше
    obs = []
    for sym, d in px.items():
        ks = sorted(d)
        for i in range(24 * 15, len(ks) - 48):
            t = ks[i]
            if t not in board:
                continue
            f = {}
            b1, b3, b7, b14 = board_ret(t, 24), board_ret(t, 72), board_ret(t, 168), board_ret(t, 336)
            if b3 is None or b7 is None:
                continue
            f["доска 1д"] = "↓" if b1 < -0.01 else "↑" if b1 > 0.01 else "ровно"
            f["доска 3д"] = "↓" if b3 < -0.03 else "↑" if b3 > 0.03 else "ровно"
            f["доска 7д"] = "↓" if b7 < -0.05 else "↑" if b7 > 0.05 else "ровно"
            if b14 is not None:
                f["доска 14д"] = "↓" if b14 < -0.08 else "↑" if b14 > 0.08 else "ровно"
            # дней подряд в одну сторону
            run = 0
            for k in range(1, 8):
                x = board_ret(t - (k - 1) * D, 24)
                if x is None:
                    break
                if k == 1:
                    sign = 1 if x > 0 else -1
                    run = 1
                elif (x > 0) == (sign > 0):
                    run += 1
                else:
                    break
            f["дней подряд"] = f"{'вверх' if sign > 0 else 'вниз'} {min(run, 4)}" if run else None
            # истощение: ход недели против медианы недельных ходов месяца
            wk_moves = [abs(board_ret(t - k * 168 * H, 168) or 0) for k in range(1, 5)]
            norm = st.median([x for x in wk_moves if x]) or 1e-9
            f["истощение"] = "×2+" if abs(b7) >= 2 * norm else "×1.5+" if abs(b7) >= 1.5 * norm else "обычно"
            ts3, ts7 = top_share(t, 72), top_share(t, 168)
            if ts3 is not None:
                f["тянет одна 3д"] = ">50%" if ts3 > .5 else "30–50%" if ts3 > .3 else "<30%"
            if ts7 is not None:
                f["тянет одна 7д"] = ">50%" if ts7 > .5 else "30–50%" if ts7 > .3 else "<30%"
            # сколько дней с последнего большого хода по доске
            last_big = None
            for k in range(0, 15):
                tt = t - k * D
                mx = max((r(px[s], tt, 72) or 0) for s in px)
                if mx >= 0.40:
                    last_big = k
                    break
            f["с последнего ×1.4"] = ("сегодня" if last_big == 0 else f"{last_big} дн" if last_big is not None and last_big <= 3 else "4–14 дн" if last_big is not None else "больше 2 нед")
            seq = [board[tt][0] for tt in bt_sorted if t - 72 * H <= tt <= t]
            f["режим доски"] = reg(seq[::6]) if len(seq) >= 36 else None
            if bpx:
                for hh, nm in ((24, "1д"), (168, "7д")):
                    x = r(bpx, t, hh)
                    if x is not None:
                        f[f"биткоин {nm}"] = "↓" if x < -0.01 * (hh / 24) else "↑" if x > 0.01 * (hh / 24) else "ровно"
                xb, xd = r(bpx, t, 168), b7
                if xb is not None and abs(xb) > 0.005:
                    f["альты к биткоину"] = "сильнее" if xd > xb else "слабее"
            r2, r6, r24 = r(d, t, 2), r(d, t, 6), r(d, t, 24)
            r3d, r7d = r(d, t, 72), r(d, t, 168)
            if r2 is not None:
                f["монета 2ч"] = "сильно ↑" if r2 >= .08 else "↑" if r2 > .02 else "сильно ↓" if r2 <= -.08 else "↓" if r2 < -.02 else "ровно"
            if r24 is not None:
                f["монета 1д"] = "сильно ↑" if r24 >= .15 else "↑" if r24 > .03 else "сильно ↓" if r24 <= -.15 else "↓" if r24 < -.03 else "ровно"
            if r7d is not None:
                f["монета 7д"] = "сильно ↑" if r7d >= .30 else "↑" if r7d > .05 else "сильно ↓" if r7d <= -.30 else "↓" if r7d < -.05 else "ровно"
            w = [d[ks[q]] for q in range(i - 20, i)]
            m = sum(w) / 20
            sd = (sum((x - m) ** 2 for x in w) / 20) ** .5 or 1e-9
            zz = (d[t] - m) / sd
            f["z20"] = "<−2" if zz < -2 else ">+2" if zz > 2 else "0"
            fw = {}
            for hh in (12, 24, 48):
                tt = t + hh * H
                if tt in d:
                    fw[hh] = (d[tt] / d[t] - 1) * 100
            if 24 not in fw:
                continue
            day = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%Y-%m-%d")
            obs.append((f, fw, t, day))
    if not obs:
        print("\nнаблюдений нет")
        return 0
    print(f"\nнаблюдений {len(obs)} · признаков {len(set(k for f, *_ in obs for k in f))}")
    q = len(obs) // 4
    ts_all = sorted(x[2] for x in obs)
    qb = [ts_all[q], ts_all[2 * q], ts_all[3 * q]]

    def quarter(t):
        return 0 if t < qb[0] else 1 if t < qb[1] else 2 if t < qb[2] else 3

    ctrl = st.median([x[1][24] for x in obs])

    def scan(pool, title, minn):
        conds = defaultdict(list)
        for f, fw, t, day in pool:
            items = [(k, v) for k, v in f.items() if v is not None]
            for it in items:
                conds[(it,)].append((fw[24], quarter(t)))
            for pair in itertools.combinations(items, 2):
                conds[pair].append((fw[24], quarter(t)))
        base = st.median([x[1][24] for x in pool]) if pool else 0
        res = []
        for cond, v in conds.items():
            if len(v) < minn:
                continue
            vals = [x[0] for x in v]
            e = st.median(vals) - base
            if abs(e) < a.edge:
                continue
            qs = defaultdict(list)
            for val, qq in v:
                qs[qq].append(val)
            signs = [1 if (st.median(x) - base) > 0 else -1 for x in qs.values() if len(x) >= max(10, minn // 8)]
            if len(signs) < 3 or abs(sum(signs)) < len(signs) - 1:      # знак держится в 3 из 4
                continue
            res.append((e, cond, len(v), st.median(vals), 100 * sum(1 for x in vals if x >= 2) / len(vals), 100 * sum(1 for x in vals if x <= -2) / len(vals), len(signs), sum(signs)))
        res.sort(key=lambda x: -abs(x[0]))
        if not res:
            print(f"\n── {title}: ничего не прошло отбор (n ≥ {minn}, край ≥ {a.edge}%, знак в 3 из 4 четвертей)")
            return
        print(f"\n── {title} · контроль {base:+.2f}% за сутки · n ≥ {minn}")
        for e, cond, n, med, up2, dn2, nq, ss in res[:a.top]:
            side = "ЛОНГ " if e > 0 else "ШОРТ "
            print(f"  {side}{' · '.join(f'{k}={v}' for k, v in cond):<62} n={n:>5} · край {e:+5.2f}% · за сутки {med:+5.2f}% · ≥+2% {up2:3.0f}% · ≤−2% {dn2:3.0f}% · четвертей {abs(ss)}/{nq}")
    scan(obs, "ВСЁ ПОЛУГОДИЕ", a.min)
    for s_, e_ in periods:
        sub = [x for x in obs if s_ <= x[3] <= e_]
        if len(sub) >= a.min * 3:
            scan(sub, f"ПЕРИОД {s_} → {e_}", max(60, a.min // 3))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
