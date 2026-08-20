"""
styles.py — вся вёрстка отчёта.
Правится независимо от логики скринера.
"""

# ═══════════════════════════════════════════════════
# ПЕРЕМЕННЫЕ ТЕМЫ
# ═══════════════════════════════════════════════════
TOKENS = """
:root{
  --bg:#0a0a0c; --card:#0e0e12; --panel:#16161c; --panel2:#121217; --panel3:#0f0f14;
  --line:#22222a; --line2:#1a1a22;
  --am1:#FFD24A; --am2:#F0A800; --am3:#e0b850; --am4:#c9a24a; --am5:#a8863a; --am6:#8a6a2a;
  --txt:#e8e8f0; --txt2:#c8c8d4;
  --mut:#6b6b76; --mut2:#4e4e58; --mut3:#3f3f48; --ghost:#2e2e36;
  --up:#7fbf8f; --dn:#e39a9a;
  --mono:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',monospace;
  --serif:Georgia,'Times New Roman',serif;
}
"""

# ═══════════════════════════════════════════════════
# БАЗА
# ═══════════════════════════════════════════════════
BASE = """
*{box-sizing:border-box}
body{background:var(--bg);color:var(--txt);margin:0;padding:26px 30px 60px;
  font-family:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
  font-size:13px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit}
summary{cursor:pointer;list-style:none}
summary::-webkit-details-marker{display:none}
.up{color:var(--up)}
.dn{color:var(--dn)}
.empty-note{font-family:var(--serif);font-style:italic;font-size:10px;
  color:#3a3a44;padding:6px 22px}
"""

# ═══════════════════════════════════════════════════
# ШАПКА · ПАНЕЛЬ ПРИБОРОВ · ЛЕГЕНДА
# ═══════════════════════════════════════════════════
HEADER = """
.hd{display:flex;align-items:flex-start;gap:14px;margin-bottom:14px}
.hd-bar{width:6px;height:26px;border-radius:3px;
  background:linear-gradient(160deg,var(--am1),var(--am2));flex:none;margin-top:2px}
.hd-t{font-size:19px;font-weight:900;letter-spacing:2px;color:#fdfdff;margin:0}
.hd-t span{color:var(--am1)}
.hd-sub{display:flex;align-items:center;gap:10px;margin-top:5px}
.hd-ts{font-family:var(--mono);font-size:9px;color:#5c5c66}
.hd-stage{background:#22222a;border-radius:8px;padding:2px 9px;font-size:7px;
  font-weight:900;letter-spacing:1.5px;color:#8a8a96}
.hd-r{margin-left:auto;text-align:right}
.hd-n{font-family:var(--mono);font-size:20px;font-weight:900;color:var(--am1);line-height:1}
.hd-nl{font-size:8px;letter-spacing:2px;color:var(--mut2);margin-top:4px}
.hd-rule{height:1.5px;border:0;margin:0 0 12px;
  background:linear-gradient(90deg,rgba(255,184,0,.4),rgba(255,184,0,0))}

.dash{display:grid;grid-template-columns:repeat(7,1fr);background:var(--panel2);
  border-radius:22px;padding:22px 0 20px}
.dcell{padding:0 0 0 36px;position:relative}
.dcell+.dcell::before{content:'';position:absolute;left:0;top:0;bottom:0;
  width:1px;background:#1e1e26}
.dcell-l{font-size:8px;font-weight:900;letter-spacing:2px;color:var(--dc,var(--am1))}
.dcell-v{font-family:var(--mono);font-size:24px;font-weight:900;
  color:var(--dc,var(--am1));margin:12px 0 4px;line-height:1}
.dcell-d{font-family:var(--serif);font-style:italic;font-size:8px;color:var(--mut2)}
.dc-1{--dc:var(--am1)} .dc-2{--dc:var(--am3)} .dc-3{--dc:var(--am4)}
.dc-4{--dc:var(--am5)} .dc-5{--dc:var(--mut)}
.dcell.empty{--dc:#3a3a44}
.dcell.empty .dcell-d{color:#2a2a32}

.lg{margin:12px 0 4px;background:#0d0d11;border:1px solid var(--line2);border-radius:17px}
.lg summary{display:flex;align-items:center;gap:20px;height:34px;padding:0 14px}
.lg-q{width:18px;height:18px;border-radius:50%;background:#22201a;color:var(--am4);
  font-size:9px;font-weight:900;display:flex;align-items:center;justify-content:center;flex:none}
.lg-t{font-size:9px;font-weight:900;letter-spacing:2px;color:#8a8a96}
.lg-d{font-family:var(--serif);font-style:italic;font-size:9px;color:#45454e}
.lg-c{margin-left:auto;width:22px;height:22px;border-radius:50%;background:#1a1a22;
  display:flex;align-items:center;justify-content:center;transition:transform .18s}
.lg-c::before{content:'';width:7px;height:7px;border-right:1.8px solid var(--am4);
  border-bottom:1.8px solid var(--am4);transform:translateY(-2px) rotate(45deg)}
.lg[open] .lg-c{transform:rotate(180deg)}
.lg[open] .lg-t{color:var(--txt2)}
.lg-body{display:grid;grid-template-columns:1fr 1px 1fr;gap:0 34px;padding:4px 26px 20px}
.lg-sep{background:var(--line2)}
.lg-h{font-size:7px;font-weight:900;letter-spacing:2px;color:#3a3a44;margin:6px 0 12px}
.lg-row{display:flex;gap:12px;padding:4px 0;font-size:8.5px;align-items:baseline}
.lg-k{font-weight:900;letter-spacing:1.5px;width:76px;flex:none;color:var(--am4)}
.lg-v{font-family:var(--serif);font-style:italic;color:var(--mut)}
.lg-n{font-family:var(--mono);color:var(--am4);width:56px;flex:none}
"""

