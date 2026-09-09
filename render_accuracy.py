#!/usr/bin/env python3
"""ЖУРНАЛ — accuracy.html (08.09): три части на одном экране.

Владелец: «журнал должен разделиться на три части. Первая — наши первые и в очереди в течение дня.
Вторая — фон: биткоин и монеты, которые растут, неважно, из нашей выборки они или нет. Третья —
дополнительные измерения». И отдельно: «в плашках по дням показывать монеты, которые были в первых,
их максимальную и минимальную цену за день, и на каких позициях они были в течение дня — примерно
так 1→3→2→1; если выпала из очереди, то точное время, и это конец прогноза».

Первая часть — из output/queue_log.jsonl (места по прогонам) и cq_v2/intraday (цены).
Вторая — из output/market_bg.jsonl: биткоин, ширина, поток, десятка лидеров биржи с отсечкой свежих
листингов и мелочи по обороту (08.09: «MEME и BONER — мемы, залистились на днях, не в счёт»).
Третья — пузыри и уровни: спорные считаются ОТДЕЛЬНОЙ группой, а не промахом анализа; при наведении
на плашку — список случаев для разбора.

    python3 render_accuracy.py            # печать сводки
    python3 render_accuracy.py --write    # → <REPORT_PATH>/accuracy.html
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

try:
    from core_paths import BASE_DIR, REPORT_PATH   # type: ignore
except Exception:  # noqa: BLE001
    BASE_DIR = Path(__file__).resolve().parent
    REPORT_PATH = BASE_DIR / "output" / "report.html"

OUTD = BASE_DIR / "output"
INTRA = BASE_DIR / "cq_v2" / "intraday"


def _jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


def _bars(sym: str) -> list[dict]:
    rows = _jsonl(INTRA / f"{sym.replace('USDT', '').lower()}.jsonl")
    rows.sort(key=lambda r: str(r.get("candle") or ""))
    return rows


SESSIONS = (("Азия", 0.0, 8.0), ("Европа", 7.0, 16.0), ("США", 13.5, 20.0))


def _session_of(hhmm: str) -> str:
    """Чья сессия в этот час (09.09, владелец: «срез сделать четыре раза в день по разным рынкам»,
    оставили Азию, Европу и США). Часы те же, что в market_bg. Пересечения Азия/Европа и
    Европа/США относим к той, что открылась позже — она и ведёт торг."""
    try:
        h = int(hhmm[:2]) + int(hhmm[3:5]) / 60
    except (ValueError, IndexError):
        return "вне сессий"
    cur = "вне сессий"
    for name, a, b in SESSIONS:
        if a <= h < b:
            cur = name
    return cur


def _bg_rows() -> list[dict]:
    """Лента фона целиком — сырая, как пишется каждый прогон."""
    rows = [r for r in _jsonl(OUTD / "market_bg.jsonl") if r.get("at")]
    rows.sort(key=lambda r: str(r.get("at")))
    return rows


_BG_CACHE: list = []


def _bg_at(day: str, hhmm: str) -> dict:
    """СОСТОЯНИЕ ФОНА НА МОМЕНТ (09.09, кнопки журнала): берём последнюю запись ленты не позже
    этого времени и раскладываем на категории. Сырая лента при этом не трогается — категории
    считаются здесь, поверх, и в любой момент их можно пересчитать иначе."""
    global _BG_CACHE
    if not _BG_CACHE:
        _BG_CACHE = _bg_rows()
    want = f"{day}T{hhmm}"
    best = None
    for r in _BG_CACHE:
        if str(r.get("at"))[:16] <= want:
            best = r
        else:
            break
    if not best:
        return {}
    btc = (best.get("btc") or {}).get("day_pct")
    br = best.get("breadth") or {}
    share = (br.get("up") / br["n"]) if br.get("n") else None
    med = (best.get("risk_on") or {}).get("median_pct")
    tk = (best.get("taker") or {}).get("day")
    ld = best.get("leader") or {}
    pumps = best.get("pumps") or []
    return {
        "btc": None if btc is None else ("падает" if btc < -0.5 else ("растёт" if btc > 0.5 else "стоит")),
        "board": None if share is None else ("узкая" if share < 0.4 else ("широкая" if share > 0.6 else "ровная")),
        "median": None if med is None else ("минус" if med < -0.3 else ("плюс" if med > 0.3 else "около нуля")),
        "taker": None if tk is None else ("продают" if tk < 0.98 else ("покупают" if tk > 1.02 else "вровень")),
        "leader": "есть" if (pumps or ld.get("pulls")) else "нет",
    }


def _part1() -> dict:
    """Монеты, побывавшие в первых: путь по местам, вход и выход, цены дня."""
    q = [r for r in _jsonl(OUTD / "queue_log.jsonl") if r.get("at") and r.get("sym")]
    q.sort(key=lambda r: (str(r["at"]), r.get("place") or 99))
    runs = sorted({r["at"] for r in q})
    by_run: dict = {}
    for r in q:
        by_run.setdefault(r["at"], {})[r["sym"]] = r
    days: dict = {}
    for k, t in enumerate(runs):
        d = days.setdefault(t[:10], {})
        for sym, row in by_run[t].items():
            pl = row.get("place")
            if not pl:
                continue
            e = d.setdefault(sym, {"path": [], "first_top": None, "gone": None, "best": 99})
            # ВРЕМЯ, ДО КОТОРОГО МЕСТО ДЕРЖАЛОСЬ (09.09, владелец: «почему не пишется место на
            # каждом прогоне, если оно одинаковое? давай время хотя бы дописывать, до какого
            # повторение»). Писать место каждый прогон — это десятки одинаковых цифр в строке.
            # Вместо этого у ступени третье поле: время последнего прогона, где она держалась.
            # Видно и путь, и сколько монета простояла на каждом месте.
            # СКОЛЬКО ПРОГОНОВ МЕСТО ДЕРЖАЛОСЬ (09.09, владелец: «в журнале в скобках писать,
            # сколько раз место повторялось рядом с номером позиции»). Четвёртое поле — счётчик
            # прогонов. IOST шёл 6→8→4→1 и встал; FF за день сменил место двадцать один раз и
            # никуда не пошёл — число повторов различает удержание и болтанку.
            # ПОЧЕМУ ПЕРЕШЛО НА ЭТО МЕСТО (09.09, владелец: «всплывашка при наведении на место —
            # почему перешло; там, где 10 раз подряд было первое, вся история, что менялось»).
            # Пятое поле ступени — числа балла на каждом прогоне внутри неё: балл, ход, интерес,
            # состояние, стадия, пузырь. По ним видно, чем этот прогон отличался от прошлого.
            _snap = {"t": t[11:16], "score": row.get("score"), "move": row.get("move_pct"),
                     "oi": row.get("oi_chg_pct"), "oi3": row.get("oi_trend_pct"),
                     "state": row.get("today"), "stage": row.get("stage"),
                     "bubble": row.get("bubble"), "mode": row.get("mode"),
                     "engine": row.get("engine"), "size": row.get("size")}
            if not e["path"] or e["path"][-1][1] != pl:
                e["path"].append([t[11:16], pl, t[11:16], 1, [_snap]])
            else:
                e["path"][-1][2] = t[11:16]
                e["path"][-1][3] = (e["path"][-1][3] if len(e["path"][-1]) > 3 else 1) + 1
                if len(e["path"][-1]) > 4:
                    e["path"][-1][4].append(_snap)
            e["best"] = min(e["best"], pl)
            if pl <= 3 and not e["first_top"]:
                e["first_top"] = t[11:16]
        if k:
            for sym in by_run[runs[k - 1]]:
                if sym not in by_run[t] and sym in d and not d[sym]["gone"]:
                    d[sym]["gone"] = t[11:16]
    out: dict = {}
    for day, coins in days.items():
        rows = []
        for sym, e in coins.items():
            if e["best"] > 3:
                continue
            b = [r for r in _bars(sym) if str(r.get("candle", ""))[:10] == day and r.get("px")]
            if not b:
                continue
            px = [r["px"] for r in b]
            t0 = e["first_top"] or e["path"][0][0]
            i0 = next((i for i, r in enumerate(b) if r["candle"][11:16] >= t0), 0)
            after = px[i0:] or px
            p_in = after[0]
            rows.append({"s": sym.replace("USDT", ""), "in": t0, "gone": e["gone"],
                         "ses": _session_of(t0), "bg": _bg_at(day, t0),
                         "path": e["path"], "px": p_in,
                         "up": round((max(after) / p_in - 1) * 100, 1),
                         "dn": round((min(after) / p_in - 1) * 100, 1),
                         "end": round((after[-1] / p_in - 1) * 100, 1)})
        rows.sort(key=lambda r: -r["up"])
        if rows:
            out[day] = rows
    return out


def _part2() -> dict:
    """Фон дня: биткоин, ширина, поток и монеты с ходом по всей бирже."""
    out: dict = {}
    for b in _jsonl(OUTD / "market_bg.jsonl"):
        if not b.get("at"):
            continue
        top = [x for x in ((b.get("leaders") or {}).get("top") or [])
               if (x.get("vol_usd") or 0) >= 5e6 and (x.get("age_days") or 0) >= 30]
        out[b["at"][:10]] = {
            "btc": b.get("btc") or {}, "breadth": b.get("breadth") or {},
            "taker": b.get("taker") or {}, "risk": (b.get("risk_on") or {}).get("appetite"),
            "top": [{"s": x["sym"].replace("USDT", ""), "p": x.get("day_pct"),
                     "v": round((x.get("vol_usd") or 0) / 1e6), "mine": x.get("mine")} for x in top[:6]],
        }
    return out


def _part3() -> dict:
    """Пузыри и уровни: спорные — отдельной группой, плюс случаи для разбора."""
    # ПО ДНЯМ, А НЕ СРАЗУ ЗА ВСЮ ИСТОРИЮ (09.09, владелец: «пузыри и уровни — один и тот же процент
    # за все дни»): раньше считалось по всему архиву и одно число показывалось на каждой вкладке.
    # Теперь каждая дата считается отдельно, плюс общий итог под ключом «все».
    syms = {r["sym"] for r in _jsonl(OUTD / "queue_log.jsonl") if r.get("sym")}
    by_day: dict = {}

    def _slot(day: str):
        return by_day.setdefault(day, {
            "res": {"ясный": {"ok": 0, "no": 0}, "сомнительный": {"ok": 0, "no": 0},
                    "обычный": {"ok": 0, "no": 0}},
            "levels": {"up": 0, "dn": 0, "none": 0}, "cases": [], "lev": []})

    res = {"ясный": {"ok": 0, "no": 0}, "сомнительный": {"ok": 0, "no": 0}, "обычный": {"ok": 0, "no": 0}}
    lv = {"up": 0, "dn": 0, "none": 0}
    cases, lev_cases = [], []
    for sym in sorted(syms):
        rows = _bars(sym)
        if not rows:
            continue
        for day in sorted({r["candle"][:10] for r in rows if r.get("candle")}):
            d = [r for r in rows if r["candle"][:10] == day and r.get("px")]
            full = [r for r in d if (r.get("fut") or {}).get("tk")]
            if len(full) < 10:
                continue
            px = [r["px"] for r in d]
            lo, hi = min(px), max(px)
            ds = [((r.get("fut") or {}).get("d") or 0) for r in full]
            mu = sum(ds) / len(ds)
            sd = (sum((x - mu) ** 2 for x in ds) / len(ds)) ** .5 or 1
            prev = None
            for i, (r, x) in enumerate(zip(full, ds)):
                oi = r.get("oi") or 0
                if abs(x - mu) >= 2 * sd:
                    p = r["px"]
                    pos = (p - lo) / (hi - lo) * 100 if hi > lo else 50
                    nxt = [full[k].get("px") for k in range(i + 1, min(i + 5, len(full)))]
                    if nxt and nxt[-1]:
                        after = (nxt[-1] / p - 1) * 100
                        oich = (oi / prev - 1) * 100 if (prev and oi) else None
                        sure = ("сомнительный" if (oich is not None and oich <= -1.5)
                                or r.get("oi_type") == "long_close"
                                else "ясный" if (oich is not None and oich >= 1.5) else "обычный")
                        buy_low, sell_hi = (x > 0 and pos <= 40), (x < 0 and pos >= 70)
                        if buy_low or sell_hi:
                            ok = (after > 0) if buy_low else (after < 0)
                            res[sure]["ok" if ok else "no"] += 1
                            case = {"s": sym.replace("USDT", ""), "d": day[5:], "t": r["candle"][11:16],
                                    "ses": _session_of(r["candle"][11:16]),
                                    "bg": _bg_at(day, r["candle"][11:16]),
                                    "sure": sure, "ok": ok, "after": round(after, 1),
                                    "oi": round(oich, 1) if oich is not None else None}
                            cases.append(case)
                            sl = _slot(day)
                            sl["res"][sure]["ok" if ok else "no"] += 1
                            sl["cases"].append(case)
                if oi:
                    prev = oi
            for r in d:
                z = r.get("zones") or {}
                if not (z.get("up") or z.get("down")):
                    continue
                p = r["px"]
                up = sorted([q for q, _w in (z.get("up") or []) if q > p])
                dn = sorted([q for q, _w in (z.get("down") or []) if q < p], reverse=True)
                fut = [x["px"] for x in d if x["candle"] > r["candle"]][:48]
                if not fut or not (up or dn):
                    break
                hit = None
                for v in fut:
                    if up and v >= up[0]:
                        hit = "up"
                        break
                    if dn and v <= dn[0]:
                        hit = "dn"
                        break
                lv[hit or "none"] += 1
                _slot(day)["levels"][hit or "none"] += 1
                _slot(day).setdefault("lev_all", []).append(
                    {"hit": hit or "none", "ses": _session_of(r["candle"][11:16]),
                     "bg": _bg_at(day, r["candle"][11:16])})
                if not hit:
                    lc = {"s": sym.replace("USDT", ""), "d": day[5:], "hit": "никуда",
                          "ses": _session_of(r["candle"][11:16]),
                          "bg": _bg_at(day, r["candle"][11:16]),
                          "up": round((up[0] / p - 1) * 100, 1) if up else None,
                          "dn": round((dn[0] / p - 1) * 100, 1) if dn else None,
                          "end": round((fut[-1] / p - 1) * 100, 1)}
                    lev_cases.append(lc)
                    _slot(day)["lev"].append(lc)
                break
    by_day["все"] = {"res": res, "levels": lv, "cases": cases, "lev": lev_cases}
    return {"res": res, "levels": lv, "cases": cases, "lev": lev_cases, "by_day": by_day}


def build_data() -> dict:
    days = _part1()
    p3 = _part3()
    rows = [r for v in days.values() for r in v]
    n = len(rows)
    mx = sum(1 for r in rows if r["up"] >= 2)
    en = sum(1 for r in rows if r["end"] >= 2)
    cost = round(statistics.median([r["up"] - r["end"] for r in rows]), 1) if rows else 0
    # СРЕЗ ПО РЫНКАМ (09.09): заходы и пузыри в разрезе Азии, Европы и США — в чью смену наши
    # монеты ходят и в чью смену работают правила.
    ses: dict = {}
    for r in rows:
        e = ses.setdefault(r.get("ses") or "вне сессий",
                           {"n": 0, "max": 0, "end": 0, "up": [], "bub_ok": 0, "bub_no": 0})
        e["n"] += 1
        e["max"] += 1 if r["up"] >= 2 else 0
        e["end"] += 1 if r["end"] >= 2 else 0
        e["up"].append(r["up"])
    for c in (p3.get("cases") or []):
        e = ses.setdefault(c.get("ses") or "вне сессий",
                           {"n": 0, "max": 0, "end": 0, "up": [], "bub_ok": 0, "bub_no": 0})
        e["bub_ok" if c["ok"] else "bub_no"] += 1
    for k, e in ses.items():
        e["max_pct"] = round(e["max"] / e["n"] * 100) if e["n"] else 0
        e["end_pct"] = round(e["end"] / e["n"] * 100) if e["n"] else 0
        e["mfe_med"] = round(statistics.median(e["up"]), 1) if e["up"] else 0
        e.pop("up", None)

    return {
        "days": days, "bg": _part2(), "ses": ses,
        "an": {"bubbles": {"ok": sum(v["ok"] for v in p3["res"].values()),
                           "no": sum(v["no"] for v in p3["res"].values())},
               "levels": p3["levels"]},
        "bub2": {"res": p3["res"], "cases": p3["cases"]},
        "an_by_day": p3.get("by_day") or {},
        "an_list": {"bub": p3["cases"], "lev": p3["lev"]},
        "sum": {"n": n, "max_n": mx, "max_pct": round(mx / n * 100) if n else 0,
                "end_n": en, "end_pct": round(en / n * 100) if n else 0, "cost": cost},
    }


CSS = """
/* СВЕТЛЫЙ НЕОМОРФИЗМ (08.09, возврат к прежнему виду с новыми вводными): мягкие выпуклые плашки,
   двойная тень — тёмная снизу-справа и белая сверху-слева, никаких рамок. */
