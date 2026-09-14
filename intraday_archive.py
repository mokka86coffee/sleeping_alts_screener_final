#!/usr/bin/env python3
"""Внутридневной архив (05.09, владелец: «писать рядом с квантом данные внутри дня,
которые уже собираем, и смотреть»): `cq_v2/intraday/<база>.jsonl` — ОДНА строка на
закрытую получасовку по каждой монете журнала. Ничего нового не считает — только
перестаёт терять то, что прогон уже собрал и перезаписал бы следующим срезом.

В строке (всё, чего нет, — null; список `missing` говорит, чего именно):
  candle, sym, px                         — свеча (UTC, начало), пара, закрытие бара
  h, l, o                                 — размах и открытие бара (свеча Binance, 11.09; нет — missing: hl)
  fut: {b, s, d, tk}                      — перп за бар: покупки, продажи, дельта, тейкер бара
  spot: {b, s, d, tk}                     — спот за бар (у перповых монет null)
  oi, oi_chg_pct                          — интерес $ и его ход за сутки (срез)
  funding, taker24, delta24               — фандинг, тейкер и дельта за сутки (срез)
  liq24: {long, short}                    — ликвидации за сутки по сторонам
  oi_type                                 — тип часа по плечу: long_open / short_open / short_close / long_close / flat
  plot, stage                             — шаблон и стадия репутации на эту свечу
  zones: {up: [[цена, вес]×3], down: [...]} — три плотнейшие полосы карты на сторону
  missing                                 — чего не было в источниках

Читатели: разбор «что стояло за сутки до хода» по монетам, которые пошли (4, ARB), и
по тем, кто не пошёл. Запуск — из прогона после сбора Coinglass и быстрых срезов;
руками: `python3 intraday_archive.py --only 4` (одна монета, печать без записи) или
`--write`. Свеча уже в файле — не дублируется. Дозабор простоя пишет сюда же через
`--candle` (штамп свечи в ISO).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

OUT_DIR = BASE_DIR / "cq_v2" / "intraday"
try:
    from core_config import ARCHIVE_FILL_BACK_BARS, ARCHIVE_HEALTH_HOURS, ARCHIVE_MIN_COVER_PCT
except ImportError:
    ARCHIVE_FILL_BACK_BARS, ARCHIVE_HEALTH_HOURS, ARCHIVE_MIN_COVER_PCT = 6, 24, 90


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _last_jsonl_by_sym(path: Path, key: str = "sym") -> dict:
    """Последняя строка по каждой монете из jsonl (лог ликвидности)."""
    out: dict = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        s = str(r.get(key) or "").upper()
        if s:
            out[s] = r
    return out


def _bar_at(series: list, candle_ms: int) -> dict | None:
    for b in series or []:
        t = b.get("t")
        try:
            t = int(t)
        except (TypeError, ValueError):
            continue
        if t < 1e12:
            t *= 1000
        if t == candle_ms:
            return b
    return None


def _legs(bar: dict | None) -> dict | None:
    if not bar:
        return None
    b, s = bar.get("b"), bar.get("s")
    if b is None and s is None:
        return None
    b, s = float(b or 0), float(s or 0)
    return {"b": round(b, 0), "s": round(s, 0), "d": round(b - s, 0), "tk": round(b / s, 3) if s else None}


def _top3(zones: list, above: bool, px: float) -> list:
    zs = [z for z in zones or [] if z.get("price") and ((z["price"] > px) if above else (z["price"] <= px))]
    zs.sort(key=lambda z: -(z.get("usd") or z.get("weight") or 0))
    return [[round(float(z["price"]), 8), round(float(z.get("usd") or z.get("weight") or 0), 2)] for z in zs[:3]]


def snapshot_candle(cg: dict) -> tuple[int | None, str | None]:
    """Свеча, к которой ОТНОСИТСЯ срез Coinglass, и причина, если он не снят (07.09).

    Раньше штамп брался из candle_gate.boundary() в момент записи, а данные — из среза,
    который мог остаться от прошлой свечи (калитка не дождалась бара). Тогда ноги по времени
    не совпадали (fut/spot пустые, missing: fut_bar), а интерес, фандинг, ликвидации, тип бара
    и шаблон писались из прошлой свечи под именем текущей — так вышло 07.09 в 09:00 у всех
    монет разом. Теперь имя строки берётся у самого среза."""
    st = cg.get("stamp") or {}
    c = st.get("candle")
    ms = None
    if isinstance(c, (int, float)):
        ms = int(c if c > 1e12 else c * 1000)
    elif isinstance(c, str) and c:
        from datetime import datetime, timezone
        try:
            d = datetime.fromisoformat(c.replace("Z", "+00:00"))
            ms = int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp() * 1000)
        except ValueError:
            ms = None
    return ms, (str(st.get("why") or st.get("missing") or "") or None) if st.get("missing") else None


def build_rows(candle_ms: int, only: list[str] | None = None, cg_ok: bool = True, cg_why: str | None = None) -> list[dict]:
    """cg_ok=False (14.09 вечер): срез Coinglass не снят — раньше строка НЕ ПИСАЛАСЬ ВООБЩЕ, и в архиве
    ARK за 14.09 пропали двенадцать часов ровно на пике (28 баров из 54). Правило 07.09 «не подписывать
    прошлый срез именем текущей свечи» остаётся: поля Coinglass (ноги, интерес, фандинг, ликвидации) в
    такой строке null и в missing стоит «coinglass: <почему>». А свеча Binance — размах, открытие,
    закрытие, объём — своя, свежая, и пишется: вортексу и клингеру нужна именно она."""
    cg = (_read(BASE_DIR / "output" / "coinglass_fetch.json") or {}) if cg_ok else {}
    coins = cg.get("coins") or {}
    # список монет без среза — из журнала лидеров и очереди, чтобы дыра не расползлась на всех
    if not cg_ok and not only:
        syms_set: set = set()
        for name in ("leaders.json", "pump_leaders.json"):
            for k in (_read(BASE_DIR / "output" / name) or {}).keys():
                if not str(k).startswith("_"):
                    syms_set.add(str(k).upper())
        for k in ((_read(BASE_DIR / "output" / "near_move.json") or {}).get("coins") or {}).keys():
            syms_set.add(str(k).upper())
        coins = {k: {} for k in syms_set}
    rep = _read(BASE_DIR / "output" / "reputation.json") or {}
    pulse = _read(BASE_DIR / "pulse.json") or {}
    oit = (_read(BASE_DIR / "output" / "oi_types.json") or {}).get("coins") or {}
    liq_last = _last_jsonl_by_sym(BASE_DIR / "output" / "liq_log.jsonl")
    candle = __import__("time").strftime("%Y-%m-%dT%H:%M:00Z", __import__("time").gmtime(candle_ms / 1000))
    rows = []
    syms = only or sorted(coins.keys())
    for sym in syms:
        sym = sym.upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        c = coins.get(sym) or coins.get(sym.replace("USDT", "")) or {}
        missing: list[str] = list(c.get("missing") or [])
        fut = _legs(_bar_at((c.get("fut") or {}).get("series") or [], candle_ms))
        spot = _legs(_bar_at((c.get("spot") or {}).get("series") or [], candle_ms))
        if not cg_ok:
            missing.append("coinglass: " + (cg_why or "срез не снят"))
        elif fut is None and "fut" not in missing:
            missing.append("fut_bar")
        # тип часа по плечу — час, в который попадает свеча
        oi_type = None
        hours = (oit.get(sym) or {}).get("hours") or []
        hour_ms = (candle_ms // 3600000) * 3600000
        for h in hours:
            if int(h[0]) == hour_ms or int(h[0]) == hour_ms + 3600000:
                oi_type = h[1]
                break
        if oi_type is None and hours:
            missing.append("oi_type")
        r = rep.get(sym) or rep.get(sym.replace("USDT", "")) or {}
        lq = liq_last.get(sym.replace("USDT", "")) or {}
        # ЦЕНА БАРА — ИЗ ПУЛЬСА (06.09, найдено на ENA: во всех строках стояло закрытие
        # дневки): последняя точка пульса не позже конца свечи; нет — цена бара Coinglass;
        # нет — из лога. Дневка — последней, с пометкой в missing.
        px = None
        pr = [q for q in (pulse.get(sym) or []) if q.get("price") and (q.get("t") or 0) * 1000 <= candle_ms + 1800000 + 60000]
        if pr:
            pr.sort(key=lambda q: q.get("t") or 0)
            px = float(pr[-1]["price"])
        # МАКСИМУМ, МИНИМУМ И ОТКРЫТИЕ БАРА — У BINANCE (11.09). Первая версия брала их из
        # бара серии Coinglass по ключам h/l/o, но в той серии их нет: проверено 11.09 на IOST,
        # ключи бара t, tk, b, s, cvd — покупки, продажи, тейкер, накопленная дельта. Три
        # прогона размах писался null, и missing молчал. Теперь свеча с тем же временем
        # открытия берётся у биржи через core_binance (вес запроса один); нет свечи — в
        # missing пишется hl, чтобы пустой размах не был тихим. Цена (px) как была.
        bar = _bar_at((c.get("fut") or {}).get("series") or [], candle_ms)
        hi = lo = op = None
        kv = None          # объём свечи Binance (14.09 вечер): клингеру без среза Coinglass нужен хоть какой-то объём
        k_close = None
        try:
            import core_binance as _cb
            from core_binance import K_HIGH, K_LOW, K_OPEN, K_OPEN_TIME, klines_30m_last
            _K_CLOSE = getattr(_cb, "K_CLOSE", 4)
            _K_VOL = getattr(_cb, "K_VOLUME", 5)
            _K_QVOL = getattr(_cb, "K_QUOTE_VOLUME", 7)
            for k in klines_30m_last(sym):
                if int(k[K_OPEN_TIME]) == candle_ms:
                    hi, lo, op = float(k[K_HIGH]), float(k[K_LOW]), float(k[K_OPEN])
                    # закрытие и объём — ОТДЕЛЬНО и по длине свечи: первая версия брала их в той же
                    # строке, и если свеча core_binance короче стандартной, IndexError ронял и h/l
                    # (14.09 17:00: у всех 126 монет h/l null, missing: hl — при живом срезе)
                    try:
                        if len(k) > _K_CLOSE:
                            k_close = float(k[_K_CLOSE])
                        if len(k) > _K_QVOL:
                            kv = {"v": round(float(k[_K_VOL]), 0), "qv": round(float(k[_K_QVOL]), 0)}
                        elif len(k) > _K_VOL:
                            kv = {"v": round(float(k[_K_VOL]), 0), "qv": None}
                    except (TypeError, ValueError, IndexError):
                        k_close, kv = None, None
                    break
        except Exception:  # noqa: BLE001 — сеть не должна ронять архив, только помечать
            hi = lo = op = None
        if hi is None or lo is None:
            missing.append("hl")
        if px is None:
            if bar and bar.get("c"):
                px = float(bar["c"])
        if px is None and k_close is not None:
            px = k_close                     # закрытие свечи биржи — раньше дневки (14.09 вечер)
        if px is None:
            for cand in (lq.get("px"), r.get("px"), r.get("close")):
                if cand:
                    px = float(cand)
                    missing.append("px_daily")
                    break
        zones = None
        if lq and px:
            zh = lq.get("zones_hour") or lq.get("zones_day") or []
            zones = {"up": _top3(zh, True, px), "down": _top3(zh, False, px)}
        elif lq:
            missing.append("zones")
        rows.append({
            "candle": candle, "sym": sym, "px": px,
            "h": hi, "l": lo, "o": op,          # размах бара — для вортекса и Klinger (11.09)
            "kv": kv,                            # объём свечи Binance: базовый и в долларах (14.09 вечер)
            "fut": fut, "spot": spot,
            "oi": c.get("oiUsd"), "oi_chg_pct": c.get("oiChgPct"),
            "funding": c.get("funding"),
            "taker24": (c.get("fut") or {}).get("taker"),
            "delta24": (round(((c.get("fut") or {}).get("buyUsd") or 0) - ((c.get("fut") or {}).get("sellUsd") or 0), 0)
                        if c.get("fut") else None),
            "liq24": {"long": (c.get("liq") or {}).get("long24h"), "short": (c.get("liq") or {}).get("short24h")} if c.get("liq") else None,
            "oi_type": oi_type,
            "plot": (r.get("plot") or "").split("(")[0].strip() or None, "stage": r.get("stage"),
            "zones": zones,
            "missing": missing,
        })
    return rows


def write_rows(rows: list[dict], refill: bool = False) -> int:
    """refill (07.09): строка на эту свечу уже есть, но НЕПОЛНАЯ, а новая полнее — заменить.
    Без этого пустой бар оставался в архиве навсегда: дозабор видел штамп и молча пропускал."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for r in rows:
        base = r["sym"].replace("USDT", "").lower()
        p = OUT_DIR / f"{base}.jsonl"
        if p.exists():
            tail = p.read_text(encoding="utf-8")[-4000:]
            if f'"candle": "{r["candle"]}"' in tail:
                if not refill:
                    continue   # свеча уже записана
                lines = p.read_text(encoding="utf-8").splitlines()
                idx = None
                for i in range(len(lines) - 1, -1, -1):
                    try:
                        old = json.loads(lines[i])
                    except ValueError:
                        continue
                    if old.get("candle") == r["candle"]:
                        idx = i
                        break
                if idx is None:
                    continue
                old = json.loads(lines[idx])
                if len(r.get("missing") or []) >= len(old.get("missing") or []):
                    continue   # новая не полнее — не трогаем
                lines[idx] = json.dumps(r, ensure_ascii=False)
                p.write_text("\n".join(lines) + "\n", encoding="utf-8")
                n += 1
                continue
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        n += 1
    return n


