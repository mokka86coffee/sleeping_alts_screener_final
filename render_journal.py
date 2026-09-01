#!/usr/bin/env python3
"""Экран журнала прогнозов (01.09).

Отвечает на один вопрос: когда система сменила мнение по монете и что
цена делала до и после. Линия и метки берутся ИЗ ОДНОГО РЯДА —
output/forecasts.jsonl, — поэтому метка стоит ровно на своей точке, а
не приблизительно рядом.

Что на экране:
  СЛЕВА  список монет; у каждой — сколько смен и ход за всё время
         записи. Сортировка по числу смен: где система металась,
         там и смотреть.
  СПРАВА график цены по журналу, шкала дат снизу, вертикальные метки
         в точках СМЕНЫ шаблона с подписью нового имени и ходом от
         прошлой смены.

Почему не рисуем цену дневками архива: линия и метки оказались бы из
разных источников и разошлись бы на стыке. Ряд короткий и будет расти
день за днём — это честнее склейки.

    python3 render_journal.py            # output/journal.html
    python3 render_journal.py --out X    # свой путь
"""
import argparse
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

W, H = 1920, 1080
PAD_L, PAD_R, PAD_T, PAD_B = 470, 90, 130, 150

AP = argparse.ArgumentParser()
AP.add_argument("--log", default="output/forecasts.jsonl")
AP.add_argument("--out", default="output/journal.html")
A = AP.parse_args()


def load(path: Path) -> dict:
    """Журнал → {монета: [точки]}. Без цены точка не годится."""
    if not path.exists():
        return {}
    by: dict = OrderedDict()
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        px = r.get("px")
        if not isinstance(px, (int, float)) or not px:
            continue                      # старые записи без цены
        try:
            t = datetime.strptime(f"{r.get('at','')} {r.get('hm','00:00')}",
                                  "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        by.setdefault(str(r.get("sym", "")).upper(), []).append(
            {"t": t, "px": float(px), "tpl": str(r.get("tpl") or ""),
             "stage": str(r.get("stage") or "")})
    for k in by:
        by[k].sort(key=lambda x: x["t"])
    return by


def switches(pts: list) -> list:
    """Точки, где шаблон сменился. Первая — не смена, а начало."""
    out, prev = [], None
    for i, p in enumerate(pts):
        if prev is not None and p["tpl"] != prev:
            out.append(i)
        prev = p["tpl"]
    return out


def short(tpl: str) -> str:
    return tpl.split("(")[0].strip()[:34]


DATA = load(Path(A.log))
if not DATA:
    # СТРАНИЦА ВСЁ РАВНО ПИШЕТСЯ (правка 01.09). Прежде сборщик
    # отказывался и выходил — а кнопка в схеме вела в пустоту, 404.
    # Цены в журнале появляются только с прогонов на новой версии,
    # старые записи их не имеют; до тех пор честнее показать причину,
    # чем сломанную ссылку.
    _n = 0
    _p = Path(A.log)
    if _p.exists():
        _n = sum(1 for x in _p.read_text(encoding="utf-8").splitlines()
                 if x.strip())
    stub = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Журнал прогнозов</title><style>
