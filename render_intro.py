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
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core_time import row_dt

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
        rows.sort(key=lambda r: row_dt(r) or datetime.min.replace(tzinfo=timezone.utc))
        by: dict = {}
        last_goal: dict = {}     # последнее «у цели» по монете: имя и время постановки серии
        for r in rows:
            sym = str(r.get("sym") or "").upper()
            if not sym:
                continue
            nm = str(r.get("tpl") or "").split("(")[0].strip().lower()
            full = str(r.get("tpl") or "").strip().lower()
            _d = row_dt(r)                  # UTC; строка без пометки tz — время неизвестно, пропуск (16.09)
            if _d is None:
                continue
            t = _d.strftime("%Y-%m-%d %H:%M")
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
                mark = f"⟦t:{int(d0.timestamp())}⟧"     # местное время подставит страница
            except ValueError:
                hrs, mark = 0.0, t_out[5:16]
            out[sym] = (nm_out, round(hrs, 1), mark)
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
        _t0 = datetime.min.replace(tzinfo=timezone.utc)
        rows.sort(key=lambda r: row_dt(r) or _t0)
        for r in rows:
            s = str(r.get("sym") or "").upper()
            if s:
                out[s] = str(r.get("tpl") or "").split("(")[0].strip().lower()
        break
    return out


def _many_lead() -> dict | None:
    """МНОГО ЛИДЕРОВ — ОГРАНИЧЕНИЯ СНЯТЫ (16.09, владелец: на доске SYN +126%, BR +121%, LSK +48%, а экран
    писал «тянет одна · вход в остальных закрыт» и ноль в очереди). Состояние считает near_move
    (MANY_LEADERS_* в core_config: ход за сутки, оборот, квант и листинг — те же отсекатели, что у
    памп-лидеров), здесь только читаем и проверяем срок: снято до начала следующей сессии минус час."""
    from datetime import datetime, timezone
    for _p in (BASE_DIR / "output" / "near_move.json", BASE_DIR / "near_move.json"):
        try:
            _ml = (json.loads(_p.read_text(encoding="utf-8")) or {}).get("many_lead")
        except (OSError, ValueError):
            continue
        if not _ml or not _ml.get("until"):
            return None
        if datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") < str(_ml["until"]):
            return _ml
        return None
    return None


def _sess_pickup_all() -> dict:
    """ВТОРОЙ ПРИЗНАК ЗВЁЗД (19.09, владелец: «яркость и появление тоже регулируй по второму признаку»):
    первый час-полтора после открытия сессии — оборот к норме ЭТОЙ сессии и приход плеча. Разбор ночи
    18–19.09: у ONE ×25 и у SYN ×61 оборота в первый час Сиднея, у остальных семи звёзд — до ×5; пошли
    ONE и SYN. Считается по архиву получасовок для всех монет: {SYMUSDT: {volx, oi, delta, px, bars, sess}}.
    Пороги — STAR_SESS_* в core_config."""
    from datetime import datetime, timezone
    import statistics as _st
    d = BASE_DIR / "cq_v2" / "intraday"
    if not d.exists():
        return {}
    OPENS = ((21, "Сидней"), (0, "Токио"), (7, "Лондон"), (13, "Нью-Йорк"))
    out: dict = {}
    for p in d.glob("*.jsonl"):
        try:
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
        except OSError:
            continue
        rows = []
        for ln in lines:
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            if r.get("px") and r.get("candle"):
                try:
                    r["_t"] = int(datetime.fromisoformat(str(r["candle"]).replace("Z", "+00:00")).timestamp() * 1000)
                except ValueError:
                    continue
                rows.append(r)
        if len(rows) < 30:
            continue
        rows.sort(key=lambda r: r["_t"])
        qv = lambda r: float((r.get("kv") or {}).get("qv") or 0)
        # последнее открытие, у которого закрыт хотя бы бар открытия
        opens = []
        for r in rows[-96:]:
            h = datetime.fromtimestamp(r["_t"] / 1000, timezone.utc)
            for oh, nm in OPENS:
                if h.hour == oh and h.minute == 0:
                    opens.append((r["_t"], nm))
        if not opens:
            continue
        t0, name = opens[-1]
        idx = {r["_t"]: i for i, r in enumerate(rows)}
        i0 = idx.get(t0)
        if i0 is None:
            continue
        h0 = next(oh for oh, nm in OPENS if nm == name)
        norm_bars = [qv(r) for r in rows[-336:] if qv(r) > 0
                     and (datetime.fromtimestamp(r["_t"] / 1000, timezone.utc).hour - h0) % 24 < 9]
        nrm = _st.median(norm_bars) if norm_bars else 0
        seg = rows[i0:i0 + 3]
        vol = sum(qv(r) for r in seg)
        volx = (vol / (nrm * len(seg))) if (nrm and seg) else None
        oi_a = next((float(r["oi"]) for r in reversed(rows[max(0, i0 - 2):i0]) if r.get("oi")), None)
        oi_b = next((float(r["oi"]) for r in reversed(seg) if r.get("oi")), None)
        oich = ((oi_b / oi_a - 1) * 100) if (oi_a and oi_b) else None
        dl = [(r.get("fut") or {}).get("d") for r in seg]
        dl = None if any(x is None for x in dl) else sum(float(x) for x in dl)
        px0 = float(rows[i0 - 1]["px"]) if i0 else float(seg[0]["px"])
        pxch = (float(seg[-1]["px"]) / px0 - 1) * 100 if px0 else None
        out[p.stem.upper() + "USDT"] = {"volx": volx, "oi": oich, "delta": dl, "px": pxch, "bars": len(seg), "sess": name}
    return out


