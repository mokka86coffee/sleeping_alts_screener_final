#!/usr/bin/env python3
"""Журнал прогнозов (правка №3 списка 31.08, сделана 01.09).

ЗАЧЕМ. Без него нельзя отличить плохой шаблон от плохого рынка.
31.08 весь список — ONG, BMT, TRUMP, STX — ушёл в минус, и это ничего
не сказало о шаблонах: биткоин в тот день минус три с половиной,
корреляция альтов ноль восемьдесят семь. Один день не улика; улика —
статистика по шаблону за месяц, где видно, что «набор кита» держит, а
«дёрг» нет.

ЧТО ПИШЕТ. Каждый прогон дописывает строку на монету, у которой есть
сюжет: тикер, шаблон, стадия, цена в момент записи, был ли фон против.
Одна запись на монету в сутки — прогон ежечасный, и двадцать четыре
одинаковых строки только испортили бы счёт.

ЧЕМ МЕРИТ ИСХОД. Дневками архива cq_v2, а не своей памятью: цена
через день и через три берётся из ohlcv по дате. Поэтому исход
проставляется задним числом и не зависит от того, работал ли прогон в
нужный час.

ЧЕГО НЕ ДЕЛАЕТ. Не решает, хороший шаблон или плохой, и не трогает
пороги. Считает и показывает; выводы — человеку.

Запуск отдельно, чтобы посмотреть накопленное:
    python3 forecast_log.py --report
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

LOG = Path("output") / "forecasts.jsonl"
ARCHIVE = Path("cq_v2")
HORIZONS = (1, 3)          # через сколько дней меряем исход


def _today() -> str:
    return date.today().isoformat()


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue                      # битая строка не рушит журнал
    return out


def _write(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False)
                             for r in rows) + "\n", encoding="utf-8")
    tmp.replace(path)


def _closes(base: str, archive: Path) -> dict:
    """Дата → закрытие по дневкам архива. Пусто — монеты в архиве нет."""
    fp = archive / f"{base.lower()}.json"
    if not fp.exists():
        return {}
    try:
        d = json.loads(fp.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return {str(r.get("datetime") or "")[:10]: r.get("close")
            for r in (d.get("ohlcv") or []) if r.get("close")}


def gate_against(md: Path = Path("REGIME_GATE.md")) -> bool:
    """Работает ли фаза против списка — по вердикту гейта.

    Читаем файл сами, а не просим снимок: снимок несёт режим ВЫБОРКИ
    (доля зелёных), а это другая величина, и путать их нельзя.
    """
    for c in (md, Path(__file__).resolve().parent / md.name):
        if not c.exists():
            continue
        try:
            t = c.read_text(encoding="utf-8")
        except OSError:
            continue
        for ln in t.splitlines():
            if ln.startswith("ВЕРДИКТ"):
                v = ln.lower()
                return ("раздача" in v or "тянет деньги" in v
                        or "сосёт" in v)
    return False


def record(rep: dict, against: bool | None = None,
           log_path: Path = LOG) -> int:
    """Записать сегодняшний список сюжетов. Сколько строк добавлено.

    На вход — карта репутаций (та же, что уходит в
    output/reputation.json). Звёзды не нужны: сюжет и стадия живут
    здесь, а цену для счёта берём из дневок архива — тогда вход и
    исход меряются одним рядом, а не смесью дневки с внутриднём.

    Пишем ВСЕ монеты с сюжетом, а не только кандидатов: через месяц
    надо будет сравнить «Пойдёт?» с полкой «уже идёт» и с теми, кого
    фильтр не пустил вовсе. Отсев на чтении дешевле, чем нехватка
    данных.
    """
    rows = _read(log_path)
    today = _today()
    have = {(r.get("at"), r.get("sym")) for r in rows}
    if against is None:
        against = gate_against()
    added = 0
    for sym, e in (rep or {}).items():
        if sym == "_meta" or not isinstance(e, dict):
            continue
        plot = str(e.get("plot") or "")
        sym = str(sym).upper()
        if not plot or (today, sym) in have:   # одна запись в сутки
            continue
        rows.append({
            "at": today, "sym": sym,
            "tpl": plot.split(":")[0].strip()[:60],
            "stage": e.get("stage") or "",
            "veto": bool(against),
        })
        have.add((today, sym))
        added += 1
    if added:
        _write(log_path, rows)
    return added


def score(log_path: Path = LOG, archive: Path = ARCHIVE) -> int:
    """Проставить исходы там, где срок уже прошёл. Идемпотентна."""
    rows = _read(log_path)
    if not rows:
        return 0
    cache: dict[str, dict] = {}
    today = date.today()
    filled = 0
    for r in rows:
        try:
            d0 = datetime.strptime(r.get("at", ""), "%Y-%m-%d").date()
        except ValueError:
            continue
        base = str(r.get("sym") or "").lower().removesuffix("usdt")
        if base not in cache:
            cache[base] = _closes(base, archive)
        cl = cache[base]
        if not cl:
            continue
        # Цена входа — ТОЛЬКО из дневок: запись сделана днём, а
        # дневка этого дня появится назавтра. Ждём её.
        p0 = cl.get(r["at"])
        if not p0:
            continue
        for h in HORIZONS:
            key = f"ret{h}d"
            if r.get(key) is not None:
                continue
            dn = d0 + timedelta(days=h)
            if dn > today:
                continue              # срок ещё не вышел
            p1 = cl.get(dn.isoformat())
            if not p1:
                continue              # дневки ещё нет — вернёмся позже
            r[key] = round((float(p1) / float(p0) - 1) * 100, 1)
            filled += 1
    if filled:
        _write(log_path, rows)
    return filled


def report(log_path: Path = LOG) -> str:
    """Сводка по шаблонам: сколько, сколько в плюс, медиана хода."""
    rows = [r for r in _read(log_path) if r.get("ret3d") is not None]
    if not rows:
        return "журнал прогнозов пуст или исходы ещё не созрели"
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(f"{r.get('tpl','?')} [{r.get('stage') or '—'}]",
                      []).append(r)
    def med(xs):
        xs = sorted(xs)
        n = len(xs)
        return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2
    out = [f"журнал прогнозов: записей с исходом {len(rows)}", ""]
    for k in sorted(by, key=lambda k: -len(by[k])):
        g = by[k]
        r1 = [x["ret1d"] for x in g if x.get("ret1d") is not None]
        r3 = [x["ret3d"] for x in g]
        up = sum(1 for x in r3 if x > 0)
        out.append(f"{k}")
        out.append(f"   n={len(g):<3} в плюс через 3 дня {up}/{len(r3)}"
                   f" · медиана 1д {med(r1):+.1f}% 3д {med(r3):+.1f}%"
                   if r1 else
                   f"   n={len(g):<3} в плюс через 3 дня {up}/{len(r3)}"
                   f" · медиана 3д {med(r3):+.1f}%")
    veto = [r for r in rows if r.get("veto")]
    if veto:
        r3v = [r["ret3d"] for r in veto]
        r3n = [r["ret3d"] for r in rows if not r.get("veto")]
        out += ["", f"фон против: n={len(veto)} медиана 3д {med(r3v):+.1f}%"
                    + (f" · без вето {med(r3n):+.1f}%" if r3n else "")]
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--log", default=str(LOG))
    a = ap.parse_args()
    lp = Path(a.log)
    if a.score or not a.report:
        print(f"исходов проставлено: {score(lp)}")
    if a.report:
        print(report(lp))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
