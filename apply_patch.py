#!/usr/bin/env python3
"""Применение патчей из markdown к файлам проекта.

Читает .md с блоками «было»/«стало» и переносит их в исходники.

Зачем скрипт, а не руки: патчи для больших файлов (orbit 1994 строки,
flow_core 1498, dashboard 1399) состоят из пяти-десяти блоков, и
перенос глазами — это ровно та операция, где ошибка не видна сразу.

Главная гарантия — атомарность по файлу. Сначала все блоки
прогоняются вхолостую в памяти, и только если легли ВСЕ и результат
парсится как Python, файл переписывается. Частично применённый патч
опаснее непримененного: он выглядит как успех.

Запуск:
    python apply_patch.py patch-*.md                 сухой прогон
    python apply_patch.py patch-*.md --apply         записать
    python apply_patch.py patch-*.md --root ../repo  корень проекта
    python apply_patch.py patch-*.md --list          только разбор md
"""

from __future__ import annotations

import argparse
import ast
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Расширения, для которых имя в заголовке считается целевым файлом.
CODE_SUFFIXES = {".py", ".js", ".css", ".html", ".json", ".md", ".txt"}

# Заголовок markdown любого уровня.
RE_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")

# Путь в обратных кавычках либо после «файл:». Второе имеет приоритет:
# заголовок может упоминать несколько файлов, и явная пометка снимает
# двусмысленность.
RE_EXPLICIT = re.compile(r"(?:файл|file)\s*[:·]\s*`?([^\s`]+)`?", re.I)
RE_BACKTICK = re.compile(r"`([^`]+)`")

RE_FENCE = re.compile(r"^\s*(```+|~~~+)(.*)$")


@dataclass
class Change:
    """Одна замена: где, что на что, откуда взято."""
    target: str
    old: str
    new: str
    source: str          # имя md-файла
    line: int            # строка заголовка «было» в md


@dataclass
class Manual:
    """Блок, который нельзя применить автоматически."""
    target: str
    reason: str
    source: str
    line: int


@dataclass
class FileResult:
    path: Path
    applied: list[Change] = field(default_factory=list)
    already: list[Change] = field(default_factory=list)
    errors: list[tuple[Change, str]] = field(default_factory=list)
    text: str = ""
    changed: bool = False


# ─────────────────────────────────────────────────────────────
# Разбор markdown
# ─────────────────────────────────────────────────────────────
def _looks_like_path(token: str) -> bool:
    return Path(token).suffix.lower() in CODE_SUFFIXES


def _target_from_heading(text: str) -> str | None:
    """Целевой файл из текста заголовка, если он там назван."""
    m = RE_EXPLICIT.search(text)
    if m and _looks_like_path(m.group(1)):
        return m.group(1)
    for token in RE_BACKTICK.findall(text):
        token = token.strip()
        if _looks_like_path(token):
            return token
    return None


def _read_fence(lines: list[str], start: int) -> tuple[str | None, int]:
    """Первый огороженный блок после start и до следующего заголовка.

    Возвращает содержимое и индекс строки после закрывающей ограды.
    Прозаические абзацы между заголовком и оградой пропускаются: они
    объясняют блок человеку и к содержимому не относятся.
    """
    i = start
    while i < len(lines):
        if RE_HEADING.match(lines[i]):
            return None, i
        m = RE_FENCE.match(lines[i])
        if m:
            marker = m.group(1)
            body: list[str] = []
            i += 1
            while i < len(lines):
                close = RE_FENCE.match(lines[i])
                if close and close.group(1).startswith(marker[0] * 3):
                    return "\n".join(body), i + 1
                body.append(lines[i].rstrip("\n"))
                i += 1
            return None, i          # ограда не закрыта
        i += 1
    return None, i


