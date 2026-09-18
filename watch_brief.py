"""СВОДКА «ЗА КЕМ СЛЕЖУ» (18.09, владелец: «добавим в конец сообщения сводку по моим монетам»).

Монеты — в `watch.json` в корне проекта, владелец правит его руками, прогон только читает.
Блок уходит ТОЛЬКО в телеграм: ни на страницы, ни в публикуемый output ничего из него не пишется
(правило 12.09 — сайт публичный, личное туда не идёт).

Ничего не считает заново: быстрые (вортекс 30м, клингер 30м), пузыри и событие конца берутся из
`render_coin._fast_events` — те же формулы, что на карточке; место в истории, интерес, фандинг,
ликвидации, полосы и сюжет — из архива получасовок `cq_v2/intraday/<монета>.jsonl`; состояние,
очередь и подхват сессии — из `near_move.json`; стены — из `depth.json`.

Что видно каждый прогон: у монеты с событием — полный разбор, у тихой — одна строка «без изменений»
(владелец 18.09: «дублировать смысла нет, можно просто писать, что ничего не поменялось»).
Сверху блока — строка про стык сессий: за час до открытия хеджировать, через полчаса после —
следить за хеджами, после прочтения подхвата — снимать или держать.

Руками: `python3 watch_brief.py` — напечатать блок; `--only ONE` — по одной монете.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

try:
    from core_config import (WATCH_FILE, WATCH_JUMP_BAR_PCT, WATCH_JUMP_HOUR_PCT, WATCH_VOL_X,
                             WATCH_FUND_PCT, WATCH_UNLOCK_DAYS, WATCH_HEDGE_PRE_MIN, WATCH_HEDGE_POST_MIN,
                             WATCH_SESSIONS)
except ImportError:                                   # пороги живут в core_config; здесь — запасные значения
    WATCH_FILE = "watch.json"
    WATCH_JUMP_BAR_PCT = 3.0        # рывок цены за получасовку, % — событие
    WATCH_JUMP_HOUR_PCT = 5.0       # рывок за час, %
    WATCH_VOL_X = 3.0               # всплеск оборота к норме монеты, раз
    WATCH_FUND_PCT = 0.5            # переход фандинга через этот порог по модулю, %
    WATCH_UNLOCK_DAYS = 3           # разлок ближе этого числа дней — событие
    WATCH_HEDGE_PRE_MIN = 60        # за сколько минут до открытия сессии просить хеджировать
    WATCH_HEDGE_POST_MIN = 30       # сколько минут после открытия просить следить за хеджами
    WATCH_SESSIONS = [(21, "Сидней"), (0, "Токио"), (7, "Лондон"), (13, "Нью-Йорк")]

STATE_NAME = "watch_state.json"     # что уже отправлено — чтобы не повторять одно и то же событие


# ─────────────────────────── чтение файлов проекта ───────────────────────────

def _read_json(name: str):
    for p in (BASE_DIR / "output" / name, BASE_DIR / name, Path("output") / name, Path(name)):
        try:
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _write_state(data: dict) -> None:
    p = BASE_DIR / "output" / STATE_NAME
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            from core_io import write_atomic
            write_atomic(p, json.dumps(data, ensure_ascii=False))
        except ImportError:
            p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def watch_list() -> list[dict]:
    """watch.json → [{sym, note, entry}]. Понимает три записи: список тикеров, список словарей,
    словарь с ключом coins. Нет файла — пустой список, блок не печатается вовсе."""
    raw = None
    for p in (BASE_DIR / WATCH_FILE, Path(WATCH_FILE), BASE_DIR / "config" / WATCH_FILE):
        try:
            if p.exists():
                raw = json.loads(p.read_text(encoding="utf-8"))
                break
        except (OSError, ValueError):
            return []
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("coins") or raw.get("watch") or []
    out = []
    for x in (raw or []):
        if isinstance(x, str):
            out.append({"sym": x.upper().replace("USDT", ""), "note": "", "entry": None})
        elif isinstance(x, dict) and (x.get("sym") or x.get("coin")):
            out.append({"sym": str(x.get("sym") or x.get("coin")).upper().replace("USDT", ""),
                        "note": str(x.get("note") or ""), "entry": x.get("entry")})
    return out


# ─────────────────────────── мелочи вывода ───────────────────────────

def _px(v) -> str:
    if v is None:
        return "—"
    a = abs(float(v))
    d = 2 if a >= 100 else 4 if a >= 1 else 5 if a >= 0.01 else 7 if a >= 0.0001 else 9
    return f"{float(v):.{d}f}".rstrip("0").rstrip(".")


def _pc(v, nd: int = 1) -> str:
    return "—" if v is None else ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.{nd}f}%"


def _usd(v) -> str:
    if v is None:
        return "—"
    a = abs(float(v))
    return ("$%.1fM" % (a / 1e6)) if a >= 1e6 else ("$%.0fK" % (a / 1e3)) if a >= 1e3 else ("$%.0f" % a)


def _loc(ts_ms) -> str:
    """время — в часах смотрящего (правило 12.09), из миллисекунд UTC"""
    return datetime.fromtimestamp(ts_ms / 1000).strftime("%H:%M")


def _ms(c) -> int | None:
    try:
        return int(datetime.fromisoformat(str(c).replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


# ─────────────────────────── сессии и хедж ───────────────────────────

def session_head(now: datetime | None = None) -> tuple[str, str]:
    """Шапка блока: что делать с хеджами на стыке. Возвращает (строка, ключ события).
    Границы сессий считаются в UTC, на экран идут в часах смотрящего (правило 12.09)."""
    now = now or datetime.now(timezone.utc)
    opens = []
    for h, name in WATCH_SESSIONS:
        for k in (-1, 0, 1):
            t = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=k, hours=h)
            opens.append((t, name))
    opens.sort()
    nxt = next((o for o in opens if o[0] > now), opens[-1])
    prev = [o for o in opens if o[0] <= now][-1]
    to_m = int((nxt[0] - now).total_seconds() // 60)
    since_m = int((now - prev[0]).total_seconds() // 60)
    loc = nxt[0].astimezone().strftime("%H:%M")
    if to_m <= WATCH_HEDGE_PRE_MIN:
        return (f"⚠ ДО {nxt[1].upper()} {to_m} МИН ({loc}) — ХЕДЖИРОВАТЬ ВСЕ ПОЗИЦИИ", f"pre:{nxt[1]}:{nxt[0]:%d%H}")
    if since_m <= WATCH_HEDGE_POST_MIN:
        return (f"⚠ {prev[1].upper()} ОТКРЫЛСЯ {since_m} МИН НАЗАД — СЛЕДИТЬ ЗА ХЕДЖАМИ, "
                f"скоро станет ясно, снимать или держать", f"post:{prev[1]}:{prev[0]:%d%H}")
    return (f"сессии: идёт {prev[1]} ({since_m // 60} ч {since_m % 60} мин) · до {nxt[1]} "
            f"{to_m // 60}:{to_m % 60:02d}", "")


def pickup_line(near_sym: dict) -> tuple[str, str]:
    """Подхват последнего открытия — из near_move (его же показывают звёзды и карточка)."""
    np_ = ((near_sym or {}).get("today") or {}).get("sess_pickup") or {}
    if not np_ or not np_.get("at"):
        return "подхват не прочитан", ""
    t = _ms(np_.get("at"))
    s = f"{np_.get('session') or '—'} {(_loc(t) if t else '')}"
    if np_.get("pickup"):
        return (f"{s} подхватил — новые руки с плечом, хедж можно снимать", f"pickup:{np_.get('at')}:1")
    return (f"{s} НЕ подхватил — цену отпускают до следующей сессии, хедж держать", f"pickup:{np_.get('at')}:0")


# ─────────────────────────── разбор одной монеты ───────────────────────────

def _bars(base: str) -> list[dict]:
    for d in (BASE_DIR / "cq_v2" / "intraday", Path("cq_v2") / "intraday"):
        p = d / f"{base.lower()}.jsonl"
        if not p.exists():
            continue
        rows = []
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("px") and r.get("candle"):
                    r["_t"] = _ms(r["candle"])
                    if r["_t"]:
                        rows.append(r)
        except OSError:
            return []
        rows.sort(key=lambda x: x["_t"])
        return rows
    return []


def _fast(base: str) -> dict:
    """быстрые и пузыри — теми же формулами, что карточка"""
    try:
        from render_coin import _fast_events
        return (_fast_events(only=[base]) or {}).get(base.upper() + "USDT") or {}
    except Exception:                                   # noqa: BLE001 — сводка не должна ронять прогон
        return {}


def _vx_line(fe: dict) -> str:
    vx = fe.get("vx30") or []
    if not vx:
        return "вортекс 30м — нет ряда"
    t, vp, vm = vx[-1]
    who = "покупатели" if vp > vm else "продавцы"
    gap = abs(vp - vm)
    turn = ""
    for i in range(len(vx) - 1, 0, -1):
        if (vx[i][1] > vx[i][2]) != (vx[i - 1][1] > vx[i - 1][2]):
            turn = f", слом {'вверх' if vx[i][1] > vx[i][2] else 'вниз'} {_loc(vx[i][0])}"
            break
    return f"вортекс 30м {who}, разрыв {gap:.2f}{turn}"


def _kl_line(fe: dict) -> str:
    kl = fe.get("kl30") or []
    if not kl:
        return "клингер 30м — нет ряда"
    t, kvo, sig = kl[-1]
    who = "покупатели" if kvo > sig else "продавцы"
    turn = ""
    for i in range(len(kl) - 1, 0, -1):
        if (kl[i][1] > kl[i][2]) != (kl[i - 1][1] > kl[i - 1][2]):
            turn = f", крест {'вверх' if kl[i][1] > kl[i][2] else 'вниз'} {_loc(kl[i][0])}"
            break
    return f"клингер 30м {who}{turn}"


def _bub_line(fe: dict) -> str:
    bub = sorted(fe.get("bubbles") or [], key=lambda x: x["t"])
    end = sorted(fe.get("end") or [], key=lambda x: x["t"])
    out = []
    if bub:
        b = bub[-1]
        out.append(f"пузырь 30м {_loc(b['t'])} {'покупка' if b['side'] == 'buy' else 'продажа'} ({b['sure']})")
        clear_buy = [x for x in bub if x["side"] == "buy" and x["sure"] == "ясный"]
        if clear_buy and clear_buy[-1] is not b:
            out.append(f"последний ясный на покупку {_loc(clear_buy[-1]['t'])}")
    if end:
        out.append(f"конец 30м {_loc(end[-1]['t'])}")
    return " · ".join(out) or "пузырей за окно нет"


def _zones_line(row: dict, px: float) -> str:
    z = row.get("zones") or {}
    def side(key, name):
        items = sorted((z.get(key) or []), key=lambda q: abs((q[0] / px - 1) if px else 0))[:3]
        if not items:
            return f"{name} пусто"
        return name + " " + ", ".join(f"{_px(q[0])} ({_pc((q[0] / px - 1) * 100 if px else None)}, {_usd(q[1])})" for q in items)
    return side("up", "сверху") + " · " + side("down", "снизу")


def _depth_line(base: str, depth: dict, px: float) -> str:
    dp = (depth or {}).get(base.upper() + "USDT") or {}
    walls = dp.get("walls") or []
    if not walls:
        return ""
    def one(w):
        return (f"{_px(w.get('px'))} ({_pc(w.get('dist_pct'), 1)}, {_usd(w.get('usd'))}"
                + (", спот" if w.get("kind") == "spot" else "")
                + (f", {w.get('runs')} пр." if (w.get("runs") or 0) > 1 else "") + ")")
    ask = [w for w in walls if w.get("side") == "ask"][:2]
    bid = [w for w in walls if w.get("side") == "bid"][:2]
    parts = []
    if ask:
        parts.append("потолок " + " · ".join(one(w) for w in ask))
    if bid:
        parts.append("пол " + " · ".join(one(w) for w in bid))
    return " · ".join(parts)


def _unlock_days(base: str, unlocks: dict):
    rec = (unlocks or {}).get(base.upper() + "USDT") or (unlocks or {}).get(base.upper()) or {}
    if not isinstance(rec, dict):
        return None
    for k, v in rec.items():
        if not isinstance(v, str) or "date" not in str(k).lower() and "next" not in str(k).lower() and "at" != str(k).lower():
            continue
        t = _ms(v) or _ms(v + "T00:00:00Z")
        if t:
            d = (t / 1000 - datetime.now(timezone.utc).timestamp()) / 86400
            if d >= 0:
                return round(d, 1)
    return None


def coin_block(w: dict, near: dict, depth: dict, unlocks: dict, state: dict) -> tuple[list[str], list[str], dict]:
    """Строки по монете, список событий и новое состояние для сравнения на следующем прогоне."""
    base = w["sym"]
    rows = _bars(base)
    st: dict = {}
    if not rows:
        return [f"  · {base} — архива получасовок нет"], [], st
    last = rows[-1]
    px = float(last.get("px") or 0)
    st["px"] = px
    st["bar"] = last.get("_t")
    fresh_bar = state.get("bar") != last.get("_t")      # один бар — один рывок: в том же баре не повторяем
    ev: list[str] = []

    # ход цены: бар, час, сутки
    def back(n):
        return float(rows[-1 - n].get("px") or 0) if len(rows) > n else None
    d_bar = (px / back(1) - 1) * 100 if back(1) else None
    d_hr = (px / back(2) - 1) * 100 if back(2) else None
    d_day = (px / back(48) - 1) * 100 if back(48) else None
    if fresh_bar and d_bar is not None and abs(d_bar) >= WATCH_JUMP_BAR_PCT:
        ev.append(f"рывок за бар {_pc(d_bar)}")
    if fresh_bar and d_hr is not None and abs(d_hr) >= WATCH_JUMP_HOUR_PCT:
        ev.append(f"за час {_pc(d_hr)}")

    # место в истории: основание и вершина по архиву, от вершины
    pxs = [float(r.get("px") or 0) for r in rows if r.get("px")]
    low, high = (min(pxs), max(pxs)) if pxs else (None, None)
    from_low = (px / low - 1) * 100 if low else None
    from_top = (px / high - 1) * 100 if high else None

    # оборот к своей норме
    def qv(r):
        return float((r.get("kv") or {}).get("qv") or 0) or (float((r.get("fut") or {}).get("b") or 0) + float((r.get("fut") or {}).get("s") or 0))
    hist = sorted(qv(r) for r in rows[-336:-1] if qv(r) > 0)
    norm = hist[len(hist) // 2] if hist else 0
    volx = (qv(last) / norm) if norm else None
    st["volx"] = round(volx, 2) if volx else None
    if volx and volx >= WATCH_VOL_X and (state.get("volx") or 0) < WATCH_VOL_X:
        ev.append(f"всплеск оборота ×{volx:.1f} к норме")

    fund = last.get("funding")
    st["fund"] = fund
    if fund is not None and state.get("fund") is not None:
        was, now_ = abs(float(state["fund"])), abs(float(fund))
        if (was < WATCH_FUND_PCT) != (now_ < WATCH_FUND_PCT):
            ev.append(f"фандинг {_pc(float(fund), 2)} — перешёл порог")

    fe = _fast(base)
    bub = sorted(fe.get("bubbles") or [], key=lambda x: x["t"])
    end = sorted(fe.get("end") or [], key=lambda x: x["t"])
    st["bub"] = bub[-1]["t"] if bub else None
    st["end"] = end[-1]["t"] if end else None
    if bub and state.get("bub") != st["bub"]:
        b = bub[-1]
        ev.append(f"пузырь {'покупки' if b['side'] == 'buy' else 'продажи'} {b['sure']} {_loc(b['t'])}")
    if end and state.get("end") != st["end"]:
        ev.append(f"событие конца {_loc(end[-1]['t'])}")
    elif state.get("end") and not end:
        ev.append("конец снят — рука вернулась")

    # слом быстрых
    for key, name, series in (("vxt", "вортекс 30м", fe.get("vx30") or []), ("klt", "клингер 30м", fe.get("kl30") or [])):
        turn = None
        for i in range(len(series) - 1, 0, -1):
            if (series[i][1] > series[i][2]) != (series[i - 1][1] > series[i - 1][2]):
                turn = (series[i][0], series[i][1] > series[i][2])
                break
        st[key] = turn[0] if turn else None
        if turn and state.get(key) != turn[0]:
            ev.append(f"{name} слом {'вверх' if turn[1] else 'вниз'} {_loc(turn[0])}")

    nr = (near or {}).get(base.upper() + "USDT") or {}
    nums, qq = nr.get("nums") or {}, nr.get("queue") or {}
    today = nr.get("today") or {}
    pick, pick_key = pickup_line(nr)
    st["pickup"] = pick_key
    if pick_key and state.get("pickup") != pick_key:
        ev.append("стык прочитан: " + pick.split(" — ")[0])
    place = qq.get("place") or qq.get("rank")
    st["place"] = place
    if place and state.get("place") != place:
        ev.append(f"место в очереди {place}")

    unl = _unlock_days(base, unlocks)
    st["unlock"] = unl
    if unl is not None and unl <= WATCH_UNLOCK_DAYS:
        ev.append(f"разлок через {unl} дн")

    if not ev:
        line = f"  · {base} {_px(px)} · {_pc(d_day)} за сутки — без изменений"
        if w.get("entry"):
            line += f" · от входа {_pc((px / float(w['entry']) - 1) * 100)}"
        return [line], ev, st

    liq = last.get("liq24") or {}
    head = f"  · {base} {_px(px)} · {_pc(d_day)} за сутки" + (f" · от входа {_pc((px / float(w['entry']) - 1) * 100)}" if w.get("entry") else "")
    if w.get("note"):
        head += f" · {w['note']}"
    lines = [head,
             "    быстрые: " + _vx_line(fe) + " · " + _kl_line(fe),
             "    пузыри: " + _bub_line(fe),
             f"    где цена: {_pc(from_low)} от дна архива, {_pc(from_top)} от вершины · "
             f"оборот {('×%.1f' % volx) if volx else '—'} к норме · бар {_pc(d_bar)}, час {_pc(d_hr)}",
             f"    плечо: интерес {_pc(last.get('oi_chg_pct'))} за сутки · фандинг "
             f"{_pc(float(fund), 3) if fund is not None else '—'} · тейкер {last.get('taker24') or '—'} · "
             f"ликв 24ч: шортов {_usd(liq.get('short'))} против лонгов {_usd(liq.get('long'))}"
             + (f" · бар {last.get('oi_type')}" if last.get("oi_type") else ""),
             "    полосы: " + _zones_line(last, px)]
    dl = _depth_line(base, depth, px)
    if dl:
        lines.append("    стакан: " + dl)
    tail = []
    if last.get("plot"):
        _pl = str(last["plot"]);
        tail.append("сюжет: " + (_pl[:150].rsplit(" ", 1)[0] + "…" if len(_pl) > 160 else _pl))
    if nums.get("harvest_day"):
        tail.append(f"сбор {str(nums['harvest_day'])[5:]} ×{round(nums.get('harvest_x') or 0)}"
                    + (f", плечо ×{float(nums.get('oi_grow') or 1):.2f}" if nums.get("oi_grow") else ""))
    if today.get("ended_at"):
        tail.append("состояние: конец" + (" · лонги выходят" if (today.get("closing_bars") or 0) >= 3 else " · рука ушла"))
    for t in tail:
        lines.append("    " + t)
    lines.append("    стык: " + pick)
    lines.append("    СОБЫТИЕ: " + " · ".join(ev))
    return lines, ev, st


# ─────────────────────────── сборка блока ───────────────────────────

def watch_block(only: list | None = None) -> str:
    """Готовый текст блока для хвоста сообщения прогона. Нет watch.json — пустая строка."""
    coins = watch_list()
    if only:
        keep = {str(x).upper().replace("USDT", "") for x in only}
        coins = [c for c in coins if c["sym"] in keep]
    if not coins:
        return ""
    near = ((_read_json("near_move.json") or {}).get("coins")
            or (_read_json("near_move.json") or {}) or {})
    depth = (_read_json("depth.json") or {}).get("coins") or {}
    unlocks = _read_json("unlocks.json") or {}
    state = _read_json(STATE_NAME) or {}
    head, head_key = session_head()
    out = ["", "ЗА КЕМ СЛЕЖУ (" + ", ".join(c["sym"] for c in coins) + ")", "  " + head]
    new_state = {"head": head_key}
    for w in coins:
        try:
            lines, ev, st = coin_block(w, near, depth, unlocks, state.get(w["sym"]) or {})
        except Exception as e:                          # noqa: BLE001 — одна монета не роняет блок
            lines, ev, st = [f"  · {w['sym']} — сбой разбора: {type(e).__name__}: {e}"], [], {}
        out += lines
        new_state[w["sym"]] = st
    _write_state(new_state)
    return "\n".join(out)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="сводка по своим монетам — блок для телеграма")
    ap.add_argument("--only", help="одна монета или несколько через запятую")
    a = ap.parse_args()
    print(watch_block([x.strip() for x in a.only.split(",")] if a.only else None) or "watch.json пуст или не найден")
