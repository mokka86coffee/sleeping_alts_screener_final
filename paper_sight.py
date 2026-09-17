#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ «КАРТИНА» (17.09, владелец: «добавляй новую стратегию — очень быструю, изначально абсолютно тупую:
берём все признаки, что знаем, пусть заходит на всех монетах каждые полчаса; ошибки поправим по наблюдениям»).

Бот — глаза на 120 монет каждые полчаса. Он не выбирает стратегию, он читает картину бара по всем слоям, что
уже считает прогон, и открывает туда, куда картина смотрит. Сторона — по СОГЛАСИЮ голосов, веса равные:
  вортекс 30м        VI+ выше VI−, и линия покупателей росла на баре → +1; зеркально −1
  клингер 30м        над сигнальной и растёт → +1; под и падает → −1
  интерес к цене     за SIGHT_OI_BARS: интерес вырос и цена вверх → +1 (набивают в ход); интерес вырос и цена вниз → −1
  фандинг            платят шорты (< −SIGHT_FUND_MIN) → +1; платят лонги (> +SIGHT_FUND_MIN) → −1
  пузырь 30м         последний ясный пузырь за SIGHT_BUBBLE_BARS: покупка +1, продажа −1
  тейкер бара        покупки к продажам ≥ SIGHT_TAKER_UP → +1; ≤ SIGHT_TAKER_DN → −1
  доска              медиана хода > 0 и растёт ≥ SIGHT_BOARD_UP доли → +1; медиана < 0 и растёт ≤ SIGHT_BOARD_DN → −1
  биткоин            ход за час ≥ +SIGHT_BTC_H1 → +1; ≤ −SIGHT_BTC_H1 → −1
Сумма ≥ +SIGHT_MIN_SCORE — лонг, ≤ −SIGHT_MIN_SCORE — шорт, иначе монета мимо. За прогон — до SIGHT_MAX_PER_RUN
самых единодушных; по монете одна позиция.

Выход и хедж — правила владельца:
  • ход в плюс ≥ SIGHT_TARGET по закрытию — закрыть;
  • убыток НЕ закрываем: при ходе против ≤ −SIGHT_HEDGE_PCT открывается хедж — противоположная нога того же
    размера, ход замораживается; хедж снимается, когда картина снова смотрит в сторону позиции (сумма голосов
    ≥ SIGHT_MIN_SCORE в её сторону) — это и есть «другой признак, который служит разворотом»; дальше позиция
    идёт сама и может хеджироваться снова;
  • срок SIGHT_HOLD_BARS — закрыть всё, что осталось (страховка журнала, не правило владельца).
Результат сделки = ход основной ноги + сумма ходов всех хедж-ног. В журнал — голоса при каждом событии.

Данные: cq_v2/intraday/<монета>.jsonl (h, l, px, oi, funding, fut, oi_type); фон — market_bg.last_row().
Состояние output/paper_sight.json, журнал output/paper_sight.jsonl. Запуск из прогона; руками --only / --write.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import (SIGHT_MIN_SCORE, SIGHT_MAX_PER_RUN, SIGHT_TARGET, SIGHT_HEDGE_PCT, SIGHT_HOLD_BARS,
                             SIGHT_FEE, SIGHT_OI_BARS, SIGHT_FUND_MIN, SIGHT_BUBBLE_BARS, SIGHT_TAKER_UP, SIGHT_TAKER_DN,
                             SIGHT_BOARD_UP, SIGHT_BOARD_DN, SIGHT_BTC_H1, SIGHT_MIN_BARS)
except ImportError:
    SIGHT_MIN_SCORE, SIGHT_MAX_PER_RUN, SIGHT_TARGET, SIGHT_HEDGE_PCT, SIGHT_HOLD_BARS = 4, 20, 0.03, 0.015, 48
    SIGHT_FEE, SIGHT_OI_BARS, SIGHT_FUND_MIN, SIGHT_BUBBLE_BARS = 0.001, 6, 0.01, 8
    SIGHT_TAKER_UP, SIGHT_TAKER_DN, SIGHT_BOARD_UP, SIGHT_BOARD_DN, SIGHT_BTC_H1, SIGHT_MIN_BARS = 1.08, 0.92, 0.6, 0.4, 0.3, 70
