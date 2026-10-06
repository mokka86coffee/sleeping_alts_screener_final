#!/bin/zsh
# ПРОВЕРКА БОТА ПОСЛЕ ЛЮБОЙ ПРАВКИ (03.10 17:05, владелец: «после правок любых проверяй работу бота на тестовых данных для всех правил ВСЕГДА», «и правь все найденные ошибки»).
# 1) свежие 3-мин свечи по всем монетам; 2) настоящий код бота по минувшим суткам с полуночи (все ветки, которые встретились за день: всплеск, перевороты, А/А2/Б/В/Ж, R47, R53, R55, R56,
#    сканер R52, сессии, Лондон, лимит входов, все выходы); 3) 6 часов с принудительно растущей доской (ветка R54); 4) один живой цикл обеих книг вхолостую с открытыми окнами входа.
# Ничего в книге бота не меняет (временная папка). Итог: строки «СБОЙ»/Traceback — их быть не должно. Запуск: zsh claude/research/bot_test.sh
cd "$(dirname "$0")/../.." || exit 1
T=${TMPDIR:-/tmp}/bot_test_$$; mkdir -p $T; PY=.venv/bin/python
$PY -m py_compile fast_tier.py core_config.py bingx_trader.py || { echo "ПРОВАЛ: не компилируется"; exit 1; }
$PY claude/research/replay_fetch.py $T/k3.pkl | tail -1
$PY claude/research/replay_day.py $T/k3.pkl $T/day > $T/day.out 2>&1
REPLAY_BOARD=4 $PY claude/research/replay_day.py $T/k3.pkl $T/board 08:00 02:00 > $T/board.out 2>&1
REPLAY_CFG='{"FAST3_PUMP_RISE": 6, "FAST3_GROW_RISE": 4}' $PY claude/research/replay_day.py $T/k3.pkl $T/pump 20:00 00:00 > $T/pump.out 2>&1   # ветки R58–R60 (конец роста, запрет лонга) на заниженных порогах
$PY - > $T/live.out 2>&1 <<PYEOF
import json, copy, fast_tier as ft
from pathlib import Path
ft._RATE_F = Path("$T") / "dry_rate.json"; ft.ses_gate = lambda now, t_bar, side=1: (True, "", None); ft.london_gate = lambda sym, now, why: None
SS = {}
for nm, f in (("всплеск/вынос", ft.STATE), ("пробуждение", ft.WAKE_STATE)):
    s = json.loads(f.read_text()); s.setdefault("open", {}); s.setdefault("last_exit", {}); SS[nm] = copy.deepcopy(s)
ft._OTHER["всплеск/вынос"] = dict(state=SS["пробуждение"], book="пробуждение"); ft._OTHER["пробуждение"] = dict(state=SS["всплеск/вынос"], book="всплеск/вынос")   # R63: книги видят друг друга, как в main
for nm, fn in (("всплеск/вынос", ft.step), ("пробуждение", ft.wake_step)):
    try:
        for m in fn(SS[nm], False): print(nm + ":", m)
    except Exception as e:
        import traceback; print("СБОЙ", nm, type(e).__name__, e); traceback.print_exc()
