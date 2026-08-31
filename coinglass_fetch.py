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
    запрос на монету. Окно — 24 ЗАКРЫТЫХ часа (карточка просит ряд
    тейкера за сутки); в срез кладётся и свод, и РЯД по барам
    (t / tk / cvd) — по ряду считаются метки зала.
  · СПОТОВАЯ ДЕЛЬТА /spot/aggregated-cvd/history — зеркало: имена
    полей подтверждены живьём 29.08 и совпадают с фьючерсными. Пустой
    ответ у перповой монеты (MAGMA: спота нет на Binance, OKX, Bybit)
    — это ОТВЕТ «движение оплачено плечом», а не поломка; в срезе
    поле spot = null.
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
ликвидаций: на двадцати пяти монетах это ~101 запрос; пауза 0.8 с
ПЛЮС сетевая задержка дают две-три минуты. Показ печатается один раз
в конце, поэтому ХОД РАБОТЫ идёт строками в stderr — счёт монет,
ориентир времени, строка на монету: тишина не должна выглядеть
зависанием (живой урок 29.08). Потолок MAX_COINS держит лимит;
расширять вместе с паузой, не вместо неё.
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
STATE_PATH = BASE_DIR / "output" / "coinglass_fetch.json"


def _bad_key(msg) -> bool:
    """Отказ именно по КЛЮЧУ (не по тарифу) — повод остановить прогон:
    мёртвый ключ убьёт каждый следующий запрос точно так же."""
    m = str(msg).lower()
    return "api key" in m or "apikey" in m


def _key_stop(err) -> str:
    return (f"ключ не принят Coinglass ({err}) — прогон остановлен, лимит "
            f"не жжём. Задайте свежий В ЭТОМ окне терминала: export "
            f"{KEY_ENV}=… — переменная живёт только в окне, где её задали; "
            f"новое окно — задать заново")


EXCHANGES = "Binance,OKX,Bybit"     # как в пробнике
INTERVAL = "1h"
WINDOW = 24                         # закрытых баров: сутки — просит карточка
MAX_COINS = 80        # предохранитель от разбухшего журнала, не норма:
#   29.08 выяснилось, что потолок 25 МОЛЧА резал журнал из 62 монет —
#   срез выглядел здоровым, а следил за третью списка. Теперь потолок
#   с запасом, а усечение печатается причиной (см. _journal_coins).
PAUSE_SEC = 0.8                     # восемьдесят в минуту — с запасом
TIMEOUT = 20

LIQ_WINDOWS = ("24h", "12h", "4h", "1h")


# ── сеть ────────────────────────────────────────────────────────────

# Остаток лимита из заголовков ответа (01.09). Тариф Startup —
# восемьдесят запросов в минуту; прогон идёт примерно на сорока
# четырёх, то есть на половине. Но это прикидка по секундомеру, а
# решать про частоту надо по числу от самого источника. Заголовков
# может и не быть — тогда строка честно скажет, что их нет.
RATE = {"last": None, "seen": 0}


def get(path: str, params: dict, key: str) -> tuple[int, dict | str]:
    """Как в пробнике: (HTTP-код, разобранное тело либо текст)."""
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "CG-API-KEY": key,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            for _h, _v in r.headers.items():
                if any(w in _h.lower() for w in
                       ("ratelimit", "rate-limit", "x-remain", "quota",
                        "credit", "retry-after")):
                    RATE["last"] = f"{_h}={_v}"
                    RATE["seen"] += 1
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
    """Тейкер и дельта из aggregated-cvd — свод ПЛЮС ряд по барам.

    Имена полей у спота подтверждены живьём 29.08 и совпадают с
    фьючерсными до буквы (agg_taker_buy_vol / agg_taker_sell_vol /
    cum_vol_delta); терпимый разбор оставлен на случай переименований.
    Ряд series = [{"t": мс, "tk": тейкер бара, "b"/"s": объёмы сторон,
    "cvd": накопленная}] — его просят метки зала («тейкер падает»,
    «дельта перевернулась»: объёмы дают ВЗВЕШЕННЫЕ половины) и
    ветвь «продавец» карточки; свод остаётся для показа строкой.
    Возврат None — данных нет (пустой data): у перповых монет так
    выглядит спот, и это ответ, а не ошибка.
    """
    rows = _closed(_rows(doc))
    if not rows:
        return None
    buy = sell = 0.0
    seen = False
    series: list[dict] = []
    cvd_first = cvd_last = None
    for r in rows:
        b = _pick(r, ("buy",), avoid=("sell",))
        s = _pick(r, ("sell",))
        c = _pick(r, ("delta",))
        if c is None:
            c = _pick(r, ("cvd",))
        if b is not None:
            buy += b; seen = True
        if s is not None:
            sell += s; seen = True
        if c is not None:
            if cvd_first is None:
                cvd_first = c
            cvd_last = c
        t = r.get("time") or r.get("timestamp") or r.get("ts")
        series.append({
            "t": int(t) if isinstance(t, (int, float)) else None,
            "tk": round(b / s, 3) if (b is not None and s) else None,
            "b": round(b, 2) if b is not None else None,
            "s": round(s, 2) if s is not None else None,
            "cvd": round(c, 2) if c is not None else None,
        })
    if not seen and cvd_last is None:
        return None
    out: dict = {"buyUsd": round(buy, 2), "sellUsd": round(sell, 2),
                 "taker": round(buy / sell, 3) if sell > 0 else None,
                 "bars": len(rows), "series": series}
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

