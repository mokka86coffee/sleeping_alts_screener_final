"""Пробник Coinglass, вторая версия. Смотрим, что реально приходит,
прежде чем писать сборщик.

    export COINGLASS_KEY=...            # ключ НЕ в коде
    python coinglass_probe.py           # по умолчанию BTC
    python coinglass_probe.py ONG       # по своей монете
    python coinglass_probe.py ONG --raw # печатать сырой ответ целиком
    python coinglass_probe.py --only спот   # только точки со словом в имени

ЧТО ИЗМЕНИЛОСЬ ПРОТИВ ПЕРВОЙ ВЕРСИИ. Первый заход показал, что
фьючерсная половина отвечает целиком, и вскрыл три вещи, из-за которых
список точек переписан.

1. СПОТ. Всё, что пробник спрашивал, было фьючерсным потоком. А
   обязательная строка ежедневного среза — откуп спота: движение на
   спотовом спросе и движение на одном плече это два разных рынка под
   одной свечой, и второй ликвидируют. У Coinglass спотовый раздел
   зеркальный фьючерсному, включая накопленную дельту и приток.

2. СЧЁТ РЕЖИМА. Три величины, которые различают «собирают деньги» и
   «приносят деньги», до сих пор искались по чужим сводкам и сегодня
   не нашлись вовсе. Все три есть точками: отношение фьючерсного
   оборота к спотовому, капитализация стейблкоинов и перевес
   ликвидаций по рынку.

3. РАЗЛОКИ. В перечне есть /coin/unlock-list и /coin/vesting. Если они
   входят в тариф, ручное заполнение unlocks.json отменяется целиком —
   а это была работа на тридцать монет с пересмотром раз в квартал.

ПУТИ. BASE уже кончается на /api, поэтому путь точки пишется БЕЗ него.
В первой версии запись «уровень подписки (v4)» начиналась с /api и
потому давала двойной префикс — здесь исправлено.

ОТКАЗ ВНУТРИ КОДА 200. Coinglass отвечает двумястами и кладёт отказ в
поле code тела: «нет доступа по тарифу» неотличимо от «данных нет»,
если смотреть только на статус. Пробник проверяет и то, и другое.

ЕДИНИЦЫ И ТИПЫ. Числа приходят строками, время в миллисекундах. При
разборе приводить явно, иначе сложение склеит строки в текст.

НЕПОЛНЫЙ ПОСЛЕДНИЙ БАР. Текущий час всегда неполон: в первом заходе
трёхчасовой бар дал триста восемьдесят тысяч против двенадцати
миллионов часом раньше — это не падение активности в тридцать раз, а
незакрытый интервал. Пробник помечает последнюю строку словом
«неполный», чтобы на этом не строить вывод.

ЧТО ПОКАЗАЛИ ДВА ПРОГОНА 29 АВГУСТА. Отказы делятся на четыре
разных случая, и путать их нельзя:
  · четыреста — ошибка в параметрах, чинится нами;
  · четыреста один — точка не входит в тариф Startup, не чинится;
  · четыреста четыре — путь другой, чем в перечне;
  · пятьсот — параметры верные, падает сервер.

ПУСТО — ЭТО ТОЖЕ ОТВЕТ, а не поломка. По MAGMA пусты все три
спотовые точки: спота у монеты нет вовсе на Binance, OKX и Bybit,
и движение оплачивается только плечом. Это ответ на главный вопрос
дня, а не повод чинить запрос.

РАБОТАЮТ: разлоки со всеми полями, ликвидации по полутора тысячам
монет с разбивкой на лонги и шорты, календарь, индекс альтсезона,
доминация, сводный открытый интерес, фандинг, оба списка притоков.

ЛИМИТ Startup — восемьдесят запросов в минуту. Точек стало больше
двадцати, пауза оставлена; сборщику на шестьдесят монет она тем более
нужна.
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

BASE = "https://open-api-v4.coinglass.com/api"
KEY_ENV = "COINGLASS_KEY"

# Вид аргумента: "coin" — монета (ONG), "pair" — пара (ONGUSDT),
# None — точка без символа вовсе.
PROBES = [
    # ── СПОТ. Главное дополнение второй версии ──────────────────────
    # Разлоченные токены и настоящие покупатели приходят на спот, а не
    # на бессрочный контракт. Без этой половины ответ «растёт только
    # плечо» отличить от «растёт спот» нельзя.
    ("спот · тейкерское отношение по монете",
     "/spot/aggregated-taker-buy-sell-volume/history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    # Ошибка была моя: точка просит именно exchange, а я заменил его
    # на exchange_list — ответ прямо сказал «Required String parameter
    # exchange is not present». Возвращено.
    ("спот · тейкерское отношение по паре",
     "/spot/taker-buy-sell-volume/history",
     {"exchange": "Binance", "interval": "1h", "limit": "5"}, "pair"),

    ("спот · накопленная дельта сводная",
     "/spot/aggregated-cvd/history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    ("спот · приток по монете",
     "/spot/coin/netflow", {"interval": "1h", "limit": "5"}, "coin"),

    # Список по всем монетам разом — самая дешёвая точка на монету.
    # У фьючерсного близнеца пришло сто строк с горизонтами от пяти
    # минут до ста двадцати дней и капитализацией рядом; капитализация
    # нужна, чтобы считать поток ОТНОСИТЕЛЬНО размера монеты, а не
    # абсолютом — сравнивать абсолюты между монетами бессмысленно.
    ("спот · список притоков по монетам",
     "/spot/netflow-list", {}, None),

    # НЕ ВХОДИТ В ТАРИФ Startup (четыреста один, «Upgrade plan»).
    # Оставлено, чтобы проверить снова при смене тарифа. Долю спота
    # эта точка не заменяет — она берётся из отношения выше.
    ("спот · рынок по монетам (объём, капитализация)",
     "/spot/coins-markets", {}, None),

    # ── СЧЁТ РЕЖИМА. Три величины, отменяющие нынешнюю рамку ────────
    # Записано заранее: рамка меняется, если ВСЕ ТРИ сдвинулись к
    # притоку и держатся так неделю. Поэтому считать их надо каждый
    # день из одного источника, а не собирать по чужим сводкам.

    # Первая: во сколько раз фьючерсный оборот больше спотового.
    # Величина ПОМОНЕТНАЯ, а не рыночная — и это лучше, чем мы думали:
    # рядом с отношением приходит спотовый оборот в долларах, то есть
    # доля спота считается по каждой монете отдельно. Все три
    # параметра обязательные; без них приходит четырёхсотый внутри
    # кода двести.
    # На MAGMA даёт пятисотую — параметры верные, падает сервер.
    # Вероятная причина: спота у монеты нет вовсе, делить не на что.
    # Проверять на биткоине, где спот заведомо есть.
    ("режим · отношение фьючерсов к споту",
     "/futures_spot_volume_ratio",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    # Вторая: капитализация стейблкоинов. Оборот стейблов к обороту
    # рынка точкой не отдаётся, но капитализация — основа для него.
    ("режим · капитализация стейблкоинов",
     "/index/stableCoin-marketCap-history", {}, None),

    # Третья: перевес ликвидаций по рынку целиком, а не по монете.
    ("режим · ликвидации по всем монетам",
     "/futures/liquidation/coin-list", {"range": "24h"}, None),

    # ── РАЗЛОКИ. Возможная отмена ручного файла ─────────────────────
    # Если обе точки в тарифе — unlocks.json заполняется сам. Проверять
    # надо не только код ответа, но и содержимое: нужны дата, объём и
    # раунд, иначе признак инсайдерского транша не построить.
    # РАБОТАЕТ И ОТДАЁТ ВСЁ, что мы снимали руками с DropsTab: дату
    # ближайшего разлока, сумму в долларах, объём в токенах, долю от
    # циркуляции и долю от общего предложения, плюс заблокированное,
    # циркулирующее и FDV. Ручное заполнение unlocks.json отменяется.
    ("разлоки · ближайшие по рынку",
     "/coin/unlock-list", {}, None),

    ("разлоки · расписание по монете",
     "/coin/vesting", {}, "coin"),

    # ── ФОН РЫНКА ──────────────────────────────────────────────────
    # Календарь: частокол событий с датами, который мы собирались
    # вести руками.
    ("фон · экономический календарь",
     "/calendar/economic-data", {}, None),

    ("фон · индекс альтсезона",
     "/index/altcoin-season", {}, None),

    ("фон · доминация биткоина",
     "/index/bitcoin-dominance", {}, None),

    ("фон · страх и жадность",
     "/index/fear-greed-history", {}, None),

    # ── ФЬЮЧЕРСЫ. Оставлено из первой версии, отвечало ──────────────
    ("фьючерсы · тейкерское отношение по монете",
     "/futures/aggregated-taker-buy-sell-volume/history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    ("фьючерсы · накопленная дельта сводная",
     "/futures/aggregated-cvd/history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    ("фьючерсы · ликвидации по монете",
     "/futures/liquidation/aggregated-history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    ("фьючерсы · список притоков по монетам",
     "/futures/netflow-list", {}, None),

    # Открытый интерес сводный по биржам. У Binance история тридцать
    # дней и только по своей площадке; здесь может быть длиннее и по
    # всем сразу — ради этого и смотрим.
    ("фьючерсы · открытый интерес сводный",
     "/futures/open-interest/aggregated-history",
     {"exchange_list": "Binance,OKX,Bybit", "interval": "1h", "limit": "5"}, "coin"),

    ("фьючерсы · фандинг с весом по интересу",
     "/futures/funding-rate/oi-weight-history",
     {"interval": "1h", "limit": "5"}, "coin"),

    # Крупные лимитные заявки в стакане. У нас крупная заявка
    # выводится из среднего размера сделки за бар и потому одиночную
    # не видит — здесь она названа прямо.
    # НЕ ВХОДИТ В ТАРИФ Startup (четыреста один). У нас крупная
    # заявка и так выводится из размера сделки за бар; здесь она была
    # бы названа прямо, но без неё живём.
    ("фьючерсы · крупные заявки в стакане",
     "/futures/orderbook/large-limit-order", {"exchange": "Binance"}, "pair"),

    # ── СЛУЖЕБНОЕ ──────────────────────────────────────────────────
    # BASE уже содержит /api, поэтому путь пишется без него. В первой
    # версии второй вариант начинался с /api и давал двойной префикс.
    # Четыреста четвёртый: путь в перечне отличается от настоящего.
    # Тариф выясняется и без него — по тому, какие точки отвечают.
    ("уровень подписки", "/user/account-subscription", {}, None),
]


def get(path: str, params: dict, key: str) -> tuple[int, dict | str]:
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={
        "CG-API-KEY": key,          # заголовок именно такой
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body
    except Exception as e:
        return 0, f"{type(e).__name__}: {e}"


def _when(row: dict) -> str:
    """Время строки. Coinglass шлёт миллисекунды, иногда секунды."""
    t = row.get("time") or row.get("timestamp") or row.get("ts") or row.get("date")
    if isinstance(t, str) and t.isdigit():
        t = int(t)
    if not isinstance(t, (int, float)):
        return ""
    if t > 1e11:
        t /= 1000
    try:
        return datetime.fromtimestamp(t, timezone.utc).strftime("%d.%m %H:%M")
    except (OSError, ValueError):
        return ""


def _ratio(vals: dict) -> str:
    """Покупки к продажам, если в строке есть обе стороны."""
    try:
        b = next(float(v) for k, v in vals.items()
                 if "buy" in k.lower() and "sell" not in k.lower())
        s = next(float(v) for k, v in vals.items() if "sell" in k.lower())
        return f"   → отношение {b / s:.3f}" if s else ""
    except (StopIteration, TypeError, ValueError):
        return ""


def _columns(obj: dict) -> list[dict]:
    """Колоночный ответ в строки. Пусто, если форма другая.

    Ключи вида *_list одинаковой длины — это столбцы одной таблицы.
    Время лежит в time_list и переносится в поле time, чтобы дальше
    строка разбиралась тем же путём, что и обычная.
    """
    lists = {k: v for k, v in obj.items()
             if k.endswith("_list") and isinstance(v, list)}
    if len(lists) < 2:
        return []
    n = min(len(v) for v in lists.values())
    if not n:
        return []
    out = []
    for i in range(n):
        row = {}
        for k, v in lists.items():
            row["time" if k == "time_list" else k[:-5]] = v[i]
        out.append(row)
    return out


def show(name: str, code: int, data, raw: bool) -> None:
    print(f"\n{'═' * 62}\n{name}   [код {code}]")
    if raw:
        print(json.dumps(data, ensure_ascii=False, indent=1)[:2500])
        return
    if not isinstance(data, dict):
        print("  ответ не разобрался:", str(data)[:300]); return

    msg = data.get("msg") or data.get("message")
    if msg and str(msg).lower() not in ("success", "ok"):
        print("  сообщение:", msg)

    rows = data.get("data")
    if rows is None:
        print("  поля верхнего уровня:", list(data.keys())[:10]); return
    if isinstance(rows, dict):
        print("  data — объект, поля:", list(rows.keys())[:16])
        # Часть точек (стейблкоины, страх и жадность) отдаёт не строки,
        # а КОЛОНКИ: параллельные списки time_list, price_list,
        # data_list одинаковой длины. Первая версия разборщика такой
        # формы не знала и печатала «пусто» — точка при этом работала.
        cols = _columns(rows)
        rows = cols if cols else (rows.get("list") or rows.get("dataList")
                                  or rows.get("data") or [])
    if not isinstance(rows, list) or not rows:
        print("  data пуст"); return

    print(f"  строк: {len(rows)}")
    first = rows[0]
    if not isinstance(first, dict):
        print("  первая строка:", json.dumps(first, ensure_ascii=False)[:220]); return

    print("  ПОЛЯ:", ", ".join(list(first.keys())[:22]))
    for i, r in enumerate(rows[-3:]):
        vals = {k: v for k, v in r.items()
                if k not in ("time", "timestamp", "ts", "date")}
        # Последняя строка почти всегда незакрытый интервал — на ней
        # легко построить ложный вывод о падении активности.
        tail = "  ← неполный" if i == len(rows[-3:]) - 1 and len(rows) > 1 else ""
        print(f"   {_when(r)}  "
              f"{json.dumps(vals, ensure_ascii=False)[:170]}{_ratio(vals)}{tail}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Пробник Coinglass")
    ap.add_argument("symbol", nargs="?", default="BTC",
                    help="монета БЕЗ USDT: BTC, ONG, HEMI")
    ap.add_argument("--raw", action="store_true", help="печатать сырой ответ")
    ap.add_argument("--only", default="",
                    help="брать только точки, в чьём имени есть это слово")
    a = ap.parse_args()

    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"✗ нет переменной {KEY_ENV}.\n"
              f"  Задайте её так (ключ в код не пишем):\n"
              f"    export {KEY_ENV}=ваш_ключ")
        return 1

    print(f"монета: {a.symbol}   ключ: …{key[-4:]}   "
          f"{datetime.now(timezone.utc):%d.%m %H:%M} UTC")

    coin = a.symbol.upper()
    for tail in ("USDT", "USDC", "USD"):
        if coin.endswith(tail) and len(coin) > len(tail):
            coin = coin[:-len(tail)]; break
    pair = coin + "USDT"
    print(f"монета: {coin}   пара: {pair}")

    probes = [p for p in PROBES if a.only.lower() in p[0].lower()]
    if not probes:
        print(f"✗ по слову «{a.only}» точек не нашлось"); return 1

    ok, denied = 0, []
    for name, path, params, kind in probes:
        p = dict(params)
        if kind == "coin":
            p["symbol"] = coin
        elif kind == "pair":
            p["symbol"] = pair
        code, data = get(path, p, key)
        show(name, code, data, a.raw)

        # Отказ приходит ВНУТРИ тела при коде 200 — смотрим оба поля,
        # иначе «не пустили по тарифу» неотличимо от «данных нет».
        inner = data.get("code") if isinstance(data, dict) else None
        if code == 200 and str(inner) in ("0", "None", "success"):
            ok += 1
        else:
            denied.append(f"{name}  [{code}/{inner}]")
        time.sleep(0.8)          # восемьдесят в минуту — с запасом

    print(f"\n{'═' * 62}\nответили: {ok} из {len(probes)}")
    if denied:
        print("не ответили:")
        for d in denied:
            print("  ·", d)
        print("Причина одна из двух: путь другой или точка не входит в тариф.\n"
              "Покажите вывод — поправлю по фактическому ответу, а не по догадке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