def _book_count() -> int:
    """Сколько позиций у бота сейчас — для подписи-перехода «книга N» (16.09). Считаем открытые во всех
    бумажных книгах: paper_end, paper_crowd, paper_fast (у последнего позиция может быть в хедже)."""
    n = 0
    for _nm in ("paper_end.json", "paper_crowd.json", "paper_fast.json", "paper_bottom.json", "paper_sight.json",
                "paper_first3.json"):
        for _p in (BASE_DIR / "output" / _nm, BASE_DIR / _nm):
            try:
                _d = json.loads(_p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            n += len((_d or {}).get("open") or {})
            break
    return n


try:
    from core_config import LEADER_STARS_MEDIAN_MIN, LEADER_STARS_MIN_UP
except ImportError:
    LEADER_STARS_MEDIAN_MIN, LEADER_STARS_MIN_UP = 0.0, 60


def _board_now() -> dict | None:
    """Доска сейчас из последней строки фона (market_bg): медиана хода за сутки и сколько монет растёт.
    Нет строки — None: тогда при лидере звёзды гаснут, как раньше."""
    try:
        from market_bg import last_row
        _ro = (last_row() or {}).get("risk_on") or {}
    except Exception:  # noqa: BLE001
        return None
    if _ro.get("median_pct") is None:
        return None
    return {"median": float(_ro["median_pct"]), "up": int(_ro.get("green") or 0), "n": int(_ro.get("n") or 0)}


def _pump_lead() -> dict | None:
    """Живой лидер по пампу с наибольшим ходом — из pump_leaders.json, ничего не считая."""
    try:
        from core_config import PUMP_LEADERS_PATH as _pl
    except ImportError:
        _pl = BASE_DIR / "output" / "pump_leaders.json"
    try:
        _recs = json.loads(Path(_pl).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    _live = [r for r in (_recs.values() if isinstance(_recs, dict) else _recs)
             if isinstance(r, dict) and r.get("symbol") and not r.get("retired_at")]
    if not _live:
        return None
    _live.sort(key=lambda r: -(r.get("run_pct") or 0))
    _live = _queue_first_first(_live)
    _l = _live[0]
    return {"sym": str(_l["symbol"]), "run_pct": float(_l.get("run_pct") or 0), "mine": bool(_l.get("mine"))}


def _queue_first_first(live: list) -> list:
    # ОТКЛЮЧЕНО (18.09, владелец: ARB с +20% в плашке «ведёт» — «в смысле всё ок?»): первое место очереди по баллу —
    # не лидер; плашка — про сильнейшего из живых лидеров журнала, как и было
    return live
    """ЛИДЕР — ПЕРВЫЙ В ОЧЕРЕДИ (18.09, владелец: «лидер просто тот, кто сейчас первый в очереди, и прогнозы про
    него»): запись первого в очереди ставится первой; если у него нет записи в журнале лидеров — собирается из сводки"""
    try:
        _nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8")) or {}
        _first = str(((_nm.get("first") or [None])[0]) or "").upper()
    except (OSError, ValueError):
        return live
    if not _first:
        return live
    hit = [r for r in live if str(r.get("symbol") or "").upper() == _first]
    rest = [r for r in live if str(r.get("symbol") or "").upper() != _first]
    if hit:
        return hit + rest
    _c = ((_nm.get("coins") or {}).get(_first) or {})
    _mv = ((_c.get("today") or {}).get("px_chg_pct")) if isinstance(_c, dict) else None
    return [{"symbol": _first, "run_pct": float(_mv or 0), "day_pct": _mv, "mine": bool(_c.get("mine")) if isinstance(_c, dict) else False}] + live


_QH: dict = {}   # история очереди за сутки для рисования: sym → 48 получасов (1 — была первой)
_QS: dict = {}   # sym → прогонов подряд первой до «сейчас»
_QT: dict = {}   # sym → метки «первая N подряд» / «первая N раз за сутки»


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
    # ПЕРВЫЕ — ТОЛЬКО С ТРЕТЬЕГО ПРОГОНА ПОДРЯД (12.09, владелец): near_move отдаёт first уже с этим
    # правилом; кто в верхних строках, но серия короче, — в «очереди», с подписью «первой N прогонов»
    _nm = nm
    _first = set(nm.get("first") or queue[:3])
    _streak = nm.get("first_streak") or {}
    for i, sym in enumerate(queue):
        v = coins.get(sym) or {}
        sc = float((v.get("queue") or {}).get("score") or 0)
        _st = _streak.get(sym)
        _sub = hist_line(v)
        # ДВЕ ЗВЕЗДЫ — ДВЕ ПРИЧИНЫ (12.09, владелец): near_move пишет first_why — «держится N-й
        # прогон» и/или «приток плеча +N%». Показываем причину как есть, не домысливая.
        _why_first = (_nm.get("first_why") or {}).get(sym)
        if sym in _first and _why_first:
            _sub = _why_first + (" · " + _sub if _sub else "")
        elif i < 3 and _st:
            _sub = f"в первых {_st}-й прогон, нужно 3" + (" · " + _sub if _sub else "")
        add(sym, 0 if sym in _first else 1, " · ".join(v.get("why") or []), _sub, sc)
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

    # ПУЗЫРЬ У ДНА (17.09, владелец: ENA — «пузырь в карте сильный и много за, но ни в звёздах, нигде нет
    # ничего»). Бот paper_bottom пишет живые сигналы прогона и свои открытые позиции; сигнал — звезда «брать»
    # с подписью «пузырь у дна», позиция без свежего сигнала — «держать». Только монеты сводки: остальные
    # части экрана берут данные из near_move. Лидер «тянет одна» ниже всё равно гасит остальные звёзды.
    try:
        _pbm = json.loads((BASE_DIR / "output" / "paper_bottom.json").read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        _pbm = {}
    for _sg in (_pbm.get("signals") or []):
        _s = str(_sg.get("sym") or "")
        if _s in coins:
            add(_s, 0, f"пузырь у дна · {_sg.get('why') or ''} · от дна {float(_sg.get('dist_now_pct') or 0):+.1f}%",
                "пузырь у дна", 5.0)
    for _s, _pp in (_pbm.get("open") or {}).items():
        if _s in coins:
            add(_s, 1, f"держать · лонг от дна {float(_pp.get('px') or 0):.6g} · выход — рука ушла", "дно · в работе", 3.0)
    # КОНЕЦ ТРЕНДА (07.09): монеты, выпавшие из очереди — интерес ушёл вместе с ценой на одном
    # баре, — не исчезают, а становятся «у цели · конец тренда»: вход закрыт, для позиции — выход
    for sym, v in coins.items():
        if (v.get("today") or {}).get("leaving_kind") == "конец":
            add(sym, 2, " · ".join(v.get("why") or []) + " · интерес ушёл вместе с ценой — выход, не хедж", "выход 100%")
    # ЛИДЕР — ОДНА ЗВЕЗДА (12.09, владелец: «должен показываться один лидер, а его даже нет, и есть
    # все звёзды»). Лидер из pump_leaders (та же мерка, что везде) становится звездой всегда, даже
    # если очередь его не держит — LAB +65% в очередь не попадал и звезды не имел. Пока он тянет,
    # очередь гаснет: «если тянет одна, остальное будет во флэте или падать». Гаснут ВСЕ, включая
    # «у цели» (правка 12.09, см. ниже): при лидере это не цель, а отток денег в него.
    _many = _many_lead()
    _lead = _pump_lead()
    if _lead and (_lead["sym"] in coins or _lead.get("mine")):
        _ls = _lead["sym"]
        _why = (f"ведёт · +{_lead['run_pct']:.0f}% от основы · тянет одна — вход в остальных закрыт, "
                f"открытые хеджировать")
        _hit = next((it for it in items if it["sym"] == _ls), None)
        if _hit:
            _hit.update({"g": 0, "why": _why, "sub": "лидер · " + str(_hit.get("sub") or ""), "rel": 1e9})
        else:
            add(_ls, 0, _why, "лидер", 1e9)
        # ПРИ ЛИДЕРЕ НА ЭКРАНЕ ОДНА ЗВЕЗДА (12.09, владелец: «убери все звёзды, ты оставил „у цели“,
        # хотя они не у цели — просто деньги из них перетекают в лидера, потом могут вернуться, а
        # позиция уже закрыта»). Проверено в тот же день: за часы набора LSK интерес LAB упал
        # 63.6M→49.9M, RIVER 29.6M→24.8M — из них вынули ~19M, а LSK набрала +44M; как только LSK
        # откатила, RIVER тут же отскочил. «У цели» в этот момент означает не цель, а отток —
        # закрывать по нему позицию нельзя, правильное действие одно: хеджировать.
        # СНЯТИЕ ПРИ МНОГИХ ЛИДЕРАХ (16.09): когда за сутки две и больше монет дали от 40% при обороте
        # от 10M — это не «тянет одна», а заход денег; очередь не гасим, у лидера остаётся только его
        # подпись. Держится до начала следующей сессии минус час (срок считает near_move).
        if _many:
            _txt = str(_many.get("why") or "")
            if _hit:
                _hit["why"] = f"ведёт · +{_lead['run_pct']:.0f}% от основы · {_txt}"
            else:
                items[-1]["why"] = f"ведёт · +{_lead['run_pct']:.0f}% от основы · {_txt}"
        else:
            # ЗВЁЗДЫ ПРИ ЛИДЕРЕ, ЕСЛИ ДОСКА ЗЕЛЁНАЯ (17.09, владелец: «показывать звёзды в случае лидера, если
            # медиана доски положительная или идёт больше 60 монет; надпись „не входить“ оставляем»). Когда лидер
            # тянет один при красной доске — деньги уходят в него, звёзды гаснут (12.09). Когда доска при лидере
            # растёт — деньги идут не только в него: звёзды видны, но подпись лидера про закрытый вход остаётся.
            _bg = _board_now()
            if _bg and ((_bg["median"] or 0) > LEADER_STARS_MEDIAN_MIN or (_bg["up"] or 0) >= LEADER_STARS_MIN_UP):
                for it in items:
                    if it["sym"] != _ls:
                        it["sub"] = "при лидере · " + str(it.get("sub") or "")
                _note = (f"доска растёт: медиана {_bg['median']:+.2f}% · растёт {_bg['up']} из {_bg['n']}")
                if _hit:
                    _hit["why"] += f" · звёзды видны — {_note}"
                else:
                    items[-1]["why"] += f" · звёзды видны — {_note}"
            else:
                items[:] = [it for it in items if it["sym"] == _ls]
    # ТОЛЬКО ПРОФИЛЬ ЛИДЕРА (17.09, владелец: «показывай только такие звёзды, убираем очередь и прочую фигню,
    # снимаем ограничения про одного лидера, медиану и вообще всё»). Всё, что собрано выше — очередь, «у цели»,
    # конец, лидер, дно, — заменяется звёздами analytics_profile: лидеры дня с отметками профиля от
    # PROFILE_MIN_MARKS. Группа 0 — все семь или шесть, группа 1 — пять; яркость — по числу отметок.
    try:
        import analytics_profile as _ap
        _stars = _ap.stars()
        items[:] = []
        seen.clear()
        for _x in _stars:
            _sym = _x["sym"]
            _v = coins.get(_sym) or {}
            # ПОДПИСЬ И ВСПЛЫВАШКА — КАК У ОЧЕРЕДИ (18.09, владелец: «нужны отметки, которые были, вроде „Лондон
            # поддержал“, пузыри на звезде, кометы, всплывашка — всё оставляем»): причины из сводки, hist_line, first_why;
            # ход от основания — одной короткой фразой в конце причин. Пузыри, кометы, орбиты вешаются ниже по sym.
            _why = " · ".join(_v.get("why") or [])
            _run = f"звезда: +{_x['run']:.0f}% от основания, от вершины −{_x['dd']:.0f}%"
            _why = (_why + " · " if _why else "") + _run
            _sub = hist_line(_v)
            _why_first = (_nm.get("first_why") or {}).get(_sym)
            if _why_first:
                _sub = _why_first + (" · " + _sub if _sub else "")
            add(_sym, 0, _why, _sub, float(_x["run"]) + (100.0 if _x.get("led") else 0.0))
            items[-1]["run"], items[-1]["dd"] = float(_x.get("run") or 0), float(_x.get("dd") or 0)
    except Exception as _e:  # noqa: BLE001
        print(f"профиль лидера не собрался: {type(_e).__name__}: {_e}", file=sys.stderr)
    # ВТОРОЙ ПРИЗНАК — СТЫК СЕССИИ (19.09, владелец): яркость и появление регулируются дополнительно по
    # первому часу сессии — оборот к норме этой сессии и приход плеча. Появление: монета не звезда по ходу,
    # но на стыке оборот от STAR_SESS_VOL_X норм и плечо от STAR_SESS_OI_PCT при цене вверх — загорается с
    # подписью «подхват стыка». Яркость: место в очереди первым ключом (ONE 18.09 стояла первой в очереди с
    # 14:10, а звездой была второй-третьей — экран показывал, кто уже прошёл, а не кто пойдёт), стык вторым,
    # ход от основания третьим. Правило, КТО горит по ходу, не тронуто.
    try:
        from core_config import STAR_SESS_VOL_X, STAR_SESS_OI_PCT
    except ImportError:
        STAR_SESS_VOL_X, STAR_SESS_OI_PCT = 5.0, 3.0
    _pick = _sess_pickup_all()
    _qpos = {sym: i + 1 for i, sym in enumerate(nm.get("queue") or [])}
    try:
        from core_config import STAR_DIM
    except ImportError:
        STAR_DIM = 0.22           # яркость звезды без места в очереди и без подхвата стыка
    for _sym, _pk in _pick.items():
        if _sym in seen or _sym not in coins:
            continue
        if (_pk.get("volx") or 0) >= STAR_SESS_VOL_X and (_pk.get("oi") or 0) >= STAR_SESS_OI_PCT and (_pk.get("px") or 0) > 0:
            _v = coins.get(_sym) or {}
            _why = " · ".join(_v.get("why") or [])
            _line = (f"подхват стыка {_pk['sess']}: оборот ×{_pk['volx']:.0f} к норме · плечо {_pk['oi']:+.1f}%"
                     + (f" · дельта {_pk['delta'] / 1e3:+.0f}K" if _pk.get("delta") is not None else "") + f" · цена {_pk['px']:+.1f}% по {_pk['bars']} бар."
                     )
            add(_sym, 0, (_why + " · " if _why else "") + _line + " · ступени ещё нет — не вход", "подхват стыка · ступени ещё нет — не вход · " + hist_line(_v), 0.0)
    # ТРИ КАТЕГОРИИ (19.09, владелец: «нужно разделить на 3 категории — которые скоро пойдут, которые могут пойти,
    # которые пошли, но не отдали 60% от пика»). Группа 2 — ПОШЛИ: ход от основания ≥ PROFILE_RUN_MIN (нынешнее
    # правило звёзд, откат <60% от вершины). Группа 0 — СКОРО: ещё не прошли, но оба ключа сразу — первая тройка
    # очереди И подхват стыка. Группа 1 — МОГУТ: один ключ из двух, либо копится по классу владельца — сбор за три дня
    # и плечо не ушло. Кто не попал никуда — с экрана уходит («экран показывает, кто уже прошёл, а не кто пойдёт»).
    try:
        from analytics_profile import PROFILE_RUN_MIN as _RUN_MIN
    except ImportError:
        _RUN_MIN = 60.0
    try:
        from core_config import STAR_QUEUE_TOP
    except ImportError:
        STAR_QUEUE_TOP = 3          # место в очереди, которое считается ключом (лаборатория лидеров: только тройка)
    _streak = nm.get("first_streak") or {}      # сколько прогонов подряд монета держится в первых (near_move)
    def _qtag(sym, _q):
        """подпись места: первой — со счётом прогонов подряд (19.09, владелец: «AKE вчера был почти весь день и ONE тоже»)"""
        if not _q:
            return "очереди нет"
        _n = int(_streak.get(sym) or 0)
        if _q == 1:
            return "ПЕРВАЯ" + (f" · в первых {_n} пр. подряд" if _n else "")
        return f"очередь {_q}-я" + (f" · в первых {_n} пр." if _n else "")
    def _keys(sym):
        _pk = _pick.get(sym) or {}
        _q = _qpos.get(sym)
        k_q = bool(_q and _q <= STAR_QUEUE_TOP)
        k_s = bool((_pk.get("volx") or 0) >= STAR_SESS_VOL_X and (_pk.get("oi") or 0) >= STAR_SESS_OI_PCT and (_pk.get("px") or 0) > 0)
        _nums = (coins.get(sym) or {}).get("nums") or {}
        _hd = str(_nums.get("harvest_day") or "")
        k_c = False
        if _hd:
            try:
                k_c = (datetime.now(timezone.utc).date() - datetime.strptime(_hd, "%Y-%m-%d").date()).days <= 3 \
                      and float(_nums.get("oi_grow") or 0) >= 1.0
            except ValueError:
                k_c = False
        return k_q, k_s, k_c, _q, _pk
    for it in list(items):
        k_q, k_s, k_c, _q, _pk = _keys(it["sym"])
        went = float(it.get("run") or 0) >= _RUN_MIN
        if went and k_q and k_s:
            it["g"] = 0                                  # ВТОРОЙ АКТ (19.09): ход был, и деньги идут снова — в центр
            it["why"] = "второй акт: ход был, и деньги идут снова — в первой тройке очереди и стык подхвачен · " + str(it.get("why") or "")
        elif went:
            it["g"] = 2
        elif k_q and k_s:
            it["g"] = 0
        elif k_q or k_s or k_c:
            it["g"] = 1
        else:
            items.remove(it); continue
        # ПОДПИСЬ ГРУППАМИ (19.09, владелец: «надо в звезде как-то разделять эту простыню, всё сливается»): статус ‖
        # очередь ‖ стык ‖ сбор ‖ режим — всплывашка рисует каждую группу своей строкой с подписью слева.
        _run = float(it.get("run") or 0)
        if not went:
            _st = f"ход от основания +{_run:.0f}% · ступени ещё нет — не вход"     # НЕ «БРАТЬ» (19.09)
        elif it["g"] == 0:
            _st = f"ВТОРОЙ АКТ · ход +{_run:.0f}% · снова в первой тройке очереди и стык подхвачен"
        else:
            _st = f"пошла · ход +{_run:.0f}% · от вершины {float(it.get('dd') or 0):+.0f}%"
        _sx = ("подхвачен" if k_s else "не подхвачен") + (f" · оборот ×{_pk.get('volx', 0):.0f}" if _pk.get("volx") is not None else "") + (f" · плечо {_pk.get('oi', 0):+.0f}%" if _pk.get("oi") is not None else "")
        _old = [x for x in str(it.get("sub") or "").split(" · ") if x and not x.startswith("стык")]
        _mode = [x for x in _old if x in ("лестница", "парабола", "сквиз") or x.startswith("режим")]
        _rest = [x[5:] if x.startswith("сбор ") else x for x in _old
                 if x not in _mode and not x.startswith("держится") and x not in ("подхват стыка", "ступени ещё нет — не вход")]
        _qt = _qtag(it["sym"], _q if k_q else None)
        _qt = _qt[8:] if _qt.startswith("очередь ") else _qt
        it["sub"] = " ‖ ".join([_st, "очередь: " + _qt,
                                "стык: " + _sx,
                                "сбор: " + (" · ".join(_rest) + (" · копится" if k_c else "") if (_rest or k_c) else "—"),
                                "режим: " + (" · ".join(_mode) if _mode else "—")])
    # первая тройка очереди без звезды — «могут пойти», если есть хотя бы один ключ
    for _sym, _q in _qpos.items():
        if _q > STAR_QUEUE_TOP or _sym in {it["sym"] for it in items} or _sym not in coins:
            continue
        k_q, k_s, k_c, _q2, _pk = _keys(_sym)
        _v = coins.get(_sym) or {}
        _why = " · ".join(_v.get("why") or []) or "в первой тройке очереди"
        add(_sym, 0 if k_s else 1, _why + " · " + _qtag(_sym, _q) + (" · стык подхвачен" if k_s else " · стык не подхвачен") + " · ступени ещё нет — не вход",
            ("ступени ещё нет — не вход · " + _qtag(_sym, _q) + " · " + ("стык подхвачен" if k_s else "стык не подхвачен") + " · " + hist_line(_v)).strip(" ·"), 0.0)
    # ИСТОРИЯ ОЧЕРЕДИ ЗА СУТКИ (24.09, владелец): два ДОБАВОЧНЫХ повода попасть в «скоро» — сверх «тройка очереди
    # И стык», ничего не отменяют: (1) первая в очереди STAR_FIRST_STREAK прогонов подряд и больше — показ на третьем
    # подряд, то есть два прогона она уже была первой; (2) первая больше STAR_FIRST_DAY раз за сутки, не обязательно
    # подряд. Могут совпасть — тогда обе метки. Вокруг звезды рисуются сутки по кругу (48 получасов): янтарная риска —
    # была первой, мятная нить до засечки «сейчас» — серия подряд. Считается по output/queue_log.jsonl.
    try:
        from core_config import STAR_FIRST_STREAK, STAR_FIRST_DAY
    except ImportError:
        STAR_FIRST_STREAK, STAR_FIRST_DAY = 3, 10
    try:
        from core_config import STAR_TOP_STREAK, STAR_TOP_N
    except ImportError:
        STAR_TOP_STREAK, STAR_TOP_N = 3, 3
    _top_h: dict = {}                                              # sym → 48 получасов (1 — была в топе)
    _top_s: dict = {}                                              # sym → прогонов подряд в топе до «сейчас»
    _QH.clear(); _QS.clear(); _QT.clear()
    try:
        _now = datetime.now(timezone.utc)
        _since = _now - timedelta(hours=24)
        _slots: dict = {}                                          # номер получаса → кто был первым (для рисунка)
        _runs: dict = {}                                           # прогон → {монета: место}
        for _line in (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines()[-9000:]:
            try:
                _r = json.loads(_line)
            except ValueError:
                continue
            if not _r.get("sym") or not _r.get("at"):
                continue
            _t = datetime.fromisoformat(str(_r["at"]).replace("Z", "+00:00"))
            if _t < _since:
                continue
            _run = _runs.setdefault(str(_r["at"]), {})
            _pl = _r.get("place")
            if not isinstance(_pl, int) or _pl > STAR_TOP_N:
                continue
            _run[str(_r["sym"]).upper()] = _pl
            if _pl == 1:
                _k = min(47, int((_t - _since).total_seconds() // 1800))
                _slots.setdefault(_k, set()).add(str(_r["sym"]).upper())
        for _k, _ss in _slots.items():
            for _s in _ss:
                _QH.setdefault(_s, [0] * 48)[_k] = 1
        # СЕРИЯ — ПО ПРОГОНАМ, НЕ ПО ПОЛУЧАСОВЫМ ЯЧЕЙКАМ (25.09): прогоны идут неровно (01:10, 01:55, 02:11) — одна
        # ячейка пустеет, две сливаются, и серия рвалась: у NIL шесть прогонов подряд в топе, а метки не было.
        # 25.09, владелец: первая подряд — только ПЕРВОЕ место, как у бота «3 в первых подряд». Раньше у нынешней
        # первой бралось большее с first_streak из near_move (первые ТРИ места и серия лидера дальше): у PLAY выходило
        # «первая 13 подряд» при четырёх прогонах на первом месте.
        _order = sorted(_runs, reverse=True)

        def _run_streak(_s: str, _top: bool) -> int:
            _n = 0
            for _a in _order:
                _pl = _runs[_a].get(_s)
                if _pl is not None and (_top or _pl == 1):
                    _n += 1
                else:
                    break
            return _n
        for _s in {x for _run in _runs.values() for x in _run}:
            if _s in _QH:
                _QS[_s] = _run_streak(_s, False)
            _top_s[_s] = _run_streak(_s, True)
    except (OSError, ValueError):
        pass
    # В ТОПЕ ПОДРЯД (25.09, владелец: «PLAY пошла гораздо раньше, чем попала три раза в первые, — была три раза во
    # втором или больше»): третий повод — монета в первых STAR_TOP_N местах очереди STAR_TOP_STREAK получасовок подряд
    # и больше, метка «в топе N подряд». Первая подряд важнее и заменяет её. Рисунок вокруг звезды прежний.
    for _s in list(dict.fromkeys(list(_QH) + list(_top_s))):
        _h = _QH.get(_s) or [0] * 48
        _n24, _nst, _ntop = sum(_h), int(_QS.get(_s) or 0), int(_top_s.get(_s) or 0)
        _tags = ([f"первая {_nst} подряд"] if _nst >= STAR_FIRST_STREAK else
                 [f"в топе {_ntop} подряд"] if _ntop >= STAR_TOP_STREAK else []) + \
                ([f"первая {_n24} раз за сутки"] if _n24 > STAR_FIRST_DAY else [])
        if not _tags:
            continue
        _QT[_s] = _tags
        _it = next((x for x in items if x["sym"] == _s), None)
        if _it is None:
            if _s not in coins:
                continue
            _v = coins.get(_s) or {}
            add(_s, 0, " · ".join(_tags + list(_v.get("why") or [])), "", 0.0)
            _it = items[-1]
            _it["sub"] = " ‖ ".join([" · ".join(_tags), "очередь: " + _qtag(_s, _qpos.get(_s)).replace("очередь ", ""),
                                     "стык: —", "сбор: " + (hist_line(_v) or "—"), "режим: —"])
        else:
            _it["g"] = 0
            _sub = str(_it.get("sub") or "")
            if "‖" in _sub:
                _G = _sub.split(" ‖ ")
                _G[0] = " · ".join(_tags) + " · " + _G[0]
                _it["sub"] = " ‖ ".join(_G)
            else:
                _it["sub"] = " · ".join(_tags) + (" · " + _sub if _sub else "")
    for it in items:
        _pk = _pick.get(it["sym"]) or {}
        _q = _qpos.get(it["sym"])
        _sess = (max(0.0, min(50.0, float(_pk.get("volx") or 0))) + max(0.0, float(_pk.get("oi") or 0))) if _pk else 0.0
        it["rel"] = (400.0 if _q == 1 else 300.0 if _q == 2 else 200.0 if _q == 3 else 100.0 if _q else 0.0) + _sess + float(it.get("rel") or 0.0) / 10.0
        if _pk and _pk.get("volx") is not None and "‖" not in str(it.get("sub") or ""):
            it["sub"] = (it.get("sub") or "") + f" · стык: оборот ×{_pk['volx']:.0f}" + (f" · плечо {_pk['oi']:+.0f}%" if _pk.get("oi") is not None else "")
    # порядок: брать, держать, у цели; внутри группы — по надёжности, самая надёжная первой
    items.sort(key=lambda it: (it["g"], -it.get("rel", 0.0)))
    # яркость внутри группы: лучшая — 1.0, остальные вниз до 0.45; «у цели» — ровно 0.7
    for g in (0, 1, 2):
        grp = [it for it in items if it["g"] == g]
        if not grp:
            continue
        # ЯРКОСТЬ ПО ДВУМ КЛЮЧАМ (19.09, владелец: «как было 9, так и осталось» — прежний пол 45% делал всех
        # почти одинаковыми). Звезда без места в очереди и без подхвата стыка — тусклая (пол STAR_DIM); первое место
        # в очереди или живой стык — в полную силу; между ними — по rel.
        hi_r, lo_r = max(it["rel"] for it in grp), min(it["rel"] for it in grp)
        for it in grp:
            _key = (it["rel"] >= 100.0) or ((_pick.get(it["sym"]) or {}).get("volx", 0) >= STAR_SESS_VOL_X)
            if not _key:
                it["bright"] = STAR_DIM
            else:
                it["bright"] = 1.0 if hi_r <= lo_r else STAR_DIM + (1.0 - STAR_DIM) * (it["rel"] - lo_r) / (hi_r - lo_r)
    for it in items:
        if it["g"] == 2:
            it["bright"] = min(0.85, float(it.get("bright") or STAR_DIM))   # «пошли» светят по ключам, но не ярче «скоро»
        elif it["g"] == 4:
            it["bright"] = 0.4
    # ЗВЁЗДЫ — В ФАЙЛ ДЛЯ ТЕЛЕГРАМА (19.09, владелец: «в телеграм оставляем биткоин и информацию по звёздам, скоро и
    # могут»): тот же список, что на экране, — группа, подпись группами, доводы. Сбой записи экран не роняет.
    try:
        import json as _json
        _out = [{"sym": it["sym"], "name": it.get("n") or it["sym"].replace("USDT", ""), "g": it["g"], "sub": it.get("sub") or "",
                 "why": it.get("why") or "", "run": it.get("run"), "dd": it.get("dd")} for it in items[:MAX_NAMES] if it.get("sym")]
        _txt = _json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "stars": _out}, ensure_ascii=False)
        try:
            from sources_storage import write_atomic as _wa
            _wa(BASE_DIR / "output" / "stars.json", _txt)
        except ImportError:
            (BASE_DIR / "output").mkdir(parents=True, exist_ok=True)
            (BASE_DIR / "output" / "stars.json").write_text(_txt, encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
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
    # ЗВЁЗДЫ НЕ ЛЕЗУТ ПОД ПРИБОРЫ — ИСКЛЮЧЕНИЕМ, А НЕ СУЖЕНИЕМ (09.09, владелец: «теперь стоят
    # сеткой ровно в ряд, это некрасиво»). Сначала я сдвинул левый край зоны с 0.10 на 0.26 —
    # зона стала узкой, точки перестали помещаться, и раскладка свалилась в запасную сетку.
    # Теперь зона снова широкая, а панель вырезана прямоугольником: облако свободное, но левый
    # столбец под приборами пуст.
    x0, y0, x1, y1 = zone or (0.10, 0.13, 0.90, 0.72)
    PANEL = (0.0, 0.16, 0.245, 0.76)      # где стоят приборы фона
    min_d = 0.16 if n <= 8 else 0.13
    while len(pts) < n and tries < 20000:
        tries += 1
        x = x0 + 0.08 * (x1 - x0) + rnd.random() * 0.84 * (x1 - x0)
        y = y0 + 0.10 * (y1 - y0) + rnd.random() * 0.68 * (y1 - y0)
        # вырез под панелью приборов
        if PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]:
            continue
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
        x0 = max(x0, 0.26)          # запасная сетка — правее панели
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
    # ПОДПИСИ ГРУПП — ПО ПРОФИЛЮ (18.09): звёзды с 17.09 только по профилю лидера, «первые» и «в очереди» больше
    # не про очередь: группа 0 — профиль полный (шесть-семь отметок или все известные), группа 1 — на границе (пять)
    labels = [{"n": f"скоро {counts[0]}", "sym": "", "g": 0, "why": "в первой тройке очереди И стык подхвачен (оборот на открытии сессии от пяти норм с приходом плеча) — ещё не прошли 60%", "label": True},
              {"n": f"могут {counts[1]}", "sym": "", "g": 1, "why": "одно из двух: в тройке очереди без стыка, стык без очереди — или копится после сбора", "label": True},
              {"n": f"пошли {counts[2]}", "sym": "", "g": 2, "why": "прошли от основания 60% и больше, от вершины отдали меньше 60% — вход только по лестнице", "label": True}]
    if counts[3]:
        labels.append({"n": f"остывшие {counts[3]}", "sym": "", "g": 4, "why": "", "label": True})
    # переход в книгу — не подписью в ряду, а спутником в левом нижнем углу (16.09, владелец):
    # подпись убрана, чтобы не было двух переходов в одно место
    # раскладка (откат 06.09, владелец: «с зонами некрасиво»): одно облако-созвездие для всех
    # групп, различие — цветом и поведением света; подписи групп — четыре внизу
    # порядок появления (06.09, владелец): подпись группы → её звёзды → следующая → её звёзды
    # ниже и шире (07.09): раньше подписи стояли на одной высоте с потоком и наезжали друг на друга
    # ПЕРЕХОД В КНИГУ (16.09, владелец: «в звёздах это элемент для перехода на экран, а не информация
    # по монетам»): подпись «книга N» в том же нижнем ряду, кликом открывает book.html. Не фильтр
    # группы, как остальные подписи, — поэтому у неё свой признак go и позиция правее «у цели».
    LABPOS = {0: [0.30, 0.945], 1: [0.52, 0.945], 2: [0.74, 0.945], 4: [0.92, 0.945]}
    star_pos = layout(len(items))
    allit: list[dict] = []
    pos: list[list[float]] = []
    k = 0
    stale = [it for it in items if it["g"] == 4]
    # КОЛЬЦА (19.09): группа задаёт расстояние от центра облака — «скоро» в центре, «могут» среднее кольцо,
    # «пошли» край; угол случайный, чтобы не было ряда; вырез под приборами и минимальное расстояние — как были
    def _rings(counts_g: dict, seed: int = 11) -> dict:
        rnd = random.Random(seed + sum(counts_g.values()))
        CX0, CY0, AX = 0.56, 0.44, 1.55           # центр облака и сжатие по вертикали
        BAND = {0: (0.02, 0.11), 1: (0.15, 0.24), 2: (0.27, 0.36)}
        PANEL = (0.0, 0.16, 0.245, 0.76)
        out: dict = {g: [] for g in counts_g}
        placed: list = []
        for g in (0, 1, 2):
            r0, r1 = BAND.get(g, (0.27, 0.36))
            for _k in range(counts_g.get(g, 0)):
                ok = False
                for _try in range(4000):
                    rr = r0 + rnd.random() * (r1 - r0)
                    a = rnd.random() * 2 * math.pi
                    x, y = CX0 + rr * AX * math.cos(a) * 0.62, CY0 + rr * math.sin(a)
                    if not (0.08 <= x <= 0.92 and 0.10 <= y <= 0.78):
                        continue
                    if PANEL[0] <= x <= PANEL[2] and PANEL[1] <= y <= PANEL[3]:
                        continue
                    if all((abs(y - py) >= 0.075) or (abs(x - px) >= 0.17) for px, py in placed) and \
                       all(math.hypot((x - px) * 1.4, y - py) >= 0.12 for px, py in placed):
                        ok = True; break
                if not ok:                                   # не поместилась — чуть дальше от центра, но в своём секторе
                    x, y = CX0 + (r1 + 0.05 * (_k + 1)) * AX * 0.62 * math.cos(a), CY0 + (r1 + 0.05 * (_k + 1)) * math.sin(a)
                    x, y = min(0.92, max(0.26, x)), min(0.78, max(0.10, y))
                placed.append((x, y)); out[g].append([round(x, 3), round(y, 3)])
        return out
    _ring_pos = _rings({g: sum(1 for it in items if it["g"] == g) for g in (0, 1, 2)})
    star_pos = _ring_pos[0] + _ring_pos[1] + _ring_pos[2]
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
    goes = [str(it.get("go") or "") for it in allit]        # подпись-переход: куда вести кликом
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

    # ЛИДЕР — ОДИН ИСТОЧНИК НА ПРОЕКТ (09.09, владелец: «какой смысл делать половинчатую правку?»).
    # Здесь был свой расчёт: верхний по СУТОЧНОМУ ходу из очереди, порог по нему же. После того как
    # правило переехало в analytics_leaders (+50% за сутки, оборот, квант, листинг, основа), правило
    # стало жить в двух местах — и экран показывал IOST лидером с +16.7% и подписью «+17% от дна
    # недели», где на самом деле стоял суточный ход. Теперь интро НИЧЕГО не считает: читает готовый
    # список pump_leaders.json. Мелькающие остаются здесь — это про ленту очереди, а не про лидера.
    leader: dict = {}
    flicker: list = []
    _live: list = []
    try:
        from core_config import PUMP_LEADERS_PATH as _pl
    except ImportError:
        _pl = BASE_DIR / "output" / "pump_leaders.json"
    try:
        _recs = json.loads(_pl.read_text(encoding="utf-8"))
        _live[:] = [r for r in _recs.values()
                 if isinstance(r, dict) and not r.get("retired_at")]
        _live.sort(key=lambda r: -(r.get("run_pct") or 0))
        _live[:] = _queue_first_first(_live)                     # 18.09: плашка — про первого в очереди
        if _live:
            _l = _live[0]
            _sym = str(_l.get("symbol") or "")
            # ЧЕМ ОПАСЕН ЛИДЕР (09.09, владелец: «добавь, что происходит опасного — фандинг,
            # дельта, оборот, интерес угасает»). Панель говорила, кто ведёт, но не говорила цену
            # вопроса. Берём числа последнего прогона по этой монете из ленты очереди и оставляем
            # только то, что сработало: пустых строк не будет.
            _risk: list = []
            try:
                _rows = [json.loads(_l) for _l in
                         (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines()
                         if _l.strip()]
                _last = next((r for r in reversed(_rows) if r.get("sym") == _sym), None)
            except (OSError, ValueError):
                _last = None
            if _last:
                _f = _last.get("funding")
                _oi, _px = _last.get("oi_chg_pct"), _last.get("px_chg_pct")
                _dd = _last.get("drawdown_pct")
                _tr = _last.get("oi_trend_pct")
                _bt = _last.get("today") or ""
                if _f is not None and abs(_f) >= 0.05:
                    _risk.append(("шорты платят" if _f < 0 else "лонги платят")
                                 + f" {_f:+.2f}% — так долго не держится")
                if _oi and _px and _px > 0 and _oi / _px >= 2.5:
                    # СТОРОНУ НЕ ДОМЫСЛИВАЕМ (09.09, владелец): число — это отношение процента
                    # роста интереса к проценту роста цены, а не «плечо к цене». И набивать могут
                    # шорты: у IOST фандинг минус, значит платят как раз они. Сторону показывает
                    # отдельная строка про фандинг.
                    _risk.append(f"интерес растёт быстрее цены в {_oi / _px:.1f} раза")
                if _tr is not None and _tr <= -2:
                    _risk.append(f"интерес угасает {_tr:+.1f}% за три часа")
                if _dd is not None and _dd <= -8:
                    _risk.append(f"от вершины дня {_dd:+.0f}%")
                if "шорты закрывают" in str(_bt):
                    _risk.append("вверх толкают закрывающиеся шорты — топливо конечно")
                # СИЛА ВЫДЫХАЕТСЯ (10.09): разворот дельты раньше цены. Проверено на 22 ходах —
                # сработал в 21, медианная фора 3 бара (1.5 ч), медианное падение после вершины
                # −7.2%; SOPH дал 6 баров форы и дальше −47.5%. В балл не идёт, только показ.
                _fa = _last.get("force_turn_ago")
                if _fa is not None and _fa <= 8:
                    _risk.insert(0, f"сила развернулась {_fa} бар назад — ход выдыхается")
                # ВИХРЬ — ХЕДЖ ПО ФОРМЕ ХОДА (11.09, четыре лидера недели). Капсула ДОБАВЛЯЕТСЯ к
                # остальным, ничего не заменяет. Парабола: продавцы поднимают лои под максимумом дня
                # (IOST, SOPH, USELESS — по 5–7 баров под повторной вершиной, сила там дёргалась).
                # Лестница: сторона сменилась (DOOD, ARB — до слома). Ставится следом за силой.
                _vh = _last.get("vortex_hedge") or {}
                if _vh.get("kind") == "парабола" and (_vh.get("bars") or 0) <= 8:
                    _risk.insert(1 if (_fa is not None and _fa <= 8) else 0,
                                 f"вортекс: продавцы поднимают лои {_vh['bars']} бар под максимумом дня")
                elif _vh.get("kind") in ("лестница", "сторона") and (_vh.get("bars") or 0) <= 8:
                    _risk.insert(1 if (_fa is not None and _fa <= 8) else 0,
                                 f"вортекс: сторона сменилась на продавцов {_vh['bars']} бар назад")
                elif _vh.get("kind") == "пересечение":
                    _risk.insert(1 if (_fa is not None and _fa <= 8) else 0,
                                 f"вортекс: продавцы над покупателями {_vh['bars']} бар подряд")
            leader = {
                "sym": _sym.replace("USDT", ""),
                "risk": _risk[:3],
                "run_pct": _l.get("run_pct"),
                "state": "тянет одна" if len(_live) == 1 else f"тянут {len(_live)}",
                "line": f"+{_l.get('run_pct') or 0:.0f}% от основы"
                        + (f" · {_l['day_pct']:+.0f}% за сутки" if _l.get("day_pct") is not None else "")
                        + (" · наша" if _l.get("mine") else " · не из выборки"),
                "lead_gap": 99 if len(_live) == 1 else 5,   # панель показывается, пока лидер есть
                "ended": None, "hours": None, "runs_weak": 0,
            }
    except (OSError, ValueError):
        leader = {}
    # ПРИПИСКА О ФОНЕ (07.09, владелец: «лучше показывать, чем не показывать, но она не должна
    # никак влиять»): нейтральная строка фактов внизу экрана. В балл и в группы не входит.
    # 08.09: фон приходит СПИСКОМ признаков — каждый со своим состоянием, а не одной строкой
    bgnote: list = []
    try:
        from market_bg import bg_note
        bgnote = bg_note() or []
    except Exception as _e:  # noqa: BLE001
        # ОШИБКА НЕ ПРОГЛАТЫВАЕТСЯ МОЛЧА (10.09): 10.09 фон падал на делении на ноль, панель
        # приборов исчезала с экрана целиком, и снаружи это выглядело как «пропали приборы».
        # Пишем причину в stderr — она попадает в лог прогона, как любой другой сбой источника.
        print(f"фон не собрался: {type(_e).__name__}: {_e}", file=sys.stderr)
        bgnote = []
    # ПОДНЯТО ВЫШЕ (10.09): блок «фон давит» читает bgnote, а создавался он ниже по файлу —
    # Python считал имя локальным и на каждом прогоне давал UnboundLocalError. Его глотал
    # except Exception, поэтому blank всегда оставался пустым и режим «пустое поле» не включался
    # ни разу. Тот же класс тихого обрыва, что 09.09 с timedelta: шаг не падает, правка не живёт.

    # ── ФОН ДАВИТ: ЗВЁЗД НЕТ (10.09, владелец: «звёзды все убираем, если фон не лидер; если
    # лидер — только его оставляем»). Читать доску нечем: деньги либо заняты одной монетой, либо
    # их нет вовсе. Показываем светило по центру и одну строку — что именно мешает.
    # Верхняя панель лидера убрана: её текст переехал вниз, под светило, в том же виде.
    # ПЕРВАЯ, КОТОРАЯ ДЕРЖИТСЯ (11.09, владелец): ОДНА звезда — нынешняя первая очереди, если она была
    # первой не меньше трёх прогонов за сутки (сейчас плюс ещё два). На неё не действует ни одно
    # гашение экрана: солнце, фон, фильтры. Считается всегда, идёт в данные.
    keep_first: dict = {}
    try:
        _nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
        _first = str(((_nm.get("first") or [None])[0]) or "")
        _since = datetime.now(timezone.utc) - timedelta(hours=24)
        _n1 = 0
        if _first:
            for _line in (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines()[-4000:]:
                try:
                    _r = json.loads(_line)
                except ValueError:
                    continue
                if _r.get("sym") == _first and _r.get("place") == 1 and datetime.fromisoformat(str(_r.get("at")).replace("Z", "+00:00")) >= _since:
                    _n1 += 1
        if _first and _n1 >= 3:
            keep_first = {_first: _n1}
    except Exception:  # noqa: BLE001
        keep_first = {}
    for _i, _sym in enumerate(syms):
        if _sym in keep_first:
            bright[_i] = 1.0

    blank: dict = {}
    try:
        _bg = {r[0]: (r[1], r[2]) for r in (bgnote or [])}
        # один прибор «монеты к медиане» (13.09): оба числа теперь в одной строке
        _br = _bg.get("монеты к медиане") or _bg.get("монеты")
        _md = _br
        _share = None
        _m = re.search(r"растёт (\d+) из (\d+)", str(_br[1])) if _br else None
        if _m:
            _share = int(_m.group(1)) / max(1, int(_m.group(2)))
        _med = None
        _m2 = re.search(r"(-?\d+[.,]?\d*)% медиана", str(_br[1])) if _br else None
        if _m2:
            _med = float(_m2.group(1).replace(",", "."))
        _lead_alive = bool(leader.get("sym"))
        # «доска давит» тоже снимается при многих лидерах (16.09): медиана минусовая ровно потому,
        # что деньги собрались в нескольких монетах, — гасить звёзды в этот момент нельзя.
        if (not _many_lead()) and not _lead_alive and _share is not None and _med is not None and _share < 0.5 and _med < -0.3:
            _parts = []                                        # 24.09: одна и та же строка приходила дважды
            for _x in ((str(_br[1]) if _br else ""), (str(_md[1]) if _md else ""), "лидера нет"):
                for _y in _x.split(" · "):
                    if _y and _y not in _parts:
                        _parts.append(_y)
            blank = {"why": "доска давит", "note": " · ".join(_parts)}
            # ПЕРВАЯ, КОТОРАЯ ДЕРЖИТСЯ (11.09, владелец): под солнцем звёзд нет, но если нынешняя первая
            # очереди была первой не меньше трёх прогонов за сутки — её звезда остаётся: узкая доска
            # при живой первой — след того, что деньги собираются в неё (лидер первичен).
            if keep_first:
                _k, _v = next(iter(keep_first.items()))
                blank["keep"] = [_k]
                blank["note"] += f" · {_k.replace('USDT', '')} первой {_v} прогонов за сутки — держится"
    except Exception:  # noqa: BLE001
        blank = {}

    # ПЛЕЧО КОПИТСЯ, ЦЕНА СТОИТ (09.09): метка на звезде — интерес за три дня прибавил от 30%,
    # цена в пределах 10%. Признак наблюдательный, в балл не идёт; на истории 21 монеты давал
    # ход ≥10% за три дня почти в половине случаев, а при интересе от +50% — в трёх из четырёх.
    accum: dict = {}
    try:
        _nmj = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
        for _s, _v in (_nmj.get("coins") or {}).items():
            _n = _v.get("nums") or {}
            _a = _n.get("accum")
            if _a:
                accum[_s.replace("USDT", "")] = dict(_a, past=False)
            elif _n.get("accum_past"):
                accum[_s.replace("USDT", "")] = dict(_n["accum_past"], past=True)
    except (OSError, ValueError):
        accum = {}

    # ── ДВА ПОСЛЕДНИХ ПУЗЫРЯ У ЛИДЕРОВ (09.09, владелец: «показывать пузырик ровно как мы их
    # рисовали на графике — яркие и сомнительные, только у монет с ходом +40% за 24ч»).
    # Берём монеты из pump_leaders.json (порог, оборот, квант и листинг уже проверены там) и по
    # каждой — два последних пузыря дня из near_move: сторона и спорность, как на карточке.
    bub: dict = {}
    try:
        _lead_syms = {str(r.get("symbol") or "") for r in _live} if _live else set()
        if _lead_syms:
            _nm2 = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
            for _s2, _v2 in (_nm2.get("coins") or {}).items():
                if _s2 not in _lead_syms:
                    continue
                _bl = ((_v2.get("today") or {}).get("bubbles") or [])[-2:]
                if _bl:
                    bub[_s2.replace("USDT", "")] = [
                        {"buy": b.get("side") == "buy", "doubt": b.get("sure") == "сомнительный"}
                        for b in _bl]
    except (OSError, ValueError, NameError):
        bub = {}

    # мелькающие: за последние 6 прогонов были и в первых, и вне их
    try:
        _by: dict = {}
        for line in (BASE_DIR / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                _r = json.loads(line)
            except ValueError:
                continue
            _by.setdefault(_r.get("sym"), []).append(_r.get("place"))
        for s3, places in _by.items():
            tail = [p for p in places[-6:] if p]
            if len(tail) >= 4 and any(p <= 3 for p in tail) and any(p > 3 for p in tail):
                flicker.append(str(s3).replace("USDT", ""))
    except OSError:
        flicker = []

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
    # СЕССИИ ДЛЯ ПЕРВОГО ЭКРАНА (12.09, владелец): за час до перехода — предупреждение, в час
    # открытия — сам переход, и главное — подхватила ли новая сессия лидера. Границы в UTC
    # (они у бирж), подписи без времени, чтобы не спорить с местными часами смотрящего.
    sess_box: dict = {}
    try:
        from datetime import datetime, timezone
        _now = datetime.now(timezone.utc)
        _h = _now.hour + _now.minute / 60
        _opens = ((21.0, "Сидней"), (0.0, "Токио"), (7.0, "Лондон"), (13.0, "Нью-Йорк"))
        _next, _left, _just = "", 24.0, ""
        for _oh, _nm in _opens:
            _d = _oh - _h
            if -1.0 <= _d <= 0:
                _just = _nm
            if _d <= 0:
                _d += 24
            if _d < _left:
                _left, _next = _d, _nm
        sess_box = {"next": _next, "in_h": round(_left, 2), "just_open": _just}
        _nm2 = _read("near_move.json") or {}
        _lsym = str((leader or {}).get("sym") or "")
        if _lsym and not _lsym.endswith("USDT"):
            _lsym += "USDT"
        _lp = (((_nm2.get("coins") or {}).get(_lsym) or {}).get("today") or {}).get("sess_pickup")
        if _lp:
            sess_box["pickup"] = {"ok": bool(_lp.get("pickup")),
                                  "text": str(_lp.get("why") or "")}
    except Exception:   # noqa: BLE001 — сессии не обязаны считаться
        sess_box = {}
    # ВСПЛЫВАШКА БИТКОИНА (18.09, владелец: «оставляем только монету и стрелку, остальное при наведении»):
    # весь срез из output/btc_pulse.json уходит в данные страницы; на экране — монета, цена, стрелка.
    _bp = _read("btc_pulse.json") or {}
    btc_pulse = {k: _bp.get(k) for k in ("map", "liq", "premium", "etf", "stamp", "read") if _bp.get(k) is not None}
    if blank:
        _keep = set(blank.get("keep") or []) | {s2 for s2, g2 in zip(syms, grp) if g2 == 0 and s2}
        blank["keep"] = sorted(_keep)
        keep_first = {k: keep_first.get(k, 0) for k in _keep}
    _qh_out = {sy: _QH[sy] for sy in syms if sy in _QH and sum(_QH[sy])}
    _qs_out = {sy: int(_QS.get(sy) or 0) for sy in _qh_out}
    _qt_out = {sy: _QT[sy] for sy in _qh_out if sy in _QT}
    data = json.dumps({"qh": _qh_out, "qs": _qs_out, "qt": _qt_out, "btc": btc_pulse, "names": names, "grp": grp, "syms": syms, "goes": goes, "many": _many_lead(), "book": _book_count(), "whys": whys, "pos": pos, "counts": counts, "label": lab, "subs": subs, "bright": bright, "zones": zones, "taker": taker, "acc": acc, "orbits": orbits, "bgnote": bgnote, "leader": leader, "sess": sess_box, "flicker": flicker, "accum": accum, "bub": bub, "blank": blank, "keep": list(keep_first)},
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
  /* ЗАГОЛОВОК ЛИДЕРА (09.09, владелец: «давай красивее, каких-то элементов дорисовать и чуть
     анимации»): раньше — три строки текста без обрамления. Теперь: тонкие световые усы по бокам
     подписи, мягкое зарево за именем, медленный проход блика по буквам и еле заметное дыхание
     всего блока. Ничего не мигает: экран должен оставаться спокойным. */
  .lead{position:fixed;left:50%;top:22px;transform:translateX(-50%);text-align:center;pointer-events:none;z-index:4;
    font-family:"Inter",system-ui,sans-serif;font-weight:300;animation:leadbreath 7.5s ease-in-out infinite}
  @keyframes leadbreath{50%{transform:translateX(-50%) translateY(1.5px)}}
  /* зарево за именем */
  .lead:before{content:"";position:absolute;left:50%;top:14px;width:280px;height:64px;
    transform:translateX(-50%);pointer-events:none;border-radius:50%;
    background:radial-gradient(closest-side,rgba(150,190,255,.20),rgba(150,190,255,0) 72%);
    filter:blur(3px);animation:leadglow 6s ease-in-out infinite}
  @keyframes leadglow{50%{opacity:.55}}
  /* имя: проход блика по буквам, медленный */
  .lead b{display:block;position:relative;font-family:"Michroma",system-ui,sans-serif;font-weight:400;
    font-size:13.6px;letter-spacing:.28em;color:#f2f7ff;
    text-shadow:0 0 26px rgba(190,220,255,.9),0 0 60px rgba(140,180,255,.5);
    background:linear-gradient(100deg,#f2f7ff 38%,#ffffff 47%,#cfe4ff 56%,#f2f7ff 66%);
    background-size:280% 100%;-webkit-background-clip:text;background-clip:text;
    animation:leadshine 9s ease-in-out infinite}
  @keyframes leadshine{0%,100%{background-position:120% 0}50%{background-position:-20% 0}}
  /* РАЗДЕЛЕНИЕ СТРОК (09.09, владелец: «давай эти надписи визуально разделим»): строка с числами
     отбита сверху волоском, а внутри неё разделители — ромбы, не точки. */
  .lead s{display:block;text-decoration:none;margin-top:8px;padding-top:8px;font-size:8.4px;
    letter-spacing:.14em;color:#cfe0ff;position:relative}
  .lead s:before{content:"";position:absolute;left:50%;top:0;width:120px;height:1px;transform:translateX(-50%);
    background:linear-gradient(90deg,transparent,rgba(160,200,255,.35),transparent)}
  .lead s o{color:rgba(150,190,255,.45);font-size:5.5px;vertical-align:1.5px;margin:0 2px}
  /* подпись «сейчас ведёт» со световыми усами по бокам */
  .lead i{display:flex;align-items:center;justify-content:center;gap:9px;font-style:normal;margin-top:4px;
    font-size:6.4px;letter-spacing:.3em;text-transform:uppercase;color:rgba(190,205,255,.55)}
  .lead i:before,.lead i:after{content:"";width:52px;height:1px;
    background:linear-gradient(90deg,transparent,rgba(160,200,255,.55))}
  .lead i:after{background:linear-gradient(270deg,transparent,rgba(160,200,255,.55))}
  .lead u.hot{color:#ff8a70;text-shadow:0 0 16px rgba(255,130,100,.8)}
  .lead u.warn{color:#ffc069;text-shadow:0 0 16px rgba(255,180,90,.85)}
  /* ограничения сняты: многие лидеры (16.09) — зелёным, это открытый вход, не предупреждение */
  .lead u.lift{color:#7fe6b8;text-shadow:0 0 16px rgba(127,230,184,.7);border-color:rgba(127,230,184,.45)}
  /* предупреждение — в тонкой янтарной рамке-капсуле */
  /* состояние — своя капсула, холодная; «вход закрыт» остаётся янтарной */
  .lead u.state{color:#dbe8ff;text-shadow:0 0 16px rgba(160,200,255,.8);
    box-shadow:inset 0 0 0 1px rgba(160,200,255,.35),0 0 22px rgba(140,180,255,.12);margin-right:6px}
  .lead u{display:inline-block;text-decoration:none;margin-top:10px;font-size:8px;font-weight:600;
    letter-spacing:.26em;text-transform:uppercase;color:#ffe0b8;
    text-shadow:0 0 16px rgba(255,200,140,.9);
    padding:5px 14px;border-radius:999px;
    box-shadow:inset 0 0 0 1px rgba(255,200,120,.45),0 0 22px rgba(255,180,90,.16)}
  /* ЧЕМ ОПАСЕН (09.09): коралловые строки под предупреждением, каждая с числом */
  .lead em{display:block;margin-top:9px;padding-top:9px;font-style:normal;position:relative}
  .lead em:before{content:"";position:absolute;left:50%;top:0;width:90px;height:1px;transform:translateX(-50%);
    background:linear-gradient(90deg,transparent,rgba(255,150,120,.30),transparent)}
  .lead em i{display:inline-block;font-style:normal;margin:2px 5px;font-size:7px;letter-spacing:.16em;
    text-transform:uppercase;color:#ffb0a0;padding:3px 9px;border-radius:999px;
    box-shadow:inset 0 0 0 1px rgba(255,140,110,.25);text-shadow:0 0 12px rgba(255,120,90,.55)}
  .lead.ended b{color:#ffd8cc;text-shadow:0 0 26px rgba(255,150,120,.7)}
  .lead.ended s{color:#ffd8cc}
  /* ПЛЕЧО КОПИТСЯ — ЗОЛОТОЙ СПУТНИК (09.09, владелец: «кольцо сильно портит дизайн, сделай рядом
     яркий золотой спутник который двигается»). Кольцо обводило имя и спорило с лучами; спутник
     живёт рядом со звездой и не трогает её. Обходит имя по вытянутой орбите, ярко светится,
     оставляет короткий след. Сильный случай (интерес от +50% при цене ±5%) крупнее и быстрее. */
  /* СПУТНИК В ЦВЕТ ЗВЕЗДЫ (09.09, владелец): золотой спорил с холодным светом имён. Берёт тот же
     тон, что и подписи, — белое ядро с голубым ореолом; сильный случай крупнее и ярче. */
  /* ЦВЕТ РАЗДЕЛЯЕТ ДВА СЛУЧАЯ (09.09, владелец: «у кого в истории — белым, у кого копится
     сейчас — золотым с подсветкой; они сейчас не светятся вообще»).
     Копится СЕЙЧАС — золотой и живой: тёплое ядро, три слоя свечения, мягкий пульс.
     Копилось РАНЬШЕ — белый и спокойный: холодное ядро, свечения меньше. */
  .sat{position:fixed;pointer-events:none;z-index:3;width:15px;height:15px;border-radius:50%;
    transform:translate(-50%,-50%);
    background:radial-gradient(circle at 34% 30%,#fffdf5,#ffe9a8 38%,#ffc247 72%,#f0a01e);
    box-shadow:0 0 22px rgba(255,206,110,1),0 0 55px rgba(255,180,60,.85),0 0 105px rgba(240,150,30,.45);
    animation:satdrift 5.2s ease-in-out infinite, satglow 2.6s ease-in-out infinite}
  .sat.strong{width:21px;height:21px;
    box-shadow:0 0 32px rgba(255,222,140,1),0 0 80px rgba(255,190,70,1),0 0 145px rgba(240,150,30,.55)}
  @keyframes satglow{50%{box-shadow:0 0 30px rgba(255,216,130,1),0 0 74px rgba(255,190,70,1),0 0 130px rgba(240,150,30,.6)}}
  /* лёгкий дрейф на месте вместо орбиты: несколько пикселей вверх-вниз и чуть вбок */
  @keyframes satdrift{0%,100%{transform:translate(-50%,-50%)}
                      50%{transform:translate(calc(-50% + 4px),calc(-50% - 5px))}}
  /* КОПИЛОСЬ РАНЬШЕ (09.09): ход уже начался, а происхождение важно — такая монета после отката
     уходит выше. Спутник тусклее и со шлейфом длиннее: уходящий, а не набирающий. */
  .sat.past{width:12px;height:12px;opacity:.85;animation:satdrift 7.5s ease-in-out infinite;
    background:radial-gradient(circle at 34% 30%,#fff,#f2f7ff 45%,#cfe0f8 75%,#a8c2e6);
    box-shadow:0 0 16px rgba(235,244,255,.9),0 0 40px rgba(190,215,255,.5)}
  /* ЛУЧИ У СПУТНИКА (09.09, владелец: «можешь им лучи тоже добавить?») — как у звёзд: четыре
     тонких луча крест-накрест, длинные по горизонтали, короче по вертикали. Рисуются двумя
     псевдоэлементами самого спутника, поэтому двигаются и пульсируют вместе с ним. */
  .sat i{display:none}
  .sat:before,.sat:after{content:"";position:absolute;left:50%;top:50%;pointer-events:none;
    transform:translate(-50%,-50%)}
  .sat:before{width:74px;height:1.5px;
    background:linear-gradient(90deg,transparent,rgba(255,214,130,.9) 50%,transparent)}
  .sat:after{width:1.5px;height:46px;
    background:linear-gradient(180deg,transparent,rgba(255,214,130,.85) 50%,transparent)}
  .sat.strong:before{width:104px;height:2px}
  .sat.strong:after{width:2px;height:64px}
  .sat.past:before{width:58px;background:linear-gradient(90deg,transparent,rgba(230,242,255,.75) 50%,transparent)}
  .sat.past:after{height:36px;background:linear-gradient(180deg,transparent,rgba(230,242,255,.7) 50%,transparent)}
  .sat.past i{width:60px;background:linear-gradient(90deg,rgba(225,238,255,.55),transparent)}
  .sattip{position:fixed;pointer-events:none;z-index:3;font-size:6.6px;letter-spacing:.2em;
    text-transform:uppercase;color:rgba(255,216,150,.8);white-space:nowrap;transform:translate(-50%,-50%)}
  .sattip.past{color:rgba(225,238,255,.7)}
  .sattip b{font-weight:500;color:#ffc247;text-shadow:0 0 8px rgba(255,180,60,.8),0 0 2px rgba(0,0,0,.9)}
  .sattip{text-shadow:0 0 6px rgba(0,0,0,.9)}
  /* ПУЗЫРИ ПОД ИМЕНЕМ (09.09, вариант А): два последних, цвет по стороне заявки, у спорного
     правая половина янтарная — ровно как на графике карточки. Только у монет из лидеров. */
  .bub{position:fixed;pointer-events:none;z-index:3;border-radius:50%;transform:translate(-50%,-50%);
    width:7px;height:7px}
  .bub.buy{background:radial-gradient(circle at 35% 32%,#eafff6,#5fe6a6 60%,#2fbf82);
    box-shadow:0 0 10px rgba(95,230,166,.9),0 0 26px rgba(60,200,140,.45)}
  .bub.sell{background:radial-gradient(circle at 35% 32%,#fff0ec,#ff7a63 60%,#d8503a);
    box-shadow:0 0 10px rgba(255,122,99,.9),0 0 26px rgba(210,80,60,.45)}
  .bub.half{overflow:hidden}
  .bub.half:after{content:"";position:absolute;left:50%;top:0;right:0;bottom:0;
    background:linear-gradient(180deg,#ffd27a,#ffb020)}
  /* КОЛОНКА ШИРЕ И ОТ КРАЯ (09.09): строка «плечо уходит −1.1% · жгут лонгов ×4.3 · Америка не
     покупает» не помещалась и обрезалась слева. */
.blank{position:fixed;inset:0;z-index:7;pointer-events:none;display:grid;place-items:center;
  opacity:0;animation:blankin 1.8s ease .9s forwards}
@keyframes blankin{to{opacity:1}}
.blank.aside{place-items:start end;padding:8vh 9vw 0 0}
.blank.aside .sun{transform:scale(.62);transform-origin:100% 0}
.sun{position:relative;width:360px;height:360px;display:grid;place-items:center}
.sun .core{position:relative;width:74px;height:74px;border-radius:50%;
  background:radial-gradient(circle at 36% 32%, #ffffff, #eaf3ff 34%, #a9c8ff 62%, #6b93ff);
  box-shadow:0 0 26px rgba(200,225,255,1), 0 0 72px rgba(140,185,255,.85), 0 0 155px rgba(100,150,255,.5);
  animation:sunbreath 5.5s ease-in-out infinite}
@keyframes sunbreath{50%{filter:brightness(1.2)}}
.sun .far{position:absolute;inset:-40%;border-radius:50%;
  background:radial-gradient(closest-side, rgba(120,165,255,.16), transparent 72%);
  filter:blur(24px);animation:sunbreath 9s ease-in-out infinite}
/* ПРИТЯЖЕНИЕ (10.09, владелец: «пусть точки притягиваются к солнцу как у первых звёзд»).
   У звёзд группы «брать» искры текут к имени — здесь так же: частицы летят к ядру со всех
   сторон, вытянуты по ходу движения (короткий след), ускоряются к центру и гаснут у самой
   поверхности. Углы, дальность и скорость у каждой свои — потока ровными пачками нет. */
.sun .arm{position:absolute;left:50%;top:50%;width:0;height:0}
.sun .arm i{position:absolute;left:0;top:0;width:7px;height:2px;margin:-1px 0 0 0;border-radius:2px;
  transform-origin:0 50%;
  background:linear-gradient(90deg, rgba(255,255,255,0), rgba(215,235,255,.95));
  box-shadow:0 0 8px rgba(170,205,255,.85), 0 0 20px rgba(120,170,255,.45);
  animation:pull cubic-bezier(.35,0,.7,1) infinite}
@keyframes pull{
  0%{opacity:0;transform:rotate(var(--a)) translateX(var(--r)) scaleX(.6)}
  10%{opacity:.95}
  70%{opacity:1;transform:rotate(var(--a)) translateX(72px) scaleX(1.6)}
  100%{opacity:0;transform:rotate(var(--a)) translateX(34px) scaleX(.5)}}
.sun .halo{position:absolute;inset:2%;border-radius:50%;
  background:radial-gradient(closest-side, rgba(160,200,255,.18), transparent 70%);filter:blur(9px);
  animation:sunbreath 7s ease-in-out infinite}

/* ЛУЧИ ИЗ ЯДРА (10.09, владелец: «ровно четыре смотрится плоско»): девять под разными углами,
   разной длины и яркости, каждый дышит в своём ритме. */
.sun .rr{position:absolute;left:50%;top:50%;height:1.5px;transform-origin:0 50%;pointer-events:none;
  background:linear-gradient(90deg, rgba(210,232,255,.9), rgba(160,200,255,.35) 45%, transparent);
  animation:rrpulse ease-in-out infinite}
@keyframes rrpulse{50%{opacity:.4;filter:blur(.4px)}}
.blank .say{position:absolute;left:50%;top:calc(50% + 170px);transform:translateX(-50%);text-align:center;
  font-family:"Inter",system-ui,sans-serif;white-space:nowrap}
.blank .say i{display:block;font-style:normal;font-size:7.5px;letter-spacing:.46em;text-transform:uppercase;
  color:rgba(190,205,255,.5);margin-bottom:13px}
.blank .say b{display:block;font-weight:200;font-size:20px;letter-spacing:.15em;color:#eef4ff;
  text-shadow:0 0 30px rgba(150,190,255,.65)}
.blank .say s{display:block;text-decoration:none;margin-top:12px;font-size:10px;letter-spacing:.07em;
  color:rgba(190,205,255,.5)}
.blank .say s w{color:#dbe6ff}
/* текст лидера — тот же вид, что под светилом, только внизу по центру (10.09) */
.blank.leadsay{display:block;background:none;pointer-events:none}
.blank.leadsay .say{top:auto;bottom:96px}
.blank.leadsay .say b{color:#ffeec6;text-shadow:0 0 26px rgba(255,180,90,.5)}
.blank.leadsay .say s w{color:#ffd9a8}
.blank.leadsay .say u{display:block;text-decoration:none;margin-top:10px;font-size:8.5px;
  letter-spacing:.14em;text-transform:uppercase;color:#ffb0a0}
  .bgnote{position:fixed;left:2vw;bottom:34vh;width:clamp(190px,19vw,260px);z-index:3;
    font-family:"Inter",system-ui,sans-serif;font-weight:300;pointer-events:none}
  .bgnote i.hd{font-style:normal;display:block;font-size:6.1px;letter-spacing:.34em;text-transform:uppercase;
    color:rgba(190,205,255,.34);margin-bottom:14px}
  .bgnote .g{position:relative;margin-bottom:24px}
  .bgnote .g .t{font-size:6.1px;letter-spacing:.3em;text-transform:uppercase;
    color:rgba(190,205,255,.42);margin-bottom:20px}
  /* ЗНАЧОК СЛЕВА ОТ ПОДПИСИ (09.09, владелец: «значка биткоина нет»): стоял справа и уезжал за
     край узкой колонки. Теперь перед словом, в потоке строки. */
  .bgnote .ico{width:30px;height:30px;color:rgba(255,206,120,.85);vertical-align:-10px;margin-right:7px;
    filter:drop-shadow(0 0 8px rgba(255,190,90,.45))}
  /* дуга идёт ПО САМОЙ обводке: та же окружность, тот же центр, вращается группа целиком */
  .bgnote .ico .btcrun{transform-box:view-box;transform-origin:50% 50%;
    animation:btcrun 3.4s linear infinite;filter:drop-shadow(0 0 4px rgba(255,230,170,.95))}
  @keyframes btcrun{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  /* ОДИН ПРИБОР БИТКОИНА (18.09): монета, цена, стрелка; всплывашка — в языке всплывашки звезды */
  .bgnote .g.btcg{margin-bottom:22px;pointer-events:auto;cursor:default}
  .bgnote .bt_face{display:flex;align-items:center;gap:10px}
  .bgnote .bt_face .ico{width:38px;height:38px;margin:0;vertical-align:0}
  .bgnote .bt_pxv{font-size:21px;font-weight:200;letter-spacing:.02em;color:#eef3ff;text-shadow:0 0 18px rgba(150,190,255,.25)}
  .bgnote .bt_pxv s{text-decoration:none;font-size:10px;color:rgba(190,205,255,.42);margin-left:3px}
  .bgnote .bt_arw{width:20px;height:28px;opacity:var(--p);filter:drop-shadow(0 0 6px currentColor)}
  .bgnote .bt_arw.up{color:#7fe0b0}.bgnote .bt_arw.dn{color:#ff8fa3}.bgnote .bt_arw.flat{color:#9fb0d8}
  /* плита стоит справа от прибора, по центру его высоты, и не вылезает за экран: высота ограничена, внутри прокрутка */
  .bgnote .bt_tipwrap{position:absolute;left:calc(100% + 18px);top:50%;z-index:9;opacity:0;transform:translate(6px,-50%);
    pointer-events:none;transition:opacity .22s ease,transform .22s ease}
  .bgnote .btcg:hover .bt_tipwrap,.bgnote .btcg:focus-within .bt_tipwrap{opacity:1;transform:translate(0,-50%);pointer-events:auto}
  .bgnote .bt_tip{width:340px;max-height:min(86vh,720px);overflow:auto;padding:14px 15px 12px;border-radius:4px;
    background:linear-gradient(180deg,rgba(11,16,34,.97),rgba(7,10,24,.97));
    border:1px solid rgba(150,175,255,.18);box-shadow:0 20px 60px rgba(0,0,0,.65),0 0 0 1px rgba(255,255,255,.02) inset}
  .bgnote .bt_tip::-webkit-scrollbar{width:4px}.bgnote .bt_tip::-webkit-scrollbar-thumb{background:rgba(150,175,255,.2)}
  .bgnote .bt_th{font-size:6.1px;letter-spacing:.3em;text-transform:uppercase;color:rgba(190,205,255,.42)}
  .bgnote .bt_th em{font-style:normal;color:rgba(190,205,255,.28)}
  .bgnote .bt_big{font-size:30px;font-weight:200;letter-spacing:.02em;margin:6px 0 10px;color:#eef3ff}
  .bgnote .bt_big s{text-decoration:none;font-size:13px;color:rgba(190,205,255,.42);margin-left:4px}
  .bgnote .bt_sec{font-size:6.1px;letter-spacing:.28em;text-transform:uppercase;color:rgba(190,205,255,.3);margin:12px 0 6px}
  .bgnote .bt_kv{display:flex;justify-content:space-between;gap:10px;font-size:8.6px;padding:3px 0;border-bottom:1px solid rgba(150,175,255,.06)}
  .bgnote .bt_kv span{color:rgba(190,205,255,.42)}.bgnote .bt_kv b{font-weight:300;color:#dbe6ff;text-align:right}
  .bgnote .bt_kv b.sh{color:#ffb26f}.bgnote .bt_kv b.lo{color:#6fb4ff}.bgnote .bt_kv b.gr{color:#7fe0b0}.bgnote .bt_kv b.ro{color:#ff8fa3}
  .bgnote .bt_zones{margin:10px 0 2px}
  .bgnote .bt_z{display:flex;align-items:center;gap:6px;font-size:8px;padding:2px 0}
  .bgnote .bt_zp{width:52px;color:#dbe6ff}.bgnote .bt_zu{width:42px;text-align:right;color:rgba(190,205,255,.42)}.bgnote .bt_zd{width:42px;text-align:right;color:rgba(190,205,255,.28)}
  .bgnote .bt_zb{flex:1;height:3px;background:rgba(150,175,255,.08);border-radius:2px;overflow:hidden}
  .bgnote .bt_zb i{display:block;height:100%}
  .bgnote .bt_z.sh .bt_zb i{background:linear-gradient(90deg,rgba(255,178,111,.35),#ffb26f);box-shadow:0 0 8px rgba(255,178,111,.5)}
  .bgnote .bt_z.lo .bt_zb i{background:linear-gradient(90deg,rgba(111,180,255,.35),#6fb4ff);box-shadow:0 0 8px rgba(111,180,255,.45)}
  .bgnote .bt_zc{display:flex;justify-content:space-between;font-size:8px;margin:4px 0;padding:3px 0;border-top:1px dashed rgba(255,255,255,.18);border-bottom:1px dashed rgba(255,255,255,.18)}
  .bgnote .bt_zc b{font-weight:400;color:#fff}.bgnote .bt_zc span{color:#fff}
  .bgnote .bt_foot{font-size:7.4px;color:rgba(190,205,255,.28);margin-top:10px}
  /* строка без датчика: только состояние и число */
  .bgnote .g.plain{margin-bottom:18px}
  .bgnote .g.plain .t{margin-bottom:6px}
  .bgnote .g.plain .pv{font-size:9.9px;font-weight:300;color:#dbe6ff;letter-spacing:.05em}
  .bgnote .g.plain .pn{font-size:8.5px;color:rgba(190,205,255,.42);letter-spacing:.05em;margin-top:2px}
  .bgnote .g.plain .pn w{color:rgba(190,205,255,.34)}
  /* 1. нить с бусиной — перевес сторон */
  .bgnote .rail{position:relative;height:1px;
    background:linear-gradient(90deg,rgba(150,175,255,0),rgba(150,175,255,.32) 18%,rgba(150,175,255,.32) 82%,rgba(150,175,255,0))}
  .bgnote .rail i{position:absolute;left:50%;top:-4px;width:1px;height:9px;background:rgba(160,185,255,.3)}
  .bgnote .rail:after{content:"";position:absolute;inset:-3px 0;
    background:repeating-linear-gradient(90deg,rgba(210,230,255,.8) 0 2px,transparent 2px 34px);
    -webkit-mask:linear-gradient(90deg,transparent,#000 22%,#000 78%,transparent);
    mask:linear-gradient(90deg,transparent,#000 22%,#000 78%,transparent);opacity:.45;animation:drift 3.4s linear infinite}
  .bgnote .g.dn .rail:after{animation-direction:reverse}
  .bgnote .g.flat .rail:after{opacity:.2;animation-duration:7s}
  .bgnote .bead{position:absolute;top:-4.5px;width:9.5px;height:9.5px;border-radius:50%;transform:translateX(-50%);
    transition:left .8s cubic-bezier(.2,.8,.2,1);animation:bead 3.2s ease-in-out infinite}
  .bgnote .g.up .bead{background:radial-gradient(circle at 36% 32%,#fff,#bff0dd 55%,#5cc9a6);
    box-shadow:0 0 9px rgba(127,227,200,.95),0 0 26px rgba(127,227,200,.5)}
  .bgnote .g.dn .bead{background:radial-gradient(circle at 36% 32%,#fff,#ffd2c4 55%,#e8836a);
    box-shadow:0 0 9px rgba(232,131,106,.95),0 0 26px rgba(232,131,106,.5)}
  .bgnote .g.flat .bead{background:radial-gradient(circle at 36% 32%,#fff,#d6e2f5 55%,#93a7bd);
    box-shadow:0 0 8px rgba(160,185,220,.8)}
  /* ЧИСЛА СВЕТЛЫЕ, СЛОВА СЕРЫЕ (08.09, владелец: «растёт, из, за сутки — тоже второстепенным
     цветом»): значение читается сразу, служебные слова не мешают. */
  /* белые числа в приборах −10% (09.09) */
  .bgnote .val{position:absolute;top:-19px;transform:translateX(-50%);white-space:nowrap;font-size:9px;
    font-weight:200;color:#e2ebff;text-shadow:0 0 15px rgba(150,190,255,.7);transition:left .8s cubic-bezier(.2,.8,.2,1)}
  .bgnote .val w{font-style:normal;color:rgba(190,205,255,.42);text-shadow:none;font-size:8.5px}
  .bgnote .ends{position:relative;height:0}
  .bgnote .ends em{position:absolute;top:9px;font-style:normal;font-size:5.8px;letter-spacing:.24em;
    text-transform:uppercase;color:rgba(190,205,255,.36)}
  .bgnote .ends em.r{right:0}
  /* 2. лидер — кольцо с заполнением по ходу от дна недели */
  .bgnote .g.lead{display:grid;grid-template-columns:44px 1fr;column-gap:11px;align-items:center}
  .bgnote .g.lead .t{grid-column:1/3;margin-bottom:12px}
  .bgnote .ring{position:relative;width:44px;height:44px;border-radius:50%;
    background:conic-gradient(from -90deg,#ffd08a calc(var(--p)*1%),rgba(255,255,255,.06) 0);
    -webkit-mask:radial-gradient(circle,transparent 64%,#000 65%);mask:radial-gradient(circle,transparent 64%,#000 65%);
    filter:drop-shadow(0 0 10px rgba(255,190,110,.6));animation:bead 3.6s ease-in-out infinite}
  .bgnote .ring+.lx{min-width:0}
  /* ПОДПИСЬ ЛИДЕРА В ОДНУ СТРОКУ (09.09, владелец: текст рвался на «ни» и «одна от дна недели») */
  .bgnote .lx b{display:block;font-weight:200;font-size:11.7px;color:#ffe0b0;white-space:nowrap;
    text-shadow:0 0 16px rgba(255,190,110,.7)}
  .bgnote .lx u{display:block;text-decoration:none;font-size:6.8px;letter-spacing:.16em;text-transform:uppercase;
    color:#ffd8a8;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .bgnote .lx u w{font-style:normal;color:rgba(200,212,255,.4)}
  /* 3. торги — циферблат суток: дуги сессий и бегунок «сейчас» */
  .bgnote .clock{position:relative;width:100%;height:26px}
  .bgnote .clock .ln{position:absolute;left:0;right:0;top:12px;height:1px;background:rgba(150,175,255,.18)}
  .bgnote .clock span{position:absolute;top:10px;height:3px;border-radius:3px;opacity:.5}
  .bgnote .clock .now{position:absolute;top:5px;width:1px;height:15px;background:#dbe8ff;
    box-shadow:0 0 9px rgba(200,225,255,.9);animation:bead 3s ease-in-out infinite}
  /* переход близко: прибор теплеет, у границы — метка (12.09) */
  .bgnote .g.soon{background:linear-gradient(180deg,rgba(255,200,120,.08),rgba(255,200,120,0));border-radius:6px}
  .bgnote .g.soon .t{color:#ffd8a8}
  .bgnote .ends em.l b.tleft{font-weight:400;color:#ffd98a;letter-spacing:.14em;
    text-shadow:0 0 10px rgba(255,217,138,.45)}
  .bgnote .g.soon .ends em.l b.tleft{color:#ffb86b;text-shadow:0 0 12px rgba(255,184,107,.75)}
  .bgnote .g .t b.sw{font-weight:400;font-size:5.4px;letter-spacing:.22em;color:#ffb86b;margin-left:6px;
    padding:1px 5px;border:1px solid rgba(255,184,107,.45);border-radius:8px;animation:bead 2.4s ease-in-out infinite}
  .bgnote .clock .edge{position:absolute;top:4px;width:1px;height:17px;background:#ffb86b;
    box-shadow:0 0 10px rgba(255,184,107,.9);opacity:.9}
  .bgnote .clock em{position:absolute;top:17px;font-style:normal;font-size:5.6px;letter-spacing:.2em;
    text-transform:uppercase;color:rgba(190,205,255,.4)}
  @media (prefers-reduced-motion:reduce){.bgnote *{animation:none!important}}
  .hint{position:fixed;right:3vw;bottom:12px;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.12em;color:rgba(200,210,255,.35);pointer-events:none}
  .tip{position:fixed;padding:11px 14px;border-radius:12px;background:rgba(8,12,24,.95);
    backdrop-filter:blur(12px);box-shadow:inset 0 0 0 1px rgba(255,255,255,.09),0 18px 40px rgba(0,0,0,.7);
    color:#dfe6ff;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;
    letter-spacing:.04em;max-width:340px;pointer-events:none;opacity:0;transition:opacity .18s;z-index:9}
  .tip b{display:block;font-weight:400;font-size:13px;letter-spacing:.14em;color:#f0f5ff;
    text-shadow:0 0 18px rgba(150,190,255,.6)}
  .tip s{display:block;text-decoration:none;margin-top:5px;font-size:10px;letter-spacing:.08em;color:#bcd0ea}
  .tip .sg{margin-top:7px;display:grid;row-gap:4px}
  .tip .sgr{display:grid;grid-template-columns:52px 1fr;column-gap:10px;align-items:baseline;font-size:10px;letter-spacing:.06em;color:#bcd0ea;line-height:1.45}
  .tip .sgr i{font-style:normal;font-size:7.5px;letter-spacing:.28em;text-transform:uppercase;color:rgba(190,205,255,.42)}
  .tip .sgr.st{grid-template-columns:1fr;font-size:11px;color:#eaf1ff;margin-bottom:3px}
  .tip u{display:block;text-decoration:none;margin-top:8px;padding-top:8px;
    border-top:1px solid rgba(255,255,255,.07)}
  .tip p{display:grid;grid-template-columns:9px 1fr;column-gap:8px;align-items:baseline;margin:0 0 5px;
    font-size:9.5px;line-height:1.6;letter-spacing:.03em;color:rgba(198,213,255,.72)}
  .tip p:last-child{margin-bottom:0}
  .tip p em{width:5px;height:5px;border-radius:50%;margin-top:5px;
    box-shadow:0 0 8px currentColor;filter:drop-shadow(0 0 4px rgba(255,255,255,.25))}
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

  /* ── СПУТНИК КНИГИ (16.09, владелец: «космический недвижимый элемент… добавь сияния»):
     переход на экран бота. Неподвижен — движется только свет: корона дышит, лучи мерцают
     вразнобой, искры дрейфуют по кольцу, по шару скользит блик. ── */
  .moon{position:fixed;left:7%;bottom:15%;width:230px;height:230px;cursor:pointer;z-index:6}
  .moon svg{position:absolute;inset:0;overflow:visible}
  .moon .glowpad{position:absolute;left:50%;top:48%;width:320px;height:320px;transform:translate(-50%,-50%);pointer-events:none;
    background:radial-gradient(circle,rgba(150,190,255,.13),rgba(120,160,255,.05) 45%,transparent 70%);filter:blur(14px)}
  .moon .cap{position:absolute;left:50%;transform:translateX(-50%);bottom:-6px;white-space:nowrap;
    font-family:var(--f-cap,Jost);font-size:9.5px;letter-spacing:.44em;text-transform:uppercase;color:#a9bde8;
    text-shadow:0 0 14px rgba(150,190,255,.45);transition:color .4s}
  .moon .sub{position:absolute;left:50%;transform:translateX(-50%);bottom:-24px;white-space:nowrap;
    font-family:var(--f-cap,Jost);font-size:6.5px;letter-spacing:.36em;text-transform:uppercase;color:#6d7ea6;transition:color .4s}
  .moon:hover .cap{color:#eaf2ff}.moon:hover .sub{color:#ffd9a8}.moon:hover .mcorona{opacity:.95}
  .mcorona{transform-origin:130px 126px;animation:mbreathe 9s ease-in-out infinite;transition:opacity .6s}
  @keyframes mbreathe{0%,100%{opacity:.5;transform:scale(1)}50%{opacity:.9;transform:scale(1.045)}}
  @keyframes mterm{0%,100%{opacity:.55}50%{opacity:.95}}
  @keyframes mray{0%,100%{opacity:.18}50%{opacity:.62}}
  @keyframes mwink{0%,100%{opacity:.2}50%{opacity:.9}}
  @keyframes mdrift{to{transform:rotate(360deg)}}
  @keyframes msheen{0%{opacity:0}18%{opacity:.5}36%{opacity:0}100%{opacity:0}}
  #mlim{animation:mterm 7s ease-in-out infinite}
  #mrays line{animation:mray 6s ease-in-out infinite}
  #msheen{animation:msheen 11s ease-in-out infinite}
  #msp1{transform-origin:130px 130px;animation:mdrift 140s linear infinite}
  #msp2{transform-origin:130px 130px;animation:mdrift 200s linear infinite reverse}
</style>
</head>
<body>
<canvas id="c"></canvas>
<canvas id="fx"></canvas>
<div class="flow" id="flow">
  <div class="t">поток рыночных заявок</div>
  <div class="rail"><i></i>
    <span class="val" id="fval">—</span>
    <span class="bead" id="bead"></span>
    <span class="mark" id="fmark"><u>разворот</u></span>
  </div>
  <div class="ends"><em class="l">продают</em><em class="r">покупают</em></div>
</div>
<div class="moon" id="moon" title="книга бота" style="display:none">
  <div class="glowpad"></div>
  <svg viewBox="0 0 260 260">
    <defs>
      <radialGradient id="mbody" cx="34%" cy="30%" r="78%">
        <stop offset="0" stop-color="#5c6f9e"/><stop offset="42%" stop-color="#2b3559"/><stop offset="100%" stop-color="#0d1226"/>
      </radialGradient>
      <radialGradient id="mglow" cx="50%" cy="50%" r="50%">
        <stop offset="55%" stop-color="rgba(150,190,255,0)"/><stop offset="100%" stop-color="rgba(150,190,255,.20)"/>
      </radialGradient>
      <radialGradient id="mcor" cx="50%" cy="50%" r="50%">
        <stop offset="0" stop-color="rgba(170,205,255,.30)"/><stop offset="38%" stop-color="rgba(150,190,255,.14)"/>
        <stop offset="72%" stop-color="rgba(120,160,255,.05)"/><stop offset="100%" stop-color="rgba(120,160,255,0)"/>
      </radialGradient>
      <radialGradient id="mwarm" cx="30%" cy="26%" r="46%">
        <stop offset="0" stop-color="rgba(255,236,200,.22)"/><stop offset="100%" stop-color="rgba(255,220,170,0)"/>
      </radialGradient>
      <linearGradient id="mring" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="rgba(190,215,255,0)"/><stop offset="30%" stop-color="rgba(190,215,255,.55)"/>
        <stop offset="70%" stop-color="rgba(190,215,255,.25)"/><stop offset="100%" stop-color="rgba(190,215,255,0)"/>
      </linearGradient>
      <filter id="msoft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>
    </defs>
    <g id="mrays" filter="url(#msoft)"></g>
    <circle class="mcorona" cx="130" cy="126" r="132" fill="url(#mcor)"/>
    <circle cx="130" cy="126" r="96" fill="url(#mglow)" opacity=".3"/>
    <ellipse cx="130" cy="130" rx="112" ry="30" fill="none" stroke="url(#mring)" stroke-width="1.1" transform="rotate(-17 130 130)"/>
    <ellipse cx="130" cy="130" rx="92" ry="24" fill="none" stroke="rgba(190,215,255,.13)" stroke-width=".8" transform="rotate(-17 130 130)"/>
    <circle cx="130" cy="126" r="62" fill="url(#mbody)"/>
    <path id="mlim" d="M 130 64 A 62 62 0 0 0 130 188 A 44 62 0 0 1 130 64 Z" fill="rgba(200,224,255,.16)"/>
    <circle cx="106" cy="104" r="9" fill="rgba(10,16,34,.42)"/>
    <circle cx="146" cy="146" r="6" fill="rgba(10,16,34,.36)"/>
    <circle cx="118" cy="152" r="4" fill="rgba(10,16,34,.30)"/>
    <circle cx="130" cy="126" r="62" fill="url(#mwarm)"/>
    <path id="msheen" d="M 92 78 A 62 62 0 0 0 92 174 A 30 62 0 0 1 92 78 Z" fill="rgba(215,235,255,.22)"/>
    <g id="msp1"></g><g id="msp2"></g>
  </svg>
  <div class="cap">книга</div>
  <div class="sub" id="msub">перейти</div>
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
// МЕСТНОЕ ТОЛЬКО НА ЭКРАНЕ (16.09): метки ⟦t:секунды⟧ в строках — в часы смотрящего
(function(){const p=n=>(n<10?'0':'')+n, loc=t=>{const d=new Date(t*1000);return p(d.getDate())+'.'+p(d.getMonth()+1)+' '+p(d.getHours())+':'+p(d.getMinutes());};
  const fx=s=>typeof s==='string'?s.replace(/⟦t:(\d+)⟧/g,(m,t)=>loc(+t)):s;
  DATA.whys=(DATA.whys||[]).map(fx); DATA.subs=(DATA.subs||[]).map(fx);})();
// группы: 0 — брать, 1 — держать, 2 — закрыть (владелец, 06.09)
const names=DATA.names.length?DATA.names:['—'],GRP=DATA.names.length?DATA.grp:[1];
const N=names.length,NF=4,FONT='Michroma';
const POS=DATA.names.length?DATA.pos:[[.5,.5]];
const LAB=DATA.label||[];
// ── СПУТНИК КНИГИ (16.09): лучи и искры строятся кодом, элемент виден только когда есть позиции
(function(){
  const box=document.getElementById('moon'); if(!box) return;
  const n=DATA.book||0; if(!n){box.remove();return}
  box.style.display='block';
  const sub=document.getElementById('msub'); if(sub) sub.textContent=n+' в позиции · перейти';
  let s='';
  for(let i=0;i<10;i++){
    const a=(i/10)*Math.PI*2+0.3, r0=96, r1=r0+26+Math.random()*58;
    const x1=130+Math.cos(a)*r0, y1=126+Math.sin(a)*r0, x2=130+Math.cos(a)*r1, y2=126+Math.sin(a)*r1;
    s+='<line x1="'+x1.toFixed(1)+'" y1="'+y1.toFixed(1)+'" x2="'+x2.toFixed(1)+'" y2="'+y2.toFixed(1)+
       '" stroke="rgba(190,218,255,.85)" stroke-width="'+(0.9+Math.random()*1.1).toFixed(2)+
       '" stroke-linecap="round" style="animation-duration:'+(5+Math.random()*5).toFixed(1)+
       's;animation-delay:-'+(Math.random()*6).toFixed(1)+'s"/>';
  }
  document.getElementById('mrays').innerHTML=s;
  const spark=(id,rx,ry,cnt,col)=>{const g=document.getElementById(id);let t='';
    for(let i=0;i<cnt;i++){const a=Math.random()*Math.PI*2,x=130+Math.cos(a)*rx,y=130+Math.sin(a)*ry;
      t+='<circle cx="'+x.toFixed(1)+'" cy="'+y.toFixed(1)+'" r="'+(0.7+Math.random()).toFixed(1)+'" fill="'+col+
         '" style="animation:mwink '+(3+Math.random()*5).toFixed(1)+'s ease-in-out infinite;animation-delay:-'+(Math.random()*6).toFixed(1)+'s"/>';}
    g.setAttribute('transform','rotate(-17 130 130)');g.innerHTML=t;};
  spark('msp1',112,30,14,'#cfe4ff'); spark('msp2',92,24,9,'rgba(200,225,255,.7)');
  box.addEventListener('click',ev=>{ev.stopPropagation();
    if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'book'},'*')}catch(e){}}
    location.href='book.html';});
})();
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
  float er=0.;   // 19.09: третья группа теперь «пошли», не «закрыть» — эрозии букв нет
  core*=1.-er*.9;soft*=1.-er*.75;
  float near_=smoothstep(.16,.04,best)*inbox;
  float drift=0.;   // 19.09: и сдува нет
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
  // ЯРКОСТЬ ГАСИТ ВСЁ ИМЯ ЦЕЛИКОМ (08.09): BR входил только в lvl — два слагаемых из десяти, а
  // зерно, дрейф и ореолы групп рисовались мимо него. Теперь множитель на самой видимости, и не
  // линейный, а в квадрате: белый текст на тёмном при 10% всё ещё читался («скрывается всё, кроме
  // названия»), в квадрате это уже один процент — имя пропадает вместе со всем остальным.
  float bdim = clamp(Bi, 0., 1.);
  vis *= bdim * bdim;
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
    if(window.__BLANK && !LAB[i] && !window.__KEEP.has((DATA.syms||[])[i])) continue;   // фон давит: имя в маску не пишем (10.09)
    // подписи групп — кириллицей, Michroma её не знает: Inter, чуть крупнее и с разрядкой
    const isStale=(DATA.grp||[])[i]===4;
    m.font=LAB[i]?`300 ${size*(isStale?.78:.92)}px "Inter",system-ui,sans-serif`:`400 ${size*(isStale?.66:.935)}px "${FONT}",system-ui,sans-serif`;   // остывшие мельче (07.09)
    m.letterSpacing=LAB[i]?'0.32em':'0.12em';
    // РОВНЫЙ СВЕТ НА ЛЮБОЙ ШИРИНЕ (09.09, владелец показал сравнение: на узком экране ярче, на
    // широком тусклее). Причина не в яркости: кегль имени упирается в потолок 21px, и радиус
    // ореола, считанный от кегля, дальше не растёт — а экран растёт, и свет тонет в пустоте.
    // Растягиваем только РАЗМЫТИЕ, буквы не трогаем: на 1440 множитель единица (узкий экран как
    // был), к 2560 плавно до полутора — там ореол становится шире и звезда снова видна.
    const kg=Math.min(1.5,Math.max(1,W/1440));
    m.fillStyle='#0f0';m.filter=`blur(${size*.16*kg}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
    m.fillStyle='#00f';m.filter=`blur(${size*.035*kg}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
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
    if(window.__BLANK && !LAB[i] && !window.__KEEP.has((DATA.syms||[])[i])) continue;   // фон давит: имя в маску не пишем (10.09)
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
// МЕТКИ РИСУЮТСЯ ПОСЛЕ РАСЧЁТА РАЗМЕРОВ (09.09, владелец: «спутник появляется не всегда — если
// повернуть планшет, то они появляются; и на компьютере, если уменьшить или увеличить экран»).
// Причина: спутники и пузыри рисовались один раз при загрузке, когда W, H и позиции звёзд ещё не
// посчитаны — координаты выходили нулевыми, и метки уезжали за экран. На resize всё
// пересчитывалось, и они вставали на место. Теперь у слоёв общий список перерисовки: resize
// вызывает его сам, и он же вызывается один раз после первого расчёта размеров.
const REDRAW=[];
function resize(){const d=Math.min(devicePixelRatio,1.5);W=innerWidth;H=innerHeight;
  c.width=W*d;c.height=H*d;gl.viewport(0,0,c.width,c.height);gl.uniform2f(uR,c.width,c.height);mask();
  REDRAW.forEach(f=>{try{f()}catch(e){}});}
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
    // ЧУЖИЕ — ПРОЗРАЧНОСТЬ 10% (08.09, владелец): не доля от своей яркости, а один уровень для всех
    // чужих, иначе яркие оставались заметнее тусклых. Было 0.12 от собственной, стало ровно 0.1.
    out[i]=mine?BR0[i]*((PICK!==null&&mine&&!LAB[i])?1.15:1):0.1;
  }
  gl.uniform1fv(U('BR'),out);
}
// ПЛЕЧО КОПИТСЯ — СПУТНИК СПРАВА СВЕРХУ (09.09, владелец: «убери вращение по орбите, пусть
// справа сверху просто немного двигаются»). Никакой анимации в кадре: точка стоит у имени и
// чуть покачивается средствами CSS. Позиция пересчитывается только при сборке и на resize.
(function(){
  const AC=DATA.accum||{}; if(!Object.keys(AC).length)return;
  const host=document.createElement('div'); document.body.appendChild(host);
  function place(){
    host.innerHTML='';
    (DATA.names||[]).forEach((nm,i)=>{
      if(LAB[i]||(window.__BLANK && !window.__KEEP.has((DATA.syms||[])[i])))return;
      const a=AC[nm]; if(!a)return;
      const x=W*POS[i][0], y=H*POS[i][1];
      const dx=nm.length*SIZE*0.34+16, dy=SIZE*0.62+8;   // справа сверху от имени
      const el=document.createElement('div');
      el.className='sat'+(a.past?' past':(a.strong?' strong':''));
      el.style.left=(x+dx)+'px'; el.style.top=(y-dy)+'px';
      el.style.animationDelay=(-(i%7)*0.6)+'s';
      const tip=document.createElement('div');
      tip.className='sattip'+(a.past?' past':'');
      // ЦИФРА ОРАНЖЕВАЯ И ВЫШЕ ЛУЧА (09.09, владелец: «число дней перекрывается белым лучом,
      // лучше сделать цифру оранжевой»): белый луч спутника проходил ровно по подписи.
      tip.innerHTML = a.past ? `копилось <b>${a.ago}</b> дн назад` : `плечо <b>+${a.oi3}%</b>`;
      tip.style.left=(x+dx)+'px'; tip.style.top=(y-dy-14)+'px';
      host.appendChild(el); host.appendChild(tip);
    });
  }
  REDRAW.push(place);
  if(W) place();          // при загрузке размеры ещё не посчитаны — рисует resize()
})();

// ДВА ПОСЛЕДНИХ ПУЗЫРЯ ПОД ИМЕНЕМ (09.09): слева от состояния, слева направо по времени
(function(){
  const B=DATA.bub||{}; if(!Object.keys(B).length)return;
  const host=document.createElement('div'); document.body.appendChild(host);
  function place(){
    host.innerHTML='';
    (DATA.names||[]).forEach((nm,i)=>{
      if(LAB[i]||(window.__BLANK && !window.__KEEP.has((DATA.syms||[])[i])))return;
      const b=B[nm]; if(!b||!b.length)return;
      const x=W*POS[i][0], y=H*POS[i][1];
      b.forEach((p,k)=>{
        const el=document.createElement('div');
        el.className='bub '+(p.buy?'buy':'sell')+(p.doubt?' half':'');
        el.style.left=(x - nm.length*SIZE*0.31 - 14 + k*11)+'px';
        el.style.top=(y + SIZE*0.62)+'px';
        host.appendChild(el);
      });
    });
  }
  REDRAW.push(place);
  if(W) place();          // при загрузке размеры ещё не посчитаны — рисует resize()
})();

// ── ФОН ДАВИТ: ЗВЁЗД НЕТ, ПО ЦЕНТРУ СВЕТИЛО (10.09) ──────────────────────────────────────────
// Гасить яркостью мало: имена запекаются в маску, а орбиты и подписи рисует канва — все три
// слоя знают про флаг. Верхняя панель лидера при этом не показывается: её текст внизу.
window.__BLANK = !!(DATA.blank && DATA.blank.why);
window.__KEEP = new Set((DATA.keep || []).concat(((DATA.syms || []).filter(function (s, i) { return (DATA.grp || [])[i] === 0 && s; }))));   // 24.09: «скоро» видно при любой доске   // первые, которые держались ≥3 прогонов за сутки: на них не действуют никакие гашения (11.09)
if (window.__BLANK) {
  const d = document.createElement('div');
  d.className = 'blank' + ((window.__KEEP && window.__KEEP.size) ? ' aside' : '');
  d.innerHTML = `<div class="sun"><div class="far"></div><div class="halo"></div><div class="arm"><i style="--a:224.2deg;--r:165px;animation-duration:6.3s;animation-delay:5.9s"></i><i style="--a:266.4deg;--r:187px;animation-duration:3.5s;animation-delay:1.6s"></i><i style="--a:339.6deg;--r:203px;animation-duration:3.6s;animation-delay:0.6s"></i><i style="--a:133.8deg;--r:151px;animation-duration:4.8s;animation-delay:0.5s"></i><i style="--a:89.8deg;--r:147px;animation-duration:4.9s;animation-delay:0.9s"></i><i style="--a:312.3deg;--r:169px;animation-duration:4.0s;animation-delay:3.2s"></i><i style="--a:50.0deg;--r:199px;animation-duration:5.0s;animation-delay:0.7s"></i><i style="--a:350.0deg;--r:120px;animation-duration:4.2s;animation-delay:0.9s"></i><i style="--a:353.7deg;--r:141px;animation-duration:4.4s;animation-delay:4.2s"></i><i style="--a:194.1deg;--r:200px;animation-duration:4.1s;animation-delay:3.9s"></i><i style="--a:248.6deg;--r:169px;animation-duration:4.5s;animation-delay:1.6s"></i><i style="--a:59.7deg;--r:138px;animation-duration:4.3s;animation-delay:1.4s"></i><i style="--a:294.3deg;--r:195px;animation-duration:3.4s;animation-delay:2.3s"></i><i style="--a:121.6deg;--r:159px;animation-duration:4.7s;animation-delay:1.4s"></i><i style="--a:250.7deg;--r:143px;animation-duration:5.1s;animation-delay:3.6s"></i><i style="--a:20.5deg;--r:122px;animation-duration:6.8s;animation-delay:2.4s"></i><i style="--a:145.5deg;--r:190px;animation-duration:6.2s;animation-delay:2.3s"></i><i style="--a:208.3deg;--r:121px;animation-duration:5.0s;animation-delay:3.5s"></i><i style="--a:224.5deg;--r:145px;animation-duration:3.8s;animation-delay:0.9s"></i><i style="--a:295.0deg;--r:179px;animation-duration:4.6s;animation-delay:1.6s"></i><i style="--a:188.9deg;--r:179px;animation-duration:3.8s;animation-delay:2.8s"></i><i style="--a:287.0deg;--r:157px;animation-duration:3.5s;animation-delay:3.3s"></i><i style="--a:32.8deg;--r:163px;animation-duration:5.2s;animation-delay:1.9s"></i><i style="--a:53.4deg;--r:155px;animation-duration:6.7s;animation-delay:3.7s"></i><i style="--a:112.5deg;--r:160px;animation-duration:4.5s;animation-delay:3.6s"></i><i style="--a:225.7deg;--r:159px;animation-duration:7.0s;animation-delay:1.1s"></i><i style="--a:17.5deg;--r:196px;animation-duration:5.3s;animation-delay:2.2s"></i><i style="--a:85.4deg;--r:196px;animation-duration:4.6s;animation-delay:1.2s"></i><i style="--a:234.3deg;--r:138px;animation-duration:3.6s;animation-delay:3.3s"></i><i style="--a:11.8deg;--r:183px;animation-duration:4.6s;animation-delay:1.0s"></i><i style="--a:353.3deg;--r:192px;animation-duration:6.8s;animation-delay:4.3s"></i><i style="--a:283.7deg;--r:133px;animation-duration:4.0s;animation-delay:1.5s"></i><i style="--a:21.2deg;--r:173px;animation-duration:4.5s;animation-delay:2.0s"></i><i style="--a:359.7deg;--r:141px;animation-duration:6.9s;animation-delay:3.1s"></i></div><div class="rr" style="width:178px;transform:rotate(7deg);animation-duration:5.4s;animation-delay:0s"></div><div class="rr" style="width:126px;transform:rotate(41deg);animation-duration:6.8s;animation-delay:0.9s"></div><div class="rr" style="width:205px;transform:rotate(88deg);animation-duration:4.9s;animation-delay:2.1s"></div><div class="rr" style="width:148px;transform:rotate(133deg);animation-duration:7.6s;animation-delay:1.3s"></div><div class="rr" style="width:190px;transform:rotate(176deg);animation-duration:5.9s;animation-delay:3.0s"></div><div class="rr" style="width:118px;transform:rotate(214deg);animation-duration:6.2s;animation-delay:0.4s"></div><div class="rr" style="width:168px;transform:rotate(258deg);animation-duration:8.1s;animation-delay:2.6s"></div><div class="rr" style="width:138px;transform:rotate(299deg);animation-duration:5.1s;animation-delay:1.7s"></div><div class="rr" style="width:196px;transform:rotate(338deg);animation-duration:7.0s;animation-delay:0.2s"></div><div class="core"></div></div><div class="say"><i>сегодня брать нечего</i><b>доска давит</b><s>растёт <w>42</w> из <w>110</w> · медиана <w>−1.10%</w> · лидера нет</s></div>`;
  const say = d.querySelector('.say');
  if (say) {
    say.innerHTML = '<i>сегодня брать нечего</i><b>' + DATA.blank.why + '</b>'
      + '<s>' + String(DATA.blank.note || '').replace(/(\d+[.,]?\d*%?)/g, '<w>$1</w>') + '</s>';
  }
  document.body.appendChild(d);
}
const tip=document.getElementById('tip');
c.addEventListener('mousemove',ev=>{const j=hit(ev,true),i=hit(ev);
  c.style.cursor=(j>=0)?'pointer':'default';
  const hg=(j>=0&&LAB[j])?(DATA.grp||[])[j]:null;
  if(hg!==HOVER){HOVER=hg;applyGroup();}
  if(i>=0){
    const sub=(DATA.subs||[])[i]||'', why=(DATA.whys||[])[i]||'';
    if(sub||why){
      // ТОЧКА У КАЖДОЙ ПРИЧИНЫ (08.09, владелец: «чтобы не выглядело простынёй»): цвет по смыслу —
      // мятный за монету, коралловый против, янтарный про плечо и сбор, холодный про режим.
      const dotOf=t=>{
        t=t.toLowerCase();
        if(/выход|осечк|отпустил|ушёл|вынос|раздач|против|не удерж/.test(t))return '#ff9078';
        if(/сбор|плечо|шорт|оборот/.test(t))return '#ffc069';
        if(/режим|лестниц|парабол|двигатель/.test(t))return '#8fb4e8';
        if(/удерж|спрос|покуп|набир|рос/.test(t))return '#4fe3b8';
        return '#8ea3ba';
      };
      const list=why?why.split(' · ').filter(Boolean)
        .map(w=>'<p><em style="background:'+dotOf(w)+'"></em>'+w+'</p>').join(''):'';
      // ГРУППЫ ПОДПИСИ (19.09): «статус ‖ очередь: … ‖ стык: … ‖ сбор: … ‖ режим: …» — каждая своей строкой,
      // подпись группы слева капителью; старая подпись без ‖ рисуется как раньше
      var subHtml='';
      if(sub&&sub.indexOf('‖')>=0){
        subHtml='<div class="sg">'+sub.split(' ‖ ').map(function(g,k){var m=g.match(/^([^:]{2,12}):\s*(.*)$/);
          return m?'<div class="sgr"><i>'+m[1]+'</i><span>'+m[2]+'</span></div>':'<div class="sgr st"><span>'+g+'</span></div>';}).join('')+'</div>';
      } else if(sub){ subHtml='<s>'+sub+'</s>'; }
      tip.innerHTML='<b>'+names[i]+'</b>'+subHtml+(list?'<u>'+list+'</u>':'');
      tip.style.left=Math.min(ev.clientX+14,innerWidth-380)+'px';
      tip.style.top=Math.min(ev.clientY+12,innerHeight-260)+'px';tip.style.opacity=1;
    } else tip.style.opacity=0;
  }
  else if(j>=0&&LAB[j]){tip.innerHTML='<b>'+names[j]+'</b><s>только эта группа · клик закрепляет</s>';tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+12)+'px';tip.style.opacity=1}
  else tip.style.opacity=0});
c.addEventListener('mouseleave',()=>{HOVER=null;applyGroup();tip.style.opacity=0});
function next(){try{window.parent.postMessage({type:'ob:done',screen:'intro'},'*')}catch(e){}
  if(window===window.parent)location.href='brief.html'}
c.addEventListener('click',ev=>{const j=hit(ev,true);
  // клик по подписи группы — фильтр, экран НЕ закрываем (07.09)
  if(j>=0&&LAB[j]){const go=(DATA.goes||[])[j];
    if(go){ if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'book'},'*')}catch(e){}}
            location.href=go; return }
    const g=(DATA.grp||[])[j];PICK=(PICK===g)?null:g;applyGroup();return}
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
    if(LAB[i]||(window.__BLANK && !window.__KEEP.has((DATA.syms||[])[i])))continue;
    const g=(DATA.grp||[])[i];
    if(PICK!==null&&g!==PICK)continue;
    // ЧУЖИЕ ГАСНУТ И НА КАНВЕ (08.09, владелец: «становятся тусклее, но процентов на пять»):
    // орбиты, хвосты и подписи рисуются вторым слоем — он про наведение на группу не знал вовсе,
    // поэтому имена оставались яркими, сколько ни уменьшай яркость в шейдере. Теперь при наведении
    // на категорию чужие тут тоже уходят в 10% — как и их свечение.
    const dimOther=(HOVER!==null&&g!==HOVER)?0.1:1;
    const F=Fv[i]*dimOther; if(F<=0.02)continue;
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
    // ── СУТКИ ПО КРУГУ (24.09, прототип владельца marks.html): история очереди на ОДНОЙ орбите — самой внешней,
    // снаружи всех остальных, поэтому ни на одну не налезает. 48 рисок = 48 получасов; засечка сверху — «сейчас»,
    // по часовой назад — прошлое. Янтарная риска — была первой в очереди; мятные риски с нитью до засечки — серия
    // подряд. Сверху мелко — метки «первая N подряд» и «первая N раз за сутки».
    const QH=(DATA.qh||{})[(DATA.syms||[])[i]];
    if(QH){
      let rmax=0;
      if(o.up!=null)rmax=Math.max(rmax,rr(o.up)*1.25);
      if(o.dn!=null)rmax=Math.max(rmax,rr(-o.dn)*1.25);
      if(o.low!=null&&o.high!=null)rmax=Math.max(rmax,K*3.4*1.2);
      if(o.unlock!=null&&o.unlock<=7)rmax=Math.max(rmax,K*(4.6-1.8*(1-o.unlock/7))*1.2);
      const RX=Math.max(K*4.4,rmax*1.14), RY=RX*.385, NS=QH.length, ST=(DATA.qs||{})[(DATA.syms||[])[i]]||0;
      const P=(u,r)=>{const ang=-Math.PI/2-u*2*Math.PI;                       // u=0 — сейчас, растёт в прошлое
        const ex=Math.cos(ang)*RX*r, ey=Math.sin(ang)*RY*r;
        return [cx+ex*Math.cos(tilt)-ey*Math.sin(tilt), cy+ex*Math.sin(tilt)+ey*Math.cos(tilt), Math.sin(ang)<0?.55:1];};
      fc.lineCap='round';
      for(let k=0;k<NS;k++){
        const u=(NS-1-k+.5)/NS, [x1,y1,dp]=P(u,.93), [x2,y2]=P(u,1.09);
        const on=QH[k], inS=on&&ST>=3&&k>=NS-ST;
        fc.strokeStyle=!on?'rgba(170,190,255,'+(.2*F*dp).toFixed(3)+')':(inS?'rgba(143,240,196,'+(.95*F*dp).toFixed(3)+')':'rgba(255,201,138,'+(.9*F*dp).toFixed(3)+')');
        fc.lineWidth=!on?1:(inS?2.2:1.7);
        if(on){fc.shadowColor=inS?'rgba(143,240,196,.9)':'rgba(255,201,138,.9)';fc.shadowBlur=6*F;}
        fc.beginPath();fc.moveTo(x1,y1);fc.lineTo(x2,y2);fc.stroke();fc.shadowBlur=0;
      }
      if(ST>=3){                                                              // нить серии до «сейчас»
        const u1=Math.min(1,ST/NS);
        fc.shadowColor='rgba(143,240,196,.9)';fc.shadowBlur=10*F;fc.lineWidth=1.2;
        fc.strokeStyle='rgba(201,255,230,'+(.85*F).toFixed(3)+')';fc.beginPath();
        for(let k=0;k<=48;k++){const [x,y]=P(u1*k/48,1.17);k?fc.lineTo(x,y):fc.moveTo(x,y);}
        fc.stroke();fc.shadowBlur=0;
      }
      const pls=.6+.4*Math.sin(t*2.6), [nx1,ny1]=P(0,.84), [nx2,ny2]=P(0,1.26);  // засечка «сейчас»
      fc.strokeStyle='rgba(234,244,255,'+(pls*F).toFixed(3)+')';fc.lineWidth=1.3;fc.beginPath();fc.moveTo(nx1,ny1);fc.lineTo(nx2,ny2);fc.stroke();
      bead(nx2,ny2,2.2,'#eaf4ff','rgba(234,244,255,.9)',pls*F);
      const TG=(DATA.qt||{})[(DATA.syms||[])[i]]||[];
      if(TG.length){fc.font=`400 ${SZ*.38}px "Inter",system-ui,sans-serif`;fc.textAlign='center';fc.textBaseline='middle';
        try{fc.letterSpacing='0.28em';}catch(e){}
        const top=Math.min(cy-SZ*1.6, P(0,1.26)[1]-SZ*.6);
        TG.forEach((tg,k)=>{fc.fillStyle=(/подряд/.test(tg)?'rgba(143,240,196,':'rgba(255,201,138,')+(.9*F).toFixed(2)+')';
          fc.fillText(tg.toUpperCase(),cx,top-k*SZ*.62);});
        try{fc.letterSpacing='0px';}catch(e){}}
    }
    // ── ПОДПИСЬ: три вида, переключаются кнопками (07.09, владелец: «тексты выглядят некрасиво»)
    // A — строка-шлейф: одна строка вбок, слова гаснут к хвосту; ничего не громоздится
    // B — два уровня: крупное слово «что сейчас» и одна мелкая строка под ним
    // C — капсулы: короткие пилюли в ряд, как метки на приборе
    // подпись группами (19.09): на экране — короткое из стыка («плечо +25%»), статус — первой; группы не печатаются
    const _raw=((DATA.subs||[])[i]||'');
    let subAll;
    if(_raw.indexOf('‖')>=0){
      const G=_raw.split(' ‖ '), st=G[0]||'', sx=(G.find(x=>x.indexOf('стык:')===0)||'').replace(/^стык:\s*/,'');
      const sxp=sx.split(' · ').filter(Boolean), last=sxp.find(x=>/^плечо/.test(x))||sxp[sxp.length-1]||'';
      subAll=st.split(' · ').filter(Boolean).concat(last?[last]:[]);
    } else subAll=_raw.split(' · ').filter(Boolean);
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
      // ПОЛНЫЙ РАЗБОР — ВО ВСПЛЫВАЮЩЕЕ, А НЕ ПОД ЗВЕЗДОЙ (08.09, владелец): под именем остаётся
      // одно слово состояния, вся строка показывается в подсказке у курсора — она не громоздится
      // на соседние звёзды и читается на любом фоне.
      const words=[state];
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
  const PULL=!!L.sym;
  // КАПСУЛЫ СЕССИЙ — ВСЕГДА (12.09): переход и открытие относятся к фону, а не к монете,
  // поэтому показываются и когда лидера нет. Подхват — только при лидере, он про него.
  // ПЕРЕХОД СЧИТАЕТСЯ НА КЛИЕНТЕ (19.09, владелец: «прогон раз в полчаса, эта надпись уже через минуту врёт»):
  // минуты до открытия и «открытие» берутся из часов браузера по таблице сессий (UTC: Сидней 21, Токио 0,
  // Лондон 7, Нью-Йорк 13), капсула пересчитывается каждые 30 секунд. Подхват — из прогона, он про монету.
  const SESS_OPEN=[[21,'Сидней'],[0,'Токио'],[7,'Лондон'],[13,'Нью-Йорк']];
  function sessCaps(){ var S=DATA.sess||{}, out='', now=Date.now(), d0=Math.floor(now/864e5)*864e5, ord=[];
      SESS_OPEN.forEach(function(se){ [-1,0,1].forEach(function(k){ ord.push([d0+k*864e5+se[0]*36e5, se[1]]); }); });
      ord.sort(function(a,b){return a[0]-b[0];});
      var last=null, next=null;
      for(var i=0;i<ord.length;i++){ if(ord[i][0]<=now) last=ord[i]; else if(!next) next=ord[i]; }
      if(next){ var m=Math.round((next[0]-now)/6e4);
        if(m<=60) out += '<u class="warn">скоро переход · '+next[1]+' через '+(m>=60?'1 ч':m<=0?'минуту':m+' мин')+'</u>'; }
      if(last && now-last[0]<=30*6e4) out += '<u class="state">открытие · '+last[1]+'</u>';
      if(S.pickup && L.sym) out += '<u class="'+(S.pickup.ok?'state':'hot')+'">'+S.pickup.text+'</u>';
      return '<span id="sesscaps">'+out+'</span>'; }
  const SESSCAPS=sessCaps();
  setInterval(function(){ var sc=document.getElementById('sesscaps'); if(!sc) return;
    var fresh=sessCaps().replace(/^<span id="sesscaps">|<\/span>$/g,''); if(sc.innerHTML!==fresh) sc.innerHTML=fresh; }, 30000);
  if(el&&L.sym&&PULL){
    el.className='lead'+(L.ended?' ended':'');
    // разделитель — ромб, чтобы числа не сливались в одну строку (09.09)
    var SEP=' <o>\u25c6</o> ';
    // ПОРЯДОК: СНАЧАЛА МОНЕТА, ПОТОМ СОСТОЯНИЕ (09.09, владелец: «давай просто местами поменяем,
    // вверху про монету, а ниже — тянет одна и вход закрыт»). Раньше состояние стояло первым
    // числом в строке и читалось как заголовок всего экрана, а не как признак этой монеты.
    // РИСКИ — СРАЗУ ПОД МОНЕТОЙ (09.09, владелец: «поставь коралловые прямо под монету, чтобы было
    // понятно, что это относится к монете»). Стояли последними, после «вход закрыт», и читались
    // как общее предупреждение экрана. Теперь порядок: имя → её числа → чем она опасна →
    // и только потом состояние и последствие для остальных.
    el.innerHTML='<i>сейчас ведёт</i><b>'+L.sym+'</b><s>'
      + String(L.line||'').split(' · ').join(SEP)
      + (L.hours?(SEP+L.hours+' ч в первых'):'')
      + (L.ended?(SEP+'конец в '+L.ended):'')+'</s>'
      + ((L.risk||[]).length ? '<em>'+L.risk.map(x=>'<i>'+x+'</i>').join('')+'</em>' : '')
      // СЕССИИ НА ПЕРВОМ ЭКРАНЕ (12.09, владелец: «за час показывать — аккуратно, скоро переход между
      // сессиями, потом сам переход, открытие Азии, и откупила ли новая сессия лидера»). Смена рук
      // происходит на стыке: пока он не пройден, ход не подтверждён, а после — видно, взяли или нет.
      + SESSCAPS
      + (L.state? '<u class="state">'+L.state+'</u>' : '')+
      ((L.runs_weak||0)>0&&!L.ended
        ? (Math.abs(L.run_pct||0)>=150
            ? '<u class="hot">ход '+Math.round(L.run_pct)+'% за день · интерес падает · '+L.runs_weak+' прогон без роста</u>'
            : '<u class="warn">ход '+Math.round(L.run_pct||0)+'% за день · '+L.runs_weak+' из 3 прогонов без роста интереса</u>')
        // ДУБЛЬ УБРАН (09.09, владелец: «в верхней строке уже есть „тянут 2“, а внизу пишется
        // „тянет одна“»): состояние живёт в строке над именем, здесь — только последствие.
        // СНЯТИЕ ПРИ МНОГИХ ЛИДЕРАХ (16.09): плашка живёт в JS и своей проверкой по разрыву, поэтому
        // питоновское снятие её не касалось — гасим здесь же и пишем, почему вход открыт.
        : ((DATA.many) ? '<u class="lift">'+((DATA.many.why)||'ограничения сняты')+'</u>'
            : ((L.lead_gap||0)>=5 ? '<u>вход в остальных закрыт</u>' : '')))
;
  } else if(el){
    if(SESSCAPS){ el.className='lead'; el.innerHTML='<i>фон</i>'+SESSCAPS; }
    else el.style.display='none';
  }
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
  // порог уже проверен в analytics_leaders — здесь только показ (09.09)
  const idx=DATA.names.indexOf(L.sym||'');
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
  // ФОН ПО ПРИЗНАКАМ (08.09, владелец: «нужно писать всё по отдельности — фон по монетам давит /
  // нейтральный / рост, биткоин падает / флэт / рост, и так далее»): строка на признак, состояние
  // выделено цветом по смыслу, число рядом мелким.
  // ПОТОК РЫНОЧНЫХ ЗАЯВОК — ОДИН РАЗ (13.09, владелец: «убери под ними прибор рыночных заявок,
  // он дублирует самый нижний такой же, нижний оставляем»). Внизу экрана стоит отдельная панель
  // .flow с той же величиной, поэтому из списка приборов фона строку убираем.
  const rows=(DATA.bgnote||[]).filter(r=>String(r[0])!=='поток рыночных заявок');
  if(!rows.length){el.style.display='none';return}
  const DIR={'давит':-1,'падает':-1,'продают':-1,'рост':1,'покупают':1,'нейтральный':0,'флэт':0,'вровень':0,'поровну':0};
  const ENDS={'монеты к медиане':['давит','рост'],'монеты':['давит','рост'],'медиана доски':['падает','рост'],'биткоин':['падает','рост'],'биткоин сейчас':['давит','тянет'],'очередь':['давит','рост'],'поток рыночных заявок':['продают','покупают']};
  // сессии в часах UTC — те же, что в фоне
  // ЧЕТЫРЕ СЕССИИ (12.09, владелец: «у нас 3 сессии, по факту их 4»). Сидней 21–6 UTC идёт через
  // полночь, поэтому рисуется двумя дугами — хвост суток и начало следующих.
  const SES=[['Сидней',21,24,'#ffd98a'],['Сидней',0,6,'#ffd98a'],['Токио',0,9,'#6fb4ff'],['Лондон',7,16,'#a98cff'],['Нью-Йорк',13,22,'#ffb26f']];
  const OPENS=[[21,'Сидней'],[0,'Токио'],[7,'Лондон'],[13,'Нью-Йорк']];
  // ДО СЛЕДУЮЩЕЙ СЕССИИ — ОТДЕЛЬНОЙ СТРОКОЙ (13.09, владелец: «до сессии Токио 1 ч 30 м»).
  // Часы и минуты, а не доли часа: смена рук идёт на стыке, и важно, сколько до него осталось.
  function leftTxt(h){ const hh=Math.floor(h), mm=Math.round((h-hh)*60);
    return (hh? hh+' ч ':'') + (mm? mm+' м' : (hh? '' : '0 м')); }
  const h=new Date().getUTCHours()+new Date().getUTCMinutes()/60;
  // служебные слова — серым, числа остаются светлыми
  function dim(txt){
    return String(txt).replace(/(растёт|из|за сутки|за час|нет данных|срез не пришёл|от дна недели)/g,
                               '<w>$1</w>');
  }
  // ЗНАЧОК БИТКОИНА (09.09, владелец): у строк про биткоин вместо слова — символ, чтобы они
  // читались как одна пара, а не как два разных признака.
  // ЗНАЧОК БИТКОИНА (09.09, владелец: «верни как было, просто шрифт у буквы тоньше»):
  // объёмная монета не пошла — вернули плоский контур, буква тонким штрихом вместо заливки.
  const BTC='<svg class="ico" viewBox="0 0 24 24" fill="none">'
    +'<circle cx="12" cy="12" r="9.2" stroke="currentColor" stroke-width="1.3"/>'
    +'<path d="M9.9 7.8h3.6c1.4 0 2.2.7 2.2 1.8s-.8 1.7-1.9 1.8c1.3.1 2.1.8 2.1 2 0 1.3-1 2.1-2.6 2.1H9.9V7.8z"'
    +' stroke="currentColor" stroke-width="1.15" stroke-linejoin="round"/>'
    +'<path d="M9.9 11.4h3.9" stroke="currentColor" stroke-width="1.15" stroke-linecap="round"/>'
    +'<path d="M11.2 6v1.8M13.5 6v1.8M11.2 15.5v1.8M13.5 15.5v1.8"'
    +' stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/>'
    // БЕГУЩЕЕ ПЯТНО ПО КОЛЬЦУ (09.09, владелец): короткая яркая дуга обходит окружность —
    // значок оживает, но ничего не мигает. Длина окружности при r=9.2 ≈ 57.8.
    +'<g class="btcrun"><circle cx="12" cy="12" r="9.2" fill="none" stroke="#fff3d0" stroke-width="1.3"'
    +' stroke-linecap="round" stroke-dasharray="6 51.8" opacity=".95"/></g></svg>';
  // БЕЗ ДАТЧИКА (09.09, владелец: «у второй надписи не нужен датчик»): «биткоин дальше» — это не
  // перевес двух сторон, а расстояние до плит. Нить с бусиной там врёт, поэтому просто строка.
  // ОДИН ПРИБОР БИТКОИНА (18.09, владелец): монета, под ней цена (это «сейчас»), рядом стрелка (это «дальше»),
  // всё остальное — во всплывашке при наведении. Стрелка — топливо по сторонам в трёх процентах: шорты сверху
  // к лонгам снизу больше единицы — вверх, меньше — вниз; яркость по величине перевеса. Нет среза — старые строки.
  function btcGauge(rNow, rNext){
    const B=DATA.btc||{}, M=B.map||{}, L=B.liq||{}, P=B.premium||{}, E=B.etf||{}, ST=B.stamp||{};
    if(!M.px) return (rNow?railGauge(rNow, BTC):'')+(rNext?plainRow(rNext, BTC):'');
    const usd=v=>{if(v==null)return '—';const a=Math.abs(v),s=v<0?'−':'';return s+(a>=1e9?'$'+(a/1e9).toFixed(2)+'B':a>=1e6?'$'+(a/1e6).toFixed(0)+'M':a>=1e3?'$'+(a/1e3).toFixed(0)+'K':'$'+a.toFixed(0));};
    const pc=(v,n)=>v==null?'—':((v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(n==null?2:n)+'%');
    const px=v=>v==null?'—':Math.round(v).toLocaleString('ru-RU').replace(/\u00a0/g,'\u202f');
    const ratio=+M.short_to_long_3pct||1, side=ratio>1.08?'up':ratio<0.92?'dn':'flat', pw=Math.min(1,Math.abs(ratio-1)/1.2);
    const arrow='<svg class="bt_arw '+side+'" viewBox="0 0 24 34" fill="none" style="--p:'+(0.35+0.65*pw).toFixed(2)+'">'
      +'<path d="M12 3 L12 31" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>'
      +'<path d="'+(side==='up'?'M5 11 L12 3 L19 11':side==='dn'?'M5 23 L12 31 L19 23':'M5 17 L19 17')+'" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    const A=M.above||{}, Bw=M.below||{}, an=A.nearest||{}, ad=A.densest||{}, bn=Bw.nearest||{}, bd=Bw.densest||{};
    const kv=(k,v,c)=>'<div class="bt_kv"><span>'+k+'</span><b class="'+(c||'')+'">'+v+'</b></div>';
    const zones=(M.zones||[]).slice().sort((a,b)=>b.price-a.price), mx=Math.max(1,...zones.map(z=>+z.usd||0));
    let rows='', cur=false;
    zones.forEach(z=>{ if(!cur&&z.price<M.px){rows+='<div class="bt_zc"><b>цена сейчас</b><span>'+px(M.px)+'</span></div>';cur=true;}
      const c=z.side==='шорты'?'sh':'lo';
      rows+='<div class="bt_z '+c+'"><span class="bt_zp">'+px(z.price)+'</span><span class="bt_zb"><i style="width:'+((+z.usd||0)/mx*100).toFixed(0)+'%"></i></span><span class="bt_zu">'+usd(z.usd)+'</span><span class="bt_zd">'+pc(z.pct,1)+'</span></div>';});
    if(!cur) rows+='<div class="bt_zc"><b>цена сейчас</b><span>'+px(M.px)+'</span></div>';
    const hm=(iso)=>{ if(!iso)return ''; const d=new Date(iso); return isNaN(d)?'':(d.getHours()<10?'0':'')+d.getHours()+':'+(d.getMinutes()<10?'0':'')+d.getMinutes(); };
    const tip='<div class="bt_tip">'
      +'<div class="bt_th">биткоин · срез прогона <em>'+hm(ST.candle)+'</em></div>'
      +'<div class="bt_big">'+px(M.px)+'<s>$</s></div>'
      +(rNow?'<div class="bt_sec">сейчас</div>'+kv(rNow[0],String(rNow[2]||rNow[1]||'').replace(/<[^>]+>/g,'')):'')
      +(rNext?kv(rNext[0],String(rNext[1]||'')+' · '+String(rNext[2]||'').replace(/<[^>]+>/g,'')):'')
      +'<div class="bt_sec">карта плит · ближняя и плотнейшая</div>'
      +kv('сверху ближняя',px(an.price)+' · '+pc(an.pct)+' · '+usd(an.usd),'sh')
      +kv('сверху плотнейшая',px(ad.price)+' · '+pc(ad.pct)+' · '+usd(ad.usd),'sh')
      +kv('снизу ближняя',px(bn.price)+' · '+pc(bn.pct)+' · '+usd(bn.usd),'lo')
      +kv('снизу плотнейшая',px(bd.price)+' · '+pc(bd.pct)+' · '+usd(bd.usd),'lo')
      +'<div class="bt_zones">'+rows+'</div>'
      +'<div class="bt_sec">топливо по сторонам</div>'
      +kv('в трёх процентах','шорты '+usd(A.usd_3pct)+' против лонгов '+usd(Bw.usd_3pct)+' · ×'+(M.short_to_long_3pct==null?'—':M.short_to_long_3pct),'sh')
      +kv('в десяти процентах','шорты '+usd(A.usd_10pct)+' против лонгов '+usd(Bw.usd_10pct)+' · ×'+(M.short_to_long_10pct==null?'—':M.short_to_long_10pct),'lo')
      +kv('цена процента вверх',usd(an.usd_per_pct)+' на процент')
      +kv('цена процента вниз',usd(bn.usd_per_pct)+' на процент')
      +'<div class="bt_sec">плечо и ликвидации</div>'
      +kv('интерес',usd(M.oi_usd)+' · '+pc(M.oi_chg24_pct,1)+' за сутки','gr')
      +(M.oi_btc?kv('интерес в монетах',Math.round(M.oi_btc).toLocaleString('ru-RU')+' BTC'):'')
      +kv('сожгли за сутки','шортов '+usd(L.short_24h_usd)+' против лонгов '+usd(L.long_24h_usd),'gr')
      +'<div class="bt_sec">спрос снаружи</div>'
      +kv('премия Coinbase',pc(P.last,3)+' · за сутки '+pc(P.min_24h,3)+'…'+pc(P.max_24h,3),(P.last||0)<0?'ro':'gr')
      +(P.hours_positive!=null?kv('часов в плюсе',P.hours_positive+' из 24'):'')
      +kv('ETF за день',usd(E.last_usd))
      +kv('ETF за пять дней',usd(E.sum5_usd)+(E.days_positive!=null?' · в плюс '+E.days_positive+' из 5':''),(E.sum5_usd||0)<0?'ro':'gr')
      +'<div class="bt_foot">срез собран '+hm(ST.written_at)+' · свеча '+hm(ST.candle)+'</div></div>';
    return '<div class="g btcg hot" tabindex="0"><div class="bt_face">'+BTC+'<div class="bt_pxw"><div class="bt_pxv">'+px(M.px)+'<s>$</s></div></div>'+arrow+'</div><div class="bt_tipwrap">'+tip+'</div></div>';
  }
  function plainRow(r, ico){
    return `<div class="g plain"><div class="t">${ico||''}${r[0]}</div>
      <div class="pv">${r[1]}</div><div class="pn">${dim(r[2]||'')}</div></div>`;
  }
  function railGauge(r, ico){
    const dir=DIR[r[1]], cls=dir>0?'up':(dir<0?'dn':'flat');
    let k=0.5; const num=parseFloat(String(r[3]||'').replace(',','.'));
    if(!isNaN(num)) k = Math.abs(num)<=1 ? num : Math.min(1,Math.max(0,0.5+num/40));
    const left=(12+Math.min(1,Math.max(0,k))*76).toFixed(0);
    const e=ENDS[r[0]]||['',''];
    return `<div class="g ${cls}"><div class="t">${ico||''}${r[0]}</div>
      <div class="rail"><i></i><span class="val" style="left:${left}%">${dim(r[2]||r[1])}</span>
        <span class="bead" style="left:${left}%"></span></div>
      <div class="ends"><em class="l">${e[0]}</em><em class="r">${e[1]}</em></div></div>`;
  }
  function leadGauge(r){
    // ПУСТОЙ ЛИДЕР — ЧЕСТНО (12.09, владелец: прибор рисовал «ни» и «одна от дна недели»)
    if(!r[2] || !String(r[2]).trim() || /^ни\b/i.test(String(r[2]).trim())){   // 19.09: «ни одна…» — лидера нет, а не имя «НИ»
      return `<div class="g lead"><div class="t">${r[0]}</div>
        <div class="ring" style="--p:0;opacity:.25"></div>
        <div class="lx"><b style="color:rgba(200,212,255,.45)">лидера нет</b><u><w>доска без ведущего</w></u></div></div>`;
    }
    const run=parseFloat(String(r[3]||'0'));
    const p=Math.min(100,Math.max(4,isNaN(run)?0:run/3));   // 300% хода = полное кольцо
    const name=(r[2]||'').split(' ')[0], val=(r[2]||'').split(' ')[1]||r[1];
    return `<div class="g lead"><div class="t">${r[0]}</div>
      <div class="ring" style="--p:${p.toFixed(0)}"></div>
      <div class="lx"><b>${name}</b><u>${val} <w>от дна недели</w></u></div></div>`;
  }
  function clockGauge(r){
    const arcs=SES.map(([n,a,b,c])=>
      `<span style="left:${(a/24*100).toFixed(1)}%;width:${((b-a)/24*100).toFixed(1)}%;background:${c};box-shadow:0 0 8px ${c}"></span>`).join('');
    const cur=[...new Set(SES.filter(([n,a,b])=>h>=a&&h<b).map(x=>x[0]))].join(', ');
    // ПЕРЕХОД БЛИЗКО (12.09, владелец: «за час до окончания сессии подсвечивать прибор и писать,
    // на какую переход»). Смена рук идёт на стыке — прибор должен предупредить заранее.
    // ОДИН ИСТОЧНИК ВРЕМЕНИ (12.09): если фон уже посчитал переход — берём его, иначе считаем сами.
    // Иначе прибор и капсулы под лидером показывают разное: капсулы из DATA.sess, прибор из new Date().
    // СЛЕДУЮЩАЯ — ТА, ЧТО ЕЩЁ НЕ ОТКРЫТА (13.09, владелец: «Сидней, Токио — до сессии Токио 1 ч 30 м?»).
    // Брать ближайшее открытие по часам нельзя: сессия может идти прямо сейчас, и подпись обещала
    // открыть уже открытое. Пропускаем те, что в списке идущих.
    const S=DATA.sess||{};
    const open=new Set((cur||'').split(', ').filter(Boolean));
    let nx='', left=24;
    OPENS.forEach(([oh,nm])=>{ if(open.has(nm)) return; let d=oh-h; if(d<=0) d+=24; if(d<left){left=d; nx=nm;} });
    if(!nx && S.next && S.in_h!=null){ nx=S.next; left=+S.in_h; }
    const soon=left<=1;
    // время до сессии — ярче остального (13.09, владелец): это единственное число в подписи
    const sub=`${cur||r[1]} · до сессии ${nx} <b class="tleft">${leftTxt(left)}</b>`;
    return `<div class="g${soon?' soon':''}"><div class="t">${r[0]}${soon?' <b class="sw">переход</b>':''}</div>
      <div class="clock"><div class="ln"></div>${arcs}
        ${soon?`<div class="edge" style="left:${(((h+left)%24)/24*100).toFixed(1)}%"></div>`:''}
        <div class="now" style="left:${(h/24*100).toFixed(1)}%"></div>
        <em style="left:0">00</em><em style="left:48%">12</em><em style="right:0">24</em></div>
      <div class="ends"><em class="l" style="top:2px">${sub}</em></div></div>`;
  }
  const rNow=rows.find(r=>r[0]==='биткоин сейчас'), rNext=rows.find(r=>r[0]==='биткоин дальше');
  el.innerHTML='<i class="hd">фон</i>'+rows.map(r=>
    r[0]==='лидер' ? leadGauge(r)
    : r[0]==='торги' ? clockGauge(r)
    : r[0]==='биткоин дальше' ? ''                   // 18.09: ушла в один прибор биткоина
    : r[0]==='деньги лидера' ? plainRow(r)          // откуда взял: снаружи / из соседей — не перевес сторон, строка (11.09)
    : r[0]==='биткоин сейчас' ? btcGauge(r, rNext)
    : railGauge(r)).join('');
})();
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
