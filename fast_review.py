#!/usr/bin/env python3
"""РАЗБОР ВЫХОДА БЫСТРЫХ СДЕЛОК (27.09, владелец: «по быстрым в тг присылай выход — где позиция закрылась и итог, + разбор: можно было
ещё подержать или стоп ниже поставить и добрать позицию, что было не учтено, вообще подумай сам»).

Через REVIEW_AFTER_H после выхода сделки книг «всплеск/вынос» и «пробуждение» (output/paper_fast3.jsonl, paper_wake.jsonl) — по
трёхминуткам Binance от входа до выхода + REVIEW_AFTER_H:
  путь внутри сделки — максимум за и против от входа и когда; после минимума — куда дошла (место добора);
  после выхода — стоп: дошла ли потом цена до цели и какой стоп нужен был, чтобы пересидеть; цель: сколько ещё прошла;
  срок: что дало бы ещё 1 и 2 ч;
  фон — интерес за час на входе (запись входа) и на выходе, покупатели по рынку в сделке и после, доска на входе;
  сравнение — медиана интереса за час на входе у сегодняшних плюсовых и минусовых сделок этой книги.
Сообщение в телеграм (всем подписчикам), строка в output/fast_reviews.jsonl. Пороговых решений здесь нет — только факты; правку
стопа/цели приносит счёт по журналу (--summary).

    python3 fast_review.py --write          # так зовёт fast_tier каждые 3 мин: разобрать созревшие, отправить
    python3 fast_review.py --backfill       # разобрать всё закрытое с 07:15 27.09 в журнал, без телеграма
    python3 fast_review.py --summary        # счёт по журналу разборов
"""
from __future__ import annotations

import argparse
import fcntl
import json
import statistics as st
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json  # noqa: E402

L = timezone.utc   # 06.10 владелец: «всё должно быть в utc везде» (до этого UTC+3)
BOOKS = (("всплеск/вынос", BASE_DIR / "output" / "paper_fast3.jsonl"), ("пробуждение", BASE_DIR / "output" / "paper_wake.jsonl"))
STATE = BASE_DIR / "output" / "fast_reviews.json"
JOURNAL = BASE_DIR / "output" / "fast_reviews.jsonl"
REVIEW_AFTER_H = 2.0
B3 = 180_000
BACKFILL_FROM = datetime(2026, 9, 27, 4, 15, tzinfo=L).timestamp()   # 04:15 UTC = прежние 07:15 UTC+3


def _rows(p: Path) -> list[dict]:
    out = []
    try:
        for ln in p.open(encoding="utf-8"):
            try:
                out.append(json.loads(ln))
            except ValueError:
                pass
    except OSError:
        pass
    return out


def trades() -> list[dict]:
    """закрытые сделки обеих книг с записью входа (связь — время входа)"""
    out = []
    for book, p in BOOKS:
        R = _rows(p)
        ent = {(r.get("sym"), round(float(r.get("at") or 0), 3)): r for r in R if r.get("kind") == "entry"}
        for r in R:
            if not str(r.get("kind", "")).startswith("exit") or r.get("result_pct") is None:
                continue
            e = ent.get((r.get("sym"), round(float(r.get("opened_at") or 0), 3))) or {}
            out.append(dict(book=book, sym=r["sym"], side=int(r.get("side") or 1), px_in=float(r["px_in"]), px_out=float(r.get("px_out") or 0),
                            t_in=float(r.get("opened_at") or 0), t_out=float(r["at"]), res=float(r["result_pct"]), why=r.get("why_exit") or "",
                            rule=r.get("rule") or "", tp=float(e.get("target") or 0.05), sl=float(e.get("stop") or 0.05),
                            oi1h_in=e.get("oi1h"), fon_in=e.get("fon") or {}, key=f"{book}|{r['sym']}|{int(float(r['at']))}"))
    return out


def klines(sym: str, t0: float, t1: float) -> list[list]:
    out, t = [], int(t0 * 1000) // B3 * B3
    end = int(t1 * 1000)
    while t < end:
        k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "startTime": t, "endTime": end, "limit": 500},
                     quiet_400=True, weight=2) or []
        if not k:
            break
        out += k
        t = int(k[-1][0]) + B3
        if len(k) < 500:
            break
    return [x for x in out if int(x[0]) + B3 <= int(time.time() * 1000)]


