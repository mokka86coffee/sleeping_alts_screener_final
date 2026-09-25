#!/usr/bin/env python3
"""ЭКРАН КНИГИ БОТА (16.09, владелец: «это торговый бот, подумай как лучше, на реальных данных без
моего участия, калибровать будем отдельно»). Вид — прототип book_proto-2 (16.09, принят): шар итога,
колонка дней, веер сделок дня по дуге, панель монеты по клику.

Читает открытые позиции и журналы трёх бумажных книг — paper_end (шорт по концу хода), paper_crowd
(спайк, рост на выносе, против толпы, перекупленность, провал, прокол дна, первый час Лондона) и
paper_fast (вортекс, хедж и флип), цену и суточный ход из near_move, стены из depth.

Экран (16.09, сцена по макету владельца bot_book_hud.html): шкала недели сверху, прибор выбранного дня в
центре (сегменты закрытых, дуга попаданий, точки открытых, итог бота в диске), слева «выходы», справа итог
дня к депозиту, колонки «закрыты» и «в работе», четыре панели монеты внизу и разбор открытой позиции в тех
же рамках. Шрифты и фон — модуль render_book_assets.py. Ниже — прежнее описание данных, оно не менялось:
  • ШАР — итог закрытых сделок за BOOK_DAYS дней в деньгах, число, попадания, лучший и худший день;
  • ДНИ — день бота по UTC (подпись даты и время сборки — в часах смотрящего): итог дня, столбики
    сделок, нить попаданий; ДЕПОЗИТ ДНЯ BOOK_DEPOSIT делится между ЗАКРЫТЫМИ сделками этого дня по весу
    правила (16.09: сложение процентов по одновременным сделкам врало, давало +182.8%);
  • ВЕЕР — сделки выбранного дня: закрытые с причиной выхода, открытые (день сегодняшний) с условием
    выхода с числом; у открытых деньги считаются от цены сейчас долей того же депозита и В ИТОГ ДНЯ НЕ
    ВХОДЯТ — итог дня только по закрытым, как было;
  • ПАНЕЛЬ — монета за все дни: итог, попадания, по правилам, лучшая и худшая, гистограмма всех
    закрытых сделок книги с подсветкой монеты.
Скрипт страницы только рисует — всё посчитано здесь и вшито JSON-ом.
Личного на экране нет: размер позиции и плечо не печатаются, «вес» — множитель правила бота.
Вызов как у прочих экранов: render_book() -> str, run.py кладёт в pages["book.html"].
"""
from __future__ import annotations

import json
import re
import statistics as st
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import BOOK_DEPOSIT, BOOK_DAYS
except ImportError:
    BOOK_DEPOSIT, BOOK_DAYS = 10_000.0, 10
# шрифты и фон сцены (16.09, макет владельца bot_book_hud.html) — отдельным модулем рядом, в страницу вставляются
try:
    from render_book_assets import HUD_CSS
except ImportError:
    HUD_CSS = ""                                  # без модуля — системные шрифты и тёмный фон

try:
    from core_config import PAPER_CROWD_STOP, PAPER_CROWD_HOLD
except ImportError:
    PAPER_CROWD_STOP, PAPER_CROWD_HOLD = 0.02, 6
try:
    from core_config import SPIKE_FUND_NEG, PAPER_FAST_OI_BARS
except ImportError:
    SPIKE_FUND_NEG, PAPER_FAST_OI_BARS = -0.01, 4
BAR_S = 1800                                  # получасовка — единица срока у ботов

try:
    from core_config import FIRST3_SIZE, FIRST3_TARGET, FIRST3_STREAK, FIRST3_BE, FIRST3_PAUSE_H
except ImportError:
    FIRST3_SIZE, FIRST3_TARGET, FIRST3_STREAK, FIRST3_BE, FIRST3_PAUSE_H = 500.0, 0.40, 3, 0.20, 48

BOOKS = (("конец", "paper_end"), ("толпа", "paper_crowd"), ("быстрые", "paper_fast"),
         ("дно", "paper_bottom"),       # 17.09: лонг на белом пузыре 4ч у дна, выход «рука ушла» (paper_bottom.py)
         ("3 в первых подряд", "paper_first3"))
# СВОЯ СУММА НА СДЕЛКУ (24.09, владелец: «делай по 500$ на сделку, у нового бота другие правила»): такие книги
# в делёжку депозита дня не входят, деньги сделки — сумма × результат.
FIXED = {"paper_first3": FIRST3_SIZE}
# ЗАДНИМ ЧИСЛОМ (16.09, paper_backfill.py): реконструкция правил по архиву cq_v2/intraday. С живыми не
# смешивается — живой журнал свидетельствует о работе бота, backfill только сравнивает правила (в нём нет
# события доски, запрета встречных позиций и задержек). На экране — отдельный источник, кнопкой.
BACKFILL = (("конец", "paper_end_backfill"), ("толпа", "paper_crowd_backfill"))


def _read(name: str):
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _lines(name: str) -> list[dict]:
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        if not p.exists():
            continue
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    return []


