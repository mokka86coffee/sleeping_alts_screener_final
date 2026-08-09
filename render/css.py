"""Стили отчёта. Дашборд по макету SLEEPING ALTS.

Три типа контейнера: bare (без рамки, только свечение), card (тёмная
карточка с градиентной обводкой), glass (стеклянная панель с верхним
бликом). Медиазапросы идут последними.
"""

# ═══════════════════════════════════════════════════
# ТОКЕНЫ · цвета сняты с макета
# ═══════════════════════════════════════════════════
TOKENS = """
:root{
  --bg:#08080b;
  --card1:#1a1a21;   --card2:#131318;
  --am:#F5A623;      --am-l:#FFD98A;  --am-n:#FFE0A0;  --am-d:#B36A10;
  --bl:#3E9BE0;      --bl-l:#BFE4FF;
  --gd:#E0C060;      --gd-n:#D9B84A;  --gd-b:#C9AC4A;
  --gr:#4FCF8A;      --gr-l:#A8F0C8;  --gr-n:#7FEBAE;
  --vi:#A47AE0;      --vi-l:#D8C0F8;
  --ru:#C4703A;      --st:#8FA0B0;    --st-l:#a8b2bc;  --gl:#C8DCE8;
  --t1:#f2f2f5;      --t2:#e8eaee;    --t3:#c8ccd4;
  --m1:#9aa0a8;      --m2:#6a6e77;    --m3:#5e626b;
  --m4:#4a4a56;      --m5:#3e3e48;    --m6:#33333c;
  --trk:#1c1c22;     --hr:#1a1a20;
  --glass:linear-gradient(140deg,rgba(143,180,200,.07),rgba(74,96,112,.03) 40%,
          rgba(127,168,192,.05) 75%,rgba(58,74,88,.02));
  --glassG:linear-gradient(140deg,rgba(127,200,168,.06),rgba(58,106,86,.025) 40%,
          rgba(111,184,148,.045) 75%,rgba(46,74,62,.02));
  --glassW:linear-gradient(115deg,rgba(143,180,200,.055),rgba(74,96,112,.022) 30%,
          rgba(127,168,192,.04) 62%,rgba(111,184,148,.035));
  --rim:linear-gradient(135deg,rgba(200,220,232,.38),rgba(122,140,154,.1) 35%,
          rgba(200,220,232,.22) 65%,rgba(90,106,120,.08));
  --rimG:linear-gradient(135deg,rgba(168,232,200,.34),rgba(90,140,116,.09) 35%,
          rgba(168,232,200,.2) 65%,rgba(58,90,74,.07));
  --rimW:linear-gradient(90deg,rgba(200,220,232,.3),rgba(122,140,154,.1) 30%,
          rgba(143,168,184,.12) 70%,rgba(168,232,200,.3));
  --card:#0e0e12;   --panel:#16161c;  --panel2:#121217; --panel3:#0f0f14;
  --line:#22222a;   --line2:#1a1a22;
  --am1:#FFD24A;    --am2:#F0A800;    --am3:#e0b850;
  --am4:#c9a24a;    --am5:#a8863a;    --am6:#8a6a2a;
  --txt:#e8e8f0;    --txt2:#c8c8d4;
  --mut:#6b6b76;    --mut2:#4e4e58;   --mut3:#3f3f48;  --ghost:#2e2e36;
   --up:#7fbf8f;     --dn:#e39a9a;
   --serif:Georgia,'Times New Roman',serif;
  --mono:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',monospace;
}
"""
# ═══════════════════════════════════════════════════
# БАЗА · ФОН
# ═══════════════════════════════════════════════════
BASE = """
*{box-sizing:border-box}
body{
  background:var(--bg);color:var(--t2);margin:0;padding:0;
  font-family:'Helvetica Neue',Inter,-apple-system,BlinkMacSystemFont,Arial,sans-serif;
  font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased;
  overflow-x:hidden;
}
body::-webkit-scrollbar {
  width: 1px; /* ширина полосы */
}
body::-webkit-scrollbar-track {
  background: #888; /* цвет дорожки */
}
body::-webkit-scrollbar-thumb {
  background-color: #888; /* цвет бегунка */
  border-radius: 5px; /* скруглённые углы */
  border: 1px solid orange; /* граница */
  box-shadow: inset 0 0 5px #000; /* внутренняя тень для глубины */
}

a{text-decoration:none;color:inherit}
summary{cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
.up{color:var(--up)}
.dn{color:var(--dn)}

[data-slice],[data-coin]{cursor:pointer}
.hide{display:none !important}

.bg{position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(circle 360px at 20% 22%,rgba(245,166,35,.05),transparent 70%),
    radial-gradient(circle 380px at 82% 76%,rgba(62,155,224,.045),transparent 70%);}
.bg svg{position:absolute;inset:0;width:100%;height:100%}

.screen{position:relative;z-index:1;max-width:1390px;margin:0 auto;padding:34px 20px 60px}
#panes{display:none}
#panes.on{display:block}
"""

# ═══════════════════════════════════════════════════
# ШАПКА
# ═══════════════════════════════════════════════════
HEAD = """
.hd{display:flex;align-items:center;gap:24px;margin-bottom:46px}
.hd-t{font-size:17px;font-weight:200;letter-spacing:7px;color:var(--t1);margin:0}
.hd-d{font-size:8px;font-weight:300;letter-spacing:3px;color:#43434e;margin-top:6px}

.cap{margin-left:auto;position:relative;display:flex;align-items:center;gap:22px;
  height:40px;padding:0 20px;border-radius:20px;background:var(--glass)}
.cap::before{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;
  background:var(--rim);-webkit-mask:linear-gradient(#000 0 0) content-box,
  linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;
  pointer-events:none}
.cap::after{content:'';position:absolute;top:0;left:18%;right:18%;height:1px;
  background:linear-gradient(90deg,transparent,rgba(200,220,232,.45) 30%,
  rgba(200,220,232,.45) 70%,transparent)}
.cap-g{display:flex;align-items:center;gap:10px}
.cap-k{font-size:7px;font-weight:300;letter-spacing:3px;color:#4e5560}
.cap-v{font-size:11px;font-weight:300;letter-spacing:3px;color:#E8EEF4;margin-top:4px}
.cap-dots{display:flex;gap:4px}
.cap-dots i{width:12px;height:2.5px;border-radius:1.2px;background:#2e3238}
.cap-dots i.on{background:#D8E4EE}
.cap-ap{font-size:8px;font-weight:300;color:#5a6068;letter-spacing:1px}
.cap-btc{text-align:left}
.cap-btc b{display:block;font-size:10px;font-weight:200;color:var(--st-l);
  letter-spacing:1px;margin-top:4px}
"""

# ═══════════════════════════════════════════════════
# СЕТКА И КАРКАС БЛОКА
# ═══════════════════════════════════════════════════
BLOCK = """
.row{display:grid;align-items:start;margin-bottom:52px}
.row-1{grid-template-columns:272fr 204fr 236fr 316fr;gap:30px;margin-top:34px}
.row-2{grid-template-columns:492fr 192fr 316fr;gap:52px}

.b{position:relative;padding:30px 0 0}
.halo{position:absolute;top:-14px;left:50%;transform:translateX(-50%);
  width:118%;height:104px;border-radius:50%;pointer-events:none;filter:blur(18px);
  background:radial-gradient(ellipse at 50% 0,var(--h1),var(--h2) 45%,transparent 72%)}

.g-set .halo{width:86%;height:112px}
.g-sect .halo{width:100%}
.fn .halo{width:76%;height:96px}

.c-am{--c:var(--am);--h1:rgba(245,166,35,.5);--h2:rgba(179,106,16,.1)}
.c-bl{--c:var(--bl);--h1:rgba(62,155,224,.4);--h2:rgba(42,106,160,.1)}
.c-gd{--c:var(--gd);--h1:rgba(224,192,96,.36);--h2:rgba(154,132,48,.09)}
.c-gr{--c:var(--gr);--h1:rgba(79,207,138,.38);--h2:rgba(46,138,90,.1)}
.c-vi{--c:var(--vi);--h1:rgba(164,122,224,.38);--h2:rgba(106,74,160,.1)}
.c-wh{--c:var(--gl);--h1:rgba(200,220,232,.22);--h2:rgba(106,122,136,.07)}

.b.empty{opacity:.5}
.b.empty .dial-v{fill:#5a6470}

.b-in{position:relative;padding:0 4px}

.b-card>.b-in{padding:13px 18px 3px;border-radius:18px;
  background:linear-gradient(180deg,var(--card1),var(--card2));
  box-shadow:0 18px 34px rgba(0,0,0,.55)}
.b-card>.b-in::before{content:'';position:absolute;inset:0;border-radius:inherit;
  padding:1px;background:linear-gradient(180deg,var(--e1),var(--e2) 55%,var(--e3));
  -webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);
  -webkit-mask-composite:xor;mask-composite:exclude;pointer-events:none}
.c-bl.b-card{--e1:rgba(62,155,224,.45);--e2:rgba(62,155,224,.05);--e3:rgba(62,155,224,.02)}
.c-vi.b-card{--e1:rgba(164,122,224,.42);--e2:rgba(164,122,224,.05);--e3:rgba(164,122,224,.02)}

.b-glass>.b-in{padding:26px 20px 20px;border-radius:16px;background:var(--glass)}
.b-glass.g-pool>.b-in{background:var(--glass),
  radial-gradient(ellipse 55% 55% at 50% 55%,rgba(168,200,220,.1),transparent 70%)}
.b-glass>.b-in::before{content:'';position:absolute;inset:0;border-radius:inherit;
  padding:1px;background:var(--rim);-webkit-mask:linear-gradient(#000 0 0) content-box,
  linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;
  pointer-events:none}
.b-glass>.b-in::after{content:'';position:absolute;top:0;left:19%;right:19%;height:1px;
  background:linear-gradient(90deg,transparent,rgba(200,220,232,.45) 30%,
  rgba(200,220,232,.45) 70%,transparent)}
.b-glass.gl-gr>.b-in{background:var(--glassG),
  radial-gradient(ellipse 60% 60% at 50% 40%,rgba(143,220,180,.07),transparent 70%)}
.b-glass.gl-gr>.b-in::before{background:var(--rimG)}
.b-glass.gl-gr>.b-in::after{background:linear-gradient(90deg,transparent,
  rgba(168,232,200,.4) 30%,rgba(168,232,200,.4) 70%,transparent)}

.b-ic{position:relative;width:30px;height:30px;margin:0 auto;
  display:flex;align-items:center;justify-content:center}
.b-ic::before{content:'';position:absolute;inset:0;border-radius:50%;
  background:var(--c);opacity:.26;filter:blur(7px)}
.b-ic svg{position:relative;width:26px;height:26px;overflow:visible}

.b-t{margin-top:16px;text-align:center;font-size:11px;font-weight:300;
  line-height:1.25;letter-spacing:3px;color:var(--t2)}
.b-t span{font-size:12px;font-weight:300;letter-spacing:2px;
  color:var(--m2);opacity:1;margin-left:9px}
.b-t.wide{font-size:11px;font-weight:300;letter-spacing:5px;
  color:#c8d4de;margin-top:0}

.big{display:block;text-align:center;font-size:58px;font-weight:100;
  letter-spacing:4px;line-height:1;color:var(--am-n);margin-top:30px}
.big-u{display:block;text-align:center;font-size:7.5px;font-weight:300;
  letter-spacing:2.5px;color:var(--m3);margin-top:12px}
.hr{height:1px;background:var(--hr);margin:14px 0 0}
.note{font-size:7px;font-weight:300;letter-spacing:1.5px;color:#43434e;margin-top:12px}
.note.mid{text-align:center}
"""