def _journal_syms() -> list[str]:
    """Монеты, по которым архив обязан быть полным: журнал лидеров, лидеры по пампу, очередь."""
    out: set = set()
    for name in ("leaders.json", "pump_leaders.json"):
        for k in (_read(BASE_DIR / "output" / name) or {}).keys():
            if not str(k).startswith("_"):
                out.add(str(k).upper())
    for k in ((_read(BASE_DIR / "output" / "near_move.json") or {}).get("coins") or {}).keys():
        out.add(str(k).upper())
    return sorted(out)


def _candle_ms(c: str) -> int:
    from datetime import datetime, timezone
    d = datetime.fromisoformat(str(c).replace("Z", "+00:00"))
    return int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp() * 1000)


def _load_rows(p: Path) -> list[str]:
    try:
        return p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []


def fill_missing(syms: list[str] | None = None, back: int = ARCHIVE_FILL_BACK_BARS, write: bool = True) -> dict:
    """ДОЛИВ ТОГО, ЧЕГО НЕ БЫЛО (14.09 ночь, владелец: «автоматические проверки и заполнение того, что не было
    получено»). Свежая строка пишется, когда её свеча на бирже ещё открыта, — размаха нет (`missing: hl`),
    и без долива он не появлялся никогда; строки без среза Coinglass стоят без ног бара. Здесь по каждой
    монете берутся последние `back` строк и ДОЛИВАЮТСЯ ТОЛЬКО ПОЛЯ, которые относятся к тому же бару:
    h/l/o/kv — из закрытой свечи биржи, fut/spot — из бара серии Coinglass с тем же временем. Поля среза
    (интерес, фандинг, ликвидации за сутки) НЕ трогаются: они снимались в другой момент, подписывать их
    старым баром нельзя (правило 07.09). Возвращает {sym: {"hl": n, "legs": n}} по тому, что долито."""
    cg = _read(BASE_DIR / "output" / "coinglass_fetch.json") or {}
    coins = cg.get("coins") or {}
    try:
        import core_binance as _cb
        from core_binance import K_HIGH, K_LOW, K_OPEN, K_OPEN_TIME, klines_30m_last
        _K_CLOSE, _K_VOL, _K_QVOL = getattr(_cb, "K_CLOSE", 4), getattr(_cb, "K_VOLUME", 5), getattr(_cb, "K_QUOTE_VOLUME", 7)
    except Exception:  # noqa: BLE001
        klines_30m_last = None  # type: ignore[assignment]
    report: dict = {}
    for sym in (syms or _journal_syms()):
        sym = sym.upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        p = OUT_DIR / f"{sym.replace('USDT', '').lower()}.jsonl"
        lines = _load_rows(p)
        if not lines:
            continue
        need = []
        for i in range(len(lines) - 1, max(-1, len(lines) - 1 - back), -1):
            try:
                r = json.loads(lines[i])
            except ValueError:
                continue
            miss = r.get("missing") or []
            if "hl" in miss or r.get("fut") is None:
                need.append((i, r))
        if not need:
            continue
        ks = {}
        if klines_30m_last is not None and any("hl" in (r.get("missing") or []) for _, r in need):
            try:
                for k in klines_30m_last(sym):
                    ks[int(k[K_OPEN_TIME])] = k
            except Exception:  # noqa: BLE001
                ks = {}
        c = coins.get(sym) or coins.get(sym.replace("USDT", "")) or {}
        series = (c.get("fut") or {}).get("series") or []
        sseries = (c.get("spot") or {}).get("series") or []
        n_hl = n_legs = 0
        for i, r in need:
            ms = _candle_ms(r["candle"])
            miss = list(r.get("missing") or [])
            k = ks.get(ms)
            if k is not None and "hl" in miss:
                r["h"], r["l"], r["o"] = float(k[K_HIGH]), float(k[K_LOW]), float(k[K_OPEN])
                if len(k) > _K_QVOL:
                    r["kv"] = {"v": round(float(k[_K_VOL]), 0), "qv": round(float(k[_K_QVOL]), 0)}
                if r.get("px") is None and len(k) > _K_CLOSE:
                    r["px"] = float(k[_K_CLOSE])
                miss = [m for m in miss if m != "hl"]
                n_hl += 1
            if r.get("fut") is None:
                legs = _legs(_bar_at(series, ms))
                if legs is not None:
                    r["fut"] = legs
                    r["spot"] = _legs(_bar_at(sseries, ms))
                    miss = [m for m in miss if m != "fut_bar"]
                    n_legs += 1
            r["missing"] = miss
            lines[i] = json.dumps(r, ensure_ascii=False)
        if (n_hl or n_legs) and write:
            p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        if n_hl or n_legs:
            report[sym] = {"hl": n_hl, "legs": n_legs}
    return report


