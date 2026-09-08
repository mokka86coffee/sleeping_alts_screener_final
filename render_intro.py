"""Первый экран «поведение света» (05–06.09) — прототип владельца v2_povedenie-2.html:
имена монет собираются из облака по одному и остаются созвездием; свет — состояние.

Три группы (владелец, 06.09):
  0 — БРАТЬ:    «близкие, держат после сбора» из near_move (свет набирает, искры вверх);
  1 — ДЕРЖАТЬ:  «идут» из near_move (мягкая зелёная подсветка, редкие капли);
  2 — ЗАКРЫТЬ:  текущий шаблон «у цели сбора», либо последняя смена — осечка/«отпустил»
                (буквы выедает и сдувает, блики мигают и гаснут).
Потолок — 12 имён, порядок — по группам, внутри группы по свежести сбора; раскладка —
рассыпать по облаку с минимальным расстоянием между именами (созвездие при любом N).

Шейдер, такты появления, цвета и эрозия — владельца, не трогаются. Добавлено: клик по
имени → coin.html#SYM; клик мимо / любая клавиша → дальше по оболочке (ob:done, screen
'intro'); подпись внизу «брать N · держать N · закрыть N».

    from render_intro import render_intro
    html = render_intro()                  # читает output/near_move.json, output/reputation.json,
                                           # output/forecasts.jsonl; пусто → короткое созвездие
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

MAX_NAMES = 12
END_WORDS = ("осечк", "отпустил", "отбой")


def _read(name: str):
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


HOLD_HOURS = 10        # состояние держится, пока не сменилось на другой род или пока не вышло время
STALE_HOURS = 4        # старше — «остывшие»: отдельная область внизу, мельче (07.09, владелец)


def _state_since() -> dict:
    """Когда шаблон монеты встал ВПЕРВЫЕ подряд (07.09, владелец: «не зашёл в Телеграм — как
    растянуть на 10 часов»): по forecasts.jsonl — последняя непрерывная серия одного короткого
    имени; отдаём {sym: (имя, часов держится, время постановки)}. Состояние гаснет, только когда
    имя сменилось или прошло HOLD_HOURS."""
    from datetime import datetime, timezone
    out: dict = {}
    for p in (BASE_DIR / "output" / "forecasts.jsonl", Path("output") / "forecasts.jsonl"):
        if not p.exists():
            continue
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        rows.sort(key=lambda r: f"{r.get('at', '')} {r.get('hm', '')}")
        by: dict = {}
        last_goal: dict = {}     # последнее «у цели» по монете: имя и время постановки серии
        for r in rows:
            sym = str(r.get("sym") or "").upper()
            if not sym:
                continue
            nm = str(r.get("tpl") or "").split("(")[0].strip().lower()
            full = str(r.get("tpl") or "").strip().lower()
            t = f"{r.get('at', '')} {r.get('hm', '00:00')}"
            cur = by.get(sym)
            if cur and cur[0] == nm:
                by[sym] = (nm, cur[1])          # серия продолжается — время постановки прежнее
            else:
                by[sym] = (nm, t)
            if nm.startswith("у цели"):
                prev = last_goal.get(sym)
                last_goal[sym] = (full, prev[1] if (prev and prev[0].split("(")[0] == full.split("(")[0]) else t)
        now = datetime.now(timezone.utc)
        for sym, (nm, t0) in by.items():
            src = last_goal.get(sym) if (sym in last_goal and not nm.startswith("у цели")) else None
            nm_out, t_out = (src[0], src[1]) if src else (nm, t0)
            try:
                d0 = datetime.strptime(t_out, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                hrs = (now - d0).total_seconds() / 3600
            except ValueError:
                hrs = 0.0
            out[sym] = (nm_out, round(hrs, 1), t_out[5:16])
        break
    return out


def _last_marks() -> dict:
    """Последний шаблон по монете из forecasts.jsonl (короткое имя)."""
    out: dict = {}
    for p in (BASE_DIR / "output" / "forecasts.jsonl", Path("output") / "forecasts.jsonl"):
        if not p.exists():
            continue
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        rows.sort(key=lambda r: f"{r.get('at', '')} {r.get('hm', '')}")
        for r in rows:
            s = str(r.get("sym") or "").upper()
            if s:
                out[s] = str(r.get("tpl") or "").split("(")[0].strip().lower()
        break
    return out


def collect_items() -> list[dict]:
    nm = _read("near_move.json") or {}
    coins = nm.get("coins") or {}
    rep = _read("reputation.json") or {}
    marks = _last_marks()
    since = _state_since()
    items: list[dict] = []
    seen: set = set()

    def add(sym: str, g: int, why: str, sub: str = "", rel: float = 0.0):
        if sym in seen:
            return
        seen.add(sym)
        items.append({"n": sym.replace("USDT", ""), "sym": sym, "g": g, "why": why, "sub": sub, "rel": rel})

    def reliability(v: dict) -> float:
        # БАЛЛ ОЧЕРЕДИ — ГЛАВНЫЙ (07.09, владелец: «DOOD пошёл, а светил меньше всех»): порядок
        # появления и длина лучей идут из очереди (режим, срок после сбора, плечо, бары), а не из
        # старой надёжности по обороту; она осталась запасной, если очереди нет
        q = v.get("queue") or {}
        if q.get("score") is not None:
            return float(q["score"])
        """Надёжность (06.09, владелец: «у кого надёжнее — та ярче»): сбор × рост плеча, в логарифме
        по сбору — FLOCK ×144 при плече ×2.5 против «четвёрки» ×20 при ×1.8; сегодня продают — штраф."""
        n = v.get("nums") or {}
        hx = max(1.0, float(n.get("harvest_x") or 1.0))
        og = max(0.5, float(n.get("oi_grow") or 1.0))
        r = math.log10(hx) * og
        td = (v.get("today") or {}).get("today")
        if td == "продают сегодня":
            r *= 0.6
        elif td == "набирают сегодня":
            r *= 1.15
        return r

    # ОЧЕРЕДЬ В ЗВЁЗДАХ (07.09, владелец): группы — «первые» (три верхние строки очереди, белые,
    # лучи по баллу), «в очереди» (остальные живые: держат/идут/откатились, зелёные, короче),
    # «у цели» — как была. Под именем — история одной строкой: срок после сбора · плечо · сегодня
    queue = nm.get("queue") or []
    def hist_line(v: dict) -> str:
        n = v.get("nums") or {}; q = v.get("queue") or {}
        d = q.get("days_since_harvest")
        td = q.get("today") or ((v.get("today") or {}).get("today")) or ""
        return ((n.get("mode") + " · ") if n.get("mode") else "") + ((n.get("engine") + " · ") if n.get("engine") and n.get("engine") != "нет" else "") + (f"сбор {d} дн назад" if d is not None else "сбор —") + f" · плечо ×{float(n.get('oi_grow') or 1):.1f}" + (f" · {td}" if td else "")
    for i, sym in enumerate(queue):
        v = coins.get(sym) or {}
        sc = float((v.get("queue") or {}).get("score") or 0)
        add(sym, 0 if i < 3 else 1, " · ".join(v.get("why") or []), hist_line(v), sc)
    # У ЦЕЛИ — С ДОЛЕЙ ХЕДЖА ЧИСЛОМ (07.09, владелец: «послушал бы сайт — захеджировал бы 70–80%,
    # а так 20 и потерял»): толпа набивается — плотная полоса сверху и топливо снизу, отдают быстро,
    # хедж 70–80%; кто двигает неясно — 50%; конец тренда / отпустил / осечка — выход 100%, не хедж;
    # ведут покупатели — хеджа нет, это «в очереди». Стоп хеджа — над максимумом ПО ЗАКРЫТИЮ.
    for sym, r in rep.items():
        if not isinstance(r, dict) or sym.startswith("_"):
            continue
        plot_full = str(r.get("plot") or "").lower()
        plot = plot_full.split("(")[0].strip()
        last = marks.get(sym, "")
        st = since.get(sym)
        # состояние держится: если сейчас шаблон другой, но «у цели» стояло недавно и не сменилось
        # на «ведут покупатели» или конец — показываем его дальше, до HOLD_HOURS
        if not plot.startswith("у цели") and st and st[0].startswith("у цели") and st[1] <= HOLD_HOURS:
            plot_full = st[0]
            plot = st[0]
        age = f" · {st[1]:.0f}-й час, с {st[2]}" if (st and plot.startswith(st[0][:8])) else ""
        if plot.startswith("у цели"):
            if "ведут покупатели" in plot_full or "ведёт покупатель" in plot_full:
                continue
            if "толпа" in plot_full:
                gg = 4 if (st and st[1] > STALE_HOURS) else 2
                add(sym, gg, "у цели — толпа набивается · хедж 70–80% позиции, стоп над максимумом по закрытию" + age, "хедж 70–80%")
            else:
                gg = 4 if (st and st[1] > STALE_HOURS) else 2
                add(sym, gg, "у цели — кто двигает неясно · хедж 50%, стоп над максимумом по закрытию" + age, "хедж 50%")
        elif plot.startswith("разгон отпустил") or any(w in last for w in END_WORDS):
            add(sym, 2, (plot or last) + " · выход, не хедж", "выход 100%")

    # КОНЕЦ ТРЕНДА (07.09): монеты, выпавшие из очереди — интерес ушёл вместе с ценой на одном
    # баре, — не исчезают, а становятся «у цели · конец тренда»: вход закрыт, для позиции — выход
    for sym, v in coins.items():
        if (v.get("today") or {}).get("leaving_kind") == "конец":
            add(sym, 2, " · ".join(v.get("why") or []) + " · интерес ушёл вместе с ценой — выход, не хедж", "выход 100%")
    # порядок: брать, держать, у цели; внутри группы — по надёжности, самая надёжная первой
    items.sort(key=lambda it: (it["g"], -it.get("rel", 0.0)))
    # яркость внутри группы: лучшая — 1.0, остальные вниз до 0.45; «у цели» — ровно 0.7
    for g in (0, 1, 2):
        grp = [it for it in items if it["g"] == g]
        if not grp:
            continue
        hi_r, lo_r = max(it["rel"] for it in grp), min(it["rel"] for it in grp)
        for it in grp:
            it["bright"] = 1.0 if hi_r <= lo_r else 0.45 + 0.55 * (it["rel"] - lo_r) / (hi_r - lo_r)
    for it in items:
        if it["g"] == 2:
            it["bright"] = 0.7
        elif it["g"] == 4:
            it["bright"] = 0.4
    return items[:MAX_NAMES]


# ЗОНЫ (06.09, владелец: «размещать по зонам, с очертаниями»): доли ширины/высоты — x0,y0,x1,y1
ZONES = {
    0: (0.05, 0.12, 0.47, 0.50),   # брать — слева сверху
    1: (0.53, 0.12, 0.95, 0.50),   # держать — справа сверху
    3: (0.05, 0.55, 0.60, 0.84),   # готовы — слева снизу, широкая
    2: (0.66, 0.55, 0.95, 0.84),   # у цели — справа снизу
}
ZONE_TINT = {0: "207,224,255", 1: "143,224,184", 3: "150,160,205", 2: "196,170,255"}


def layout(n: int, seed: int = 7, zone: tuple | None = None) -> list[list[float]]:
    """Созвездие внутри зоны: точки с минимальным расстоянием; детерминировано по seed."""
    if n <= 0:
        return []
    rnd = random.Random(seed + n)
    pts: list[list[float]] = []
    tries = 0
    x0, y0, x1, y1 = zone or (0.10, 0.13, 0.90, 0.72)
    min_d = 0.16 if n <= 8 else 0.13
    while len(pts) < n and tries < 6000:
        tries += 1
        x = x0 + 0.08 * (x1 - x0) + rnd.random() * 0.84 * (x1 - x0)
        y = y0 + 0.10 * (y1 - y0) + rnd.random() * 0.68 * (y1 - y0)
        # ближе к центру облака — чуть охотнее
        if rnd.random() > 0.35 + 0.65 * math.exp(-((x - 0.5) ** 2 * 3 + (y - 0.5) ** 2 * 2)):
            continue
        # прямоугольное исключение (06.09: подпись «ждёт покупателя» под одним именем ложилась
        # над соседним — «ЖД» над FLOCK): либо разнос по вертикали ≥ 0.085 высоты (имя + подпись),
        # либо по горизонтали ≥ 0.20 ширины (длинное имя с подписью)
        if all((abs(y - py) >= 0.075) or (abs(x - px) >= 0.17) for px, py in pts) and \
           all(math.hypot((x - px) * 1.4, y - py) >= min_d for px, py in pts):
            pts.append([round(x, 3), round(y, 3)])
    if len(pts) < n:
        # не разместились случайно — сетка по зоне с лёгким дрожанием (колонки по ширине, ряды по высоте)
        cols = max(1, min(n, int((x1 - x0) / 0.17)))
        rows = math.ceil(n / cols)
        pts = []
        for i in range(n):
            c_i, r_i = i % cols, i // cols
            x = x0 + (x1 - x0) * (c_i + 0.5) / cols + (rnd.random() - 0.5) * 0.02
            y = y0 + (y1 - y0) * (0.12 + 0.72 * (r_i + 0.5) / rows) + (rnd.random() - 0.5) * 0.015
            pts.append([round(x, 3), round(y, 3)])
    return pts


def render_intro(items: list[dict] | None = None) -> str:
    items = collect_items() if items is None else items
    counts = [sum(1 for it in items if it["g"] == k) for k in (0, 1, 2)]
    # ПОДПИСИ ГРУПП ПРИЛЕТАЮТ ТОЖЕ (06.09, владелец): три слова — теми же «именами» из облака,
    # первыми по тактам, каждое в своей группе: «брать» набирает свет, «держать» зеленеет,
    # «закрыть» рассыпается. Стоят рядом по низу, монеты — созвездием над ними.
    # ГОТОВЫ — СВОЯ ГРУППА (06.09, владелец: «непонятно, как отличать держать от готовы»):
    # без зелени и искр, тусклее, короткие лучи, стоят НИЖНИМ рядом над подписями —
    # «на скамейке»; держать — созвездие выше, с зелёной подсветкой
    counts = [sum(1 for it in items if it["g"] == k) for k in (0, 1, 2, 4)]
    labels = [{"n": f"первые {counts[0]}", "sym": "", "g": 0, "why": "", "label": True},
              {"n": f"в очереди {counts[1]}", "sym": "", "g": 1, "why": "", "label": True},
              {"n": f"у цели {counts[2]}", "sym": "", "g": 2, "why": "", "label": True}]
    if counts[3]:
        labels.append({"n": f"остывшие {counts[3]}", "sym": "", "g": 4, "why": "", "label": True})
    # раскладка (откат 06.09, владелец: «с зонами некрасиво»): одно облако-созвездие для всех
    # групп, различие — цветом и поведением света; подписи групп — четыре внизу
    # порядок появления (06.09, владелец): подпись группы → её звёзды → следующая → её звёзды
    # ниже и шире (07.09): раньше подписи стояли на одной высоте с потоком и наезжали друг на друга
    LABPOS = {0: [0.30, 0.945], 1: [0.52, 0.945], 2: [0.74, 0.945], 4: [0.92, 0.945]}
    star_pos = layout(len(items))
    allit: list[dict] = []
    pos: list[list[float]] = []
    k = 0
    stale = [it for it in items if it["g"] == 4]
    star_pos = layout(len([it for it in items if it["g"] != 4]))
    # остывшие — своим рядом у низа, мелко (07.09): «у цели» старше четырёх часов
    n_s = len(stale)
    stale_pos = [[round(0.14 + 0.72 * (i + 0.5) / max(1, n_s), 3), 0.83 + 0.02 * (i % 2)] for i in range(n_s)]
    si = 0
    for g in (0, 1, 2, 4):
        lab_it = next((it for it in labels if it["g"] == g), None)
        if lab_it is None:
            continue
        allit.append(lab_it); pos.append(LABPOS[g])
        for it in items:
            if it["g"] == g:
                if g == 4:
                    allit.append(it); pos.append(stale_pos[si]); si += 1
                else:
                    allit.append(it); pos.append(star_pos[k]); k += 1
    names = [it["n"] for it in allit]; grp = [it["g"] for it in allit]; syms = [it["sym"] for it in allit]
    whys = [it.get("why", "") for it in allit]
    zones = []
    lab = [1 if it.get("label") else 0 for it in allit]
    subs = [it.get("sub", "") for it in allit]
    bright = [1.0 if it.get("label") else float(it.get("bright", 0.85)) for it in allit]
    n = max(1, len(allit))
    # ПОТОК ПО ДОСКЕ (07.09): сводный тейкер из фона — своё число, а не из лент; фона нет — блок скрыт
    taker = {}
    try:
        from market_bg import last_row
        taker = (last_row() or {}).get("taker") or {}
    except Exception:  # noqa: BLE001
        taker = {}
    # ОРБИТЫ (07.09): адреса карты, место в истории, разлок — по каждому имени очереди.
    # Всё из того, что уже собирается: последний бар внутридневного архива (zones и цена),
    # дневки cq_v2 (дно и пик за всю историю), events.json (ближайший разлок по монете).
    orbits: dict = {}
    try:
        import time as _t
        _today = _t.strftime("%Y-%m-%d", _t.gmtime())
        _ev = []
        try:
            _ev = json.loads((BASE_DIR / "events.json").read_text(encoding="utf-8")) or []
        except (OSError, ValueError):
            _ev = []
        for _it in allit:
            _sym = _it.get("sym") or ""
            if not _sym or _it.get("label"):
                continue
            _base = _sym.replace("USDT", "")
            _o: dict = {}
            # адреса: последний бар архива
            try:
                _lines = (BASE_DIR / "cq_v2" / "intraday" / f"{_base.lower()}.jsonl").read_text(encoding="utf-8").splitlines()
                _last = json.loads(_lines[-1])
                _px = _last.get("px")
                _z = _last.get("zones") or {}
                if _px:
                    _up = sorted([q for q, _w in (_z.get("up") or []) if q and q > _px])
                    _dn = sorted([q for q, _w in (_z.get("down") or []) if q and q < _px], reverse=True)
                    if _up:
                        _o["up"] = round((_up[0] / _px - 1) * 100, 2)
                    if _dn:
                        _o["dn"] = round((_dn[0] / _px - 1) * 100, 2)
                    # история: дно и пик за всё, что есть в дневках
                    _d = json.loads((BASE_DIR / "cq_v2" / f"{_base.lower()}.json").read_text(encoding="utf-8"))
                    _oh = _d.get("ohlcv") or []
                    _lo = min((float(r["low"]) for r in _oh if r.get("low")), default=None)
                    _hi = max((float(r["high"]) for r in _oh if r.get("high")), default=None)
                    if _lo and _hi and _lo > 0:
                        _o["low"] = round((_px / _lo - 1) * 100, 0)
                        _o["high"] = round((_px / _hi - 1) * 100, 0)
            except (OSError, ValueError, IndexError, KeyError):
                pass
            # событие: ближайший разлок по этой монете из календаря
            try:
                _days = [
                    (datetime.strptime(e["date"], "%Y-%m-%d") - datetime.strptime(_today, "%Y-%m-%d")).days
                    for e in _ev
                    if e.get("kind") == "unlock" and _base.upper() in str(e.get("title", "")).upper()
                    and e.get("date", "") >= _today
                ]
                if _days:
                    _o["unlock"] = min(_days)
            except Exception:  # noqa: BLE001
                pass
            if _o:
                orbits[_base] = _o
    except Exception:  # noqa: BLE001
        orbits = {}

    # ЛИДЕР И МЕЛЬКАЮЩИЕ (08.09): кто ведёт, насколько оторвался от медианы наших, сколько часов
    # держится в первых, сколько прогонов подряд у него не растёт интерес, и кто мелькает —
    # входил в первые и выходил за последние прогоны. Всё из ленты очереди и near_move.
    leader: dict = {}
    flicker: list = []
    try:
        _nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
        _first = (_nm.get("first") or _nm.get("queue") or [])[:1]
        _coins = _nm.get("coins") or {}
        _moves = [((_coins.get(s2) or {}).get("today") or {}).get("px_chg_pct")
                  for s2 in (_nm.get("queue") or [])]
        _moves = [m for m in _moves if m is not None]
        if _first and _moves:
            _sym = _first[0]
            _t = (_coins.get(_sym) or {}).get("today") or {}
            _mv = _t.get("px_chg_pct") or 0.0
            _med = sorted(_moves)[len(_moves) // 2]
            _gap = (abs(_mv) / abs(_med)) if abs(_med) >= 0.3 else (abs(_mv) / 0.3 if _mv else 0)
            # часы в первых и слабые прогоны — по ленте очереди
            _rows = []
            try:
                for line in (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines():
                    try:
                        _r = json.loads(line)
                    except ValueError:
                        continue
                    if _r.get("sym") == _sym:
                        _rows.append(_r)
            except OSError:
                _rows = []
            _hours = 0
            _runs = [r for r in _rows if r.get("place")]
            for r in reversed(_runs):
                if (r.get("place") or 99) <= 3:
                    _hours += 1
                else:
                    break
            _hours = round(_hours * 0.5)                     # прогон раз в полчаса
            _weak = 0
            for r in reversed(_runs):
                _tr = r.get("oi_trend_pct")
                if _tr is None or _tr > 0:
                    break
                _weak += 1
            leader = {"sym": _sym.replace("USDT", ""), "state": _t.get("today"),
                      "run_pct": round(_mv, 0),
                      "line": f"{_mv:+.0f}% за сутки · интерес {_t.get('oi_chg_pct', 0):+.0f}%"
                              + (f" · до плиты {_t.get('to_up_pct'):.1f}%" if _t.get("to_up_pct") else ""),
                      "ended": (_t.get("ended_at") or "")[11:16] or None,
                      "hours": _hours, "lead_gap": round(_gap, 1), "runs_weak": _weak}
            # мелькающие: за последние 6 прогонов были и в первых, и вне их
            _by: dict = {}
            try:
                for line in (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines():
                    try:
                        _r = json.loads(line)
                    except ValueError:
                        continue
                    _by.setdefault(_r.get("sym"), []).append(_r.get("place"))
            except OSError:
                _by = {}
            for s3, places in _by.items():
                tail = [p for p in places[-6:] if p]
                if len(tail) >= 4 and any(p <= 3 for p in tail) and any(p > 3 for p in tail):
                    flicker.append(str(s3).replace("USDT", ""))
    except Exception:  # noqa: BLE001
        leader, flicker = {}, []

    # ПРИПИСКА О ФОНЕ (07.09, владелец: «лучше показывать, чем не показывать, но она не должна
    # никак влиять»): нейтральная строка фактов внизу экрана. В балл и в группы не входит.
    bgnote = ""
    try:
        from market_bg import bg_note
        bgnote = bg_note() or ""
    except Exception:  # noqa: BLE001
        bgnote = ""

    # ТОЧНОСТЬ (07.09): доля сбывшихся из считалки; файла нет — под планетой прочерк
    acc = {}
    try:
        _sc = json.loads((BASE_DIR / "output" / "entries_score.json").read_text(encoding="utf-8"))
        # ТОЧНОСТЬ — ПО ЗАХОДАМ В ПЕРВЫЕ (08.09): доля заходов, где монета дала ход от 2%.
        # Раньше бралась доля сбывшихся шаблонов по всей доске — число, которое ничего не говорило
        # о наших первых (23% при том, что заходы в первые давали 89%).
        _a = _sc.get("первые") or {}
        if _a.get("n"):
            acc = {"ok_pct": _a.get("доля"), "ok": _a.get("пошли"), "n": _a.get("n"),
                   "enough": bool(_a.get("n", 0) >= 20)}
    except (OSError, ValueError):
        acc = {}
    data = json.dumps({"names": names, "grp": grp, "syms": syms, "whys": whys, "pos": pos, "counts": counts, "label": lab, "subs": subs, "bright": bright, "zones": zones, "taker": taker, "acc": acc, "orbits": orbits, "bgnote": bgnote, "leader": leader, "flicker": flicker},
                      ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__N__", str(n)).replace("__DATA__", data)


TEMPLATE = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>поведение света</title>
<link href="https://fonts.googleapis.com/css2?family=Michroma&family=Inter:wght@300&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#171a3a}
  canvas{position:fixed;inset:0;width:100%;height:100%;display:block;cursor:default}
  #fx{pointer-events:none;z-index:2}
  .cap{position:fixed;left:0;right:0;bottom:26px;text-align:center;font-family:"Michroma",system-ui,sans-serif;font-size:9px;letter-spacing:.34em;text-transform:uppercase;color:rgba(200,210,255,.55);pointer-events:none}
  .cap b{font-weight:400;color:rgba(230,236,255,.9)}
  .cap .buy{color:#cfe0ff}.cap .hold{color:#8fe0b8}.cap .close{color:#8f97c8}
  /* ФОН — ПОД ПОТОКОМ (08.09, владелец: «он не читается и не виден вообще»): было 9.5px при
     прозрачности .34 внизу по центру — на тёмном фоне не видно. Стало: блок под тем же прибором,
     столбиком, числа выделены. Ничего не решает, только показывает. */
  /* ЛИДЕР (08.09): панель сверху появляется ТОЛЬКО когда одна монета тянет всё на себя —
     разрыв с медианой наших впятеро и больше либо у неё уже конец. Иначе панели нет. */
  .lead{position:fixed;left:50%;top:26px;transform:translateX(-50%);text-align:center;pointer-events:none;z-index:4;
    font-family:"Inter",system-ui,sans-serif;font-weight:300}
  .lead b{display:block;font-family:"Michroma",system-ui,sans-serif;font-weight:400;font-size:17px;
    letter-spacing:.28em;color:#f2f7ff;text-shadow:0 0 26px rgba(190,220,255,.9),0 0 60px rgba(140,180,255,.5)}
  .lead s{display:block;text-decoration:none;margin-top:7px;font-size:10.5px;letter-spacing:.14em;color:#cfe0ff}
  .lead i{display:block;font-style:normal;margin-top:5px;font-size:8px;letter-spacing:.3em;text-transform:uppercase;
    color:rgba(190,205,255,.45)}
  .lead u.hot{color:#ff8a70;text-shadow:0 0 16px rgba(255,130,100,.8)}
  .lead u.warn{color:#ffc069;text-shadow:0 0 16px rgba(255,180,90,.85)}
  .lead u{display:block;text-decoration:none;margin-top:9px;font-size:9px;letter-spacing:.24em;
    text-transform:uppercase;color:#ffd8a8;text-shadow:0 0 14px rgba(255,200,140,.7)}
  .lead.ended b{color:#ffd8cc;text-shadow:0 0 26px rgba(255,150,120,.7)}
  .lead.ended s{color:#ffd8cc}
  .bgnote{position:fixed;left:3.5vw;bottom:4vh;max-width:24vw;font-family:"Inter",system-ui,sans-serif;
    font-weight:300;font-size:10.5px;line-height:1.95;letter-spacing:.12em;color:rgba(200,214,255,.62);
    pointer-events:none}
  .bgnote i{font-style:normal;display:block;font-size:7.5px;letter-spacing:.34em;text-transform:uppercase;
    color:rgba(190,205,255,.34);margin-bottom:10px}
  .bgnote b{font-weight:400;color:#dbe6ff}
  .hint{position:fixed;right:3vw;bottom:12px;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.12em;color:rgba(200,210,255,.35);pointer-events:none}
  .tip{position:fixed;padding:6px 10px;border-radius:6px;background:rgba(10,12,30,.86);color:#dfe6ff;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.04em;max-width:360px;pointer-events:none;opacity:0;transition:opacity .2s}
  /* ПЛАНЕТА-КНОПКА В ЖУРНАЛ (07.09, владелец: «сделай кнопку на первом экране со звёздами —
     планету какую-нибудь для перехода в этот журнал»): холодный шар в гамме экрана, кольцо
     задней и передней дугой (объём, а не наклейка), два слоя облаков разной скорости,
     атмосфера, две луны навстречу друг другу, раз в семь секунд падающая звезда.
     При наведении разгорается и всё ускоряется. Клик — экран журнала прогнозов. */
  .planet{position:fixed;right:6.5vw;bottom:8vh;width:clamp(84px,10vw,130px);aspect-ratio:1;cursor:pointer;
    transition:transform .5s cubic-bezier(.2,.8,.2,1);will-change:transform;z-index:3}
  .planet:hover{transform:scale(1.07)}
  .planet .halo{position:absolute;inset:-34%;border-radius:50%;pointer-events:none;
    background:radial-gradient(circle,rgba(120,160,255,.26),transparent 62%);animation:breathe 6s ease-in-out infinite}
  @keyframes breathe{50%{transform:scale(1.13);opacity:.7}}
  .planet:hover .halo{background:radial-gradient(circle,rgba(170,205,255,.42),transparent 66%)}
  .ringbox{position:absolute;inset:-24% -30%;pointer-events:none}
  .ringbox svg{width:100%;height:100%;overflow:visible;transform:rotate(-17deg)}
  .ringbox .r1{fill:none;stroke:rgba(178,203,255,.55);stroke-width:1.1}
  .ringbox .r2{fill:none;stroke:rgba(150,180,255,.28);stroke-width:3.4;filter:blur(2px)}
  .ringbox .dust{fill:#dce8ff;opacity:.75}
  .ringspin{transform-origin:50% 50%;animation:ringspin 42s linear infinite}
  @keyframes ringspin{to{transform:rotate(360deg)}}
  .planet:hover .ringspin{animation-duration:16s}
  .ball{position:absolute;inset:0;border-radius:50%;overflow:hidden;
    background:radial-gradient(120% 120% at 26% 22%, #dbe7ff 0%, #93a6e6 22%, #4b58a0 50%, #1a2149 78%, #080d24 100%);
    box-shadow:0 0 30px rgba(120,150,255,.30), inset -16px -12px 34px rgba(0,0,0,.8), inset 9px 7px 26px rgba(200,220,255,.28)}
  .ball .c1,.ball .c2{position:absolute;inset:-40% -70%;opacity:.42;
    background:radial-gradient(28% 16% at 18% 34%, rgba(215,230,255,.85), transparent 70%),
      radial-gradient(22% 12% at 52% 62%, rgba(190,210,255,.75), transparent 70%),
      radial-gradient(30% 14% at 78% 40%, rgba(205,225,255,.7), transparent 72%);
    filter:blur(2px);animation:spin 30s linear infinite}
  .ball .c2{opacity:.24;filter:blur(5px);animation-duration:52s;animation-direction:reverse}
  @keyframes spin{to{transform:translateX(34%)}}
  .planet:hover .ball .c1{animation-duration:14s}
  .ball .lit{position:absolute;inset:0;border-radius:50%;background:radial-gradient(38% 30% at 28% 22%, rgba(255,255,255,.5), transparent 62%)}
  .ball .dark{position:absolute;inset:0;border-radius:50%;background:radial-gradient(132% 132% at 20% 18%, transparent 38%, rgba(3,6,20,.9) 78%)}
  .atmo{position:absolute;inset:-5%;border-radius:50%;pointer-events:none;
    box-shadow:inset 0 0 14px rgba(150,190,255,.55), 0 0 22px rgba(120,160,255,.35);animation:atmo 6s ease-in-out infinite}
  @keyframes atmo{50%{box-shadow:inset 0 0 20px rgba(180,215,255,.75), 0 0 30px rgba(140,180,255,.5)}}
  .orb{position:absolute;inset:-30%;pointer-events:none;animation:orbit 18s linear infinite}
  .orb.b{inset:-46%;animation-duration:31s;animation-direction:reverse}
  @keyframes orbit{to{transform:rotate(360deg)}}
  .orb i{position:absolute;left:50%;top:0;width:6px;height:6px;margin-left:-3px;border-radius:50%;
    background:#eaf1ff;box-shadow:0 0 8px #b9d0ff,0 0 20px rgba(150,190,255,.8)}
  .orb.b i{width:4px;height:4px;margin-left:-2px;opacity:.75}
  .planet:hover .orb{animation-duration:7s}
  .planet:hover .orb.b{animation-duration:12s}
  .shoot{position:absolute;left:-40%;top:12%;width:44%;height:1.5px;pointer-events:none;opacity:0;
    background:linear-gradient(90deg,transparent,#eaf2ff);transform:rotate(28deg);
    filter:drop-shadow(0 0 6px rgba(180,215,255,.9));animation:shoot 7s ease-in infinite}
  @keyframes shoot{0%,72%{opacity:0;transform:rotate(28deg) translate(0,0)}76%{opacity:1}
    88%{opacity:0;transform:rotate(28deg) translate(240%,58%)}100%{opacity:0;transform:rotate(28deg) translate(240%,58%)}}
  .pcap{position:absolute;left:50%;top:calc(100% + 16px);transform:translateX(-50%);white-space:nowrap;
    font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.3em;text-transform:uppercase;
    color:#b3c0f5;text-shadow:0 0 12px rgba(140,175,255,.8);opacity:.5;transition:opacity .3s,letter-spacing .4s}
  .planet:hover .pcap{opacity:1;letter-spacing:.42em}
  /* ТОЧНОСТЬ ЧИСЛОМ (07.09, владелец: «добавим пока к точности 55% — это по сути весомо: мы знаем
     что и когда, но не знаем фон; по мере изучения журнала будем увеличивать»). Берётся из
     output/entries_score.json (доля заходов в первые, давших ход); пусто — прочерк. */
  .pnum{position:absolute;left:50%;top:calc(100% + 34px);transform:translateX(-50%);white-space:nowrap;
    font-family:"Inter",system-ui,sans-serif;font-weight:200;font-size:19px;letter-spacing:.02em;color:#dbe4ff;
    text-shadow:0 0 14px rgba(150,185,255,.8),0 0 40px rgba(110,150,255,.45);opacity:.85}
  .pnum s{text-decoration:none;font-size:.55em;color:rgba(190,205,255,.6)}
  .planet:hover .pnum{opacity:1}
  @media (prefers-reduced-motion:reduce){.planet *{animation:none!important}}
  /* ПОТОК ПО ДОСКЕ (07.09, владелец: «его вообще к звёздам ещё надо добавить»): сводный тейкер —
     кто бьёт по стакану. Не полоса со столбиком: нить света, по ней в сторону потока плывут искры,
     на нити бусина, смещённая от середины на величину перевеса (двадцать процентов — к краю).
     Мятная — покупают, коралловая — продают. Число из output/market_bg.jsonl. */
  .flow{position:fixed;left:3.5vw;bottom:24vh;width:clamp(140px,15vw,200px);pointer-events:none;
    font-family:"Inter",system-ui,sans-serif;font-weight:300;z-index:3}
  .flow .t{font-size:6.1px;letter-spacing:.34em;text-transform:uppercase;color:rgba(190,205,255,.34);margin-bottom:48px}
  .flow .rail{position:relative;height:1px;background:linear-gradient(90deg,rgba(150,175,255,0),rgba(150,175,255,.35) 18%,rgba(150,175,255,.35) 82%,rgba(150,175,255,0))}
  .flow .rail i{position:absolute;left:50%;top:-5px;width:1px;height:11px;background:rgba(160,185,255,.35)}
  .flow .rail::after{content:"";position:absolute;inset:-3px 0;
    background:repeating-linear-gradient(90deg,rgba(210,230,255,.85) 0 2px,transparent 2px 34px);
    -webkit-mask:linear-gradient(90deg,transparent,#000 22%,#000 78%,transparent);
    mask:linear-gradient(90deg,transparent,#000 22%,#000 78%,transparent);opacity:.5;animation:drift 3.4s linear infinite}
  @keyframes drift{to{transform:translateX(34px)}}
  .flow.sell .rail::after{animation-direction:reverse}
  .flow .bead{position:absolute;top:-5px;width:10.5px;height:10.5px;border-radius:50%;transform:translateX(-50%);
    background:radial-gradient(circle at 36% 32%,#fff,#bff0dd 55%,#5cc9a6);
    box-shadow:0 0 10px rgba(127,227,200,.95),0 0 30px rgba(127,227,200,.55);
    transition:left .8s cubic-bezier(.2,.8,.2,1);animation:bead 3.2s ease-in-out infinite}
  .flow.sell .bead{background:radial-gradient(circle at 36% 32%,#fff,#ffd2c4 55%,#e8836a);
    box-shadow:0 0 10px rgba(232,131,106,.95),0 0 30px rgba(232,131,106,.5)}
  @keyframes bead{50%{transform:translateX(-50%) scale(.86)}}
  @media (prefers-reduced-motion:reduce){.flow *{animation:none!important}}
  .flow .val{position:absolute;top:-40px;transform:translateX(-50%);white-space:nowrap;
    font-size:10.9px;font-weight:200;letter-spacing:.01em;color:#e2ebff;
    text-shadow:0 0 16px rgba(150,190,255,.75);transition:left .8s cubic-bezier(.2,.8,.2,1)}
  .flow .val s{text-decoration:none;display:block;margin-top:4px;font-size:5.8px;letter-spacing:.24em;
    text-transform:uppercase;color:rgba(200,212,255,.45);text-align:center}
  .flow .ends{position:relative;height:0}
  .flow .ends em{position:absolute;top:24px;font-style:normal;font-size:6.1px;letter-spacing:.26em;
    text-transform:uppercase;color:rgba(190,205,255,.4)}
  .flow .mark{position:absolute;top:-7px;width:1px;height:15px;background:#ffd8a8;
    box-shadow:0 0 8px rgba(255,200,140,.9);opacity:0;transition:left .8s cubic-bezier(.2,.8,.2,1),opacity .4s}
  .flow .mark u{position:absolute;left:50%;top:19px;transform:translateX(-50%);text-decoration:none;white-space:nowrap;
    font-size:5.8px;letter-spacing:.22em;text-transform:uppercase;color:#ffd8a8}
</style>
</head>
<body>
<canvas id="c"></canvas>
<canvas id="fx"></canvas>
<div class="flow" id="flow">
  <div class="t">поток по доске</div>
  <div class="rail"><i></i>
    <span class="val" id="fval">—</span>
    <span class="bead" id="bead"></span>
    <span class="mark" id="fmark"><u>разворот</u></span>
  </div>
  <div class="ends"><em class="l">продают</em><em class="r">покупают</em></div>
</div>
<div class="planet" id="planet" title="точность прогнозов">
  <div class="halo"></div>
  <div class="ringbox"><svg viewBox="0 0 100 100"><path class="r2" d="M2,50 A48,15 0 0 0 98,50"/><path class="r1" d="M2,50 A48,15 0 0 0 98,50"/></svg></div>
  <div class="ball"><div class="c1"></div><div class="c2"></div><div class="lit"></div><div class="dark"></div></div>
  <div class="atmo"></div>
  <div class="ringbox"><svg viewBox="0 0 100 100"><path class="r2" d="M2,50 A48,15 0 0 1 98,50"/><path class="r1" d="M2,50 A48,15 0 0 1 98,50"/>
    <g class="ringspin"><circle class="dust" cx="86" cy="53.4" r="1.1"/><circle class="dust" cx="18" cy="46.4" r=".8"/><circle class="dust" cx="60" cy="57" r=".7"/></g></svg></div>
  <div class="orb a"><i></i></div><div class="orb b"><i></i></div>
  <div class="shoot"></div>
  <div class="pcap">точность</div>
  <div class="pnum" id="pnum">—</div>
</div>
<div class="lead" id="lead"></div>
<div class="bgnote" id="bgnote"></div>
<div class="hint">клик по имени — монета · планета — точность · мимо или клавиша — дальше</div>
<div class="tip" id="tip"></div>
<script id="introData" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('introData').textContent);
// группы: 0 — брать, 1 — держать, 2 — закрыть (владелец, 06.09)
const names=DATA.names.length?DATA.names:['—'],GRP=DATA.names.length?DATA.grp:[1];
const N=names.length,NF=4,FONT='Michroma';
const POS=DATA.names.length?DATA.pos:[[.5,.5]];
const LAB=DATA.label||[];
// зоны и полосы сняты (06.09, владелец): группы различаются светом, не местом

const c=document.getElementById('c');
const gl=c.getContext('webgl',{antialias:false,alpha:false});
const VS=`attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
const FS=`precision highp float;
uniform vec2 R;uniform float T,A;uniform vec2 P[${N}];uniform float F[${N}];uniform float G[${N}];uniform float BR[${N}];uniform float HW[${N}];uniform float HS[${N}];uniform float HH;uniform float SUBDY;uniform float LEAD;uniform float LEADW;uniform float LEADRUN;uniform sampler2D M;uniform vec2 S[${N*NF}];uniform float SP[${N*NF}];
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(1.6,1.2,-1.2,1.6);
  for(int i=0;i<6;i++){v+=a*noise(p);p=m*p;a*=.5;}return v;}
void main(){
  vec2 uv=gl_FragCoord.xy/R;float ar=R.x/R.y;vec2 p=(uv-.5)*vec2(ar,1.);vec2 px=gl_FragCoord.xy;
  vec2 q=vec2(fbm(p*2.4+vec2(0.,T*.13)),fbm(p*2.4+vec2(5.2,1.3)-vec2(T*.1,0.)));
  vec2 r=vec2(fbm(p*2.4+q*2.2+vec2(1.7,9.2)+T*.08),fbm(p*2.4+q*2.2+vec2(8.3,2.8)-vec2(0.,T*.07)));
  float d=fbm(p*2.4+r*2.6);
  float Fi=0.,Fm=0.,Gi=1.,Bi=1.,best=1e9;
  for(int i=0;i<${N};i++){float dd=length((uv-P[i])*vec2(ar,1.));best=min(best,dd);Fm=max(Fm,F[i]);}
  // СВОЙ ПРЯМОУГОЛЬНИК (07.09, владелец: «рядом куча обрывков от других звёзд»): свет и «сборка»
  // живут только в рамке СВОЕГО имени — по его измеренной полуширине HW и полувысоте HH;
  // за рамкой всё гаснет, поэтому смещённая маска не приносит буквы соседей
  // ВЛАДЕЛЕЦ ПИКСЕЛЯ — ПО РАМКЕ, НЕ ПО БЛИЖАЙШЕМУ ЦЕНТРУ (07.09, владелец: «куча артефактов
  // текстов от звёзд, которые ещё не нарисовались»). Маска одна на всех, а гасили её по Fi
  // БЛИЖАЙШЕГО имени: длинная подпись под именем A попадала в зону имени B, и когда B уже
  // собралось, обрывки строки A светились раньше времени. Теперь пиксель принадлежит тому, в чью
  // рамку он попал: имя — по своей полуширине, подпись — по своей, ниже на SUBDY. Вне всех рамок
  // свет маски равен нулю, поэтому обрывков нет вовсе.
  float inbox=0., hwi=0.;
  for(int i=0;i<${N};i++){
    float bxi=abs(uv.x-P[i].x), byi=uv.y-P[i].y;
    float inName=smoothstep(HW[i]+.030,HW[i]+.004,bxi)*smoothstep(HH*2.2,HH*1.05,abs(byi));
    float inSub =smoothstep(HS[i]+.030,HS[i]+.004,bxi)*smoothstep(HH*1.9,HH*.85,abs(byi+SUBDY));
    float own=max(inName,inSub);
    if(own>inbox){inbox=own;hwi=HW[i];Fi=F[i];Gi=G[i];Bi=BR[i];}
  }
  float w=mix(.045,.003,Fi)*inbox;   // (07.09) смещение маски только внутри своей рамки
  vec2 mu=uv+(r-.5)*w;
  vec3 mk=texture2D(M,vec2(mu.x,1.-mu.y)).rgb;
  vec3 ms=texture2D(M,vec2(uv.x,1.-uv.y)).rgb;
  float core=ms.r,soft=ms.b,halo=mk.g;
  float isStale=step(3.5,Gi);
  float isReady=step(2.5,Gi)*(1.-isStale);
  float isClose=step(1.5,Gi)*(1.-isReady),isBuy=1.-step(.5,Gi),isHold=(1.-isClose)*(1.-isBuy)*(1.-isReady);
  float er=smoothstep(.3,.75,fbm(px*.045+vec2(T*.12,-T*.05)))*(.45+.3*sin(T*.3))*isClose;
  core*=1.-er*.9;soft*=1.-er*.75;
  float near_=smoothstep(.16,.04,best)*inbox;
  float drift=texture2D(M,vec2(uv.x-hash(px+3.)*.012,1.-(uv.y+hash(px+5.)*.008))).b*isClose*near_;
  float wrap=(halo*(.35+.65*smoothstep(.25,.85,d))+mk.r*.4)*Fi*near_;
  float blob=exp(-dot(p*vec2(1.1,.95),p*vec2(1.1,.95))*1.8);
  float cloud=smoothstep(.36,.85,d)*blob;
  float dens=clamp(cloud*(1.-Fm*.5)+wrap,0.,1.);
  vec3 bg=mix(vec3(.085,.095,.22),vec3(.16,.18,.36),uv.y*.8+exp(-dot(p,p)*1.6)*.35);
  vec3 deep=vec3(.20,.23,.52),mid=vec3(.44,.50,.86),hot=vec3(.80,.85,1.);
  vec3 col=mix(deep,mid,dens);col=mix(col,hot,pow(dens,2.5));
  col=bg+col*dens*1.15;
  col+=hot*pow(smoothstep(.55,.92,d)*max(cloud,wrap),3.)*.8;
  float appear=smoothstep(0.,.18,Fi);                 // имя ещё не пришло — маска не светится вовсе
  float vis=smoothstep(1.05-Fi*1.25,1.3-Fi*1.25,d+.1)*inbox*appear;
  float lvl=.82*Bi*(1.-.45*isReady)*(1.-.55*isStale);   // общий уровень понижен; «готовы» — ещё бледнее, без зелени
  col+=vec3(.34,.38,.72)*(soft*.8+core*.15)*vis*lvl;
  col+=vec3(.36,.42,.8)*halo*vis*.4*Fi*lvl;
  float grain=hash(px*.9+floor(T*6.)*3.1);
  float crack=smoothstep(.62,.7,fbm(px*.06+vec2(T*.25,T*.1)+11.));
  col+=vec3(.55,.62,.95)*core*vis*(grain*.18+crack*.25);
  col+=vec3(.34,.38,.72)*drift*step(.55,hash(px*1.7+floor(T*5.)))*.4*vis;
  col+=vec3(.5,.56,.9)*halo*vis*.25*isBuy*(.5+.5*sin(T*2.));
  col+=vec3(.30,.78,.58)*(halo*.32+soft*.22)*vis*isHold*Fi;
  col+=vec3(.40,.58,1.)*(halo*.28+soft*.30)*vis*isReady*Fi;                     // готовы: ровный синий, не мигает
  for(int i=0;i<${N*NF};i++){
    float on=smoothstep(.6,1.,F[i/${NF}])*(.55+.45*BR[i/${NF}]);   // блики тусклее у менее надёжных
    if(on<=0.)continue;
    float ph=SP[i];float gi=G[i/${NF}];

    vec3 fc=(gi>.5&&gi<1.5)?vec3(.72,1.,.86):(gi>2.5?vec3(.42,.62,1.):(gi<.5?vec3(.97,.98,1.):vec3(.86,.96,1.)));
    // ЛИДЕР МОЖЕТ КОНЧАТЬСЯ (08.09, владелец: «надо показывать заранее, а не ждать три прогона» —
    // SOPH за час отдал треть от вершины). Первое же подозрение красит лучи; насколько — по тому,
    // сколько монета уже прошла за день:
    //   ход больше 150% — приглушённый красный, ровный свет;
    //   ход меньше 150% — тёплый янтарь и медленное дыхание вместо ровного света.
    float isLead = step(abs(float(i/${NF}) - LEAD), .5) * step(0., LEAD);
    float sus  = step(.5, LEADW) * isLead;
    float big  = step(150., LEADRUN);
    float warn = clamp(LEADW / 3., 0., 1.) * isLead;
    vec3 wcol  = mix(vec3(1., .74, .52), vec3(1., .46, .34), big);
    fc = mix(fc, wcol, sus * mix(.45, .75, big));   // брать белые · держать зелёные · готовы синие
    vec2 cc=S[i]*R+(gi>2.5?vec2(0.):vec2(sin(T*1.9+ph*9.),cos(T*1.5+ph*5.))*1.4);
    vec2 dp=px-cc;float dist=length(dp);
    if(dist>mix(110.,240.,BR[i/${NF}]))continue;   // дальше ищем: луч стал длиннее (08.09)
    float ang=ph*6.28*.15+(gi>2.5?0.:sin(T*.35+ph*4.)*.45);
    float cs=cos(ang),sn=sin(ang);vec2 dr=vec2(dp.x*cs-dp.y*sn,dp.x*sn+dp.y*cs);
    float pulse=.4+.6*pow(.5+.5*sin(T*1.3+ph*6.28),3.);
    if(gi>2.5)pulse=.6;                                               // готовы: ровно, без дыхания
    if(gi>1.5&&gi<2.5)pulse*=step(.3,hash(vec2(floor(T*7.)+ph*13.,ph)));   // мигание — только «у цели»
    if(gi>3.5)pulse=.4;                                                    // остывшие: ровно и тускло
    if(gi<.5)pulse=.7+.3*pulse;
    // дыхание вместо мигания: период около шести секунд, свет плавно гаснет и разгорается
    float breathe = .42 + .58 * (.5 + .5 * sin(T * (.95 + .35 * warn)));
    pulse = mix(pulse, mix(breathe, .95, big), sus);
    float k=exp(-dist*dist/5.);
    // ДЛИНА ЛУЧЕЙ — ПО НАДЁЖНОСТИ (06.09, владелец: «чем больше длина, тем надёжнее»):
    // у надёжной луч в три раза длиннее, у слабой — короткий
    // ЛУЧ (08.09, правки владельца): втрое тоньше прежнего, длиннее, и вдоль него яркость идёт
    // колоколом — у ядра приглушена, вспышка на пятой части длины, дальше плавно в ноль. Длина —
    // ОБРАТНА спаду rk: у надёжной луч длиннее. Яркость для длины зажата в 0..1, иначе у лидера
    // (BR выше единицы) множитель уходил в минус и луч пропадал совсем.
    float rb=clamp(BR[i/${NF}],0.,1.);float rk=mix(3.2,1.,rb);if(gi>2.5)rk=1.9;
    float LX = 420./rk, LY = 170./rk;
    float lx = abs(dr.x)/LX, ly = abs(dr.y)/LY;
    float envX = smoothstep(0., .22, lx) * pow(max(0., 1. - lx), 2.2);
    float envY = smoothstep(0., .22, ly) * pow(max(0., 1. - ly), 2.2);
    // СИЛА ЛУЧА (08.09, владелец: «у всех звёзд огромное свечение как у лидера, вернуть как было»):
    // при переделке я поднял яркость всем, а не только лидеру. Возвращаю прежний уровень (было .7
    // и .4 до правок), лидер выделяется своей яркостью BR, а не общей силой луча.
    float st = exp(-abs(dr.y)*2.7) * envX * .95 + exp(-abs(dr.x)*2.7) * envY * .55;
    vec2 dd=vec2(dr.x+dr.y,dr.x-dr.y)*.7071;
    float LD = 260./rk;
    float ldx = abs(dd.y)/LD, ldy = abs(dd.x)/LD;
    float envDx = smoothstep(0., .22, ldx) * pow(max(0., 1. - ldx), 2.2);
    float envDy = smoothstep(0., .22, ldy) * pow(max(0., 1. - ldy), 2.2);
    st += (exp(-abs(dd.x)*3.6)*envDx + exp(-abs(dd.y)*3.6)*envDy) * .28;
    float glow=exp(-dist*.07)*.3;
    col+=fc*(k*1.8+st+glow)*pulse*on;
    float below=step(dp.y,0.)*smoothstep(gi>1.5?-130.:-70.,-8.,dp.y)*(1.-step(2.5,gi));
    float sig=2.+(-dp.y)*.05;
    float colm=exp(-dp.x*dp.x/(2.*sig*sig));
    float spd=gi<.5?-(45.+ph*30.):(gi>1.5?150.+ph*80.:60.+ph*50.);
    vec2 g=vec2(floor((px.x+ph*100.)/2.),floor((px.y+T*spd)/2.));
    float sp=step(gi>1.5?.962:.982,hash(g+ph));
    col+=fc*sp*colm*below*on*pulse*1.2;
  }
  vec2 sc=px/56.;vec2 cell=floor(sc),f=fract(sc);
  float h=hash(cell);vec2 spos=vec2(hash(cell+1.7),hash(cell+3.1));
  float ddd=length((f-spos)*56.);float sz=.5+h*1.1;
  float star=exp(-ddd*ddd/(sz*sz))*step(.78,h)*(.35+.65*(.5+.5*sin(T*.6+h*40.)));
  col+=vec3(.72,.75,.95)*star*.55;
  col*=A;
  gl_FragColor=vec4(col,1.);
}`;
function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o}
const prog=gl.createProgram();gl.attachShader(prog,sh(gl.VERTEX_SHADER,VS));gl.attachShader(prog,sh(gl.FRAGMENT_SHADER,FS));
gl.linkProgram(prog);gl.useProgram(prog);
gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
const ap=gl.getAttribLocation(prog,'p');gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,2,gl.FLOAT,false,0,0);
const U=n=>gl.getUniformLocation(prog,n);const uR=U('R'),uT=U('T'),uF=U('F'),uA=U('A'),uS=U('S'),uSP=U('SP');
gl.uniform2fv(U('P'),new Float32Array(POS.flatMap(([x,y])=>[x,1-y])));gl.uniform1fv(U('G'),new Float32Array(GRP));
gl.uniform1fv(U('BR'),new Float32Array(DATA.names.length?DATA.bright:[1]));
{const L=DATA.leader||{};const li=DATA.names.indexOf(L.sym||'');
 gl.uniform1f(U('LEAD'), (li>=0&&!L.ended)?li:-1);
 gl.uniform1f(U('LEADW'), L.ended?3:(L.runs_weak||0));
 gl.uniform1f(U('LEADRUN'), Math.abs(L.run_pct||0));}
const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
gl.uniform1i(U('M'),0);
const mc=document.createElement('canvas'),m=mc.getContext('2d');
let W,H,SIZE=14;
function mask(){
  mc.width=W;mc.height=H;
  m.globalCompositeOperation='source-over';m.fillStyle='#000';m.fillRect(0,0,W,H);
  const size=Math.min(21,Math.max(9,W*.012));SIZE=size;
  m.font=`400 ${size}px "${FONT}",system-ui,sans-serif`;m.textAlign='center';m.textBaseline='middle';
  m.letterSpacing='0.12em';
  m.globalCompositeOperation='lighter';
  for(let i=0;i<N;i++){const x=W*POS[i][0]+size*.06,y=H*POS[i][1],name=names[i];
    // подписи групп — кириллицей, Michroma её не знает: Inter, чуть крупнее и с разрядкой
    const isStale=(DATA.grp||[])[i]===4;
    m.font=LAB[i]?`300 ${size*(isStale?.78:.92)}px "Inter",system-ui,sans-serif`:`400 ${size*(isStale?.66:.935)}px "${FONT}",system-ui,sans-serif`;   // остывшие мельче (07.09)
    m.letterSpacing=LAB[i]?'0.32em':'0.12em';
    m.fillStyle='#0f0';m.filter=`blur(${size*.16}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
    m.fillStyle='#00f';m.filter=`blur(${size*.035}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
    m.fillStyle='#f00';m.filter='none';m.fillText(name,x,y);
    // ПОДПИСЬ — ХВОСТОМ, ОТДЕЛЬНЫМ СЛОЕМ (07.09, выбор владельца): в маске её больше нет, иначе
    // длинная строка снова цепляла бы соседей; рисуется на canvas #fx поверх шейдера
  }
  gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,mc);
  // ненайденный блик уводим далеко за экран (07.09): в шейдере WebGL1 нельзя отсекать
  // по значению uniform-массива с динамическим индексом — падала компиляция и весь скрипт
  const img=m.getImageData(0,0,W,H).data,S=new Float32Array(N*NF*2).fill(9.0),SP=new Float32Array(N*NF);
  const nameW=new Array(N);
  for(let i=0;i<N;i++){m.font=LAB[i]?`300 ${size*.92}px "Inter",system-ui,sans-serif`:`400 ${size*.935}px "${FONT}",system-ui,sans-serif`;
    m.letterSpacing=LAB[i]?'0.32em':'0.12em';nameW[i]=m.measureText(names[i]).width;}
  for(let i=0;i<N;i++){const x=W*POS[i][0]+size*.06,y=H*POS[i][1],name=names[i];
    for(let n=0,tries=0;n<NF&&tries<4000;tries++){
      // блик — только внутри СВОЕГО имени (07.09: брали из полосы шире имени и цепляли соседей —
      // рядом рисовались лучи без названий); ширину берём измерением, не длиной строки
      const half=nameW[i]/2;
      const px=Math.floor(x+(Math.random()-.5)*half*1.7),py=Math.floor(y+(Math.random()-.5)*size*.8);
      if(px<0||py<0||px>=W||py>=H)continue;
      if(Math.abs(px-x)>half+2||Math.abs(py-y)>size*.6)continue;
      if(img[(py*W+px)*4]>140){S[(i*NF+n)*2]=px/W;S[(i*NF+n)*2+1]=1-py/H;SP[i*NF+n]=Math.random();n++}
    }
  }
  gl.uniform2fv(uS,S);gl.uniform1fv(uSP,SP);
  // полуширина каждого имени в долях ширины — для ореола «брать»
  m.font=`400 ${size*.935}px "${FONT}",system-ui,sans-serif`;m.letterSpacing='0.12em';
  const HW=new Float32Array(N),HS=new Float32Array(N);
  for(let i=0;i<N;i++){HW[i]=(m.measureText(names[i]).width/2)/W;}
  // подпись ушла в слой хвостов — в маске её нет, рамка только по имени (07.09)
  for(let i=0;i<N;i++){HS[i]=0;}
  gl.uniform1fv(U('HW'),HW);gl.uniform1fv(U('HS'),HS);
  gl.uniform1f(U('HH'),(size*.55)/H);gl.uniform1f(U('SUBDY'),(size*1.05)/H);
}
const T_IN=2.8,GAP=Math.max(1.4,Math.min(3.0,24/N));   // при 12 именах — по 2 с, чтобы созвездие собралось за полминуты
const ease=x=>x*x*(3-2*x);
const Fv=new Float32Array(N);
function resize(){const d=Math.min(devicePixelRatio,1.5);W=innerWidth;H=innerHeight;
  c.width=W*d;c.height=H*d;gl.viewport(0,0,c.width,c.height);gl.uniform2f(uR,c.width,c.height);mask()}
addEventListener('resize',resize);
let start=null;
function loop(now){
  now/=1000;if(start===null)start=now;
  for(let i=0;i<N;i++){const t=now-start-.6-i*GAP;Fv[i]=t<=0?0:t>=T_IN?1:ease(t/T_IN)}
  gl.uniform1fv(uF,Fv);gl.uniform1f(uT,now);gl.uniform1f(uA,Math.min(1,(now-start)/1.5));
  gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  drawFx(now-start);
  requestAnimationFrame(loop);
}
// ── взаимодействие (06.09): клик по имени — монета; мимо или клавиша — дальше по оболочке ──
function hit(ev, withLabels){const x=ev.clientX,y=ev.clientY;
  for(let i=0;i<N;i++){if(LAB[i]&&!withLabels)continue;
    const cx=W*POS[i][0],cy=H*POS[i][1],
      hw=(LAB[i]?names[i].length*SIZE*.55+14:names[i].length*SIZE*.62+8),hh=SIZE*.9+6;
    if(Math.abs(x-cx)<=hw&&Math.abs(y-cy)<=hh)return i;}return -1;}

// ФИЛЬТР ПО ГРУППЕ (07.09, владелец: «при наведении/нажатии на категорию показывать только звёзды
// этой категории и не закрывать экран»). Гасим чужие имена уровнем яркости BR — сама сборка и
// такты не трогаются, экран остаётся на месте. Наведение — временно, клик — закрепляет; повторный
// клик по той же подписи или клик мимо снимает.
let PICK=null, HOVER=null;
const BR0=new Float32Array(DATA.names.length?DATA.bright:[1]);
function applyGroup(){
  const g=(PICK!==null)?PICK:HOVER;
  const out=new Float32Array(BR0.length);
  for(let i=0;i<BR0.length;i++){
    const mine=(g===null)||((DATA.grp||[])[i]===g);
    out[i]=mine?BR0[i]*((PICK!==null&&mine&&!LAB[i])?1.15:1):BR0[i]*0.12;
  }
  gl.uniform1fv(U('BR'),out);
}
const tip=document.getElementById('tip');
c.addEventListener('mousemove',ev=>{const j=hit(ev,true),i=hit(ev);
  c.style.cursor=(j>=0)?'pointer':'default';
  const hg=(j>=0&&LAB[j])?(DATA.grp||[])[j]:null;
  if(hg!==HOVER){HOVER=hg;applyGroup();}
  if(i>=0&&DATA.whys[i]){tip.textContent=names[i]+' — '+DATA.whys[i];tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+12)+'px';tip.style.opacity=1}
  else if(j>=0&&LAB[j]){tip.textContent=names[j]+' — только эта группа; клик закрепляет';tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+12)+'px';tip.style.opacity=1}
  else tip.style.opacity=0});
c.addEventListener('mouseleave',()=>{HOVER=null;applyGroup();tip.style.opacity=0});
function next(){try{window.parent.postMessage({type:'ob:done',screen:'intro'},'*')}catch(e){}
  if(window===window.parent)location.href='brief.html'}
c.addEventListener('click',ev=>{const j=hit(ev,true);
  // клик по подписи группы — фильтр, экран НЕ закрываем (07.09)
  if(j>=0&&LAB[j]){const g=(DATA.grp||[])[j];PICK=(PICK===g)?null:g;applyGroup();return}
  // клик мимо при закреплённой группе — сначала снимаем фильтр, а не уходим со экрана
  if(PICK!==null&&hit(ev)<0){PICK=null;applyGroup();return}
  const i=hit(ev);
  if(i>=0){const target='coin.html#'+encodeURIComponent(names[i]);
    if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'coin',hash:names[i]},'*')}catch(e){}}
    location.href=target;return}
  next()});
// ── СЛОЙ ХВОСТОВ И ОРБИТ (07.09) ──────────────────────────────────────────────────────────────
// Подпись — шлейфом от звезды: ближние слова ярче, дальние тают, хвост качается с инерцией.
// Орбиты вокруг имени: ближняя пара — адреса карты (золотая плита сверху, коралловая опора снизу,
// радиус = расстояние в процентах, тесная орбита = адрес рядом), дальняя зелёная — место цены
// между историческим дном и пиком (угол спутника), внешняя янтарная — разлок, подлетает к дате.
// Слой рисуется на своём canvas поверх шейдера, шейдер не трогается.
const fx=document.getElementById('fx'),fc=fx.getContext('2d');
let FW=0,FH=0;
function fxResize(){const d=Math.min(devicePixelRatio,2);FW=innerWidth;FH=innerHeight;
  fx.width=FW*d;fx.height=FH*d;fc.setTransform(d,0,0,d,0,0);}
addEventListener('resize',fxResize);fxResize();
let MX=-1,MY=-1;
c.addEventListener('mousemove',e=>{MX=e.clientX;MY=e.clientY});
c.addEventListener('mouseleave',()=>{MX=-1;MY=-1});
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
function ell(cx,cy,rx,ry,col,op){fc.strokeStyle=col.replace('OP',op.toFixed(2));fc.lineWidth=1;
  fc.beginPath();fc.ellipse(cx,cy,rx,ry,0,0,7);fc.stroke();}
function bead(px,py,r,fill,glow,op){fc.fillStyle=fill;fc.shadowColor=glow;fc.shadowBlur=10*op;
  fc.beginPath();fc.arc(px,py,r,0,7);fc.fill();fc.shadowBlur=0;}
function drawFx(t){
  if(!FW)return;
  fc.clearRect(0,0,FW,FH);
  const SZ=SIZE||14, ORB=DATA.orbits||{};
  // ── РАЗБОР ТЕСНОТЫ (07.09, владелец: «всё друг на друга накладывается»): для каждой звезды
  // считаем расстояние до ближайшей соседки; чем теснее — тем меньше её система орбит и тем
  // короче хвост. Полный хвост показываем только у первых трёх, у наведённой и у закреплённой
  // группы; у остальных — два слова. Так экран остаётся читаемым при двенадцати именах.
  const near_d=[], dirs=[];
  for(let i=0;i<N;i++){
    if(LAB[i]){near_d.push(1);dirs.push(1);continue}
    let best=1e9,bx=0;
    for(let j=0;j<N;j++){if(j===i||LAB[j])continue;
      const dx=(POS[j][0]-POS[i][0])*FW, dy=(POS[j][1]-POS[i][1])*FH, d=Math.hypot(dx,dy);
      if(d<best){best=d;bx=dx}}
    near_d.push(best/ (SZ*10));                       // 1 — просторно, <1 — тесно
    dirs.push(bx>0?-1:1);                             // хвост уходит ОТ соседа
  }
  // ── ДУГА ВМЕСТО КОЛЬЦА: рисуем не всю орбиту, а след за спутником — ближняя половина ярче
  // дальней, поэтому орбита читается наклонённой, а не плоским овалом
  function arc(cx,cy,rx,ry,a,col,op,tilt){
    const N_=26, L=Math.PI*1.15;                      // длина следа
    fc.lineWidth=1;fc.lineCap='round';
    for(let k=0;k<N_;k++){
      const u=k/N_, ang=a-L*u;
      const x1=cx+Math.cos(ang)*rx*Math.cos(tilt)-Math.sin(ang)*ry*Math.sin(tilt);
      const y1=cy+Math.cos(ang)*rx*Math.sin(tilt)+Math.sin(ang)*ry*Math.cos(tilt);
      const ang2=a-L*((k+1)/N_);
      const x2=cx+Math.cos(ang2)*rx*Math.cos(tilt)-Math.sin(ang2)*ry*Math.sin(tilt);
      const y2=cy+Math.cos(ang2)*rx*Math.sin(tilt)+Math.sin(ang2)*ry*Math.cos(tilt);
      const far=(Math.sin(ang)<0)?0.45:1;             // дальняя половина тусклее — это и даёт глубину
      fc.strokeStyle=col.replace('OP',(op*(1-u)*far).toFixed(3));
      fc.beginPath();fc.moveTo(x1,y1);fc.lineTo(x2,y2);fc.stroke();
    }
    const px=cx+Math.cos(a)*rx*Math.cos(tilt)-Math.sin(a)*ry*Math.sin(tilt);
    const py=cy+Math.cos(a)*rx*Math.sin(tilt)+Math.sin(a)*ry*Math.cos(tilt);
    return [px,py,(Math.sin(a)<0)?0.55:1];
  }
  for(let i=0;i<N;i++){
    if(LAB[i])continue;
    const F=Fv[i]; if(F<=0.02)continue;
    const g=(DATA.grp||[])[i];
    if(PICK!==null&&g!==PICK)continue;
    const cx=FW*POS[i][0],cy=FH*POS[i][1];
    const near=MX>=0&&(Math.hypot(MX-cx,MY-cy)<SZ*7 || (Math.abs(MY-cy-SZ*1.05)<SZ*1.6 && Math.abs(MX-cx)<SZ*12));
    const room=Math.max(.45,Math.min(1,near_d[i]));   // теснота ужимает систему
    const K=SZ*room*(near?1.15:1);
    const a0=(near?.95:.5)*F;
    const o=ORB[names[i]]||{};
    const tilt=-0.34+((i%3)-1)*0.16;                  // у каждой звезды свой наклон плоскости
    // радиус по логарифму расстояния: близкий адрес — тесная орбита, но овалы не разрастаются
    const rr=v=>K*(1.25+1.5*Math.log10(1+Math.max(0,v)));
    if(o.up!=null){const [px,py,dp]=arc(cx,cy,rr(o.up)*1.25,rr(o.up)*.5,t*.5+i,'rgba(230,211,163,OP)',(near?.85:.5)*F,tilt);
      bead(px,py,(o.up<2?2.6:1.9)*dp,'#fff2d2','rgba(230,211,163,.95)',a0*dp);}
    if(o.dn!=null){const [px,py,dp]=arc(cx,cy,rr(-o.dn)*1.25,rr(-o.dn)*.5,-t*.38+i*1.7,'rgba(255,138,112,OP)',(near?.7:.4)*F,tilt);
      bead(px,py,(-o.dn<3?2.6:1.9)*dp,'#ffdcd2','rgba(255,138,112,.95)',a0*dp);}
    // история — короткая дуга, угол = место цены между дном и пиком
    if(o.low!=null&&o.high!=null){
      const rh=K*3.4, k=Math.max(0,Math.min(1,o.low/(o.low+Math.abs(o.high)))), a=Math.PI-Math.PI*k;
      const [px,py,dp]=arc(cx,cy,rh*1.2,rh*.46,a,'rgba(143,224,184,OP)',(near?.55:.26)*F,tilt);
      bead(px,py,2.2*dp,'#dcfff0','rgba(143,224,184,.95)',a0*dp);}
    // разлок — только когда близко: за неделю и ближе, иначе экран рябит
    if(o.unlock!=null&&o.unlock<=7){
      const k=1-o.unlock/7, re=K*(4.6-1.8*k), a=t*.22+i*.9;
      const [px,py,dp]=arc(cx,cy,re*1.2,re*.46,a,'rgba(255,215,160,OP)',(near?.6:.3+.3*k)*F,tilt);
      bead(px,py,(1.8+1.6*k)*dp,'#ffeecd','rgba(255,200,140,.95)',a0*dp);
      if(near){fc.font=`300 ${SZ*.5}px "Inter",system-ui,sans-serif`;fc.textAlign='left';fc.textBaseline='middle';
      fc.fillStyle='rgba(255,225,180,.9)';fc.fillText('разлок '+o.unlock+' дн',px+SZ*.5,py);}
    }
    // ── ПОДПИСЬ: три вида, переключаются кнопками (07.09, владелец: «тексты выглядят некрасиво»)
    // A — строка-шлейф: одна строка вбок, слова гаснут к хвосту; ничего не громоздится
    // B — два уровня: крупное слово «что сейчас» и одна мелкая строка под ним
    // C — капсулы: короткие пилюли в ряд, как метки на приборе
    const subAll=((DATA.subs||[])[i]||'').split(' · ').filter(Boolean);
    if(subAll.length){
      const dir=dirs[i];
      // ПОЛНОТА ПОДПИСИ (08.09, владелец: «зачем мне полная строка»): на экране у ВСЕХ коротко —
      // одно слово состояния или доля выхода/хеджа. Полная строка только при наведении и в
      // закреплённой группе. Экран чистый, разбор — по наведению.
      const full=near||PICK!==null;
      const why=((DATA.whys||[])[i]||'').split(' · ').filter(Boolean);
      const parts=(near&&(g===2||g===4)&&why.length)?why.concat(subAll):subAll;   // у цели: при наведении — чем живёт
      const state=parts[parts.length-1];                       // «набирают сегодня» / «стоит» / …
      const mode=subAll[0];                                      // «лестница» / «парабола»
      const mid=subAll.slice(1,-1);                              // сбор · плечо
      fc.textBaseline='middle';
      // ПОДПИСЬ — СТРОКА-ШЛЕЙФ (07.09, выбор владельца из трёх видов): одна строка вбок,
      // слова гаснут к хвосту, разделены точкой; вниз ничего не громоздится
      const words=full?parts:[state];
      fc.font=`300 ${SZ*.52}px "Inter",system-ui,sans-serif`;
      fc.textAlign=dir>0?'left':'right';
      let off=SZ*1.25;
      words.forEach((w,k)=>{
        const fade=1-k/(words.length+.9);
        fc.fillStyle='rgba(186,199,248,'+(((near?.95:.62)*(0.35+0.65*fade))*F).toFixed(2)+')';
        const px=cx+dir*off, py=cy+SZ*.95+Math.sin(t*.5+i+k*.6)*SZ*.045*k;
        if(k===0){fc.shadowColor='rgba(150,190,255,.65)';fc.shadowBlur=near?7:3}
        fc.fillText(w,px,py);fc.shadowBlur=0;
        off+=fc.measureText(w).width+SZ*.55;
        if(k<words.length-1){                                   // разделитель-точка
          fc.fillStyle='rgba(150,175,240,'+((0.3*fade)*F).toFixed(2)+')';
          fc.fillText('·',cx+dir*(off-SZ*.33),py);}
      });
    }
  }
}
// ЛИДЕР И МЕЛЬКАЮЩИЕ (08.09) — только показ, порядок очереди не меняется
(function(){
  const L=DATA.leader||{}, el=document.getElementById('lead');
  const PULL=(Math.abs(L.run_pct||0)>=50) && ((L.lead_gap||0)>=5 || L.ended || (L.runs_weak||0)>0);
  if(el&&L.sym&&PULL){
    el.className='lead'+(L.ended?' ended':'');
    el.innerHTML='<i>сейчас ведёт</i><b>'+L.sym+'</b><s>'+(L.ended?('конец в '+L.ended):(L.state||''))+
      ' · '+(L.line||'')+(L.hours?(' · '+L.hours+' ч в первых'):'')+'</s>'+
      ((L.runs_weak||0)>0&&!L.ended
        ? (Math.abs(L.run_pct||0)>=150
            ? '<u class="hot">ход '+Math.round(L.run_pct)+'% за день · интерес падает · '+L.runs_weak+' прогон без роста</u>'
            : '<u class="warn">ход '+Math.round(L.run_pct||0)+'% за день · '+L.runs_weak+' из 3 прогонов без роста интереса</u>')
        : ((L.lead_gap||0)>=5 ? '<u>тянет одна · в '+L.lead_gap.toFixed(0)+' раз выше медианы наших · вход в остальных закрыт</u>' : ''));
  } else if(el){ el.style.display='none'; }
  // ЛИДЕР ВСЕГДА ЗАМЕТНЕЕ ОСТАЛЬНЫХ (08.09, владелец: «NAORIS в лидерах, а светится всё, и
  // некоторые ярче»): раньше подсветка включалась только пока лидер идёт, а при конце снималась
  // целиком — и на экране оставались чужие звёзды ярче лидера. Теперь три уровня:
  //   тянет одна — лидер 1.9, остальные треть своей яркости;
  //   идёт обычно — 1.45 и половина;
  //   конец пришёл — 1.25 и три четверти: лидер всё ещё виден, но поле не гасится.
  // ЛИДЕР — ТОЛЬКО ПРИ ХОДЕ ОТ 50% ЗА ДЕНЬ (08.09, владелец: «первая монета в очереди не должна
  // гореть ярче всех, если она не дала за день больше 50%; частота попадания в первые ни на что не
  // влияет — NAORIS висел почти 12 ч в первых и не пошёл»). Раньше лидером считался тот, у кого
  // наибольший суточный ход, и NAORIS с +7% полдня держал панель и затмевал остальных.
  const idx=(Math.abs(L.run_pct||0)>=50) ? DATA.names.indexOf(L.sym||'') : -1;
  const FL=new Set(DATA.flicker||[]);
  if(idx>=0){
    const hard=(L.lead_gap||0)>=5 && !L.ended;
    const done=!!L.ended || (L.runs_weak||0)>=3;
    const up = done?1.25:(hard?1.9:1.45);
    const dn = done?0.75:(hard?0.30:0.55);
    const b=new Float32Array(DATA.bright);
    for(let i=0;i<b.length;i++){
      if(LAB[i])continue;
      b[i]= (i===idx) ? up : b[i]*dn;
      if(FL.has(DATA.names[i])) b[i]*=0.6;
    }
    BR0.set(b); applyGroup();
  }
})();
(function(){const el=document.getElementById('bgnote');if(!el)return;
  const raw=(DATA.bgnote||'').replace(/^фон:\s*/,'');
  if(!raw){el.style.display='none';return}
  el.innerHTML='<i>фон</i>'+raw.split(' · ')
    .map(t=>t.replace(/([\d.,]+(?: из \d+)?%?)/g,'<b>$1</b>')).join('<br>');})();
// ТОЧНОСТЬ ПОД ПЛАНЕТОЙ (07.09): доля сбывшихся из журнала; нет данных — прочерк
(function(){const a=DATA.acc||{};const el=document.getElementById('pnum');
  if(!el)return;
  if(a.ok_pct==null){el.textContent='—';el.title='журнал ещё пуст';return}
  el.innerHTML=a.ok_pct.toFixed(0)+'<s>%</s>';
  el.title=(a.ok||0)+' из '+(a.n||0)+(a.enough?'':' · мало для статистики');})();
// ПОТОК ПО ДОСКЕ (07.09): день — число и сторона, бар — ранний разворот
(function(){const TK=DATA.taker||{};const f=document.getElementById('flow');
  if(!TK.day){f.style.display='none';return}
  const pos=v=>50+Math.max(-1,Math.min(1,(v-1)/0.2))*34;
  const p=pos(TK.day);
  document.getElementById('bead').style.left=p+'%';
  const val=document.getElementById('fval');
  val.style.left=p+'%';
  val.innerHTML=TK.day.toFixed(2)+'<s>'+(TK.side||'')+'</s>';
  f.classList.add(TK.day>1.02?'buy':TK.day<0.98?'sell':'flat');
  // засечка бара: где поток сейчас, если он разошёлся с днём
  if(TK.bar){const m=document.getElementById('fmark');
    m.style.left=pos(TK.bar)+'%';
    if((TK.day>1&&TK.bar<0.98)||(TK.day<1&&TK.bar>1.02))m.classList.add('on');}
})();
// планета → журнал прогнозов (07.09): в оболочке шлём ob:open, отдельной страницей — переход по ссылке
document.getElementById('planet').addEventListener('click',ev=>{ev.stopPropagation();
  if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'accuracy'},'*')}catch(e){}}
  location.href='accuracy.html';});
addEventListener('keydown',ev=>{
  if(PICK!==null&&(ev.key==='Escape')){PICK=null;applyGroup();return}
  if(ev.key==='Escape'||ev.key===' '||ev.key==='Enter'||ev.key==='ArrowRight')next()});
// шрифты (06.09): ждём оба — Michroma для имён и Inter для подписей; сеть молчит — стартуем
// через полторы секунды на системном, чтобы не было пустого экрана и «script error» при первом заходе
const ready=document.fonts?Promise.race([
  Promise.all([document.fonts.load(`400 40px "${FONT}"`),document.fonts.load(`300 40px "Inter"`)]).catch(()=>{}),
  new Promise(r=>setTimeout(r,1500))]):Promise.resolve();
let started=false;
ready.then(()=>{if(started)return;started=true;try{resize();requestAnimationFrame(loop)}catch(e){console.error('интро:',e)}});
</script>
</body>
</html>
'''
