#!/usr/bin/env python3
"""ЭКРАН КНИГИ БОТА (16.09, владелец: «это торговый бот, подумай как лучше, на реальных данных без
моего участия, калибровать будем отдельно»). Не журнал сделок, а приборы состояния: чем позиция
держится и что её закроет.

Читает открытые позиции и журналы трёх бумажных книг — paper_end (шорт по концу хода), paper_crowd
(против толпы, перекупленность, спайк, провал, первый час Лондона) и paper_fast (быстрые, с хеджем
и флипом), цену и суточный ход из near_move, стены из depth. Собирает book.html:
  • шапка: в позиции, ход книги сейчас, за сутки закрыто, ЗА 24 ЧАСА, ближайший выход;
  • строки позиций: имя и ТВХ, ход от входа крупной цифрой, полоса вход → сейчас с отметками
    максимума и минимума, чем держится, и справа УСЛОВИЕ ВЫХОДА С ЧИСЛОМ (до цели столько-то,
    стоп, срок, сколько баров осталось) с полосой «где мы между входом и целью»;
  • закрытые за BOOK_CLOSED_H часов с причиной выхода;
  • строка вывода: что дают выходы по событию против выходов по сроку — это и есть калибровка.
Личного на экране нет: размер позиции и плечо не печатаются, «вес» — это множитель правила бота.
Вызов как у прочих экранов: render_book() -> str, run.py кладёт в pages["book.html"].
"""
from __future__ import annotations

import json
import statistics as st
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import BOOK_CLOSED_H
except ImportError:
    BOOK_CLOSED_H = 24.0
try:
    from core_config import BOOK_DEPOSIT, BOOK_DAYS
except ImportError:
    BOOK_DEPOSIT, BOOK_DAYS = 10_000.0, 10

BOOKS = (("конец", "paper_end"), ("толпа", "paper_crowd"), ("быстрые", "paper_fast"))


def _read(name: str):
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def _lines(name: str) -> list[dict]:
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        if not p.exists():
            continue
        out = []
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
        return out
    return []


