#!/usr/bin/env python3
"""Суточный планировщик дозабора CryptoQuant (30.08.2026).

Крутится вечным процессом: раз в сутки, в 01:10 UTC (дневка CQ к
этому часу закрыта), запускает cryptoquant_fetch.py --update и
дописывает свежие дни поверх архива. При старте сразу проверяет
свежесть архива и дотягивает, если тот старше двадцати часов.
Неудача — три ретрая через полчаса, лог в <out>/_fetch.log,
процесс не умирает никогда.

Запуск фоном:
    export CQ_TOKEN="..."
    nohup python3 cq_scheduler.py \
        --journal /путь/leaders.json --out /путь/cq_v2 >/dev/null 2>&1 &

Либо из своего планировщика: from cq_scheduler import ensure_fresh
и звать ensure_fresh(journal, out) раз в час — сама решит, пора ли.
"""
import argparse
import datetime as dt
import os
import subprocess
import sys
import time
from pathlib import Path

FETCH = Path(__file__).resolve().parent / "cryptoquant_fetch.py"
RUN_AT_UTC = (1, 10)          # час, минута
STALE_HOURS = 20
RETRIES, RETRY_SLEEP = 3, 1800


def log(out: Path, msg: str) -> None:
    line = f"{dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    out.mkdir(exist_ok=True)
    with open(out / "_fetch.log", "a") as f:
        f.write(line + "\n")


def archive_age_hours(out: Path) -> float:
    p = out / "_summary.json"
    if not p.exists():
        return 1e9
    return (time.time() - p.stat().st_mtime) / 3600


def run_fetch(journal: str, out: Path) -> bool:
    cmd = [sys.executable, str(FETCH), "--update",
           "--journal", journal, "--out", str(out)]
    for i in range(1, RETRIES + 1):
        log(out, f"дозабор, попытка {i}: {' '.join(cmd[1:])}")
        r = subprocess.run(cmd, capture_output=True, text=True)
        tail = (r.stdout or r.stderr).strip().splitlines()[-1:] or ["?"]
        log(out, f"код {r.returncode} · {tail[0]}")
        if r.returncode == 0:
            return True
        time.sleep(RETRY_SLEEP)
    return False


def ensure_fresh(journal: str, out: Path) -> bool:
    """Дотянуть архив, если он старше STALE_HOURS. Для импорта в
    чужой планировщик: дёшево звать хоть каждый час."""
    age = archive_age_hours(out)
    if age < STALE_HOURS:
        return True
    log(out, f"архив старше {STALE_HOURS} ч (возраст {age:.1f} ч)")
    return run_fetch(journal, out)


def seconds_to_next_run(now: dt.datetime) -> float:
    tgt = now.replace(hour=RUN_AT_UTC[0], minute=RUN_AT_UTC[1],
                      second=0, microsecond=0)
    if tgt <= now:
        tgt += dt.timedelta(days=1)
    return (tgt - now).total_seconds()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", required=True)
    ap.add_argument("--out", default="cq_v2")
    a = ap.parse_args()
    out = Path(a.out)

    try:                                   # ключи из config.json,
        from config import load as _cfg   # export главнее файла
        _cfg()
    except Exception:
        pass
    if not os.environ.get("CQ_TOKEN", "").strip():
        print("нет CQ_TOKEN в окружении")
        return 1

    log(out, "планировщик поднят")
    ensure_fresh(a.journal, out)          # догнать при старте
    while True:
        pause = seconds_to_next_run(dt.datetime.now(dt.timezone.utc))
        log(out, f"сон до 01:10 UTC ({pause/3600:.1f} ч)")
        time.sleep(pause)
        try:
            run_fetch(a.journal, out)
        except Exception as e:            # что бы ни случилось — жить
            log(out, f"неожиданное: {e}")


if __name__ == "__main__":
    sys.exit(main())
