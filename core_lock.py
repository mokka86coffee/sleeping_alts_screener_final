"""ЗАМОК ФАЙЛА (16.09). Журнал прогнозов переписывает forecasts.jsonl целиком (перевод старых строк в UTC,
исходы через день и три), а дозабор простоя из потока медленных дописывает в тот же файл. Если оба попадали
в одну секунду, строки дозабора терялись. Замок — отдельный файл рядом (<имя>.lock) под flock: его снимает
система, даже если процесс упал, и он работает и между потоками, и между процессами.
"""
from __future__ import annotations

import contextlib
import os
import time

try:
    import fcntl
except ImportError:          # Windows — замка нет, поведение как раньше
    fcntl = None


@contextlib.contextmanager
def locked(path, timeout_s: float = 120.0):
    lock_path = f"{path}.lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock_path)), exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        if fcntl is not None:
            deadline = time.time() + timeout_s
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.time() > deadline:
                        raise TimeoutError(f"замок {lock_path} занят дольше {timeout_s:.0f} с")
                    time.sleep(0.1)
        yield
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(fd)
