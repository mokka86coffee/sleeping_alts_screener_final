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
.sx th{position:sticky;top:0;z-index:3;background:#171922;
  font-size:6.5px;font-weight:300;letter-spacing:2px;color:#5a616c;
  text-align:left;padding:14px 14px 10px;white-space:nowrap;
  border-bottom:1px solid rgba(200,220,232,.12)}

.sx td{padding:10px 14px;vertical-align:middle;white-space:nowrap;
  border-bottom:1px solid rgba(200,220,232,.06)}

/* закреплённые колонки должны совпадать с новым фоном */
.sx .sx-idx{position:sticky;left:0;z-index:2;width:34px;background:#15161c}
.sx .sx-c-sym{position:sticky;left:34px;z-index:2;width:104px;background:#15161c}
.sx .sx-c-soc{position:sticky;left:138px;z-index:2;width:74px;background:#15161c}
.sx .sx-c-surge{position:sticky;left:212px;z-index:2;width:84px;background:#15161c;
  box-shadow:10px 0 14px -8px rgba(0,0,0,.85)}
.sx th.sx-idx,.sx th.sx-c-sym,
.sx th.sx-c-soc,.sx th.sx-c-surge{background:#171922;z-index:4}
.sxr:hover .sx-idx,.sxr:hover .sx-c-sym,
.sxr:hover .sx-c-soc,.sxr:hover .sx-c-surge{background:#1b1e27}

.sxr:hover{background:rgba(255,255,255,.03)}
.sxr.vetoed{opacity:.78}
.sxr.faded{opacity:.5}

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
  color:#4e535c;margin-top:3px}
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
  border-radius:8px;font-size:7.5px;font-weight:300;letter-spacing:.8px;
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
}

@media (max-width:520px){
  .big{font-size:46px}
  .risk-v{font-size:42px}
  .risk-legs{gap:14px}
  .g-risk{min-height:0}
  .sx .sx-idx{display:none}
  .sx .sx-c-sym{left:0}
}
"""

CSS = "".join([
    TOKENS, BASE, HEAD, BLOCK, VOL, SOC, BARS, SET, IMP,
    RISK, FUNNEL, PANES, SCAN, RESPONSIVE,
])
