"""Журнал предположений (Р-28). Что стратегия сказала — и когда.

Зачем. Слой действия (Р-27) — ГИПОТЕЗА. Он не посчитан, не проверен и
пока ничем не заслужил доверия. Единственный способ это изменить —
записывать предложение ЗАРАНЕЕ, с ценой и датой, а потом смотреть, что
вышло. Задним числом «мы бы вышли вовремя» доказать нельзя: память
подстраивается под результат, а лог — нет.

Разделение, которое стоит держать в голове:
    decisions.json  — что решил ЧЕЛОВЕК (Р-14);
    actions_log     — что предложила МАШИНА (этот файл).
Их сравнение и есть проверка стратегии: где предложение совпало с
решением, где разошлось, и кто в каждом случае оказался прав. Смешать
их в один файл значит потерять ровно тот вопрос, ради которого оба
заводились.

Формат — построчный JSON (append-only), одна строка на смену
предложения по монете:

    {"at": "2026-08-22T18:40:00+00:00", "symbol": "BLESSUSDT",
     "act": "сократить", "group": "exit", "price": 0.0093,
     "score": 61, "why": "транш 17% обращения через 8 дн"}

Пишется ТОЛЬКО при смене предложения. Иначе за сутки набежит восемь
одинаковых строк на монету, и в логе утонет ровно то, что мы ищем, —
момент, когда стратегия передумала.

Файл не ротируется и не чистится: это материал замера, а не кэш.
Строка — около полутора сотен байт; при сорока монетах и нескольких
сменах в неделю это единицы мегабайт в год.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from core_config import BASE_DIR

ACTIONS_LOG = BASE_DIR / "output" / "actions_log.jsonl"


def _last_acts(path: Path) -> dict[str, str]:
    """Последнее записанное предложение по каждой монете.

    Читается весь файл: он маленький, а держать отдельный индекс —
    значит завести второй источник истины и однажды его рассинхронить.
    """
    out: dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                sym = rec.get("symbol")
                if sym:
                    out[str(sym)] = str(rec.get("act") or "")
    except OSError:
        return {}
    return out


def log_actions(stars: list[dict], path: Path = ACTIONS_LOG) -> int:
    """Дописывает изменившиеся предложения. Возвращает число строк.

    stars — собранные звёзды: у каждой уже есть act (Р-27), цена и
    скор. Ничего не считает заново: журнал предположений обязан
    записывать ровно то, что видел человек на экране, иначе сравнивать
    будет не с чем.
    """
    if not stars:
        return 0
    prev = _last_acts(path)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []

    for s in stars:
        act = (s.get("act") or {})
        name = str(act.get("act") or "")
        if not name:
            continue
        sym = str(s.get("t") or "")
        if not sym:
            continue
        key = sym if sym.endswith("USDT") else sym + "USDT"
        if prev.get(key) == name:
            continue                      # предложение не менялось
        rec = {
            "at": now, "symbol": key, "act": name,
            "group": str(act.get("group") or ""),
            "why": str(act.get("why") or "")[:180],
        }
        if s.get("px") is not None:
            try:
                rec["price"] = float(s["px"])
            except (TypeError, ValueError):
                pass
        if s.get("score") is not None:
            try:
                rec["score"] = int(s["score"])
            except (TypeError, ValueError):
                pass
        # Сумма операции — чтобы лог читался как учёт, а не как лента
        # намерений: «выйти» без денег не отличить от «подумал выйти».
        # Ступень размера (Р-15) уже посчитана в звезде.
        tier = (s.get("size") or {}).get("tier") or ""
        if tier:
            rec["tier"] = tier
        usd = (s.get("size") or {}).get("usd")
        add = (s.get("size") or {}).get("add")
        if name == "брать" and usd is not None:
            rec["usd"] = usd
        elif name == "добрать" and add is not None:
            rec["usd"] = add
        lines.append(json.dumps(rec, ensure_ascii=False))

    if not lines:
        return 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        return 0
    return len(lines)
