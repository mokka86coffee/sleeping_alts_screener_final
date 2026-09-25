#!/usr/bin/env python3
"""
budilnik2.py — десять будильников, по одному на день (или на два).

Задания закодированы нарочно: если прочитать все сразу, внезапности не будет.
Скрипт показывает их по одному. Раскрыть все — ключ --spoil.

Каждое задание собрано так, чтобы работали три центра сразу:
непривычное движение (двигательный), ощущение от него (инстинктивный),
и фраза о цели, произнесённая в образовавшийся зазор (мысль и чувство).
Непривычное действие без удержанной цели — просто гимнастика.

Запуск:
    python3 budilnik2.py              # фоновый цикл
    python3 budilnik2.py --today      # какое задание сегодня (без ожидания)
    python3 budilnik2.py --test       # показать окно проверки прямо сейчас
    python3 budilnik2.py --report     # отчёт
    python3 budilnik2.py --newrun     # новый прогон, порядок перемешивается заново
    python3 budilnik2.py --spoil      # раскрыть все десять
    python3 budilnik2.py --selftest   # проверка логики без окон
"""

import argparse
import base64
import json
import os
import random
import sys
import time
from datetime import datetime, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

# --- пороги и пути: всё здесь, магических чисел в теле нет -------------------
CONFIG = {
    "log_path": os.path.join(HERE, "budilnik2_log.jsonl"),
    "state_path": os.path.join(HERE, "budilnik2_state.json"),
    "days_per_alarm": 1,              # сколько дней живёт одно задание
    "wait_answer_sec": 600,           # сколько окно ждёт ответа, потом «не ответил»
    "task_hours": ("08:30", "10:30"),  # когда выдаётся задание дня
    "check_hours": ("10:45", "21:00"),  # когда всплывают проверки
    "evening_hours": ("21:30", "23:00"),  # когда подводится день
    "dwell_task_sec": 5,              # выдержка кнопки: задание
    "dwell_check_sec": 20,            # выдержка кнопки: проверка (время на действие)
    "dwell_evening_sec": 3,
    "poll_sec": 20,
    "window_w": 640,
    "window_h": 460,
}

CENTERS = [
    (1, "1 — только ум: подумал, телом ничего не сделал"),
    (2, "2 — ум и тело: сделал, но внутри ничего не шевельнулось"),
    (3, "3 — ум, тело и чувство: сделал, ощутил, и цель попала в зазор"),
]

FORCE = [
    ("мало", "мало — не заметил ощущения, привычка не дрогнула"),
    ("впору", "впору — заметил, но мог продолжать своё"),
    ("много", "много — ощущение забрало всё внимание, про цель забыл"),
]

