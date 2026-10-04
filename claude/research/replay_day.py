#!/usr/bin/env python3
"""ПЕРЕСЧЁТ ДНЯ ПО НОВЫМ ПРАВИЛАМ, шаг 2 (03.10 17:00, владелец: «посчитай все сделки, как они бы были сегодня по новым правилам с самого начала суток, и внеси в бота, ошибочные все удали из книги»).
Гоняет НАСТОЯЩИЙ код бота (fast_tier.step, книга «всплеск/вынос») по минувшим суткам, тик раз в 3 минуты, с подменой часов и источников данных на «как было в тот момент»:
  • время: fast_tier.time → поддельные часы;
  • 3-мин свечи: из файла replay_fetch.py (без сети); ещё не закрытая свеча подаётся плоской по цене открытия (без заглядывания вперёд);
  • остальные свечи (1h/4h/1d, спот), интерес и толпа: запрос к Binance с endTime = момент тика; незакрытый бар пересобирается из 3-мин свечей до момента тика;
  • ликвидации (поток OKX+Bybit, cq_v2/liq): события только до момента тика; получасовой архив — только закрытые получасовки; доска 24 ч — из 3-мин свечей на момент тика;
  • файлы бота (книга, журнал, счётчики) — во временной папке; Coinglass и BingX отключены.
Позиции, открытые ДО полуночи и живые в полночь, не пересчитываются: монета занята до фактического выхода (+2 ч паузы). NIGHT (ручной вход по слову владельца) занят весь день.
Книга «пробуждение» не пересчитывается. Фандинг 7 дн (R55) — текущий кэш (на начало суток он немного другой). Ожидающие шорты на полночь не восстановлены (начинаем без них).
    .venv/bin/python claude/research/replay_day.py K3.pkl ПАПКА [ЧЧ:ММ конец]"""
import sys, json, pickle, time as _time, bisect, shutil, statistics as st
from pathlib import Path
from datetime import datetime, timezone, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
L = ft.L; K3P = Path(sys.argv[1]); WD = Path(sys.argv[2]); WD.mkdir(parents=True, exist_ok=True); (WD / "output").mkdir(exist_ok=True)
import os as _os
REAL = ft.BASE_DIR; d0 = datetime.now(L).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
if _os.environ.get("REPLAY_HOURS"):                                      # пересчёт последних N часов: началом считается «сейчас − N ч» (кратно 3 минутам)
    d0 = (_time.time() - float(_os.environ["REPLAY_HOURS"]) * 3600) // 180 * 180
END = d0 + (int(sys.argv[3][:2]) * 3600 + int(sys.argv[3][3:]) * 60 if len(sys.argv) > 3 else 0) if len(sys.argv) > 3 else None
START = d0 + (int(sys.argv[4][:2]) * 3600 + int(sys.argv[4][3:]) * 60) if len(sys.argv) > 4 else d0
pk = pickle.load(open(K3P, "rb")); K3 = pk["K"]; T3 = {s: [int(x[0]) for x in k] for s, k in K3.items()}; FETCH_AT = pk["at"]
if END is None: END = FETCH_AT - 200
class Fake:
    t = d0
    def time(self): return self.t
    def sleep(self, s): pass
    def __getattr__(self, k): return getattr(_time, k)
fake = Fake(); ft.time = fake; real_get = ft.get_json; NC = {}
IVMS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "2h": 7_200_000, "4h": 14_400_000, "1d": 86_400_000}
def k3_asof(sym, now_ms, start=None, end=None, limit=500):
    bars, times = K3[sym], T3[sym]; j = bisect.bisect_right(times, now_ms)
    if end is not None: j = min(j, bisect.bisect_right(times, int(end)))
    lo = bisect.bisect_left(times, int(start)) if start is not None else 0
    out = bars[lo:j]; out = out[:limit] if start is not None else out[-limit:]
    if out and int(out[-1][0]) + 180_000 > now_ms:                       # свеча ещё не закрыта — плоская по открытию
        b = list(out[-1]); b[2] = b[3] = b[4] = b[1]; b[5] = b[7] = b[9] = b[10] = "0"; out = out[:-1] + [b]
    return out
