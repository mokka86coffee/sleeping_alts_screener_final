#!/usr/bin/env python3
"""ЭКРАН «ЛЕСТНИЦА» ПО ЛИДЕРАМ (02.10, владелец по MINA/ZRO/ALICE: «выбили одну сторону, откупили слив, цена не вернулась — улетели»; «может ещё что добавишь, и с лидерами попробуем связать»).
Черновик признаков R45 по данным Binance (бесплатно) для лидеров по пампу (output/pump_leaders.json), текущих первых (output/queue_state.json top/cand), звёзд владельца и трёх эталонов (MINA, ZRO, ALICE):
  run90 — ×от минимума 90 дн; spike — день за 30 дн с крупнейшим диапазоном (h/l) × объёмом (прокси выброса одной стороны); days_since — дней с него;
  held — закрытие сейчас выше минимума дня выброса (цена не вернулась); drawdown_after — макс. откат от максимума после выброса;
  fund_neg14 — доля отрицательных фандингов за 14 дн (шорты платят); oi_since — интерес с дня выброса, %; oi7 — интерес за 7 дн, %; flat7 — диапазон за 7 дн (h/l−1), %.
Только запись (claude/research/ladder_screen.md); порогов нет — эталоны показывают, как выглядят «да».
    .venv/bin/python claude/research/ladder_screen.py"""
import json, urllib.request, time
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; HERE = Path(__file__).parent; L = timezone(timedelta(hours=3))
def get(u):
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(u, timeout=20))
        except Exception: time.sleep(1)
    return []
P = json.load(open(ROOT / "output/pump_leaders.json")); Q = json.load(open(ROOT / "output/queue_state.json"))
syms = {"MINAUSDT", "ZROUSDT", "ALICEUSDT"} | {k for k, v in P.items() if not v.get("retired_at")} | set(Q.get("top") or []) | set(Q.get("cand") or []) | {s + "USDT" for s in "MON NOM DUSK GTC ZETA MOVR JASMY LYN".split()}
tags = {s: [] for s in syms}
for s in ("MINAUSDT", "ZROUSDT", "ALICEUSDT"): tags[s].append("эталон")
for k, v in P.items():
    if k in tags and not v.get("retired_at"): tags[k].append("лидер по пампу")
for s in (Q.get("top") or []): tags.setdefault(s, []).append("первые")
for s in (Q.get("cand") or []): tags.setdefault(s, []).append("кандидат")
for s in "MON NOM DUSK GTC ZETA MOVR JASMY LYN".split(): tags[s + "USDT"].append("звезда")
def one(sym):
    k = get(f"https://fapi.binance.com/fapi/v1/klines?symbol={sym}&interval=1d&limit=91")
    if len(k) < 35: return None
    h = [float(x[2]) for x in k]; l = [float(x[3]) for x in k]; c = [float(x[4]) for x in k]; v = [float(x[7]) for x in k]
    run90 = c[-1] / min(l)
    w = range(len(k) - 30, len(k) - 1)                                   # 30 дн без сегодняшней свечи
    i = max(w, key=lambda j: (h[j] / l[j] - 1) * v[j])
    spike_day = datetime.fromtimestamp(int(k[i][0]) / 1000, L).strftime("%d.%m"); days_since = len(k) - 1 - i
    held = c[-1] > l[i]; after_hi = max(h[i:]); dd_after = (min(l[i:]) / after_hi - 1) * 100
    fr = get(f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={sym}&limit=42")
    fneg = sum(1 for x in fr if float(x["fundingRate"]) < 0) / max(1, len(fr)) * 100
    oi = get(f"https://fapi.binance.com/futures/data/openInterestHist?symbol={sym}&period=1d&limit=30")
    ov = [float(x["sumOpenInterest"]) for x in oi]
    oi_since = (ov[-1] / ov[max(0, len(ov) - 1 - days_since)] - 1) * 100 if len(ov) > days_since + 1 and ov[max(0, len(ov) - 1 - days_since)] else None
    oi7 = (ov[-1] / ov[-8] - 1) * 100 if len(ov) >= 8 and ov[-8] else None
    flat7 = (max(h[-7:]) / min(l[-7:]) - 1) * 100
    return dict(sym=sym[:-4], run90=run90, spike=spike_day, days=days_since, held=held, dd=dd_after, fneg=fneg, oi_since=oi_since, oi7=oi7, flat7=flat7, ch_since=(c[-1] / c[i] - 1) * 100, tags=", ".join(tags.get(sym, [])))
with ThreadPoolExecutor(6) as ex: R = [r for r in ex.map(one, sorted(syms)) if r]
R.sort(key=lambda r: (0 if "эталон" in r["tags"] else 1, -r["fneg"]))
f = lambda v, s="%.0f": "—" if v is None else s % v
md = [f"# Экран «лестница» по лидерам ({datetime.now(L):%d.%m %H:%M})", "", "Признаки R45 по Binance (черновик, порогов нет): эталоны MINA/ZRO/ALICE сверху — так выглядит «да». Только запись.", "",
      "| монета | кто | ×от мин 90д | день выброса | дней | цена выше низа выброса | ход с выброса | откат после | фандинг<0, 14 дн | интерес с выброса | интерес 7д | размах 7д |", "|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in R:
    md.append(f"| {r['sym']} | {r['tags']} | ×{r['run90']:.1f} | {r['spike']} | {r['days']} | {'да' if r['held'] else 'НЕТ'} | {r['ch_since']:+.0f}% | {r['dd']:.0f}% | {r['fneg']:.0f}% | {f(r['oi_since'],'%+.0f%%')} | {f(r['oi7'],'%+.0f%%')} | {r['flat7']:.0f}% |")
(HERE / "ladder_screen.md").write_text("\n".join(md) + "\n", encoding="utf-8"); print("\n".join(md))
