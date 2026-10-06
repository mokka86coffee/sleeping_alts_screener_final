#!/usr/bin/env python3
"""КЛАСТЕРЫ С ГРАФИКА ВЛАДЕЛЬЦА В TRADINGVIEW DESKTOP (07.10, владелец показал Volume footprint по MOVR: «вот кластера», «включил», «разбирай»,
«прямо возьми все пампы за последние 7 дней и посмотри что и где закончилось и почему»).
График должен быть в режиме Volume footprint. Через порт отладки 9222 ставит монету и таймфрейм, ждёт загрузки кластеров и читает из служебного
индикатора Footprint по каждой свече: покупки и продажи по рынку на каждом уровне цены. Пишет claude/research/tvd/<SYM>_fp<TF>.json:
bars [t, o, h, l, c, v], fp [{i, poc, val, vah, buy, sell, levels [[цена, покупки, продажи], ...]}]. В конце возвращает монету и таймфрейм владельца.
С Binance напрямую ничего не запрашивается. Только чтение.
    .venv/bin/python claude/research/tv_footprint.py 30 MOVR RLC ..."""
import asyncio, fcntl, json, sys, time, urllib.request, websockets
from pathlib import Path
OUT = Path(__file__).parent / "tvd"; OUT.mkdir(exist_ok=True)


def tv_lock():
    """один скрипт у графика за раз (сборщик кластеров и сигнал «где продавать» переключают монету на одном графике) — ждёт своей очереди"""
    f = open(OUT / ".tv.lock", "w"); fcntl.flock(f, fcntl.LOCK_EX); return f
JS = r"""
(async (sym, res) => {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const api = window.TradingViewApi; const c = api.activeChart();
  if (c.chartType() !== 17) return JSON.stringify({err: 'график не в режиме Volume footprint (тип ' + c.chartType() + ')'});
  if (c.resolution() !== res) { await new Promise(r => { let d = false; c.setResolution(res, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 9000); }); }
  if (c.symbol() !== sym) { await new Promise(r => { let d = false; c.setSymbol(sym, () => { d = true; r(); }); setTimeout(() => { if (!d) r(); }, 12000); }); }
  const m = api._activeChartWidgetWV.value()._chartWidget.model();
  let fp = null, bi = [];
  for (let k = 0; k < 60; k++) {
    await sleep(300);
    const ms = m.mainSeries(); bi = ms.bars()._items || [];
    const b = (ms._studyBindings._bindings || []).find(x => x && x._study && x._study.metaInfo && /Footprint/.test(x._study.metaInfo().id || ''));
    const pc = b && b._study._graphics && b._study._graphics._primitivesCollection;
    fp = pc && pc.footprints && pc.footprints.get('footprint');
    if (c.symbol() === sym && fp && bi.length > 50 && fp._primitiveById.size >= bi.length - 2) break;
  }
  if (c.symbol() !== sym) return JSON.stringify({err: 'символ не встал: ' + c.symbol()});
  const out = {sym: c.symbol(), res: c.resolution(), bars: bi.map(x => Array.from(x.value)), fp: []};
  if (fp) for (const p of fp._primitiveById.values()) {
    let buy = 0, sell = 0; const lv = [];
    for (const l of p.levels || []) { buy += l.buyVolume || 0; sell += l.sellVolume || 0; lv.push([l.price, Math.round(l.buyVolume || 0), Math.round(l.sellVolume || 0)]); }
    out.fp.push({i: p.index, poc: p.poc, val: p.val, vah: p.vah, buy, sell, levels: lv});
  }
  return JSON.stringify(out);
})(%s, %s)
"""


def page():
    for t in json.load(urllib.request.urlopen("http://127.0.0.1:9222/json", timeout=5)):
        if t.get("type") == "page" and "tradingview.com/chart" in t.get("url", ""):
            return t["webSocketDebuggerUrl"]
    raise SystemExit("вкладка графика TradingView не найдена")


async def ev(ws, expr, _id=[0]):
    _id[0] += 1
    await ws.send(json.dumps({"id": _id[0], "method": "Runtime.evaluate", "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
    while True:
        r = json.loads(await ws.recv())
        if r.get("id") == _id[0]:
            return r.get("result", {}).get("result", {}).get("value")


async def main(res, syms):
    _lk = tv_lock()
    async with websockets.connect(page(), max_size=None) as ws:
        was = json.loads(await ev(ws, "JSON.stringify([window.TradingViewApi.activeChart().symbol(), window.TradingViewApi.activeChart().resolution()])"))
        print("на графике было:", was)
        for s in syms:
            full = s if ":" in s else f"BINANCE:{s}USDT.P"
            v = await ev(ws, JS % (json.dumps(full), json.dumps(res)))
            try:
                d = json.loads(v)
            except (TypeError, ValueError):
                print(f"{s}: нет ответа"); continue
            if d.get("err"):
                print(f"{s}: {d['err']}"); continue
            n = len(d["bars"]); d["fp"].sort(key=lambda x: x["i"])
            # сверка: кластер i ↔ свеча i, если сумма покупок и продаж сходится с объёмом свечи
            ok = sum(1 for f in d["fp"] if f["i"] < n and d["bars"][f["i"]][5] and abs((f["buy"] + f["sell"]) / d["bars"][f["i"]][5] - 1) < 0.05)
            d["aligned"] = ok
            (OUT / f"{s}_fp{res}.json").write_text(json.dumps(d), encoding="utf-8")
            print(f"{s}: свечей {n}, кластеров {len(d['fp'])}, сошлось с объёмом свечи {ok}", flush=True)
        await ev(ws, JS % (json.dumps(was[0]), json.dumps(was[1])))
        print("график возвращён на", was)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1], sys.argv[2:]))
