"""Сборщик Coinglass по журналу: одна команда — один срез.

    export COINGLASS_KEY=...              # ключ НЕ в коде
    python coinglass_fetch.py             # журнал + BTC: показать и НЕ писать
    python coinglass_fetch.py MAGMA HEMI  # только названные монеты
    python coinglass_fetch.py --write     # ещё и записать output/coinglass_fetch.json

ПРАВИЛО РЕЗЕРВУАРА: по умолчанию сборщик ПОКАЗЫВАЕТ и ничего не
пишет. Запись — только флагом --write; врезка в run.py — отдельным
решением после просмотра живого среза.

ЧТО СНИМАЕТ И ПОЧЕМУ ИМЕННО ТАК (по фактам пробника 29.08, MAGMA):

  · ФЬЮЧЕРСНАЯ ДЕЛЬТА /futures/aggregated-cvd/history — в ОДНОЙ точке
    и тейкерские объёмы (agg_taker_buy_vol / agg_taker_sell_vol), и
    накопленная дельта (cum_vol_delta). Пробник показал, что отдельная
    точка тейкера отдаёт ТЕ ЖЕ числа, поэтому её не зовём: минус один
    запрос на монету.
  · СПОТОВАЯ ДЕЛЬТА /spot/aggregated-cvd/history — зеркало. Пустой
    ответ у перповой монеты (MAGMA: спота нет на Binance, OKX, Bybit)
    — это ОТВЕТ «движение оплачено плечом», а не поломка; в срезе
    поле spot = null. Имена спотовых полей вживую не видели — разбор
    терпимый, по подстрокам buy/sell/delta.
  · ОТКРЫТЫЙ ИНТЕРЕС /futures/open-interest/aggregated-history и
    ФАНДИНГ /futures/funding-rate/oi-weight-history — агрегат по всем
    биржам: Р-11 и Т-4 меряют рынок, а не одну Binance. Значения
    приходят СТРОКАМИ в OHLC-виде — приводим явно, иначе сложение
    склеит текст. Фандинг храним как отдаёт точка (проценты); сверка
    масштаба с нашим пульсовым фандингом — отдельным шагом.
  · ЛИКВИДАЦИИ /futures/liquidation/coin-list — полторы тысячи монет
    ОДНИМ запросом, лонг и шорт за 24ч/12ч/4ч/1ч. Из списка режем
    журнал; помонетный цикл истории (как в sources_coinglass.py) для
    среза не нужен.

УРОКИ ПРОБНИКА, ВПИСАННЫЕ В КОД:
  · ОТКАЗ ВНУТРИ КОДА 200: Coinglass кладёт code в тело ответа.
    Проверяем его ДО разбора данных, иначе «нет доступа по тарифу»
    неотличимо от «данных нет» — монета молча пропадает, а счётчик
    ошибок не растёт. Отказ пишется в срез с сообщением точки.
  · НЕПОЛНЫЙ ПОСЛЕДНИЙ БАР: текущий час всегда незакрыт (в пробнике
    он давал тридцатикратное «падение» объёма). Просим WINDOW+1 баров
    и последний ОТБРАСЫВАЕМ; все суммы — только по закрытым.
  · ПУСТО ≠ ОШИБКА: код ноль и пустой data — это «данных нет», в
    счётчик ошибок не идёт.

ЛИМИТ Startup — восемьдесят запросов в минуту. Четыре запроса на
монету (фьюч-дельта, спот-дельта, OI, фандинг) плюс один общий список
ликвидаций: на двадцати пяти монетах это ~101 запрос и около полутора
минут при паузе 0.8 с. Потолок MAX_COINS держит лимит; журнал в него
влезает с запасом только по срезанному хвосту — расширять вместе с
паузой, не вместо неё.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except ImportError:                      # запуск вне окружения проекта
    BASE_DIR = Path(__file__).resolve().parent
    def log(msg: str) -> None:
        print(msg)

BASE = "https://open-api-v4.coinglass.com/api"
KEY_ENV = "COINGLASS_KEY"
CONFIG_PATH = BASE_DIR / "output" / "coinglass_config.json"
STATE_PATH = BASE_DIR / "output" / "coinglass_fetch.json"

EXCHANGES = "Binance,OKX,Bybit"     # как в пробнике
INTERVAL = "1h"
WINDOW = 12                         # закрытых баров в окне (часов)
MAX_COINS = 25                      # журнал + BTC; потолок под лимит
PAUSE_SEC = 0.8                     # восемьдесят в минуту — с запасом
TIMEOUT = 20

LIQ_WINDOWS = ("24h", "12h", "4h", "1h")


# ── сеть ────────────────────────────────────────────────────────────

def get(path: str, params: dict, key: str) -> tuple[int, dict | str]:
    """Как в пробнике: (HTTP-код, разобранное тело либо текст)."""
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "CG-API-KEY": key,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body
    except Exception as e:              # сеть, таймаут, кривой JSON
        return 0, f"{type(e).__name__}: {e}"


class Denied(Exception):
    """Точка отказала: HTTP не двести ИЛИ code в теле не ноль."""


def _body(code: int, data) -> dict:
    """Тело при живом ответе; иначе Denied с человеческим текстом.

    Отказ внутри кода 200 — главный урок пробника: смотрим ОБА поля.
    """
    inner = data.get("code") if isinstance(data, dict) else None
    if code == 200 and str(inner) in ("0", "None", "success"):
        return data
    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("msg") or data.get("message") or "")
    elif isinstance(data, str):
        msg = data[:120]
    raise Denied(f"[{code}/{inner}] {msg}".strip())


# ── разбор ──────────────────────────────────────────────────────────

def _num(v) -> float | None:
    """Число из числа или строки; NaN и мусор — None, не ноль."""
    if isinstance(v, str):
        v = v.strip().replace(",", "")
    try:
        f = float(v)
        return f if f == f else None
    except (TypeError, ValueError):
        return None


def _columns(obj: dict) -> list[dict]:
    """Колоночный ответ (*_list параллельными списками) — в строки."""
    lists = {k: v for k, v in obj.items()
             if k.endswith("_list") and isinstance(v, list)}
    if len(lists) < 2:
        return []
    n = min(len(v) for v in lists.values())
    out = []
    for i in range(n):
        row = {}
        for k, v in lists.items():
            row["time" if k == "time_list" else k[:-5]] = v[i]
        out.append(row)
    return out


def _rows(doc: dict) -> list[dict]:
    """data → список строк-словарей; любая другая форма → пусто."""
    rows = doc.get("data")
    if isinstance(rows, dict):
        cols = _columns(rows)
        rows = cols if cols else (rows.get("list") or rows.get("dataList")
                                  or rows.get("data") or [])
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def _closed(rows: list[dict]) -> list[dict]:
    """Отбросить незакрытый последний бар. Одна строка — не окно."""
    return rows[:-1] if len(rows) > 1 else []


def _pick(row: dict, need: tuple[str, ...],
          avoid: tuple[str, ...] = ()) -> float | None:
    """Значение по подстрокам имени поля — терпимо к переименованиям."""
    for k, v in row.items():
        kl = k.lower()
        if all(s in kl for s in need) and not any(s in kl for s in avoid):
            return _num(v)
    return None


def parse_cvd(doc: dict) -> dict | None:
    """Тейкер и дельта из aggregated-cvd (фьючерсы и спот — одна форма).

    Возврат None — данных нет (пустой data): у перповых монет так
    выглядит спот, и это ответ, а не ошибка.
    """
    rows = _closed(_rows(doc))
    if not rows:
        return None
    buy = sell = 0.0
    seen = False
    cvd_first = cvd_last = None
    for r in rows:
        b = _pick(r, ("buy",), avoid=("sell",))
        s = _pick(r, ("sell",))
        if b is not None:
            buy += b; seen = True
        if s is not None:
            sell += s; seen = True
        c = _pick(r, ("delta",))
        if c is None:
            c = _pick(r, ("cvd",))
        if c is not None:
            if cvd_first is None:
                cvd_first = c
            cvd_last = c
    if not seen and cvd_last is None:
        return None
    out: dict = {"buyUsd": round(buy, 2), "sellUsd": round(sell, 2),
                 "taker": round(buy / sell, 3) if sell > 0 else None,
                 "bars": len(rows)}
    if cvd_last is not None:
        out["cvd"] = round(cvd_last, 2)
        if cvd_first is not None:
            out["cvdChg"] = round(cvd_last - cvd_first, 2)
    return out


def parse_ohlc_close(doc: dict) -> dict | None:
    """Последний и первый close закрытых баров (OI, фандинг).

    Числа приходят строками — _num приводит; мусор не превращается
    в ноль.
    """
    closes = [c for c in (_num(r.get("close")) for r in _closed(_rows(doc)))
              if c is not None]
    if not closes:
        return None
    out = {"last": closes[-1], "first": closes[0], "bars": len(closes)}
    if closes[0]:
        out["chgPct"] = round((closes[-1] / closes[0] - 1) * 100, 2)
    return out


def parse_liq_list(doc: dict) -> dict[str, dict]:
    """Список ликвидаций по всем монетам → {SYM: {long24h, short24h, …}}.

    Окно ищем с границей «_4h», не голым «4h»: иначе оно находит
    себя внутри «_24h» и окна перепутываются (вскрыто юнитом).
    Свободный поиск — только запасным ходом, если строгий не нашёл
    в строке ничего вовсе (переименование полей).
    """
    out: dict[str, dict] = {}
    for r in _rows(doc):
        sym = str(r.get("symbol") or "").upper()
        if not sym:
            continue
        entry: dict = {}
        for strict in (True, False):
            for w in LIQ_WINDOWS:
                mark = f"_{w}" if strict else w
                lo = _pick(r, ("long", mark))
                sh = _pick(r, ("short", mark))
                if lo is not None:
                    entry[f"long{w}"] = lo
                if sh is not None:
                    entry[f"short{w}"] = sh
            if entry:
                break
        if entry:
            out[sym] = entry
    return out


# ── монеты и ключ ───────────────────────────────────────────────────

def _base_coin(sym: str) -> str:
    """BTCUSDT → BTC: Coinglass ходит по монете, не по паре."""
    s = sym.upper()
    for tail in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(tail) and len(s) > len(tail):
            return s[: -len(tail)]
    return s


def _journal_coins() -> tuple[list[str], str | None]:
    """Монеты журнала + BTC. Вторым значением — причина, если журнал
    НЕ прочитался: живой прогон показал, что молчаливый откат до
    одного BTC выглядит как «всё хорошо, монет одна» — теперь причина
    печатается в ошибках среза. Обычные причины: запуск не из корня
    проекта либо analytics_leaders не собрался.
    """
    note = None
    try:
        from analytics_leaders import tracked_symbols
        symbols = sorted(tracked_symbols())
    except Exception as e:
        symbols = []
        note = (f"журнал не прочитан ({type(e).__name__}: {e}) — "
                f"в срезе только BTC; запускать из корня проекта")
    coins: list[str] = []
    for s in ["BTC"] + [_base_coin(x) for x in symbols]:
        if s and s not in coins:
            coins.append(s)
    return coins[:MAX_COINS], note


def _key() -> str:
    """Окружение первым, файл вне гита — запасным. В коде ключа нет."""
    k = os.environ.get(KEY_ENV, "").strip()
    if k:
        return k
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return str(cfg.get("api_key") or "").strip()
    except (OSError, ValueError):
        return ""


# ── сбор ────────────────────────────────────────────────────────────

def snap_coin(coin: str, key: str, errors: dict) -> dict:
    """Четыре точки по монете; отказ пишется в errors, пусто — null."""
    out: dict = {}
    probes = (
        ("fut", "/futures/aggregated-cvd/history",
         {"exchange_list": EXCHANGES, "interval": INTERVAL,
          "limit": str(WINDOW + 1), "symbol": coin}, parse_cvd),
        ("spot", "/spot/aggregated-cvd/history",
         {"exchange_list": EXCHANGES, "interval": INTERVAL,
          "limit": str(WINDOW + 1), "symbol": coin}, parse_cvd),
        ("oi", "/futures/open-interest/aggregated-history",
         {"exchange_list": EXCHANGES, "interval": INTERVAL,
          "limit": str(WINDOW + 1), "symbol": coin}, parse_ohlc_close),
        ("funding", "/futures/funding-rate/oi-weight-history",
         {"interval": INTERVAL, "limit": str(WINDOW + 1),
          "symbol": coin}, parse_ohlc_close),
    )
    for field, path, params, parse in probes:
        try:
            doc = _body(*get(path, params, key))
            out[field] = parse(doc)          # None = данных нет, это ответ
        except Denied as e:
            out[field] = None
            errors[f"{coin} {field}"] = str(e)
        time.sleep(PAUSE_SEC)
    if isinstance(out.get("oi"), dict):
        oi = out.pop("oi")
        out["oiUsd"] = oi.get("last")
        out["oiChgPct"] = oi.get("chgPct")
    else:
        out["oiUsd"] = out["oiChgPct"] = None
        out.pop("oi", None)
    if isinstance(out.get("funding"), dict):
        out["funding"] = out["funding"].get("last")
    return out


def collect(symbols: list[str] | None = None, *,
            key: str | None = None, write: bool = False) -> dict:
    """Срез по журналу (или названным монетам). write=False — не пишет."""
    key = key if key is not None else _key()
    if not key:
        return {"error": f"нет ключа: переменная {KEY_ENV} "
                         f"или {CONFIG_PATH}"}
    coins = [_base_coin(s) for s in symbols] if symbols else None
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "window": f"{WINDOW}x{INTERVAL}", "coins": {},
                   "errors": {}, "requests": 0}
    if coins is None:
        coins, note = _journal_coins()
        if note:
            state["errors"]["журнал"] = note

    # Ликвидации по всем монетам — один запрос на весь журнал.
    liq_all: dict[str, dict] = {}
    try:
        doc = _body(*get("/futures/liquidation/coin-list",
                         {"range": "24h"}, key))
        liq_all = parse_liq_list(doc)
    except Denied as e:
        state["errors"]["liq-list"] = str(e)
    state["requests"] += 1
    time.sleep(PAUSE_SEC)

    for coin in coins:
        entry = snap_coin(coin, key, state["errors"])
        state["requests"] += 4
        entry["liq"] = liq_all.get(coin)
        state["coins"][coin] = entry

    if write:
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(
                json.dumps(state, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            state["errors"]["write"] = "срез не записался"
    return state


# ── показ ───────────────────────────────────────────────────────────

def _usd(v) -> str:
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:.1f}{suf}"
    return f"{v:.0f}"


def digest(state: dict) -> str:
    """Одна строка на монету; интерпретаций нет — только числа."""
    if state.get("error"):
        return "coinglass: " + state["error"]
    head = (f"coinglass-срез {state.get('at', '')} · окно {state.get('window')} "
            f"· монет {len(state.get('coins', {}))} "
            f"· запросов {state.get('requests', 0)} "
            f"· ошибок {len(state.get('errors', {}))}")
    lines = [head,
             f"{'монета':<9} {'тейкФ':>6} {'CVDΔ':>9} {'спот':>13}"
             f" {'OI':>8} {'OIΔ%':>7} {'фанд':>8} {'ликв24 Л/Ш':>15}"]
    for coin, c in state.get("coins", {}).items():
        fut, spot, liq = c.get("fut"), c.get("spot"), c.get("liq")
        taker = f"{fut['taker']:.2f}" if fut and fut.get("taker") else "—"
        cvd = _usd(fut.get("cvdChg")) if fut else "—"
        sp = (f"{spot['taker']:.2f}/{_usd(spot.get('cvdChg'))}"
              if spot and spot.get("taker") else "нет")
        oi = _usd(c.get("oiUsd"))
        oip = f"{c['oiChgPct']:+.1f}" if c.get("oiChgPct") is not None else "—"
        fund = f"{c['funding']:.4f}" if c.get("funding") is not None else "—"
        lq = (f"{_usd(liq.get('long24h'))}/{_usd(liq.get('short24h'))}"
              if liq else "—")
        # живой урок: без явных пробелов длинный минус (−431.0M)
        # упирался в спот-колонку и строки слипались
        lines.append(f"{coin:<9} {taker:>6} {cvd:>9} {sp:>13}"
                     f" {oi:>8} {oip:>7} {fund:>8} {lq:>15}")
    for what, why in state.get("errors", {}).items():
        lines.append(f"  ✗ {what}: {why}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Сборщик Coinglass по журналу")
    ap.add_argument("symbols", nargs="*",
                    help="монеты вместо журнала: MAGMA HEMI (можно с USDT)")
    ap.add_argument("--write", action="store_true",
                    help=f"записать срез в {STATE_PATH}")
    a = ap.parse_args()
    state = collect(a.symbols or None, write=a.write)
    print(digest(state))
    if a.write and "write" not in state.get("errors", {}) \
            and not state.get("error"):
        print(f"записано: {STATE_PATH}")
    return 0 if not state.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
