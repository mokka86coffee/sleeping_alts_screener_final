#!/usr/bin/env python3
"""Экран журнала прогнозов (01.09, переписан 03.09 в язык «восход»).

Отвечает на один вопрос: когда система сменила мнение по монете и что
цена делала до и после. Линия и метки берутся ИЗ ОДНОГО РЯДА —
output/forecasts.jsonl — поэтому метка стоит ровно на своей точке.

Что на экране:
  ВВЕРХУ  «К РАЗБОРУ» — монеты, у которых прогноз кончился развязкой
          против: «курок — осечка», «кит ушёл», «крупняк отпустил»,
          «раздача». Их владелец разбирает отдельно: не отличив
          плохой шаблон от плохого рынка, порогов не поправить.
          У каждой — сколько осечек и ход цены после последней.
  СЛЕВА   список монет, ПРОКРУЧИВАЕТСЯ (01.09 список был SVG и не
          вертелся); сортировка по числу смен, потом по осечкам.
  СПРАВА  линия цены по журналу, шкала дат, метки смен с подписью
          нового имени и ходом от прошлой смены; осечки красным.

Данные вшиты в JSON, экран рисует сам (как coin.html); стили в
документе, шрифты Jost и IBM Plex Mono, как у экрана монеты.

    python3 render_journal.py            # output/journal.html
    python3 render_journal.py --out X    # свой путь
"""
import argparse
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

AP = argparse.ArgumentParser()
AP.add_argument("--log", default="output/forecasts.jsonl")
AP.add_argument("--out", default="output/journal.html")
A = AP.parse_args()