ALARMS_B64 = [
    "eyJpZCI6ICJhMDEiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQstGB0ZEg0LHRi9GC0L7QstC+0LUg4oCUINC70LXQstC+0Lkg0YDRg9C60L7QuSAo0LXRgdC70Lgg0YLRiyDQu9C10LLRiNCwIOKAlCDQv9GA0LDQstC+0LkpLlxu0JTQstC10YDRjCwg0LrRgNCw0L0sINGH0LDQudC90LjQuiwg0LvQvtC20LrQsCwg0YLQtdC70LXRhNC+0L0sINGJ0ZHRgtC60LAuINCd0LUg0L/QvtC00YHRgtGA0LDRhdC+0LLRi9Cy0LDQudGB0Y8g0LLRgtC+0YDQvtC5LlxuXG7QodC40LvQsDog0LTQvtC70LbQvdC+INCx0YvRgtGMINC+0YLRh9GR0YLQu9C40LLQviDQvdC10LvQvtCy0LrQvi4g0J3QviDQvdC1INC90LDRgdGC0L7Qu9GM0LrQviwg0YfRgtC+0LHRiyDRgtGLXG7QtNGD0LzQsNC7INGC0L7Qu9GM0LrQviDQvtCxINGN0YLQvtC8LiIsICJwcm9tcHQiOiAi0KHQtNC10LvQsNC5INCx0LvQuNC20LDQudGI0LXQtSDQv9GA0LjQstGL0YfQvdC+0LUg0LTQtdC50YHRgtCy0LjQtSDQtNGA0YPQs9C+0Lkg0YDRg9C60L7QuS4g0JzQtdC00LvQtdC90L3Qvi5cbtCf0L7QutCwINC00LXQu9Cw0LXRiNGMIOKAlCDQstGB0LvRg9GFLCDQvtC00L3QvtC5INGE0YDQsNC30L7QuTog0LfQsNGH0LXQvCDRjyDQt9C00LXRgdGMINGB0LXQs9C+0LTQvdGPLiIsICJjaGVja3NfcGVyX2RheSI6IDR9",
    "eyJpZCI6ICJhMDIiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQt9CwINC60L7QvNC/0YzRjtGC0LXRgNC+0Lwg4oCUINC80YvRiNGMINCyINC00YDRg9Cz0L7QuSDRgNGD0LrQtS5cbtCV0YHQu9C4INC+0LHRi9GH0L3QviDQvNGL0YjRjCDigJQg0YLQvtC70YzQutC+INGC0LDRh9C/0LDQtC4g0JXRgdC70Lgg0L7QsdGL0YfQvdC+INGC0LDRh9C/0LDQtCDigJQg0LzRi9GI0Ywg0L3QsNC+0LHQvtGA0L7Rgi5cblxu0KHQuNC70LA6INGA0LDQsdC+0YLQsCDQtNC+0LvQttC90LAg0LfQsNC80LXRgtC90L4g0LfQsNC80LXQtNC70LjRgtGM0YHRjy4g0JXRgdC70Lgg0YHQutC+0YDQvtGB0YLRjCDRgtCwINC20LUg4oCUINGD0YHQu9C+0LbQvdC4LiIsICJwcm9tcHQiOiAi0J7RgtC60YDQvtC5INGH0YLQvi3QvdC40LHRg9C00Ywg0Lgg0L/QvtGA0LDQsdC+0YLQsNC5INC80LjQvdGD0YLRgyDQsiDQvdC10L/RgNC40LLRi9GH0L3QvtC8INGD0L/RgNCw0LLQu9C10L3QuNC4Llxu0JLRgdC70YPRhSwg0L/QvtC60LAg0YDQsNCx0L7RgtCw0LXRiNGMOiDQt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uIiwgImNoZWNrc19wZXJfZGF5IjogNH0=",
    "eyJpZCI6ICJhMDMiLCAidGFzayI6ICLQndCwINC00LLQsCDRh9Cw0YHQsCDQv9C+0LvQvtC20Lgg0LIg0L7QsdGD0LLRjCDQvNC10LvQutC40Lkg0LrQsNC80LXRiNC10Log0LjQu9C4INGC0YPQs9C+INGB0LvQvtC20LXQvdC90YPRjiDQsdGD0LzQsNC20LrRgy5cbtCi0LDQuiwg0YfRgtC+0LHRiyDRh9GD0LLRgdGC0LLQvtCy0LDQu9C+0YHRjCDQv9GA0Lgg0LrQsNC20LTQvtC8INGI0LDQs9C1LiDQp9C10YDQtdC3INC00LLQsCDRh9Cw0YHQsCDQstGL0L3RjC5cblxu0KHQuNC70LA6INC+0YLRh9GR0YLQu9C40LLQviwg0L3QviDQvdC1INCx0L7Qu9GM0L3Qvi4g0JXRgdC70Lgg0L3QsNGH0LjQvdCw0LXRgiDQvNC10YjQsNGC0Ywg0LjQtNGC0Lgg4oCUINC80LXQvdGM0YjQtS4iLCAicHJvbXB0IjogItCS0YHRgtCw0L3RjCDQuCDQv9GA0L7QudC00Lgg0LTQstCw0LTRhtCw0YLRjCDRiNCw0LPQvtCyLCDQt9Cw0LzQtdGH0LDRjyDRgdGC0L7Qv9GDLlxu0JLRgdC70YPRhSDQvdCwINGF0L7QtNGDOiDQt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uIiwgImNoZWNrc19wZXJfZGF5IjogM30=",
    "eyJpZCI6ICJhMDQiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQstGB0ZEg0L3QvtGB0LjQvNC+0LUg4oCUINC90LAg0LTRgNGD0LPQvtC5INGB0YLQvtGA0L7QvdC1Llxu0KfQsNGB0Ysg0L3QsCDQtNGA0YPQs9GD0Y4g0YDRg9C60YMsINGC0LXQu9C10YTQvtC9INCyINC00YDRg9Cz0L7QuSDQutCw0YDQvNCw0L0sINC60L7Qu9GM0YbQviDQvdCwINC00YDRg9Cz0L7QuSDQv9Cw0LvQtdGGLFxu0YHRg9C80LrQsCDQvdCwINC00YDRg9Cz0L7QtSDQv9C70LXRh9C+LlxuXG7QodC40LvQsDog0LrQsNC20LTRi9C5INGA0LDQtywg0LrQvtCz0LTQsCDRgNGD0LrQsCDQuNC00ZHRgiDQvdC1INGC0YPQtNCwLCDigJQg0Y3RgtC+INC4INC10YHRgtGMINC30LDQt9C+0YAuIiwgInByb21wdCI6ICLQn9C+0YLRj9C90LjRgdGMINC30LAg0YLQtdC70LXRhNC+0L3QvtC8INC40LvQuCDRh9Cw0YHQsNC80Lgg0L/QviDQv9GA0LjQstGL0YfQutC1IOKAlCDQuCDQvtGB0YLQsNC90L7QstC4INGA0YPQutGDINC90LAg0L/QvtC70L/Rg9GC0LguXG7QktGB0LvRg9GFOiDQt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uIiwgImNoZWNrc19wZXJfZGF5IjogNH0=",
    "eyJpZCI6ICJhMDUiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQvdC1INGB0LDQtNC40YHRjCDQuCDQvdC1INGB0YLQvtC5LCDQutCw0Log0L/RgNC40LLRi9C6Llxu0JzQtdC90Y/QuSDQv9C+0LvQvtC20LXQvdC40LUg0LrQsNC20LTRi9C1INC/0L7Qu9GH0LDRgdCwOiDQutGA0LDQuSDRgdGC0YPQu9CwLCDQtNGA0YPQs9Cw0Y8g0L7Qv9C+0YDQvdCw0Y8g0L3QvtCz0LAsXG7QutC+0YDQv9GD0YEg0YDQsNC30LLRkdGA0L3Rg9GCINC90LUg0LIg0YLRgyDRgdGC0L7RgNC+0L3Rgy5cblxu0KHQuNC70LA6INC80YvRiNGG0Ysg0LTQvtC70LbQvdGLINGB0L7QvtCx0YnQsNGC0Ywg0L4g0YHQtdCx0LUuINCX0LDRgtC10LrQsNGC0Ywg4oCUINC90LUg0LTQvtC70LbQvdC+LiIsICJwcm9tcHQiOiAi0J/RgNC40LzQuCDQv9C+0LvQvtC20LXQvdC40LUsINCyINC60L7RgtC+0YDQvtC8INGB0LXQs9C+0LTQvdGPINC10YnRkSDQvdC1INCx0YvQuy4g0JTQtdGA0LbQuCDQvNC40L3Rg9GC0YMuXG7QmtC+0LPQtNCwINC/0L7Rj9Cy0LjRgtGB0Y8g0L7RidGD0YnQtdC90LjQtSDigJQg0LLRgdC70YPRhSwg0L3QtSDQvNC10L3Rj9GPINC/0L7Qt9GLOiDQt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uIiwgImNoZWNrc19wZXJfZGF5IjogNH0=",
    "eyJpZCI6ICJhMDYiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQsiDQv9C+0LzQtdGJ0LXQvdC40Lgg0LTQstC40LPQsNC50YHRjyDQstC00LLQvtC1INC80LXQtNC70LXQvdC90LXQtSDQvtCx0YvRh9C90L7Qs9C+Llxu0JLRgdGC0LDQstCw0YLRjCwg0YXQvtC00LjRgtGMLCDQsdGA0LDRgtGMINC/0YDQtdC00LzQtdGC0YssINC+0YLQutGA0YvQstCw0YLRjCDQtNCy0LXRgNC4LlxuXG7QodC40LvQsDog0LTQvtC70LbQvdC+INGA0LDQt9C00YDQsNC20LDRgtGMLiDQldGB0LvQuCDQvdC1INGA0LDQt9C00YDQsNC20LDQtdGCIOKAlCDQtdGJ0ZEg0LzQtdC00LvQtdC90L3QtdC1LiIsICJwcm9tcHQiOiAi0J/RgNC+0LnQtNC4INC+0YIg0YHRgtC10L3RiyDQtNC+INGB0YLQtdC90Ysg0LLQtNCy0L7QtSDQvNC10LTQu9C10L3QvdC10LUsINGH0LXQvCDRhdC+0YfQtdGC0YHRjy5cbtCd0LAg0YXQvtC00YMg0LLRgdC70YPRhTog0LfQsNGH0LXQvCDRjyDQt9C00LXRgdGMINGB0LXQs9C+0LTQvdGPLiIsICJjaGVja3NfcGVyX2RheSI6IDN9",
    "eyJpZCI6ICJhMDciLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQs9C+0LLQvtGA0Lgg0YLQuNGI0LUg0Lgg0LzQtdC00LvQtdC90L3QtdC1INC+0LHRi9GH0L3QvtCz0L4uINCh0L4g0LLRgdC10LzQuCwg0LLQutC70Y7Rh9Cw0Y8g0YLQtdC70LXRhNC+0L0uXG5cbtCh0LjQu9CwOiDRgdC+0LHQtdGB0LXQtNC90LjQuiDQtNC+0LvQttC10L0g0LfQsNC80LXRgtC40YLRjC4g0JXRgdC70Lgg0LfQsCDQtNC10L3RjCDQvdC40LrRgtC+INC90LUg0LfQsNC80LXRgtC40Lsg4oCUINC10YnRkSDRgtC40YjQtS4iLCAicHJvbXB0IjogItCh0LrQsNC20Lgg0LLRgdC70YPRhSwg0LIg0YHQstC+0ZHQvCDRgdC10LPQvtC00L3Rj9GI0L3QtdC8INGC0LXQvNC/0LUsINC+0LTQvdGDINGE0YDQsNC30YM6XG7Qt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uINCc0LXQtNC70LXQvdC90LXQtSwg0YfQtdC8INGF0L7Rh9C10YLRgdGPLiIsICJjaGVja3NfcGVyX2RheSI6IDR9",
    "eyJpZCI6ICJhMDgiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQstGB0LUg0LHRi9GC0L7QstGL0LUg0L/QvtGB0LvQtdC00L7QstCw0YLQtdC70YzQvdC+0YHRgtC4IOKAlCDQsiDQvtCx0YDQsNGC0L3QvtC8INC/0L7RgNGP0LTQutC1Llxu0JrQsNC60L7QuSDQsdC+0YLQuNC90L7QuiDQv9C10YDQstGL0LwsINC60LDQutC+0Lkg0YDRg9C60LDQsiwg0YEg0LrQsNC60L7QuSDRgdGC0L7RgNC+0L3RiyDQstGB0YLQsNGR0YjRjCxcbtC60LDQutC+0Lkg0LfRg9CxINGH0LjRgdGC0LjRiNGMINC/0LXRgNCy0YvQvCwg0YfRgtC+INC60LvQsNC00ZHRiNGMINCyINGH0LDRiNC60YMg0YDQsNC90YzRiNC1LlxuXG7QodC40LvQsDog0YLRiyDQtNC+0LvQttC10L0g0L3QtdGB0LrQvtC70YzQutC+INGA0LDQtyDRgdCx0LjRgtGM0YHRjyDQuCDQvdCw0YfQsNGC0Ywg0LfQsNC90L7QstC+LiIsICJwcm9tcHQiOiAi0J3QsNC50LTQuCDQsdC70LjQttCw0LnRiNGD0Y4g0L/RgNC40LLRi9GH0L3Rg9GOINC/0L7RgdC70LXQtNC+0LLQsNGC0LXQu9GM0L3QvtGB0YLRjCDQuCDRgNCw0LfQstC10YDQvdC4INC10ZEuXG7Qn9C+0LrQsCDQtNC10LvQsNC10YjRjCDigJQg0LLRgdC70YPRhTog0LfQsNGH0LXQvCDRjyDQt9C00LXRgdGMINGB0LXQs9C+0LTQvdGPLiIsICJjaGVja3NfcGVyX2RheSI6IDR9",
    "eyJpZCI6ICJhMDkiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDRgNGD0LrQuCDQuCDQvdC+0LPQuCDRgdC60YDQtdGJ0LjQstCw0Lkg0L3QsNC+0LHQvtGA0L7Rgi5cbtCX0LDQvNC10YLQuNC7INC/0YDQuNCy0YvRh9C90L7QtSDRgdC60YDQtdGJ0LjQstCw0L3QuNC1IOKAlCDQv9C10YDQtdC70L7QttC4LlxuXG7QodC40LvQsDog0LTQvtC70LbQvdC+INCx0YvRgtGMINC90LXRg9GO0YLQvdC+INC60LDQttC00YvQuSDRgNCw0LcsINCwINC90LUg0L7QtNC40L0uIiwgInByb21wdCI6ICLQodC60YDQtdGB0YLQuCDRgNGD0LrQuCDQutCw0Log0L7QsdGL0YfQvdC+LCDQv9C+0YLQvtC8INC/0LXRgNC10LvQvtC20Lgg0L3QsNC+0LHQvtGA0L7RgiDQuCDQtNC10YDQttC4INC80LjQvdGD0YLRgy5cbtCa0L7Qs9C00LAg0YHRgtCw0L3QtdGCINC90LXRg9GO0YLQvdC+IOKAlCDQstGB0LvRg9GFOiDQt9Cw0YfQtdC8INGPINC30LTQtdGB0Ywg0YHQtdCz0L7QtNC90Y8uIiwgImNoZWNrc19wZXJfZGF5IjogNH0=",
    "eyJpZCI6ICJhMTAiLCAidGFzayI6ICLQodC10LPQvtC00L3RjyDQtdGI0Ywg0L3QtdC/0YDQuNCy0YvRh9C90L46INC/0YDQuNCx0L7RgCDQsiDQtNGA0YPQs9C+0Lkg0YDRg9C60LUsINCy0LTQstC+0LUg0LzQtdC00LvQtdC90L3QtdC1LFxu0LHQtdC3INGN0LrRgNCw0L3QsCDQuCDQsdC10Lcg0YfRgtC10L3QuNGPLlxuXG7QodC40LvQsDog0LXQtNCwINC00L7Qu9C20L3QsCDQt9Cw0L3Rj9GC0Ywg0LfQsNC80LXRgtC90L4g0LHQvtC70YzRiNC1INCy0YDQtdC80LXQvdC4LCDRh9C10Lwg0L7QsdGL0YfQvdC+LiIsICJwcm9tcHQiOiAi0JXRgdC70Lgg0YHQtdC50YfQsNGBINC10LTQsCDQuNC70Lgg0L/QuNGC0YzRkSDigJQg0YHQtNC10LvQsNC5INCz0LvQvtGC0L7QuiDQuNC70Lgg0YPQutGD0YEg0LIg0Y3RgtC+0Lwg0YDQtdC20LjQvNC1Llxu0JXRgdC70Lgg0L3QtdGCIOKAlCDQstGL0L/QtdC5INCy0L7QtNGLINGC0LDQuiDQttC1LCDQvNC10LTQu9C10L3QvdC+Llxu0JLRgdC70YPRhTog0LfQsNGH0LXQvCDRjyDQt9C00LXRgdGMINGB0LXQs9C+0LTQvdGPLiIsICJjaGVja3NfcGVyX2RheSI6IDN9",
]