try:
    from core_config import SIGHT_HEDGE_BY
except ImportError:
    SIGHT_HEDGE_BY = "close"      # "close" — хедж, если бар ЗАКРЫЛСЯ ниже порога; "range" — по триггеру внутри бара
try:
    from core_config import FAST_BUBBLE_SIGMA, FAST_BUBBLE_OI_PCT
except ImportError:
    FAST_BUBBLE_SIGMA, FAST_BUBBLE_OI_PCT = 2.0, 1.5

import lab_junctions as lj

ARCH = BASE_DIR / "cq_v2" / "intraday"
STATE = BASE_DIR / "output" / "paper_sight.json"
LOG = BASE_DIR / "output" / "paper_sight.jsonl"
BOOK_NAME = "paper_sight"
BOOK_LABEL = "картина"            # подпись книги на экране; в строки журнала идёт она
BAR_MS = 1_800_000


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rows_of(sym: str) -> list[dict]:
    """получасовки архива по порядку свечей, повтор — последняя запись, без свечей из будущего"""
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    by: dict = {}
    if not p.exists():
        return []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("px") and r.get("h") and r.get("l") and r.get("candle"):
            try:
                r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            except ValueError:
                continue
            by[r["t"]] = r
    now_ms = int(time.time() * 1000)
    return [by[t] for t in sorted(by) if t <= now_ms]


