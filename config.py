#!/usr/bin/env python3
"""Конфиг ключей проекта (30.08.2026).

Ключи живут в папке config/ проекта, файлом в её стиле именования:
config/cryptoquant_config.json (рядом с coinglass_config,
telegram_config и почтовым). Прежнее место config.json в корне
понимается для совместимости.

С 03.09 ЭКСПОРТА НЕТ (правило владельца): никакого `export KEY=…` в
терминале ни при каком запуске. Ключ читается ИЗ ФАЙЛА функцией get(),
файл переживает перезагрузку, окна терминала и службы — задать один раз.
coinglass_fetch и всё, что берёт сеть через него, уже на get().

load() — не экспорт, а внутренний мостик для двух модулей кванта
(cryptoquant_fetch, cq_scheduler), которые пока читают переменную
CQ_TOKEN по старому: она берёт значение из файла и отдаёт им под тем же
именем, ничего от пользователя не требуя; уже заданный экспорт при этом
ПЕРЕКРЫВАЕТСЯ файлом. Как только квант перейдёт на get(), load()
удалить.

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
    """Ключи из ВСЕХ найденных файлов конфига, слитые в один словарь:
    первый файл главнее по совпадающим ключам, недостающие добираются
    из следующих. Урок 03.09: рядом лежали cryptoquant_config.json с
    одним CQ_TOKEN и config.json со всеми ключами; чтение «первый
    найденный — и стоп» возвращало пустой COINGLASS_KEY, и прогон
    отвечал «нет ключа» при заполненном конфиге."""
    merged: dict = {}
    for src in _spots(path):
        if not src.exists():
            continue
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, str) and v.strip() and k not in merged:
                    merged[k] = v.strip()
    return merged


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
    data = _read()
    keys = [k for k in ("CQ_TOKEN", "COINGLASS_KEY", "ARKHAM_KEY")
            if isinstance(data.get(k), str) and data[k].strip()]
    found = [str(p) for p in _spots() if p.exists()]
    print(f"конфиг {'найден' if data else 'НЕ найден'} · файлы: "
          f"{', '.join(found) or 'нет'}")
    print(f"ключи: {', '.join(k + ' …' + data[k][-4:] for k in keys) or 'нет'}")
    ok = bool(data)
    if not ok:
        here = Path(__file__).resolve().parent
        print("искал:", ", ".join(str(p) for p in
              [Path("config/cryptoquant_config.json"),
               Path("config/config.json"), Path("config.json"),
               here / "config" / "config.json"]))