# ═══════════════════════════════════════════════════
# ОБЪЁМЫ
# ═══════════════════════════════════════════════════
VOL = """
.vol-chart{margin-top:26px}
.vol-chart.dim{opacity:.3}
.vol-chart svg{display:block;width:100%;height:48px;overflow:visible}
.vol-legend{display:flex;justify-content:space-between;font-size:7.5px;
  font-weight:300;letter-spacing:1px;color:var(--m2);margin-top:14px}
.vol-call{position:absolute;top:-4px;right:-6px;text-align:right;pointer-events:none}
.vol-call b{display:block;font-size:10px;font-weight:200;letter-spacing:2px;color:#8a8f98}
.vol-call i{display:block;font-style:normal;font-size:6.5px;font-weight:300;
  letter-spacing:1.5px;color:var(--m5);margin-top:3px}
.vol-hook{position:absolute;top:14px;right:38px;width:52px;height:32px}
"""

# ═══════════════════════════════════════════════════
# СОЦСЕТИ
# ═══════════════════════════════════════════════════
SOC = """
.dial{display:block;margin:3px auto 0;width:64px;height:64px}
.dial-v{font-size:26px;font-weight:100;letter-spacing:1px;fill:var(--bl-l)}
.soc-sub{text-align:center;font-size:7px;font-weight:300;letter-spacing:2px;
  color:var(--m3);margin-top:4px}
.pill{position:relative;z-index:2;display:flex;align-items:center;justify-content:center;
  gap:10px;min-width:120px;height:28px;margin:-11px auto -14px;padding:0 12px;
  border-radius:14px;background:#111319;border:1px solid #213038;
  box-shadow:0 8px 16px rgba(0,0,0,.6)}
.pill i{width:7px;height:7px;border-radius:50%;background:var(--bl);flex:none}
.pill b{font-size:9px;font-weight:300;letter-spacing:1.5px;color:var(--bl-l);
  white-space:nowrap}
"""

# ═══════════════════════════════════════════════════
# ПАТТЕРНЫ · СЕКТОРА · общие полосы
# ═══════════════════════════════════════════════════
BARS = """
.rows{margin-top:24px}
.brow{display:grid;grid-template-columns:58px 1fr 34px;align-items:center;gap:12px;
  padding:6px 0;font-size:8px;font-weight:300;letter-spacing:1.5px}
.brow-n{color:var(--m2)}
.brow-t{position:relative;height:4px;border-radius:2px;background:var(--trk)}
.brow-t i{position:absolute;top:0;left:0;height:4px;border-radius:2px;background:var(--bc)}
.brow-v{text-align:right;font-size:10px;font-weight:200;color:var(--bc)}
.brow.off{opacity:.35}
.p-taiko{--bc:linear-gradient(90deg,#B87A18,#FFD98A)}
.p-taiko .brow-v{color:#F5C880}
.p-dexe{--bc:var(--ru)}
.p-dexe .brow-v{color:var(--ru)}
.p-strong{--bc:var(--gd-b)}
.p-strong .brow-v{color:var(--gd-n)}
.p-good{--bc:var(--gr)}
.p-good .brow-v{color:var(--gr)}

.srow{display:grid;grid-template-columns:74px 1fr 62px;align-items:center;gap:14px;
  padding:6px 0;font-size:8px;font-weight:300;letter-spacing:1.5px}
.srow-n{color:var(--m1);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.srow-t{position:relative;height:4px;border-radius:2px;background:var(--trk)}
.srow-t i{position:absolute;top:0;height:4px;border-radius:2px;min-width:6px}
.srow-t i.up{left:50%;background:var(--gr)}
.srow-t i.dn{right:50%;background:var(--ru)}
.srow-v{text-align:right;font-size:10px;font-weight:200}
.srow-v.up{color:var(--gr)}
.srow-v.dn{color:var(--ru)}
"""

# ═══════════════════════════════════════════════════
# СЕТАПЫ
# ═══════════════════════════════════════════════════
SET = """
.g-set .b-t{white-space:nowrap}
.g-set .b-t span{font-size:12px}
.set-list{margin-top:22px}
.set-row{display:grid;grid-template-columns:1fr 26px 62px 92px;align-items:center;
  gap:14px;padding:14px 18px;border-top:1px solid rgba(168,232,200,.07);
  transition:background .12s}
.set-row:hover{background:rgba(168,232,200,.03)}
.set-sym{font-size:12px;font-weight:300;letter-spacing:1.5px;color:var(--t2)}
.set-sub{font-size:7px;font-weight:300;letter-spacing:1px;color:#55625b;margin-top:5px}
.set-dial{width:26px;height:26px;overflow:visible}
.set-rr{font-size:15px;font-weight:200;letter-spacing:1px}
.set-rr.gr{color:var(--gr)}
.set-rr.am{color:var(--am)}
.set-in{font-size:8px;font-weight:300;letter-spacing:1px;color:#6a7a72}
.set-empty{padding:26px 0;text-align:center;font-size:8px;font-weight:300;
  letter-spacing:2px;color:var(--m4)}
"""

# ═══════════════════════════════════════════════════
# ИМПУЛЬС
# ═══════════════════════════════════════════════════
IMP = """
.imp-bars{display:flex;align-items:flex-end;justify-content:center;gap:10px;
  height:48px;margin-top:30px}
.imp-bars i{width:12px;border-radius:2px;background:var(--trk)}
.imp-bars i.on{background:var(--am)}
.imp-bars.dim{opacity:.25}
"""

# ═══════════════════════════════════════════════════
# РИСК
# ═══════════════════════════════════════════════════
RISK = """
.g-risk{min-height:184px}
.g-risk>.b-in{padding:14px 34px 10px;overflow:visible}

.risk-cap{position:absolute;top:-34px;right:0;z-index:2;display:flex;
  align-items:center;gap:8px;height:26px;padding:0 14px;border-radius:13px;
  background:var(--glass);border:1px solid rgba(200,220,232,.16)}
.risk-cap span{display:flex;flex-direction:column;align-items:flex-start;
  line-height:1}
.risk-cap b{font-size:10px;font-weight:200;letter-spacing:1px;color:#dfe8f0}
.risk-cap b i{font-style:normal;font-size:6.5px;color:#7d8994;letter-spacing:1.5px}
.risk-cap s{text-decoration:none;font-size:5.5px;font-weight:300;
  letter-spacing:2px;color:#5e6a76;margin-top:3px}
.risk-cap svg{width:14px;height:8px;flex:none}

.risk-mid{position:relative;margin-top:16px;height:92px;
  display:flex;flex-direction:column;align-items:center;justify-content:center}
.risk-orbit{position:absolute;left:50%;top:50%;
  transform:translate(-50%,-50%);width:100%;height:76px;
  overflow:visible;pointer-events:none;z-index:0}
.risk-k{position:relative;z-index:1;font-size:6.5px;font-weight:300;
  letter-spacing:3px;color:#7d8994}
.risk-v{position:relative;z-index:1;font-size:50px;font-weight:100;
  letter-spacing:3px;color:#f2f8fc;line-height:1;margin-top:6px}

.risk-arc{position:absolute;top:50%;transform:translateY(-50%);
  width:34px;height:78px;pointer-events:none;z-index:1}
.risk-arc.l{left:6px}
.risk-arc.r{right:6px}
.risk-arc svg{width:100%;height:100%}
.risk-arc span{position:absolute;top:50%;left:50%;
  font-size:6px;font-weight:300;letter-spacing:1.5px;color:#8494a2;
  white-space:nowrap}
.risk-arc.l span{transform:translate(-50%,-50%) rotate(-90deg)}
.risk-arc.r span{transform:translate(-50%,-50%) rotate(90deg)}

.risk-legs{position:relative;z-index:1;display:flex;justify-content:center;
  gap:24px;margin-top:12px;font-size:6.5px;font-weight:300;letter-spacing:1.5px}
.risk-legs span{color:#6a7682}
.risk-legs b{font-size:9px;font-weight:200;margin-left:8px}
.risk-legs b.ru{color:var(--ru)}
.risk-legs b.gl{color:#c8d4de}
.risk-legs b.st{color:#94a0aa}
"""

# ═══════════════════════════════════════════════════
# ВОРОНКА
# ═══════════════════════════════════════════════════
FUNNEL = """
.fn{position:relative;margin-bottom:40px}
.fn-cap{position:absolute;top:-12px;left:50%;transform:translateX(-50%);z-index:2;
  height:24px;padding:0 22px;border-radius:12px;background:#0c0e11;
  border:1px solid rgba(200,220,232,.2);display:flex;align-items:center;
  font-size:7px;font-weight:300;letter-spacing:4px;color:#8a95a0}
.fn-in{position:relative;padding:52px 44px 42px;border-radius:20px;background:var(--glassW),
  radial-gradient(ellipse 60% 60% at 88% 50%,rgba(143,220,180,.07),transparent 60%)}
.fn-in::before{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;
  background:var(--rimW);-webkit-mask:linear-gradient(#000 0 0) content-box,
  linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;
  pointer-events:none}
.fn-in::after{content:'';position:absolute;top:0;left:18%;right:18%;height:1px;
  background:linear-gradient(90deg,transparent,rgba(200,220,232,.4) 22%,
  rgba(168,232,200,.4) 78%,transparent)}

.fn-line{position:absolute;left:82px;right:114px;top:104px;height:1.2px;
  background:linear-gradient(90deg,rgba(138,143,152,.3),rgba(245,166,35,.45) 32%,
  rgba(196,112,58,.4) 62%,rgba(79,207,138,.7))}
.fn-nodes{position:relative;display:flex;align-items:flex-start;
  justify-content:space-between}
.fn-node{position:relative;text-align:center;width:76px}
.fn-node svg{display:block;margin:0 auto;overflow:visible}
.fn-v{font-size:18px;font-weight:100;letter-spacing:1px;fill:var(--t3)}
.fn-l{display:block;font-size:6.5px;font-weight:300;letter-spacing:2px;
  color:var(--m4);margin-top:16px}
.fn-node.last .fn-v{fill:var(--gr-n);font-size:23px}
.fn-node.last .fn-l{color:#4a5a52}
.fn-node[data-slice]:hover .fn-l{color:var(--t3)}
.fn-gap{position:relative;flex:1;text-align:center;font-size:6px;font-weight:300;
  letter-spacing:1.5px;color:var(--m5);padding-top:36px}
.fn-foot{display:flex;justify-content:space-between;margin-top:24px;
  font-size:6.5px;font-weight:300;letter-spacing:2px;color:var(--m6)}
.fn-foot b{font-weight:300;color:#3a3a44}
"""