*{{box-sizing:border-box;margin:0}}html,body{{height:100%}}
body{{background:#000306;color:#9fb8cc;font:300 16px/1.7 Arial;
display:grid;place-items:center;text-align:center;padding:40px}}
h1{{font-weight:800;font-size:15px;letter-spacing:.26em;color:#9fb8cc;
margin-bottom:18px}}
b{{color:#ffb44a;font-weight:700}}
i{{display:block;margin-top:22px;font-size:13px;color:#5f7a90;
font-style:italic;max-width:52ch}}
a{{position:fixed;left:18px;top:16px;font:700 11px Arial;
letter-spacing:.14em;color:#ffb44a;text-decoration:none;
border:1px solid rgba(255,180,74,.35);border-radius:8px;padding:5px 11px;
opacity:.55}}
</style></head><body><a href="index.html">\u2190 схема</a>
<div><h1>ЖУРНАЛ ПРОГНОЗОВ</h1>
<p>записей в журнале: <b>{_n}</b>, из них с ценой: <b>0</b></p>
<p>график строится по цене, а её в старых записях нет</p>
<i>Цена пишется с прогонов на новой версии журнала. Появится с
ближайшего — и страница соберётся сама, дальше будет удлиняться
каждым прогоном.</i></div></body></html>"""
    out = Path(A.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(stub, encoding="utf-8")
    print(f"журнал: записей {_n}, с ценой 0 — страница-заглушка")
    raise SystemExit(0)

# порядок монет: где больше смен, там интереснее
ORDER = sorted(DATA, key=lambda s: (-len(switches(DATA[s])), s))

DEFS = """
<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
 <stop offset="0" stop-color="#000306"/><stop offset=".5" stop-color="#030d16"/>
 <stop offset="1" stop-color="#000205"/></linearGradient>
<linearGradient id="hot" x1="0" y1="0" x2="1" y2="0">
 <stop offset="0" stop-color="#ff9a2e"/><stop offset="1" stop-color="#ffd07a"/>
</linearGradient>
<radialGradient id="glowA" cx="50%" cy="50%" r="50%">
 <stop offset="0" stop-color="#ffb44a" stop-opacity=".9"/>
 <stop offset="1" stop-color="#ff7a1a" stop-opacity="0"/></radialGradient>
<radialGradient id="vig" cx="50%" cy="50%" r="74%">
 <stop offset=".62" stop-color="#000" stop-opacity="0"/>
 <stop offset="1" stop-color="#000" stop-opacity=".7"/></radialGradient>
<filter id="b3"><feGaussianBlur stdDeviation="3"/></filter>
<filter id="b9"><feGaussianBlur stdDeviation="9"/></filter>
<filter id="b26"><feGaussianBlur stdDeviation="26"/></filter>"""


def squid():
    """Кальмар — знак страницы. Живёт в океане, как и наши киты."""
    return """
<g id="squid" opacity=".5">
  <ellipse cx="0" cy="-16" rx="17" ry="25" fill="none"
    stroke="#5fe0ff" stroke-width="1.6"/>
  <ellipse cx="0" cy="-24" rx="9" ry="11" fill="#5fe0ff" opacity=".18"/>
  <circle cx="-6" cy="-12" r="2.6" fill="#dff6ff"/>
  <circle cx="6" cy="-12" r="2.6" fill="#dff6ff"/>
  <path d="M-13,4 C-16,20 -11,30 -15,42" fill="none" stroke="#5fe0ff"
    stroke-width="1.5" stroke-linecap="round"/>
  <path d="M-7,7 C-9,24 -4,34 -8,46" fill="none" stroke="#5fe0ff"
    stroke-width="1.5" stroke-linecap="round"/>
  <path d="M0,8 C0,26 3,36 0,48" fill="none" stroke="#7fe8ff"
    stroke-width="1.7" stroke-linecap="round"/>
  <path d="M7,7 C9,24 4,34 8,46" fill="none" stroke="#5fe0ff"
    stroke-width="1.5" stroke-linecap="round"/>
  <path d="M13,4 C16,20 11,30 15,42" fill="none" stroke="#5fe0ff"
    stroke-width="1.5" stroke-linecap="round"/>
</g>"""


def panel(sym: str, pts: list) -> str:
    """Одна панель: линия, шкала дат, метки смен."""
    n = len(pts)
    lo = min(p["px"] for p in pts)
    hi = max(p["px"] for p in pts)
    rng = (hi - lo) or (hi * .02) or 1
    lo, hi = lo - rng * .12, hi + rng * .18
    x0, x1 = PAD_L, W - PAD_R
    y0, y1 = PAD_T, H - PAD_B

    def X(i):
        return x0 + (i / max(1, n - 1)) * (x1 - x0)

    def Y(v):
        return y1 - (v - lo) / (hi - lo) * (y1 - y0)

    pl = " ".join(f"{X(i):.1f},{Y(p['px']):.1f}" for i, p in enumerate(pts))
    art = [
        f'<polyline points="{pl}" fill="none" stroke="#000306" '
        f'stroke-width="9" opacity=".8" filter="url(#b3)" '
        f'transform="translate(2,4)"/>',
        f'<polyline points="{pl}" fill="none" stroke="url(#hot)" '
        f'stroke-width="26" opacity=".13" filter="url(#b26)"/>',
        f'<polyline points="{pl}" fill="none" stroke="url(#hot)" '
        f'stroke-width="7" opacity=".4" filter="url(#b9)"/>',
        f'<polyline points="{pl}" fill="none" stroke="url(#hot)" '
        f'stroke-width="2.6"/>',
        f'<polyline points="{pl}" fill="none" stroke="#fff6e4" '
        f'stroke-width=".9" opacity=".75" transform="translate(0,-1)"/>']

    # шкала дат: подпись на смене суток и по краям
    seen, ticks = set(), []
    for i, p in enumerate(pts):
        d = p["t"].strftime("%d.%m")
        if d in seen and i not in (0, n - 1):
            continue
        seen.add(d)
        ticks.append(f'<line x1="{X(i):.0f}" y1="{y1}" x2="{X(i):.0f}" '
                     f'y2="{y1 + 8}" stroke="#3a5468" stroke-width="1"/>'
                     f'<text x="{X(i):.0f}" y="{y1 + 26}" text-anchor="middle"'
                     f' font-family="Arial" font-weight="700" font-size="11"'
                     f' fill="#6f8ba0" letter-spacing=".12em">'
                     f'{p["t"].strftime("%d.%m")}</text>')
    ticks.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" '
                 f'stroke="#22384a" stroke-width="1"/>')

    # МЕТКИ СМЕН — то, ради чего экран
    marks, prev_px, k = [], pts[0]["px"], 0
    for i in switches(pts):
        p = pts[i]
        x, y = X(i), Y(p["px"])
        up = k % 2 == 0
        ly = (y0 + 34 + (k // 2) * 46) if up else (y1 - 70 - (k // 2) * 46)
        k += 1
        move = (p["px"] / prev_px - 1) * 100 if prev_px else 0
        col = "#7fe8ff" if p["stage"] == "moving" else "#ffb44a"
        marks.append(
            f'<line x1="{x:.0f}" y1="{y0}" x2="{x:.0f}" y2="{y1}" '
            f'stroke="{col}" stroke-width="1" opacity=".22"/>'
            f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{x:.0f}" y2="{ly:.0f}" '
            f'stroke="{col}" stroke-width="1.2" opacity=".5"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="16" fill="url(#glowA)" '
            f'opacity=".6" filter="url(#b9)"/>'
            f'<circle cx="{x:.0f}" cy="{y:.0f}" r="3.4" fill="#fff6e4"/>'
            f'<text x="{x + 9:.0f}" y="{ly:.0f}" font-family="Arial" '
            f'font-weight="800" font-size="13" fill="{col}" '
            f'letter-spacing=".02em">{short(p["tpl"])}</text>'
            f'<text x="{x + 9:.0f}" y="{ly + 17:.0f}" font-family="Arial" '
            f'font-weight="700" font-size="11" fill="#7f9bb0" '
            f'opacity=".8">{p["t"].strftime("%d.%m %H:%M")} · '
            f'{p["px"]:.6g} · {move:+.1f}% от прошлой</text>')
        prev_px = p["px"]

    # начало и конец
    first, last = pts[0], pts[-1]
    ends = (f'<circle cx="{X(0):.0f}" cy="{Y(first["px"]):.0f}" r="3" '
            f'fill="#8fa8bc"/>'
            f'<text x="{X(0):.0f}" y="{Y(first["px"]) - 14:.0f}" '
            f'font-family="Arial" font-weight="700" font-size="11" '
            f'fill="#8fa8bc">начало записи · {first["px"]:.6g}</text>'
            f'<circle cx="{X(n-1):.0f}" cy="{Y(last["px"]):.0f}" r="16" '
            f'fill="url(#glowA)" opacity=".7" filter="url(#b9)"/>'
            f'<circle cx="{X(n-1):.0f}" cy="{Y(last["px"]):.0f}" r="4" '
            f'fill="#fffaf0"/>'
            f'<text x="{X(n-1) - 8:.0f}" y="{Y(last["px"]) - 18:.0f}" '
            f'text-anchor="end" font-family="Arial" font-weight="800" '
            f'font-size="15" fill="#fff6e4">{last["px"]:.6g} сейчас</text>')

    ch = (last["px"] / first["px"] - 1) * 100
    head = (f'<text x="{PAD_L}" y="72" font-family="Arial" font-weight="800" '
            f'font-size="46" fill="#fff6e4" letter-spacing=".02em">'
            f'{sym.replace("USDT", "")}</text>'
            f'<text x="{PAD_L + 12 + len(sym) * 22}" y="72" '
            f'font-family="Arial" font-weight="800" font-size="20" '
            f'fill="{"#4fc98a" if ch >= 0 else "#ec6f5e"}">{ch:+.1f}%</text>'
            f'<text x="{PAD_L}" y="98" font-family="Arial" font-weight="700" '
            f'font-size="12" fill="#6f8ba0" letter-spacing=".14em">'
            f'ЗАПИСЕЙ {n} · СМЕН ПРОГНОЗА {len(switches(pts))} · '
            f'С {first["t"].strftime("%d.%m %H:%M")}</text>')
    return head + "".join(art) + "".join(ticks) + "".join(marks) + ends


def side() -> str:
    """Список монет. Число смен — мера того, насколько система металась."""
    rows = []
    y = 150
    for sym in ORDER:
        pts = DATA[sym]
        sw = len(switches(pts))
        ch = (pts[-1]["px"] / pts[0]["px"] - 1) * 100
        rows.append(
            f'<g class="pick" data-sym="{sym}">'
            f'<rect x="56" y="{y - 26}" width="360" height="46" rx="9" '
            f'fill="#0b1a26" opacity=".55"/>'
            f'<text x="76" y="{y}" font-family="Arial" font-weight="800" '
            f'font-size="19" fill="#dfe8f2">{sym.replace("USDT", "")}</text>'
            f'<text x="248" y="{y}" font-family="Arial" font-weight="700" '
            f'font-size="14" fill="{"#4fc98a" if ch >= 0 else "#ec6f5e"}">'
            f'{ch:+.1f}%</text>'
            f'<text x="330" y="{y}" font-family="Arial" font-weight="700" '
            f'font-size="12" fill="#6f8ba0">смен {sw}</text></g>')
        y += 58
    return "".join(rows)


PANELS = "".join(
    f'<g class="panel" data-sym="{s}" style="display:none">{panel(s, DATA[s])}</g>'
    for s in ORDER)

svg = f"""<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg">
<defs>{DEFS}</defs>
<rect width="{W}" height="{H}" fill="url(#bg)"/>
{squid()}
<use href="#squid" x="150" y="70" transform="scale(1.5)"
  transform-origin="150 70"/>
<text x="56" y="66" font-family="Arial" font-weight="800" font-size="15"
  fill="#9fb8cc" letter-spacing=".26em">ЖУРНАЛ ПРОГНОЗОВ</text>
<text x="56" y="90" font-family="Georgia,serif" font-style="italic"
  font-size="13" fill="#6f8ba0">когда система сменила мнение и что было
  с ценой</text>
{side()}
{PANELS}
<rect width="{W}" height="{H}" fill="url(#vig)" pointer-events="none"/>
</svg>"""

html = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Журнал прогнозов</title><style>
*{{box-sizing:border-box;margin:0}}html,body{{height:100%}}
body{{background:#000306;overflow:hidden}}
svg{{display:block;width:100vw;height:100vh}}
.pick{{cursor:pointer}}
.pick rect{{transition:opacity .18s}}
.pick:hover rect{{opacity:.95}}
.pick.on rect{{opacity:1;stroke:#ffb44a;stroke-width:1.2}}
.back{{position:fixed;left:18px;top:16px;z-index:9;font:700 11px Arial;
letter-spacing:.14em;color:#ffb44a;text-decoration:none;
border:1px solid rgba(255,180,74,.35);border-radius:8px;padding:5px 11px;
opacity:.55}}.back:hover{{opacity:1}}
</style></head><body><a class="back" href="index.html">\u2190 схема</a>
{svg}
<script>
(function(){{
  var picks = [].slice.call(document.querySelectorAll('.pick'));
  var panes = [].slice.call(document.querySelectorAll('.panel'));
  function show(sym){{
    panes.forEach(function(p){{
      p.style.display = p.dataset.sym === sym ? '' : 'none'; }});
    picks.forEach(function(p){{
      p.classList.toggle('on', p.dataset.sym === sym); }});
  }}
  picks.forEach(function(p){{
    p.addEventListener('click', function(){{ show(p.dataset.sym); }}); }});
  if (picks.length) show(picks[0].dataset.sym);
}})();
</script></body></html>"""

out = Path(A.out)
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding="utf-8")
print(f"журнал собран: {len(html)} байт · монет {len(DATA)} · "
      f"смен всего {sum(len(switches(v)) for v in DATA.values())}")
