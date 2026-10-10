#!/usr/bin/env python3
"""R81 + R82 (10.10 владелец «да»): шорт после выноса шортов — только на развороте фандинга (пульс скринера) и не по монете с меткой очереди
«1»/«★» (output/fast_state.json). Подставные файлы во временной папке; книги бота не трогает. Итог — строка «R81/R82: ок»."""
import json, os, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft

now = time.time(); T = Path(tempfile.mkdtemp(prefix="r81_")); bad = []
def pulse(rows):
    p = T / f"pulse_{len(os.listdir(T))}.json"; p.write_text(json.dumps({"XUSDT": [dict(t=t, funding=f, price=1.0, oi_usd=1.0) for t, f in rows]})); return p
def chk(name, got, want_block):
    ok = (got is not None) == want_block
    print(("ок   " if ok else "СБОЙ ") + name + " → " + (got or "вход разрешён"))
    if not ok: bad.append(name)
# R81
chk("R81 фандинг +0,002 → −0,002 (ушёл в минус)", ft._fund_turn("XUSDT", now, pulse([(now - 4000, 0.002), (now - 2000, -0.002)])), True)
chk("R81 фандинг −0,0086 → −0,0123 (минус растёт)", ft._fund_turn("XUSDT", now, pulse([(now - 4000, -0.0086), (now - 2000, -0.0123)])), True)
chk("R81 фандинг −0,0123 → −0,0071 (развернулся)", ft._fund_turn("XUSDT", now, pulse([(now - 4000, -0.0123), (now - 2000, -0.0071)])), False)
chk("R81 фандинг −0,005 → −0,005 (не ниже прошлого)", ft._fund_turn("XUSDT", now, pulse([(now - 4000, -0.005), (now - 2000, -0.005)])), False)
chk("R81 фандинг в плюсе 0,003 → 0,005", ft._fund_turn("XUSDT", now, pulse([(now - 4000, 0.003), (now - 2000, 0.005)])), False)
chk("R81 последнее показание старше 90 мин", ft._fund_turn("XUSDT", now, pulse([(now - 9000, -0.002), (now - 6000, -0.004)])), True)
chk("R81 одно показание", ft._fund_turn("XUSDT", now, pulse([(now - 2000, -0.004)])), True)
chk("R81 монеты нет в пульсе", ft._fund_turn("YUSDT", now, pulse([(now - 4000, -0.002), (now - 2000, -0.004)])), True)
# R82
st = T / "fast_state.json"; st.write_text(json.dumps({"queue": [{"sym": "XUSDT", "mark": "★", "streak": 4}, {"sym": "ZUSDT", "mark": 1, "streak": 15}]}))
chk("R82 монета с меткой «★»", ft._queue_mark("XUSDT", now, st), True)
chk("R82 монета с меткой «1»", ft._queue_mark("ZUSDT", now, st), True)
chk("R82 монеты нет в очереди", ft._queue_mark("YUSDT", now, st), False)
os.utime(st, (now - 1200, now - 1200)); ft._QM["key"] = None
chk("R82 файл состояния старше 15 мин — правило молчит", ft._queue_mark("XUSDT", now, st), False)
chk("R82 файла нет — правило молчит", ft._queue_mark("XUSDT", now, T / "нет.json"), False)
# подключение к трём путям
src = Path(ft.__file__).read_text(encoding="utf-8")
n = src.count("_short_flush_block(sym, now)")
print(("ок   " if n == 3 else "СБОЙ ") + f"проверка стоит на трёх путях шорта (найдено {n})")
if n != 3: bad.append("пути")
from core_config import FAST3_FLUSH_SHORT_FUND_TURN, FAST3_FLUSH_SHORT_QUEUE_MARK
print(("ок   " if FAST3_FLUSH_SHORT_FUND_TURN and FAST3_FLUSH_SHORT_QUEUE_MARK else "СБОЙ ") + "оба правила включены в core_config")
print("R81/R82: ок" if not bad else "R81/R82: СБОЙ " + ", ".join(bad))
