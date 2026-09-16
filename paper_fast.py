#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ НА БЫСТРЫХ (15.09, владелец: «делай всё»; правило владельца 07.09: бот ходит по уровням и смотрит
пузыри, сначала бумажно). Здесь — быстрый слой: то, что сложилось на ARK и LAB, считается прогоном и торгуется
на бумаге без меня.

ВХОД (все три на одном баре, монеты — первые очереди и звёзды):
  1. слом вортекса ВВЕРХ по разрыву — покупатели−продавцы развернулись от минимума за 6 баров, минимум ≤ −BRK_MIN_VX;
  2. интерес вырос за последние 4 бара (oi30);
  3. фандинг ≤ FUND_ENTRY (шорты платят — топливо; у ARK перед вторым пиком −1.5).
ВЫХОД — не закрытие, а ХЕДЖ И ФЛИП (владелец 16.09: «падает клингер после пампа — открываем шорт и ждём; пошло
выше — не страшно, лонг открыт; видим слом вортекса, интерес падает — закрываем лонг и сидим в шорте»; по архивам
11–16.09 два эпизода: держать −18.9%, хедж→флип +14.85%):
  1. слом клингера ВНИЗ при цене выше входа → открыть шорт 1.0 (нетто ноль), лонг держать;
  2. в хедже: слом вортекса ВНИЗ при падающем интересе → закрыть лонг, остаться в шорте;
  3. в шорте: слом вортекса ВВЕРХ → закрыть шорт. Без флипа, если цена ушла выше: хедж снимается при сломе
     клингера ВВЕРХ (шорт закрыт, лонг остался).
Ценового стопа нет — размер условный 1.0 на ногу, риск считается по итогам.
Пишет `output/paper_fast.json` (открытые) и `output/paper_fast.jsonl` (все входы и выходы с причинами).
Ряды берёт из render_coin._fast_events (vx30, kl30, oi30, fund30 — клайны Binance без дыр).
Запуск: из прогона после карточек; руками `python3 paper_fast.py --only ARK` (печать), `--write`.
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
    from core_config import PAPER_FAST_BRK_MIN_VX, PAPER_FAST_FUND_ENTRY, PAPER_FAST_OI_BARS, PAPER_FAST_TOP_N
except ImportError:
    PAPER_FAST_BRK_MIN_VX, PAPER_FAST_FUND_ENTRY, PAPER_FAST_OI_BARS, PAPER_FAST_TOP_N = 0.25, -0.3, 4, 5

STATE = BASE_DIR / "output" / "paper_fast.json"
LOG = BASE_DIR / "output" / "paper_fast.jsonl"
EXT = 6


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def breaks(gaps: list[float], big: float) -> list[int]:
    """0 / +1 / −1 на каждом баре: слом по разрыву от экстремума за EXT баров, экстремум не меньше big по модулю."""
    out = [0] * len(gaps)
    for i in range(EXT + 1, len(gaps)):
        w = gaps[i - EXT:i]
        if gaps[i] < gaps[i - 1] and gaps[i - 1] >= max(w) and gaps[i - 1] >= big:
            out[i] = -1
        elif gaps[i] > gaps[i - 1] and gaps[i - 1] <= min(w) and gaps[i - 1] <= -big:
            out[i] = 1
    return out


def watch_list() -> list[str]:
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out = [str(s).upper() for s in (nm.get("first") or [])]
    for s in (nm.get("queue") or [])[:PAPER_FAST_TOP_N]:
        s = s if isinstance(s, str) else (s or {}).get("sym")
        if s:
            out.append(str(s).upper())
    return list(dict.fromkeys(out))


