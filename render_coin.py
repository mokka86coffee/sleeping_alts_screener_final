"""Единый экран монеты · coin.html (03.09 ночь, концепт «восход»).

Четыре экрана одной монеты — журнал прогнозов, три горизонта, зал-пейзаж
с кольцами, перемол — сведены в один. Прототип принят владельцем целиком
(proto_one_rise_fonts.html); здесь он переведён в живой документ: сцена
строится в браузере из JSON по ВСЕМ монетам журнала, монета выбирается
списком по алфавиту или хвостом адреса (coin.html#SOMI).

Что на экране (порядок чтения монеты — правило владельца 03.09):
  холст   стеклянная плита в перспективе на полу: линия цены по дневкам
          звезды, сетка внутри, уровни (плита · стоп · опора), полосы
          кластеров ликвидаций с суммой, «сейчас», отражение, лужи света
  решение внутри плиты под кривой: вердикт, основание, когда снимется,
          что торопит, строки ЗА и ПРОТИВ
  пометки пять групп вокруг плиты: ГДЕ ЦЕНА · ПОТОК · ПЛЕЧО · ПАМЯТЬ ·
          КАЛЕНДАРЬ-ФУНДАМЕНТ — цифра, единица, чтение одной строкой;
          наведение раскрывает карточку по центру экрана: строки
          «ярлык — значение», цифры золотом, слоты без данных подвалом
  часы    сосуд «до роста» из схемы, справа внизу; сияние над графиком
          по состоянию: зелёное при росте, красное при сливе, за час —
          вполсилы и дышит
  монеты  кнопка со списком журнала по алфавиту

Данные вшиваются в документ, как у схемы: звёзды одного расчёта
(render_page.build_stars), market, output/schedule.json (часы),
output/whales.json (киты по монетам), output/forecasts.jsonl (журнал
прогнозов: записей, смен, начало записи, последняя смена).
Чего в сводке нет — на экране так и написано «нет в сводке»; чисел из
воздуха модуль не выдумывает.

Правило владельца по стилю: никаких чужих файлов стилей — всё в
документе; никаких чёрных подложек — стекло в гамме; шрифты Jost для
цифр, IBM Plex Mono для ярлыков (набор А прототипа).
"""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path


def _read_json(name: str):
    for p in (Path("output") / name,
              Path(__file__).resolve().parent / "output" / name):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                return None
    return None


def _journal() -> dict:
    """output/forecasts.jsonl → {тикер: {n, switches, first, firstAt,
    lastSwitch:{tpl, at, px, chg}}}. Тот же ряд, что у render_journal —
    второго источника меток не заводим."""
    out: dict = {}
    for p in (Path("output") / "forecasts.jsonl",
              Path(__file__).resolve().parent / "output" / "forecasts.jsonl"):
        if not p.exists():
            continue
        by: dict = OrderedDict()
        for ln in p.read_text(encoding="utf-8").splitlines():
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
            by.setdefault(str(r.get("sym", "")).upper().replace("USDT", ""), []).append(
                {"t": t, "px": float(px), "tpl": str(r.get("tpl") or "")})
        for sym, pts in by.items():
            pts.sort(key=lambda x: x["t"])
            sw, prev, last = 0, None, None
            for i, q in enumerate(pts):
                if prev is not None and q["tpl"] != prev:
                    sw += 1
                    last = {"tpl": q["tpl"].split("(")[0].strip()[:40],
                            "at": q["t"].strftime("%d.%m %H:%M"), "px": q["px"],
                            "chg": round((q["px"] / pts[i - 1]["px"] - 1) * 100, 1)}
                prev = q["tpl"]
            out[sym] = {"n": len(pts), "switches": sw, "first": pts[0]["px"],
                        "firstAt": pts[0]["t"].strftime("%d.%m %H:%M"),
                        "lastSwitch": last}
        break
    return out


def _root_json(name: str):
    for p in (Path(name), Path(__file__).resolve().parent / name):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                return None
    return None


def _history(stars: list[dict]) -> dict:
    """Дневки за полгода из архива CryptoQuant cq_v2/<монета>.json — того
    же, что кормит три горизонта (make_flow). Только закрытия и края дат:
    полный архив на восемьдесят монет весил бы мегабайты. Нет файла —
    холст рисуется по series звезды (две недели)."""
    out: dict = {}
    for st in stars:
        t = str(st.get("t") or "").lower()
        if not t:
            continue
        for p in (Path("cq_v2") / f"{t}.json",
                  Path(__file__).resolve().parent / "cq_v2" / f"{t}.json"):
            if not p.exists():
                continue
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                rows = sorted((r for r in d.get("ohlcv") or [] if r.get("close")),
                              key=lambda r: r["datetime"])[-180:]
                if len(rows) >= 14:
                    out[t.upper()] = {"c": [round(float(r["close"]), 8) for r in rows],
                                      "d0": rows[0]["datetime"][:10],
                                      "d1": rows[-1]["datetime"][:10]}
            except (ValueError, KeyError, TypeError):
                pass
            break
    return out


def _book() -> dict:
    """leaders.json → позиции и вход журнала: вход, ход от входа, максимум,
    с какого дня, своя ли (added_manually). Результат позиции мерится ОТ
    ВХОДА — правило владельца."""
    L = _root_json("leaders.json") or {}
    out: dict = {}
    for sym, r in L.items():
        if not isinstance(r, dict):
            continue
        t = str(sym).upper().replace("USDT", "")
        out[t] = {"entry": r.get("entry_price"), "chg": r.get("change_pct"),
                  "maxChg": r.get("max_change_pct"), "minChg": r.get("min_change_pct"),
                  "since": str(r.get("first_seen") or "")[:10],
                  "manual": bool(r.get("added_manually")),
                  "closed": bool(r.get("closed")), "closedPx": r.get("closed_price"),
                  "upX": r.get("now_up_x") or r.get("up_x"), "maxUpX": r.get("max_up_x"),
                  "trendDone": bool(r.get("trend_done")), "hits": r.get("hits")}
    return out


def render_coin(stars: list[dict], market: dict) -> str:
    """Тело документа единого экрана монеты. Данные вшиты в JSON."""
    sched = _read_json("schedule.json")
    whales = _read_json("whales.json") or {}
    crowd = (_read_json("coinglass_crowd.json") or {}).get("coins") or {}
    flow = {}
    for r in (_read_json("flow_watch.json") or {}).get("coins") or []:
        flow[str(r.get("sym") or "").upper().replace("USDT", "")] = {
            "case": r.get("case"), "low": r.get("low"), "high": r.get("high")}
    blob = json.dumps({"stars": stars, "market": market,
                       "whales": whales.get("by_coin") or {},
                       "sched": sched, "journal": _journal(),
                       "hist": _history(stars), "book": _book(),
                       "crowd": crowd, "flow": flow},
                      ensure_ascii=False, separators=(",", ":"))
    safe = blob.replace("</", "<\\/")
    return (COIN_HTML
            + f'<script id="coinData" type="application/json">{safe}</script>'
            + COIN_JS)


