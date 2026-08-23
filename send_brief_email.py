"""Письмо-рапорт прогона: бриф и группы зала на почту.

Отправляется в конце КАЖДОГО прогона (вызов встроен в run.py после
сборки отчёта). Источник — тот же вшитый JSON, что читают экраны
(<script id="obfData"> внутри brief.html): письмо не пересобирает
звёзды и потому не трогает ни журнал предположений, ни состояние
сдвигов — урок двойной сборки соблюдён, побочных эффектов ноль.

Содержание: окно рынка с нотами, счета двух подходов, лидер с
причиной действия, заряженные на сжим, и три группы зала — брать /
в работе / закрыть; у «брать» и «закрыть» печатается причина
(act.why, у закрытия запасным ходом exitWhy). Критерии групп — те
же, что в зале: заявка = act.act == «брать», закрыть = позиция
книги с act.group == «exit», в работе — остальные позиции.

Настройка: output/email_config.json. Файл живёт именно в output/ —
каталог целиком в .gitignore, а run.py публикует «всё изменённое»
в ПУБЛИЧНЫЙ репозиторий GitHub Pages: конфиг с паролем в корне
уехал бы в интернет первым же прогоном. При первом запуске без
конфига скрипт сам пишет шаблон и объясняет, что заполнить.

Сбой почты никогда не роняет прогон: наружу отдаётся код возврата,
все исключения гасятся с записью в лог.
"""

from __future__ import annotations

import json
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formatdate
from pathlib import Path

try:
    from core_config import BASE_DIR, REPORT_PATH
    from core_http import log
except ImportError:                      # запуск вне окружения проекта
    BASE_DIR = Path(__file__).resolve().parent
    REPORT_PATH = BASE_DIR / "index.html"
    def log(msg: str) -> None:
        print(msg)

CONFIG_PATH = BASE_DIR / "output" / "email_config.json"
SITE_URL = "https://mokka86coffee.github.io/sleeping_alts_screener_final/"

CONFIG_TEMPLATE = {
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 465,
    "user": "",
    "password": "",
    "to": [""],
    "from_addr": "",
    "_note": ("Заполните user/password/to. Для Gmail нужен пароль "
              "приложения (myaccount.google.com/apppasswords), обычный "
              "пароль не подойдёт. Порт 465 — SSL, 587 — STARTTLS. "
              "Файл лежит в output/ и в git не попадает — не переносите "
              "его в корень: корень публикуется на GitHub Pages."),
}


# ─────────────────────────────────────────────────────────────
# Данные: тот же JSON, что видят экраны
# ─────────────────────────────────────────────────────────────
def load_report_data(brief_path: Path | None = None) -> tuple[list, dict]:
    """Достаёт stars и market из собранного brief.html."""
    path = brief_path or (REPORT_PATH.parent / "brief.html")
    html = path.read_text(encoding="utf-8")
    m = re.search(
        r'<script id="obfData" type="application/json">(.*?)</script>',
        html, re.S)
    if not m:
        raise ValueError(f"в {path.name} нет вшитых данных obfData")
    data = json.loads(m.group(1).replace("<\\/", "</"))
    return data.get("stars") or [], data.get("market") or {}


# ─────────────────────────────────────────────────────────────
# Группы зала — критерии те же, что в podium
# ─────────────────────────────────────────────────────────────
def split_groups(stars: list) -> dict:
    take, work, close = [], [], []
    for s in stars:
        act = s.get("act") or {}
        book = s.get("book") or None
        if book and (book.get("usd") or book.get("px")):
            if act.get("group") == "exit":
                close.append(s)
            else:
                work.append(s)
        elif act.get("act") == "брать":
            take.append(s)
    take.sort(key=lambda s: -(s.get("score") or 0))
    work.sort(key=lambda s: -((s.get("book") or {}).get("usd") or 0))
    close.sort(key=lambda s: -((s.get("book") or {}).get("usd") or 0))
    return {"take": take, "work": work, "close": close}