# ═══════════════════════════════════════════════════
# ТАБЛИЦЫ СРЕЗОВ · МОДАЛКА
# ═══════════════════════════════════════════════════
PANES = """
.pane{display:none;padding-top:10px}
.pane.on{display:block}
.pane-hd{display:flex;align-items:baseline;gap:12px;padding-bottom:18px;
  margin-bottom:6px;border-bottom:1px solid rgba(200,220,232,.08)}
.pane-back{align-self:center;font-family:inherit;font-size:7px;font-weight:300;
  letter-spacing:3px;color:#8a95a0;background:var(--glass);
  border:1px solid rgba(200,220,232,.16);border-radius:13px;height:26px;
  padding:0 16px;cursor:pointer;flex:none}
.pane-back:hover{color:var(--t2)}
.pane-t{font-size:14px;font-weight:400;letter-spacing:2px;color:var(--t2)}
.pane-c{font-size:9px;font-weight:200;letter-spacing:1px;color:var(--am-n);
  font-variant-numeric:tabular-nums}
.pane-n{font-size:7px;font-weight:300;letter-spacing:2px;color:var(--m4);margin-left:auto}

.modal{display:none;position:fixed;inset:0;z-index:900}
.modal.on{display:block}
.modal-bd{position:absolute;inset:0;background:rgba(6,7,9,.86);backdrop-filter:blur(6px)}
.modal-in{position:relative;z-index:1;max-width:580px;margin:40px auto;
  max-height:calc(100vh - 80px);overflow-y:auto;padding:0 16px 40px}
.modal-x{position:sticky;top:0;margin-left:auto;display:block;width:32px;height:32px;
  border-radius:50%;background:rgba(255,255,255,.08);
  border:1px solid rgba(200,220,232,.16);color:var(--t3);font-size:13px;cursor:pointer}
"""

# ═══════════════════════════════════════════════════
# ТАБЛИЦА ВЫБОРКИ · терминальный режим, 20+ колонок
# Первые четыре колонки закреплены через position:sticky.
# Ширины закреплённых колонок и их смещения слева должны
# совпадать: 34 / 104 / 74 / 84 → left 0 / 34 / 138 / 212.
# ═══════════════════════════════════════════════════
SCAN = """
.scan{margin-top:56px}
.sx-hint{font-size:7px;font-weight:300;letter-spacing:2px;color:var(--m5);
  margin:10px 0 14px}

.sx-empty{padding:52px 0;text-align:center;font-size:8px;font-weight:300;
  letter-spacing:2px;color:var(--m4)}

.sx-wrap{position:relative;overflow-x:auto;overflow-y:visible;
  border-radius:14px;background:linear-gradient(180deg,#15161c,#101116);
  border:1px solid rgba(200,220,232,.1);
  scrollbar-width:thin;scrollbar-color:#2a2c34 transparent}
.sx-wrap::-webkit-scrollbar{height:8px}
.sx-wrap::-webkit-scrollbar-thumb{background:#24262e;border-radius:4px}
.sx-wrap::-webkit-scrollbar-track{background:transparent}

.sx{border-collapse:separate;border-spacing:0;width:max-content;min-width:100%}
.sx th{position:sticky;top:0;z-index:3;background:#0d0e12;
  font-size:8px;font-weight:600;letter-spacing:2px;color:#b0b0b0;
  text-align:left;padding:14px 14px 10px;white-space:nowrap;
  border-bottom:1px solid rgba(200,220,232,.09)}
.sh th::first-letter {
 color: white;
 font-size: 11px;
}
.sx td{padding:10px 14px;vertical-align:middle;white-space:nowrap;
  border-bottom:1px solid rgba(200,220,232,.045)}

.sxr{transition:background .12s}
.sxr:hover{background:rgba(255,255,255,.022)}
.sxr td:first-child{position:relative}
.sxr td:first-child::before{content:'';position:absolute;left:0;top:6px;bottom:6px;
  width:2px;border-radius:1px;background:var(--acc);opacity:0;transition:opacity .12s}
.sxr:hover td:first-child::before{opacity:.8}
.sxr.vetoed{opacity:.62}
.sxr.faded{opacity:.4}

/* ── закреплённые колонки ── */
.sx .sx-idx{position:sticky;left:0;z-index:2;width:34px;background:#0d0e12}
.sx .sx-c-sym{position:sticky;left:34px;z-index:2;width:104px;background:#0d0e12}
.sx .sx-c-soc{position:sticky;left:138px;z-index:2;width:74px;background:#0d0e12}
.sx .sx-c-surge{position:sticky;left:212px;z-index:2;width:84px;background:#0d0e12;
  box-shadow:10px 0 14px -8px rgba(0,0,0,.85)}
.sx th.sx-idx,.sx th.sx-c-sym,.sx th.sx-c-soc,.sx th.sx-c-surge{z-index:4}
.sxr:hover .sx-idx,.sxr:hover .sx-c-sym,
.sxr:hover .sx-c-soc,.sxr:hover .sx-c-surge{background:#12141a}

.sx-idx{font-size:9px;font-weight:200;color:#3a3e46;
  font-variant-numeric:tabular-nums}

.sx-sym{display:inline-flex;align-items:center;gap:5px;font-size:13px;
  font-weight:300;letter-spacing:1.2px;color:#eceef2;text-decoration:none}
.sx-sym svg{width:8px;height:8px;opacity:0;transition:opacity .12s;color:var(--am)}
.sx-sym:hover{color:var(--am-l)}
.sx-sym:hover svg{opacity:1}
.sx-sub{display:block;font-size:6.5px;font-weight:300;letter-spacing:1.2px;
  margin-top:3px}
.sx-sub2{display:block;font-size:6.5px;font-weight:300;letter-spacing:1.2px;
  color:#565b64;margin-top:4px}
.sx-mut{font-size:10px;color:#3e424a}

/* ── примитивы ── */
.sx-ring{display:block;width:32px;height:32px;overflow:visible}
.sx-ring-v{font-size:10px;font-weight:200;fill:var(--t3)}
td:nth-child(6) .sx-ring{width:36px;height:36px}

.sx-bar{position:relative;display:block;height:3px;border-radius:1.5px;
  background:#1b1c22;margin-top:5px;overflow:hidden}
.sx-bar i{position:absolute;left:0;top:0;height:100%;border-radius:1.5px;
  min-width:3px}

.sx-n{font-size:11px;font-weight:200;letter-spacing:.5px;color:var(--t3);
  font-variant-numeric:tabular-nums}
.sx-n.up{color:var(--gr)}
.sx-n.dn{color:var(--ru)}
.sx-n.am{color:var(--am-l)}
.sx-n.mut{color:#7a7f88}

.sx-rr{font-size:14px;font-weight:200;letter-spacing:.8px;
  font-variant-numeric:tabular-nums}
.sx-rr.up{color:var(--gr)}
.sx-rr.am{color:var(--am)}
.sx-rr.mut{color:#43474f}

.sx-badge{display:inline-flex;align-items:center;height:16px;padding:0 8px;
  border-radius:8px;font-size:10px;font-weight:300;letter-spacing:.8px;
  color:var(--bc);background:color-mix(in srgb,var(--bc) 12%,transparent);
  border:1px solid color-mix(in srgb,var(--bc) 38%,transparent)}
.sx-badge.off{opacity:.3}
.sx-chips{display:flex;gap:5px;flex-wrap:nowrap}

.sx-steps{display:flex;gap:3px}
.sx-steps i{width:12px;height:3px;border-radius:1.5px;background:#25262d}
.sx-steps i.on{background:var(--sc)}

.sx-sb{display:flex;align-items:flex-end;gap:2.5px;height:22px;width:56px}
.sx-sb i{flex:1;border-radius:1px;background:var(--sbc);opacity:.4}
.sx-sb i.last{opacity:1}
.sx-sb.empty{opacity:.15;border-bottom:1px solid #2a2c34}

.sx-sl{display:block;width:72px;height:26px;overflow:visible}
.sx-sl.empty{display:block;width:72px;height:1px;background:#22242a;margin:12px 0}

.sx-soc{display:flex;align-items:center;gap:7px}
.sx-soc-l{font-size:7px;font-weight:300;letter-spacing:1.2px;color:#3e4650}
.sx-soc-l.hot{color:var(--bl)}
.sx-soc-l.warm{color:#3a6a90}
.sx-soc-l b{display:block;font-size:6.5px;font-weight:300;color:#4a505a;
  margin-top:2px}

.sx-surge,.sx-taiko{display:flex;flex-direction:column;align-items:flex-start}

.sx-veto{display:flex;align-items:center;gap:8px}
.sx-dots{display:flex;gap:4px}
.sx-dots i{width:7px;height:7px;border-radius:50%;background:#1e2026;
  border:1px solid #2a2c32}
.sx-dots i.on{border-color:transparent}
.sx-veto-l{font-size:7.5px;font-weight:300;letter-spacing:1px}
.sx-veto-l.ok{color:#4a6a58}
.sx-veto-l.bad{color:var(--ru)}

.sx-bp{position:relative;display:block;width:64px;height:4px;border-radius:2px;
  background:#1b1c22}
.sx-bp::after{content:'';position:absolute;left:50%;top:-3px;width:1px;height:10px;
  background:#3a3a44}
.sx-bp i{position:absolute;top:0;height:100%;border-radius:2px;min-width:2px}
.sx-bp-v{display:block;font-size:8px;font-weight:200;margin-top:5px;
  font-variant-numeric:tabular-nums}

.sx-lv{position:relative;display:block;width:78px;height:8px}
.sx-lv::before{content:'';position:absolute;left:0;right:0;top:3.5px;height:1px;
  background:#22242a}
.sx-lv i{position:absolute;top:0}
.sx-lv i.s{left:0;width:3px;height:8px;border-radius:1.5px;background:var(--ru)}
.sx-lv i.t{right:0;width:3px;height:8px;border-radius:1.5px;background:var(--gr)}
.sx-lv i.e{width:6px;height:6px;top:1px;border-radius:50%;background:var(--gl);
  transform:translateX(-50%)}
.sx-lv.empty{font-size:6.5px;color:#3a3a44;letter-spacing:1px;
  width:auto;height:auto}
.sx-lv-v{display:block;font-size:7px;font-weight:300;color:#4a505a;margin-top:5px;
  font-variant-numeric:tabular-nums}

.sx-act{font-size:8px;font-weight:300;letter-spacing:1.5px;color:var(--m3)}
.sx-act.go{color:var(--gr)}
.sx-act.mut{color:#43474f}

.sx-f{display:flex;align-items:center;gap:18px;margin-top:16px;
  font-size:7px;font-weight:300;letter-spacing:2px;color:var(--m5)}
.sx-f-m{color:var(--am-d)}
.sx-f-r{margin-left:auto}
"""