# ═════════════════════════════════════════════════════════════════════
# РАЗМЕТКА И СТИЛИ. Живут в <template>, переносятся в теневое дерево:
# стили документа (render_css) внутрь не проходят и не затираются.
# ═════════════════════════════════════════════════════════════════════
COIN_HTML = r"""
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500&family=IBM+Plex+Mono:wght@400;500&family=Inter:wght@300;400&display=swap" rel="stylesheet">
<div id="coinHost"></div>
<template id="coinTpl">
<style>
:host{all:initial}
*{box-sizing:border-box}
.wrap{position:fixed;inset:0;overflow:hidden;background:#020907;color:#e8fff4;font-family:Inter,system-ui,sans-serif;font-weight:300}
.stage{position:absolute;left:50%;top:50%;width:1440px;height:900px;transform-origin:50% 50%;
  --f-name:Jost,sans-serif;--f-num:Jost,sans-serif;--f-cap:Jost,sans-serif;--f-text:Inter,sans-serif;
  background:radial-gradient(900px 640px at 86% -4%, #1f7a5c 0%, #0f3f31 30%, #062219 55%, #020907 85%),#020907}
.beam{position:absolute;left:900px;top:-80px;width:520px;height:900px;background:linear-gradient(rgba(160,255,214,.22),rgba(160,255,214,0));filter:blur(40px);transform:skewX(-14deg);pointer-events:none;animation:beam 9s ease-in-out infinite}
@keyframes beam{0%,100%{opacity:.85;transform:skewX(-14deg)}50%{opacity:1;transform:skewX(-11deg)}}
.floor{position:absolute;left:0;right:0;top:475px;bottom:0;pointer-events:none;
  background:linear-gradient(180deg, rgba(150,225,195,.16) 0, rgba(110,190,160,.13) 5%, rgba(60,140,110,.11) 14%, rgba(20,70,55,.10) 38%, rgba(2,9,7,0) 75%)}
.floor:before{content:"";position:absolute;left:0;right:0;top:-1px;height:2px;background:linear-gradient(90deg,transparent,rgba(190,245,220,.16) 25%,rgba(190,245,220,.16) 75%,transparent);filter:blur(2px)}
.floor:after{content:"";position:absolute;left:0;right:0;top:0;height:90px;background:linear-gradient(180deg,rgba(160,230,200,.10),transparent);filter:blur(14px)}
.slab{position:absolute;left:330px;top:70px;width:860px;height:720px;transform:perspective(1500px) rotateY(16deg);transform-origin:50% 50%}
.slab svg{display:block;width:860px;height:720px;overflow:visible}
.leaders{position:absolute;inset:0;width:1440px;height:900px;pointer-events:none}
.mono,.cap{font-family:"IBM Plex Mono",ui-monospace,Menlo,monospace}
.hd{position:absolute;left:100px;top:40px;display:flex;align-items:baseline;gap:18px}
.hd .t{font-family:var(--f-name);font-size:26px;font-weight:200;letter-spacing:.22em;color:#fff;text-shadow:0 0 18px rgba(255,255,255,.25);text-decoration:none;cursor:pointer;transition:.25s}
.hd .t:hover{color:#ffd98a;text-shadow:0 0 22px rgba(245,169,58,.55)}
.hd .ch{font-size:9px;color:#8fe0b5;letter-spacing:.04em}.hd .ch.dn{color:#ff9f8a}
.hd .st{font-family:var(--f-cap);font-size:7px;letter-spacing:.34em;color:#7fb8a0;text-transform:uppercase}
.hdr{position:absolute;right:100px;top:50px;text-align:right;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.22em;color:#7fb8a0;text-transform:uppercase}
.hdr b{color:#dfe9e4;font-weight:400}
.pos{position:absolute;left:100px;top:96px;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.22em;text-transform:uppercase;color:#7fb8a0;opacity:0;animation:fadein .9s ease .3s forwards}
.pos b{font-weight:400;color:#e8fff4}.pos.mine{color:#f5a93a}.pos.mine b{color:#ffd98a}
.back{position:absolute;left:100px;top:78px;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.28em;text-transform:uppercase;color:#7fb8a0;text-decoration:none;opacity:.8}
.back:hover{color:#dfffee}
/* пометки групп */
.note{position:absolute;width:180px;color:#ffcf6e;cursor:default}
.note .row{display:flex;align-items:center;gap:7px;color:#f5a93a;filter:drop-shadow(0 0 5px rgba(255,207,110,.55))}
.note .cap{font-size:7.5px;letter-spacing:.32em;text-transform:uppercase;color:#a9dcc6;font-weight:500}
.note .num{font-family:var(--f-num);font-weight:200;font-size:16px;color:#fff;margin:5px 0 1px;letter-spacing:.02em;text-shadow:0 0 14px rgba(255,207,110,.4)}
.note .unit{font-size:9px;color:#9fd8bf;line-height:1.35}
.note .sub{font-size:8.5px;color:#7fb8a0;line-height:1.35;margin-top:3px;opacity:.85}
.note .sub.hot{color:#f5a93a;opacity:1}
.note:hover .num{color:#ffcf6e}
/* карточка — по центру экрана */
.card{position:fixed;left:50%;top:50%;transform:translate(-50%,-46%);width:460px;max-height:82vh;overflow:auto;
  background:rgba(3,18,14,.8);border:1px solid rgba(127,232,176,.3);color:#e8ecfb;backdrop-filter:blur(14px);border-radius:12px;padding:16px 20px 14px;
  box-shadow:0 30px 80px rgba(0,0,0,.55);opacity:0;pointer-events:none;transition:.25s;z-index:9}
.note:hover .card,.dzone:hover .card{opacity:1;transform:translate(-50%,-50%)}
.card .head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid rgba(127,232,176,.25)}
.card .head .cap{font-size:8px;letter-spacing:.3em;text-transform:uppercase;color:#9fd8bf}
.card .hn{font-family:var(--f-num);font-size:15px;font-weight:300;letter-spacing:.04em;color:#f5a93a}
.card .r{display:grid;grid-template-columns:10px 92px 1fr;gap:0 8px;align-items:start;padding:6px 0;border-top:1px solid rgba(255,255,255,.06)}
.card .r:first-of-type{border-top:0}
.card .r i{display:block;width:5px;height:5px;margin-top:5px;border:1px solid #f5a93a;transform:rotate(45deg);opacity:.7}
.card .r .k{font-family:var(--f-cap);font-size:7px;letter-spacing:.2em;text-transform:uppercase;line-height:1.5;padding-top:2px;color:#9fd8bf;opacity:.85}
.card .r .v{font-size:11px;line-height:1.5}
.card .r .v b{font-weight:400;color:#ffd98a}
.card .r.slots{margin-top:4px;padding-top:8px;border-top:1px dashed rgba(127,232,176,.25)}
.card .r.slots i{border-style:dashed;opacity:.4}.card .r.slots .k,.card .r.slots .v{color:#7fb8a0;opacity:.7;font-size:9.5px}
.dzone{position:absolute;cursor:default}
/* монеты */
.coins{position:absolute;right:100px;top:74px;z-index:6}
.cbtn{display:inline-flex;align-items:center;gap:8px;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.28em;text-transform:uppercase;color:#bfe9d6;cursor:pointer;
  border:1px solid rgba(255,207,110,.3);border-radius:16px;padding:6px 13px 6px 10px;background:rgba(3,18,14,.5);backdrop-filter:blur(8px);transition:.25s}
.cbtn i{width:6px;height:6px;border:1px solid #f5a93a;transform:rotate(45deg);box-shadow:0 0 8px rgba(245,169,58,.7)}
.cbtn b{font-weight:400;color:#f5a93a}
.coins:hover .cbtn{border-color:rgba(255,207,110,.7);color:#fff;box-shadow:0 0 24px rgba(245,169,58,.18)}
.coins:after{content:"";position:absolute;left:-30px;right:-30px;top:100%;height:24px}
.clist{position:absolute;right:0;top:calc(100% + 10px);display:block;padding:14px 18px 12px;border-radius:12px;
  background:rgba(3,18,14,.82);border:1px solid rgba(127,232,176,.3);backdrop-filter:blur(14px);box-shadow:0 30px 80px rgba(0,0,0,.55);
  opacity:0;transform:translateY(-6px);pointer-events:none;transition:opacity .25s,transform .25s;transition-delay:.35s}
.clist:before{content:"";position:absolute;left:-20px;right:-20px;top:-18px;height:20px}
.coins:hover .clist{opacity:1;transform:none;pointer-events:auto;transition-delay:0s}
.clist .ch{position:absolute;left:18px;top:-9px;padding:0 6px;background:#03120e;font-family:var(--f-cap);font-size:7px;letter-spacing:.28em;text-transform:uppercase;color:#7fb8a0;white-space:nowrap}
.clist .cols{display:flex;gap:14px}
.clist .col{display:flex;flex-direction:column;gap:1px;min-width:132px}
.clist a{display:flex;align-items:center;gap:7px;font-family:var(--f-num);font-weight:300;font-size:12px;letter-spacing:.1em;color:#dfe9e4;padding:3px 8px;border-radius:6px;cursor:pointer;transition:.15s;border-left:1px solid transparent;text-decoration:none;white-space:nowrap}
.clist a i{width:6px;height:6px;border-radius:50%;flex:0 0 6px;opacity:.9}
.clist a span{min-width:64px}
.clist a em{font-style:normal;font-size:9px;line-height:1;opacity:.9}.clist em.ld{color:#f5a93a}.clist em.ht{color:#ff8a70}.clist em.nw{color:#7fe8b0}.clist em.my{color:#ffd98a}
.clist a u{text-decoration:none;font-family:var(--f-cap);font-size:6.5px;letter-spacing:.16em;text-transform:uppercase;border:1px solid;border-radius:8px;padding:1px 5px;opacity:.85;margin-left:auto}
.clist a:hover{color:#f5a93a;background:rgba(245,169,58,.08);border-left-color:#f5a93a}
.clist a.cur{color:#f5a93a}.clist a.cur span:after{content:" ·"}
.cleg{display:flex;flex-wrap:wrap;gap:4px 12px;margin-top:10px;padding-top:9px;border-top:1px dashed rgba(127,232,176,.2);font-family:var(--f-cap);font-size:6.5px;letter-spacing:.18em;text-transform:uppercase;color:#7fb8a0;white-space:nowrap}
.cleg b{display:inline-flex;align-items:center;gap:5px;font-weight:400}.cleg b i{width:6px;height:6px;border-radius:50%}.cleg s{flex:0 0 100%;height:0}.cleg em{font-style:normal;font-size:9px}
/* часы и сияние */
.clockbox{position:absolute;right:96px;bottom:44px;display:flex;align-items:flex-end;gap:14px}
.cvessel{position:relative;width:100px;height:140px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}
.cvessel svg{width:100px;height:100px;display:block;overflow:visible}
.ctop{text-align:center;margin-bottom:2px;line-height:1;white-space:nowrap}
.ctop b{display:block;font-family:var(--f-num);font-weight:200;font-size:18px;letter-spacing:.06em;text-shadow:0 0 14px rgba(255,255,255,.25)}
.ctop span{display:block;margin-top:4px;font-family:var(--f-cap);font-size:6.5px;letter-spacing:.3em;text-transform:uppercase;color:#bfe9d6}
.ctxt{margin-bottom:34px;display:flex;flex-direction:column;gap:6px;font-family:var(--f-cap);font-size:8px;letter-spacing:.16em;text-transform:uppercase}
.ctxt .k{color:#7fb8a0;margin-right:8px}.ctxt b{font-weight:400;color:#e8fff4}
.w1{animation:wave 9s linear infinite}.w2{animation:wave 14s linear infinite reverse}@keyframes wave{to{transform:translateX(-92px)}}
.breath{animation:breath 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes breath{0%,100%{opacity:.28;transform:scale(1)}50%{opacity:.42;transform:scale(1.04)}}
.aura{position:absolute;left:250px;width:960px;top:-40px;height:340px;border-radius:50%;filter:blur(46px);opacity:0;transition:opacity 1.2s;pointer-events:none;transform-origin:50% 65%}
.aura.up{background:radial-gradient(50% 60% at 50% 65%, rgba(90,255,160,.8), rgba(70,240,140,.3) 45%, transparent 75%)}
.aura.dn{background:radial-gradient(50% 60% at 50% 65%, rgba(255,90,74,.7), rgba(255,90,74,.22) 45%, transparent 75%)}
.aura:after{content:"";position:absolute;left:12%;right:12%;top:62%;height:26%;border-radius:50%;filter:blur(18px)}
.aura.up:after{background:rgba(120,255,180,.5)}.aura.dn:after{background:rgba(255,110,90,.5)}
.aura.on{opacity:1}.aura.soon{opacity:.42;transform:scale(.5);animation:auraPulse 3s ease-in-out infinite}
@keyframes auraPulse{0%,100%{opacity:.3}50%{opacity:.55}}
/* появление сцены */
.an{opacity:0;animation:fadein 1s ease forwards}
.ln{stroke-dasharray:var(--L);stroke-dashoffset:var(--L);animation:draw 1.9s cubic-bezier(.5,0,.3,1) .6s forwards}
.ld{stroke-dasharray:var(--L);stroke-dashoffset:var(--L);animation:draw .5s ease-out forwards}
.grd{animation-delay:.25s}.edge{animation-delay:2.3s}.fillg{animation-delay:1.9s;animation-duration:1.4s}.mesh{animation-delay:2.1s;animation-duration:1.4s}
.nd{animation-duration:.5s}.refl{animation-delay:2.6s;animation-duration:1.2s}.lv,.lv2{animation-delay:2.7s}.now{animation-delay:2.5s}
.ldc{animation-duration:.4s}.note.an{animation-duration:.7s}.dec{animation-delay:3.5s;animation-duration:1s}
.hd,.hdr,.coins,.clockbox,.back{opacity:0;animation:fadein .9s ease .1s forwards}
@keyframes fadein{to{opacity:1}}@keyframes draw{to{stroke-dashoffset:0}}
.tw{animation:tw 5s ease-in-out infinite}@keyframes tw{0%,100%{opacity:.85}50%{opacity:.25}}
.ring{transform-box:fill-box;transform-origin:center;animation:ring 2.2s ease-out infinite}@keyframes ring{0%{transform:scale(.6);opacity:.9}100%{transform:scale(3.2);opacity:0}}
.replay{position:absolute;left:100px;bottom:22px;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.24em;text-transform:uppercase;color:#7fb8a0;cursor:pointer;border:1px solid rgba(127,232,176,.25);border-radius:14px;padding:5px 12px;z-index:5}
.replay:hover{color:#dfffee;border-color:rgba(127,232,176,.5)}
.legend{position:absolute;right:270px;bottom:22px;font-family:var(--f-cap);font-size:7px;letter-spacing:.22em;color:#5e8f7a}
.atmo{position:absolute;inset:0;pointer-events:none}
.atmo .vig{position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 50% 45%, transparent 45%, rgba(0,0,0,.55) 100%)}
.atmo svg{position:absolute;inset:0;width:100%;height:100%;opacity:.07;mix-blend-mode:overlay}
.empty{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;font-family:var(--f-cap);font-size:9px;letter-spacing:.3em;text-transform:uppercase;color:#7fb8a0}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}.an,.hd,.hdr,.coins,.clockbox,.back{opacity:1}.ln,.ld{stroke-dashoffset:0}}
</style>
<div class="wrap"><div class="stage" id="stage"></div></div>
</template>
"""


