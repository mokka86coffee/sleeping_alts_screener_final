#!/usr/bin/env python3
"""ЗАКРЫТЫЕ СДЕЛКИ БЫСТРОГО БОТА НА COINGLASS (28.09, владелец: «продолжай проверять бота, каждая сделка закрытая — идёшь в коинглас и смотришь
историю на 30 мин, часах, 6ч, дневках»; «посмотри по коингласс, сколько можно было на растущей монете досидеть с твх до выноса в лонге»).

По каждой монете с закрытыми сделками (книги «пробуждение» и «всплеск/вынос» с 27.09 07:15) открывает Coinglass Binance_<монета> с «моими»
индикаторами (+ ликвидации и базис, без заявок) и:
  1) выгружает цифры графика (exportData) на 15m, 30m, 1h, 6h, 1D → claude/research/cgx/<монета>_<тф>.json
     колонки: t, o, h, l, c, vol, cvd_f, cvd_s, fund, oi, liq_long (+, вынесены лонги), liq_short (+, вынесены шорты), basis;
  2) по каждой сделке — снимки 30m / 1h / 6h / 1D с линиями входа и выхода → claude/research/cgr/<монета>_<время входа>_<тф>.png
     (окна: 30m — 2 сут до входа … 1 сут после выхода; 1h — 5 сут … 2 сут; 6h — 30 сут … 5 сут; 1D — 90 сут … 10 сут).
Уже снятое не переснимает (файлы есть). Список сделок и готовых — claude/research/cgr/trades.json.

    .venv/bin/python claude/research/cg_review.py            # все закрытые сделки, которых ещё нет
    .venv/bin/python claude/research/cg_review.py --no-shots # только цифры
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SRC, PROF = ROOT / "output" / "cg_profile", ROOT / "output" / "cg_profile_review"
HERE = Path(__file__).parent
XD, RD = HERE / "cgx", HERE / "cgr"
L = timezone(timedelta(hours=3))
T0 = datetime(2026, 9, 27, 7, 15, tzinfo=L).timestamp()
CHART = "const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();"
TF = {"15": 10, "30": 12, "60": 30, "360": 120, "1D": 365}                  # тф → сколько суток истории грузить для цифр
SHOT = {"30": (2, 1), "60": (5, 2), "360": (30, 5), "1D": (90, 10)}          # тф → (сут до входа, сут после выхода) на снимке
COLS = (("vol", "Volume", "Volume"), ("cvd_f", "<CoinGlass> Cumulative Volume Delta", "Candles (Close)"),
        ("cvd_s", "<CoinGlass> Aggregated Spot Cumulative", "Candles (Close)"), ("fund", "<CoinGlass> Funding", None),
        ("oi", "<CoinGlass> Open Interest", "Candles (Close)"), ("liq_long", "<CoinGlass> Aggregated Liquidations", "Long"),
        ("liq_short", "<CoinGlass> Aggregated Liquidations", "Short"), ("basis", "<CoinGlass> Basis", None))


def trades() -> list[dict]:
    out = []
    for book, f in (("пробуждение", "paper_wake.jsonl"), ("всплеск/вынос", "paper_fast3.jsonl")):
        for ln in open(ROOT / "output" / f):
            r = json.loads(ln)
            if not str(r.get("kind", "")).startswith("exit") or float(r.get("opened_at") or 0) < T0:
                continue
            out.append(dict(book=book, sym=r["sym"], side=int(r.get("side") or 1), t_in=float(r["opened_at"]),
                            t_out=float(r.get("at") or r["opened_at"]), px_in=float(r.get("px_in") or 0),
                            px_out=float(r.get("px_out") or 0), res=float(r["result_pct"]),
                            why=r.get("why_exit") or "", rule=r.get("rule") or ""))
    seen, uniq = set(), []                                            # 30.09 владелец: книги «пробуждение» и «всплеск/вынос» — РАЗНЫЕ правила, сделки каждой отдельно (схлопываем только повтор внутри одной книги)
    for x in sorted(out, key=lambda x: x["t_in"]):
        k = (x["book"], x["sym"], x["side"], int(x["t_in"] // 60))
        if k not in seen:
            seen.add(k); uniq.append(x)
    return uniq


def tid(x: dict) -> str:
    return f"{x['sym'][:-4]}_{datetime.fromtimestamp(x['t_in'], L):%m%d_%H%M}"


def export(fr) -> dict:
    d = fr.evaluate(f"""async () => {{ {CHART}
      const d = await c.exportData({{includeTime: true, includeSeries: true, includedStudies: 'all'}});
      return {{schema: d.schema.map(x => [x.sourceTitle || '', x.plotTitle || '']), data: d.data.map(r => Array.from(r))}}; }}""")
    sch = d["schema"]
    idx = {"t": 0, "o": 1, "h": 2, "l": 3, "c": 4}
    for name, src, plot in COLS:
        for i, (s, p) in enumerate(sch):
            if s.startswith(src) and (plot is None or p.startswith(plot)):
                idx[name] = i; break
    rows = []
    for r in d["data"]:
        o = {k: (r[i] if i < len(r) else None) for k, i in idx.items()}
        if o.get("liq_short") is not None:
            o["liq_short"] = -o["liq_short"]
        rows.append(o)
    return {"cols": list(idx), "rows": rows}


def main() -> int:
    shots = "--no-shots" not in sys.argv
    part = next((a.split("=")[1] for a in sys.argv if a.startswith("--part=")), None)   # «i/n» — своя часть монет, свой профиль
    global PROF
    if part:
        PROF = ROOT / "output" / f"cg_profile_review_{part.replace('/', '_')}"
    XD.mkdir(exist_ok=True); RD.mkdir(exist_ok=True)
    T = trades()
    only = [x.upper() + ("" if x.upper().endswith("USDT") else "USDT") for x in sys.argv[1:] if not x.startswith("-")]
    if only:                                                          # переснять только эти монеты
        T = [x for x in T if x["sym"] in only]
    if not only:
        json.dump(T, open(RD / "trades.json", "w"), ensure_ascii=False, indent=0)
    todo = {}
    for x in T:
        need_x = any(not (XD / f"{x['sym']}_{tf}.json").exists() or (XD / f"{x['sym']}_{tf}.json").stat().st_mtime < x["t_out"] + 3600
                     for tf in TF) and time.time() - x["t_out"] > 0
        need_s = shots and any(not (RD / f"{tid(x)}_{tf}.png").exists() for tf in SHOT)
        if need_x or need_s:
            todo.setdefault(x["sym"], []).append(x)
    if part:
        i, n = map(int, part.split("/"))
        todo = {k: v for j, (k, v) in enumerate(sorted(todo.items())) if j % n == i}
    print(f"сделок {len(T)}, монет к съёмке {len(todo)}", flush=True)
    if not todo:
        return 0
    shutil.rmtree(PROF, ignore_errors=True); shutil.copytree(SRC, PROF, ignore=shutil.ignore_patterns("Singleton*", "*.lock"))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROF), headless=True, viewport={"width": 1700, "height": 1500})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        for sym, xs in todo.items():
            try:
                pg.goto(f"https://www.coinglass.com/tv/Binance_{sym}"); pg.wait_for_timeout(14000)
                fr = next(f for f in pg.frames if f != pg.main_frame)
                fr.evaluate(f"() => {{ {CHART} for (const s of c.getAllStudies()) if (/Bid & Ask/.test(s.name)) c.removeEntity(s.id); }}")
                have = fr.evaluate(f"() => {{ {CHART} return c.getAllStudies().map(s => s.name).join('|'); }}")
                for n in ("Aggregated Liquidations", "Basis"):
                    if n in have:
                        continue
                    try:
                        pg.get_by_text("CoinGlass - Indicators", exact=True).first.click(); pg.wait_for_timeout(1200)
                        pg.get_by_text(n, exact=True).first.click(); pg.wait_for_timeout(1500); pg.keyboard.press("Escape")
                    except Exception:  # noqa: BLE001
                        print(f"{sym}: не добавлен {n}", flush=True)
                t_last = max(x["t_out"] for x in xs)
                for tf, days in TF.items():
                    fx = XD / f"{sym}_{tf}.json"
                    fresh = fx.exists() and fx.stat().st_mtime >= t_last + 3600
                    if fresh and (not shots or tf not in SHOT):
                        continue                                      # цифры свежие, снимков на этом тф нет
                    fr.evaluate(f"(R) => new Promise(ok => {{ {CHART} c.setResolution(R, () => ok(1)); setTimeout(() => ok(0), 10000); }})", tf)
                    pg.wait_for_timeout(4000)
                    fr.evaluate(f"(R) => {{ {CHART} c.setVisibleRange({{from: R[0], to: R[1]}}); }}", [int(time.time() - days * 86400), int(time.time())])
                    if not fresh:
                        pg.wait_for_timeout(5000)
                        json.dump(export(fr), open(fx, "w"))
                    if not shots or tf not in SHOT:
                        continue
                    b, a = SHOT[tf]
                    for x in xs:
                        out = RD / f"{tid(x)}_{tf}.png"
                        if out.exists():
                            continue
                        fr.evaluate(f"(R) => {{ {CHART} c.setVisibleRange({{from: R[0], to: R[1]}}); }}",
                                    [int(x["t_in"] - b * 86400), int(min(time.time(), x["t_out"] + a * 86400))])
                        pg.wait_for_timeout(3500)
                        fr.evaluate(f"""async (X) => {{ {CHART}
                          for (const id of (window.__ids || [])) {{ try {{ c.removeEntity(id); }} catch (e) {{}} }}
                          c.removeAllShapes(); window.__ids = [];
                          const v = (t, col) => window.__ids.push(c.createShape({{time: t}}, {{shape: 'vertical_line', lock: true, disableSelection: true, overrides: {{linecolor: col, linewidth: 2, linestyle: 2}}}}));
                          const h = (pr, col, txt) => window.__ids.push(c.createShape({{time: X.t_in, price: pr}}, {{shape: 'horizontal_line', lock: true, disableSelection: true, text: txt,
                              overrides: {{linecolor: col, linewidth: 1, showLabel: true, textcolor: col, horzLabelsAlign: 'left', fontsize: 13}}}}));
                          v(Math.floor(X.t_in), '#f5a623'); v(Math.floor(X.t_out), '#ffffff');
                          h(X.px_in, '#f5a623', (X.label || (X.side < 0 ? 'ШОРТ ' : 'ЛОНГ ')) + ' ' + X.px_in); if (X.px_out) h(X.px_out, '#ffffff', 'ВЫХ ' + X.px_out + ' ' + X.res + '%');
                          window.__ids = await Promise.all(window.__ids); }}""", x)
                        pg.wait_for_timeout(2000); pg.mouse.move(1695, 1495)
                        pg.screenshot(path=str(out))
                    fr.evaluate(f"() => {{ {CHART} for (const id of (window.__ids || [])) {{ try {{ c.removeEntity(id); }} catch (e) {{}} }} c.removeAllShapes(); window.__ids = []; }}")
                print(f"{sym}: сделок {len(xs)} — готово", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"{sym}: не снят — {type(e).__name__}: {str(e)[:100]}", flush=True)
        ctx.close()
    shutil.rmtree(PROF, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
