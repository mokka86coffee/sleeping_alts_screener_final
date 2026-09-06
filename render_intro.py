"""Первый экран «поведение света» (05–06.09) — прототип владельца v2_povedenie-2.html:
имена монет собираются из облака по одному и остаются созвездием; свет — состояние.

Три группы (владелец, 06.09):
  0 — БРАТЬ:    «близкие, держат после сбора» из near_move (свет набирает, искры вверх);
  1 — ДЕРЖАТЬ:  «идут» из near_move (мягкая зелёная подсветка, редкие капли);
  2 — ЗАКРЫТЬ:  текущий шаблон «у цели сбора», либо последняя смена — осечка/«отпустил»
                (буквы выедает и сдувает, блики мигают и гаснут).
Потолок — 12 имён, порядок — по группам, внутри группы по свежести сбора; раскладка —
рассыпать по облаку с минимальным расстоянием между именами (созвездие при любом N).

Шейдер, такты появления, цвета и эрозия — владельца, не трогаются. Добавлено: клик по
имени → coin.html#SYM; клик мимо / любая клавиша → дальше по оболочке (ob:done, screen
'intro'); подпись внизу «брать N · держать N · закрыть N».

    from render_intro import render_intro
    html = render_intro()                  # читает output/near_move.json, output/reputation.json,
                                           # output/forecasts.jsonl; пусто → короткое созвездие
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

MAX_NAMES = 12
END_WORDS = ("осечк", "отпустил", "отбой")


def _read(name: str):
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _last_marks() -> dict:
    """Последний шаблон по монете из forecasts.jsonl (короткое имя)."""
    out: dict = {}
    for p in (BASE_DIR / "output" / "forecasts.jsonl", Path("output") / "forecasts.jsonl"):
        if not p.exists():
            continue
        rows = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
        rows.sort(key=lambda r: f"{r.get('at', '')} {r.get('hm', '')}")
        for r in rows:
            s = str(r.get("sym") or "").upper()
            if s:
                out[s] = str(r.get("tpl") or "").split("(")[0].strip().lower()
        break
    return out


def collect_items() -> list[dict]:
    nm = _read("near_move.json") or {}
    coins = nm.get("coins") or {}
    rep = _read("reputation.json") or {}
    marks = _last_marks()
    items: list[dict] = []
    seen: set = set()

    def add(sym: str, g: int, why: str, sub: str = "", rel: float = 0.0):
        if sym in seen:
            return
        seen.add(sym)
        items.append({"n": sym.replace("USDT", ""), "sym": sym, "g": g, "why": why, "sub": sub, "rel": rel})

    def reliability(v: dict) -> float:
        """Надёжность (06.09, владелец: «у кого надёжнее — та ярче»): сбор × рост плеча, в логарифме
        по сбору — FLOCK ×144 при плече ×2.5 против «четвёрки» ×20 при ×1.8; сегодня продают — штраф."""
        n = v.get("nums") or {}
        hx = max(1.0, float(n.get("harvest_x") or 1.0))
        og = max(0.5, float(n.get("oi_grow") or 1.0))
        r = math.log10(hx) * og
        td = (v.get("today") or {}).get("today")
        if td == "продают сегодня":
            r *= 0.6
        elif td == "покупают сегодня":
            r *= 1.15
        return r

    for sym in nm.get("holding") or []:
        v = coins.get(sym) or {}
        td = (v.get("today") or {}).get("today")
        # сегодня по барам (06.09): покупают — подпись «покупают сегодня», продают — «ждёт покупателя»
        sub = "покупают сегодня" if td == "покупают сегодня" else ("ждёт покупателя" if td == "продают сегодня" else "")
        add(sym, 0, " · ".join(v.get("why") or []) + (f" · сегодня: {td}" if td else ""), sub, reliability(v))
    for sym in nm.get("going") or []:
        v = coins.get(sym) or {}
        td = (v.get("today") or {}).get("today")
        # в «держать» подпись — предупреждение о выходе: «продают сегодня»; покупают — молча
        add(sym, 1, " · ".join(v.get("why") or []) + (f" · сегодня: {td}" if td else ""), "продают сегодня" if td == "продают сегодня" else "", reliability(v))
    # ДЕРЖАТЬ / ЗАКРЫТЬ ПО СМЫСЛУ ДВИЖЕНИЯ (06.09, случай ENA: «у цели — ведут покупатели» попала в
    # «закрыть», а сменившись на «кит набирает тихо» — исчезла совсем):
    #   держать — «идут» из фильтра + шаблоны «у цели … ведут покупатели», «крупняк тащит вверх»,
    #             «разгон на спросе», «кит набирает тихо» при дельте дня в плюс;
    #   закрыть — «у цели» с веткой «толпа набивается» / «неясно», «разгон отпустил», осечка/отбой.
    cg = _read("coinglass_fetch.json") or {}
    cgc = cg.get("coins") or {}
    for sym, r in rep.items():
        if not isinstance(r, dict) or sym.startswith("_"):
            continue
        plot_full = str(r.get("plot") or "").lower()
        plot = plot_full.split("(")[0].strip()
        last = marks.get(sym, "")
        fut = (cgc.get(sym) or {}).get("fut") or {}
        d24 = (fut.get("buyUsd") or 0) - (fut.get("sellUsd") or 0)
        # ТРЕТЬЯ ГРУППА — «У ЦЕЛИ» с подписью, что делать (06.09, владелец):
        #   хеджировать — у цели, толпа набивается; ждать подтверждения — у цели, кто двигает неясно;
        #   конец тренда — разгон отпустил, осечка, отбой
        if plot.startswith("у цели"):
            if "ведут покупатели" in plot_full or "ведёт покупатель" in plot_full:
                add(sym, 1, "у цели — ведут покупатели")
            elif "толпа" in plot_full:
                add(sym, 2, "у цели — толпа набивается", "хеджировать")
            else:
                add(sym, 2, "у цели — кто двигает неясно", "ждать подтверждения")
        elif plot.startswith("разгон отпустил") or any(w in last for w in END_WORDS):
            add(sym, 2, plot or last, "конец тренда")
        elif plot.startswith(("крупняк тащит", "разгон на спросе")):
            add(sym, 1, plot)
        elif plot.startswith("кит набирает тихо") and d24 > 0:
            add(sym, 1, plot + " · дельта дня в плюс")
    # порядок: брать, держать, у цели; внутри группы — по надёжности, самая надёжная первой
    items.sort(key=lambda it: (it["g"], -it.get("rel", 0.0)))
    # яркость внутри группы: лучшая — 1.0, остальные вниз до 0.45; «у цели» — ровно 0.7
    for g in (0, 1):
        grp = [it for it in items if it["g"] == g]
        if not grp:
            continue
        hi_r, lo_r = max(it["rel"] for it in grp), min(it["rel"] for it in grp)
        for it in grp:
            it["bright"] = 1.0 if hi_r <= lo_r else 0.45 + 0.55 * (it["rel"] - lo_r) / (hi_r - lo_r)
    for it in items:
        if it["g"] == 2:
            it["bright"] = 0.7
    return items[:MAX_NAMES]


def layout(n: int, seed: int = 7) -> list[list[float]]:
    """Созвездие: точки в облаке с минимальным расстоянием; детерминировано по seed."""
    if n <= 0:
        return []
    rnd = random.Random(seed + n)
    pts: list[list[float]] = []
    tries = 0
    min_d = 0.16 if n <= 8 else 0.13
    while len(pts) < n and tries < 5000:
        tries += 1
        x = 0.24 + rnd.random() * 0.52
        y = 0.18 + rnd.random() * 0.58
        # ближе к центру облака — чуть охотнее
        if rnd.random() > 0.35 + 0.65 * math.exp(-((x - 0.5) ** 2 * 3 + (y - 0.5) ** 2 * 2)):
            continue
        # прямоугольное исключение (06.09: подпись «ждёт покупателя» под одним именем ложилась
        # над соседним — «ЖД» над FLOCK): либо разнос по вертикали ≥ 0.085 высоты (имя + подпись),
        # либо по горизонтали ≥ 0.20 ширины (длинное имя с подписью)
        if all((abs(y - py) >= 0.085) or (abs(x - px) >= 0.20) for px, py in pts) and \
           all(math.hypot((x - px) * 1.4, y - py) >= min_d for px, py in pts):
            pts.append([round(x, 3), round(y, 3)])
    while len(pts) < n:  # на крайний случай — сетка
        i = len(pts)
        pts.append([round(0.3 + 0.4 * ((i * 7) % 5) / 4, 3), round(0.22 + 0.6 * (i / n), 3)])
    return pts


def render_intro(items: list[dict] | None = None) -> str:
    items = collect_items() if items is None else items
    counts = [sum(1 for it in items if it["g"] == k) for k in (0, 1, 2)]
    # ПОДПИСИ ГРУПП ПРИЛЕТАЮТ ТОЖЕ (06.09, владелец): три слова — теми же «именами» из облака,
    # первыми по тактам, каждое в своей группе: «брать» набирает свет, «держать» зеленеет,
    # «закрыть» рассыпается. Стоят рядом по низу, монеты — созвездием над ними.
    labels = [{"n": f"брать {counts[0]}", "sym": "", "g": 0, "why": "", "label": True},
              {"n": f"держать {counts[1]}", "sym": "", "g": 1, "why": "", "label": True},
              {"n": f"у цели {counts[2]}", "sym": "", "g": 2, "why": "", "label": True}]
    allit = labels + items
    names = [it["n"] for it in allit]
    grp = [it["g"] for it in allit]
    syms = [it["sym"] for it in allit]
    whys = [it.get("why", "") for it in allit]
    lab = [1 if it.get("label") else 0 for it in allit]
    subs = [it.get("sub", "") for it in allit]
    bright = [1.0 if it.get("label") else float(it.get("bright", 0.85)) for it in allit]
    pos = [[0.24, 0.90], [0.50, 0.90], [0.76, 0.90]] + layout(len(items))
    n = max(1, len(allit))
    data = json.dumps({"names": names, "grp": grp, "syms": syms, "whys": whys, "pos": pos, "counts": counts, "label": lab, "subs": subs, "bright": bright},
                      ensure_ascii=False).replace("</", "<\\/")
    return TEMPLATE.replace("__N__", str(n)).replace("__DATA__", data)


TEMPLATE = r'''<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>поведение света</title>
<link href="https://fonts.googleapis.com/css2?family=Michroma&family=Inter:wght@300&display=swap" rel="stylesheet">
<style>
  html,body{margin:0;height:100%;overflow:hidden;background:#171a3a}
  canvas{position:fixed;inset:0;width:100%;height:100%;display:block;cursor:default}
  .cap{position:fixed;left:0;right:0;bottom:26px;text-align:center;font-family:"Michroma",system-ui,sans-serif;font-size:9px;letter-spacing:.34em;text-transform:uppercase;color:rgba(200,210,255,.55);pointer-events:none}
  .cap b{font-weight:400;color:rgba(230,236,255,.9)}
  .cap .buy{color:#cfe0ff}.cap .hold{color:#8fe0b8}.cap .close{color:#8f97c8}
  .hint{position:fixed;right:24px;bottom:26px;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.12em;color:rgba(200,210,255,.35);pointer-events:none}
  .tip{position:fixed;padding:6px 10px;border-radius:6px;background:rgba(10,12,30,.86);color:#dfe6ff;font-family:"Inter",system-ui,sans-serif;font-weight:300;font-size:11px;letter-spacing:.04em;max-width:360px;pointer-events:none;opacity:0;transition:opacity .2s}
</style>
</head>
<body>
<canvas id="c"></canvas>
<div class="hint">клик по имени — монета · мимо или клавиша — дальше</div>
<div class="tip" id="tip"></div>
<script id="introData" type="application/json">__DATA__</script>
<script>
const DATA=JSON.parse(document.getElementById('introData').textContent);
// группы: 0 — брать, 1 — держать, 2 — закрыть (владелец, 06.09)
const names=DATA.names.length?DATA.names:['—'],GRP=DATA.names.length?DATA.grp:[1];
const N=names.length,NF=4,FONT='Michroma';
const POS=DATA.names.length?DATA.pos:[[.5,.5]];
const LAB=DATA.label||[];
const c=document.getElementById('c');
const gl=c.getContext('webgl',{antialias:false,alpha:false});
const VS=`attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
const FS=`precision highp float;
uniform vec2 R;uniform float T,A;uniform vec2 P[${N}];uniform float F[${N}];uniform float G[${N}];uniform float BR[${N}];uniform sampler2D M;uniform vec2 S[${N*NF}];uniform float SP[${N*NF}];
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;mat2 m=mat2(1.6,1.2,-1.2,1.6);
  for(int i=0;i<6;i++){v+=a*noise(p);p=m*p;a*=.5;}return v;}
void main(){
  vec2 uv=gl_FragCoord.xy/R;float ar=R.x/R.y;vec2 p=(uv-.5)*vec2(ar,1.);vec2 px=gl_FragCoord.xy;
  vec2 q=vec2(fbm(p*2.4+vec2(0.,T*.13)),fbm(p*2.4+vec2(5.2,1.3)-vec2(T*.1,0.)));
  vec2 r=vec2(fbm(p*2.4+q*2.2+vec2(1.7,9.2)+T*.08),fbm(p*2.4+q*2.2+vec2(8.3,2.8)-vec2(0.,T*.07)));
  float d=fbm(p*2.4+r*2.6);
  float Fi=0.,Fm=0.,Gi=1.,Bi=1.,best=1e9;
  for(int i=0;i<${N};i++){float dd=length((uv-P[i])*vec2(ar,1.));if(dd<best){best=dd;Fi=F[i];Gi=G[i];Bi=BR[i];}Fm=max(Fm,F[i]);}
  float w=mix(.15,.01,Fi);
  vec2 mu=uv+(r-.5)*w;
  vec3 mk=texture2D(M,vec2(mu.x,1.-mu.y)).rgb;
  vec3 ms=texture2D(M,vec2(uv.x,1.-uv.y)).rgb;
  float core=ms.r,soft=ms.b,halo=mk.g;
  float isClose=step(1.5,Gi),isBuy=1.-step(.5,Gi),isHold=(1.-isClose)*(1.-isBuy);
  float er=smoothstep(.3,.75,fbm(px*.045+vec2(T*.12,-T*.05)))*(.45+.3*sin(T*.3))*isClose;
  core*=1.-er*.9;soft*=1.-er*.75;
  float drift=texture2D(M,vec2(uv.x-hash(px+3.)*.03,1.-(uv.y+hash(px+5.)*.016))).b*isClose;
  float wrap=(halo*(.35+.65*smoothstep(.25,.85,d))+mk.r*.4)*Fi;
  float blob=exp(-dot(p*vec2(1.1,.95),p*vec2(1.1,.95))*1.8);
  float cloud=smoothstep(.36,.85,d)*blob;
  float dens=clamp(cloud*(1.-Fm*.5)+wrap,0.,1.);
  vec3 bg=mix(vec3(.085,.095,.22),vec3(.16,.18,.36),uv.y*.8+exp(-dot(p,p)*1.6)*.35);
  vec3 deep=vec3(.20,.23,.52),mid=vec3(.44,.50,.86),hot=vec3(.80,.85,1.);
  vec3 col=mix(deep,mid,dens);col=mix(col,hot,pow(dens,2.5));
  col=bg+col*dens*1.15;
  col+=hot*pow(smoothstep(.55,.92,d)*max(cloud,wrap),3.)*.8;
  float vis=smoothstep(1.05-Fi*1.25,1.3-Fi*1.25,d+.1);
  float lvl=.82*Bi;   // общий уровень света имён понижен, яркость — по надёжности
  col+=vec3(.34,.38,.72)*(soft*.8+core*.15)*vis*lvl;
  col+=vec3(.36,.42,.8)*halo*vis*.4*Fi*lvl;
  float grain=hash(px*.9+floor(T*6.)*3.1);
  float crack=smoothstep(.62,.7,fbm(px*.06+vec2(T*.25,T*.1)+11.));
  col+=vec3(.55,.62,.95)*core*vis*(grain*.18+crack*.25);
  col+=vec3(.34,.38,.72)*drift*step(.55,hash(px*1.7+floor(T*5.)))*.4*vis;
  col+=vec3(.5,.56,.9)*halo*vis*.25*isBuy*(.5+.5*sin(T*2.));
  col+=vec3(.30,.78,.58)*(halo*.32+soft*.22)*vis*isHold*Fi;
  for(int i=0;i<${N*NF};i++){
    float on=smoothstep(.6,1.,F[i/${NF}])*(.55+.45*BR[i/${NF}]);   // блики тусклее у менее надёжных
    if(on<=0.)continue;
    float ph=SP[i];float gi=G[i/${NF}];
    vec3 fc=(gi>.5&&gi<1.5)?vec3(.72,1.,.86):vec3(.86,.96,1.);
    vec2 cc=S[i]*R+vec2(sin(T*1.9+ph*9.),cos(T*1.5+ph*5.))*1.4;
    vec2 dp=px-cc;float dist=length(dp);
    if(dist>mix(70.,160.,BR[i/${NF}]))continue;
    float ang=ph*6.28*.15+sin(T*.35+ph*4.)*.45;
    float cs=cos(ang),sn=sin(ang);vec2 dr=vec2(dp.x*cs-dp.y*sn,dp.x*sn+dp.y*cs);
    float pulse=.4+.6*pow(.5+.5*sin(T*1.3+ph*6.28),3.);
    if(gi>1.5)pulse*=step(.3,hash(vec2(floor(T*7.)+ph*13.,ph)));
    if(gi<.5)pulse=.7+.3*pulse;
    float k=exp(-dist*dist/5.);
    // ДЛИНА ЛУЧЕЙ — ПО НАДЁЖНОСТИ (06.09, владелец: «чем больше длина, тем надёжнее»):
    // у надёжной луч в три раза длиннее, у слабой — короткий
    float rb=BR[i/${NF}];float rk=mix(3.2,1.,rb);
    float st=exp(-abs(dr.y)*.9)*exp(-abs(dr.x)*.014*rk)*.7+exp(-abs(dr.x)*.9)*exp(-abs(dr.y)*.035*rk)*.4;
    vec2 dd=vec2(dr.x+dr.y,dr.x-dr.y)*.7071;
    st+=(exp(-abs(dd.x)*1.2)*exp(-abs(dd.y)*.08*rk)+exp(-abs(dd.y)*1.2)*exp(-abs(dd.x)*.08*rk))*.2;
    float glow=exp(-dist*.07)*.3;
    col+=fc*(k*1.8+st+glow)*pulse*on;
    float below=step(dp.y,0.)*smoothstep(gi>1.5?-130.:-70.,-8.,dp.y);
    float sig=2.+(-dp.y)*.05;
    float colm=exp(-dp.x*dp.x/(2.*sig*sig));
    float spd=gi<.5?-(45.+ph*30.):(gi>1.5?150.+ph*80.:60.+ph*50.);
    vec2 g=vec2(floor((px.x+ph*100.)/2.),floor((px.y+T*spd)/2.));
    float sp=step(gi>1.5?.962:.982,hash(g+ph));
    col+=fc*sp*colm*below*on*pulse*1.2;
  }
  vec2 sc=px/56.;vec2 cell=floor(sc),f=fract(sc);
  float h=hash(cell);vec2 spos=vec2(hash(cell+1.7),hash(cell+3.1));
  float ddd=length((f-spos)*56.);float sz=.5+h*1.1;
  float star=exp(-ddd*ddd/(sz*sz))*step(.78,h)*(.35+.65*(.5+.5*sin(T*.6+h*40.)));
  col+=vec3(.72,.75,.95)*star*.55;
  col*=A;
  gl_FragColor=vec4(col,1.);
}`;
function sh(t,s){const o=gl.createShader(t);gl.shaderSource(o,s);gl.compileShader(o);
  if(!gl.getShaderParameter(o,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(o);return o}
const prog=gl.createProgram();gl.attachShader(prog,sh(gl.VERTEX_SHADER,VS));gl.attachShader(prog,sh(gl.FRAGMENT_SHADER,FS));
gl.linkProgram(prog);gl.useProgram(prog);
gl.bindBuffer(gl.ARRAY_BUFFER,gl.createBuffer());
gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
const ap=gl.getAttribLocation(prog,'p');gl.enableVertexAttribArray(ap);gl.vertexAttribPointer(ap,2,gl.FLOAT,false,0,0);
const U=n=>gl.getUniformLocation(prog,n);const uR=U('R'),uT=U('T'),uF=U('F'),uA=U('A'),uS=U('S'),uSP=U('SP');
gl.uniform2fv(U('P'),new Float32Array(POS.flatMap(([x,y])=>[x,1-y])));gl.uniform1fv(U('G'),new Float32Array(GRP));
gl.uniform1fv(U('BR'),new Float32Array(DATA.names.length?DATA.bright:[1]));
const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
gl.uniform1i(U('M'),0);
const mc=document.createElement('canvas'),m=mc.getContext('2d');
let W,H,SIZE=14;
function mask(){
  mc.width=W;mc.height=H;
  m.globalCompositeOperation='source-over';m.fillStyle='#000';m.fillRect(0,0,W,H);
  const size=Math.min(21,Math.max(9,W*.012));SIZE=size;
  m.font=`400 ${size}px "${FONT}",system-ui,sans-serif`;m.textAlign='center';m.textBaseline='middle';
  m.letterSpacing='0.12em';
  m.globalCompositeOperation='lighter';
  for(let i=0;i<N;i++){const x=W*POS[i][0]+size*.06,y=H*POS[i][1],name=names[i];
    // подписи групп — кириллицей, Michroma её не знает: Inter, чуть крупнее и с разрядкой
    m.font=LAB[i]?`300 ${size*1.15}px "Inter",system-ui,sans-serif`:`400 ${size*.935}px "${FONT}",system-ui,sans-serif`;   // монеты на 6.5% мельче (06.09)
    m.letterSpacing=LAB[i]?'0.32em':'0.12em';
    m.fillStyle='#0f0';m.filter=`blur(${size*.16}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
    m.fillStyle='#00f';m.filter=`blur(${size*.035}px)`;m.fillText(name,x,y);m.fillText(name,x,y);
    m.fillStyle='#f00';m.filter='none';m.fillText(name,x,y);
    // подпись «что делать» под именем (группа «у цели»): хеджировать / ждать подтверждения / конец тренда
    const sub=(DATA.subs||[])[i];
    if(sub){m.font=`300 ${size*.62}px "Inter",system-ui,sans-serif`;m.letterSpacing='0.22em';
      m.fillStyle='#0f0';m.filter=`blur(${size*.1}px)`;m.fillText(sub,x,y+size*1.05);
      m.fillStyle='#00f';m.filter=`blur(${size*.03}px)`;m.fillText(sub,x,y+size*1.05);
      m.fillStyle='#f00';m.filter='none';m.fillText(sub,x,y+size*1.05);}
  }
  gl.bindTexture(gl.TEXTURE_2D,tex);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,mc);
  const img=m.getImageData(0,0,W,H).data,S=new Float32Array(N*NF*2).fill(-1),SP=new Float32Array(N*NF);
  for(let i=0;i<N;i++){const x=W*POS[i][0]+size*.06,y=H*POS[i][1],name=names[i];
    for(let n=0,tries=0;n<NF&&tries<4000;tries++){
      const px=Math.floor(x+(Math.random()-.5)*name.length*size*1.2),py=Math.floor(y+(Math.random()-.5)*size);
      if(px<0||py<0||px>=W||py>=H)continue;
      if(img[(py*W+px)*4]>140){S[(i*NF+n)*2]=px/W;S[(i*NF+n)*2+1]=1-py/H;SP[i*NF+n]=Math.random();n++}
    }
  }
  gl.uniform2fv(uS,S);gl.uniform1fv(uSP,SP);
}
const T_IN=2.8,GAP=Math.max(1.4,Math.min(3.0,24/N));   // при 12 именах — по 2 с, чтобы созвездие собралось за полминуты
const ease=x=>x*x*(3-2*x);
const Fv=new Float32Array(N);
function resize(){const d=Math.min(devicePixelRatio,1.5);W=innerWidth;H=innerHeight;
  c.width=W*d;c.height=H*d;gl.viewport(0,0,c.width,c.height);gl.uniform2f(uR,c.width,c.height);mask()}
addEventListener('resize',resize);
let start=null;
function loop(now){
  now/=1000;if(start===null)start=now;
  for(let i=0;i<N;i++){const t=now-start-.6-i*GAP;Fv[i]=t<=0?0:t>=T_IN?1:ease(t/T_IN)}
  gl.uniform1fv(uF,Fv);gl.uniform1f(uT,now);gl.uniform1f(uA,Math.min(1,(now-start)/1.5));
  gl.drawArrays(gl.TRIANGLE_STRIP,0,4);
  requestAnimationFrame(loop);
}
// ── взаимодействие (06.09): клик по имени — монета; мимо или клавиша — дальше по оболочке ──
function hit(ev){const x=ev.clientX,y=ev.clientY;
  for(let i=0;i<N;i++){if(LAB[i])continue;const cx=W*POS[i][0],cy=H*POS[i][1],hw=names[i].length*SIZE*.62+8,hh=SIZE*.9+6;
    if(Math.abs(x-cx)<=hw&&Math.abs(y-cy)<=hh)return i;}return -1;}
const tip=document.getElementById('tip');
c.addEventListener('mousemove',ev=>{const i=hit(ev);c.style.cursor=i>=0?'pointer':'default';
  if(i>=0&&DATA.whys[i]){tip.textContent=names[i]+' — '+DATA.whys[i];tip.style.left=(ev.clientX+14)+'px';tip.style.top=(ev.clientY+12)+'px';tip.style.opacity=1}else tip.style.opacity=0});
function next(){try{window.parent.postMessage({type:'ob:done',screen:'intro'},'*')}catch(e){}
  if(window===window.parent)location.href='brief.html'}
c.addEventListener('click',ev=>{const i=hit(ev);
  if(i>=0){const target='coin.html#'+encodeURIComponent(names[i]);
    if(window!==window.parent){try{window.parent.postMessage({type:'ob:open',screen:'coin',hash:names[i]},'*')}catch(e){}}
    location.href=target;return}
  next()});
addEventListener('keydown',ev=>{if(ev.key==='Escape'||ev.key===' '||ev.key==='Enter'||ev.key==='ArrowRight')next()});
// шрифты (06.09): ждём оба — Michroma для имён и Inter для подписей; сеть молчит — стартуем
// через полторы секунды на системном, чтобы не было пустого экрана и «script error» при первом заходе
const ready=document.fonts?Promise.race([
  Promise.all([document.fonts.load(`400 40px "${FONT}"`),document.fonts.load(`300 40px "Inter"`)]).catch(()=>{}),
  new Promise(r=>setTimeout(r,1500))]):Promise.resolve();
let started=false;
ready.then(()=>{if(started)return;started=true;try{resize();requestAnimationFrame(loop)}catch(e){console.error('интро:',e)}});
</script>
</body>
</html>
'''