def health(syms: list[str] | None = None, hours: int = ARCHIVE_HEALTH_HOURS) -> dict:
    """ПРОВЕРКА АРХИВА (14.09 ночь): по монетам журнала — сколько закрытых свечей за `hours` есть, сколько
    должно быть, где дыры, сколько строк без размаха и без среза. Ничего не чинит — считает и отдаёт;
    прогон печатает это в лог и в реестр сбоев, если покрытие ниже ARCHIVE_MIN_COVER_PCT."""
    import time as _time
    now = int(_time.time() * 1000)
    last_closed = (now // 1800000) * 1800000 - 1800000
    since = last_closed - hours * 3600000
    expected = hours * 2
    out: dict = {"hours": hours, "expected": expected, "coins": {}, "bad": [], "worst": None}
    for sym in (syms or _journal_syms()):
        sym = sym.upper()
        if not sym.endswith("USDT"):
            sym += "USDT"
        p = OUT_DIR / f"{sym.replace('USDT', '').lower()}.jsonl"
        ts, no_hl, no_cg = [], 0, 0
        for line in _load_rows(p):
            try:
                r = json.loads(line)
            except ValueError:
                continue
            try:
                ms = _candle_ms(r["candle"])
            except (KeyError, ValueError):
                continue
            if since < ms <= last_closed:
                ts.append(ms)
                miss = r.get("missing") or []
                no_hl += "hl" in miss
                no_cg += any(str(m).startswith("coinglass") for m in miss)
        ts = sorted(set(ts))
        holes = []
        for a, b in zip(ts, ts[1:]):
            if b - a > 1800000:
                holes.append([a, b, int((b - a) // 1800000) - 1])
        cover = round(100 * len(ts) / expected, 1) if expected else 0
        row = {"have": len(ts), "cover_pct": cover, "holes": len(holes), "missing_bars": sum(h[2] for h in holes),
               "no_hl": no_hl, "no_coinglass": no_cg,
               "last": __import__("time").strftime("%Y-%m-%dT%H:%M:00Z", __import__("time").gmtime(ts[-1] / 1000)) if ts else None}
        out["coins"][sym] = row
        if cover < ARCHIVE_MIN_COVER_PCT:
            out["bad"].append(sym)
        if out["worst"] is None or cover < out["coins"][out["worst"]]["cover_pct"]:
            out["worst"] = sym
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="монеты через запятую")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--candle", help="свеча ISO (для дозабора); по умолчанию — из штампа среза")
    ap.add_argument("--refill", action="store_true", help="заменить неполную строку на более полную")
    ap.add_argument("--force", action="store_true", help="писать, даже если срез не снят")
    ap.add_argument("--fill", action="store_true", help="долить размах и ноги бара в последние строки (только свои поля бара)")
    ap.add_argument("--health", action="store_true", help="проверка покрытия за сутки по монетам журнала, json одной строкой")
    a = ap.parse_args()
    if a.fill or a.health:
        syms = [x.strip() for x in a.only.split(",")] if a.only else None
        if a.fill:
            rep_ = fill_missing(syms, write=True)
            print("intraday --fill: " + (", ".join(f"{k} hl+{v['hl']} legs+{v['legs']}" for k, v in rep_.items()) or "долить нечего"))
        if a.health:
            h = health(syms)
            print("intraday --health: " + json.dumps(
                {"expected": h["expected"], "coins": len(h["coins"]), "bad": h["bad"],
                 "worst": h["worst"], "worst_cover_pct": (h["coins"].get(h["worst"]) or {}).get("cover_pct"),
                 "no_hl": sum(v["no_hl"] for v in h["coins"].values()),
                 "no_coinglass": sum(v["no_coinglass"] for v in h["coins"].values()),
                 "missing_bars": sum(v["missing_bars"] for v in h["coins"].values())}, ensure_ascii=False))
            try:
                (BASE_DIR / "output" / "archive_health.json").write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
        return 0
    cg_ok, why = True, None
    if a.candle:
        from datetime import datetime, timezone
        t = a.candle.replace("Z", "+00:00")
        d = datetime.fromisoformat(t)
        candle_ms = int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp() * 1000)
    else:
        cg = _read(BASE_DIR / "output" / "coinglass_fetch.json") or {}
        candle_ms, why = snapshot_candle(cg)
        if why and not a.force:
            # СРЕЗ НЕ СНЯТ — ПИШЕМ ТОЛЬКО СВЕЧУ (14.09 вечер): раньше здесь был return, и архив молчал
            # часами (ARK 14.09: 00:30 → 13:00 пусто). Поля Coinglass — null с пометкой, свеча Binance — своя.
            cg_ok = False
            import candle_gate
            candle_ms = candle_gate.boundary()
            print(f"intraday: срез Coinglass не снят ({why}) — пишу свечу Binance без полей среза, "
                  f"missing: coinglass; --force чтобы записать срез как есть")
        elif candle_ms is None:
            import candle_gate
            candle_ms = candle_gate.boundary()
            print("intraday: в срезе нет штампа свечи — беру границу калитки")
    rows = build_rows(candle_ms, [x.strip() for x in a.only.split(",")] if a.only else None,
                      cg_ok=cg_ok, cg_why=why if not cg_ok else None)
    if not a.write:
        for r in rows[:3]:
            print(json.dumps(r, ensure_ascii=False))
        print(f"строк {len(rows)} (без записи; --write чтобы записать)")
        return 0
    # строка без среза Coinglass неполная; когда дозабор принесёт полную — она заменит её (refill)
    n = write_rows(rows, refill=a.refill or not cg_ok)
    print(f"intraday: записано {n} строк из {len(rows)} → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