def asof(url, params=None, quiet_400=False, weight=1, timeout=None):
    p = dict(params or {}); now_ms = int(fake.t * 1000)
    if url.endswith("/fapi/v1/klines") or url.endswith("/api/v3/klines"):
        sym, iv = p.get("symbol"), p.get("interval")
        if iv == "3m" and url.endswith("/fapi/v1/klines") and sym in K3:
            return k3_asof(sym, now_ms, p.get("startTime"), p.get("endTime"), int(p.get("limit", 500)))
        q = dict(p); q.setdefault("endTime", now_ms); ivms = IVMS.get(iv, 3_600_000); bucket = 900_000 if ivms <= 3_600_000 else 3_600_000
        key = (url, sym, iv, q.get("limit"), q.get("startTime"), int(q["endTime"]) // bucket)
        if key not in NC: NC[key] = real_get(url, q, quiet_400=True, weight=weight) or []
        r = [list(x) for x in NC[key]]
        r = [x for x in r if int(x[0]) <= now_ms]
        if r and int(r[-1][0]) + ivms > now_ms and url.endswith("/fapi/v1/klines") and sym in K3:   # незакрытый бар — пересобрать из 3-мин свечей до момента тика
            seg = k3_asof(sym, now_ms, start=int(r[-1][0]), limit=1000)
            if seg:
                b = r[-1]; b[1] = seg[0][1]; b[2] = str(max(float(x[2]) for x in seg)); b[3] = str(min(float(x[3]) for x in seg)); b[4] = seg[-1][4]
                for i in (5, 7, 9, 10): b[i] = str(sum(float(x[i]) for x in seg))
        return r
    if "/futures/data/" in url:
        q = dict(p); q.setdefault("endTime", now_ms); key = (url, q.get("symbol"), q.get("period"), q.get("limit"), int(q["endTime"]) // 300_000)
        if key not in NC: NC[key] = real_get(url, q, quiet_400=True, weight=weight) or []
        return [dict(x) for x in NC[key]]
    if url.endswith("/fapi/v1/ticker/price") and p.get("symbol") in K3:
        b = k3_asof(p["symbol"], now_ms, limit=1); return {"symbol": p["symbol"], "price": b[-1][4]} if b else {}
    if url.endswith("/ticker/24hr") or url.endswith("/fundingRate"): return []
    return real_get(url, p, quiet_400=quiet_400, weight=weight)
ft.get_json = asof
# доска на момент тика
_bc = {}
def board_asof():
    now_ms = int(fake.t * 1000); kb = now_ms // 600_000
    if kb not in _bc:
        ch = []
        for s, times in T3.items():
            j = bisect.bisect_right(times, now_ms - 180_000) - 1; j0 = bisect.bisect_right(times, now_ms - 86_400_000 - 180_000) - 1
            if j > 0 and j0 >= 0:
                c1, c0 = float(K3[s][j][4]), float(K3[s][j0][4])
                if c0 > 0: ch.append((c1 / c0 - 1) * 100)
        ch.sort(); med = ch[len(ch) // 2] if ch else None
        _bc.clear(); _bc[kb] = dict(at=fake.t, board24=round(med, 2), up=round(sum(1 for x in ch if x > 0) / len(ch) * 100, 1), n=len(ch), btc=0.0, up_level=1.0, mode="", flush_side="") if med is not None else None
    return _bc[kb]
import os
if os.environ.get("REPLAY_BOARD"):                                       # проверка R54: доска принудительно задана (например REPLAY_BOARD=2.5)
    _fb = float(os.environ["REPLAY_BOARD"]); _real_board = board_asof
    def board_asof():
        return dict(at=fake.t, board24=_fb, up=80.0, n=500, btc=0.0, up_level=1.0, mode="растёт", flush_side="лонг")
ft._board24 = board_asof; ft._board_set = lambda tk: None
# получасовой архив — только закрытые получасовки
_real_rows = ft.rows_of; _RC = {}
def rows_asof(sym):
    if sym not in _RC:
        r = _real_rows(sym); _RC[sym] = (r, [x["t"] for x in r])
    r, ts = _RC[sym]; return r[:bisect.bisect_right(ts, int(fake.t * 1000) - 1_800_000)]
ft.rows_of = rows_asof
# ликвидации — события до момента тика
full = ft._liq_hourly(); d0ms = int(d0 * 1000) - 86_400_000 * 0
base = {k: {h: v for h, v in hs.items() if h < int(d0 * 1000)} for k, hs in full.items()}
evs = []; seen = set()
for pth in sorted((REAL / "cq_v2" / "liq").glob("*.jsonl"))[-5:]:
    for ln in pth.open(encoding="utf-8", errors="ignore"):
        try: r = json.loads(ln)
        except ValueError: continue
        if r.get("side") not in ("long", "short") or int(r.get("t") or 0) < int(d0 * 1000): continue
        k = (r.get("t"), r.get("sym"), r["side"], r.get("usd"), r.get("src"))
        if k in seen: continue
        seen.add(k); evs.append((int(r["t"]), r["sym"], r["side"], float(r.get("usd") or 0)))
evs.sort(); _lp = [0]
def liq_asof():
    now_ms = int(fake.t * 1000)
    while _lp[0] < len(evs) and evs[_lp[0]][0] <= now_ms:
        t, sym, sd, usd = evs[_lp[0]]; h = t // 3_600_000 * 3_600_000; d = base.setdefault((sym, sd), {}); d[h] = d.get(h, 0.0) + usd; _lp[0] += 1
    return base
ft._liq_hourly = liq_asof
# файлы — во временную папку
for f in ("own_mm.json",):
    try: shutil.copy(REAL / "output" / f, WD / "output" / f)
    except OSError: pass
if not (WD / "cq_v2").exists(): (WD / "cq_v2").symlink_to(REAL / "cq_v2")
ft.BASE_DIR = WD; ft.STATE = WD / "output" / "paper_fast3.json"; ft.LOG = WD / "output" / "paper_fast3.jsonl"; ft._RATE_F = WD / "output" / "fast_entry_times.json"
for f in (ft.LOG, ft._RATE_F, WD / "output" / "london_count.json"):
    try: f.unlink()
    except OSError: pass
ft.cg = lambda *a, **k: None; ft._bingx = lambda ev: []; ft.fon = lambda: {}
if _os.environ.get("REPLAY_CFG"):                                        # проверка редких веток: подмена констант core_config на время пересчёта, например {"FAST3_PUMP_RISE": 5}
    import core_config as _cc
    for _k, _v in json.loads(_os.environ["REPLAY_CFG"]).items(): setattr(_cc, _k, _v)
try: (WD / "output" / "pump_end.json").unlink()
except OSError: pass
# занятые монеты: открыты до полуночи и живы в полночь (до фактического выхода), NIGHT — весь день
ent = {}; exi = {}
for ln in open(_os.environ.get("REPLAY_JOURNAL") or (REAL / "output" / "paper_fast3.jsonl"), encoding="utf-8"):
    try: r = json.loads(ln)
    except ValueError: continue
    if r.get("kind") == "entry": ent[(r["sym"], round(r["at"]))] = r
    elif r.get("kind") in ("exit_long", "exit_short"): exi[(r["sym"], round(r.get("opened_at", 0)))] = r
state = {"open": {}, "last_exit": {}}; locked = {}
for (sym, at), r in ent.items():
    if r["at"] >= d0: continue
    x = exi.get((sym, at))
    if x is None: locked[sym] = 1e12
    elif x["at"] >= d0 - 7200: locked[sym] = max(locked.get(sym, 0), x["at"])
locked["NIGHTUSDT"] = 1e12
state["last_exit"].update(locked)
_real_open = ft._open_short_now
def open_guard(state_, ev, msgs, sym, c, t_bar, now, why, book, write, side=-1, **kw):
    if sym in locked and now - locked[sym] < 0:
        msgs.append(f"{sym[:-4]} вынос — монета занята настоящей позицией, пересчёт не входит"); return False
    return _real_open(state_, ev, msgs, sym, c, t_bar, now, why, book, write, side=side, **kw)
ft._open_short_now = open_guard
print(f"пересчёт {datetime.fromtimestamp(d0, L):%d.%m %H:%M} → {datetime.fromtimestamp(END, L):%H:%M}; занято монет {len(locked)}: {', '.join(s[:-4] for s in sorted(locked))}", flush=True)
t = START + 45; n = 0; t_real = _time.time(); out_log = open(WD / "replay_msgs.log", "w", encoding="utf-8")
while t <= END:
    fake.t = t
    try:
        for m in ft.step(state, True):
            if "список:" in m: continue
            out_log.write(f"{datetime.fromtimestamp(t, L):%H:%M:%S} {m}\n")
            if " вход " in m or " выход " in m: print(f"{datetime.fromtimestamp(t, L):%H:%M} {m[:230]}", flush=True)
    except Exception as e:  # noqa: BLE001
        import traceback; print(f"{datetime.fromtimestamp(t, L):%H:%M} СБОЙ {type(e).__name__}: {e}", flush=True); traceback.print_exc(); break
    out_log.flush(); n += 1; t += 180
    if n % 40 == 0: print(f"  … {datetime.fromtimestamp(t, L):%H:%M}, тиков {n}, прошло {_time.time() - t_real:.0f} с, сетевых ответов в кэше {len(NC)}", flush=True)
json.dump(state, open(WD / "state_end.json", "w"), ensure_ascii=False); json.dump(dict(end=t - 180, d0=d0, locked=locked), open(WD / "meta.json", "w"))
print(f"готово: тиков {n}, {_time.time() - t_real:.0f} с; открыто в конце {len(state['open'])}: {', '.join(s[:-4] for s in state['open'])}", flush=True)
