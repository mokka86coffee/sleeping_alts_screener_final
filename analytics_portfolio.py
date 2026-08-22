"""Два подхода к одним монетам: HOLD и трейдинг (Р-29).

Это не «мои позиции против машинных» — монеты одни и те же, журнал
один. Разные ПОДХОДЫ к ним:

    HOLD (инвестирование) — попал в лидеры, взял на $1000, держу.
        Выходов нет, правила не применяются вовсе. Один тезис:
        отобрал — держи.
    ТРЕЙДИНГ — те же монеты, но по правилам: вход, добор, сокращение,
        хедж, выход, повторный вход. Начинает с ПУСТОГО счёта и ведёт
        свою книгу (журнал предположений, analytics_actionlog).

Почему счета РАЗДЕЛЬНЫЕ, а не один. Правила иногда закрывают и
открывают заново — у трейдинга появляются собственные точки входа,
которых у HOLD нет. Считать оба на одной ленте значит смешать две
разные истории и получить число, не описывающее ни одну.

Разница между ними и есть ответ на главный вопрос затеи: стоит ли
торговать то, что можно было просто держать. Плюс — правила
помогают, минус — мешают, около нуля — не отличаются от «купил и
забыл», и тогда весь слой действия не нужен.

ЧТО СЧИТАЕТСЯ ВХОДОМ. Попадание монеты в журнал лидеров и ЕСТЬ вход:
отбор делается затем, чтобы взять. Для HOLD этого достаточно — позиция
открыта и больше ничего не происходит. Трейдинг получает тот же сигнал
входа, но дальше живёт своими правилами.

Размеры — те, что названы человеком (22.08):
    капитал        $1 000 000
    позиция        $1 000 на монету
    добор          $500 (один раз)
Ступень размера (Р-15) режет позицию: половина — $500, четверть — $250.

Чего здесь НЕТ: комиссий, проскальзывания, плеча и налогов. Мы
сравниваем два способа принимать решения на одних и тех же ценах, а
не считаем доходность — для второго нужны данные исполнения, которых
у нас нет и не будет.
"""

from __future__ import annotations

import json
from pathlib import Path

from analytics_actionlog import ACTIONS_LOG
from analytics_decisions import DECISIONS_PATH

CAPITAL_USD = 1_000_000.0
POSITION_USD = 1_000.0
ADD_USD = 500.0

# Доля позиции по ступени размера (Р-15). «Полный» — база.
TIER_SHARE = {"полный": 1.0, "половина": 0.5, "четверть": 0.25}

# Что делает каждое предложение с позицией. Хедж денег не двигает:
# он снимает риск на событие, а не меняет размер — иначе в счёте
# появилась бы прибыль, которой в реальности нет.
OPEN_ACTS = {"брать"}
ADD_ACTS = {"добрать"}
CUT_ACTS = {"сократить"}          # половина позиции
CLOSE_ACTS = {"выйти"}


