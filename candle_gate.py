#!/usr/bin/env python3
"""Граница свечи и ожидание её закрытия — ОДИН модуль на все быстрые сборщики (05.09).

Правило владельца: целостность важнее расписания. Быстрый сборщик стартует на
границе получаса и ЖДЁТ, пока у источника появится закрытый бар именно этой
границы; проверка — по одной монете-часовому (все монеты закрываются в одну
минуту, у остальных бар будет тем же), дальше обход идёт без проверок.

    from candle_gate import boundary, wait_binance, wait_coinglass
    b = boundary()                    # начало последней закрытой получасовки, мс
    wait_binance(b)                   # ждёт, пока у Binance закроется свеча этой границы
    wait_coinglass(b, get_fn, key)    # то же для Coinglass (get_fn — функция запроса сборщика)

Возврат — сколько секунд ждали; исключение GateTimeout — свеча не появилась до
следующей границы (единственный допустимый случай отставания, сборщик пишет
прошлую с пометкой). Опрос — раз в POLL_S секунд, первый запрос без задержки.
"""
from __future__ import annotations

import json
import time
import urllib.request

INTERVAL_S = 1800          # получасовка — свеча источников
LAUNCH_S = 1200            # запуск сборщиков раз в 20 мин (владелец, 05.09): лучше подождать
                           # закрытия, чем опоздать; повторный запуск на ту же свечу — пропуск
POLL_S = 20                # шаг опроса источника
SENTINEL = "BTCUSDT"       # монета-часовой: есть у всех, ликвидна, бар закрывается первым
BINANCE_FAPI = "https://fapi.binance.com"


class GateTimeout(RuntimeError):
    """Закрытый бар этой границы не появился до следующей границы."""


