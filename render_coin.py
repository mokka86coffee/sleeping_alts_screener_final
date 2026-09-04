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
from datetime import datetime, timezone
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


# развязка ПРОТИВ прогноза — те же корни имён, что у render_journal
MISS_WORDS = ("осечка", "ушёл", "отпустил", "раздача")


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
            sw, prev, last, marks = 0, None, None, []
            for i, q in enumerate(pts):
                if prev is not None and q["tpl"] != prev:
                    sw += 1
                    last = {"tpl": q["tpl"].split("(")[0].strip()[:40],
                            "at": q["t"].strftime("%d.%m %H:%M"), "px": q["px"],
                            "chg": round((q["px"] / pts[i - 1]["px"] - 1) * 100, 1)}
                    # МЕТКИ ПРОГНОЗА на плите (04.09): каждая смена — где и что
                    # за событие, тем же рядом, что у журнала прогнозов.
                    marks.append({"t": q["t"].strftime("%Y-%m-%dT%H:%M"), "px": q["px"],
                                  "tpl": last["tpl"],
                                  "miss": any(w in q["tpl"].lower() for w in MISS_WORDS)})
                prev = q["tpl"]
            if not marks and pts[0]["tpl"]:      # смен нет — показываем стартовое состояние
                marks.append({"t": pts[0]["t"].strftime("%Y-%m-%dT%H:%M"), "px": pts[0]["px"],
                              "tpl": pts[0]["tpl"].split("(")[0].strip()[:40],
                              "miss": any(w in pts[0]["tpl"].lower() for w in MISS_WORDS)})
            out[sym] = {"n": len(pts), "switches": sw, "first": pts[0]["px"],
                        "firstAt": pts[0]["t"].strftime("%d.%m %H:%M"),
                        "lastSwitch": last, "marks": marks}
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
                    rec = {"c": [round(float(r["close"]), 8) for r in rows],
                           "d0": rows[0]["datetime"][:10],
                           "d1": rows[-1]["datetime"][:10]}
                    # ПАТТЕРНЫ ДНЕВОК (03.09, разбор UNI/BULLA): цикл плеча,
                    # «продавцы давят — цена держится», шорты как топливо.
                    # Ряды на две недели, читаются на экране, скор не трогают.
                    oi = sorted((r for r in d.get("oi") or [] if r.get("open_interest")),
                                key=lambda r: r["datetime"])[-14:]
                    tr = sorted((r for r in d.get("trade") or [] if r.get("buy_sell_ratio")),
                                key=lambda r: r["datetime"])[-14:]
                    lq = sorted((r for r in d.get("liq") or []), key=lambda r: r["datetime"])[-3:]
                    vol = [float(r.get("quote_volume") or 0) for r in rows]
                    rec["oi"] = [round(float(r["open_interest"]) / 1e6, 2) for r in oi]
                    rec["tk"] = [round(float(r["buy_sell_ratio"]), 3) for r in tr]
                    rec["v"] = [round(v / 1e6, 3) for v in vol[-14:]]
                    rec["vmed"] = round(sorted(vol[-60:-7])[len(vol[-60:-7]) // 2] / 1e6, 3) if len(vol) > 60 else None
                    fu = sorted((r for r in d.get("funding") or [] if r.get("funding_rate") is not None),
                                key=lambda r: r["datetime"])
                    if fu:
                        rec["fundNow"] = float(fu[-1]["funding_rate"])   # у кванта уже в процентах
                    if lq:
                        rec["liq"] = [[r["datetime"][5:10], round(float(r.get("long_liquidations_usd") or 0) / 1e6, 2),
                                       round(float(r.get("short_liquidations_usd") or 0) / 1e6, 2)] for r in lq]
                    out[t.upper()] = rec
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


def _pulse_stamp():
    """Последняя точка пульса: pulse.json — словарь тикер → список точек;
    имя поля времени в точке не фиксировано, пробуем привычные; нет
    поля — берём время файла."""
    for p in (Path("pulse.json"), Path(__file__).resolve().parent / "pulse.json",
              Path("output") / "pulse.json"):
        if not p.exists():
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            return None
        best = None
        rows = d.values() if isinstance(d, dict) else [d]
        for v in rows:
            if not isinstance(v, list) or not v or not isinstance(v[-1], dict):
                continue
            for k in ("at", "ts", "t", "time", "datetime"):
                x = v[-1].get(k)
                if isinstance(x, (int, float)):
                    x = datetime.fromtimestamp(x / (1000 if x > 1e12 else 1), tz=timezone.utc).isoformat()
                if isinstance(x, str) and (best is None or x > best):
                    best = x
                    break
        return best or datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat()
    return None


def _quant_stamp():
    """Свежесть архива кванта: cq_v2/_summary.json (full_at — час полного
    обхода), иначе самый свежий файл архива по mtime."""
    for base in (Path("cq_v2"), Path(__file__).resolve().parent / "cq_v2"):
        if not base.exists():
            continue
        sm = base / "_summary.json"
        if sm.exists():
            try:
                d = json.loads(sm.read_text(encoding="utf-8"))
                for k in ("full_at", "at", "updated"):
                    if d.get(k):
                        return str(d[k])
            except ValueError:
                pass
        files = [f for f in base.glob("*.json") if not f.name.startswith("_")]
        if files:
            return datetime.fromtimestamp(max(f.stat().st_mtime for f in files), tz=timezone.utc).isoformat()
    return None


def source_stamps(stars: list[dict], market: dict) -> dict:
    """ВОЗРАСТ ИСТОЧНИКОВ (03.09, правило владельца: «всё подсвечивать
    всегда — лучше знать, что нет информации, чем неточная»). Штампы
    каждого источника уходят на экран; экран сам считает возраст и
    красит: квант — сутки, остальное — час; старше — красный."""
    whales = _read_json("whales.json") or {}
    sched = _read_json("schedule.json") or {}
    return {"run": market.get("ts"),
            "coinglass": max((str((st.get("cg") or {}).get("at") or "") for st in stars), default="") or None,
            "quant": _quant_stamp(),
            "pulse": _pulse_stamp(),
            "whales": whales.get("at"),
            "crowd": (_read_json("coinglass_crowd.json") or {}).get("at"),
            "unlocks": (_read_json("coinglass_unlocks.json") or {}).get("at"),
            "sched": sched.get("at"),
            "flow": ((_read_json("flow_watch.json") or {}).get("_meta") or {}).get("at")}


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
                       "crowd": crowd, "flow": flow,
                       "sources": source_stamps(stars, market)},
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
.stage{position:absolute;left:50%;top:100%;width:1440px;height:900px;transform-origin:50% 100%;
  --f-name:Jost,sans-serif;--f-num:Jost,sans-serif;--f-cap:Jost,sans-serif;--f-text:Inter,sans-serif;
  background:radial-gradient(900px 640px at 86% -4%, #1f7a5c 0%, #0f3f31 30%, #062219 55%, #020907 85%),#020907}
.beam{position:absolute;left:900px;top:-80px;width:520px;height:900px;background:linear-gradient(rgba(160,255,214,.22),rgba(160,255,214,0));filter:blur(24px);transform:skewX(-14deg);pointer-events:none;will-change:opacity;animation:beam 9s ease-in-out infinite}
@keyframes beam{0%,100%{opacity:.85;transform:skewX(-14deg)}50%{opacity:1;transform:skewX(-11deg)}}
.floor{position:absolute;left:0;right:0;top:475px;bottom:0;pointer-events:none;
  background:linear-gradient(180deg, rgba(150,225,195,.16) 0, rgba(110,190,160,.13) 5%, rgba(60,140,110,.11) 14%, rgba(20,70,55,.10) 38%, rgba(2,9,7,0) 75%)}
.floor:before{content:"";position:absolute;left:0;right:0;top:-1px;height:2px;background:linear-gradient(90deg,transparent,rgba(190,245,220,.16) 25%,rgba(190,245,220,.16) 75%,transparent);filter:blur(2px)}
.floor:after{content:"";position:absolute;left:0;right:0;top:0;height:90px;background:linear-gradient(180deg,rgba(160,230,200,.10),transparent);filter:blur(14px)}
.slab{position:absolute;left:330px;top:70px;width:860px;height:720px;transform:perspective(1500px) rotateY(16deg);transform-origin:50% 50%;will-change:transform}
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
.srcs{position:absolute;left:100px;top:118px;display:flex;flex-wrap:wrap;gap:4px 10px;max-width:560px;opacity:0;animation:fadein .9s ease .4s forwards}
.src{display:inline-flex;align-items:center;gap:5px;font-family:var(--f-cap);font-size:6.5px;letter-spacing:.2em;text-transform:uppercase;color:#9fd8bf;white-space:nowrap}
.src i{width:5px;height:5px;border-radius:50%;background:#5fe6a8;box-shadow:0 0 6px rgba(95,230,168,.8)}
.src.stale{color:#ff8a70}.src.stale i{background:#ff5a4a;box-shadow:0 0 8px rgba(255,90,74,.9);animation:staleBlink 1.3s ease-in-out infinite}
.src.none{color:#6b7f76}.src.none i{background:transparent;border:1px solid #6b7f76;box-shadow:none}
/* одна метка свежести (04.09) */
.srcs.one{cursor:default;max-width:none}.srcs.one .src{font-size:7.5px;padding:5px 10px 5px 8px;border-radius:9px;border:1px solid rgba(127,232,176,.16);background:rgba(3,18,14,.35)}
.srcs.one .src.stale{border-color:rgba(255,90,74,.5);animation:staleBlink 1.3s ease-in-out infinite}
.srcs.one:hover .card{opacity:1;transform:translate(-50%,-50%)}
.card .r.src-r i{border-radius:50%;transform:none;border:0;width:6px;height:6px;margin-top:6px;background:#5fe6a8;box-shadow:0 0 6px rgba(95,230,168,.8)}
.card .r.src-r.stale i{background:#ff5a4a;box-shadow:0 0 8px rgba(255,90,74,.9)}.card .r.src-r.stale .v{color:#ff9d84}
.card .r.src-r.none i{background:transparent;border:1px solid #6b7f76;box-shadow:none}.card .r.src-r.none .v{color:#8fa79c}
.stalebar{position:absolute;left:0;top:0;width:100%;height:3px;background:linear-gradient(90deg,transparent,#ff5a4a,transparent);box-shadow:0 0 18px rgba(255,90,74,.8);animation:staleBlink 1.3s ease-in-out infinite;pointer-events:none}
@keyframes staleBlink{0%,100%{opacity:1}50%{opacity:.3}}
.card .card-src{position:static;margin:-4px 0 8px;opacity:1;animation:none;max-width:none}
.note .num.stale{color:#ff9f8a}.note .num u{display:inline-block;width:6px;height:6px;border-radius:50%;background:#ff5a4a;margin-left:8px;vertical-align:middle;box-shadow:0 0 8px rgba(255,90,74,.9);animation:staleBlink 1.3s ease-in-out infinite}
.note .sub.stale{color:#ff8a70;opacity:1}
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
/* ПЯТНА НА ПОЛУ (04.09): вернул как HTML-слои с CSS-размытием — это слой на видеокарте,
   а не SVG-фильтр внутри повёрнутой плиты, и стоит в разы дешевле */
.pool{position:absolute;border-radius:50%;pointer-events:none;will-change:transform;transform:translateZ(0)}
.pool.g1{left:360px;top:515px;width:820px;height:120px;background:radial-gradient(#f5a93a,rgba(245,169,58,0) 70%);opacity:.42;filter:blur(30px)}
.pool.g2{left:470px;top:560px;width:600px;height:150px;background:radial-gradient(#e0891f,rgba(224,137,31,0) 70%);opacity:.28;filter:blur(36px)}
.pool.t{left:520px;top:590px;width:700px;height:160px;background:radial-gradient(#2ec98d,rgba(46,201,141,0) 70%);opacity:.22;filter:blur(40px)}
/* ЛЁГКИЕ АНИМАЦИИ (04.09): только position:absolute + transform/opacity, без фильтров и без SVG —
   пылинки всплывают, световая полоса раз в 16 с проходит по сцене, две искры у оси дышат */
.dustbox{position:absolute;inset:0;pointer-events:none;animation:dustgate 24s linear infinite}
/* волнами: ~6 с видны, ~1 с гаснут, ~7 с пусто, ~1 с возвращаются */
@keyframes dustgate{0%,71%{opacity:1}75%,96%{opacity:0}100%{opacity:1}}
.dust{position:absolute;width:5px;height:5px;border-radius:50%;background:radial-gradient(#fff,#bfffe0 40%,rgba(191,255,224,0) 72%);box-shadow:0 0 6px rgba(191,255,224,.6);opacity:0;pointer-events:none;will-change:transform,opacity;animation:dust var(--d,14s) linear var(--w,0s) infinite}
.dust.g{background:radial-gradient(#fff,#ffd98a 40%,rgba(255,217,138,0) 72%);box-shadow:0 0 6px rgba(245,169,58,.6)}
@keyframes dust{0%{transform:translate3d(0,0,0) scale(.5);opacity:0}10%{opacity:.95}55%{opacity:.7}100%{transform:translate3d(var(--x,20px),-340px,0) scale(1.2);opacity:0}}
.sweep{position:absolute;left:670px;top:-40px;width:320px;height:760px;pointer-events:none;will-change:transform;transform-origin:50% 0;
  background:linear-gradient(180deg,rgba(191,255,224,.22) 0%,rgba(191,255,224,.12) 40%,rgba(255,217,138,.08) 75%,rgba(255,217,138,0) 100%);
  clip-path:polygon(47.4% 0,52.6% 0,100% 100%,0 100%);animation:sweep 9s ease-in-out infinite alternate}
@keyframes sweep{0%{transform:rotate(-16deg)}100%{transform:rotate(16deg)}}
.spark{position:absolute;width:9px;height:9px;border-radius:50%;background:#ffd98a;box-shadow:0 0 14px 5px rgba(245,169,58,.55);pointer-events:none;will-change:transform,opacity;animation:spark 3.6s ease-in-out infinite}
.spark.b{background:#bfffe0;box-shadow:0 0 10px 3px rgba(127,240,184,.4);animation-delay:1.8s}
@keyframes spark{0%,100%{transform:scale(.6);opacity:.3}50%{transform:scale(1.4);opacity:1}}

/* плашка решения слева внизу (04.09) */
/* ── ТРИ МИНИ-ПЛИТЫ ВНИЗУ (04.09, финал): вердикт, журнал за две недели, расписание —
   уменьшенные копии большой плиты: тот же разворот в перспективе, белая линия земли,
   золотое свечение под ней, отражение. Без кубов и панелей. ── */
.mini{position:absolute;bottom:64px;width:320px;height:180px;transform:perspective(900px) rotateX(var(--px)) rotateY(var(--py)) rotateZ(var(--pz)) scale(var(--sc,1));transform-origin:50% 100%;opacity:0;animation:fadein 1.2s ease 3s forwards;--c:#ffd98a;--g:245,169,58}
/* углы — те, что владелец подобрал на стенде (04.09): ось у нижней кромки */
.mini.verdict{left:520px}
.mini.journal{right:80px;--px:-20deg;--py:-18deg;--pz:0deg;bottom:114px;--sc:.91}   /* стенд 05.09 */   /* дальше от зрителя на 50 */
.mini.sched{left:60px;--px:-15deg;--py:11deg;--pz:-2deg;bottom:214px;width:288px;--sc:.82}   /* стенд 05.09 */      /* дальше на 100 */
.mini .ground{position:absolute;left:0;right:0;bottom:30px;height:1px;background:#fff6dc;opacity:.55}
.mini .gglow{position:absolute;left:-10%;right:-10%;bottom:6px;height:44px;border-radius:50%;background:radial-gradient(rgba(var(--g),.55),rgba(var(--g),0) 70%);filter:blur(12px);pointer-events:none}
.mini .refl{position:absolute;left:0;right:0;top:calc(100% - 30px);height:60px;transform:scaleY(-1);transform-origin:50% 0;opacity:.28;-webkit-mask-image:linear-gradient(#000,transparent);mask-image:linear-gradient(#000,transparent);pointer-events:none}
.mini svg{position:absolute;left:0;top:0;width:100%;height:100%;overflow:visible}
.mini .ax{font-family:var(--f-cap);font-size:6.5px;letter-spacing:.14em;fill:rgba(255,255,255,.45)}
.mini .fc{font-family:var(--f-num);font-weight:500;font-size:8px;letter-spacing:.14em;text-transform:uppercase;fill:#ffe2a8}.mini .fc.miss{fill:#ffa892}
.mini .ln{stroke-dasharray:var(--L);stroke-dashoffset:var(--L);animation:draw 2.2s cubic-bezier(.5,0,.3,1) 3.4s forwards}
.mini .ring{transform-box:fill-box;transform-origin:center;animation:ringp 3s ease-in-out infinite}@keyframes ringp{0%,100%{transform:scale(1);opacity:.5}50%{transform:scale(1.35);opacity:1}}
.mini .nowp{transform-box:fill-box;transform-origin:center;animation:nowp 2.4s ease-in-out infinite}@keyframes nowp{0%,100%{transform:scale(1);opacity:.7}50%{transform:scale(1.6);opacity:1}}
.mini .seg{animation:seg 3.2s ease-in-out infinite alternate}@keyframes seg{0%{opacity:.6}100%{opacity:1}}
/* ВЕРДИКТ (05.09, по референсу): слева синий светящийся куб, над ним в свете висит решение,
   справа тёмный матовый блок, на его грани — «за» и «против». Настоящие ящики из граней. */
.mini.verdict{width:420px;height:230px;transform:none;--px:0deg;--py:0deg;--pz:0deg}
.mini.verdict .ground,.mini.verdict .gglow{display:none}
.vb .box{position:absolute;transform-style:preserve-3d;transform-origin:50% 100% 0;transform:perspective(900px) rotateX(var(--bx,-12deg)) rotateY(var(--by,14deg))}
.vb .f{position:absolute;left:0;top:0}
.vb .f.front{width:var(--W);height:var(--H);transform:translateZ(var(--D))}
.vb .f.back{width:var(--W);height:var(--H);transform:rotateY(180deg)}
.vb .f.left{width:var(--D);height:var(--H);transform:rotateY(-90deg);transform-origin:0 0}
.vb .f.right{width:var(--D);height:var(--H);transform:translateX(var(--W)) rotateY(-90deg);transform-origin:0 0}
.vb .f.top{width:var(--W);height:var(--D);transform:rotateX(90deg);transform-origin:0 0}
.vb .f.bottom{width:var(--W);height:var(--D);transform:translateY(var(--H)) rotateX(90deg);transform-origin:0 0}
/* синий куб */
.vb .blue{--W:72px;--H:72px;--D:72px;--bx:-12deg;--by:18deg;left:34px;bottom:0;width:var(--W);height:var(--H)}
.vb .blue .f{border:1px solid rgba(140,185,255,.8);box-shadow:inset 0 0 18px rgba(60,120,255,.7);background-image:linear-gradient(rgba(200,225,255,.35) 1px,transparent 1px),linear-gradient(90deg,rgba(200,225,255,.35) 1px,transparent 1px),linear-gradient(135deg,rgba(40,95,235,.9),rgba(18,55,190,.85) 60%,rgba(8,26,120,.95));background-size:20% 20%,20% 20%,100% 100%}
.vb .blue .f.top{box-shadow:inset 0 0 26px rgba(150,200,255,.95);background-image:linear-gradient(rgba(220,240,255,.45) 1px,transparent 1px),linear-gradient(90deg,rgba(220,240,255,.45) 1px,transparent 1px),linear-gradient(180deg,rgba(120,180,255,.95),rgba(40,95,235,.9));background-size:20% 20%,20% 20%,100% 100%}
.vb .blue .f.left,.vb .blue .f.right{filter:brightness(.7)}
/* светлый вариант куба (как в первом эскизе по референсу) */
.vb.light .blue .f{border:1px solid rgba(190,220,255,.7);box-shadow:inset 0 0 18px rgba(150,200,255,.7);background-image:linear-gradient(rgba(255,255,255,.28) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.28) 1px,transparent 1px),linear-gradient(135deg,rgba(120,170,255,.55),rgba(40,90,220,.35) 60%,rgba(20,50,160,.5));background-size:33.3% 33.3%,33.3% 33.3%,100% 100%}
.vb.light .blue .f.top{box-shadow:inset 0 0 26px rgba(220,240,255,.9);background-image:linear-gradient(rgba(255,255,255,.35) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.35) 1px,transparent 1px),linear-gradient(180deg,rgba(220,240,255,.7),rgba(120,170,255,.5));background-size:33.3% 33.3%,33.3% 33.3%,100% 100%}
.vb.light .blue .f.left,.vb.light .blue .f.right{filter:none}
.vb .bglow{position:absolute;left:20px;bottom:-14px;width:140px;height:40px;border-radius:50%;background:radial-gradient(#4f8cff,rgba(60,120,255,0) 70%);filter:blur(14px)}
.vb .bglow2{position:absolute;left:-10px;bottom:30px;width:200px;height:200px;border-radius:50%;background:radial-gradient(rgba(80,140,255,.34),rgba(80,140,255,0) 65%);filter:blur(22px);pointer-events:none}
.vb .ray{position:absolute;bottom:0;width:1px;height:200px;background:linear-gradient(0deg,rgba(190,220,255,.6),rgba(190,220,255,0));animation:vray var(--rd,6s) ease-in-out var(--rw,0s) infinite alternate;transform-origin:50% 100%}
.vb .ray::after{content:"";position:absolute;left:-1.5px;top:0;width:3px;height:3px;border-radius:50%;background:#fff;box-shadow:0 0 6px #bfe0ff}
@keyframes vray{0%{transform:scaleY(.5);opacity:.3}100%{transform:scaleY(1);opacity:.9}}
.vb .vtxt{position:absolute;left:-40px;bottom:70px;width:220px;text-align:center}
.vb .vtxt .vcap{font-family:var(--f-cap);font-size:7px;letter-spacing:.34em;text-transform:uppercase;color:#bfe0ff;opacity:.8}
.vb .vtxt .vw{font-family:var(--f-num);font-weight:300;font-size:30px;letter-spacing:.24em;color:#eaf4ff;text-shadow:0 0 12px rgba(150,200,255,.9),0 0 34px rgba(120,170,255,.6);margin:4px 0 2px;line-height:1.1}
.vb .vtxt .vwhy{font-family:var(--f-cap);font-size:7px;letter-spacing:.22em;text-transform:uppercase;color:#bfe0ff}
/* серый блок */
.vb .grey{--W:230px;--H:145px;--D:110px;--bx:-8deg;--by:-14deg;left:190px;bottom:0;width:var(--W);height:var(--H)}
.vb .grey .f.front{transform-style:preserve-3d}.vb .grey .txt{transform:translateZ(1px)}   /* строго в плоскости грани — строки параллельны её верхней кромке */   /* текст лежит в плоскости грани */
.vb .grey .f{background:#0d1110;border:1px solid rgba(255,255,255,.05)}
.vb .grey .f.front{background:linear-gradient(180deg,#171c1b,#0a0d0c);box-shadow:inset 0 0 50px rgba(0,0,0,.75)}
.vb .grey .f.top{background:linear-gradient(180deg,#1f2523,#121615)}
.vb .grey .f.left{background:linear-gradient(90deg,#060807,#111514)}.vb .grey .f.right{background:linear-gradient(270deg,#060807,#111514)}
.vb .grey .f.back,.vb .grey .f.bottom{background:#080b0a}
.vb .grey .txt{position:absolute;inset:0;padding:18px 16px;display:grid;grid-template-columns:42px 1fr;gap:10px 8px;align-content:center}
/* гравировка: одна фактура у всех строк — цвет чуть темнее грани, тонкая светлая кромка снизу и тень сверху */
.vb .grey .txt b,.vb .grey .txt span{color:#5c6763;text-shadow:0 1px 0 rgba(255,255,255,.22),0 -1px 0 rgba(0,0,0,.95),0 0 6px rgba(0,0,0,.6)}
.vb .grey .txt b{font-family:var(--f-cap);font-weight:500;font-size:7px;letter-spacing:.3em;text-transform:uppercase;padding-top:2px}
.vb .grey .txt span{font-family:var(--f-cap);font-size:8.5px;line-height:1.55;letter-spacing:.02em}   /* моно, вариант 1 (05.09) */
.vb .grey .txt .con{color:#6b5f59;text-shadow:0 1px 0 rgba(255,225,205,.2),0 -1px 0 rgba(0,0,0,.95),0 0 6px rgba(0,0,0,.6)}
.vb .gshadow{position:absolute;left:170px;bottom:-10px;width:280px;height:24px;border-radius:50%;background:radial-gradient(rgba(0,0,0,.8),rgba(0,0,0,0) 70%)}
.mini.verdict.v-buy{--c:#ffd98a;--g:245,169,58}.mini.verdict.v-hold{--c:#fbe9c4;--g:251,233,196}.mini.verdict.v-wait{--c:#a8f0dc;--g:79,209,168}.mini.verdict.v-exit{--c:#ffc4b3;--g:255,138,112}
.decbox{left:56px;bottom:56px;width:330px;padding:0;background:none;border:0;box-shadow:none;z-index:4}
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
.clockbox{position:absolute}
.cvessel{position:relative;width:100px;height:140px;display:flex;flex-direction:column;align-items:center;justify-content:flex-end}
.cvessel svg{width:100px;height:100px;display:block;overflow:visible}
.cvessel.dial{height:150px;justify-content:center}.cvessel.dial svg{width:150px;height:150px}
.ctop{text-align:center;margin-bottom:2px;line-height:1;white-space:nowrap}
.ctop b{display:block;font-family:var(--f-num);font-weight:200;font-size:18px;letter-spacing:.06em;text-shadow:0 0 14px rgba(255,255,255,.25)}
.ctop span{display:block;margin-top:4px;font-family:var(--f-cap);font-size:6.5px;letter-spacing:.3em;text-transform:uppercase;color:#bfe9d6}
.ctxt{margin-bottom:34px;display:flex;flex-direction:column;gap:6px;font-family:var(--f-cap);font-size:8px;letter-spacing:.16em;text-transform:uppercase}
.ctxt .k{color:#7fb8a0;margin-right:8px}.ctxt b{font-weight:400;color:#e8fff4}
.w1{animation:wave 9s linear infinite}.w2{animation:wave 14s linear infinite reverse}@keyframes wave{to{transform:translateX(-92px)}}
.breath{animation:breath 2.4s ease-in-out infinite;transform-box:fill-box;transform-origin:center}
@keyframes breath{0%,100%{opacity:.25;transform:scale(.8)}50%{opacity:.9;transform:scale(1.25)}}
.aura{position:absolute;left:250px;width:960px;top:-40px;height:340px;border-radius:50%;filter:blur(28px);opacity:0;transition:opacity 1.2s;pointer-events:none;transform-origin:50% 65%}
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
.tw{opacity:.6}
.ring{transform-box:fill-box;transform-origin:center;animation:ring 2.2s ease-out 3;animation-fill-mode:forwards}@keyframes ring{0%{transform:scale(.6);opacity:.9}100%{transform:scale(3.2);opacity:0}}
.replay{position:absolute;left:100px;bottom:22px;font-family:var(--f-cap);font-size:7.5px;letter-spacing:.24em;text-transform:uppercase;color:#7fb8a0;cursor:pointer;border:1px solid rgba(127,232,176,.25);border-radius:14px;padding:5px 12px;z-index:5}
.replay:hover{color:#dfffee;border-color:rgba(127,232,176,.5)}
.legend{position:absolute;right:270px;bottom:22px;font-family:var(--f-cap);font-size:7px;letter-spacing:.22em;color:#5e8f7a}
.atmo{position:absolute;inset:0;pointer-events:none}
.atmo .vig{position:absolute;inset:0;background:radial-gradient(ellipse 70% 60% at 50% 45%, transparent 45%, rgba(0,0,0,.55) 100%)}
.atmo svg{position:absolute;inset:0;width:100%;height:100%;opacity:.07;mix-blend-mode:overlay}
.empty{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);text-align:center;font-family:var(--f-cap);font-size:9px;letter-spacing:.3em;text-transform:uppercase;color:#7fb8a0}
@media (prefers-reduced-motion:reduce){*{animation:none !important;transition:none !important}.an,.hd,.hdr,.coins,.clockbox,.back{opacity:1}.ln,.ld{stroke-dashoffset:0}}
/* ── ПРОГНОЗ ЖУРНАЛА на плите (04.09): подпись на 20% крупнее обычной, свечение, подчёркивание светом ── */
.fc text{font-family:Jost,Inter,sans-serif;font-weight:500;font-size:12px;letter-spacing:.2em;text-transform:uppercase}
.fc.now text{fill:#ffe2a8;paint-order:stroke;stroke:rgba(3,17,12,.85);stroke-width:2.5px;stroke-linejoin:round}
.fc.past text{fill:#bfe9d6;font-weight:400;paint-order:stroke;stroke:rgba(3,17,12,.8);stroke-width:2px;stroke-linejoin:round}
.fc.miss text{fill:#ffa892;paint-order:stroke;stroke:rgba(3,17,12,.85);stroke-width:2.5px;stroke-linejoin:round}
.fc .u{stroke-width:.8;stroke-linecap:round;opacity:.8}.fc.now .u{stroke:url(#fcu1)}.fc.past .u{stroke:url(#fcu2)}.fc.miss .u{stroke:url(#fcu3)}
.fc .st{stroke-dasharray:2 5}
@keyframes fcglint{0%,100%{opacity:1}50%{opacity:.78}}
@keyframes fcflow{to{stroke-dashoffset:-70}}
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

  // ── ВОЗРАСТ ИСТОЧНИКОВ: считается на месте, от часов зрителя; квант — сутки, остальное — час ──
  var SRC = D.sources || {};
  var SRC_LIST = [['прогон', 'run', 1], ['Coinglass', 'coinglass', 1], ['квант', 'quant', 24], ['пульс', 'pulse', 1], ['киты', 'whales', 1], ['толпа', 'crowd', 24], ['разлоки', 'unlocks', 24], ['расписание', 'sched', 48], ['поток', 'flow', 1]];
  function ageH(ts) { if (!ts) return null; var t = Date.parse(String(ts).length === 10 ? ts + 'T23:59:00Z' : ts); return isNaN(t) ? null : (Date.now() - t) / 36e5; }
  function ageTxt(h) { return h === null ? 'нет данных' : h < 1 ? Math.round(h * 60) + ' мин' : h < 48 ? Math.round(h) + ' ч' : Math.round(h / 24) + ' дн'; }
  function badge(label, ts, maxH) { var h = ageH(ts), cls = h === null ? 'none' : h > maxH ? 'stale' : 'fresh'; return '<span class="src ' + cls + '" title="' + esc(label) + ': ' + esc(ts || 'нет данных') + ' · порог ' + maxH + ' ч"><i></i>' + esc(label) + ' ' + ageTxt(h) + '</span>'; }
  // ОДНА метка свежести (04.09): зелёная — все источники в сроке, красная —
  // хоть один протух или пуст. При наведении — та же карточка, что у групп:
  // построчно кто свеж, кто нет. Если красная — сверху экрана пульсирует
  // красная кромка, и сама метка мигает.
  function srcLine() {
    var rows = SRC_LIST.map(function (q) { var h = ageH(SRC[q[1]]), st = h === null ? 'none' : h > q[2] ? 'stale' : 'fresh'; return { label: q[0], ts: SRC[q[1]], h: h, max: q[2], st: st }; });
    var bad = rows.filter(function (r) { return r.st !== 'fresh'; }), ok = rows.length - bad.length, all = !bad.length;
    var card = '<div class="card"><div class="head"><span class="cap">данные</span><span class="hn">' + (all ? 'всё обновлено' : bad.length + ' из ' + rows.length + ' не в сроке') + '</span></div>' +
      rows.map(function (r) { return '<div class="r src-r ' + r.st + '"><i></i><span class="k">' + esc(r.label) + '</span><span class="v">' + (r.st === 'none' ? 'нет данных' : ageTxt(r.h) + ' назад · порог ' + r.max + ' ч') + (r.st === 'stale' ? ' <b>протух</b>' : r.st === 'none' ? ' <b>пусто</b>' : '') + '</span></div>'; }).join('') + '</div>';
    return (all ? '' : '<div class="stalebar"></div>') + '<div class="srcs one"><span class="src ' + (all ? 'fresh' : 'stale') + '"><i></i>' + (all ? 'всё обновлено · ' + ok + ' из ' + rows.length : 'не обновлено · ' + bad.map(function (r) { return r.label; }).join(', ')) + '</span>' + card + '</div>';
  }
  function stale(ts, maxH) { var h = ageH(ts); return h === null || h > maxH; }

  // ── ПАТТЕРНЫ ДНЕВОК (03.09, разбор UNI/BULLA) — чтения, не скор ──
  //  цикл плеча: «разгрузили и залили заново» (BULLA: −46% и +74% за два дня перед выстрелом)
  //              или «копится N дней подряд» (UNI: +80% за неделю лестницей);
  //  продавцы давят, цена держится: тейкер ниже 0.97 в N днях из 7, а закрытие не ниже недельной давности;
  //  шорты — топливо: толпа в лонге меньше 45% или фандинг в минусе; в день хода горят шорты.
  function patterns(H, cw) {
    var out = {};
    var oi = H.oi || [], tk = H.tk || [], c = H.c || [], v = H.v || [];
    if (oi.length >= 7) {
      var last = oi[oi.length - 1], win = oi.slice(-8);
      var mn = Math.min.apply(null, win), imn = win.indexOf(mn), mxBefore = Math.max.apply(null, win.slice(0, imn + 1));
      var ups = 0; for (var i = 1; i < win.length; i++) if (win[i] > win[i - 1]) ups++;
      if (mxBefore > 0 && mn / mxBefore <= .7 && last / mn >= 1.5) {
        out.leverKind = 'reload'; out.leverShort = 'плечо залили заново';
        out.lever = 'разгрузили на ' + Math.round((1 - mn / mxBefore) * 100) + '% и залили ×' + (last / mn).toFixed(1) + ' за ' + (win.length - 1 - imn) + ' дн — цикл разгрузка→залив, как у BULLA перед выстрелом';
      } else if (win[0] > 0 && last / win[0] >= 1.5 && ups >= 5) {
        out.leverKind = 'build'; out.leverShort = 'плечо копится ' + ups + ' дн из 7';
        out.lever = 'плечо ×' + (last / win[0]).toFixed(1) + ' за неделю, рост в ' + ups + ' днях из 7 — накопление лестницей, как у UNI';
      } else if (win[0] > 0 && last / win[0] <= .6) {
        out.leverKind = 'flush'; out.leverShort = 'плечо слито';
        out.lever = 'плечо −' + Math.round((1 - last / win[0]) * 100) + '% за неделю — разгружено, залива пока нет';
      }
    }
    if (tk.length >= 7 && c.length >= 8) {
      var sell = tk.slice(-7).filter(function (x) { return x < .97; }).length, chg7 = (c[c.length - 1] / c[c.length - 8] - 1) * 100;
      if (sell >= 5 && chg7 >= -3) {
        out.absorb = 'продают ' + sell + ' дн из 7 (тейкер ниже 0.97), а цена за неделю ' + (chg7 >= 0 ? '+' : '') + chg7.toFixed(1) + '% — кто-то принимает лимитками';
        out.absorbShort = 'продают ' + sell + ' дн из 7, цена держится';
      }
    }
    var sh = [];
    if (cw && cw.crowd && +cw.crowd.longPct < 45) sh.push('толпа в лонге ' + cw.crowd.longPct + '% — большинство в шорте');
    if (has(H.fundNow) && +H.fundNow < 0) sh.push('фандинг в минусе — платят шорты');
    if (H.liq && H.liq.length) { var L = H.liq[H.liq.length - 1]; if (L[2] > L[1] * 1.5 && L[2] >= .05) sh.push('за ' + L[0] + ' вынесено шортов ' + money(L[2] * 1e6) + ' против лонгов ' + money(L[1] * 1e6)); }
    if (sh.length) { out.short = sh.join(' · '); out.shortShort = sh[0].split(' — ')[0]; }
    if (v.length >= 7 && H.vmed) {
      var x = v.slice(-7).map(function (q) { return q / H.vmed; }), last3 = x.slice(-3), quiet = x.slice(0, 4).filter(function (q) { return q < .8; }).length;
      if (x[x.length - 1] >= 4 && quiet >= 3) out.vol = 'из тишины: ' + quiet + ' дн ниже 0.8 нормы, потом ×' + x[x.length - 1].toFixed(1) + ' — выстрел с пустого места';
      else if (last3[0] >= 2 && last3[1] >= last3[0] * .9 && last3[2] >= last3[1] * .9 && last3[2] >= 3) out.vol = 'ступенями: ×' + last3.map(function (q) { return q.toFixed(1); }).join(' → ×') + ' — оборот растёт третий день';
    }
    return out;
  }

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
    g.price = { src: [['архив', 'quant', 24], ['прогон', 'run', 1]], cap: 'где цена', num: has(s.lifeDrop) ? '−' + Math.round(s.lifeDrop) + '%' : (has(s.up) ? '+' + Math.round(s.up) + '%' : '—'),
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
    var patD = patterns(HIST[String(s.t).toUpperCase()] || {}, CROWD[String(s.t).toUpperCase()]);
    if (patD.absorbShort) pro.push(patD.absorbShort);
    if (patD.shortShort) pro.push(patD.shortShort);
    if (patD.leverShort) (patD.leverKind === 'reload' || patD.leverKind === 'build' ? pro : con).push(patD.leverShort);
    dr.push(['за', pro.length ? pro.join(' · ') : 'нет'], ['против', con.length ? con.join(' · ') : 'нет']);
    g.decision = { src: [['квант', 'quant', 24], ['Coinglass', 'coinglass', 1], ['пульс', 'pulse', 1]], cap: 'решение', num: verdict, verdict: verdict.toUpperCase(), why: why, rows: dr, pro: pro, con: con,
      exit: s.exitWhy || '', hurry: (s.exitDeadline ? 'срок ' + s.exitDeadline : (u && u.days <= 1 ? 'разлок ' + (u.days ? 'завтра' : 'сегодня') : '')) };
    // ПОТОК
    var fr = [];
    if (has(cg.taker)) fr.push(['покупки к продажам', '×' + (+cg.taker).toFixed(2) + (has(cg.cvdChg) ? ' · дельта ' + money(cg.cvdChg) : '')]);
    if (rep.phrase) fr.push(['в стакане · дневка', rep.phrase + (rep.delta_usd ? ' · дельта ' + money(rep.delta_usd) : '')]);
    var pat0 = patterns(HIST[String(s.t).toUpperCase()] || {}, CROWD[String(s.t).toUpperCase()]);
    if (pat0.absorb) fr.push(['продавцы давят', pat0.absorb]);
    if (pat0.vol) fr.push(['оборот по дневкам', pat0.vol]);
    if (has(s.press)) fr.push(['давление', String(s.press) + (has(s.pressShare) ? ' · доля ' + Math.round(+s.pressShare <= 1 ? +s.pressShare * 100 : +s.pressShare) + '%' : '')]);
    if (has(s.v1d)) fr.push(['объём', '×' + (+s.v1d).toFixed(1) + ' к норме' + (has(s.v1h) ? ' · час ×' + (+s.v1h).toFixed(1) : '') + (s.volBg ? ' · фон ' + s.volBg : '')]);
    if (has(cg.spotUsd)) fr.push(['спот', money(cg.spotUsd) + (has(cg.spotTaker) ? ' · тейкер ×' + (+cg.spotTaker).toFixed(2) : '') + (has(cg.fsRatio) ? ' · фьюч к споту ×' + (+cg.fsRatio).toFixed(1) : '')]);
    if (has(s.bigCount) && +s.bigCount > 0) fr.push(['крупные', s.bigCount + ' сделок' + (s.bigBuys !== undefined ? ' · покупок ' + s.bigBuys + ', продаж ' + s.bigSells : '') + (s.bigMax ? ' · крупнейшая ' + money(s.bigMax) : '')]);
    if (s.klinger) fr.push(['клингер', (s.klinger.crossUp ? 'крест вверх у дна' : s.klinger.crossDn ? 'крест вниз' : s.klinger.above ? 'выше сигнала' : 'ниже сигнала')]);
    if (has(s.shakeX)) fr.push(['вынос', '×' + f(s.shakeX) + (s.shakeHours ? ' за ' + s.shakeHours + ' ч' : '') + (has(s.shakeMove) ? ' · ход ' + pct(s.shakeMove) : '')]);
    var flowNum = has(cg.taker) ? '×' + (+cg.taker).toFixed(2) : (has(s.v1d) ? '×' + (+s.v1d).toFixed(1) : '—');
    g.flow = { stale: stale(SRC.coinglass, 1), src: [['Coinglass', 'coinglass', 1], ['квант', 'quant', 24], ['поток', 'flow', 1]], cap: 'поток', num: flowNum, unit: has(cg.taker) ? 'покупки к продажам' : 'объём к норме', sub: rep.phrase ? String(rep.phrase).split(' — ')[0].slice(0, 60) : (has(s.v1d) ? 'объём ×' + (+s.v1d).toFixed(1) + ' к норме' : ''), rows: fr, glyph: 'dia' };
    // ПЛЕЧО
    var lr = [];
    if (has(cg.oiChgPct)) lr.push(['OI за сутки', pct(cg.oiChgPct) + (has(s.fund) ? ' · фандинг ' + (+s.fund).toFixed(4) + '%' : '')]);
    else if (has(s.fund)) lr.push(['фандинг', (+s.fund).toFixed(4) + '%']);
    if (s.oiState) lr.push(['цикл плеча', s.oiState === 'held' ? 'застряло' : s.oiState === 'cleared' ? 'разгружено' : s.oiState === 'repeat' ? 'повторный цикл' : String(s.oiState)]);
    if (s.liqFuel && (s.liqFuel.below || s.liqFuel.above)) lr.push(['в капитализации', (s.liqFuel.below ? 'снизу ' + (+s.liqFuel.below * 100).toFixed(1) + '%' : '') + (s.liqFuel.above ? ' · сверху ' + (+s.liqFuel.above * 100).toFixed(1) + '%' : '') + ' — оценка по модели, не наблюдение']);
    if (s.liq24h && (s.liq24h.long || s.liq24h.short)) lr.push(['ликвидации за сутки', 'лонгов ' + (money(s.liq24h.long) || '$0') + ' против шортов ' + (money(s.liq24h.short) || '$0')]);
    if (s.vxDir) lr.push(['топливо', 'вортекс ' + (s.vxDir === 'up' ? 'вверх' : s.vxDir === 'down' ? 'вниз' : s.vxDir) + (has(s.vxSpread) ? ' · разрыв ' + f(s.vxSpread) : '') + (s.vxAgo ? ' · ' + s.vxAgo + ' ч назад' : '')]);
    var cw = CROWD[String(s.t).toUpperCase()]; if (cw && cw.crowd) lr.push(['толпа', 'в лонге ' + cw.crowd.longPct + '%' + (has(cw.crowd.chg1d) ? ' (за сутки ' + pct(cw.crowd.chg1d) + ')' : '') + (cw.top ? ' · топы ' + cw.top.longPct + '%' : '')]);
    // ПАТТЕРНЫ ДНЕВОК (03.09): цикл плеча по архиву — накопление или «разгрузили и залили заново»
    var Hh = HIST[String(s.t).toUpperCase()] || {};
    var pat = patterns(Hh, cw);
    if (pat.lever) lr.push(['цикл по дневкам', pat.lever]);
    if (pat.short) lr.push(['шорты — топливо', pat.short]);
    var w = WH[String(s.t).toUpperCase()] || WH[String(s.t)];
    if (w) lr.push(['киты Hyperliquid', 'лонг ' + (money(w.long) || '$0') + ' против шорта ' + (money(w.short) || '$0') + (w.n ? ' · позиций ' + w.n : '')]);
    var levNum = has(cg.oiChgPct) ? pct(cg.oiChgPct) : (has(s.fund) ? (+s.fund).toFixed(3) + '%' : '—');
    g.lever = { stale: stale(SRC.coinglass, 1), src: [['Coinglass', 'coinglass', 1], ['толпа', 'crowd', 24], ['киты', 'whales', 1]], cap: 'плечо', num: levNum, unit: has(cg.oiChgPct) ? 'OI за сутки' : 'фандинг', sub: (s.oiState ? (s.oiState === 'held' ? 'застряло' : s.oiState === 'cleared' ? 'разгружено' : 'повторный цикл') : '') + (s.liqFuel && s.liqFuel.below ? ' · ' + (+s.liqFuel.below * 100).toFixed(1) + '% снизу' : '') + (s.liqFuel && s.liqFuel.above ? ' · ' + (+s.liqFuel.above * 100).toFixed(1) + '% сверху' : ''), rows: lr, glyph: 'chev' };
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
    g.memory = { src: [['квант', 'quant', 24], ['пульс', 'pulse', 1]], cap: 'память', num: memNum, unit: has(s.heldRallies) && has(s.rallies) ? 'отскоков устояли' : (j ? 'смен прогноза' : ''), sub: j ? 'журнал: ' + j.n + ' записей · смен ' + j.switches : (has(s.days) ? 'в журнале ' + s.days + ' дн' : ''), rows: mr, glyph: 'plus' };
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
    g.calendar = { src: [['разлоки', 'unlocks', 24], ['прогон', 'run', 1]], cap: 'календарь · фундамент', num: calNum, unit: u ? 'до разлока' : (s.exitDeadline ? 'срок' : ''), sub: u ? u.pct + '% обращения' + (u.ins !== undefined ? ' · инсайдерам ' + u.ins + '%' : '') : (s.news && s.news.t ? s.news.t : ''), rows: cr, glyph: 'arrow', hot: hot };
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
    var sb = (g.src || []).map(function (q) { return badge(q[0], SRC[q[1]], q[2]); }).join('');
    return '<div class="card"><div class="head"><span class="cap">' + esc(g.cap) + '</span><span class="hn">' + esc(g.num) + '</span></div>' + (sb ? '<div class="srcs card-src">' + sb + '</div>' : '') + rows + '</div>';
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
    t += '<g class="an grd"><ellipse cx="' + ((X0 + X1) / 2) + '" cy="' + (Y0 + 9) + '" rx="' + ((X1 - X0) / 2 + 60) + '" ry="10" fill="url(#gpool)" opacity=".5"/>' +
      '<line x1="' + (X0 - 40) + '" y1="' + Y0 + '" x2="' + (X1 + 40) + '" y2="' + Y0 + '" stroke="' + GOLDL + '" stroke-width="7" opacity=".5" filter="url(#blur3)"/>' +
      '<line x1="' + (X0 - 30) + '" y1="' + Y0 + '" x2="' + (X1 + 30) + '" y2="' + Y0 + '" stroke="url(#ground)" stroke-width="4"/>' +
      '<line x1="' + (X0 - 24) + '" y1="' + Y0 + '" x2="' + (X1 + 24) + '" y2="' + Y0 + '" stroke="#fff6dc" stroke-width="1.6" opacity=".95"/></g>';
    var pl = P.map(function (p) { return f(p[0]) + ',' + f(p[1]); }).join(' '), LEN = 0;
    for (i = 1; i < P.length; i++) LEN += Math.hypot(P[i][0] - P[i - 1][0], P[i][1] - P[i - 1][1]);
    [[26, .14, '', '#e0891f'], [12, .22, ' filter="url(#blur6)"', GOLD], [5, .55, '', GOLD], [2.6, .95, '', GOLD], [1.4, 1, '', GOLDL]].forEach(function (q) {
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
    // РАСПИСАНИЕ — мини-плита (04.09): лента суток с окнами роста и слива, метка «сейчас», отсчёт
    var W = 320, H = 180, x0 = 20, x1 = 300, y = 118, now = new Date(), lh = now.getHours() + now.getMinutes() / 60;
    function X(h) { return x0 + (h / 24) * (x1 - x0); }
    function len(sg) { var l = ((sg[1] + 1 - sg[0]) % 24 + 24) % 24; return l || 24; }
    var s = '<rect x="' + x0 + '" y="' + (y - 1.25) + '" width="' + (x1 - x0) + '" height="2.5" rx="1.25" fill="rgba(255,255,255,.10)" stroke="rgba(255,255,255,.45)" stroke-width=".6"/>';
    function seg(sg, col, cls) { var a = nyHourToLocal(sg[0]), l = len(sg), out = '';
      for (var k = 0; k < 2; k++) { var st = a + (k ? -24 : 0), xa = Math.max(x0, X(st)), xb = Math.min(x1, X(st + l)); if (xb > xa) out += '<rect class="' + cls + '" x="' + xa.toFixed(1) + '" y="' + (y - 1.25) + '" width="' + (xb - xa).toFixed(1) + '" height="2.5" rx="1.25" fill="' + col + '"/>'; }
      return out; }
    (SC.pump || []).forEach(function (sg) { s += seg(sg, '#bfffe0', 'seg'); });
    (SC.dump || []).forEach(function (sg) { s += seg(sg, '#ffb59f', ''); });
    for (var h = 0; h <= 24; h += 6) s += '<line x1="' + X(h).toFixed(1) + '" y1="' + (y + 6) + '" x2="' + X(h).toFixed(1) + '" y2="' + (y + 11) + '" stroke="#fff" opacity=".5"/><text class="ax" x="' + X(h).toFixed(1) + '" y="' + (y + 24) + '" text-anchor="middle">' + pad(h % 24) + '</text>';
    s += '<line x1="' + X(lh).toFixed(1) + '" y1="' + (y - 18) + '" x2="' + X(lh).toFixed(1) + '" y2="' + (y + 6) + '" stroke="#fff" stroke-width="1"/><circle class="nowp" cx="' + X(lh).toFixed(1) + '" cy="' + (y - 20) + '" r="3" fill="#fff"/>';
    var inH = Math.floor(cs.dh), inM = Math.round((cs.dh - inH) * 60), col = cs.kind === 'up' ? '#bfffe0' : '#ffb59f';
    var cap = cs.live ? (cs.kind === 'up' ? 'РОСТ ИДЁТ · ЕЩЁ' : 'СЛИВ ИДЁТ · ЕЩЁ') : (cs.kind === 'up' ? 'ДО РОСТА' : 'ДО СЛИВА');
    s += '<text x="' + (W / 2) + '" y="52" text-anchor="middle" font-family="Jost,Inter" font-weight="200" font-size="32" letter-spacing=".06em" fill="' + col + '">' + inH + ':' + pad(inM) + '</text>';
    s += '<text x="' + (W / 2) + '" y="70" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="8" letter-spacing=".26em" fill="rgba(255,255,255,.7)">' + cap + '</text>';
    s += (cs.tUp ? '<text class="fc" x="' + x0 + '" y="' + (y + 40) + '" text-anchor="start" style="fill:#bfffe0;font-size:6.8px">рост ' + cs.tUp + '</text>' : '') +
         (cs.tDn ? '<text class="fc" x="' + x1 + '" y="' + (y + 40) + '" text-anchor="end" style="fill:#ffb59f;font-size:6.8px">слив ' + cs.tDn + '</text>' : '');
    return '<div class="clockbox mini sched" style="--c:#bfffe0;--g:127,240,184"><div class="gglow"></div><svg viewBox="0 0 ' + W + ' ' + H + '">' + s + '</svg><div class="ground"></div></div>';
  }

  // ── СБОРКА ЭКРАНА ОДНОЙ МОНЕТЫ ──
  var GLYPH = { sq: '<rect x="2" y="2" width="12" height="12"/>', dia: '<path d="M8 1 L15 8 L8 15 L1 8 Z"/>', chev: '<path d="M3 4 L8 9 L13 4 M3 9 L8 14 L13 9"/>', plus: '<path d="M8 2 V14 M2 8 H14"/>', arrow: '<path d="M2 8 H13 M9 4 L13 8 L9 12"/>' };
  function build(tick) {
    var s = BY[tick]; if (!s) { stage.innerHTML = '<div class="empty">монета ' + esc(tick) + ' не в журнале</div>'; return; }
    var g = groups(s), rnd = seeded(tick.split('').reduce(function (a, c) { return a + c.charCodeAt(0); }, 7));
    var H = HIST[String(s.t).toUpperCase()], ser, d0 = null, d1 = null;
    // окно плиты — 4 месяца (04.09: было полгода, метки прогноза за двое суток слипались у края)
    var SHOW_DAYS = 120;
    if (H && H.c && H.c.length >= 14) {
      var N = H.c.length, cut = Math.max(0, N - SHOW_DAYS);
      ser = H.c.slice(cut); d0 = H.d0; d1 = H.d1;
      if (cut && d0 && d1) { var _a = new Date(d0).getTime(), _b = new Date(d1).getTime(); d0 = new Date(_a + (_b - _a) * cut / Math.max(1, N - 1)).toISOString().slice(0, 10); }
      if (s.px && ser[ser.length - 1] !== +s.px) ser.push(+s.px);
    }
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
    slab += '<path d="' + sh + '" fill="url(#shadowG)" opacity=".55"/>';
    slab += '<defs><radialGradient id="gpool"><stop offset="0" stop-color="' + GOLD + '" stop-opacity=".55"/><stop offset=".6" stop-color="' + GOLD + '" stop-opacity=".18"/><stop offset="1" stop-color="' + GOLD + '" stop-opacity="0"/></radialGradient></defs>' +
      '' +
      '';
    var sc = scene(P, rnd);
    slab += '<g class="an refl"><g transform="translate(0,' + (2 * Y0) + ') scale(1,-1)" mask="url(#rm)" opacity=".45">' + sc + '</g></g>' + sc;   // ОПТИМИЗАЦИЯ 04.09: отражение без blur
    // уровни справа от блока решения
    var LV = [];
    if (lv.above && lv.above.price) LV.push(['ПЛИТА', +lv.above.price, GOLD]);
    if (s.stop) LV.push(['СТОП', +s.stop, '#9fd8bf']);
    if (lv.below && lv.below.price) LV.push(['ОПОРА', +lv.below.price, MINT]);
    // ПРАВАЯ КОЛОНКА ПОДПИСЕЙ (04.09, разгрузка): плита, стоп, опора и
    // ликвидации сначала складываются в список, потом раздвигаются по
    // вертикали не ближе 12px друг к другу; линия уровня остаётся на
    // своей высоте, к подписи ведёт короткий отвод — так при сгущении
    // уровней у цены подписи не лезут одна на другую и на «сейчас».
    var RL = [];
    LV.forEach(function (l) { RL.push({ y: sy(l[1]), col: l[2], txt: l[0] + ' ' + px4(l[1]), line: true, x1: X0 + 330, dash: '3 5', w: .6, op: .45 }); });
    (s.liqZones || []).slice(0, 3).forEach(function (z) { RL.push({ y: sy((z.lo + z.hi) / 2), col: '#e6d3a3', txt: 'ЛИКВ ' + (money(z.fuel) || ''), liq: true, x1: X0, dash: '6 4', w: .8, op: .55 }); });
    RL.push({ y: ny0 = P[P.length - 1][1], col: '#fff', txt: '', now: true });   // место под «сейчас» тоже занимает строку
    RL.sort(function (a, b) { return a.y - b.y; });
    for (var ri = 1; ri < RL.length; ri++) { RL[ri].ly = Math.max(RL[ri].ly !== undefined ? RL[ri].ly : RL[ri].y, (RL[ri - 1].ly !== undefined ? RL[ri - 1].ly : RL[ri - 1].y) + 12); }
    for (ri = RL.length - 2; ri >= 0; ri--) { var nxt = RL[ri + 1].ly, cur = RL[ri].ly !== undefined ? RL[ri].ly : RL[ri].y; if (cur > nxt - 12) RL[ri].ly = nxt - 12; }
    RL.forEach(function (r) {
      if (r.ly === undefined) r.ly = r.y;
      if (r.now) return;
      var g = '<g class="an lv"' + (r.liq ? ' opacity=".8"' : '') + '>';
      if (r.liq) g += '<line x1="' + r.x1 + '" y1="' + f(r.y) + '" x2="' + (X1 + 30) + '" y2="' + f(r.y) + '" stroke="' + GOLD + '" stroke-width="6" opacity=".12" filter="url(#blur3)"/>';
      g += '<line x1="' + r.x1 + '" y1="' + f(r.y) + '" x2="' + (X1 + 30) + '" y2="' + f(r.y) + '" stroke="' + (r.liq ? '#fff1cc' : r.col) + '" stroke-width="' + r.w + '" opacity="' + r.op + '" stroke-dasharray="' + r.dash + '"/>';
      if (Math.abs(r.ly - r.y) > 1) g += '<polyline points="' + (X1 + 30) + ',' + f(r.y) + ' ' + (X1 + 42) + ',' + f(r.ly) + ' ' + (X1 + 48) + ',' + f(r.ly) + '" fill="none" stroke="' + r.col + '" stroke-width=".6" opacity=".5"/>';
      g += '<text x="' + (X1 + 52) + '" y="' + f(r.ly + 2.5) + '" class="mono" font-size="7" letter-spacing=".16em" fill="' + r.col + '" opacity=".95">' + esc(r.txt) + '</text></g>';
      slab += g;
    });
    var ny0;
    var nx = P[P.length - 1][0], ny = P[P.length - 1][1];
    slab += '<g class="an now"><circle cx="' + f(nx) + '" cy="' + f(ny) + '" r="14" fill="#fff" opacity=".22" filter="url(#blur6)"/><circle cx="' + f(nx) + '" cy="' + f(ny) + '" r="3.2" fill="#fff"/><circle class="ring" cx="' + f(nx) + '" cy="' + f(ny) + '" r="6" fill="none" stroke="#fff" stroke-width="1"/></g>';
    slab += '<g class="an lv2"><text x="' + f(nx - 12) + '" y="' + f(ny - 12) + '" text-anchor="end" font-family="Jost,Inter" font-weight="300" font-size="10" fill="#fff">' + px4(s.px || ser[ser.length - 1]) + ' <tspan fill="#bfe9d6">сейчас</tspan></text>';
    // РИСКИ ЦЕН на левой оси (04.09): четыре деления между низом и верхом
    // окна, чтобы у графика был масштаб, а не только даты
    (function () {
      var smin = Math.min.apply(null, ser), smax = Math.max.apply(null, ser), ax = X0 - 26;
      for (var ti = 0; ti <= 3; ti++) { var pv = smin + (smax - smin) * ti / 3, yy = sy(pv);
        slab += '<line x1="' + (ax - 4) + '" y1="' + f(yy) + '" x2="' + (ax + 4) + '" y2="' + f(yy) + '" stroke="' + GOLD + '" stroke-width=".8" opacity=".6"/><text x="' + (ax - 8) + '" y="' + f(yy + 2.5) + '" text-anchor="end" class="mono" font-size="7" letter-spacing=".12em" fill="#9fd8bf" opacity=".85">' + px4(pv) + '</text>'; }
    })();
    // ДНО ОКНА и ход от него (04.09, «нет роста от дна»): точка минимума,
    // пунктир к «сейчас», подпись +N% от дна
    (function () {
      var imn = 0; for (var i = 1; i < ser.length; i++) if (ser[i] < ser[imn]) imn = i;
      if (imn === ser.length - 1) return;
      var bx = P[imn][0], by = P[imn][1], up = (ser[ser.length - 1] / ser[imn] - 1) * 100;
      slab += '<g class="an lv2"><circle cx="' + f(bx) + '" cy="' + f(by) + '" r="3" fill="none" stroke="' + MINT + '" stroke-width="1"/>' +
        '<text x="' + f(bx) + '" y="' + f(by + 14) + '" text-anchor="middle" class="mono" font-size="7" letter-spacing=".14em" fill="' + MINT + '" opacity=".9">ДНО ' + px4(ser[imn]) + '</text>' +
        '<line x1="' + f(bx) + '" y1="' + f(by) + '" x2="' + f(nx) + '" y2="' + f(ny) + '" stroke="' + MINT + '" stroke-width=".7" opacity=".45" stroke-dasharray="2 5"/>' +
        '<text x="' + f((bx + nx) / 2) + '" y="' + f((by + ny) / 2 - 6) + '" text-anchor="middle" class="mono" font-size="7.5" letter-spacing=".14em" fill="' + MINT + '">' + (up >= 0 ? '+' : '') + up.toFixed(0) + '% ОТ ДНА</text></g>';
    })();
    [[0, dlab(0)], [Math.floor(days / 2), dlab(Math.floor(days / 2))], [days - 1, 'сегодня']].forEach(function (d) { slab += '<text x="' + f(P[d[0]][0]) + '" y="' + (Y0 + 18) + '" text-anchor="middle" class="mono" font-size="7" letter-spacing=".16em" fill="#7fb8a0">' + d[1] + '</text>'; });
    slab += '<line x1="' + (X0 - 26) + '" y1="' + Y0 + '" x2="' + (X0 - 26) + '" y2="' + (Y1 + 4) + '" stroke="' + GOLD + '" stroke-width=".8" opacity=".5"/><path d="M' + (X0 - 26) + ',' + Y1 + ' l-3.5,6 h7 z" fill="' + GOLD + '" opacity=".6"/></g>';
    // ── ПРОГНОЗ ЖУРНАЛА: точка смены на линии, ножка, подпись с подчёркиванием ──
    // Где и что за событие — те же смены, что на экране журнала. Даты нет:
    // где на плите, там и когда. Подписи ярусами справа налево, наезда нет.
    (function () {
      var J = JR[String(s.t).toUpperCase()], M = J && J.marks;
      if (!M || !M.length) return;
      var t0 = d0 ? new Date(d0).getTime() : null, t1 = d1 ? new Date(d1).getTime() : null;
      slab += '<defs>' +
        '<filter id="fcglow" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur in="SourceGraphic" stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
        '<filter id="fcglow2" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur in="SourceGraphic" stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
        '<filter id="fcglow3" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur in="SourceGraphic" stdDeviation="1.8" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>' +
        '<linearGradient id="fcu1"><stop offset="0" stop-color="#f5a93a" stop-opacity="0"/><stop offset=".6" stop-color="#ffd98a"/><stop offset="1" stop-color="#fff"/></linearGradient>' +
        '<linearGradient id="fcu2"><stop offset="0" stop-color="#7fe8b0" stop-opacity="0"/><stop offset=".6" stop-color="#bfe9d6"/><stop offset="1" stop-color="#fff"/></linearGradient>' +
        '<linearGradient id="fcu3"><stop offset="0" stop-color="#ff5a4a" stop-opacity="0"/><stop offset=".6" stop-color="#ff9d84"/><stop offset="1" stop-color="#fff"/></linearGradient></defs>';
      var last = M.length - 1;
      M.forEach(function (m, k) {
        var tm = new Date(m.t).getTime(), x;
        if (t0 && t1 && t1 > t0) x = X0 + Math.max(0, Math.min(1, (tm - t0) / (t1 - t0))) * (X1 - X0);
        else x = P[P.length - 1][0];
        var y = sy(+m.px), cls = k === last ? 'now' : 'past', col = k === last ? '#ffd98a' : '#bfe9d6';
        if (m.miss) { cls = k === last ? 'now miss' : 'miss'; col = '#ff9d84'; }
        // подписи — вереницей справа налево по верху плиты (последняя смена —
        // самая правая), в два ряда, к каждой — прямая выноска от её точки
        var tier = last - k, w = m.tpl.length * 7.2, ex = X1 + 10 - tier * 170, ty = Y1 + 24 + (tier % 2) * 22;
        if (ex - w < X0) { ex = X0 + w; }
        slab += '<g class="an fc ' + cls + '" style="animation-delay:' + (2.2 + k * .2).toFixed(1) + 's">' +
          '<circle cx="' + f(x) + '" cy="' + f(y) + '" r="' + (k === last ? 12 : 8) + '" fill="' + col + '" opacity=".28" filter="url(#blur6)"/><circle cx="' + f(x) + '" cy="' + f(y) + '" r="2.6" fill="#fff6e4"/>' +
          '<line class="st" x1="' + f(x) + '" y1="' + f(y) + '" x2="' + f(ex - w / 2) + '" y2="' + f(ty + 8) + '" stroke="' + col + '" stroke-width="1" opacity=".55"/>' +
          '<text x="' + f(ex) + '" y="' + f(ty) + '" text-anchor="end">' + esc(m.tpl) + '</text>' +
          '<line class="u" x1="' + f(ex - w) + '" y1="' + f(ty + 6) + '" x2="' + f(ex) + '" y2="' + f(ty + 6) + '"/></g>';
      });
    })();
    // РЕШЕНИЕ — ВНЕ ПЛИТЫ (04.09): плашка ушла с графика влево-вниз, HTML-слоем
    // на сцене; на плите остаётся только линия, уровни и прогноз. Карточка
    // при наведении — та же (dzone).
    var dec = g.decision;
    // россыпь значков
    [[200, 190, 'sq'], [420, 120, 'plus'], [560, 240, 'dia'], [700, 160, 'chev'], [330, 250, 'sq']].forEach(function (d) { var inn = { sq: '<rect x="0" y="0" width="10" height="10"/>', plus: '<path d="M5 0 V10 M0 5 H10"/>', chev: '<path d="M0 2 L5 7 L10 2"/>', dia: '<path d="M5 0 L10 5 L5 10 L0 5 Z"/>' }[d[2]]; slab += '<g fill="none" stroke="' + GOLD + '" stroke-width="1" opacity=".5" transform="translate(' + d[0] + ',' + d[1] + ') scale(1.4)">' + inn + '</g>'; });
    // пометки и выноски
    var imin = 0; for (var i = 1; i < P.length; i++) if (P[i][1] > P[imin][1]) imin = i;
    var imax = 0; for (i = 1; i < P.length; i++) if (P[i][1] < P[imax][1]) imax = i;
    var NOTES = [['lever', 110, 250, P[imax]], ['memory', 700, 28, P[Math.floor(P.length / 2)]], ['flow', 1190, 150, P[Math.max(0, P.length - 3)]], ['price', 700, 600, P[imin]], ['calendar', 1190, 470, P[P.length - 1]]];
    var notes = '', leaders = '';
    NOTES.forEach(function (n, ni) { var G = g[n[0]], pr = project(n[3][0], n[3][1]), lx = n[1] + 8, ly = n[2] + 40, ll = Math.hypot(pr[0] - lx, pr[1] - ly);
      leaders += '<line class="ld" x1="' + lx + '" y1="' + ly + '" x2="' + f(pr[0]) + '" y2="' + f(pr[1]) + '" stroke="' + GOLD + '" stroke-width=".6" opacity=".5" style="--L:' + Math.ceil(ll + 2) + ';animation-delay:' + (2.9 + ni * .15).toFixed(2) + 's"/><circle class="an ldc" cx="' + f(pr[0]) + '" cy="' + f(pr[1]) + '" r="2.6" fill="none" stroke="' + GOLD + '" stroke-width=".8" style="animation-delay:' + (3.3 + ni * .15).toFixed(2) + 's"/>';
      notes += '<div class="note an" style="left:' + n[1] + 'px;top:' + n[2] + 'px;animation-delay:' + (3 + ni * .15).toFixed(2) + 's">' + cardHtml(G) + '<div class="row"><svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.3">' + GLYPH[G.glyph] + '</svg><span class="cap">' + esc(G.cap) + '</span></div><div class="num' + (G.stale ? ' stale' : '') + '">' + esc(G.num) + (G.stale ? '<u title="Coinglass протух или нет данных"></u>' : '') + '</div><div class="unit">' + esc(G.unit || '') + '</div><div class="sub' + (G.hot ? ' hot' : '') + '">' + esc(G.sub || '') + '</div>' + (G.stale ? '<div class="sub stale">Coinglass ' + ageTxt(ageH(SRC.coinglass)) + ' — числа не свежие</div>' : '') + '</div>';
    });
    // фигуры: статуя (мрамор, драпировка, пьедестал) и стеклянный куб
    // лёгкие анимации сцены: 12 пылинок, полоса света, две искры у оси
    var ANIM = '<div class="pool g1"></div><div class="pool g2"></div><div class="pool t"></div>';
    ANIM += '<div class="dustbox">';
    for (var di = 0; di < 6; di++) { var rx = 120 + ((di * 137) % 1200), ry = 420 + ((di * 71) % 460), dd = 9 + (di % 5) * 2, dw = -(di * 1.3), dx = (di % 2 ? 1 : -1) * (12 + (di * 9) % 40);
      ANIM += '<div class="dust' + (di % 3 === 0 ? ' g' : '') + '" style="left:' + rx + 'px;top:' + ry + 'px;--d:' + dd + 's;--w:' + dw + 's;--x:' + dx + 'px"></div>'; }
    ANIM += '</div><div class="spark" style="left:' + (SL + (X0 - 26) - 3) + 'px;top:' + (ST + Y1 - 10) + 'px"></div><div class="spark b" style="left:' + (SL + (X0 - 26) - 3) + 'px;top:' + (ST + Y0 - 3) + 'px"></div>';
    var vtxt = String(dec.verdict || '').toLowerCase(), vcls = /брать|купить/.test(vtxt) ? 'v-buy' : /держ/.test(vtxt) ? 'v-hold' : /закр|выход|выйти|прода/.test(vtxt) ? 'v-exit' : 'v-wait';
    var BOX6 = '<div class="f back"></div><div class="f bottom"></div><div class="f left"></div><div class="f right"></div><div class="f top"></div>';
    var dzone = ANIM + '<div class="mini verdict ' + vcls + ' dzone decbox vb ' + (window.VERDICT_STYLE || 'dark') + '">' + cardHtml(dec) +
      '<div class="bglow2"></div><div class="bglow"></div>' +
      [[46, 6.2, 0], [62, 7.1, .8], [78, 5.6, 1.6], [94, 6.8, .4], [110, 7.6, 1.2]].map(function (r) { return '<i class="ray" style="left:' + r[0] + 'px;--rd:' + r[1] + 's;--rw:' + (-r[2]) + 's"></i>'; }).join('') +
      '<div class="vtxt"><div class="vcap">решение</div><div class="vw">' + esc(dec.verdict) + '</div><div class="vwhy">' + esc(String(dec.why).split('—')[0].slice(0, 32)) + '</div></div>' +
      '<div class="gshadow"></div><div class="box grey">' + BOX6 + '<div class="f front"><div class="txt"><b>за</b><span>' + esc(dec.pro.join(' · ') || 'нет') + '</span><b class="con">против</b><span class="con">' + esc(dec.con.join(' · ') || 'нет') + '</span></div></div></div></div>';
    // ── журнал за две недели — мини-плита: последние 14 дневок, метки смен ──
    (function () {
      var J = JR[String(s.t).toUpperCase()], M = (J && J.marks) || [];
      var ser14 = ser.slice(-15), n = ser14.length; if (n < 3) return;
      var W = 320, H = 180, lo = Math.min.apply(null, ser14), hi = Math.max.apply(null, ser14); if (hi === lo) hi = lo * 1.01;
      var X = function (i) { return 12 + i / (n - 1) * (W - 24); }, Y = function (p) { return 34 + (1 - (p - lo) / (hi - lo)) * (H - 90); };
      var dpath = ser14.map(function (p, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(p).toFixed(1); }).join(' ');
      var Ln = 0; for (var i = 1; i < n; i++) Ln += Math.hypot(X(i) - X(i - 1), Y(ser14[i]) - Y(ser14[i - 1]));
      var t1 = d1 ? new Date(d1).getTime() : null, DAY = 864e5, GY = H - 30;
      var g = '<defs><linearGradient id="hf" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="' + GOLD + '" stop-opacity=".22"/><stop offset="1" stop-color="' + GOLD + '" stop-opacity="0"/></linearGradient></defs>' +
        '<path d="' + dpath + ' L' + X(n - 1).toFixed(1) + ',' + GY + ' L12,' + GY + ' Z" fill="url(#hf)" opacity=".6"/>' +
        '<path d="' + dpath + '" fill="none" stroke="' + GOLD + '" stroke-width="5" stroke-linejoin="round" opacity=".18"/>' +
        '<path class="ln" style="--L:' + Math.ceil(Ln + 2) + '" d="' + dpath + '" fill="none" stroke="' + GOLDL + '" stroke-width="1.4" stroke-linejoin="round"/>' +
        '<circle r="2.4" fill="#fff"><animateMotion dur="7s" begin="5.6s" repeatCount="indefinite" path="' + dpath + '"/></circle>';
      var dates = ['2 нед', '1 нед', 'сегодня'];
      [0, Math.floor((n - 1) / 2), n - 1].forEach(function (ii, k) { g += '<text class="ax" x="' + X(ii).toFixed(1) + '" y="' + (GY + 12) + '" text-anchor="middle">' + dates[k] + '</text>'; });
      M.forEach(function (m, k) {
        var tm = new Date(m.t).getTime(), fi = t1 ? (n - 1) - (t1 - tm) / DAY : n - 1; fi = Math.max(0, Math.min(n - 1, fi));
        var x = X(fi), y = Y(+m.px), ty = 12 + (k % 2) * 12, col = m.miss ? '#ffa892' : GOLDL;
        g += '<line x1="' + x.toFixed(1) + '" y1="' + y.toFixed(1) + '" x2="' + x.toFixed(1) + '" y2="' + (ty + 4) + '" stroke="' + col + '" stroke-width=".8" stroke-dasharray="2 4" opacity=".7"/>' +
          '<circle class="ring" style="animation-delay:' + (k * .7) + 's" cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="6" fill="none" stroke="' + col + '" stroke-width="1" opacity=".8"/><circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.2" fill="#fff"/>' +
          '<text class="fc' + (m.miss ? ' miss' : '') + '" x="' + (x - 4).toFixed(1) + '" y="' + ty + '" text-anchor="end">' + esc(m.tpl) + '</text>';
      });
      g += '<circle cx="' + X(n - 1).toFixed(1) + '" cy="' + Y(ser14[n - 1]).toFixed(1) + '" r="2.6" fill="#fff"/>';
      var svg = '<svg viewBox="0 0 ' + W + ' ' + H + '">' + g + '</svg>';
      dzone += '<div class="mini journal"><div class="gglow"></div>' + svg + '<div class="ground"></div><div class="refl">' + svg + '</div></div>';
    })();
    // шапка, монеты, часы
    var chg = has(s.p1d) ? (+s.p1d) : null;
    var bk2 = BOOK[String(s.t).toUpperCase()], pos = '';
    if (bk2 && bk2.entry) pos = '<div class="pos' + (bk2.manual ? ' mine' : '') + '">' + (bk2.manual ? 'твоя позиция' : 'вход журнала') + ' <b>' + px4(bk2.entry) + '</b>' + (has(bk2.chg) ? ' · <b>' + pct(bk2.chg) + '</b> от входа' : '') + (bk2.upX && +bk2.upX >= 1.5 ? ' · ×' + (+bk2.upX).toFixed(1) : '') + (bk2.closed ? ' · закрыта' : '') + '</div>';
    // имя монеты — ссылка на TradingView, бессрочный фьючерс Binance (суффикс .P), в новой вкладке
    var tvSym = 'BINANCE:' + String(s.coin || (String(s.t).toUpperCase() + 'USDT')).toUpperCase().replace(/[^A-Z0-9]/g, '') + '.P';
    var srcs = srcLine();
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
    stage.innerHTML = '<div class="beam"></div><div class="floor"></div><div class="sweep"></div>' + aura + '<div class="slab"><svg viewBox="0 0 ' + SW + ' ' + SH + '">' + slab + '</svg></div><svg class="leaders" viewBox="0 0 1440 900">' + leaders + '</svg>' +
      hd + hdr + srcs + '<a class="back" href="brief.html">← схема</a>' + coins + notes + dzone + clock + '<div class="replay" id="replay">заново</div><div class="legend">' + (ser.length > 2 ? 'цена · ' + days + ' дневок' + (d0 ? ' · архив' : ' · звезда') : 'ряда цены нет') + ' · наведи на пометку — полная группа</div>' +
      '<div class="atmo"><div class="vig"></div></div>';   // ОПТИМИЗАЦИЯ 04.09: зерно feTurbulence на весь экран снято — на планшете это половина кадра
    root.getElementById('replay').onclick = function () { build(tick); };
    fit();
  }
  function fit() { var W = root.host.ownerDocument.documentElement.clientWidth || window.innerWidth, H = window.innerHeight; var k = Math.min(W / 1440, H / 900); stage.style.transform = 'translate(-50%,-100%) scale(' + k.toFixed(4) + ')'; }   // 04.09: якорь — низ окна, не центр
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