# развязка ПРОТИВ прогноза — по корням имён сюжетов (имена 01.09)
MISS_WORDS = ("осечка", "ушёл", "отпустил", "раздача")


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
            continue
        try:
            t = datetime.strptime(f"{r.get('at', '')} {r.get('hm', '00:00')}",
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
    return tpl.split("(")[0].strip()[:40]


def is_miss(tpl: str) -> bool:
    t = tpl.lower()
    return any(w in t for w in MISS_WORDS)


DATA = load(Path(A.log))
if not DATA:
    # СТРАНИЦА ВСЁ РАВНО ПИШЕТСЯ (правка 01.09): кнопка в схеме не должна
    # вести в пустоту; честнее показать причину, чем 404.
    _n = 0
    _p = Path(A.log)
    if _p.exists():
        _n = sum(1 for x in _p.read_text(encoding="utf-8").splitlines()
                 if x.strip())
    stub = f"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Журнал прогнозов</title><style>
*{{box-sizing:border-box;margin:0}}html,body{{height:100%}}
body{{background:#020907;color:#9fd8bf;font:300 16px/1.7 Inter,Arial;
display:grid;place-items:center;text-align:center;padding:40px}}
h1{{font-weight:400;font-size:13px;letter-spacing:.3em;color:#7fb8a0;margin-bottom:18px}}
b{{color:#f5a93a;font-weight:400}}
i{{display:block;margin-top:22px;font-size:13px;color:#5e8f7a;max-width:52ch}}
a{{position:fixed;left:18px;top:16px;font:400 11px Inter,Arial;letter-spacing:.2em;color:#f5a93a;
text-decoration:none;border:1px solid rgba(245,169,58,.35);border-radius:8px;padding:5px 11px;opacity:.7}}
</style></head><body><a href="brief.html">\u2190 схема</a>
<div><h1>ЖУРНАЛ ПРОГНОЗОВ</h1>
<p>записей в журнале: <b>{_n}</b>, из них с ценой: <b>0</b></p>
<p>график строится по цене, а её в старых записях нет</p>
<i>Цена пишется с прогонов на новой версии журнала. Появится с
ближайшего — и страница соберётся сама.</i></div></body></html>"""
    out = Path(A.out)
    out.parent.mkdir(exist_ok=True)
    out.write_text(stub, encoding="utf-8")
    print(f"журнал: записей {_n}, с ценой 0 — страница-заглушка")
    raise SystemExit(0)

# ── компактные данные для экрана ──
coins = []
for sym, pts in DATA.items():
    sw = switches(pts)
    misses = [i for i in sw if is_miss(pts[i]["tpl"])]
    last_miss = misses[-1] if misses else None
    coins.append({
        "t": sym.replace("USDT", ""),
        "p": [[int(p["t"].timestamp() * 1000), round(p["px"], 8),
               short(p["tpl"]), p["stage"]] for p in pts],
        "sw": sw, "miss": misses,
        "chg": round((pts[-1]["px"] / pts[0]["px"] - 1) * 100, 1),
        "afterMiss": (round((pts[-1]["px"] / pts[last_miss]["px"] - 1) * 100, 1)
                      if last_miss is not None else None),
    })
# порядок: больше осечек — выше, потом больше смен, потом имя
coins.sort(key=lambda c: (-len(c["miss"]), -len(c["sw"]), c["t"]))
blob = json.dumps(coins, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
n_switch = sum(len(c["sw"]) for c in coins)
n_miss = sum(len(c["miss"]) for c in coins)

html = r"""<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Журнал прогнозов</title>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@300;400&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box;margin:0}html,body{height:100%}
body{background:#020907;color:#e8fff4;font-family:Inter,system-ui,sans-serif;font-weight:300;overflow:hidden}
.bg{position:fixed;inset:0;background:radial-gradient(900px 640px at 86% -4%, #1f7a5c 0%, #0f3f31 30%, #062219 55%, #020907 85%),#020907}
.beam{position:fixed;left:62%;top:-80px;width:520px;height:100vh;background:linear-gradient(rgba(160,255,214,.18),rgba(160,255,214,0));filter:blur(40px);transform:skewX(-14deg);pointer-events:none;animation:beam 9s ease-in-out infinite}
@keyframes beam{0%,100%{opacity:.85;transform:skewX(-14deg)}50%{opacity:1;transform:skewX(-11deg)}}
.vig{position:fixed;inset:0;background:radial-gradient(ellipse 70% 60% at 50% 45%, transparent 45%, rgba(0,0,0,.55) 100%);pointer-events:none}
.mono,.cap{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace}
.num{font-family:Jost,Inter,sans-serif;font-weight:200}
.wrap{position:relative;height:100vh;display:grid;grid-template-columns:340px 1fr;grid-template-rows:auto 1fr;gap:0 28px;padding:28px 48px 24px 48px}
.head{grid-column:1/3;display:flex;align-items:baseline;gap:26px;flex-wrap:wrap;margin-bottom:14px}
.head .t{font-family:Jost,Inter,sans-serif;font-size:22px;font-weight:200;letter-spacing:.3em;color:#fff;text-shadow:0 0 18px rgba(255,255,255,.25)}
.head .s{font-size:11px;color:#7fb8a0}
.head .st{margin-left:auto;font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:7.5px;letter-spacing:.22em;text-transform:uppercase;color:#7fb8a0}
.head .st b{color:#dfe9e4;font-weight:400}
.back{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:7.5px;letter-spacing:.28em;text-transform:uppercase;color:#7fb8a0;text-decoration:none;border:1px solid rgba(127,232,176,.25);border-radius:14px;padding:5px 12px;align-self:center}
.back:hover{color:#dfffee;border-color:rgba(127,232,176,.5)}
/* к разбору */
.review{grid-column:1/3;display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 16px;padding:12px 16px;border-radius:12px;
  background:linear-gradient(135deg,rgba(255,90,74,.08),rgba(3,18,14,.5));border:1px solid rgba(255,138,112,.28);box-shadow:0 0 40px rgba(255,90,74,.06)}
.review .cap{font-size:7.5px;letter-spacing:.32em;text-transform:uppercase;color:#ff8a70;margin-right:6px}
.review .hint{font-size:10px;color:#9fd8bf;margin-right:8px}
.chip{display:inline-flex;align-items:center;gap:8px;padding:5px 11px 5px 9px;border-radius:14px;border:1px solid rgba(255,138,112,.35);background:rgba(3,18,14,.55);cursor:pointer;transition:.2s}
.chip:hover,.chip.on{border-color:#ff8a70;box-shadow:0 0 16px rgba(255,90,74,.25)}
.chip i{width:6px;height:6px;border-radius:50%;background:#ff5a4a;box-shadow:0 0 8px rgba(255,90,74,.9)}
.chip b{font-family:Jost,Inter,sans-serif;font-weight:400;font-size:12px;letter-spacing:.12em;color:#fff}
.chip s{text-decoration:none;font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:7px;letter-spacing:.16em;text-transform:uppercase;color:#ffb59f}
.chip em{font-style:normal;font-size:10px;color:#9fd8bf}
.review .none{font-size:10px;color:#7fb8a0}
/* список */
.list{overflow:auto;padding-right:6px;scrollbar-width:thin;scrollbar-color:rgba(127,232,176,.25) transparent}
.list::-webkit-scrollbar{width:6px}.list::-webkit-scrollbar-thumb{background:rgba(127,232,176,.25);border-radius:3px}
.row{display:grid;grid-template-columns:1fr auto auto;align-items:center;gap:12px;padding:9px 12px;margin-bottom:4px;border-radius:9px;cursor:pointer;
  background:rgba(3,18,14,.45);border:1px solid rgba(127,232,176,.08);transition:.18s}
.row:hover{border-color:rgba(245,169,58,.35);background:rgba(3,18,14,.7)}
.row.on{border-color:rgba(245,169,58,.7);box-shadow:0 0 18px rgba(245,169,58,.15)}
.row .n{font-family:Jost,Inter,sans-serif;font-size:14px;font-weight:300;letter-spacing:.12em;color:#e8fff4;display:flex;align-items:center;gap:8px}
.row .n i{width:5px;height:5px;border-radius:50%;background:#ff5a4a;box-shadow:0 0 8px rgba(255,90,74,.9)}
.row .c{font-family:Jost,Inter,sans-serif;font-size:12px;font-weight:300}
.row .c.up{color:#7fe8b0}.row .c.dn{color:#ff8a70}
.row .w{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:7px;letter-spacing:.16em;text-transform:uppercase;color:#7fb8a0;white-space:nowrap}
/* панель */
.pane{position:relative;min-width:0}
.pane svg{display:block;width:100%;height:100%;overflow:visible}
.ttl{position:absolute;left:0;top:0;display:flex;align-items:baseline;gap:16px}
.ttl .t{font-family:Jost,Inter,sans-serif;font-size:30px;font-weight:200;letter-spacing:.2em;color:#fff;text-shadow:0 0 18px rgba(255,255,255,.25);text-decoration:none}
.ttl .t:hover{color:#ffd98a}
.ttl .c{font-family:Jost,Inter,sans-serif;font-size:14px;font-weight:300}.ttl .c.up{color:#7fe8b0}.ttl .c.dn{color:#ff8a70}
.ttl .s{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace;font-size:7.5px;letter-spacing:.22em;text-transform:uppercase;color:#7fb8a0}
.ttl .s b{color:#dfe9e4;font-weight:400}
.ln{stroke-dasharray:var(--L);stroke-dashoffset:var(--L);animation:draw 1.4s cubic-bezier(.5,0,.3,1) .2s forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.an{opacity:0;animation:fadein .8s ease forwards}@keyframes fadein{to{opacity:1}}
@media (max-width:900px){.wrap{grid-template-columns:1fr;grid-template-rows:auto auto 200px 1fr;padding:16px}.head,.review{grid-column:1}.list{max-height:200px}}
</style></head><body>
<div class="bg"></div><div class="beam"></div>
<div class="wrap">
  <div class="head"><a class="back" href="brief.html">← схема</a><span class="t">ЖУРНАЛ ПРОГНОЗОВ</span><span class="s">когда система сменила мнение и что было с ценой</span>
    <span class="st">монет <b>__NCOINS__</b> · смен <b>__NSW__</b> · осечек <b>__NMISS__</b></span></div>
  <div class="review" id="review"></div>
  <div class="list" id="list"></div>
  <div class="pane" id="pane"></div>
</div>
<div class="vig"></div>
<script id="jData" type="application/json">__DATA__</script>
<script>
(function(){
  var D = JSON.parse(document.getElementById('jData').textContent);
  var GOLD = '#f5a93a', GOLDL = '#ffd98a', RED = '#ff8a70', MINT = '#7fe8b0';
  function esc(t){ return String(t == null ? '' : t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
  function pad(n){ return (n < 10 ? '0' : '') + n; }
  function dm(ms){ var d = new Date(ms); return pad(d.getDate()) + '.' + pad(d.getMonth() + 1); }
  function hm(ms){ var d = new Date(ms); return pad(d.getHours()) + ':' + pad(d.getMinutes()); }
  function px4(v){ v = +v; return v >= 100 ? v.toFixed(1) : v >= 1 ? v.toFixed(3) : v >= 0.01 ? v.toFixed(4) : v.toFixed(6); }
  function pct(v){ return (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(1) + '%'; }
  var MISS = /осечка|ушёл|отпустил|раздача/;
  var BY = {}; D.forEach(function(c){ BY[c.t] = c; });

  // ── к разбору ──
  var rv = document.getElementById('review'), miss = D.filter(function(c){ return c.miss.length; });
  rv.innerHTML = '<span class="cap">к разбору</span><span class="hint">прогноз кончился развязкой против — осечка, кит ушёл, крупняк отпустил</span>' +
    (miss.length ? miss.map(function(c){ return '<span class="chip" data-t="' + esc(c.t) + '"><i></i><b>' + esc(c.t) + '</b><s>осечек ' + c.miss.length + '</s>' + (c.afterMiss !== null ? '<em>после ' + pct(c.afterMiss) + '</em>' : '') + '</span>'; }).join('')
                : '<span class="none">осечек нет</span>');

  // ── список ──
  var ls = document.getElementById('list');
  ls.innerHTML = D.map(function(c){ return '<div class="row" data-t="' + esc(c.t) + '"><span class="n">' + (c.miss.length ? '<i title="осечек ' + c.miss.length + '"></i>' : '') + esc(c.t) + '</span><span class="c ' + (c.chg >= 0 ? 'up' : 'dn') + '">' + pct(c.chg) + '</span><span class="w">смен ' + c.sw.length + '</span></div>'; }).join('');

  // ── панель ──
  var pane = document.getElementById('pane');
  function draw(t){
    var c = BY[t]; if (!c) return;
    var W = pane.clientWidth || 1000, H = pane.clientHeight || 600, P = c.p, n = P.length;
    var padL = 24, padR = 150, padT = 96, padB = 54, x0 = padL, x1 = W - padR, y0 = padT, y1 = H - padB;
    var lo = Infinity, hi = -Infinity; P.forEach(function(q){ if (q[1] < lo) lo = q[1]; if (q[1] > hi) hi = q[1]; });
    var rng = (hi - lo) || hi * .02 || 1; lo -= rng * .14; hi += rng * .22;
    function X(i){ return x0 + (i / Math.max(1, n - 1)) * (x1 - x0); }
    function Y(v){ return y1 - (v - lo) / (hi - lo) * (y1 - y0); }
    var pl = P.map(function(q, i){ return X(i).toFixed(1) + ',' + Y(q[1]).toFixed(1); }).join(' '), L = 0;
    for (var i = 1; i < n; i++) L += Math.hypot(X(i) - X(i - 1), Y(P[i][1]) - Y(P[i - 1][1]));
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '"><defs>' +
      '<filter id="b3" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="3"/></filter><filter id="b12" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="12"/></filter><filter id="b30" x="-40%" y="-80%" width="180%" height="260%"><feGaussianBlur stdDeviation="30"/></filter>' +
      '<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1fc47c" stop-opacity=".16"/><stop offset="1" stop-color="#065a3b" stop-opacity="0"/></linearGradient></defs>';
    // полотно под линией и пол
    s += '<path class="an" style="animation-delay:.9s" d="M' + X(0).toFixed(1) + ',' + y1 + ' L' + pl.split(' ').join(' L') + ' L' + X(n - 1).toFixed(1) + ',' + y1 + ' Z" fill="url(#fill)"/>';
    s += '<line x1="' + x0 + '" y1="' + y1 + '" x2="' + x1 + '" y2="' + y1 + '" stroke="' + GOLD + '" stroke-width="14" opacity=".16" filter="url(#b12)"/>' +
         '<line x1="' + x0 + '" y1="' + y1 + '" x2="' + x1 + '" y2="' + y1 + '" stroke="#fff6dc" stroke-width="1" opacity=".55"/>';
    // шкала дат: смена суток и края
    var seen = {}; for (i = 0; i < n; i++) { var d = dm(P[i][0]); if (seen[d] && i !== 0 && i !== n - 1) continue; seen[d] = 1;
      s += '<line x1="' + X(i).toFixed(0) + '" y1="' + y1 + '" x2="' + X(i).toFixed(0) + '" y2="' + (y1 + 7) + '" stroke="#5e8f7a" stroke-width="1"/><text x="' + X(i).toFixed(0) + '" y="' + (y1 + 24) + '" text-anchor="middle" font-family="IBM Plex Mono,Menlo,monospace" font-size="8" letter-spacing=".16em" fill="#7fb8a0">' + d + '</text>'; }
    // линия — неон
    [[36, .12, ' filter="url(#b30)"', '#e0891f'], [16, .22, ' filter="url(#b12)"', GOLD], [7, .5, ' filter="url(#b3)"', GOLD], [3, .9, '', GOLD], [1.6, 1, '', GOLDL]].forEach(function(q){
      s += '<polyline class="ln" points="' + pl + '" fill="none" stroke="' + q[3] + '" stroke-width="' + q[0] + '" stroke-linejoin="round" stroke-linecap="round" opacity="' + q[1] + '" style="--L:' + Math.ceil(L + 2) + '"' + q[2] + '/>'; });
    // метки смен
    var k = 0, prevPx = P[0][1];
    c.sw.forEach(function(i){
      var q = P[i], x = X(i), y = Y(q[1]), up = k % 2 === 0, ly = up ? (y0 + 30 + Math.floor(k / 2) * 44) : (y1 - 64 - Math.floor(k / 2) * 44); k++;
      var move = prevPx ? (q[1] / prevPx - 1) * 100 : 0, missed = MISS.test(q[2]), col = missed ? RED : (q[3] === 'moving' ? MINT : GOLD);
      var sub = dm(q[0]) + ' ' + hm(q[0]) + ' · ' + px4(q[1]) + ' · ' + pct(move) + ' от прошлой';
      var bw = Math.max(q[2].length * 7.2, sub.length * 5.4) + 18, left = x + bw + 20 > x1 + padR - 10;   // у правого края — подпись влево
      var tx = left ? x - 16 : x + 16, rx = left ? x - 8 - bw : x + 8, anc = left ? ' text-anchor="end"' : '';
      s += '<g class="an" style="animation-delay:' + (1.4 + k * .1).toFixed(1) + 's">' +
        '<line x1="' + x.toFixed(0) + '" y1="' + y0 + '" x2="' + x.toFixed(0) + '" y2="' + y1 + '" stroke="' + col + '" stroke-width="1" opacity=".18"/>' +
        '<line x1="' + x.toFixed(0) + '" y1="' + y.toFixed(0) + '" x2="' + x.toFixed(0) + '" y2="' + ly.toFixed(0) + '" stroke="' + col + '" stroke-width="1" opacity=".5"/>' +
        '<circle cx="' + x.toFixed(0) + '" cy="' + y.toFixed(0) + '" r="12" fill="' + col + '" opacity=".35" filter="url(#b12)"/><circle cx="' + x.toFixed(0) + '" cy="' + y.toFixed(0) + '" r="3" fill="#fff6e4"/>' +
        '<rect x="' + rx.toFixed(0) + '" y="' + (ly - 14).toFixed(0) + '" width="' + bw.toFixed(0) + '" height="34" rx="7" fill="#03110c" opacity=".55"/>' +
        '<text x="' + tx.toFixed(0) + '" y="' + ly.toFixed(0) + '"' + anc + ' font-family="Jost,Inter,sans-serif" font-weight="400" font-size="12" letter-spacing=".06em" fill="' + col + '">' + esc(q[2]) + '</text>' +
        '<text x="' + tx.toFixed(0) + '" y="' + (ly + 14).toFixed(0) + '"' + anc + ' font-family="IBM Plex Mono,Menlo,monospace" font-size="8" letter-spacing=".12em" fill="#9fd8bf">' + sub + '</text></g>';
      prevPx = q[1];
    });
    // начало и сейчас
    var f = P[0], l = P[n - 1];
    s += '<circle cx="' + X(0).toFixed(0) + '" cy="' + Y(f[1]).toFixed(0) + '" r="3" fill="#9fd8bf"/><text x="' + X(0).toFixed(0) + '" y="' + (Y(f[1]) - 14).toFixed(0) + '" font-family="IBM Plex Mono,Menlo,monospace" font-size="8" letter-spacing=".12em" fill="#9fd8bf">начало записи · ' + px4(f[1]) + '</text>';
    s += '<g class="an" style="animation-delay:1.5s"><circle cx="' + X(n - 1).toFixed(0) + '" cy="' + Y(l[1]).toFixed(0) + '" r="14" fill="#fff" opacity=".2" filter="url(#b12)"/><circle cx="' + X(n - 1).toFixed(0) + '" cy="' + Y(l[1]).toFixed(0) + '" r="3.4" fill="#fff"/>' +
         '<text x="' + (X(n - 1) + 12).toFixed(0) + '" y="' + (Y(l[1]) + 4).toFixed(0) + '" font-family="Jost,Inter,sans-serif" font-weight="300" font-size="13" fill="#fff">' + px4(l[1]) + ' <tspan fill="#bfe9d6" font-size="10">сейчас</tspan></text></g>';
    s += '</svg>';
    var tv = 'https://www.tradingview.com/chart/?symbol=' + encodeURIComponent('BINANCE:' + t + 'USDT.P');
    pane.innerHTML = '<div class="ttl"><a class="t" href="' + tv + '" target="_blank" rel="noopener" title="открыть в TradingView">' + esc(t) + '</a><span class="c ' + (c.chg >= 0 ? 'up' : 'dn') + '">' + pct(c.chg) + '</span>' +
      '<span class="s">записей <b>' + n + '</b> · смен прогноза <b>' + c.sw.length + '</b>' + (c.miss.length ? ' · <b style="color:#ff8a70">осечек ' + c.miss.length + '</b>' : '') + ' · с <b>' + dm(f[0]) + ' ' + hm(f[0]) + '</b></span></div>' + s;
    [].forEach.call(document.querySelectorAll('.row,.chip'), function(el){ el.classList.toggle('on', el.dataset.t === t); });
    var row = document.querySelector('.row.on'); if (row && row.scrollIntoView) row.scrollIntoView({ block: 'nearest' });
    location.hash = t;
  }
  document.addEventListener('click', function(e){ var el = e.target.closest('.row,.chip'); if (el) draw(el.dataset.t); });
  window.addEventListener('resize', function(){ var on = document.querySelector('.row.on'); if (on) draw(on.dataset.t); });
  var h = (location.hash || '').replace('#', '').toUpperCase();
  draw(BY[h] ? h : (D[0] && D[0].t));
})();
</script></body></html>
"""
html = (html.replace("__DATA__", blob).replace("__NCOINS__", str(len(coins)))
        .replace("__NSW__", str(n_switch)).replace("__NMISS__", str(n_miss)))
out = Path(A.out)
out.parent.mkdir(exist_ok=True)
out.write_text(html, encoding="utf-8")
print(f"журнал собран: {len(html)} байт · монет {len(coins)} · смен {n_switch} · "
      f"осечек {n_miss} у {sum(1 for c in coins if c['miss'])} монет")
