#!/usr/bin/env python3
"""СТАКАН ПО ПЕРВЫМ (15.09, владелец: «по первым каждый прогон смотреть, где примерно висят толстые заявки —
это ближе к пониманию, вынесут шорты или нет»). Стакан Binance Futures отдаёт бесплатно: `depth`, до тысячи
уровней на сторону, вес 50 за запрос. Coinglass для этого не нужен.

Что делает каждый прогон по монетам ПЕРВЫХ (звёзды `near_move.first`), первым DEPTH_TOP_N очереди и КНИГЕ:
  1. снимок ВСЕГО стакана, что отдаёт биржа (до 1000 уровней на сторону — сколько это в процентах, зависит от
     шага цены монеты; покрытие пишется: «виден до +64% / −38%»). Владелец 15.09: «±10% мало, когда может улететь
     в 10–20 раз; плотняк рядом мы и по ликвидациям видим» — поэтому ближние стены (до DEPTH_NEAR_PCT) считаются
     ближними и на карточке не главные, главное — СРЕДНИЕ и ДАЛЬНИЕ: потолок и пол стакана;
     свёртка — по шагам DEPTH_STEP_PCT в первые 10%, дальше по 5%, дальше по 25% (для чтения формы);
  2. СТЕНЫ — одиночные уровни, где стоит больше DEPTH_WALL_X медианного уровня: цена, размер $, сторона, зона
     (ближняя / средняя / дальняя); плюс СПОТ-стакан той же монеты, если пара есть на споте — там стоят запасы
     маркетмейкера, и потолок обычно виден именно там;
  3. судьба стен: по прошлым снимкам — сколько прогонов стоит; исчезла — «сняли» (цена не дошла) или «съели»
     (цена прошла сквозь). Это и есть ответ на вопрос: стены над ценой перед выносом — их снимают или в них раздают;
  4. пишет архив `cq_v2/depth/<монета>.jsonl` (строка на снимок) и `output/depth.json` для карточки.

Сеть — через core_binance.get_depth, если он есть (общий лимитер); нет — свой запрос к тому же адресу с пометкой
в логе: вес 50 на монету, пять монет — 250 в полчаса, лимит биржи 2400 в минуту.
Запуск руками: `python3 depth_fetch.py --only ARK` (печать без записи), `--write`.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import DEPTH_LIMIT, DEPTH_RANGE_PCT, DEPTH_STEP_PCT, DEPTH_TOP_N, DEPTH_WALL_X, DEPTH_MIN_WALL_USD
except ImportError:
    DEPTH_LIMIT, DEPTH_RANGE_PCT, DEPTH_STEP_PCT, DEPTH_TOP_N, DEPTH_WALL_X, DEPTH_MIN_WALL_USD = 1000, 10.0, 0.5, 3, 8.0, 20000.0
try:
    from core_config import DEPTH_NEAR_PCT, DEPTH_MID_PCT, DEPTH_SPOT
except ImportError:
    DEPTH_NEAR_PCT, DEPTH_MID_PCT, DEPTH_SPOT = 5.0, 30.0, True

OUT_DIR = BASE_DIR / "cq_v2" / "depth"
STATE = BASE_DIR / "output" / "depth.json"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def get_depth(sym: str, limit: int = DEPTH_LIMIT) -> dict | None:
    """Сырой стакан {bids: [[px, qty]...], asks: [...]}. Сначала core_binance (общий лимитер), потом свой запрос."""
    try:
        import core_binance as cb
        fn = getattr(cb, "get_depth", None) or getattr(cb, "depth", None)
        if fn:
            return fn(sym, limit)
    except Exception:  # noqa: BLE001
        pass
    import urllib.request as u
    url = f"https://fapi.binance.com/fapi/v1/depth?symbol={sym}&limit={limit}"
    try:
        with u.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def get_spot_depth(sym: str, limit: int = DEPTH_LIMIT) -> dict | None:
    """Спот-стакан той же пары (api.binance.com). Нет пары на споте — None."""
    try:
        import core_binance as cb
        fn = getattr(cb, "get_spot_depth", None)
        if fn:
            return fn(sym, limit)
    except Exception:  # noqa: BLE001
        pass
    import urllib.request as u
    url = f"https://api.binance.com/api/v3/depth?symbol={sym}&limit={limit}"
    try:
        with u.urlopen(url, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return None


def zone(dist_pct: float) -> str:
    d = abs(dist_pct)
    return "ближняя" if d < DEPTH_NEAR_PCT else "средняя" if d < DEPTH_MID_PCT else "дальняя"


def coins_to_watch() -> list[str]:
    """Первые (звёзды), первые DEPTH_TOP_N очереди и книга позиций — по ним и смотрим стены."""
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out: list[str] = []
    for s in (nm.get("first") or []):
        out.append(str(s).upper())
    for s in (nm.get("queue") or [])[:DEPTH_TOP_N]:
        s = s if isinstance(s, str) else (s or {}).get("sym")
        if s:
            out.append(str(s).upper())
    book = _read(BASE_DIR / "output" / "book.json") or _read(BASE_DIR / "book.json") or {}
    for s in (book.keys() if isinstance(book, dict) else []):
        if not str(s).startswith("_"):
            out.append(str(s).upper() + ("" if str(s).upper().endswith("USDT") else "USDT"))
    seen, res = set(), []
    for s in out:
        s = s if s.endswith("USDT") else s + "USDT"
        if s not in seen:
            seen.add(s)
            res.append(s)
    return res


def _bucket(dist_pct: float) -> str:
    """Ключ шага для свёртки формы стакана: 0.5% до 10%, потом 5%, потом 25%."""
    d = abs(dist_pct)
    if d < 10:
        return f"{int(d // DEPTH_STEP_PCT) * DEPTH_STEP_PCT:.1f}"
    if d < 100:
        return f"{int(d // 5) * 5}"
    return f"{int(d // 25) * 25}"


def snapshot(sym: str, raw: dict, ts_ms: int, kind: str = "perp") -> dict | None:
    bids = [(float(p), float(q)) for p, q in (raw.get("bids") or []) if float(q) > 0]
    asks = [(float(p), float(q)) for p, q in (raw.get("asks") or []) if float(q) > 0]
    if not bids or not asks:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2
    steps_b: dict[str, float] = {}
    steps_a: dict[str, float] = {}
    for p, q in bids:
        k = _bucket((p / mid - 1) * 100)
        steps_b[k] = steps_b.get(k, 0.0) + p * q
    for p, q in asks:
        k = _bucket((p / mid - 1) * 100)
        steps_a[k] = steps_a.get(k, 0.0) + p * q
    lv = sorted([p * q for p, q in bids] + [p * q for p, q in asks])
    med = lv[len(lv) // 2] if lv else 0.0
    thr = max(DEPTH_MIN_WALL_USD, med * DEPTH_WALL_X)
    walls = []
    for side, arr in (("bid", bids), ("ask", asks)):
        for p, q in arr:
            usd = p * q
            if usd >= thr:
                d = round((p / mid - 1) * 100, 2)
                walls.append({"side": side, "px": p, "usd": round(usd, 0), "dist_pct": d, "zone": zone(d), "kind": kind})
    walls.sort(key=lambda w: -w["usd"])
    cover_up = round((asks[-1][0] / mid - 1) * 100, 1)
    cover_dn = round((bids[-1][0] / mid - 1) * 100, 1)
    near_b = sum(p * q for p, q in bids if p >= mid * (1 - DEPTH_NEAR_PCT / 100))
    near_a = sum(p * q for p, q in asks if p <= mid * (1 + DEPTH_NEAR_PCT / 100))
    return {
        "t": ts_ms, "sym": sym, "kind": kind, "mid": mid,
        "cover_up_pct": cover_up, "cover_dn_pct": cover_dn,
        "bid_usd": round(sum(p * q for p, q in bids), 0), "ask_usd": round(sum(p * q for p, q in asks), 0),
        "near_bid_usd": round(near_b, 0), "near_ask_usd": round(near_a, 0),
        "imbalance": round((near_b - near_a) / max(1.0, near_b + near_a), 3),
        "steps_bid": steps_b, "steps_ask": steps_a,
        "level_med_usd": round(med, 0), "wall_thr_usd": round(thr, 0),
        "walls": walls[:24],
    }


def _history(sym: str, n: int = 48) -> list[dict]:
    p = OUT_DIR / f"{sym.replace('USDT', '').lower()}.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines()[-n:]:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def fate(sym: str, snap: dict, hist: list[dict]) -> dict:
    """Судьба стен: у нынешних — сколько снимков подряд стоят (на той же цене ± шаг); у прошлых, которых нет, —
    «съели» (mid прошёл цену стены) или «сняли» (не дошёл). Возвращает и то и другое."""
    def same(a: dict, b: dict) -> bool:
        return a["side"] == b["side"] and a.get("kind", "perp") == b.get("kind", "perp") and abs(a["px"] - b["px"]) / max(1e-12, b["px"]) <= DEPTH_STEP_PCT / 200
    stood = []
    for w in snap["walls"]:
        n = 1
        for h in reversed(hist):
            if any(same(w, x) for x in h.get("walls") or []):
                n += 1
            else:
                break
        stood.append(dict(w, runs=n))
    gone = []
    if hist:
        prev = hist[-1]
        for w in prev.get("walls") or []:
            if any(same(w, x) for x in snap["walls"]):
                continue
            crossed = (w["side"] == "ask" and snap["mid"] >= w["px"]) or (w["side"] == "bid" and snap["mid"] <= w["px"])
            n = 1
            for h in reversed(hist[:-1]):
                if any(same(w, x) for x in h.get("walls") or []):
                    n += 1
                else:
                    break
            gone.append(dict(w, runs=n, fate="съели" if crossed else "сняли", at=snap["t"]))
    return {"walls": stood, "gone": gone}


def read_walls(sym: str, snap: dict, ft: dict) -> str:
    """Одной строкой для лога и карточки: сначала ДАЛЬНИЕ и СРЕДНИЕ стены (потолок и пол), ближние — в конце;
    покрытие стакана, судьба ушедших."""
    def fmt(w):
        return f"{w['px']:.6g} ({w['dist_pct']:+.1f}%, ${w['usd']/1e3:.0f}K, {w['runs']} пр.)"
    far_a = [w for w in ft["walls"] if w["side"] == "ask" and w["zone"] != "ближняя"][:3]
    far_b = [w for w in ft["walls"] if w["side"] == "bid" and w["zone"] != "ближняя"][:3]
    near_a = [w for w in ft["walls"] if w["side"] == "ask" and w["zone"] == "ближняя"][:2]
    near_b = [w for w in ft["walls"] if w["side"] == "bid" and w["zone"] == "ближняя"][:2]
    parts = [f"виден до {snap['cover_up_pct']:+.0f}% / {snap['cover_dn_pct']:+.0f}%"]
    if far_a:
        parts.append("потолок: " + ", ".join(fmt(w) for w in far_a))
    if far_b:
        parts.append("пол: " + ", ".join(fmt(w) for w in far_b))
    if near_a or near_b:
        parts.append("рядом: " + ", ".join(("аск " if w["side"] == "ask" else "бид ") + fmt(w) for w in near_a + near_b))
    for g in ft["gone"][:2]:
        parts.append(f"{'аск' if g['side']=='ask' else 'бид'} {g['px']:.6g} ${g['usd']/1e3:.0f}K — {g['fate']} после {g['runs']} пр.")
    parts.append(f"перекос {snap['imbalance']:+.2f}")
    return " · ".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="монеты через запятую")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    syms = [x.strip().upper() for x in a.only.split(",")] if a.only else coins_to_watch()
    syms = [s if s.endswith("USDT") else s + "USDT" for s in syms]
    ts = int(time.time() // 60 * 60 * 1000)
    state = {"at": ts, "coins": {}}
    n_ok = 0
    for sym in syms:
        raw = get_depth(sym)
        if not raw:
            print(f"depth: {sym} — стакан не получен")
            continue
        snap = snapshot(sym, raw, ts)
        if not snap:
            continue
        if DEPTH_SPOT:
            sraw = get_spot_depth(sym)
            ssnap = snapshot(sym, sraw, ts, kind="spot") if sraw else None
            if ssnap:
                snap["spot"] = {k: ssnap[k] for k in ("mid", "cover_up_pct", "cover_dn_pct", "bid_usd", "ask_usd", "walls")}
                snap["walls"] = sorted(snap["walls"] + ssnap["walls"], key=lambda w: -w["usd"])[:24]
        hist = _history(sym)
        ft = fate(sym, snap, hist)
        line = read_walls(sym, snap, ft)
        print(f"depth: {sym} mid {snap['mid']:.6g} · {line}")
        state["coins"][sym] = dict(snap, walls=ft["walls"], gone=ft["gone"], read=line)
        if a.write:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            with (OUT_DIR / f"{sym.replace('USDT', '').lower()}.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        n_ok += 1
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
        print(f"depth: записано {n_ok} из {len(syms)} → {OUT_DIR}, состояние → {STATE}")
    else:
        print(f"depth: {n_ok} из {len(syms)} (без записи; --write чтобы записать)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
