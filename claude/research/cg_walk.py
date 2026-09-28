#!/usr/bin/env python3
"""ПРОХОД ПО МОНЕТЕ В COINGLASS НА РАЗНЫХ ТАЙМФРЕЙМАХ (28.09, владелец: «возьми одну монету SEI, потом ONE, потом PLAY и пройди по ним
в Coinglass на разных ТФ за разный период»; «начни с известных индикаторов, потом добавь другие»).
Профиль output/cg_profile копируется (живые снимки бота не мешают), индикаторы Coinglass по умолчанию снимаются, ставится набор SET.
Снимки → claude/research/cg/<монета>_<набор>_<ТФ>.png

    .venv/bin/python claude/research/cg_walk.py SEIUSDT known
"""
from __future__ import annotations

import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SRC, PROF = ROOT / "output" / "cg_profile", ROOT / "output" / "cg_profile_walk"
OUT = Path(__file__).with_name("cg")
SETS = {
    # известные: объём (остаётся у Coinglass), сводный интерес, сводные ликвидации, CVD фьючерсов и спота по всем биржам, фандинг по интересу, толпа
    "known": ["Aggregated Open Interest (Candles)", "Aggregated Liquidations", "Aggregated Futures Cumulative Volume Delta (CVD)",
              "Aggregated Spot Cumulative Volume Delta (CVD)", "Funding Rates(Open Interest Weighted)", "Long/Short Ratio (Accounts)"],
    # следующий слой: реальные позиции, крупные трейдеры, интерес к капитализации, давление по рынку, спот/фьючерсы
    "more": ["Net Longs", "Net Shorts", "Top Trader Long/Short (Positions)", "Open Interest/Market Cap",
             "Aggregated Futures Taker Buy/Sell Volume", "Aggregated Futures/Spot Volume Ratio"],
}
TFS = [("1D", "1D", 365), ("4h", "240", 60), ("1h", "60", 14), ("15m", "15", 3), ("3m", "3", 1)]   # таймфрейм, код для API графика, период в днях


def main() -> int:
    sym, kind = sys.argv[1].upper(), (sys.argv[2] if len(sys.argv) > 2 else "known")
    OUT.mkdir(exist_ok=True)
    shutil.rmtree(PROF, ignore_errors=True); shutil.copytree(SRC, PROF, ignore=shutil.ignore_patterns("Singleton*", "*.lock"))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROF), headless=True, viewport={"width": 1700, "height": 2000})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(f"https://www.coinglass.com/tv/Binance_{sym}"); pg.wait_for_timeout(16000)
        fr = next(f for f in pg.frames if f != pg.main_frame)
        chart = "const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();"
        fr.evaluate(f"() => {{ {chart} for (const s of c.getAllStudies()) if (!/^Volume/.test(s.name)) c.removeEntity(s.id); }}")
        pg.wait_for_timeout(1500)
        for n in SETS[kind]:
            try:
                pg.get_by_text("CoinGlass - Indicators", exact=True).first.click(); pg.wait_for_timeout(1500)
                pg.get_by_text(n, exact=True).first.click(); pg.wait_for_timeout(1500)
                pg.keyboard.press("Escape"); pg.wait_for_timeout(500)
            except Exception as e:  # noqa: BLE001
                print(f"{sym}: индикатор «{n}» не добавлен: {type(e).__name__}")
        names = fr.evaluate(f"() => {{ {chart} return c.getAllStudies().map(s => s.name); }}")
        print(sym, kind, "индикаторы:", names)
        for tf, res, days in TFS:
            try:                                   # таймфрейм — через API графика (меню Coinglass в безголовом окне не открывается)
                got = fr.evaluate(f"(R) => new Promise(ok => {{ {chart} c.setResolution(R, () => ok(c.resolution())); setTimeout(() => ok('?'), 12000); }})", res)
                pg.wait_for_timeout(6000)
                if got != res:
                    print(f"{sym}: ТФ {tf}: график ответил {got}")
            except Exception as e:  # noqa: BLE001
                print(f"{sym}: ТФ {tf} не выставлен: {type(e).__name__}"); continue
            now = int(time.time())
            try:
                fr.evaluate(f"(R) => {{ {chart} return c.setVisibleRange({{from: R[0], to: R[1]}}); }}", [now - days * 86400, now])
            except Exception as e:  # noqa: BLE001
                print(f"{sym}: период {days} дн не выставлен: {type(e).__name__}")
            pg.wait_for_timeout(7000)
            pg.mouse.move(1695, 1995)
            out = OUT / f"{sym[:-4]}_{kind}_{tf}.png"
            pg.screenshot(path=str(out))
            print("снимок", out.name)
        ctx.close()
    shutil.rmtree(PROF, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
