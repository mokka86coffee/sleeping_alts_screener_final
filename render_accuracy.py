#!/usr/bin/env python3
"""ЭКРАН ТОЧНОСТИ (07.09) — accuracy.html: дни → часы → монеты.

ВНИМАНИЕ: в проекте с 01.09 уже есть render_journal.py со своей страницей journal.html —
это ДРУГОЙ экран, он не трогается. Этот модуль называется иначе и пишет accuracy.html.

Владелец: «нужно сделать список сначала по дням, где мы будем показывать, какое количество
прогнозов сбылось, какое нет. Дальше при нажатии на день мы попадаем в список по часам…
и при входе в конкретный час нужно показывать, какие монеты из первых, сколько ушли по цене».
Плюс 07.09: «при заходе в часы показывать, какой рынок открыт, идёт, скоро закроется».

Данные — output/entries_score.json (08.09: ТОЛЬКО заходы в первые и в очередь, а не смены шаблонов
по всей доске) и output/market_bg.jsonl (фон на момент: risk on, биткоин, состояние рынков)
Ничего не считает
сам: если считалка не отработала, экран покажет, что журнал пуст, и не соврёт числами.

Сбылось = цена дошла до ближайшей полосы СВЕРХУ раньше, чем до полосы снизу и раньше срока
(три границы, а не фиксированный процент: ход, измеренный на одну отметку, не видит пути).

    python3 render_accuracy.py            # печать длины и краткой сводки
    python3 render_accuracy.py --write    # → <REPORT_PATH>/accuracy.html
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR, REPORT_PATH
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    REPORT_PATH = BASE_DIR / "output" / "index.html"
sys.path.insert(0, str(BASE_DIR))

OUTD = BASE_DIR / "output"
DOW = {0: "понедельник", 1: "вторник", 2: "среда", 3: "четверг", 4: "пятница", 5: "суббота", 6: "воскресенье"}


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(p: Path) -> list[dict]:
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def _bg_rows() -> list[dict]:
    return _jsonl(OUTD / "market_bg.jsonl")


def _bg_for(bgs: list[dict], prefix: str) -> dict:
    """Последняя строка фона, попавшая в этот день (YYYY-MM-DD) или час (…THH)."""
    got = [b for b in bgs if str(b.get("at", "")).startswith(prefix)]
    return got[-1] if got else {}


def _bg_text(b: dict) -> str:
    if not b:
        return ""
    ro, btc = b.get("risk_on") or {}, (b.get("btc") or {}).get("day_pct")
    parts = []
    if ro.get("appetite"):
        parts.append(f"risk on <b>{ro['appetite']}/5</b>")
    if btc is not None:
        parts.append(f"биткоин <b>{btc:+.1f}%</b>")
    ld = b.get("leaders") or {}
    if ld.get("mine_n") is not None and ld.get("n"):
        parts.append(f"лидеры наши <b>{ld['mine_n']} из {ld['n']}</b>")
    return " · ".join(parts)


def _markets(b: dict) -> list[list]:
    """Пилюли рынков: имя, состояние, часы, класс подсветки."""
    out = []
    for m in ((b.get("time") or {}).get("markets") or []):
        st = m.get("state") or ""
        cls = "on" if m.get("open") and st == "идёт" else ("soon" if "скоро" in st else "")
        left = m.get("left_h") if m.get("open") else m.get("in_h")
        out.append([m.get("name"), st, left or 0, cls])
    return out


def build_data() -> dict:
    """ПО ДНЯМ — МОНЕТЫ, ПОБЫВАВШИЕ В ПЕРВЫХ (08.09, владелец: «куча бесполезной информации,
    которая имеет смысл только для расчётов; нужно в плашках по дням показывать монеты, которые
    были в первых, их максимальную и минимальную цену за день, и на каких позициях они были в
    течение дня — примерно так 1→3→2→1; если выпала из очереди вообще, то точное время, и это
    будет конец прогноза»).

    Ничего не считаем сами: путь по местам берём из ленты очереди, цены — из внутридневного архива.
    Кривые, MFE, MAE, разрезы по фону остаются в entries_score.json для расчётов, на экран не идут.
    """
    q = [r for r in _jsonl(OUTD / "queue_log.jsonl") if r.get("at") and r.get("sym")]
    q.sort(key=lambda r: (str(r.get("at")), r.get("place") or 99))
    runs = sorted({r["at"] for r in q})
    by_run: dict[str, dict] = {}
    for r in q:
        by_run.setdefault(r["at"], {})[r["sym"]] = r

    # по дням: кто был в первых хоть раз
    days_map: dict[str, dict] = {}
    for t in runs:
        day = t[:10]
        d = days_map.setdefault(day, {})
        for sym, row in by_run[t].items():
            pl = row.get("place")
            if not pl:
                continue
            e = d.setdefault(sym, {"path": [], "times": [], "first": t, "px_in": row.get("px"),
                                   "top": False, "gone": None})
            if not e["path"] or e["path"][-1] != pl:
                e["path"].append(pl)
                e["times"].append(t)
            if pl <= 3:
                e["top"] = True
        # кто был в прошлом прогоне и пропал — конец прогноза
        prev = runs[runs.index(t) - 1] if runs.index(t) else None
        if prev and prev[:10] == day:
            for sym in by_run[prev]:
                if sym not in by_run[t] and sym in d and not d[sym]["gone"]:
                    d[sym]["gone"] = t

    days = []
    for day in sorted(days_map, reverse=True):
        coins = []
        for sym, e in days_map[day].items():
            if not e["top"]:
                continue
            bars = [r for r in _bars(sym) if str(r.get("candle", ""))[:10] == day and r.get("px")]
            pxs = [r["px"] for r in bars]
            lo = min(pxs) if pxs else None
            hi = max(pxs) if pxs else None
            now = pxs[-1] if pxs else None
            coins.append({
                "s": sym.replace("USDT", ""),
                "path": " → ".join(str(p) for p in e["path"]),
                "best": min(e["path"]),
                "in_at": e["first"][11:16],
                "px": e["px_in"],
                "lo": lo, "hi": hi, "now": now,
                "up": round((hi / e["px_in"] - 1) * 100, 1) if (hi and e["px_in"]) else None,
                "dn": round((lo / e["px_in"] - 1) * 100, 1) if (lo and e["px_in"]) else None,
                "end": round((now / e["px_in"] - 1) * 100, 1) if (now and e["px_in"]) else None,
                "gone": e["gone"][11:16] if e["gone"] else None,
            })
        coins.sort(key=lambda c: (c["best"], c["in_at"]))
        if coins:
            try:
                dow = DOW[datetime.strptime(day, "%Y-%m-%d").weekday()]
            except ValueError:
                dow = ""
            days.append({"d": day, "dow": dow, "coins": coins})
    return {"days": days, "at": datetime.now(timezone.utc).strftime("%d.%m %H:%M")}


def _bars(sym: str) -> list[dict]:
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    rows = _jsonl(p)
    rows.sort(key=lambda r: str(r.get("candle") or ""))
    return rows


def _jsonl(path: Path) -> list[dict]:
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    except OSError:
        pass
    return out


CSS = """
/* СТЕКЛО (08.09, референс владельца — набор стеклянных элементов на тёмном): матовое стекло с
   размытием фона, светящаяся кромка по краю, диагональный блик по верхней грани, цветное зарево
   позади карточки и его отражение под ней. Никаких плоских заливок и рамок в одну линию. */
