"""ХВОСТ БОЛЬШОГО ЖУРНАЛА БЕЗ ЧТЕНИЯ ЦЕЛИКОМ (28.10).
output/queue_log.jsonl дорос до 683 МБ; read_text().splitlines()[-N:] держал весь файл в памяти (пик 2,7 ГБ на одно чтение),
а за прогон run.py таких чтений было пять-шесть — процесс раздувался до 4–5 ГБ. Здесь файл читается с конца блоками по 1 МБ."""
from __future__ import annotations

from pathlib import Path

_BLOCK = 1 << 20


def tail_lines(path: Path | str, n: int) -> list[str]:
    """последние n строк файла (как read_text().splitlines()[-n:]); нет файла — OSError, как у read_text"""
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buf = b""
        while pos > 0 and buf.count(b"\n") <= n:
            step = min(_BLOCK, pos)
            pos -= step
            f.seek(pos)
            buf = f.read(step) + buf
    lines = buf.decode("utf-8", errors="replace").splitlines()
    if pos > 0:
        lines = lines[1:]          # первая строка блока могла начаться с середины
    return lines[-n:] if n > 0 else []
