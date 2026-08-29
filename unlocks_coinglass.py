"""Разлоки-автомат (Г-5): расписания Coinglass + сверка с unlocks.json.

Запуск из каталога проекта (сеть нужна, ключ в COINGLASS_KEY):
    python unlocks_coinglass.py             # показать и сверить
    python unlocks_coinglass.py --write     # записать срез
    python unlocks_coinglass.py H HYPE      # только названные монеты

ЧТО ДЕЛАЕТ. Один запрос забирает общий список разлоков (ближайший
транш: дата, деньги, токены, доля обращения). Монетам журнала, которых
в списке нет ИЛИ у которых транш в горизонте (по умолчанию 21 день),
даётся по запросу вестинга: он несёт СОСТАВ транша именованными
аллокациями — и «кому достаётся» частично выводится само. Прецедент
живой формы (H, 29.08): в транше 25.09 инвесторы и ранние
контрибьюторы дают ~51% — грубая метка considered, ступень Р-27
остаётся ручной и решающей.

ЧЕГО НЕ ДЕЛАЕТ. Ручной unlocks.json НЕ ТРОГАЕТ НИКОГДА — правка
данных только с одобрения владельца. Инструмент пишет СВОЙ файл
output/coinglass_unlocks.json (--write), а расхождения с ручным
печатает глазам: прецеденты GUA (4.5% против 17.63%) и PORTAL (в
записи лежала чужая монета Wormhole) показали, что сверка двух
источников ценнее любого из них поодиночке.

УРОКИ ЖИВОЙ ФОРМЫ (29.08, unlock_probe.txt — не переоткрывать):
  - параметр вестинга называется symbol; 'coin' отбивается кодом 400;
  - числа здесь приходят ЧИСЛАМИ (не строками, в отличие от дельт);
  - next_unlock_of_circulating — в ПРОЦЕНТАХ (сверено арифметикой:
    NEAR 2.79M/1304.8M = 0.214 в поле);
  - даты в миллисекундах;
  - у вестинга есть chart помесячной эмиссии — НЕ храним: тяжёлый и
    отвечает на вопрос, которого пока нет; allocations хватает;
  - общий список отсортирован по дате ближайшего транша, пагинация
    не изучена — отсутствие монеты в нём НЕ значит «нет данных»,
    поэтому недостающим даётся вестинг адресно.

ЦЕНА: 1 запрос + по одному на монету без строки в списке или с
траншем в горизонте. На журнале в 25 монет худший случай ~26
запросов и ~40 секунд с паузой 0.8с — лимит Startup не задевается.

Сеть, ключ, разбор отказов внутри кода 200 — ИЗ coinglass_fetch:
один сетевой слой на все инструменты Coinglass, второй разошёлся бы.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from coinglass_fetch import (BASE_DIR, Denied, PAUSE_SEC, _base_coin, _body,
                             _journal_coins, _key, get)

OUT_PATH = BASE_DIR / "output" / "coinglass_unlocks.json"
MANUAL_PATH = BASE_DIR / "unlocks.json"

HORIZON_DAYS = 21          # траншам ближе — вестинг ради состава

# «Заметный» транш: доля обращения, с которой событие перестаёт быть
# дневной каплей линейки. Порог на глаз (0.5%), ждёт калибровки по
# истории влияния; у ручного файла та же идея живёт полем next_big.
SIGNIFICANT_PCT = 0.5
# Капля: ближайший «разлок» сегодня-завтра мельче этой доли — это
# ежедневная линейная эмиссия, а не транш. Урок живого прогона 29.08:
# ATH 0.067% и BMT 0.093% «сегодня» ложно флажились против наших
# клиффов 12.09 и 11.09 — определения у источников разные.
DRIP_PCT = 0.2

# «Кому достаётся» по имени аллокации — грубая метка, НЕ ступень Р-27.
# Неопознанное не голосует (казна, резервы, foundation) — то же
# правило, что у тяжести транша: неизвестное не ужесточает и не
# смягчает.
INSIDER_WORDS = ("invest", "contributor", "team", "advisor", "seed",
                 "private", "founder", "backer", "core")
COMMUNITY_WORDS = ("community", "ecosystem", "reward", "airdrop",
                   "incentive", "public", "launchpool", "staking")


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def _dt(ms) -> str:
    n = _num(ms)
    if not n:
        return "—"
    return datetime.fromtimestamp(n / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _days_to(ms) -> int | None:
    n = _num(ms)
    if not n:
        return None
    return int((n / 1000 - time.time()) // 86400)


def classify_alloc(name: str) -> str:
    low = (name or "").lower()
    if any(w in low for w in INSIDER_WORDS):
        return "insider"
    if any(w in low for w in COMMUNITY_WORDS):
        return "community"
    return "unknown"


def parse_unlock_row(row: dict) -> dict:
    """Строка общего списка → компакт ближайшего транша."""
    out = {
        "nextDate": _dt(row.get("next_unlock_date")),
        "nextDays": _days_to(row.get("next_unlock_date")),
        "nextUsd": _num(row.get("next_unlock_usd")),
        "nextTokens": _num(row.get("next_unlock_tokens")),
        # уже в процентах — см. уроки живой формы в шапке
        "nextPctCirc": _num(row.get("next_unlock_of_circulating")),
        "nextPctSupply": _num(row.get("next_unlock_of_supply")),
        "mcap": _num(row.get("market_cap")),
        "circ": _num(row.get("circulating_supply")),
    }
    _mark(out)
    return out


def _mark(e: dict) -> None:
    """Пометки поверх ближайшего транша: капля и протухшее.

    Протухшее (дата в прошлом дальше чем на два дня) данными не
    является — CETUS на живом прогоне показал транш минус сто
    двенадцать дней; верить такому нельзя, флаг честнее."""
    d, p = e.get("nextDays"), e.get("nextPctCirc")
    if d is not None and d < -2:
        e["stale"] = f"расписание протухло: транш {e.get('nextDate')}"
    elif d is not None and -1 <= d <= 1 and p is not None and p < DRIP_PCT:
        e["drip"] = True


def parse_vesting(doc: dict) -> dict | None:
    """Ответ вестинга → компакт: транш, состав, хвост эмиссии."""
    d = doc.get("data") if isinstance(doc, dict) else None
    if not isinstance(d, dict):
        return None
    nxt = d.get("next_unlock") or {}
    nxt_date = nxt.get("date")
    total_next = _num(nxt.get("next_unlock_token_amount")) or 0.0
    comp, ins, com = [], 0.0, 0.0
    for a in d.get("allocations") or []:
        an = (a.get("next_unlock") or {})
        if _num(an.get("date")) != _num(nxt_date):
            continue
        amt = _num(an.get("next_unlock_token_amount")) or 0.0
        if amt <= 0:
            continue
        cls = classify_alloc(a.get("name") or "")
        comp.append({"name": (a.get("name") or "").strip(),
                     "tokens": amt, "class": cls})
        if cls == "insider":
            ins += amt
        elif cls == "community":
            com += amt
    total_supply = _num(d.get("total_supply"))
    locked = _num(d.get("total_locked"))
    out = {
        "nextDate": _dt(nxt_date),
        "nextDays": _days_to(nxt_date),
        "nextTokens": total_next or None,
        "circ": _num(d.get("circulating_supply")),
        "mcap": _num(d.get("market_cap")),
        "lockedPctSupply": (round(locked / total_supply * 100, 1)
                            if locked and total_supply else None),
        "vestingEnd": _dt(d.get("vesting_end_date")),
        "composition": comp,
    }
    if total_next > 0:
        cov = ins + com
        out["insiderSharePct"] = round(ins / total_next * 100, 1)
        out["communitySharePct"] = round(com / total_next * 100, 1)
        out["unknownSharePct"] = round(max(total_next - cov, 0.0)
                                       / total_next * 100, 1)
    # доля обращения — своя, если есть из чего; в процентах, как у списка
    if total_next and out["circ"]:
        out["nextPctCirc"] = round(total_next / out["circ"] * 100, 4)
    _mark(out)
    # Следующий ЗАМЕТНЫЙ транш — из графика того же ответа (запросов
    # ноль сверху): первый будущий с долей ≥ SIGNIFICANT_PCT. Именно
    # его сверяем с ручным файлом — тот держит клиффы, а не капли.
    circ = out.get("circ")
    if circ:
        now_ms = time.time() * 1000
        for ev in d.get("chart") or []:
            ts = _num(ev.get("date"))
            amt = _num(ev.get("unlocked_token_amount"))
            if not ts or not amt or ts < now_ms:
                continue
            pct = amt / circ * 100
            if pct >= SIGNIFICANT_PCT:
                out["nextBig"] = {"date": _dt(ts), "days": _days_to(ts),
                                  "tokens": amt, "pctCirc": round(pct, 4)}
                break
    return out


def build(symbols: list[str] | None = None, *, key: str | None = None,
          horizon: int = HORIZON_DAYS, verbose: bool = True) -> dict:
    key = key if key is not None else _key()
    if not key:
        return {"error": "нет ключа: export COINGLASS_KEY=… в этом окне"}
    coins = [_base_coin(s) for s in symbols] if symbols else None
    if coins is None:
        coins, note = _journal_coins()
    state: dict = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "coins": {}, "errors": {}, "requests": 0}

    listed: dict[str, dict] = {}
    try:
        doc = _body(*get("/coin/unlock-list", {}, key))
        for row in doc.get("data") or []:
            if isinstance(row, dict) and row.get("symbol"):
                listed[str(row["symbol"])] = row
        if verbose:
            print(f"общий список: {len(listed)} монет", file=sys.stderr)
    except Denied as e:
        state["errors"]["unlock-list"] = str(e)
    state["requests"] += 1
    time.sleep(PAUSE_SEC)

    for coin in coins:
        entry: dict = {"src": "coinglass"}
        row = listed.get(coin)
        if row:
            entry.update(parse_unlock_row(row))
        # Вестинг нужен: строки нет; транш в горизонте (состав);
        # капля или протухшее (в графике лежит следующий заметный).
        need_vesting = (not row) or entry.get("drip") \
            or entry.get("stale") or (
            entry.get("nextDays") is not None
            and 0 <= entry["nextDays"] <= horizon)
        if need_vesting:
            try:
                v = parse_vesting(_body(*get("/coin/vesting",
                                             {"symbol": coin}, key)))
                if v:
                    entry.update({k: val for k, val in v.items()
                                  if val is not None})
                elif not row:
                    entry["absent"] = "нет ни в списке, ни в вестинге"
            except Denied as e:
                state["errors"][coin + " vesting"] = str(e)
            state["requests"] += 1
            time.sleep(PAUSE_SEC)
        state["coins"][coin] = entry
        if verbose:
            nd = entry.get("nextDays")
            line = f"  {coin}: "
            if entry.get("stale"):
                line += "⚠ " + entry["stale"]
            elif entry.get("drip"):
                big = entry.get("nextBig")
                line += "дневная линейка"
                if big:
                    line += (f" · заметный транш {big['date']} "
                             f"({big['days']} дн, {big['pctCirc']:.2f}%)")
            elif nd is not None:
                line += f"транш {entry.get('nextDate')} ({nd} дн)"
            else:
                line += "транш не виден"
            if entry.get("insiderSharePct") is not None:
                line += f" · инсайдерам {entry['insiderSharePct']}%"
            print(line, file=sys.stderr)
    return state


# ── сверка с ручным файлом: печать, никакой записи ──────────────────

def _manual_next_pct_circ(rec: dict) -> float | None:
    """Ручная доля обращения: прямое поле или конвертер из доли
    предложения — та же формула, что у next_pct_float в проекте."""
    direct = _num(rec.get("next_pct_float") or rec.get("next_pct_float_src"))
    if direct:
        return direct
    sup, circ = _num(rec.get("next_pct_supply")), _num(rec.get("circ_pct"))
    if sup and circ:
        return round(sup / circ * 100, 4)
    return None


def verify(state: dict, manual_path: Path = MANUAL_PATH) -> list[str]:
    """Расхождения срез против ручного unlocks.json — строками.

    Флажки: дата разошлась на 2+ дня; доля обращения различается
    больше чем вдвое (порог грубый — прецедент GUA был 4.5 против
    17.63, в четыре раза). Совпадение молчит: сверка ищет беду, а не
    хвалит согласие."""
    try:
        manual = json.loads(Path(manual_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["✗ unlocks.json не прочитан — сверять не с чем"]
    out: list[str] = []
    for coin, cg in (state.get("coins") or {}).items():
        rec = manual.get(coin + "USDT") or manual.get(coin)
        if not isinstance(rec, dict):
            continue
        if cg.get("stale"):
            out.append(f"{coin}: у Coinglass {cg['stale']} — их данным "
                       f"не верить, наша запись остаётся")
            continue
        # Ручной файл держит КЛИФФЫ — сверяем с заметным траншем, а не
        # с дневной каплей линейки (урок ATH/BMT 29.08).
        big = cg.get("nextBig") or {}
        c_date = big.get("date") or cg.get("nextDate")
        c_pct_v = big.get("pctCirc") if big else cg.get("nextPctCirc")
        m_date = str(rec.get("next_date") or "")
        if m_date and c_date and c_date != "—" and m_date != c_date:
            try:
                dd = abs((datetime.strptime(m_date, "%Y-%m-%d")
                          - datetime.strptime(c_date, "%Y-%m-%d")).days)
            except ValueError:
                dd = 999
            if dd >= 2:
                out.append(f"{coin}: дата у нас {m_date}, у Coinglass "
                           f"{c_date} — разъехались на {dd} дн")
        m_pct, c_pct = _manual_next_pct_circ(rec), _num(c_pct_v)
        if m_pct and c_pct and (m_pct / c_pct > 2 or c_pct / m_pct > 2):
            out.append(f"{coin}: доля обращения у нас {m_pct}%, у "
                       f"Coinglass {c_pct}% — больше чем вдвое, "
                       f"профиль GUA/PORTAL, проверить руками")
    return out


_SCREENS_CACHE: dict = {"mtime": None, "data": {}}


def for_screens() -> dict[str, dict]:
    """Срез для ПОКАЗА: тикер → компакт пилюли разлока.

    Читает готовый output/coinglass_unlocks.json без сети, кеш по
    mtime — как for_screens сборщика. Правила чтения: протухшее
    расписание не показывается вовсе; у дневной линейки берётся
    ЗАМЕТНЫЙ транш (клифф), а капля остаётся флагом drip; прошедший
    транш (days < 0) карточке не нужен.
    """
    try:
        mt = OUT_PATH.stat().st_mtime
    except OSError:
        return {}
    if _SCREENS_CACHE["mtime"] == mt:
        return _SCREENS_CACHE["data"]
    try:
        raw = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for sym, e in (raw.get("coins") or {}).items():
        if not isinstance(e, dict) or e.get("stale"):
            continue
        big = e.get("nextBig") or {}
        days = big.get("days", e.get("nextDays"))
        pct = big.get("pctCirc", e.get("nextPctCirc"))
        if days is None or days < 0 or pct is None:
            continue
        rec: dict = {"days": int(days), "pct": round(float(pct), 2)}
        ins = e.get("insiderSharePct")
        if ins is not None:
            rec["ins"] = ins
        if e.get("drip"):
            rec["drip"] = True
        out[sym] = rec
    _SCREENS_CACHE.update(mtime=mt, data=out)
    return out


def auto_update(max_age_hours: float = 24.0) -> str:
    """Суточный контур для врезки в run.py: обновляет срез, только
    если output/coinglass_unlocks.json старше max_age_hours.

    Правило владельца 29.08: ручные контуры живут В ПРОГОНЕ, но
    запускаются ОТ СВЕЖЕСТИ имеющегося файла, а не каждый круг —
    расписания разлоков медленные, и жечь по 26 запросов каждые три
    часа значило бы платить за те же числа. Возвращает строку для
    лога; исключения наружу не выпускает поверх сетевого слоя — сбой
    сборки прогон гасит своим try, как у почты.
    """
    try:
        age_h = (time.time() - OUT_PATH.stat().st_mtime) / 3600
        if age_h < max_age_hours:
            return f"срез свеж ({age_h:.0f} ч) — пропуск"
    except OSError:
        pass                     # файла нет — первый заход, собираем
    state = build(verbose=False)
    if state.get("error"):
        return "✗ " + state["error"]
    try:
        OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1),
                            encoding="utf-8")
    except OSError as e:
        return f"✗ срез собран, но не записался: {e}"
    flags = verify(state)
    tail = ("сверка чиста" if not flags
            else f"⚠ сверка: {len(flags)} — " + "; ".join(flags[:2]))
    return (f"монет {len(state['coins'])}, запросов {state['requests']}, "
            f"ошибок {len(state['errors'])} · {tail}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Разлоки Coinglass + сверка")
    ap.add_argument("symbols", nargs="*", help="монеты вместо журнала")
    ap.add_argument("--write", action="store_true",
                    help=f"записать срез в {OUT_PATH}")
    ap.add_argument("--horizon", type=int, default=HORIZON_DAYS,
                    help="дни до транша, при которых берётся вестинг")
    a = ap.parse_args()
    state = build(a.symbols or None, horizon=a.horizon)
    if state.get("error"):
        print("✗", state["error"])
        return 1
    near = sorted((c for c, e in state["coins"].items()
                   if e.get("nextDays") is not None and e["nextDays"] >= 0),
                  key=lambda c: state["coins"][c]["nextDays"])
    print(f"\nмонет: {len(state['coins'])} · запросов: {state['requests']}"
          f" · ошибок: {len(state['errors'])}")
    for c in near[:10]:
        e = state["coins"][c]
        usd = e.get("nextUsd")
        print(f"  {c:<9} {e.get('nextDate')} · {e.get('nextDays')} дн"
              + (f" · ${usd / 1e6:.2f}M" if usd else "")
              + (f" · {e.get('nextPctCirc'):.2f}% обращения"
                 if e.get("nextPctCirc") else "")
              + (f" · инсайдерам {e['insiderSharePct']}%"
                 if e.get("insiderSharePct") is not None else ""))
    for what, why in state["errors"].items():
        print(f"  ✗ {what}: {why}")
    flags = verify(state)
    if flags:
        print("\nСВЕРКА с unlocks.json — расхождения:")
        for f in flags:
            print("  ⚠", f)
    else:
        print("\nсверка с unlocks.json: расхождений нет")
    if a.write:
        try:
            OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
            OUT_PATH.write_text(json.dumps(state, ensure_ascii=False,
                                           indent=1), encoding="utf-8")
            print(f"записано: {OUT_PATH}")
        except OSError as e:
            print(f"✗ не записалось: {e}")
            return 1
    else:
        print("(ничего не записано: --write, когда срез выглядит честным; "
              "unlocks.json этот инструмент не трогает никогда)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