def oi1h_at(sym: str, t: float):
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist",
                  {"symbol": sym, "period": "5m", "endTime": int(t * 1000), "limit": 13}, quiet_400=True) or []
    v = [float(x["sumOpenInterestValue"]) for x in oi]
    return round((v[-1] / v[0] - 1) * 100, 1) if len(v) >= 13 and v[0] else None


def review(tr: dict, today: list[dict]) -> dict | None:
    sd, e = tr["side"], tr["px_in"]
    k = klines(tr["sym"], tr["t_in"] - 180, tr["t_out"] + REVIEW_AFTER_H * 3600)
    if not k:
        return None
    t_out_ms = tr["t_out"] * 1000
    inside = [x for x in k if int(x[0]) >= tr["t_in"] * 1000 - B3 and int(x[0]) + B3 <= t_out_ms + B3]
    after = [x for x in k if int(x[0]) >= t_out_ms]
    if not inside:
        return None
    fav = lambda x: (float(x[2]) / e - 1) * 100 * sd if sd == 1 else (float(x[3]) / e - 1) * 100 * sd   # noqa: E731 — лучшая точка бара
    adv = lambda x: (float(x[3]) / e - 1) * 100 * sd if sd == 1 else (float(x[2]) / e - 1) * 100 * sd   # noqa: E731 — худшая
    mins = lambda x: int((int(x[0]) + B3 - tr["t_in"] * 1000) / 60000)                                  # noqa: E731
    i_best = max(inside, key=fav); i_worst = min(inside, key=adv)
    out = dict(key=tr["key"], book=tr["book"], sym=tr["sym"], side=sd, why=tr["why"], res=tr["res"], t_in=tr["t_in"], t_out=tr["t_out"],
               mfe=round(fav(i_best), 2), mfe_min=mins(i_best), mae=round(adv(i_worst), 2), mae_min=mins(i_worst))
    # после минимума внутри сделки — куда дошла до выхода (место добора)
    after_mae = [x for x in inside if int(x[0]) > int(i_worst[0])]
    out["after_mae_best"] = round(max(fav(x) for x in after_mae), 2) if after_mae else None
    tgt = e * (1 + sd * tr["tp"])
    if after:
        a_best = max(after, key=fav); a_worst = min(after, key=adv)
        out.update(post_best=round(fav(a_best), 2), post_best_min=int((int(a_best[0]) + B3 - t_out_ms) / 60000),
                   post_worst=round(adv(a_worst), 2), post_close=round((float(after[-1][4]) / e - 1) * 100 * sd, 2),
                   post_h=round((int(after[-1][0]) + B3 - t_out_ms) / 3.6e6, 1))
        hit = next((x for x in after if (float(x[2]) >= tgt if sd == 1 else float(x[3]) <= tgt)), None)
        if hit is not None:
            # какой стоп нужен был, чтобы дожить до цели: худшая точка от входа до касания цели
            path = [x for x in k if int(x[0]) >= tr["t_in"] * 1000 - B3 and int(x[0]) <= int(hit[0])]
            out["target_after_min"] = int((int(hit[0]) + B3 - t_out_ms) / 60000)
            out["stop_needed"] = round(min(adv(x) for x in path), 2)
        for h in (1, 2):
            b = [x for x in after if int(x[0]) + B3 <= t_out_ms + h * 3.6e6]
            if b:
                out[f"hold_{h}h"] = round((float(b[-1][4]) / e - 1) * 100 * sd, 2)
    # покупатели по рынку: доля покупок тейкером в обороте — в сделке и после
    tb = lambda xs: round(sum(float(x[10]) for x in xs) / max(1.0, sum(float(x[7]) for x in xs)) * 100) if xs else None  # noqa: E731
    out.update(buy_in=tb(inside), buy_after=tb(after), oi1h_in=tr["oi1h_in"], oi1h_out=oi1h_at(tr["sym"], tr["t_out"]),
               board6_in=(tr["fon_in"] or {}).get("board6"))
    # сравнение с сегодняшними сделками этой книги: интерес за час на входе у плюсовых и минусовых
    w = [x["oi1h_in"] for x in today if x["book"] == tr["book"] and x["res"] > 0 and x["oi1h_in"] is not None]
    l_ = [x["oi1h_in"] for x in today if x["book"] == tr["book"] and x["res"] <= 0 and x["oi1h_in"] is not None]
    out["cmp"] = dict(win_n=len(w), win_oi1h=round(st.median(w), 1) if w else None, loss_n=len(l_), loss_oi1h=round(st.median(l_), 1) if l_ else None)
    out["verdict"] = verdict(out, tr)
    return out