def _why_close(s: dict) -> str:
    act = s.get("act") or {}
    if act.get("why"):
        return act["why"]
    ew = s.get("exitWhy") or []
    return ew[0] if ew else "причина не названа"


def _why_take(s: dict) -> str:
    act = s.get("act") or {}
    if act.get("why"):
        return act["why"]
    ph = s.get("phase") or {}
    return ph.get("a") or "причина не названа"


def _pos_line(s: dict) -> str:
    """Строка позиции: тикер, деньги, ход от входа."""
    book = s.get("book") or {}
    usd = book.get("usd")
    entry, px = book.get("px"), s.get("px")
    run = ""
    if entry and px:
        try:
            run = f", ход {(float(px) / float(entry) - 1) * 100:+.1f}% от входа"
        except (TypeError, ValueError, ZeroDivisionError):
            run = ""
    money = f" ${usd:,.0f}".replace(",", " ") if usd else ""
    return f"{s.get('t', '?')}{money}{run}"


# ─────────────────────────────────────────────────────────────
# Письмо
# ─────────────────────────────────────────────────────────────
def build_letter(stars: list, market: dict) -> tuple[str, str]:
    g = split_groups(stars)
    p = market.get("permission") or {}
    ts = str(market.get("ts") or "")[:16].replace("T", " ")

    lines: list[str] = []
    add = lines.append

    add(f"ПРОГОН {ts}")
    add(SITE_URL)
    add("")

    # ── Окно рынка ──
    score, total = p.get("score"), p.get("total") or p.get("of")
    head = "ОКНО РЫНКА"
    if score is not None and total:
        head += f": {score} из {total}"
    add(head)
    notes = p.get("notes") or []
    if isinstance(notes, list) and notes:
        for n in notes:
            add(f"  · {_plain(n)}")
    elif p.get("note"):
        add(f"  · {_plain(p['note'])}")
    if market.get("weekend"):
        add("  · выходные — тонкий стакан")
    if market.get("frozen"):
        add("  · рынок замер")
    add("")

    # ── Счета двух подходов ──
    pf = market.get("portfolios") or {}
    for key, name in (("hold", "HOLD"), ("trade", "ТРЕЙДИНГ")):
        b = pf.get(key) or {}
        if not b:
            continue
        n = b.get('open', 0)
        add(f"{name}: {n} {_pos_word(n)} · "
            f"${b.get('value', 0):,.0f}".replace(",", " ") +
            f" · P/L {b.get('pnl', 0):+,.0f} ({b.get('pnlPct', 0):+.1f}%)"
            .replace(",", " "))
    add("")

    # ── Лидер с причиной действия ──
    leader = market.get("leader") or {}
    if leader.get("t"):
        star = next((s for s in stars if s.get("t") == leader["t"]), {})
        act = star.get("act") or {}
        why = f" — {act.get('act', '')}: {act['why']}" if act.get("why") else ""
        add(f"ЛИДЕР: {leader['t']} · score {leader.get('score', '—')} · "
            f"{leader.get('cap', '')}{why}")
        add("")

    # ── Заряжены на сжим ──
    charged = [s for s in stars
               if (s.get("squeeze") or {}).get("charged")]
    charged.sort(key=lambda s: -((s.get("squeeze") or {}).get("negRun") or 0))
    if charged:
        add(f"ЗАРЯЖЕНЫ НА СЖИМ ({len(charged)}):")
        for s in charged:
            note = (s.get("squeeze") or {}).get("note") or ""
            add(f"  · {s.get('t', '?')} — {note}")
        add("")

    # ── Три группы зала ──
    add(f"БРАТЬ ({len(g['take'])}):" if g["take"] else "БРАТЬ: нечего")
    for s in g["take"]:
        usd = (s.get("act") or {}).get("usd")
        money = f" ${usd:,.0f}".replace(",", " ") if usd else ""
        add(f"  · {s.get('t', '?')}{money} — {_why_take(s)}")
    add("")

    add(f"В РАБОТЕ ({len(g['work'])}):" if g["work"] else "В РАБОТЕ: пусто")
    for s in g["work"]:
        add(f"  · {_pos_line(s)}")
    add("")

    add(f"ЗАКРЫТЬ ({len(g['close'])}):" if g["close"] else "ЗАКРЫТЬ: нечего")
    for s in g["close"]:
        add(f"  · {_pos_line(s)} — {_why_close(s)}")
    add("")

    # ── Кандидаты фазы go ──
    go = [s for s in stars if (s.get("phase") or {}).get("k") == "go"]
    go.sort(key=lambda s: -(s.get("score") or 0))
    if go:
        names = ", ".join(s.get("t", "?") for s in go[:15])
        more = f" и ещё {len(go) - 15}" if len(go) > 15 else ""
        add(f"КАНДИДАТЫ ФАЗЫ GO ({len(go)}): {names}{more}")
        add("")

    subject = (f"Скринер · прогон {ts} · "
               f"брать {len(g['take'])} / в работе {len(g['work'])} / "
               f"закрыть {len(g['close'])}")
    return subject, "\n".join(lines)