def evaluate(sym: str, F: dict, px_now: float | None) -> dict:
    """Что говорит быстрый слой на последнем закрытом баре: вход / выход / ничего, с числами для журнала."""
    vx, kl, oi, fd = F.get("vx30") or [], F.get("kl30") or [], F.get("oi30") or [], F.get("fund30") or []
    if len(vx) < EXT + 2:
        return {"sym": sym, "signal": None, "why": "мало баров вортекса"}
    gv = [r[1] - r[2] for r in vx]
    bv = breaks(gv, PAPER_FAST_BRK_MIN_VX)
    gk = [r[1] - r[2] for r in kl] if len(kl) >= EXT + 2 else []
    mxk = max([abs(x) for x in gk] + [1e-9])
    bk = breaks(gk, 0.25 * mxk) if gk else []
    oi_fall = len(oi) >= 2 and oi[-1][1] < oi[-2][1]
    # слом смотрим на двух последних барах: прогон идёт раз в полчаса и может опоздать на бар
    i_up = next((i for i in (-1, -2) if bv[i] == 1), None)
    i_dn = next((i for i in (-1, -2) if bv[i] == -1), None)
    i_kd = next((i for i in (-1, -2) if bk and bk[i] == -1), None)
    t = vx[-1][0]
    oi_up = None
    if len(oi) > PAPER_FAST_OI_BARS:
        oi_up = oi[-1][1] > oi[-1 - PAPER_FAST_OI_BARS][1]
    fund = fd[-1][1] if fd else None
    r = {"sym": sym, "t": t, "vx_break": bv[-1], "kl_break": (bk[-1] if bk else 0), "gap": round(gv[-1], 3),
         "oi_up": oi_up, "oi_fall": oi_fall, "fund": fund, "px": px_now, "signal": None, "why": "",
         "i_dn": i_dn, "i_kd": i_kd, "i_up": i_up, "i_ku": next((i for i in (-1, -2) if bk and bk[i] == 1), None)}
    if i_up is not None and oi_up and fund is not None and fund <= PAPER_FAST_FUND_ENTRY:
        r["signal"] = "entry"
        r["why"] = f"слом вортекса вверх (разрыв {gv[i_up - 1]:+.2f} → {gv[i_up]:+.2f}) · интерес вырос за {PAPER_FAST_OI_BARS} бара · фандинг {fund:+.2f}"
    elif i_dn is not None:
        r["signal"] = "exit"
        r["why"] = f"слом вортекса вниз (разрыв {gv[i_dn - 1]:+.2f} → {gv[i_dn]:+.2f})"
    elif i_kd is not None:
        r["signal"] = "exit"
        r["why"] = "слом клингера вниз"
    return r


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    import render_coin
    fast = render_coin._fast_events()
    # цена бара — из пульса (последняя точка), как в архиве; нет — из near_move
    px_of = {}
    pulse = _read(BASE_DIR / "pulse.json") or {}
    for k, pts in (pulse.items() if isinstance(pulse, dict) else []):
        if not isinstance(pts, list):          # в pulse.json есть и служебные ключи со строками — не монеты
            continue
        pts = [q for q in pts if isinstance(q, dict) and q.get("price")]
        if pts:
            px_of[str(k).upper()] = float(sorted(pts, key=lambda q: q.get("t") or 0)[-1]["price"])
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    for k, v in (nm.get("coins") or {}).items():
        if str(k).upper() in px_of:
            continue
        p = (v.get("live") or {}).get("px") if isinstance(v.get("live"), dict) else None
        p = p or v.get("px") or (v.get("today") or {}).get("px")
        if p:
            px_of[str(k).upper()] = float(p)
    syms = [x.strip().upper() for x in a.only.split(",")] if a.only else watch_list()
    syms = [s if s.endswith("USDT") else s + "USDT" for s in syms]
    state = _read(STATE) or {"open": {}}
    opened, closed = [], []
    now = int(time.time())
    for sym in syms + [s for s in list(state["open"].keys()) if s not in syms]:   # открытые смотрим всегда
        F = fast.get(sym)
        if not F:
            continue
        ev = evaluate(sym, F, px_of.get(sym))
        pos = state["open"].get(sym)
        st_ = (pos or {}).get("state", "long") if pos else None
        line = f"paper_fast: {sym} · " + (ev["signal"] or "тихо") + (" · " + ev["why"] if ev["why"] else "") + (f" · позиция {st_}" if pos else "")
        print(line)
        px = ev["px"]
        if ev["signal"] == "entry" and not pos and sym in syms:
            state["open"][sym] = {"t": ev["t"], "px": px, "why": ev["why"], "opened_at": now, "state": "long", "legs": {"long": px}}
            opened.append(dict(ev, kind="entry"))
            continue
        if not pos or not px:
            continue
        legs = pos.setdefault("legs", {"long": pos.get("px")})
        above = legs.get("long") and px > legs["long"]
        if st_ == "long" and ev.get("i_kd") is not None and above:
            # 1. слом клингера вниз выше входа → хедж
            legs["short"] = px
            pos["state"] = "hedged"
            pos["vx_dn"] = ev.get("i_dn") is not None
            opened.append(dict(ev, kind="hedge", legs=dict(legs)))
            print(f"paper_fast: {sym} · ХЕДЖ · шорт {px:.6g} против лонга {legs['long']:.6g} · {ev['why'] or 'слом клингера вниз'}")
        elif st_ == "hedged":
            if ev.get("i_dn") is not None:
                pos["vx_dn"] = True          # слом вортекса вниз случился после хеджа — помним
            if pos.get("vx_dn") and ev.get("oi_fall"):
                # 2. слом вортекса вниз при падающем интересе → закрыть лонг, остаться в шорте
                res_l = (px / legs["long"] - 1) * 100
                closed.append(dict(ev, kind="exit_long", entry_px=legs["long"], result_pct=round(res_l, 2), why_exit="флип: слом вортекса вниз, интерес падает"))
                pos["state"] = "short"
                legs.pop("long", None)
                print(f"paper_fast: {sym} · ФЛИП · лонг закрыт {res_l:+.2f}%, сидим в шорте от {legs['short']:.6g}")
            elif ev.get("i_ku") is not None:
                # цена пошла выше — хедж снять
                res_s = (legs["short"] / px - 1) * 100
                closed.append(dict(ev, kind="exit_short", entry_px=legs["short"], result_pct=round(res_s, 2), why_exit="хедж снят: слом клингера вверх"))
                pos["state"] = "long"
                legs.pop("short", None)
        elif st_ == "short" and (ev.get("i_up") is not None or ev.get("i_ku") is not None):
            # 3. слом вортекса (или клингера) вверх → закрыть шорт
            res_s = (legs["short"] / px - 1) * 100
            closed.append(dict(ev, kind="exit_short", entry_px=legs["short"], result_pct=round(res_s, 2), why_exit="слом вортекса вверх"))
            del state["open"][sym]
            print(f"paper_fast: {sym} · шорт закрыт {res_s:+.2f}%")
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for r in opened + closed:
                f.write(json.dumps(dict(r, at=now), ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    print(f"paper_fast: открыто {len(opened)}, закрыто {len(closed)}, в позиции {len(state['open'])}" + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
