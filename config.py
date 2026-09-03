#!/usr/bin/env python3
"""Конфиг ключей проекта (30.08.2026).

Ключи живут в папке config/ проекта, файлом в её стиле именования:
config/cryptoquant_config.json (рядом с coinglass_config,
telegram_config и почтовым). Прежнее место config.json в корне
понимается для совместимости. С 03.09 (правило владельца: экспорт из
окружения не используем) ключ читается ИЗ ФАЙЛА функцией get();
coinglass_fetch уже на ней. load() оставлена для cryptoquant_fetch и
cq_scheduler, которые пока читают os.environ: она кладёт значения из
файла в окружение, и файл теперь главнее экспорта.

Формат config/cryptoquant_config.json:
    {
      "CQ_TOKEN": "...",
      "COINGLASS_KEY": "..."
    }

Гигиена: chmod 600 config/cryptoquant_config.json; папка config/
и так в гитигноре.
"""
import json
import os
from pathlib import Path


def _spots(path: str | None = None) -> list[Path]:
    here = Path(__file__).resolve().parent
    return ([Path(path)] if path else
            [Path("config/cryptoquant_config.json"),
             here / "config" / "cryptoquant_config.json",
             Path("config/config.json"),        # общий файл ключей
             here / "config" / "config.json",
             Path("config.json"),               # прежнее место
             here / "config.json"])


def _read(path: str | None = None) -> dict:
    for src in _spots(path):
        if not src.exists():
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            return data
    return {}


def get(key: str, path: str | None = None) -> str:
    """Ключ ТОЛЬКО ИЗ ФАЙЛА конфига (03.09, правило владельца: экспорт из
    окружения не используем — переменная живёт в одном окне терминала,
    у цикла и служб её нет, и сборщики молча простаивали сутки).
    Нет файла или ключа — пустая строка."""
    v = _read(path).get(key)
    return v.strip() if isinstance(v, str) else ""


def load(path: str | None = None) -> bool:
    """Положить ключи из файла в окружение — для потребителей, которые
    ещё читают os.environ (cryptoquant_fetch, cq_scheduler). С 03.09
    ФАЙЛ ГЛАВНЕЕ: значение из файла перекрывает экспорт, а не уступает
    ему (было setdefault) — источник ключа один, спорить не с чем.
    Новым потребителям читать через get(), окружение не трогать.
    Возвращает, нашёлся ли файл; нет файла или битый JSON — False."""
    here = Path(__file__).resolve().parent
    spots = ([Path(path)] if path else
             [Path("config/cryptoquant_config.json"),
              here / "config" / "cryptoquant_config.json",
              Path("config/config.json"),        # общий файл ключей
              here / "config" / "config.json",
              Path("config.json"),               # прежнее место
              here / "config.json"])
    found = False
    for src in spots:
        if not src.exists():
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for k, v in data.items():
            if isinstance(v, str) and v.strip():
                os.environ[str(k)] = v.strip()
        found = True
        break
    return found


if __name__ == "__main__":
    ok = load()
    keys = [k for k in ("CQ_TOKEN", "COINGLASS_KEY") if os.environ.get(k)]
    print(f"конфиг {'найден' if ok else 'НЕ найден'} · "
          f"ключи в окружении: {', '.join(keys) or 'нет'}")
    if not ok:
        here = Path(__file__).resolve().parent
        print("искал:", ", ".join(str(p) for p in
              [Path("config/cryptoquant_config.json"),
               Path("config/config.json"), Path("config.json"),
               here / "config" / "config.json"]))
