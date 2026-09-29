#!/usr/bin/env python3
"""СНИМКИ COINGLASS ПО ВСПЛЕСКАМ СБОРЩИКА (29.09, владелец: «проверки с теми же условиями на коингласс, те же индикаторы, те же таймфреймы»).
Берёт всплески из output/spike_log.jsonl (spike_collector.py), которым уже больше 1 часа и снимков ещё нет; Coinglass Binance_<монета>, «мои» индикаторы + ликвидации + базис,
1D / 6h / 1h / 30m, вертикаль — бар всплеска, горизонталь — цена всплеска → collector/shots/, цифры графика → ../cgx/ (как у сделок бота и сигналов канала).
    .venv/bin/python claude/research/spikes/coll_cg.py [N]      # не больше N всплесков за запуск (по умолчанию 20), самые свежие первыми
"""
import json, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
HERE = Path(__file__).parent; ROOT = HERE.parents[2]; sys.path.insert(0, str(HERE.parent))
import cg_review as R
L = timezone(timedelta(hours=3))
N = int(sys.argv[1]) if len(sys.argv) > 1 else 20
OUT = HERE / "collector"; (OUT / "shots").mkdir(parents=True, exist_ok=True)
if not (ROOT / "output" / "spike_log.jsonl").exists():
    print("журнала всплесков ещё нет"); raise SystemExit(0)
spikes = [json.loads(l) for l in open(ROOT / "output" / "spike_log.jsonl") if '"kind": "spike"' in l]
now = datetime.now().timestamp(); B = []
for s in sorted(spikes, key=lambda s: -s["t_ms"]):
    t = s["t_ms"] / 1000 + 180
    if now - t < 3600: continue
    tid = f"{s['sym'][:-4]}_{datetime.fromtimestamp(t, L):%m%d_%H%M}"
    if all((OUT / "shots" / f"{tid}_{tf}.png").exists() for tf in ("1D", "360", "60", "30")): continue
    B.append(dict(sym=s["sym"], side=1, t_in=t, t_out=t + 1, px_in=s["px"], px_out=0, res=0, why="всплеск", book="сборщик", rule="",
                  label=f"ВСПЛЕСК {s['bar']}% ×{s['x']:.0f}"))
    if len(B) >= N: break
print(f"к съёмке {len(B)}", flush=True)
if B:
    json.dump(B, open(OUT / "batch.json", "w"), ensure_ascii=False)
    R.trades = lambda: B; R.RD = OUT / "shots"
    R.PROF = ROOT / "output" / "cg_profile_coll"
    sys.argv = [sys.argv[0]]
    raise SystemExit(R.main())
