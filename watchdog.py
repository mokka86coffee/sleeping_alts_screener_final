"""СТОРОЖ ПРОЦЕССОВ (29.09, владелец: «добавь в прогон, чтобы он проверял такие вещи и убивал лишние процессы, а нужные запускал, если их нет»).

Раз в минуту из прогона (run.py --loop, отдельная нить): по каждому нужному процессу —
  · копий нет → запуск (те же команды и логи, что у прогона: liq_stream.py → output/liq_stream.log, fast_tier.py --loop → output/fast_tier.log,
    fast_server.py → output/fast_server.log);
  · копий больше одной → лишние гасятся (SIGTERM), остаётся одна: у liq_stream — дочерний процесс прогона, иначе самая новая (свежий код).
Считаются только настоящие python-процессы со скриптом в аргументах (обёртки zsh -c и grep не в счёт). Сам run.py не трогается: лишние копии
прогона только пишутся в лог. Ничего не запускается и не гасится, пока стоит флаг WATCHDOG_ENABLED = False (core_config).

    .venv/bin/python watchdog.py          # показать, что запущено и что сделал бы сторож (ничего не трогает)
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
# имя → (команда запуска, лог, аргумент, по которому опознаётся процесс)
NEED = {
    "liq_stream.py": (["liq_stream.py"], "liq_stream.log", None),
    "fast_tier.py": (["fast_tier.py", "--loop"], "fast_tier.log", "--loop"),
    "fast_server.py": (["fast_server.py"], "fast_server.log", None),
}


def _secs(t: str) -> int:
    """etime macOS: [[дн-]чч:]мм:сс → секунды"""
    d, _, r = t.rpartition("-")
    a = [int(x) for x in r.split(":")]
    while len(a) < 3:
        a.insert(0, 0)
    return int(d or 0) * 86400 + a[0] * 3600 + a[1] * 60 + a[2]


def procs(script: str, arg: str | None = None) -> list[tuple[int, int, int]]:
    """[(pid, ppid, возраст в секундах)] настоящих python-процессов, запущенных со скриптом script (и аргументом arg)"""
    out = subprocess.run(["ps", "-eo", "pid=,ppid=,etime=,command="], capture_output=True, text=True).stdout
    res = []
    for ln in out.splitlines():
        p = ln.split(None, 3)
        if len(p) < 4:
            continue
        toks = p[3].split()
        exe = os.path.basename(toks[0]).lower()
        if not (exe.startswith("python") or "python" in toks[0].lower()):
            continue
        if any(os.path.basename(t) == script for t in toks[1:3]) and (arg is None or arg in toks):
            res.append((int(p[0]), int(p[1]), _secs(p[2])))
    return res


def check(act: bool = True, keep_child_of: int | None = None, log=print) -> list[str]:
    """→ список сказанного/сделанного; act=False — ничего не трогать"""
    said = []
    me = os.getpid()
    for script, (cmd, logname, arg) in NEED.items():
        pr = [x for x in procs(script, arg) if x[0] != me]
        if not pr:
            said.append(f"{script}: нет — " + ("запуск" if act else "запустил бы"))
            if act:
                fh = open(BASE_DIR / "output" / logname, "a", encoding="utf-8")
                subprocess.Popen([sys.executable] + cmd, cwd=BASE_DIR, stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)
            continue
        if len(pr) > 1:
            keep = next((x for x in pr if keep_child_of and x[1] == keep_child_of), None) or min(pr, key=lambda x: x[2])
            for pid, ppid, age in pr:
                if pid == keep[0]:
                    continue
                said.append(f"{script}: лишняя копия pid {pid} (возраст {age // 3600} ч) — " + ("гашу" if act else "погасил бы") + f"; остаётся {keep[0]}")
                if act:
                    try:
                        os.kill(pid, signal.SIGTERM)
                    except OSError as e:
                        said.append(f"  не вышло: {e}")
    me_runs = [x for x in procs("run.py", "--loop") if x[0] != me]
    if len(me_runs) > 1:
        said.append(f"run.py --loop: копий {len(me_runs)} ({', '.join(str(x[0]) for x in me_runs)}) — не трогаю, решает владелец")
    for s in said:
        log(f"→ Сторож: {s}")
    return said


if __name__ == "__main__":
    for pid in NEED:
        print(pid, procs(pid, NEED[pid][2]))
    print("run.py:", procs("run.py", "--loop"))
    print(check(act=False, log=lambda s: None) or "всё на месте")