def _esc(x) -> str:
    return (str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def _m(v) -> str:
    """деньги с пробелом в разрядах: глобальная замена запятых по всему документу ломала JS (16.09)"""
    return f"{float(v):+,.0f} $".replace(",", " ")


def _m0(v) -> str:
    return f"{float(v):,.0f} $".replace(",", " ")


def _px(v) -> str:
    if v is None:
        return "—"
    v = float(v)
    return f"{v:.6g}"


def _now() -> float:
    return datetime.now(timezone.utc).timestamp()


def _live_px() -> dict:
    """цена сейчас и ход монеты за сутки — из сводки прогона"""
    out = {}
    nm = _read("near_move.json") or {}
    for sym, v in (nm.get("coins") or {}).items():
        t = v.get("today") or {}
        n = v.get("nums") or {}
        out[str(sym).upper()] = (t.get("px") or n.get("px_now"), t.get("px_chg_pct"))
    return out


def _bars_since(t_ms, minutes: int = 30) -> int:
    try:
        return max(0, int((_now() - float(t_ms) / 1000) / (minutes * 60)))
    except (TypeError, ValueError):
        return 0


def _walls(sym: str) -> str:
    """ближайший потолок и пол из стакана — коротко, в строку «чем держится»"""
    dp = ((_read("depth.json") or {}).get("coins") or {}).get(sym) or {}
    ws = dp.get("walls") or []
    a = sorted([w for w in ws if w.get("side") == "ask" and (w.get("dist_pct") or 0) > 0], key=lambda w: w["dist_pct"])
    b = sorted([w for w in ws if w.get("side") == "bid" and (w.get("dist_pct") or 0) < 0], key=lambda w: -w["dist_pct"])
    parts = []
    if a:
        parts.append(f"потолок {_px(a[0]['px'])} ({a[0]['dist_pct']:+.1f}%)")
    if b:
        parts.append(f"пол {_px(b[0]['px'])} ({b[0]['dist_pct']:+.1f}%)")
    return " · ".join(parts)


def _collect() -> tuple[list[dict], list[dict]]:
    """открытые позиции всех книг и закрытые за последние BOOK_CLOSED_H часов"""
    live_px = _live_px()
    opened, closed = [], []
    cut = _now() - BOOK_DAYS * 86400
    for book, stem in BOOKS:
        st_ = _read(f"{stem}.json") or {}
        for sym, p in (st_.get("open") or {}).items():
            sym = str(sym).upper()
            px_now, d24 = live_px.get(sym, (None, None))
            entry = p.get("px") or (p.get("legs") or {}).get("long") or (p.get("legs") or {}).get("short")
            # сторона: у paper_end бот только шортит (бар «конец хода»), у paper_crowd она в записи,
            # у paper_fast — в состоянии позиции (long / hedged / short)
            side = p.get("side")
            if side is None:
                side = -1 if (stem == "paper_end" or str(p.get("state")) == "short") else 1
            res = None
            if entry and px_now:
                res = (float(px_now) / float(entry) - 1) * 100 * (1 if side > 0 else -1)
                if abs(res) < 0.005:
                    res = 0.0
            opened.append({
                "book": book, "sym": sym, "side": side, "entry": entry, "px": px_now, "res": res, "d24": d24,
                "size": p.get("size") or 1.0, "rule": p.get("rule") or p.get("why") or p.get("state") or "",
                "target": p.get("target"), "stop": p.get("stop"), "hold": p.get("hold"),
                "bars": _bars_since(p.get("t")), "walls": _walls(sym),
                "fund": p.get("fund"), "oi_bar": p.get("oi_bar_pct"), "run": p.get("run_pct"),
                "bg12": p.get("bg12"), "z": p.get("z"), "state": p.get("state"),
            })
        for r in _lines(f"{stem}.jsonl"):
            if str(r.get("kind") or "").startswith("exit") and (r.get("at") or 0) >= cut:
                at = r.get("at") or 0
                closed.append({
                    "book": book, "sym": str(r.get("sym") or "").upper(), "res": r.get("result_pct"),
                    "sized": r.get("result_sized_pct"), "why": r.get("why_exit") or r.get("why") or "",
                    "rule": r.get("rule") or "", "size": float(r.get("size") or 1.0), "at": at,
                    "day": datetime.fromtimestamp(at, timezone.utc).astimezone().strftime("%Y-%m-%d") if at else "",
                })
    opened.sort(key=lambda x: -(abs(x["res"]) if x["res"] is not None else 0))
    closed.sort(key=lambda x: -(x["at"] or 0))
    return opened, closed


def _exit_block(p: dict) -> tuple[str, str, float]:
    """условие выхода словами с числом + доля пути до цели (0..1)"""
    res = p["res"] or 0.0
    tgt = p.get("target")
    stop = p.get("stop")
    hold = p.get("hold")
    left = (int(hold) - p["bars"]) if hold else None
    tail = []
    if stop:
        tail.append(f"стоп {float(stop) * 100:.1f}%")
    if hold:
        tail.append(f"срок {int(hold)} баров" + (f", осталось {max(0, left)}" if left is not None else ""))
    if tgt:
        head = f'цель <b>{float(tgt) * 100:.1f}%</b>'
        tail.insert(0, f"до неё {max(0.0, float(tgt) * 100 - res):.2f}%")
        frac = max(0.0, min(1.0, res / (float(tgt) * 100))) if tgt else 0.0
    elif p["book"] == "быстрые":
        head = 'по событию: <b>слом вортекса</b>'
        tail.insert(0, "хедж и флип по правилу")
        frac = 0.0
    else:
        head = 'по событию: <b>z ниже нуля</b>'
        if p.get("z") is not None:
            tail.insert(0, f"сейчас {float(p['z']):+.1f}")
        frac = 0.0
    return head, " · ".join(tail), frac


def _hold_why(p: dict) -> str:
    """чем позиция держится — из полей правила, одной строкой"""
    bits = [_esc(p["rule"])]
    x = []
    if p.get("oi_bar") is not None:
        x.append(f"интерес <b>{float(p['oi_bar']):+.2f}%</b> за бар")
    if p.get("run") is not None:
        x.append(f"рост до сигнала <b>{float(p['run']):+.1f}%</b>")
    if p.get("fund") is not None:
        x.append(f"фандинг <b>{float(p['fund']):+.3f}</b>")
    if p.get("bg12"):
        x.append(f"фон 12 ч {_esc(p['bg12'])}")
    if p.get("walls"):
        x.append(_esc(p["walls"]))
    return bits[0] + ("<br><span>" + " · ".join(x) + "</span>" if x else "")


def _money_day(rows: list[dict]) -> dict:
    """ДЕПОЗИТ НА ДЕНЬ (16.09, владелец: «поставь депозит 10000 на день, пусть распределяется на сделки,
    за 24 часа итог в деньгах, каждые 24 часа депозит снова 10000»). Депозит дня делится между сделками
    этого дня пропорционально весу правила: доля = депозит × вес / сумма весов дня. Деньги сделки —
    доля × результат. Так итог дня не зависит от числа сделок: шестьдесят сделок по проценту и три по
    двадцати дают сопоставимые числа, а сложение процентов, как было, — нет."""
    w = sum(float(r.get("size") or 1) for r in rows) or 1.0
    out = []
    for r in rows:
        share = BOOK_DEPOSIT * float(r.get("size") or 1) / w
        money = share * float(r.get("res") or 0) / 100
        out.append(dict(r, share=share, money=money))
    tot = sum(x["money"] for x in out)
    hit = (100 * sum(1 for x in out if x["money"] > 0) / len(out)) if out else 0
    return {"rows": out, "total": tot, "hit": hit, "n": len(out),
            "best": max((x["money"] for x in out), default=0.0),
            "worst": min((x["money"] for x in out), default=0.0)}


def render_book() -> str:
    opened, closed = _collect()
    n = len(opened)
    plus = sum(1 for p in opened if (p["res"] or 0) > 0)
    shorts = sum(1 for p in opened if p["side"] < 0)
    # ход открытых — СРЕДНЯЯ на позицию, не сумма (16.09: сумма процентов по одновременным сделкам врёт)
    cur = st.mean([p["res"] for p in opened if p["res"] is not None]) if opened else 0.0
    days = sorted({c["day"] for c in closed if c.get("day")}, reverse=True)[:BOOK_DAYS]
    per_day = {d: _money_day([c for c in closed if c.get("day") == d]) for d in days}
    today = days[0] if days else datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    cur_day = per_day.get(today) or {"rows": [], "total": 0.0, "hit": 0, "n": 0, "best": 0.0, "worst": 0.0}
    nearest = None
    for p in opened:
        if p.get("target") and p["res"] is not None:
            left = float(p["target"]) * 100 - p["res"]
            if nearest is None or left < nearest[0]:
                nearest = (left, p)
    allrows = [x for d in days for x in per_day[d]["rows"]]
    by_event = [x["money"] for x in allrows if not str(x.get("why") or "").startswith("срок")]
    by_time = [x["money"] for x in allrows if str(x.get("why") or "").startswith("срок")]
    note = ""
    if len(by_event) >= 3 and len(by_time) >= 3:
        note = (f"выходы по событию дают {_m(st.mean(by_event))} на сделку, по сроку {_m(st.mean(by_time))} · "
                f"сделок {len(by_event)} против {len(by_time)}")

    rows = []
    for p in opened:
        res = p["res"]
        cls = "p" if (res or 0) > 0 else ("m" if (res or 0) < 0 else "")
        head, tail, frac = _exit_block(p)
        side_cls = "short" if p["side"] < 0 else "long"
        side_nm = "шорт" if p["side"] < 0 else "лонг"
        d24 = p.get("d24")
        d24_html = ""
        if d24 is not None:
            d24_html = (f'<div class="d24">за 24 часа <b class="{"p" if float(d24) > 0 else "m"}">'
                        f'{float(d24):+.1f}%</b></div>')
        w = min(42.0, abs(res or 0) * 8)
        left = 50 - w if (res or 0) < 0 else 50
        rows.append(f'''  <div class="pos {side_cls}">
    <div class="who">
      <div class="nm">{_esc(p["sym"].replace("USDT", ""))} <em>{side_nm} · вес ×{float(p["size"] or 1):g} · {_esc(p["book"])}</em></div>
      <div class="tvh">ТВХ <b>{_px(p["entry"])}</b> · сейчас {_px(p["px"])}<br>в позиции {p["bars"]} бар</div>
      {d24_html}
    </div>
    <div class="big {cls}">{("%+.2f%%" % res) if res is not None else "—"}</div>
    <div class="mv">
      <div class="track"><div class="fill {cls}" style="left:{left:.0f}%;width:{w:.0f}%"></div>
        <div class="pin" style="left:50%"><u>вход</u></div></div>
      <div class="why">{_hold_why(p)}</div>
    </div>
    <div class="ex"><i>выход</i>
      <div class="cond">{head}<br><s>{_esc(tail)}</s></div>
      <div class="bar"><i style="width:{frac * 100:.0f}%"></i><em style="left:100%"></em></div>
      <div class="legend"><span>вход</span><span>цель</span></div>
    </div>
  </div>''')

    # дни: кнопки и списки сделок каждого дня (деньги от депозита дня)
    tabs, blocks = [], []
    for i, d in enumerate(days):
        m = per_day[d]
        lbl = datetime.strptime(d, "%Y-%m-%d").strftime("%d.%m")
        cls = "on" if i == 0 else ""
        sign = "p" if m["total"] >= 0 else "m"
        tabs.append(f'''<button class="tab {cls}" data-day="{d}"><b>{lbl}</b>'''
                    f'''<s class="{sign}">{_m(m["total"])}</s><u>{m["n"]} сделок</u></button>''')
        lines = []
        for c in sorted(m["rows"], key=lambda x: -abs(x["money"])):
            mv = c["money"]
            lines.append(f'''    <div class="row"><span class="n">{_esc(c["sym"].replace("USDT", ""))}</span>'''
                         f'''<span>{_esc(c["book"])} · ×{float(c.get("size") or 1):g}</span>'''
                         f'''<span>{_esc(c["why"])}{" · " + _esc(c["rule"]) if c.get("rule") else ""}</span>'''
                         f'''<span class="r2">{float(c.get("res") or 0):+.2f}%</span>'''
                         f'''<span class="r {"p" if mv > 0 else "m"}">{_m(mv)}</span></div>'''.replace(",", " "))
        blocks.append(f'''<div class="day" data-day="{d}" style="display:{"block" if i == 0 else "none"}">
    <div class="daytot">депозит дня <b>{_m0(BOOK_DEPOSIT)}</b> · распределён на {m["n"]} сделок по весу правила ·
      итог <b class="{sign}">{_m(m["total"])}</b> · попаданий {m["hit"]:.0f}% ·
      лучшая {_m(m["best"])} · худшая {_m(m["worst"])}</div>
{chr(10).join(lines) if lines else '<div class="empty">в этот день выходов не было</div>'}
  </div>''')

    nearest_html, nearest_sub = "—", "целей по времени нет"
    if nearest:
        nearest_html = (f'{_esc(nearest[1]["sym"].replace("USDT", ""))} · цель '
                        f'{float(nearest[1]["target"]) * 100:.1f}%')
        nearest_sub = f'осталось {max(0.0, nearest[0]):.2f}%'
    stamp = datetime.now(timezone.utc).astimezone().strftime("%H:%M")
    day_sign = "p" if cur_day["total"] >= 0 else "m"
    return f'''<!doctype html>
<html lang="ru"><head><meta charset="utf-8"><title>книга · бот</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Jost:wght@200;300;400;500&family=IBM+Plex+Mono:wght@400&display=swap" rel="stylesheet">
<style>
:root{{--f-cap:Jost,sans-serif;--f-mono:"IBM Plex Mono",monospace;--gold:#f5a93a;--up:#4fd1a8;--dn:#ff7a7a;--ice:#eaf4ff;--dim:#6f8f88;--cap:#7fa898}}
*{{box-sizing:border-box}}
html,body{{margin:0;background:#05090a;color:var(--ice);font-family:var(--f-cap);-webkit-font-smoothing:antialiased}}
body{{min-height:100vh;background:radial-gradient(1200px 520px at 50% -8%,rgba(245,169,58,.10),transparent 70%),
  radial-gradient(900px 600px at 15% 30%,rgba(79,209,168,.05),transparent 65%),
  radial-gradient(1400px 800px at 50% 70%,#0a1613,#05090a 62%)}}
.wrap{{max-width:1180px;margin:0 auto;padding:26px 30px 54px}}
.head{{display:flex;align-items:flex-end;justify-content:space-between}}
.head h1{{margin:0;font-weight:200;font-size:26px;letter-spacing:.44em;text-transform:uppercase}}
.head .back{{font-size:8px;letter-spacing:.3em;text-transform:uppercase;color:var(--cap);text-decoration:none}}
.head .back:hover{{color:var(--ice)}}
.tot{{position:relative;display:flex;align-items:flex-end;gap:22px;padding:14px 20px;margin:10px 0 18px;border-radius:10px;overflow:hidden;
  background:linear-gradient(180deg,rgba(10,26,22,.5),rgba(4,10,9,.5));border:1px solid rgba(233,255,244,.07)}}
.tot::after{{content:"";position:absolute;left:0;right:0;bottom:0;height:1px;background:linear-gradient(90deg,transparent,rgba(245,169,58,.5),transparent)}}
.tot .cell i{{display:block;font-style:normal;font-size:7px;letter-spacing:.24em;white-space:nowrap;text-transform:uppercase;color:var(--cap);margin-bottom:5px}}
.tot .cell b{{font-weight:200;font-size:24px;letter-spacing:.02em;line-height:1}}
.tot .cell s{{display:block;text-decoration:none;font-size:7.2px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-top:6px;white-space:nowrap}}
.tot .sep{{width:1px;align-self:stretch;background:rgba(233,255,244,.08)}}
.tot .next{{margin-left:auto;text-align:right}}
.tot .next b{{font-size:15px;letter-spacing:.08em;color:var(--gold);white-space:nowrap}}
.p{{color:var(--up)}}.m{{color:var(--dn)}}
.sec{{font-size:7.5px;letter-spacing:.3em;text-transform:uppercase;color:var(--cap);margin:0 0 9px 2px}}
.pos{{position:relative;display:grid;grid-template-columns:150px 118px 1fr 258px;gap:18px;align-items:center;
  padding:9px 16px;margin-bottom:5px;border-radius:7px;
  background:linear-gradient(180deg,rgba(10,24,20,.44),rgba(4,10,9,.44));border:1px solid rgba(233,255,244,.06)}}
.pos::before{{content:"";position:absolute;left:0;top:8px;bottom:8px;width:2px;border-radius:2px}}
.pos.long::before{{background:var(--up);box-shadow:0 0 10px var(--up)}}
.pos.short::before{{background:var(--dn);box-shadow:0 0 10px var(--dn)}}
.who{{padding-left:8px}}
.who .nm{{font-size:13px;letter-spacing:.16em;text-transform:uppercase;font-weight:300;white-space:nowrap}}
.who .nm em{{font-style:normal;font-size:7px;letter-spacing:.2em;margin-left:6px;color:var(--dim)}}
.who .tvh{{font-family:var(--f-mono);font-size:7.4px;white-space:nowrap;letter-spacing:.02em;color:var(--dim);margin-top:3px;line-height:1.5}}
.who .d24{{margin-top:4px;font-size:7px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);white-space:nowrap}}
.who .d24 b{{font-family:Jost;font-weight:400;font-size:9px;letter-spacing:.04em}}
.big{{font-weight:200;font-size:24px;white-space:nowrap;letter-spacing:.02em;line-height:1;text-align:right}}
.big.p{{text-shadow:0 0 14px rgba(79,209,168,.3)}}.big.m{{text-shadow:0 0 14px rgba(255,122,122,.28)}}
.mv .track{{position:relative;height:3px;width:100%;border-radius:3px;background:rgba(233,255,244,.09)}}
.mv .fill{{position:absolute;top:0;bottom:0;border-radius:3px}}
.mv .fill.p{{background:linear-gradient(90deg,rgba(79,209,168,.25),var(--up))}}
.mv .fill.m{{background:linear-gradient(90deg,rgba(255,122,122,.25),var(--dn))}}
.mv .pin{{position:absolute;top:-4px;width:1px;height:11px;background:rgba(233,255,244,.4)}}
.mv .pin u{{position:absolute;top:11px;left:50%;transform:translateX(-50%);text-decoration:none;font-size:6.5px;letter-spacing:.18em;white-space:nowrap;color:var(--dim)}}
.mv .why{{margin-top:13px;font-size:7.4px;letter-spacing:.11em;text-transform:uppercase;color:#9fb8ae;line-height:1.55}}
.mv .why b{{color:var(--gold);font-weight:400}}
.mv .why span{{color:var(--dim)}}
.ex{{border-left:1px solid rgba(233,255,244,.07);padding-left:16px}}
.ex i{{display:block;font-style:normal;font-size:6.5px;letter-spacing:.26em;text-transform:uppercase;color:var(--cap);margin-bottom:4px}}
.ex .cond{{font-size:7.4px;letter-spacing:.06em;text-transform:uppercase;line-height:1.55}}
.ex .cond b{{font-family:Jost;font-weight:300;font-size:14px;letter-spacing:.03em;color:var(--ice)}}
.ex .cond s{{text-decoration:none;color:var(--dim)}}
.ex .bar{{position:relative;height:2px;margin-top:7px;border-radius:2px;background:rgba(233,255,244,.08)}}
.ex .bar i{{position:absolute;left:0;top:0;bottom:0;border-radius:2px;background:linear-gradient(90deg,rgba(245,169,58,.3),var(--gold));margin:0}}
.ex .bar em{{position:absolute;top:-4px;width:1px;height:10px;background:var(--dn);opacity:.8}}
.ex .legend{{display:flex;justify-content:space-between;margin-top:5px;font-size:6px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim)}}
/* ── дни: кнопки ── */
.tabs{{display:flex;gap:6px;flex-wrap:wrap;margin:22px 0 12px}}
.tab{{background:linear-gradient(180deg,rgba(10,24,20,.5),rgba(4,10,9,.5));border:1px solid rgba(233,255,244,.07);
  border-radius:7px;padding:7px 13px;cursor:pointer;color:var(--ice);font-family:var(--f-cap);text-align:left;transition:border-color .25s,background .25s}}
.tab b{{display:block;font-weight:300;font-size:11px;letter-spacing:.12em}}
.tab s{{display:block;text-decoration:none;font-size:11px;font-weight:300;letter-spacing:.04em;margin-top:3px}}
.tab u{{display:block;text-decoration:none;font-size:6.5px;letter-spacing:.2em;text-transform:uppercase;color:var(--dim);margin-top:3px}}
.tab:hover{{border-color:rgba(233,255,244,.18)}}
.tab.on{{border-color:rgba(245,169,58,.5);background:linear-gradient(180deg,rgba(28,24,12,.6),rgba(10,8,4,.6))}}
.daytot{{padding:8px 16px 12px;font-size:7.6px;letter-spacing:.14em;text-transform:uppercase;color:#9fb8ae}}
.daytot b{{font-family:Jost;font-weight:300;font-size:13px;letter-spacing:.04em;color:var(--ice)}}
.daytot b.p{{color:var(--up)}}.daytot b.m{{color:var(--dn)}}
.row{{display:grid;grid-template-columns:104px 84px 1fr 80px 104px;gap:14px;align-items:baseline;
  padding:6px 16px;border-bottom:1px solid rgba(233,255,244,.05);font-size:8.5px;letter-spacing:.13em;text-transform:uppercase;color:#9fb8ae}}
.row .n{{font-size:11px;letter-spacing:.2em;color:var(--ice)}}
.row .r2{{font-family:Jost;font-size:10px;text-align:right;color:var(--dim)}}
.row .r{{font-family:Jost;font-weight:300;font-size:15px;letter-spacing:.03em;text-align:right}}
.row span{{color:var(--dim)}}
.foot{{margin-top:22px;font-size:7.5px;letter-spacing:.22em;text-transform:uppercase;color:#4d635d}}
.empty{{padding:34px 0;text-align:center;font-size:9px;letter-spacing:.3em;text-transform:uppercase;color:var(--dim)}}
</style></head><body>
<div class="wrap">
  <div class="head"><h1>книга</h1><a class="back" href="intro.html">← звёзды</a></div>
  <div class="tot">
    <div class="cell"><i>в позиции</i><b>{n}</b><s>шортов {shorts} · лонгов {n - shorts}</s></div>
    <div class="sep"></div>
    <div class="cell"><i>ход открытых</i><b class="{"p" if cur >= 0 else "m"}">{cur:+.2f}%</b><s>в среднем на позицию · в плюсе {plus} из {n}</s></div>
    <div class="sep"></div>
    <div class="cell"><i>сегодня сделок</i><b>{cur_day["n"]}</b><s>попаданий {cur_day["hit"]:.0f}%</s></div>
    <div class="sep"></div>
    <div class="cell"><i>итог дня на депозит {_m0(BOOK_DEPOSIT)}</i><b class="{day_sign}">{_m(cur_day["total"])}</b>
      <s>лучшая {_m(cur_day["best"])} · худшая {_m(cur_day["worst"])}</s></div>
    <div class="cell next"><i>ближайший выход</i><b>{nearest_html}</b><s>{nearest_sub}</s></div>
  </div>
  <div class="sec">в позиции · условие выхода с числом</div>
{chr(10).join(rows) if rows else '<div class="empty">позиций нет</div>'}
  <div class="sec" style="margin-top:22px">закрытые по дням · депозит {_m0(BOOK_DEPOSIT)} на день, делится между сделками дня по весу правила</div>
  <div class="tabs">{"".join(tabs) if tabs else ""}</div>
{chr(10).join(blocks) if blocks else '<div class="empty">закрытых сделок нет</div>'}
  <div class="foot">{_esc(note)}{" · " if note else ""}обновлено {stamp}</div>
</div>
<script>
document.querySelectorAll('.tab').forEach(function(b){{
  b.addEventListener('click',function(){{
    document.querySelectorAll('.tab').forEach(function(x){{x.classList.remove('on')}});
    b.classList.add('on');
    var d=b.getAttribute('data-day');
    document.querySelectorAll('.day').forEach(function(x){{x.style.display=(x.getAttribute('data-day')===d)?'block':'none'}});
  }});
}});
</script>
</body></html>'''


if __name__ == "__main__":
    out = BASE_DIR / "output" / "book.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_book(), encoding="utf-8")
    print(f"книга: {out}")
