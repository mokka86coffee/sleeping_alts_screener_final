#!/usr/bin/env python3
"""ПОЛНАЯ ДНЕВНАЯ ИСТОРИЯ С TRADINGVIEW DESKTOP (26.10.2026, владелец: «по годам посчитать по росту от исторического дна в 30-50-100 раз сколько монет», «начиная с 20-го»).
Через порт 9222: на графике ставит символ на 1D и догружает историю requestMoreData, пока первый бар не перестанет сдвигаться. Пишет только бары
claude/research/tvd_full/<SYM>.json {sym, bars:[[t,o,h,l,c,v]]}. Делистнутых монет здесь нет — список берётся из claude/research/tvd/*USDT.P_1D.json.
    .venv/bin/python claude/research/tv_full_hist.py [SYM ...]   — без списка все; уже собранные пропускает"""
import asyncio, glob, json, sys, time, urllib.request, websockets
from pathlib import Path
OUT = Path(__file__).parent / "tvd_full"; OUT.mkdir(exist_ok=True)
JS = r"""
(async (sym) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const c = window.TradingViewApi.activeChart();
  if (c.resolution() !== '1D') await new Promise(r => { c.setResolution('1D', r); setTimeout(r, 8000); });
  if (c.symbol() !== sym) await new Promise(r => { c.setSymbol(sym, r); setTimeout(r, 12000); });
  await sleep(1200);
  const ms = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model().mainSeries();
  let first = null, same = 0;
  for (let k = 0; k < 40 && same < 3; k++) {
    ms.requestMoreData(2000); await sleep(900);
    const b = ms.bars(), f = b.firstIndex() != null ? b.valueAt(b.firstIndex())[0] : null;
    if (f === first) same++; else { first = f; same = 0; }
  }
  const b = ms.bars(), bars = [];
  for (let i = b.firstIndex(); i <= b.lastIndex(); i++) { const v = b.valueAt(i); if (v) bars.push(Array.from(v).slice(0, 6)); }
  return { sym: ms.symbol(), bars };
})(%s)
"""
def page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)):
        if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""): return t["webSocketDebuggerUrl"]
async def ev(ws, js, _id=[0]):
    _id[0] += 1; i = _id[0]
    await ws.send(json.dumps({"id": i, "method": "Runtime.evaluate", "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 120))
        if m.get("id") == i: return m.get("result", {}).get("result", {}).get("value")
async def main(syms):
    async with websockets.connect(page(), max_size=256 * 1024 * 1024) as ws:
        t0 = time.time(); n = 0
        for k, s in enumerate(syms):
            f = OUT / f"{s}.json"
            if f.exists(): continue
            try:
                d = await ev(ws, JS % json.dumps(f"BINANCE:{s}USDT.P"))
            except Exception as e:  # noqa: BLE001
                print(f"{s}: сбой {type(e).__name__}", flush=True); continue
            if not d or not d.get("bars") or d.get("sym") != f"BINANCE:{s}USDT.P":
                print(f"{s}: нет данных ({(d or {}).get('sym')})", flush=True); continue
            f.write_text(json.dumps(d)); n += 1
            if n % 20 == 0: print(f"{k + 1}/{len(syms)} · {n} · {time.time() - t0:.0f} с", flush=True)
        print(f"готово {n} за {time.time() - t0:.0f} с", flush=True)
if __name__ == "__main__":
    syms = sys.argv[1:] or sorted(Path(p).name.split("USDT.P")[0] for p in glob.glob(str(Path(__file__).parent / "tvd" / "*USDT.P_1D.json")))
    asyncio.run(main(syms))
