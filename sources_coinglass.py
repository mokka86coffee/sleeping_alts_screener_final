"""Coinglass API v4: живые ликвидации по монетам журнала.

Т-5 из техдолга методов трейдеров получил данные: пользователь завёл
ключ Coinglass. Что берём и почему именно это:

  • COIN LIQUIDATION HISTORY (aggregated-history) — суммы лонг- и
    шорт-ликвидаций по монете. Это живое подтверждение стороны
    каскада (Р-2): «за сутки вынесло лонгов на X» — не догадка по
    свечам, а факт от бирж. Доступна на нижних тарифах.
  • COIN LIQUIDATION MAP (aggregated-map) — карта уровней-кластеров,
    те самые «магниты» из практики ликвидационных карт. По прайсу
    Coinglass она открыта ТОЛЬКО с тарифа Professional; код готов и
    включится сам, как только probe увидит доступ. До того поле
    mapAvailable=false честно говорит «тариф ниже».

Ключ живёт в output/coinglass_config.json (output/ вне git — как у
почты и телеграма; ключ в репозиторий не попадает). Шаблон файла
создаётся сам при первом запуске. БЕЗОПАСНОСТЬ: если ключ засветился
где-то ещё (скриншот, переписка) — перевыпустить в кабинете, это
одна кнопка.

Монеты: журнал (tracked_symbols) + всегда BTC как рыночный фон, с
потолком MAX_COINS — у нижних тарифов жёсткий лимит запросов в
минуту, вся выборка в него не влезает, а журнал — то, чем мы
реально живём. Пауза между запросами держит лимит.

Вызывается из run.py рядом с пульсом; сбой — лог и пропуск. Живая
сверка формата (у меня сети нет, поля обложены терпимым парсером):
    python sources_coinglass.py --probe
"""

from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except ImportError:                      # запуск вне окружения проекта
    BASE_DIR = Path(__file__).resolve().parent
    def log(msg: str) -> None:
        print(msg)

CG_BASE = "https://open-api-v4.coinglass.com"
CONFIG_PATH = BASE_DIR / "output" / "coinglass_config.json"
STATE_PATH = BASE_DIR / "output" / "coinglass_state.json"

MAX_COINS = 25          # журнал + BTC; потолок под лимит запросов/мин
PAUSE_SEC = 0.35        # бережём лимит нижнего тарифа
TIMEOUT = 12

_TEMPLATE = {
    "api_key": "",
    "enabled": True,
    "_help": "ключ из кабинета coinglass.com/account; файл вне git "
             "(output/ в .gitignore). Ключ показывали на скрине — "
             "лучше перевыпустить после вставки сюда.",
}


