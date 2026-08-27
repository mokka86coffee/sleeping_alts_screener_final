"""Озвучка сводки: текст под голос и звуковой файл рядом с отчётом.

ЗАЧЕМ. Сводку смотрят утром, часто занятыми руками. Прочитанная вслух,
она не требует экрана вовсе — а числа в ней и так уже пишутся словами
(правило проекта: «минус десять и семь десятых процента», а не
«−10.7%»), потому что текст изначально готовился под чтение.

ЧТО ДЕЛАЕТ. Берёт те же данные, что и экран сводки, — stars и market, —
собирает из них связный текст и отдаёт системному синтезу macOS
(команда `say`). Результат кладётся рядом с отчётом, экран его
подхватывает и показывает кнопку звука.

ЧЕГО НЕ ДЕЛАЕТ. Ничего не решает и ни на что не влияет: это чтение
готовых полей вслух. Ни один порог, вес или правило отбора здесь не
участвует.

ГРАНИЦА ПЕРЕНОСИМОСТИ. `say` есть только на macOS. На любой другой
системе модуль молча ничего не делает и возвращает False — прогон от
этого не страдает, а экран просто не покажет кнопку. Это осознанный
размен: локальный синтез бесплатен, работает без сети и без ключей,
но привязан к машине разработчика.

ГОЛОС. Milena (Enhanced), темп 150 слов в минуту, высота 55,
модуляция 80 — подобрано на слух 27.08. Умолчания `say` (200 слов в
минуту, ровный тон) для сводки слишком торопливы и плоски.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

from core_http import log

# ── голос и подача ──
VOICE = "Milena (Enhanced)"
RATE = 150          # слов в минуту
PITCH_BASE = 55     # [[pbas]] — средняя нота
PITCH_MOD = 80      # [[pmod]] — размах интонации
SAY_TIMEOUT_SEC = 120

MONTHS = {
    1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
    7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября",
    12: "декабря",
}
DAYS_RU = {
    1: "первое", 2: "второе", 3: "третье", 4: "четвёртое", 5: "пятое",
    6: "шестое", 7: "седьмое", 8: "восьмое", 9: "девятое", 10: "десятое",
    11: "одиннадцатое", 12: "двенадцатое", 13: "тринадцатое",
    14: "четырнадцатое", 15: "пятнадцатое", 16: "шестнадцатое",
    17: "семнадцатое", 18: "восемнадцатое", 19: "девятнадцатое",
    20: "двадцатое", 21: "двадцать первое", 22: "двадцать второе",
    23: "двадцать третье", 24: "двадцать четвёртое", 25: "двадцать пятое",
    26: "двадцать шестое", 27: "двадцать седьмое", 28: "двадцать восьмое",
    29: "двадцать девятое", 30: "тридцатое", 31: "тридцать первое",
}
ONES = ["ноль", "один", "два", "три", "четыре", "пять", "шесть", "семь",
        "восемь", "девять", "десять", "одиннадцать", "двенадцать",
        "тринадцать", "четырнадцать", "пятнадцать", "шестнадцать",
        "семнадцать", "восемнадцать", "девятнадцать"]
TENS = ["", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят",
        "семьдесят", "восемьдесят", "девяносто"]
HUNDREDS = ["", "сто", "двести", "триста", "четыреста", "пятьсот",
            "шестьсот", "семьсот", "восемьсот", "девятьсот"]
TENTHS = ["", "одна десятая", "две десятых", "три десятых", "четыре десятых",
          "пять десятых", "шесть десятых", "семь десятых", "восемь десятых",
          "девять десятых"]


def _int_ru(n: int) -> str:
    """Целое словами до 999 999. Больше — читаем как есть: таких чисел
    в сводке нет, а сочинять правила для миллионов ради «на всякий
    случай» значит писать код, который никто не проверит."""
    n = int(n)
    if n < 0:
        return "минус " + _int_ru(-n)
    if n >= 1_000_000:
        return str(n)
    out = []
    if n >= 1000:
        th = n // 1000
        n %= 1000
        if th == 1:
            out.append("одна тысяча")
        elif th == 2:
            out.append("две тысячи")
        elif th < 5:
            out.append(_int_ru(th) + " тысячи")
        else:
            out.append(_int_ru(th) + " тысяч")
    if n >= 100:
        out.append(HUNDREDS[n // 100])
        n %= 100
    if n >= 20:
        out.append(TENS[n // 10])
        n %= 10
    if n or not out:
        out.append(ONES[n])
    return " ".join(x for x in out if x)


def _plural(n: int, one: str, few: str, many: str) -> str:
    """Форма слова при числе. Без неё голос говорит «тридцать два
    минут» и «два из семь составляющих» — на слух это резче, чем
    кажется в тексте."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _rod(n: int) -> str:
    """Родительный для «из семи составляющих»: числительное после
    предлога «из» стоит не в именительном."""
    FORMS = {1: "одной", 2: "двух", 3: "трёх", 4: "четырёх", 5: "пяти",
             6: "шести", 7: "семи", 8: "восьми", 9: "девяти", 10: "десяти"}
    return FORMS.get(int(n), _int_ru(n))