# ═════════════════════════════════════════════════════════════════════
# ЛОГИКА. Всё считается из данных на месте: сцена, пометки, карточки,
# часы. Ничего не рисуется тем, чего в сводке нет.
# ═════════════════════════════════════════════════════════════════════
COIN_JS = r"""
<script>
(function () {
  'use strict';
  var raw = document.getElementById('coinData');
  var D; try { D = JSON.parse(raw.textContent); } catch (e) { return; }
  var host = document.getElementById('coinHost');
  var tpl = document.getElementById('coinTpl');
  var root = host.attachShadow({ mode: 'open' });
  root.appendChild(tpl.content.cloneNode(true));
  var stage = root.getElementById('stage');

  var STARS = (D.stars || []).filter(function (s) { return s && s.t; });
  var BY = {}; STARS.forEach(function (s) { BY[String(s.t).toUpperCase()] = s; });
  var NAMES = Object.keys(BY).sort();
  var WH = D.whales || {}, SC = D.sched, JR = D.journal || {}, HIST = D.hist || {}, BOOK = D.book || {}, CROWD = D.crowd || {}, FLOW = D.flow || {};

  // ── помощники ──
  function esc(t) { return String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
  function f(x) { return (Math.round(x * 100) / 100).toString(); }
  function pct(v, d) { if (v === undefined || v === null || isNaN(+v)) return null; var n = +v; return (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(d === undefined ? 1 : d) + '%'; }
  function px4(v) { v = +v; if (!v) return '—'; return v >= 100 ? v.toFixed(1) : v >= 1 ? v.toFixed(3) : v >= 0.01 ? v.toFixed(4) : v.toFixed(6); }
  function money(v) { v = +v; if (!v) return null; var a = Math.abs(v), s = v < 0 ? '−' : '';
    return s + '$' + (a >= 1e9 ? (a / 1e9).toFixed(1) + 'B' : a >= 1e6 ? (a / 1e6).toFixed(1) + 'M' : a >= 1e3 ? (a / 1e3).toFixed(0) + 'K' : a.toFixed(0)); }
  function pad(n) { return (n < 10 ? '0' : '') + n; }
  var NUM = /(?<![\w])([+−\-]?\$?\d[\d.,]*[%KMB]?|×\d[\d.]*|\d+\/\d+|ATR)(?![\w])/g;
  function hl(t) { return esc(t).replace(NUM, '<b>$1</b>'); }
  function has(v) { return v !== undefined && v !== null && v !== '' && !(typeof v === 'number' && isNaN(v)); }

  // ── ШЕСТЬ ГРУПП: цифра, единица, чтение и строки карточки — из полей звезды ──
  function groups(s) {
    var cg = s.cg || {}, rep = s.rep || {}, lv = s.levels || {}, u = s.unlock, act = s.act || {};
    var g = {};
    // ГДЕ ЦЕНА
    var pr = [];
    pr.push(['сейчас', px4(s.px) + (s.cap ? ' · капитализация ' + s.cap : '') + (has(s.floatPct) ? ' · флоат ' + Math.round(s.floatPct) + '%' : '')]);
    pr.push(['масштаб', (has(s.lifeDrop) ? '−' + Math.round(s.lifeDrop) + '% от пика жизни' : 'от пика: нет в сводке') + (has(s.up) ? ' · +' + Math.round(s.up) + '% от дна' + (s.updays ? ' за ' + s.updays + ' дн' : '') : '')]);
    if (lv.above && lv.above.price) pr.push(['плита', px4(lv.above.price) + (lv.above.dist !== undefined ? ' — ' + pct(lv.above.dist) : '') + (lv.above.touches ? ' · касаний ' + lv.above.touches : '')]);
    if (lv.below && lv.below.price) pr.push(['опора', px4(lv.below.price) + (lv.below.dist !== undefined ? ' — ' + pct(lv.below.dist) : '') + (lv.below.touches ? ' · касаний ' + lv.below.touches : '')]);
    if (lv.note) pr.push(['реакция на уровень', lv.note]);
    if (s.stop) pr.push(['стоп', px4(s.stop) + (s.px && +s.stop >= +s.px ? ' — УЖЕ ПРОЙДЕН' : s.stopPct !== undefined ? ' · ' + pct(-Math.abs(s.stopPct)) + ' от цены' : '')]);
    if (s.liqZones && s.liqZones.length) pr.push(['ликвидации над ценой', s.liqZones.slice(0, 3).map(function (z) { return money(z.fuel) + ' @ ' + px4((z.lo + z.hi) / 2); }).join(' · ')]);
    var fw = FLOW[String(s.t).toUpperCase()]; if (fw && fw.low && fw.high) pr.push(['коридор потока', px4(fw.low) + ' – ' + px4(fw.high) + (fw.case ? ' · случай ' + fw.case : '')]);
    if (has(s.rangePos)) pr.push(['в диапазоне', Math.round(s.rangePos * (s.rangePos <= 1 ? 100 : 1)) + '%']);
    if (has(s.speedAtr)) pr.push(['скорость хода', f(s.speedAtr) + ' ATR']);
    g.price = { cap: 'где цена', num: has(s.lifeDrop) ? '−' + Math.round(s.lifeDrop) + '%' : (has(s.up) ? '+' + Math.round(s.up) + '%' : '—'),
      unit: has(s.lifeDrop) ? 'от пика' : 'от дна', sub: has(s.up) ? '+' + Math.round(s.up) + '% от дна' + (s.upX ? ' · ×' + s.upX + ' ход' : '') : '', rows: pr, glyph: 'sq' };
    // РЕШЕНИЕ
    var verdict = String(act.act || s.stanceVerdict || s.verdict || 'ждать').toLowerCase();
    var why = (act.whyFull && act.whyFull[0]) || act.why || s.verdict || '';
    var dr = [['вердикт', verdict.toUpperCase() + (why ? ' · ' + why : '')]];
    if (act.whyFull && act.whyFull.length > 1) act.whyFull.slice(1).forEach(function (w, i) { dr.push([i ? '' : 'основание', w]); });
    if (s.exitWhy) dr.push(['снимется', s.exitWhy + (s.exitDeadline ? ' · до ' + s.exitDeadline : '')]);
    var st = []; ['absorb', 'squeeze', 'effort', 'wyckoffTest'].forEach(function (k) { if (s[k] && s[k].note) st.push(s[k].note); });
    dr.push(['шаблон', (s.pattern || '—') + (s.phase ? ' · фаза ' + s.phase : '') + (st.length ? ' · состояние: ' + st.slice(0, 2).join(' · ') : '')]);
    if (s.st) dr.push(['стадия', String(s.st) + (s.streak ? ' · подряд ' + s.streak : '')]);
    var pro = [], con = [];
    if (cg.taker && +cg.taker > 1) pro.push('покупки ×' + (+cg.taker).toFixed(2) + ' к продажам'); else if (cg.taker && +cg.taker < 0.9) con.push('продают ×' + (1 / +cg.taker).toFixed(2) + ' к покупкам');
    if (s.vxDir === 'up') pro.push('вортекс вверх'); else if (s.vxDir === 'down') con.push('вортекс вниз');
    if (s.klinger && s.klinger.crossUp) pro.push('клингер крест вверх');
    if (s.oiState === 'held') con.push('плечо застряло'); else if (s.oiState === 'cleared') pro.push('плечо разгружено');
    if (u && u.days <= 3) con.push('разлок ' + u.days + ' дн');
    if (has(s.fund) && +s.fund > 0.01) con.push('толпа в лонге, фандинг ' + (+s.fund).toFixed(3) + '%');
    if (has(s.fund) && +s.fund < -0.01) pro.push('шорты платят');
    if (rep.delta_usd && +rep.delta_usd > 0) pro.push('дельта дневки в плюс'); else if (rep.delta_usd && +rep.delta_usd < 0) con.push('дельта дневки в минус');
    dr.push(['за', pro.length ? pro.join(' · ') : 'нет'], ['против', con.length ? con.join(' · ') : 'нет']);
    g.decision = { cap: 'решение', num: verdict, verdict: verdict.toUpperCase(), why: why, rows: dr, pro: pro, con: con,
      exit: s.exitWhy || '', hurry: (s.exitDeadline ? 'срок ' + s.exitDeadline : (u && u.days <= 1 ? 'разлок ' + (u.days ? 'завтра' : 'сегодня') : '')) };
    // ПОТОК
    var fr = [];
    if (has(cg.taker)) fr.push(['покупки к продажам', '×' + (+cg.taker).toFixed(2) + (has(cg.cvdChg) ? ' · дельта ' + money(cg.cvdChg) : '')]);
    if (rep.phrase) fr.push(['в стакане · дневка', rep.phrase + (rep.delta_usd ? ' · дельта ' + money(rep.delta_usd) : '')]);
    if (has(s.press)) fr.push(['давление', String(s.press) + (has(s.pressShare) ? ' · доля ' + Math.round(+s.pressShare <= 1 ? +s.pressShare * 100 : +s.pressShare) + '%' : '')]);
    if (has(s.v1d)) fr.push(['объём', '×' + (+s.v1d).toFixed(1) + ' к норме' + (has(s.v1h) ? ' · час ×' + (+s.v1h).toFixed(1) : '') + (s.volBg ? ' · фон ' + s.volBg : '')]);
    if (has(cg.spotUsd)) fr.push(['спот', money(cg.spotUsd) + (has(cg.spotTaker) ? ' · тейкер ×' + (+cg.spotTaker).toFixed(2) : '') + (has(cg.fsRatio) ? ' · фьюч к споту ×' + (+cg.fsRatio).toFixed(1) : '')]);
    if (has(s.bigCount) && +s.bigCount > 0) fr.push(['крупные', s.bigCount + ' сделок' + (s.bigBuys !== undefined ? ' · покупок ' + s.bigBuys + ', продаж ' + s.bigSells : '') + (s.bigMax ? ' · крупнейшая ' + money(s.bigMax) : '')]);
    if (s.klinger) fr.push(['клингер', (s.klinger.crossUp ? 'крест вверх у дна' : s.klinger.crossDn ? 'крест вниз' : s.klinger.above ? 'выше сигнала' : 'ниже сигнала')]);
    if (has(s.shakeX)) fr.push(['вынос', '×' + f(s.shakeX) + (s.shakeHours ? ' за ' + s.shakeHours + ' ч' : '') + (has(s.shakeMove) ? ' · ход ' + pct(s.shakeMove) : '')]);
    var flowNum = has(cg.taker) ? '×' + (+cg.taker).toFixed(2) : (has(s.v1d) ? '×' + (+s.v1d).toFixed(1) : '—');
    g.flow = { cap: 'поток', num: flowNum, unit: has(cg.taker) ? 'покупки к продажам' : 'объём к норме', sub: rep.phrase ? String(rep.phrase).split(' — ')[0].slice(0, 60) : (has(s.v1d) ? 'объём ×' + (+s.v1d).toFixed(1) + ' к норме' : ''), rows: fr, glyph: 'dia' };
    // ПЛЕЧО
    var lr = [];
    if (has(cg.oiChgPct)) lr.push(['OI за сутки', pct(cg.oiChgPct) + (has(s.fund) ? ' · фандинг ' + (+s.fund).toFixed(4) + '%' : '')]);
    else if (has(s.fund)) lr.push(['фандинг', (+s.fund).toFixed(4) + '%']);
    if (s.oiState) lr.push(['цикл плеча', s.oiState === 'held' ? 'застряло' : s.oiState === 'cleared' ? 'разгружено' : s.oiState === 'repeat' ? 'повторный цикл' : String(s.oiState)]);
    if (s.liqFuel && (s.liqFuel.below || s.liqFuel.above)) lr.push(['в капитализации', (s.liqFuel.below ? 'снизу ' + (+s.liqFuel.below * 100).toFixed(1) + '%' : '') + (s.liqFuel.above ? ' · сверху ' + (+s.liqFuel.above * 100).toFixed(1) + '%' : '') + ' — оценка по модели, не наблюдение']);
    if (s.liq24h && (s.liq24h.long || s.liq24h.short)) lr.push(['ликвидации за сутки', 'лонгов ' + (money(s.liq24h.long) || '$0') + ' против шортов ' + (money(s.liq24h.short) || '$0')]);
    if (s.vxDir) lr.push(['топливо', 'вортекс ' + (s.vxDir === 'up' ? 'вверх' : s.vxDir === 'down' ? 'вниз' : s.vxDir) + (has(s.vxSpread) ? ' · разрыв ' + f(s.vxSpread) : '') + (s.vxAgo ? ' · ' + s.vxAgo + ' ч назад' : '')]);
    var cw = CROWD[String(s.t).toUpperCase()]; if (cw && cw.crowd) lr.push(['толпа', 'в лонге ' + cw.crowd.longPct + '%' + (has(cw.crowd.chg1d) ? ' (за сутки ' + pct(cw.crowd.chg1d) + ')' : '') + (cw.top ? ' · топы ' + cw.top.longPct + '%' : '')]);
    var w = WH[String(s.t).toUpperCase()] || WH[String(s.t)];
    if (w) lr.push(['киты Hyperliquid', 'лонг ' + (money(w.long) || '$0') + ' против шорта ' + (money(w.short) || '$0') + (w.n ? ' · позиций ' + w.n : '')]);
    var levNum = has(cg.oiChgPct) ? pct(cg.oiChgPct) : (has(s.fund) ? (+s.fund).toFixed(3) + '%' : '—');
    g.lever = { cap: 'плечо', num: levNum, unit: has(cg.oiChgPct) ? 'OI за сутки' : 'фандинг', sub: (s.oiState ? (s.oiState === 'held' ? 'застряло' : s.oiState === 'cleared' ? 'разгружено' : 'повторный цикл') : '') + (s.liqFuel && s.liqFuel.below ? ' · ' + (+s.liqFuel.below * 100).toFixed(1) + '% снизу' : '') + (s.liqFuel && s.liqFuel.above ? ' · ' + (+s.liqFuel.above * 100).toFixed(1) + '% сверху' : ''), rows: lr, glyph: 'chev' };
    // ПАМЯТЬ
    var mr = [];
    if (rep.line) mr.push(['репутация монеты', rep.line]);
    if (has(s.rallies)) mr.push(['отскоки', s.rallies + ' всего' + (has(s.heldRallies) ? ' · удержали ' + s.heldRallies : '')]);
    if (has(s.days)) mr.push(['в журнале', s.days + ' дн' + (has(s.hitCount) ? ' · попаданий ' + s.hitCount : '') + (has(s.runsSeen) ? ' · пробегов ' + s.runsSeen : '')]);
    var bk = BOOK[String(s.t).toUpperCase()];
    if (bk && bk.entry) mr.push([bk.manual ? 'твоя позиция' : 'вход журнала', px4(bk.entry) + ' с ' + bk.since.slice(8, 10) + '.' + bk.since.slice(5, 7) + (has(bk.chg) ? ' · ' + pct(bk.chg) + ' от входа' : '') + (has(bk.maxChg) ? ' · максимум ' + pct(bk.maxChg) : '') + (bk.closed ? ' · ЗАКРЫТА' + (bk.closedPx ? ' по ' + px4(bk.closedPx) : '') : '')]);
    var j = JR[String(s.t).toUpperCase()];
    if (j) {
      mr.push(['журнал прогнозов', 'записей ' + j.n + ' · смен ' + j.switches + ' · с ' + j.firstAt + ' по ' + px4(j.first)]);
      if (j.lastSwitch) mr.push(['последняя смена', '«' + j.lastSwitch.tpl + '» ' + j.lastSwitch.at + ' · ' + px4(j.lastSwitch.px) + ' · ' + pct(j.lastSwitch.chg) + ' от прошлой']);
    }
    if (s.trendDone) mr.push(['ход', 'отработан']);
    var memNum = has(s.heldRallies) && has(s.rallies) ? s.heldRallies + ' из ' + s.rallies : (j ? String(j.switches) : '—');
    g.memory = { cap: 'память', num: memNum, unit: has(s.heldRallies) && has(s.rallies) ? 'отскоков устояли' : (j ? 'смен прогноза' : ''), sub: j ? 'журнал: ' + j.n + ' записей · смен ' + j.switches : (has(s.days) ? 'в журнале ' + s.days + ' дн' : ''), rows: mr, glyph: 'plus' };
    // КАЛЕНДАРЬ · ФУНДАМЕНТ
    var cr = [], hot = false;
    if (u) { hot = (u.pct >= 10) || (u.ins >= 60 && u.pct >= 2); cr.push(['разлок', u.days + ' дн · ' + u.pct + '% обращения' + (u.ins !== undefined ? ' · инсайдерам ' + u.ins + '%' : '')]); }
    if (s.exitDeadline) cr.push(['срок', String(s.exitDeadline) + (s.exitWhy ? ' — ' + s.exitWhy : '')]);
    if (s.news && (s.news.t || s.news.why)) cr.push(['повод', (s.news.t || '') + (s.news.why ? ' — ' + s.news.why : '')]);
    if (s.investors && s.investors.length) cr.push(['инвесторы', s.investors.join(' · ')]);
    var pf = []; if (s.organizer) pf.push('организатор ' + s.organizer); if (s.chain) pf.push(s.chain); if (has(s.listingDays)) pf.push('листинг ' + s.listingDays + ' дн назад');
    if (pf.length) cr.push(['профиль', pf.join(' · ')]);
    if (s.sector && s.sector !== '—') cr.push(['сектор', s.sector]);
    if (has(s.fdvRatio)) cr.push(['FDV к капе', '×' + (+s.fdvRatio).toFixed(1)]);
    var calNum = u ? u.days + ' дн' : (s.exitDeadline ? String(s.exitDeadline) : '—');
    g.calendar = { cap: 'календарь · фундамент', num: calNum, unit: u ? 'до разлока' : (s.exitDeadline ? 'срок' : ''), sub: u ? u.pct + '% обращения' + (u.ins !== undefined ? ' · инсайдерам ' + u.ins + '%' : '') : (s.news && s.news.t ? s.news.t : ''), rows: cr, glyph: 'arrow', hot: hot };
    // слоты, которых у монеты нет — подвалом, чтобы было видно место
    var slots = { price: ['вершина хода', 'крупнейшая плита', 'ход и скорость хода'], flow: ['полусутки', 'чем оплачено', 'дивер', 'откупы за сутки', 'доля спота', 'фон суток', 'в книге', 'на биржи/с бирж', 'спрос', 'формы суток'],
      lever: ['киты Hyperliquid', 'плечо открыли', 'плечо под и над ценой'], memory: ['ожидание по эпизодам', 'заметность'], calendar: ['макро-даты', 'листинг/делистинг'] };
    Object.keys(slots).forEach(function (k) { var have = g[k].rows.map(function (r) { return r[0]; }); var miss = slots[k].filter(function (n) { return have.indexOf(n) < 0; }); if (miss.length) g[k].rows.push(['без данных', miss.join(' · ')]); });
    return g;
  }

  function cardHtml(g) {
    var rows = g.rows.map(function (r) {
      if (r[0] === 'без данных') return '<div class="r slots"><i></i><span class="k">без данных у монеты</span><span class="v">' + esc(r[1]) + '</span></div>';
      return '<div class="r"><i></i><span class="k">' + esc(r[0]) + '</span><span class="v">' + hl(r[1]) + '</span></div>';
    }).join('');
    return '<div class="card"><div class="head"><span class="cap">' + esc(g.cap) + '</span><span class="hn">' + esc(g.num) + '</span></div>' + rows + '</div>';
  }

  // ── ГЕОМЕТРИЯ ПЛИТЫ ──
  var SW = 860, SH = 720, SL = 330, ST = 70, X0 = 70, X1 = 790, Y1 = 40, Y0 = 500, TH = 16 * Math.PI / 180, PERS = 1500;
  function project(x, y) { var cx = SL + SW / 2, cy = ST + SH / 2, dx = SL + x - cx, dy = ST + y - cy; var x1 = dx * Math.cos(TH), z1 = -dx * Math.sin(TH), w = 1 - z1 / PERS; return [cx + x1 / w, cy + dy / w]; }
  var GOLD = '#f5a93a', GOLDL = '#ffd98a', MINT = '#7ff0b8', TEAL = '#2ec98d';
  function seeded(seed) { var s = seed; return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; }; }

  function scene(P, rnd) {
    var t = '', i;
    var area = 'M' + f(P[0][0]) + ',' + Y0 + ' ' + P.map(function (p) { return 'L' + f(p[0]) + ',' + f(p[1]); }).join(' ') + ' L' + f(P[P.length - 1][0]) + ',' + Y0 + ' Z';
    t += '<g class="an fillg"><path d="' + area + '" fill="url(#slab)"/><path d="' + area + '" fill="url(#sheen)"/></g>';
    t += '<g class="an mesh">';
    for (i = 0; i < P.length; i += 2) t += '<line x1="' + f(P[i][0]) + '" y1="' + f(P[i][1]) + '" x2="' + f(P[i][0]) + '" y2="' + Y0 + '" stroke="' + MINT + '" stroke-width=".5" opacity=".28"/>';
    var pts = [];
    for (i = 0; i < 110; i++) { var k = Math.min(P.length - 2, Math.floor(rnd() * (P.length - 1))); var x = P[k][0] + rnd() * (P[k + 1][0] - P[k][0]);
      var yt = P[k][1] + (P[k + 1][1] - P[k][1]) * (x - P[k][0]) / Math.max(1e-6, P[k + 1][0] - P[k][0]); pts.push([x, yt + rnd() * (Y0 - yt)]); }
    pts.forEach(function (p) {
      var near = pts.slice().sort(function (a, b) { return ((a[0] - p[0]) * (a[0] - p[0]) + (a[1] - p[1]) * (a[1] - p[1])) - ((b[0] - p[0]) * (b[0] - p[0]) + (b[1] - p[1]) * (b[1] - p[1])); }).slice(1, 3);
      near.forEach(function (q) { t += '<line x1="' + f(p[0]) + '" y1="' + f(p[1]) + '" x2="' + f(q[0]) + '" y2="' + f(q[1]) + '" stroke="' + MINT + '" stroke-width=".5" opacity=".4"/>'; });
      t += '<circle cx="' + f(p[0]) + '" cy="' + f(p[1]) + '" r="2.4" fill="' + MINT + '" opacity=".35" filter="url(#blur3)"/><circle cx="' + f(p[0]) + '" cy="' + f(p[1]) + '" r=".9" fill="#dfffee" opacity=".85" class="tw" style="animation-delay:' + (rnd() * 6).toFixed(1) + 's"/>';
    });
    t += '</g>';
    var L = P[P.length - 1];
    t += '<g class="an edge"><line x1="' + f(L[0]) + '" y1="' + f(L[1]) + '" x2="' + f(L[0]) + '" y2="' + Y0 + '" stroke="' + MINT + '" stroke-width="5" opacity=".25" filter="url(#blur3)"/><line x1="' + f(L[0]) + '" y1="' + f(L[1]) + '" x2="' + f(L[0]) + '" y2="' + Y0 + '" stroke="#e9fff4" stroke-width="1" opacity=".7"/></g>';
    t += '<g class="an grd"><ellipse cx="' + ((X0 + X1) / 2) + '" cy="' + (Y0 + 9) + '" rx="' + ((X1 - X0) / 2 + 60) + '" ry="16" fill="' + GOLD + '" opacity=".4" filter="url(#blur12)"/>' +
      '<line x1="' + (X0 - 40) + '" y1="' + Y0 + '" x2="' + (X1 + 40) + '" y2="' + Y0 + '" stroke="' + GOLDL + '" stroke-width="7" opacity=".5" filter="url(#blur3)"/>' +
      '<line x1="' + (X0 - 30) + '" y1="' + Y0 + '" x2="' + (X1 + 30) + '" y2="' + Y0 + '" stroke="url(#ground)" stroke-width="4"/>' +
      '<line x1="' + (X0 - 24) + '" y1="' + Y0 + '" x2="' + (X1 + 24) + '" y2="' + Y0 + '" stroke="#fff6dc" stroke-width="1.6" opacity=".95"/></g>';
    var pl = P.map(function (p) { return f(p[0]) + ',' + f(p[1]); }).join(' '), LEN = 0;
    for (i = 1; i < P.length; i++) LEN += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
    [[44, .16, ' filter="url(#blur30)"', '#e0891f'], [22, .26, ' filter="url(#blur12)"', GOLD], [9, .5, ' filter="url(#blur3)"', GOLD], [4, .9, '', GOLD], [2, 1, '', GOLDL]].forEach(function (q) {
      t += '<polyline class="ln" points="' + pl + '" fill="none" stroke="' + q[3] + '" stroke-width="' + q[0] + '" stroke-linejoin="round" stroke-linecap="round" opacity="' + q[1] + '" style="--L:' + Math.ceil(LEN + 2) + '"' + q[2] + '/>';
    });
    var step = Math.max(1, Math.round(P.length / 12));
    for (i = 0; i < P.length; i++) if (i % step === 0 || i === P.length - 1)
      t += '<g class="an nd" style="animation-delay:' + (.6 + 1.8 * i / (P.length - 1)).toFixed(2) + 's"><circle cx="' + f(P[i][0]) + '" cy="' + f(P[i][1]) + '" r="7" fill="' + GOLD + '" opacity=".4" filter="url(#blur3)"/><circle cx="' + f(P[i][0]) + '" cy="' + f(P[i][1]) + '" r="2.4" fill="' + GOLDL + '"/></g>';
    return t;
  }

  // ── ЧАСЫ: состояние по сводке «когда ходит мелочь» (та же логика, что в схеме) ──
  function nyHourToLocal(h) { var d = new Date(); var g = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), h + 4, 0)); return g.getHours(); }
  function clockState() {
    if (!SC || !SC.pump) return null;
    var now = new Date(), lh = now.getHours() + now.getMinutes() / 60;
    function len(s) { var l = ((s[1] + 1 - s[0]) % 24 + 24) % 24; return l || 24; }
    var ups = (SC.pump || []).map(function (s) { return [nyHourToLocal(s[0]), len(s)]; }), dns = (SC.dump || []).map(function (s) { return [nyHourToLocal(s[0]), len(s)]; });
    var wins = ups.map(function (w) { return { h: w[0], e: w[0] + w[1], k: 'up' }; }).concat(dns.map(function (w) { return { h: w[0], e: w[0] + w[1], k: 'dn' }; }));
    var inside = null; wins.forEach(function (w) { var rel = (lh - w.h + 24) % 24; if (rel < w.e - w.h) inside = { k: w.k, left: w.e - w.h - rel }; });
    var ev = wins.map(function (w) { return { h: w.h, k: w.k, dh: (w.h - lh + 24) % 24 }; }).sort(function (a, b) { return a.dh - b.dh; });
    var live = false, nxt, dh;
    if (inside) { var other = ev.filter(function (e) { return e.k !== inside.k; }); if (other.length && other[0].dh < inside.left) { nxt = other[0]; dh = other[0].dh; } else { live = true; nxt = { k: inside.k }; dh = inside.left; } }
    else { nxt = ev[0]; dh = ev[0].dh; }
    function nearest(ws) { var b = null; ws.forEach(function (w) { var d = (w[0] - lh + 24) % 24; if (b === null || d < b.d) b = { d: d, h: w[0] }; }); return b; }
    var nu = nearest(ups), nd = nearest(dns);
    return { kind: nxt.k, dh: dh, live: live, soon: !live && dh <= 1, tUp: nu ? pad(nu.h) + ':00' : null, tDn: nd ? pad(nd.h) + ':00' : null };
  }
  var WATER = { up0: { nc: '#9ff5d8', top: '#8ff0cc', body: '#2fb98a', deep: '#0f5c44', halo: '#5fe6a8' }, up1: { nc: '#b9f5d3', top: '#a8f0c8', body: '#4fc08a', deep: '#1f6e52', halo: '#6fd9a8' },
    dn0: { nc: '#ffcaa8', top: '#ffc9a6', body: '#c9805e', deep: '#6a3a2a', halo: '#e0a078' }, dn1: { nc: '#ffc4b8', top: '#ffb3a7', body: '#ff5a4a', deep: '#7a2a30', halo: '#ff7a68' } };
  function vessel(cs) {
    var W = 150, H = 150, cx = 66, cy = 70, r = 44, L = 2 * r + 4, w = WATER[cs.kind + (cs.live ? '1' : '0')], nc = w.nc;
    var fill = cs.live ? .97 : Math.max(.05, Math.min(.97, 1 - cs.dh / 12)), lvl = cy + r - fill * 2 * r;
    var s = '<svg viewBox="0 0 ' + W + ' ' + H + '"><defs><filter id="vglow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="1.6"/></filter><filter id="vhalo" x="-40%" y="-40%" width="180%" height="180%"><feGaussianBlur stdDeviation="7"/></filter>' +
      '<radialGradient id="vaura" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="' + w.halo + '" stop-opacity=".30"/><stop offset=".55" stop-color="' + w.halo + '" stop-opacity=".14"/><stop offset="1" stop-color="' + w.halo + '" stop-opacity="0"/></radialGradient>' +
      '<radialGradient id="vdisc" cx="50%" cy="30%" r="75%"><stop offset="0" stop-color="#2a3058"/><stop offset=".7" stop-color="#1a1e40"/><stop offset="1" stop-color="#141733"/></radialGradient>' +
      '<linearGradient id="vliq" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + w.top + '" stop-opacity=".9"/><stop offset=".3" stop-color="' + w.body + '" stop-opacity=".82"/><stop offset="1" stop-color="' + w.deep + '" stop-opacity=".78"/></linearGradient>' +
      '<linearGradient id="vrim" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".34"/><stop offset=".5" stop-color="#fff" stop-opacity=".08"/><stop offset="1" stop-color="#fff" stop-opacity=".16"/></linearGradient>' +
      '<clipPath id="vclip"><circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"/></clipPath></defs>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r + 22) + '" fill="url(#vaura)"/>';
    if (cs.soon || cs.live) { var hw = cs.live ? w : WATER[cs.kind + '1']; s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r + 3) + '" fill="none" stroke="' + hw.halo + '" stroke-width="10" opacity=".28" filter="url(#vhalo)" class="breath"/>'; }
    if (cs.live) s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + (r + 2.5) + '" fill="none" stroke="' + nc + '" stroke-width="1" opacity=".5"/>';
    s += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="url(#vdisc)" opacity=".9"/><g clip-path="url(#vclip)">';
    [[2.2, 0, .95, 'w1'], [1.6, 1.9, .6, 'w2']].forEach(function (wv) {
      var x0 = cx - r - 2, d = 'M' + (x0 - L).toFixed(1) + ',' + lvl.toFixed(1);
      for (var k = 0; k <= 180; k++) { var x = x0 - L + k * (3 * L) / 180, y = lvl + Math.sin((x - x0) / L * Math.PI * 6 + wv[1]) * wv[0]; d += ' L' + x.toFixed(1) + ',' + y.toFixed(1); }
      d += ' L' + (x0 + 2 * L).toFixed(1) + ',' + (cy + r + 2) + ' L' + (x0 - L).toFixed(1) + ',' + (cy + r + 2) + ' Z';
      s += '<g class="' + wv[3] + '"><path d="' + d + '" fill="url(#vliq)" opacity="' + wv[2] + '"/><path d="' + d + '" fill="none" stroke="#fff" stroke-width=".8" opacity="' + (wv[2] * .55).toFixed(2) + '" filter="url(#vglow)"/></g>';
    });
    s += '<ellipse cx="' + (cx - 18) + '" cy="' + (lvl + 6).toFixed(1) + '" rx="14" ry="3" fill="#fff" opacity=".10" filter="url(#vglow)"/>';
    [[cx - 18, lvl + 14, 1.2], [cx + 11, lvl + 26, .9], [cx - 4, lvl + 38, 1.4], [cx + 22, lvl + 9, .7]].forEach(function (b) { if (b[1] < cy + r) s += '<circle cx="' + b[0].toFixed(1) + '" cy="' + b[1].toFixed(1) + '" r="' + b[2] + '" fill="#fff" opacity=".4"/>'; });
    s += '</g><circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="url(#vrim)" stroke-width="1"/></svg>';
    var inH = Math.floor(cs.dh), inM = Math.round((cs.dh - inH) * 60), num = inH + ':' + pad(inM);
    var top = cs.live ? '<b style="color:' + nc + '">' + (cs.kind === 'up' ? 'РОСТ' : 'СЛИВ') + ' ИДЁТ</b><span>ещё ' + num + '</span>' : '<b style="color:' + nc + '">' + num + '</b><span>до ' + (cs.kind === 'up' ? 'роста' : 'слива') + '</span>';
    return '<div class="clockbox"><div class="cvessel"><div class="ctop">' + top + '</div>' + s + '</div><div class="ctxt">' + (cs.tUp ? '<div><span class="k">рост</span><b>' + cs.tUp + '</b></div>' : '') + (cs.tDn ? '<div><span class="k">слив</span><b>' + cs.tDn + '</b></div>' : '') + '</div></div>';
  }

  // ── СБОРКА ЭКРАНА ОДНОЙ МОНЕТЫ ──
  var GLYPH = { sq: '<rect x="2" y="2" width="12" height="12"/>', dia: '<path d="M8 1 L15 8 L8 15 L1 8 Z"/>', chev: '<path d="M3 4 L8 9 L13 4 M3 9 L8 14 L13 9"/>', plus: '<path d="M8 2 V14 M2 8 H14"/>', arrow: '<path d="M2 8 H13 M9 4 L13 8 L9 12"/>' };
  function build(tick) {
    var s = BY[tick]; if (!s) { stage.innerHTML = '<div class="empty">монета ' + esc(tick) + ' не в журнале</div>'; return; }
    var g = groups(s), rnd = seeded(tick.split('').reduce(function (a, c) { return a + c.charCodeAt(0); }, 7));
    var H = HIST[String(s.t).toUpperCase()], ser, d0 = null, d1 = null;
    if (H && H.c && H.c.length >= 14) { ser = H.c.slice(); d0 = H.d0; d1 = H.d1; if (s.px && ser[ser.length - 1] !== +s.px) ser.push(+s.px); }
    else ser = (s.series || []).map(Number).filter(function (v) { return v > 0; });
    if (ser.length < 2 && s.px) ser = [s.px, s.px];
    var lv = s.levels || {}, extra = [];
    if (lv.above && lv.above.price) extra.push(+lv.above.price); if (lv.below && lv.below.price) extra.push(+lv.below.price); if (s.stop) extra.push(+s.stop);
    (s.liqZones || []).slice(0, 3).forEach(function (z) { extra.push((z.lo + z.hi) / 2); });
    var lo = Math.min.apply(null, ser.concat(extra)) * .96, hi = Math.max.apply(null, ser.concat(extra)) * 1.04;
    function sy(v) { return (Y0 - 16) - (v - lo) / (hi - lo) * ((Y0 - 16) - Y1); }
    var P = ser.map(function (v, i) { return [X0 + i * (X1 - X0) / (ser.length - 1), sy(v)]; });
    var days = ser.length, today = new Date();
    function dlab(i) { var d = new Date(today.getTime() - (days - 1 - i) * 864e5); return pad(d.getDate()) + '.' + pad(d.getMonth() + 1); }
    if (d0) { var _d0 = new Date(d0), _d1 = new Date(d1); dlab = function (i) { var d = new Date(_d0.getTime() + (_d1.getTime() - _d0.getTime()) * i / Math.max(1, days - 1)); return pad(d.getDate()) + '.' + pad(d.getMonth() + 1); }; }
    // плита
    var slab = '<defs><filter id="blur3" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="3"/></filter><filter id="blur6" x="-10%" y="-40%" width="120%" height="180%"><feGaussianBlur stdDeviation="6"/></filter><filter id="blur12" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="12"/></filter><filter id="blur30" x="-40%" y="-80%" width="180%" height="260%"><feGaussianBlur stdDeviation="30"/></filter>' +
      '<linearGradient id="slab" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#1fc47c" stop-opacity=".20"/><stop offset=".5" stop-color="#118a5c" stop-opacity=".15"/><stop offset="1" stop-color="#065a3b" stop-opacity=".14"/></linearGradient>' +
      '<linearGradient id="sheen" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#9fffd0" stop-opacity="0"/><stop offset=".45" stop-color="#9fffd0" stop-opacity=".03"/><stop offset=".55" stop-color="#9fffd0" stop-opacity="0"/></linearGradient>' +
      '<linearGradient id="ground" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="' + GOLD + '" stop-opacity="0"/><stop offset=".08" stop-color="#ffe08a"/><stop offset=".92" stop-color="#ffe08a"/><stop offset="1" stop-color="' + GOLD + '" stop-opacity="0"/></linearGradient>' +
      '<linearGradient id="rf" gradientUnits="userSpaceOnUse" x1="0" y1="' + Y0 + '" x2="0" y2="' + (Y0 - 210) + '"><stop offset="0" stop-color="#fff" stop-opacity=".75"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient><mask id="rm"><rect width="100%" height="100%" fill="url(#rf)"/></mask>' +
      '<linearGradient id="shadowG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#000" stop-opacity=".75"/><stop offset="1" stop-color="#000" stop-opacity="0"/></linearGradient></defs>';
    var sh = 'M' + (X0 - 10) + ',' + (Y0 + 2) + ' ' + P.map(function (p) { return 'L' + f(p[0] + 26) + ',' + f(Y0 + (Y0 - p[1]) * .55 + 2); }).join(' ') + ' L' + f(P[P.length - 1][0] + 26) + ',' + (Y0 + 2) + ' Z';
    slab += '<path d="' + sh + '" fill="url(#shadowG)" opacity=".8" filter="url(#blur12)"/>';
    slab += '<ellipse cx="' + ((X0 + X1) / 2) + '" cy="' + (Y0 + 26) + '" rx="440" ry="36" fill="' + GOLD + '" opacity=".5" filter="url(#blur30)"/><ellipse cx="' + ((X0 + X1) / 2) + '" cy="' + (Y0 + 60) + '" rx="300" ry="60" fill="' + TEAL + '" opacity=".22" filter="url(#blur30)"/>' +
      '<ellipse cx="' + (X0 + 40) + '" cy="' + (Y0 + 40) + '" rx="120" ry="30" fill="' + GOLD + '" opacity=".3" filter="url(#blur30)"/><ellipse cx="' + (X1 - 20) + '" cy="' + (Y0 + 40) + '" rx="120" ry="30" fill="' + GOLD + '" opacity=".3" filter="url(#blur30)"/>';
    var sc = scene(P, rnd);
    slab += '<g class="an refl"><g transform="translate(0,' + (2 * Y0) + ') scale(1,-1)" mask="url(#rm)" opacity=".62" filter="url(#blur3)">' + sc + '</g></g>' + sc;
    // уровни справа от блока решения
    var LV = [];
    if (lv.above && lv.above.price) LV.push(['ПЛИТА', +lv.above.price, GOLD]);
    if (s.stop) LV.push(['СТОП', +s.stop, '#9fd8bf']);
    if (lv.below && lv.below.price) LV.push(['ОПОРА', +lv.below.price, MINT]);
    LV.forEach(function (l) { var y = sy(l[1]); slab += '<g class="an lv"><line x1="' + (X0 + 330) + '" y1="' + f(y) + '" x2="' + (X1 + 30) + '" y2="' + f(y) + '" stroke="' + l[2] + '" stroke-width=".6" opacity=".45" stroke-dasharray="3 5"/><text x="' + (X1 + 36) + '" y="' + f(y + 2.5) + '" class="mono" font-size="7" letter-spacing=".18em" fill="' + l[2] + '" opacity=".9">' + l[0] + ' ' + px4(l[1]) + '</text></g>'; });
    (s.liqZones || []).slice(0, 3).forEach(function (z) { var y = sy((z.lo + z.hi) / 2); slab += '<g class="an lv" opacity=".8"><line x1="' + X0 + '" y1="' + f(y) + '" x2="' + (X1 + 30) + '" y2="' + f(y) + '" stroke="' + GOLD + '" stroke-width="6" opacity=".12" filter="url(#blur3)"/><line x1="' + X0 + '" y1="' + f(y) + '" x2="' + (X1 + 30) + '" y2="' + f(y) + '" stroke="#fff1cc" stroke-width=".8" opacity=".55" stroke-dasharray="6 4"/><text x="' + (X1 + 36) + '" y="' + f(y + 2.5) + '" class="mono" font-size="7" letter-spacing=".14em" fill="#e6d3a3" opacity=".95">ЛИКВ ' + esc(money(z.fuel) || '') + '</text></g>'; });
    var nx = P[P.length - 1][0], ny = P[P.length - 1][1];
    slab += '<g class="an now"><circle cx="' + f(nx) + '" cy="' + f(ny) + '" r="14" fill="#fff" opacity=".22" filter="url(#blur6)"/><circle cx="' + f(nx) + '" cy="' + f(ny) + '" r="3.2" fill="#fff"/><circle class="ring" cx="' + f(nx) + '" cy="' + f(ny) + '" r="6" fill="none" stroke="#fff" stroke-width="1"/></g>';
    slab += '<g class="an lv2"><text x="' + f(nx) + '" y="' + f(ny - 14) + '" text-anchor="middle" font-family="Jost,Inter" font-weight="300" font-size="10" fill="#fff">' + px4(s.px || ser[ser.length - 1]) + ' <tspan fill="#bfe9d6">сейчас</tspan></text>';
    [[0, dlab(0)], [Math.floor(days / 2), dlab(Math.floor(days / 2))], [days - 1, 'сегодня']].forEach(function (d) { slab += '<text x="' + f(P[d[0]][0]) + '" y="' + (Y0 + 18) + '" text-anchor="middle" class="mono" font-size="7" letter-spacing=".16em" fill="#7fb8a0">' + d[1] + '</text>'; });
    slab += '<line x1="' + (X0 - 26) + '" y1="' + Y0 + '" x2="' + (X0 - 26) + '" y2="' + (Y1 + 4) + '" stroke="' + GOLD + '" stroke-width=".8" opacity=".5"/><path d="M' + (X0 - 26) + ',' + Y1 + ' l-3.5,6 h7 z" fill="' + GOLD + '" opacity=".6"/></g>';
    // решение внутри плиты
    var DX = X0 + 44, DY = Y0 - 146, dec = g.decision;
    slab += '<g class="an dec"><rect x="' + (DX - 26) + '" y="' + (DY - 30) + '" width="300" height="158" rx="12" fill="#03110c" opacity=".38" filter="url(#blur12)"/>' +
      '<rect x="' + (DX - 22) + '" y="' + (DY - 26) + '" width="292" height="150" rx="10" fill="#041d15" opacity=".42"/>' +
      '<rect x="' + (DX - 22) + '" y="' + (DY - 26) + '" width="292" height="150" rx="10" fill="none" stroke="#7ff0b8" stroke-width=".6" opacity=".22"/></g><g class="an dec"><g opacity=".78">' +
      '<text x="' + DX + '" y="' + DY + '" class="cap" font-size="7" letter-spacing=".34em" fill="#9fd8bf">РЕШЕНИЕ</text>';
    [[8, .12], [3, .24]].forEach(function (q) { slab += '<text x="' + DX + '" y="' + (DY + 38) + '" font-family="Jost,Inter" font-weight="200" font-size="34" letter-spacing=".2em" fill="none" stroke="#e0891f" stroke-width="' + q[0] + '" opacity="' + q[1] + '">' + esc(dec.verdict) + '</text>'; });
    slab += '<text x="' + DX + '" y="' + (DY + 38) + '" font-family="Jost,Inter" font-weight="200" font-size="34" letter-spacing=".2em" fill="' + GOLD + '">' + esc(dec.verdict) + '</text>';
    slab += '<text x="' + DX + '" y="' + (DY + 58) + '" font-family="Inter" font-size="10" fill="#e9fff4" opacity=".9">' + esc(String(dec.why).slice(0, 46)) + '</text>';
    slab += '<text x="' + DX + '" y="' + (DY + 72) + '" font-family="Inter" font-size="8.5" fill="#9fd8bf" opacity=".85">' + esc(dec.exit ? ('снимется: ' + dec.exit).slice(0, 56) : '') + '</text>';
    slab += '<text x="' + DX + '" y="' + (DY + 84) + '" font-family="Inter" font-size="8.5" fill="#9fd8bf" opacity=".85">' + esc(dec.hurry ? ('торопит ' + dec.hurry).slice(0, 56) : '') + '</text>';
    slab += '<line x1="' + DX + '" y1="' + (DY + 95) + '" x2="' + (DX + 250) + '" y2="' + (DY + 95) + '" stroke="#9fd8bf" stroke-width=".5" opacity=".3"/>';
    slab += '<text x="' + DX + '" y="' + (DY + 108) + '" class="cap" font-size="6.5" letter-spacing=".3em" fill="#7fe8b0">ЗА</text><text x="' + (DX + 44) + '" y="' + (DY + 108) + '" font-family="Inter" font-size="8.5" fill="#bfffe0" opacity=".9">' + esc((dec.pro.join(' · ') || 'нет').slice(0, 52)) + '</text>';
    slab += '<text x="' + DX + '" y="' + (DY + 121) + '" class="cap" font-size="6.5" letter-spacing=".3em" fill="#ffb59f">ПРОТИВ</text><text x="' + (DX + 44) + '" y="' + (DY + 121) + '" font-family="Inter" font-size="8.5" fill="#ffd9c8" opacity=".9">' + esc((dec.con.join(' · ') || 'нет').slice(0, 52)) + '</text></g></g>';
    // россыпь значков
    [[200, 190, 'sq'], [420, 120, 'plus'], [560, 240, 'dia'], [700, 160, 'chev'], [330, 250, 'sq']].forEach(function (d) { var inn = { sq: '<rect x="0" y="0" width="10" height="10"/>', plus: '<path d="M5 0 V10 M0 5 H10"/>', chev: '<path d="M0 2 L5 7 L10 2"/>', dia: '<path d="M5 0 L10 5 L5 10 L0 5 Z"/>' }[d[2]]; slab += '<g fill="none" stroke="' + GOLD + '" stroke-width="1" opacity=".5" transform="translate(' + d[0] + ',' + d[1] + ') scale(1.4)">' + inn + '</g>'; });
    // пометки и выноски
    var imin = 0; for (var i = 1; i < P.length; i++) if (P[i][1] > P[imin][1]) imin = i;
    var imax = 0; for (i = 1; i < P.length; i++) if (P[i][1] < P[imax][1]) imax = i;
    var NOTES = [['lever', 110, 250, P[imax]], ['memory', 700, 28, P[Math.floor(P.length / 2)]], ['flow', 1190, 150, P[Math.max(0, P.length - 3)]], ['price', 700, 760, P[imin]], ['calendar', 1190, 400, P[P.length - 1]]];
    var notes = '', leaders = '';
    NOTES.forEach(function (n, ni) { var G = g[n[0]], pr = project(n[3][0], n[3][1]), lx = n[1] + 8, ly = n[2] + 40, ll = Math.hypot(pr[0] - lx, pr[1] - ly);
      leaders += '<line class="ld" x1="' + lx + '" y1="' + ly + '" x2="' + f(pr[0]) + '" y2="' + f(pr[1]) + '" stroke="' + GOLD + '" stroke-width=".6" opacity=".5" style="--L:' + Math.ceil(ll + 2) + ';animation-delay:' + (2.9 + ni * .15).toFixed(2) + 's"/><circle class="an ldc" cx="' + f(pr[0]) + '" cy="' + f(pr[1]) + '" r="2.6" fill="none" stroke="' + GOLD + '" stroke-width=".8" style="animation-delay:' + (3.3 + ni * .15).toFixed(2) + 's"/>';
      notes += '<div class="note an" style="left:' + n[1] + 'px;top:' + n[2] + 'px;animation-delay:' + (3 + ni * .15).toFixed(2) + 's">' + cardHtml(G) + '<div class="row"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3">' + GLYPH[G.glyph] + '</svg><span class="cap">' + esc(G.cap) + '</span></div><div class="num">' + esc(G.num) + '</div><div class="unit">' + esc(G.unit || '') + '</div><div class="sub' + (G.hot ? ' hot' : '') + '">' + esc(G.sub || '') + '</div></div>';
    });
    var d1 = project(DX - 20, DY - 24), d2 = project(DX + 270, DY + 92);
    var dzone = '<div class="dzone" style="left:' + Math.round(d1[0]) + 'px;top:' + Math.round(d1[1]) + 'px;width:' + Math.round(d2[0] - d1[0]) + 'px;height:' + Math.round(d2[1] - d1[1]) + 'px">' + cardHtml(g.decision) + '</div>';
    // шапка, монеты, часы
    var chg = has(s.p1d) ? (+s.p1d) : null;
    var bk2 = BOOK[String(s.t).toUpperCase()], pos = '';
    if (bk2 && bk2.entry) pos = '<div class="pos' + (bk2.manual ? ' mine' : '') + '">' + (bk2.manual ? 'твоя позиция' : 'вход журнала') + ' <b>' + px4(bk2.entry) + '</b>' + (has(bk2.chg) ? ' · <b>' + pct(bk2.chg) + '</b> от входа' : '') + (bk2.upX && +bk2.upX >= 1.5 ? ' · ×' + (+bk2.upX).toFixed(1) : '') + (bk2.closed ? ' · закрыта' : '') + '</div>';
    // имя монеты — ссылка на TradingView, бессрочный фьючерс Binance (суффикс .P), в новой вкладке
    var tvSym = 'BINANCE:' + String(s.coin || (String(s.t).toUpperCase() + 'USDT')).toUpperCase().replace(/[^A-Z0-9]/g, '') + '.P';
    var hd = '<div class="hd"><a class="t" href="https://www.tradingview.com/chart/?symbol=' + encodeURIComponent(tvSym) + '" target="_blank" rel="noopener" title="открыть в TradingView · Binance фьючерс">' + esc(s.t) + '</a>' + (chg !== null ? '<span class="ch' + (chg < 0 ? ' dn' : '') + '">' + pct(chg) + ' за сутки</span>' : '') + (s.pattern ? '<span class="st">' + esc(s.pattern) + '</span>' : '') + '</div>' + pos;
    var hdr = '<div class="hdr">' + (s.cap ? 'капитализация <b>' + esc(s.cap) + '</b>' : '') + (has(s.v1d) ? ' · объём к норме <b>×' + (+s.v1d).toFixed(1) + '</b>' : '') + (has(s.fund) ? ' · фандинг <b>' + (+s.fund).toFixed(3) + '%</b>' : '') + '</div>';
    // значки — как в зале: цвет кейса FLOW (GATE_CASE), группа книги (в работе · брать · выходить), лидер, горячая, новая, своя
    var CASE_C = { hidden: ['#d9b96e', 'скрытый спрос'], spring: ['#6b7ae0', 'пружина'], churn: ['#8b93c4', 'перемол'], fuel: ['#f0a878', 'топливо'], dormant: ['#5c6598', 'спячка'], taker: ['#c98ce0', 'смена агрессора'], leverage: ['#ec6f5e', 'плечо'] };
    var GRP_C = { take: ['#6b7ae0', 'брать'], trade: ['#4fc98a', 'в работе'], exit: ['#ec6f5e', 'выходить'] };
    function grpOf(z) { var inBook = !!(z.book && (z.book.usd || z.book.px)); if (inBook) return (z.act && z.act.group) === 'exit' ? 'exit' : 'trade'; return (z.act && z.act.act) === 'брать' ? 'take' : null; }
    function marks(z) { var m = ''; if (z.lead) m += '<em class="ld" title="лидер прогона">★</em>'; if (z.hot) m += '<em class="ht" title="горячая: оборот выше порога">●</em>'; if (z.new) m += '<em class="nw" title="новая в журнале">✦</em>'; var b = BOOK[String(z.t).toUpperCase()]; if (b && b.manual && !b.closed) m += '<em class="my" title="твоя позиция">◆</em>'; return m; }
    var cols = '', per = 14;
    for (i = 0; i < NAMES.length; i += per) cols += '<div class="col">' + NAMES.slice(i, i + per).map(function (c) {
      var z = BY[c], cc = CASE_C[z.st] || ['#7b83b8', 'без кейса'], gr = grpOf(z);
      return '<a href="#' + esc(c) + '" class="' + (c === tick ? 'cur' : '') + '"><i style="background:' + cc[0] + ';box-shadow:0 0 6px ' + cc[0] + '" title="' + cc[1] + '"></i><span>' + esc(c) + '</span>' + marks(z) + (gr ? '<u style="color:' + GRP_C[gr][0] + ';border-color:' + GRP_C[gr][0] + '">' + GRP_C[gr][1] + '</u>' : '') + '</a>';
    }).join('') + '</div>';
    var legend = '<div class="cleg">' + Object.keys(CASE_C).map(function (k) { return '<b><i style="background:' + CASE_C[k][0] + '"></i>' + CASE_C[k][1] + '</b>'; }).join('') + '<s></s><b><em class="ld">★</em>лидер</b><b><em class="ht">●</em>горячая</b><b><em class="nw">✦</em>новая</b><b><em class="my">◆</em>твоя</b></div>';
    var coins = '<div class="coins"><div class="cbtn"><i></i>монеты <b>' + NAMES.length + '</b></div><div class="clist"><div class="ch">монеты журнала · по алфавиту · цвет — кейс, метка — группа книги</div><div class="cols">' + cols + '</div>' + legend + '</div></div>';
    var cs = clockState(), clock = cs ? vessel(cs) : '';
    var aura = '<div class="aura up' + (cs && cs.kind === 'up' ? (cs.live ? ' on' : cs.soon ? ' soon' : '') : '') + '"></div><div class="aura dn' + (cs && cs.kind === 'dn' ? (cs.live ? ' on' : cs.soon ? ' soon' : '') : '') + '"></div>';
    stage.innerHTML = '<div class="beam"></div><div class="floor"></div>' + aura + '<div class="slab"><svg viewBox="0 0 ' + SW + ' ' + SH + '">' + slab + '</svg></div><svg class="leaders" viewBox="0 0 1440 900">' + leaders + '</svg>' +
      hd + hdr + '<a class="back" href="brief.html">← схема</a>' + coins + notes + dzone + clock + '<div class="replay" id="replay">заново</div><div class="legend">' + (ser.length > 2 ? 'цена · ' + days + ' дневок' + (d0 ? ' · архив' : ' · звезда') : 'ряда цены нет') + ' · наведи на пометку — полная группа</div>' +
      '<div class="atmo"><div class="vig"></div><svg><filter id="grain" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".8" numOctaves="2" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/></filter><rect width="100%" height="100%" filter="url(#grain)"/></svg></div>';
    root.getElementById('replay').onclick = function () { build(tick); };
    fit();
  }
  function fit() { var W = root.host.ownerDocument.documentElement.clientWidth || window.innerWidth, H = window.innerHeight; var k = Math.min(W / 1440, H / 900); stage.style.transform = 'translate(-50%,-50%) scale(' + k.toFixed(4) + ')'; }
  function fromHash() { var h = (location.hash || '').replace('#', '').toUpperCase(); return BY[h] ? h : null; }
  function start() {
    var lead = STARS.filter(function (s) { return s.lead; })[0];
    build(fromHash() || (lead && String(lead.t).toUpperCase()) || NAMES[0]);
  }
  window.addEventListener('hashchange', function () { var h = fromHash(); if (h) build(h); });
  window.addEventListener('resize', fit);
  // часы живут: пересчёт раз в минуту — состояние сосуда и сияние
  setInterval(function () { var cs = clockState(); if (!cs) return; var box = root.querySelector('.clockbox'); if (box) box.outerHTML = vessel(cs);
    var up = root.querySelector('.aura.up'), dn = root.querySelector('.aura.dn'); if (up && dn) { up.className = 'aura up' + (cs.kind === 'up' ? (cs.live ? ' on' : cs.soon ? ' soon' : '') : ''); dn.className = 'aura dn' + (cs.kind === 'dn' ? (cs.live ? ' on' : cs.soon ? ' soon' : '') : ''); } }, 60000);
  if (STARS.length) start(); else stage.innerHTML = '<div class="empty">звёзд в сводке нет</div>';
})();
</script>
"""