def _config() -> dict:
    """Конфиг с ключом; при отсутствии — создать шаблон и молчать."""
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        try:
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(_TEMPLATE, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass
        return {}


def _get(path: str, params: dict, api_key: str) -> dict:
    """GET к Coinglass. Возвращает разобранный JSON целиком.

    Ошибки поднимаются наверх: вызывающий решает, что с ними делать
    (сборщик пропускает монету, probe печатает).
    """
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    req = urllib.request.Request(
        f"{CG_BASE}{path}?{qs}",
        headers={"accept": "application/json", "CG-API-KEY": api_key},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(v) -> float:
    try:
        f = float(v)
        return f if f == f else 0.0
    except (TypeError, ValueError):
        return 0.0


def parse_liq_history(doc: dict) -> dict | None:
    """Суммарные ликвидации из ответа aggregated-history.

    Формат обложен терпимо: data — список точек; в точке ищем ключи
    с подстроками long/short + liquidation/usd (регистр любой,
    camelCase режется). Берём СУММУ по всем точкам ответа — интервал
    задаёт запрос, здесь только сложение. Ничего похожего — None,
    а не нули: «не смогли прочитать» отличимо от «ликвидаций не было».
    """
    rows = doc.get("data")
    if isinstance(rows, dict):           # иногда данные завёрнуты глубже
        rows = rows.get("data") or rows.get("list")
    if not isinstance(rows, list) or not rows:
        return None
    long_usd = short_usd = 0.0
    seen = False
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key, val in row.items():
            k = key.lower()
            if "liq" not in k and "usd" not in k:
                continue
            if "long" in k:
                long_usd += _num(val)
                seen = True
            elif "short" in k:
                short_usd += _num(val)
                seen = True
    if not seen:
        return None
    return {"long": round(long_usd, 2), "short": round(short_usd, 2)}


def parse_liq_map(doc: dict) -> list[dict] | None:
    """Кластеры карты: [{price, level}], топ по величине уровня.

    Формат по докам: data.data = {"<цена>": [[цена, уровень, ...]]}.
    Возврат None — карта не читается (обычно 4xx по тарифу).
    """
    data = doc.get("data")
    if isinstance(data, dict):
        data = data.get("data")
    if not isinstance(data, dict) or not data:
        return None
    clusters: list[dict] = []
    for rows in data.values():
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, list) and len(row) >= 2:
                price, level = _num(row[0]), _num(row[1])
                if price > 0 and level > 0:
                    clusters.append({"price": price, "level": level})
    if not clusters:
        return None
    clusters.sort(key=lambda c: -c["level"])
    return clusters[:12]


def _base_coin(sym: str) -> str:
    """BTCUSDT → BTC: Coinglass ходит по монете, не по паре."""
    s = sym.upper()
    for tail in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(tail) and len(s) > len(tail):
            return s[: -len(tail)]
    return s


def collect(symbols: list[str] | None = None) -> str:
    """Шаг прогона: снять ликвидации по журналу + BTC, сложить срез.

    Возвращает строку для лога. Без ключа — тихий пропуск (как почта
    без конфига). Ошибка по монете — пропуск монеты, не прогона.
    """
    cfg = _config()
    key = str(cfg.get("api_key") or "").strip()
    if not key or cfg.get("enabled") is False:
        return "coinglass: нет ключа (output/coinglass_config.json) — пропуск"

    if symbols is None:
        try:
            from analytics_leaders import tracked_symbols
            symbols = sorted(tracked_symbols())
        except Exception:
            symbols = []
    coins: list[str] = []
    for s in ["BTC"] + [_base_coin(x) for x in symbols]:
        if s and s not in coins:
            coins.append(s)
    coins = coins[:MAX_COINS]

    out: dict = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "coins": {}, "mapAvailable": False, "errors": 0}

    # Карта пробуется ОДИН раз на BTC: доступ тарифный, а не помонетный.
    try:
        doc = _get("/api/futures/liquidation/aggregated-map",
                   {"symbol": "BTC", "range": "1d"}, key)
        if parse_liq_map(doc):
            out["mapAvailable"] = True
    except Exception:
        pass
    time.sleep(PAUSE_SEC)

    for coin in coins:
        try:
            doc = _get("/api/futures/liquidation/aggregated-history",
                       {"symbol": coin, "interval": "1h", "limit": 24}, key)
            liq = parse_liq_history(doc)
            if liq:
                out["coins"][coin] = liq
            if out["mapAvailable"]:
                mdoc = _get("/api/futures/liquidation/aggregated-map",
                            {"symbol": coin, "range": "1d"}, key)
                clusters = parse_liq_map(mdoc)
                if clusters:
                    out["coins"].setdefault(coin, {})["map"] = clusters
                time.sleep(PAUSE_SEC)
        except Exception as e:
            out["errors"] += 1
            log(f"coinglass {coin}: {type(e).__name__} — пропуск")
        time.sleep(PAUSE_SEC)

    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                              encoding="utf-8")
    except OSError:
        return "coinglass: срез не записался"
    карта = "карта доступна" if out["mapAvailable"] else "карта закрыта тарифом"
    return (f"coinglass: {len(out['coins'])} монет из {len(coins)}, "
            f"{карта}, ошибок {out['errors']}")


def _probe() -> None:
    """Живой прогон руками: тариф, история BTC, попытка карты."""
    cfg = _config()
    key = str(cfg.get("api_key") or "").strip()
    if not key:
        print(f"впишите ключ в {CONFIG_PATH} и повторите")
        return
    for title, path, params in (
        ("уровень аккаунта", "/api/user/account-subscription", {}),
        ("история ликвидаций BTC",
         "/api/futures/liquidation/aggregated-history",
         {"symbol": "BTC", "interval": "1h", "limit": 3}),
        ("карта ликвидаций BTC (нужен Professional)",
         "/api/futures/liquidation/aggregated-map",
         {"symbol": "BTC", "range": "1d"}),
    ):
        print(f"\n── {title} ──")
        try:
            doc = _get(path, params, key)
            print(json.dumps(doc, ensure_ascii=False)[:700])
            if "history" in path:
                print("разобрано:", parse_liq_history(doc))
            if "map" in path:
                print("кластеров:", len(parse_liq_map(doc) or []))
        except Exception as e:
            print(f"{type(e).__name__}: {e}")


if __name__ == "__main__":
    import sys
    if "--probe" in sys.argv:
        _probe()
    else:
        print(collect())
