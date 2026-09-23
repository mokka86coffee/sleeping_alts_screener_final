#!/usr/bin/env python3
"""ТРЁХМИНУТКИ ПО ЛИДЕРАМ (17.09, владелец: «пиши бота, который каждые три минуты ходит за ценами на всех лидеров;
через пару часов будут данные, вортекс и остальное по тридцатиминуткам — там будем придумывать»).

Отдельный процесс, не шаг прогона. Раз в три минуты, по закрытию трёхминутной свечи, по каждому лидеру берёт
с биржи закрытую свечу: открытие, максимум, минимум, закрытие, оборот, покупки по рынку — из них дельта и
тейкер бара — и число сделок; к ней интерес (последняя точка истории интереса по 5 минут) и фандинг. Пишет
строку в cq_v2/tick/<база>.jsonl. При старте дозабирает историю: TICK_BACKFILL свечей (по умолчанию 960 — двое
суток), чтобы данные были сразу, а не через пару часов.

Кто лидер — читается каждый цикл, ничего не решается:
  • живые записи pump_leaders.json;
  • монеты из junction_state.json (первые доски по ходу за сутки, с хвостом после лидерства);
  • TICK_EXTRA из core_config — что владелец добавил руками (позиции, наблюдаемые);
  • BTC — всегда, как фон.
Сеть — через core_binance (общий лимитер). Сбой одной монеты не останавливает цикл.
    python3 tick_fetch.py --once            # один цикл сейчас, без ожидания свечи
    python3 tick_fetch.py --only ONE --once
    python3 tick_fetch.py                   # бесконечно, по закрытию каждой трёхминутки
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import TICK_INTERVAL, TICK_BACKFILL, TICK_EXTRA, TICK_LAG_SEC
except ImportError:
    TICK_INTERVAL, TICK_BACKFILL, TICK_EXTRA, TICK_LAG_SEC = "3m", 960, [], 6
try:
    from core_config import PUMP_LEADERS_PATH
except ImportError:
    PUMP_LEADERS_PATH = BASE_DIR / "output" / "pump_leaders.json"
try:
    from core_http import log
except ImportError:
    def log(msg: str) -> None:
        print(msg, flush=True)

import core_binance as cb
from core_binance import get_klines
from core_config import BINANCE_FAPI
from core_http import get_json

TICK_DIR = BASE_DIR / "cq_v2" / "tick"
STATE = BASE_DIR / "output" / "tick_state.json"
SIGHT_STATE = BASE_DIR / "output" / "paper_sight.json"
TICK_WORKERS = 8
STEP = {"1m": 60, "3m": 180, "5m": 300}[TICK_INTERVAL]
# индексы свечи Binance: 0 время открытия, 1 открытие, 2 максимум, 3 минимум, 4 закрытие, 5 объём, 7 оборот $,
# 8 сделок, 10 покупки по рынку $. Если core_binance объявляет свои константы — берутся они.
K_T, K_O, K_H, K_L, K_C = (getattr(cb, "K_OPEN_TIME", 0), getattr(cb, "K_OPEN", 1), getattr(cb, "K_HIGH", 2),
                           getattr(cb, "K_LOW", 3), getattr(cb, "K_CLOSE", 4))
K_V, K_Q, K_N, K_TBQ = (getattr(cb, "K_VOLUME", 5), getattr(cb, "K_QUOTE_VOLUME", 7), getattr(cb, "K_TRADES", 8),
                        getattr(cb, "K_TAKER_BUY_QUOTE", 10))


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def leaders() -> list[str]:
    """список монет на этот цикл: лидеры по пампу, лидеры стыков, ручной список, биткоин"""
    out: set = set()
    recs = _read(Path(PUMP_LEADERS_PATH)) or {}
    for r in (recs.values() if isinstance(recs, dict) else recs):
        if isinstance(r, dict) and r.get("symbol") and not r.get("retired_at"):
            out.add(str(r["symbol"]).upper())
    js = _read(BASE_DIR / "output" / "junction_state.json") or {}
    for s in (js.get("leader_last") or {}):
        out.add(str(s).upper())
    for s in TICK_EXTRA or []:
        s = str(s).upper()
        out.add(s if s.endswith("USDT") else s + "USDT")
    # 23.09: открытые позиции «картины» — её цели и повтор идут по трёхминуткам (paper_sight --tick)
    for s in ((_read(SIGHT_STATE) or {}).get("open") or {}):
        out.add(str(s).upper())
    out.add("BTCUSDT")
    return sorted(out)


def sight_tick() -> None:
    """цели и повтор «картины» по только что записанным трёхминуткам; сбой книги сборщик не роняет"""
    try:
        r = subprocess.run([sys.executable, "paper_sight.py", "--tick", "--write"], cwd=BASE_DIR,
                           capture_output=True, text=True, timeout=150)
        for line in (r.stdout or "").splitlines():
            log(line)
        if r.returncode:
            log(f"tick: paper_sight --tick код {r.returncode}: {(r.stderr or '').strip()[-300:]}")
    except Exception as e:  # noqa: BLE001
        log(f"tick: paper_sight --tick сбой {type(e).__name__}: {e}")


def _row(sym: str, k: list, oi, fund) -> dict:
    t = int(k[K_T]) // 1000
    qv = float(k[K_Q] or 0)
    tb = float(k[K_TBQ] or 0) if len(k) > K_TBQ else 0.0
    return {"candle": datetime.fromtimestamp(t, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sym": sym,
            "o": float(k[K_O]), "h": float(k[K_H]), "l": float(k[K_L]), "c": float(k[K_C]),
            "v": float(k[K_V] or 0), "qv": round(qv, 2), "n": int(k[K_N] or 0) if len(k) > K_N else None,
            "tb": round(tb, 2), "d": round(2 * tb - qv, 2),                       # дельта $: покупки минус продажи
            "tk": round(tb / (qv - tb), 4) if qv > tb > 0 else None,             # тейкер бара
            "oi": oi, "funding": fund}


def _last_candle(rows: list[dict]) -> str:
    return max((r.get("candle") or "" for r in rows), default="")


def _existing(base: str, tail_bytes: int | None = 60_000) -> set:
    """свечи, что уже в файле. По умолчанию — хвост (23.09: полный разбор 114 файлов по мегабайту занимал две минуты
    из трёх); целиком — при дозаборе дыры, где новые свечи могут лечь далеко от конца."""
    p = TICK_DIR / f"{base}.jsonl"
    if not p.exists():
        return set()
    out = set()
    with p.open("rb") as f:
        if tail_bytes:
            f.seek(0, 2)
            f.seek(max(0, f.tell() - tail_bytes))
        text = f.read().decode("utf-8", "ignore")
    for line in text.splitlines():
        try:
            out.add(json.loads(line).get("candle"))
        except ValueError:
            continue
    return out


def _oi_now(sym: str):
    try:
        h = cb.get_oi_history(sym, "5m", 1) or []
        x = h[-1] if h else None
        if isinstance(x, dict):
            return float(x.get("sumOpenInterestValue") or x.get("oi_usd") or x.get("sumOpenInterest") or 0) or None
    except Exception:  # noqa: BLE001
        return None
    return None


def _fund_now(sym: str):
    try:
        f = cb.get_funding_rate(sym)
        if isinstance(f, dict):
            f = f.get("lastFundingRate") or f.get("funding") or f.get("rate")
        return round(float(f) * 100, 4) if f is not None else None                # в процентах, как в архиве
    except Exception:  # noqa: BLE001
        return None


def _klines_since(sym: str, start_ms: int) -> list:
    """Свечи от start_ms до сейчас, страницами по 1500 (23.09: дыра 17→23.09 не закрывалась — цикл брал
    три последние свечи, а дозабор шёл только для нового файла). Мимо кэша прогона: здесь он не нужен."""
    out: list = []
    while True:
        page = get_json(f"{BINANCE_FAPI}/fapi/v1/klines",
                        {"symbol": sym, "interval": TICK_INTERVAL, "startTime": start_ms, "limit": 1500},
                        weight=10) or []
        if not page:
            break
        out.extend(page)
        if len(page) < 1500:
            break
        start_ms = int(page[-1][K_T]) + STEP * 1000
    return out


def fetch(sym: str, limit: int, write: bool, since_ms: int | None = None) -> int:
    """закрытые свечи монеты, которых ещё нет в файле; интерес и фандинг — только к последней.
    Если в файле дыра больше limit свечей — дозабор от последней записанной (или от since_ms)."""
    base = sym.replace("USDT", "").lower()
    have = _existing(base, None if (since_ms or limit > 50) else 60_000)    # дозабор — по всему файлу, иначе дубли
    last = max((c for c in have if c), default="")
    start_ms = since_ms
    if start_ms is None and last:
        last_ms = int(datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
        if time.time() * 1000 - last_ms > limit * STEP * 1000:
            start_ms = last_ms + STEP * 1000
    ks = _klines_since(sym, start_ms) if start_ms else (get_klines(sym, TICK_INTERVAL, limit=limit) or [])
    now = time.time()
    ks = [k for k in ks if int(k[K_T]) // 1000 + STEP <= now]                    # открытая свеча не берётся
    if not ks:
        return 0
    oi, fund = _oi_now(sym), _fund_now(sym)
    new = []
    for i, k in enumerate(ks):
        c = datetime.fromtimestamp(int(k[K_T]) // 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if c in have:
            continue
        last = i == len(ks) - 1
        new.append(_row(sym, k, oi if last else None, fund if last else None))
    if write and new:
        TICK_DIR.mkdir(parents=True, exist_ok=True)
        with (TICK_DIR / f"{base}.jsonl").open("a", encoding="utf-8") as f:
            for r in new:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return len(new)


def cycle(syms: list[str], write: bool, backfill: bool, since_ms: int | None = None) -> None:
    t0 = time.time()
    # 23.09: кэш core_binance живёт «на прогон», а этот процесс — бесконечный: с 17.09 каждый цикл получал из
    # кэша те же три свечи, и в файлы не легло ни одной новой («новых свечей 0» шесть дней подряд)
    cb.KLINES_CACHE.clear()
    total, bad = 0, []

    def one(sym: str) -> int:
        base = sym.replace("USDT", "").lower()
        limit = TICK_BACKFILL if (backfill or not (TICK_DIR / f"{base}.jsonl").exists()) else 3
        return fetch(sym, limit, write, since_ms)

    # 23.09: 114 монет по очереди — 140 с из 180 (три запроса на монету). Потоками; лимит биржи держит общий
    # токен-бакет core_http, у каждой монеты свой файл — записи не пересекаются.
    with ThreadPoolExecutor(max_workers=TICK_WORKERS) as ex:
        futs = {ex.submit(one, s): s for s in syms}
        for f in as_completed(futs):
            try:
                total += f.result()
            except Exception as e:  # noqa: BLE001
                bad.append(f"{futs[f]}: {type(e).__name__}: {e}")
    log(f"tick: монет {len(syms)} · новых свечей {total} · {time.time() - t0:.1f} с"
        + (f" · сбоев {len(bad)}: {'; '.join(bad)[:200]}" if bad else "") + ("" if write else " (без записи)"))
    if write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "syms": syms,
                                   "new": total, "bad": bad}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--backfill", action="store_true", help="дозабрать TICK_BACKFILL свечей даже если файл есть")
    ap.add_argument("--since", help="дозабрать от даты UTC (2026-09-16), свечи уже в файле не дублируются")
    a = ap.parse_args()
    write = not a.no_write
    since_ms = (int(datetime.fromisoformat(a.since).replace(tzinfo=timezone.utc).timestamp() * 1000)
                if a.since else None)
    if a.only:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
    else:
        syms = leaders()
    if a.once:
        cycle(syms, write, a.backfill, since_ms)
        return 0
    log(f"tick: старт · интервал {TICK_INTERVAL} · лидеров {len(syms)} · история {TICK_BACKFILL} свечей")
    cycle(syms, write, True)
    while True:
        # ждём закрытия следующей свечи плюс небольшой лаг, чтобы биржа успела её отдать
        now = time.time()
        nxt = (int(now) // STEP + 1) * STEP + TICK_LAG_SEC
        time.sleep(max(1.0, nxt - now))
        try:
            syms = leaders() if not a.only else syms
            cycle(syms, write, False)
            if write and not a.only:
                sight_tick()
        except Exception as e:  # noqa: BLE001
            log(f"tick: сбой цикла {type(e).__name__}: {e}")
            time.sleep(10)


if __name__ == "__main__":
    raise SystemExit(main())