def _pct(v, unit: str = "процента", sign: bool = True) -> str:
    """Число словами с одним знаком после запятой.

    Знак проговаривается: «минус одна и одна десятая процента». Без
    него на слух минус теряется полностью — а это ровно та величина,
    ради которой сводку и слушают.
    """
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "неизвестно"
    pre = ""
    if sign:
        pre = "минус " if v < 0 else "плюс "
    a = abs(v)
    whole = int(a)
    tenth = int(round((a - whole) * 10))
    if tenth == 10:
        whole += 1
        tenth = 0
    tail = " и " + TENTHS[tenth] if tenth else ""
    # Форма единицы согласуется с последним произнесённым числом:
    # при дробной части — с ней («три десятых процента»), иначе — с
    # целым («семь процентов», «двадцать один процент»).
    if unit == "процента":
        unit = ("процента" if tenth
                else _plural(whole, "процент", "процента", "процентов"))
    return f"{pre}{_int_ru(whole)}{tail} {unit}"


def _money_ru(cap: str) -> str:
    """«$23M» → «двадцать три миллиона долларов». Форма слова
    согласуется с числом: миллион, миллиона, миллионов."""
    m = re.match(r"\$?\s*([\d.]+)\s*([MBK])?", cap.strip())
    if not m:
        return _clean(cap)
    try:
        v = float(m.group(1))
    except ValueError:
        return _clean(cap)
    suf = (m.group(2) or "").upper()
    whole = int(v)
    if suf == "B":
        word = _plural(whole, "миллиард", "миллиарда", "миллиардов")
    elif suf == "K":
        whole = int(v * 1000)
        word = ""
    else:
        word = _plural(whole, "миллион", "миллиона", "миллионов")
    return f"{_int_ru(whole)} {word} долларов".replace("  ", " ")


