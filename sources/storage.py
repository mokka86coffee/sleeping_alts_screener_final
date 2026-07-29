"""Хранение снимков прогонов: история результатов и последний срез."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.config import LATEST_JSON, OUTPUT_DIR, RUNS_DIR, RUNS_KEEP
from core.models import RunSnapshot

log = logging.getLogger(__name__)


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)


def write_atomic(path: Path, content: str) -> None:
    """Запись через временный файл: незавершённый прогон не портит отчёт."""
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def save_snapshot(snapshot: RunSnapshot) -> Path:
    """Сохраняет снимок прогона и обновляет latest."""
    ensure_dirs()

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    path = RUNS_DIR / f"run-{stamp}.json"

    payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=1)
    write_atomic(path, payload)
    write_atomic(LATEST_JSON, payload)

    prune_runs()
    return path


def prune_runs(keep: int = RUNS_KEEP) -> int:
    """Удаляет старые снимки, оставляя последние keep штук."""
    if not RUNS_DIR.exists():
        return 0
    files = sorted(RUNS_DIR.glob("run-*.json"))
    doomed = files[:-keep] if len(files) > keep else []
    for f in doomed:
        try:
            f.unlink()
        except OSError:
            pass
    return len(doomed)


def load_latest() -> dict | None:
    """Последний снимок, если он есть."""
    if not LATEST_JSON.exists():
        return None
    try:
        return json.loads(LATEST_JSON.read_text(encoding="utf-8"))
    except Exception as e:
        log.debug(f"Не удалось прочитать latest: {e}")
        return None


def load_history(limit: int = 30) -> list[dict]:
    """История прогонов от свежих к старым."""
    if not RUNS_DIR.exists():
        return []
    files = sorted(RUNS_DIR.glob("run-*.json"), reverse=True)[:limit]
    out: list[dict] = []
    for f in files:
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def compare_with_previous(current: RunSnapshot) -> dict[str, Any]:
    """Что изменилось с прошлого прогона: новые монеты и выбывшие."""
    prev = load_latest()
    if not prev:
        return {"has_previous": False, "new": [], "gone": [], "delta": {}}

    def tradable_set(data: dict) -> set:
        return {
            c.get("symbol") for c in data.get("candidates", [])
            if c.get("tradable")
        }

    prev_set = tradable_set(prev)
    curr_set = {c.get("symbol") for c in current.candidates if c.get("tradable")}

    prev_counts = prev.get("counts", {})
    delta = {
        key: current.counts.get(key, 0) - prev_counts.get(key, 0)
        for key in set(current.counts) | set(prev_counts)
    }

    return {
        "has_previous": True,
        "previous_timestamp": prev.get("timestamp", ""),
        "new": sorted(curr_set - prev_set),
        "gone": sorted(prev_set - curr_set),
        "delta": delta,
    }
