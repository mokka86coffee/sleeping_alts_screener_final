#!/usr/bin/env python3
"""СНИМКИ ГРАФИКА ВЛАДЕЛЬЦА В TRADINGVIEW DESKTOP (05.10 владелец: «разбирай сделки бота на tradingview… каждую монету отдельно на разных таймфреймах»).
Через порт отладки 9222 ставит на активном графике монету и таймфрейм, при необходимости окно по времени, и снимает экран — с раскладкой и индикаторами
владельца (пузыри, интерес, фандинг, ликвидации). В конце возвращает символ и таймфрейм, которые стояли. Торговли и Binance не касается.
    .venv/bin/python claude/research/tv_shot.py ПАПКА SYM:TF[:от_часов_назад[:до_часов_назад]] ...
    пример: tv_shot.py /tmp/x MOVR:240 MOVR:60:96:0 MOVR:15:30:0"""
import asyncio, base64, json, sys, time, urllib.request, websockets
from pathlib import Path

SET = r"""
(async (sym, res, frm, to) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const c = window.TradingViewApi.activeChart();
  if (c.resolution() !== res) { await new Promise(r => { let d = false; c.setResolution(res, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 9000); }); }
  if (c.symbol() !== sym) { await new Promise(r => { let d = false; c.setSymbol(sym, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 12000); }); }
  await sleep(1800);
  if (frm) { try { await c.setVisibleRange({ from: frm, to: to }, { percentRightMargin: 6 }); } catch (e) {} await sleep(1500); }
  return [c.symbol(), c.resolution()];
})(%s, %s, %s, %s)
"""


def page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)):
        if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise SystemExit("вкладка графика TradingView не найдена")


async def call(ws, method, params, _id=[0]):
    _id[0] += 1; i = _id[0]
    await ws.send(json.dumps({"id": i, "method": method, "params": params}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 60))
        if m.get("id") == i:
            return m.get("result") or {}


async def ev(ws, js):
    r = await call(ws, "Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": True})
    return (r.get("result") or {}).get("value")


async def main(out: Path, jobs: list):
    out.mkdir(parents=True, exist_ok=True)
    async with websockets.connect(page(), max_size=256 * 1024 * 1024) as ws:
        was = await ev(ws, "(()=>{const c=window.TradingViewApi.activeChart(); const r=c.getVisibleRange(); return [c.symbol(), c.resolution(), r.from, r.to]})()")
        print("на графике было:", was[:2], flush=True)
        try:
            for j in jobs:
                p = j.split(":"); sym = p[0].upper(); res = p[1]
                full = sym if ":" in sym else f"BINANCE:{sym}{'' if sym.endswith('USDT.P') else 'USDT.P'}"
                now = time.time(); frm = int(now - float(p[2]) * 3600) if len(p) > 2 else 0; to = int(now - float(p[3]) * 3600) if len(p) > 3 else int(now)
                got = await ev(ws, SET % (json.dumps(full), json.dumps(res), frm, to))
                if not got or got[0] != full:
                    print(f"{j}: монета не встала ({got})", flush=True); continue
                r = await call(ws, "Page.captureScreenshot", {"format": "jpeg", "quality": 72})
                f = out / f"{sym.replace('USDT.P', '')}_{res}{'_' + p[2] if len(p) > 2 else ''}.jpg"
                f.write_bytes(base64.b64decode(r["data"])); print(f"{j}: {f.name} {f.stat().st_size // 1024} КБ", flush=True)
        finally:
            if was:
                await ev(ws, SET % (json.dumps(was[0]), json.dumps(was[1]), int(was[2]), int(was[3])))
            print("график возвращён на", was[:2], flush=True)


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2:]))