def _halves(series: list) -> dict | None:
    """Сутки пополам: тейкер и дельта каждой половины.

    Взвешенный тейкер половины = сумма покупок / сумма продаж (ноги
    b/s в барах v3.1). Без ног — среднее tk половины: хуже, но не
    враньё. Дельта половины — приращение cvd; у первой теряется час.
    """
    n = len(series)
    if n < 8:
        return None
    mid = n // 2
    out = {}
    for tag, part in (("1", series[:mid]), ("2", series[mid:])):
        buys = [b.get("b") for b in part]
        sells = [b.get("s") for b in part]
        if all(v is not None for v in buys + sells) and sum(
                v or 0 for v in sells):
            out["tk" + tag] = round(sum(buys) / sum(sells), 3)
        else:
            tks = [b.get("tk") for b in part if b.get("tk") is not None]
            if tks:
                out["tk" + tag] = round(sum(tks) / len(tks), 3)
    c0 = series[0].get("cvd")
    cm = series[mid - 1].get("cvd")
    cl = series[-1].get("cvd")
    if None not in (c0, cm, cl):
        out["d1"] = round(cm - c0, 0)
        out["d2"] = round(cl - cm, 0)
    return out or None


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
    if len(coins) > MAX_COINS:
        # Усечение — только вслух: тихий обрез 29.08 прятал две трети
        # журнала, и никто не знал.
        note = ((note + " · ") if note else "") + (
            f"журнал {len(coins)} монет, взято {MAX_COINS} "
            f"(потолок MAX_COINS)")
    return coins[:MAX_COINS], note


def _key() -> str:
    """Ключ ТОЛЬКО из окружения — правило владельца, теперь в коде буквально.

    Запасной ход через output/coinglass_config.json убран 29.08 после
    живого сбоя: переменная окружения живёт в том окне терминала, где
    её задали, — в новом окне её нет, и запасной ход молча подсунул
    старый отозванный ключ; сотня запросов ушла бы впустую. Честный
    отказ сразу лучше тихой подмены ключа.
    """
    return os.environ.get(KEY_ENV, "").strip()


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


def _say(msg: str, on: bool) -> None:
    """Ход работы — в stderr: stdout остаётся чистым показом."""
    if on:
        print(msg, file=sys.stderr, flush=True)