def _clean(t: str) -> str:
    """Проза без математических знаков: их синтез читает вслух буквально
    либо проглатывает. Тикеры и латиница остаются как есть — их голос
    произносит по буквам, и это правильно."""
    t = re.sub(r"<[^>]+>", "", str(t or ""))
    t = (t.replace("%", " процентов").replace("×", " в ")
           .replace("$", "").replace("·", ",").replace("—", ",")
           .replace("–", ",").replace("→", " к ").replace("+", "плюс ")
           .replace("−", "минус "))
    # Числа внутри готовых заметок разворачиваем здесь же: они приходят
    # из датчиков, и оставить «79 процентов» значит сорвать голос на
    # цифру посреди прочитанного словами текста.
    t = re.sub(r"(\d+)[.,](\d+)",
               lambda m: _pct(float(m.group(0).replace(",", ".")), "", sign=False).strip(), t)
    t = re.sub(r"\b\d+\b", lambda m: _int_ru(int(m.group(0))), t)
    t = re.sub(r"\bATR\b", "атээр", t, flags=re.I)
    t = re.sub(r"\s+([,.:;])", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def build_text(stars: list[dict], market: dict) -> str:
    """Текст сводки под чтение вслух.

    Порядок тот же, что на экране: окно рынка, фон, портфели, лидер,
    объём, действия, события. Слушающий и смотрящий должны получать
    одно и то же в одной последовательности — иначе звук и картинка
    расходятся, и доверия к обоим меньше.
    """
    M = market or {}
    P = M.get("permission") or {}
    pp = P.get("parts") or {}
    md = M.get("medians") or {}
    pf = M.get("portfolios") or {}
    hold = pf.get("hold") or {}
    trade = pf.get("trade") or {}
    lead = M.get("leader") or {}
    peak = M.get("peakVol") or {}
    top = M.get("topVol") or []
    res = pp.get("reservoir") or {}
    cal = (pp.get("calendar") or {}).get("items") or []

    by_t = {s.get("t"): s for s in (stars or [])}
    lead_star = by_t.get(lead.get("t")) or {}

    take = [s for s in (stars or [])
            if (s.get("act") or {}).get("group") == "take"
            and (s.get("act") or {}).get("act") == "брать"]
    book = [s for s in (stars or []) if (s.get("book") or {}).get("usd")]

    parts: list[str] = []

    # ── когда ──
    ts = str(M.get("ts") or "")
    if len(ts) >= 16:
        day = int(ts[8:10]); mon = int(ts[5:7])
        hh = int(ts[11:13]); mm = int(ts[14:16])
        parts.append(
            f"Сводка прогона. {DAYS_RU.get(day, day).capitalize()} "
            f"{MONTHS.get(mon, '')}, {_int_ru(hh)} "
            f"{_plural(hh, 'час', 'часа', 'часов')} {_int_ru(mm)} "
            f"{_plural(mm, 'минута', 'минуты', 'минут')}."
        )

    # ── окно рынка ──
    warn = int(P.get("warnCount") or 0)
    known = int(P.get("knownCount") or 7)
    size = "урезанный" if warn >= 4 else "полный"
    parts.append(f"Окно рынка: {_int_ru(warn)} из {_rod(known)} составляющих "
                 f"{_plural(warn, 'предупреждает', 'предупреждают', 'предупреждают')}. "
                 f"Размер по правилу {size}.")

    for key in ("funding", "oi", "cascade"):
        note = (pp.get(key) or {}).get("note")
        if note:
            parts.append(_clean(note) + ".")
            break

    # ── фон ──
    bg = (f"Фон: медиана выборки за неделю {_pct(md.get('d7'))}, "
          f"за сутки {_pct(md.get('d1'))}, за месяц {_pct(md.get('d30'))}.")
    if M.get("dom"):
        bg += f" Доминация биткоина {_pct(M['dom'], sign=False)}."
    parts.append(bg)

    if res.get("share"):
        age = res.get("ageDays")
        s = f"Стейблкоины — {_pct(res['share'], sign=False)} капитализации"
        if age is not None:
            s += f", данным {_int_ru(int(age))} дней"
        parts.append(s + ".")

    # ── деньги ──
    if hold:
        parts.append(
            f"Портфели. Журнал: {_int_ru(int(hold.get('open') or 0))} позиций, "
            f"вложено {_int_ru(round(float(hold.get('invested') or 0) / 1000))} тысяч долларов, "
            f"стоит {_int_ru(round(float(hold.get('value') or 0) / 1000))} тысяч, "
            f"ход {_pct(hold.get('pnlPct'))}. "
            f"Книга по правилам: {_int_ru(int(trade.get('open') or 0))} позиций, "
            f"{_pct(trade.get('pnlPct'))}."
        )

    # ── лидер ──
    if lead.get("t"):
        cap = _money_ru(str(lead.get("cap") or ""))
        s = (f"Лидер прогона — {lead['t']}. Скор {_int_ru(int(lead.get('score') or 0))}, "
             f"фигура {lead.get('case') or 'не названа'}")
        if cap.strip():
            s += f", капитализация {cap.strip()}"
        if lead_star.get("chg") is not None:
            s += f", ход {_pct(lead_star['chg'])}"
        parts.append(s + ".")
        # Довод берём КОРОТКИЙ: полный на слух не держится — там
        # придаточные и двоеточия, к концу фразы начало забыто.
        why = (lead_star.get("act") or {}).get("why")
        if why:
            # В доводе попадаются свои числа («опора в 0.4 ATR») —
            # разворачиваем и их: одно непрочитанное число ломает
            # впечатление от всей фразы.
            w = re.sub(r"(\d+)[.,](\d)",
                       lambda m: _pct(float(m.group(0).replace(",", ".")),
                                      "", sign=False).strip(),
                       _clean(why))
            w = re.sub(r"\bATR\b", "атээр", w, flags=re.I)
            parts.append(w.capitalize() + ".")

    # ── объём ──
    # Число НЕ проговариваем, когда оно выше десяти: по собственному
    # замечанию проекта (analytics_indicators, WINDOW_RATIO_CAP) выше
    # этой границы величина описывает возраст монеты, а не рынок.
    # Голосом «в тысячу раз выше нормы» звучит как факт рынка, хотя
    # мерить там нечем.
    if peak.get("sym"):
        x = float(peak.get("x") or 0)
        if x > 10:
            parts.append(f"Топ объёма: {peak['sym']}, объём аномально высок.")
        else:
            parts.append(f"Топ объёма: {peak['sym']}, объём в {_pct(x, 'раза', sign=False)} выше нормы.")

    # ── действия ──
    if take:
        parts.append("Брать: " + ", ".join(s["t"] for s in take) + ".")
    else:
        parts.append("Брать нечего: ни одна монета не прошла порог входа.")
    parts.append(f"В работе {_int_ru(len(book))} позиций.")

    # ── события ──
    if cal:
        e = cal[0]
        d = e.get("days")
        when = ("сегодня" if (e.get("running") or d == 0)
                else "завтра" if d == 1
                else f"через {_int_ru(int(d or 0))} дней")
        parts.append(f"Впереди {_int_ru(len(cal))} событий. "
                     f"Ближайшее, {when}: {_clean(e.get('title'))}.")

    parts.append("Дальше зал.")
    return "\n\n".join(parts)


def speak(text: str, out_path: Path) -> bool:
    """Пишет звук через системный синтез macOS. Не роняет прогон.

    Возвращает True, только если файл действительно появился: код
    возврата ноль при пустом файле — та же ошибка, только тихая.
    """
    if sys.platform != "darwin" or not shutil.which("say"):
        return False

    aiff = out_path.with_suffix(".aiff")
    head = f"[[pbas {PITCH_BASE}]] [[pmod {PITCH_MOD}]] "
    try:
        subprocess.run(
            ["say", "-v", VOICE, "-r", str(RATE), "-o", str(aiff), head + text],
            check=True, capture_output=True, timeout=SAY_TIMEOUT_SEC,
        )
    except FileNotFoundError:
        return False
    except subprocess.TimeoutExpired:
        log("✗ озвучка: say не уложился в отведённое время")
        return False
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode(errors="replace").strip()
        log(f"✗ озвучка: say вернул ошибку — {err[:200]}")
        return False

    if not aiff.exists() or aiff.stat().st_size < 1024:
        log("✗ озвучка: файл пуст")
        return False

    # Формат для браузера. afconvert есть на любой macOS; если он вдруг
    # не сработал, оставляем aiff — Safari его играет, остальные нет,
    # но лучше так, чем ничего.
    try:
        subprocess.run(
            ["afconvert", str(aiff), str(out_path),
             "-f", "m4af", "-d", "aac", "-q", "127", "-s", "3"],
            check=True, capture_output=True, timeout=SAY_TIMEOUT_SEC,
        )
        aiff.unlink(missing_ok=True)
    except Exception:
        return aiff.exists()

    return out_path.exists() and out_path.stat().st_size > 1024


def render_voice(stars: list[dict], market: dict, out_dir: Path) -> bool:
    """Собрать текст и записать звук рядом с отчётом.

    Рядом со звуком кладётся и сам текст: по нему видно, что именно
    прочитано, и его можно вставить в любой другой синтез, если
    когда-нибудь захочется голос получше.
    """
    try:
        text = build_text(stars, market)
    except Exception as e:
        log(f"✗ озвучка: текст не собран — {type(e).__name__}: {e}")
        return False

    try:
        (out_dir / "brief_voice.txt").write_text(text + "\n", encoding="utf-8")
    except OSError as e:
        log(f"✗ озвучка: текст не записан — {e}")

    ok = speak(text, out_dir / "brief_voice.m4a")
    if ok:
        log("→ озвучка: brief_voice.m4a записан")
    return ok