:root{--ink:#e6eefa;--mid:#93a7bd;--dim:#63768c;--up:#4fe3b8;--dn:#ff9078;--acc:#6fb4ff;--vio:#a98cff;
  --glass:linear-gradient(150deg,rgba(255,255,255,.10) 0%,rgba(255,255,255,.035) 38%,rgba(255,255,255,.015) 60%,rgba(0,0,0,.16) 100%);
  --edge:inset 0 0 0 1px rgba(255,255,255,.10);
  --lift:0 26px 50px rgba(0,0,0,.60),0 6px 16px rgba(0,0,0,.42)}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;color:var(--ink);font-family:Inter,system-ui,sans-serif;font-weight:300;
 -webkit-font-smoothing:antialiased;
 background:
  radial-gradient(60% 46% at 8% -10%,rgba(60,140,255,.20) 0,transparent 60%),
  radial-gradient(54% 44% at 94% 0%,rgba(150,90,255,.18) 0,transparent 62%),
  radial-gradient(80% 55% at 50% 112%,rgba(40,110,180,.16) 0,transparent 70%),
  linear-gradient(168deg,#161b24 0%,#12161f 55%,#0e1219 100%);background-attachment:fixed}
.wrap{max-width:1060px;margin:0 auto;padding:26px 18px 60px}
.head{display:flex;align-items:baseline;gap:14px;padding:2px 6px 20px}
.head h1{margin:0;font-size:12px;font-weight:300;letter-spacing:.34em;text-transform:uppercase;color:#e2edfb;
 text-shadow:0 0 24px rgba(140,190,255,.4)}
.head s{text-decoration:none;font-size:10px;color:var(--dim);letter-spacing:.12em}
.head .back{margin-left:auto;font-size:10px;letter-spacing:.18em;color:#cfe0f5;text-decoration:none;
 padding:9px 17px;border-radius:999px;background:var(--glass);backdrop-filter:blur(14px);
 box-shadow:var(--edge),0 10px 22px rgba(0,0,0,.5)}

/* вкладки — стеклянная гряда, активная светится изнутри голубым */
.tabs{display:flex;gap:10px;margin-bottom:22px;overflow-x:auto;scrollbar-width:none;padding:4px}
.tabs::-webkit-scrollbar{display:none}
.tab{position:relative;flex:none;cursor:pointer;padding:11px 19px;border-radius:16px;font-size:11.5px;
 letter-spacing:.1em;color:var(--mid);background:var(--glass);backdrop-filter:blur(14px);
 box-shadow:var(--edge),0 12px 24px rgba(0,0,0,.5);transition:.25s;white-space:nowrap;overflow:hidden}
.tab:before{content:'';position:absolute;inset:0 0 55% 0;
 background:linear-gradient(160deg,rgba(255,255,255,.16),transparent 70%);pointer-events:none}
.tab b{font-weight:400;color:#e2edfb;margin-right:8px}
.tab.on{color:#f2f8ff;background:linear-gradient(150deg,rgba(110,180,255,.34),rgba(120,90,220,.16));
 box-shadow:var(--edge),0 0 34px rgba(110,175,255,.42),0 14px 26px rgba(0,0,0,.5)}
.tab.on b{color:#fff}

.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:20px}
/* карточка — матовое стекло: зарево позади, блик по верхней грани, светящаяся кромка */
.coin{position:relative;border-radius:24px;padding:20px 22px 17px;
 background:var(--glass);backdrop-filter:blur(18px) saturate(115%);
 box-shadow:var(--edge),var(--lift);isolation:isolate}
.coin:before{content:'';position:absolute;inset:-2px;border-radius:26px;z-index:-2;filter:blur(22px);opacity:.5;
 background:linear-gradient(140deg,var(--c,#6fb4ff),transparent 55%,var(--vio))}
.coin:after{content:'';position:absolute;inset:1px 1px 62% 1px;border-radius:23px;pointer-events:none;
 background:linear-gradient(158deg,rgba(255,255,255,.18) 0%,rgba(255,255,255,.05) 45%,transparent 100%)}
.coin.up{--c:#4fe3b8}.coin.down{--c:#ff9078}.coin.flat{--c:#7fa0c4}
.c1{position:relative;display:flex;align-items:baseline;gap:11px;z-index:1}
.c1 h3{margin:0;font-size:21px;font-weight:200;letter-spacing:.16em;color:#f4f9ff;
 text-shadow:0 0 26px rgba(160,205,255,.5)}
.c1 s{text-decoration:none;font-size:10px;color:var(--dim);letter-spacing:.16em}
.c1 em{margin-left:auto;font-style:normal;font-size:27px;font-weight:200;letter-spacing:-.01em;
 font-variant-numeric:tabular-nums;color:var(--c);text-shadow:0 0 28px var(--c)}
.trail{position:relative;z-index:1;margin:15px 0 4px;font-size:12.5px;color:#9db1c7;
 font-variant-numeric:tabular-nums;white-space:nowrap;overflow-x:auto;scrollbar-width:none}
.trail::-webkit-scrollbar{display:none}
.trail i{font-style:normal;color:#3b4c62;margin:0 6px}
.trail b{font-weight:400;color:#eef5ff;text-shadow:0 0 14px rgba(160,205,255,.45)}
.trail u{text-decoration:none;color:var(--dn);text-shadow:0 0 14px rgba(255,144,120,.65)}
/* полоса дня — стеклянная трубка со светом внутри */
.bar{position:relative;z-index:1;height:8px;border-radius:999px;margin:17px 0 12px;
 background:linear-gradient(180deg,rgba(0,0,0,.55),rgba(255,255,255,.04));
 box-shadow:inset 0 2px 6px rgba(0,0,0,.8),inset 0 -1px 0 rgba(255,255,255,.09)}
.bar i{position:absolute;top:0;bottom:0;border-radius:999px;
 background:linear-gradient(90deg,rgba(140,175,215,.3),var(--c));box-shadow:0 0 18px var(--c);opacity:.8}
.bar u{position:absolute;top:-5px;width:2px;height:18px;border-radius:2px;background:#bacfe6;opacity:.8}
.bar em{position:absolute;top:-6px;width:11px;height:20px;border-radius:5px;background:var(--c);
 box-shadow:0 0 22px var(--c),0 0 48px var(--c),inset 0 1px 0 rgba(255,255,255,.5);transform:translateX(-5px)}
.nums{position:relative;z-index:1;display:flex;flex-wrap:wrap;gap:16px;font-size:10.5px;color:var(--mid);
 font-variant-numeric:tabular-nums}
.nums b{font-weight:400;color:#d6e5f7}
.nums .u{color:var(--up)}.nums .d{color:var(--dn)}
.empty{padding:60px 10px;text-align:center;color:var(--dim);font-size:11.5px;letter-spacing:.16em}
@media(max-width:640px){.grid{grid-template-columns:1fr}.c1 em{font-size:23px}}
"""


def _n(v) -> str:
    """Цена как число, а не как пусто: архив может не иметь баров по монете за этот день."""
    return f"{v:.6g}" if isinstance(v, (int, float)) else "—"


def _pos(v, lo, hi) -> float:
    """Где значение между минимумом и максимумом дня, в процентах ширины полосы."""
    if not all(isinstance(x, (int, float)) for x in (v, lo, hi)) or hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (v - lo) / (hi - lo) * 100))


def render_accuracy() -> str:
    data = build_data()
    tabs, panes = [], []
    for k, d in enumerate(data["days"]):
        on = " on" if k == 0 else ""
        tabs.append(f"<div class='tab{on}' data-i='{k}'><b>{d['d'][8:10]}.{d['d'][5:7]}</b>{d['dow']} · {len(d['coins'])}</div>")
        cards = []
        for c in d["coins"]:
            end = c.get("end")
            cls = "up" if (end or 0) > 1 else ("down" if (end or 0) < -1 else "flat")
            etxt = ("+" if (end or 0) > 0 else "") + (f"{end}%" if end is not None else "—")
            # лента мест: 2 → 2 → 5 → и время выхода последним звеном (08.09, владелец)
            steps = [f"<b>{p}</b>" for p in c["path"].split(" → ")]
            if c.get("gone"):
                steps.append(f"<u>{c['gone']}</u>")
            trail = "<i>→</i>".join(steps)
            lo, hi, px, now = c.get("lo"), c.get("hi"), c.get("px"), c.get("now")
            p_in, p_now = _pos(px, lo, hi), _pos(now, lo, hi)
            left, width = min(p_in, p_now), abs(p_now - p_in)
            up = f"<span class='u'>+{c['up']}%</span>" if c.get("up") is not None else "—"
            dn = f"<span class='d'>{c['dn']}%</span>" if c.get("dn") is not None else "—"
            cards.append(f"""    <div class="coin {cls}">
      <div class="c1"><h3>{c['s']}</h3><s>{c['in_at']}</s><em>{etxt}</em></div>
      <div class="trail">{trail}</div>
      <div class="bar"><i style="left:{left:.1f}%;width:{width:.1f}%"></i>
        <u style="left:{p_in:.1f}%"></u><em style="left:{p_now:.1f}%"></em></div>
      <div class="nums"><span>вход <b>{_n(px)}</b></span><span>дно <b>{_n(lo)}</b></span>
        <span>верх <b>{_n(hi)}</b></span><span>{up} {dn}</span></div>
    </div>""")
        panes.append(f"<div class='grid' data-i='{k}'{'' if k == 0 else ' hidden'}>{''.join(cards)}</div>")
    body = ("<div class='tabs'>" + "".join(tabs) + "</div>" + "".join(panes)) if tabs \
        else '<div class="empty">за это время в первых никого не было</div>'
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>журнал заходов</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <div class="head"><h1>Журнал заходов</h1><s>монеты, побывавшие в первых</s><a class="back" href="intro.html">← созвездие</a></div>
{body}
</div>
<script>
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{{
  document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('on',x===t));
  document.querySelectorAll('.grid').forEach(g=>g.hidden=(g.dataset.i!==t.dataset.i));
}});
</script>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    html = render_accuracy()
    d = build_data()
    n = sum(len(x["coins"]) for x in d["days"])
    print(f"журнал заходов: дней {len(d['days'])} · монет в первых {n} · html {len(html)} байт")
    if a.write:
        p = REPORT_PATH.parent / "accuracy.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        print("→", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