def _prices(stars: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in stars:
        t = str(s.get("t") or "")
        try:
            px = float(s.get("px") or 0.0)
        except (TypeError, ValueError):
            continue
        if t and px > 0:
            out[t if t.endswith("USDT") else t + "USDT"] = px
    return out


def _tier_of(stars: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for s in stars:
        t = str(s.get("t") or "")
        tier = ((s.get("size") or {}).get("tier") or "полный")
        if t:
            out[t if t.endswith("USDT") else t + "USDT"] = TIER_SHARE.get(tier, 1.0)
    return out


def _machine_ops(path: Path = ACTIONS_LOG) -> list[dict]:
    """Строки журнала предположений по порядку. Нет файла — пусто."""
    out: list[dict] = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        return []
    return out


def _walk(ops: list[dict], prices: dict[str, float],
          tiers: dict[str, float]) -> dict:
    """Прогон операций по порядку. Позиция — доллары и цена входа.

    Средняя цена при доборе считается по деньгам, а не по половинкам:
    добор идёт другой суммой, и среднее арифметическое цен соврало бы.
    """
    pos: dict[str, dict] = {}
    realized = 0.0
    trades = 0

    for op in ops:
        sym = str(op.get("symbol") or "")
        act = str(op.get("act") or "")
        px = float(op.get("price") or 0.0)
        if not sym or px <= 0:
            continue
        p = pos.get(sym)

        if act in OPEN_ACTS and not p:
            usd = POSITION_USD * tiers.get(sym, 1.0)
            pos[sym] = {"usd": usd, "px": px, "added": False}
            trades += 1
        elif act in ADD_ACTS and p and not p["added"]:
            usd = ADD_USD * tiers.get(sym, 1.0)
            total = p["usd"] + usd
            # Средняя по деньгам: цена входа взвешивается вложенным.
            p["px"] = (p["px"] * p["usd"] + px * usd) / total
            p["usd"] = total
            p["added"] = True
            trades += 1
        elif act in CUT_ACTS and p:
            half = p["usd"] / 2.0
            realized += half * (px / p["px"] - 1.0)
            p["usd"] -= half
            trades += 1
            if p["usd"] <= 1e-6:
                pos.pop(sym, None)
        elif act in CLOSE_ACTS and p:
            realized += p["usd"] * (px / p["px"] - 1.0)
            pos.pop(sym, None)
            trades += 1

    invested = sum(p["usd"] for p in pos.values())
    value = 0.0
    unknown = 0
    for sym, p in pos.items():
        now_px = prices.get(sym)
        if not now_px:
            value += p["usd"]        # цены нет — считаем по вложенному
            unknown += 1
            continue
        value += p["usd"] * (now_px / p["px"])
    open_pnl = value - invested

    return {
        "open": len(pos), "invested": round(invested, 2),
        "value": round(value, 2), "openPnl": round(open_pnl, 2),
        "realized": round(realized, 2),
        "pnl": round(open_pnl + realized, 2),
        "pnlPct": (round((open_pnl + realized) / invested * 100, 2)
                   if invested > 0 else None),
        "trades": trades, "unknownPrice": unknown,
        "capitalPct": round(invested / CAPITAL_USD * 100, 3),
    }


def open_trade_positions(path: Path = ACTIONS_LOG) -> dict[str, dict]:
    """Открытые позиции трейдинга: сколько вложено и по какой цене.

    Не просто состав, а РАЗМЕР: вход теперь дробится на части, и
    правило должно знать, сколько уже набрано, чтобы предложить
    добрать остаток плана — или не предлагать, если план выбран.
    """
    pos: dict[str, dict] = {}
    for op in _machine_ops(path):
        sym = str(op.get("symbol") or "")
        act = str(op.get("act") or "")
        if not sym:
            continue
        try:
            usd = float(op.get("usd") or 0.0)
            px = float(op.get("price") or 0.0)
        except (TypeError, ValueError):
            usd = px = 0.0
        p = pos.get(sym)
        if act in OPEN_ACTS and not p:
            pos[sym] = {"usd": usd or POSITION_USD, "px": px,
                        "parts": 1, "plan": float(op.get("plan") or 0.0)}
        elif act in ADD_ACTS and p:
            p["usd"] += usd or ADD_USD
            p["parts"] += 1
        elif act in CUT_ACTS and p:
            p["usd"] /= 2.0
        elif act in CLOSE_ACTS:
            pos.pop(sym, None)
    return pos


def open_trade_symbols(path: Path = ACTIONS_LOG) -> set[str]:
    """Состав книги. Обёртка над open_trade_positions для читателей,
    которым размер не нужен."""
    return set(open_trade_positions(path))


def _hold_book(stars: list[dict]) -> dict:
    """HOLD: КАЖДАЯ монета журнала, по $1000, без выходов.

    Правила к нему не применяются вовсе — в этом весь смысл подхода.
    Позиция открывается попаданием в лидеры и живёт, пока запись в
    журнале; цена входа восстанавливается из хода монеты от входа
    (поле chg), который журнал и так ведёт — отдельного поля не нужно.
    """
    invested = 0.0
    value = 0.0
    n = 0
    for s in stars:
        if s.get("days") is None:
            continue                       # не запись журнала
        try:
            px = float(s.get("px") or 0.0)
            chg = float(s.get("chg") or 0.0)
        except (TypeError, ValueError):
            continue
        if px <= 0:
            continue
        n += 1
        invested += POSITION_USD
        value += POSITION_USD * (1.0 + chg / 100.0)
    pnl = value - invested
    return {
        "open": n, "invested": round(invested, 2),
        "value": round(value, 2), "openPnl": round(pnl, 2),
        "realized": 0.0, "pnl": round(pnl, 2),
        "pnlPct": (round(pnl / invested * 100, 2) if invested > 0 else None),
        "trades": n, "capitalPct": round(invested / CAPITAL_USD * 100, 3),
    }


def _human_ops(path: Path = DECISIONS_PATH) -> list[dict]:
    """Решения человека в виде операций того же вида.

    Размер берётся из записи: человек мог войти иначе, чем предписано,
    и подменять его правилом значит стирать ровно ту разницу, ради
    которой сравнение и затевается. Цена — из поля price, если есть;
    без неё запись в счёт не идёт (нечем считать), но это видно в
    поле skipped.
    """
    out: list[dict] = []
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    for rec in data:
        if not isinstance(rec, dict):
            continue
        act = str(rec.get("action") or "")
        sym = str(rec.get("symbol") or "")
        if not sym or act not in ("вход", "добор", "выход", "сокращение"):
            continue
        out.append({
            "symbol": sym,
            "act": {"вход": "брать", "добор": "добрать",
                    "выход": "выйти", "сокращение": "сократить"}[act],
            "price": rec.get("price"),
            "size": rec.get("size"),
        })
    return out


def _walk_human(ops: list[dict], prices: dict[str, float]) -> dict:
    """То же, но размеры берутся из записей человека, а не из правила."""
    pos: dict[str, dict] = {}
    realized = 0.0
    trades = 0
    skipped = 0

    for op in ops:
        sym, act = op["symbol"], op["act"]
        try:
            px = float(op.get("price") or 0.0)
        except (TypeError, ValueError):
            px = 0.0
        if px <= 0:
            skipped += 1
            continue
        try:
            size = float(op.get("size") or 0.0)
        except (TypeError, ValueError):
            size = 0.0
        p = pos.get(sym)

        if act == "брать" and not p:
            pos[sym] = {"usd": size or POSITION_USD, "px": px}
            trades += 1
        elif act == "добрать" and p:
            usd = size or ADD_USD
            total = p["usd"] + usd
            p["px"] = (p["px"] * p["usd"] + px * usd) / total
            p["usd"] = total
            trades += 1
        elif act == "сократить" and p:
            half = (size or p["usd"] / 2.0)
            half = min(half, p["usd"])
            realized += half * (px / p["px"] - 1.0)
            p["usd"] -= half
            trades += 1
            if p["usd"] <= 1e-6:
                pos.pop(sym, None)
        elif act == "выйти" and p:
            realized += p["usd"] * (px / p["px"] - 1.0)
            pos.pop(sym, None)
            trades += 1

    invested = sum(p["usd"] for p in pos.values())
    value = 0.0
    for sym, p in pos.items():
        now_px = prices.get(sym)
        value += p["usd"] * (now_px / p["px"]) if now_px else p["usd"]
    open_pnl = value - invested
    return {
        "open": len(pos), "invested": round(invested, 2),
        "value": round(value, 2), "openPnl": round(open_pnl, 2),
        "realized": round(realized, 2),
        "pnl": round(open_pnl + realized, 2),
        "pnlPct": (round((open_pnl + realized) / invested * 100, 2)
                   if invested > 0 else None),
        "trades": trades, "skipped": skipped,
        "capitalPct": round(invested / CAPITAL_USD * 100, 3),
    }


def portfolios(stars: list[dict]) -> dict:
    """Два счёта на одних ценах. Пустой журнал — не ошибка, а ноль."""
    prices = _prices(stars)
    tiers = _tier_of(stars)
    return {
        "capital": CAPITAL_USD,
        "position": POSITION_USD,
        "add": ADD_USD,
        # HOLD — журнал целиком по $1000, без правил и без выходов.
        "hold": _hold_book(stars),
        # Трейдинг — только по правилам, начинает с ПУСТОГО счёта.
        "trade": _walk(_machine_ops(), prices, tiers),
        # Ручные записи решений — третий, необязательный счёт: он про
        # то, что человек отметил сам, с размерами и выходами,
        # отличными от базовых. Пуст, пока журнал решений пуст.
        "human": _walk_human(_human_ops(), prices),
    }