def verdict(r: dict, tr: dict) -> str:
    why = tr["why"]
    if why.startswith("стоп"):
        if r.get("target_after_min") is not None:
            return (f"стоп тесный: через {r['target_after_min']} мин после стопа цена дошла до цели; пересидеть — стоп ниже "
                    f"{r['stop_needed']:+.1f}% от входа")
        return f"стоп по делу: после выхода ещё {r.get('post_worst', 0):+.1f}% против, к цели не вернулась за {r.get('post_h', 0)} ч"
    if why.startswith("цель"):
        more = (r.get("post_best") or 0) - tr["tp"] * 100
        return (f"цель рано: после выхода ещё до {r.get('post_best', 0):+.1f}% от входа (+{more:.1f}% сверх цели) за {r.get('post_best_min')} мин"
                if more > 0 else f"цель по делу: выше цели после выхода не прошла (лучшее {r.get('post_best', 0):+.1f}% от входа)")
    h1, h2 = r.get("hold_1h"), r.get("hold_2h")
    s = f"по сроку {tr['res']:+.2f}%; ещё 1 ч — {h1:+.2f}%" if h1 is not None else f"по сроку {tr['res']:+.2f}%"
    if h2 is not None:
        s += f", 2 ч — {h2:+.2f}%"
    if r["mfe"] >= tr["tp"] * 100 * 0.8:
        s += f"; внутри сделки было {r['mfe']:+.1f}% (цель {tr['tp'] * 100:.0f}%) — не забрали"
    return s


def text(r: dict) -> str:
    """сообщение разбора: заголовок и строки с отступами и значками (27.09 владелец: «простыня не читаемая»)"""
    sd = "ЛОНГ" if r["side"] == 1 else "ШОРТ"
    tin = datetime.fromtimestamp(r["t_in"], L); tout = datetime.fromtimestamp(r["t_out"], L)
    ln = [f"🧾 РАЗБОР · {sd} · {r['sym'][:-4]} · {r['why']} {r['res']:+.2f}%", f"📘 {r['book']} · {tin:%H:%M} → {tout:%H:%M} UTC", "",
          f"📈 в сделке:   лучшее {r['mfe']:+.1f}% ({r['mfe_min']} мин) · худшее {r['mae']:+.1f}% ({r['mae_min']} мин)"]
    if r.get("after_mae_best") is not None:
        ln.append(f"↩️ после минимума: дошла до {r['after_mae_best']:+.1f}%")
    if r.get("post_best") is not None:
        ln.append(f"🔭 после выхода за {r['post_h']} ч: лучшее {r['post_best']:+.1f}% · худшее {r['post_worst']:+.1f}% · сейчас {r['post_close']:+.1f}%")
    if r.get("hold_1h") is not None:
        ln.append(f"⏳ держать дальше: ещё 1 ч {r['hold_1h']:+.1f}%" + (f" · 2 ч {r['hold_2h']:+.1f}%" if r.get("hold_2h") is not None else ""))
    ln.append("")
    f = [f"интерес 1ч на входе {r['oi1h_in']:+.1f}%" if r.get("oi1h_in") is not None else None,
         f"на выходе {r['oi1h_out']:+.1f}%" if r.get("oi1h_out") is not None else None]
    if any(f):
        ln.append("🌡 " + " · ".join(x for x in f if x))
    if r.get("buy_in") is not None:
        ln.append(f"🛒 покупатели: {r['buy_in']}% в сделке · {r['buy_after']}% после")
    if r.get("board6_in") is not None:
        ln.append(f"🌊 доска 6 ч на входе: {r['board6_in']:+.1f}%")
    c = r.get("cmp") or {}
    if c.get("win_n") or c.get("loss_n"):
        ln.append(f"📊 сегодня в книге, интерес 1ч на входе: плюсовые {c.get('win_oi1h')}% (n{c.get('win_n')}) · минусовые {c.get('loss_oi1h')}% (n{c.get('loss_n')})")
    ln += ["", "💡 " + r["verdict"]]
    return "\n".join(ln)


