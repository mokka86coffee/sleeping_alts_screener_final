"""Помощник резервуара (Р-20) на CoinMarketCap.

Запуск из каталога проекта (нужна сеть):
    python reservoir_fetch.py           # только показать
    python reservoir_fetch.py --write   # дописать в reservoir.json

ЧТО ЭТО. Резервуар — единственное место проекта, где правило «ноль
запросов» нарушено осознанно: одно число в неделю, руками. Скрипт
снимает рутину, а РЕШЕНИЕ оставляет человеку: по умолчанию ничего не
пишет, только показывает и печатает готовую строку для вставки.

ИСТОЧНИК — CoinMarketCap, БЕЗ КЛЮЧА. Ключ нужен лишь для больших
объёмов, нам хватает трёх запросов в неделю. Прежняя версия ходила в
CoinGecko и считала долю стейблов САМА, складывая капитализации монет
из списка топ-20. Здесь доля приходит готовой вместе с доминацией — и
это тот же расчёт, что показан на самом сайте, а не наша самодельная
сумма по короткому списку.

ЧТО ЗАБИРАЕМ, тремя запросами:
    /v1/global-metrics/quotes/latest — доминация BTC и ETH, доля
        стейблов в капитализации, полная капитализация рынка;
    /v1/altcoin-season-index/latest  — индекс альтсезона: сколько монет
        из топ-100 обошли биткоин за 90 дней. Ровно тот вопрос, ради
        которого резервуар и заведён;
    /v3/fear-and-greed/latest        — жадность, для фона.

ПОЧЕМУ ЭТО БОЛЬШЕ, ЧЕМ ЗАМЕНА ИСТОЧНИКА. Резервуарный контур отвечает
на вопрос альтсезона: деньгам, которым предстоит поднять альты,
сначала надо выйти из доллара. Доля стейблов показывает, вышли ли;
индекс альтсезона — дошли ли до альтов. Две половины одного вопроса, и
обе теперь приходят сами.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path

try:                                  # в проекте путь берётся из конфига
    from core_config import BASE_DIR  # noqa
except Exception:                     # запуск в одиночку — рядом с файлом
    BASE_DIR = Path(__file__).resolve().parent

RESERVOIR_PATH = BASE_DIR / "reservoir.json"

# Keyless-корень. Ключ НЕ нужен, и заголовок с ним слать нельзя.
CMC = "https://pro-api.coinmarketcap.com/public-api"
EP_GLOBAL = CMC + "/v1/global-metrics/quotes/latest?convert=USD"
EP_ALTSEASON = CMC + "/v1/altcoin-season-index/latest"
EP_FEAR = CMC + "/v3/fear-and-greed/latest"

# Границы правдоподобия: доля стейблов вне коридора почти наверняка
# означает не рынок, а сломанный ответ.
SANE = (3.0, 40.0)


def _get(url: str, tries: int = 4):
    """GET с отступом при 429. Документация прямо предупреждает:
    keyless-запросы делят общий счётчик по адресу, и короткая пауза его
    освобождает. Без этого один занятый сосед ломает наш прогон."""
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429 and i < tries - 1:
                time.sleep(2 ** i)          # 1с, 2с, 4с
                continue
            raise
    raise RuntimeError("не удалось получить ответ")


def measure() -> dict:
    """Три запроса — всё, что нужно резервуару и немного сверх."""
    g = (_get(EP_GLOBAL).get("data") or {})
    q = (g.get("quote") or {}).get("USD") or {}

    total = float(q.get("total_market_cap") or 0.0)
    stable_cap = float(q.get("stablecoin_market_cap") or 0.0)
    stable_vol = float(q.get("stablecoin_volume_24h") or 0.0)

    out = {
        "total_usd": total,
        "stables_usd": stable_cap,
        # ГОТОВАЯ доля от всего рынка, а не наша сумма по списку монет
        "pct_global": round(stable_cap / total * 100, 2) if total else None,
        "btc_dom_pct": round(float(g.get("btc_dominance") or 0.0), 2),
        "eth_dom_pct": round(float(g.get("eth_dominance") or 0.0), 2),
        "stable_vol_usd": stable_vol,
        # Оборот стейблов к их капитализации: сколько раз за сутки
        # оборачивается «сухой порох». Такой величины у нас не было, а
        # она отличает лежащие деньги от работающих.
        "stable_turnover": (round(stable_vol / stable_cap, 3)
                            if stable_cap else None),
        "active_coins": g.get("active_cryptocurrencies"),
    }

    # Индекс альтсезона и жадность не критичны: упали — значит просто
    # нет в выдаче, а не весь замер насмарку.
    try:
        a = (_get(EP_ALTSEASON).get("data") or {})
        out["altseason"] = a.get("altcoin_index") or a.get("value")
    except Exception:
        out["altseason"] = None

    try:
        f = (_get(EP_FEAR).get("data") or {})
        out["fear_greed"] = f.get("value")
        out["fear_greed_name"] = f.get("value_classification")
    except Exception:
        out["fear_greed"] = None

    return out


def load_rows(path: Path) -> list[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    ap = argparse.ArgumentParser(description="Резервуар по данным CoinMarketCap")
    ap.add_argument("--write", action="store_true", help="дописать в reservoir.json")
    ap.add_argument("--min-gap", type=int, default=5,
                    help="не писать, если последняя запись свежее N дней")
    ap.add_argument("--force", action="store_true", help="писать, несмотря на min-gap")
    ap.add_argument("--path", default=str(RESERVOIR_PATH))
    a = ap.parse_args()

    try:
        m = measure()
    except Exception as exc:
        print(f"✗ источник недоступен: {type(exc).__name__}: {exc}")
        return 1

    print(f"→ рынок целиком      ${m['total_usd'] / 1e12:.3f}T")
    print(f"→ стейблы            ${m['stables_usd'] / 1e9:.1f}B  = "
          f"{m['pct_global']}% капитализации")
    if m.get("stable_turnover"):
        print(f"→ оборот стейблов    ×{m['stable_turnover']} от их капитализации за сутки")
    print(f"→ доминация BTC      {m['btc_dom_pct']}%   ETH {m['eth_dom_pct']}%")
    if m.get("altseason") is not None:
        print(f"→ индекс альтсезона  {m['altseason']} из 100")
    if m.get("fear_greed") is not None:
        print(f"→ жадность           {m['fear_greed']} · {m.get('fear_greed_name')}")

    share = m["pct_global"]
    if share is None or not (SANE[0] <= share <= SANE[1]):
        print(f"✗ доля {share} вне коридора {SANE[0]}–{SANE[1]}% — "
              f"это не рынок, а сломанный ответ. Не записываю.")
        return 1

    today = date.today().isoformat()
    row = {"date": today, "stables_pct": round(share, 1),
           "btc_dom_pct": m["btc_dom_pct"],
           "src": "coinmarketcap", "method": "global"}
    if m.get("altseason") is not None:
        row["altseason"] = m["altseason"]
    if m.get("stable_turnover") is not None:
        row["stable_turnover"] = m["stable_turnover"]

    print(f"\nстрока для reservoir.json:\n  {json.dumps(row, ensure_ascii=False)},")

    if not a.write:
        print("\n(ничего не записано: добавьте --write, если срез совпадает с рядом)")
        return 0

    path = Path(a.path)
    rows = load_rows(path)
    if rows:
        last = rows[-1]
        if str(last.get("date")) == today:
            print("✗ запись за сегодня уже есть — ряд не лог, "
                  "второй раз за день не пишем")
            return 1

        # СМЕНА СРЕЗА — главная защита этого скрипта. Прежние записи
        # снимались вручную с другого среза (доля от топ-20). Доля от
        # ВСЕГО рынка — другая величина; дописать её в тот же ряд
        # значит сломать сравнимость: модуль печатает ход к предыдущей
        # записи, и первый же замер покажет движение, которого на
        # рынке не было.
        prev_method = str(last.get("method") or "top20")
        if prev_method != "global":
            print(f"✗ последняя запись снята способом «{prev_method}», "
                  f"а CMC даёт долю от ВСЕГО рынка. Смена среза ломает "
                  f"сравнимость ряда — начните новый файл, а не "
                  f"дописывайте сюда.")
            return 1

        try:
            gap = (date.today() - datetime.strptime(
                str(last.get("date")), "%Y-%m-%d").date()).days
        except ValueError:
            gap = 999
        if gap < a.min_gap and not a.force:
            print(f"✗ последняя запись {gap} дн назад, порог {a.min_gap}. "
                  f"Контур недельный; если правда нужно — --force")
            return 1

    rows.append(row)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                    encoding="utf-8")
    print(f"✓ дописано в {path} (записей: {len(rows)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
