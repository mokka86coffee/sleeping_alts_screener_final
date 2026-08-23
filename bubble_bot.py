"""Пузырь-бот v2 «FLOW-полигон» — виртуальный полигон трёх этапов.

Отдельный проект. Со скринером связан ОДНИМ файлом: читает
output/flow_watch.json — СПИСОК FLOW (монеты ленты стратегии со
своим подкейсом: hidden/spring/churn/fuel/dormant/taker/leverage) —
и прогоняет каждую через три этапа большой стратегии на 5-минутных
данных ([stated] 24.08: «прогонять наш список flow и понимать, как
лучше выстраивать ТВХ… все 3 основных этапа, и 2-й этап дополнить:
где частичное закрытие, где хеджирование»). Обратно в скринер не
пишет НИЧЕГО; денег нет — виртуальный счёт и два журнала.

ЭТАП 1 · ТЕХ (точка входа):
  вход LONG — крупный БЕЛЫЙ пузырь (перевес агрессивных ПОКУПОК,
  §10 спеки: дельта = 2·takerBuyQuote − quoteVol) в нижней четверти
  суточного коридора. Кейс FLOW пишется в позицию — разрез отчёта
  по кейсам скажет, на каких фигурах ТВХ работает.

ЭТАП 2 · ХОД (ядро эксперимента, всё — в bubble_events.jsonl):
  • ЧАСТИЧКА: на +PARTIAL_PCT закрывается половина, стоп остатка
    встаёт в безубыток — позиция дальше бесплатна;
  • ХЕДЖ: красный пузырь в СЕРЕДИНЕ коридора (не у верха, где это
    раздача, и не у дна, где спека велит его игнорировать) — вместо
    стопа открывается виртуальный шорт того же размера, результат
    замораживается; снятие — по белому пузырю или у низа коридора;
    пока хедж жив, стопы лонг не закрывают;
  • ДОБОР: один, на −DCA_DROP_PCT, только до частички.

ЭТАП 3 · ЗАКРЫТИЕ остатка/позиции:
  красный пузырь у верха (раздача), пробой вверх из коридора,
  безубыток остатка после частички, стоп за нижней границей.

Журналы: bubble_events.jsonl — каждое решение ведения (сырьё для
механики 2-го этапа большой стратегии); bubble_trades.jsonl — итог
сделки целиком (все реализации: частички + хедж + остаток).
Известный компромисс спеки: «обманный прокол вниз» фигуру не
отменяет, а у бота без частички это стоп — кандидат калибровки.

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
WATCH_PATH = BASE_DIR / "output" / "flow_watch.json"   # мост: список FLOW
MANUAL_PATH = BASE_DIR / "bubble_manual.json"          # ручной список, в корне
STATE_PATH = BASE_DIR / "output" / "bubble_state.json"  # открытые позиции
TRADES_PATH = BASE_DIR / "output" / "bubble_trades.jsonl"  # закрытые сделки
EVENTS_PATH = BASE_DIR / "output" / "bubble_events.jsonl"  # события ведения
REPORT_PATH = BASE_DIR / "output" / "bubble_report.txt"

FAPI = "https://fapi.binance.com"

# ── Параметры стратегии (стартовые, калибруются по журналу) ──
BAR = "5m"
BARS_LOOKBACK = 20         # окно для средней силы пузыря
BUBBLE_K = 3.0            # крупный пузырь = дельта бара ≥ K× средней |дельты|
NEAR_LOW_PCT = 25.0       # «у нижней границы» — нижняя четверть коридора
# [stated] 24.08: тейк срезан с 8 до 2 — микро-скальп по любой
# структуре, оборот и калибровка важнее размера цели. АСИММЕТРИЯ
# осознана: стоп за коридором может быть кратно больше тейка,
# винрейт обязан быть высоким; журнал покажет математику. В реале
# комиссии тейкера съели бы ~0.2% из этих 2% — у нас виртуал без
# комиссий, при переносе в реал это первый вопрос.
PARTIAL_PCT = 2.0        # этап 2: частичное закрытие половины

# Т-5 · риск-сайзинг (школа фандед-трейдеров / Ван Тарп): постоянен
# РИСК на сделку, а не размер. size = RISK_USD / (доля пути до стопа);
# узкий коридор → позиция больше, широкий → меньше, статистика сделок
# становится сравнимой. Капы держат размер в разумном коридоре.
RISK_USD = 0.50          # риск на сделку в долларах (≈ прежние $5 при стопе 10%)
SIZE_MIN_USD = 2.0       # не мельчить
SIZE_MAX_USD = 10.0      # и не раздувать на узких коридорах

# Т-5 · буфер стопа за низом коридора. Два независимых источника:
# спека FLOW («флэт завершается обманным проколом вниз, прокол фигуру
# не отменяет» — первый кандидат калибровки) и практика ликвидационных
# карт («не ставь стоп прямо в кластер — его снимут викой»). Стоп
# уходит на процент ПОД границу; прокол на полпроцента больше не выбивает.
STOP_BUF_PCT = 1.0
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


def append_event(ev: dict) -> None:
    """Журнал ВЕДЕНИЯ — каждое решение бота отдельной строкой.
    Это сырьё для механики 2-го этапа большой стратегии: где
    частичное закрытие спасает результат, где хедж, где добор."""
    EVENTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENTS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


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
        case = p.get("case", "?")

        near_high = (low and high and
                     price >= high - (high - low) * NEAR_LOW_PCT / 100)
        near_low = (low and high and
                    price <= low + (high - low) * NEAR_LOW_PCT / 100)
        big_red = (avg > 0 and last_delta < 0
                   and abs(last_delta) >= avg * BUBBLE_K)
        big_white = (avg > 0 and last_delta > 0
                     and last_delta >= avg * BUBBLE_K)

        # ── ЭТАП 2а: активный хедж — сидим в нетто-нуле, ждём
        # возврата покупателя (белый пузырь) или прижатия к низу.
        # Пока хедж жив, никакие стопы лонг не закрывают: защита
        # уже стоит, и в этом суть эксперимента с хеджированием.
        if p.get("hedge"):
            h = p["hedge"]
            if big_white or near_low:
                h_pnl = (h["entry"] - price) * h["qty"]
                st["equity"] += h_pnl
                p["realized"] = p.get("realized", 0.0) + h_pnl
                why = ("белый пузырь — покупатель вернулся"
                       if big_white else "цена у низа коридора")
                p["hedge"] = None
                append_event({
                    "at": _now(), "sym": sym, "case": case,
                    "ev": "hedge_off", "price": price,
                    "pnlUsd": round(h_pnl, 2), "note": why})
                _log(f"{sym} ХЕДЖ СНЯТ @ {price:.6g} · {why} · "
                     f"шорт дал {h_pnl:+.2f}")
            continue

        # ── ЭТАП 2б: частичное закрытие — половина фиксируется на
        # +PARTIAL_PCT, стоп остатка встаёт в безубыток (средний
        # вход). Дальше позиция бесплатна: худший исход — ноль.
        if not p.get("partial") and pnl_pct >= PARTIAL_PCT:
            half = p["qty"] / 2
            part_pnl = (price - avg_entry) * half
            st["equity"] += part_pnl
            p["qty"] -= half
            p["cost"] = avg_entry * p["qty"]
            p["partial"] = True
            p["be"] = avg_entry
            p["realized"] = p.get("realized", 0.0) + part_pnl
            append_event({
                "at": _now(), "sym": sym, "case": case,
                "ev": "partial", "price": price,
                "pnlPct": round(pnl_pct, 2),
                "pnlUsd": round(part_pnl, 2),
                "note": "половина зафиксирована, стоп в безубыток"})
            _log(f"{sym} ЧАСТИЧКА @ {price:.6g} ({pnl_pct:+.1f}%) · "
                 f"половина в кассу {part_pnl:+.2f} · стоп остатка "
                 f"в безубыток {avg_entry:.6g}")
            continue

        # ── ЭТАП 3: выходы остатка / всей позиции ──
        exit_reason = None
        if near_high and big_red and pnl_pct > 0:
            exit_reason = "красный пузырь у верха — раздача"
        elif high and price > high:
            exit_reason = "пробой вверх из коридора"
        elif p.get("partial") and p.get("be") and price <= p["be"]:
            exit_reason = "безубыток остатка"
        # ── ЭТАП 2в: хедж — красный пузырь в СЕРЕДИНЕ коридора
        # (не у верха, где это раздача-выход, и не у низа, где
        # спека велит его игнорировать): против позиции пришёл
        # продавец — вместо стопа накрываемся виртуальным шортом
        # того же размера и замораживаем результат.
        elif big_red and not near_high and not near_low:
            p["hedge"] = {"entry": price, "qty": p["qty"]}
            p["hadHedge"] = True
            append_event({
                "at": _now(), "sym": sym, "case": case,
                "ev": "hedge_on", "price": price,
                "pnlPct": round(pnl_pct, 2),
                "note": "красный в середине — шорт против лонга"})
            _log(f"{sym} ХЕДЖ @ {price:.6g} ({pnl_pct:+.1f}%) · "
                 f"красный в середине коридора, результат заморожен")
            continue
        # Добор — один, только ДО частички (усреднять уже
        # зафиксированное нелогично), и раньше стопа-вниз.
        elif (not p["dca"] and not p.get("partial")
              and pnl_pct <= -DCA_DROP_PCT):
            add_qty = DCA_USD / price
            p["qty"] += add_qty
            p["cost"] += DCA_USD
            p["invested"] = p.get("invested", POS_USD) + DCA_USD
            p["dca"] = True
            append_event({
                "at": _now(), "sym": sym, "case": case, "ev": "dca",
                "price": price, "pnlPct": round(pnl_pct, 2),
                "note": "добор на просадке"})
            _log(f"{sym} ДОБОР @ {price:.6g} (просадка {pnl_pct:+.1f}%)")
            continue
        elif low and price < p.get("stopLine", low) and not p.get("partial"):
            exit_reason = "стоп: пробой вниз (за буфером)"
        elif low and price < p.get("stopLine", low):
            exit_reason = "низ коридора при остатке"

        if exit_reason:
            rest_pnl = (price - avg_entry) * p["qty"]
            realized = p.get("realized", 0.0)
            pnl_usd = rest_pnl + realized
            invested = p.get("invested", POS_USD)
            st["equity"] += rest_pnl
            append_event({
                "at": _now(), "sym": sym, "case": case, "ev": "exit",
                "price": price, "pnlUsd": round(pnl_usd, 2),
                "note": exit_reason})
            risk0 = p.get("initialRisk") or 0
            append_trade({
                "sym": sym, "case": case, "opened": p["opened"],
                "closed": _now(), "entry": avg_entry, "exit": price,
                "invested": invested,
                "pnlUsd": round(pnl_usd, 2),
                "pnlPct": round(pnl_usd / invested * 100, 2),
                "r": round(pnl_usd / risk0, 2) if risk0 > 0 else None,
                "dca": p["dca"], "partial": bool(p.get("partial")),
                "hedged": p.get("hadHedge", False),
                "reason": exit_reason,
            })
            _log(f"{sym} ЗАКРЫТ @ {price:.6g} · {exit_reason} · "
                 f"сделка целиком {pnl_usd:+.2f} "
                 f"({pnl_usd / invested * 100:+.1f}%) · "
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
            stop_line = low * (1 - STOP_BUF_PCT / 100)
            stop_frac = (price - stop_line) / price
            if stop_frac <= 0:
                continue
            size_usd = max(SIZE_MIN_USD,
                           min(SIZE_MAX_USD, RISK_USD / stop_frac))
            qty = size_usd / price
            case = c.get("case", c.get("reason", "?"))
            pos[sym] = {
                "opened": _now(), "entry": price, "qty": qty,
                "cost": size_usd, "invested": size_usd, "dca": False,
                "partial": False, "be": None, "hedge": None,
                "realized": 0.0, "hadHedge": False,
                "stopLine": stop_line,
                "initialRisk": round(size_usd * stop_frac, 4),
                "case": case, "low": low, "high": high,
            }
            append_event({
                "at": _now(), "sym": sym, "case": case, "ev": "enter",
                "price": price,
                "note": f"белый ×{last_delta/avg:.1f} у дна коридора"})
            _log(f"{sym} ВХОД LONG @ {price:.6g} [{case}] · белый "
                 f"пузырь (покупки ×{last_delta/avg:.1f}) у дна · "
                 f"размер ${size_usd:.2f} (риск ${size_usd*stop_frac:.2f} "
                 f"до стопа {stop_line:.6g})")

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
            метки = "".join([
                f" [{p.get('case', '?')}]",
                " [½]" if p.get("partial") else "",
                " [hedge]" if p.get("hedge") else "",
                " [добор]" if p["dca"] else ""])
            _log(f"  {sym} long @{ae:.6g} · сейчас {cur:.6g} "
                 f"({(cur / ae - 1) * 100:+.1f}%) · коридор "
                 f"{p['low']:.6g}–{p['high']:.6g}{метки}")
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

    def _open_lines() -> list[str]:
        """Открытые позиции с живой ценой — главное между закрытиями."""
        out = []
        for sym, p in st.get("positions", {}).items():
            ae = p["cost"] / p["qty"]
            try:
                cur = float(klines(sym, 1)[-1][4])
                mark = f"сейчас {cur:.6g} ({(cur / ae - 1) * 100:+.1f}%)"
            except Exception:
                mark = "цена недоступна"
            try:
                opened = datetime.fromisoformat(p["opened"])
                age = (datetime.now(timezone.utc) - opened
                       ).total_seconds() / 3600
                age_s = f" · висит {age:.1f}ч"
            except (ValueError, TypeError):
                age_s = ""
            метки = "".join([
                f" [{p.get('case', '?')}]",
                " [½]" if p.get("partial") else "",
                " [hedge]" if p.get("hedge") else "",
                " [добор]" if p.get("dca") else ""])
            out.append(f"  {sym} long @{ae:.6g} · {mark} · коридор "
                       f"{p['low']:.6g}–{p['high']:.6g}{age_s}{метки}")
        return out

    if not trades:
        lines.append(f"\nсделок ещё нет · открыто позиций: {open_n} · "
                     f"накопленный P/L ${st.get('equity', 0.0):+.2f}")
        if open_n:
            lines.append("открытые позиции:")
            lines += _open_lines()
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
    # Т-5 · метрики профи: ожидание в единицах риска и просадка.
    # Expectancy = сколько R приносит средняя сделка; положительное
    # ожидание при любом винрейте — единственная цель калибровки.
    rs = [t["r"] for t in trades if t.get("r") is not None]
    if rs:
        win_r = [r for r in rs if r > 0]
        loss_r = [r for r in rs if r <= 0]
        exp_r = sum(rs) / len(rs)
        lines.append(
            f"ожидание: {exp_r:+.2f}R на сделку "
            f"(средний плюс {sum(win_r)/len(win_r):+.2f}R, "
            f"средний минус {sum(loss_r)/len(loss_r):+.2f}R)"
            if win_r and loss_r else
            f"ожидание: {exp_r:+.2f}R на сделку")
    # просадка кривой накопления по порядку закрытий
    eq = peak = dd = 0.0
    for t in trades:
        eq += t["pnlUsd"]
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    lines.append(f"макс. просадка накопителя: ${dd:.2f}")

    # разрез по кейсам FLOW — на каких фигурах вход работает
    by_case: dict[str, list] = {}
    for t in trades:
        by_case.setdefault(t.get("case", "?"), []).append(t)
    if by_case:
        lines.append("по кейсам FLOW:")
        for case, ts in sorted(by_case.items(),
                               key=lambda x: -sum(t["pnlUsd"] for t in x[1])):
            w = sum(1 for t in ts if t["pnlUsd"] > 0)
            pl = sum(t["pnlUsd"] for t in ts)
            lines.append(f"  {case}: {len(ts)} сделок · "
                         f"винрейт {w / len(ts) * 100:.0f}% · "
                         f"P/L ${pl:+.2f}")

    # механики этапа 2 из журнала событий
    evs = []
    if EVENTS_PATH.exists():
        for line in EVENTS_PATH.read_text(encoding="utf-8").splitlines():
            try:
                evs.append(json.loads(line))
            except ValueError:
                continue
    if evs:
        n_part = sum(1 for e in evs if e.get("ev") == "partial")
        h_off = [e for e in evs if e.get("ev") == "hedge_off"]
        h_saved = sum(1 for e in h_off if (e.get("pnlUsd") or 0) > 0)
        lines.append(f"этап 2: частичек {n_part} · хеджей "
                     f"{len(h_off)} (шорт в плюс {h_saved}, "
                     f"в минус {len(h_off) - h_saved})")
        part_trades = [t for t in trades if t.get("partial")]
        if part_trades:
            pl_part = sum(t["pnlUsd"] for t in part_trades)
            lines.append(f"  сделки с частичкой: {len(part_trades)} · "
                         f"P/L ${pl_part:+.2f} (сравнить со сделками "
                         f"без — эффект механики)")

    dca_losses = [t for t in losses if t.get("dca")]
    if open_n:
        lines.append("открытые позиции:")
        lines += _open_lines()
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
