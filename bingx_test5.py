#!/usr/bin/env python3
"""ТЕСТ 5 ОРДЕРОВ НА BINGX СО СТОПАМИ (30.09, владелец: «5 ордеров открыть со стопами со всем на 2 доллара на позицию … просто проверить, где и что, чтобы бота откалибровать»).
Запускает ТЫ (я реальные ордера не отправляю). По умолчанию — ДЕМО (VST, виртуальные деньги, свои демо-ключи в bingx_config.json). Реальный счёт — только с флагом --live и словом-подтверждением.
Для каждой из 5 монет: рыночный вход на `size_usd` (по умолчанию 2 $), стоп на бирже, затем проверка — позиция есть, стоп стоит, цена исполнения против цены сигнала (проскальзывание),
комиссия. Отчёт — output/bingx_test5.md (по монетам: что сработало, что нет, ошибки биржи). --close — закрыть все тестовые позиции и снять стопы.
    .venv/bin/python bingx_test5.py                  # 5 ордеров в ДЕМО (монеты — из списка ниже или --coins ARX,DOOD,...)
    .venv/bin/python bingx_test5.py --close          # закрыть тестовые позиции
    .venv/bin/python bingx_test5.py --live           # то же на РЕАЛЬНОМ счёте (спросит подтверждение)
"""
import json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path
import bingx_trader as bx

COINS = ['DOOD', 'MEW', 'QNT', 'PHAROS', 'MET']         # только с открытой торговлей по API (apiStateOpen=true), разные по ликвидности; поменяй: --coins=A,B,C,D,E
live = "--live" in sys.argv
arg = next((a for a in sys.argv if a.startswith("--coins=")), None)
coins = arg.split("=")[1].split(",") if arg else COINS
c = bx.cfg(); c["mode"] = "live" if live else "demo"; c["enabled"] = True
if c["size_usd"] is None: c["size_usd"] = 2.0
c["max_open"] = max(int(c["max_open"] or 0), 5)
if not (c["api_key"] and c["api_secret"]):
    sys.exit("нет ключей: заполни bingx_config.json (api_key, api_secret). Для демо — ключи демо-счёта BingX (VST)")
if live and input("РЕАЛЬНЫЙ счёт: 5 позиций по %s $. Введи LIVE для подтверждения: " % c["size_usd"]).strip() != "LIVE":
    sys.exit("отменено")
if "--close" in sys.argv:
    for sym in list(bx.state()["open"]):
        print(sym, bx.close_position(sym, c=c))
    sys.exit(0)
def bin_px(sym):
    return float(json.load(urllib.request.urlopen(f"https://fapi.binance.com/fapi/v1/ticker/price?symbol={sym}", timeout=10))["price"])
rows = []
for cn in coins:
    sym = cn + "USDT"; ct = bx.contracts().get(sym)
    if not ct:
        rows.append((cn, "нет на BingX")); continue
    try: sig = bin_px(sym)
    except Exception: sig = None
    t0 = time.time()
    r = bx.open_position(sym, 1, sig or 0, why="тест 5 ордеров", c=c, size_usd=float(c["size_usd"]))
    dt = round(time.time() - t0, 1)
    if not r["ok"]:
        rows.append((cn, f"вход не прошёл: {r['why']}")); continue
    slip = (r["entry"] / sig - 1) * 100 if sig else None
    rows.append((cn, f"вход ok: {r['qty']} @ {r['entry']} (цена Binance {sig}, проскальзывание {slip:+.3f}%), стоп {r['stop']} {'ок' if r['stop_ok'] else 'НЕ ПОСТАВЛЕН: ' + r['stop_msg']}, {dt} с"))
    time.sleep(0.5)
pos = bx.request("GET", "/openApi/swap/v2/user/positions", c=c); orders = bx.request("GET", "/openApi/swap/v2/trade/openOrders", c=c)
have = {p.get("symbol") for p in (pos.get("data") or [])}; stops = [o for o in ((orders.get("data") or {}).get("orders") or []) if "STOP" in str(o.get("type"))]
md = [f"# Тест 5 ордеров BingX — {datetime.now():%d.%m %H:%M}, режим {c['mode']}, {c['size_usd']} $ на позицию", ""]
for cn, msg in rows: md.append(f"- {cn}: {msg}")
md += ["", f"позиции на бирже: {sorted(have)}", f"стоп-ордера на бирже: {len(stops)}", "", "Закрыть: `.venv/bin/python bingx_test5.py --close`" + (" --live" if live else "")]
Path("output").mkdir(exist_ok=True); Path("output/bingx_test5.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md))
