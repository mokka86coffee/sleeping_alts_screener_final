"""Hyperliquid: съём позиций отслеживаемых китов и контекста рынка.

Т-1 из техдолга методов трейдеров. Лидерборд Hyperliquid публичен,
но официальный info-API списка топов не отдаёт — он отдаёт ПОЗИЦИИ
ЛЮБОГО адреса (clearinghouseState). Поэтому источник устроен так:
СПИСОК китов ведёт человек — ручной файл hl_whales.json в корне
(адреса берутся с любого трекера лидерборда; брать имена, устойчиво
сидящие на недельных и месячных досках, 5–15 штук), а код по этому
списку тянет позиции одним запросом на адрес и складывает срез в
output/hl_state.json. Дальше сеть не нужна: analytics_hyperliquid
читает готовый файл.

Оговорка из тех же источников, зашитая в смысл поля: киты —
КОНТЕКСТ, не сигнал на копирование. Крупные счета бывают
хеджированы, маркет-мейкерят или просто неправы; их перекос по
монете — довесок к нашим правилам, не замена.

Вызывается из run.py рядом с пульсом; любой сбой — лог и пропуск,
прогон не роняется. Формат ответа API обложен get'ами: первый живой
прогон — проверка; ручная проба формата:
    python sources_hyperliquid.py --probe 0xАДРЕС
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except ImportError:                      # запуск вне окружения проекта
    BASE_DIR = Path(__file__).resolve().parent
    def log(msg: str) -> None:
        print(msg)

HL_INFO_URL = "https://api.hyperliquid.xyz/info"
# Неофициальный, но публичный срез лидерборда (официальный info-API
# списка топов не отдаёт). Схема обложена get'ами; сверка руками:
#     python sources_hyperliquid.py --probe-board
HL_BOARD_URL = "https://stats-data.hyperliquid.xyz/Mainnet/leaderboard"
WHALES_PATH = BASE_DIR / "hl_whales.json"          # ручной файл, в корне
STATE_PATH = BASE_DIR / "output" / "hl_state.json" # срез, вне git

# ── Авто-пополнение списка китов ──
# Прогон сам ходит на лидерборд и держит в файле секцию "auto":
# до AUTO_N живых МУЛЬТИМОНЕТНЫХ трейдеров. Фильтр — не поля доски
# (Volume там пуст у всех, а верх по счёту — холдеры HYPE), а сам
# probe: кандидат берётся, только если clearinghouseState показал
# ≥ AUTO_MIN_COINS перп-позиций. Ручной список "addresses" —
# неприкосновенен: авто его не трогает и не дублирует. Отбор
# перезапускается не чаще AUTO_REFRESH_HOURS; выключается
# AUTO_ENABLED = False.
AUTO_ENABLED = True
AUTO_N = 10                 # сколько авто-китов держать
AUTO_SCAN = 60              # сколько верхних строк доски пробовать
AUTO_MIN_COINS = 3          # мультимонетность: перп-позиций от
AUTO_REFRESH_HOURS = 24
AUTO_SKIP_NAMES = ("vault", "hlp")   # пулы и ММ-хранилища — мимо

WHALES_TEMPLATE = {
    "addresses": [
        {"addr": "", "label": "пример: топ-3 недельной доски"},
    ],
    "auto": [],
    "_note": ("Адреса китов Hyperliquid. Секцию addresses ведёт "
              "человек — она неприкосновенна. Секцию auto прогон "
              "пополняет сам с лидерборда: живые мультимонетные "
              "трейдеры (проверка позициями, не полями доски), "
              "обновление раз в AUTO_REFRESH_HOURS."),
}


def _post(payload: dict, timeout: int = 15) -> object:
    """POST на info-эндпоинт. Только стандартная библиотека: у
    проекта нет зависимости от requests, и заводить её ради одного
    вызова незачем."""
    import urllib.request
    req = urllib.request.Request(
        HL_INFO_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _positions_of(addr: str) -> dict:
    """Позиции одного адреса: {COIN: {szi, entryPx, valueUsd, pnl}}.

    szi > 0 — лонг, szi < 0 — шорт (соглашение Hyperliquid).
    Неожиданный формат не роняет сбор — просто пустой словарь.
    """
    try:
        raw = _post({"type": "clearinghouseState", "user": addr})
    except Exception as e:
        log(f"  hl: {addr[:10]}… не прочитан: {type(e).__name__}: {e}")
        return {}
    out: dict = {}
    for ap in (raw or {}).get("assetPositions") or []:
        pos = (ap or {}).get("position") or {}
        coin = pos.get("coin")
        try:
            szi = float(pos.get("szi") or 0)
        except (TypeError, ValueError):
            continue
        if not coin or not szi:
            continue
        def _f(key):
            try:
                return float(pos.get(key))
            except (TypeError, ValueError):
                return None
        out[str(coin).upper()] = {
            "szi": szi,
            "entryPx": _f("entryPx"),
            "valueUsd": _f("positionValue"),
            "pnl": _f("unrealizedPnl"),
        }
    return out


def _get(url: str, timeout: int = 20) -> object:
    import urllib.request
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _board_rows() -> list[dict]:
    """Строки лидерборда, приведённые к [{addr, name, pnl_w, pnl_m}].

    Схема неофициального среза может отличаться от ожидания — всё
    через get, неожиданное просто пропускается. windowPerformances
    встречается и списком пар, и словарём.
    """
    data = _get(HL_BOARD_URL)
    rows = data.get("leaderboardRows") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("лидерборд: неожиданная схема ответа")
    out: list[dict] = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        addr = r.get("ethAddress") or r.get("user") or r.get("address")
        if not addr:
            continue
        perf = r.get("windowPerformances")
        if isinstance(perf, list):
            perf = {str(k): v for k, v in perf
                    if isinstance(v, dict)} if all(
                        isinstance(p, (list, tuple)) and len(p) == 2
                        for p in perf) else {}
        if not isinstance(perf, dict):
            perf = {}
        def _pnl(win: str) -> float:
            try:
                return float((perf.get(win) or {}).get("pnl"))
            except (TypeError, ValueError):
                return 0.0
        out.append({"addr": str(addr),
                    "name": str(r.get("displayName") or ""),
                    "pnl_w": _pnl("week"), "pnl_m": _pnl("month")})
    return out


def _auto_pick(manual: set[str]) -> list[dict]:
    """Живые мультимонетные киты с верха доски.

    Кандидаты — зелёные и на неделе, и на месяце, без Vault/HLP и
    без дублей ручного списка; решает не доска, а probe: берётся
    только счёт с ≥ AUTO_MIN_COINS перп-позициями.
    """
    import time as _t
    rows = [r for r in _board_rows()
            if r["pnl_w"] > 0 and r["pnl_m"] > 0
            and r["addr"].lower() not in manual
            and not any(x in r["name"].lower() for x in AUTO_SKIP_NAMES)]
    rows.sort(key=lambda r: -r["pnl_m"])
    picked: list[dict] = []
    scanned = 0
    for r in rows[:AUTO_SCAN]:
        scanned += 1
        pos = _positions_of(r["addr"])
        _t.sleep(0.15)
        if len(pos) < AUTO_MIN_COINS:
            continue
        coins = sorted(pos, key=lambda c: -(pos[c].get("valueUsd") or 0))
        picked.append({
            "addr": r["addr"], "auto": True,
            "label": (f"авто: pnl мес ${r['pnl_m'] / 1e6:.1f}M, "
                      f"{len(pos)} монет ({', '.join(coins[:3])}…)")})
        if len(picked) >= AUTO_N:
            break
    log(f"  hl-авто: просмотрено {scanned}, отобрано {len(picked)}")
    return picked


def _maybe_refresh_auto(doc: dict) -> bool:
    """Обновляет секцию auto по TTL. True — файл нужно перезаписать."""
    if not AUTO_ENABLED:
        return False
    from datetime import datetime, timezone
    meta = doc.get("_auto") or {}
    try:
        last = datetime.fromisoformat(meta.get("at") or "")
        fresh = (datetime.now(timezone.utc) - last).total_seconds()             < AUTO_REFRESH_HOURS * 3600
    except ValueError:
        fresh = False
    if fresh and doc.get("auto"):
        return False
    manual = {(w.get("addr") or "").lower()
              for w in (doc.get("addresses") or [])}
    try:
        picked = _auto_pick(manual)
    except Exception as e:
        log(f"  hl-авто: лидерборд не разобран "
            f"({type(e).__name__}: {e}) — секция auto не тронута")
        return False
    doc["auto"] = picked
    doc["_auto"] = {"at": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds"),
                    "picked": len(picked)}
    return True


def collect_hyperliquid(candidates: list | None = None) -> str:
    """Шаг прогона: срез позиций китов → output/hl_state.json.

    candidates не обязателен: срез пишется по ВСЕМ позициям китов —
    сопоставление с выборкой делает analytics-слой на чтении (монета
    может войти в журнал завтра, а срез уже будет).
    """
    if not WHALES_PATH.exists():
        WHALES_PATH.write_text(
            json.dumps(WHALES_TEMPLATE, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return ("список китов пуст — создан шаблон hl_whales.json, "
                "заполните адреса")
    try:
        doc = json.loads(WHALES_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"hl_whales.json не прочитан: {e}"
    if _maybe_refresh_auto(doc):
        WHALES_PATH.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2),
            encoding="utf-8")
    whales = [w for w in ((doc.get("addresses") or []) +
                          (doc.get("auto") or []))
              if (w.get("addr") or "").startswith("0x")]
    if not whales:
        return ("в hl_whales.json нет адресов (и авто-отбор пуст) — "
                "срез пропущен")

    state: dict = {"whales": {}}
    ok = 0
    for w in whales:
        addr = w["addr"]
        pos = _positions_of(addr)
        if pos:
            ok += 1
        state["whales"][addr] = {"label": w.get("label") or "",
                                 "positions": pos}
    from datetime import datetime, timezone
    state["_meta"] = {"at": datetime.now(timezone.utc)
                      .isoformat(timespec="seconds"),
                      "asked": len(whales), "answered": ok}
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                          encoding="utf-8")
    return f"{STATE_PATH} · китов опрошено {ok} из {len(whales)}"


if __name__ == "__main__":
    import sys
    if "--probe-board" in sys.argv:
        raw = _get(HL_BOARD_URL)
        print(json.dumps(raw, ensure_ascii=False, indent=1)[:1500])
        rows = _board_rows()
        print(f"\n→ строк разобрано: {len(rows)}; первые:")
        for r in rows[:5]:
            print(f"  {r['addr'][:12]}… pnl нед ${r['pnl_w']:,.0f} "
                  f"мес ${r['pnl_m']:,.0f} {r['name']}"
                  .replace(",", " "))
        sys.exit(0)
    if "--probe" in sys.argv:
        addr = sys.argv[sys.argv.index("--probe") + 1]
        raw = _post({"type": "clearinghouseState", "user": addr})
        print(json.dumps(raw, indent=1)[:1200])
        # Вердикт человеку: верх лидерборда по размеру счёта забит
        # ХОЛДЕРАМИ HYPE (одинаковый ROI ~ рост монеты, объём $0,
        # в эксплорере — TokenDelegate): перпов у них нет, и в
        # список китов такие не годятся. Годится тот, у кого есть
        # живые перп-позиции.
        pos = _positions_of(addr)
        print(f"\n→ перп-позиций: {len(pos)}")
        if not pos:
            print("  счёт без перпов — вероятно холдер/стейкер "
                  "(делегирование, объём $0). В список китов НЕ "
                  "годится: перекос мерить не по чему.")
        else:
            for coin, p in sorted(pos.items(),
                                  key=lambda x: -(x[1]["valueUsd"] or 0))[:5]:
                side = "лонг" if p["szi"] > 0 else "шорт"
                print(f"  {coin:<8} {side} ${p['valueUsd']:,.0f}"
                      .replace(",", " "))
            print("  живой трейдер — в hl_whales.json годится.")
    else:
        print(collect_hyperliquid())
