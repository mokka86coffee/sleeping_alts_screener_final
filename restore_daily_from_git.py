"""Восстановление дневного архива снимков из git-истории.

Запуск из корня репозитория:
    python restore_daily_from_git.py            # найдёт latest.json сам
    python restore_daily_from_git.py --file output/latest.json
    python restore_daily_from_git.py --dry      # показать, не писать

Зачем. Рабочие снимки ротируются (prune_runs, последние RUNS_KEEP
штук ≈ трое суток истории), и материал замеров Р-16/Р-22/Р-23 в
каталоге не выжил. Но run.py коммитит и пушит выходной каталог каждый
прогон — история latest.json в git и есть история прогонов. Скрипт
идёт по коммитам, затронувшим latest.json, берёт ПОСЛЕДНИЙ коммит
каждого календарного дня (то же прореживание, которым замеры читают
историю) и выкладывает содержимое в RUNS_DIR/daily/run-ГГГГММДД.json.

Ничего не удаляет и не перезаписывает: день, у которого файл в daily
уже есть (например, записанный новым save_snapshot), пропускается —
живой прогон точнее восстановленного.

Порядок работы — два шага, от надёжного к возможному:
1) забэкфилл из ЖИВЫХ снимков RUNS_DIR (run-*.json ещё не съедены
   ротацией): по дню — последний, в daily. Работает всегда и спасает
   те дни, что пока на диске.
2) git-история latest.json — только если файл вообще коммитился;
   при output/ в .gitignore этот шаг честно скажет, что истории нет.

Требует запуска из корня проекта; git нужен только второму шагу.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

try:
    from core_config import RUNS_DIR
except Exception:
    RUNS_DIR = Path("output/runs")


def sh(*args: str) -> str:
    return subprocess.run(args, check=True, capture_output=True,
                          text=True).stdout


# Кандидаты пути, когда файла нет среди отслеживаемых. Порядок — от
# вероятного к экзотике; --file всегда сильнее любого поиска.
PATH_GUESSES = ("output/latest.json", "latest.json", "docs/latest.json",
                "public/latest.json", "site/latest.json")


def find_latest_path() -> str | None:
    """Путь latest.json: сначала отслеживаемые файлы текущей ветки,
    затем история ВСЕХ веток, включая удалённые.

    Второй шаг — не перестраховка: выходной каталог часто стоит в
    .gitignore рабочей ветки, а публикация идёт пушем в отдельную
    ветку (gh-pages) — тогда ls-files пуст, но git log --all историю
    видит, и git show достаёт содержимое по sha без переключения
    веток.
    """
    try:
        files = sh("git", "ls-files").splitlines()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None
    hits = [f for f in files if f.endswith("latest.json")]
    if hits:
        return hits[0]
    for guess in PATH_GUESSES:
        try:
            out = sh("git", "log", "--all", "-1", "--format=%H",
                     "--", guess)
        except subprocess.CalledProcessError:
            continue
        if out.strip():
            print(f"→ в текущей ветке файла нет, найден в истории "
                  f"веток: {guess}")
            return guess
    return None


def backfill_from_runs() -> int:
    """Дневной архив из живых снимков рабочего каталога.

    Ротация держит последние RUNS_KEEP прогонов — обычно считанные
    дни, но и их терять незачем: каждый спасённый день приближает
    первые распределения Р-22/Р-23 на сутки.
    """
    if not RUNS_DIR.is_dir():
        return 0
    last_by_day: dict[str, Path] = {}
    for p in sorted(RUNS_DIR.glob("run-*.json")):
        if p.is_file() and len(p.stem) >= 17:      # run-ГГГГММДД-ЧЧММ
            last_by_day[p.stem[4:12]] = p
    daily = RUNS_DIR / "daily"
    saved = 0
    for day, src in sorted(last_by_day.items()):
        out = daily / f"run-{day}.json"
        if out.exists():
            continue
        try:
            json.loads(src.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        daily.mkdir(parents=True, exist_ok=True)
        out.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        saved += 1
    if saved:
        print(f"→ забэкфилл из живых снимков: {saved} дн (RUNS_DIR/daily)")
    return saved


def main() -> int:
    ap = argparse.ArgumentParser(description="Дневной архив из git-истории")
    ap.add_argument("--file", default="", help="путь latest.json в репо")
    ap.add_argument("--dry", action="store_true", help="показать, не писать")
    a = ap.parse_args()

    saved = backfill_from_runs()

    path = a.file or find_latest_path()
    if not path:
        if saved:
            print("→ git-истории нет, но живые снимки спасены — дальше "
                  "daily копится прогонами")
            return 0
        print("✗ latest.json не найден ни среди отслеживаемых файлов, ни "
              "в истории веток.")
        print("  Диагностика по шагам:")
        print("    git check-ignore -v output/latest.json   # игнорится?")
        print("    git branch -a                            # есть gh-pages?")
        print("    git fetch origin '+refs/heads/*:refs/remotes/origin/*'")
        print("  После fetch запустить снова; либо явно: "
              "--file путь/в/той/ветке")
        return 1
    print(f"→ файл: {path}")

    # Коммиты, менявшие файл: дата дня + sha, от старых к новым —
    # последняя запись дня перетирает предыдущие, остаётся вечерняя.
    try:
        # --all: история берётся по всем веткам, включая удалённые —
        # публикация в gh-pages иначе осталась бы невидимой.
        log_out = sh("git", "log", "--all", "--reverse",
                     "--format=%H %cs", "--", path)
    except subprocess.CalledProcessError as exc:
        print(f"✗ git log не удался: {exc.stderr.strip() or exc}")
        return 1
    last_by_day: dict[str, str] = {}
    for line in log_out.splitlines():
        sha, day = line.split()
        last_by_day[day] = sha
    if not last_by_day:
        print("✗ история файла пуста")
        return 1
    days = sorted(last_by_day)
    print(f"→ дней в истории: {len(days)} ({days[0]} — {days[-1]})")

    daily = RUNS_DIR / "daily"
    written = skipped = broken = 0
    for day in days:
        out = daily / f"run-{day.replace('-', '')}.json"
        if out.exists():
            skipped += 1
            continue
        try:
            payload = sh("git", "show", f"{last_by_day[day]}:{path}")
            json.loads(payload)          # битый снимок в архив не кладём
        except (subprocess.CalledProcessError, ValueError):
            broken += 1
            continue
        if a.dry:
            written += 1
            continue
        daily.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(out)
        written += 1

    verb = "восстановилось бы" if a.dry else "восстановлено"
    print(f"✓ {verb}: {written} дн | пропущено (уже есть): {skipped}"
          + (f" | битых: {broken}" if broken else ""))
    if written and not a.dry:
        print(f"  каталог: {daily} — measure_journal.py возьмёт его сам")
    return 0


if __name__ == "__main__":
    sys.exit(main())
