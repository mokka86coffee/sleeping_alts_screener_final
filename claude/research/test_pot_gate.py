#!/usr/bin/env python3
"""R84 (11.10 владелец «написал же делай с котлом»): бот слушает котёл больших ростов. Подставные снимок котла и список лидеров во временной папке;
книги бота и биржу не трогает. Итог — строка «R84: ок»."""
import json, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import fast_tier as ft
import core_config

T = Path(tempfile.mkdtemp()); POT = T / "pump_pot.json"; LEAD = T / "leaders.json"
LEAD.write_text(json.dumps({"AAAUSDT": {}, "BBBUSDT": {}}), encoding="utf-8")
now = time.time()
def pot(used, full, warn, age_min=5, moves=()):
    at = datetime.fromtimestamp(now - age_min * 60, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    POT.write_text(json.dumps({"at": at, "pot_usd": 600e6, "used_usd": used * 1e6, "left_usd": (600 - used) * 1e6, "full": full, "warn": warn,
                               "reset_at": "2026-10-14T01:30:00Z", "moves": [dict(sym=s, done=d) for s, d in moves]}), encoding="utf-8")
    ft._POT_C["mt"] = None
def g(sym, side, why): return ft._pot_gate(sym, side, why, now, pot_path=POT, leaders_path=LEAD)
R52 = "R52 вынос → против хода: вынос шортов 68K$ за час с 15:00 UTC — ×1.8 к максимуму часа за сутки → шорт против хода"
R58 = "R58 конец роста → шорт: минимумы за 48 ч росли · вынос шортов 10K$ за час с 14:00 UTC — ×11.2"
R58L = "R58 конец роста → шорт вдогонку: сквиз был 10.0 ч назад, цена после выноса лонгов не вернулась (-7.6%) · вынос лонгов 8K$"
R65 = "R65 сползание 3 дня (минимумы -6%) → шорт на отскоке, после вершины всплеска · всплеск: бар +1.1% · вход после вершины 0.05 (вынос шортов 125K$ с начала всплеска)"
S55 = "всплеск → шорт 5/5 (03.10: на 301 входе недели лонг −1632 $) · всплеск: бар +1.14%"
SPK = "переворот отменён · вынос шортов на всплеске → шорт · всплеск: бар +2%"
errs = []
def chk(c, m):
    if not c: errs.append(m)
core_config.MANUAL_BY_USER_POT_BOT_ON = True
# 1. котёл полный
pot(935, True, True, moves=(("STRKUSDT", False),))
chk(g("AAAUSDT", 1, "всплеск: бар +2%") and "лонги не берём" in g("AAAUSDT", 1, "x"), "полный: лонг должен быть отклонён")
chk(g("STRKUSDT", 1, "R83 очередь"), "полный: лонг книги «очередь» должен быть отклонён, даже если монета идёт")
for nm, w in (("R52", R52), ("R58", R58), ("R58 вдогонку", R58L), ("на всплеске", SPK), ("R65", R65), ("5/5", S55)):   # 11.10 01:25 UTC: шорты котёл не трогает
    chk(g("AAAUSDT", -1, w) is None, f"полный: шорт {nm} у лидера должен пройти: " + str(g("AAAUSDT", -1, w)))
    chk(g("ZZZUSDT", -1, w) is None, f"полный: шорт {nm} не у лидера должен пройти: " + str(g("ZZZUSDT", -1, w)))
# 1а. шорт по монете, которая сейчас идёт в котле, не берём (11.10 02:50 UTC: «так лидер же идёт»); «вдогонку» — исключение
chk(g("STRKUSDT", -1, R52) and "идёт в котле" in g("STRKUSDT", -1, R52), "полный: шорт R52 по идущей монете должен быть отклонён")
chk(g("STRKUSDT", -1, R58) and g("STRKUSDT", -1, R65), "полный: шорты R58 и R65 по идущей монете должны быть отклонены")
chk(g("STRKUSDT", -1, R58L) is None, "полный: шорт «вдогонку» по идущей монете проходит: " + str(g("STRKUSDT", -1, R58L)))
pot(120, False, False, moves=(("STRKUSDT", False), ("METUSDT", True)))
chk(g("STRKUSDT", -1, R52) and g("METUSDT", -1, R52) is None and g("AAAUSDT", -1, R52) is None, "ниже метки: шорт по идущей монете отклонён, по закончившей рост и по посторонней — проходит")
# 2. красная метка, не полный
pot(450, False, True, moves=(("STRKUSDT", False), ("METUSDT", True)))
chk(g("STRKUSDT", 1, "всплеск") is None, "метка: лонг по идущей монете должен пройти")
chk(g("METUSDT", 1, "всплеск") and "идёт сейчас" in g("METUSDT", 1, "всплеск"), "метка: лонг по закончившей рост монете должен быть отклонён")
chk(g("AAAUSDT", 1, "всплеск"), "метка: лонг по монете вне котла должен быть отклонён")
chk(g("ZZZUSDT", -1, S55) is None and g("ZZZUSDT", -1, R65) is None, "метка: шорты идут как обычно")
# 3. ниже метки, старый снимок, выключатель, нет файла
pot(120, False, False); chk(g("AAAUSDT", 1, "x") is None and g("ZZZUSDT", -1, S55) is None, "ниже метки правило молчит")
pot(935, True, True, age_min=ft.POT_MAX_AGE_MIN + 10); chk(g("AAAUSDT", 1, "x") is None, "старый снимок — правило молчит")
pot(935, True, True); core_config.MANUAL_BY_USER_POT_BOT_ON = False; chk(g("AAAUSDT", 1, "x") is None, "выключатель — правило молчит")
core_config.MANUAL_BY_USER_POT_BOT_ON = True; POT.unlink(); ft._POT_C["mt"] = None; chk(g("AAAUSDT", 1, "x") is None, "нет снимка — правило молчит")
# 4. вход через общий путь: при полном котле _open_short_now не открывает лонг
pot(935, True, True); real = ft._pot_gate
ft._pot_gate = lambda sym, side, why, now_, pot_path=None, leaders_path=None: real(sym, side, why, now_, pot_path=POT, leaders_path=LEAD)
st = {"open": {}, "last_exit": {}}; ev = []; msgs = []
ok = ft._open_short_now(st, ev, msgs, "AAAUSDT", 1.0, int(now * 1000), now, "R59 вынос лонгов на росте → лонг", "всплеск/вынос", False, side=1)
chk(ok is False and not st["open"] and not ev and any("R84" in m for m in msgs), f"_open_short_now открыл лонг при полном котле: {msgs}")
ft._pot_gate = real
print("R84: ок" if not errs else "СБОЙ R84: " + "; ".join(errs))
