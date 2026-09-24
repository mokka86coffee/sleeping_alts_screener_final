#!/usr/bin/env python3
"""
budilnik.py — фоновые окна-будильники.

Только стандартная библиотека. Окно всплывает в случайный момент,
требует действия телом, пишет в журнал факт (не содержание).
Через неделю набор вопросов считается изношенным и требует замены.

Запуск:
    python3 budilnik.py              # фоновый цикл на неделю
    python3 budilnik.py --test vsluh # показать одно окно прямо сейчас
    python3 budilnik.py --report     # отчёт за неделю
    python3 budilnik.py --newweek    # начать новую неделю (после смены вопросов)
    python3 budilnik.py --selftest   # проверка логики без окон
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

# ─── пороги и пути: всё здесь, в коде магических чисел нет ───────────────────
CONFIG = {
    "log_path": os.path.join(HERE, "budilnik_log.jsonl"),
    "state_path": os.path.join(HERE, "budilnik_state.json"),
    "wait_answer_sec": 600,       # сколько окно ждёт ответа, потом «не ответил»
    "week_days": 7,               # срок жизни набора вопросов
    "instant_margin_sec": 1.5,    # клик быстрее выдержки + это = мгновенный
    "window_w": 560,
    "window_h": 300,
    "poll_sec": 20,               # шаг цикла ожидания
}

# ─── каталог будильников ─────────────────────────────────────────────────────
# kind:  confirm — одна кнопка, засчитывается факт
#        text    — строка не короче min_chars
# dwell_sec: столько секунд кнопка неактивна (время на само действие)
ALARMS = {
    "vsluh": {
        "title": "Вслух",
        "text": ("Произнеси ВСЛУХ, в голос, одну фразу:\n"
                 "что я делаю прямо сейчас и зачем.\n\n"
                 "Не про себя. Кнопка оживёт, когда фраза уже сказана."),
        "kind": "confirm",
        "dwell_sec": 6,
        "hours": ("10:00", "22:00"),
        "per_day": 3,
    },
    "vstat": {
        "title": "Встать",
        "text": ("Встань и выйди из комнаты. Без телефона.\n"
                 "Вернись — нажми кнопку.\n\n"
                 "Кнопка оживёт через минуту."),
        "kind": "confirm",
        "dwell_sec": 60,
        "hours": ("10:00", "22:00"),
        "per_day": 2,
    },
    "ruki_utro": {
        "title": "Руками — утро",
        "text": ("Положи на стол предмет из кармана.\n"
                 "Скажи вслух, что он значит сегодня.\n\n"
                 "Он остаётся лежать до вечера."),
        "kind": "confirm",
        "dwell_sec": 8,
        "hours": ("08:30", "11:00"),
        "per_day": 1,
    },
    "ruki_vecher": {
        "title": "Руками — вечер",
        "text": ("Убери предмет со стола.\n"
                 "Скажи вслух: сбылось или нет."),
        "kind": "confirm",
        "dwell_sec": 8,
        "hours": ("21:00", "23:30"),
        "per_day": 1,
    },
    "cancel": {
        "title": "Условие отмены",
        "text": ("То, что сейчас открыто и чем ты занят —\n"
                 "напиши ОДНОЙ строкой условие, при котором это отменяется.\n"
                 "Так, чтобы посторонний проверил по экрану, не спрашивая тебя."),
        "kind": "text",
        "min_chars": 20,
        "dwell_sec": 0,
        "hours": ("10:00", "22:00"),
        "per_day": 2,
    },
    # ниже — из первой тройки, выключены; включаются добавлением в ACTIVE
    "organized": {
        "title": "Кто организовал последний час",
        "text": ("Одним существительным: что задало порядок последнего часа.\n"
                 "«уведомление», «график», «звонок», «план».\n"
                 "«работал» и «думал» не считаются."),
        "kind": "text",
        "min_chars": 3,
        "dwell_sec": 0,
        "hours": ("10:00", "22:00"),
        "per_day": 2,
    },
    "ne_soshlos": {
        "title": "Что не сошлось",
        "text": ("Назови место, где сегодня не сошлось. Своё, не чужое.\n"
                 "Пустой ответ — не ноль, а сигнал: день только подтверждал."),
        "kind": "text",
        "min_chars": 10,
        "dwell_sec": 0,
        "hours": ("21:30", "23:30"),
        "per_day": 1,
    },
}

ACTIVE = ["vsluh", "vstat", "ruki_utro", "ruki_vecher", "cancel"]


# ─── журнал и состояние ──────────────────────────────────────────────────────
def log_write(record):
    record["ts"] = datetime.now().isoformat(timespec="seconds")
    line = json.dumps(record, ensure_ascii=False)
    with open(CONFIG["log_path"], "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_read():
    if not os.path.exists(CONFIG["log_path"]):
        return []
    out = []
    with open(CONFIG["log_path"], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def state_read():
    if not os.path.exists(CONFIG["state_path"]):
        return {"week_start": date.today().isoformat()}
    with open(CONFIG["state_path"], encoding="utf-8") as f:
        return json.load(f)


def state_write(state):
    with open(CONFIG["state_path"], "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def week_day_number():
    start = date.fromisoformat(state_read()["week_start"])
    return (date.today() - start).days + 1


# ─── расписание ──────────────────────────────────────────────────────────────
def parse_hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def plan_day(day, alarm_ids=None):
    """Случайные моменты на один день. Возвращает список (datetime, alarm_id)."""
    alarm_ids = alarm_ids or ACTIVE
    plan = []
    for aid in alarm_ids:
        a = ALARMS[aid]
        lo, hi = parse_hm(a["hours"][0]), parse_hm(a["hours"][1])
        if hi <= lo:
            continue
        picks = sorted(random.sample(range(lo, hi), min(a["per_day"], hi - lo)))
        for minute in picks:
            when = datetime.combine(day, datetime.min.time()) + timedelta(minutes=minute)
            plan.append((when, aid))
    plan.sort(key=lambda x: x[0])
    return plan


# ─── окно ────────────────────────────────────────────────────────────────────
def show_window(alarm_id):
    """Возвращает dict: answer=done|skipped|timeout|empty, text, reaction."""
    a = ALARMS[alarm_id]
    try:
        import tkinter as tk
    except ImportError:
        return show_console(alarm_id)

    res = {"answer": "timeout", "text": "", "reaction": None}
    shown = time.monotonic()

    root = tk.Tk()
    root.title("будильник — " + a["title"])
    root.geometry("%dx%d" % (CONFIG["window_w"], CONFIG["window_h"]))
    root.attributes("-topmost", True)
    root.lift()
    try:
        root.focus_force()
    except tk.TclError:
        pass

    tk.Label(root, text=a["title"], font=("TkDefaultFont", 16, "bold")).pack(pady=(18, 6))
    tk.Label(root, text=a["text"], justify="left", wraplength=CONFIG["window_w"] - 60).pack(padx=30)

    entry = None
    if a["kind"] == "text":
        entry = tk.Entry(root, width=58)
        entry.pack(pady=12)
        entry.focus_set()

    hint = tk.Label(root, text="", fg="#888")
    hint.pack()

    row = tk.Frame(root)
    row.pack(pady=10)
    btn_ok = tk.Button(row, text="сделал", width=14)
    btn_skip = tk.Button(row, text="пропустил", width=14)
    btn_ok.pack(side="left", padx=6)
    btn_skip.pack(side="left", padx=6)

    def finish(answer):
        res["answer"] = answer
        res["reaction"] = round(time.monotonic() - shown, 1)
        if entry is not None:
            res["text"] = entry.get().strip()
        root.destroy()

    def on_ok():
        if a["kind"] == "text":
            if len(entry.get().strip()) < a.get("min_chars", 1):
                hint.config(text="коротко — нужна проверяемая строка", fg="#c44")
                return
        finish("done")

    btn_ok.config(command=on_ok)
    btn_skip.config(command=lambda: finish("skipped"))

    dwell = a["dwell_sec"]
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

    if a["kind"] == "text" and res["answer"] == "done" and not res["text"]:
        res["answer"] = "empty"
    return res


def show_console(alarm_id):
    """Запасной вариант, если tkinter нет."""
    a = ALARMS[alarm_id]
    shown = time.monotonic()
    print("\n" + "=" * 60)
    print(a["title"])
    print(a["text"])
    if a["dwell_sec"] > 0:
        print("\n[ждём %d с]" % a["dwell_sec"])
        time.sleep(a["dwell_sec"])
    try:
        ans = input("\nсделал? [д/н] ").strip().lower()
    except EOFError:
        return {"answer": "timeout", "text": "", "reaction": None}
    text = ""
    if a["kind"] == "text" and ans.startswith("д"):
        text = input("строка: ").strip()
        if len(text) < a.get("min_chars", 1):
            return {"answer": "empty", "text": text,
                    "reaction": round(time.monotonic() - shown, 1)}
    return {"answer": "done" if ans.startswith("д") else "skipped",
            "text": text, "reaction": round(time.monotonic() - shown, 1)}


def fire(alarm_id):
    res = show_window(alarm_id)
    log_write({
        "alarm": alarm_id,
        "answer": res["answer"],
        "reaction": res["reaction"],
        "chars": len(res["text"]),
        "text": res["text"],
        "week_day": week_day_number(),
    })
    return res


# ─── отчёт ───────────────────────────────────────────────────────────────────
def report():
    rows = log_read()
    if not rows:
        print("журнал пуст")
        return
    start = date.fromisoformat(state_read()["week_start"])
    rows = [r for r in rows
            if date.fromisoformat(r["ts"][:10]) >= start]

    print("\nнеделя с %s, день %d из %d" % (start.isoformat(), week_day_number(), CONFIG["week_days"]))
    print("-" * 64)
    print("%-14s %6s %6s %6s %6s %8s" % ("будильник", "всего", "сдел", "проп", "молч", "мгнов"))
    total_silent = total_empty = 0
    for aid in ACTIVE:
        sub = [r for r in rows if r["alarm"] == aid]
        if not sub:
            continue
        done = sum(1 for r in sub if r["answer"] == "done")
        skip = sum(1 for r in sub if r["answer"] == "skipped")
        silent = sum(1 for r in sub if r["answer"] == "timeout")
        empty = sum(1 for r in sub if r["answer"] == "empty")
        margin = ALARMS[aid]["dwell_sec"] + CONFIG["instant_margin_sec"]
        instant = sum(1 for r in sub
                      if r["answer"] == "done" and r.get("reaction") is not None
                      and r["reaction"] < margin)
        total_silent += silent
        total_empty += empty
        print("%-14s %6d %6d %6d %6d %8d" % (aid, len(sub), done, skip, silent, instant))
    print("-" * 64)
    print("не ответил:   %d" % total_silent)
    print("пустых:       %d" % total_empty)
    print("\nмгнов — нажал почти сразу после выдержки. Не нарушение, но смотри на это число.")
    if week_day_number() > CONFIG["week_days"]:
        print("\nНЕДЕЛЯ КОНЧИЛАСЬ. Перепиши вопросы своими сегодняшними словами,")
        print("в спокойный день, ничего не держа открытым. Потом: --newweek")


# ─── цикл ────────────────────────────────────────────────────────────────────
def run_loop():
    print("будильник запущен, день %d из %d" % (week_day_number(), CONFIG["week_days"]))
    print("журнал: %s" % CONFIG["log_path"])
    current_day = None
    queue = []
    while True:
        now = datetime.now()
        if current_day != now.date():
            current_day = now.date()
            queue = [(w, a) for w, a in plan_day(current_day) if w > now]
            print("[%s] план на день: %d окон" % (now.strftime("%H:%M"), len(queue)))
        if week_day_number() > CONFIG["week_days"]:
            print("неделя кончилась — вопросы изношены. Перепиши и запусти --newweek")
            return
        if queue and now >= queue[0][0]:
            _, aid = queue.pop(0)
            fire(aid)
        time.sleep(CONFIG["poll_sec"])


def selftest():
    print("план на сегодня:")
    for when, aid in plan_day(date.today()):
        print("  %s  %s" % (when.strftime("%H:%M"), aid))
    print("\nпроверка журнала:")
    probe = CONFIG["log_path"]
    CONFIG["log_path"] = probe + ".selftest"
    for i in range(6):
        log_write({"alarm": "vsluh", "answer": ["done", "skipped", "timeout"][i % 3],
                   "reaction": 3.0 + i, "chars": 0, "text": "", "week_day": 1})
    rows = log_read()
    print("  записано и прочитано: %d строк" % len(rows))
    os.remove(CONFIG["log_path"])
    CONFIG["log_path"] = probe
    print("ок")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--test", metavar="ID", help="показать одно окно прямо сейчас")
    p.add_argument("--report", action="store_true")
    p.add_argument("--newweek", action="store_true")
    p.add_argument("--selftest", action="store_true")
    args = p.parse_args()

    if args.selftest:
        selftest()
    elif args.newweek:
        state_write({"week_start": date.today().isoformat()})
        print("новая неделя с %s" % date.today().isoformat())
    elif args.report:
        report()
    elif args.test:
        if args.test not in ALARMS:
            print("нет такого: %s\nесть: %s" % (args.test, ", ".join(ALARMS)))
            sys.exit(1)
        res = fire(args.test)
        print(res)
    else:
        if not os.path.exists(CONFIG["state_path"]):
            state_write({"week_start": date.today().isoformat()})
        run_loop()


if __name__ == "__main__":
    main()
