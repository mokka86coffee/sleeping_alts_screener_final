#!/usr/bin/env python3
"""ФОН РЫНКА — журнал признаков дня рядом с прогнозами (07.09, владелец: «нужно писать
дополнительно в журнал всё, что может быть фоном… максимально собрать закономерности,
тогда наш таймер по-настоящему заработает, а не будет казиношным»).

Зачем. Отбор кандидатов работает — 07.09 счётчик назвал DOOD до хода. Ломается порядок:
из шести хороших пошла одна, остальные отдали. Владелец: «проблема не в монетах, а в деньгах».
Значит, надо писать не только прогноз по монете, но и состояние доски в этот момент, чтобы
потом посчитать, при каком фоне прогнозы сбывались, а при каком нет.

ПРИЗНАКИ ВЛАДЕЛЬЦА (три названных):
  1. risk_on   — аппетит: доля растущих по доске (та же шкала 1..5, что в run.build_market_regime)
  2. btc       — биткоин: цена, ход за сутки и за час, интерес, тейкер
  3. время     — день недели, час UTC, какая сессия открыта, выходные
И ещё два, добавленные им же 07.09:
  4. streak    — сколько дней подряд монета росла: «1–2 дня роста → следующие 1–3 дня флэт или
                 слив: деньги пришли, об них закрылись, ждут новые»
  5. big_mover — сильный рост одной-двух: монета от +50% за день. Пишем её и что в этот момент
                 с остальной выборкой — чтобы проверить, забирает ли она деньги у прочих

МОИ ДОБАВКИ (07.09, на вопрос «может, ты сам ещё подскажешь»):
  6. concentration — доля лидера в приросте интереса и в дельте по всей доске. Прямой ответ на
                     «куда идут деньги»: если одна забирает больше трети — остальные не пойдут,
                     как бы хорошо ни выглядели (случаи BLESS против USELESS, ARB против ENA)
  7. breadth      — сколько монет РАСТЁТ и сколько НАБИРАЕТ интерес: пять из девяноста — узкий
                     рынок, деньги в одном месте; тридцать — размазано, ход будет вялым у всех
  8а. leader_flow — деньги лидера (11.09): снаружи (доска растёт с ним) / из соседей (доска стоит
      или падает, лидер растёт) / лидер отдаёт / нет лидера — по нашей же ленте за LEADER_FLOW_HOURS
  8. oi_total     — сумма интереса по доске: растёт — деньги приходят; стоит, а у одной растёт —
                     это перекладка из остальных, рост одной означает падение других
  9. funding_med  — медианный фандинг по доске: за плечо платят все или только одна монета
 10. taker        — СВОДНЫЙ ТЕЙКЕР ПО ДОСКЕ (07.09, владелец спросил, где его брать): кто бьёт по
                    стакану на рынке в целом. Складываем рыночные покупки и продажи по всем монетам
                    и делим одно на другое: выше единицы — агрессивнее покупают, ниже — продают.
                    Ленты 07.09 писали «поток лёг в шорт, 51.6% на продажу» — это то же число,
                    только чужое; своё считается из наших же баров и потому пересчитываемо.
                    Пишем за сутки (taker24 из среза) и за последний бар — разворот виден раньше.
 11. leader       — НАШ ЛИДЕР КАК ПРИЗНАК ФОНА (08.09, владелец: «нужно записывать в журнал, какой
                    лидер и в какое время шёл, чтобы это было таким же фоном, как биткоин»). За два
                    дня подтвердились ровно два признака фона: падение биткоина и наличие монеты с
                    сильным ходом. Пока одна тянет, остальные не идут: 07.09 SOPH +11.7% при медиане
                    +0.5%, 08.09 SOPH +104% при медиане +3.2% — вторые и третьи не дали ничего.
                    Пишем: кто ведёт, ход за день, во сколько раз оторвался от медианы наших,
                    сколько часов держится в первых, был ли конец. Это НАБЛЮДЕНИЕ: в решения и в
                    балл не входит, но режет журнал так же, как биткоин и сессия.
 12. leaders      — десятка лидеров дня ПО ВСЕЙ БИРЖЕ, а не по нашей доске (07.09, владелец
                    прислал список: MEME +137%, BONER +123%, NUDES, IOST, SOLV, PIEVERSE — обороты
                    по пятьсот-семьсот тысяч). Деньги не ушли с рынка, они ушли МИМО нашей выборки,
                    в свежие листинги и мемы, где хватает пары сотен тысяч на плюс сто процентов.
                    Пишем: сколько лидеров в нашей доске, сколько залистились меньше месяца назад,
                    их медианный оборот. Через неделю станет видно, сбывается ли у нас что-нибудь
                    в дни, когда лидеры дня — не наши и свежие

Пишет output/market_bg.jsonl — ОДНА строка на прогон: признаки доски + движения по всем
доступным монетам (sym, цена, ход за час и за сутки, интерес, дельта, дней роста подряд).
Ничего не решает и ни на что не влияет — только копит, чтобы через неделю считать
закономерности по числам, а не на глаз.

    python3 market_bg.py                 # печать без записи
    python3 market_bg.py --write         # строка в output/market_bg.jsonl
    python3 market_bg.py --only DOOD     # одна монета — проверка расчёта
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR, LEADER_FLOW_HOURS, LEADER_FLOW_BOARD_UP_PCT
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    LEADER_FLOW_HOURS, LEADER_FLOW_BOARD_UP_PCT = 6.0, 0.5
sys.path.insert(0, str(BASE_DIR))

ARCH = BASE_DIR / "cq_v2"
INTRA = ARCH / "intraday"
OUT = BASE_DIR / "output" / "market_bg.jsonl"
BIG_MOVE = 50.0          # «сильный рост одной-двух»: от +50% за день
STREAK_MIN = 0.03        # день считается растущим от +3%
LEADERS_N = 10           # сколько лидеров биржи писать
FRESH_DAYS = 30          # «свежий листинг» — первая свеча меньше месяца назад
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


# ── чтение ────────────────────────────────────────────────────────────────────
def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _today_rows(p: Path, day: str) -> list[dict]:
    """Бары монеты за сегодня из внутридневного архива (пустые — вон)."""
    rows = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if (r.get("candle") or "").startswith(day):
                rows.append(r)
    except OSError:
        return []
    return rows


def _streak(sym: str) -> int:
    """Сколько дней ПОДРЯД монета росла (последний закрытый день — первый в счёте).
    Признак владельца: после одного-двух дней роста чаще идёт флэт или слив."""
    d = _read(ARCH / f"{sym.replace('USDT', '').lower()}.json") or {}
    oh = d.get("ohlcv") or []
    if not oh:
        return 0
    oh = sorted(oh, key=lambda r: r.get("datetime") or "")
    n = 0
    for r in reversed(oh):
        try:
            o, c = float(r["open"]), float(r["close"])
        except (KeyError, TypeError, ValueError):
            break
        if o and (c / o - 1) >= STREAK_MIN:
            n += 1
        else:
            break
    return n


def _leaders(mine: set[str]) -> dict | None:
    """Десятка лидеров дня по всей бирже (суточный тикер Binance) и их возраст листинга.

    Наша доска — девяносто монет, а ход дня может целиком уйти в бумаги, которых у нас нет:
    07.09 первые строки биржи — MEME и BONER с плюс ста двадцатью и ста тридцатью при обороте
    в полмиллиона. Считаем, сколько лидеров наши и сколько из них свежие."""
    import urllib.request

    def _get(url: str):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None

    rows = _get("https://fapi.binance.com/fapi/v1/ticker/24hr")
    if not isinstance(rows, list):
        return None
    usdt = [r for r in rows if str(r.get("symbol", "")).endswith("USDT")]
    for r in usdt:
        try:
            r["_p"] = float(r.get("priceChangePercent") or 0)
            r["_q"] = float(r.get("quoteVolume") or 0)
        except (TypeError, ValueError):
            r["_p"], r["_q"] = 0.0, 0.0
    top = sorted(usdt, key=lambda r: -r["_p"])[:LEADERS_N]
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    out = []
    for r in top:
        sym = r["symbol"]
        age = None
        first = _get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1d&limit=1&startTime=0")
        if isinstance(first, list) and first:
            age = int((now_ms - int(first[0][0])) / 86400000)
        out.append({"sym": sym, "day_pct": round(r["_p"], 2), "vol_usd": round(r["_q"], 0),
                    "age_days": age, "mine": sym in mine})
    vols = [x["vol_usd"] for x in out if x["vol_usd"]]
    ages = [x["age_days"] for x in out if x["age_days"] is not None]
    return {"top": out, "n": len(out),
            "mine_n": sum(1 for x in out if x["mine"]),
            "fresh_n": sum(1 for x in out if (x["age_days"] is not None and x["age_days"] <= FRESH_DAYS)),
            "vol_med": round(statistics.median(vols), 0) if vols else None,
            "age_med": round(statistics.median(ages)) if ages else None}


# Лидер по пампу считается в analytics_leaders (правило владельца 09.09: +50% за сутки,
# оборот от MIN_QUOTE_VOLUME_24H, есть в кванте, листинг раньше полугода; основа фиксируется
# и не переставляется). Здесь только читаем готовый список — счёт и пороги живут там же, где
# остальные лидеры, а константы в core_config.


def _pump_list() -> list:
    try:
        from core_config import PUMP_LEADERS_PATH as _p
    except ImportError:
        _p = BASE_DIR / "output" / "pump_leaders.json"
    try:
        recs = json.loads(_p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    live = [r for r in recs.values() if isinstance(r, dict) and not r.get("retired_at")]
    return sorted(live, key=lambda x: -(x.get("run_pct") or 0))


# сессии в UTC: начало, конец. ЧАСЫ ПОПРАВЛЕНЫ 11.09 (владелец: слив IOST пошёл ровно на
# закрытии Нью-Йорка в 22:00 UTC, а США считались до 20:00 — журнал писал это как «сессии нет»):
# Токио 0–9, Лондон 7–16, Нью-Йорк 13–22. Сидней 21–6 не добавлен — на часах интро три дуги,
# четвёртая — вопрос к прототипу.
SESSIONS = (("Азия", 0.0, 9.0), ("Европа", 7.0, 16.0), ("США", 13.0, 22.0))
SOON_H = 1.0     # «скоро закроется» / «скоро откроется» — за час


def _chg_from_log(px_now, hours: float):
    """Ход биткоина за N часов — по нашей же ленте фона (08.09): в срезе btc_pulse его нет,
    там только изменение интереса. Берём ближайшую запись нужной давности с ценой BTC."""
    if not px_now:
        return None
    from datetime import datetime, timedelta, timezone
    try:
        lines = (BASE_DIR / "output" / "market_bg.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    want = datetime.now(timezone.utc) - timedelta(hours=hours)
    best, best_d = None, None
    for line in reversed(lines[-400:]):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        p = ((r.get("btc") or {}).get("px"))
        t = r.get("at")
        if not p or not t:
            continue
        try:
            ts = datetime.fromisoformat(str(t).replace("Z", "+00:00"))
        except ValueError:
            continue
        d = abs((ts - want).total_seconds())
        if best_d is None or d < best_d:
            best, best_d = p, d
    # ближе получаса к нужной отметке — иначе число будет врать
    if best and best_d is not None and best_d <= 1800 + hours * 60:
        return round((px_now / best - 1) * 100, 2)
    return None


def _first(*vals):
    """Первое непустое значение — чтобы срез имел приоритет, а доска была запасным вариантом."""
    for v in vals:
        if v is not None:
            return v
    return None


def _row_hours_ago(hours: float) -> dict | None:
    """Строка нашей же ленты нужной давности (ближайшая по времени, не дальше двух часов от неё)."""
    from datetime import datetime, timedelta, timezone
    try:
        lines = OUT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    want = datetime.now(timezone.utc) - timedelta(hours=hours)
    best, best_d = None, None
    for line in reversed(lines[-400:]):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        try:
            ts = datetime.fromisoformat(str(r.get("at")).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        d = abs((ts - want).total_seconds())
        if best_d is None or d < best_d:
            best, best_d = r, d
    if best is None or best_d > 2 * 3600:
        return None
    return best


def _leader_flow(oi_now: float, coins: list, leader_sym: str | None, hours: float) -> dict:
    """ДЕНЬГИ ЛИДЕРА (11.09): откуда он взял интерес за последние hours — доска целиком
    выросла (снаружи) или стояла/падала (из соседей). Считается по нашей же ленте: интерес доски
    и интерес лидера тогда против сейчас. Нет лидера — так и пишем."""
    out = {"state": "нет лидера", "sym": None, "hours": hours, "board_chg": None,
           "board_chg_pct": None, "leader_chg": None}
    if not leader_sym:
        return out
    out["sym"] = leader_sym
    prev = _row_hours_ago(hours)
    if not prev or not oi_now:
        out["state"] = "нет истории"
        return out
    tot0 = (prev.get("money") or {}).get("oi_total")
    cs0 = {c.get("sym"): c for c in prev.get("coins") or []}
    cs1 = {c.get("sym"): c for c in coins}
    l0, l1 = (cs0.get(leader_sym) or {}).get("oi"), (cs1.get(leader_sym) or {}).get("oi")
    if not tot0 or l0 is None or l1 is None:
        out["state"] = "нет истории"
        return out
    board_chg = oi_now - tot0
    board_pct = board_chg / tot0 * 100
    lead_chg = l1 - l0
    out.update({"board_chg": round(board_chg, 0), "board_chg_pct": round(board_pct, 2),
                "leader_chg": round(lead_chg, 0)})
    if lead_chg <= 0:
        out["state"] = "лидер отдаёт"
    elif board_pct >= LEADER_FLOW_BOARD_UP_PCT:
        out["state"] = "снаружи"
    else:
        out["state"] = "из соседей"
    return out


def _session(now: datetime) -> dict:
    """День недели, час UTC и что с рынками (07.09, владелец: «при заходе в часы показывать, какой
    рынок открыт, идёт, скоро закроется»). У каждой сессии — состояние и сколько часов осталось:
      открылась (первый час) · идёт · скоро закроется (последний час) · закрыта · скоро откроется."""
    h = now.hour + now.minute / 60
    out = []
    for name, a, b in SESSIONS:
        if a <= h < b:
            left = round(b - h, 1)
            state = "открылась" if h - a < SOON_H else ("скоро закроется" if left <= SOON_H else "идёт")
            out.append({"name": name, "state": state, "left_h": left, "open": True})
        else:
            to = (a - h) if h < a else (24 - h + a)
            out.append({"name": name, "state": "скоро откроется" if to <= SOON_H else "закрыта",
                        "in_h": round(to, 1), "open": False})
    live = [s["name"] for s in out if s["open"]]
    # ПЕРЕХОД МЕЖДУ СЕССИЯМИ (08.09, владелец: «межсессионье нужно заменить на то, от какой сессии
    # к какой переход»): когда открытых нет, пишем, какая закрылась последней и какая ближайшая
    # откроется, вместо безликого «межсессионье».
    gap = None
    if not live:
        nxt = min((s for s in out if not s["open"]), key=lambda s: s.get("in_h", 99))
        prev_name, prev_ago = None, 99.0
        for name, _a, b in SESSIONS:
            ago = (h - b) if h >= b else (24 - b + h)
            if ago < prev_ago:
                prev_ago, prev_name = ago, name
        gap = {"from": prev_name, "from_h": round(prev_ago, 1),
               "to": nxt["name"], "to_h": nxt.get("in_h")}
    return {"dow": now.strftime("%a"), "dow_n": now.isoweekday(), "hour_utc": now.hour,
            "weekend": now.isoweekday() >= 6, "gap": gap,
            "sessions": live or ["межсессионье"], "markets": out}


# ── сбор ──────────────────────────────────────────────────────────────────────
def _queue_groups() -> dict:
    """Кто сейчас в первых и в очереди (07.09, владелец: «здесь нам важны только наши первые и в
    очереди — закрытые и нейтральные монеты нас не интересуют: они ходят вместе с фоном»).
    Берём из output/near_move.json: первые три строки очереди — «первые», остальные — «в очереди»."""
    try:
        nm = json.loads((BASE_DIR / "output" / "near_move.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    q = nm.get("queue") or []
    return {sym: ("первые" if i < 3 else "в очереди") for i, sym in enumerate(q)}


def build(only: list[str] | None = None, now: datetime | None = None, leaders: bool = True) -> dict:
    now = now or datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    cg = (_read(BASE_DIR / "output" / "coinglass_fetch.json") or {}).get("coins") or {}
    files = sorted(INTRA.glob("*.jsonl"))
    if only:
        keep = {s.replace("USDT", "").lower() for s in only}
        files = [p for p in files if p.stem.lower() in keep]

    coins = []
    tb = ts = tb_bar = ts_bar = 0.0        # покупки и продажи по всей доске: за день и за последний бар
    for p in files:
        rows = _today_rows(p, day)
        if not rows:
            continue
        sym = (rows[-1].get("sym") or p.stem.upper() + "USDT")
        full = [r for r in rows if (r.get("fut") or {}).get("tk")]
        px = [r["px"] for r in rows if r.get("px")]
        oi = [r["oi"] for r in rows if r.get("oi")]
        if not px:
            continue
        d1h = None
        if len(px) >= 3:
            d1h = (px[-1] / px[-3] - 1) * 100
        c = cg.get(sym) or {}
        for r in full:
            f = r.get("fut") or {}
            tb += float(f.get("b") or 0)
            ts += float(f.get("s") or 0)
        if full:
            fl = full[-1].get("fut") or {}
            tb_bar += float(fl.get("b") or 0)
            ts_bar += float(fl.get("s") or 0)
        coins.append({
            "sym": sym, "px": px[-1],
            "day_pct": round((px[-1] / px[0] - 1) * 100, 2),
            "h1_pct": round(d1h, 2) if d1h is not None else None,
            "oi": oi[-1] if oi else None,
            "oi_day_pct": round((oi[-1] / oi[0] - 1) * 100, 2) if len(oi) >= 2 and oi[0] else None,
            "oi_add": (oi[-1] - oi[0]) if len(oi) >= 2 else None,
            "delta": round(sum(((r.get("fut") or {}).get("d") or 0) for r in full), 0),
            "funding": c.get("funding"),
            "streak_up": _streak(sym),
            "bars": len(rows), "skipped": len(rows) - len(full),
        })
    if not coins:
        return {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "note": "нет баров за сегодня"}

    # ── СЧЁТ ПО ГРУППАМ (07.09): по всей доске считаем только ширину (сколько растёт, сколько
    # падает) и сильный рост; всё остальное — отдельно по нашим первым и очереди, потому что
    # именно у них хороший фон даёт идеальный ход, а плохой — обратное.
    grp = _queue_groups()
    for c in coins:
        c["queue"] = grp.get(c["sym"])
    ours = [c for c in coins if c.get("queue")]
    first3 = [c for c in coins if c.get("queue") == "первые"]

    day_pcts = [c["day_pct"] for c in coins]
    green = sum(1 for x in day_pcts if x > 0)
    share = green / len(day_pcts)
    appetite = 5 if share > .65 else 4 if share > .55 else 3 if share > .45 else 2 if share > .35 else 1
    regime = "risk-on" if appetite >= 4 else "neutral" if appetite == 3 else "risk-off"

    # концентрация: чью долю забирает лидер в приросте интереса и в дельте по доске
    adds = [(c["sym"], c["oi_add"]) for c in coins if (c.get("oi_add") or 0) > 0]
    tot_add = sum(v for _, v in adds)
    lead_oi = max(adds, key=lambda kv: kv[1]) if adds else None
    dels = [(c["sym"], c["delta"]) for c in coins if (c.get("delta") or 0) > 0]
    tot_del = sum(v for _, v in dels)
    lead_d = max(dels, key=lambda kv: kv[1]) if dels else None

    # сильный рост одной-двух и что в этот момент с остальными
    big = sorted([c for c in coins if c["day_pct"] >= BIG_MOVE], key=lambda c: -c["day_pct"])[:2]
    rest = [c for c in coins if c not in big]
    big_block = None
    if big:
        rp = [c["day_pct"] for c in rest]
        big_block = {
            "syms": [{"sym": c["sym"], "day_pct": c["day_pct"],
                      "oi_day_pct": c["oi_day_pct"]} for c in big],
            "rest_n": len(rest),
            "rest_median_pct": round(statistics.median(rp), 2) if rp else None,
            "rest_green": sum(1 for x in rp if x > 0),
        }

    fundings = [c["funding"] for c in coins if c.get("funding") is not None]
    oi_now = sum(c["oi"] for c in coins if c.get("oi"))
    oi_add_total = sum(c["oi_add"] for c in coins if c.get("oi_add") is not None)

    # НАШ ЛИДЕР — из очереди и её же ходов за день
    our_lead = None
    if ours:
        _top = sorted(ours, key=lambda c: -(c.get("day_pct") or 0))
        _l = _top[0]
        _moves = sorted([c.get("day_pct") or 0 for c in ours])
        _med = _moves[len(_moves) // 2]
        _gap = (abs(_l["day_pct"]) / abs(_med)) if abs(_med) >= 0.3 else (abs(_l["day_pct"]) / 0.3 if _l["day_pct"] else 0)
        our_lead = {
            "sym": _l["sym"], "day_pct": _l["day_pct"], "oi_day_pct": _l.get("oi_day_pct"),
            "median_ours": round(_med, 2), "gap": round(_gap, 1),
            # тянет одна — только при ходе от 50% за день (08.09): монета с +7% не «тянет»,
            # она просто выше медианы; NAORIS полдня закрывал вход остальным без всякого хода
            # порог — ход от дна за 7 дней, а не за сутки (08.09): ход длится 2–3 дня и в сутки
            # не помещается; при отсутствии недельного числа берём суточное
            "run7": _l.get("run7"),
            "pulls": bool(_gap >= 5 and ((_l.get("run7") if _l.get("run7") is not None else (_l["day_pct"] or 0)) >= 50)),
            "queue": _l.get("queue"),
        }

    # ── ДЕНЬГИ НА ДОСКЕ (09.09) ────────────────────────────────────────────────────────────────
    # Владелец: медленные пузыри работают не всегда. Три-четыре месяца назад, когда деньги пришли
    # на доску, они дали ×5–10 по десяткам монет; сейчас, на дне, они есть почти у всех и ничего
    # не различают. Значит нужна мерка, КОГДА деньги на доске.
    # Измеримый след того эпизода: открытый интерес по альтам впервые с декабря 2024 стал выше
    # биткоиновского. У кванта на Advanced интереса по альтам нет — считаем своё: сумма интереса
    # по нашей доске к интересу биткоина. Само число мало значит (110 монет из тысяч), важен СДВИГ.
    # ВЕСЬ БЛОК ПОД ЗАЩИТОЙ (10.09): фон перестал писаться с 09.09 19:45 — ровно тогда, когда сюда
    # добавилась доля плеча альтов. Любая ошибка здесь роняла шаг целиком, и лента обрывалась.
    # Теперь сбой в этом счёте не мешает записать всё остальное.
    alt_share = {"alt_oi": None, "btc_oi": None, "ratio": None, "chg_24h": None}
    try:
        _alt_oi = sum((c.get("oi") or 0) for c in coins if not str(c.get("sym") or "").startswith("BTC"))
        _btc_oi = btc_block.get("oi") or 0
        alt_share = {"alt_oi": round(_alt_oi), "btc_oi": round(_btc_oi),
                     "ratio": round(_alt_oi / _btc_oi, 4) if _btc_oi else None, "chg_24h": None}
    except Exception:  # noqa: BLE001
        pass
    if alt_share.get("ratio"):
        try:
            _want = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M")
            _old = None
            for _l in OUT.read_text(encoding="utf-8").splitlines()[-400:]:
                try:
                    _r = json.loads(_l)
                except ValueError:
                    continue
                _rr = ((_r.get("alt_share") or {}).get("ratio"))
                if _rr and str(_r.get("at") or "")[:16] <= _want:
                    _old = _rr
            if _old:
                alt_share["chg_24h"] = round((alt_share["ratio"] / _old - 1) * 100, 1)
        except OSError:
            pass

    lead = _leaders({c["sym"] for c in coins}) if leaders else None
    # лидеры по пампу — по правилу владельца (+50% за сутки, оборот от $2M, есть в кванте,
    # листинг раньше полугода); основа фиксируется и не переставляется
    pumps = _pump_list()
    # деньги лидера: лидер — первый памп, иначе наш тянущий
    _lead_sym = None
    if pumps:
        _lead_sym = str(pumps[0].get("symbol") or pumps[0].get("sym") or "") or None
    elif our_lead and our_lead.get("pulls"):
        _lead_sym = our_lead.get("sym")
    leader_flow = _leader_flow(oi_now, coins, _lead_sym, LEADER_FLOW_HOURS)

    # БИТКОИН — ИЗ ГОТОВОГО СРЕЗА ШАГА «БИТКОИН» (08.09): в прогоне он собирается отдельным шагом
    # (btc_pulse) и всё там есть — цена, плечо, ликвидации, премия. А фон брал его из своей доски,
    # где BTC чаще всего просто нет, и писал прочерки: у владельца четыре прогона подряд в журнале
    # «биткоин за сутки —». Теперь сначала читаем срез, и только если его нет — считаем сами.
    btc = next((c for c in coins if c["sym"].startswith("BTC")), None)
    b = cg.get("BTCUSDT") or {}
    pulse = {}
    for name in ("btc_pulse.json", "btc.json"):
        for q in (BASE_DIR / "output" / name, BASE_DIR / name):
            if q.exists():
                try:
                    pulse = json.loads(q.read_text(encoding="utf-8")) or {}
                except (OSError, ValueError):
                    pulse = {}
                break
        if pulse:
            break
    # РАЗБОР СРЕЗА: цена и карта лежат в map, ликвидации в liq, премия в premium, фонды в etf.
    # ХОДА ЗА СУТКИ И ЗА ЧАС В СРЕЗЕ НЕТ ВОВСЕ (08.09) — там только изменение интереса. Считаем сами
    # по нашей же ленте фона: цена биткоина пишется каждый прогон, берём запись сутки и час назад.
    pm = (pulse.get("map") or {})
    pl = (pulse.get("liq") or {})
    ppr = (pulse.get("premium") or {})
    px_now = _first(pm.get("px"), pulse.get("px"), (btc or {}).get("px"), b.get("price"))
    # ход за сутки и за неделю — из того же рыночного среза, что кормит схему (09.09): там он уже
    # посчитан (btc24 / btc7d), ждать сутки собственной ленты не нужно
    mk = {}
    for nm in ("market.json", "flow.json", "market_now.json"):
        for q in (BASE_DIR / "output" / nm, BASE_DIR / nm):
            if q.exists():
                try:
                    mk = json.loads(q.read_text(encoding="utf-8")) or {}
                except (OSError, ValueError):
                    mk = {}
                break
        if mk.get("btc24") is not None or mk.get("btc7d") is not None:
            break
    day_pct = _first(mk.get("btc24"), (btc or {}).get("day_pct"), _chg_from_log(px_now, 24))
    h1_pct = _first((btc or {}).get("h1_pct"), _chg_from_log(px_now, 1))
    btc_block = {
        "px": px_now,
        "day_pct": day_pct, "h1_pct": h1_pct, "week_pct": mk.get("btc7d"),
        "oi": _first(pm.get("oi_usd"), (btc or {}).get("oi"), b.get("oiUsd")),
        "oi_day_pct": _first(pm.get("oi_chg24_pct"), (btc or {}).get("oi_day_pct"), b.get("oiChgPct")),
        "taker24": _first(pulse.get("taker24"), ((b.get("fut") or {}).get("taker"))),
        "liq_long": pl.get("long_24h_usd"), "liq_short": pl.get("short_24h_usd"),
        "premium": ppr.get("last"),
        "up_pct": ((pm.get("above") or {}).get("nearest") or {}).get("pct"),
        "dn_pct": ((pm.get("below") or {}).get("nearest") or {}).get("pct"),
        "short_to_long": pm.get("short_to_long_3pct"),
        "src": "срез" if pulse else "доска",
    }

    return {
        "at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "candle": now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0).strftime("%Y-%m-%dT%H:%M:00Z"),
        "time": _session(now),
        "risk_on": {"regime": regime, "appetite": appetite,
                    "green_share": round(share, 3), "green": green, "n": len(coins),
                    "median_pct": round(statistics.median(day_pcts), 2)},
        "btc": btc_block,
        "breadth": {"up": green, "down": len(coins) - green,
                    "oi_up": sum(1 for c in coins if (c.get("oi_day_pct") or 0) > 0),
                    "n": len(coins)},
        "taker": {
            "day": round(tb / ts, 3) if ts else None,
            "bar": round(tb_bar / ts_bar, 3) if ts_bar else None,
            "sell_share_pct": round(ts / (tb + ts) * 100, 1) if (tb + ts) else None,
            "buy_usd": round(tb, 0), "sell_usd": round(ts, 0),
            "side": ("покупают" if ts and tb / ts > 1.02 else "продают" if ts and tb / ts < 0.98 else "вровень"),
        },
        "money": {
            "oi_total": round(oi_now, 0) if oi_now else None,
            "oi_added": round(oi_add_total, 0),
            "leader_oi": lead_oi[0] if lead_oi else None,
            "leader_oi_share": round(lead_oi[1] / tot_add, 3) if lead_oi and tot_add else None,
            "leader_delta": lead_d[0] if lead_d else None,
            "leader_delta_share": round(lead_d[1] / tot_del, 3) if lead_d and tot_del else None,
            "funding_med": round(statistics.median(fundings), 5) if fundings else None,
            "leader_flow": leader_flow,
        },
        # наши: сколько растёт из скольких и медиана — отдельно по первым и по очереди
        "ours": {
            "n": len(ours), "up": sum(1 for c in ours if c["day_pct"] > 0),
            "median_pct": round(statistics.median([c["day_pct"] for c in ours]), 2) if ours else None,
            "first3": [{"sym": c["sym"], "day_pct": c["day_pct"], "oi_day_pct": c["oi_day_pct"]} for c in first3],
            "first3_up": sum(1 for c in first3 if c["day_pct"] > 0),
        },
        "leader": our_lead, "pumps": pumps,
        "alt_share": alt_share,
        "big_mover": big_block,
        "leaders": lead,
        "coins": sorted(coins, key=lambda c: -c["day_pct"]),
    }


def last_row() -> dict:
    """Последняя строка фона — для интро и сводки (07.09: тейкер по доске нужен и там, и там)."""
    try:
        lines = OUT.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    for line in reversed(lines):
        if line.strip():
            try:
                return json.loads(line)
            except ValueError:
                continue
    return {}


def bg_note(row: dict | None = None) -> list:
    """ФОН СТРОКАМИ, КАЖДЫЙ ПРИЗНАК ОТДЕЛЬНО (08.09, владелец: «сейчас в звёздах написано растёт
    столько и столько-то наших — опять непонятно, каких наших; а нужно писать всё по отдельности:
    фон по монетам — давит / нейтральный / рост, биткоин — падает / флэт / рост, и так далее»).

    Возвращает список строк вида (что, состояние, число). Ничего не решает и в балл не входит —
    только показывает. Каждый признак читается сам по себе, без оценочных слов вроде risk-on.
    """
    r = row if row is not None else last_row()
    if not r:
        return []
    out: list = []
    br = r.get("breadth") or {}
    if br.get("n"):
        share = br["up"] / br["n"]
        state = "давит" if share < 0.4 else ("рост" if share > 0.6 else "нейтральный")
        out.append(["монеты", state, f"растёт {br['up']} из {br['n']}"])
    # МЕДИАНА ПО ВСЕЙ ДОСКЕ (08.09, владелец: «общая медиана по всем монетам также определяет
    # полностью рынок»). Ширина говорит, сколько растёт, медиана — насколько; это разные вещи:
    # растёт половина, но медиана −1% значит, что растут по чуть-чуть, а падают сильно.
    med = ((r.get("risk_on") or {}).get("median_pct"))
    if med is not None:
        state = "падает" if med < -0.3 else ("рост" if med > 0.3 else "ровно")
        out.append(["медиана доски", state, f"{med:+.2f}% медиана хода"])
    # БИТКОИН — ДВЕ СТРОКИ: ЧТО СЕЙЧАС И ЧТО БУДЕТ (09.09, владелец: «мы тут должны иметь две вещи —
    # что будет и что сейчас»). Раньше они были слиты в одно слово, и «давит» читалось как оба сразу.
    # А это разные вещи: жечь могут лонгов, а вести всё равно вверх, если топливо наверху.
    #   СЕЙЧАС — свершившееся: интерес за сутки, кого жгут, покупает ли Америка;
    #   ДАЛЬШЕ — ожидание: где лежит топливо и до какой плиты ближе.
    b = r.get("btc") or {}
    now_votes, now_why = 0, []
    oi_d = b.get("oi_day_pct")
    if oi_d is not None:
        if oi_d <= -1:
            now_votes -= 1
            now_why.append(f"плечо уходит {oi_d:+.1f}%")
        elif oi_d >= 1:
            now_votes += 1
            now_why.append(f"плечо копится {oi_d:+.1f}%")
    ll, ls = b.get("liq_long"), b.get("liq_short")
    if ll and ls:
        if ll > ls * 1.5:
            now_votes -= 1
            now_why.append(f"жгут лонгов ×{ll / ls:.1f}")
        elif ls > ll * 1.5:
            now_votes += 1
            now_why.append(f"жгут шортов ×{ls / ll:.1f}")
    pr = b.get("premium")
    if pr is not None:
        if pr < -0.005:
            now_votes -= 1
            now_why.append("Америка не покупает")
        elif pr > 0.005:
            now_votes += 1
            now_why.append("Америка покупает")
    if now_why:
        out.append(["биткоин сейчас",
                    "давит" if now_votes <= -2 else ("тянет" if now_votes >= 2 else "ровно"),
                    " · ".join(now_why)])
    # ДАЛЬШЕ: куда есть смысл вести — топливо по сторонам и что ближе
    stl = b.get("short_to_long")
    up_p, dn_p = b.get("up_pct"), b.get("dn_pct")
    fut_why = []
    fut = None
    # ПУСТАЯ СТОРОНА — ЭТО СОСТОЯНИЕ, А НЕ СБОЙ (10.09). Полоса шортов в трёх процентах над ценой
    # бывает пустой, тогда short_to_long приходит нулём. Строка `1 / stl` роняла bg_note целиком
    # с ZeroDivisionError, render_intro глотал ошибку своим except — и панель приборов пропадала
    # с экрана вся, хотя лента фона писалась исправно. Обе крайности теперь называются словами.
    if stl is not None:
        if stl <= 0:
            fut = "вниз"
            fut_why.append("сверху топлива нет")
        elif stl == float("inf") or stl != stl:      # снизу пусто: деление уже дало бесконечность
            fut = "вверх"
            fut_why.append("снизу топлива нет")
        elif stl < 0.8:
            fut = "вниз"
            fut_why.append(f"топлива снизу ×{1 / stl:.1f}")
        elif stl > 1.25:
            fut = "вверх"
            fut_why.append(f"топлива сверху ×{stl:.1f}")
        else:
            fut = "поровну"
            fut_why.append("топливо поровну")
    if up_p is not None and dn_p is not None:
        fut_why.append(f"плита {up_p:+.1f}% / {dn_p:+.1f}%")
        if fut == "поровну":
            fut = "вниз" if abs(dn_p) < abs(up_p) else "вверх"
    if fut_why:
        out.append(["биткоин дальше", fut or "—", " · ".join(fut_why)])
    # ДЕНЬГИ НА ДОСКЕ (09.09): доля плеча альтов к биткоину и её сдвиг за сутки — мерка того,
    # когда деньги приходят на доску. Медленные пузыри оживают именно в такие периоды.
    al = r.get("alt_share") or {}
    if al.get("ratio"):
        ch = al.get("chg_24h")
        state = ("идут в альты" if (ch is not None and ch >= 3) else
                 "уходят в биткоин" if (ch is not None and ch <= -3) else "стоят")
        out.append(["деньги на доске", state,
                    f"плечо альтов ×{al['ratio']:.3f} к биткоину"
                    + (f" · {ch:+.1f}% за сутки" if ch is not None else " · сутки не набрались")])
    tk = r.get("taker") or {}
    if tk.get("day"):
        state = "продают" if tk["day"] < 0.98 else ("покупают" if tk["day"] > 1.02 else "вровень")
        # «поток рыночных заявок» (08.09, владелец): это тейкер — покупки по рынку против продаж
        # по рынку, в долларах; лимитные заявки сюда не входят
        out.append(["поток рыночных заявок", state, f"{tk['day']:.2f}"])
    # ПРИБОР «ОЧЕРЕДЬ» УБРАН (10.09, владелец): панель говорит о РЫНКЕ — доска, медиана, биткоин,
    # поток, деньги, лидер. Наша очередь — это не рынок, а наш отбор, и она видна на самом экране
    # звёздами и подписями групп. Числа по ней остаются в данных (ours), просто не рисуются.
    # ЛИДЕР ПОКАЗЫВАЕТСЯ, ТОЛЬКО ЕСЛИ ОН ЕСТЬ (09.09, владелец: «как PLAY попал в лидеры с ходом
    # +3.7%?»). Порог отрабатывал верно — PLAY его не проходил, — но строка всё равно печатала
    # верхнюю по ходу монету и приписывала рядом «без лидера». Читалось как «лидер PLAY».
    # Теперь без монеты: просто «лидера нет», и никакой тикер не мелькает.
    # ЛИДЕР ПО ПАМПУ ГЛАВНЕЕ (09.09): монета с +50% за сутки, прошедшая отсекатели, — это и есть
    # «куда пошли деньги», независимо от того, наша она или нет
    # ПАМП-ЛИДЕР НЕ ОБРЫВАЕТ СПИСОК (10.09): здесь стоял return, и при живом лидере панель теряла
    # последний прибор — циферблат торгов. Проверено запуском: с пампом семь приборов вместо восьми.
    # Памп по-прежнему главнее нашего лидера, просто вместо выхода из функции — ветка else.
    pm = (r.get("pumps") or [])
    if pm:
        p0 = pm[0]
        out.append(["лидер", "тянет одна" if len(pm) == 1 else f"тянут {len(pm)}",
                    f"{str(p0.get('symbol') or p0.get('sym') or '').replace('USDT', '')} "
                    f"+{p0.get('run_pct') or 0:.0f}% от основы"
                    + (" · наша" if p0.get("mine") else " · не из выборки")])
    else:
        ol = r.get("leader") or {}
        if ol.get("sym") and ol.get("pulls"):
            state = "тянет одна"
            run = ol.get("run7")
            out.append(["лидер", state,
                        f"{ol['sym'].replace('USDT', '')} "
                        + (f"+{run:.0f}% от дна недели" if run is not None else f"{ol['day_pct']:+.0f}% за сутки")
                        + f" · ×{ol['gap']} к медиане очереди"])
        else:
            out.append(["лидер", "нет", "ни одна не оторвалась от очереди"])
    # ДЕНЬГИ ЛИДЕРА (11.09): снаружи — доска растёт вместе с ним, соседи целы (SOPH 08.09);
    # из соседей — доска стоит или падает, лидер растёт — вынимают у вчерашних (IOST 09.09)
    lf = (r.get("money") or {}).get("leader_flow") or {}
    if lf.get("state") in ("снаружи", "из соседей", "лидер отдаёт"):
        out.append(["деньги лидера", lf["state"],
                    f"{str(lf.get('sym') or '').replace('USDT', '')} {(lf.get('leader_chg') or 0) / 1e6:+.0f}M · "
                    f"доска {(lf.get('board_chg') or 0) / 1e6:+.0f}M за {lf.get('hours'):.0f} ч"])
    tm = r.get("time") or {}
    live = [m for m in (tm.get("markets") or []) if m.get("open")]
    if live:
        out.append(["торги", live[0].get("state") or "идут",
                    ", ".join(m["name"] for m in live)])
    elif tm.get("gap"):
        g = tm["gap"]
        out.append(["торги", f"{g['from']} → {g['to']}",
                    f"{g['from']} закрылась {g['from_h']} ч назад · {g['to']} через {g['to_h']} ч"])
    elif tm.get("markets"):
        out.append(["торги", "все закрыты", ""])
    return out


def bg_line(row: dict | None = None) -> str:
    """То же одной строкой — для мест, где список не помещается."""
    return " · ".join(f"{a} {b}" for a, b, _c in bg_note(row))


def taker_line(row: dict | None = None) -> str:
    """Готовая строка про поток для сводки и первого экрана: «поток рыночных заявок 0.94 — продают,
    52% потока; последний бар 1.03 — разворот». Пусто, если фон ещё не собран."""
    r = row if row is not None else last_row()
    tk = (r or {}).get("taker") or {}
    d, b = tk.get("day"), tk.get("bar")
    if not d:
        return ""
    out = f"поток рыночных заявок {d:.2f} — {tk.get('side')}"
    if tk.get("sell_share_pct") is not None:
        out += f", продаж {tk['sell_share_pct']:.0f}% потока"
    if b:
        turn = (d > 1 and b < 0.98) or (d < 1 and b > 1.02)
        out += f"; последний бар {b:.2f}" + (" — разворот" if turn else "")
    return out


def write(res: dict) -> Path:
    """Пишет срез фона в ленту. ВМЕСТЕ С СОСТОЯНИЯМИ ПАНЕЛИ (09.09, владелец: «убедись, что мы
    пишем в журнал каждый прогон текущее состояние всех индикаторов на боковой панели»).

    Сырые числа писались и раньше, а состояния считались на лету при показе — значит журнал их
    не видел и не мог по ним фильтровать. Теперь одна и та же величина в трёх ролях: пишется в
    ленту, служит кнопкой в журнале и показывается сводкой. Расчёт один — bg_note, поэтому
    сводка и фильтр разойтись не могут. Сырое при этом остаётся нетронутым: состояния лежат
    ОТДЕЛЬНЫМ полем, поверх, и в любой момент их можно пересчитать иначе."""
    if "panel" not in res:
        try:
            res = dict(res)
            res["panel"] = [[a, b, c] for a, b, c in bg_note(res)]
        except Exception:  # noqa: BLE001
            res["panel"] = []
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a", encoding="utf-8") as f:
        f.write(json.dumps(res, ensure_ascii=False) + "\n")
    return OUT


def _print(r: dict) -> None:
    if r.get("note"):
        print(r["note"])
        return
    t, ro, br, mo, b = r["time"], r["risk_on"], r["breadth"], r["money"], r["btc"]
    print(f"{r['at']} · {t['dow']} {t['hour_utc']}:00 UTC" + (" · выходные" if t["weekend"] else ""))
    print("рынки: " + " · ".join(
        f"{s['name']} {s['state']}" + (f", ещё {s['left_h']} ч" if s.get("open") else
                                       (f", через {s['in_h']} ч" if s["state"] == "скоро откроется" else ""))
        for s in t.get("markets", [])))
    print(f"risk on: {ro['regime']} · аппетит {ro['appetite']}/5 · растёт {ro['green']} из {ro['n']} "
          f"({ro['green_share']*100:.0f}%) · медиана {ro['median_pct']:+.2f}%")
    if b.get("px"):
        print(f"биткоин: {b['px']} · за сутки {b.get('day_pct')} · за час {b.get('h1_pct')} · тейкер {b.get('taker24')}")
    else:
        print("биткоин: нет в выборке")
    print(f"ширина: цена вверх {br['up']}/{br['n']} · интерес вверх {br['oi_up']}/{br['n']}")
    ou = r.get("ours") or {}
    if ou.get("n"):
        print(f"наши: растёт {ou['up']} из {ou['n']} · медиана {ou['median_pct']:+.2f}% · "
              f"первые три: {ou['first3_up']} из {len(ou['first3'])} в плюсе"
              + (" · " + " · ".join(f"{x['sym'].replace('USDT','')} {x['day_pct']:+.1f}%" for x in ou["first3"]) if ou["first3"] else ""))
    tk = r.get("taker") or {}
    if tk.get("day"):
        print(f"тейкер по доске: за день {tk['day']} · последний бар {tk['bar']} · "
              f"{tk['side']} · продаж {tk['sell_share_pct']}% потока")
    print(f"деньги: интерес по доске {(mo['oi_total'] or 0)/1e6:.0f}M, прирост {(mo['oi_added'] or 0)/1e6:+.1f}M · "
          f"лидер прироста {mo['leader_oi']} доля {(mo['leader_oi_share'] or 0)*100:.0f}% · "
          f"лидер дельты {mo['leader_delta']} доля {(mo['leader_delta_share'] or 0)*100:.0f}% · "
          f"фандинг медиана {mo['funding_med']}")
    ld = r.get("leaders")
    if ld:
        print(f"лидеры биржи: наших {ld['mine_n']} из {ld['n']} · свежих (до {FRESH_DAYS} дн) {ld['fresh_n']} · "
              f"оборот медиана {(ld['vol_med'] or 0)/1e6:.2f}M · возраст медиана {ld['age_med']} дн")
        for x in ld["top"][:5]:
            print(f"   {x['sym'].replace('USDT',''):12s} {x['day_pct']:+7.1f}% · оборот {(x['vol_usd'] or 0)/1e6:6.2f}M · "
                  f"листингу {x['age_days']} дн{' · наша' if x['mine'] else ''}")
    ol = r.get("leader")
    if ol:
        print(f"наш лидер: {ol['sym'].replace('USDT','')} {ol['day_pct']:+.1f}% · медиана наших {ol['median_ours']:+.1f}% · "
              f"разрыв ×{ol['gap']}" + (" · ТЯНЕТ ОДНА" if ol["pulls"] else ""))
    if r.get("big_mover"):
        bm = r["big_mover"]
        for s in bm["syms"]:
            print(f"сильный рост: {s['sym']} {s['day_pct']:+.1f}% (интерес {s['oi_day_pct']})")
        print(f"  остальные {bm['rest_n']}: медиана {bm['rest_median_pct']:+.2f}%, растёт {bm['rest_green']}")
    print("\nмонеты:")
    for c in r["coins"]:
        print(f"  {c['sym'].replace('USDT',''):8s} {c['px']:>10.6f} день {c['day_pct']:+6.2f}% "
              f"час {str(c['h1_pct']) + '%':>8s} интерес {str(c['oi_day_pct']) + '%':>8s} "
              f"дельта {(c['delta'] or 0)/1e3:+8.0f}K подряд роста {c['streak_up']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="фон рынка рядом с прогнозами")
    ap.add_argument("--only", help="монеты через запятую")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--no-leaders", action="store_true", help="без запроса к Binance (быстро, офлайн)")
    a = ap.parse_args()
    res = build([x.strip() for x in a.only.split(",")] if a.only else None, leaders=not a.no_leaders)
    _print(res)
    if a.write and not res.get("note"):
        print("\n→", write(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