def _px(v) -> str:
    if v is None:
        return "—"
    return f"{float(v):.6g}"


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _utc_day(ts) -> str:
    """день бота — по UTC: граница одна для всех, деньги сделки не зависят от пояса смотрящего"""
    try:
        return datetime.fromtimestamp(float(ts), timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return ""


def _live_px() -> dict:
    """цена сейчас и ход монеты за сутки — из сводки прогона"""
    out = {}
    nm = _read("near_move.json") or {}
    for sym, v in (nm.get("coins") or {}).items():
        t = v.get("today") or {}
        n = v.get("nums") or {}
        out[str(sym).upper()] = (t.get("px") or n.get("px_now"), t.get("px_chg_pct"))
    return out


def _bars_since(t_ms, minutes: int = 30) -> int:
    try:
        return max(0, int((_now() - float(t_ms) / 1000) / (minutes * 60)))
    except (TypeError, ValueError):
        return 0


def _walls(sym: str) -> str:
    """ближайший потолок и пол из стакана — коротко"""
    dp = ((_read("depth.json") or {}).get("coins") or {}).get(sym) or {}
    ws = dp.get("walls") or []
    a = sorted([w for w in ws if w.get("side") == "ask" and (w.get("dist_pct") or 0) > 0], key=lambda w: w["dist_pct"])
    b = sorted([w for w in ws if w.get("side") == "bid" and (w.get("dist_pct") or 0) < 0], key=lambda w: -w["dist_pct"])
    parts = []
    if a:
        parts.append(f"потолок {_px(a[0]['px'])} ({a[0]['dist_pct']:+.1f}%)")
    if b:
        parts.append(f"пол {_px(b[0]['px'])} ({b[0]['dist_pct']:+.1f}%)")
    return " · ".join(parts)


def _short_rule(book: str, rule: str) -> str:
    """имя правила для веера и разреза «по правилам»: до двоеточия («конец: интерес −2%…» → «конец»);
    у быстрых правило одно — вортекс, текст события живёт в причине"""
    if book == "быстрые":
        return "вортекс"
    if book == "дно":
        return "пузырь у дна"
    if book == "3 в первых подряд":
        return book
    s = str(rule or "").split(":")[0].strip()
    return s or book


def _side_closed(stem: str, r: dict) -> int:
    kind = str(r.get("kind") or "")
    if kind == "exit_long":
        return 1
    if kind == "exit_short":
        return -1
    if r.get("side") is not None:
        return 1 if float(r["side"]) > 0 else -1
    return -1 if stem == "paper_end" else 1


def _closed_rows(stem: str, book: str, cut: float) -> list[dict]:
    """закрытые сделки журнала: kind exit / exit_long / exit_short, не раньше cut"""
    out = []
    for r in _lines(f"{stem}.jsonl"):
        if not str(r.get("kind") or "").startswith("exit"):
            continue
        at = r.get("at") or 0
        if at < cut or r.get("result_pct") is None:
            continue
        rule = r.get("rule") or r.get("why") or ""
        bk = r.get("book") or book
        out.append({
            "book": bk, "sym": str(r.get("sym") or "").upper(), "side": _side_closed(stem, r),
            "res": float(r["result_pct"]), "why": r.get("why_exit") or "", "rule": rule,
            "rk": _short_rule(bk, rule), "size": float(r.get("size") or 1.0), "at": at,
            "ent": r.get("entry_at") or r.get("opened_at") or 0, "day": _utc_day(at),
            "fixed": FIXED.get(stem), "usd": r.get("usd"),
        })
    return out


def _collect() -> tuple[list[dict], list[dict]]:
    """открытые позиции всех книг и закрытые сделки за BOOK_DAYS дней"""
    live_px = _live_px()
    opened, closed = [], []
    cut = _now() - BOOK_DAYS * 86400
    for book, stem in BOOKS:
        st_ = _read(f"{stem}.json") or {}
        for sym, p in (st_.get("open") or {}).items():
            sym = str(sym).upper()
            if stem == "paper_first3":
                # у этой книги время входа в «at», сигнальный бар — последняя закрытая получасовка на входе
                at0 = int(p.get("at") or 0)
                p = dict(p, opened_at=at0, t=(at0 // 1800 * 1800 - 1800) * 1000, target=FIRST3_TARGET,
                         rule=f"первая {FIRST3_STREAK} получасовки подряд"
                              + (" · стоп в точке входа" if p.get("armed") else ""))
            px_now, d24 = live_px.get(sym, (None, None))
            legs = p.get("legs") or {}
            # сторона: у paper_end бот только шортит, у paper_crowd она в записи, у paper_fast — в
            # состоянии позиции (long / hedged / short); у хеджированной ход считаем по лонговой ноге
            side = p.get("side")
            if side is None:
                side = -1 if (stem == "paper_end" or str(p.get("state")) == "short") else 1
            entry = p.get("px")
            if stem == "paper_fast":
                entry = legs.get("short") if side < 0 else (legs.get("long") or p.get("px"))
            res = None
            if entry and px_now:
                res = (float(px_now) / float(entry) - 1) * 100 * (1 if side > 0 else -1)
            if stem == "paper_fast" and str(p.get("state")) == "hedged" and legs.get("long") and legs.get("short"):
                # в хедже обе ноги равны — ход заморожен на разнице цен ног, цена сейчас его не двигает
                res = (float(legs["short"]) / float(legs["long"]) - 1) * 100
            if res is not None and abs(res) < 0.005:
                res = 0.0
            rule = p.get("rule") or p.get("why") or ""
            opened.append({
                "book": book, "sym": sym, "side": side, "entry": entry, "px": px_now, "res": res, "d24": d24,
                "size": float(p.get("size") or 1.0), "rule": rule, "rk": _short_rule(book, rule),
                "target": p.get("target"), "stop": p.get("stop"), "hold": p.get("hold"),
                "bars": _bars_since(p.get("t")), "walls": _walls(sym), "z": p.get("z"),
                "state": p.get("state"), "at": p.get("opened_at") or _now(), "ent": p.get("opened_at") or 0,
                "stem": stem, "raw": p, "legs": legs, "fixed": FIXED.get(stem),
            })
        closed += _closed_rows(stem, book, cut)
    opened.sort(key=lambda x: -(abs(x["res"]) if x["res"] is not None else 0))
    closed.sort(key=lambda x: -(x["at"] or 0))
    return opened, closed


# КЭШ АРХИВА ЖИВЁТ ОДИН ВЫЗОВ (17.09, найдено по ava.jsonl владельца: прогон импортирует render_book один раз и
# зовёт render_book() каждые полчаса, а этот словарь заполнялся при первом обращении к монете и дальше не
# обновлялся — у AVA цена «сейчас» была с бара 00:30 при входе в 06:30, +31.56% из воздуха; у каждой открытой
# позиции цена застывала на баре первого её появления). Чистится в начале book_data().
_ARCH: dict = {}


def _arch_rows(sym: str) -> list[dict]:
    """получасовки архива монеты — те же, по которым боты решают выход (cq_v2/intraday)"""
    key = sym.replace("USDT", "").lower()
    if key in _ARCH:
        return _ARCH[key]
    out = []
    p = BASE_DIR / "cq_v2" / "intraday" / f"{key}.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            except (ValueError, KeyError, TypeError):
                continue
            if not r.get("px"):
                continue
            _fu = r.get("fut") or {}
            out.append({"t": t, "px": float(r["px"]), "h": r.get("h"), "l": r.get("l"), "oi": r.get("oi"),
                        "fund": r.get("funding"), "ot": r.get("oi_type"),
                        "vol": float(_fu.get("b") or 0) + float(_fu.get("s") or 0), "d": _fu.get("d")})
    # ПО ПОРЯДКУ СВЕЧЕЙ, БЕЗ БУДУЩЕГО (17.09, AVA: у открытой позиции +31.56% через две минуты после входа —
    # цена «сейчас» была не с последней закрытой свечи). Повтор свечи — последняя запись; свечи позже текущего
    # времени не берутся
    now_ms = _now() * 1000
    by = {r["t"]: r for r in out if r["t"] <= now_ms}
    out = [by[t] for t in sorted(by)]
    _ARCH[key] = out
    return out


def _zs(C: list[float], i: int, N: int = 20):
    """z-скор как у paper_crowd: отклонение закрытия от средней 20 баров в стандартных отклонениях"""
    if i < N:
        return None
    w = C[i - N:i]
    m = sum(w) / N
    sd = (sum((x - m) ** 2 for x in w) / N) ** .5 or 1e-9
    return (C[i] - m) / sd


FAST_SPARK_BARS = 24                        # баров в мини-графиках вортекса и клингера на карточке


def _fast_now(rows: list[dict]) -> dict:
    """БЫСТРЫЕ СЕЙЧАС (16.09, владелец: «вортекс — давление продавцов от бара к бару, клингер — следующий пик ниже
    и с пика упал, цена висит на плече»; «индикаторы и переход между сессиями — основа и подтверждение»).
    Только наблюдение для глаза: в решение бота не входит. Линии и признаки — теми же функциями, что журнал
    наблюдений (lab_junctions, analytics_regime), по архиву получасовок монеты."""
    try:
        import lab_junctions as lj
        import analytics_regime as ar
    except Exception:  # noqa: BLE001
        return {}
    bars = [(r["t"] // 1000, float(r["h"]), float(r["l"]), float(r["px"]), float(r.get("vol") or 0))
            for r in rows if r.get("h") and r.get("l")]
    if len(bars) < 30:
        return {}
    out: dict = {}
    t_last = bars[-1][0]
    vl = lj.vortex_lines(bars)
    ts = sorted(vl)[-FAST_SPARK_BARS:]
    if len(ts) >= 6:
        out["vx"] = [[round(vl[t][0], 3), round(vl[t][1], 3)] for t in ts]
        run_m = run_p = 0
        allts = sorted(vl)
        for i in range(len(allts) - 1, 0, -1):
            if allts[i] - allts[i - 1] != lj.BAR or vl[allts[i]][1] <= vl[allts[i - 1]][1]:
                break
            run_m += 1
        for i in range(len(allts) - 1, 0, -1):
            if allts[i] - allts[i - 1] != lj.BAR or vl[allts[i]][0] <= vl[allts[i - 1]][0]:
                break
            run_p += 1
        vp, vm = vl[allts[-1]]
        hist_m = [vl[x][1] for x in allts[-97:]]
        hist_p = [vl[x][0] for x in allts[-97:]]
        if run_m >= 2 and run_m > run_p:
            out["vx_state"] = {"who": "продавцы", "bars": run_m,
                               "heat": round(100 * sum(1 for x in hist_m if x <= vm) / len(hist_m))}
        elif run_p >= 2 and run_p > run_m:
            out["vx_state"] = {"who": "покупатели", "bars": run_p,
                               "heat": round(100 * sum(1 for x in hist_p if x <= vp) / len(hist_p))}
        else:
            out["vx_state"] = {"who": "ровно", "bars": 0}
        out["vx_now"] = [round(vp, 3), round(vm, 3)]
    if sum(b[4] for b in bars) > 0:
        kl = lj.klinger_lines(bars)
        kts = sorted(kl)
        if len(kts) >= 6:
            out["kl"] = [[round(kl[t][0]), round(kl[t][1])] for t in kts[-FAST_SPARK_BARS:]]
            kv = [kl[t][0] for t in kts]
            n = len(kv)
            hi = [j for j in range(3, n - 2) if kv[j] > 0 and kv[j] == max(kv[j - 3:j + 3])]
            lo = [j for j in range(3, n - 2) if kv[j] < 0 and kv[j] == min(kv[j - 3:j + 3])]
            k_now, s_now = kl[kts[-1]]
            falling = n > 1 and kv[-1] < kv[-2]
            st_ = {"above": k_now > s_now, "falling": falling}
            if len(hi) >= 2 and kv[hi[-1]] < kv[hi[-2]] and not st_["above"] and falling and (not lo or hi[-1] > lo[-1]):
                st_.update(state="выдыхается", p1=round(kv[hi[-2]]), p2=round(kv[hi[-1]]))
            elif len(lo) >= 2 and kv[lo[-1]] > kv[lo[-2]] and st_["above"] and not falling and (not hi or lo[-1] > hi[-1]):
                st_.update(state="продавцы выдыхаются", p1=round(kv[lo[-2]]), p2=round(kv[lo[-1]]))
            else:
                st_["state"] = "над сигнальной" if st_["above"] else "под сигнальной"
            out["kl_state"] = st_
    nxt, prv = lj.opens_around(t_last + lj.BAR)
    now = time.time()
    out["jn"] = {"next": lj.sess_name(nxt), "next_t": nxt, "in_min": max(0, round((nxt - now) / 60)),
                 "prev": lj.sess_name(prv), "prev_t": prv, "ago_min": max(0, round((now - prv) / 60))}
    oi = {r["t"] // 1000: float(r["oi"]) for r in rows if r.get("oi")}
    lev, off = lj.leverage(oi, t_last)
    if lev:
        out["lev"] = {"state": lev, "off": off}
    closes = [b[3] for b in bars]
    tmap = {r["t"] // 1000: r for r in rows}
    ds = [tmap.get(b[0], {}).get("d") for b in bars]
    os_ = [oi.get(b[0]) for b in bars]
    try:
        m = ar.measures(closes, ds if sum(1 for x in ds if x is not None) >= 16 else None,
                        os_ if sum(1 for x in os_ if x is not None) >= 16 else None)
    except Exception:  # noqa: BLE001
        m = {}
    rg = []
    hr = (m.get("hurst") or {}).get("rel")
    if hr is not None:
        rg.append({"k": "Хёрст", "v": "ход продолжается" if hr > 0.08 else "ход отменяется" if hr < -0.08 else "случайность"})
    fl = m.get("flow") or {}
    if fl.get("absorb", 0) >= 0.25:
        rg.append({"k": "поток", "v": "поглощение"})
    elif fl.get("paint", 0) >= 0.25:
        rg.append({"k": "поток", "v": "палка на пустом"})
    cv = m.get("curve") or {}
    if cv:
        rg.append({"k": "рост", "v": "парабола" if (cv.get("c") or 0) > 0.5 and (cv.get("r2") or 0) > 0.8
                   else "загиб вниз" if (cv.get("c") or 0) < -0.5 else "прямая"})
    if (m.get("branch") or {}).get("ratio") is not None:
        rg.append({"k": "выносы", "v": "тянут друг друга" if m["branch"]["ratio"] >= 1.5 else "поодиночке"})
    who = (m.get("lead") or {}).get("who")
    if who:
        rg.append({"k": "ведёт", "v": who})
    if m.get("pe") is not None:
        rg.append({"k": "порядок", "v": "план" if m["pe"] < 0.85 else "хаос"})
    out["regime"] = rg
    return out


def _f(v, nd=2, sign=True):
    if v is None:
        return "—"
    return (f"{float(v):+.{nd}f}" if sign else f"{float(v):.{nd}f}").replace("-", "−")


def _analyse(o: dict) -> dict:
    """РАЗБОР ОТКРЫТОЙ ПОЗИЦИИ (16.09, владелец: «почему взята, чего ждёт, когда закрыть — максимально понятно»).
    Числа — по тем же барам архива и тем же формулам, что у ботов: результат, цель и стоп в цене, сколько баров
    прошло, когда кончится срок, что с интересом и фандингом с момента входа. Время — метками {T:секунды},
    экран переводит их в часы смотрящего."""
    p, stem, side = o["raw"], o["stem"], int(o["side"])
    rows = _arch_rows(o["sym"])
    t_sig = int(p.get("t") or 0)
    after = [r for r in rows if r["t"] > t_sig] if t_sig else []
    last = rows[-1] if rows else None
    legs = o.get("legs") or {}
    e = float(o["entry"]) if o.get("entry") else None
    px, px_src = (last["px"], "архив") if last else (o.get("px"), "сводка")
    px = float(px) if px else None
    # ЦЕНА НЕ СТАРШЕ ВХОДА (17.09): если последняя свеча архива старше сигнального бара позиции или архива нет
    # вовсе — сводка даёт суточную цену, и результат выходит фантомным (AVA: +31.56% при входе две минуты назад).
    # Тогда цены нет, результат не считается, на экране «цена отстала»
    if t_sig and (not last or last["t"] < t_sig):
        px, px_src = None, "нет: архив старше входа" if last else "нет: архива нет"
    if not last and t_sig:
        after = []
    bars = len(after) if rows and t_sig else o["bars"]
    sgn = "шорт" if side < 0 else "лонг"
    a = {"sym": o["sym"].replace("USDT", ""), "book": o["book"], "side": side, "size": o["size"], "rule": o["rk"],
         "rl": o["rule"], "entry": e, "px": px, "px_src": px_src, "d24": o.get("d24"), "bars": bars,
         "stale": px is None,
         "opened": int(p.get("opened_at") or 0), "sig_t": t_sig // 1000, "walls": o.get("walls") or "",
         "state": p.get("state"), "legs": legs}
    # результат — формулой своего бота
    res = None
    if e and px:
        if stem == "paper_end":
            res = (e / px - 1) * 100
        elif stem == "paper_fast":
            st_ = str(p.get("state") or "long")
            if st_ == "hedged" and legs.get("long") and legs.get("short"):
                res = (float(legs["short"]) / float(legs["long"]) - 1) * 100
            elif st_ == "short" and legs.get("short"):
                res = (float(legs["short"]) / px - 1) * 100
            else:
                res = (px / float(legs.get("long") or e) - 1) * 100
        else:
            res = side * (px / e - 1) * 100
    a["res"] = None if res is None else round(res, 2)
    # лучший и худший ход с входа — по размаху баров
    if after and e:
        hs = [float(r["h"]) for r in after if r.get("h")] or [r["px"] for r in after]
        ls = [float(r["l"]) for r in after if r.get("l")] or [r["px"] for r in after]
        if side < 0:
            a["mfe"], a["mae"] = round((e - min(ls)) / e * 100, 2), round((max(hs) - e) / e * 100, 2)
        else:
            a["mfe"], a["mae"] = round((max(hs) - e) / e * 100, 2), round((e - min(ls)) / e * 100, 2)
    # что с плечом и фандингом с момента входа
    bar0 = next((r for r in rows if r["t"] == t_sig), None)
    if bar0 and last and bar0.get("oi") and last.get("oi"):
        a["oi_chg"] = round((float(last["oi"]) / float(bar0["oi"]) - 1) * 100, 2)
    if last and last.get("fund") is not None:
        a["fund_now"] = float(last["fund"])
    if rows:
        a["types"] = [r.get("ot") for r in rows[-3:]]
        # ПУТЬ ЦЕНЫ для графика карточки: от 12 баров до входа до последнего бара, не длиннее 96 баров
        i0 = next((k for k, r in enumerate(rows) if r["t"] >= t_sig), len(rows)) if t_sig else max(0, len(rows) - 48)
        seg = rows[max(0, i0 - 12):][-96:]
        a["path"] = [[r["t"] // 1000, round(r["px"], 10)] for r in seg]
    close, why, wait = [], "", ""
    fund0 = p.get("funding") if p.get("funding") is not None else p.get("fund")
    oi_note = ""
    if a.get("oi_chg") is not None:
        good = (a["oi_chg"] < 0) if side < 0 else (a["oi_chg"] >= -2)
        oi_note = (f" Интерес с входа {_f(a['oi_chg'], 1)}% — " +
                   ("плечо уходит, сценарий идёт." if side < 0 and good else
                    "плечо возвращается — это против шорта." if side < 0 else
                    "плечо на месте." if good else "плечо уходит — покупателя нет."))
    if stem == "paper_fast":
        st_ = str(p.get("state") or "long")
        why = (f"Лонг на быстрых: {p.get('why') or 'слом вортекса вверх при росте интереса и отрицательном фандинге'}. "
               f"Шорты платят — есть кого выносить.")
        lp, sp_ = legs.get("long"), legs.get("short")
        if st_ == "hedged":
            wait = (f"Позиция в хедже: лонг {_px(lp)} закрыт шортом {_px(sp_)} на тот же объём, ход заморожен на "
                    f"{_f(res)}%. Дальше одно из двух: слом вортекса вниз при падающем интересе — лонг закрываем, "
                    f"сидим в шорте; слом клингера вверх — шорт снимаем, лонг идёт дальше.")
            close = [{"k": "флип", "v": "слом вортекса вниз", "s": "и интерес падает → закрыть лонг, остаться в шорте", "sh": "+ интерес падает → остаёмся в шорте"},
                     {"k": "снять хедж", "v": "слом клингера вверх", "s": "шорт закрыть, лонг держать", "sh": "шорт закрыть, лонг держать"}]
        elif st_ == "short":
            wait = (f"После флипа сидим в шорте от {_px(sp_)}: ждём, пока продавцы выдохнутся. Сейчас {_f(res)}%.")
            close = [{"k": "закрыть шорт", "v": "слом вортекса вверх", "s": "покупатели развернулись", "sh": "покупатели развернулись"}]
        else:
            wait = (f"Лонг от {_px(lp or e)} держим, пока быстрые не повернут. Сейчас {_f(res)}%. "
                    f"Ценового стопа нет — риск снимает шорт-нога.")
            close = [{"k": "хедж", "v": "слом клингера вниз", "s": f"при цене выше входа {_px(lp or e)} → шорт на весь объём", "sh": "шорт на весь объём"},
                     {"k": "стоп", "v": "нет", "s": "вместо стопа — хедж и флип", "sh": "вместо стопа — хедж"}]
        import re as _re
        F = [{"k": "вход", "v": "слом вортекса вверх", "t": "key"}]
        m = _re.search(r"фандинг ([+\-−]?[\d.]+)", str(p.get("why") or ""))
        if m:
            F.append({"k": "фандинг", "v": m.group(1).replace("-", "−"), "t": "key"})
        if "интерес вырос" in str(p.get("why") or ""):
            F.append({"k": "интерес", "v": f"↑ за {PAPER_FAST_OI_BARS} бара", "t": "neu"})
        F.append({"k": "состояние", "v": {"hedged": "в хедже", "short": "в шорте после флипа"}.get(st_, "лонг"), "t": "neu"})
        a["facts"] = F
        a["goal"] = {"k": "ждём", "v": {"hedged": "флип или снятие хеджа", "short": "слом вортекса вверх"}.get(st_, "слом клингера вниз"),
                     "s": "ценового стопа нет"}
        a["now"] = _now_facts(a, side)
        a["fast"] = _fast_now(rows)
        a.update(why=why, wait=wait + oi_note, close=close)
        a["nearest"] = "событие"
        return a
    if stem == "paper_bottom":
        return _analyse_bottom(a, p, o, rows, e, px, res, bars, t_sig, side, oi_note)
    tgt = p.get("target")
    stop = p.get("stop") or (PAPER_CROWD_STOP if stem == "paper_crowd" else None)
    hold = p.get("hold") or (PAPER_CROWD_HOLD if stem == "paper_crowd" else None)
    rk = o["rk"]
    # ── ПОЧЕМУ ВЗЯТА
    if stem == "paper_end":
        why = (f"Шорт на конце хода. До сигнала монета выросла на {_f(p.get('run_pct'), 1)}% от минимума суток; "
               f"на сигнальном баре интерес {_f(p.get('oi_bar_pct'))}% при дельте в минус и цене ниже прошлого бара — "
               f"плечо закрывают, покупатель выходит. Чем больше был рост, тем больше вес и дальше цель: "
               f"вес ×{o['size']:g}, цель {tgt * 100:.1f}%." if tgt else "Шорт на конце хода.")
        if fund0 is not None:
            why += f" Фандинг при входе {_f(fund0, 3)}."
    elif rk.startswith("спайк"):
        why = (f"Шорт на спайке: +{_f(p.get('r2'), 1, False)}% за два часа (за сутки {_f(p.get('r24'), 1)}%). "
               f"Такие всплески гасят в следующие шесть часов. Фандинг {_f(fund0, 3)}"
               + (" — платят шорты, рост на выносе: вес и цель удвоены, срок длиннее." if fund0 is not None and fund0 <= SPIKE_FUND_NEG else ".")
               + (f" Первый час после открытия сессии — вес урезан до ×{o['size']:g}." if (p.get("since_open_h") or 9) < 1 else ""))
    elif rk.startswith("рост на выносе"):
        why = (f"Шорт: +{_f(p.get('r6'), 1, False)}% за шесть часов при фандинге {_f(fund0, 3)} — растёт на выносе шортов, "
               f"а не на покупках; такой рост отдают." + (" Последний бар — шорты крылись, вес выше." if "крылись" in o["rule"] else ""))
    elif rk.startswith("против толпы"):
        why = (f"Шорт против толпы: три бара подряд открывают лонги, фандинг {_f(fund0, 3)} не отрицательный, "
               f"интерес за сутки {_f(p.get('oi24'), 1)}% не растёт — толпа набирает, новых денег нет.")
    elif rk.startswith("перекуплен"):
        why = (f"Шорт на перекупленности: z-скор {_f(p.get('z'))} — цена выше средней 20 баров больше чем на два "
               f"отклонения, а интерес за сутки {_f(p.get('oi24'), 1)}% и фандинг {_f(fund0, 3)} роста не подтверждают.")
    elif rk.startswith("провал"):
        why = (f"Лонг на провале: {_f(p.get('r2'), 1)}% за два часа (за шесть часов {_f(p.get('r6'), 1)}%). "
               f"Правило пока наблюдение — на истории то откупают, то продолжают, поэтому вес ×{o['size']:g}.")
    elif rk.startswith("прокол дна"):
        why = (f"Лонг на проколе дна: цена ушла ниже минимума восьми баров на полтора процента при ровном интересе "
               f"({_f(p.get('oi24'), 1)}% за сутки) — прокол без плеча, его обычно выкупают.")
    elif rk.startswith("первый час Лондона"):
        why = (f"Шорт на первый час Лондона: после открытия в 07:00 UTC цена чаще идёт вниз. Фон 12 ч {p.get('bg12') or '—'}.")
    elif stem == "paper_first3":
        why = (f"Лонг на {FIRST3_SIZE:.0f} $: монета первая в очереди {FIRST3_STREAK} получасовки подряд. Цель "
               f"+{FIRST3_TARGET * 100:.0f}%, после +{FIRST3_BE * 100:.0f}% стоп в точку входа, до этого стопа и срока нет.")
    else:
        why = o["rule"]
    if p.get("bg12") and "Фон" not in why:
        why += f" Фон 12 ч {p['bg12']}."
    # ФАКТЫ ДЛЯ ГЛАЗА (16.09, владелец: «простыня, всё одним цветом»): те же числа, что в тексте, плитками.
    # t: key — число, по которому правило сработало; neu — фон
    F = []
    def fact(k, v, t="neu"):
        if v not in (None, "", "—"):
            F.append({"k": k, "v": v, "t": t})
    fund0v = None if fund0 is None else _f(fund0, 3)
    if stem == "paper_end":
        fact("рост до сигнала", f"{_f(p.get('run_pct'), 1)}%" if p.get("run_pct") is not None else None, "key")
        fact("интерес на баре", f"{_f(p.get('oi_bar_pct'))}%" if p.get("oi_bar_pct") is not None else None, "key")
        fact("фандинг", fund0v)
    elif rk.startswith("спайк"):
        fact("за 2 часа", f"+{_f(p.get('r2'), 1, False)}%" if p.get("r2") is not None else None, "key")
        fact("за сутки", f"{_f(p.get('r24'), 1)}%" if p.get("r24") is not None else None)
        fact("фандинг", fund0v, "key" if (fund0 is not None and fund0 <= SPIKE_FUND_NEG) else "neu")
    elif rk.startswith("рост на выносе"):
        fact("за 6 часов", f"+{_f(p.get('r6'), 1, False)}%" if p.get("r6") is not None else None, "key")
        fact("фандинг", fund0v, "key")
    elif rk.startswith("против толпы"):
        fact("бары", "3× лонги открывают", "key")
        fact("фандинг", fund0v)
        fact("интерес за сутки", f"{_f(p.get('oi24'), 1)}%" if p.get("oi24") is not None else None)
    elif rk.startswith("перекуплен"):
        fact("z при входе", _f(p.get("z")) if p.get("z") is not None else None, "key")
        fact("интерес за сутки", f"{_f(p.get('oi24'), 1)}%" if p.get("oi24") is not None else None)
        fact("фандинг", fund0v)
    elif rk.startswith("провал"):
        fact("за 2 часа", f"{_f(p.get('r2'), 1)}%" if p.get("r2") is not None else None, "key")
        fact("за 6 часов", f"{_f(p.get('r6'), 1)}%" if p.get("r6") is not None else None)
        fact("статус", "наблюдение")
    elif rk.startswith("прокол дна"):
        fact("ниже дна 8 баров", "−1.5%", "key")
        fact("интерес за сутки", f"{_f(p.get('oi24'), 1)}%" if p.get("oi24") is not None else None)
    elif rk.startswith("первый час Лондона"):
        fact("окно", "07:00 UTC, 1 час", "key")
    elif stem == "paper_first3":
        # 25.09, владелец обвёл пустую панель «почему взята» у сделок нового бота
        fact("первая в очереди подряд", f"{FIRST3_STREAK} получасовки", "key")
        if p.get("streak_from"):
            fact("серия с", f"{{T:{int(p['streak_from'])}}}")
        fact("сумма", f"{FIRST3_SIZE:.0f} $")
        fact("цена входа", _px(e) if e else None)
        fact(f"цель +{FIRST3_TARGET * 100:.0f}%", _px(e * (1 + FIRST3_TARGET)) if e else None, "key")
        fact("стоп в точку входа", "встал" if p.get("armed") else
             (f"после {_px(e * (1 + FIRST3_BE))}" if e else None), "good" if p.get("armed") else "neu")
        fact("повтор по монете", f"через {FIRST3_PAUSE_H} ч")
    if p.get("bg12"):
        fact("фон 12 ч", p["bg12"])
    a["facts"] = F
    # ── ЧЕГО ЖДЁМ И КОГДА ЗАКРОЕТСЯ
    dirw = "вниз" if side < 0 else "вверх"
    znow = None
    if rows:
        znow = _zs([r["px"] for r in rows], len(rows) - 1)
    frac = {}
    if tgt and e:
        pt = e / (1 + tgt) if stem == "paper_end" else e * (1 + side * tgt)
        rem = tgt * 100 - (res or 0)
        mv = (pt / px - 1) * 100 if px else None
        a["goal"] = {"k": "ждём цену", "v": _px(pt),
                     "s": (f"цене {dirw} ещё {abs(mv):.2f}%" if (mv is not None and rem > 0) else "цель достигнута")}
        wait = (f"Ждём цену {_px(pt)} — это {tgt * 100:.1f}% от входа {_px(e)}. Сейчас {_f(res)}%, до цели осталось "
                f"{max(0.0, rem):.2f}%" + (f" (цене {dirw} ещё {abs(mv):.2f}%)." if mv is not None and rem > 0 else "."))
        close.append({"k": "цель", "v": _px(pt), "s": f"{tgt * 100:.1f}% от входа · осталось {max(0.0, rem):.2f}%",
                      "sh": (f"ещё {rem:.2f}%" if rem > 0 else "достигнута"),
                      "f": max(0.0, min(1.0, (res or 0) / (tgt * 100)))})
        frac["цель"] = max(0.0, (res or 0) / (tgt * 100))
        a["tgt_pct"], a["tgt_px"] = round(tgt * 100, 2), pt
    else:
        z0 = p.get("z")
        a["goal"] = {"k": "ждём", "v": "z ниже нуля", "s": (f"сейчас z {_f(znow)}" if znow is not None else "z сейчас неизвестен")}
        wait = ("Ждём, когда цена вернётся к средней: выход на первом баре с z ниже нуля. "
                + (f"Сейчас z {_f(znow)}" if znow is not None else "Текущего z нет в архиве")
                + (f", при входе было {_f(z0)}." if z0 is not None else "."))
        close.append({"k": "событие", "v": "z ниже нуля", "sh": (f"сейчас {_f(znow)}" if znow is not None else "z неизвестен"),
                      "s": (f"сейчас {_f(znow)}" if znow is not None else "z сейчас неизвестен")
                      + (f" · при входе {_f(z0)}" if z0 is not None else ""),
                      "f": max(0.0, min(1.0, (float(z0) - znow) / float(z0))) if (z0 and znow is not None and float(z0) > 0) else 0.0})
        if z0 and znow is not None and float(z0) > 0:
            frac["событие"] = (float(z0) - znow) / float(z0)
        a["z_now"] = None if znow is None else round(znow, 2)
    if stop and e:
        ps = e * (1 + stop) if side < 0 else e * (1 - stop)
        mv = (ps / px - 1) * 100 if px else None
        _hit = mv is not None and not ((side < 0 and mv > 0) or (side > 0 and mv < 0))
        close.append({"k": "стоп", "v": _px(ps),
                      "sh": ("за стопом" if _hit else (f"цене {'вверх' if side < 0 else 'вниз'} {abs(mv):.2f}%" if mv is not None else "")),
                      "s": f"{stop * 100:.1f}% против позиции по размаху бара",
                      "f": max(0.0, min(1.0, (a.get("mae") or 0) / (stop * 100)))})
        frac["стоп"] = max(0.0, -(res or 0)) / (stop * 100)
        a["stop_pct"], a["stop_px"] = round(stop * 100, 2), ps
    if hold:
        left = max(0, int(hold) - bars)
        due = t_sig // 1000 + (int(hold) + 1) * BAR_S if t_sig else None
        close.append({"k": "срок", "v": f"{min(bars, int(hold))} из {int(hold)} баров", "sh": (f"~{{T:{due}}}" if due else f"осталось {left}"),
                      "s": (f"осталось {left} · закроется около {{T:{due}}}" if due else f"осталось {left}"),
                      "f": min(1.0, bars / int(hold)), "due": due})
        frac["срок"] = bars / int(hold)
        a["hold"], a["left"], a["due"] = int(hold), left, due
    # ТОЛЬКО ВОШЛА (16.09, на живых данных PHA и KAVA стояли «ближе к стопу» при стопе 0%): пока ни один выход
    # не прошёл и пяти процентов пути, ближайшего нет — позиция помечается fresh
    if frac and max(frac.values()) >= 0.05:
        a["nearest"] = max(frac, key=frac.get)
        a["nearest_f"] = round(max(frac.values()), 2)
    else:
        a["nearest"], a["nearest_f"], a["fresh"] = "", round(max(frac.values()), 2) if frac else 0, True
    # УЖЕ СРАБОТАЛО — позиция закроется на ближайшем прогоне (бот проверяет выходы раз в полчаса)
    done = []
    if frac.get("цель", 0) >= 1:
        done.append("цель достигнута")
    if frac.get("стоп", 0) >= 1:
        done.append(f"цена за стопом ({_f(res)}% при стопе {stop * 100:.1f}%)")
    if frac.get("событие", 0) >= 1 or (znow is not None and znow < 0 and not tgt):
        done.append("z уже ниже нуля")
    if hold and bars >= int(hold):
        done.append("срок вышел")
    if done:
        a["done"] = True
        a["done_list"] = done
    if a.get("mfe") is not None:
        wait += f" С входа лучшая точка {_f(a['mfe'])}%, худшая {_f(-a['mae'])}%."
    a["now"] = _now_facts(a, side)
    a["fast"] = _fast_now(rows)
    a.update(why=why, wait=wait + oi_note, close=close)
    return a


def _now_facts(a: dict, side: int) -> list[dict]:
    """что происходит с позицией сейчас — плитками; t: good — за позицию, bad — против, neu — фон"""
    out = []
    if a.get("oi_chg") is not None:
        good = (a["oi_chg"] < 0) if side < 0 else (a["oi_chg"] >= -2)
        out.append({"k": "интерес с входа", "v": f"{_f(a['oi_chg'], 1)}%", "t": "good" if good else "bad"})
    if a.get("mfe") is not None:
        out.append({"k": "лучшая точка", "v": f"{_f(a['mfe'])}%", "t": "good" if a["mfe"] > 0 else "neu"})
        out.append({"k": "худшая точка", "v": f"{_f(-a['mae'])}%", "t": "bad" if a["mae"] > 0 else "neu"})
    if a.get("fund_now") is not None:
        out.append({"k": "фандинг сейчас", "v": _f(a["fund_now"], 3), "t": "neu"})
    if a.get("d24") is not None:
        out.append({"k": "монета за 24 ч", "v": f"{_f(a['d24'], 1)}%", "t": "neu"})
    return out


def _analyse_bottom(a, p, o, rows, e, px, res, bars, t_sig, side, oi_note) -> dict:
    """РАЗБОР ПОЗИЦИИ «ДНО» (17.09): почему взята — пузырь 4ч у дна и доводы за; чего ждём — ухода руки;
    когда закроется — событие, закрытие под дном (не у класса DWF) и срок"""
    dist = p.get("dist_bubble_pct")
    why = (f"Лонг у дна: ясный белый пузырь на четырёх часах"
           + (f" в {float(dist):.1f}% от дна {_px(p.get('bottom'))}" if dist is not None else "")
           + " — на баре пузыря интерес вырос, позиции открывали, а не закрывали. За: "
           + "; ".join(f"{k} {v}" for k, v in (p.get("za") or []))
           + f". Карточка по заходам к дну: {p.get('card_rule') or '—'}. Правило пока наблюдение.")
    F = []
    for k, v in (p.get("za") or []):
        F.append({"k": k, "v": v, "t": "key" if k.startswith("пузырь 4ч") else "good"})
    if p.get("bottom"):
        F.append({"k": "дно", "v": _px(p["bottom"]), "t": "neu"})
    if p.get("card_rule"):
        F.append({"k": "заходы к дну", "v": p["card_rule"].replace("второй заход к дну ", ""), "t": "neu"})
    a["facts"] = F
    a["goal"] = {"k": "ждём", "v": "рука уйдёт", "s": "выход по событию, не по цене"}
    wait = (f"Держим лонг от {_px(e)}, пока рука здесь. Сейчас {_f(res)}%. Выход — ясный пузырь продажи на "
            f"четырёх часах, событие конца (не вынос по доске) или интерес вниз несколько баров подряд при "
            f"стоячей цене." + (" Цены-стопа нет: у класса DWF снятие дна — это сбор."
                               if p.get("dwf") else f" Страховка — закрытие ниже {_px(p.get('stop_px'))}."))
    close = [{"k": "событие", "v": "рука ушла", "sh": "пузырь продажи · конец · плечо вниз",
              "s": "ясный пузырь продажи 4ч · конец не по доске · интерес вниз подряд", "f": 0.0}]
    frac = {}
    sp = p.get("stop_px")
    if sp and px:
        mv = (float(sp) / px - 1) * 100
        span = (1 - float(sp) / e) * 100 if e else None
        close.append({"k": "стоп", "v": _px(sp), "sh": ("под дном" if mv >= 0 else f"цене вниз {abs(mv):.2f}%"),
                      "s": "закрытие получасовки ниже дна", "f": max(0.0, min(1.0, -(res or 0) / span)) if span else 0.0})
        frac["стоп"] = max(0.0, -(res or 0)) / span if span else 0.0
        a["stop_pct"], a["stop_px"] = round(span, 2) if span else None, float(sp)
    else:
        close.append({"k": "стоп", "v": "нет", "sh": "класс DWF", "s": "снятие дна у класса DWF — сбор"})
    hold = int(p.get("hold") or 0)
    if hold:
        left = max(0, hold - bars)
        due = t_sig // 1000 + (hold + 1) * BAR_S if t_sig else None
        close.append({"k": "срок", "v": f"{min(bars, hold)} из {hold} баров", "sh": (f"~{{T:{due}}}" if due else f"осталось {left}"),
                      "s": (f"осталось {left} · закроется около {{T:{due}}}" if due else f"осталось {left}"),
                      "f": min(1.0, bars / hold), "due": due})
        frac["срок"] = bars / hold
        a["hold"], a["left"], a["due"] = hold, left, due
    if frac and max(frac.values()) >= 0.05:
        a["nearest"] = max(frac, key=frac.get)
        a["nearest_f"] = round(max(frac.values()), 2)
    else:
        a["nearest"], a["nearest_f"], a["fresh"] = "", round(max(frac.values()), 2) if frac else 0, True
    a["now"] = _now_facts(a, side)
    a["fast"] = _fast_now(rows)
    a.update(why=why, wait=wait + oi_note, close=close, dwf=bool(p.get("dwf")))
    a["done"], a["done_list"] = False, []
    return a


def _exit_text(p: dict) -> str:
    """условие выхода открытой позиции словами с числом"""
    res = p["res"] or 0.0
    tgt, stop, hold = p.get("target"), p.get("stop"), p.get("hold")
    left = (int(hold) - p["bars"]) if hold else None
    bits = []
    if tgt:
        bits.append(f"цель {float(tgt) * 100:.1f}%, до неё {max(0.0, float(tgt) * 100 - res):.2f}%")
    elif p["book"] == "дно":
        bits.append("выход: рука ушла — пузырь продажи 4ч, конец не по доске, интерес вниз "
                    + ("· цены-стопа нет (класс DWF)" if p.get("dwf") else
                       (f"· закрытие под дном {float(p['stop_px']):.6g}" if p.get("stop_px") else "")))
    elif p["book"] == "быстрые":
        bits.append({"hedged": "в хедже: флип по слому вортекса", "short": "в шорте после флипа"}.get(
            str(p.get("state")), "выход по слому клингера → хедж"))
    else:
        bits.append("выход: z ниже нуля" + (f", сейчас {float(p['z']):+.1f}" if p.get("z") is not None else ""))
    if stop:
        bits.append(f"стоп {float(stop) * 100:.1f}%")
    if hold:
        bits.append(f"срок {int(hold)} баров" + (f", осталось {max(0, left)}" if left is not None else ""))
    if p.get("walls"):
        bits.append(p["walls"])
    return " · ".join(bits)


def _money_day(rows: list[dict]) -> dict:
    """ДЕПОЗИТ НА ДЕНЬ (16.09, владелец: «поставь депозит 10000 на день, пусть распределяется на сделки,
    за 24 часа итог в деньгах, каждые 24 часа депозит снова 10000»). Депозит дня делится между сделками
    этого дня пропорционально весу правила: доля = депозит × вес / сумма весов дня. Деньги сделки —
    доля × результат. Так итог дня не зависит от числа сделок."""
    w = sum(float(r.get("size") or 1) for r in rows if not r.get("fixed"))
    out = []
    for r in rows:
        if r.get("fixed"):
            share = float(r["fixed"])
            money = float(r["usd"]) if r.get("usd") is not None else share * float(r.get("res") or 0) / 100
        else:
            share = BOOK_DEPOSIT * float(r.get("size") or 1) / (w or 1.0)
            money = share * float(r.get("res") or 0) / 100
        out.append(dict(r, share=share, money=money))
    tot = sum(x["money"] for x in out)
    hit = (100 * sum(1 for x in out if x["money"] > 0) / len(out)) if out else 0
    return {"rows": out, "total": tot, "hit": hit, "n": len(out), "w": w}


def _row(x: dict, is_open: bool) -> dict:
    return {"sym": x["sym"].replace("USDT", ""), "book": x["book"], "side": int(x["side"]),
            "rule": x["rk"], "rl": x["rule"], "why": x["why"] if not is_open else x["cond"],
            "res": None if x["res"] is None else round(float(x["res"]), 2),
            "size": round(float(x["size"]), 2), "money": round(float(x["money"]), 2),
            "at": int(x["at"] or 0), "ent": int(x.get("ent") or 0), "open": is_open}


def _source(opened: list[dict], closed: list[dict]) -> dict:
    """один источник экрана: дни с деньгами, открытые в сегодняшнем дне, итог и строка вывода"""
    days = sorted({c["day"] for c in closed if c.get("day")}, reverse=True)[:BOOK_DAYS]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if opened and today not in days:
        days = [today] + days
    per_day = {d: _money_day([c for c in closed if c.get("day") == d]) for d in days}
    # открытые — в сегодняшний день, деньги от цены сейчас той же долей депозита; в итог дня не входят
    w_open = sum(p["size"] for p in opened if not p.get("fixed"))
    for p in opened:
        p["cond"] = _exit_text(p)
        if p.get("fixed"):
            share = float(p["fixed"])
        else:
            share = BOOK_DEPOSIT * p["size"] / (per_day[today]["w"] + w_open or 1.0)
        p["money"] = share * (p["res"] or 0) / 100
    out_days = []
    for d in days:
        m = per_day[d]
        rows = [_row(x, False) for x in sorted(m["rows"], key=lambda x: -(x["at"] or 0))]
        if d == today:
            rows = [_row(p, True) for p in sorted(opened, key=lambda x: -(x["at"] or 0))] + rows
        out_days.append({"d": d, "n": m["n"], "nopen": len(opened) if d == today else 0,
                         "total": round(m["total"], 2), "hit": round(m["hit"]), "rows": rows,
                         "ex": _exits(m["rows"])})
    allrows = [x for d in days for x in per_day[d]["rows"]]
    by_event = [x["money"] for x in allrows if not str(x.get("why") or "").startswith("срок")]
    by_time = [x["money"] for x in allrows if str(x.get("why") or "").startswith("срок")]
    note = ""
    if len(by_event) >= 3 and len(by_time) >= 3:
        note = (f"выходы по событию и цели дают {st.mean(by_event):+.1f} $ на сделку, по сроку "
                f"{st.mean(by_time):+.1f} $ · сделок {len(by_event)} против {len(by_time)}")
    return {"note": note, "total": round(sum(per_day[d]["total"] for d in days), 2), "days": out_days,
            "ex": _exits(allrows)}


def _exits(rows: list[dict]) -> dict:
    """ВЫХОДЫ ЧИСЛАМИ (16.09, прибор «выходы» на экране): по событию и цели против выхода по сроку —
    сколько сделок и сколько денег в среднем на сделку. Причина выхода «срок…» — по сроку, прочее — событие."""
    ev = [x["money"] for x in rows if not str(x.get("why") or "").startswith("срок")]
    tm = [x["money"] for x in rows if str(x.get("why") or "").startswith("срок")]
    return {"ev_n": len(ev), "ev": round(st.mean(ev), 2) if ev else None,
            "tm_n": len(tm), "tm": round(st.mean(tm), 2) if tm else None}


def book_data() -> dict:
    _ARCH.clear()                       # архив читается заново при каждой сборке страницы
    """всё, что рисует экран, одним словарём — его же удобно сверять руками"""
    opened, closed = _collect()
    back = []
    cut = _now() - BOOK_DAYS * 86400
    for book, stem in BACKFILL:
        back += _closed_rows(stem, book, cut)
    back.sort(key=lambda x: -(x["at"] or 0))
    # ОДНА ЦЕНА С БОТАМИ (17.09, владелец прислал экран: у всех 25 открытых «0 $» и прочерк). Колонки брали цену
    # только из сводки прогона, а в near_move есть не все монеты; разбор позиции уже считал результат по
    # последней получасовке архива формулой своего бота. Теперь и строки берут этот же результат.
    work = [_analyse(o) for o in opened]
    for o, a in zip(opened, work):
        o["res"] = a.get("res")            # None, если цены с закрытой свечи после входа ещё нет
        o["px"] = a.get("px")
    live = _source(opened, closed)
    bk = _source([], back)
    if bk["days"]:
        bk["note"] = ("реконструкция по архиву: без события доски, запрета встречных и задержек — "
                      "для сравнения правил, не обещание денег" + (" · " + bk["note"] if bk["note"] else ""))
    work.sort(key=lambda x: -(x.get("nearest_f") or 0))
    return {"deposit": BOOK_DEPOSIT, "built": int(time.time()), "live": live, "back": bk, "work": work}


def render_book() -> str:
    data = json.dumps(book_data(), ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")          # строка внутри <script> не должна закрыть тег
    return TEMPLATE.replace("__HUD_CSS__", HUD_CSS).replace("__BOOK_DATA__", data)


TEMPLATE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>книга · бот</title>
<style>
__HUD_CSS__
/* ЭКРАН КНИГИ — СЦЕНА (16.09, макет владельца bot_book_hud.html, «делай»): одна сцена 1600×1000 в духе
   KYLO III — шкала недели, прибор дня в центре, колонки «закрыты» и «в работе», четыре панели монеты внизу.
   Всё рисуется из данных страницы; день бота — по UTC, время — в часах смотрящего. */
:root{--void:#05070a;--frost:#e8edf4;--dust:#7f8a98;--dim2:#4c5563;--amber:#ffa53a;--amberhi:#ffd08a;--rose:#f0506a}
html,body{margin:0;height:100%;background:var(--void);overflow:hidden}
.bg{position:fixed;inset:0;background-color:#05070a;background-position:center;background-size:cover;background-repeat:no-repeat}
.vig{position:fixed;inset:0;pointer-events:none;background:radial-gradient(ellipse at 50% 47%,transparent 52%,rgba(0,0,0,.6) 100%)}
.grain{position:fixed;inset:0;pointer-events:none;opacity:.08;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}
.vp{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
.stage{position:relative;width:min(100vw,160vh);height:min(62.5vw,100vh);flex:none}
@media (orientation:portrait) and (max-width:900px){.vp{overflow-x:auto;justify-content:flex-start}.stage{height:100svh;width:160svh}}
#scene{position:absolute;inset:0;width:100%;height:100%;overflow:visible;user-select:none;-webkit-user-select:none}
#scene text{font-family:Jost,"Futura","Segoe UI",system-ui,sans-serif;fill:var(--frost)}
#scene .mono{font-family:JBM,ui-monospace,Menlo,monospace;font-weight:300}
[data-act]{cursor:pointer}
.hit{fill:#000;fill-opacity:0;pointer-events:all}
.hit:hover{fill:#ffa53a;fill-opacity:.05}
.wm{font-size:15px;font-weight:500;letter-spacing:.55em}
.ttl{font-size:12px;font-weight:500;letter-spacing:.34em}
.hdr{font-size:22px;font-weight:300;letter-spacing:.3em}
.cap{font-size:9.5px;font-weight:500;letter-spacing:.26em;fill:var(--dust)!important}
.ctl{font-size:12px;font-weight:500;letter-spacing:.3em;fill:var(--dust)!important;transition:fill .3s}
.ctl.on{fill:var(--amber)!important}
.cnt{font-size:40px;font-weight:200}
.sm{font-size:11px}.xs{font-size:10px}.xs2{font-size:9.5px}.xs3{font-size:9px}
.tk{font-size:12px;letter-spacing:.14em;fill:#c9d1dc!important}
.dim{fill:var(--dust)!important}.dim2{fill:var(--dim2)!important}.mid{fill:#aeb7c3!important}.lt{fill:var(--frost)!important}
.amb{fill:var(--amber)!important}.ros{fill:var(--rose)!important}
.big2{font-size:13px}
.big{font-size:60px;font-weight:200;letter-spacing:.02em}.bigu{font-size:26px}
.bigg{font-size:60px;font-weight:300;fill:#ffcf8a!important;opacity:.28}
.big2x{font-size:34px;font-weight:200}.bigu2{font-size:16px;fill:var(--dust)!important}
.goalv{font-size:16px;font-weight:300;fill:var(--amberhi)!important}
.ln{fill:none;stroke:rgba(210,222,236,.22)}
.tick{stroke:rgba(210,222,236,.4)}.tick2{stroke:rgba(210,222,236,.18)}
.dayon{fill:none;stroke:var(--amber);stroke-width:2;filter:drop-shadow(0 0 4px rgba(255,165,58,.8))}
.orb{fill:none;stroke:rgba(210,222,236,.06)}
.orbf{fill:none;stroke:rgba(210,222,236,.12)}
.under{fill:none;stroke:#05070a;stroke-width:6}
.halo{fill:none;stroke:var(--amber);stroke-width:14;opacity:.09;filter:url(#g3)}
.tk1{stroke:rgba(210,222,236,.45)}.tk3{stroke:rgba(210,222,236,.16)}
.ring0{fill:none;stroke:rgba(210,222,236,.07)}
.wdot{fill:var(--amber);filter:drop-shadow(0 0 3px rgba(255,165,58,.9))}
.cseg{fill:none;stroke:rgba(210,222,236,.55);stroke-width:3}
.cseg.m{stroke:rgba(240,80,106,.7)}
.hitl{fill:none;stroke:var(--amber);stroke-width:2;stroke-dasharray:1}
.hitg{fill:none;stroke:var(--amber);stroke-width:4;opacity:.6}
.hitr{fill:none;stroke:rgba(210,222,236,.12);stroke-width:1;stroke-dasharray:2 3}
.hitdot{fill:var(--amberhi);filter:drop-shadow(0 0 5px #ffa53a)}
.rim{fill:none;stroke:rgba(210,222,236,.18)}
.sonar{fill:none;stroke:rgba(210,222,236,.04)}
.ax{stroke:rgba(210,222,236,.2)}
.legr{stroke:var(--rose);stroke-width:3;filter:drop-shadow(0 0 4px rgba(240,80,106,.7))}
.legw{stroke:var(--frost);stroke-width:3;filter:drop-shadow(0 0 4px rgba(232,237,244,.6))}
.odc{fill:var(--amberhi)}.cdot{fill:var(--frost)}
.conn{stroke:rgba(255,165,58,.5);stroke-dasharray:1 3}
.garc{fill:none;stroke:rgba(210,222,236,.1)}
.ret{fill:none;stroke:rgba(210,222,236,.5)}
.mk-r{stroke:var(--rose);stroke-width:2}.mk-w{stroke:var(--frost);stroke-width:2}.mk-a{stroke:var(--amber);stroke-width:2.2}
.ico{fill:none;stroke:var(--amber)}
.frm{fill:none;stroke:rgba(210,222,236,.28)}
.row .sel{fill:var(--amber);opacity:0;transition:opacity .25s;filter:drop-shadow(0 0 4px #ffa53a)}
.row.on .sel{opacity:1}.row.on .tk{fill:#fff!important;font-weight:500}
.fc,.fw{transition:opacity .35s}
#scene.f-c .fw,#scene.f-w .fc{opacity:.18}
.pill{fill:none}.pw{stroke:rgba(255,165,58,.7)}.pc{stroke:rgba(210,222,236,.3)}
.entry{stroke:rgba(210,222,236,.5)}
.now{fill:#05070a;stroke:var(--frost)}
.tgt{stroke:var(--amber);stroke-width:1.6}
.stp{stroke:var(--rose);stroke-width:1.4;stroke-dasharray:2 2}
.gap{fill:none;stroke:rgba(255,165,58,.6);stroke-dasharray:2 3}
.sepl{stroke:rgba(210,222,236,.06)}
.barw{fill:var(--frost)}.barr{fill:var(--rose)}.bara{fill:var(--amber)}.bard{fill:rgba(210,222,236,.35)}
.sep{stroke:rgba(210,222,236,.1)}
.chev{fill:none;stroke:var(--amber);stroke-width:1.2}
.chev.off{stroke:var(--dim2)}
.rtc{fill:none;stroke:var(--amber)}.rtd{fill:none;stroke:rgba(255,165,58,.4);stroke-dasharray:3 4;transform-box:fill-box;transform-origin:center;animation:sp 14s linear infinite}
.retc{transition:opacity .3s}#scene.f-c .retc,#scene.f-w .retc{opacity:.35}
.btn{fill:rgba(5,7,10,.5);stroke:rgba(255,165,58,.55)}
.btn.off{stroke:rgba(210,222,236,.15)}
.star{fill:#fff;animation:twk 4s ease-in-out infinite}
.a-fi,.a-fl,.a-dr,.a-si{animation-duration:1.1s;animation-fill-mode:both;animation-timing-function:cubic-bezier(.2,.7,.2,1)}
.a-fi{animation-name:fi}.a-fl{animation-name:fl}.a-dr{animation-name:dr}
.a-si{animation-name:si;transform-box:view-box;transform-origin:800px 478px;animation-duration:1.6s}
.hitdot,.wdot{animation:br 3s ease-in-out infinite}
@keyframes sp{to{transform:rotate(360deg)}}
@keyframes twk{0%,100%{opacity:.15}50%{opacity:.9}}
@keyframes br{0%,100%{opacity:.6}50%{opacity:1}}
@keyframes fi{from{opacity:0}to{opacity:1}}
@keyframes fl{0%{opacity:0}30%{opacity:.7}45%{opacity:.1}70%{opacity:.9}100%{opacity:1}}
@keyframes dr{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes si{from{opacity:0;transform:rotate(-30deg)}to{opacity:1;transform:rotate(0)}}
@media (prefers-reduced-motion:reduce){#scene *{animation:none!important}}
</style>
</head>
<body>
<div class="bg"></div><div class="vig"></div>
<div class="vp"><div class="stage">
<svg id="scene" viewBox="0 0 1600 1000" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Бумажная книга бота">
<defs>
<filter id="g1" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4"/></filter>
<filter id="g2" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="8"/></filter>
<filter id="g3" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="18"/></filter>
<radialGradient id="disc"><stop offset="0" stop-color="#0c1017" stop-opacity=".97"/><stop offset=".75" stop-color="#07090d" stop-opacity=".92"/><stop offset=".95" stop-color="#101722" stop-opacity=".7"/><stop offset="1" stop-color="#26303e" stop-opacity=".3"/></radialGradient>
<radialGradient id="hi" cx="34%" cy="24%" r="70%"><stop offset="0" stop-color="#a9bcd4" stop-opacity=".12"/><stop offset=".55" stop-color="#a9bcd4" stop-opacity="0"/></radialGradient>
<linearGradient id="rf" gradientUnits="userSpaceOnUse" x1="110" x2="1490"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".15" stop-color="#fff"/><stop offset=".85" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<mask id="rm"><rect x="0" y="0" width="1600" height="260" fill="url(#rf)"/></mask>
<mask id="od"><rect width="1600" height="1000" fill="#fff"/><circle cx="800" cy="478" r="164" fill="#000"/></mask>
<linearGradient id="bt" x1="0" x2="1"><stop offset="0" stop-color="#ffa53a" stop-opacity=".02"/><stop offset=".5" stop-color="#ffa53a" stop-opacity=".16"/><stop offset="1" stop-color="#ffa53a" stop-opacity=".02"/></linearGradient>
</defs>
<g id="L_back"></g>
<g id="L_day"></g>
<g id="L_front"></g>
<g id="L_cols"></g>
<g id="L_coin"></g>
<g id="L_ctl"></g>
</svg>
</div></div>
<div class="grain"></div>
<script>
/* ── данные собраны render_book.py из paper_end / paper_crowd / paper_fast; день бота — UTC ── */
const BOOK=__BOOK_DATA__;
const SC=document.getElementById('scene');
const $=id=>document.getElementById(id);
const esc=x=>String(x==null?'':x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const MI='\u2212';
const num=(v,d)=>(v>0?'+':v<0?MI:'')+Math.abs(v).toFixed(d).replace('.',',');
const numS=v=>{const a=Math.abs(v);return a>=100?num(v,0):a>=10?num(v,1):num(v,2)};
const pct=v=>v==null?'—':num(v,2)+'%';
const usd=v=>{const r=Math.round(v);return (r>0?'+':r<0?MI:'')+Math.abs(r).toLocaleString('ru-RU')+' $'};
const usdN=v=>{const r=Math.round(v);return (r>0?'+':r<0?MI:'')+Math.abs(r).toLocaleString('ru-RU')};
const sg=v=>(v||0)<0?'ros':'lt';
const f2=x=>String(Math.round(x*100)/100);
const fit=(s,n)=>{s=String(s==null?'':s);return s.length>n?s.slice(0,n-1)+'…':s};
const T=(x,y,c,t,a,ex)=>`<text x="${f2(x)}" y="${f2(y)}" class="${c}" text-anchor="${a||'start'}"${ex?' '+ex:''}>${t}</text>`;
const Ln=(x1,y1,x2,y2,c,ex)=>`<line x1="${f2(x1)}" y1="${f2(y1)}" x2="${f2(x2)}" y2="${f2(y2)}" class="${c}"${ex?' '+ex:''}/>`;
const tm=t=>new Date(t*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
const ddmm=d=>d.slice(8,10)+'.'+d.slice(5,7);
const WD=['воскресенье','понедельник','вторник','среда','четверг','пятница','суббота'];
const WDS=['вс','пн','вт','ср','чт','пт','сб'];
const CX=800,CY=478;
const PT=(r,a)=>[CX+r*Math.sin(a*Math.PI/180),CY-r*Math.cos(a*Math.PI/180)];     // угол по часовой от верха
const ARC=(r,a0,a1)=>{const p=PT(r,a0),q=PT(r,a1);return `M${f2(p[0])} ${f2(p[1])}A${r} ${r} 0 ${a1-a0>180?1:0} 1 ${f2(q[0])} ${f2(q[1])}`};
let seed=20260916;
function rand(){seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}
const del=s=>`style="animation-delay:${s.toFixed(2)}s"`;

/* состояние экрана */
let SRC=(BOOK.live.days.length||!BOOK.back.days.length)?'live':'back';
let DAY=0, SYM=null, FILT='all', MODE='panels', OFFL=0, OFFR=0;
const NV=10, RY=312, RS=40;   // шаг 40 — видно 10 строк, иначе нижняя ложится на рамки панелей
const S=()=>BOOK[SRC];
const DAYS=()=>S().days;
const D=()=>DAYS()[DAY]||null;
const byMoney=(a,b)=>Math.abs(b.money)-Math.abs(a.money);
const closedDay=()=>(D()?D().rows:[]).filter(r=>!r.open).sort(byMoney);
const openDay=()=>(D()?D().rows:[]).filter(r=>r.open).sort(byMoney);
const allRows=()=>DAYS().flatMap(d=>d.rows.map(r=>Object.assign({dd:d.d},r)));
const WORK=sym=>SRC==='live'?(BOOK.work||[]).find(w=>w.sym===sym):null;

/* ── ЗАДНИЙ ПЛАН: звёзды, орбита, дуга недели, шкалы приборов, рамки панелей ── */
function drawBack(){
  let o='';
  seed=7331;
  for(let i=0;i<46;i++){const x=40+rand()*1520,y=40+rand()*920;o+=`<circle cx="${f2(x)}" cy="${f2(y)}" r="${(.7+rand()*.6).toFixed(2)}" class="star" style="animation-delay:${(rand()*4).toFixed(2)}s"/>`;}
  o+=`<ellipse cx="800" cy="478" rx="430" ry="82" transform="rotate(-6 800 478)" class="orb"/><circle cx="800" cy="478" r="170" class="halo"/>`;
  // дуга недели: окружность R=4500 с центром (800, 4636)
  o+=`<path d="M110 189.21A4500 4500 0 0 1 1490 189.21" class="ln a-fi" mask="url(#rm)" ${del(.2)}/>`;
  for(let k=0;k<41;k++){const x=-50+k*42.5,y=WY(x),big=(k%4===0);o+=Ln(x,y,x,y-(big?9:4),big?'tick':'tick2');}
  // бок «выходы» слева и «депозит дня» справа: дуги R=430 вокруг центра, засечки через градус
  for(const side of [-1,1]){
    for(let a=-20;a<=20;a+=1){const big=a%5===0,r1=430,r2=big?438:434,rad=a*Math.PI/180;
      o+=Ln(CX+side*r1*Math.cos(rad),CY+r1*Math.sin(rad),CX+side*r2*Math.cos(rad),CY+r2*Math.sin(rad),big?'tk1':'tk3');}
    const p=[CX+side*430*Math.cos(20*Math.PI/180),CY+430*Math.sin(20*Math.PI/180)],q=[p[0],CY-430*Math.sin(20*Math.PI/180)];
    o+=side<0?`<path d="M${f2(p[0])} ${f2(p[1])}A430 430 0 0 1 ${f2(q[0])} ${f2(q[1])}" class="garc"/>`:`<path d="M${f2(q[0])} ${f2(q[1])}A430 430 0 0 1 ${f2(p[0])} ${f2(p[1])}" class="garc"/>`;
    o+=`<circle cx="${CX+side*430}" cy="${CY}" r="6.5" class="ret"/>`;
  }
  o+=T(396,306,'cap','ВЫХОДЫ','middle')+T(1204,306,'cap','ДЕПОЗИТ ДНЯ','middle');
  // значок и рамка заголовка «закрыты»
  o+=`<path d="M70 243V236H77M100 243V236H93M70 259V266H77M100 259V266H93" class="frm"/><circle cx="85" cy="251" r="4" class="ico"/><ellipse cx="85" cy="251" rx="10" ry="3.5" class="ico"/>`;
  // рамки четырёх панелей
  for(const [a,b] of [[70,306],[330,580],[1020,1270],[1294,1530]])
    o+=`<path d="M${a} 752V742H${a+10}M${b} 752V742H${b-10}M${a} 956V966H${a+10}M${b} 956V966H${b-10}" class="frm"/>`;
  o+=Ln(640,760,960,760,'sep')+Ln(640,858,960,858,'sep');
  o+=T(70,80,'wm','СПЯЩИЕ АЛЬТЫ')+T(70,102,'sm dim','бумажная книга бота');
  $('L_back').innerHTML=o;
  $('L_front').innerHTML=`<path d="M372.36 522.95A430 82 -6 0 0 1227.64 433.05" class="under" mask="url(#od)"/><path d="M372.36 522.95A430 82 -6 0 0 1227.64 433.05" class="orbf"/><path d="M800 206 V246" class="conn"/>`;
}
const WY=x=>4636-Math.sqrt(4500*4500-(x-800)*(x-800));

/* ── ДЕНЬ: шкала недели, заголовки, прибор в центре, боковые приборы ── */
function drawDay(){
  const d=D(), B=S();
  let o='';
  // шапка
  if(d){
    o+=`<g class="a-fi" ${del(.3)}>`+T(800,62,'ttl',`СДЕЛКИ ЗА ${ddmm(d.d)} UTC`,'middle')
      +T(800,84,'sm dim',`закрыто <tspan class="lt">${d.n}</tspan>   в работе <tspan class="lt">${d.nopen}</tspan>   итог <tspan class="${d.total<0?'ros':'lt'}">${usd(d.total)}</tspan>   депозит дня <tspan class="lt">${Math.round(BOOK.deposit).toLocaleString('ru-RU')} $</tspan>`,'middle')+`</g>`;
  }else o+=T(800,62,'ttl',SRC==='back'?'РЕКОНСТРУКЦИИ НЕТ':'ЖИВЫХ ЖУРНАЛОВ ПОКА НЕТ','middle');
  // неделя выбранного дня
  const idx={}; DAYS().forEach((x,i)=>idx[x.d]=i);
  const base=d?new Date(d.d+'T12:00:00Z'):new Date();
  const mon=new Date(base.getTime()-((base.getUTCDay()+6)%7)*864e5);
  const iso=t=>new Date(t).toISOString().slice(0,10);
  for(let k=0;k<7;k++){
    const t=mon.getTime()+k*864e5, ds=iso(t), x=290+170*k, y=WY(x), wd=new Date(t).getUTCDay(), i=idx[ds];
    const on=d&&ds===d.d, has=i!=null;
    o+=`<g class="a-fi" ${del(.35+k*.05)}>`;
    o+=T(x,y-16,'xs2',on?`<tspan class="lt">${WDS[wd]}</tspan> <tspan class="lt big2">${+ds.slice(8,10)}</tspan>`:`<tspan class="dim">${WDS[wd]}</tspan> <tspan class="mid">${+ds.slice(8,10)}</tspan>`,'middle');
    if(has){const X=DAYS()[i],v=X.total;o+=T(x,y+20,'xs '+(on?'amb':(v<0?'ros':'mid')),X.n?usd(v):(X.nopen?`в работе ${X.nopen}`:'сделок нет'),'middle');}
    else o+=T(x,y+20,'xs dim2','нет данных','middle');
    if(has&&!on) o+=`<rect x="${x-80}" y="${f2(y-30)}" width="160" height="58" class="hit" data-act="day" data-i="${i}"><title>${esc('день бота '+ddmm(ds)+' UTC')}</title></rect>`;
    o+=`</g>`;
    if(on) o+=`<path d="M${x-85} ${f2(WY(x-85)+4)}A4500 4500 0 0 1 ${x+85} ${f2(WY(x+85)+4)}" class="dayon"/>`;
  }
  // соседние недели, если в них есть дни
  const monIso=iso(mon.getTime()), sunIso=iso(mon.getTime()+6*864e5);
  const prev=DAYS().findIndex(x=>x.d<monIso), next=DAYS().map(x=>x.d).filter(x=>x>sunIso);
  if(prev>=0) o+=T(120,WY(120)-16,'xs2 amb','‹ раньше','middle')+`<rect x="80" y="${f2(WY(120)-30)}" width="80" height="26" class="hit" data-act="day" data-i="${prev}"/>`;
  if(next.length){const ni=idx[next[next.length-1]];o+=T(1480,WY(1480)-16,'xs2 amb','позже ›','middle')+`<rect x="1440" y="${f2(WY(1480)-30)}" width="80" height="26" class="hit" data-act="day" data-i="${ni}"/>`;}
  // заголовок дня в центре
  if(d){
    const full=DAYS().filter(x=>x.n), best=full.length?Math.max(...full.map(x=>x.total)):0, worst=full.length?Math.min(...full.map(x=>x.total)):0;
    o+=`<g class="a-fi" ${del(.9)}>`+T(800,180,'ttl',`${WD[new Date(d.d+'T12:00:00Z').getUTCDay()].toUpperCase()} · ${ddmm(d.d)}`,'middle')
      +T(800,199,'sm amb',`лучший день ${usd(best)} · худший ${usd(worst)}`,'middle')+`</g>`;
  }
  // кольцо засечек
  o+=`<g class="a-si">`;
  for(let a=0;a<360;a+=3.75){const big=a%30===0,p=PT(222,a),q=PT(big?212:219,a);o+=Ln(p[0],p[1],q[0],q[1],big?'tk1':'tk3');}
  o+=`<circle cx="800" cy="478" r="228" class="ring0"/></g>`;
  if(d){
    // в работе — точки по внешнему кругу
    const k=Math.min(d.nopen,60);
    for(let i=0;i<k;i++){const p=PT(244,i*360/k);o+=`<circle cx="${f2(p[0])}" cy="${f2(p[1])}" r="2.3" class="wdot a-fi" ${del(.8+i*.03)}/>`;}
    if(d.nopen) o+=T(1022,339,'xs amb',`в работе ${d.nopen}`);
    // закрытые — сегменты; красные — сделки в минусе
    const cl=d.rows.filter(r=>!r.open).sort((a,b)=>a.at-b.at), m=Math.min(cl.length,48);
    const step=m?360/m:0, g=Math.min(2,step*.15);
    for(let i=0;i<m;i++) o+=`<path d="${ARC(204,i*step+g,(i+1)*step-g)}" class="cseg${cl[Math.floor(i*cl.length/m)].money<0?' m':''} a-fi" ${del(.6+i*.02)}/>`;
    o+=T(573,347,'xs dim',d.n?`закрыто ${d.n} · <tspan class="lt">попаданий ${d.hit}%</tspan>`:`закрыто ${d.n}`,'end');
    // попадания — дуга от верха
    if(d.n){
      const h=Math.max(0,Math.min(99.9,d.hit))*3.6, p=PT(192,h);
      if(h>0){o+=`<path d="${ARC(192,0,h)}" class="hitg" filter="url(#g1)"/><path d="${ARC(192,0,h)}" pathLength="1" class="hitl a-dr" ${del(1)}/>`;}
      o+=`<path d="${ARC(192,h,359.9)}" class="hitr"/><circle cx="${f2(p[0])}" cy="${f2(p[1])}" r="3" class="hitdot"/>`;
      // подпись попаданий стоит рядом с «закрыто» (17.09: у кольца она ложилась на «10 000 $» справа)
    }
  }
  // диск и итог бота
  o+=`<circle cx="800" cy="478" r="160" fill="url(#disc)"/><circle cx="800" cy="478" r="160" class="rim"/><circle cx="800" cy="478" r="156" fill="url(#hi)"/>`
    +`<circle cx="800" cy="478" r="60" class="sonar"/><circle cx="800" cy="478" r="100" class="sonar"/><circle cx="800" cy="478" r="130" class="sonar"/>`;
  // выходы дня — полоска внутри диска: слева событие и цель, справа срок
  const ex=d?d.ex:null;
  o+=Ln(688,540,912,540,'ax')+Ln(800,534,800,546,'ax');
  if(ex&&(ex.ev!=null||ex.tm!=null)){
    const mx=Math.max(Math.abs(ex.ev||0),Math.abs(ex.tm||0))||1, k=Math.min(14,100/mx);
    const le=Math.abs(ex.ev||0)*k, re=Math.abs(ex.tm||0)*k;
    if(ex.ev!=null){o+=Ln(800,540,800-le,540,(ex.ev<0?'legr':'legw'))+T(800-le-4,562,'xs '+sg(ex.ev),numS(ex.ev)+' $','end');}
    if(ex.tm!=null){o+=Ln(800,540,800+re,540,(ex.tm<0?'legr':'legw'))+T(800+re+2,562,'xs '+sg(ex.tm),numS(ex.tm)+' $','start');}
    o+=T(800,578,'xs2 dim','событие и цель · по сроку','middle');
  }else o+=T(800,578,'xs2 dim',d?'закрытых за день нет':'—','middle');
  const tot=B.total;
  o+=`<g class="a-fi" ${del(1.4)}>`+T(800,416,'cap','ИТОГ БОТА','middle')
    +`<text x="800" y="484" text-anchor="middle" class="bigg" filter="url(#g2)">${usd(tot)}</text>`
    +T(800,484,'big'+(tot<0?' ros':''),`${usdN(tot)}<tspan class="bigu" dx="6">$</tspan>`,'middle')
    +T(800,508,'sm dim',DAYS().length?(SRC==='back'?`задним числом за ${DAYS().length} дн`:`закрытые за ${DAYS().length} дн`):'закрытых сделок нет','middle')+`</g>`;
  // бок слева: выходы за все дни источника
  const E=B.ex||{};
  const gk=Math.min(2.5,18/(Math.max(Math.abs(E.tm||0),Math.abs(E.ev||0))||1));
  const mk=(v,c)=>{const a=-v*gk*Math.PI/180;return Ln(CX-432*Math.cos(a),CY+432*Math.sin(a),CX-454*Math.cos(a),CY+454*Math.sin(a),c)};
  if(E.tm!=null) o+=mk(E.tm,E.tm<0?'mk-r':'mk-w');
  if(E.ev!=null) o+=mk(E.ev,E.ev<0?'mk-r':'mk-w');
  o+=T(404,402,'big2x'+(E.tm<0?' ros':''),E.tm==null?'—':`${numS(E.tm)}<tspan class="bigu2">$</tspan>`)
    +T(406,422,'xs dim','по сроку, на сделку')
    +T(404,560,'big2x'+(E.ev<0?' ros':''),E.ev==null?'—':`${numS(E.ev)}<tspan class="bigu2">$</tspan>`)
    +T(406,580,'xs dim','событие и цель, на сделку')
    +T(406,612,'xs lt',`сделок ${E.ev_n||0} против ${E.tm_n||0} · за ${DAYS().length} дн`);
  // бок справа: итог дня к депозиту
  const dp=d?d.total/BOOK.deposit*100:0, ra=-Math.max(-19,Math.min(19,dp*10))*Math.PI/180;
  o+=Ln(CX+432*Math.cos(ra),CY+432*Math.sin(ra),CX+454*Math.cos(ra),CY+454*Math.sin(ra),'mk-a')
    +Ln(CX+432*Math.cos(ra),CY+432*Math.sin(ra),CX+454*Math.cos(ra),CY+454*Math.sin(ra),'mk-a','filter="url(#g1)"')
    +T(1196,410,'big2x'+(dp<0?' ros':''),`${num(dp,2)}<tspan class="bigu2">%</tspan>`,'end')
    +T(1194,430,'xs dim','итог дня к депозиту','end')
    +T(1196,560,'big2x',`${Math.round(BOOK.deposit).toLocaleString('ru-RU')}<tspan class="bigu2">$</tspan>`,'end')
    +T(1194,580,'xs dim','депозит дня','end')
    +T(1194,612,'xs lt','вес правила решает долю','end');
  $('L_day').innerHTML=o;
}

/* ── КОЛОНКИ: закрытые слева, в работе справа; колесо и стрелки листают ── */
function drawCols(anim){
  // СТРОКА В ДВА ЯРУСА С ВОЗДУХОМ (17.09, владелец: «расстояние как в макете, сейчас сливается причина и
  // название»): имя и точка, деньги справа; ниже стрелка стороны, ход и правило; шаг строки 40 (владелец: +3, потом ещё +5)
  const cl=closedDay(), op=openDay();
  OFFL=Math.max(0,Math.min(OFFL,Math.max(0,cl.length-NV))); OFFR=Math.max(0,Math.min(OFFR,Math.max(0,op.length-NV)));
  const seen=(off,n)=>`видно ${off+1}–${Math.min(n,off+NV)} из ${n}`;
  const row=(r,k,x0,x1,selx,hx0,dot)=>{const y=RY+k*RS;
    return `<g class="row${r.sym===SYM?' on':''}${anim?' a-fl':''}" data-sym="${esc(r.sym)}" ${anim?del(.9+k*.05):''}>`
      +`<rect x="${selx}" y="${y-13}" width="2" height="30" class="sel"/>`
      +T(x0,y,'tk',`${esc(r.sym)}<tspan class="${dot}" dx="7" font-size="8">●</tspan>`)
      +T(x1,y,'mono sm '+sg(r.money),usd(r.money),'end')
      +T(x0,y+15,'xs2 dim',`<tspan class="dim2">${r.side<0?'▼':'▲'}</tspan> <tspan class="mono ${r.res==null?'dim2':(r.res<0?'ros':'mid')}">${r.open&&r.res==null?'цена отстала':pct(r.res)}</tspan> ${esc(fit(r.rule,18))}`)
      +`<rect x="${hx0}" y="${y-16}" width="252" height="${RS}" class="hit" data-act="coin" data-sym="${esc(r.sym)}"><title>${esc(r.book+' · '+r.rl+'\n'+r.why)}</title></rect></g>`;
  };
  let o='<g class="fc">'+T(114,250,'ttl','ЗАКРЫТЫ')+T(114,269,'sm amb',cl.length>NV?seen(OFFL,cl.length):'итог зафиксирован')+T(300,262,'cnt',cl.length,'end');
  if(!cl.length) o+=T(74,RY,'xs dim',D()?'закрытых за день нет':'—');
  cl.slice(OFFL,OFFL+NV).forEach((r,k)=>{o+=row(r,k,74,300,62,58,'dim');});
  if(cl.length>NV){o+=chev(290,284,-1,'L',OFFL>0)+chev(290,RY+NV*RS-8,1,'L',OFFL+NV<cl.length);}
  const hx=1530-String(op.length).length*24-14;      // число крупное — заголовок левее на его ширину
  o+='</g><g class="fw">'+T(hx,250,'ttl','В РАБОТЕ','end')+T(hx,269,'sm amb',op.length>NV?seen(OFFR,op.length):'деньги от цены сейчас','end')+T(1530,262,'cnt',op.length,'end');
  if(!op.length) o+=T(1530,RY,'xs dim',SRC==='back'?'в реконструкции открытых нет':'открытых позиций нет','end');
  op.slice(OFFR,OFFR+NV).forEach((r,k)=>{o+=row(r,k,1320,1530,1538,1296,'amb');});
  if(op.length>NV){o+=chev(1310,284,-1,'R',OFFR>0)+chev(1310,RY+NV*RS-8,1,'R',OFFR+NV<op.length);}
  o+='</g>';
  $('L_cols').innerHTML=o;
}
function chev(x,y,dir,col,on){
  const d=dir<0?`M${x-6} ${y+4}l6 -6l6 6`:`M${x-6} ${y-4}l6 6l6 -6`;
  return `<path d="${d}" class="chev${on?'':' off'}"/>`+(on?`<rect x="${x-14}" y="${y-12}" width="28" height="24" class="hit" data-act="scroll" data-col="${col}" data-dir="${dir}"/>`:'');
}

/* ── МОНЕТА: заголовок справа и четыре панели; «разбор позиции» — те же рамки ── */
function drawCoin(){
  let o='';
  const rows=allRows().filter(r=>r.sym===SYM).sort((a,b)=>(b.open-a.open)||((b.at||0)-(a.at||0)));   // открытая — первой
  const w=SYM?WORK(SYM):null;
  if(!SYM||!rows.length){ $('L_coin').innerHTML=T(1530,74,'hdr','—','end')+T(84,764,'cap','СДЕЛКИ')+T(84,800,'xs dim','выберите монету в колонке'); return; }
  const rules=[...new Set(rows.map(r=>r.rule))];
  if(MODE==='pos'&&w){ $('L_coin').innerHTML=drawPos(w,rows); return; }
  o+=`<g class="a-fi" ${del(0)}>`+T(1530,74,'hdr',esc(SYM),'end')+T(1530,96,'sm dim',`${rows.length} ${rows.length===1?'сделка':rows.length<5?'сделки':'сделок'} за ${DAYS().length} дн · правил ${rules.length}`,'end')+`</g>`;
  o+=T(84,764,'cap','СДЕЛКИ')+T(344,764,'cap','ПУТЬ К ЦЕЛИ')+T(1034,764,'cap','ПРАВИЛА')+T(1308,764,'cap','ИТОГ ПО МОНЕТЕ')+T(1256,764,'xs dim','за день '+(D()?ddmm(D().d):''),'end');
  // сделки монеты
  o+=T(292,764,'sm lt',esc(SYM),'end');
  const shown=rows.slice(0,3);
  shown.forEach((r,j)=>{const y=798+j*40;
    o+=`<circle cx="88" cy="${y-4}" r="2.6" class="${r.open?'odc':'cdot'}"/>`+T(98,y,'sm lt',esc(fit(r.rule,20)))
      +T(98,y+18,'mono xs dim',ddmm(r.dd))+T(214,y+18,'mono xs dim',pct(r.res),'end')+T(292,y+18,'mono sm '+sg(r.money),usd(r.money),'end');
  });
  const open=rows.some(r=>r.open);
  let fy=884;
  if(shown.length===1) o+=`<rect x="84" y="830" width="${open?64:58}" height="18" rx="2" class="pill ${open?'pw':'pc'}"/>`+T(92,843,'xs '+(open?'amb':'dim'),open?'в работе':'закрыта');
  else fy=Math.max(884,798+shown.length*40+14);
  o+=T(84,fy,'xs dim',`сделок ${rows.length}`+(rows.length>3?' · видно 3':''))+T(292,fy,'xs dim',`правил ${rules.length}`,'end');
  // путь к цели — последняя сделка
  const r=rows[0];
  o+=T(344,802,'sm lt',esc(fit('последняя: '+r.rule,34)));
  o+=T(344,818,'xs dim',esc(fit(r.open?('поставлена '+(r.ent?tm(r.ent):ddmm(r.dd))):('закрыта: '+r.why),42)));
  const tg=r.open&&w?w.tgt_pct:null, st=r.open&&w?w.stop_pct:null, res=r.res||0;
  const R=Math.max(3,Math.ceil(Math.max(Math.abs(res),tg||0,st||0)*1.1));
  const X=v=>455+Math.max(-1,Math.min(1,v/R))*105;
  o+=Ln(350,862,560,862,'ax');
  for(let k=-3;k<=3;k++){const v=R*k/3,x=455+k*35;o+=Ln(x,859,x,865,'tk3')+T(x,880,'mono xs2 '+(k?'dim2':'dim'),k?num(Math.round(v*10)/10,Number.isInteger(Math.round(v*10)/10)?0:1):'вход','middle');}
  o+=Ln(455,848,455,868,'entry');
  if(st!=null) o+=Ln(X(-st),846,X(-st),868,'stp')+T(X(-st)-3,838,'xs ros','стоп '+num(-st,1)+'%','end');   // влево от черты
  if(tg!=null){o+=Ln(X(tg),840,X(tg),868,'tgt')+Ln(X(tg),840,X(tg),868,'tgt','filter="url(#g1)"')+T(X(tg)+3,834,'xs amb','цель '+num(tg,1)+'%','start');   // вправо от черты
    if(res>=tg) o+=T(455,916,'xs amb','цель пройдена — закроется на ближайшем прогоне','middle');
    else o+=`<path d="M${f2(X(res))} 900H${f2(X(tg))}" class="gap"/>`+T((X(res)+X(tg))/2,916,'xs lt','до цели '+num(tg-res,2).replace('+','')+'%','middle');}
  else if(r.open&&w&&w.goal) o+=T(455,916,'xs amb',esc(fit(w.goal.k+' '+w.goal.v,40)),'middle');
  o+=Ln(455,862,X(res),862,res<0?'legr':'legw')+`<path d="M${f2(X(res))} 856l5 6l-5 6l-5 -6z" class="now"/>`+T(X(res),852,'mono xs lt',pct(r.res),'middle');
  // правила выбранного дня
  const dr=D()?D().rows:[], g={};
  dr.forEach(x=>{const q=g[x.rule]||(g[x.rule]={n:0,op:0,sum:0,cl:0});q.n++;if(x.open)q.op++;else{q.sum+=x.money;q.cl++;}});
  const top=Object.entries(g).sort((a,b)=>Math.abs(b[1].sum)-Math.abs(a[1].sum)||b[1].n-a[1].n).slice(0,3);
  const mx=Math.max(...top.map(([,q])=>Math.abs(q.sum)),1);
  top.forEach(([k,q],j)=>{const y=800+j*54, bw=Math.abs(q.sum)/mx*110;
    o+=T(1034,y,'sm lt',esc(fit(k,22)))+T(1256,y,'mono sm '+(q.cl?sg(q.sum):'dim'),q.cl?usd(q.sum):'в работе','end')
      +Ln(1034,y+14,1256,y+14,'ax')+Ln(1145,y+9,1145,y+19,'tk1')
      +(q.cl?`<rect x="${f2(q.sum<0?1145-bw:1145)}" y="${y+12}" width="${f2(Math.max(1,bw))}" height="4" class="${q.sum<0?'barr':'barw'}"/>`:'')
      +T(1034,y+32,'xs dim',`строк ${q.n} · в работе ${q.op}`);
  });
  if(!top.length) o+=T(1034,800,'xs dim','за день сделок нет');
  // итог по монете
  const cl=rows.filter(x=>!x.open), base=cl.length?cl:rows;
  const avg=base.filter(x=>x.res!=null); const av=avg.length?avg.reduce((s,x)=>s+x.res,0)/avg.length:null;
  const best=base.reduce((a,b)=>a.money>b.money?a:b), worst=base.reduce((a,b)=>a.money<b.money?a:b);
  const lines=[['закрытых',cl.length?String(cl.length):'нет','lt'],['в среднем на сделку',pct(av),sg(av)],
    ['сделок',`${rows.length} · ${open?'в работе':'закрыты'}`,'lt'],['лучшая',usd(best.money),sg(best.money)],
    ['худшая',usd(worst.money),sg(worst.money)],['правило',esc(fit(r.rule,18)),'lt']];
  lines.forEach(([k,v,c],j)=>{const y=798+j*24;o+=Ln(1308,y+8,1516,y+8,'sepl')+T(1308,y,'xs dim',k)+T(1516,y,'mono xs '+c,v,'end');});
  $('L_coin').innerHTML=o;
}

/* разбор открытой позиции — в тех же четырёх рамках */
function drawPos(w,rows){
  const short=w.side<0, f=w.fast||{};
  const cc=t=>t==='key'?'amb':t==='bad'?'ros':t==='good'?'lt':'mid';
  let o=`<g class="a-fi" ${del(0)}>`+T(1530,74,'hdr',esc(w.sym),'end')
    +T(1530,96,'sm dim',`разбор позиции · ${short?'шорт':'лонг'} · ${esc(w.book)} · вход ${w.opened?tm(w.opened):'—'}`,'end')+`</g>`;
  const tip=`<title>${esc('Почему взята. '+String(w.why||'').replace(/\{T:(\d+)\}/g,(m,t)=>tm(+t))+'\n\nЧего ждём. '+String(w.wait||'').replace(/\{T:(\d+)\}/g,(m,t)=>tm(+t)))}</title>`;
  // 1: чего ждём и когда закроется
  let gk=w.goal?w.goal.k:'ждём', gv=w.goal?w.goal.v:'—', gs=w.goal?(w.goal.s||''):'';
  if(w.done){gk='сработало';gv=fit((w.done_list||[])[0]||'',22);gs='закроется на ближайшем прогоне';}
  o+=`<g>${tip}<rect x="70" y="742" width="236" height="224" class="hit"/>`+T(84,764,'cap','ЧЕГО ЖДЁМ')+T(292,764,'sm '+sg(w.res),pct(w.res),'end')
    +T(84,790,'xs dim',esc(fit(gk,34)))+T(84,812,'goalv',esc(fit(gv,22)))+T(84,830,'xs dim',esc(fit(gs,40)));
  (w.close||[]).slice(0,3).forEach((c,j)=>{const y=858+j*30,k=String(c.k).split(' ')[0],col=k==='цель'?'amb':k==='стоп'?'ros':'lt';
    o+=T(84,y,'xs lt',esc(fit(c.k,14)))+T(292,y,'mono xs '+col,esc(fit(c.v,16)),'end')
      +T(84,y+11,'xs3 dim2',esc(fit(String(c.sh||'').replace(/\{T:(\d+)\}/g,(m,t)=>tm(+t)),40)))
      +Ln(84,y+16,292,y+16,'sepl');
    if(c.f!=null){const fw=Math.max(1,Math.min(1,c.f)*208);o+=`<rect x="84" y="${y+15}" width="${f2(fw)}" height="2" class="${k==='цель'?'bara':k==='стоп'?'barr':'bard'}"/>`;}
  });
  o+=`</g>`;
  // 2: почему взята
  o+=T(344,764,'cap','ПОЧЕМУ ВЗЯТА');
  (w.facts||[]).slice(0,7).forEach((x,j)=>{const y=792+j*22;o+=T(344,y,'xs dim',esc(fit(x.k,26)))+T(566,y,'mono xs '+cc(x.t),esc(fit(String(x.v).replace(/\{T:(\d+)\}/g,(m,t)=>tm(+t)),14)),'end')+Ln(344,y+7,566,y+7,'sepl');});
  o+=T(344,952,'xs3 dim2',esc(fit(w.rl,44)));
  // 3: что сейчас
  o+=T(1034,764,'cap','ЧТО СЕЙЧАС')+T(1256,764,'xs dim',w.d24!=null?'за 24 ч '+num(w.d24,1)+'%':'','end');
  (w.now||[]).slice(0,7).forEach((x,j)=>{const y=792+j*22;o+=T(1034,y,'xs dim',esc(fit(x.k,24)))+T(1256,y,'mono xs '+cc(x.t),esc(fit(x.v,14)),'end')+Ln(1034,y+7,1256,y+7,'sepl');});
  if(w.walls) o+=T(1034,952,'xs3 dim2',esc(fit('стакан: '+w.walls,44)));
  // 4: быстрые линии и режим — наблюдение
  o+=T(1308,764,'cap','БЫСТРЫЕ · НАБЛЮДЕНИЕ');
  const L=[];
  if(f.vx){const v=f.vx_state||{},good=(v.who==='продавцы'&&short)||(v.who==='покупатели'&&!short),bad=(v.who==='продавцы'&&!short)||(v.who==='покупатели'&&short);
    L.push(['вортекс 30м',v.who==='ровно'?'серии нет':'давят '+v.who+' · '+v.bars,good?'lt':bad?'ros':'mid']);}
  if(f.kl){const k=f.kl_state||{},good=(k.state==='выдыхается'&&short)||(k.state==='продавцы выдыхаются'&&!short),bad=(k.state==='выдыхается'&&!short)||(k.state==='продавцы выдыхаются'&&short);
    L.push(['клингер 30м',k.state||'—',good?'lt':bad?'ros':'mid']);}
  if(f.jn){const dm=x=>Math.floor(x/60)+':'+String(x%60).padStart(2,'0');L.push(['до «'+f.jn.next+'»',dm(f.jn.in_min)+' · у вас '+tm(f.jn.next_t).slice(-5),'amb']);}
  if(f.lev){const good=short?f.lev.state==='уходит':f.lev.state==='держит';L.push(['плечо',f.lev.state+' '+num(f.lev.off,1)+'%',good?'lt':'ros']);}
  (f.regime||[]).forEach(x=>L.push([x.k,x.v,'mid']));
  if(!L.length) L.push(['быстрых нет','архив короткий','dim']);
  L.slice(0,7).forEach(([k,v,c],j)=>{const y=792+j*22;o+=T(1308,y,'xs dim',esc(fit(k,18)))+T(1516,y,'mono xs '+c,esc(fit(v,20)),'end')+Ln(1308,y+7,1516,y+7,'sepl');});
  o+=T(1308,952,'xs3 dim2','боты это не читают');
  return o;
}

/* ── УПРАВЛЕНИЕ: источник, заново, звёзды, переключатель колонок, кнопка разбора, подвал ── */
function drawCtl(){
  let o='';
  o+=`<g data-act="replay"><path d="M78 125a6 6 0 1 1 -2 -4.5" class="chev"/><path d="M76 117v4.2h4" class="chev"/>`+T(90,129,'xs dim','заново')+`<rect x="66" y="112" width="70" height="24" class="hit"/></g>`;
  [['live','живые',150],['back','задним числом',206]].forEach(([k,t,x])=>{
    const has=BOOK[k].days.length, on=SRC===k;
    o+=T(x,129,'xs '+(on?'amb':has?'mid':'dim2'),t)+(has&&!on?`<rect x="${x-4}" y="114" width="${t.length*6+8}" height="22" class="hit" data-act="src" data-k="${k}"/>`:'');
  });
  o+=`<a href="intro.html">`+T(1530,124,'xs dim','← звёзды','end')+`<rect x="1470" y="110" width="64" height="22" class="hit"/></a>`;
  // переключатель
  o+=T(752,806,'ctl'+(FILT==='c'?' on':''),'ЗАКРЫТЫ','end')+T(752,824,'xs2 dim','итог зафиксирован','end')
    +`<path d="M772 796l-6 6l6 6" class="chev"/><path d="M828 796l6 6l-6 6" class="chev"/>`
    +`<g class="retc"><circle cx="800" cy="802" r="13" class="rtc"/><circle cx="800" cy="802" r="18" class="rtd"/><circle cx="800" cy="802" r="2" class="odc"/></g>`
    +T(800,838,'xs2 '+(FILT==='all'?'amb':'dim'),'все','middle')
    +T(848,806,'ctl'+(FILT==='w'?' on':''),'В РАБОТЕ')+T(848,824,'xs2 dim','ждём цели или события')
    +`<rect x="650" y="788" width="126" height="42" class="hit" data-act="filt" data-f="c"/>`
    +`<rect x="780" y="782" width="40" height="62" class="hit" data-act="filt" data-f="all"/>`
    +`<rect x="824" y="788" width="136" height="42" class="hit" data-act="filt" data-f="w"/>`;
  // кнопка разбора
  const w=SYM?WORK(SYM):null;
  const txt=MODE==='pos'?'← вернуть панели монеты':(w?'разбор позиции: почему взята и чего ждём':(SRC==='back'?'разбор — только у живых позиций':'у выбранной монеты позиции нет'));
  o+=`<rect x="640" y="876" width="320" height="34" rx="3" class="btn${w?'':' off'}"/>`+(w?`<rect x="640" y="876" width="320" height="34" rx="3" fill="url(#bt)"/>`:'')
    +T(800,898,'sm '+(w?'amb':'dim2'),txt,'middle')+(w?`<rect x="640" y="876" width="320" height="34" class="hit" data-act="pos"/>`:'')
    +T(800,938,'xs dim','вес правила решает, сколько депозита дня получила сделка','middle');
  // подвал
  const bt=new Date(BOOK.built*1000);
  o+=T(1530,990,'xs dim2',`сборка ${bt.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})} · время ваше · день бота по UTC`,'end');
  const note=SRC==='back'?'реконструкция по архиву — для сравнения правил, не обещание денег':'у открытых деньги от цены сейчас, в итог дня не входят';
  o+=T(70,990,'xs dim2',esc(note));
  $('L_ctl').innerHTML=o;
  SC.classList.toggle('f-c',FILT==='c'); SC.classList.toggle('f-w',FILT==='w');
}

/* ── сборка и события ── */
function pickDefault(){
  const op=openDay(), cl=closedDay();
  const keep=SYM&&(op.some(r=>r.sym===SYM)||cl.some(r=>r.sym===SYM));
  if(!keep) SYM=(op[0]||cl[0]||{}).sym||null;
  if(MODE==='pos'&&!(SYM&&WORK(SYM))) MODE='panels';
}
function drawAll(){ pickDefault(); drawDay(); drawCols(true); drawCoin(); drawCtl(); }
function selectCoin(sym){
  SYM=sym; if(MODE==='pos'&&!WORK(sym)) MODE='panels';
  SC.querySelectorAll('.row').forEach(g=>g.classList.toggle('on',g.dataset.sym===sym));
  drawCoin(); drawCtl();
}
SC.addEventListener('click',e=>{
  const t=e.target.closest('[data-act]'); if(!t) return;
  const a=t.dataset.act;
  if(a==='coin') selectCoin(t.dataset.sym);
  else if(a==='day'){ DAY=+t.dataset.i; OFFL=OFFR=0; drawAll(); }
  else if(a==='src'){ SRC=t.dataset.k; DAY=0; OFFL=OFFR=0; MODE='panels'; drawBack(); drawAll(); }
  else if(a==='filt'){ const f=t.dataset.f; FILT=(FILT===f||f==='all')?'all':f; drawCtl(); }
  else if(a==='pos'){ MODE=MODE==='pos'?'panels':'pos'; drawCoin(); drawCtl(); }
  else if(a==='replay'){ drawBack(); drawAll(); }
  else if(a==='scroll'){ scrollCol(t.dataset.col,+t.dataset.dir*NV); }
});
function scrollCol(col,d){
  if(col==='L') OFFL+=d; else OFFR+=d;
  drawCols(false);
}
function svgPt(ev){const p=SC.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;const m=SC.getScreenCTM();return m?p.matrixTransform(m.inverse()):{x:0,y:0};}
SC.addEventListener('wheel',e=>{
  const p=svgPt(e); if(p.y<230||p.y>740) return;
  const col=p.x<330?'L':p.x>1270?'R':null; if(!col) return;
  e.preventDefault(); scrollCol(col,e.deltaY>0?1:-1);
},{passive:false});
let tY=null,tCol=null;
SC.addEventListener('touchstart',e=>{const p=svgPt(e.touches[0]);tCol=(p.y>230&&p.y<740)?(p.x<330?'L':p.x>1270?'R':null):null;tY=e.touches[0].clientY;},{passive:true});
SC.addEventListener('touchmove',e=>{if(!tCol)return;const dy=e.touches[0].clientY-tY;if(Math.abs(dy)>24){scrollCol(tCol,dy<0?1:-1);tY=e.touches[0].clientY;}},{passive:true});
addEventListener('keydown',e=>{if(e.key==='Escape'&&MODE==='pos'){MODE='panels';drawCoin();drawCtl();}});
drawBack(); drawAll();
// телефон стоя: сцена шире экрана и листается вбок — открываем её на центральном приборе
(function(){const v=document.querySelector('.vp'); if(v&&v.scrollWidth>v.clientWidth+4) v.scrollLeft=(v.scrollWidth-v.clientWidth)/2;})();
</script>
</body></html>
"""


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="экран книги бота")
    ap.add_argument("--data", action="store_true", help="напечатать данные экрана вместо сборки")
    a = ap.parse_args()
    if a.data:
        dd = book_data()
        for key, name in (("live", "живые"), ("back", "задним числом")):
            d = dd[key]
            print(f"{name}: итог закрытых {d['total']:+.2f} $ за {len(d['days'])} дн")
            for x in d["days"]:
                print(f"  {x['d']} · закрыто {x['n']} · в работе {x['nopen']} · итог {x['total']:+.2f} $ · попаданий {x['hit']}%")
    else:
        out = BASE_DIR / "output" / "book.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render_book(), encoding="utf-8")
        print(f"книга: {out}")