def collect(symbols: list[str] | None = None, *,
            key: str | None = None, write: bool = False,
            verbose: bool = True) -> dict:
    """Срез по журналу (или названным монетам). write=False — не пишет.

    verbose=True печатает ход в stderr (счёт монет, ориентир времени,
    строка на монету) — иначе две-три минуты тишины выглядят
    зависанием; для врезки в run.py можно передать verbose=False.
    """
    key = key if key is not None else _key()
    if not key:
        return {"error": f"нет ключа: задайте export {KEY_ENV}=… в этом "
                         f"окне терминала — переменная живёт только в окне, "
                         f"где её задали; новое окно — задать заново"}
    coins = [_base_coin(s) for s in symbols] if symbols else None
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "window": f"{WINDOW}x{INTERVAL}", "coins": {},
                   "errors": {}, "requests": 0}
    if coins is None:
        coins, note = _journal_coins()
        if note:
            state["errors"]["журнал"] = note

    total = len(coins) * 4 + 1
    secs = total * (PAUSE_SEC + 0.6)          # пауза + сетевая задержка
    orient = (f"~{secs / 60:.0f}–{secs * 1.6 / 60:.0f} мин" if secs >= 60
              else f"~{secs:.0f} с")
    _say(f"coinglass: ключ …{key[-4:]}, монет {len(coins)}, "
         f"запросов ~{total}, ориентир {orient}; показ придёт в конце",
         verbose)

    # Ликвидации по всем монетам — один запрос на весь журнал.
    liq_all: dict[str, dict] = {}
    try:
        doc = _body(*get("/futures/liquidation/coin-list",
                         {"range": "24h"}, key))
        liq_all = parse_liq_list(doc)
        _say(f"  общий список ликвидаций: {len(liq_all)} монет", verbose)
    except Denied as e:
        state["errors"]["liq-list"] = str(e)
        _say(f"  общий список ликвидаций: отказ {e}", verbose)
        if _bad_key(e):
            state["error"] = _key_stop(e)
            _say("  " + state["error"], verbose)
            state["requests"] += 1
            return state
    state["requests"] += 1
    time.sleep(PAUSE_SEC)

    import sys as _sys
    import time as _time
    _t0 = _time.time()
    for i, coin in enumerate(coins, 1):
        # Пульс (30.08): «зависло на коинглассе» оказалось долгой
        # сетью — 273 тихих запроса. Каждые 15 монет — строка ходу
        # в stderr, всегда: молчание дольше минуты пугает владельца
        # сильнее, чем лишняя строка в логе.
        if i % 15 == 1 and i > 1:
            _sys.stderr.write(
                f"    coinglass: {i}/{len(coins)} монет, "
                f"{_time.time() - _t0:.0f} с\n")
            _sys.stderr.flush()
        entry = snap_coin(coin, key, state["errors"])
        state["requests"] += 4
        entry["liq"] = liq_all.get(coin)
        state["coins"][coin] = entry
        bad = sum(1 for k in state["errors"] if k.startswith(coin + " "))
        _say(f"  {i}/{len(coins)} {coin}"
             + (f" — ошибок {bad}" if bad else ""), verbose)
        dead = next((v for v in state["errors"].values() if _bad_key(v)),
                    None)
        if dead:
            state["error"] = _key_stop(dead)
            _say("  " + state["error"], verbose)
            break

    if write and not state.get("error"):
        try:
            STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            STATE_PATH.write_text(
                json.dumps(state, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            state["errors"]["write"] = "срез не записался"
    return state


# ── показ ───────────────────────────────────────────────────────────

# ── интерфейс для экранов (Г-1) ────────────────────────────────────

_SCREENS_CACHE: dict = {"mtime": None, "data": {}}


def for_screens() -> dict[str, dict]:
    """Срез для ПОКАЗА: тикер → компактный словарь карточки зала.

    Читает готовый output/coinglass_fetch.json (его пишет врезка в
    run.py) и НЕ ходит в сеть: экраны собираются из файла, как пульс.
    Кеш по mtime — за сборку страниц вызовов несколько, файл один.
    Нет файла или он битый — пустой словарь: карточка просто молчит,
    это показ, а не отбор.
    """
    try:
        mt = STATE_PATH.stat().st_mtime
    except OSError:
        return {}
    if _SCREENS_CACHE["mtime"] == mt:
        return _SCREENS_CACHE["data"]
    try:
        raw = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for sym, c in (raw.get("coins") or {}).items():
        if not isinstance(c, dict):
            continue
        fut = c.get("fut") or {}
        spot = c.get("spot") or {}
        liq = c.get("liq") or {}
        spot_usd = (spot.get("buyUsd") or 0) + (spot.get("sellUsd") or 0)
        fut_usd = (fut.get("buyUsd") or 0) + (fut.get("sellUsd") or 0)
        out[sym] = {
            "at": raw.get("at"),
            "taker": fut.get("taker"),
            "cvdChg": fut.get("cvdChg"),
            "spotUsd": spot_usd or None,
            "spotTaker": spot.get("taker"),
            "oiChgPct": c.get("oiChgPct"),
            # Г-2: отношение фьючерсного оборота к спотовому — из ТЕХ ЖЕ
            # ног объёма, что уже в срезе; отдельная точка Coinglass не
            # нужна (экономия 25 запросов/прогон). Спот пуст → None:
            # «делить не на что» — это ответ перповой монеты, не ошибка.
            "fsRatio": (round(fut_usd / spot_usd, 1)
                        if spot_usd and fut_usd else None),
            # Половины суток для меток строк зала (Г-15, прототип):
            # tk — тейкер половин, ВЗВЕШЕННО по ногам b/s, когда бар
            # их несёт (срез v3.1+); старый срез без ног — честное
            # среднее tk по барам. d — дельта половин из накопленного
            # cvd; первый час первой половины теряется — накопление
            # стартует не с нуля окна, и это записано, а не довраано.
            "halves": _halves(fut.get("series") or []),
            # Хвост дельты для мини-ряда «формы суток» (29.08): боевой
            # компакт не нёс рядов, и спарк в карточке был пуст —
            # стенд кормился полным series и промаха не видел.
            "cvdSpark": [round(b.get("cvd") or 0, 0)
                         for b in (fut.get("series") or [])[-24:]],
            "liqLong": liq.get("long24h"),
            "liqShort": liq.get("short24h"),
        }
    _SCREENS_CACHE.update(mtime=mt, data=out)
    return out


def _usd(v) -> str:
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:.1f}{suf}"
    return f"{v:.0f}"


def _hot_coins(limit: int = 10) -> list[str]:
    """Монеты, ради которых стоит ходить чаще часа.

    Полный обход — двести восемьдесят пять запросов и шесть с
    половиной минут; учетверить его нельзя, тариф Startup даёт
    восемьдесят запросов в минуту. Но и незачем: между часовыми
    прогонами интересны единицы монет, а не весь журнал.

    Берём три источника, все уже лежат в output/ и считать заново
    нечего: сюжеты растущего класса из репутаций, открытые позиции
    книги и лидер прогона. Ничего нет — короткий круг молчит.
    """
    hot: list[str] = []

    def add(sym):
        c = _base_coin(str(sym or "").upper())
        if c and c not in hot:
            hot.append(c)

    rp = Path("output/reputation.json")
    if rp.exists():
        try:
            for sym, e in (json.loads(rp.read_text(encoding="utf-8"))
                           or {}).items():
                if sym == "_meta" or not isinstance(e, dict):
                    continue
                head = str(e.get("plot") or "").split(":")[0]
                if any(m in head for m in ("крупняк", "курок взведён",
                                           "кит набирает тихо")):
                    add(sym)
        except ValueError:
            pass

    for name in ("output/book.json", "book.json", "output/positions.json"):
        p = Path(name)
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            continue
        rows = d.values() if isinstance(d, dict) else d
        for r in rows:
            if isinstance(r, dict):
                add(r.get("symbol") or r.get("sym") or r.get("t"))
            else:
                add(r)
        break

    lp = Path("output/leaders_last.json")
    if lp.exists():
        try:
            add((json.loads(lp.read_text(encoding="utf-8"))
                 or {}).get("leader"))
        except ValueError:
            pass
    return hot[:limit]


def digest(state: dict) -> str:
    """Одна строка на монету; интерпретаций нет — только числа."""
    if state.get("error"):
        return "coinglass: " + state["error"]
    head = (f"coinglass-срез {state.get('at', '')} · окно {state.get('window')} "
            f"· монет {len(state.get('coins', {}))} "
            f"· запросов {state.get('requests', 0)} "
            f"· ошибок {len(state.get('errors', {}))}"
            + (f" · лимит: {RATE['last']}" if RATE["last"]
               else " · лимит: заголовков нет"))
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
    ap.add_argument("--hot", action="store_true",
                    help="короткий круг: только кандидаты, книга и лидер")
    a = ap.parse_args()
    syms = a.symbols or None
    if a.hot and not syms:
        syms = _hot_coins()
        if not syms:
            print("короткий круг: горячих монет нет — пропуск")
            return 0
        print(f"короткий круг: {len(syms)} монет · {' '.join(syms)}")
    state = collect(syms, write=a.write)
    print(digest(state))
    if a.write and "write" not in state.get("errors", {}) \
            and not state.get("error"):
        print(f"записано: {STATE_PATH}")
    return 0 if not state.get("error") else 1


if __name__ == "__main__":
    sys.exit(main())