def parse_patch(path: Path) -> tuple[list[Change], list[Manual]]:
    """Разбирает один md на список замен и список ручных блоков."""
    lines = path.read_text(encoding="utf-8").splitlines()
    changes: list[Change] = []
    manual: list[Manual] = []

    target: str | None = None
    pending_old: tuple[str, int] | None = None

    i = 0
    while i < len(lines):
        m = RE_HEADING.match(lines[i])
        if not m:
            i += 1
            continue

        head = m.group(2)
        head_line = i + 1
        found = _target_from_heading(head)
        if found:
            target = found

        low = head.lower().lstrip()
        if low.startswith("было"):
            code, nxt = _read_fence(lines, i + 1)
            if code is None:
                manual.append(Manual(target or "?", "у блока «было» нет кода",
                                     path.name, head_line))
                pending_old = None
            else:
                if pending_old is not None:
                    manual.append(Manual(target or "?",
                                         "два «было» подряд, без «стало»",
                                         path.name, pending_old[1]))
                pending_old = (code, head_line)
            i = nxt
            continue

        if low.startswith("стало"):
            code, nxt = _read_fence(lines, i + 1)
            if code is None:
                manual.append(Manual(target or "?", "у блока «стало» нет кода",
                                     path.name, head_line))
            elif pending_old is None:
                manual.append(Manual(
                    target or "?",
                    "«стало» без «было»: якоря нет, нужна пара",
                    path.name, head_line,
                ))
            elif target is None:
                manual.append(Manual("?", "не назван целевой файл",
                                     path.name, head_line))
            else:
                changes.append(Change(target, pending_old[0], code,
                                      path.name, pending_old[1]))
            pending_old = None
            i = nxt
            continue

        # Заголовок не «было» и не «стало», а код под ним есть.
        #
        # Такой блок раньше пропадал бесследно: парсер его не видел, и
        # отчёт показывал «ручных 0», то есть полный успех. Ровно так
        # вставка констант LEV_* не попала в flow_config, а импорт
        # flow_leverage при этом раскомментировался — патч применился
        # на пятнадцать блоков из шестнадцати и выглядел как чистый.
        #
        # Молчаливый пропуск опаснее отказа, поэтому осиротевший код
        # теперь попадает в ручные, а не исчезает.
        code, nxt = _read_fence(lines, i + 1)
        if code is not None and code.strip():
            manual.append(Manual(
                target or "?",
                f"код под заголовком «{head[:40]}» вне пары было/стало",
                path.name, head_line,
            ))
            i = nxt
            continue

        i += 1

    if pending_old is not None:
        manual.append(Manual(target or "?", "«было» без «стало»",
                             path.name, pending_old[1]))
    return changes, manual


# ─────────────────────────────────────────────────────────────
# Применение
# ─────────────────────────────────────────────────────────────
def apply_to_file(path: Path, changes: list[Change]) -> FileResult:
    """Прогоняет блоки по одному файлу. На диск не пишет.

    Блоки применяются последовательно к накопленному тексту, а не все
    к исходному: соседние правки часто перекрываются контекстом, и
    проверка по исходнику дала бы ложное «не найдено» на втором блоке.
    """
    res = FileResult(path=path)
    if not path.exists():
        for ch in changes:
            res.errors.append((ch, "файла нет"))
        return res

    text = path.read_text(encoding="utf-8")
    original = text

    for ch in changes:
        # Вставка: «стало» содержит «было» целиком плюс добавленные
        # строки. Якорь переживает применение, поэтому по одному его
        # наличию нельзя судить, применён блок или нет — второй запуск
        # вставил бы добавленное дважды. Для таких блоков признак
        # «уже применено» — присутствие «стало».
        #
        # Для удаления всё наоборот: «стало» является подмножеством
        # «было» и присутствует в тексте ДО применения. Там судить
        # нужно по якорю. Отсюда две ветки, а не одна проверка.
        insertion = ch.old in ch.new and ch.old != ch.new
        n_old = text.count(ch.old)

        if insertion and ch.new in text:
            res.already.append(ch)
        elif n_old == 1:
            text = text.replace(ch.old, ch.new, 1)
            res.applied.append(ch)
        elif n_old == 0:
            # Якорь не совпал либо блок уже применён. Различать
            # обязательно: первое — ошибка, второе — норма при
            # повторном запуске.
            if ch.new and ch.new in text:
                res.already.append(ch)
            else:
                res.errors.append((ch, "якорь «было» не найден"))
        else:
            res.errors.append((ch, f"якорь встречается {n_old} раз, нужен один"))

    res.text = text
    res.changed = text != original
    return res


