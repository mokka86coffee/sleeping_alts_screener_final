#!/usr/bin/env python3
"""СБОР С TRADINGVIEW DESKTOP (03.10, владелец: «изучай TV, смотри всех лидеров, что были, и думай, как точнее определять, что пойдёт»; Binance не нагружать).
Через порт отладки 9222 (мост tradingview-mcp удалён): на активном графике по очереди ставит символ и таймфрейм и читает из модели графика бары и ряды
индикаторов владельца — Open Interest, Funding Rate, Liquidations (лонги/шорты), Klinger Oscillator, Vortex. Пишет claude/research/tvd/<SYM>_<TF>.json.
    .venv/bin/python claude/research/tv_collect.py 1D [SYM ...]      — без списка: все BINANCE:*USDT.P из скринера TV (scratchpad tv_scan.json)
По окончании возвращает на график символ и таймфрейм, которые стояли у владельца."""
import asyncio, json, sys, time, urllib.request, websockets
from pathlib import Path
OUT = Path(__file__).parent / "tvd"; OUT.mkdir(exist_ok=True)
JS = r"""
(async (sym, res) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const c = window.TradingViewApi.activeChart();
  if (c.resolution() !== res) { await new Promise(r => { let d = false; c.setResolution(res, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 9000); }); }
  if (c.symbol() !== sym) { await new Promise(r => { let d = false; c.setSymbol(sym, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 12000); }); }
  const m = window.TradingViewApi._activeChartWidgetWV.value()._chartWidget.model();
  const find = n => m.model().dataSources().find(s => s.metaInfo && s.data && (s.metaInfo().description || '') === n);
  const lastT = () => { const b = m.mainSeries().bars(); const v = b.valueAt(b.lastIndex()); return v ? v[0] : null; };
  for (let i = 0; i < 45; i++) {
    await sleep(250);
    const oi = find('Open Interest'), lq = find('Liquidations'), t = lastT();
    const ok = s => { if (!s) return false; const d = s.data(); const li = d.lastIndex(); const v = li != null ? d.valueAt(li) : null; return v && v[0] === t; };
    if (t && ok(oi) && ok(lq)) break;
  }
  const dump = (s, idx) => { if (!s) return []; const d = s.data(); const a = [], f = d.firstIndex(), l = d.lastIndex(); if (f == null || l == null) return a;
    for (let i = f; i <= l; i++) { const v = d.valueAt(i); if (v) a.push([v[0]].concat(idx.map(j => v[j]))); } return a; };
  const b = m.mainSeries().bars(); const bars = []; for (let i = b.firstIndex(); i <= b.lastIndex(); i++) { const v = b.valueAt(i); if (v) bars.push(Array.from(v).slice(0, 6)); }
  return { sym: m.mainSeries().symbol(), res: c.resolution(), bars, oi: dump(find('Open Interest'), [1]), fund: dump(find('Funding Rate'), [1]), liq: dump(find('Liquidations'), [1, 2]),
           ko: dump(find('Klinger Oscillator'), [1, 2]), vi: dump(find('Vortex Indicator'), [1, 2]) };
})(%s, %s)
"""
def page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)):
        if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""): return t["webSocketDebuggerUrl"]
    raise SystemExit("вкладка графика TradingView не найдена")
async def ev(ws, js, _id=[0]):
    _id[0] += 1; i = _id[0]
    await ws.send(json.dumps({"id": i, "method": "Runtime.evaluate", "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
    while True:
        m = json.loads(await asyncio.wait_for(ws.recv(), 60))
        if m.get("id") == i: return ((m.get("result") or {}).get("result") or {}).get("value")
async def main(res, syms, force):
    async with websockets.connect(page(), max_size=128 * 1024 * 1024) as ws:
        was = await ev(ws, "(()=>{const c=window.TradingViewApi.activeChart(); return [c.symbol(), c.resolution()]})()")
        print("на графике было:", was, flush=True); t0 = time.time(); n = 0
        try:
            for k, s in enumerate(syms):
                f = OUT / f"{s.split(':')[1]}_{res}.json"
                if f.exists() and not force and time.time() - f.stat().st_mtime < 20 * 3600: continue
                try:
                    d = await ev(ws, JS % (json.dumps(s), json.dumps(res)))
                except Exception as e:  # noqa: BLE001
                    print(f"{s}: сбой {type(e).__name__}", flush=True); continue
                if not d or not d.get("bars") or d.get("sym") != s:
                    print(f"{s}: нет данных ({(d or {}).get('sym')})", flush=True); continue
                f.write_text(json.dumps(d)); n += 1
                if n % 25 == 0: print(f"{k + 1}/{len(syms)} · записано {n} · {time.time() - t0:.0f} с · {s} баров {len(d['bars'])} oi {len(d['oi'])} liq {len(d['liq'])}", flush=True)
        finally:
            if was: await ev(ws, JS % (json.dumps(was[0]), json.dumps(was[1])))
            print(f"готово: записано {n} за {time.time() - t0:.0f} с; график возвращён на {was}", flush=True)
if __name__ == "__main__":
    a = sys.argv[1:]; force = "--force" in a; a = [x for x in a if x != "--force"]; res = a[0] if a else "1D"; syms = a[1:]
    if not syms:
        import glob
        p = sorted(glob.glob("/private/tmp/claude-501/-Users-evgenijminko-Work-random-python/*/scratchpad/tv_scan.json"), key=lambda x: -Path(x).stat().st_mtime)[0]
        syms = [r["sym"] for r in json.load(open(p))]
    syms = [x if ":" in x else f"BINANCE:{x.upper()}{'' if x.upper().endswith('USDT.P') else 'USDT.P'}" for x in syms]
    asyncio.run(main(res, syms, force))
