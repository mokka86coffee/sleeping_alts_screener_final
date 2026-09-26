"""ТИК КАЖДЫЕ ПОЛЧАСА (26.09, план владельца на 2 дня): что нового — входы/выходы книг с прошлого тика, монеты с ходом ≥ +40% за сутки или 48 ч, которых
мы не увидели (не было места в очереди за 48 ч до, не было в звёздах, нет входа книг), состояние доски. Состояние тика — claude/research/tick_state.json.
    .venv/bin/python claude/research/tick.py            # печатает отчёт; секции ВХОДЫ / НЕ УВИДЕЛИ пустые → тихо
"""
import json, sys, time, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
L = timezone(timedelta(hours=3)); ST = Path(__file__).with_name("tick_state.json")
state = json.loads(ST.read_text()) if ST.exists() else {"last": 0, "reported": {}}
now = time.time(); last = float(state.get("last") or (now - 1800))
def g(u): return json.loads(urllib.request.urlopen(u, timeout=20).read())
ours = sorted(p.stem.upper() + "USDT" for p in (ROOT / "cq_v2" / "intraday").glob("*.jsonl"))
# ── 1. новые события книг ──
books = {"картина": "paper_sight", "3 в первых": "paper_first3", "толпа": "paper_crowd", "конец": "paper_end", "интерес": "paper_interest", "второй ход": "paper_second"}
ev = []
for name, f in books.items():
    p = ROOT / "output" / f"{f}.jsonl"
    if not p.exists(): continue
    for line in p.read_text(encoding="utf-8").splitlines()[-400:]:
        try: r = json.loads(line)
        except ValueError: continue
        if r.get("kind") not in ("entry", "exit", "armed"): continue
        if float(r.get("at") or 0) <= last: continue
        ev.append((float(r["at"]), name, r))
ev.sort(key=lambda x: x[0])
# ── 2. бегуны ≥ +40% за сутки по тикеру Binance (все USDT-перпы) и ≥ +40% за 48 ч по нашим ──
tk = g("https://fapi.binance.com/fapi/v1/ticker/24hr")
movers = [(x["symbol"], float(x["priceChangePercent"]), float(x["quoteVolume"])) for x in tk if x["symbol"].endswith("USDT") and float(x["priceChangePercent"]) >= 40 and float(x["quoteVolume"]) >= 2e6]
movers.sort(key=lambda x: -x[1])
# ── 3. кого видели: место в очереди за 48 ч до сейчас, звёзды, входы книг ──
seen_q = {}
since = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
for line in (ROOT / "output" / "queue_log.jsonl").read_text(encoding="utf-8").splitlines()[-40000:]:
    try: r = json.loads(line)
    except ValueError: continue
    if r.get("at", "") < since or not r.get("place"): continue
    s = r["sym"]; seen_q[s] = min(seen_q.get(s, 99), int(r["place"]))
stars = {}
try:
    sj = json.loads((ROOT / "output" / "stars.json").read_text(encoding="utf-8"))
    stars = {x["sym"]: x["g"] for x in sj.get("stars", [])}
except Exception: pass
book_syms = set()
for name, f in books.items():
    p = ROOT / "output" / f"{f}.jsonl"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines()[-2000:]:
            if '"kind": "entry"' in line:
                try: book_syms.add(json.loads(line)["sym"])
                except Exception: pass
nm = {}
try: nm = json.loads((ROOT / "output" / "near_move.json").read_text(encoding="utf-8")).get("coins") or {}
except Exception: pass
# ── 4. доска ──
board = []
try:
    import render_intro as ri
    board = ri._board_state_notes()
except Exception as e: board = [("доска", "—", f"не собралась: {e}")]
# ── отчёт ──
print(f"ТИК {datetime.now(L).strftime('%d.%m %H:%M')} (с {datetime.fromtimestamp(last, L).strftime('%H:%M')})")
print("ДОСКА:", " | ".join(f"{a}: {c}" for a, b, c in board) or "—")
print("ВХОДЫ/ВЫХОДЫ КНИГ:" if ev else "ВХОДЫ/ВЫХОДЫ КНИГ: нет")
for at, name, r in ev:
    k = r["kind"]; s = r["sym"][:-4]
    if k == "entry": print(f"  {datetime.fromtimestamp(at, L).strftime('%H:%M')} {name} · ВХОД {s} по {r.get('px')} · {str(r.get('rule') or '')[:110]}")
    elif k == "exit": print(f"  {datetime.fromtimestamp(at, L).strftime('%H:%M')} {name} · выход {s} · {r.get('result_pct')}% · {str(r.get('why_exit') or r.get('why') or '')[:90]}")
    else: print(f"  {datetime.fromtimestamp(at, L).strftime('%H:%M')} {name} · {s} стоп в ноль")
missed, seen = [], []
for s, pct, qv in movers:
    tag = ("наша" if s in ours else "не наша")
    q = seen_q.get(s); st = stars.get(s); bk = s in book_syms
    sc = (nm.get(s) or {}).get("score"); grp = (nm.get(s) or {}).get("group")
    line = f"{s[:-4]:<10} +{pct:.0f}% за сутки · оборот {qv/1e6:.0f}M$ · {tag} · очередь {('место %d' % q) if q else 'нет'} · звёзды {('группа %s' % st) if st is not None else 'нет'} · книги {'да' if bk else 'нет'} · near_move {sc}/{grp}"
    if s in ours and not q and st is None and not bk: missed.append((s, line))
    else: seen.append(line)
print("БЕГУНЫ ≥ +40% за сутки:", len(movers))
for l in seen: print("  видели:", l)
print("НЕ УВИДЕЛИ:" if missed else "НЕ УВИДЕЛИ: нет")
for s, l in missed:
    flag = "" if state["reported"].get(s, 0) < now - 24 * 3600 else " (уже разбирали)"
    print("  " + l + flag)
    if not flag: state["reported"][s] = now
state["last"] = now; ST.write_text(json.dumps(state))