# ═══════════════════════════════════════════════════
# КАРТОЧКА МОНЕТЫ · рендерится в модалке (render.card)
# Каркас, шапка, чипы, сигналы, блоки 01/02/03, вето, подкова R:R.
# Перенесено из прошлой реализации без изменений логики.
# ═══════════════════════════════════════════════════
CARD = """
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));
  gap:20px;align-items:start;margin-bottom:8px}
.card{position:relative;background:var(--card);border-radius:30px;padding:16px}
.card.glow{background:linear-gradient(135deg,var(--g1),var(--g2) 50%,var(--g3));
  padding:1.2px;border-radius:30px;box-shadow:0 0 11px var(--gs1),0 0 24px var(--gs2)}
.card.glow>.card-in{background:var(--card);border-radius:28.8px;padding:15px}
.card-in{position:relative}
.g-am{--g1:#FFB800;--g2:#e07a3a;--g3:#FFD24A;--gs1:rgba(255,184,0,.42);--gs2:rgba(240,168,0,.16)}
.g-rd{--g1:#e05a5a;--g2:#c04a6a;--g3:#f08a8a;--gs1:rgba(224,90,90,.42);--gs2:rgba(208,85,85,.16)}

.hdr{position:relative;height:118px;border-radius:22px;margin:0 0 14px;
  background:linear-gradient(160deg,var(--h1),var(--h2));box-shadow:0 5px 18px var(--hs)}
.hdr.amber{--h1:#FFD24A;--h2:#F0A800;--hs:rgba(240,168,0,.3);
  --hf:#7a5c00;--hd:#1a1400;--hp:#6b5000}
.hdr.red{--h1:#f0a0a0;--h2:#d06060;--hs:rgba(208,85,85,.3);
  --hf:#5c1a1a;--hd:#2a0d0d;--hp:#6b2a2a}
.hdr::after{content:'';position:absolute;bottom:-22px;left:96px;width:44px;height:44px;
  border-radius:50%;background:var(--card)}
.hdr-cl{position:absolute;inset:0;border-radius:22px;overflow:hidden}
.hdr-gh{position:absolute;left:-4px;bottom:-16px;font-size:80px;font-weight:900;
  letter-spacing:-3px;color:var(--hd);opacity:.12;line-height:1;white-space:nowrap}
.hdr-in{position:relative;padding:22px 24px 0}
.hdr-rk{display:flex;align-items:center;gap:12px}
.hdr-rk b{font-size:8px;font-weight:800;letter-spacing:3px;color:var(--hf)}
.hdr-rk i{flex:1;max-width:80px;height:1px;background:var(--hf);opacity:.35}
.hdr-sym{margin-top:16px;font-weight:900;color:#fffdf6;
  text-shadow:0 2px 3px rgba(58,42,0,.55);white-space:nowrap;overflow:hidden}
.hdr-ph{font-family:var(--serif);font-style:italic;font-weight:500;font-size:27px;
  color:var(--hd);margin:-2px 0 0 10px;line-height:1.05}
.hdr-pr{position:absolute;right:24px;bottom:14px;font-family:var(--mono);
  font-size:9px;font-weight:800;color:var(--hp)}
.hdr-sym-a{display:block}
.hdr-sym-a:hover .hdr-sym{opacity:.82}

.med{position:absolute;top:52px;right:38px;width:50px;height:50px;border-radius:50%;
  background:conic-gradient(from -90deg,var(--am1) calc(var(--p)*3.6deg),#24242c 0);
  box-shadow:0 5px 8px rgba(0,0,0,.92),0 0 10px rgba(255,184,0,.35)}
.med.red{background:conic-gradient(from -90deg,#e39a9a calc(var(--p)*3.6deg),#24242c 0)}
.med::before{content:'';position:absolute;inset:3.4px;border-radius:50%;background:#14141a}
.med-i{position:relative;height:100%;display:flex;flex-direction:column;
  align-items:center;justify-content:center;gap:1px}
.med-v{font-size:16px;font-weight:900;color:var(--am1);line-height:1}
.med.red .med-v{color:var(--dn)}
.med-l{font-size:5.5px;font-weight:800;letter-spacing:1.2px;color:var(--mut)}
.med-link{position:absolute;top:76px;right:88px;width:30px;height:1.2px;
  background:var(--am2);opacity:.6}

.chips{display:flex;flex-wrap:wrap;gap:6px;margin:26px 0 12px}
.chip{height:18px;padding:0 11px;border-radius:9px;background:#1e1e26;color:#8a8a96;
  font-size:7px;font-weight:900;letter-spacing:1px;display:flex;align-items:center;
  text-transform:uppercase}
.chip.risk{background:#2c1c1f;color:var(--dn)}
.chip.more{background:transparent;border:1px dashed #2a2a34;color:var(--mut3)}

.wrap{display:grid;grid-template-columns:120px 1fr;gap:8px;margin-bottom:12px}
.rvol{grid-row:span 2;background:var(--panel);border-radius:22px;padding:14px 0;
  text-align:center;box-shadow:2px 4px 5px rgba(0,0,0,.8)}
.rvol-i{width:34px;height:34px;margin:0 auto;border-radius:50%;
  background:rgba(255,184,0,.14);display:flex;align-items:center;
  justify-content:center;font-size:15px}
.rvol-v{font-family:var(--mono);font-size:22px;font-weight:900;color:var(--am1);margin-top:12px}
.rvol-l{font-size:7.5px;font-weight:700;letter-spacing:1.5px;color:#9a9080;margin-top:6px}
.rvol-d{font-family:var(--serif);font-style:italic;font-size:8px;color:#6e6a60;margin-top:4px}

.sigs{display:flex;flex-direction:column;gap:8px}
.sig{display:flex;align-items:center;gap:12px;height:46px;padding:0 16px;border-radius:20px;
  background:var(--panel);box-shadow:2px 4px 5px rgba(0,0,0,.8)}
.sig.half{height:30px;border-radius:15px;background:#141419;box-shadow:none}
.sig-i{width:24px;height:24px;border-radius:50%;background:#2b2718;color:var(--am1);
  flex:none;font-size:9px;font-weight:900;display:flex;align-items:center;justify-content:center}
.sig.rd .sig-i{background:#2c1c1f;color:var(--dn)}
.sig.half .sig-i{width:18px;height:18px;background:#22201a;color:var(--am4);font-size:8px}
.sig-t{font-size:9px;font-weight:900;letter-spacing:1.2px;color:#f2f2f6}
.sig.half .sig-t{font-size:8px;color:#dcdce4}
.sig-d{font-family:var(--serif);font-style:italic;font-size:8.5px;color:#82828e;
  margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sig.half .sig-d{font-family:var(--mono);font-style:normal;font-size:7.5px;color:#5c5c66}
.sig-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}

.perf{display:grid;grid-template-columns:repeat(4,1fr);height:48px;align-items:center;
  padding:0 24px;border-radius:20px;background:#0a0a0d;border:1px solid var(--line);
  margin-bottom:8px}
.perf-k{font-size:7px;font-weight:700;letter-spacing:1.8px;color:#57575f}
.perf-v{font-family:var(--mono);font-size:12px;font-weight:800;margin-top:5px}
.tech{height:22px;line-height:20px;border-radius:11px;background:#0a0a0d;
  border:1px solid var(--line2);text-align:center;font-family:var(--mono);
  font-size:7.5px;color:var(--mut2);margin-bottom:16px;white-space:nowrap;overflow:hidden}

.lnks{display:flex;gap:8px;margin-top:12px}
.lnk{flex:1;height:32px;border-radius:16px;background:#121217;border:1px solid var(--line2);
  display:flex;align-items:center;justify-content:center;gap:7px;
  font-size:8px;font-weight:900;letter-spacing:1.5px;color:#8a8a96;
  transition:background .15s,color .15s,border-color .15s}
.lnk:hover{background:#1c1a14;border-color:rgba(255,184,0,.4);color:var(--am1)}
.lnk i{font-style:normal;font-size:9px;opacity:.7}
.lnk.pri{background:#1a1710;border-color:rgba(255,184,0,.32);color:var(--am4)}
.lnk.pri:hover{background:#241f10;color:var(--am1)}

.blk{position:relative;border-radius:20px;margin-bottom:8px;overflow:hidden}
.blk-n{position:absolute;left:16px;top:50%;transform:translateY(-50%);
  font-size:38px;font-weight:900;line-height:1;pointer-events:none}

.b1{background:#141418;min-height:52px;box-shadow:2px 4px 5px rgba(0,0,0,.8)}
.b1 .blk-n{color:#26262e}
.b1-in{padding:12px 16px 12px 82px}
.b1-h{display:flex;align-items:center;gap:8px}
.tw{width:22px;height:22px;border-radius:50%;background:#1d2a33;flex:none;
  display:flex;align-items:center;justify-content:center}
.tw svg{width:11px;height:11px;fill:#8fc4e8}
.b1-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:#c8c8d4}
.b1-lv{height:13px;padding:0 8px;border-radius:6.5px;font-size:6.5px;font-weight:900;
  letter-spacing:1.2px;display:flex;align-items:center}
.lv-hot{background:#3a2f18;color:var(--am1)}
.lv-warm{background:#3a2f18;color:var(--am4)}
.lv-cool{background:#22222a;color:#8a8a96}
.lv-cold{background:#1a1a22;color:var(--mut2)}
.b1-d{font-size:8.5px;color:#63636d;margin-top:6px;line-height:1.4}

.b2{background:var(--panel);box-shadow:2px 4px 5px rgba(0,0,0,.8)}
.b2 summary{display:flex;align-items:center;min-height:52px;padding:10px 16px;gap:12px;
  list-style:none;cursor:pointer}
.b2 summary::-webkit-details-marker{display:none}
.b2 summary .blk-n{position:static;transform:none;flex:none;width:66px;
  color:#332a12;pointer-events:none}
.b2-in{min-width:0;flex:1}
.b2-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:var(--am1)}
.b2-p{font-size:8.5px;color:#63636d;margin-top:6px;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis;max-width:250px}
.b2-c{margin-left:auto;width:22px;height:22px;border-radius:50%;background:#22222a;
  flex:none;display:flex;align-items:center;justify-content:center;transition:transform .18s}
.b2-c::before{content:'';width:7px;height:7px;border-right:1.8px solid var(--am1);
  border-bottom:1.8px solid var(--am1);transform:translateY(-2px) rotate(45deg)}
.b2[open] .b2-c{transform:rotate(180deg)}
.b2[open] .b2-p{white-space:normal;max-width:none}
.b2-body{padding:0 20px 16px 82px;font-size:9.5px;line-height:1.65;color:#9a9aa4}
.b2-body p{margin:0 0 8px}
.b2-body p:last-child{margin:0}

.b3{position:relative;min-height:112px;border-radius:20px;
  background:linear-gradient(135deg,#1c1810,#131318);
  border:1px solid #3a2f18;box-shadow:2px 4px 5px rgba(0,0,0,.8)}
.b3 .blk-n{color:#2a2317;font-size:42px}
.b3-in{padding:14px 20px 14px 88px}
.b3-hd{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.b3-t{font-size:8px;font-weight:900;letter-spacing:2.5px;color:var(--am1)}
.b3-chip{display:inline-flex;align-items:center;height:14px;padding:0 8px;
  border-radius:7px;background:#2b2718;color:var(--am4);
  font-size:6.5px;font-weight:900;letter-spacing:1px}
.b3-tv{margin-left:auto;font-size:7.5px;font-weight:900;color:var(--am4);
  text-decoration:none;letter-spacing:.5px;transition:color .15s}
.b3-tv:hover{color:var(--am1)}
.b3-grid{display:flex;align-items:center;gap:18px;margin-bottom:10px}
.b3-d{font-size:8.5px;color:#9a9080;line-height:1.5}

.veto{border-radius:16px;background:rgba(196,112,58,.06);
  border:1px solid rgba(196,112,58,.22);padding:10px 14px;margin-bottom:8px}
.veto-h{font-size:7px;font-weight:900;letter-spacing:2px;color:var(--ru);margin-bottom:8px}
.veto-row{display:flex;gap:10px;align-items:baseline;padding:2px 0}
.veto-k{font-size:7.5px;font-weight:900;letter-spacing:1.2px;color:#a07a62;
  width:96px;flex:none}
.veto-v{font-family:var(--serif);font-style:italic;font-size:8px;color:#6e6058}

.rr-dial{position:relative;width:72px;height:72px;flex:none}
.rr-dial svg{width:72px;height:72px;transform:rotate(-90deg)}
.rr-trk{fill:none;stroke:#24242c;stroke-width:9.5}
.rr-arc{fill:none;stroke-width:9.5;stroke-linecap:round;
  transition:stroke-dasharray .5s cubic-bezier(.4,0,.2,1)}
.rr-poor .rr-arc{stroke:#c46a6a}
.rr-fair .rr-arc{stroke:#F0A800}
.rr-good .rr-arc{stroke:#7fbf8f}
.rr-val{position:absolute;left:0;right:0;top:26px;text-align:center;
  font-family:var(--mono);font-size:15px;font-weight:900;line-height:1}
.rr-poor .rr-val{color:#e39a9a}
.rr-fair .rr-val{color:var(--am1)}
.rr-good .rr-val{color:#7fbf8f}
.rr-cap{position:absolute;left:0;right:0;top:44px;text-align:center;
  font-size:6px;font-weight:800;letter-spacing:2px;color:#57575f}
.rr-nums{display:flex;gap:22px;flex:1;min-width:0}
.rr-c{display:flex;flex-direction:column;gap:3px;min-width:0}
.rr-l{font-size:6.5px;font-weight:900;letter-spacing:1.5px;color:#57575f}
.rr-p{font-family:var(--mono);font-size:11px;font-weight:900;
  white-space:nowrap;line-height:1}
.rr-e{color:var(--am1)}
.rr-s{color:#e39a9a}
.rr-t{color:#7fbf8f}
.rr-d{font-family:var(--mono);font-size:7px;color:#3f3f48;line-height:1}
"""

