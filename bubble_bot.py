"""Пузырь-бот — самостоятельный сигнальный сервис (виртуальные сделки).

Отдельный проект. Со скринером связан ОДНИМ файлом: читает
output/flat_watch.json (монеты во флэте у дна, их пишет скринер) и
гоняет по ним быструю логику на 5-минутных данных. Обратно в
скринер не пишет НИЧЕГО. Реальных денег нет — только виртуальный
счёт и журнал; это витрина для оценки стратегии, не торговля.

Семантика по спецификации Market Order Bubbles (документ FLOW):
«пузырь» = аномальный перевес дельты агрессивных сделок за бар;
БЕЛЫЙ = перевес агрессивных ПОКУПОК, КРАСНЫЙ = перевес агрессивных
ПРОДАЖ. Цвет — факт давления в моменте, не прогноз; бот тестирует
гипотезу «белый брать, красный тейк» внутри коридора флэта:
  • вход LONG — крупный БЕЛЫЙ пузырь (перевес покупок) в нижней
    четверти коридора: кто-то крупно откупает у дна;
  • добор один — на DCA_DROP_PCT ниже входа;
  • выход — красный пузырь (перевес продаж) в верхней четверти
    коридора, или тейк +TAKE_PCT, или стоп при выходе цены за
    коридор (флэт кончился — гипотеза отменена).
Известный компромисс из спеки: флэт часто завершается «обманным
проколом вниз», который фигуру НЕ отменяет, — а у бота такой прокол
= стоп. Это цена ограничения риска в скальпе; первый кандидат на
калибровку по журналу (буфер под границей или вход после прокола).
Данные — по §10 спеки: дельта бара = buys − (total − buys) из klines
(quoteVolume idx7, takerBuyQuoteVolume idx10), aggTrades не нужен.

Пороги (K пузыря, тейк, добор) — стартовые, калибруются по журналу.
Данные тянутся с публичного Binance Futures в реальном времени;
бэктеста на прошлом нет — счёт идёт вперёд от запуска.

Запуск:
    python bubble_bot.py                 один цикл (для крона)
    python bubble_bot.py --loop          вечный цикл, шаг POLL_SEC
    python bubble_bot.py --report        показать сводку и выйти
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WATCH_PATH = BASE_DIR / "output" / "flat_watch.json"   # мост от скринера
MANUAL_PATH = BASE_DIR / "bubble_manual.json"          # ручной список, в корне
STATE_PATH = BASE_DIR / "output" / "bubble_state.json"  # открытые позиции
TRADES_PATH = BASE_DIR / "output" / "bubble_trades.jsonl"  # закрытые сделки
REPORT_PATH = BASE_DIR / "output" / "bubble_report.txt"

FAPI = "https://fapi.binance.com"

# ── Параметры стратегии (стартовые, калибруются по журналу) ──
BAR = "5m"
BARS_LOOKBACK = 20         # окно для средней силы пузыря
BUBBLE_K = 3.0            # крупный пузырь = дельта бара ≥ K× средней |дельты|
NEAR_LOW_PCT = 25.0       # «у нижней границы» — нижняя четверть коридора
TAKE_PCT = 8.0           # цель прибыли
DCA_DROP_PCT = 4.0       # добор на столько ниже входа
# Размеры микроскопические сознательно: сейчас важны ПРОГОНЫ и
# калибровка порогов, а не судьба виртуального счёта. Полная позиция
# на монету не превышает $10 (вход + один добор). Капитал НЕ
# ограничен: equity — простой накопитель P/L от нуля, проверок
# «хватает ли денег» нет вовсе — никакая просадка бота не остановит.
POS_USD = 5.0            # виртуальный размер первого входа
DCA_USD = 5.0            # виртуальный добор (один); вход+добор ≤ $10
START_EQUITY = 0.0       # накопитель P/L, не лимит
POLL_SEC = 180           # шаг цикла --loop
MANUAL_RANGE_BARS = 288  # автокоридор ручных монет: крайние за 24ч (5m)

MANUAL_TEMPLATE = {
    "coins": [
        {"sym": "PLAYUSDT",
         "note": "первый ручной кандидат: многомесячный флэт 0.030–0.040"},
    ],
    "_note": ("Ручные монеты пузырь-бота, СВЕРХ списка скринера. Формат "
              "записи: {\"sym\": \"XXXUSDT\"} — этого достаточно: коридор "
              "бот построит сам по крайним за последние 24 часа и будет "
              "обновлять его, пока нет позиции. Можно задать границы "
              "руками: {\"sym\": ..., \"low\": 0.034, \"high\": 0.039} — "
              "тогда бот возьмёт их как есть. Если монета одновременно "
              "пришла и от скринера, его коридор главнее.")
}


# ─────────────────────────────────────────────────────────────
# Данные
# ─────────────────────────────────────────────────────────────
def _get(path: str, params: dict) -> object:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{FAPI}{path}?{q}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def klines(sym: str, limit: int) -> list[list]:
    return _get("/fapi/v1/klines",
                {"symbol": sym, "interval": BAR, "limit": limit})


def bar_delta(k: list) -> float:
    """Дельта бара по §10 спеки: buys − (total − buys) = 2·tb − qv.

    Положительное = перевес агрессивных ПОКУПОК (белый пузырь),
    отрицательное = перевес агрессивных ПРОДАЖ (красный).
    quoteVolume — индекс 7, takerBuyQuoteVolume — индекс 10.
    """
    try:
        qv, tb = float(k[7]), float(k[10])
    except (IndexError, TypeError, ValueError):
        return 0.0
    return 2 * tb - qv


# ─────────────────────────────────────────────────────────────
# Хранилище
# ─────────────────────────────────────────────────────────────
def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_watch() -> list[dict]:
    doc = _load_json(WATCH_PATH, {})
    return (doc or {}).get("coins") or []


def load_manual() -> list[dict]:
    """Ручной список монет; при первом запуске пишется шаблон с PLAY."""
    if not MANUAL_PATH.exists():
        MANUAL_PATH.write_text(
            json.dumps(MANUAL_TEMPLATE, ensure_ascii=False, indent=2),
            encoding="utf-8")
    doc = _load_json(MANUAL_PATH, {})
    return [c for c in (doc.get("coins") or []) if c.get("sym")]


def auto_corridor(sym: str) -> tuple[float, float] | None:
    """Коридор ручной монеты: крайние за последние 24 часа.

    Пересчитывается каждый цикл, пока позиции нет; при входе границы
    замораживаются в позиции — стоп не дрейфует вместе с окном.
    """
    try:
        ks = klines(sym, MANUAL_RANGE_BARS)
    except Exception:
        return None
    if len(ks) < 50:
        return None
    try:
        lo = min(float(k[3]) for k in ks)
        hi = max(float(k[2]) for k in ks)
    except (IndexError, TypeError, ValueError):
        return None
    return (lo, hi) if hi > lo > 0 else None


def build_watchlist() -> list[dict]:
    """Скринерский флэт-вотч + ручные монеты, без дублей.

    При совпадении побеждает скринер: его коридор считан на часовых
    данных, где флэт виден лучше, чем в суточном окне бота.
    """
    watch = load_watch()
    seen = {c.get("sym") for c in watch}
    for m in load_manual():
        sym = m["sym"]
        if sym in seen:
            continue
        entry = {"sym": sym, "reason": "ручной"}
        low, high = m.get("low"), m.get("high")
        if low and high and high > low:
            entry["low"], entry["high"] = float(low), float(high)
        else:
            corr = auto_corridor(sym)
            if not corr:
                continue
            entry["low"], entry["high"] = corr
        watch.append(entry)
        seen.add(sym)
    return watch


def load_state() -> dict:
    return _load_json(STATE_PATH, {"equity": START_EQUITY, "positions": {}})


def save_state(st: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(st, ensure_ascii=False, indent=1),
                          encoding="utf-8")


def append_trade(tr: dict) -> None:
    TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADES_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(tr, ensure_ascii=False) + "\n")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─────────────────────────────────────────────────────────────
# Один цикл
# ─────────────────────────────────────────────────────────────
def _delta_stats(sym: str) -> tuple[float, float, float]:
    """Средняя |дельта| за окно, дельта последнего бара, его close.

    Один запрос klines — по §10 спеки этого достаточно: сторона
    тейкера лежит в самом баре, точно для каждого бара окна.
    """
    ks = klines(sym, BARS_LOOKBACK + 1)
    if len(ks) < BARS_LOOKBACK + 1:
        return 0.0, 0.0, 0.0
    hist = [abs(bar_delta(k)) for k in ks[:-1]]
    avg = sum(hist) / len(hist) if hist else 0.0
    last = ks[-1]
    try:
        price = float(last[4])
    except (IndexError, TypeError, ValueError):
        price = 0.0
    return avg, bar_delta(last), price


def step() -> None:
    watch = build_watchlist()
    if not watch:
        _log("список пуст: скринер монет не передал, ручной список пуст")
        return
    st = load_state()
    pos = st["positions"]
    watch_by = {c["sym"]: c for c in watch}

    prices: dict[str, float] = {}

    # 1. Ведём открытые позиции: красный у верха / тейк / стоп
    for sym in list(pos.keys()):
        p = pos[sym]
        try:
            avg, last_delta, price = _delta_stats(sym)
        except Exception as e:
            _log(f"{sym}: сеть/данные недоступны ({type(e).__name__}) — "
                 f"пропускаю монету в этом цикле")
            continue
        if not price:
            continue
        prices[sym] = price
        corr = watch_by.get(sym)
        low = (corr or p).get("low")
        high = (corr or p).get("high")

        avg_entry = p["cost"] / p["qty"]
        pnl_pct = (price / avg_entry - 1) * 100

        # «красный тейк»: перевес агрессивных ПРОДАЖ в верхней
        # четверти коридора — раздача у потолка, фиксируемся, не
        # дожидаясь полного TAKE_PCT.
        near_high = (low and high and
                     price >= high - (high - low) * NEAR_LOW_PCT / 100)
        big_red = (avg > 0 and last_delta < 0
                   and abs(last_delta) >= avg * BUBBLE_K)

        exit_reason = None
        if pnl_pct >= TAKE_PCT:
            exit_reason = "тейк"
        elif near_high and big_red and pnl_pct > 0:
            exit_reason = "красный пузырь у верха — фиксация"
        elif high and price > high:
            exit_reason = "стоп: пробой вверх из флэта"
        # Добор проверяется РАНЬШЕ стопа-вниз: иначе при близкой нижней
        # границе цена пробивает коридор прежде, чем дойдёт до порога
        # добора, и усреднение не случится никогда. Один раз.
        elif not p["dca"] and pnl_pct <= -DCA_DROP_PCT:
            add_qty = DCA_USD / price
            p["qty"] += add_qty
            p["cost"] += DCA_USD
            p["dca"] = True
            _log(f"{sym} ДОБОР @ {price:.6g} (просадка {pnl_pct:+.1f}%)")
            continue
        elif low and price < low:
            exit_reason = "стоп: пробой вниз из флэта"

        if exit_reason:
            pnl_usd = (price - avg_entry) * p["qty"]
            st["equity"] += pnl_usd
            append_trade({
                "sym": sym, "opened": p["opened"], "closed": _now(),
                "entry": avg_entry, "exit": price, "qty": p["qty"],
                "cost": p["cost"], "pnlUsd": round(pnl_usd, 2),
                "pnlPct": round((price / avg_entry - 1) * 100, 2),
                "dca": p["dca"], "reason": exit_reason,
            })
            _log(f"{sym} ЗАКРЫТ @ {price:.6g} · {exit_reason} · "
                 f"P/L {pnl_usd:+.2f} ({(price/avg_entry-1)*100:+.1f}%) · "
                 f"накоплено ${st['equity']:+.2f}")
            del pos[sym]

    # 2. Ищем входы среди флэтовых, кого ещё не держим
    for c in watch:
        sym = c["sym"]
        if sym in pos:
            continue
        low, high = c.get("low"), c.get("high")
        if not (low and high and high > low):
            continue
        try:
            avg, last_delta, price = _delta_stats(sym)
        except Exception as e:
            _log(f"{sym}: сеть/данные недоступны ({type(e).__name__}) — "
                 f"пропускаю монету в этом цикле")
            continue
        if avg <= 0 or not price:
            continue
        prices[sym] = price

        # у нижней границы коридора?
        near_low = price <= low + (high - low) * NEAR_LOW_PCT / 100
        # крупный БЕЛЫЙ пузырь: перевес агрессивных ПОКУПОК —
        # кто-то крупно откупает у дна (семантика спеки)
        big_white = last_delta > 0 and last_delta >= avg * BUBBLE_K
        if near_low and big_white:
            qty = POS_USD / price
            pos[sym] = {
                "opened": _now(), "entry": price, "qty": qty,
                "cost": POS_USD, "dca": False, "low": low, "high": high,
            }
            _log(f"{sym} ВХОД LONG @ {price:.6g} · белый пузырь "
                 f"(покупки ×{last_delta/avg:.1f}) у дна коридора")

    save_state(st)

    # Сердцебиение цикла: видно, что бот жив, чем занят и где стоит.
    n_man = sum(1 for c in watch if c.get("reason") == "ручной")
    _log(f"цикл: монет {len(watch)} (скринер {len(watch) - n_man} + "
         f"ручных {n_man}) · позиций {len(pos)} · "
         f"накоплено ${st['equity']:+.2f}")
    if pos:
        for sym, p in pos.items():
            cur = prices.get(sym)
            if not cur:
                continue
            ae = p["cost"] / p["qty"]
            _log(f"  {sym} long @{ae:.6g} · сейчас {cur:.6g} "
                 f"({(cur / ae - 1) * 100:+.1f}%) · коридор "
                 f"{p['low']:.6g}–{p['high']:.6g}"
                 f"{' · добор был' if p['dca'] else ''}")
    else:
        _log("  позиций нет — жду белый пузырь у дна коридора")


# ─────────────────────────────────────────────────────────────
# Сводка
# ─────────────────────────────────────────────────────────────
def report() -> str:
    trades = []
    if TRADES_PATH.exists():
        for line in TRADES_PATH.read_text(encoding="utf-8").splitlines():
            try:
                trades.append(json.loads(line))
            except ValueError:
                continue
    st = load_state()
    open_n = len(st.get("positions", {}))
    lines = ["═══ ПУЗЫРЬ-БОТ · СВОДКА ═══", f"время: {_now()}"]

    if not trades:
        lines.append(f"\nсделок ещё нет · открыто позиций: {open_n} · "
                     f"накопленный P/L ${st.get('equity', 0.0):+.2f}")
        out = "\n".join(lines)
        REPORT_PATH.write_text(out, encoding="utf-8")
        return out

    wins = [t for t in trades if t["pnlUsd"] > 0]
    losses = [t for t in trades if t["pnlUsd"] <= 0]
    tot = sum(t["pnlUsd"] for t in trades)
    wr = len(wins) / len(trades) * 100
    avg_w = sum(t["pnlPct"] for t in wins) / len(wins) if wins else 0
    avg_l = sum(t["pnlPct"] for t in losses) / len(losses) if losses else 0
    best = max(trades, key=lambda t: t["pnlPct"])
    worst = min(trades, key=lambda t: t["pnlPct"])

    lines += [
        f"\nсделок: {len(trades)} · открыто ещё: {open_n}",
        f"винрейт: {wr:.0f}% ({len(wins)}/{len(trades)})",
        f"суммарный P/L: ${tot:+.2f} · накоплено ${st.get('equity', 0.0):+.2f}",
        f"средний плюс: {avg_w:+.1f}% · средний минус: {avg_l:+.1f}%",
        f"лучшая: {best['sym']} {best['pnlPct']:+.1f}% · "
        f"худшая: {worst['sym']} {worst['pnlPct']:+.1f}%",
    ]
    # причины закрытий и роль добора — то, из чего читается механика
    by_reason: dict[str, int] = {}
    for t in trades:
        by_reason[t["reason"]] = by_reason.get(t["reason"], 0) + 1
    lines.append("выходы: " + ", ".join(f"{k} ×{v}"
                 for k, v in sorted(by_reason.items(), key=lambda x: -x[1])))
    dca_losses = [t for t in losses if t.get("dca")]
    lines.append(f"убытки с добором: {len(dca_losses)} из {len(losses)} "
                 f"(добор перед стопом — сигнал, что усреднять здесь вредно)"
                 if losses else "убытков нет")
    out = "\n".join(lines)
    REPORT_PATH.write_text(out, encoding="utf-8")
    return out


def _log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}")


if __name__ == "__main__":
    if "--report" in sys.argv:
        print(report())
    elif "--loop" in sys.argv:
        _log(f"пузырь-бот запущен, шаг {POLL_SEC}с · Ctrl+C для остановки")
        while True:
            try:
                step()
            except Exception as e:
                _log(f"цикл упал: {type(e).__name__}: {e}")
            time.sleep(POLL_SEC)
    else:
        step()
        print(report())
