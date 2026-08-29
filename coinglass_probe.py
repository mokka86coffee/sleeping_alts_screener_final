"""Пробник Coinglass. Один прогон по ОДНОЙ монете — посмотреть, что
реально приходит, прежде чем писать сборщик.

    export COINGLASS_KEY=...            # ключ НЕ в коде
    python coinglass_probe.py           # по умолчанию BTC
    python coinglass_probe.py ONG       # по своей монете
    python coinglass_probe.py ONG --raw # печатать сырой ответ целиком

ЗАЧЕМ ОТДЕЛЬНЫЙ ПРОБНИК. Форму ответа нельзя угадать по описанию
тарифа: имена полей, единицы, порядок баров и способ подписи времени
у каждой точки свои. Писать сборщик по догадке — это разбирать чужой
JSON вслепую, а потом искать, почему число не сходится. Дешевле
один раз посмотреть.

ЧТО ПРОВЕРЯЕМ, ЧЕТЫРЬМЯ ЗАПРОСАМИ:
    · тейкерское отношение — агрессивные покупки против продаж.
      По ETH оно ушло на 0.81 (шестилетний минимум) — величина, ради
      которой подписка и бралась;
    · накопленная дельта — второй индикатор из связки, дававшей
      сигнал за пять дней; сами посчитать не можем, нужны сделки;
    · приток и отток по монете — «заводят или выводят», прямой ответ
      на вопрос о разгрузке;
    · история ликвидаций — сторона важнее суммы: 19.08 вынесло шорты,
      26.08 уже лонги.

КЛЮЧ. Только из окружения. В коде его нет и не будет: файл уходит в
репозиторий, в копии проекта и в переписку, а ключ — это оплаченный
доступ. Если переменной нет, скрипт скажет об этом и остановится.

ЛИМИТ Startup — 80 запросов в минуту. Пробник делает четыре, с паузой,
так что упереться невозможно; сборщику на 60 монет пауза уже нужна.
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

# Четыре точки. Пути даны по документации; если какая-то ответит 404
# или «нет доступа», пробник это ПОКАЖЕТ и пойдёт дальше — ради того
# он и написан.
PROBES = [
    ("тейкерское отношение", "/futures/taker-buy-sell-volume/history",
     {"exchange": "Binance", "interval": "1h", "limit": "5"}),
    ("накопленная дельта", "/futures/cumulative-volume-delta/history",
     {"exchange": "Binance", "interval": "1h", "limit": "5"}),
    ("приток и отток", "/futures/net-flow/history",
     {"interval": "1h", "limit": "5"}),
    ("ликвидации", "/futures/liquidation/history",
     {"exchange": "Binance", "interval": "1h", "limit": "5"}),
]


def get(path: str, params: dict, key: str) -> tuple[int, dict | str]:
    url = BASE + path + "?" + urllib.parse.urlencode(params)
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


def show(name: str, code: int, data, raw: bool) -> None:
    print(f"\n{'═' * 62}\n{name}   [код {code}]")
    if raw:
        print(json.dumps(data, ensure_ascii=False, indent=1)[:2500])
        return
    if not isinstance(data, dict):
        print("  ответ не разобрался:", str(data)[:300]); return

    # Coinglass кладёт полезное в data, а рядом code/msg — печатаем и то, и то
    msg = data.get("msg") or data.get("message")
    if msg and str(msg).lower() not in ("success", "ok"):
        print("  сообщение:", msg)
    rows = data.get("data")
    if rows is None:
        print("  поля верхнего уровня:", list(data.keys())[:10]); return
    if isinstance(rows, dict):
        print("  data — объект, поля:", list(rows.keys())[:14])
        rows = rows.get("list") or rows.get("dataList") or []
    if not isinstance(rows, list) or not rows:
        print("  data пуст"); return

    print(f"  строк: {len(rows)}")
    first = rows[0]
    if isinstance(first, dict):
        print("  ПОЛЯ:", ", ".join(list(first.keys())))
        for r in rows[-3:]:
            # время у Coinglass в миллисекундах — переводим, чтобы
            # сразу было видно, свежие данные или вчерашние
            t = r.get("time") or r.get("timestamp") or r.get("ts")
            when = ""
            if isinstance(t, (int, float)) and t > 1e11:
                when = datetime.fromtimestamp(t / 1000, timezone.utc).strftime("%d.%m %H:%M")
            vals = {k: v for k, v in r.items() if k not in ("time", "timestamp", "ts")}
            print(f"   {when}  {json.dumps(vals, ensure_ascii=False)[:190]}")
    else:
        print("  первая строка:", json.dumps(first, ensure_ascii=False)[:220])


def main() -> int:
    ap = argparse.ArgumentParser(description="Пробник Coinglass")
    ap.add_argument("symbol", nargs="?", default="BTC",
                    help="монета БЕЗ USDT: BTC, ONG, HEMI")
    ap.add_argument("--raw", action="store_true", help="печатать сырой ответ")
    a = ap.parse_args()

    key = os.environ.get(KEY_ENV)
    if not key:
        print(f"✗ нет переменной {KEY_ENV}.\n"
              f"  Задайте её так (ключ в код не пишем):\n"
              f"    export {KEY_ENV}=ваш_ключ")
        return 1

    print(f"монета: {a.symbol}   ключ: …{key[-4:]}   {datetime.now(timezone.utc):%d.%m %H:%M} UTC")

    ok = 0
    for name, path, params in PROBES:
        p = dict(params); p["symbol"] = a.symbol
        code, data = get(path, p, key)
        show(name, code, data, a.raw)
        if code == 200:
            ok += 1
        time.sleep(0.8)          # 80/мин — с запасом

    print(f"\n{'═' * 62}\nответили: {ok} из {len(PROBES)}")
    if ok < len(PROBES):
        print("Неответившие — либо другой путь в документации, либо не входят\n"
              "в тариф. Покажите вывод: поправлю пути по фактическому ответу,\n"
              "а не по догадке.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