# ═══════════════════════════════════════════════════
# РЯД СТРАТЕГИЙ · лента FLOW
# ═══════════════════════════════════════════════════
STRAT = """
/* Ряд стратегий: лента + правая колонка «кто двигает рынок».

   Колонка стоит в потоке обычной флекс-ячейкой. Раньше она
   вырывалась в absolute — из-за этого её высота не влияла на
   строку, и при семи тикерах список наезжал на воронку снизу.
   Теперь строка растёт вместе с содержимым, а лента остаётся
   по центру за счёт flex:1 и margin:0 auto внутри .fl. */
.row-s{display:flex;align-items:stretch;gap:28px;margin-bottom:52px;
  position:relative}
.strat{position:relative;flex:1 1 auto;min-width:0;padding:8px 0 0;cursor:pointer; margin-bottom: 30px}
.c-fl{--c:#D9A441;--h1:rgba(217,164,65,.30);--h2:rgba(184,134,11,.08)}
.strat .halo{width:56%;height:96px;top:2px}
.strat.empty{opacity:.45;pointer-events:none}

.fl{display:block;width:100%;max-width:620px;height:130px;margin:0 auto;
    overflow:visible}
.fl-blur{filter:blur(7px)}

.fl-lk{font-size:6px;font-weight:300;letter-spacing:3.5px;fill:#6a5c3d}
.fl-tot{font-size:23px;font-weight:100;letter-spacing:1px;fill:#FFF9EC}
.fl-n{font-size:14px;font-weight:200;letter-spacing:1px;fill:#FFF4D8}
.fl-c{font-size:7px;font-weight:300;letter-spacing:2.5px;fill:#D4B476}
.fl-glow{fill:#D9A441;opacity:.16;filter:blur(4px)}
.fl-lv{font-size:12px;font-weight:300;letter-spacing:1.5px;fill:#e8eaee}
.fl-ls{font-size:14px;font-weight:200;letter-spacing:1px;fill:#FFD98A}
.fl-note{font-size:6px;font-weight:300;letter-spacing:3px;fill:#6b5c38}

.fl-node{transition:opacity .15s}
.fl-node.big .fl-n{font-size:26px;font-weight:700;fill:#fff}
.fl-node.big .fl-c{font-size:8px;letter-spacing:3.5px;fill:#FFEBB8}
.fl-node.off{opacity:.3}
.fl:hover .fl-node{opacity:.55}
.fl:hover .fl-node:hover{opacity:1}
.fl-node:hover .fl-c{fill:#FFF4D8}

/* Правый край ленты FLOW · «кто двигает рынок».

   Порядок задаёт кратность объёма, а не источник, поэтому
   золотые и белые идут вперемешку — так и задумано.

   Кант под первой буквой — лидер выборки FLOW.
   Цвет и яркость — объём: x50 / x100 / x200.
   Признаки не спорят за одно свойство и читаются вместе. */

    .g-lead{
        display: flex;
        flex-direction: column;
        align-items: center;
        padding-top: 0;
        position: static;
        justify-content: center;
    }
/*.g-lead{position:absolute;right:0;top:-23px;
  display:flex;flex-direction:column;align-items:flex-end;
  gap:12px;padding:8px 0 12px}*/

/* Колонки вместо одной длинной ленты: список растёт влево,
   и все тикеры видны без скролла — как в планшетной раскладке.
   Строк ровно 7: восьмая монета начинает новую колонку,
   а не удлиняет блок и не давит на воронку снизу. */
.lead-list{
    max-width: none;
    margin-bottom: 18px;
    display: flex;
    flex-direction: row;
    flex-wrap: wrap;
    overflow: visible;
    gap: 10px;
   }

.lead-t{font-size:7px;font-weight:300;letter-spacing:2.5px;
  color:rgba(232,234,238,.56);transition:color .14s;
      border-radius: 100%;
    /*transition: transform .2s, box-shadow .2s, background .1s, text-shadow .2s;*/
  }
  /* .lead-t:hover {
      transform: scale(3);
      background: radial-gradient(circle, #0012fd, transparent) 131% / 1029px;
      box-shadow: 0 0 19px 8px #0012fdde;
      text-shadow: 1px 1px 1px black, 1px 1px 1px black;
      z-index: 2;
  } */

/* три ступени объёма: приглушённое золото → полное → светлое.
   Одного цвета мало: x50 и x200 одинаково жёлтыми сливаются,
   и топ теряется ровно там, где он важнее всего. */
.lead-t.lead-g1{color:#B99B5C}
.lead-t.lead-g2{color:#D4B476}
.lead-t.lead-g3{color:#FFE0A0;text-shadow:0 0 8px rgba(217,164,65,.4)}

/* лидер выборки FLOW — кант под первой буквой */
.lead-t.lead-f::first-letter{border-bottom:1px solid rgba(255,186,0,.55)}
.lead-t.lead-f.lead-g3::first-letter{border-bottom-color:rgba(255,208,120,.9)}

/* журналы пусты — панель гаснет, а не исчезает:
   пропавший блок читается как поломка вёрстки */
.lead-t.off{color:#3a3a44;letter-spacing:2px}

.lead-t[data-coin]{position:relative;cursor:pointer}
.lead-t[data-coin]:hover{color:var(--gd)}

.lead-hd{font-weight:300;font-size:6px;letter-spacing:3px;color:#6b5c38;
  white-space:nowrap;align-self:right}
.lead-hd s{text-decoration:none}
"""