PYEOF
$PY claude/research/test_r63.py > $T/r63.out 2>&1   # R63: одна монета — одна позиция на обе книги (слияние ×2, отмена, встречный сигнал, зеркало)
$PY claude/research/test_r65.py >> $T/r63.out 2>&1   # R65: сползающая монета — лонгов нет, шорт только на отскоке
grep -q 'R65: ок' $T/r63.out || echo "СБОЙ: проверка R65 не дала «ок»" >> $T/r63.out
$PY claude/research/test_r72.py >> $T/r63.out 2>&1   # R72 (06.10): лонг только после слива на 20 % от максимума 72 ч
grep -q 'R72: ок' $T/r63.out || echo "СБОЙ: проверка R72 не дала «ок»" >> $T/r63.out
$PY claude/research/test_r66.py >> $T/r63.out 2>&1   # R66 и свечи позиции дальше 50 часов
grep -q 'R66: ок' $T/r63.out || echo "СБОЙ: проверка R66 не дала «ок»" >> $T/r63.out
$PY claude/research/test_r67.py >> $T/r63.out 2>&1   # R67: во флэте шорт не берём
grep -q 'R67: ок' $T/r63.out || echo "СБОЙ: проверка R67 не дала «ок»" >> $T/r63.out
$PY claude/research/test_r70.py >> $T/r63.out 2>&1   # R70: флэт по суткам, лонг лимиткой от линии флэта
$PY claude/research/test_scanman.py >> $T/r63.out 2>&1   # 04.10: сканер не берёт шорт в монете ручного списка лестницы (R47)
grep -q 'R70: ок' $T/r63.out || echo "СБОЙ: проверка R70 не дала «ок»" >> $T/r63.out
$PY claude/research/test_bingx_close.py >> $T/r63.out 2>&1   # выход на BingX: ошибка запроса не теряет позицию (SOON 03.10)
$PY claude/research/test_bingx_be.py >> $T/r63.out 2>&1   # 05.10: стоп в твх на BingX — от цены исполнения с комиссией (NOM 04.10)
grep -q 'ВЫХОД BINGX: ок' $T/r63.out || echo "СБОЙ: проверка выхода BingX не дала «ок»" >> $T/r63.out
grep -q 'ТВХ BINGX: ок' $T/r63.out || echo "СБОЙ: проверка твх BingX не дала «ок»" >> $T/r63.out
echo "сутки: $(grep -c ' вход ' $T/day.out) входов, $(grep -c ' выход ' $T/day.out) выходов · $(grep 'готово' $T/day.out)"
echo "растущая доска (R54), 02:00–08:00: $(grep -c ' вход ' $T/board.out) входов, из них лонг вместо шорта (R54): $(grep -c "R54" $T/board/output/paper_fast3.jsonl 2>/dev/null)"
echo "заниженные пороги пампа (R58–R60), 00:00–20:00: входов $(grep -c ' вход ' $T/pump.out) · шорт «конец роста»: $(grep -c 'R58 конец роста' $T/pump/output/paper_fast3.jsonl 2>/dev/null) · лонг на выносе лонгов (R59): $(grep -c 'R59 вынос лонгов' $T/pump/output/paper_fast3.jsonl 2>/dev/null) · отказов по запрету лонга (R60): $(grep -c 'R60' $T/pump/replay_msgs.log 2>/dev/null) · ожиданий у верха свечи: $(grep -c 'ждёт возврата цены' $T/pump/replay_msgs.log 2>/dev/null) · выходов шорта «конец роста»: $(grep -c 'R58' <(grep 'exit_short' $T/pump/output/paper_fast3.jsonl 2>/dev/null))"
echo "сутки по нынешним порогам: R58 $(grep -c 'R58 конец роста' $T/day/output/paper_fast3.jsonl 2>/dev/null) · R59 $(grep -c 'R59 вынос лонгов' $T/day/output/paper_fast3.jsonl 2>/dev/null)"
echo "живой цикл: $(grep -c '' $T/live.out) строк"
echo "$(grep 'R63:' $T/r63.out | tail -1)"; echo "$(grep 'R65:' $T/r63.out | tail -1)"; echo "$(grep 'R66:' $T/r63.out | tail -1)"; echo "$(grep 'R67:' $T/r63.out | tail -1)"; echo "$(grep 'R70:' $T/r63.out | tail -1)"; echo "$(grep 'ВЫХОД BINGX' $T/r63.out | tail -1)"
grep -q 'R63: ок' $T/r63.out || echo "СБОЙ: проверка R63 не дала «ок»" >> $T/r63.out
B=$(cat $T/day.out $T/board.out $T/pump.out $T/live.out $T/r63.out | grep -c 'СБОЙ\|Traceback\|Error')
if [ "$B" -gt 0 ]; then echo "ПРОВАЛ: сбоев $B"; cat $T/day.out $T/board.out $T/pump.out $T/live.out $T/r63.out | grep -B2 -A12 'СБОЙ\|Traceback' | head -60; exit 1; else echo "ПРОВЕРКА ПРОЙДЕНА: сбоев нет (папка $T)"; fi
