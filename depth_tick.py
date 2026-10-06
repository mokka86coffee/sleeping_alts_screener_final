#!/usr/bin/env python3
"""ПЛИТЫ СТАКАНА РАЗ В ТРИ МИНУТЫ (25.09, владелец: «нужны две вещи — сделки из новой стратегии и те монеты, что я
заношу в файл руками; по ним проверка плит раз в три минуты»).

Зовёт run.py --loop своим потоком раз в три минуты. Монеты — открытые сделки «3 в первых подряд»
(output/paper_first3.json) и монеты watch.json. По каждой: снимок стакана фьючерса и спота и судьба стен — функциями depth_fetch (те же пороги
стены, то же «съели / сняли»). Снимки держатся в своей памяти output/depth_tick.json — получасовой стакан, его
архив и карточка не трогаются.

Тревога — как у прогона (run.py _fast_alerts): ушла стена, простоявшая не меньше DEPTH_TICK_MIN_SNAPS снимков,
не дальше 30% от цены. Строка «⏱ МОМЕНТ» в том же виде, вместо «после N пр.» — «стояла N мин».
Ключи отправленного — в общем output/alerts_sent.json с меткой tick: прогон по той же стене второй раз не шлёт.

СТАКАН ПО ВСЕМ ОТКРЫТЫМ СДЕЛКАМ (27.09, владелец: «половина позиций в плюс, половина в минус при одних и тех же условиях —
нужна доп. проверка по стакану; какой размер плит относительно объёма или капитализации влияет»). Монеты — ещё и открытые
сделки всех книг output/paper_*.json. Телеграм как был: только «3 в первых» и watch.json. По всем монетам каждое событие
(поставили / съели / убрали, не дальше 30% от цены) — строкой в output/depth_events.jsonl: сделки монеты (книга, сторона,
вход), размер плиты в $ и её доля к обороту фьючерса за сутки, к обороту последнего часа, к интересу и к капитализации
(обращение Binance × цена, кэш на час output/depth_mcap.json). Это данные для счёта; книги журнал пока не читают.
Сбор в 4 потока (последовательно 80 монет ≈ 160 с, а прогон даёт шагу 150 с), через DEADLINE_S что не успело — пропуск.

    python3 depth_tick.py              # что ушло бы сейчас, без записи и без телеграма
    python3 depth_tick.py --write      # снимок, память, телеграм, журнал событий (так зовёт run.py)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from core_time import msg_hm   # 06.10: подписи — в поясе владельца, не машины
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import DEPTH_TICK_MIN_SNAPS, DEPTH_SPOT
except ImportError:
    DEPTH_TICK_MIN_SNAPS, DEPTH_SPOT = 10, True

import depth_fetch as df

FIRST3 = BASE_DIR / "output" / "paper_first3.json"
WATCH = BASE_DIR / "watch.json"
MEM = BASE_DIR / "output" / "depth_tick.json"
SENT = BASE_DIR / "output" / "alerts_sent.json"
SNAP_MIN = 3
try:
    from core_config import DEPTH_TICK_REMOVED_MIN_MIN as _REMOVED_MIN
except ImportError:
    _REMOVED_MIN = 180
KEEP = 40                      # снимков на монету — два часа, дольше судьбе смотреть незачем
FAR_PCT = 30                   # дальше — застрявшие продавцы, как в run.py _fast_alerts
EVENTS = BASE_DIR / "output" / "depth_events.jsonl"
BAN = BASE_DIR / "output" / "binance_ban.json"   # 27.09 18:37 бан фьючерсного API (418): до этого времени фьючерсы не трогаем
try:
    from core_config import DEPTH_LIMIT, BINANCE_FAPI, BINANCE_SPOT, WEIGHT_SOFT_LIMIT
except ImportError:
    DEPTH_LIMIT, BINANCE_FAPI, BINANCE_SPOT, WEIGHT_SOFT_LIMIT = 1000, "https://fapi.binance.com", "https://api.binance.com", 1900
_STOP = {"fut": False, "spot": False, "used": 0.0}
MCAP = BASE_DIR / "output" / "depth_mcap.json"
WORKERS = 4
DEADLINE_S = 110               # прогон рвёт шаг на 150 с
SIDE_DEFAULT = {"end": -1}     # книги без поля side: «конец» — только шорты; first3, second, book — только лонги


def _read(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def coins() -> list[str]:
    """сделки нового бота, потом монеты владельца; повторы схлопываются"""
    out = list(((_read(FIRST3, {}) or {}).get("open") or {}).keys())
    for c in (_read(WATCH, {}) or {}).get("coins") or []:
        s = str((c or {}).get("sym") or "").upper()
        if s:
            out.append(s if s.endswith("USDT") else s + "USDT")
    return list(dict.fromkeys(s.upper() for s in out))


def trades() -> dict[str, list[dict]]:
    """открытые сделки всех книг: монета → [{книга, сторона, вход, когда}]"""
    out: dict[str, list[dict]] = {}
    for p in sorted((BASE_DIR / "output").glob("paper_*.json")):
        d = _read(p, {})
        o = d.get("open") if isinstance(d, dict) else None
        if not isinstance(o, dict):
            continue
        book = p.stem[len("paper_"):]
        for s, v in o.items():
            v = v if isinstance(v, dict) else {}
            out.setdefault(str(s).upper(), []).append({
                "book": book, "side": v.get("side") or SIDE_DEFAULT.get(book, 1),
                "px": v.get("px") or v.get("entry_px"),
                "at": v.get("opened_at") or v.get("at") or v.get("entry_at"),
            })
    return out


def _mult(base: str, cs: dict) -> tuple[str, float]:
    """1000BONK на фьючерсе = BONK на споте, цена за тысячу"""
    if base in cs:
        return base, 1.0
    for pre, m in (("1000000", 1e6), ("1000", 1e3), ("1M", 1e6)):
        if base.startswith(pre) and base[len(pre):] in cs:
            return base[len(pre):], m
    return base, 1.0


def market(write: bool) -> dict:
    """оборот фьючерсов за сутки и цена (один запрос на весь рынок) + обращение монет (раз в час)"""
    out = {"qv": {}, "px": {}, "cs": {}}
    try:
        import core_binance as cb
        for t in cb.get_futures_tickers():
            out["qv"][t["symbol"]] = float(t.get("quoteVolume") or 0)
            out["px"][t["symbol"]] = float(t.get("lastPrice") or 0)
    except Exception as e:  # noqa: BLE001
        print(f"depth_tick: тикеры не получены: {type(e).__name__}")
    mc = _read(MCAP, {}) or {}
    if time.time() - float(mc.get("t") or 0) > 3600:
        import urllib.request as u
        try:
            with u.urlopen("https://www.binance.com/bapi/asset/v2/public/asset-service/product/get-products?includeEtf=true",
                           timeout=15) as r:
                rows = json.loads(r.read().decode("utf-8")).get("data") or []
            cs = {str(x.get("b")): float(x["cs"]) for x in rows if x.get("cs")}
            if cs:
                mc = {"t": int(time.time()), "cs": cs}
                if write:
                    from sources_storage import write_atomic
                    write_atomic(MCAP, json.dumps(mc, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            print(f"depth_tick: обращение монет не получено: {type(e).__name__}")
    out["cs"] = mc.get("cs") or {}
    return out


def extra(sym: str) -> dict:
    """для монет с событием: оборот последнего закрытого часа и интерес в $"""
    res = {}
    try:
        import core_binance as cb
        kl = cb.get_klines(sym, "1h", 3)
        if kl:
            res["vol1h"] = float(kl[-1][7])
        res["oi"] = cb.get_open_interest(sym)
    except Exception:  # noqa: BLE001
        pass
    return res


def banned(kind: str) -> float:
    until = float((_read(BAN, {}) or {}).get(kind) or 0)
    return until if until > time.time() else 0.0


def _ban(kind: str, sec: float) -> None:
    from sources_storage import write_atomic
    b = _read(BAN, {}) or {}
    b[kind] = max(float(b.get(kind) or 0), time.time() + sec)
    write_atomic(BAN, json.dumps(b))


def _get(kind: str, sym: str, url: str | None = None):
    """стакан напрямую (не через core_http: его пауза при 418 ждёт Retry-After и держала бы шаг дольше 150 с). Вес всех процессов
    видим по X-MBX-USED-WEIGHT-1M: дошли до WEIGHT_SOFT_LIMIT — фьючерсы в этом шаге больше не берём; 418/429 — стоп и запись бана."""
    import urllib.request as u
    import urllib.error as ue
    if _STOP[kind] or banned(kind):
        return None
    url = url or (f"{BINANCE_FAPI}/fapi/v1/depth" if kind == "fut" else f"{BINANCE_SPOT}/api/v3/depth") + f"?symbol={sym}&limit={DEPTH_LIMIT}"
    try:
        with u.urlopen(url, timeout=10) as r:
            used = r.headers.get("X-MBX-USED-WEIGHT-1M")
            if used and kind == "fut":
                _STOP["used"] = max(_STOP["used"], float(used))
                if float(used) >= WEIGHT_SOFT_LIMIT:
                    _STOP["fut"] = True
            return json.loads(r.read().decode("utf-8"))
    except ue.HTTPError as e:
        if e.code in (418, 429):
            _STOP[kind] = True
            try:
                sec = float(e.headers.get("Retry-After") or 60)
            except (TypeError, ValueError):
                sec = 60.0
            _ban(kind, sec)
            print(f"depth_tick: {kind} HTTP {e.code}, пауза {sec:.0f} с")
        return None
    except Exception:  # noqa: BLE001
        return None


def take(sym: str, ts: int) -> dict | None:
    raw = _get("fut", sym)
    snap = df.snapshot(sym, raw, ts) if raw else None
    if not snap:
        return None
    near = {"perp": {"bid": snap["near_bid_usd"], "ask": snap["near_ask_usd"]}}
    if DEPTH_SPOT:
        sraw = _get("spot", sym)
        ss = df.snapshot(sym, sraw, ts, kind="spot") if sraw else None
        if ss:
            snap["walls"] = sorted(snap["walls"] + ss["walls"], key=lambda w: -w["usd"])[:24]
            near["spot"] = {"bid": ss["near_bid_usd"], "ask": ss["near_ask_usd"]}
    return {"t": snap["t"], "mid": snap["mid"], "walls": snap["walls"], "near": near}


def _range(sym: str, t_from: int, t_to: int) -> dict:
    """28.09 (SEI 0.086: цена прошла плиту между снимками и вернулась — снимок записал «убрали»): хай и лоу трёхминутных свечей между
    двумя снимками, фьючерс и спот — плиту, которую цена прошла свечой, считаем съеденной, даже если к снимку цена вернулась"""
    out = {}
    for kind, base in (("perp", f"{BINANCE_FAPI}/fapi/v1/klines"), ("spot", f"{BINANCE_SPOT}/api/v3/klines")):
        k = _get("fut" if kind == "perp" else "spot", sym, f"{base}?symbol={sym}&interval=3m&startTime={t_from // 180_000 * 180_000}&endTime={t_to + 59_999}&limit=10")
        if isinstance(k, list) and k:
            out[kind] = (max(float(x[2]) for x in k), min(float(x[3]) for x in k))
    return out


def _recross(ft: dict, rng: dict) -> None:
    """«сняли» → «съели», если свеча между снимками дошла до цены плиты"""
    for g in ft["gone"]:
        r = rng.get(g.get("kind", "perp"))
        if g["fate"] == "съели" or not r:
            continue
        if (g["side"] == "ask" and r[0] >= g["px"]) or (g["side"] == "bid" and r[1] <= g["px"]):
            g["fate"], g["by_wick"] = "съели", True


def _w(w: dict) -> dict:
    return {"px": w["px"], "usd": w["usd"], "dist": w.get("dist_pct"), "runs": w.get("runs")}


def side_rows(sym: str, snap: dict, prev: dict, ft: dict) -> list[dict]:
    """по каждой стороне (фьючерс/спот × пол/потолок), где плиты поменялись: все плиты до и после, ушедшие (съели/сняли),
    новые, масса стороны в 5% от цены до и после. Классы («одна из стопки», «переставили», «вся опора») строит счёт."""
    # в снимке только 24 крупнейшие плиты на монету: плита меньше последней могла не уйти, а выпасть из списка — счёт её отсекает по cut_usd
    cut = min((w["usd"] for w in snap["walls"]), default=0) if len(snap["walls"]) >= 24 else 0
    rows = []
    for kind in ("perp", "spot"):
        for side in ("bid", "ask"):
            ok = lambda w: w["side"] == side and w.get("kind", "perp") == kind and abs(w.get("dist_pct") or 0) <= FAR_PCT  # noqa: E731
            gone = [dict(_w(g), fate="съели" if g["fate"] == "съели" else "убрали") for g in ft["gone"] if ok(g)]
            new = [_w(w) for w in ft["walls"] if ok(w) and w["runs"] == 1]
            if not gone and not new:
                continue
            nb, na = (prev.get("near") or {}).get(kind) or {}, (snap.get("near") or {}).get(kind) or {}
            rows.append({
                "t": snap["t"], "sym": sym, "kind": kind, "side": side, "mid": snap["mid"], "mid_prev": prev["mid"],
                "before": [_w(w) for w in prev.get("walls") or [] if ok(w)], "after": [_w(w) for w in ft["walls"] if ok(w)],
                "gone": gone, "new": new, "near_before": nb.get(side), "near_after": na.get(side), "cut_usd": cut,
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    t0 = time.time()
    if a.write:                          # 27.09: подписка по /start — проверять каждые 3 мин, а не только когда бот что-то шлёт
        try:
            from send_brief_telegram import load_config, poll_subscribers
            _cfg = load_config()
            if _cfg:
                poll_subscribers(_cfg)
        except Exception:  # noqa: BLE001
            pass
    alert = coins()                      # телеграм — только по ним, как было
    tr = trades()
    ts = int(time.time() // 60 * 60 * 1000)
    if banned("fut"):
        print(f"depth_tick: фьючерсы Binance под баном до {msg_hm(banned('fut'))} — шаг пропущен")
        return 0
    # 27.09 после бана: монеты сделок — по половине за шаг (каждая раз в 6 мин), монеты тревог — каждые 3 мин
    half = (ts // (SNAP_MIN * 60_000)) % 2
    rest = sorted(s for s in tr if s not in alert)
    syms = alert + [s for i, s in enumerate(rest) if i % 2 == half]
    step_of = {s: SNAP_MIN for s in alert}
    mem = _read(MEM, {}) or {}
    sent = _read(SENT, {}) or {}
    mk = market(a.write)
    from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutTimeout
    snaps: dict[str, dict | None] = {}
    ex = ThreadPoolExecutor(WORKERS)
    fut = {ex.submit(take, s, ts): s for s in syms}
    try:
        for f in as_completed(fut, timeout=max(10, DEADLINE_S - (time.time() - t0))):
            try:
                snaps[fut[f]] = f.result()
            except Exception:  # noqa: BLE001
                snaps[fut[f]] = None
    except FutTimeout:
        print(f"depth_tick: не успели {len(syms) - len(snaps)} монет за {DEADLINE_S} с")
    ex.shutdown(wait=False, cancel_futures=True)
    lines, keys, rows = [], [], []
    fts, hists = {}, {}
    for sym in syms:
        if not snaps.get(sym):
            continue
        hist = mem.get(sym) or []
        # дыра в памяти (монета выпадала из списка, прогон стоял) — судьбу по старому снимку не судим
        if hist and ts - int(hist[-1]["t"]) > 2 * step_of.get(sym, 2 * SNAP_MIN) * 60_000:
            hist = []
        hists[sym], fts[sym] = hist, df.fate(sym, snaps[sym], hist)
    # «сняли» при цене, не дошедшей на снимке, — проверить свечами между снимками (по монете один запрос на фьючерс и спот)
    # плиты одного снимка — шум, их не проверяем; монеты тревог первыми; прогон рвёт шаг на 150 с — после 125 с не начинаем
    need = [s for s, ft in fts.items() if any(g["fate"] != "съели" and g.get("runs", 1) >= 2 and abs(g.get("dist_pct") or 0) <= FAR_PCT for g in ft["gone"])]
    need.sort(key=lambda s: s not in alert)
    t_rng = time.time()
    if need and time.time() - t0 < DEADLINE_S + 15:
        with ThreadPoolExecutor(WORKERS) as ex3:
            for s, rng in zip(need, ex3.map(lambda s: _range(s, int(hists[s][-1]["t"]), ts), need)):
                _recross(fts[s], rng)
    rng_s = time.time() - t_rng
    for sym in syms:
        if sym not in snaps:
            continue
        snap = snaps[sym]
        if not snap:
            print(f"depth_tick: {sym} — стакан не получен")
            continue
        hist, ft = hists[sym], fts[sym]
        if hist:
            rows += side_rows(sym, snap, hist[-1], ft)
        for g in (ft["gone"] if sym in alert else []):
            if g["runs"] < DEPTH_TICK_MIN_SNAPS or abs(g.get("dist_pct") or 0) > FAR_PCT:
                continue
            if g["fate"] != "съели" and g["runs"] * SNAP_MIN < _REMOVED_MIN:      # 27.09 владелец: снятия плит младше 3 ч не слать
                continue
            k = f"wall|{sym}|{g['side']}|{g['px']}|{g['at']}|tick"
            if k in sent:
                continue
            ask = g["side"] == "ask"
            what = (f"съели — прошли {'вверх' if ask else 'вниз'}" + (" свечой, цена вернулась" if g.get("by_wick") else "") if g["fate"] == "съели"
                    else f"убрали — цена не доходила, {'путь вверх свободен' if ask else 'опора ушла'}")
            lines.append(f"{sym[:-4]} · {'потолок' if ask else 'пол'} {g['px']:.6g} ({g['dist_pct']:+.1f}%, "
                         f"${g.get('usd', 0) / 1e3:.0f}K) {what}, стояла {g['runs'] * SNAP_MIN} мин")
            keys.append(k)
        mem[sym] = (hist + [snap])[-KEEP:]
    mem = {s: h for s, h in mem.items() if h and ts - int(h[-1]["t"]) <= KEEP * SNAP_MIN * 60_000}
    # фон к событиям: оборот часа и интерес — только по монетам с событием
    ev_syms = sorted({r["sym"] for r in rows})
    ext: dict[str, dict] = {}
    if ev_syms and time.time() - t0 < DEADLINE_S:
        with ThreadPoolExecutor(WORKERS) as ex2:
            for s, e in zip(ev_syms, ex2.map(extra, ev_syms)):
                ext[s] = e
    for r in rows:
        s, e = r["sym"], ext.get(r["sym"]) or {}
        base, m = _mult(s[:-4], mk["cs"])
        px = mk["px"].get(s) or r["mid"]
        r["trades"] = tr.get(s) or []
        r["step_min"] = step_of.get(s, 2 * SNAP_MIN)
        r["qv24"] = mk["qv"].get(s)
        r["vol1h"] = e.get("vol1h")
        r["oi_usd"] = round(e["oi"] * r["mid"], 0) if e.get("oi") else None
        r["mcap"] = round(mk["cs"][base] * px / m, 0) if base in mk["cs"] else None
    for ln in lines:
        print(f"depth_tick: {ln}")
    print(f"depth_tick: монет {len(syms)} (тревоги {len(alert)}, сделки {len(tr)}) · тревог {len(lines)} · "
          f"сторон с переменами {len(rows)} · свечами проверено {len(need)} ({rng_s:.0f} с), съели свечой {sum(1 for ft in fts.values() for g in ft['gone'] if g.get('by_wick'))} · вес фьючерсов {_STOP['used']:.0f}" + (" · СТОП по весу/бану" if _STOP["fut"] else "") + f" · {time.time() - t0:.0f} с")
    if not a.write:
        return 0
    from sources_storage import write_atomic
    write_atomic(MEM, json.dumps(mem, ensure_ascii=False))
    if rows:
        with EVENTS.open("a", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if lines:
        from send_brief_telegram import load_config, send_telegram
        cfg = load_config()
        if cfg and send_telegram("⏱ МОМЕНТ\n" + "\n".join(lines[:8]), cfg):
            sent = _read(SENT, {}) or {}          # перечитать: прогон мог дописать своё за эти секунды
            now = int(time.time())
            sent.update({k: now for k in keys})
            sent = {k: v for k, v in sent.items() if v >= now - 3 * 86400}
            write_atomic(SENT, json.dumps(sent, ensure_ascii=False))
        else:
            print("depth_tick: телеграм не ушёл")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