# ═══════════════════════════════════════════════════
# ОТЧЁТ FLOW · карточки, вариант B
# Свет из левого нижнего угла, кант затухает вправо,
# цвет = статус строки. Только для стратегии flow.
# ═══════════════════════════════════════════════════
FLOWREP = """
.fr-list{padding-top:20px}
.fr-empty{padding:80px 0;text-align:center;font-size:9px;font-weight:300;
          letter-spacing:3px;color:var(--m4)}
.fr-tail{padding:26px 0 10px;text-align:center;font-size:7px;font-weight:300;
         letter-spacing:3px;color:#2e2e38}

.fr{position:relative;margin-bottom:32px;border-radius:30px;background:#0a0b0f;
    box-shadow:0 16px 20px rgba(0,0,0,.62);cursor:pointer;
    transition:transform .14s,box-shadow .14s}
.fr:hover{transform:translateY(-2px);box-shadow:0 20px 26px rgba(0,0,0,.7)}

.t-gd{--fc:#FFB020;--fl:#FFD25E;--fw:#FFEBB0;--fo:.65}
.t-gr{--fc:#22E08A;--fl:#6BFFB4;--fw:#BFFFDF;--fo:.60}
.t-rd{--fc:#FF6B35;--fl:#FF9B6B;--fw:#FFC4A0;--fo:.45}

/* состояние импульса: 4 сегмента, 3 тона. Заполнение растёт
   вместе с риском, поэтому шкала читается наоборот к фазе:
   больше сегментов — хуже, а не лучше. */
.fr-imp{display:flex;gap:3px}
.fr-imp i{width:9px;height:4px;border-radius:2px;background:#1e1f26}
.fr-imp.flat i.on{background:#4FCF8A}
.fr-imp.up i.on{background:#F5A623}
.fr-imp.cross i.on{background:#C4703A}
.fr-imp.none{opacity:.3}
.fr-impv{font-size:8px;font-weight:300;letter-spacing:1px;color:#7f838c}
.fr-imp-off{font-size:7px;font-weight:300;letter-spacing:1px;color:#4a4a54}

/* стекло + свет из левого нижнего угла */
.fr::before{content:'';position:absolute;inset:0;border-radius:inherit;
  background:var(--glass),
    radial-gradient(ellipse 52% 52% at 18% 105%,
      color-mix(in srgb,var(--fc) 26%,transparent),transparent 70%);
  pointer-events:none}
/* кант корпуса */
.fr::after{content:'';position:absolute;inset:0;border-radius:inherit;padding:1px;
  background:var(--rim);-webkit-mask:linear-gradient(#000 0 0) content-box,
  linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;
  pointer-events:none}

/* ссылки: строка над тикером, компактные ярлыки */
.fr-lnks{display:flex;gap:5px;margin-bottom:9px}
.fr-lnk{display:inline-flex;align-items:center;gap:3px;height:18px;
        padding:0 8px;border-radius:9px;background:#121217;
        border:1px solid #1f1f28;font-size:7.5px;font-weight:400;
        letter-spacing:1px;color:#8a8a96;text-transform:uppercase;
        transition:background .14s,color .14s,border-color .14s}
.fr-lnk:hover{background:#1c1a14;color:var(--fl);
              border-color:color-mix(in srgb,var(--fc) 45%,transparent)}
.fr-lnk i{font-style:normal;font-size:7px;opacity:.5}
.fr-lnk.pri{color:var(--fl);background:color-mix(in srgb,var(--fc) 10%,transparent);
            border-color:color-mix(in srgb,var(--fc) 38%,transparent)}
.fr-lnk.off{opacity:.3;cursor:default}

/* горизонт: занял место кнопки */
.fr-hz{display:flex;align-items:baseline;gap:5px}
.fr-hz b{font-size:17px;font-weight:200;color:var(--fl);
         font-variant-numeric:tabular-nums}
.fr-hz s{text-decoration:none;font-size:7px;font-weight:300;
         letter-spacing:1px;color:#7f838c}
.fr-hz.off{font-size:12px;color:#3a3a44}

/* тикер стал ссылкой на график */
.fr-sym{display:block;font-size:19px;font-weight:200;letter-spacing:2px;
        color:#f4f6f8;margin-top:6px;white-space:nowrap;overflow:hidden;
        text-overflow:ellipsis;transition:color .14s}
.fr-sym:hover{color:var(--fl)}

.fr-in{position:relative;z-index:1;display:grid;
       grid-template-columns:188px 68px 104px 116px 158px 100px 92px 92px 104px;
       align-items:center;gap:0 14px;min-height:136px;padding:0 26px}
/* чип паттерна: ярлык, не абзац — перенос запрещён */
.fr-chip{align-self:flex-start;max-width:100%;height:16px;line-height:14px;
         padding:0 9px;border-radius:4px;font-size:8px;font-weight:300;
         white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
         color:var(--fl);background:color-mix(in srgb,var(--fc) 10%,transparent);
         border:1px solid color-mix(in srgb,var(--fc) 30%,transparent)}

/* зоны: стрелка · дистанция · подпись */
.fr-zn{display:flex;align-items:baseline;gap:5px}
.fr-zn i{font-style:normal;font-size:8px;opacity:.6}
.fr-zn b{font-size:12px;font-weight:200;font-variant-numeric:tabular-nums}
.fr-zn s{text-decoration:none;font-size:6.5px;font-weight:300;
         letter-spacing:1px;color:#f7f7f7}
.fr-zn.up b,.fr-zn.up i{color:#FF6B35}
.fr-zn.dn b,.fr-zn.dn i{color:#22E08A}
.fr-zn.off{font-size:7px;color:#4a4a54;letter-spacing:1px}

/* шапка: два тега в строку */
.fr-caps{display:flex;gap:6px;margin-top:9px;flex-wrap:wrap}
.fr-tag{height:15px;line-height:13px;padding:0 8px;border-radius:8px;
  font-size:8.6px;font-weight:400;color:var(--fl);
  background:color-mix(in srgb,var(--fc) 13%,transparent);
  border:1px solid color-mix(in srgb,var(--fc) 40%,transparent); opacity: 0.8}
.fr-tag.gh{color:#f7f7f7;background:transparent;border-color:transparent}
/* тег роста от дна */
.fr-tag.up{background:transparent;border-color:transparent}

/* объём: три масштаба столбиком */
.fr-vol{gap:7px}
.fr-vr.off b{color:#3a3a44}
.fr-vr{position:relative;display:grid;grid-template-columns:18px 40px;
  align-items:center;gap:8px;padding-bottom:5px}
.fr-vr i{font-style:normal;font-size:7px;font-weight:300;letter-spacing:1px;
  color:#f7f7f7}
.fr-vr b{font-size:13px;font-weight:200;color:#8d929b;
  font-variant-numeric:tabular-nums}
.fr-vr s{position:absolute;left:26px;right:0;bottom:0;height:2px;
  border-radius:1px;background:color-mix(in srgb,var(--fc) 26%,transparent);
  text-decoration:none;max-width:calc(100% - 26px)}
.fr-vr.warm b{color:#c9ced6}
.fr-vr.hot b{color:var(--fw)}
.fr-vr.hot s{background:var(--fc);box-shadow:0 0 6px color-mix(in srgb,var(--fc) 55%,transparent)}

/* цена: крупный 1д + спарклайн + два периода */
.fr-price{gap:5px}
.fr-big{font-size:19px;font-weight:200;letter-spacing:.5px;
  font-variant-numeric:tabular-nums}
.fr-big.up{color:#22E08A}
.fr-big.dn{color:#FF6B35}
.fr-price svg{width:100%;height:40px;overflow:visible}
.fr-legs{display:flex;gap:16px}
.fr-legs i{font-style:normal;font-size:7px;font-weight:300;letter-spacing:1px;
  color:#f7f7f7}
.fr-legs b{font-size:9px;font-weight:200;margin-left:5px;
  font-variant-numeric:tabular-nums}
.fr-legs b.up{color:#22E08A}
.fr-legs b.dn{color:#FF6B35}

.fr-dots{display:flex;gap:4px}
.fr-dots i{width:5.2px;height:5.2px;border-radius:50%;background:var(--fc);
           opacity:.2}
.fr-dots i.on{opacity:1}

/* фандинг: биполярный бар от центра */
.fr-fund{position:relative;display:block;width:100%;max-width:104px;height:5px;
  border-radius:2.5px;background:#15161b}
.fr-fund s{position:absolute;left:50%;top:-3px;width:1px;height:11px;
  background:#3a3a44;text-decoration:none}
.fr-fund i{position:absolute;top:0;height:5px;border-radius:2.5px;min-width:3px}
.fr-fund i.pos{background:#E8843C}
.fr-fund i.neg{background:#8FB4D0}
.fr-fv{font-size:9px;font-weight:200;font-variant-numeric:tabular-nums;
  margin-top:2px}
.fr-fv.pos{color:#E8843C}
.fr-fv.neg{color:#8FB4D0}

/* верхний блик и нижний светящийся кант */
.fr-in::before{content:'';position:absolute;top:0;left:9%;right:9%;height:1px;
  background:linear-gradient(90deg,transparent,rgba(234,244,250,.45) 28%,
  rgba(234,244,250,.4) 72%,transparent)}
.fr-in::after{content:'';position:absolute;bottom:0;left:4%;width:70%;height:1.3px;
  background:linear-gradient(90deg,var(--fw),
    color-mix(in srgb,var(--fc) 55%,transparent) 35%,transparent);
  box-shadow:0 0 9px 1px color-mix(in srgb,var(--fc) 42%,transparent);
  opacity:var(--fo)}

.fr-c{display:flex;flex-direction:column;justify-content:center;gap:4px;
      min-width:0;padding:26px 0}
.fr-c1{gap:0}
.fr-idx{font-size:9px;font-weight:200;color:#2f3138}
.fr-sym{font-size:19px;font-weight:200;letter-spacing:2px;color:#f4f6f8;
        margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.fr-sec{font-size:7px;font-weight:300;letter-spacing:1.5px;
        color:color-mix(in srgb,var(--fc) 34%,#ffffff);margin-top:5px}

.fr-ring{width:62px;height:62px;overflow:visible;justify-self:center}
.fr-ring-v{font-size:20px;font-weight:100;fill:var(--fw)}
.fr-ring-l{font-size:6px;font-weight:300;letter-spacing:2px;fill:#4a4a54}

.fr-k{font-size:6px;font-weight:300;letter-spacing:2px;color:#fff}

.fr-chip{align-self:flex-start;height:16px;line-height:14px;padding:0 10px;
  border-radius:4px;font-size:8px;font-weight:300;color:var(--fl);
  background:color-mix(in srgb,var(--fc) 10%,transparent);
  border:1px solid color-mix(in srgb,var(--fc) 30%,transparent)}
.fr-steps{display:flex;gap:4px}
.fr-steps i{width:11px;height:3px;border-radius:1.5px;
  background:color-mix(in srgb,var(--fc) 22%,transparent)}
.fr-steps i.on{background:var(--fc)}

/* фон торговли: три уровня + подпись.
   Штрихи, а не точки: величина порядковая (тихо → разгон),
   а точки читаются как счётчик чего-то дискретного. */
.fr-bg{display:flex;align-items:center;gap:5px}
.fr-bg i{width:4px;height:11px;border-radius:1px;background:var(--fc);
         opacity:.2}
.fr-bg i.on{opacity:1}
.fr-bg b{font-size:8px;font-weight:300;letter-spacing:1px;color:#7f838c;
         margin-left:3px}

.fr-veto{font-size:9px;font-weight:300;letter-spacing:1px}
.fr-veto.ok{color:#22E08A}
.fr-veto.bad{color:#FF6B35}
.fr-rr{font-size:15px;font-weight:200;color:var(--fl);
       font-variant-numeric:tabular-nums}
"""
# ═══════════════════════════════════════════════════
# ОРБИТА · верхний экран дашборда
# Заменить в css.py весь блок ORBIT целиком — строки 1084..1285
#
# Всё с префиксом .ob- : в отчёте заняты .card и .chip,
# без префикса орбита сломала бы карточки монет.
# Порядок правил важен — он повторяет прототип.
# ═══════════════════════════════════════════════════
ORBIT = """
/* ── Карточка монеты ────────────────────────────────────────
   Без подложки: панель отсекала кусок сцены и превращала наведение
   в «окно поверх экрана». Читаемость держат тень текста и тонкие
   разделители, как у подписей звёзд.

   Композиция из двух частей: слева вертикальная колонка с тем, что
   отвечает на «что это за монета», справа горизонтальная полоса с тем,
   что отвечает на «что с ней сейчас». Разные вопросы — разные оси. */
/* Цвет в карточке.
   ТОН (золото при score ≥ 90, иначе зелёный) отвечает ровно на один
   вопрос — топ это или нет, и живёт только на кольце и подписи паттерна.
   Остальным величинам цвет назначен по их природе, а не по качеству
   монеты: цена — зелёный/ржавый по знаку, объём — синий, фандинг — по
   знаку, служебное — серый. Иначе карточка красится целиком в один цвет
   и перестаёт читаться.

   Шрифты тоже разведены: цифры моноширинные, подписи — тот же тонкий
   гротеск, что на всём экране. Разная гарнитура делает то же, что разный
   цвет, только не тратя палитру. */
.ob-scard{--up:#48A97C;--dn:#FF6B35;--vol:#63A6E0;--mut:#8b929c;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace}
.ob-scard{position:absolute;left:50%;top:50%;z-index:6;
  display:flex;align-items:stretch;gap:16px;
  padding:2px;pointer-events:none;
  transform:translate(-50%,-50%) scale(.97);opacity:0;
  text-shadow:0 1px 10px rgba(4,4,7,.95),0 0 3px rgba(4,4,7,.9);
  transition:opacity .2s ease,transform .28s cubic-bezier(.2,.9,.25,1.1)}
.ob-scard.on{opacity:1;transform:translate(-50%,-50%) scale(1)}
/* Затемнение под карточкой. Смещено влево и вытянуто: правая половина
   карточки и так лежит на тёмном центре, а левая колонка попадает на
   светлый край ленты, где сквозь неё просвечивают дуги и подписи звёзд.
   Радиальный градиент без резкой границы — панель отсекала бы кусок
   сцены, а здесь фон просто густеет. */
.ob-scard::before{content:'';position:absolute;left:-46%;top:50%;
  width:150%;height:280%;transform:translateY(-50%);z-index:-1;
  background:radial-gradient(ellipse 55% 50% at 38% 50%,
    rgba(4,4,7,.93),rgba(4,4,7,.72) 45%,rgba(4,4,7,0) 78%);
  pointer-events:none}
/* --- левая колонка: идентичность --- */
.ob-sc-id{flex:0 0 128px;display:flex;flex-direction:column;gap:9px}
.ob-sc-hd{display:flex;align-items:flex-start;gap:9px}
.ob-sc-t{font-size:16px;font-weight:200;letter-spacing:3px;color:var(--t1);
  display:block;line-height:1}
.ob-sc-sec{font-size:8px;letter-spacing:1.3px;color:#6a6f79;margin-top:4px;
  display:block;line-height:1.3}
.ob-sc-ring{flex:0 0 auto;width:40px;height:40px;overflow:visible}
.ob-sc-ring circle{fill:none;stroke-width:2.2}
.ob-sc-ring .trk{stroke:rgba(200,220,232,.12)}
.ob-sc-ring .val{stroke:var(--tone);stroke-linecap:round}
.ob-sc-ring text{font-size:12px;font-weight:200;fill:var(--t1)}
.ob-sc-tags{display:flex;flex-direction:column;gap:4px;align-items:flex-start}
.ob-sc-tag{font-size:8px;letter-spacing:1px;color:#8b929c}
.ob-sc-tag u{text-decoration:none;font-family:var(--mono);color:#c8ccd4}
.ob-sc-tag.up{color:var(--up)}
.ob-sc-tag.ath u{color:#c98f78}
.ob-sc-chip{font-size:8.5px;letter-spacing:1.6px;color:var(--tone);
  padding-top:7px;border-top:1px solid rgba(200,220,232,.1);align-self:stretch}
/* --- правая полоса: состояние --- */
.ob-sc-st{flex:0 0 auto;display:flex;flex-direction:column;gap:11px;
  padding-left:16px;border-left:1px solid rgba(200,220,232,.1)}
/* Объёмы в строку, а не столбиком: три горизонта — это одна величина
   в трёх масштабах, и рядом они сравниваются взглядом без чтения. */
.ob-sc-vols{display:flex;gap:14px}
.ob-sc-v{min-width:44px}
.ob-sc-v i{font-style:normal;display:block;font-size:7px;letter-spacing:2px;
  color:#5b606a}
.ob-sc-v b{display:block;font-family:var(--mono);font-weight:400;font-size:13px;
  letter-spacing:0;color:#cfe0f0;font-variant-numeric:tabular-nums;margin-top:2px}
.ob-sc-v s{text-decoration:none;display:block;height:2px;margin-top:4px;
  background:rgba(200,220,232,.1);position:relative}
.ob-sc-v s u{position:absolute;inset:0 auto 0 0;background:var(--vol);
  opacity:.9;display:block}
.ob-sc-v.off b{color:#3a3d45}
.ob-sc-v.off s u{display:none}
.ob-sc-row{display:flex;align-items:flex-end;gap:14px}
.ob-sc-p7{font-family:var(--mono);font-size:20px;font-weight:300;line-height:1;
  font-variant-numeric:tabular-nums;letter-spacing:-.5px}
.ob-sc-p7.up{color:var(--up)}
.ob-sc-p7.dn{color:var(--dn)}
.ob-sc-pd{font-size:8px;letter-spacing:1px;color:#8b929c;margin-top:5px;
  font-variant-numeric:tabular-nums;white-space:nowrap}
.ob-sc-pd b{font-family:var(--mono);font-weight:400;color:#c8ccd4}
.ob-sc-pd b.up{color:var(--up)}
.ob-sc-pd b.dn{color:var(--dn)}
.ob-sc-spark{width:104px;height:26px;display:block}
.ob-sc-foot{display:flex;align-items:center;gap:14px;font-size:8px;
  letter-spacing:1.1px;color:#5b606a;white-space:nowrap}
.ob-sc-foot b{font-family:var(--mono);font-weight:400;font-size:9.5px;
  color:#c8ccd4;font-variant-numeric:tabular-nums}
.ob-sc-fund{display:flex;align-items:center;gap:7px}
.ob-sc-fund s{text-decoration:none;width:52px;height:2px;
  background:rgba(200,220,232,.1);position:relative;display:block}
.ob-sc-fund s u{position:absolute;top:-2px;width:6px;height:6px;
  border-radius:2px;display:block}
.ob-sc-fund.pos u{background:var(--dn)}
.ob-sc-fund.pos b{color:var(--dn)}
.ob-sc-fund.neg u{background:var(--vol)}
.ob-sc-fund.neg b{color:var(--vol)}
/* Остаток 14-дневного окна — тонкая линия под всей правой полосой */
.ob-sc-life{height:1px;background:rgba(200,220,232,.1);position:relative}
.ob-sc-life u{position:absolute;inset:0 auto 0 0;background:var(--mut);
  opacity:.45;display:block}
.ob{position:relative;height:88vh;min-height:560px;max-height:900px;
  overflow:hidden;
  /* Выход из сетки .screen на всю ширину окна. Блок остаётся ВНУТРИ #dash:
     showPane() вешает .hide на #dash целиком, и вынеси мы орбиту наружу —
     её пришлось бы прятать отдельной правкой в DASH_JS.
     Отрицательный margin-top съедает верхний padding .screen, чтобы
     экран начинался от края окна, а не с отступом. */
  width:100vw;margin-left:calc(50% - 50vw);margin-top:-34px;margin-bottom:44px}
.ob > svg{position:absolute;inset:0;width:100%;height:100%}
/* Затемнение слева. Карточка монеты и подписи узлов живут в левой
   половине, а лента дуг там же самая светлая — текст ложился прямо
   на золото. Градиент гасит фон, но не трогает содержимое: он лежит
   под слоем подписей (z-index 3) и над сценой. */
.ob::before{content:'';position:absolute;inset:0;z-index:2;pointer-events:none;
  background:linear-gradient(90deg,
    rgba(4,4,7,.78) 0%,rgba(4,4,7,.55) 18%,rgba(4,4,7,.22) 36%,transparent 52%)}
/* Подписи узлов — HTML поверх SVG: у отчёта своя гарнитура и трекинг,
   текст внутри SVG жил бы по своим правилам и не совпал бы с блоками. */
.ob-lab{position:absolute;transform:translate(-50%,-50%);text-align:center;
  cursor:pointer;user-select:none;white-space:nowrap;z-index:3;
  transition:opacity .3s ease}
/* Названия категорий держим приглушёнными: они постоянны от прогона
   к прогону и в чтении не нуждаются — подсвечиваются при наведении
   и у активного узла. Верхний слой экрана отдан монетам, они меняются. */
.ob-lab-n{font-size:8px;font-weight:300;letter-spacing:3.5px;color:var(--m2);
  opacity:.6;transition:color .3s ease,opacity .3s ease}
.ob-lab-v{font-size:20px;font-weight:200;letter-spacing:2px;margin-top:2px;
  color:var(--c,var(--t3));opacity:.5;transition:opacity .3s ease}
.ob-lab:hover .ob-lab-n,.ob-lab.on .ob-lab-n{opacity:1}
.ob-lab:hover .ob-lab-n,.ob-lab.on .ob-lab-n{color:var(--c,var(--am-l))}
.ob-lab:hover .ob-lab-v,.ob-lab.on .ob-lab-v{opacity:1}
/* Невыбранные притухают, но не исчезают — орбита должна читаться целиком */
.ob.picked .ob-lab:not(.on){opacity:.42}
.ob-core{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  text-align:center;width:340px;pointer-events:none;z-index:3;
  transition:opacity .35s ease}
.ob-core-k{font-size:7px;letter-spacing:3px;color:#43434e}
.ob-core-v{font-size:26px;font-weight:200;letter-spacing:6px;color:var(--t1);
  margin-top:5px}
.ob-core-s{font-size:9px;letter-spacing:2px;color:var(--m2);margin-top:12px}
.ob-core-s b{color:var(--gd);font-weight:400}
/* Режим рынка уступает место карточке и возвращается, когда её нет */
.ob.showing .ob-core{opacity:0}
/* Наведение на звезду забирает центр себе: карточка категории и режим
   рынка гаснут, затемняющая подложка остаётся ради читаемости. */
.ob.starred .ob-core{opacity:0}
.ob.starred .ob-card{opacity:0}
.ob.starred .ob-wrap::before{opacity:1}
/* Подписи звёзд уходят под карточку и мешают её читать. Пока карточка
   открыта, гасим их все, кроме той звезды, на которую навели. */
.ob.starred .ob-star{transition:opacity .25s ease}
.ob.starred .ob-star:not(.hot){opacity:.18}
/* Цвет категории приходит инлайновой переменной --c с каждого узла,
   поэтому правила одни на все семь, а палитра живёт в данных. */
.ob-node{cursor:pointer}
.ob-node .ob-ring{fill:none;stroke-width:.9;opacity:.5;transition:opacity .3s ease}
.ob-node .ob-ic{opacity:.8;transition:opacity .3s ease}
.ob-node .ob-glow{opacity:.14;transition:opacity .4s ease}
.ob-node .ob-ping{opacity:0}
.ob-node:hover .ob-ring,.ob-node:hover .ob-ic{opacity:1}
.ob-node.on .ob-ring{opacity:1;stroke-width:1.3}
.ob-node.on .ob-ic{opacity:1}
.ob-node.on .ob-glow{opacity:.5}
/* Пинг только у выбранного: у всех семи сразу экран стал бы мигалкой */
.ob-node.on .ob-ping{animation:ob-ping 2.6s ease-out infinite}
/* Сегмент доли на орбите подсвечивается вместе со своим узлом:
   иначе выделение живёт только на точке, а дуга остаётся ровной. */
.ob-seg{transition:opacity .3s ease,stroke-width .3s ease}
.ob-seg.on{opacity:1;stroke-width:1.4}
/* Выноска от узла к центру — появляется только у активного */
.ob-link{stroke-dasharray:2 4;opacity:0;transition:opacity .35s ease}
.ob-link.on{opacity:.4}
/* Содержимое категории показывается в центре орбиты, а не у узла:
   центр — единственное место, где ничего не перекрывается дугами,
   и взгляд не бегает за кометой по кругу. */
.ob-wrap{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);
  width:300px;z-index:4;pointer-events:none}
.ob-wrap::before{content:'';position:absolute;left:50%;top:50%;
  width:540px;height:410px;transform:translate(-50%,-50%);
  background:radial-gradient(ellipse at center,rgba(6,6,9,.92),
    rgba(6,6,9,.6) 45%,rgba(6,6,9,0) 72%);
  opacity:0;transition:opacity .4s ease;pointer-events:none}
.ob.showing .ob-wrap::before{opacity:1}
/* Карточка узкая: полоса во всю ширину заставляла глаз проделывать
   путь от тикера до значения и терять строку. Ширина ленты сжата
   примерно втрое, тикер и число теперь в одном взгляде. */
.ob-card{position:absolute;left:50%;top:50%;width:150px;
  transform:translate(-50%,-50%) scale(.96);opacity:0;
  transition:opacity .4s ease,transform .5s cubic-bezier(.2,.9,.25,1.1)}
.ob-card.on{opacity:1;transform:translate(-50%,-50%) scale(1)}
.ob-card-h{text-align:center;margin-bottom:2px}
.ob-card-n{display:block;font-size:8px;letter-spacing:3.5px;color:var(--c)}
.ob-card-v{display:block;font-size:30px;font-weight:200;letter-spacing:3px;
  color:var(--t1);font-variant-numeric:tabular-nums;margin-top:4px}
.ob-card-note{font-size:10px;letter-spacing:1.6px;color:#5b606a;
  margin-bottom:14px;text-align:center}
/* Заголовок подкейса внутри карточки. Первому не нужен верхний отступ —
   он идёт сразу за подписью категории. */
.ob-card-g{font-size:9px;letter-spacing:2.5px;color:#5b606a;
  margin:13px 0 2px;text-transform:uppercase}
.ob-card-g:first-of-type{margin-top:0}
/* Колонки подогнаны под содержимое: пустота между тикером и полосой
   заставляла глаз делать лишний скачок. Полоса теперь короткая —
   она показывает соотношение, а точное значение стоит рядом цифрой. */
.ob-card-r{display:grid;grid-template-columns:46px 34px 42px;align-items:center;
  gap:7px;margin-top:8px}
.ob-card-k{font-size:11px;color:var(--t3);overflow:hidden;text-overflow:ellipsis}
.ob-card-k s{display:block;font-size:7px;letter-spacing:1.5px;color:#5b606a;
  text-decoration:none;margin-top:1px}
.ob-card-bar{height:2px;background:var(--trk);position:relative}
.ob-card-bar i{position:absolute;inset:0 auto 0 0;background:var(--c);opacity:.85}
.ob-card-x{font-size:11px;text-align:right;color:#8b929c;
  font-variant-numeric:tabular-nums}
.ob-card-spark{display:block;width:100%;height:26px;margin-top:10px;opacity:.75}
.ob-chips{display:flex;flex-wrap:wrap;gap:5px 9px;margin-top:2px;
  justify-content:center;pointer-events:auto}
/* Три ступени яркости вместо трёх цветов: цвет уже занят категорией,
   а кратность объёма читается светимостью — как в ленте .lead-list. */
.ob-chip{font-size:9px;letter-spacing:1.5px}
.ob-chip[data-coin]{cursor:pointer}
.ob-chip.t0{color:#5f6572}
.ob-chip.t1{color:#8a7c58}
.ob-chip.t2{color:#D4B476}
.ob-chip.t3{color:#FFE0A0;text-shadow:0 0 8px rgba(217,164,65,.4)}
/* ── Звёзды: лидер FLOW и монеты из журнала ──────────────────
   Стоят вне орбиты, чтобы не путаться с узлами категорий.
   Свежесть попадания в журнал несёт размер и яркость, кратность
   объёма — цвет и второй луч. Признаки не спорят за одно свойство. */
.ob-star{cursor:pointer}
.ob-star .ob-ray{transition:opacity .3s ease}
.ob-star:hover .ob-ray{opacity:1}
.ob-star-lbl{font-size:5.7px;letter-spacing:1.2px;
  paint-order:stroke;stroke:rgba(6,6,9,.92);stroke-width:2;
  transition:opacity .25s ease}
.ob-star-lbl.lead{font-size:6.6px;letter-spacing:1.6px}
/* Рост от дна — вторая строка подписи. Цвет наследуется от звезды
   (задаётся при отрисовке), а не берётся зелёным: зелёный на тёмном
   фоне среди золота бьёт по глазам и читается как отдельный статус,
   хотя это просто величина. */
.ob-star-up{font-size:5px;letter-spacing:.6px;font-weight:400;
  paint-order:stroke;stroke:rgba(6,6,9,.92);stroke-width:2.5;
  transition:opacity .25s ease}
.ob-star:hover .ob-star-lbl,.ob-star:hover .ob-star-up{opacity:1}
/* Кольцо только у ×50 и выше: доп. признак, а не украшение у всех */
.ob-star-ring{fill:none;stroke:var(--am-l);stroke-width:.4;opacity:.35;
  animation:ob-halo 4.5s ease-in-out infinite}
@keyframes ob-halo{
  0%,100%{transform:scale(1);opacity:.35}
  50%{transform:scale(1.5);opacity:.08}
}
.ob-star.fresh > *:not(text){
  animation:ob-shine 1.5s ease-in-out infinite;animation-delay:inherit}
/* У выбранного мерцание гасим: оно спорит с радарным пингом */
.ob-star.fresh:hover > *{animation:none}
@keyframes ob-drift{to{transform:rotate(360deg)}}
@keyframes ob-driftBack{to{transform:rotate(-360deg)}}
@keyframes ob-run{to{stroke-dashoffset:-1000}}
@keyframes ob-twinkle{0%,100%{opacity:.15}50%{opacity:.7}}
@keyframes ob-pulse{0%,100%{opacity:.30}50%{opacity:.55}}
@keyframes ob-ping{
  0%{transform:scale(1);opacity:.55}
  70%,100%{transform:scale(2.6);opacity:0}
}
/* Дрейф семейства: оборот за 4 минуты. Крутится группа без фильтров —
   размытая подсветка лежит внутри и на кадр не пересчитывается. */
.ob-spin{transform-origin:500px 320px;animation:ob-drift 240s linear infinite}
/* Встречный слой медленнее и в другую сторону: два одинаковых направления
   читались бы как одно, разница скоростей даёт параллакс. */
.ob-spin-back{transform-origin:500px 320px;
  animation:ob-driftBack 380s linear infinite}
.ob-breathe{animation:ob-pulse 9s ease-in-out infinite}
/* Попутные частицы: те же дуги орбиты коротким штрихом, разные скорости
   и фазы дают ощущение потока, а не одной кометы. */
.ob-mote{animation:ob-run linear infinite}
@media (prefers-reduced-motion:reduce){
  .ob-spin,.ob-spin-back,.ob-breathe,.ob-dust circle,
  .ob-node .ob-ping,.ob-mote,.ob-star-ring,.ob-star,
  .ob-star.fresh > *{animation:none}
}
"""

