"""СТОРОНА ОТ ФОНА ДЛЯ БУМАЖНЫХ КНИГ (19.09, моя реализация по журналам 16–19.09).

Наблюдение: за три дня «толпа» и «конец» открыли 365 шортов на −176% и 14 лонгов на +19.5% — бот шортил
рынок, в котором биткоин шёл вверх и жгли шортов в десятки раз. Лаборатория lab_side.py на тех же сделках:
с фильтром стороны обе книги из −157% выходят в +19.5%.

Три правила, все считаются из того, что прогон уже пишет:
  1. СТОРОНА ОТ ФОНА — по output/btc_pulse.json: сожгли шортов больше лонгов в SIDE_LIQ_RATIO раз — открыты
     только лонги; сожгли лонгов больше — только шорты; ровно — обе стороны.
  2. ПРАВИЛА ВЫКЛЮЧЕНЫ — SIDE_RULES_OFF: «рост на выносе» (0 из 9), «спайк на выносе» — шортят ход лидера.
  3. ПОТОЛОК ПО МОНЕТЕ — SIDE_STOPS_PER_DAY стопов по монете за день — монета до следующего дня закрыта
     (AVA была взята 22 раза за три дня).

Как подключить в книге, перед открытием сделки:
    from paper_side import allowed
    ok, why = allowed(side, sym, rule, "paper_crowd")
    if not ok:
        <записать skip с why и не открывать>
Пороги — в core_config; запасные значения ниже.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
try:
    from core_config import SIDE_LIQ_RATIO, SIDE_STOPS_PER_DAY, SIDE_RULES_OFF
except ImportError:
    SIDE_LIQ_RATIO = 1.5              # сожгли одной стороны больше другой во столько раз — фон задаёт сторону
    SIDE_STOPS_PER_DAY = 2            # столько стопов по монете за день — монета закрыта до завтра
    SIDE_RULES_OFF = ("рост на выносе", "спайк на выносе")


def _read(name: str):
    for p in (BASE_DIR / "output" / name, Path("output") / name):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return None


def bg_side() -> tuple[int, str]:
    """+1 — фон за лонги (жгут шортов), −1 — за шорты (жгут лонгов), 0 — ровно или среза нет"""
    p = _read("btc_pulse.json") or {}
    liq = p.get("liq") or {}
    s, l = liq.get("short_24h_usd"), liq.get("long_24h_usd")
    if s is None or l is None:
        return 0, "среза биткоина нет — сторона свободна"
    s, l = float(s), float(l)
    if s >= SIDE_LIQ_RATIO * max(l, 1.0):
        return +1, f"биткоин: сожгли шортов ${s / 1e6:.0f}M против лонгов ${l / 1e6:.0f}M — фон за лонги"
    if l >= SIDE_LIQ_RATIO * max(s, 1.0):
        return -1, f"биткоин: сожгли лонгов ${l / 1e6:.0f}M против шортов ${s / 1e6:.0f}M — фон за шорты"
    return 0, f"биткоин: шортов ${s / 1e6:.0f}M, лонгов ${l / 1e6:.0f}M — ровно, сторона свободна"


def stops_today(sym: str, book: str) -> int:
    """сколько стопов по монете за сегодняшний день бота (UTC) в журнале книги"""
    p = BASE_DIR / "output" / f"{book}.jsonl"
    if not p.exists():
        p = Path("output") / f"{book}.jsonl"
    if not p.exists():
        return 0
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    n = 0
    try:
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines()[-4000:]:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("kind") != "follow" or r.get("sym") != sym:
                continue
            if not str(r.get("why_exit") or "").startswith("стоп"):
                continue
            t = r.get("written_at") or r.get("at")
            if t and datetime.fromtimestamp(float(t), timezone.utc).strftime("%Y-%m-%d") == today:
                n += 1
    except OSError:
        return 0
    return n


def allowed(side: int, sym: str, rule: str, book: str) -> tuple[bool, str]:
    """можно ли открывать сделку: (да/нет, почему). Порядок проверок — выключенное правило, потолок, фон."""
    rule = str(rule or "")
    for off in SIDE_RULES_OFF:
        if rule.startswith(off):
            return False, f"правило выключено: {off} (по журналам 16–19.09 в минусе)"
    n = stops_today(sym, book)
    if n >= SIDE_STOPS_PER_DAY:
        return False, f"потолок: {n} стоп(а) по {sym} сегодня — монета закрыта до завтра"
    bg, why = bg_side()
    if bg and bg != side:
        return False, f"сторона против фона · {why}"
    return True, why


if __name__ == "__main__":
    bg, why = bg_side()
    print("фон:", bg, "·", why)
    for s, sym, rule in ((-1, "ONEUSDT", "перекуплен: z>+2"), (1, "ONEUSDT", "провал: −8% за 2 ч"), (-1, "AVAUSDT", "рост на выносе: 6 ч +12%")):
        print(("шорт" if s < 0 else "лонг"), sym, rule[:20], "→", allowed(s, sym, rule, "paper_crowd"))
