#!/usr/bin/env python3
"""Что изменилось в прогнозах за ПОСЛЕДНИЙ прогон (03.09, просьба владельца:
«в сообщение на почту и в тг добавь монеты, у которых появился /
сменился / осечка при каждом прогоне»).

Источник один — output/forecasts.jsonl, тот же ряд, что у журнала
прогнозов: одна запись на монету за прогон (sym, at, hm, px, tpl, stage,
veto). Сравниваются два последних прогона:

  ПОЯВИЛСЯ  монета есть в последнем прогоне с непустым шаблоном, а в
            предыдущем её не было или шаблон был пуст;
  СМЕНИЛСЯ  шаблон в последнем прогоне не тот, что в предыдущем;
  ОСЕЧКА    новый шаблон — развязка против: «осечка», «ушёл»,
            «отпустил», «раздача» (корни имён сюжетов 01.09);
  СНЯТ      шаблон был, стал пустым — монета ушла с полки.

    python3 forecast_diff.py            # печать текста
    python3 forecast_diff.py --json     # словарь

Для писем: text() отдаёт готовый абзац, changes() — словарь. Вызов из
run.py после записи журнала; результат также кладётся в
output/forecast_changes.json, чтобы рассыльщики (send_brief_email,
send_brief_telegram) могли просто прочитать файл, не считая заново.
"""
from __future__ import annotations

import json
from pathlib import Path

MISS_WORDS = ("осечка", "ушёл", "отпустил", "раздача")


def _short(tpl: str) -> str:
    return str(tpl or "").split("(")[0].strip()[:40]


def _is_miss(tpl: str) -> bool:
    t = str(tpl or "").lower()
    return any(w in t for w in MISS_WORDS)


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        if r.get("at") and r.get("sym"):
            out.append(r)
    return out


def changes(path: str | Path = "output/forecasts.jsonl") -> dict:
    """Сравнение двух последних прогонов журнала."""
    rows = _load(Path(path))
    if not rows:
        return {"runs": 0, "new": [], "changed": [], "miss": [], "dropped": []}
    stamp = lambda r: f"{r.get('at')} {r.get('hm') or '00:00'}"
    runs = sorted({stamp(r) for r in rows})
    last = runs[-1]
    prev = runs[-2] if len(runs) > 1 else None
    cur = {str(r["sym"]).upper().replace("USDT", ""): r for r in rows if stamp(r) == last}
    old = {str(r["sym"]).upper().replace("USDT", ""): r for r in rows if prev and stamp(r) == prev}
    new, changed, miss, dropped = [], [], [], []
    for sym, r in sorted(cur.items()):
        tpl, was = _short(r.get("tpl")), _short((old.get(sym) or {}).get("tpl"))
        item = {"sym": sym, "tpl": tpl, "was": was, "px": r.get("px"),
                "stage": r.get("stage") or ""}
        if tpl and not was:
            new.append(item)
        elif tpl and was and tpl != was:
            (miss if _is_miss(tpl) else changed).append(item)
        elif not tpl and was:
            dropped.append(item)
    return {"runs": len(runs), "last": last, "prev": prev,
            "new": new, "changed": changed, "miss": miss, "dropped": dropped}


def text(ch: dict | None = None, path: str | Path = "output/forecasts.jsonl") -> str:
    """Абзац для письма и Телеграма. Пусто, если ничего не менялось."""
    ch = ch or changes(path)
    if not ch.get("runs"):
        return ""
    lines = []
    if ch["miss"]:
        lines.append("✗ осечка: " + " · ".join(f"{i['sym']} — {i['tpl']} (было: {i['was']})" for i in ch["miss"]))
    if ch["new"]:
        lines.append("✦ появился: " + " · ".join(f"{i['sym']} — {i['tpl']}" for i in ch["new"]))
    if ch["changed"]:
        lines.append("↻ сменился: " + " · ".join(f"{i['sym']} — {i['was']} → {i['tpl']}" for i in ch["changed"]))
    if ch["dropped"]:
        lines.append("— снят: " + " · ".join(f"{i['sym']} (был {i['was']})" for i in ch["dropped"]))
    if not lines:
        return "прогнозы за прогон: без изменений"
    return "прогнозы за прогон:\n" + "\n".join(lines)


def write(path: str | Path = "output/forecasts.jsonl",
          out: str | Path = "output/forecast_changes.json") -> dict:
    """Посчитать и положить рядом с журналом: словарь + готовый текст."""
    ch = changes(path)
    ch["text"] = text(ch)
    p = Path(out)
    p.parent.mkdir(exist_ok=True)
    p.write_text(json.dumps(ch, ensure_ascii=False, indent=1), encoding="utf-8")
    return ch


if __name__ == "__main__":
    import sys
    ch = changes()
    if "--json" in sys.argv:
        print(json.dumps(ch, ensure_ascii=False, indent=1))
    else:
        print(text(ch) or "журнал пуст")