def _bars(rows: list[dict]) -> list[tuple]:
    """(t сек, h, l, c, оборот $) — формат лаборатории стыков"""
    out = []
    for r in rows:
        f = r.get("fut") or {}
        v = float(f.get("b") or 0) + float(f.get("s") or 0) or float((r.get("kv") or {}).get("qv") or 0)
        out.append((r["t"] // 1000, float(r["h"]), float(r["l"]), float(r["px"]), v))
    return out


def background() -> dict:
    """доска и биткоин из последней строки фона"""
    try:
        from market_bg import last_row
        row = last_row() or {}
    except Exception:  # noqa: BLE001
        return {}
    ro, btc = row.get("risk_on") or {}, row.get("btc") or {}
    n = int(ro.get("n") or 0)
    return {"median": ro.get("median_pct"), "share": (int(ro.get("green") or 0) / n) if n else None,
            "btc_h1": btc.get("h1_pct")}


def series(rows: list[dict]) -> dict:
    """линии и норма дельты по всей истории монеты — считаются один раз (лаборатория гоняет по барам)"""
    bars = _bars(rows)
    dl = [float((x.get("fut") or {}).get("d") or 0) for x in rows]
    return {"bars": bars, "vl": lj.vortex_lines(bars), "kl": lj.klinger_lines(bars),
            "mu": st.mean(dl) if dl else 0.0, "sd": (st.pstdev(dl) if dl else 0.0) or 1.0, "dl": dl}


def votes_at(i: int, rows: list[dict], S: dict, bg: dict) -> dict | None:
    """голоса картины на баре i по готовым линиям S (series); bg — доска и биткоин на этом баре"""
    if i < SIGHT_MIN_BARS - 1:
        return None
    bars, vl, kl, dl = S["bars"], S["vl"], S["kl"], S["dl"]
    r = rows[i]
    t, t0 = bars[i][0], bars[i - 1][0]
    v: dict = {}
    if t in vl and t0 in vl:
        p, m = vl[t]
        pp, pm = vl[t0]
        v["вортекс"] = 1 if (p > m and p >= pp) else -1 if (m > p and m >= pm) else 0
    if t in kl and t0 in kl:
        k, sg = kl[t]
        k0, _ = kl[t0]
        v["клингер"] = 1 if (k > sg and k >= k0) else -1 if (k < sg and k <= k0) else 0
    ois = [float(x["oi"]) for x in rows[i - SIGHT_OI_BARS:i + 1] if x.get("oi")]
    if len(ois) >= 2 and ois[0]:
        d_px = float(r["px"]) / float(rows[i - SIGHT_OI_BARS]["px"]) - 1
        d_oi = ois[-1] / ois[0] - 1
        v["интерес"] = (1 if d_px > 0 else -1) if d_oi > 0.005 else 0
    fund = r.get("funding")
    if fund is not None:
        v["фандинг"] = 1 if fund < -SIGHT_FUND_MIN else -1 if fund > SIGHT_FUND_MIN else 0
    bub = 0
    for k in range(i, max(-1, i - SIGHT_BUBBLE_BARS), -1):
        x = rows[k]
        o0 = next((float(y["oi"]) for y in rows[k - 1::-1] if y.get("oi")), None) if k > 0 else None
        ch = (float(x["oi"]) / o0 - 1) * 100 if (o0 and x.get("oi")) else None
        if abs(dl[k] - S["mu"]) >= FAST_BUBBLE_SIGMA * S["sd"] and ch is not None and ch >= FAST_BUBBLE_OI_PCT:
            bub = 1 if dl[k] > 0 else -1
            break
    v["пузырь"] = bub
    tk = (r.get("fut") or {}).get("tk")
    if tk is not None:
        v["тейкер"] = 1 if tk >= SIGHT_TAKER_UP else -1 if tk <= SIGHT_TAKER_DN else 0
    if bg.get("median") is not None and bg.get("share") is not None:
        v["доска"] = (1 if (bg["median"] > 0 and bg["share"] >= SIGHT_BOARD_UP) else
                      -1 if (bg["median"] < 0 and bg["share"] <= SIGHT_BOARD_DN) else 0)
    if bg.get("btc_h1") is not None:
        v["биткоин"] = 1 if bg["btc_h1"] >= SIGHT_BTC_H1 else -1 if bg["btc_h1"] <= -SIGHT_BTC_H1 else 0
    return v


def votes(rows: list[dict], bg: dict) -> dict | None:
    """голоса картины на последнем закрытом баре"""
    if len(rows) < SIGHT_MIN_BARS:
        return None
    return votes_at(len(rows) - 1, rows, series(rows), bg)


def side_of(v: dict) -> int:
    s = sum(v.values())
    return 1 if s >= SIGHT_MIN_SCORE else -1 if s <= -SIGHT_MIN_SCORE else 0


def _txt(v: dict) -> str:
    return " ".join(f"{k}{'+' if x > 0 else '−' if x < 0 else '·'}" for k, x in v.items())


def leg_res(leg: dict, px: float) -> float:
    return int(leg["side"]) * (px / float(leg["px"]) - 1)


def total_res(pos: dict, px: float) -> float:
    """ход позиции: основная нога + закрытые хеджи + открытый хедж"""
    r = leg_res(pos, px)
    for h in pos.get("hedges") or []:
        r += h["res"] if h.get("closed") else leg_res(h, px)
    return r


def step(pos: dict, rows: list[dict], v: dict | None, now: int) -> list[dict]:
    """одна позиция на новом баре: цель / хедж / снятие хеджа / срок. Возвращает события журнала.

    КАК НА БИРЖЕ, А НЕ ПО ЗАКРЫТИЮ (17.09, владелец: «бот взял лимитный ордер на продажу +3% и всё, биржа не ждёт
    полчаса»). Цель — лимитная заявка на основной ноге по цене входа ± SIGHT_TARGET: исполнена, если максимум бара
    (у лонга) или минимум (у шорта) её достиг; результат — ровно цель. Хедж — триггер по цене входа ∓ SIGHT_HEDGE_PCT:
    сработал, если размах бара его коснулся; хедж-нога открывается по цене триггера. Если в одном баре достигнуты
    и цель, и триггер, порядок неизвестен: у бара по ходу позиции (закрытие лучше открытия) считаем, что сначала
    был ход против — хедж, потом цель уже не считается (позиция заморожена); у бара против — тоже хедж. То есть
    спорный бар всегда трактуется против позиции. Снятие хеджа — по картине на закрытии бара, как и было."""
    r = rows[-1]
    t, px = r["t"], float(r["px"])
    h, l = float(r.get("h") or px), float(r.get("l") or px)
    if t <= int(pos.get("last_t") or pos["t"]):
        return []
    pos["last_t"] = t
    pos["bars"] = int(pos.get("bars") or 0) + 1
    side = int(pos["side"])
    e = float(pos["px"])
    ev: list[dict] = []
    open_h = next((h_ for h_ in pos.get("hedges") or [] if not h_.get("closed")), None)
    score = sum(v.values()) if v else 0
    tgt_px = e * (1 + side * SIGHT_TARGET)
    hdg_px = e * (1 - side * SIGHT_HEDGE_PCT)
    hit_tgt = (h >= tgt_px) if side > 0 else (l <= tgt_px)
    # ХЕДЖ ПО ЗАКРЫТИЮ ИЛИ ПО ТРИГГЕРУ (17.09): на выносных монетах триггер −1.5% цепляется хвостом почти каждого бара
    # и хедж встаёт на дне тряски (AVA: хедж по хвосту, снят на закрытии +10% — нога −13%, сделка −11% при взятой
    # цели). По закрытию хедж встаёт только если бар закрылся под порогом. Что лучше — считает лаборатория.
    if SIGHT_HEDGE_BY == "range":
        hit_hdg = (l <= hdg_px) if side > 0 else (h >= hdg_px)
    else:
        hit_hdg = leg_res(pos, px) <= -SIGHT_HEDGE_PCT
        hdg_px = px
    closed_h = sum(float(h_["res"]) for h_ in pos.get("hedges") or [] if h_.get("closed"))
    if not open_h:
        if hit_hdg and pos["bars"] < SIGHT_HOLD_BARS:
            # триггер хеджа сработал внутри бара — ставим ногу по цене триггера; цель в этом баре уже не считается
            hh = {"side": -side, "px": hdg_px, "t": t, "closed": False}
            pos.setdefault("hedges", []).append(hh)
            ev.append(dict(kind="hedge", px=hdg_px, res_at_hedge_pct=round(leg_res(pos, hdg_px) * 100, 2), votes=v,
                           why=(f"ход против до −{SIGHT_HEDGE_PCT * 100:.1f}% внутри бара — хедж по триггеру" if SIGHT_HEDGE_BY == "range"
                                else f"закрытие {leg_res(pos, px) * 100:.2f}% против — хедж") + ", ждём разворота"))
            open_h = hh
        elif hit_tgt:
            res = SIGHT_TARGET + closed_h - SIGHT_FEE
            pos["closed"] = {"why": f"цель {SIGHT_TARGET * 100:.0f}% лимиткой на баре {pos['bars']}", "res": res, "px": tgt_px}
            return [dict(kind="exit", why_exit=pos["closed"]["why"], result_pct=round(res * 100, 2), px_out=tgt_px, votes=v)]
    else:
        if (score >= SIGHT_MIN_SCORE and side > 0) or (score <= -SIGHT_MIN_SCORE and side < 0):
            open_h["closed"], open_h["t_close"], open_h["px_close"] = True, t, px
            open_h["res"] = leg_res(open_h, px) - SIGHT_FEE
            ev.append(dict(kind="unhedge", px=px, hedge_res_pct=round(open_h["res"] * 100, 2), votes=v,
                           why="картина снова в сторону позиции: " + _txt(v)))
            open_h = None
    if pos["bars"] >= SIGHT_HOLD_BARS:
        for h_ in pos.get("hedges") or []:
            if not h_.get("closed"):
                h_["closed"], h_["t_close"], h_["px_close"], h_["res"] = True, t, px, leg_res(h_, px) - SIGHT_FEE
        res = total_res(pos, px) - SIGHT_FEE
        pos["closed"] = {"why": f"срок {SIGHT_HOLD_BARS} баров", "res": res, "px": px}
        ev.append(dict(kind="exit", why_exit=pos["closed"]["why"], result_pct=round(res * 100, 2), px_out=px, votes=v))
    return ev


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    syms = ([x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only
            else sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl")))
    state = _read(STATE) or {"open": {}, "last_sig": {}}
    state.setdefault("open", {}); state.setdefault("last_sig", {})
    now = int(time.time())
    bg = background()
    events, cands = [], []
    n_closed = 0
    for sym in syms:
        rows = rows_of(sym)
        if len(rows) < SIGHT_MIN_BARS:
            continue
        v = votes(rows, bg)
        pos = state["open"].get(sym)
        if pos:
            for e in step(pos, rows, v, now):
                events.append(dict(e, book=BOOK_LABEL, sym=sym, side=pos["side"], t=pos["t"], px_in=pos["px"],
                                   size=pos.get("size", 1.0), rule=pos.get("rule"), at=now,
                                   hedges=len(pos.get("hedges") or []),
                                   **({"result_sized_pct": round(pos["closed"]["res"] * pos.get("size", 1.0) * 100, 2)} if e["kind"] == "exit" else {})))
                if e["kind"] == "exit":
                    n_closed += 1
                    print(f"paper_sight: {sym} · выход · {e['why_exit']} · {e['result_pct']:+.2f}% · хеджей {len(pos.get('hedges') or [])}")
                elif e["kind"] == "hedge":
                    print(f"paper_sight: {sym} · хедж по {e['px']:.6g} · {e['why']}")
                else:
                    print(f"paper_sight: {sym} · хедж снят по {e['px']:.6g} · {e['hedge_res_pct']:+.2f}% · {e['why'][:60]}")
            if pos.get("closed"):
                del state["open"][sym]
                pos = None
        if pos or v is None:
            continue
        s = side_of(v)
        t = rows[-1]["t"]
        if s and t > int(state["last_sig"].get(sym) or 0):
            cands.append((sym, s, v, t, float(rows[-1]["px"])))
    cands.sort(key=lambda x: -abs(sum(x[2].values())))
    taken, skipped = cands[:SIGHT_MAX_PER_RUN], cands[SIGHT_MAX_PER_RUN:]
    for sym, s, v, t, px in skipped:
        state["last_sig"][sym] = t
        events.append({"kind": "skip", "book": BOOK_LABEL, "sym": sym, "side": s, "t": t, "px": px, "at": now,
                       "why_skip": f"за прогон уже {SIGHT_MAX_PER_RUN}", "score": sum(v.values()), "votes": v})
    for sym, s, v, t, px in taken:
        pos = {"rule": f"картина: {'лонг' if s > 0 else 'шорт'} {abs(sum(v.values()))} голосов", "side": s, "t": t,
               "px": px, "size": 1.0, "target": SIGHT_TARGET, "stop": None, "hold": SIGHT_HOLD_BARS,
               "votes": v, "bg": bg, "hedges": [], "bars": 0, "last_t": t, "opened_at": now, "state": "long" if s > 0 else "short"}
        state["open"][sym] = pos
        state["last_sig"][sym] = t
        events.append(dict(kind="entry", book=BOOK_LABEL, sym=sym, side=s, t=t, px=px, size=1.0, rule=pos["rule"],
                           score=sum(v.values()), votes=v, bg=bg, at=now))
        print(f"paper_sight: {sym} · вход {'лонг' if s > 0 else 'шорт'} {px:.6g} · {sum(v.values()):+d} · {_txt(v)}")
    if a.only:
        for sym in syms:
            rows = rows_of(sym)
            v = votes(rows, bg) if len(rows) >= SIGHT_MIN_BARS else None
            print(f"paper_sight: {sym} · картина: {(_txt(v) + f' · сумма {sum(v.values()):+d}') if v else 'баров мало'}")
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for e in events:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    n_h = sum(1 for e in events if e["kind"] == "hedge")
    print(f"paper_sight: открыто {len(taken)}, пропущено {len(skipped)}, хеджей {n_h}, закрыто {n_closed}, "
          f"в позиции {len(state['open'])}" + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