# ═══════════════════════════════════════════════════
# КАМЕННЫЙ КУБ · декор справа от ряда стратегий
# Вставить в css.py ПЕРЕД блоком RESPONSIVE
# ═══════════════════════════════════════════════════
CUBE = """
/* Куб стоит третьим элементом в .row-s, справа от FLOW.
   flex:0 0 — ширина фиксирована, чтобы он не отбирал место
   у ленты FLOW, которая тянется по flex:1. */
.g-cube{flex:0 0 300px;display:flex;align-items:center;justify-content:center;
  pointer-events:none;
  /* Палитра куба. Сменить эти четыре значения — сменить породу целиком.
     По умолчанию янтарь, в тон ряду FLOW рядом.
     Синий вариант: #1a2030 / #2e3850 / #A8C4FF / #4A72E0 / #78A0FF */
  --cb-dark:#22201a; --cb-rock:#3a352a; --cb-lit:#F5D089;
  --cb-glow:#D9A441; --cb-spec:#FFCF80}

/* Анимируем сам элемент svg, а не группу внутри: результат фильтров
   растеризуется один раз и дальше вращается композитором. Поворот
   внутренней группы заставлял бы пересчитывать feTurbulence
   и feDisplacementMap на каждом кадре. */
.cb{display:block;width:100%;height:auto;overflow:visible;
  will-change:transform;transform-origin:50% 55%;
  animation:cb-sway 7s ease-in-out infinite}

/* Покачивание ±4°: предмет читается живым, но это не выглядит вращением.
   Не нужна анимация — убери строку animation выше, картинка останется. */
@keyframes cb-sway{
  0%,100%{transform:rotate(-4deg)}
  50%    {transform:rotate(4deg)}
}

@media (prefers-reduced-motion:reduce){.cb{animation:none}}

@media (max-width:1240px){
  .g-cube{flex:0 0 220px}
}
@media (max-width:760px){
  /* На узком экране ряд и так переносится — декор только мешает */
  .g-cube{display:none}
}
"""

