#!/usr/bin/env python3
"""ПУЗЫРЬ У ДНА (17.09, владелец: ENA — лонг от дна с белыми пузырями на 4ч, «хочется, чтобы такие вещи тоже
попадали в торговлю, хотя пузырь в карте сильный и много за, но ни в звёздах, нигде нет ничего»).

Что было не так:
  1. Пузыри у нас считались только на получасовках, а главный признак владельца — БЕЛЫЙ ПУЗЫРЬ У ДНА НА
     БОЛЬШОМ ТАЙМФРЕЙМЕ. Здесь четырёхчасовые бары собираются из тех же получасовок архива (8 в один):
     дельта бара против нормы монеты (σ), интерес за бар — «ясный» (открывали позиции) / «спорный».
  2. ENA 15.09 получила «конец тренда», и флаг закрыл ей вход. Но в том же прогоне «конец» стоял у 61 монеты
     из ~133: вынос плеча по всему рынку (голосование по Clarity), а не уход руки из монеты. И флаг не
     снимался, когда рука вернулась (16.09 интерес и дельта вверх, 17.09 03:00 белый пузырь).
     Отсюда две правки, которые применяются к near_move.json сразу после его записи (fix_near_move):
       • «вынос по доске» — если на том же часе событие конца у доли доски ≥ BOARD_END_SHARE, это фон:
         у монеты пишется leaving_kind «вынос доски», вход не закрывается;
       • «рука вернулась» — после события конца на получасовке был ясный белый пузырь и интерес сейчас выше,
         чем на баре события: флаг снимается.
     Исходное значение сохраняется в leaving_kind_raw — факты не отсекаются.

Ничего не торгует само: сигнал читает бумажный бот paper_bottom.py, звёзды и экран книги.
    python3 analytics_bottom.py --only ENA            # разбор монеты сейчас
    python3 analytics_bottom.py --fix-near-move       # показать, что поменялось бы в near_move.json
    python3 analytics_bottom.py --fix-near-move --write
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
try:
    from core_config import (BOTTOM_LOOKBACK_D, BOTTOM_NEAR_PCT, BOTTOM_CHASE_PCT, BOTTOM_BUBBLE_SIGMA,
                             BOTTOM_BUBBLE_OI_PCT, BOTTOM_BUBBLE_FRESH_4H, BOTTOM_MIN_ZA, BOTTOM_KL30_BARS,
                             BOTTOM_KL4H_BARS, BOTTOM_END_FRESH_BARS, BOTTOM_APPROACH_PCT)
except ImportError:
    BOTTOM_LOOKBACK_D, BOTTOM_NEAR_PCT, BOTTOM_CHASE_PCT = 30, 15.0, 20.0
    BOTTOM_BUBBLE_SIGMA, BOTTOM_BUBBLE_OI_PCT, BOTTOM_BUBBLE_FRESH_4H = 2.0, 1.5, 2
    BOTTOM_MIN_ZA, BOTTOM_KL30_BARS, BOTTOM_KL4H_BARS, BOTTOM_END_FRESH_BARS = 2, 4, 6, 6
    BOTTOM_APPROACH_PCT = 5.0
try:
    from core_config import BOTTOM_RANGE_MIN_PCT
except ImportError:
    BOTTOM_RANGE_MIN_PCT = 20.0     # дно имеет смысл после падения: вершина окна выше дна хотя бы на столько
try:
    from core_config import BOARD_END_SHARE, BOARD_END_MIN_COINS
except ImportError:
    BOARD_END_SHARE, BOARD_END_MIN_COINS = 0.33, 20
try:
    from core_config import FAST_END_OI_PCT, FAST_BUBBLE_SIGMA, FAST_BUBBLE_OI_PCT, KLINGER_30M_EMA
except ImportError:
    FAST_END_OI_PCT, FAST_BUBBLE_SIGMA, FAST_BUBBLE_OI_PCT, KLINGER_30M_EMA = -2.0, 2.0, 1.5, (34, 55, 13)

ARCH = BASE_DIR / "cq_v2" / "intraday"
NEAR = BASE_DIR / "output" / "near_move.json"
BAR = 1_800_000                 # получасовка, мс
B4 = 8 * BAR                    # четыре часа


def _ms(c: str) -> int:
    return int(datetime.strptime(c, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


def _hm(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%d.%m %H:%M")


def load_rows(sym: str, days: int | None = None) -> list[dict]:
    """получасовки архива монеты: по свече, повтор свечи — последняя запись, только бары с ценой"""
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    if not p.exists():
        return []
    since = None
    if days:
        since = int(datetime.now(timezone.utc).timestamp() * 1000) - days * 86_400_000
    by: dict = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        c = r.get("candle")
        if not c or not r.get("px"):
            continue
        try:
            t = _ms(c)
        except ValueError:
            continue
        if since and t < since:
            continue
        r["t"] = t
        by[t] = r
    return [by[t] for t in sorted(by)]


def _ema(xs: list, n: int) -> list:
    k, e, out = 2 / (n + 1), None, []
    for x in xs:
        e = x if e is None else x * k + e * (1 - k)
        out.append(e)
    return out


def _vol(r: dict) -> float:
    f = r.get("fut") or {}
    v = float(f.get("b") or 0) + float(f.get("s") or 0)
    return v or float((r.get("kv") or {}).get("qv") or 0)


def bars4h(rows: list[dict]) -> list[dict]:
    """четырёхчасовые бары из получасовок, границы по UTC (00, 04, 08…); только полные — все восемь свечей"""
    groups: dict = {}
    for r in rows:
        groups.setdefault(r["t"] // B4 * B4, []).append(r)
    out = []
    for t0 in sorted(groups):
        g = groups[t0]
        if len(g) < 8:
            continue
        ois = [float(r["oi"]) for r in g if r.get("oi")]
        out.append({"t": t0, "t_end": t0 + B4,
                    "o": float(g[0]["px"]), "c": float(g[-1]["px"]),
                    "h": max(float(r.get("h") or r["px"]) for r in g),
                    "l": min(float(r.get("l") or r["px"]) for r in g),
                    "d": sum(float((r.get("fut") or {}).get("d") or 0) for r in g),
                    "vol": sum(_vol(r) for r in g),
                    "oi0": ois[0] if ois else None, "oi1": ois[-1] if ois else None,
                    "long_close": sum(1 for r in g if r.get("oi_type") == "long_close")})
    return out


def klinger(bars: list[dict]) -> list[tuple]:
    """клингер как на TradingView: объём со знаком по hlc3, EMA 34/55, сигнальная 13; разогрев 55 баров"""
    f34, f55, f13 = KLINGER_30M_EMA
    sv, prev = [], None
    for b in bars:
        hlc = (float(b.get("h") or b.get("c") or b.get("px")) + float(b.get("l") or b.get("c") or b.get("px"))
               + float(b.get("c") or b.get("px"))) / 3
        v = float(b.get("vol") if "vol" in b else _vol(b))
        sv.append(v if (prev is None or hlc >= prev) else -v)
        prev = hlc
    kvo = [a - b for a, b in zip(_ema(sv, f34), _ema(sv, f55))]
    sig = _ema(kvo, f13)
    return [(kvo[i], sig[i]) if i >= f55 else (None, None) for i in range(len(bars))]


def cross_up_ago(kl: list[tuple]) -> int | None:
    """сколько баров назад клингер пересёк сигнальную снизу вверх; None — последнее пересечение было вниз"""
    for k in range(len(kl) - 1, 0, -1):
        a, b = kl[k], kl[k - 1]
        if a[0] is None or b[0] is None:
            return None
        if (a[0] > a[1]) != (b[0] > b[1]):
            return (len(kl) - 1 - k) if a[0] > a[1] else None
    return None


def bubbles4h(b4: list[dict]) -> list[dict]:
    """пузыри на 4ч: дельта бара дальше BOTTOM_BUBBLE_SIGMA σ от нормы монеты; «ясный» — интерес за бар
    вырос на BOTTOM_BUBBLE_OI_PCT и больше, «спорный» — ушёл или на баре закрывали лонги"""
    if len(b4) < 12:
        return []
    ds = [b["d"] for b in b4]
    mu, sd = st.mean(ds), (st.pstdev(ds) or 1.0)
    out = []
    for b in b4:
        z = (b["d"] - mu) / sd
        if abs(z) < BOTTOM_BUBBLE_SIGMA:
            continue
        ch = (b["oi1"] / b["oi0"] - 1) * 100 if (b["oi0"] and b["oi1"]) else None
        sure = ("спорный" if ((ch is not None and ch <= -BOTTOM_BUBBLE_OI_PCT) or b["long_close"] >= 4)
                else "ясный" if (ch is not None and ch >= BOTTOM_BUBBLE_OI_PCT) else "обычный")
        out.append({"t": b["t"], "t_end": b["t_end"], "px": b["c"], "low": b["l"],
                    "side": "buy" if z > 0 else "sell", "sure": sure, "z": round(z, 2),
                    "oi_pct": round(ch, 2) if ch is not None else None})
    return out


def bubbles30(rows: list[dict]) -> list[dict]:
    """пузыри на получасовках — те же формулы, что у карточки (render_coin._fast_events)"""
    rr = [r for r in rows if (r.get("fut") or {}).get("tk") is not None]
    if len(rr) < 30:
        return []
    ds = [float((r.get("fut") or {}).get("d") or 0) for r in rr]
    mu, sd = st.mean(ds), (st.pstdev(ds) or 1.0)
    out, prev = [], None
    for r, x in zip(rr, ds):
        o = r.get("oi")
        ch = (o / prev - 1) * 100 if (prev and o) else None
        if abs(x - mu) >= FAST_BUBBLE_SIGMA * sd:
            sure = ("спорный" if ((ch is not None and ch <= -FAST_BUBBLE_OI_PCT) or r.get("oi_type") == "long_close")
                    else "ясный" if (ch is not None and ch >= FAST_BUBBLE_OI_PCT) else "обычный")
            out.append({"t": r["t"], "px": r["px"], "side": "buy" if x > 0 else "sell", "sure": sure})
        if o:
            prev = o
    return out


def end_bars(rows: list[dict]) -> list[int]:
    """событие конца на получасовке: интерес за бар ≤ FAST_END_OI_PCT при отрицательной дельте"""
    out, prev = [], None
    for r in rows:
        o = r.get("oi")
        if prev and o and (o / prev - 1) * 100 <= FAST_END_OI_PCT and float((r.get("fut") or {}).get("d") or 0) < 0:
            out.append(r["t"])
        if o:
            prev = o
    return out


def board_end_share(all_ends: dict, t: int, n_coins: int) -> float:
    """доля монет доски с событием конца в том же часе (бар события ± одна получасовка)"""
    if not n_coins:
        return 0.0
    hit = sum(1 for ts in all_ends.values() if any(abs(x - t) <= BAR for x in ts))
    return hit / n_coins


def board_ends(syms: list[str] | None = None, days: int = 3) -> tuple[dict, int]:
    """события конца по всей доске за последние дни: sym → [t]; второе — сколько монет с баром"""
    files = sorted(ARCH.glob("*.jsonl")) if not syms else [ARCH / f"{s.replace('USDT', '').lower()}.jsonl" for s in syms]
    ends, n = {}, 0
    for p in files:
        rows = load_rows(p.stem, days=days)
        if len(rows) < 10:
            continue
        n += 1
        ends[p.stem.upper() + "USDT"] = end_bars(rows)
    return ends, n


def _approaches(b4: list[dict], bottom: float) -> list[dict]:
    """заходы к дну на 4ч: бары с минимумом в BOTTOM_APPROACH_PCT от дна, соседние — один заход"""
    out, last_i = [], -99
    for i, b in enumerate(b4):
        if b["l"] <= bottom * (1 + BOTTOM_APPROACH_PCT / 100):
            if i - last_i >= 3 or not out:
                out.append({"t": b["t"], "vol": b["vol"], "low": b["l"]})
            else:
                out[-1]["vol"] = max(out[-1]["vol"], b["vol"])
                out[-1]["low"] = min(out[-1]["low"], b["l"])
            last_i = i
    return out


def _leader_block(sym: str) -> str | None:
    """«тянет одна» (12.09): живой памп-лидер — не эта монета — и нет «заходят многие» → вход закрыт"""
    try:
        from core_config import PUMP_LEADERS_PATH as _pl
    except ImportError:
        _pl = BASE_DIR / "output" / "pump_leaders.json"
    try:
        recs = json.loads(Path(_pl).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    live = [r for r in (recs.values() if isinstance(recs, dict) else recs)
            if isinstance(r, dict) and r.get("symbol") and not r.get("retired_at")]
    if not live:
        return None
    lead = max(live, key=lambda r: r.get("run_pct") or 0)
    if str(lead["symbol"]).upper() == sym.upper():
        return None
    try:
        ml = (json.loads(NEAR.read_text(encoding="utf-8")) or {}).get("many_lead") or {}
        if ml.get("until") and datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") < str(ml["until"]):
            return None
    except (OSError, ValueError):
        pass
    return f"тянет одна: {str(lead['symbol']).replace('USDT', '')} +{float(lead.get('run_pct') or 0):.0f}%"


def analyse(sym: str, rows: list[dict] | None = None, ends: tuple | None = None, upto: int | None = None) -> dict:
    """разбор монеты на последнем закрытом баре (или на баре upto — для прогона по истории)"""
    sym = sym.upper() + ("" if sym.upper().endswith("USDT") else "USDT")
    rows = rows if rows is not None else load_rows(sym, days=BOTTOM_LOOKBACK_D + 3)
    if upto is not None:
        rows = [r for r in rows if r["t"] <= upto]
    out = {"sym": sym, "ok": False, "za": [], "protiv": [], "why": ""}
    if len(rows) < 60:
        out["why"] = f"архив короткий: {len(rows)} баров"
        return out
    last = rows[-1]
    now_t, px = last["t"], float(last["px"])
    look = [r for r in rows if r["t"] >= now_t - BOTTOM_LOOKBACK_D * 86_400_000]
    bot_r = min(look, key=lambda r: float(r.get("l") or r["px"]))
    bottom = float(bot_r.get("l") or bot_r["px"])
    top = max(float(r.get("h") or r["px"]) for r in look)
    b4 = [b for b in bars4h(rows) if b["t_end"] <= now_t + BAR]
    bub4 = bubbles4h(b4)
    fresh_from = (b4[-BOTTOM_BUBBLE_FRESH_4H]["t"] if len(b4) >= BOTTOM_BUBBLE_FRESH_4H else 0)
    buy = next((b for b in reversed(bub4) if b["side"] == "buy" and b["sure"] == "ясный" and b["t"] >= fresh_from), None)
    out.update({"px": px, "t": now_t, "bottom": bottom, "bottom_t": bot_r["t"], "top": top,
                "range_pct": round((top / bottom - 1) * 100, 1),
                "dist_now_pct": round((px / bottom - 1) * 100, 2),
                "bub4": bub4[-6:], "bubble": buy})
    # вердикт карточки по заходам: «второй заход к дну тише» — её правило входа (дно снимают на тихом обороте)
    ap = _approaches(b4, bottom)
    out["approaches"] = len(ap)
    out["second_quiet"] = (ap[-1]["vol"] < ap[-2]["vol"]) if len(ap) >= 2 else None
    out["card_rule"] = ("заход к дну один" if len(ap) < 2 else
                        "второй заход к дну тише" if out["second_quiet"] else "второй заход к дну не тише")
    if out["range_pct"] < BOTTOM_RANGE_MIN_PCT:
        # у ровной монеты любой бар «у дна» — это не дно, а середина пилы
        out["why"] = f"дна нет: вершина окна выше дна лишь на {out['range_pct']:.0f}%"
        return out
    if not buy:
        out["why"] = "ясного белого пузыря на 4ч за последние " + str(BOTTOM_BUBBLE_FRESH_4H) + " бара нет"
        return out
    dist_b = (buy["low"] / bottom - 1) * 100
    out["dist_bubble_pct"] = round(dist_b, 2)
    if dist_b > BOTTOM_NEAR_PCT:
        out["why"] = f"пузырь не у дна: +{dist_b:.1f}% от дна {bottom:.6g}"
        return out
    if out["dist_now_pct"] > BOTTOM_CHASE_PCT:
        out["why"] = f"цена ушла от дна на {out['dist_now_pct']:.1f}% — не догоняем"
        return out
    # ── ЗА
    za = [("пузырь 4ч", f"{_hm(buy['t'])} · σ {buy['z']:+.1f} · интерес {buy['oi_pct']:+.1f}%")]
    kl30 = klinger(rows)
    a30 = cross_up_ago(kl30)
    if a30 is not None and a30 <= BOTTOM_KL30_BARS:
        za.append(("клингер 30м", f"крест вверх {a30 * 0.5:g} ч назад"))
    kl4 = klinger(b4)
    a4 = cross_up_ago(kl4)
    if a4 is not None and a4 <= BOTTOM_KL4H_BARS:
        za.append(("клингер 4ч", f"крест вверх {a4 * 4} ч назад"))
    day = [r for r in rows if r["t"] > now_t - 86_400_000]
    ois = [float(r["oi"]) for r in day if r.get("oi")]
    oi24 = (ois[-1] / ois[0] - 1) * 100 if len(ois) >= 2 and ois[0] else None
    if oi24 is not None and oi24 > 0:
        za.append(("интерес за сутки", f"{oi24:+.1f}%"))
    d24 = sum(float((r.get("fut") or {}).get("d") or 0) for r in day)
    if d24 > 0:
        za.append(("дельта за сутки", f"+{d24 / 1e3:.0f}K"))
    b30 = [b for b in bubbles30(rows) if b["t"] > now_t - 8 * BAR and b["side"] == "buy" and b["sure"] == "ясный"]
    if b30:
        za.append(("пузырь 30м", _hm(b30[-1]["t"])))
    # ── ПРОТИВ
    protiv = []
    my_ends = [t for t in end_bars(rows) if t > now_t - BOTTOM_END_FRESH_BARS * BAR]
    if my_ends:
        t_e = my_ends[-1]
        share = board_end_share(ends[0], t_e, ends[1]) if ends else 0.0
        if share >= BOARD_END_SHARE and (ends and ends[1] >= BOARD_END_MIN_COINS):
            za.append(("конец — вынос по доске", f"{_hm(t_e)} · у {share * 100:.0f}% доски"))
        else:
            protiv.append(("событие конца", _hm(t_e)))
    sell = next((b for b in bub4 if b["side"] == "sell" and b["sure"] == "ясный" and b["t"] > buy["t"]), None)
    if sell:
        protiv.append(("пузырь продажи 4ч после", _hm(sell["t"])))
    lb = _leader_block(sym)
    if lb:
        protiv.append(("фон", lb))
    out.update({"za": za, "protiv": protiv, "oi24": oi24, "d24": d24,
                "kl30_ago": a30, "kl4_ago": a4})
    n_za = len([z for z in za if z[0] != "пузырь 4ч"])
    if protiv:
        out["why"] = "против: " + "; ".join(f"{k} {v}" for k, v in protiv)
    elif n_za < BOTTOM_MIN_ZA:
        out["why"] = f"доводов за {n_za} из нужных {BOTTOM_MIN_ZA}"
    else:
        out["ok"] = True
        out["why"] = "пузырь у дна · " + "; ".join(f"{k} {v}" for k, v in za)
    return out


def fix_near_move(write: bool = False, path: Path | None = None) -> dict:
    """правки «конца» в near_move.json: вынос по доске и рука вернулась (исходное — в leaving_kind_raw)"""
    path = path or NEAR
    try:
        nm = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"note": "near_move.json не читается"}
    coins = nm.get("coins") or {}
    ends, n = board_ends(days=2)
    board, back, kept = [], [], []
    for sym, v in coins.items():
        td = v.get("today") or {}
        if td.get("leaving_kind") != "конец":
            continue
        rows = load_rows(sym, days=5)
        my = end_bars(rows)
        if not my:
            kept.append(sym)
            continue
        t_e = my[-1]
        share = board_end_share(ends, t_e, n)
        if share >= BOARD_END_SHARE and n >= BOARD_END_MIN_COINS:
            td["leaving_kind_raw"] = "конец"
            td["leaving_kind"] = "вынос доски"
            td["today"] = "вынос по доске · вход открыт"
            td["end_fix"] = {"kind": "вынос доски", "t": _hm(t_e), "share": round(share, 2), "board": n}
            board.append(sym)
            continue
        e_row = next((r for r in rows if r["t"] == t_e), None)
        oi_e = float(e_row["oi"]) if (e_row and e_row.get("oi")) else None
        oi_now = next((float(r["oi"]) for r in reversed(rows) if r.get("oi")), None)
        wb = [b for b in bubbles30(rows) if b["t"] > t_e and b["side"] == "buy" and b["sure"] == "ясный"]
        if wb and oi_e and oi_now and oi_now > oi_e:
            td["leaving_kind_raw"] = "конец"
            td["leaving_kind"] = None
            td["today"] = "рука вернулась"
            td["end_fix"] = {"kind": "рука вернулась", "t": _hm(t_e), "bubble": _hm(wb[-1]["t"]),
                             "oi_since_pct": round((oi_now / oi_e - 1) * 100, 2)}
            back.append(sym)
        else:
            kept.append(sym)
    res = {"board": board, "back": back, "kept": kept, "coins_with_bars": n}
    if write and (board or back):
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(nm, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--fix-near-move", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.fix_near_move:
        r = fix_near_move(write=a.write)
        if r.get("note"):
            print("конец: " + r["note"])
            return 0
        print(f"конец: вынос по доске {len(r['board'])}, рука вернулась {len(r['back'])}, "
              f"остался конец {len(r['kept'])} · монет с барами {r['coins_with_bars']}"
              + ("" if a.write else " (без записи)"))
        if r["back"]:
            print("  рука вернулась: " + ", ".join(s.replace("USDT", "") for s in r["back"]))
        return 0
    syms = [s.strip() for s in (a.only or "").split(",") if s.strip()]
    if not syms:
        print("укажите --only МОНЕТА")
        return 1
    ends = board_ends(days=2)
    for s in syms:
        r = analyse(s, ends=ends)
        print(f"{r['sym']}: {'СИГНАЛ' if r['ok'] else 'нет'} · {r['why']}")
        if r.get("px"):
            print(f"  цена {r['px']:.6g} · дно {r['bottom']:.6g} ({_hm(r['bottom_t'])}) · от дна {r['dist_now_pct']:+.1f}% · {r['card_rule']}")
        for k, v in r.get("za") or []:
            print(f"  за: {k} · {v}")
        for k, v in r.get("protiv") or []:
            print(f"  против: {k} · {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