:root{--ink:#1d2a36;--mid:#5d7285;--dim:#98abbb;--up:#12a17c;--dn:#e0644c}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;color:var(--ink);font-family:Inter,system-ui,sans-serif;font-weight:300;
 -webkit-font-smoothing:antialiased;
 background:radial-gradient(50% 40% at 15% 0%,#e9f0fb 0,transparent 60%),
  radial-gradient(45% 40% at 88% 6%,#efe9fb 0,transparent 62%),
  linear-gradient(170deg,#f2f5fb 0%,#e7ecf6 55%,#dde4f1 100%);background-attachment:fixed}
.wrap{max-width:1240px;margin:0 auto;padding:26px 20px 50px}
.plate{border-radius:28px;padding:26px 26px 18px;background:linear-gradient(160deg,#fdfeff,#eef2f9 60%,#e7edf7);
 box-shadow:12px 14px 30px rgba(120,140,175,.30),-10px -12px 26px rgba(255,255,255,.95)}
.head{display:flex;align-items:baseline;gap:12px;padding:2px 4px 18px}
.head h1{margin:0;font-size:21px;font-weight:500;letter-spacing:-.01em;color:#1d2a36}
.head s{text-decoration:none;font-size:13px;color:var(--mid)}
.days{display:flex;gap:10px;margin-left:auto}
.day{cursor:pointer;font-size:12px;padding:10px 18px;border-radius:999px;color:#5d7285;
 background:linear-gradient(160deg,#fff,#e9eef7);box-shadow:5px 6px 12px rgba(120,140,175,.25),-4px -5px 10px rgba(255,255,255,.95)}
.day.on{color:#fff;background:linear-gradient(160deg,#38455c,#1e2735)}
.cols{display:grid;grid-template-columns:1.55fr 1fr .95fr;gap:16px;align-items:start}
.box{border-radius:20px;padding:16px 17px;background:linear-gradient(160deg,#fdfeff,#eef2f9);
 box-shadow:6px 7px 16px rgba(120,140,175,.24),-5px -6px 13px rgba(255,255,255,.95)}
.cap{font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin:0 0 13px}
/* строка монеты — вдавленная дорожка с выпуклым содержимым */
.r{display:grid;grid-template-columns:84px minmax(0,1fr) 76px;gap:11px;align-items:center;
 margin-bottom:9px;padding:11px 13px;border-radius:16px;background:linear-gradient(160deg,#fff,#eef2f9);
 box-shadow:4px 5px 11px rgba(120,140,175,.20),-3px -4px 9px rgba(255,255,255,.95)}
.s{font-size:14px;font-weight:500;color:#1d2a36;line-height:1.25}
.s a.go{color:inherit;text-decoration:none;cursor:pointer;border-bottom:1px solid transparent;transition:.15s}
.s a.go:hover{color:#12a17c;border-color:rgba(18,161,124,.45)}
.s u{text-decoration:none;display:block;font-size:10px;font-weight:300;color:var(--dim);margin-top:2px}
.path{font-size:12px;color:#5d7285;font-variant-numeric:tabular-nums;white-space:nowrap;overflow-x:auto;
 scrollbar-width:none;min-width:0}
.path::-webkit-scrollbar{display:none}
.path b{font-weight:500;color:#33475a}.path i{font-style:normal;color:#b9c6d4;margin:0 4px}
.path w{font-size:8.5px;color:#a8b6c6;margin-left:2px;font-variant-numeric:tabular-nums}
.path n{font-size:10px;color:#12a17c;margin-left:1px;font-variant-numeric:tabular-nums}
.path .st{position:relative;cursor:default;padding:2px 1px;border-radius:5px;transition:.14s}
.path .st:hover{background:rgba(18,161,124,.10)}
/* ПОЧЕМУ ПЕРЕШЛО НА ЭТО МЕСТО (09.09): вся история ступени — прогон за прогоном */
#stpop{position:fixed;z-index:20;max-width:420px;padding:13px 15px;border-radius:16px;
 background:linear-gradient(160deg,#fff,#eef2f9);
 box-shadow:12px 14px 30px rgba(120,140,175,.42),-6px -8px 18px rgba(255,255,255,1);
 opacity:0;visibility:hidden;transition:.14s;pointer-events:none}
#stpop.on{opacity:1;visibility:visible}
#stpop h6{margin:0 0 8px;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--dim);font-weight:400}
#stpop .sr2{display:grid;grid-template-columns:42px 54px 1fr;gap:8px;font-size:11px;padding:5px 0;
 border-top:1px solid rgba(120,140,175,.14);color:var(--mid);font-variant-numeric:tabular-nums}
#stpop .sr2 b{color:#1d2a36;font-weight:500}
#stpop .sr2 em{font-style:normal;color:#33475a}
#stpop .up{color:var(--up)}#stpop .dn{color:var(--dn)}
.path u{text-decoration:none;color:var(--dn);font-weight:500}
.v{text-align:right;font-variant-numeric:tabular-nums;font-size:15px;font-weight:500;line-height:1.2}
.v s{text-decoration:none;display:block;font-size:10px;font-weight:400;color:var(--up)}
.up{color:var(--up)}.dn{color:var(--dn)}.flat{color:var(--mid)}
.hero{margin-bottom:14px;padding:14px 15px;border-radius:16px;background:linear-gradient(160deg,#fff,#eaeff8);
 box-shadow:inset 3px 4px 9px rgba(120,140,175,.22),inset -3px -3px 8px rgba(255,255,255,.95)}
.hero em{display:block;font-style:normal;font-size:13px;font-weight:500;color:#33475a}
.hero b{display:block;font-size:30px;font-weight:200;letter-spacing:-.02em;color:var(--up);line-height:1.2}
.hero s{text-decoration:none;font-size:11px;color:var(--dim)}
.line{display:flex;justify-content:space-between;padding:10px 2px;font-size:12.5px;color:var(--mid);
 border-bottom:1px solid rgba(120,140,175,.14)}
.line b{color:#1d2a36;font-weight:500;font-variant-numeric:tabular-nums}
.lead{display:grid;grid-template-columns:66px minmax(0,1fr) 52px;gap:10px;align-items:center;padding:8px 2px;font-size:11.5px}
.ls{font-weight:500;color:#33475a}
.g{display:block;height:8px;border-radius:999px;background:#e7ecf5;box-shadow:inset 2px 2px 5px rgba(120,140,175,.3),inset -1px -1px 3px #fff}
.g i{display:block;height:100%;border-radius:999px;background:linear-gradient(90deg,#8fd8c4,#12a17c);box-shadow:0 0 10px rgba(18,161,124,.45)}
.n{text-align:right;color:var(--mid);font-variant-numeric:tabular-nums;font-size:11px}
.an{position:relative;margin-bottom:14px;padding:16px;border-radius:18px;background:linear-gradient(160deg,#fdfeff,#eef2f9);
 box-shadow:6px 7px 16px rgba(120,140,175,.24),-5px -6px 13px rgba(255,255,255,.95);transition:.18s}
.an:hover{box-shadow:8px 9px 20px rgba(120,140,175,.3),-6px -7px 16px rgba(255,255,255,1)}
.an h4{margin:0 0 12px;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);font-weight:400}
/* ЧИСЛО ВНУТРИ КОЛЬЦА, ПОДПИСЬ РЯДОМ — В ОДНУ СТРОКУ (08.09) */
.row2{display:grid;grid-template-columns:86px 1fr;gap:14px;align-items:center}
.rw{position:relative;width:86px;height:86px}
.ring{position:absolute;inset:0;border-radius:50%;
 background:conic-gradient(from -90deg,#12a17c calc(var(--p)*1%),#e2e8f2 0);
 -webkit-mask:radial-gradient(circle,transparent 66%,#000 67%);mask:radial-gradient(circle,transparent 66%,#000 67%);
 filter:drop-shadow(2px 3px 7px rgba(18,161,124,.35))}
.ring span{display:none}
.rv{position:absolute;inset:0;display:grid;place-items:center;font-size:25px;font-weight:200;color:#1d2a36;
 line-height:1;font-variant-numeric:tabular-nums}
.rv i{font-style:normal;font-size:11px;color:var(--dim);margin-left:1px;font-weight:300}
/* КНОПКИ-ФИЛЬТРЫ (09.09, владелец: «кнопки не должны друг друга отрицать — можно выбрать
   биткоин падает и есть лидер; отрицают только внутри категории»). Фильтр НИЧЕГО не отсекает
   в данных: это срез той же истории. Состояния берутся из поля bg каждой записи — того самого,
   что пишется в ленту фона каждый прогон и рисуется приборами слева от звёзд. */
.filters{display:flex;flex-wrap:wrap;gap:8px 18px;padding:4px 6px 18px;align-items:center}
.fg{display:flex;align-items:center;gap:7px}
.fg > s{text-decoration:none;font-size:9px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);margin-right:2px}
.fb{cursor:pointer;font-size:11.5px;padding:7px 13px;border-radius:999px;color:#5d7285;
 background:linear-gradient(160deg,#fff,#e9eef7);
 box-shadow:4px 5px 10px rgba(120,140,175,.22),-3px -4px 8px rgba(255,255,255,.95);transition:.16s;white-space:nowrap}
.fb:hover{color:#33475a}
.fb.on{color:#fff;background:linear-gradient(160deg,#38455c,#1e2735);box-shadow:inset 2px 3px 7px rgba(0,0,0,.35)}
.fb em{font-style:normal;opacity:.55;margin-left:5px;font-size:10px}
.fclear{margin-left:auto;font-size:11px;color:var(--mid);cursor:pointer;text-decoration:underline}
.fnote{width:100%;font-size:11px;color:var(--mid);padding-top:2px}
.leg{font-size:11.5px;color:var(--mid);line-height:1.7}
/* СРЕЗ ПО РЫНКАМ (09.09): строка на сессию — доля по максимуму полосой, числа рядом */
.sr{display:grid;grid-template-columns:56px 1fr 44px;gap:9px;align-items:center;margin-bottom:9px}
.sr .sn{font-size:11px;font-weight:500;color:#33475a}
.sr .sb{display:block;height:8px;border-radius:999px;background:#e7ecf5;
 box-shadow:inset 2px 2px 5px rgba(120,140,175,.3),inset -1px -1px 3px #fff}
.sr .sb i{display:block;height:100%;border-radius:999px;
 background:linear-gradient(90deg,#8fd8c4,#12a17c);box-shadow:0 0 10px rgba(18,161,124,.45)}
.sr .sv{text-align:right;font-size:15px;font-weight:200;color:#1d2a36;font-variant-numeric:tabular-nums}
.sr .sv i{font-style:normal;font-size:9px;color:var(--dim);margin-left:1px}
.sr em{grid-column:1/4;font-style:normal;font-size:10px;color:var(--mid);margin-top:-3px}
.leg b{color:#1d2a36;font-weight:500}
.bars{margin-top:12px;display:grid;gap:8px}
.bl{display:grid;grid-template-columns:62px 1fr 72px;gap:9px;align-items:center;font-size:10.5px;color:var(--mid)}
.bl i{display:block;height:6px;border-radius:999px;background:linear-gradient(90deg,#f3c58a,#e39b3f);
 box-shadow:0 0 8px rgba(227,155,63,.4)}
.bl em{font-style:normal;text-align:right;font-variant-numeric:tabular-nums;color:#33475a}
.two{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:4px 0 10px}
.two em{display:block;font-style:normal;font-size:27px;font-weight:200;color:#1d2a36;line-height:1.15}
.two em i{font-style:normal;font-size:12px;color:var(--dim);margin-left:1px}
.two s{display:block;text-decoration:none;font-size:10px;color:var(--mid);margin-top:3px;line-height:1.5}
.pop{position:absolute;left:0;right:0;top:calc(100% + 8px);z-index:9;padding:14px;border-radius:18px;
 background:linear-gradient(160deg,#fff,#eef2f9);box-shadow:10px 12px 28px rgba(120,140,175,.4),-6px -7px 16px rgba(255,255,255,1);
 opacity:0;visibility:hidden;transform:translateY(-4px);transition:.16s}
.an:hover .pop{opacity:1;visibility:visible;transform:none}
.pop h5{margin:0 0 9px;font-size:9.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);font-weight:400}
.pr{display:grid;grid-template-columns:58px 44px minmax(0,1fr) 52px;gap:8px;font-size:11px;padding:6px 0;
 border-top:1px solid rgba(120,140,175,.16);color:var(--mid);font-variant-numeric:tabular-nums}
.pr b{color:#1d2a36;font-weight:500}.pr .bad{color:var(--dn)}
.sm{font-size:12px;color:var(--mid)}
.foot{margin-top:14px;padding:14px 6px 2px;font-size:12px;color:var(--dim)}
@media(max-width:980px){.cols{grid-template-columns:1fr}}
"""

JS = """
const D=__DATA__;
let DAY=Object.keys(D.days).sort().reverse()[0];
// ── КНОПКИ-ФИЛЬТРЫ ─────────────────────────────────────────────────────────────
// Внутри категории выбор один (повторный клик снимает), между категориями — «и».
// Пересчитывается ВСЁ: заходы, сводка фона и аналитика — потому что состояние лежит
// в самой записи, а не считается отдельно.
const CATS=[['btc','биткоин',['падает','стоит','растёт']],
            ['board','доска',['узкая','ровная','широкая']],
            ['median','медиана',['минус','около нуля','плюс']],
            ['taker','поток',['продают','вровень','покупают']],
            ['leader','лидер',['есть','нет']]];
let F={};
function pass(bg){ if(!bg)return !Object.keys(F).length;
  return Object.entries(F).every(([k,v])=>bg[k]===v); }
function countFor(key,val){
  const rows=(D.days[DAY]||[]);
  const test=Object.assign({},F); test[key]=val;
  return rows.filter(r=>Object.entries(test).every(([k,v])=>(r.bg||{})[k]===v)).length;
}
function drawFilters(){
  const el=document.getElementById('filters');
  el.innerHTML=CATS.map(([k,label,vals])=>
    `<div class="fg"><s>${label}</s>`+vals.map(v=>{
      const n=countFor(k,v);
      return `<div class="fb${F[k]===v?' on':''}" data-k="${k}" data-v="${v}">${v}<em>${n}</em></div>`;
    }).join('')+`</div>`).join('')
    + (Object.keys(F).length?`<span class="fclear" id="fclear">сбросить</span>`:'')
    + `<div class="fnote">${Object.keys(F).length
        ? 'фильтр показывает срез тех же данных — ничего не отсекается'
        : 'выбери состояние фона, чтобы посмотреть, как при нём работали правила'}</div>`;
  el.querySelectorAll('.fb').forEach(b=>b.onclick=()=>{
    const k=b.dataset.k, v=b.dataset.v;
    if(F[k]===v) delete F[k]; else F[k]=v;
    redraw();
  });
  const c=document.getElementById('fclear'); if(c)c.onclick=()=>{F={};redraw();};
}
function part1(){
  const rows=(D.days[DAY]||[]).filter(r=>pass(r.bg));
  document.getElementById('c1').innerHTML=rows.map(r=>{
    // место · сколько прогонов держалось · с какого по какое время (09.09, владелец)
    // место · сколько прогонов держалось · с какого по какое время; при наведении — история
    const steps=r.path.map((p,pi)=>
      `<span class="st" data-c="${r.s}" data-i="${pi}">`
      + `<b>${p[1]}</b>` + ((p[3]||1)>1 ? `<n>(${p[3]})</n>` : '')
      + `<w>${p[0]}${p[2] && p[2]!==p[0] ? '–'+p[2] : ''}</w>`
      + `</span>`);
    if(r.gone)steps.push(`<u>${r.gone}</u>`);
    const cl=r.end>1?'up':(r.end<-1?'dn':'flat');
    // КЛИК ПО ИМЕНИ — КАРТОЧКА МОНЕТЫ (09.09, владелец): тот же переход, что со звёзд,
    // coin.html#SYM; внутри оболочки — сообщением родителю, чтобы экран открылся в ней.
    return `<div class="r"><div class="s"><a class="go" data-s="${r.s}" href="coin.html#${encodeURIComponent(r.s)}">${r.s}</a><u>в первых ${r.in}</u></div>
      <div class="path">${steps.join('<i>→</i>')}</div>
      <div class="v ${cl}">${r.end>0?'+':''}${r.end}%<s>+${r.up}%</s></div></div>`;
  }).join('')||'<div class="sm">при выбранном фоне заходов не было</div>';
}
function part2(){
  // СВОДКА ПО ВЫБОРКЕ (09.09): при фильтре центр показывает фон именно тех моментов, что попали
  const rows=(D.days[DAY]||[]).filter(r=>pass(r.bg));
  if(Object.keys(F).length){
    const cnt=(k)=>{const m={};rows.forEach(r=>{const v=(r.bg||{})[k];if(v)m[v]=(m[v]||0)+1});
      return Object.entries(m).sort((a,b)=>b[1]-a[1]);};
    let h='<div class="hero"><em>выбранный фон</em><b>'+rows.length+'</b><s>заходов в срезе</s></div>';
    CATS.forEach(([k,label])=>{
      const v=cnt(k); if(!v.length)return;
      h+=`<div class="line"><span>${label}</span><b>${v.map(x=>x[0]+' '+x[1]).join(' · ')}</b></div>`;});
    document.getElementById('c2').innerHTML=h; return;
  }
  const b=D.bg[DAY];
  if(!b){document.getElementById('c2').innerHTML='<div class="sm">фон за этот день не писался</div>';return}
  const btc=b.btc||{},br=b.breadth||{},tk=b.taker||{},lead=(b.top||[])[0];
  let h='';
  if(lead)h+=`<div class="hero"><em>${lead.s}</em><b>+${(lead.p||0).toFixed(0)}%</b><s>${lead.v}M${lead.mine?' · наша':''}</s></div>`;
  h+=`<div class="line"><span>биткоин за сутки</span><b>${btc.day_pct!=null?(btc.day_pct>0?'+':'')+btc.day_pct+'%':'—'}</b></div>`;
  h+=`<div class="line"><span>биткоин за час</span><b>${btc.h1_pct!=null?(btc.h1_pct>0?'+':'')+btc.h1_pct+'%':'—'}</b></div>`;
  h+=`<div class="line"><span>растёт монет</span><b>${br.up??'—'} из ${br.n??'—'}</b></div>`;
  h+=`<div class="line"><span>поток</span><b>${tk.side??'—'} ${tk.day??''}</b></div>`;
  const mx=Math.max(10,...(b.top||[]).map(x=>x.p||0));
  h+=(b.top||[]).map(x=>`<div class="lead"><span class="ls">${x.s}</span>
    <span class="g"><i style="width:${Math.max(6,(x.p||0)/mx*100).toFixed(0)}%"></i></span>
    <span class="n">+${(x.p||0).toFixed(0)}%</span></div>`).join('');
  document.getElementById('c2').innerHTML=h;
}
function popBub(){const day=(D.an_by_day||{})[DAY]||{};
  const bad=((day.cases)||D.bub2.cases||[]).filter(x=>!x.ok&&x.sure==='ясный');if(!bad.length)return '';
  return `<div class="pop"><h5>не сработало · ${bad.length} для разбора</h5>`+bad.map(x=>
  `<div class="pr"><b>${x.s}</b><span>${x.d} ${x.t}</span><span>интерес ${x.oi>0?'+':''}${x.oi}%</span>
   <span class="bad">${x.after>0?'+':''}${x.after}%</span></div>`).join('')+`</div>`;}
function popLev(){const day=(D.an_by_day||{})[DAY]||{};
  const bad=((day.lev)||D.an_list.lev||[]).filter(x=>x.hit==='никуда');if(!bad.length)return '';
  return `<div class="pop"><h5>не дошла до полосы · ${bad.length}</h5>`+bad.map(x=>
  `<div class="pr"><b>${x.s}</b><span>${x.d}</span><span>вверх ${x.up!=null?x.up+'%':'—'} · вниз ${x.dn!=null?x.dn+'%':'—'}</span>
   <span class="bad">${x.end>0?'+':''}${x.end}%</span></div>`).join('')+`</div>`;}
function part3(){
  // ЧИСЛА ВЫБРАННОГО ДНЯ (09.09): раньше на всех вкладках стояло одно и то же — считалось по всей
  // истории сразу. Теперь берём группу открытого дня, а если её нет — общий итог.
  const day=(D.an_by_day||{})[DAY] || (D.an_by_day||{})['все'] || null;
  let R = day ? day.res : D.bub2.res;
  let lv = day ? day.levels : D.an.levels;
  if(Object.keys(F).length){
    // пузыри и уровни пересчитываются под тот же фильтр — состояние лежит в самой записи
    const cs=(D.bub2.cases||[]).filter(x=>pass(x.bg));
    R={'ясный':{ok:0,no:0},'сомнительный':{ok:0,no:0},'обычный':{ok:0,no:0}};
    cs.forEach(x=>{ if(R[x.sure]) R[x.sure][x.ok?'ok':'no']++; });
    const lf=(((day||{}).lev_all)||[]).filter(x=>pass(x.bg));
    lv={up:lf.filter(x=>x.hit==='up').length, dn:lf.filter(x=>x.hit==='dn').length,
        none:lf.filter(x=>x.hit==='none').length};
  }
  const bbOk = Object.values(R).reduce((s,v)=>s+v.ok,0), bbNo = Object.values(R).reduce((s,v)=>s+v.no,0);
  const bb={ok:bbOk,no:bbNo}, bt=bbOk+bbNo, okp=bt?bbOk/bt*100:0, lt=lv.up+lv.dn+lv.none;
  // СПОРНЫЕ СЧИТАЮТСЯ ОТДЕЛЬНО (08.09): пузырь, об который закрывались, — не промах анализа,
  // а другой случай. В общую долю идут только ясные, спорные и обычные показаны рядом.
  const nS=R['ясный'].ok+R['ясный'].no, nD=R['сомнительный'].ok+R['сомнительный'].no, nO=R['обычный'].ok+R['обычный'].no;
  const sureP=nS?R['ясный'].ok/nS*100:0, dP=nD?R['сомнительный'].ok/nD*100:0, oP=nO?R['обычный'].ok/nO*100:0;
  const wD=dP, wO=oP;
  const lp=lt?((lv.up+lv.dn)/lt*100):0;
  document.getElementById('c3').innerHTML=`
   <div class="an"><h4>сбылось · по максимуму и по закрытию</h4>
     <div class="two"><div><em>${D.sum.max_pct}<i>%</i></em><s>по максимуму<br>${D.sum.max_n} из ${D.sum.n}</s></div>
       <div><em>${D.sum.end_pct}<i>%</i></em><s>по закрытию<br>${D.sum.end_n} из ${D.sum.n}</s></div></div>
     <div class="leg">цена выхода ${D.sum.cost}% — столько теряется, если не выйти на вершине</div></div>
   <div class="an"><h4>пузыри · пошло в нужную сторону</h4>${popBub()}
     <div class="row2"><div class="rw"><div class="ring" style="--p:${sureP}"></div>
       <div class="rv">${sureP.toFixed(0)}<i>%</i></div></div>
       <div class="leg"><b>ясные</b> ${R['ясный'].ok} из ${R['ясный'].ok+R['ясный'].no}<br>
         только они идут в счёт</div></div>
     <div class="bars">
       <div class="bl"><span>спорные</span><i style="width:${wD}%"></i><em>${dP.toFixed(0)}% из ${nD}</em></div>
       <div class="bl"><span>обычные</span><i style="width:${wO}%"></i><em>${oP.toFixed(0)}% из ${nO}</em></div>
     </div></div>
   <div class="an"><h4>по рынкам · в чью смену ходят</h4>
     ${Object.entries(D.ses||{}).filter(([k])=>k!=='вне сессий')
       .sort((a,b)=>b[1].n-a[1].n).map(([k,v])=>`
       <div class="sr"><span class="sn">${k}</span>
         <span class="sb"><i style="width:${v.max_pct}%"></i></span>
         <span class="sv">${v.max_pct}<i>%</i></span>
         <em>${v.n} заходов · по закрытию ${v.end_pct}% · лучший ${v.mfe_med}% · пузыри ${v.bub_ok} из ${v.bub_ok+v.bub_no}</em></div>`).join('')}
   </div>
   <div class="an"><h4>уровни ликвидации · дошла ли цена</h4>${popLev()}
     <div class="row2"><div class="rw"><div class="ring" style="--p:${lp}"></div>
       <div class="rv">${lp.toFixed(0)}<i>%</i></div></div>
       <div class="leg">вверх ${lv.up} · вниз ${lv.dn}<br>никуда ${lv.none}</div></div></div>`;
}
function redraw(){drawFilters();part1();part2();part3();}
const days=Object.keys(D.days).sort().reverse();
document.getElementById('days').innerHTML=days.map((d,i)=>`<div class="day${i?'':' on'}" data-d="${d}">${d.slice(8,10)}.${d.slice(5,7)}</div>`).join('');
// ПОЧЕМУ ПЕРЕШЛО НА ЭТО МЕСТО (09.09): наведение на ступень — история прогон за прогоном.
// Показываем, что было с баллом, ходом и интересом на каждом прогоне внутри ступени, и чем
// первый прогон ступени отличался от последнего прогона предыдущей — это и есть причина перехода.
(function(){
  const pop=document.createElement('div'); pop.id='stpop'; document.body.appendChild(pop);
  function fmt(v,suf){ return (v===null||v===undefined)?'—':((v>0?'+':'')+v+(suf||'')); }
  document.addEventListener('mouseover', ev=>{
    const el=ev.target.closest && ev.target.closest('.st'); if(!el)return;
    const rows=(D.days[DAY]||[]).filter(r=>pass(r.bg));
    const coin=rows.find(r=>r.s===el.dataset.c); if(!coin)return;
    const i=+el.dataset.i, p=coin.path[i], prev=coin.path[i-1];
    const hist=(p[4]||[]);
    const before=prev && prev[4] && prev[4].length ? prev[4][prev[4].length-1] : null;
    const first=hist[0]||{};
    let why='';
    if(before){
      const parts=[];
      if(before.score!=null && first.score!=null){
        const d=(first.score-before.score);
        parts.push(`балл ${before.score} → ${first.score} (${d>0?'+':''}${d.toFixed(3)})`);
      }
      if(before.state!==first.state) parts.push(`состояние: ${before.state} → ${first.state}`);
      if(before.stage!==first.stage) parts.push(`стадия: ${before.stage} → ${first.stage}`);
      if(before.bubble!==first.bubble) parts.push(`пузырь: ${before.bubble} → ${first.bubble}`);
      why = parts.length ? parts.join(' · ') : 'числа не изменились — сдвинули соседи';
    } else why='первое появление в очереди';
    pop.innerHTML=`<h6>место ${p[1]} · ${p[0]}${p[2]&&p[2]!==p[0]?'–'+p[2]:''} · ${p[3]||1} прогон${(p[3]||1)>1?'а':''}</h6>`
      + `<div class="sr2"><b>почему</b><em colspan="2" style="grid-column:2/4">${why}</em></div>`
      + hist.map(h=>`<div class="sr2"><b>${h.t}</b>`
          + `<em>${h.score!=null?h.score:'—'}</em>`
          + `<span>ход <em class="${(h.move||0)>0?'up':'dn'}">${fmt(h.move,'%')}</em>`
          + ` · интерес <em class="${(h.oi||0)>0?'up':'dn'}">${fmt(h.oi,'%')}</em>`
          + ` · ${h.state||''}${h.bubble&&h.bubble!=='тихо'?' · пузырь '+h.bubble:''}</span></div>`).join('');
    const r=el.getBoundingClientRect();
    pop.style.left=Math.min(r.left, innerWidth-440)+'px';
    pop.style.top=Math.min(r.bottom+8, innerHeight-260)+'px';
    pop.classList.add('on');
  });
  document.addEventListener('mouseout', ev=>{
    if(ev.target.closest && ev.target.closest('.st')) pop.classList.remove('on');
  });
})();

// переход в карточку монеты по клику на имя
document.addEventListener('click', ev=>{
  const a=ev.target.closest && ev.target.closest('a.go'); if(!a)return;
  ev.preventDefault();
  const sym=a.dataset.s;
  if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'coin',hash:sym},'*')}catch(e){}}
  location.href='coin.html#'+encodeURIComponent(sym);
});
document.querySelectorAll('.day').forEach(t=>t.onclick=()=>{document.querySelectorAll('.day').forEach(x=>x.classList.toggle('on',x===t));DAY=t.dataset.d;redraw();});
redraw();
"""


def render_accuracy() -> str:
    data = build_data()
    js = JS.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>журнал</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap"><div class="plate">
  <div class="head"><h1>Журнал</h1><s>наблюдение по дням</s><div class="days" id="days"></div></div>
  <div class="filters" id="filters"></div>
  <div class="cols">
    <div class="box"><div class="cap">первые и очередь · смена мест и выпадение</div><div id="c1"></div></div>
    <div class="box"><div class="cap">фон · ход монет и биткоин</div><div id="c2"></div></div>
    <div class="box"><div class="cap">аналитика</div><div id="c3"></div></div>
  </div>
  <div class="foot">место в очереди по прогонам · время красным — монета выпала из очереди, это конец прогноза</div>
</div></div>
<script>
{js}
</script>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    html = render_accuracy()
    d = build_data()
    n = sum(len(x) for x in d["days"].values())
    print(f"журнал: дней {len(d['days'])} · монет в первых {n} · "
          f"пузырей {sum(v['ok'] + v['no'] for v in d['bub2']['res'].values())} · html {len(html)} байт")
    if a.write:
        p = REPORT_PATH.parent / "accuracy.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        print("→", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