def summary() -> str:
    R_all = _rows(JOURNAL)
    if not R_all:
        return "разборов нет"
    try:                                                              # 27.09: монеты своего ММ в счёт правил не идут
        om = set(json.loads((BASE_DIR / "output" / "own_mm.json").read_text()).get("coins", {}).keys())
    except (OSError, ValueError):
        om = set()
    R = [r for r in R_all if r["sym"] not in om]
    out = [f"разборов {len(R)} (монеты своего ММ вне счёта: {len(R_all) - len(R)})"]
    for book in sorted({r["book"] for r in R}):
        g = [r for r in R if r["book"] == book]
        st_ = [r for r in g if r["why"].startswith("стоп")]; tg = [r for r in g if r["why"].startswith("цель")]; tm = [r for r in g if r["why"].startswith("срок")]
        tight = [r for r in st_ if r.get("target_after_min") is not None]
        early = [r for r in tg if (r.get("post_best") or 0) > 5.0]
        med = lambda v: f"{st.median(v):+.1f}%" if v else "—"   # noqa: E731
        out.append(f"{book}: стопов {len(st_)}, из них цена потом дошла до цели {len(tight)}"
                   + (f" (стоп нужен был медиана {st.median([r['stop_needed'] for r in tight]):+.1f}%)" if tight else "")
                   + f"; целей {len(tg)}, после них ещё выше цели {len(early)} (лучшее после выхода, медиана {med([r['post_best'] for r in tg if r.get('post_best') is not None])} от входа)"
                   + f"; по сроку {len(tm)}: итог медиана {med([r['res'] for r in tm])}, держать ещё 1 ч {med([r['hold_1h'] for r in tm if r.get('hold_1h') is not None])},"
                   f" 2 ч {med([r['hold_2h'] for r in tm if r.get('hold_2h') is not None])}; внутри было ≥ 80% цели {sum(1 for r in tm if r['mfe'] >= 4.0)}")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--summary", action="store_true")
    a = ap.parse_args()
    if a.summary:
        print(summary())
        return 0
    with open(STATE.with_suffix(".lock"), "w") as lk:
        try:
            fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)              # один разбор за раз (fast_tier зовёт каждые 3 мин)
        except OSError:
            return 0
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            state = {"since": time.time(), "done": []}                  # первый запуск: разбираем только выходы после него
        since = BACKFILL_FROM if a.backfill else float(state.get("since") or time.time())
        done = set(state.get("done") or [])
        T = trades()
        day0 = datetime.now(L).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        today = [x for x in T if x["t_out"] >= day0]
        due = [x for x in T if x["t_out"] >= since and x["key"] not in done and time.time() >= x["t_out"] + REVIEW_AFTER_H * 3600]
        cfg = None
        if a.write and not a.backfill:
            from send_brief_telegram import load_config
            cfg = load_config()
        n = 0
        for tr in due:
            r = review(tr, today)
            if not r:
                continue
            with JOURNAL.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            done.add(tr["key"]); n += 1
            if cfg:
                from send_brief_telegram import send_telegram
                send_telegram(text(r), cfg)
            else:
                print(text(r) + "\n")
        if a.write or a.backfill:
            state["done"] = sorted(done)[-3000:]
            state.setdefault("since", since if not a.backfill else time.time())
            tmp = STATE.with_suffix(".tmp"); tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8"); tmp.replace(STATE)
        print(f"fast_review: разобрано {n}, ждут {len([x for x in T if x['t_out'] >= since and x['key'] not in done]) - 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
