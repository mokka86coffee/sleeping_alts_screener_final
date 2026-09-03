"""Сводка прогона в Телеграм — брат send_brief_email, доставка другая.

Текст НЕ собирается заново: берутся те же load_report_data и
build_letter из send_brief_email (один источник правды — собранный
brief.html), меняется только транспорт: Telegram Bot API sendMessage.

Настройка один раз:
  1. В Телеграме написать @BotFather команду /newbot, назвать бота —
     он выдаст токен вида 123456:ABC-DEF...
  2. Написать СВОЕМУ новому боту любое сообщение (иначе он не может
     писать первым).
  3. Узнать свой chat_id: написать @userinfobot, он ответит числом.
  4. Вписать токен и chat_id в output/telegram_config.json (шаблон
     создастся при первом запуске; файл в output — в паблик не
     попадает, как и почтовый конфиг).

Проверка:  python send_brief_telegram.py --dry   (печать без отправки)
Живьём:    python send_brief_telegram.py
Любой файл: python send_brief_telegram.py --file output/bubble_report.txt
            (так удобно слать сводку пузырь-бота)

В прогоне зовётся из run.py после письма; сбой Телеграма прогон не
роняет — как и у почты.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

try:
    from core_config import BASE_DIR
    from core_http import log
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
    def log(msg: str) -> None:
        print(msg)

CONFIG_PATH = BASE_DIR / "output" / "telegram_config.json"

CONFIG_TEMPLATE = {
    "bot_token": "",
    "chat_id": "",
    "enabled": True,
    "_note": ("Токен — от @BotFather (/newbot). chat_id — спросить у "
              "@userinfobot. Своему боту сначала написать любое "
              "сообщение, иначе Телеграм не даст ему писать вам. "
              "enabled: false выключает отправку без удаления файла."),
}

# Телеграм режет сообщения длиннее 4096 символов — режем сами по
# границам строк с запасом.
CHUNK_LIMIT = 3900


def load_config() -> dict | None:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
            encoding="utf-8")
        log(f"  телеграм: создан шаблон {CONFIG_PATH.name} — "
            f"впишите bot_token и chat_id")
        return None
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"  телеграм: конфиг не читается ({e}) — пропуск")
        return None
    if not cfg.get("enabled", True):
        log("  телеграм: enabled=false в конфиге — пропуск")
        return None
    if not (cfg.get("bot_token") and cfg.get("chat_id")):
        log("  телеграм: bot_token/chat_id не заполнены — пропуск")
        return None
    return cfg


def split_chunks(text: str, limit: int = CHUNK_LIMIT) -> list[str]:
    """Режет длинный текст на сообщения по границам строк."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    buf: list[str] = []
    size = 0
    for line in text.splitlines():
        add = len(line) + 1
        if size + add > limit and buf:
            chunks.append("\n".join(buf))
            buf, size = [], 0
        # сверхдлинная одиночная строка — режется жёстко
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
            add = len(line) + 1
        buf.append(line)
        size += add
    if buf:
        chunks.append("\n".join(buf))
    return chunks


def send_telegram(text: str, cfg: dict) -> bool:
    """Шлёт текст (кусками при необходимости). True — всё ушло."""
    url = (f"https://api.telegram.org/bot{cfg['bot_token']}"
           f"/sendMessage")
    ok = True
    for i, chunk in enumerate(split_chunks(text)):
        payload = json.dumps({
            "chat_id": cfg["chat_id"],
            "text": chunk,
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload,
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if not body.get("ok"):
                log(f"  телеграм: API ответил ошибкой: "
                    f"{body.get('description')}")
                ok = False
        except Exception as e:
            log(f"  телеграм: отправка не прошла "
                f"({type(e).__name__}: {e})")
            ok = False
        if i:
            time.sleep(0.3)
    return ok


def main(dry: bool = False, file_path: str | None = None) -> int:
    if file_path:
        try:
            text = Path(file_path).read_text(encoding="utf-8")
        except OSError as e:
            log(f"  телеграм: файл не читается ({e})")
            return 1
        subject = Path(file_path).name
    else:
        from send_brief_email import build_letter, load_report_data
        try:
            stars, market = load_report_data()
        except Exception as e:
            log(f"  телеграм: brief.html не разобран "
                f"({type(e).__name__}: {e})")
            return 1
        subject, text = build_letter(stars, market)
        text = f"{subject}\n\n{text}"

    if dry:
        print(f"── {subject} ──\n{text}")
        n = len(split_chunks(text))
        print(f"\n[dry] сообщений ушло бы: {n}")
        return 0

    cfg = load_config()
    if cfg is None:
        return 0          # причина уже в логе (load_config)
    n = len(split_chunks(text))
    ok = send_telegram(text, cfg)
    log(f"  телеграм: {'ушло' if ok else 'НЕ ушло'} · кусков {n} · {len(text)} симв.")
    return 0 if ok else 1


def send_after_run() -> None:
    """Вызов из run.py: сбой Телеграма прогон не роняет."""
    try:
        main()
    except Exception as e:
        log(f"  телеграм: {type(e).__name__}: {e} — прогон продолжается")


if __name__ == "__main__":
    dry = "--dry" in sys.argv
    fp = None
    if "--file" in sys.argv:
        i = sys.argv.index("--file")
        fp = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
        if not fp:
            print("после --file нужен путь к файлу")
            sys.exit(2)
    sys.exit(main(dry=dry, file_path=fp))