# ═══════════════════════════════════════════════════
# АДАПТИВ · ВСЕГДА В КОНЦЕ
# ═══════════════════════════════════════════════════
RESPONSIVE = """
@media (max-width:1240px){
  .row-1{grid-template-columns:1fr 1fr;gap:34px 40px}
  .row-2{grid-template-columns:1fr 1fr;gap:34px 40px}
  .row-2 .g-set{grid-column:1 / -1}
  .fn-line{left:60px;right:80px}
  .fn-node{width:64px}
  .risk-cap{right:auto;left:0}
  .fr-in{grid-template-columns:150px 64px 96px 92px 1fr 92px 86px 84px 96px;
         gap:0 12px;padding:0 20px}
  .fl{max-width:560px}
  .row-s{flex-wrap:wrap}
    .g-lead{flex:1 1 100%;align-items:center;padding-top:0; position:static}
  .lead-list{display:flex;flex-direction:row;flex-wrap:wrap;
    max-width:none;overflow:visible}
  .lead-t.lead-x{opacity:1;transform: translateX(0);pointer-events:auto}
  .lead-hd{align-self:center}
}

@media (max-width:760px){
  .screen{padding:24px 16px 48px}
  .hd{flex-wrap:wrap;gap:16px}
  .cap{margin-left:0;width:100%;justify-content:space-between;gap:12px;padding:0 14px}
  .row-1,.row-2{grid-template-columns:1fr;gap:44px}
  .row-2 .g-set{grid-column:auto}
  .vol-call,.vol-hook,.risk-arc{display:none}
  .fn-nodes{flex-wrap:wrap;justify-content:center;gap:24px}
  .fn-gap{display:none}
  .fn-line{display:none}
  .fn-in{padding:44px 20px 32px}
  .fn-foot{flex-direction:column;gap:8px}
  .set-row{grid-template-columns:1fr 26px 56px;gap:10px;padding:12px 8px}
  .set-in{display:none}
  .pane-hd{flex-wrap:wrap;gap:10px}
  .pane-n{margin-left:0;width:100%}
  /* на узком экране закрепляем только тикер */
  .sx .sx-c-soc,.sx .sx-c-surge{position:static;box-shadow:none}
  .sx .sx-c-sym{box-shadow:10px 0 14px -8px rgba(0,0,0,.85)}
  .sx td,.sx th{padding-left:10px;padding-right:10px}


  .fr-in{grid-template-columns:150px 66px;gap:0 12px;padding:0 22px}
  .fr-price svg{height:34px}
    .fr-c1{grid-column:1}
    .fr-ring{grid-column:2;grid-row:1}
    .fr-c{grid-column:1 / -1;flex-direction:row;align-items:center;
          gap:12px;padding:0;flex-wrap:wrap}
    .fr-btn{grid-column:1 / -1;justify-self:stretch;text-align:center}
    .fl{height:150px}
    .fl-c{font-size:6px;letter-spacing:1.5px}
}

@media (max-width:520px){
  .big{font-size:46px}
  .risk-v{font-size:42px}
  .risk-legs{gap:14px}
  .g-risk{min-height:0}
  .sx .sx-idx{display:none}
  .sx .sx-c-sym{left:0}
  .b3-in{padding-left:20px}
  .b3 .blk-n{display:none}
  .b3-grid{flex-direction:column;align-items:flex-start;gap:12px}
  .rr-nums{gap:16px;width:100%}
  .grid{grid-template-columns:1fr}
}
"""

CSS = "".join([
    TOKENS, BASE, HEAD, BLOCK, VOL, SOC, BARS, SET, IMP, RISK,
    STRAT, FUNNEL, PANES, FLOWREP, SCAN, CARD, CUBE, ORBIT, RESPONSIVE,
])
