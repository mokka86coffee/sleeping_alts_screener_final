#!/usr/bin/env python3
"""Конфиг ключей проекта (30.08.2026).

Ключи живут в папке config/ проекта, файлом в её стиле именования:
config/cryptoquant_config.json (рядом с coinglass_config,
telegram_config и почтовым). Прежнее место config.json в корне
понимается для совместимости. Модуль читает его и ПОДКЛАДЫВАЕТ значения в окружение
(setdefault), поэтому все существующие потребители — coinglass_fetch
(COINGLASS_KEY), cryptoquant_fetch и cq_scheduler (CQ_TOKEN), любые
будущие — работают без переделки; явный export, если он есть,
по-прежнему главнее файла.

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


def load(path: str | None = None) -> bool:
    """Подложить ключи из config.json в окружение. Возвращает,
    нашёлся ли файл. Тихая: нет файла или битый JSON — False без
    исключений, окружение остаётся как было."""
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
                os.environ.setdefault(str(k), v.strip())
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