def boundary(now: float | None = None, interval_s: int = INTERVAL_S) -> int:
    """Начало ПОСЛЕДНЕЙ ЗАКРЫТОЙ свечи в мс: границы кратны интервалу по UTC."""
    now = time.time() if now is None else now
    edge = int(now // interval_s) * interval_s      # последняя граница (свеча с этого t ещё идёт)
    return (edge - interval_s) * 1000               # закрытая — предыдущая


def next_edge(now: float | None = None, interval_s: int = INTERVAL_S) -> float:
    now = time.time() if now is None else now
    return (int(now // interval_s) + 1) * interval_s


def _binance_closed(b_ms: int, interval: str = "30m") -> bool:
    """У Binance есть закрытая свеча с началом b_ms: последняя свеча в ответе с
    closeTime ≤ now и openTime == b_ms, либо любая с openTime ≥ b_ms уже закрыта."""
    url = f"{BINANCE_FAPI}/fapi/v1/klines?symbol={SENTINEL}&interval={interval}&limit=3"
    req = urllib.request.Request(url, headers={"User-Agent": "sleeping-alts/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        rows = json.loads(r.read().decode())
    now_ms = int(time.time() * 1000)
    for k in rows:
        try:
            if int(k[0]) == b_ms and int(k[6]) <= now_ms:
                return True
        except (TypeError, ValueError, IndexError):
            continue
    return False


def wait_binance(b_ms: int, interval: str = "30m", log=print) -> float:
    """Ждать закрытую свечу границы b_ms у Binance. Возвращает секунды ожидания."""
    t0 = time.time()
    deadline = b_ms / 1000 + 2 * INTERVAL_S - 30   # до конца СЛЕДУЮЩЕЙ за целевой свечи
    first = True
    while True:
        try:
            if _binance_closed(b_ms, interval):
                waited = time.time() - t0
                if not first:
                    log(f"→ свеча {_hm(b_ms)}: Binance закрыл, ждали {waited:.0f} с")
                return waited
        except Exception as e:  # noqa: BLE001 — сеть; переспросим
            log(f"→ свеча {_hm(b_ms)}: Binance не ответил ({type(e).__name__}), переспрошу")
        if time.time() >= deadline:
            raise GateTimeout(f"Binance: свеча {_hm(b_ms)} не закрылась до следующей границы")
        if first:
            log(f"→ свеча {_hm(b_ms)}: у Binance ещё не закрыта — жду")
            first = False
        time.sleep(POLL_S)


def wait_coinglass(b_ms: int, get_fn, key: str, log=print,
                   path: str = "/futures/price/history",
                   params: dict | None = None) -> float:
    """Ждать бар границы b_ms у Coinglass. get_fn(path, params, key) → (code, body) —
    та же функция запроса, что у сборщика, чтобы лимит считался в одном месте.
    Бар есть, если в ответе строка с t == b_ms (t в мс или с)."""
    t0 = time.time()
    deadline = b_ms / 1000 + 2 * INTERVAL_S - 30
    first = True
    p = {"exchange": "Binance", "symbol": SENTINEL, "interval": "30m", "limit": 3}
    if params:
        p.update(params)
    while True:
        try:
            code, body = get_fn(path, p, key)
            rows = body.get("data") if isinstance(body, dict) else body
            if code == 200 and isinstance(rows, list):
                for r in rows:
                    t = r.get("t") or r.get("time") or r.get("ts") or r.get("timestamp") if isinstance(r, dict) else None
                    try:
                        t = int(t)
                    except (TypeError, ValueError):
                        continue
                    if t < 1e12:
                        t *= 1000
                    if t == b_ms:
                        waited = time.time() - t0
                        if not first:
                            log(f"→ свеча {_hm(b_ms)}: Coinglass завёл бар, ждали {waited:.0f} с")
                        return waited
        except Exception as e:  # noqa: BLE001
            log(f"→ свеча {_hm(b_ms)}: Coinglass не ответил ({type(e).__name__}), переспрошу")
        if time.time() >= deadline:
            raise GateTimeout(f"Coinglass: бар {_hm(b_ms)} не появился до следующей границы")
        if first:
            log(f"→ свеча {_hm(b_ms)}: у Coinglass бара ещё нет — жду")
            first = False
        time.sleep(POLL_S)


def already_done(path, b_ms: int) -> bool:
    """Файл уже содержит эту свечу (запуск раз в 20 мин при свече в 30 — каждая
    вторая проверка попадает на уже снятую свечу; тогда сборщик ничего не делает)."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(4000)
        return f'"candle_ms": {b_ms}' in head or f'"candle_ms":{b_ms}' in head
    except OSError:
        return False


def target(path, interval_s: int = INTERVAL_S) -> int:
    """Какую свечу снимать этим прогоном: последнюю закрытую, а если она уже снята
    (штамп в файле) — СЛЕДУЮЩУЮ, и её надо дождаться. Владелец, 05.09: «пришёл раньше
    закрытия — жди закрытия», а не пропуск: прогон на каждой свече, ни одного вхолостую."""
    b = boundary(interval_s=interval_s)
    return b + interval_s * 1000 if already_done(path, b) else b


def wait_closed(b_ms: int, log=print) -> float:
    """Ждать, пока свеча b_ms закроется ПО ЧАСАМ (без опроса источника): если её конец
    ещё впереди — спим до него; потом уже опрашивать Binance/Coinglass через wait_*."""
    end = b_ms / 1000 + INTERVAL_S
    now = time.time()
    if end > now:
        log(f"→ свеча {_hm(b_ms)} ещё идёт — жду её закрытия {end - now:.0f} с")
        time.sleep(end - now + 2)
        return end - now
    return 0.0


def missing_stamp(b_ms: int, why: str) -> dict:
    """Штамп НЕЗАПОЛНЕННОЙ свечи (владелец: «лучше без информации, чем с ложной»):
    свеча не снята, файл несёт прошлые данные с явной пометкой. Экраны и сборщик
    страниц обязаны смотреть на missing и не выдавать прошлое за текущее."""
    st = stamp(b_ms)
    st.update({"missing": True, "why": why})
    return st


def _hm(b_ms: int) -> str:
    return time.strftime("%H:%M", time.gmtime(b_ms / 1000)) + " UTC"


def stamp(b_ms: int) -> dict:
    """Штамп для файла быстрого сборщика: свеча и момент записи."""
    return {"candle": time.strftime("%Y-%m-%dT%H:%M:00Z", time.gmtime(b_ms / 1000)),
            "candle_ms": b_ms,
            "written_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


if __name__ == "__main__":
    b = boundary()
    print("закрытая свеча:", _hm(b), "· следующая граница через", round(next_edge() - time.time()), "с")
    try:
        print("Binance: ждали", round(wait_binance(b), 1), "с")
    except GateTimeout as e:
        print("таймаут:", e)