# ═══════════════════════════════════════════════════
# ЗАГОЛОВКИ СЕКЦИЙ
# ═══════════════════════════════════════════════════
SECTIONS = """
.sec{display:flex;align-items:center;gap:14px;margin:34px 0 12px}
.sec-p{display:flex;align-items:center;gap:14px;border-radius:19px;padding:0 18px;height:38px}
.sec-n{font-size:14px;font-weight:900;letter-spacing:2px}
.sec-c{min-width:22px;height:22px;border-radius:11px;display:flex;align-items:center;
  justify-content:center;font-family:var(--mono);font-size:9px;font-weight:900;padding:0 6px}
.sec-d{font-family:var(--serif);font-style:italic;font-size:10px;color:#7a6a44}
.sec-l{flex:1;height:1.2px;background:linear-gradient(90deg,rgba(255,184,0,.4),rgba(255,184,0,0))}

.t1 .sec-p{background:linear-gradient(160deg,var(--am1),var(--am2));
  box-shadow:0 4px 14px rgba(240,168,0,.32)}
.t1 .sec-n{color:#1a1400}
.t1 .sec-c{background:rgba(26,20,0,.2);color:#1a1400}
.t2 .sec-p{background:#241f10;border:1px solid rgba(255,184,0,.5)}
.t2 .sec-n{color:var(--am1)}
.t2 .sec-c{background:#3a2f18;color:var(--am1)}
.t3 .sec-p{background:#1a1710;border:1px solid rgba(138,106,42,.45)}
.t3 .sec-n{color:var(--am4);font-size:13px}
.t3 .sec-c{background:#2a2417;color:var(--am4)}
.t3 .sec-d{color:#6b6050}
.t3 .sec-l{background:linear-gradient(90deg,rgba(138,106,42,.4),rgba(138,106,42,0))}
.t4 .sec-p{background:#131317;border:1px solid #2a2a34}
.t4 .sec-n{color:#7a7a86;font-size:13px}
.t4 .sec-c{background:#1e1e26;color:#7a7a86}
.t4 .sec-d{color:var(--mut3)}
.t4 .sec-l{background:linear-gradient(90deg,rgba(74,74,84,.45),rgba(74,74,84,0))}
"""

