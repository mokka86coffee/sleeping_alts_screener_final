#!/usr/bin/env python3
"""ЭКРАН ТОЧНОСТИ (07.09) — accuracy.html: дни → часы → монеты.

ВНИМАНИЕ: в проекте с 01.09 уже есть render_journal.py со своей страницей journal.html —
это ДРУГОЙ экран, он не трогается. Этот модуль называется иначе и пишет accuracy.html.

Владелец: «нужно сделать список сначала по дням, где мы будем показывать, какое количество
прогнозов сбылось, какое нет. Дальше при нажатии на день мы попадаем в список по часам…
и при входе в конкретный час нужно показывать, какие монеты из первых, сколько ушли по цене».
Плюс 07.09: «при заходе в часы показывать, какой рынок открыт, идёт, скоро закроется».

Данные — output/forecast_score.json (три границы, MFE и MAE, кривая затухания, разрезы по фону)
и output/market_bg.jsonl (фон на момент: risk on, биткоин, состояние рынков). Ничего не считает
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
    sc = _read(OUTD / "forecast_score.json") or {}
    bgs = _bg_rows()
    items = sc.get("items") or []
    days, hours, coins = [], {}, {}
    for d in sc.get("days_list") or []:
        b = _bg_for(bgs, d["d"])
        try:
            dow = DOW[datetime.strptime(d["d"], "%Y-%m-%d").weekday()]
        except ValueError:
            dow = ""
        days.append({"d": d["d"], "dow": dow, "n": d.get("n", 0), "ok": d.get("ok", 0),
                     "mfe": d.get("mfe_med"), "mae": d.get("mae_med"), "bg": _bg_text(b)})
    for h in sc.get("hours_list") or []:
        day, hh = h["h"][:10], h["h"][11:13] + ":00"
        b = _bg_for(bgs, h["h"])
        hours.setdefault(day, []).append({"h": hh, "n": h.get("n", 0), "ok": h.get("ok", 0),
                                          "bg": _bg_text(b), "mk": _markets(b)})
    for x in items:
        key = f"{x['at'][:10]} {x['at'][11:13]}:00"
        why = (x.get("tpl") or "")
        if x.get("hit"):
            why += f" · {x['hit']}" + (f" через {x['hit_h']} ч" if x.get("hit_h") else "")
        coins.setdefault(key, []).append({
            "s": x["sym"].replace("USDT", ""), "p": x.get("place") or "—",
            "px": f"{x['px']:.6g}", "later": x.get("end", 0.0), "ok": bool(x.get("ok")),
            "mfe": x.get("mfe"), "mae": x.get("mae"), "why": why})
    for k in coins:
        coins[k].sort(key=lambda c: (c["p"] if isinstance(c["p"], int) else 99))
    a = sc.get("all") or {}
    curve = [[float(k), v["med"]] for k, v in (a.get("curve") or {}).items()]
    cuts = []
    for name, grp in (sc.get("cuts") or {}).items():
        for k, v in grp.items():
            if v.get("n"):
                cuts.append([f"{k}", f"{v['ok_pct']}% из {v['n']}"])
    summ = {"n": a.get("n", 0), "ok": a.get("ok", 0), "ok_pct": a.get("ok_pct", 0),
            "went": a.get("went_pct", 0), "mfe": a.get("mfe_med"), "mae": a.get("mae_med"),
            "ratio": a.get("mfe_mae"), "enough": bool(a.get("enough")),
            "curve": curve, "best": float(a["best_h"]) if a.get("best_h") else None,
            "cuts": cuts[:12]}
    return {"days": days, "hours": hours, "coins": coins, "sum": summ,
            "at": datetime.now(timezone.utc).strftime("%d.%m %H:%M UTC")}


CSS = """
:root{--ink:#1d2a36;--mid:#5d7285;--dim:#98abbb;--up:#12a17c;--dn:#e0644c}
*{box-sizing:border-box}
html,body{margin:0;min-height:100%;color:var(--ink);font-family:Inter,system-ui,sans-serif;font-weight:300;
 -webkit-font-smoothing:antialiased;overflow-x:hidden;
 background:radial-gradient(50% 40% at 15% 0%,#e9f0fb 0,transparent 60%),
  radial-gradient(45% 40% at 88% 6%,#efe9fb 0,transparent 62%),
  radial-gradient(60% 50% at 50% 110%,#dfe6f3 0,transparent 70%),
  linear-gradient(170deg,#f2f5fb 0%,#e7ecf6 55%,#dde4f1 100%);background-attachment:fixed}
.wrap{max-width:880px;margin:0 auto;padding:38px 20px 70px}
.plate{position:relative;border-radius:30px;padding:22px 20px 18px;
 background:linear-gradient(160deg,#fdfeff,#eef2f9 60%,#e7edf7);
 box-shadow:20px 24px 54px rgba(120,140,175,.30),-14px -16px 40px rgba(255,255,255,.95),inset 0 1px 0 rgba(255,255,255,.9);
 animation:rise .5s cubic-bezier(.2,.8,.2,1) both}
@keyframes rise{from{opacity:0;transform:translateY(14px) scale(.99)}}
.head{display:flex;align-items:center;gap:12px;padding:4px 8px 16px}
h1{margin:0;font-size:17px;font-weight:600;letter-spacing:-.02em}
.crumbs{font-size:12px;color:var(--mid)}.crumbs a{color:#4676c8;text-decoration:none;cursor:pointer}
.crumbs a:hover{text-decoration:underline}
.back{margin-left:auto;font-size:11.5px;padding:9px 16px;border-radius:999px;cursor:pointer;color:#31465c;
 background:linear-gradient(160deg,#fff,#eaf0f8);box-shadow:5px 6px 12px rgba(120,140,175,.28),-4px -5px 10px rgba(255,255,255,.95);
 transition:transform .15s,box-shadow .15s}
.back:active{transform:translateY(1px);box-shadow:inset 3px 4px 8px rgba(120,140,175,.3),inset -3px -3px 7px rgba(255,255,255,.9)}
.back[hidden]{display:none}
.tabs{display:flex;gap:10px;padding:0 8px 14px}
.tab{position:relative;font-size:12px;padding:10px 18px;border-radius:999px;color:#5d7285;
 background:linear-gradient(160deg,#fff,#e9eef7);box-shadow:5px 6px 12px rgba(120,140,175,.25),-4px -5px 10px rgba(255,255,255,.95)}
.tab.on{color:#fff;background:linear-gradient(160deg,#38455c,#1e2735)}
.tab.on::after{content:"";position:absolute;left:22%;right:22%;bottom:-7px;height:8px;border-radius:999px;
 background:var(--c,#5aa6ff);filter:blur(7px);opacity:.85}
.sum{display:grid;grid-template-columns:1fr 1fr 1fr 1.5fr;gap:12px;margin:0 0 14px}
.box{padding:14px 16px;border-radius:18px;background:linear-gradient(160deg,#fdfeff,#eef2f9);
 box-shadow:7px 8px 16px rgba(120,140,175,.2),-6px -7px 14px rgba(255,255,255,.95);animation:pop .34s cubic-bezier(.2,.8,.2,1) both}
.box u{display:block;text-decoration:none;font-size:9.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-bottom:8px}
.box em{font-style:normal;font-size:26px;font-weight:200;letter-spacing:-.02em;color:#1d2a36}
.box em s{text-decoration:none;font-size:.5em;color:var(--dim)}
.box p{margin:6px 0 0;font-size:11px;color:var(--mid)}
.curve{position:relative;height:56px;margin-top:4px}
.curve svg{width:100%;height:100%;overflow:visible}
.curve .ln{fill:none;stroke:url(#cg);stroke-width:2.4;stroke-linecap:round;stroke-linejoin:round;
 filter:drop-shadow(0 2px 6px rgba(60,140,220,.45));stroke-dasharray:var(--l);stroke-dashoffset:var(--l);
 animation:draw 1.1s .15s cubic-bezier(.2,.8,.2,1) forwards}
@keyframes draw{to{stroke-dashoffset:0}}
.curve .pk{fill:#fff;stroke:#12a17c;stroke-width:2.5;filter:drop-shadow(0 0 8px rgba(18,161,124,.75));opacity:0;animation:show .4s 1.05s forwards}
@keyframes show{to{opacity:1}}
.curve .xl{font-size:8.5px;fill:#98abbb;letter-spacing:.08em}
.cuts{display:flex;flex-wrap:wrap;gap:8px;margin:2px 0 14px}
.cut{font-size:11px;padding:8px 12px;border-radius:14px;color:#41566c;background:linear-gradient(160deg,#fff,#eaeff8);
 box-shadow:4px 5px 10px rgba(120,140,175,.2),-3px -4px 8px rgba(255,255,255,.95)}
.cut b{font-weight:500;color:#1d2a36}.cut i{font-style:normal;color:var(--dim)}
.list{display:flex;flex-direction:column;gap:8px}
.r{display:grid;align-items:center;gap:12px;padding:14px;border-radius:18px;cursor:pointer;
 background:linear-gradient(160deg,#fdfeff,#eef2f9);
 box-shadow:7px 8px 16px rgba(120,140,175,.22),-6px -7px 14px rgba(255,255,255,.95);
 transition:transform .18s cubic-bezier(.2,.8,.2,1),box-shadow .18s;animation:pop .34s cubic-bezier(.2,.8,.2,1) both}
@keyframes pop{from{opacity:0;transform:translateY(10px)}}
.r:hover{transform:translateY(-2px);box-shadow:10px 12px 22px rgba(120,140,175,.26),-7px -8px 16px rgba(255,255,255,1)}
.r:active{transform:translateY(0);box-shadow:inset 4px 5px 10px rgba(120,140,175,.28),inset -4px -4px 9px rgba(255,255,255,.9)}
.r.h{cursor:default;background:none;box-shadow:none;padding:2px 16px;font-size:10px;letter-spacing:.22em;
 text-transform:uppercase;color:var(--dim);animation:none}
.r.h:hover{transform:none;box-shadow:none}
.days .r,.days .r.h{grid-template-columns:130px 1fr 104px}
.hours .r,.hours .r.h{grid-template-columns:92px 1fr 104px}
.coins .r,.coins .r.h{grid-template-columns:112px 46px 1fr 96px 88px}
.k{font-weight:500;color:#1d2a36}
.k small{display:block;font-weight:300;font-size:11px;color:var(--dim);letter-spacing:.03em;margin-top:2px}
.num{text-align:right;font-variant-numeric:tabular-nums}
.up{color:var(--up)}.dn{color:var(--dn)}.mut{color:var(--dim)}
.vial{position:relative;height:14px;border-radius:999px;overflow:hidden;background:#e7ecf5;
 box-shadow:inset 3px 4px 8px rgba(120,140,175,.4),inset -2px -2px 5px rgba(255,255,255,.9)}
.vial i{position:absolute;left:0;top:0;bottom:0;width:0;border-radius:999px;
 background:linear-gradient(90deg,#31c8a0,#12a17c);box-shadow:0 0 14px rgba(18,161,124,.55);
 transition:width .9s cubic-bezier(.2,.8,.2,1)}
.vial i.mid{background:linear-gradient(90deg,#f5c173,#e39b3f);box-shadow:0 0 14px rgba(227,155,63,.5)}
.vial i.bad{background:linear-gradient(90deg,#f0937f,#e0644c);box-shadow:0 0 14px rgba(224,100,76,.45)}
.bg{font-size:11px;color:var(--mid);margin-top:7px}.bg b{font-weight:500;color:#33475a}
.mk{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.m{display:inline-flex;align-items:center;gap:6px;font-size:10.5px;color:#5d7285;padding:5px 10px;border-radius:999px;
 background:linear-gradient(160deg,#fff,#eaeff8);box-shadow:3px 4px 8px rgba(120,140,175,.2),-3px -3px 7px rgba(255,255,255,.95)}
.m u{text-decoration:none;color:#93a8b8}.m s{text-decoration:none;width:7px;height:7px;border-radius:50%;background:#c9d4e0}
.m.on s{background:#12a17c;box-shadow:0 0 8px rgba(18,161,124,.8);animation:beat 2.2s ease-in-out infinite}
.m.soon s{background:#e39b3f;box-shadow:0 0 8px rgba(227,155,63,.85);animation:beat 1.1s ease-in-out infinite}
.m.on{color:#22323d}
@keyframes beat{50%{transform:scale(.72);opacity:.55}}
.ex{display:inline-flex;gap:8px;margin-left:10px;font-size:10.5px;vertical-align:middle}
.ex s{text-decoration:none;padding:3px 8px;border-radius:999px;background:#eef3fa;
 box-shadow:inset 2px 2px 5px rgba(120,140,175,.28),inset -2px -2px 4px rgba(255,255,255,.9)}
.ex s.p{color:#0f7a5e}.ex s.m{color:#c0442c}
.place{width:30px;height:30px;border-radius:50%;display:grid;place-items:center;font-size:12.5px;color:#41566c;
 background:linear-gradient(160deg,#fff,#e9eef7);box-shadow:4px 5px 10px rgba(120,140,175,.28),-3px -4px 8px rgba(255,255,255,.95)}
.place.top{color:#0c7a5e;background:linear-gradient(160deg,#fff,#dcf3ec)}
.tick{width:9px;height:9px;border-radius:50%;display:inline-block;margin-right:7px;vertical-align:middle}
.tick.y{background:#12a17c;box-shadow:0 0 9px rgba(18,161,124,.8)}
.tick.n{background:#e0644c;box-shadow:0 0 9px rgba(224,100,76,.7)}
.note{margin:16px 10px 2px;font-size:11px;color:var(--dim)}
.empty{padding:18px;font-size:12.5px;color:var(--mid)}
@media (max-width:640px){
 .sum{grid-template-columns:1fr 1fr}
 .days .r,.days .r.h{grid-template-columns:96px 1fr 78px}
 .hours .r,.hours .r.h{grid-template-columns:66px 1fr 78px}
 .coins .r,.coins .r.h{grid-template-columns:86px 40px 1fr 70px}
 .hide{display:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = """
const pct=(o,n)=>n?Math.round(o/n*100):0;
const cls=p=>p>=60?'':p>=35?'mid':'bad';
const vial=(o,n)=>`<div class="vial"><i class="${cls(pct(o,n))}" data-w="${pct(o,n)}"></i></div>`;
const view=document.getElementById('view'),crumbs=document.getElementById('crumbs'),
      back=document.getElementById('back'),note=document.getElementById('note'),tabs=document.getElementById('tabs'),
      sumEl=document.getElementById('sum'),cutsEl=document.getElementById('cuts');
const stagger=()=>[...view.querySelectorAll('.r')].forEach((el,i)=>el.style.animationDelay=(i*45)+'ms');
const fill=()=>requestAnimationFrame(()=>setTimeout(()=>view.querySelectorAll('.vial i').forEach(i=>i.style.width=i.dataset.w+'%'),90));
const markets=mk=>!mk||!mk.length?'':`<div class="mk">`+mk.map(([n,st,left,c])=>
  `<div class="m ${c}"><s></s>${n}<u>${st}${left?` · ${left} ч`:''}</u></div>`).join('')+`</div>`;
function setTabs(l){const t=[['дни','#5aa6ff'],['часы','#f0a94a'],['монеты','#f2607f']];
  tabs.innerHTML=t.map(([n,c],i)=>`<div class="tab ${i===l?'on':''}" style="--c:${c}">${n}</div>`).join('');}
function drawSum(){
  const S=DATA.sum;
  if(!S.n){sumEl.innerHTML='<div class="empty">журнал пуст: считалка ещё не отработала или нет прогнозов за период</div>';
    cutsEl.innerHTML='';return;}
  let curveHtml='';
  if(S.curve&&S.curve.length>1){
    const w=260,h=44,xs=S.curve.map(c=>c[0]),ys=S.curve.map(c=>c[1]);
    const lx=Math.log(Math.min(...xs)),rx=Math.log(Math.max(...xs)),lo=Math.min(...ys),hi=Math.max(...ys);
    const px=v=>((Math.log(v)-lx)/((rx-lx)||1))*w,py=v=>h-((v-lo)/((hi-lo)||1))*h;
    const pts=S.curve.map(([x,y])=>[px(x),py(y)]);
    const d=pts.map((p,i)=>(i?'L':'M')+p[0].toFixed(1)+' '+p[1].toFixed(1)).join(' ');
    const bi=Math.max(0,S.curve.findIndex(c=>c[0]===S.best)),bp=pts[bi];
    curveHtml=`<div class="curve"><svg viewBox="-6 -8 ${w+30} ${h+22}" preserveAspectRatio="none">
      <defs><linearGradient id="cg" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8fc6f5"/><stop offset="1" stop-color="#12a17c"/></linearGradient></defs>
      <path class="ln" d="${d}" style="--l:${w*1.6}"/>
      <circle class="pk" cx="${bp[0].toFixed(1)}" cy="${bp[1].toFixed(1)}" r="4.5"/>
      ${S.curve.map(([x],i)=>`<text class="xl" x="${pts[i][0].toFixed(1)}" y="${h+14}" text-anchor="middle">${x}ч</text>`).join('')}
    </svg></div>`;}
  sumEl.innerHTML=`<div class="sum">
    <div class="box"><u>сбылось</u><em>${S.ok_pct}<s>%</s></em><p>${S.ok} из ${S.n}${S.enough?'':' · мало для статистики'}</p></div>
    <div class="box"><u>пошли в нашу сторону</u><em>${S.went}<s>%</s></em><p>хоть немного двинулись</p></div>
    <div class="box"><u>MFE / MAE</u><em>${S.ratio??'—'}</em><p>лучший ход ${S.mfe??'—'}% · просадка ${S.mae??'—'}%</p></div>
    <div class="box"><u>кривая затухания${S.best?` · пик ${S.best} ч`:''}</u>${curveHtml}</div></div>`;
  cutsEl.innerHTML=(S.cuts||[]).map(([k,v])=>`<div class="cut"><b>${k}</b> <i>${v}</i></div>`).join('');
}
function days(){
  setTabs(0);crumbs.textContent='по дням';back.hidden=true;view.className='list days';
  drawSum();sumEl.style.display='';cutsEl.style.display='';
  view.innerHTML=`<div class="r h"><div>день</div><div>сбылось</div><div class="num">из скольких</div></div>`+
   (DATA.days.length?DATA.days.map(d=>`<div class="r" data-d="${d.d}">
     <div class="k">${d.d.slice(8)}.${d.d.slice(5,7)}<small>${d.dow}</small></div>
     <div>${vial(d.ok,d.n)}<div class="bg">${d.bg}${d.mfe!==null&&d.mfe!==undefined?`<span class="ex"><s class="p">MFE ${d.mfe>0?'+':''}${d.mfe}%</s><s class="m">MAE ${d.mae}%</s></span>`:''}</div></div>
     <div class="num k">${pct(d.ok,d.n)}%<small>${d.ok} из ${d.n}</small></div></div>`).join('')
    :`<div class="empty">дней в журнале нет</div>`);
  note.textContent='сбылось — цена дошла до ближайшей полосы сверху раньше, чем до полосы снизу и раньше срока';
  view.querySelectorAll('.r[data-d]').forEach(el=>el.onclick=()=>hours(el.dataset.d));
  stagger();fill();
}
function hours(d){
  setTabs(1);crumbs.innerHTML=`<a id="toDays">по дням</a> · ${d}`;back.hidden=false;view.className='list hours';
  sumEl.style.display='none';cutsEl.style.display='none';
  const rows=DATA.hours[d]||[];
  view.innerHTML=`<div class="r h"><div>час</div><div>сбылось</div><div class="num">из скольких</div></div>`+
   (rows.length?rows.map(h=>`<div class="r" data-h="${h.h}">
     <div class="k">${h.h}</div>
     <div>${vial(h.ok,h.n)}<div class="bg">${h.bg}</div>${markets(h.mk)}</div>
     <div class="num k">${pct(h.ok,h.n)}%<small>${h.ok} из ${h.n}</small></div></div>`).join('')
    :`<div class="empty">за этот день часов в журнале нет</div>`);
  note.textContent='фон и рынки в строке — состояние на этот час';
  document.getElementById('toDays').onclick=days;
  view.querySelectorAll('.r[data-h]').forEach(el=>el.onclick=()=>coins(d,el.dataset.h));
  back.onclick=days;stagger();fill();
}
function coins(d,h){
  setTabs(2);crumbs.innerHTML=`<a id="toDays">по дням</a> · <a id="toHours">${d}</a> · ${h}`;
  view.className='list coins';sumEl.style.display='none';cutsEl.style.display='none';
  const rows=DATA.coins[`${d} ${h}`]||[];
  view.innerHTML=`<div class="r h"><div>монета</div><div>место</div><div>прогноз</div><div class="num">цена</div><div class="num">ушла</div></div>`+
   (rows.length?rows.map(c=>`<div class="r">
     <div class="k"><span class="tick ${c.ok?'y':'n'}"></span>${c.s}<small>${c.ok?'сбылось':'не сбылось'}</small></div>
     <div><span class="place ${c.p!=='—'&&c.p<=3?'top':''}">${c.p}</span></div>
     <div class="bg" style="margin-top:0">${c.why}<span class="ex"><s class="p">MFE ${c.mfe>0?'+':''}${c.mfe}%</s><s class="m">MAE ${c.mae}%</s></span></div>
     <div class="num k">${c.px}</div>
     <div class="num k ${c.later>0?'up':'dn'}">${c.later>0?'+':''}${(c.later||0).toFixed(1)}%</div></div>`).join('')
    :`<div class="empty">за этот час монет в журнале нет</div>`);
  note.textContent='«ушла» — ход цены от точки прогноза · первые три места подсвечены';
  document.getElementById('toDays').onclick=days;
  document.getElementById('toHours').onclick=()=>hours(d);
  back.onclick=()=>hours(d);stagger();
}
days();
"""


def render_accuracy() -> str:
    data = build_data()
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>журнал прогнозов</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@200;300;400;500;600&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>
<div class="wrap"><div class="plate">
  <div class="head">
    <h1>Журнал прогнозов</h1>
    <div class="crumbs" id="crumbs"></div>
    <div class="back" id="back" hidden>назад</div>
  </div>
  <div class="tabs" id="tabs"></div>
  <div id="sum"></div>
  <div id="cuts" class="cuts"></div>
  <div id="view" class="list"></div>
  <div class="note" id="note"></div>
</div></div>
<script>
const DATA={json.dumps(data, ensure_ascii=False)};
{JS}
</script>
</body>
</html>"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    html = render_accuracy()
    d = build_data()
    s = d["sum"]
    print(f"экран точности: дней {len(d['days'])} · часов {sum(len(v) for v in d['hours'].values())} · "
          f"прогнозов {s['n']} · сбылось {s['ok_pct']}% · html {len(html)} байт")
    if a.write:
        p = REPORT_PATH.parent / "accuracy.html"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(html, encoding="utf-8")
        print("→", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