def syntax_ok(path: Path, text: str) -> str | None:
    """Проверка синтаксиса для .py. Возвращает текст ошибки либо None.

    Дешёвая и ловит главное, чего боишься при переносе блоков руками, —
    поехавший отступ. Файл с битым отступом импортируется как рабочий
    ровно до первого вызова.
    """
    if path.suffix != ".py":
        return None
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as e:
        return f"строка {e.lineno}: {e.msg}"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Применяет md-патчи к исходникам")
    ap.add_argument("patches", nargs="+", help="файлы .md или каталоги с ними")
    ap.add_argument("--root", default=".", help="корень проекта (по умолчанию .)")
    ap.add_argument("--apply", action="store_true", help="записать изменения")
    ap.add_argument("--list", action="store_true", help="только разобрать md")
    ap.add_argument("--no-backup", action="store_true", help="не делать .bak")
    args = ap.parse_args()

    root = Path(args.root).resolve()

    md_files: list[Path] = []
    for raw in args.patches:
        p = Path(raw)
        if p.is_dir():
            md_files.extend(sorted(p.glob("*.md")))
        elif p.exists():
            md_files.append(p)
        else:
            print(f"пропуск: {raw} не найден")

    if not md_files:
        print("патчей не найдено")
        return 2

    all_changes: list[Change] = []
    all_manual: list[Manual] = []
    for md in md_files:
        ch, mn = parse_patch(md)
        all_changes.extend(ch)
        all_manual.extend(mn)
        print(f"{md.name}: блоков {len(ch)}, ручных {len(mn)}")

    if args.list:
        for ch in all_changes:
            head = ch.old.splitlines()[0][:60] if ch.old else ""
            print(f"  {ch.target:34s} строка {ch.line:4d}  {head}")
        for mn in all_manual:
            print(f"  РУЧНОЙ {mn.target:28s} строка {mn.line:4d}  {mn.reason}")
        return 0

    by_file: dict[str, list[Change]] = {}
    for ch in all_changes:
        by_file.setdefault(ch.target, []).append(ch)

    results: list[FileResult] = []
    for target, changes in sorted(by_file.items()):
        res = apply_to_file(root / target, changes)
        if res.changed:
            err = syntax_ok(root / target, res.text)
            if err:
                res.errors.append((changes[0], f"синтаксис после правки — {err}"))
        results.append(res)

    print("\n" + "=" * 56)
    bad = 0
    for res in results:
        rel = res.path.relative_to(root) if res.path.is_relative_to(root) else res.path
        mark = "ОШИБКА" if res.errors else "ок    "
        print(
            f"{mark}  {str(rel):34s} "
            f"легло {len(res.applied)}  уже было {len(res.already)}  "
            f"не легло {len(res.errors)}"
        )
        for ch, why in res.errors:
            bad += 1
            head = ch.old.splitlines()[0][:52] if ch.old else ""
            print(f"         {ch.source} строка {ch.line}: {why}")
            print(f"         якорь: {head}")

    for mn in all_manual:
        print(f"РУЧНОЙ  {mn.target:34s} {mn.source} строка {mn.line}: {mn.reason}")

    if bad:
        print(f"\nНе применено: {bad}. Файлы не тронуты — правка атомарна.")
        print("Частично применённый патч выглядит как успех, поэтому всё или ничего.")
        return 1

    if not args.apply:
        touched = [r for r in results if r.changed]
        print(f"\nСухой прогон. Готово к записи файлов: {len(touched)}.")
        print("Повторить с --apply.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    written = 0
    for res in results:
        if not res.changed:
            continue
        if not args.no_backup:
            shutil.copy2(res.path, res.path.with_suffix(res.path.suffix + f".bak-{stamp}"))
        res.path.write_text(res.text, encoding="utf-8")
        written += 1

    print(f"\nЗаписано файлов: {written}."
          + ("" if args.no_backup else f" Резервные копии: *.bak-{stamp}"))
    if all_manual:
        print(f"Осталось перенести руками блоков: {len(all_manual)} — см. выше.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