def _pos_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "позиция"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "позиции"
    return "позиций"


_TAG = re.compile(r"<[^>]+>")


def _plain(s: object) -> str:
    """Ноты приходят с разметкой экрана — письму нужен голый текст."""
    return _TAG.sub("", str(s)).strip()


# ─────────────────────────────────────────────────────────────
# Конфиг и отправка
# ─────────────────────────────────────────────────────────────
def load_config() -> dict | None:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps(CONFIG_TEMPLATE, ensure_ascii=False, indent=2),
            encoding="utf-8")
        log(f"→ Почта: создан шаблон {CONFIG_PATH} — заполните "
            f"user/password/to, письмо пойдёт со следующего прогона")
        return None
    try:
        cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        log(f"✗ Почта: конфиг не прочитан: {e}")
        return None
    if not (cfg.get("user") and cfg.get("password") and cfg.get("to")):
        log("→ Почта: конфиг не заполнен (user/password/to) — пропуск")
        return None
    return cfg


def send_mail(subject: str, body: str, cfg: dict) -> bool:
    to = cfg["to"]
    if isinstance(to, str):
        to = [to]
    to = [t for t in to if t and "@" in t]
    if not to:
        log("→ Почта: в конфиге нет адресатов — пропуск")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = cfg.get("from_addr") or cfg["user"]
    msg["To"] = ", ".join(to)
    msg["Date"] = formatdate(localtime=True)

    host = cfg.get("smtp_host") or "smtp.gmail.com"
    port = int(cfg.get("smtp_port") or 465)
    if port == 465:
        with smtplib.SMTP_SSL(host, port,
                              context=ssl.create_default_context(),
                              timeout=30) as srv:
            srv.login(cfg["user"], cfg["password"])
            srv.sendmail(msg["From"], to, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=30) as srv:
            srv.starttls(context=ssl.create_default_context())
            srv.login(cfg["user"], cfg["password"])
            srv.sendmail(msg["From"], to, msg.as_string())
    return True


# ─────────────────────────────────────────────────────────────
# Точки входа
# ─────────────────────────────────────────────────────────────
def main(brief_path: Path | None = None, dry: bool = False) -> int:
    try:
        stars, market = load_report_data(brief_path)
    except (OSError, ValueError) as e:
        log(f"✗ Почта: данные отчёта не прочитаны: {e}")
        return 1
    subject, body = build_letter(stars, market)

    if dry:
        print(subject)
        print("─" * 60)
        print(body)
        return 0

    cfg = load_config()
    if not cfg:
        return 0                       # не заполнено — тихий пропуск
    try:
        if send_mail(subject, body, cfg):
            log(f"✓ Письмо отправлено: {subject}")
        return 0
    except Exception as e:             # smtplib кидает десяток типов
        log(f"✗ Почта: {type(e).__name__}: {e}")
        return 1


def send_after_run() -> None:
    """Вызов из run.py: любой сбой погашен внутри main()."""
    main()


if __name__ == "__main__":
    import sys
    main(dry="--dry" in sys.argv)
