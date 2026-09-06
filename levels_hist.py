"""Уровни цены из истории — слой рядом с картой ликвидаций (06.09, правила владельца).

Что такое уровень (владелец, 06.09):
  «уровень — не место, где цена была, а где она среагировала: отскочила и постояла».
  Жёстких сроков нет, есть один минимум — ДВА ДНЯ. Слив без остановок уровней не
  оставляет — там записывается «пусто». Считаем по ДНЕВКАМ, недели не нужны.

Три вида:
  pause  — цена пришла (ход не меньше DEP), развернулась и постояла от MIN_DAYS дней:
           закрытия в полосе шириной от самой монеты (её обычный дневной ход), потом
           ушла в обратную сторону не меньше DEP. Это и есть «отскок с небольшим флетом».
  bounce — два и больше пиков (или впадин) в пределах BOUNCE_TOL друг от друга, каждый с
           разворотом не меньше BOUNCE_REV (четверть цены): BLESS 0.034 — апрель и август.
  points — особые точки отдельно: историческое дно, пик, цена листинга.

Вес — ранг, не отбор: дней стояла, сколько раз возвращалась (touches), как далеко уходила.
Возврат с ходом («рост с флета и спуск обратно») — не условие, а второе касание: поднимает
ранг и помечает полку как tested.

Действие по уровню считается НА 5% НИЖЕ полки (ACT_BELOW): и ступень входа, и хедж —
«нет точной цены около уровня или за уровнем флета — всё подходит».

Слив — промежуток между соседними уровнями, в котором цена шла без остановок: пишется в
empty явно, чтобы экран говорил «между X и Y уровней нет», а не молчал.

Проверка на одной монете (сначала ARB и BLESS — должны совпасть с оранжевыми линиями):
    python3 levels_hist.py --only ARBUSDT
    python3 levels_hist.py --only BLESSUSDT --write      # → output/levels/BLESSUSDT.json
Пороги — наверху файла; калибровать по этим двум, потом гонять всех.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

OUT_DIR = BASE_DIR / "output" / "levels"

# ── пороги (калибровать на ARB и BLESS) ─────────────────────────────────────────
MIN_DAYS = 2          # минимум стояния — единственное правило по времени
BAND_MIN = 0.03       # полоса стояния: медианный дневной ход монеты, но не уже 3% …
BAND_MAX = 0.15       # … и не шире 15%
DEP_K = 2.5           # ход «пришла» / «ушла» — DEP_K × полоса …
DEP_MIN = 0.12        # … но не меньше 12%
LOOK = 12             # дней до/после полки, где ищем подход и уход
BOUNCE_REV = 0.25     # отбой: разворот не меньше четверти цены с обеих сторон
BOUNCE_TOL = 0.05     # два пика в пределах 5% — один уровень отбоя
BOUNCE_WIN = 10       # дней с каждой стороны, где пик должен быть экстремумом
ACT_BELOW = 0.05      # действие — на 5% ниже полки
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


# ── история дневок: спот, если он старше перпа, иначе перп ─────────────────────
def _get(url: str, params: dict) -> list | None:
    try:
        req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers=UA)
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def _klines(base: str, sym: str, limit: int) -> list[list]:
    """Все дневки с листинга: листаем startTime вперёд, пока биржа отдаёт полные страницы."""
    out: list[list] = []
    start = 0
    for _ in range(40):
        rows = _get(base, {"symbol": sym, "interval": "1d", "limit": limit, "startTime": start})
        if not rows:
            break
        for r in rows:
            if not out or r[0] > out[-1][0]:
                out.append(r)
        if len(rows) < limit:
            break
        start = rows[-1][0] + 1
        time.sleep(0.15)
    # последняя дневка не закрыта — не считаем
    now = int(time.time() * 1000)
    return [r for r in out if int(r[6]) < now]


def load_daily(sym: str) -> tuple[list[dict], str]:
    fut = _klines("https://fapi.binance.com/fapi/v1/klines", sym, 1500)
    spot = _klines("https://api.binance.com/api/v3/klines", sym, 1000)
    src, rows = "perp", fut
    if spot and (not fut or spot[0][0] < fut[0][0]):
        src, rows = "spot", spot
    days = [{"t": int(r[0]), "o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4]),
             "q": float(r[7])} for r in rows]
    return days, src


# ── расчёт ──────────────────────────────────────────────────────────────────────
def _band_width(days: list[dict]) -> float:
    rng = [(d["h"] - d["l"]) / d["c"] for d in days if d["c"] > 0]
    med = statistics.median(rng) if rng else BAND_MIN
    return max(BAND_MIN, min(BAND_MAX, med))


def _date(t: int) -> str:
    return datetime.fromtimestamp(t / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _pauses(days: list[dict], bw: float, dep: float) -> list[dict]:
    """Полки стояния: пришла ≥dep, постояла ≥MIN_DAYS в полосе ±bw, ушла в обратную сторону ≥dep."""
    c = [d["c"] for d in days]
    n = len(c)
    out: list[dict] = []
    i = 0
    while i < n:
        run = [i]
        med = c[i]
        j = i + 1
        while j < n and abs(c[j] - med) / med <= bw:
            run.append(j)
            med = statistics.median(c[k] for k in run)
            j += 1
        if len(run) >= MIN_DAYS:
            s, e = run[0], run[-1]
            before = c[max(0, s - LOOK):s]
            after = c[e + 1:e + 1 + LOOK]
            # подход: откуда пришла — самое дальнее закрытие до полки
            appr = 0.0
            if before:
                far = max(before, key=lambda x: abs(x - med))
                appr = (med - far) / far          # >0 — пришла снизу (росла), <0 — сверху
            # уход: куда ушла после полки
            leave = 0.0
            if after:
                far2 = max(after, key=lambda x: abs(x - med))
                leave = (far2 - med) / med        # >0 — ушла вверх
            came = abs(appr) >= dep
            went = abs(leave) >= dep
            reversed_ = came and went and (appr > 0) != (leave > 0)
            if reversed_:
                lo = min(c[k] for k in run)
                hi = max(c[k] for k in run)
                out.append({"kind": "pause", "lo": lo, "hi": hi, "price": med,
                            "days": len(run), "first": _date(days[s]["t"]), "last": _date(days[e]["t"]),
                            "from": "снизу" if appr > 0 else "сверху",
                            "away": round(max(abs(appr), abs(leave)) * 100, 1),
                            "vol": sum(days[k]["q"] for k in run), "i0": s, "i1": e})
        i = run[-1] + 1
    return out


def _bounces(days: list[dict], bw: float) -> list[dict]:
    """Уровни отбоя: пики/впадины с разворотом ≥BOUNCE_REV с обеих сторон, сбившиеся в ±BOUNCE_TOL."""
    hi = [d["h"] for d in days]
    lo = [d["l"] for d in days]
    n = len(days)
    pts: list[tuple[int, float, str]] = []
    for i in range(BOUNCE_WIN, n - BOUNCE_WIN):
        w0, w1 = i - BOUNCE_WIN, i + BOUNCE_WIN + 1
        if hi[i] >= max(hi[w0:w1]):
            left = min(lo[w0:i]); right = min(lo[i + 1:w1])
            if hi[i] / max(left, 1e-12) - 1 >= BOUNCE_REV and hi[i] / max(right, 1e-12) - 1 >= BOUNCE_REV:
                pts.append((i, hi[i], "top"))
        if lo[i] <= min(lo[w0:w1]):
            left = max(hi[w0:i]); right = max(hi[i + 1:w1])
            if left / max(lo[i], 1e-12) - 1 >= BOUNCE_REV and right / max(lo[i], 1e-12) - 1 >= BOUNCE_REV:
                pts.append((i, lo[i], "bottom"))
    out: list[dict] = []
    used = [False] * len(pts)
    for a in range(len(pts)):
        if used[a]:
            continue
        grp = [pts[a]]
        used[a] = True
        for b in range(a + 1, len(pts)):
            if not used[b] and pts[b][2] == pts[a][2] and abs(pts[b][1] - pts[a][1]) / pts[a][1] <= BOUNCE_TOL:
                grp.append(pts[b]); used[b] = True
        if len(grp) >= 2:                       # одиночный пик — не уровень
            price = statistics.median(p[1] for p in grp)
            out.append({"kind": "bounce", "lo": min(p[1] for p in grp), "hi": max(p[1] for p in grp),
                        "price": price, "days": len(grp), "touches": len(grp),
                        "first": _date(days[grp[0][0]]["t"]), "last": _date(days[grp[-1][0]]["t"]),
                        "side": "сверху" if grp[0][2] == "top" else "снизу", "i0": grp[0][0], "i1": grp[-1][0]})
    return out


def _touches(level: dict, days: list[dict], bw: float, dep: float) -> tuple[int, bool]:
    """Возвраты: закрытие вошло в полосу после того, как было от неё дальше dep. tested — был ход и возврат."""
    c = [d["c"] for d in days]
    lo, hi = level["lo"] * (1 - bw / 2), level["hi"] * (1 + bw / 2)
    t, away, tested = 0, False, False
    for k in range(level["i1"] + 1, len(c)):
        if c[k] < lo * (1 - dep) or c[k] > hi * (1 + dep):
            away = True
        elif lo <= c[k] <= hi and away:
            t += 1; away = False; tested = True
    return t, tested


def _merge(levels: list[dict], bw: float) -> list[dict]:
    levels.sort(key=lambda x: x["price"])
    out: list[dict] = []
    for lv in levels:
        if out and lv["lo"] <= out[-1]["hi"] * (1 + bw):
            m = out[-1]
            m["lo"], m["hi"] = min(m["lo"], lv["lo"]), max(m["hi"], lv["hi"])
            m["price"] = (m["lo"] + m["hi"]) / 2
            m["days"] += lv["days"]; m["touches"] = m.get("touches", 0) + lv.get("touches", 0)
            m["first"], m["last"] = min(m["first"], lv["first"]), max(m["last"], lv["last"])
            m["kind"] = m["kind"] if m["kind"] == lv["kind"] else "pause+bounce"
            m["tested"] = m.get("tested", False) or lv.get("tested", False)
            m["i1"] = max(m["i1"], lv["i1"])
        else:
            out.append(dict(lv))
    return out


def compute(days: list[dict]) -> dict:
    if len(days) < MIN_DAYS + 2 * LOOK:
        return {"levels": [], "points": {}, "empty": [], "note": "мало истории"}
    bw = _band_width(days)
    dep = max(DEP_K * bw, DEP_MIN)
    levels = _pauses(days, bw, dep) + _bounces(days, bw)
    for lv in levels:
        t, tested = _touches(lv, days, bw, dep)
        lv["touches"] = lv.get("touches", 0) + t
        lv["tested"] = tested
    levels = _merge(levels, bw)
    now = days[-1]["c"]
    for lv in levels:
        lv["rank"] = round(lv["days"] + 2 * lv["touches"] + lv.get("away", 0) / 10, 1)
        lv["dist_pct"] = round((lv["price"] / now - 1) * 100, 1)
        lv["above"] = lv["price"] > now
        # действие — на 5% ниже полки: ступень/хедж ставим раньше, чем цена её коснётся
        lv["act"] = lv["price"] * (1 - ACT_BELOW)
        lv["held"] = now >= lv["lo"] * (1 - bw)     # цена не ниже полки — полка держит
        lv["broken_down"] = (not lv["held"]) and lv["last"] < _date(days[-1]["t"])
        for k in ("i0", "i1"):
            lv.pop(k, None)
        for k in ("lo", "hi", "price", "act", "vol"):
            if k in lv:
                lv[k] = float(f"{lv[k]:.6g}")
    # пусто: промежутки между соседними уровнями шире 2×dep без единого уровня
    empty = []
    ordered = sorted(levels, key=lambda x: x["price"])
    for a, b in zip(ordered, ordered[1:]):
        if b["lo"] / a["hi"] - 1 >= 2 * dep:
            empty.append([a["hi"], b["lo"]])
    lows = min(days, key=lambda d: d["l"]); highs = max(days, key=lambda d: d["h"])
    points = {"atl": {"price": lows["l"], "date": _date(lows["t"]), "dist_pct": round((lows["l"] / now - 1) * 100, 1)},
              "ath": {"price": highs["h"], "date": _date(highs["t"]), "dist_pct": round((highs["h"] / now - 1) * 100, 1)},
              "listing": {"price": days[0]["c"], "date": _date(days[0]["t"])}}
    return {"band_pct": round(bw * 100, 1), "dep_pct": round(dep * 100, 1), "levels": ordered,
            "points": points, "empty": empty, "price": now, "days": len(days)}


def build(sym: str) -> dict:
    days, src = load_daily(sym)
    res = compute(days)
    res.update({"sym": sym, "src": src, "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})
    return res


def write(res: dict) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    p = OUT_DIR / f"{res['sym']}.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def nearest(res: dict, side: str = "above", n: int = 2) -> list[dict]:
    """Ближайшие уровни сверху/снизу от цены сейчас — для экрана монеты и решений."""
    lv = [x for x in res.get("levels", []) if x["above"] == (side == "above")]
    lv.sort(key=lambda x: abs(x["dist_pct"]))
    return lv[:n]


def _print(res: dict) -> None:
    print(f"{res['sym']} · {res.get('src')} · дневок {res.get('days')} · цена {res.get('price')} "
          f"· полоса ±{res.get('band_pct')}% · ход {res.get('dep_pct')}%")
    p = res.get("points") or {}
    if p:
        print(f"  дно {p['atl']['price']} ({p['atl']['date']}, {p['atl']['dist_pct']:+}%) · "
              f"пик {p['ath']['price']} ({p['ath']['date']}, {p['ath']['dist_pct']:+}%) · листинг {p['listing']['price']}")
    for lv in sorted(res.get("levels", []), key=lambda x: -x["price"]):
        mark = "▲" if lv["above"] else "▼"
        print(f"  {mark} {lv['lo']:.6g}–{lv['hi']:.6g}  {lv['dist_pct']:+.1f}%  {lv['kind']:<12} дней {lv['days']:<3} "
              f"возвратов {lv['touches']}  {'проверена' if lv.get('tested') else 'в работе'}  "
              f"{lv['first']}…{lv['last']}  ранг {lv['rank']}  действие {lv['act']:.6g}"
              + ("  пробита вниз" if lv.get("broken_down") else ""))
    for a, b in res.get("empty", []):
        print(f"  … между {a:.6g} и {b:.6g} уровней нет")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="уровни из истории — проверка на одной монете")
    ap.add_argument("--only", required=True, help="символ, например ARBUSDT")
    ap.add_argument("--write", action="store_true", help="записать output/levels/<SYM>.json")
    a = ap.parse_args(argv)
    res = build(a.only.upper())
    _print(res)
    if a.write:
        print("→", write(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
