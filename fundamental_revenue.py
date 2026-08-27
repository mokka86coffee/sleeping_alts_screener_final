"""Третий фильтр, замер по журналу: откуда в монете деньги.

Запуск из каталога проекта (нужна сеть):
    python fundamental_revenue.py
    python fundamental_revenue.py --leaders output/leaders.json --latest output/latest.json

Что делает. Берёт монеты журнала лидеров, сопоставляет их с базой
протоколов DeFiLlama по тикеру и спрашивает выручку за 24ч/7д/30д
(бесплатный открытый API, без ключа). Рядом ставит биржевой оборот
монеты из последнего снимка — и печатает отношение: сколько проект
ЗАРАБАТЫВАЕТ на единицу того, что на нём ТОРГУЮТ.

Зачем. Прецедент PROM (22.08): скор 88, оборот $35 млн/сутки, 87%
на CEX — и выручка протокола $681 за квартал. Деньги в монете есть,
но они котировальные, не продуктовые. Для стратегии, которая охотится
за x10–60 на выборочной ленте, это не вето — распилы и мемы тоже
ездят, — но это ФАКТ ДЛЯ КАРТОЧКИ: чем питается монета, продуктом
или только стаканом.

Честные границы метода, до запуска:
- Сопоставление по тикеру неоднозначно: символы в базе Llama не
  уникальны (одноимённые токены), у мемов протокола нет вовсе.
  Совпадений несколько — печатаются все, в JSON идёт сумма с
  пометкой ambiguous; «в базе нет» — это НЕ «выручки нет», это
  «Llama не считает это протоколом», и так и печатается.
- Выручка — по методологии Llama (dailyRevenue: доля протокола, не
  комиссии целиком). Сравнивать между монетами можно, с отчётностью
  компаний — нельзя.

Выход: таблица в консоль + fundamental_revenue.json для будущего
слоя карточки (руками решите, что из него показывать).

ЧТО ЛЕЖИТ В JSON (правка 27.08). Раньше туда шли только суммы, а
главный вывод — отношение выручки к обороту, то самое «деньги
биржевые» — печатался в консоль и терялся. Теперь в файл идут оборот и
отношение, и ТРИ РАЗНЫХ НУЛЯ разведены полем status:
    measured          — выручка есть
    measured_zero     — протокол в базе есть, сборов за окно НЕ БЫЛО
    measured_negative — расходы на стимулы больше сборов (SPK, 27.08)
    no_row            — протокол есть, строки выручки нет
    not_in_db         — монеты нет в базе; это НЕ «выручки нет»
Разница между последними тремя — не формальность: «ноль» это измерение,
«нет строки» это молчание источника, и в карточке они значат разное.

Прогон записывает метку времени: без неё нельзя сказать, к какому дню
относятся числа, а выручка за 30 дней — окно скользящее.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import urllib.request
from pathlib import Path

API_PROTOCOLS = "https://api.llama.fi/protocols"
API_REVENUE = ("https://api.llama.fi/overview/fees"
               "?excludeTotalDataChart=true"
               "&excludeTotalDataChartBreakdown=true"
               "&dataType=dailyRevenue")

# Тикер журнала → тикер токена: множительные префиксы Binance.
MULT_PREFIXES = ("1000000", "10000", "1000")


def _fetch_json(url: str, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "screener/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def base_ticker(symbol: str) -> str:
    t = symbol.upper().removesuffix("USDT")
    for p in MULT_PREFIXES:
        if t.startswith(p) and len(t) > len(p):
            return t[len(p):]
    return t


def load_symbols(leaders_path: Path) -> list[str]:
    """Тикеры журнала. Служебные ключи (_meta и подобные) пропускаются."""
    d = json.loads(leaders_path.read_text(encoding="utf-8"))
    return [k for k in d if not k.startswith("_")]


def load_volumes(latest_path: Path) -> dict[str, float]:
    try:
        d = json.loads(latest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for c in d.get("candidates") or []:
        try:
            out[c["symbol"]] = float(c.get("quote_volume_24h") or 0.0)
        except (TypeError, ValueError, KeyError):
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Выручка протоколов по журналу")
    ap.add_argument("--leaders", default="output/leaders.json")
    ap.add_argument("--latest", default="output/latest.json")
    ap.add_argument("--out", default="fundamental_revenue.json")
    a = ap.parse_args()

    leaders_path = Path(a.leaders)
    if not leaders_path.is_file():
        print(f"✗ журнала {leaders_path} нет")
        return 1
    symbols = load_symbols(leaders_path)
    volumes = load_volumes(Path(a.latest))
    print(f"→ монет в журнале: {len(symbols)}")

    try:
        protocols = _fetch_json(API_PROTOCOLS)
        revenue = _fetch_json(API_REVENUE)
    except Exception as exc:
        print(f"✗ API недоступен: {type(exc).__name__}: {exc}")
        return 1

    # тикер → протоколы базы (символы не уникальны — храним все)
    by_ticker: dict[str, list[dict]] = {}
    for p in protocols if isinstance(protocols, list) else []:
        sym = str(p.get("symbol") or "").upper().strip()
        if sym and sym != "-":
            by_ticker.setdefault(sym, []).append(p)

    # имя/slug протокола → выручка. Ключуем всеми доступными именами:
    # поле сопоставления у Llama разнится (name/displayName/module).
    rev_by_name: dict[str, dict] = {}
    rows = (revenue.get("protocols") if isinstance(revenue, dict) else None) or []
    for r in rows:
        for key in ("name", "displayName", "module", "slug"):
            v = str(r.get(key) or "").lower().strip()
            if v:
                rev_by_name.setdefault(v, r)

    def find_rev(proto: dict) -> dict | None:
        for key in ("name", "slug", "displayName"):
            v = str(proto.get(key) or "").lower().strip()
            if v and v in rev_by_name:
                return rev_by_name[v]
        return None

    n_proto = sum(len(v) for v in by_ticker.values())
    print(f"→ база Llama: протоколов с тикером {n_proto}, "
          f"строк выручки {len(rows)}\n")
    hdr = (f"{'тикер':<9}{'оборот 24ч':>12}{'выручка 30д':>13}"
           f"{'в/о':>9}  протокол")
    print(hdr)
    print("─" * len(hdr))

    out_json: dict[str, dict] = {}
    absent = cheap_n = 0
    for sym in sorted(symbols):
        t = base_ticker(sym)
        vol = volumes.get(sym, 0.0)
        vol_s = f"${vol / 1e6:.1f}m" if vol else "—"
        protos = by_ticker.get(t) or []
        matches = []
        for p in protos:
            r = find_rev(p)
            if r is None:
                continue
            matches.append((p, r))
        if not matches:
            note = ("нет в базе протоколов" if not protos
                    else "протокол без строки выручки")
            print(f"{t:<9}{vol_s:>12}{'—':>13}{'—':>9}  {note}")
            out_json[sym] = {
                "ticker": t, "revenue30d": None, "note": note,
                "volume24h": round(vol, 2) if vol else None,
                "rev_to_vol30d": None,
                # молчание источника и измеренный ноль — разные вещи
                "status": ("not_in_db" if not protos else "no_row"),
            }
            absent += 1
            continue
        r30 = sum(float(r.get("total30d") or 0.0) for _, r in matches)
        names = ", ".join(str(p.get("name")) for p, _ in matches)
        ratio = (r30 / (vol * 30)) if vol else None      # выручка к обороту месяца
        ratio_s = f"{ratio * 100:.3f}%" if ratio is not None else "—"
        cheap = ratio is not None and ratio < 0.0001     # <0.01% оборота
        if cheap:
            cheap_n += 1
        print(f"{t:<9}{vol_s:>12}{'$' + format(r30, ',.0f'):>13}{ratio_s:>9}"
              f"  {names}{' [неоднозначно]' if len(matches) > 1 else ''}"
              f"{' ← деньги биржевые' if cheap else ''}")
        r7 = sum(float(r.get("total7d") or 0.0) for _, r in matches)
        out_json[sym] = {
            "ticker": t, "revenue30d": round(r30, 2),
            "revenue7d": round(r7, 2),
            # оборот и отношение — в файл, а не только на экран
            "volume24h": round(vol, 2) if vol else None,
            "rev_to_vol30d": round(ratio, 8) if ratio is not None else None,
            "status": ("measured_negative" if r30 < 0
                       else "measured_zero" if r30 == 0 else "measured"),
            "protocols": names,
            "ambiguous": len(matches) > 1,
        }

    print(f"\nитог: {len(symbols)} монет | вне базы протоколов: {absent} | "
          f"с выручкой <0.01% месячного оборота: {cheap_n}")

    # МЕТКА ПРОГОНА. Выручка за 30 дней — скользящее окно: без даты
    # нельзя сказать, к какому дню относится число. Прежние описания
    # монет (desc/kind/why), если файл уже размечен руками, сохраняются:
    # они не пересчитываются прогоном и терять их незачем.
    prev = {}
    try:
        prev = json.loads(Path(a.out).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    for sym, row in out_json.items():
        old = prev.get(sym) or {}
        for k in ("desc", "kind", "why", "desc_src", "in_book"):
            if k in old and k not in row:
                row[k] = old[k]
    meta = prev.get("_meta") or {}
    meta["run_at"] = datetime.datetime.now(datetime.timezone.utc)\
        .strftime("%Y-%m-%d %H:%M UTC")
    meta["counts"] = {
        "symbols": len(symbols), "not_in_db_or_no_row": absent,
        "cheap": cheap_n,
    }
    out_json = {"_meta": meta, **out_json}
    Path(a.out).write_text(json.dumps(out_json, ensure_ascii=False, indent=1),
                           encoding="utf-8")
    print(f"✓ {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
