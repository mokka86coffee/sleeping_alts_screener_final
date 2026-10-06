"""СТОРОЖ ПРАВИЛА «ВСЁ ПО UTC» (16.09 владелец: «все прогоны и всё вообще по UTC, локальное только на экране»; 06.10: «все настройки в utc должны
быть всегда», «никакой привязки к машине быть не должно во времени», «эта хрень где-то всплывёт с разницей в 3 часа — это конец сделки как минимум»).
Проверяет: 1) часы бота — UTC; 2) в рабочих файлах нет обращений к местным часам машины и нет своих поясов, кроме перечисленных ниже с причиной;
3) ключевые часы настроек стоят в UTC. Любое новое место ломает проверку — его надо либо перевести на UTC, либо вписать сюда с причиной."""
import re, sys
from pathlib import Path
from datetime import timezone
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import core_config as cc
import fast_tier as ft
import surge_journal as sj
ok = True
def bad(msg):
    global ok
    ok = False; print("СБОЙ ВРЕМЯ:", msg)
if ft.L != timezone.utc: bad("часы бота fast_tier.L не UTC")
if sj.L != timezone.utc: bad("журнал всплесков surge_journal.L не UTC")
if ft.SES_WIN != (("Токио", 0, 7), ("Лондон", 7, 13), ("Нью-Йорк", 13, 21), ("Сидней", 21, 24)): bad("сессии бота не в UTC-часах")
if cc.FAST3_SES_EXIT_H != {"Сидней": 31, "Токио": 7, "Лондон": 13, "Нью-Йорк": 21}: bad("часы выхода сессий не в UTC")
if cc.FAST3_NO_ENTRY_HOURS != [(6, 8), (12, 14)]: bad("часы без входов не в UTC (должно быть 6–8 и 12–14)")
if tuple(cc.FAST3_LONDON_HOURS) != (8, 12): bad("часы Лондона не в UTC (должно быть 8–12)")
# корни рабочего кода и всё, что они подключают или запускают
roots = ["run.py", "fast_tier.py", "fast_state.py", "fast_server.py", "liq_stream.py", "bingx_trader.py", "render_book.py", "surge_journal.py"]
seen, todo = set(), [r for r in roots if (ROOT / r).exists()]
while todo:
    f = todo.pop()
    if f in seen: continue
    seen.add(f); src = (ROOT / f).read_text(encoding="utf-8")
    for m in re.finditer(r"^\s*(?:from\s+([A-Za-z_][\w\.]*)\s+import|import\s+([A-Za-z_][\w\.]*(?:\s*,\s*[A-Za-z_][\w\.]*)*))", src, re.M):
        for n in ([m.group(1)] if m.group(1) else [x.strip() for x in m.group(2).split(",")]):
            p = n.split(".")[0] + ".py"
            if (ROOT / p).exists(): todo.append(p)
    for m in re.finditer(r"[\"\']([a-z_0-9]+\.py)[\"\']", src):
        if (ROOT / m.group(1)).exists(): todo.append(m.group(1))
LOCAL = {"datetime.now() без пояса": r"datetime\.now\(\s*\)", "time.localtime": r"time\.localtime\(", "time.strftime без gmtime": r"time\.strftime\((?![^\n]*gmtime)",
         "date.today()/datetime.today()": r"(?:date|datetime)\.today\(", "time.mktime": r"time\.mktime\(", ".astimezone() без пояса": r"\.astimezone\(\s*\)",
         "fromtimestamp без пояса": r"fromtimestamp\(\s*[\w\.\[\]\"\' /*+-]+\)"}
OFFSET = r"timezone\(\s*timedelta\("
ALLOW = {  # файл: причина, по которой здесь разрешён свой пояс (не от машины)
    "core_time.py": "MSG_TZ — подписи сообщений в поясе владельца",
    "fast_state.py": "L — граница суток доски и дневных списков сайта (21:00 UTC), ждёт решения владельца",
    "render_book.py": "BOT_TZ — граница суток в книге (экран), ждёт решения владельца",
}
SKIP = (  # проверенные строки, где шаблон срабатывает ложно
    ("analytics_leaders.py", "Момент прогона, не отдельный datetime.now()"),      # слова в описании функции, не вызов
    ("cryptoquant_fetch.py", 'merged["full_at"] = time.strftime('),               # gmtime стоит строкой ниже
)
for f in sorted(seen):
    for i, line in enumerate((ROOT / f).read_text(encoding="utf-8").split("\n"), 1):
        code = line.split("#")[0]
        if any(f == sf and ss in line for sf, ss in SKIP): continue
        for nm, pat in LOCAL.items():
            if re.search(pat, code): bad(f"{f}:{i} — {nm}: {line.strip()[:110]}")
        if re.search(OFFSET, code) and f not in ALLOW: bad(f"{f}:{i} — свой часовой пояс вместо UTC: {line.strip()[:110]}")
print(f"ВРЕМЯ: ок — часы бота и настройки в UTC, в {len(seen)} рабочих файлах нет местных часов машины" if ok else "ВРЕМЯ: СБОЙ")