def alarms():
    return [json.loads(base64.b64decode(b).decode("utf-8")) for b in ALARMS_B64]


# --- журнал и состояние ------------------------------------------------------
def log_write(record):
    record["ts"] = datetime.now().isoformat(timespec="seconds")
    with open(CONFIG["log_path"], "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_read():
    if not os.path.exists(CONFIG["log_path"]):
        return []
    out = []
    with open(CONFIG["log_path"], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def state_new():
    order = list(range(len(ALARMS_B64)))
    random.shuffle(order)
    return {"run_start": date.today().isoformat(), "order": order}


def state_read():
    if not os.path.exists(CONFIG["state_path"]):
        st = state_new()
        state_write(st)
        return st
    with open(CONFIG["state_path"], encoding="utf-8") as f:
        return json.load(f)


def state_write(state):
    with open(CONFIG["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def slot_today(st=None):
    st = st or state_read()
    start = date.fromisoformat(st["run_start"])
    days = (date.today() - start).days
    return days // CONFIG["days_per_alarm"]


def alarm_today(st=None):
    """Задание на сегодня или None, если набор кончился."""
    st = st or state_read()
    slot = slot_today(st)
    if slot < 0 or slot >= len(st["order"]):
        return None
    return alarms()[st["order"][slot]]


# --- расписание --------------------------------------------------------------
def parse_hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def plan_day(day, alarm):
    """Моменты на один день: [(datetime, kind)]. Времена случайные."""
    plan = []

    def pick(hours, count):
        lo, hi = parse_hm(hours[0]), parse_hm(hours[1])
        if hi <= lo or count <= 0:
            return []
        return sorted(random.sample(range(lo, hi), min(count, hi - lo)))

    base = datetime.combine(day, datetime.min.time())
    for m in pick(CONFIG["task_hours"], 1):
        plan.append((base + timedelta(minutes=m), "task"))
    for m in pick(CONFIG["check_hours"], alarm["checks_per_day"]):
        plan.append((base + timedelta(minutes=m), "check"))
    for m in pick(CONFIG["evening_hours"], 1):
        plan.append((base + timedelta(minutes=m), "evening"))
    plan.sort(key=lambda x: x[0])
    return plan


# --- окно --------------------------------------------------------------------
def show_window(kind, alarm):
    """answer=done|skipped|timeout, centers, force, recalls, reaction."""
    try:
        import tkinter as tk
    except ImportError:
        return show_console(kind, alarm)

    res = {"answer": "timeout", "centers": None, "force": None,
           "recalls": None, "reaction": None}
    shown = time.monotonic()

    if kind == "task":
        head, body, dwell = "Задание на сегодня", alarm["task"], CONFIG["dwell_task_sec"]
    elif kind == "check":
        head, body, dwell = "Сейчас", alarm["prompt"], CONFIG["dwell_check_sec"]
    else:
        head, body, dwell = ("Итог дня",
                             "Сколько раз за сегодня ты вспомнил про задание САМ,\n"
                             "без этого окна? Числом.",
                             CONFIG["dwell_evening_sec"])

    root = tk.Tk()
    root.title("будильник")
    root.geometry("%dx%d" % (CONFIG["window_w"], CONFIG["window_h"]))
    root.attributes("-topmost", True)
    root.lift()
    try:
        root.focus_force()
    except tk.TclError:
        pass

    tk.Label(root, text=head, font=("TkDefaultFont", 16, "bold")).pack(pady=(16, 8))
    tk.Label(root, text=body, justify="left",
             wraplength=CONFIG["window_w"] - 60).pack(padx=30)

    entry = None
    v_centers = tk.IntVar(value=0)
    v_force = tk.StringVar(value="")

    if kind == "evening":
        entry = tk.Entry(root, width=10, justify="center")
        entry.pack(pady=10)
        entry.focus_set()

    if kind in ("check", "evening"):
        box = tk.Frame(root)
        box.pack(pady=(12, 0), padx=30, anchor="w")
        tk.Label(box, text="сколько центров участвовало:", anchor="w").pack(anchor="w")
        for val, label in CENTERS:
            tk.Radiobutton(box, text=label, variable=v_centers, value=val,
                           anchor="w", justify="left").pack(anchor="w")
        tk.Label(box, text="сила ощущения:", anchor="w").pack(anchor="w", pady=(8, 0))
        for val, label in FORCE:
            tk.Radiobutton(box, text=label, variable=v_force, value=val,
                           anchor="w", justify="left").pack(anchor="w")

    hint = tk.Label(root, text="", fg="#888")
    hint.pack(pady=(8, 0))

    row = tk.Frame(root)
    row.pack(pady=10)
    btn_ok = tk.Button(row, text="готово", width=14)
    btn_skip = tk.Button(row, text="пропустил", width=14)
    btn_ok.pack(side="left", padx=6)
    btn_skip.pack(side="left", padx=6)

    def finish(answer):
        res["answer"] = answer
        res["reaction"] = round(time.monotonic() - shown, 1)
        if kind in ("check", "evening"):
            res["centers"] = v_centers.get() or None
            res["force"] = v_force.get() or None
        if entry is not None:
            raw = entry.get().strip()
            res["recalls"] = int(raw) if raw.isdigit() else None
        root.destroy()

    def on_ok():
        if kind in ("check", "evening") and (not v_centers.get() or not v_force.get()):
            hint.config(text="отметь оба пункта", fg="#c44")
            return
        if kind == "evening" and not entry.get().strip().isdigit():
            hint.config(text="нужно число, можно 0", fg="#c44")
            return
        finish("done")

    btn_ok.config(command=on_ok)
    btn_skip.config(command=lambda: finish("skipped"))

    if dwell > 0:
        btn_ok.config(state="disabled")

        def tick(left):
            if left <= 0:
                btn_ok.config(state="normal")
                hint.config(text="", fg="#888")
                return
            hint.config(text="кнопка оживёт через %d с" % left, fg="#888")
            root.after(1000, tick, left - 1)

        tick(dwell)

    root.after(CONFIG["wait_answer_sec"] * 1000, lambda: finish("timeout"))
    root.protocol("WM_DELETE_WINDOW", lambda: finish("skipped"))
    root.mainloop()
    return res


def show_console(kind, alarm):
    """Запасной путь, если tkinter не установлен."""
    shown = time.monotonic()
    text = alarm["task"] if kind == "task" else (
        alarm["prompt"] if kind == "check" else "Сколько раз вспомнил сам?")
    print("\n" + "=" * 64)
    print(text)
    dwell = CONFIG["dwell_check_sec"] if kind == "check" else CONFIG["dwell_task_sec"]
    if dwell:
        print("[ждём %d с]" % dwell)
        time.sleep(dwell)
    try:
        ans = input("готово? [д/н] ").strip().lower()
    except EOFError:
        return {"answer": "timeout", "centers": None, "force": None,
                "recalls": None, "reaction": None}
    out = {"answer": "done" if ans.startswith("д") else "skipped",
           "centers": None, "force": None, "recalls": None,
           "reaction": round(time.monotonic() - shown, 1)}
    if out["answer"] == "done" and kind in ("check", "evening"):
        c = input("центров (1/2/3): ").strip()
        f = input("сила (мало/впору/много): ").strip()
        out["centers"] = int(c) if c.isdigit() else None
        out["force"] = f or None
    if out["answer"] == "done" and kind == "evening":
        r = input("вспомнил сам, раз: ").strip()
        out["recalls"] = int(r) if r.isdigit() else None
    return out


def fire(kind, alarm):
    res = show_window(kind, alarm)
    rec = {"alarm": alarm["id"], "kind": kind, "slot": slot_today()}
    rec.update(res)
    log_write(rec)
    return res


# --- отчёт -------------------------------------------------------------------
def report():
    rows = log_read()
    if not rows:
        print("журнал пуст")
        return
    st = state_read()
    print("\nпрогон с %s, день %d, задание %d из %d"
          % (st["run_start"], (date.today() - date.fromisoformat(st["run_start"])).days + 1,
             min(slot_today(st) + 1, len(st["order"])), len(st["order"])))
    print("-" * 70)
    print("%-6s %6s %6s %6s %6s %7s %7s" %
          ("задан", "окон", "готов", "проп", "молч", "центры", "сам"))
    silent = empty_force = 0
    for idx in st["order"]:
        aid = alarms()[idx]["id"]
        sub = [r for r in rows if r.get("alarm") == aid]
        if not sub:
            continue
        done = sum(1 for r in sub if r["answer"] == "done")
        skip = sum(1 for r in sub if r["answer"] == "skipped")
        mute = sum(1 for r in sub if r["answer"] == "timeout")
        cs = [r["centers"] for r in sub if r.get("centers")]
        recalls = sum(r["recalls"] for r in sub if r.get("recalls"))
        silent += mute
        print("%-6s %6d %6d %6d %6d %7s %7d" %
              (aid, len(sub), done, skip, mute,
               ("%.1f" % (sum(cs) / len(cs))) if cs else "-", recalls))
    print("-" * 70)
    forces = [r["force"] for r in rows if r.get("force")]
    dist = {name: forces.count(name) for name, _ in FORCE}
    threes = sum(1 for r in rows if r.get("centers") == 3)
    checks = sum(1 for r in rows if r.get("kind") == "check" and r["answer"] == "done")
    print("не ответил:      %d" % silent)
    print("сила ощущения:   мало %d, впору %d, много %d"
          % (dist["мало"], dist["впору"], dist["много"]))
    print("цель попала:     %d из %d проверок" % (threes, checks))
    print("\nГлавное число — последнее. Сколько раз непривычное сделано — растёт само")
    print("и ничего не значит. Значит только то, сколько раз в зазор попала цель.")
    if slot_today(st) >= len(st["order"]):
        print("\nНАБОР КОНЧИЛСЯ. Новый прогон: --newrun (порядок перемешается).")


# --- цикл --------------------------------------------------------------------
def run_loop():
    st = state_read()
    print("будильник запущен. журнал: %s" % CONFIG["log_path"])
    current_day = None
    queue = []
    while True:
        now = datetime.now()
        a = alarm_today()
        if a is None:
            print("набор кончился — десять заданий пройдены. Новый прогон: --newrun")
            return
        if current_day != now.date():
            current_day = now.date()
            queue = [(w, k) for w, k in plan_day(current_day, a) if w > now]
            print("[%s] задание %s, окон сегодня: %d"
                  % (now.strftime("%H:%M"), a["id"], len(queue)))
        if queue and now >= queue[0][0]:
            _, kind = queue.pop(0)
            fire(kind, a)
        time.sleep(CONFIG["poll_sec"])


def selftest():
    st = state_read()
    print("порядок прогона:", st["order"])
    a = alarm_today(st)
    print("сегодня:", a["id"] if a else "набор кончился")
    if a:
        print("план на день:")
        for when, kind in plan_day(date.today(), a):
            print("  %s  %s" % (when.strftime("%H:%M"), kind))
    real = CONFIG["log_path"]
    CONFIG["log_path"] = real + ".selftest"
    for i in range(9):
        log_write({"alarm": "a01", "kind": ["task", "check", "evening"][i % 3],
                   "answer": ["done", "skipped", "timeout"][i % 3],
                   "centers": (i % 3) + 1, "force": FORCE[i % 3][0],
                   "recalls": i % 4, "reaction": 20.0 + i, "slot": 0})
    print("журнал: записано и прочитано %d строк" % len(log_read()))
    os.remove(CONFIG["log_path"])
    CONFIG["log_path"] = real
    print("декодирование: %d заданий, все поля на месте"
          % sum(1 for x in alarms() if x["task"] and x["prompt"]))
    print("ок")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--today", action="store_true", help="показать задание дня в терминале")
    p.add_argument("--test", action="store_true", help="окно проверки прямо сейчас")
    p.add_argument("--report", action="store_true")
    p.add_argument("--newrun", action="store_true")
    p.add_argument("--spoil", action="store_true", help="раскрыть все задания")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        selftest()
    elif args.spoil:
        for i, a in enumerate(alarms(), 1):
            print("\n--- %d (%s) ---\n%s\n\nв окне: %s" % (i, a["id"], a["task"], a["prompt"]))
    elif args.newrun:
        state_write(state_new())
        print("новый прогон с %s, порядок перемешан" % date.today().isoformat())
    elif args.report:
        report()
    elif args.today:
        a = alarm_today()
        print(a["task"] if a else "набор кончился — запусти --newrun")
    elif args.test:
        a = alarm_today()
        if a is None:
            print("набор кончился — запусти --newrun")
            sys.exit(1)
        print(fire("check", a))
    else:
        run_loop()


if __name__ == "__main__":
    main()
