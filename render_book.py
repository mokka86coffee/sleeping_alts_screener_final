#!/usr/bin/env python3
"""ЭКРАН КНИГИ БОТА (16.09, владелец: «это торговый бот, подумай как лучше, на реальных данных без
моего участия, калибровать будем отдельно»). Вид — прототип book_proto-2 (16.09, принят): шар итога,
колонка дней, веер сделок дня по дуге, панель монеты по клику.

Читает открытые позиции и журналы трёх бумажных книг — paper_end (шорт по концу хода), paper_crowd
(спайк, рост на выносе, против толпы, перекупленность, провал, прокол дна, первый час Лондона) и
paper_fast (вортекс, хедж и флип), цену и суточный ход из near_move, стены из depth.

Экран:
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

try:
    from core_config import PAPER_CROWD_STOP, PAPER_CROWD_HOLD
except ImportError:
    PAPER_CROWD_STOP, PAPER_CROWD_HOLD = 0.02, 6
try:
    from core_config import SPIKE_FUND_NEG, PAPER_FAST_OI_BARS
except ImportError:
    SPIKE_FUND_NEG, PAPER_FAST_OI_BARS = -0.01, 4
BAR_S = 1800                                  # получасовка — единица срока у ботов

BOOKS = (("конец", "paper_end"), ("толпа", "paper_crowd"), ("быстрые", "paper_fast"))
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
                "stem": stem, "raw": p, "legs": legs,
            })
        closed += _closed_rows(stem, book, cut)
    opened.sort(key=lambda x: -(abs(x["res"]) if x["res"] is not None else 0))
    closed.sort(key=lambda x: -(x["at"] or 0))
    return opened, closed


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
    out.sort(key=lambda x: x["t"])
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
    bars = len(after) if rows and t_sig else o["bars"]
    sgn = "шорт" if side < 0 else "лонг"
    a = {"sym": o["sym"].replace("USDT", ""), "book": o["book"], "side": side, "size": o["size"], "rule": o["rk"],
         "rl": o["rule"], "entry": e, "px": px, "px_src": px_src, "d24": o.get("d24"), "bars": bars,
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


def _exit_text(p: dict) -> str:
    """условие выхода открытой позиции словами с числом"""
    res = p["res"] or 0.0
    tgt, stop, hold = p.get("target"), p.get("stop"), p.get("hold")
    left = (int(hold) - p["bars"]) if hold else None
    bits = []
    if tgt:
        bits.append(f"цель {float(tgt) * 100:.1f}%, до неё {max(0.0, float(tgt) * 100 - res):.2f}%")
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
    w = sum(float(r.get("size") or 1) for r in rows) or 1.0
    out = []
    for r in rows:
        share = BOOK_DEPOSIT * float(r.get("size") or 1) / w
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
    w_open = sum(p["size"] for p in opened)
    for p in opened:
        p["cond"] = _exit_text(p)
        share = BOOK_DEPOSIT * p["size"] / ((per_day[today]["w"] if per_day[today]["n"] else 0) + w_open or 1.0)
        p["money"] = share * (p["res"] or 0) / 100
    out_days = []
    for d in days:
        m = per_day[d]
        rows = [_row(x, False) for x in sorted(m["rows"], key=lambda x: -(x["at"] or 0))]
        if d == today:
            rows = [_row(p, True) for p in sorted(opened, key=lambda x: -(x["at"] or 0))] + rows
        out_days.append({"d": d, "n": m["n"], "nopen": len(opened) if d == today else 0,
                         "total": round(m["total"], 2), "hit": round(m["hit"]), "rows": rows})
    allrows = [x for d in days for x in per_day[d]["rows"]]
    by_event = [x["money"] for x in allrows if not str(x.get("why") or "").startswith("срок")]
    by_time = [x["money"] for x in allrows if str(x.get("why") or "").startswith("срок")]
    note = ""
    if len(by_event) >= 3 and len(by_time) >= 3:
        note = (f"выходы по событию и цели дают {st.mean(by_event):+.1f} $ на сделку, по сроку "
                f"{st.mean(by_time):+.1f} $ · сделок {len(by_event)} против {len(by_time)}")
    return {"note": note, "total": round(sum(per_day[d]["total"] for d in days), 2), "days": out_days}


def book_data() -> dict:
    """всё, что рисует экран, одним словарём — его же удобно сверять руками"""
    opened, closed = _collect()
    back = []
    cut = _now() - BOOK_DAYS * 86400
    for book, stem in BACKFILL:
        back += _closed_rows(stem, book, cut)
    back.sort(key=lambda x: -(x["at"] or 0))
    live = _source(opened, closed)
    bk = _source([], back)
    if bk["days"]:
        bk["note"] = ("реконструкция по архиву: без события доски, запрета встречных и задержек — "
                      "для сравнения правил, не обещание денег" + (" · " + bk["note"] if bk["note"] else ""))
    work = sorted((_analyse(o) for o in opened), key=lambda x: -(x.get("nearest_f") or 0))
    return {"deposit": BOOK_DEPOSIT, "built": int(time.time()), "live": live, "back": bk, "work": work}


def render_book() -> str:
    data = json.dumps(book_data(), ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/")          # строка внутри <script> не должна закрыть тег
    return TEMPLATE.replace("__BOOK_DATA__", data)


TEMPLATE = r"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>книга · бот</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --f:Jost,"Futura","Century Gothic",sans-serif; --mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;
  --gold:#f5a93a; --gold-hi:#ffd08a; --up:#6fcf97; --pos:#f1f4f9; --dn:#ff7a7a; --ice:#eaf4ff;
  --txt:#c3cde4; --dim:#849dad; --cap:#9ebcce;
  --glass:linear-gradient(180deg,rgba(34,41,45,.62),rgba(15,17,19,.72));
  --edge:rgba(232,245,255,.09);
  --ease:cubic-bezier(.16,.84,.24,1);
}
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#07090a;color:var(--ice);font-family:var(--f);-webkit-font-smoothing:antialiased;overflow:hidden}
body{background:
  radial-gradient(1100px 820px at 44% 46%,rgba(62,88,100,.42),transparent 70%),
  radial-gradient(700px 300px at 50% -6%,rgba(182,192,213,.07),transparent 70%),
  radial-gradient(900px 420px at 60% 50%,rgba(245,169,58,.045),transparent 70%),
  linear-gradient(180deg,#18242b,#0c1317 60%,#080c0f)}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:20;
  background:radial-gradient(ellipse 110% 95% at 46% 46%,transparent 50%,rgba(0,0,0,.7) 100%)}
body::after{content:"";position:fixed;inset:0;pointer-events:none;z-index:21;opacity:.06;mix-blend-mode:overlay;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .6 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}

/* ── верхняя панель ── */
.top{position:fixed;left:0;right:0;top:0;height:64px;display:flex;align-items:center;gap:14px;padding:0 24px;z-index:9}
.brand{display:flex;align-items:center;gap:12px}
.brand .mark{width:34px;height:34px;border-radius:10px;display:grid;place-items:center;
  background:var(--glass);border:1px solid var(--edge);box-shadow:inset 0 1px 0 rgba(232,245,255,.08)}
.brand h1{margin:0;font-weight:300;font-size:15px;line-height:1.05;letter-spacing:.34em;text-transform:uppercase}
.brand h1 small{display:block;margin-top:3px;font-size:9.5px;letter-spacing:.24em;color:var(--dim);font-weight:400}
.tools{position:absolute;left:50%;transform:translateX(-50%);display:flex;gap:8px}
.grp{display:flex;align-items:center;gap:2px;padding:4px;border-radius:12px;background:rgba(15,17,19,.7);
  border:1px solid var(--edge);box-shadow:inset 0 1px 0 rgba(232,245,255,.06),0 10px 24px -16px #000}
.grp span{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;color:var(--dim);padding:6px 10px;border-radius:8px;white-space:nowrap}
.grp span b{font-weight:500;color:var(--ice)}
.grp span b.g{color:var(--gold-hi)}
.grp.src button{font-family:var(--mono);font-size:10.5px;letter-spacing:.06em;color:var(--dim);padding:6px 10px;border-radius:8px;
  border:0;background:none;cursor:pointer;white-space:nowrap}
.grp.src button:hover{color:var(--ice)}
.grp.src button.on{background:rgba(245,169,58,.12);color:var(--gold-hi);box-shadow:inset 0 0 0 1px rgba(245,169,58,.35)}
.grp.src button:disabled{opacity:.35;cursor:default}
.grp span.on{background:rgba(232,245,255,.06);color:var(--ice)}
.acts{margin-left:auto;display:flex;gap:8px}
.btn{font-family:var(--f);font-size:12px;letter-spacing:.04em;color:var(--txt);background:rgba(15,17,19,.7);
  border:1px solid rgba(232,245,255,.14);border-radius:10px;padding:8px 14px;cursor:pointer;text-decoration:none;
  display:inline-flex;align-items:center;gap:8px;transition:border-color .2s,color .2s}
.btn:hover{color:var(--ice);border-color:rgba(232,245,255,.3)}
.btn:focus-visible,.day:focus-visible,.tr:focus-visible{outline:2px solid var(--gold);outline-offset:2px}

/* ── сцена ── */
.stage{position:absolute;inset:64px 0 0 0;overflow:hidden;display:grid;grid-template-columns:minmax(260px,24vw) 188px minmax(340px,1fr) clamp(360px,28vw,410px)}
#wires{position:absolute;left:0;top:0;width:100%;height:100%;pointer-events:none;z-index:1;overflow:visible}
#wires .w{fill:none}
#bandsw{position:absolute;z-index:1;pointer-events:none;overflow:hidden;
  -webkit-mask-image:linear-gradient(180deg,transparent 4%,#000 30%,#000 78%,transparent 97%);mask-image:linear-gradient(180deg,transparent 4%,#000 30%,#000 78%,transparent 97%)}
#bands{position:absolute;left:0;overflow:visible;animation:flow 16s linear infinite;will-change:transform}
@keyframes flow{from{transform:translate3d(0,0,0)}to{transform:translate3d(0,var(--P),0)}}
#wires.draw .w{stroke-dasharray:1;stroke-dashoffset:1;animation:wdraw 1.4s var(--ease) forwards}
@keyframes wdraw{to{stroke-dashoffset:0}}

/* ── шар: итог за всё время ── */
.orb{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:center;padding-bottom:20px}
.disc{position:absolute;left:50%;top:50%;width:520px;height:520px;margin:-260px 0 0 -260px;border-radius:50%;pointer-events:none;
  background:
    radial-gradient(circle at 50% 50%,#050607 0 34%,#0b0d0e 48%,#131719 60%,rgba(54,64,71,.55) 66.5%,rgba(105,125,138,.22) 67.5%,rgba(29,34,37,.35) 69%,rgba(15,17,19,0) 76%);
  box-shadow:0 0 120px -20px rgba(0,0,0,.9),inset 0 -40px 80px -40px rgba(210,220,245,.08)}
.disc::before{content:"";position:absolute;inset:0;border-radius:50%;
  background:conic-gradient(from 200deg,transparent,rgba(194,205,227,.18) 40deg,transparent 110deg,transparent 250deg,rgba(245,169,58,.12) 300deg,transparent 340deg);
  -webkit-mask:radial-gradient(circle,transparent 65.5%,#000 66.5%,#000 68%,transparent 69.5%);mask:radial-gradient(circle,transparent 65.5%,#000 66.5%,#000 68%,transparent 69.5%)}
.disc::after{content:"";position:absolute;inset:23%;border-radius:50%;border:1px solid rgba(188,198,220,.06)}
.orb .head{position:relative;z-index:2;text-align:center;margin-bottom:-4px}
.orb .head .k{font-size:10px;letter-spacing:.34em;text-transform:uppercase;color:var(--cap)}
.orb .head b{display:block;margin-top:6px;font-weight:200;font-size:32px;line-height:1;letter-spacing:.01em}
.orb .head b.p{text-shadow:0 0 28px rgba(210,220,245,.45)}
.orb .head s{display:block;text-decoration:none;margin-top:5px;font-size:11px;color:var(--dim)}
.ball{position:relative;width:236px;height:236px;z-index:1}
.ball svg{position:absolute;inset:0;overflow:visible}
.orb{isolation:isolate}
#ocor{transform-origin:118px 118px;animation:bre 9s ease-in-out infinite}
@keyframes bre{0%,100%{opacity:.55;transform:scale(1)}50%{opacity:.95;transform:scale(1.04)}}
@keyframes wink{0%,100%{opacity:.18}50%{opacity:.95}}
#oring{transform-origin:118px 118px;animation:spin 90s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
body.backfill .orb .head .k::after{content:" · задним числом";color:var(--gold-hi)}
.orb .onote{position:relative;z-index:2;max-width:280px;margin-top:10px;font-size:10.5px;line-height:1.45;color:var(--dim);text-align:center}
.orb .chips{position:relative;z-index:2;display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin-top:4px;max-width:280px}
.chip{font-family:var(--mono);font-size:9.5px;color:var(--txt);padding:4px 8px;border-radius:7px;
  background:rgba(15,17,19,.8);border:1px solid rgba(232,245,255,.1);white-space:nowrap}
.chip b{font-weight:500;color:var(--ice)}
.chip b.p{color:var(--pos)} .chip b.m{color:var(--dn)}

.p{color:var(--pos)} .m{color:var(--dn)}

/* ── дни: узлы ── */
.days{position:relative;z-index:2;overflow-y:auto;padding:22px 22px 40px 4px;scrollbar-width:none;
  display:flex;flex-direction:column;justify-content:safe center;gap:12px;
  -webkit-mask-image:linear-gradient(180deg,transparent,#000 5%,#000 95%,transparent);mask-image:linear-gradient(180deg,transparent,#000 5%,#000 95%,transparent)}
.days::-webkit-scrollbar{display:none}
.cap{font-size:10.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--cap)}
.day{position:relative;flex:none;display:grid;grid-template-columns:38px 1fr;column-gap:11px;align-items:stretch;text-align:left;
  padding:8px 11px 10px 9px;border-radius:12px;cursor:pointer;font:inherit;color:inherit;overflow:hidden;isolation:isolate;
  --k:.3; --tc:196,208,232;
  background:
    radial-gradient(120px 70px at 0% 50%,rgba(var(--tc),calc(.06 + .24 * var(--k))),transparent 75%),
    radial-gradient(90px 40px at 100% 0%,rgba(232,245,255,.06),transparent 70%),
    linear-gradient(180deg,rgba(35,42,46,.9),rgba(12,14,15,.95));
  border:1px solid rgba(232,245,255,.08);
  box-shadow:inset 0 1px 0 rgba(232,245,255,.12),inset 0 -1px 0 rgba(0,0,0,.6),0 14px 26px -14px rgba(0,0,0,.95),0 2px 4px rgba(0,0,0,.5);
  transition:border-color .25s,box-shadow .25s,transform .25s}
.day.neg{--tc:255,122,122}
.day::before{content:"";position:absolute;left:0;top:18%;bottom:18%;width:2px;border-radius:2px;
  background:rgb(var(--tc));opacity:calc(.35 + .65 * var(--k));box-shadow:0 0 calc(4px + 10px * var(--k)) rgb(var(--tc))}
.day:hover{border-color:rgba(232,245,255,.22);transform:translateX(2px)}
/* дата — как лист отрывного календаря */
.day .dt{display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:8px;
  background:linear-gradient(180deg,rgba(232,245,255,.07),rgba(232,245,255,.015));
  border:1px solid rgba(232,245,255,.08);box-shadow:inset 0 1px 0 rgba(232,245,255,.08),0 4px 8px -4px #000}
.day .dt b{font-weight:300;font-size:19px;line-height:1;color:#deeaff;letter-spacing:.01em}
.day .dt i{font-style:normal;margin-top:3px;font-family:var(--mono);font-size:8px;letter-spacing:.14em;text-transform:uppercase;color:var(--dim)}
.day .mn{min-width:0;display:flex;flex-direction:column;justify-content:center}
.day .s{font-weight:300;font-size:16px;line-height:1;letter-spacing:.01em;white-space:nowrap;
  text-shadow:0 0 calc(4px + 14px * var(--k)) rgba(var(--tc),.55)}
/* сделки дня тонкими столбиками от нуля */
.day .sp{position:relative;display:flex;align-items:center;gap:1px;height:14px;margin:5px 0 4px}
.day .sp::before{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px solid rgba(232,245,255,.1)}
.day .sp i{flex:0 0 2px;border-radius:1px}
.day .sp i.p{background:var(--up);align-self:flex-end;margin-bottom:7px;box-shadow:0 0 3px rgba(210,220,245,.6)}
.day .sp i.m{background:var(--dn);align-self:flex-start;margin-top:7px;box-shadow:0 0 3px rgba(255,122,122,.6)}
.day .d{font-size:9px;color:var(--dim);white-space:nowrap;display:flex;justify-content:space-between;gap:6px}
.day .d em{font-style:normal;color:#b6bfd5}
/* попадания — светящаяся нить по нижнему краю */
.day .hr{position:absolute;left:58px;right:11px;bottom:5px;height:2px;border-radius:2px;background:rgba(232,245,255,.07)}
.day .hr i{position:absolute;left:0;top:0;bottom:0;border-radius:2px;
  background:linear-gradient(90deg,rgba(var(--tc),.2),rgb(var(--tc)));box-shadow:0 0 6px rgba(var(--tc),.8)}
.day .hr i::after{content:"";position:absolute;right:-2px;top:-2px;width:6px;height:6px;border-radius:50%;background:#fff;box-shadow:0 0 6px rgb(var(--tc))}
.day .dwk{position:absolute;right:9px;top:9px;z-index:2;display:flex;align-items:center;gap:4px;font-family:var(--mono);font-size:9px;line-height:1;padding:2px 5px 3px;border-radius:4px;
  color:var(--gold-hi);border:1px solid rgba(245,169,58,.45);background:rgba(4,10,9,.6)}
.day .dwk::before{content:"";width:5px;height:5px;border-radius:50%;background:var(--gold);box-shadow:0 0 6px var(--gold)}
.day.on{--tc:245,169,58;border-color:rgba(255,240,210,.9);
  background:
    radial-gradient(140px 80px at 0% 50%,rgba(255,200,120,.3),transparent 75%),
    radial-gradient(160px 70px at 100% 0%,rgba(255,236,200,.18),transparent 70%),
    linear-gradient(180deg,rgba(82,70,44,.95),rgba(26,22,14,.97));
  box-shadow:inset 0 1px 0 rgba(255,236,200,.4),inset 0 0 24px rgba(255,208,138,.16),0 0 0 3px rgba(245,169,58,.1),
    0 0 34px -4px rgba(245,169,58,.55),0 18px 30px -16px #000;transform:translateX(4px)}
.day.on::before{background:#ffe3b0;opacity:1;box-shadow:0 0 12px #f5a93a}
.day.on::after{content:"";position:absolute;inset:0;pointer-events:none;z-index:-1;
  background:linear-gradient(105deg,transparent 30%,rgba(255,240,210,.12) 45%,transparent 60%);
  animation:sheen 5s ease-in-out infinite}
@keyframes sheen{0%,100%{transform:translateX(-60%)}50%{transform:translateX(60%)}}
.day.on .dt{background:linear-gradient(180deg,rgba(255,236,200,.22),rgba(255,208,138,.05));border-color:rgba(255,236,200,.35)}
.day.on .dt b{color:#fff6e6;text-shadow:0 0 12px rgba(255,208,138,.7)}
.day.on .dt i,.day.on .d{color:#e2cfa8}
.day.on .d em{color:#fff1d6}
.day.on .s{color:#fff4e0;text-shadow:0 0 18px rgba(255,208,138,.6)}

/* ── веер сделок ── */
.fan{position:relative;z-index:2;overflow-y:auto;padding:50vh 0 50vh 96px;scrollbar-width:none;
  -webkit-mask-image:linear-gradient(180deg,transparent 6%,#000 23%,#000 80%,transparent 97%);mask-image:linear-gradient(180deg,transparent 6%,#000 23%,#000 80%,transparent 97%)}
.fan::-webkit-scrollbar{display:none}
.fcap{position:absolute;z-index:3;left:calc(max(260px,24vw) + 188px + 40px);top:14px;display:flex;gap:10px;align-items:baseline;pointer-events:none}
.fcap .cap{color:var(--ice)}
.fcap span{font-size:11.5px;color:var(--dim)}
.tr{position:relative;width:228px;margin:0 0 4px;padding:5px 10px 6px 16px;border-radius:9px;cursor:pointer;
  border:1px solid transparent;will-change:transform;transition:background .2s,border-color .2s}
.tr .in{display:grid;grid-template-columns:1fr auto;row-gap:3px;align-items:baseline}
.tr::before{content:"";position:absolute;left:-5px;top:50%;width:10px;height:10px;margin-top:-5px;border-radius:50%;
  background:radial-gradient(circle at 36% 32%,#fff8ea 0 20%,#e2a24e 55%,#7a5220 100%);
  box-shadow:0 0 0 2px rgba(245,169,58,.12),0 0 10px rgba(245,169,58,.75),0 2px 3px rgba(0,0,0,.8)}
.tr.done::before{background:radial-gradient(circle at 36% 32%,#ffffff 0 18%,#b8c2d7 50%,#4a5861 100%);
  box-shadow:0 0 0 2px rgba(232,245,255,.06),0 0 6px rgba(232,245,255,.35),0 2px 3px rgba(0,0,0,.8)}
.tr.open::before{animation:beadp 2.6s ease-in-out infinite}
@keyframes beadp{50%{box-shadow:0 0 0 3px rgba(245,169,58,.2),0 0 18px rgba(245,169,58,1),0 2px 3px rgba(0,0,0,.8)}}
.tr:hover{background:rgba(232,245,255,.04)}
.tr.on{background:linear-gradient(180deg,rgba(60,56,40,.75),rgba(20,20,14,.85));border-color:rgba(255,236,200,.7);
  box-shadow:inset 0 1px 0 rgba(255,236,200,.25),0 0 24px -6px rgba(245,169,58,.55),0 12px 24px -12px #000}
.tr .nm{font-size:12.5px;letter-spacing:.12em;white-space:nowrap;color:#dbe6ff}
.tr .mo{font-weight:300;font-size:13px;text-align:right;white-space:nowrap}
.tr .meta{grid-column:1 / -1;display:flex;align-items:center;gap:4px;min-width:0}
.tag{flex:none;font-family:var(--mono);font-size:8.5px;line-height:1;padding:2px 5px 3px;border-radius:4px;
  background:rgba(7,8,9,.9);border:1px solid rgba(232,245,255,.12);color:#b6bfd5;white-space:nowrap;
  box-shadow:inset 0 1px 0 rgba(232,245,255,.05)}
.tag.open{color:var(--gold-hi);border-color:rgba(245,169,58,.45)}
.tr .rule{flex:1;min-width:0;font-size:10px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.seg{flex:none;display:flex;gap:1.5px}
.seg i{width:6px;height:4px;border-radius:1px;background:rgba(232,245,255,.1)}
.seg.p i.on{background:var(--up);box-shadow:0 0 5px rgba(210,220,245,.8)}
.seg.m i.on{background:var(--dn);box-shadow:0 0 5px rgba(255,122,122,.8)}

/* ── панель монеты ── */
.side{position:relative;z-index:3;padding:12px 22px 22px 6px;overflow:hidden;display:flex;flex-direction:column;gap:10px}
.crumb{align-self:flex-end;font-size:11px;color:var(--txt);padding:7px 14px;border-radius:12px;
  background:rgba(15,17,19,.75);border:1px solid var(--edge);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.card{flex:1;min-height:0;overflow-y:auto;font-size:12px;scrollbar-width:thin;scrollbar-color:rgba(232,245,255,.14) transparent;
  border-radius:20px;padding:22px 22px 26px;
  background:
    radial-gradient(520px 300px at 0% -8%,rgba(182,192,213,.2),transparent 70%),
    radial-gradient(420px 260px at 110% 30%,rgba(150,140,230,.06),transparent 70%),
    linear-gradient(180deg,rgba(43,51,56,.86),rgba(16,19,21,.92) 40%,rgba(11,13,14,.95));
  border:1px solid rgba(232,245,255,.12);
  box-shadow:inset 0 1px 0 rgba(232,245,255,.18),inset 1px 0 0 rgba(232,245,255,.05),0 40px 80px -30px #000,0 0 0 1px rgba(0,0,0,.4)}
.kick{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--txt)}
.kick svg{color:var(--gold-hi)}
.card h2{margin:14px 0 0;font-weight:300;font-size:32px;line-height:1;letter-spacing:.16em}
.card .h2s{margin-top:6px;font-size:13px;color:var(--txt)}
.status{display:grid;grid-template-columns:1fr auto;gap:8px 14px;align-items:center;margin-top:18px;padding:12px 14px;border-radius:12px;
  border:1px solid rgba(232,245,255,.1);background:linear-gradient(180deg,rgba(9,10,11,.55),rgba(6,7,8,.7));
  box-shadow:inset 0 1px 2px rgba(0,0,0,.6),0 1px 0 rgba(232,245,255,.05)}
.pill{justify-self:start;font-size:11px;padding:3px 9px 4px;border-radius:7px;color:#e6ebf3;
  border:1px solid rgba(210,220,245,.28);background:rgba(210,220,245,.06)}
.pill.g{color:var(--gold-hi);border-color:rgba(245,169,58,.45);background:rgba(245,169,58,.08)}
.status p{grid-column:1;margin:0;font-size:11px;line-height:1.45;color:var(--dim)}
.status p b{font-weight:400;color:var(--ice)}
.status .btn{grid-column:2;grid-row:1 / span 2;font-size:11.5px;padding:9px 12px}
.hero{position:relative;margin-top:12px;padding:16px 18px 14px;border-radius:14px;overflow:hidden;
  background:
    radial-gradient(300px 170px at 0% 100%,rgba(150,170,215,.26),transparent 70%),
    radial-gradient(260px 150px at 78% 120%,rgba(245,169,58,.22),transparent 70%),
    linear-gradient(90deg,rgba(28,33,37,.95),rgba(13,16,17,.98) 60%);
  border:1px solid rgba(232,245,255,.1);
  box-shadow:inset 0 1px 0 rgba(232,245,255,.12),0 18px 30px -18px #000}
.hero.neg{background:
    radial-gradient(300px 170px at 0% 100%,rgba(255,110,90,.34),transparent 70%),
    radial-gradient(260px 150px at 78% 120%,rgba(245,169,58,.2),transparent 70%),
    linear-gradient(90deg,rgba(52,22,22,.95),rgba(18,10,10,.98) 60%)}
.hero .row{display:flex;justify-content:space-between;align-items:center}
.hero .row span{font-size:12.5px;color:var(--ice)}
.hero .row .pill{font-size:10.5px}
.hero .big{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-top:10px}
.hero .big b{font-weight:300;font-size:32px;line-height:1;white-space:nowrap}
.hero .big b.p{text-shadow:0 0 26px rgba(210,220,245,.45)}
.hero .big b.m{text-shadow:0 0 26px rgba(255,122,122,.4)}
.hero .big small{display:block;margin-top:6px;font-size:11.5px;color:var(--dim)}
.histw{flex:1;min-width:0;max-width:250px}
.hist{height:62px;display:flex;gap:0;position:relative}
.hist::after{content:"";position:absolute;left:0;right:0;top:50%;border-top:1px dotted rgba(232,245,255,.18)}
.hist i{flex:1 1 0;min-width:0;border-radius:.5px;transform-origin:50% 100%;opacity:.42}
.hist i.p{background:#d3def7;align-self:flex-end;margin-bottom:31px}
.hist i.m{background:#e9cfcf;align-self:flex-start;margin-top:31px;transform-origin:50% 0}
.hist i.me{opacity:1;flex-grow:2.2;z-index:1}
.hist i.me.p{background:linear-gradient(180deg,#fff,var(--gold));box-shadow:0 0 6px rgba(245,169,58,.9)}
.hist i.me.m{background:linear-gradient(0deg,#fff,var(--dn));box-shadow:0 0 6px rgba(255,122,122,.9)}
.histl{margin-top:5px;font-size:10px;color:var(--dim);text-align:right;white-space:nowrap}
.tiles{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:10px}
.tile{padding:12px 12px 11px;border-radius:14px;
  background:radial-gradient(200px 90px at 0% 0%,rgba(182,192,213,.1),transparent 70%),linear-gradient(180deg,rgba(32,39,43,.85),rgba(13,16,17,.9));
  border:1px solid rgba(232,245,255,.08);
  box-shadow:inset 0 1px 0 rgba(232,245,255,.1),0 14px 24px -16px #000}
.tile .t1{display:flex;align-items:center;gap:10px}
.tile .t1 svg{flex:none;width:22px;height:22px;color:#c0cae1;filter:drop-shadow(0 0 6px rgba(188,198,220,.3))}
.tile .t1 b{font-weight:300;font-size:20px;line-height:1;white-space:nowrap}
.tile .t2{margin-top:8px;font-size:11px;line-height:1.35;color:var(--txt)}
.tile .t3{margin-top:2px;font-size:10px;color:var(--dim);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sec{display:flex;align-items:center;gap:10px;margin:20px 0 6px;font-size:12.5px;color:var(--ice)}
.sec svg{color:var(--gold-hi)}
.line{display:grid;grid-template-columns:minmax(0,1fr) 42px 58px 70px;gap:8px;align-items:center;padding:6px 10px;
  border-radius:8px;font-size:11px;color:var(--txt)}
.line:nth-child(odd of .line){background:rgba(232,245,255,.025)}
.line span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.line .dm{color:var(--dim);font-family:var(--mono);font-size:11px;text-align:right}
.line b{font-weight:300;font-size:12.5px;text-align:right;white-space:nowrap}
.line .st{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:8px;vertical-align:1px;background:#6d828f}
.line .st.open{background:var(--gold);box-shadow:0 0 7px var(--gold)}
.note{margin-top:16px;padding:12px 14px;border-radius:12px;font-size:12px;line-height:1.5;color:var(--dim);
  border:1px dashed rgba(232,245,255,.12)}
.empty{display:grid;place-items:center;height:100%;text-align:center;font-size:13px;color:var(--dim)}

/* ── один показ ── */
@keyframes fade{from{opacity:0}}
@keyframes slide{from{opacity:0;transform:translateX(-14px)}}
@keyframes growy{from{transform:scaleY(0)}}
.play .orb{animation:fade 1s ease backwards}
.play .day{animation:slide .7s var(--ease) backwards;animation-delay:calc(.35s + var(--i) * .06s)}
.play .tr .in{animation:slide .6s var(--ease) backwards;animation-delay:calc(.9s + min(var(--i),24) * .035s)}
.play .tr::before{animation:fade .4s ease backwards;animation-delay:calc(.9s + min(var(--i),24) * .035s)}
.play .fcap,.play .side{animation:fade .9s ease .5s backwards}
.card.fresh .hist i{animation:growy .7s var(--ease) backwards;animation-delay:calc(min(var(--i),300) * .003s)}

/* ── узкие экраны: столбиком, без нитей ── */

/* ── разбор позиций в работе ── */
.grp.src button.wkbtn b{font-weight:500;color:var(--gold-hi);margin-left:2px}
.grp.src button.wkbtn.live b{animation:wkp 2.4s ease-in-out infinite}
@keyframes wkp{50%{text-shadow:0 0 10px rgba(245,169,58,.9)}}
/* ── «В РАБОТЕ» В СЦЕНЕ (16.09, владелец: «сделай» — тем же экраном, что живые): слева шар открытых, колонка групп
   вместо дней, веер позиций — ближе к выходу выше, справа разбор выбранной ── */
.chip .cl{color:inherit}
.day .dt b.cnt{font-size:17px}
.tag.dn{color:#ffb4b4;border-color:rgba(255,122,122,.45)}
.tag.nr{color:var(--gold-hi);border-color:rgba(245,169,58,.45)}
.tag.fr{color:#cfe0ff;border-color:rgba(160,190,240,.4)}
.tag.ev{color:#d6ccff;border-color:rgba(190,175,255,.45)}
.pchart{display:block;width:100%;height:62px}
.pos-sub{margin-top:4px;font-size:11px;color:var(--dim)}
.line.x b.k-цель{color:var(--gold-hi)} .line.x b.k-стоп{color:#ffb4b4} .line.x b.k-событие,.line.x b.k-флип,.line.x b.k-хедж{color:#d6ccff}
.line .bar{display:block;height:2px;margin-top:4px;border-radius:2px;background:rgba(232,245,255,.07);overflow:hidden}
.line .bar i{display:block;height:100%;background:#b6bfd5}
.line.x.k-цель .bar i{background:var(--gold)} .line.x.k-стоп .bar i{background:var(--dn)}
.line.f{grid-template-columns:minmax(0,1fr) 92px 96px}
.line.f svg{display:block;width:92px;height:20px}
.line.f b.good{color:var(--up)} .line.f b.bad{color:var(--dn)}
.line.kv{grid-template-columns:minmax(0,1fr) auto}
.line.kv b.key{color:var(--gold-hi)} .line.kv b.good{color:var(--up)} .line.kv b.bad{color:var(--dn)}
.sec small{margin-left:auto;font-size:10px;color:var(--dim)}
.card .gowork{margin-top:10px;width:100%;justify-content:center;border-color:rgba(245,169,58,.45);color:var(--gold-hi)}
@media (max-width:1380px){
  .tools .wideonly{display:none}
}
@media (max-width:1180px){
  html,body{overflow:auto;height:auto}
  .tools{position:fixed;top:64px;left:0;right:0;transform:none;justify-content:center;padding:6px 10px;z-index:8;
    background:linear-gradient(180deg,rgba(8,12,16,.92),rgba(8,12,16,.75));backdrop-filter:blur(6px)}
  .tools .grp:not(.src){display:none}
  .stage{position:static;display:block;padding:112px 16px 40px}
  #wires,#bandsw{display:none}
  .orb{padding:10px 0 20px}
  .disc{width:360px;height:360px;margin:-180px 0 0 -180px}
  .days{flex-direction:row;overflow-x:auto;padding:10px 0;justify-content:flex-start;-webkit-mask-image:none;mask-image:none}
  .day{min-width:170px}
  .fcap{position:static;margin:18px 0 8px}
  .fan{padding:0!important;overflow:visible;-webkit-mask-image:none;mask-image:none}
  .tr{width:auto;transform:none!important;opacity:1!important}
  .tr .nm{font-size:14px}.tr .mo{font-size:15px}.tr .rule{font-size:11px}
  .tr::before{left:4px}
  .tr .in{padding-left:8px}
  .side{padding:16px 0 0;overflow:visible}
  .card{overflow:visible}
}
@media (max-width:520px){
  .brand h1 small{display:none}
  .acts .btn span{display:none}
  .hist{max-width:110px}
  .card h2{font-size:32px}
  .line{grid-template-columns:minmax(0,1fr) 58px 72px}
  .line .hit{display:none}
}
@media (prefers-reduced-motion:reduce){
  *,*::before,*::after{animation:none!important;transition:none!important}
}
</style></head><body class="play">

<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="i-cal" viewBox="0 0 22 22"><rect x="3" y="5" width="16" height="14" rx="3" fill="none" stroke="currentColor" stroke-width="1.3"/><path d="M3 9.5h16M7.5 3v4M14.5 3v4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></symbol>
  <symbol id="i-coin" viewBox="0 0 26 26"><circle cx="13" cy="13" r="9.5" fill="none" stroke="currentColor" stroke-width="1.3"/><circle cx="13" cy="13" r="5.5" fill="none" stroke="currentColor" stroke-width="1" opacity=".6"/><path d="M13 3.5v3M13 19.5v3" stroke="currentColor" stroke-width="1.3"/></symbol>
  <symbol id="i-avg" viewBox="0 0 26 26"><circle cx="13" cy="13" r="10" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8 16l3.5-4 3 2.5L19 9" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-up" viewBox="0 0 26 26"><circle cx="13" cy="13" r="10" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M8.5 13.5l3 3 6-7" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></symbol>
  <symbol id="i-dn" viewBox="0 0 26 26"><circle cx="13" cy="13" r="10" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M9.5 9.5l7 7M16.5 9.5l-7 7" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></symbol>
  <symbol id="i-list" viewBox="0 0 26 26"><rect x="5" y="3.5" width="16" height="19" rx="2.5" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M9 9h8M9 13h8M9 17h5" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></symbol>
  <symbol id="i-spark" viewBox="0 0 20 20"><path d="M10 2.5l1.6 4.6 4.9.3-3.8 3 1.3 4.8L10 12.5l-4 2.7 1.3-4.8-3.8-3 4.9-.3z" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linejoin="round"/></symbol>
</svg>

<header class="top">
  <div class="brand">
    <div class="mark"><svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true"><circle cx="10" cy="10" r="4.2" fill="#f5a93a"/><circle cx="10" cy="10" r="8" fill="none" stroke="#ffd08a" stroke-opacity=".55" stroke-width="1"/></svg></div>
    <h1>книга<small>бумажный бот</small></h1>
  </div>
  <div class="tools" aria-label="состояние книги">
    <div class="grp"><span class="on" id="nopenbtn" role="button" tabindex="0" title="разбор открытых позиций" style="cursor:pointer">в работе <b class="g" id="nopen">0</b></span><span>депозит дня <b id="dep">0 $</b></span></div>
    <div class="grp src" id="srcsw" role="group" aria-label="источник"><button type="button" data-src="live" class="on">живые</button><button type="button" data-src="back">задним числом</button><button type="button" data-src="work" class="wkbtn">в работе <b id="nwork">0</b></button></div>
    <div class="grp"><span>дней <b id="ndays">0</b></span><span>сделок <b id="nall">0</b></span><span class="wideonly">сборка <b id="upd">—</b></span></div>
  </div>
  <div class="acts">
    <button class="btn" type="button" id="replay">↻ <span>заново</span></button>
    <a class="btn" href="intro.html">← <span>звёзды</span></a>
  </div>
</header>

<main class="stage" id="stage">
  <svg id="wires" aria-hidden="true"></svg>
  <div id="bandsw" aria-hidden="true"><svg id="bands"></svg></div>

  <!-- ШАР -->
  <section class="orb" aria-label="итог бота">
    <div class="head">
      <div class="k" id="orbk">итог бота</div>
      <b class="p" id="allmoney">+0 $</b>
      <s id="allsub">за всё время</s>
    </div>
    <div class="ball" id="ball" aria-hidden="true">
      <div class="disc"></div>
      <svg viewBox="0 0 236 236">
        <defs>
          <radialGradient id="obody" cx="36%" cy="30%" r="78%">
            <stop offset="0" stop-color="#f6f2ff"/><stop offset="14%" stop-color="#cbbcff"/>
            <stop offset="46%" stop-color="#7560c8"/><stop offset="100%" stop-color="#130e2c"/>
          </radialGradient>
          <radialGradient id="ocorona" cx="50%" cy="50%" r="50%">
            <stop offset="0" stop-color="rgba(160,140,240,.34)"/><stop offset="40%" stop-color="rgba(160,140,240,.12)"/>
            <stop offset="100%" stop-color="rgba(160,140,240,0)"/>
          </radialGradient>
          <filter id="osoft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="4"/></filter>
          <filter id="oblur" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="9"/></filter>
        </defs>
        <circle id="ocor" cx="118" cy="118" r="116" fill="url(#ocorona)"/>
        <g id="oring"></g>
        <circle cx="118" cy="118" r="50" fill="#8f78e8" opacity=".55" filter="url(#oblur)"/>
        <circle cx="118" cy="118" r="44" fill="url(#obody)"/>
        <path d="M118 74a44 44 0 0 0 0 88a30 44 0 0 1 0-88z" fill="rgba(10,6,30,.32)"/>
        <circle cx="118" cy="118" r="44" fill="none" stroke="#f0ebff" stroke-opacity=".25" stroke-width=".8"/>
        <ellipse cx="103" cy="99" rx="13" ry="7" fill="#fff" opacity=".38" transform="rotate(-30 103 99)"/>
      </svg>
    </div>
    <div class="chips">
      <span class="chip"><span class="cl" id="c1">сделок</span> <b id="alln">0</b></span>
      <span class="chip"><span class="cl" id="c2">попаданий</span> <b id="allhit">0%</b></span>
      <span class="chip"><span class="cl" id="c3">лучший день</span> <b class="p" id="bestday">0</b></span>
      <span class="chip"><span class="cl" id="c4">худший</span> <b class="m" id="worstday">0</b></span>
    </div>
    <div class="onote" id="onote"></div>
  </section>

  <!-- ДНИ -->
  <nav class="days" id="days" aria-label="дни"></nav>

  <!-- ВЕЕР -->
  <div class="fcap"><span class="cap" id="fancap">сделки дня</span><span id="fansub"></span></div>
  <section class="fan" id="fan" aria-label="сделки дня"></section>

  <!-- МОНЕТА -->
  <aside class="side" aria-label="сводка по монете">
    <div class="crumb" id="crumb">выбери монету в списке сделок</div>
    <div class="card" id="side"><div class="empty">сделок пока нет</div></div>
  </aside>
</main>



<script>
/* ── данные собраны render_book.py из paper_end / paper_crowd / paper_fast ──
   день бота — по UTC; время сборки и подписи дат — в часах смотрящего */
const BOOK=__BOOK_DATA__;
let seed=20260916;
function rand(){seed|=0;seed=seed+0x6D2B79F5|0;let t=Math.imul(seed^seed>>>15,1|seed);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296}
const esc=x=>String(x==null?'':x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const $=id=>document.getElementById(id);
const money=v=>{const r=Math.round(v);return (r>0?'+':r<0?'−':'')+Math.abs(r).toLocaleString('ru-RU')+' $'};
const pct=v=>v==null?'—':(v>0?'+':v<0?'−':'')+Math.abs(v).toFixed(2)+'%';
const cls=v=>Math.round(v)>=0?'p':'m';
const hm=t=>new Date(t*1000).toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
let DAYS=[], all=[], closedAll=[], dayMax=1, tradeMax=1, SRC='live';
$('dep').textContent=Math.round(BOOK.deposit).toLocaleString('ru-RU')+' $';
(function(){const t=new Date(BOOK.built*1000);if(!isNaN(t))$('upd').textContent=t.toLocaleString('ru-RU',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})})();

/* кольцо частиц вокруг шара */
(function(){
  let s='';
  for(let i=0;i<150;i++){
    const a=rand()*Math.PI*2, r=46+Math.pow(rand(),1.8)*20, big=rand()<.12;
    const c=rand()<.25?'#ffd08a':'#d8cfff';
    s+=`<circle cx="${(118+Math.cos(a)*r).toFixed(1)}" cy="${(118+Math.sin(a)*r).toFixed(1)}" r="${big?1.3:.6+rand()*.5}" fill="${c}"
      style="animation:wink ${(3+rand()*5).toFixed(1)}s ease-in-out infinite;animation-delay:-${(rand()*6).toFixed(1)}s"/>`;
  }
  for(let i=0;i<46;i++){
    const a=(i/46)*Math.PI*2, r0=60+rand()*4, r1=r0+4+rand()*14;
    s+=`<line x1="${(118+Math.cos(a)*r0).toFixed(1)}" y1="${(118+Math.sin(a)*r0).toFixed(1)}" x2="${(118+Math.cos(a)*r1).toFixed(1)}" y2="${(118+Math.sin(a)*r1).toFixed(1)}"
      stroke="#c4b8f5" stroke-opacity=".45" stroke-width=".7" stroke-linecap="round"
      style="animation:wink ${(4+rand()*5).toFixed(1)}s ease-in-out infinite;animation-delay:-${(rand()*6).toFixed(1)}s"/>`;
  }
  $('oring').innerHTML=s;
})();


/* ── «В РАБОТЕ» ТЕМ ЖЕ ЭКРАНОМ (16.09, владелец: «сделай»): шар открытых, колонка групп вместо дней, веер позиций
   (ближе к выходу — выше), справа разбор выбранной. Данные — BOOK.work (render_book._analyse). ── */
const tmx=s=>esc(s).replace(/\{T:(\d+)\}/g,(m,t)=>hm(+t));
const px6=v=>{if(v==null)return '—';const a=Math.abs(v);return (+v).toFixed(a>=100?2:a>=1?4:a>=.01?5:a>=.0001?7:9).replace(/0+$/,'').replace(/\.$/,'')};
const mln=v=>{const x=Math.abs(v);return (v<0?'−':'')+(x>=1e6?(x/1e6).toFixed(2)+'M':x>=1e3?(x/1e3).toFixed(0)+'K':x.toFixed(0))};
function sparkSvg(series,colors,dashed,W=92,H=20){
  const all=series.flat().filter(x=>x!=null); if(!all.length) return '';
  let lo=Math.min(...all),hi=Math.max(...all); if(hi===lo){hi+=1;lo-=1}
  const n=Math.max(...series.map(x=>x.length)), X=i=>W*i/Math.max(1,n-1), Y=v=>H-1-(H-2)*(v-lo)/(hi-lo);
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">${series.map((x,k)=>`<polyline points="${x.map((v,i)=>v==null?'':X(i).toFixed(1)+','+Y(v).toFixed(1)).join(' ')}"
    fill="none" stroke="${colors[k]}" stroke-width="${k?1:1.4}" ${dashed&&dashed[k]?'stroke-dasharray="3 2"':''} vector-effect="non-scaling-stroke"/>`).join('')}</svg>`;
}
function posChart(a){
  const P=a.path||[]; if(P.length<3) return '';
  const W=250,H=62,pd=3, ys=P.map(p=>p[1]).concat([a.entry,a.tgt_px,a.stop_px].filter(v=>v!=null));
  let lo=Math.min(...ys),hi=Math.max(...ys); const sp=(hi-lo)||hi*0.01||1; lo-=sp*.1; hi+=sp*.1;
  const t0=P[0][0],t1=P[P.length-1][0]||t0+1;
  const X=t=>pd+(W-2*pd)*(t-t0)/Math.max(1,t1-t0), Y=v=>H-pd-(H-2*pd)*(v-lo)/(hi-lo);
  const c=(a.res||0)<0?'#ff7a7a':'#f5a93a';
  const line=P.map((p,k)=>(k?'L':'M')+X(p[0]).toFixed(1)+' '+Y(p[1]).toFixed(1)).join('');
  const hl=(v,col,d)=>v==null?'':`<line x1="0" x2="${W}" y1="${Y(v).toFixed(1)}" y2="${Y(v).toFixed(1)}" stroke="${col}" ${d?'stroke-dasharray="2 4"':''} vector-effect="non-scaling-stroke"/>`;
  const te=a.sig_t?Math.max(t0,Math.min(t1,a.sig_t)):null, last=P[P.length-1], id='pg'+a.sym;
  return `<svg class="pchart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${c}" stop-opacity=".3"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></linearGradient></defs>
    ${hl(a.tgt_px,'rgba(255,208,138,.6)',true)}${hl(a.stop_px,'rgba(255,122,122,.55)',true)}${hl(a.entry,'rgba(232,245,255,.3)',false)}
    ${te!=null?`<line x1="${X(te).toFixed(1)}" x2="${X(te).toFixed(1)}" y1="0" y2="${H}" stroke="rgba(232,245,255,.15)" vector-effect="non-scaling-stroke"/>`:''}
    <path d="${line}L${X(t1).toFixed(1)} ${H}L${X(t0).toFixed(1)} ${H}Z" fill="url(#${id})"/>
    <path d="${line}" fill="none" stroke="${c}" stroke-width="1.6" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
    <circle cx="${X(last[0]).toFixed(1)}" cy="${Y(last[1]).toFixed(1)}" r="2.6" fill="#fff4e0"/></svg>`;
}
/* деньги открытой позиции — из живой строки того же входа (доля депозита дня от цены сейчас) */
function openMoney(){
  const m={};
  ((BOOK.live&&BOOK.live.days)||[]).forEach(d=>d.rows.forEach(r=>{ if(r.open) m[r.sym]=(m[r.sym]||0)+r.money; }));
  return m;
}
const WGROUPS=[['all','все','все',a=>true],
  ['done','сработало','срабо',a=>a.done],
  ['цель','ближе к цели','цель',a=>!a.done&&a.nearest==='цель'],
  ['стоп','ближе к стопу','стоп',a=>!a.done&&a.nearest==='стоп'],
  ['срок','по сроку','срок',a=>!a.done&&a.nearest==='срок'],
  ['событие','ждут события','событ',a=>!a.done&&a.nearest==='событие'],
  ['fresh','только вошли','новые',a=>!a.done&&!a.nearest]];
let WG=[], WMON={}, curGroup=0, curPos=null;
function posTag(a){
  const nf=a.nearest_f!=null?Math.round(Math.min(1,a.nearest_f)*100):null;
  if(a.done) return `<span class="tag dn">сработало</span>`;
  if(!a.nearest) return `<span class="tag fr">только вошла</span>`;
  if(a.nearest==='событие') return `<span class="tag ev">событие${nf!=null?' '+nf+'%':''}</span>`;
  return `<span class="tag nr">${esc(a.nearest)} ${nf}%</span>`;
}
function buildWork(sym){
  SRC='work';
  document.querySelectorAll('#srcsw button').forEach(x=>x.classList.toggle('on',x.dataset.src==='work'));
  document.body.classList.remove('backfill');
  document.body.classList.add('workmode');
  const W=BOOK.work||[];
  WMON=openMoney();
  const mon=a=>WMON[a.sym]!=null?WMON[a.sym]:null;
  const tot=W.reduce((s,a)=>s+(mon(a)||0),0);
  $('orbk').textContent='в работе';
  $('allmoney').textContent=money(tot); $('allmoney').className=cls(tot);
  $('allsub').textContent=W.length?`${W.length} позиций · от цены сейчас, в итог не входят`:'открытых позиций нет';
  const plus=W.filter(a=>(a.res||0)>0).length;
  $('c1').textContent='позиций'; $('alln').textContent=W.length;
  $('c2').textContent='в плюсе'; $('allhit').textContent=W.length?Math.round(100*plus/W.length)+'%':'—';
  $('c3').textContent='сработало'; $('bestday').textContent=W.filter(a=>a.done).length; $('bestday').className='';
  $('c4').textContent='только вошли'; $('worstday').textContent=W.filter(a=>!a.done&&!a.nearest).length; $('worstday').className='';
  const byRule={}; W.forEach(a=>{byRule[a.rule]=(byRule[a.rule]||0)+1});
  $('onote').textContent=Object.entries(byRule).sort((x,y)=>y[1]-x[1]).map(([k,v])=>`${k} ${v}`).join(' · ');
  WG=WGROUPS.map(([id,label,short,f])=>{
    const rows=W.filter(f).sort((x,y)=>(y.done-x.done)||((y.nearest_f||0)-(x.nearest_f||0)));
    return {id,label,short,rows,total:rows.reduce((s,a)=>s+(mon(a)||0),0),plus:rows.filter(a=>(a.res||0)>0).length};
  }).filter((g,k)=>k===0||g.rows.length);
  const mx=Math.max(...WG.map(g=>Math.abs(g.total)))||1;
  const tmax=Math.max(...W.map(a=>Math.abs(mon(a)||0)))||1;
  daysEl.innerHTML=W.length?'':'<div class="cap" style="padding:10px 4px">открытых позиций нет</div>';
  if(W.length) WG.forEach((g,i)=>{
    const el=document.createElement('button'); el.type='button'; el.className='day'+(g.total<0?' neg':''); el.style.setProperty('--i',i);
    el.style.setProperty('--k',(Math.abs(g.total)/mx).toFixed(2));
    const sp=g.rows.map(a=>{const v=mon(a)||0;return `<i class="${cls(v)}" style="height:${Math.max(1.5,Math.sqrt(Math.abs(v)/tmax)*7).toFixed(1)}px"></i>`}).join('');
    const hitp=g.rows.length?Math.round(100*g.plus/g.rows.length):0;
    el.innerHTML=`<span class="dt"><b class="cnt">${g.rows.length}</b><i>${esc(g.short)}</i></span>
      <span class="mn"><span class="s ${cls(g.total)}">${money(g.total)}</span><span class="sp" aria-hidden="true">${sp}</span>
      <span class="d"><span>${esc(g.label)}</span><span>плюс <em>${hitp}%</em></span></span></span>
      <span class="hr" aria-hidden="true">${g.rows.length?`<i style="width:${hitp}%"></i>`:''}</span>`;
    el.setAttribute('aria-label',`${g.label}: ${g.rows.length} позиций, ${money(g.total)}`);
    el.onclick=()=>pickGroup(i); daysEl.appendChild(el);
  });
  if(!W.length){
    fan.innerHTML=''; $('fancap').textContent='в работе'; $('fansub').textContent='боты проверяют входы и выходы каждый прогон';
    $('crumb').textContent='—'; $('side').innerHTML='<div class="empty">открытых позиций нет</div>'; arc(true); wires(); return;
  }
  let gi=0;
  if(sym){ const k=WG.findIndex((g,i)=>i>0&&g.rows.some(a=>a.sym===sym)); if(k>0) gi=k; }
  pickGroup(gi,sym);
}
function pickGroup(i,sym){
  curGroup=i;
  [...daysEl.children].forEach((e,k)=>e.classList.toggle('on',k===i));
  const G=WG[i];
  $('fancap').textContent='в работе · '+G.label;
  $('fansub').textContent=`позиций ${G.rows.length} · от цены сейчас ${money(G.total)} · сначала ближе к выходу`;
  fan.innerHTML='';
  G.rows.forEach((a,k)=>{
    const el=document.createElement('div'); el.className='tr '+(a.done?'done':'open');
    el.tabIndex=0; el.style.setProperty('--i',k); el.dataset.sym=a.sym;
    const m=WMON[a.sym];
    const g=a.done?String((a.done_list||[])[0]||'').replace(/\s*\(.*?\)/,''):(a.goal?`${a.goal.k} ${a.goal.v}`:'');
    el.title=`${a.sym} · ${a.side<0?'шорт':'лонг'} · ${a.rule} · вес ×${a.size}\n${a.rl}`;
    el.innerHTML=`<div class="in">
      <span class="nm">${esc(a.sym)}</span><span class="mo ${m!=null?cls(m):cls(a.res||0)}">${m!=null?money(m):pct(a.res)}</span>
      <span class="meta">${posTag(a)}<span class="tag">${a.side<0?'▼':'▲'} ${pct(a.res)}</span><span class="rule">${esc(a.rule)} · ${esc(g)}</span></span>
    </div>`;
    el.onclick=()=>pickPos(a,el);
    el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pickPos(a,el)}};
    fan.appendChild(el);
  });
  const trs=[...fan.querySelectorAll('.tr')];
  // как у живых: веер центрируется по середине списка, выбрана — самая близкая к выходу (или запрошенная)
  const pick=(sym&&trs.find(t=>t.dataset.sym===sym))||trs[0];
  const mid=sym&&pick?pick:trs[Math.floor((trs.length-1)/2)];
  if(mid) fan.scrollTop=mid.offsetTop+mid.offsetHeight/2-fan.clientHeight/2;
  if(pick) pickPos(G.rows[trs.indexOf(pick)],pick);
  arc(true); wires();
}
function pickPos(a,el){
  curPos=a.sym;
  [...fan.querySelectorAll('.tr')].forEach(e=>e.classList.toggle('on',e===el));
  const short=a.side<0, f=a.fast||{}, m=WMON[a.sym];
  const nf=a.nearest_f!=null?Math.round(Math.min(1,a.nearest_f)*100):null;
  $('crumb').textContent=`${a.sym} · ${a.book} · вход ${a.opened?hm(a.opened):'—'}`;
  const card=$('side');
  card.classList.remove('fresh'); void card.offsetWidth;
  let gk=a.goal?a.goal.k:'ждём', gv=a.goal?a.goal.v:'—', gs=a.goal?(a.goal.s||''):'';
  if(a.done){
    const d0=String((a.done_list||[])[0]||'');
    gk='сработало'; gs='закроется на ближайшем прогоне';
    gv=d0.startsWith('цена за стопом')?('стоп '+px6(a.stop_px)):d0.startsWith('цель')?('цель '+px6(a.tgt_px)):d0.startsWith('z')?'z ниже нуля':d0.startsWith('срок')?'срок вышел':d0;
  }
  const closeLines=(a.close||[]).map(c=>{const k=String(c.k).split(' ')[0];
    return `<div class="line kv x k-${esc(k)}" title="${esc(String(c.s||'').replace(/\{T:(\d+)\}/g,(q,t)=>hm(+t)))}"><span>${esc(c.k)} · <span style="color:var(--dim)">${tmx(c.sh||'')}</span>
      ${c.f!=null?`<span class="bar"><i style="width:${Math.round(Math.min(1,c.f)*100)}%"></i></span>`:''}</span><b class="k-${esc(k)}">${esc(c.v)}</b></div>`}).join('');
  const kv=list=>(list||[]).map(x=>`<div class="line kv"><span>${esc(x.k)}</span><b class="${x.t==='key'?'key':x.t==='good'?'good':x.t==='bad'?'bad':''}">${esc(x.v)}</b></div>`).join('');
  const fl=[];
  if(f.vx){const v=f.vx_state||{}, good=(v.who==='продавцы'&&short)||(v.who==='покупатели'&&!short), bad=(v.who==='продавцы'&&!short)||(v.who==='покупатели'&&short);
    fl.push(`<div class="line f"><span>вортекс 30м <span style="color:var(--dim)">· VI+ ${f.vx_now?f.vx_now[0].toFixed(2):'—'} / VI− ${f.vx_now?f.vx_now[1].toFixed(2):'—'}</span></span>${sparkSvg([f.vx.map(x=>x[0]),f.vx.map(x=>x[1])],['#6fcf97','#ff7a7a'])}
      <b class="${good?'good':bad?'bad':''}">${v.who==='ровно'?'серии нет':'давят '+esc(v.who)+' · '+v.bars}</b></div>`);}
  if(f.kl){const k=f.kl_state||{}, good=(k.state==='выдыхается'&&short)||(k.state==='продавцы выдыхаются'&&!short), bad=(k.state==='выдыхается'&&!short)||(k.state==='продавцы выдыхаются'&&short);
    fl.push(`<div class="line f"><span>клингер 30м <span style="color:var(--dim)">· ${k.p1!=null?mln(k.p1)+' → '+mln(k.p2):(k.falling?'падает':'растёт')}</span></span>${sparkSvg([f.kl.map(x=>x[0]),f.kl.map(x=>x[1])],['#f5a93a','#849dad'],[false,true])}
      <b class="${good?'good':bad?'bad':''}">${esc(k.state||'—')}</b></div>`);}
  if(f.jn){const d=x=>Math.floor(x/60)+':'+String(x%60).padStart(2,'0');
    fl.push(`<div class="line kv"><span>стык · ${esc(f.jn.next)} через ${d(f.jn.in_min)}${f.jn.ago_min<=120?' · «'+esc(f.jn.prev)+'» идёт '+d(f.jn.ago_min):''}</span><b>${hm(f.jn.next_t).slice(-5)}</b></div>`);}
  if(f.lev){const good=short?f.lev.state==='уходит':f.lev.state==='держит';
    fl.push(`<div class="line kv"><span>плечо · ${(f.lev.off>0?'+':'')+f.lev.off.toFixed(1)}% от максимума за 6 ч</span><b class="${good?'good':'bad'}">${esc(f.lev.state)}</b></div>`);}
  (f.regime||[]).forEach(x=>fl.push(`<div class="line kv"><span>${esc(x.k)}</span><b>${esc(x.v)}</b></div>`));
  const srok=a.hold?`${Math.min(a.bars,a.hold)} из ${a.hold}`:`${a.bars}`;
  card.innerHTML=`
    <div class="kick"><svg width="26" height="26"><use href="#i-coin"/></svg>позиция · ${esc(a.book)}</div>
    <h2>${esc(a.sym)}</h2>
    <div class="h2s"><span style="color:${short?'#ffb4b4':'var(--up)'}">${short?'шорт':'лонг'}</span> · ${esc(a.rule)} · вес ×${a.size}</div>
    <div class="status">
      <span class="pill ${a.done?'':'g'}">${a.done?'сработало':'в работе'}</span>
      <p>${esc(gk)}: <b>${esc(gv)}</b>${gs?' · '+esc(gs):''}</p>
    </div>
    <div class="hero ${(a.res||0)<0?'neg':''}">
      <div class="row"><span>ход с входа</span><span class="pill">${a.done?'сработало':a.nearest?'ближе всего · '+esc(a.nearest)+(nf!=null?' '+nf+'%':''):'только вошла'}</span></div>
      <div class="big">
        <div><b class="${cls(a.res||0)}">${pct(a.res)}</b><small>${m!=null?money(m)+' от цены сейчас':''}</small></div>
        <div class="histw">${posChart(a)}<div class="histl">ТВХ ${px6(a.entry)} → ${px6(a.px)}</div></div>
      </div>
    </div>
    <div class="tiles">
      <div class="tile"><div class="t1"><svg width="26" height="26"><use href="#i-avg"/></svg><b>${esc(gv)}</b></div><div class="t2">${esc(gk)}</div><div class="t3">${esc(gs)||'—'}</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26"><use href="#i-list"/></svg><b>${srok}</b></div><div class="t2">${a.hold?'баров из срока':'баров в позиции'}</div><div class="t3">${a.due?'закроется около '+hm(a.due):'без срока'}</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26" style="color:var(--up)"><use href="#i-up"/></svg><b class="p">${a.mfe!=null?pct(a.mfe):'—'}</b></div><div class="t2">лучшая точка</div><div class="t3">с входа</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26" style="color:var(--dn)"><use href="#i-dn"/></svg><b class="m">${a.mae!=null?pct(-a.mae):'—'}</b></div><div class="t2">худшая точка</div><div class="t3">с входа</div></div>
    </div>
    <div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>когда закроется</div>
    ${closeLines}
    <div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>почему взята</div>
    ${kv(a.facts)}
    <div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>что сейчас</div>
    ${kv(a.now)}
    ${fl.length?`<div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>быстрые и режим<small>наблюдение · боты не читают</small></div>${fl.join('')}`:''}
    <div class="note"><b>Почему взята.</b> ${tmx(a.why)}<br><br><b>Чего ждём.</b> ${tmx(a.wait)}<br><br>правило: ${esc(a.rl)}${a.walls?' · стакан: '+esc(a.walls):''}</div>`;
  card.classList.add('fresh'); card.scrollTop=0;
}
function showWork(sym){ buildWork(sym); reveal(); }
/* дни и шар — пересобираются при смене источника */
const daysEl=$('days');
function build(key){
  document.body.classList.remove('workmode');
  $('orbk').textContent='итог бота';
  $('c1').textContent='сделок'; $('c2').textContent='попаданий'; $('c3').textContent='лучший день'; $('c4').textContent='худший';
  SRC=key; const B=BOOK[key];
  document.querySelectorAll('#srcsw button').forEach(x=>x.classList.toggle('on',x.dataset.src===key));
  document.body.classList.toggle('backfill',key==='back');
  DAYS=B.days.map((d,i)=>{
    const noon=new Date(d.d+'T12:00:00Z');
    d.rows.forEach(r=>{r.day=i});
    return {label:d.d.slice(8,10)+'.'+d.d.slice(5,7), dd:+d.d.slice(8,10),
      wd:noon.toLocaleDateString('ru-RU',{weekday:'short',timeZone:'UTC'}), hit:d.hit, rows:d.rows, total:d.total, n:d.n, nopen:d.nopen,
      t0:Date.parse(d.d+'T00:00:00Z')/1000};
  });
  all=DAYS.flatMap(d=>d.rows);
  closedAll=all.filter(r=>!r.open);
  $('allmoney').textContent=money(B.total); $('allmoney').className=cls(B.total);
  $('allsub').textContent=DAYS.length?(key==='back'?`задним числом за ${DAYS.length} дн`:`закрытые за ${DAYS.length} дн`):'закрытых сделок нет';
  $('alln').textContent=closedAll.length; $('nall').textContent=closedAll.length; $('ndays').textContent=DAYS.length;
  $('allhit').textContent=closedAll.length?Math.round(100*closedAll.filter(r=>r.money>0).length/closedAll.length)+'%':'—';
  const bd=DAYS.length?Math.max(...DAYS.map(d=>d.total)):null, wd=DAYS.length?Math.min(...DAYS.map(d=>d.total)):null;
  $('bestday').textContent=bd==null?'—':money(bd); $('bestday').className=bd==null?'':cls(bd);
  $('worstday').textContent=wd==null?'—':money(wd); $('worstday').className=wd==null?'':cls(wd);
  $('nopen').textContent=all.filter(r=>r.open).length;
  $('onote').textContent=B.note||'';
  dayMax=Math.max(...DAYS.map(d=>Math.abs(d.total)))||1;
  tradeMax=Math.max(...all.map(r=>Math.abs(r.money)))||1;
  daysEl.innerHTML=DAYS.length?'':`<div class="cap" style="padding:10px 4px">${key==='back'?'реконструкции нет':'живых журналов пока нет'}</div>`;
  DAYS.forEach((d,i)=>{
    const el=document.createElement('button'); el.type='button'; el.className='day'+(d.total<0?' neg':''); el.style.setProperty('--i',i);
    el.style.setProperty('--k',(Math.abs(d.total)/dayMax).toFixed(2));
    const sp=d.rows.map(r=>`<i class="${cls(r.money)}" style="height:${Math.max(1.5,Math.sqrt(Math.abs(r.money)/tradeMax)*7).toFixed(1)}px"></i>`).join('');
    el.innerHTML=`<span class="dt"><b>${d.dd}</b><i>${d.wd}</i></span>
      <span class="mn">
        <span class="s ${cls(d.total)}">${money(d.total)}</span>
        <span class="sp" aria-hidden="true">${sp}</span>
        <span class="d"><span>${d.label} · <em>${d.n}</em> сделок</span><span><em>${d.n?d.hit+'%':'—'}</em></span></span>
      </span>
      <span class="hr" aria-hidden="true">${d.n?`<i style="width:${d.hit}%"></i>`:''}</span>${d.nopen?`<span class="dwk" title="в работе ${d.nopen}">${d.nopen}</span>`:''}`;
    el.setAttribute('aria-label',`${d.label}, ${money(d.total)}, сделок ${d.n}, попаданий ${d.hit}%`);
    el.title=`день бота ${d.label} UTC · у вас с ${hm(d.t0)} до ${hm(d.t0+86400)}`;
    el.onclick=()=>pickDay(i); daysEl.appendChild(el);
  });
  if(DAYS.length){ pickDay(0); }
  else{
    fan.innerHTML=''; $('fancap').textContent='сделок нет'; $('fansub').textContent='';
    $('crumb').textContent='—'; $('side').innerHTML='<div class="empty">сделок пока нет</div>';
    arc(true); wires();
  }
}

const fan=$('fan');
let curDay=0, drawOnce=false, ARC=null;

function segs(v){
  const n=Math.min(3,Math.max(1,Math.ceil(Math.abs(v)/2)));
  return `<span class="seg ${v>=0?'p':'m'}">${[0,1,2].map(k=>`<i class="${k<n?'on':''}"></i>`).join('')}</span>`;
}
function pickDay(i,keepSym){
  curDay=i;
  [...daysEl.children].forEach((e,k)=>e.classList.toggle('on',k===i));
  const D=DAYS[i];
  $('fancap').textContent='сделки за '+D.label+' UTC';
  $('fansub').textContent=`закрыто ${D.n}${D.nopen?' · в работе '+D.nopen:''} · итог ${money(D.total)} · депозит дня ${Math.round(BOOK.deposit).toLocaleString('ru-RU')} $`;
  fan.innerHTML='';
  const rows=D.rows.slice().sort((a,b)=>Math.abs(b.money)-Math.abs(a.money));
  if(!rows.length) fan.innerHTML='<div class="cap" style="padding:0 0 0 20px">в этот день сделок нет</div>';
  rows.forEach((r,k)=>{
    const el=document.createElement('div'); el.className='tr '+(r.open?'open':'done');
    el.tabIndex=0; el.style.setProperty('--i',k); el.dataset.sym=r.sym;
    el.title=`${r.sym} · ${r.side<0?'шорт':'лонг'} · вес ×${r.size} · ${r.book}\n${r.rl}\n${r.why}`+(r.ent?`\nвход ${hm(r.ent)}`:'')+(!r.open&&r.at?` · выход ${hm(r.at)}`:'');
    el.innerHTML=`<div class="in">
      <span class="nm">${esc(r.sym)}</span><span class="mo ${cls(r.money)}">${money(r.money)}</span>
      <span class="meta"><span class="tag ${r.open?'open':''}">${r.open?'в работе':'закрыта'}</span><span class="tag">${r.side<0?'▼':'▲'} ${pct(r.res)}</span>${r.res==null?'':segs(r.res)}<span class="rule">${esc(r.rule)} · ${esc(r.why)}</span></span>
    </div>`;
    el.onclick=()=>pickSym(r.sym,el);
    el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pickSym(r.sym,el)}};
    fan.appendChild(el);
  });
  const trs=[...fan.querySelectorAll('.tr')];
  const mid=trs[Math.floor((trs.length-1)/2)];
  if(mid){
    fan.scrollTop=mid.offsetTop+mid.offsetHeight/2-fan.clientHeight/2;
    pickSym(mid.dataset.sym,mid);
  }
  arc(true); wires();
}

function pickSym(sym,el){
  [...fan.querySelectorAll('.tr')].forEach(e=>e.classList.toggle('on',e===el));
  const rows=all.filter(r=>r.sym===sym);
  const done=rows.filter(r=>!r.open), open=rows.length-done.length;
  const base=done.length?done:rows;
  const tot=done.reduce((s,r)=>s+r.money,0);
  const hit=done.length?Math.round(100*done.filter(r=>r.money>0).length/done.length):null;
  const byRule={}; rows.forEach(r=>{(byRule[r.rule]=byRule[r.rule]||[]).push(r)});
  const best=base.reduce((a,b)=>a.money>b.money?a:b), worst=base.reduce((a,b)=>a.money<b.money?a:b);
  const withRes=base.filter(r=>r.res!=null);
  const avgRes=withRes.length?withRes.reduce((s,r)=>s+r.res,0)/withRes.length:null;
  const last=rows[0];
  const seq=all.filter(r=>!r.open).slice().reverse(), mx=Math.max(...seq.map(r=>Math.abs(r.money)))||1;
  const hist=seq.map((r,k)=>`<i class="${cls(r.money)}${r.sym===sym?' me':''}" style="--i:${k};height:${Math.max(1.5,Math.sqrt(Math.abs(r.money)/mx)*30).toFixed(1)}px"></i>`).join('');
  $('crumb').textContent=`${sym} · ${rows.length} сделок за ${DAYS.length} дн · правил ${Object.keys(byRule).length}`;
  const card=$('side');
  card.classList.remove('fresh'); void card.offsetWidth;
  const ruleLines=Object.entries(byRule).map(([k,v])=>{
    const vd=v.filter(r=>!r.open), t=vd.reduce((s,r)=>s+r.money,0);
    return `<div class="line"><span>${esc(k)}</span><span class="dm">${v.length} шт</span>
      <span class="dm hit">${vd.length?Math.round(100*vd.filter(r=>r.money>0).length/vd.length)+'%':'—'}</span>
      <b class="${vd.length?cls(t):''}">${vd.length?money(t):'в работе'}</b></div>`}).join('');
  card.innerHTML=`
    <div class="kick"><svg width="26" height="26"><use href="#i-coin"/></svg>монета · ${SRC==='back'?'задним числом по архиву':'бумажная книга бота'}</div>
    <h2>${esc(sym)}</h2>
    <div class="h2s">${rows.length} сделок · ${open?'в работе '+open:'все закрыты'}</div>
    <div class="status">
      <span class="pill ${open?'g':''}">${open?'в работе':'закрыта'}</span>
      <p>последняя: <b>${esc(last.rule)}</b> · ${esc(last.why)} · ${DAYS[last.day].label}</p>
      <button class="btn" type="button" onclick="document.querySelector('.card .sec').scrollIntoView({behavior:'smooth'})">по правилам ›</button>
    </div>
    <div class="hero ${tot<0?'neg':''}">
      <div class="row"><span>итог по монете</span><span class="pill ${hit==null||hit>=50?'':'g'}">${hit==null?'закрытых нет':'попаданий '+hit+'%'}</span></div>
      <div class="big">
        <div><b class="${done.length?cls(tot):''}">${done.length?money(tot):'—'}</b><small>${avgRes==null?'нет цены сейчас':pct(avgRes)+' на сделку в среднем'}</small></div>
        <div class="histw"><div class="hist" aria-hidden="true">${hist}</div><div class="histl">закрытые книги · ${esc(sym)} ярче</div></div>
      </div>
    </div>
    <div class="tiles">
      <div class="tile"><div class="t1"><svg width="26" height="26"><use href="#i-avg"/></svg><b>${done.length?money(tot/done.length):'—'}</b></div><div class="t2">средняя сделка</div><div class="t3">${avgRes==null?'—':pct(avgRes)+' на сделку'}</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26"><use href="#i-list"/></svg><b>${rows.length}</b></div><div class="t2">сделок</div><div class="t3">${open?'в работе '+open:'все закрыты'}</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26" style="color:var(--up)"><use href="#i-up"/></svg><b class="${cls(best.money)}">${money(best.money)}</b></div><div class="t2">лучшая</div><div class="t3">${esc(best.rule)}</div></div>
      <div class="tile"><div class="t1"><svg width="26" height="26" style="color:var(--dn)"><use href="#i-dn"/></svg><b class="${cls(worst.money)}">${money(worst.money)}</b></div><div class="t2">худшая</div><div class="t3">${esc(worst.rule)}</div></div>
    </div>
    <div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>по правилам</div>
    ${ruleLines}
    <div class="sec"><svg width="20" height="20"><use href="#i-spark"/></svg>сделки</div>
    ${rows.slice(0,14).map(r=>`<div class="line" title="${esc(r.why)}"><span><i class="st ${r.open?'open':''}"></i>${esc(r.rule)}</span>
      <span class="dm">${DAYS[r.day].label}</span><span class="dm hit">${r.side<0?'▼':'▲'} ${pct(r.res)}</span>
      <b class="${cls(r.money)}">${money(r.money)}</b></div>`).join('')}
    ${(BOOK.work||[]).some(w=>w.sym===sym)?`<button class="btn gowork" type="button" data-sym="${esc(sym)}">разбор позиции: почему взята и чего ждём ›</button>`:''}
    <div class="note">вес правила решает, сколько депозита дня получила сделка — процент и деньги расходятся намеренно; у открытых деньги считаются от цены сейчас и в итог не входят</div>`;
  const gw=card.querySelector('.gowork'); if(gw) gw.onclick=()=>showWork(gw.dataset.sym);
  card.classList.add('fresh'); card.scrollTop=0;
}

/* веер по дуге: середина видимой части уходит вправо, края к нитям */
const wide=()=>matchMedia('(min-width:1181px)').matches;
/* ГЕОМЕТРИЯ ВЕЕРА — снимается один раз после сборки дня и при смене размера: прокрутка не двигает
   раскладку, а чтение offsetTop после записи transform на каждой из сотен строк давало пересчёт
   раскладки на каждую строку (реконструкция — 240 сделок за день). Пишем только видимые строки. */
let GEO=null;
function geo(){
  const trs=[...fan.querySelectorAll('.tr')];
  const F=fan.getBoundingClientRect(), TW=trs.length?trs[0].offsetWidth:228;
  const S=Math.max(30,Math.min(260,F.width-TW-96-24)), h=F.height*.5;
  const R=(h*h+S*S)/(2*S);
  GEO={trs, mid:trs.map(t=>t.offsetTop+t.offsetHeight/2), F, S, h, R};
  ARC={S,R,cy:F.top+F.height/2,left:F.left+96,top:F.top,bottom:F.bottom};
}
function arc(force){
  if(!wide()){fan.querySelectorAll('.tr').forEach(t=>{t.style.transform=''});GEO=null;return}
  if(!GEO||force) geo();
  // только transform: края списка гасит маска веера; строки за краем окна не трогаем — их не видно
  const {trs,mid,F,S,h,R}=GEO, st=fan.scrollTop, half=F.height/2, pad=h*1.15;
  for(let k=0;k<trs.length;k++){
    const dyS=mid[k]-st-half;
    if(Math.abs(dyS)>pad) continue;
    const dy=Math.min(R,Math.abs(dyS));
    const x=S-(R-Math.sqrt(R*R-dy*dy));
    trs[k].style.transform=`translateX(${Math.max(-20,x).toFixed(1)}px)`;
  }
}

/* нити: шар → все дни, выбранный день → сделки */
function curve(x0,y0,x1,y1){const m=(x0+x1)/2;return `M${x0.toFixed(1)} ${y0.toFixed(1)}C${m.toFixed(1)} ${y0.toFixed(1)} ${m.toFixed(1)} ${y1.toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)}`}
function wires(){
  const svg=$('wires');
  if(!wide()){svg.innerHTML='';$('bands').innerHTML='';return}
  const R=$('stage').getBoundingClientRect(), B=$('ball').getBoundingClientRect();
  const day=daysEl.querySelector('.day.on'); if(!day) return;
  const DR=daysEl.getBoundingClientRect(), FR=fan.getBoundingClientRect();
  const x0=B.left-R.left+B.width/2+44, y0=B.top-R.top+B.height/2;
  const top=FR.top-R.top, bot=FR.bottom-R.top, H=bot-top;
  let s=`<defs>
    <filter id="wf" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>
    <filter id="wf2" x="-200%" y="-200%" width="500%" height="500%"><feGaussianBlur stdDeviation="8"/></filter>
    <linearGradient id="fadeV" gradientUnits="userSpaceOnUse" x1="0" y1="${top}" x2="0" y2="${bot}">
      <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".22" stop-color="#fff"/><stop offset=".78" stop-color="#fff"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
    <mask id="mV" maskUnits="userSpaceOnUse" x="0" y="${top}" width="${R.width}" height="${H}"><rect x="0" y="${top}" width="${R.width}" height="${H}" fill="url(#fadeV)"/></mask>
  </defs>`;
  /* шар → дни */
  [...daysEl.children].forEach(d=>{
    const b=d.getBoundingClientRect(); if(b.bottom<DR.top||b.top>DR.bottom) return;
    const y1=b.top-R.top+b.height/2, on=d===day;
    if(on) s+=`<path d="${curve(x0,y0,b.left-R.left,y1)}" fill="none" stroke="#f5a93a" stroke-opacity=".5" stroke-width="4" filter="url(#wf)"/>`;
    s+=`<path class="w" pathLength="1" d="${curve(x0,y0,b.left-R.left,y1)}" stroke="${on?'#ffe3b0':'#b9c2da'}" stroke-opacity="${on?.95:.3}" stroke-width="${on?1.4:.8}"/>`;
  });
  /* переплетённые светящиеся полосы между днями и веером — живут сами по себе */
  const xa=DR.right-R.left+14, xb=FR.left-R.left+84, xc=(xa+xb)/2, A=Math.max(10,(xb-xa)/2-8), P=300;
  const bands=[
    {ph:0,   a:1,   c:'#ffd08a', w:1.3, g:.34},
    {ph:2.1, a:.85, c:'#f5a93a', w:1,   g:.26},
    {ph:4.2, a:.95, c:'#d8cfff', w:.9,  g:.18},
    {ph:1.05,a:.55, c:'#fff1d6', w:.7,  g:.2},
    {ph:3.15,a:.6,  c:'#a9b4d8', w:.7,  g:.14},
  ];
  const path=(bd)=>{let d='';for(let y=top-P-8;y<=bot+8;y+=8){const x=xc+A*bd.a*Math.sin(2*Math.PI*y/P+bd.ph);d+=(d?'L':'M')+x.toFixed(1)+' '+y.toFixed(0)}return d};
  let glow='',core='';
  bands.forEach(bd=>{const d=path(bd);
    glow+=`<path d="${d}" stroke="${bd.c}" stroke-opacity="${bd.g}" stroke-width="7"/>`;
    core+=`<path d="${d}" stroke="${bd.c}" stroke-opacity=".75" stroke-width="${bd.w}"/>`;});
  const bw=$('bandsw'), bs=$('bands'), bx0=xa-50, BW=(xb-xa)+100;
  Object.assign(bw.style,{left:bx0+'px',top:top+'px',width:BW+'px',height:H+'px'});
  bs.setAttribute('width',BW); bs.setAttribute('height',H+P);
  bs.setAttribute('viewBox',`${bx0} ${top-P} ${BW} ${H+P}`);
  bs.style.top=(-P)+'px'; bs.style.setProperty('--P',P+'px');
  bs.innerHTML=`<defs><filter id="bf" x="-50%" y="-5%" width="200%" height="110%"><feGaussianBlur stdDeviation="3"/></filter></defs>
    <g fill="none" stroke-linecap="round"><g filter="url(#bf)">${glow}</g>${core}</g>`;
  /* дуга веера */
  if(ARC){
    const cx=ARC.left-R.left+ARC.S-ARC.R, ccy=ARC.cy-R.top, a=Math.asin(Math.min(1,(ARC.bottom-ARC.cy)/ARC.R));
    const pp=ang=>[(cx+ARC.R*Math.cos(ang)).toFixed(1),(ccy+ARC.R*Math.sin(ang)).toFixed(1)];
    const [ax,ay]=pp(-a),[bx,by]=pp(a);
    const d=`M${ax} ${ay}A${ARC.R.toFixed(1)} ${ARC.R.toFixed(1)} 0 0 1 ${bx} ${by}`;
    s+=`<g mask="url(#mV)"><path d="${d}" fill="none" stroke="#ffd08a" stroke-opacity=".3" stroke-width="5" filter="url(#wf)"/>
      <path d="${d}" fill="none" stroke="#ffd08a" stroke-opacity=".5" stroke-width="1"/></g>`;
  }
  /* вспышка у выбранного дня, уходит в полосы */
  const d=day.getBoundingClientRect(), y1=d.top-R.top+d.height/2, x2=d.right-R.left;
  s+=`<path d="M${x2} ${y1}C${x2+20} ${y1} ${xc-10} ${y1} ${xc} ${y1}" stroke="#ffe3b0" stroke-opacity=".8" stroke-width="1.2" fill="none"/>
    <ellipse cx="${(x2+xc)/2}" cy="${y1}" rx="${Math.max(40,(xc-x2)/2+30)}" ry="14" fill="#ffc977" opacity=".35" filter="url(#wf2)"/>
    <circle cx="${xc}" cy="${y1}" r="16" fill="#ffe3b0" opacity=".45" filter="url(#wf2)"/>
    <circle cx="${x2}" cy="${y1}" r="3" fill="#fffaf0"/><circle cx="${xc}" cy="${y1}" r="2.4" fill="#fffaf0"/>`;
  svg.setAttribute('viewBox',`0 0 ${R.width} ${R.height}`);
  svg.classList.toggle('draw',drawOnce);
  svg.innerHTML=s;
}

let raf=0, rw=0;
const onMove=()=>{if(raf)return;raf=requestAnimationFrame(()=>{raf=0;arc()})};
const onLayout=()=>{if(rw)return;rw=requestAnimationFrame(()=>{rw=0;arc(true);wires()})};
fan.addEventListener('scroll',onMove,{passive:true});
daysEl.addEventListener('scroll',onLayout,{passive:true});
addEventListener('resize',onLayout);

function reveal(){
  const b=document.body;
  b.classList.remove('play'); void b.offsetWidth; b.classList.add('play');
  drawOnce=true; arc(true); wires(); drawOnce=false;
}
$('replay').onclick=()=>{
  if(SRC==='work'){buildWork(curPos);reveal();return}
  if(DAYS.length)pickDay(curDay);reveal()};
const NW=(BOOK.work||[]).length;
$('nwork').textContent=NW;
if(NW) document.querySelector('#srcsw .wkbtn').classList.add('live');
document.querySelectorAll('#srcsw button').forEach(b=>{
  if(b.dataset.src==='work'){ b.onclick=()=>showWork(); return; }
  const has=BOOK[b.dataset.src]&&BOOK[b.dataset.src].days.length;
  if(!has){b.disabled=true;b.title='данных нет';}
  b.onclick=()=>{
    if(b.disabled) return;
    if(b.dataset.src===SRC) return;
    build(b.dataset.src); reveal();
  };
});
$('nopenbtn').onclick=()=>showWork();
$('nopenbtn').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();showWork()}};
build(BOOK.live.days.length||!BOOK.back.days.length?'live':'back');
(document.fonts&&document.fonts.ready?document.fonts.ready:Promise.resolve()).then(reveal);
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