# ═══════════════════════════════════════════════════
# ТАБЛИЦЫ-СЛАЙДЕРЫ
# ═══════════════════════════════════════════════════
TABLES = """
.tbl{margin-bottom:8px}
.tbl-h{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;
  padding:0 22px 8px;font-size:7px;font-weight:900;letter-spacing:2px;color:#3a3a44}
.tbl-h b:nth-child(4),.tbl-h b:nth-child(5){text-align:right;font-weight:900}
.trow{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;
  align-items:center;height:36px;padding:0 22px;border-radius:14px;background:var(--panel2)}
.trow:nth-child(even){background:var(--panel3)}
.trow:hover{background:#191920}
.t-sym{font-size:11px;font-weight:800;color:#dcdce4;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.t-note{font-family:var(--serif);font-style:italic;font-size:8px;color:var(--mut3);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.t-track{position:relative;height:5px;border-radius:2.5px;background:#1c1c24}
.t-fill{height:5px;border-radius:2.5px;background:linear-gradient(90deg,var(--am2),var(--am1))}
.t-dot{position:absolute;top:50%;width:14px;height:14px;margin:-7px 0 0 -7px;
  border-radius:50%;background:var(--am1);box-shadow:0 0 0 2.5px rgba(255,184,0,.32)}
.t-val{font-family:var(--mono);font-size:12px;font-weight:900;color:var(--am1);text-align:right}
.t-ch{font-family:var(--mono);font-size:10px;text-align:right}
.t-scale{display:grid;grid-template-columns:150px 1fr 308px 84px 66px;gap:12px;padding:8px 22px 0}
.t-scale div:nth-child(3){display:flex;justify-content:space-between;
  font-family:var(--mono);font-size:7px;color:var(--ghost)}
"""

# ═══════════════════════════════════════════════════
# КАРТОЧКА · КАРКАС И ШАПКА
# ═══════════════════════════════════════════════════
CARD_SHELL = """
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
"""

# ═══════════════════════════════════════════════════
# КАРТОЧКА · ЧИПЫ, СИГНАЛЫ, МЕТРИКИ
# ═══════════════════════════════════════════════════
CARD_BODY = """
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
"""

# ═══════════════════════════════════════════════════
# БЛОКИ 01 / 02 / 03
# ═══════════════════════════════════════════════════
BLOCKS = """
.blk{position:relative;border-radius:20px;margin-bottom:8px;overflow:hidden}
.blk-n{position:absolute;left:16px;top:50%;transform:translateY(-50%);
  font-size:38px;font-weight:900;line-height:1;pointer-events:none}

/* ── 01 · Twitter ── */
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

/* ── 02 · Анализ ── */
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

/* ── 03 · Стратегия ── */
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
"""

# ═══════════════════════════════════════════════════
# ПОДКОВА R:R
# ═══════════════════════════════════════════════════
RR_DIAL = """
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
# АДАПТИВ · ВСЕГДА В КОНЦЕ
# ═══════════════════════════════════════════════════
RESPONSIVE = """
@media (max-width:1180px){
  .dash{grid-template-columns:repeat(4,1fr);row-gap:20px}
  .dcell:nth-child(5)::before{display:none}
  .tbl-h,.trow,.t-scale{grid-template-columns:130px 1fr 200px 70px 60px}
}
@media (max-width:820px){
  body{padding:18px 14px 40px}
  .dash{grid-template-columns:repeat(2,1fr)}
  .grid{grid-template-columns:1fr}
  .tbl-h b:nth-child(2),.trow>div:nth-child(2){display:none}
  .tbl-h,.trow,.t-scale{grid-template-columns:120px 1fr 66px 56px}
  .lg-body{grid-template-columns:1fr}
  .lg-sep{display:none}
}
@media (max-width:520px){
  .b3-in{padding-left:20px}
  .b3 .blk-n{display:none}
  .b3-grid{flex-direction:column;align-items:flex-start;gap:12px}
  .rr-nums{gap:16px;width:100%}
}
"""

# ═══════════════════════════════════════════════════
# СБОРКА
# ═══════════════════════════════════════════════════
CSS = "".join([
    TOKENS,
    BASE,
    HEADER,
    SECTIONS,
    TABLES,
    CARD_SHELL,
    CARD_BODY,
    BLOCKS,
    RR_DIAL,
    RESPONSIVE,   # адаптив последним — перекрывает базовые правила
])
