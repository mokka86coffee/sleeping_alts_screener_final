#!/usr/bin/env python3
"""УБЫТОЧНЫЕ СДЕЛКИ БЫСТРОГО БОТА НА COINGLASS (28.09, владелец: «заходи по каждой убыточной сделке в Coinglass и смотри, что там происходило,
почему было выбрано неверное направление и что можно поправить; если по логике стратегии всё было верно, но цена пошла не туда — напиши,
в какое время было исключение»). Список — claude/research/losers.json (свежие первыми). Набор индикаторов — «мои» (профиль владельца +
ликвидации и базис, без заявок), 15m, окно: сутки до входа … 12 ч после выхода; вход/выход — вертикали, цены входа/выхода — горизонтали.

    .venv/bin/python claude/research/cg_trades.py 0 10        # сделки с 0-й по 9-ю → claude/research/cg/loss_<№>_<монета>.png
"""
from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
SRC, PROF = ROOT / "output" / "cg_profile", ROOT / "output" / "cg_profile_trades"
OUT = Path(__file__).with_name("cg")
CHART = "const a = window.tradingViewApi; const c = typeof a.activeChart === 'function' ? a.activeChart() : a.chart();"


def main() -> int:
    a, b = int(sys.argv[1]), int(sys.argv[2])
    L = json.load(open(Path(__file__).with_name("losers.json")))[a:b]
    OUT.mkdir(exist_ok=True)
    shutil.rmtree(PROF, ignore_errors=True); shutil.copytree(SRC, PROF, ignore=shutil.ignore_patterns("Singleton*", "*.lock"))
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(PROF), headless=True, viewport={"width": 1700, "height": 1500})
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        for i, x in enumerate(L, start=a):
            try:
                pg.goto(f"https://www.coinglass.com/tv/Binance_{x['sym']}"); pg.wait_for_timeout(14000)
                fr = next(f for f in pg.frames if f != pg.main_frame)
                fr.evaluate(f"() => {{ {CHART} for (const s of c.getAllStudies()) if (/Bid & Ask/.test(s.name)) c.removeEntity(s.id); }}")
                for n in ("Aggregated Liquidations", "Basis"):
                    try:
                        pg.get_by_text("CoinGlass - Indicators", exact=True).first.click(); pg.wait_for_timeout(1200)
                        pg.get_by_text(n, exact=True).first.click(); pg.wait_for_timeout(1200); pg.keyboard.press("Escape")
                    except Exception:  # noqa: BLE001
                        pass
                fr.evaluate(f"(R) => new Promise(ok => {{ {CHART} c.setResolution(R, () => ok(1)); setTimeout(() => ok(0), 10000); }})", "15")
                pg.wait_for_timeout(5000)
                t0, t1 = int(x["t_in"] - 86400), int(min(time.time(), x["t_out"] + 12 * 3600))
                fr.evaluate(f"(R) => {{ {CHART} c.setVisibleRange({{from: R[0], to: R[1]}}); }}", [t0, t1])
                pg.wait_for_timeout(4000)
                fr.evaluate(f"""(X) => {{ {CHART}
                  const v = (t, col) => c.createShape({{time: t}}, {{shape: 'vertical_line', lock: true, disableSelection: true, overrides: {{linecolor: col, linewidth: 2, linestyle: 2}}}});
                  const h = (pr, col, txt) => c.createShape({{time: X.t_in, price: pr}}, {{shape: 'horizontal_line', lock: true, disableSelection: true, text: txt,
                      overrides: {{linecolor: col, linewidth: 1, showLabel: true, textcolor: col, horzLabelsAlign: 'left', fontsize: 13}}}});
                  v(Math.floor(X.t_in), '#f5a623'); v(Math.floor(X.t_out), '#ffffff');
                  h(X.px_in, '#f5a623', (X.side < 0 ? 'ШОРТ ' : 'ЛОНГ ') + X.px_in); if (X.px_out) h(X.px_out, '#ffffff', 'ВЫХ ' + X.px_out + ' ' + X.res + '%'); }}""", x)
                pg.wait_for_timeout(2500); pg.mouse.move(1695, 1495)
                out = OUT / f"loss_{i:02d}_{x['sym'][:-4]}.png"
                pg.screenshot(path=str(out)); print("снимок", out.name, flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"{i} {x['sym']}: не снят — {type(e).__name__}: {str(e)[:80]}", flush=True)
        ctx.close()
    shutil.rmtree(PROF, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
