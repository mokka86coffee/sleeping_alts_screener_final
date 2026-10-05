#!/usr/bin/env python3
"""ЖУРНАЛ ВСПЛЕСКОВ (05.10 владелец: «чтобы бот находил всплески, ты читал графики… и делал выводы, разбирая эти монеты через два, четыре, шесть,
восемь часов и так далее после всплеска и находя закономерности», «тогда бы мы имели через два месяца по каждой монете свой разбор», «можешь начинать»).

Торговли нет, правил бота не касается, с Binance ничего не запрашивает. Берёт то, что бот уже написал в output/fast_tier.log: каждую монету, которую он
отметил (взял / не взял и почему / ждёт вершину / пробуждение / вынос у сканера), и ведёт по ней одну запись в claude/research/surges/journal.jsonl:
  • момент и что решил бот (сторона или причина отказа, текстом бота);
  • фон на момент из уже записанных файлов: цена, интерес и фандинг (pulse.json — показания прогона), где цена и интерес относительно недели,
    доска и BTC (последняя строка _BG в queue_log), в «первых» ли монета, сессия;
  • что стало с ценой через 2, 4, 6, 8 и 24 часа: по показаниям прогона (шаг ~30 мин), крайние значения за отрезок — по часовым свечам BingX;
  • поле read — моё чтение графика (стадия, кто зажат, что сломает), его пишу я отдельным проходом, скрипт его не трогает.
Запуск: из fast_state.py каждые 3 минуты (update()). Сводка: .venv/bin/python surge_journal.py --report"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIR = BASE / "claude" / "research" / "surges"
JOURNAL = DIR / "journal.jsonl"
STATE = DIR / "state.json"
LOG = BASE / "output" / "fast_tier.log"
L = timezone(timedelta(hours=3))
HOURS = (2, 4, 6, 8, 24)
SAME_MIN = 60            # повтор той же монеты того же вида в течение часа — та же запись
BINGX_MAX = 12           # запросов к BingX за один проход (цена на момент и часовые свечи для исходов)

_LINE = re.compile(r"^(\d\d):(\d\d):(\d\d) (всплеск/вынос|пробуждение): (.*)$")
_SYM = r"([A-Z0-9一-鿿]{1,20})"


def _read(p: Path, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def _parse(body: str):
    """строка бота → список (монета, вид, что решил бот, текст) или []"""
    m = re.match(r"^пробуждений \d+: (.+?) · открыто", body)
    if m:
        return [(s.strip() + "USDT", "wake", "пробуждение", "") for s in m.group(1).split(",") if s.strip()]
    m = re.match(rf"^{_SYM} (лонг|шорт) вход ([0-9.eE+-]+)(.*)$", body)
    if m:
        return [(m.group(1) + "USDT", "surge", m.group(2), f"вход {m.group(3)}{m.group(4)}")]
    m = re.match(rf"^{_SYM} вынос (лонгов|шортов) (.*)$", body)
    if m:
        return [(m.group(1) + "USDT", "flush", "вынос " + m.group(2), m.group(3))]
    m = re.match(rf"^{_SYM} шорт — ждём вершину(.*)$", body)
    if m:
        return [(m.group(1) + "USDT", "surge", "ждёт вершину", "шорт — ждём вершину" + m.group(2))]
    m = re.match(rf"^{_SYM} ((?:лонг |шорт |всплеск |всплеск → шорт |шорт после вершины |шорт на отскоке )?(?:не взят|пропущен)[^:]*): (.*)$", body)
    if m:
        return [(m.group(1) + "USDT", "surge", "не взят", m.group(3))]
    m = re.match(rf"^{_SYM} (?:А2?|Б|В|Ж|Г)[^:]*: сторона перевёрнута(.*)$", body)
    if m:
        return [(m.group(1) + "USDT", "surge", "перевёрнут", body[len(m.group(1)) + 1:])]
    return []


def _new_lines(st: dict) -> list:
    """новые строки лога бота с прошлого прохода (по смещению в файле); время строки — сегодняшняя дата, с поправкой на полночь"""
    try:
        size = LOG.stat().st_size; ino = LOG.stat().st_ino
    except OSError:
        return []
    off = int(st.get("offset") or 0)
    if st.get("ino") != ino or off > size:
        off = max(0, size - 400_000)                       # первый проход или файл сменился — берём хвост
    with open(LOG, "rb") as f:
        f.seek(off); raw = f.read()
    st["offset"] = off + len(raw); st["ino"] = ino
    now = datetime.now(L); out = []; day = now.replace(hour=0, minute=0, second=0, microsecond=0); nxt = now
    for ln in reversed(raw.decode("utf-8", "ignore").splitlines()):          # в логе только время: дату восстанавливаем, идя от последней строки назад —
        m = _LINE.match(ln)                                                   # если время строки заметно позже следующей за ней, между ними была полночь
        if not m:
            continue
        t = day + timedelta(hours=int(m.group(1)), minutes=int(m.group(2)), seconds=int(m.group(3)))
        if t > nxt + timedelta(hours=2):
            day -= timedelta(days=1); t -= timedelta(days=1)
        nxt = t
        out.append((t.timestamp(), m.group(4), m.group(5)))
    out.reverse()
    return out


def _bg():
    """последняя строка фона доски из queue_log (читаем только хвост файла)"""
    p = BASE / "output" / "queue_log.jsonl"
    try:
        with open(p, "rb") as f:
            f.seek(max(0, p.stat().st_size - 600_000)); tail = f.read().decode("utf-8", "ignore").splitlines()
    except OSError:
        return {}
    for ln in reversed(tail):
        if '"sym": "_BG"' in ln:
            try:
                return json.loads(ln)
            except ValueError:
                continue
    return {}


def _ses(t: float) -> str:
    h = datetime.fromtimestamp(t, L).hour
    return "Сидней" if h < 3 else "Токио" if h < 10 else "Лондон" if h < 16 else "Нью-Йорк"


_BXN = {"n": 0}


def _bx(url: str):
    if _BXN["n"] >= BINGX_MAX:
        return None
    _BXN["n"] += 1
    try:
        return (json.load(urllib.request.urlopen(url, timeout=8)) or {}).get("data")
    except Exception:  # noqa: BLE001
        return None


def _bx_sym(sym: str) -> str:
    return {"RAYSOLUSDT": "RAY-USDT", "METUSDT": "METEORA-USDT", "MONUSDT": "MONAD-USDT", "NOMUSDT": "NOMINA-USDT"}.get(sym, sym[:-4] + "-USDT")


_CS: dict = {}; _LIQ: dict = {}


def _supply() -> dict:
    """монет в обращении по базовой монете (output/depth_mcap.json, обновляет прогон) — для капитализации"""
    if not _CS:
        _CS.update((_read(BASE / "output" / "depth_mcap.json", {}) or {}).get("cs") or {})
    return _CS


def _liq7(now: float) -> dict:
    """сколько вынесено ликвидациями по монете за 7 дней в нашем потоке (OKX + Bybit; Binance в нём нет): {монета: [лонгов $, шортов $]}.
    Законченные сутки кэшируются в claude/research/surges/liq_days.json, сегодняшний файл читается заново."""
    if _LIQ:
        return _LIQ
    cache = _read(DIR / "liq_days.json", {}); today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d"); ch = False
    for i in range(8):
        d = (datetime.fromtimestamp(now, timezone.utc) - timedelta(days=i)).strftime("%Y-%m-%d")
        if d in cache and d != today:
            day = cache[d]
        else:
            day = {}
            try:
                with open(BASE / "cq_v2" / "liq" / f"{d}.jsonl", encoding="utf-8") as f:
                    for ln in f:
                        try:
                            x = json.loads(ln)
                        except ValueError:
                            continue
                        a = day.setdefault(x.get("sym"), [0.0, 0.0]); a[0 if x.get("side") == "long" else 1] += float(x.get("usd") or 0)
            except OSError:
                pass
            if d != today:
                cache[d] = day; ch = True
        for s, (a, b) in day.items():
            q = _LIQ.setdefault(s, [0.0, 0.0]); q[0] += a; q[1] += b
    if ch:
        (DIR / "liq_days.json").write_text(json.dumps({k: cache[k] for k in sorted(cache)[-10:]}), encoding="utf-8")
    return _LIQ


def _depth(sym: str) -> dict:
    """последний снимок стакана монеты из cq_v2/depth (есть у монет очереди): сколько $ стоит в заявках до ±N %"""
    p = BASE / "cq_v2" / "depth" / f"{sym[:-4].lower()}.jsonl"
    try:
        with open(p, "rb") as f:
            f.seek(max(0, p.stat().st_size - 20_000)); ln = f.read().decode("utf-8", "ignore").strip().splitlines()[-1]
        x = json.loads(ln)
        return dict(depth_ask_k=round(float(x.get("ask_usd") or 0) / 1e3), depth_bid_k=round(float(x.get("bid_usd") or 0) / 1e3), depth_up_pct=x.get("cover_up_pct"),
                    depth_age_min=round((time.time() - int(x["t"]) / 1000) / 60))
    except Exception:  # noqa: BLE001
        return {}


def _ctx(sym: str, t: float, pulse: dict, bg: dict) -> dict:
    c = dict(ses=_ses(t), wd="пн вт ср чт пт сб вс".split()[datetime.fromtimestamp(t, L).weekday()])
    if bg:
        c.update(board24=bg.get("board_med_24h"), board_up=bg.get("board_up_pct"), btc24=bg.get("btc_24h"), in_first=sym in (bg.get("first") or []))
    pl = pulse.get(sym) if isinstance(pulse.get(sym), list) else None
    pl = [x for x in pl or [] if x["t"] <= t + 60]              # только показания ДО момента всплеска (важно для строк, дочитанных задним числом)
    if pl:
        last = pl[-1]; px = [x["price"] for x in pl if x.get("price")]; oi = [x["oi_usd"] for x in pl if x.get("oi_usd")]
        c.update(pulse_age_min=round((t - last["t"]) / 60), px=last.get("price"), ch24=last.get("ch_24h"), fund=last.get("funding"), rvol1h=last.get("rvol_1h"))
        if px:
            c.update(from_hi7=round((px[-1] / max(px) - 1) * 100, 1), from_lo7=round((px[-1] / min(px) - 1) * 100, 1))
        if oi:
            c.update(oi_musd=round(oi[-1] / 1e6, 2), oi_vs_min7=round(oi[-1] / min(oi), 2), oi_vs_max7=round((oi[-1] / max(oi) - 1) * 100, 1))
        # 05.10 владелец: «нужно смотреть капитализации, объёмы… можно вычислить монету, которой нужно много собирать» — капитализация и интерес к ней
        cs = _supply().get(sym[:-4]) or _supply().get(sym[:-4].replace("1000", ""))
        if cs and last.get("price"):
            cap = float(cs) * float(last["price"]) / (1000 if sym.startswith("1000") and sym[:-4] not in _supply() else 1)
            c["cap_musd"] = round(cap / 1e6, 1)
            if oi and cap > 0:
                c["oi_to_cap_pct"] = round(oi[-1] / cap * 100, 1)
    lq = _liq7(time.time()).get(sym)
    if lq:
        c.update(liq7_long_k=round(lq[0] / 1e3), liq7_short_k=round(lq[1] / 1e3))      # собрано ликвидациями за 7 дней (OKX + Bybit)
    if time.time() - t < 3600:
        c.update(_depth(sym))                                                          # стакан — только для свежей строки, задним числом его нет
    return c


def _px_at(sym: str, t: float, pulse: dict):
    """цена по показаниям прогона: первое показание не раньше t и не позже t + 45 мин"""
    pl = pulse.get(sym) if isinstance(pulse.get(sym), list) else None
    for x in pl or []:
        if t <= x["t"] <= t + 2700 and x.get("price"):
            return float(x["price"])
    return None


def _outcomes(r: dict, pulse: dict, now: float) -> bool:
    ch = False; p0 = r.get("px0")
    if not p0:
        return False
    out = r.setdefault("out", {})
    for h in HOURS:
        k = f"h{h}"
        if k in out or now < r["t"] + h * 3600 + 1800:
            continue
        px = _px_at(r["sym"], r["t"] + h * 3600, pulse); src = "прогон"
        kl = None
        if px is None or h in (8, 24):                       # крайние значения за отрезок — по часовым свечам BingX
            kl = _bx(f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={_bx_sym(r['sym'])}&interval=1h&limit=30"
                     f"&startTime={int(r['t'] * 1000)}&endTime={int((r['t'] + h * 3600) * 1000)}")
        if kl:
            ks = sorted(kl, key=lambda x: int(x["time"]))
            if px is None:
                px = float(ks[-1]["close"]); src = "BingX"
            out[f"up{h}"] = round((max(float(x["high"]) for x in ks) / p0 - 1) * 100, 2)
            out[f"dn{h}"] = round((min(float(x["low"]) for x in ks) / p0 - 1) * 100, 2)
        if px is None:
            if now > r["t"] + (h + 6) * 3600:
                out[k] = None; ch = True                     # цены взять неоткуда — не ждём вечно
            continue
        out[k] = round((px / p0 - 1) * 100, 2); out[k + "_src"] = src; ch = True
    return ch


def update() -> str:
    DIR.mkdir(parents=True, exist_ok=True)
    st = _read(STATE, {}); now = time.time(); _BXN["n"] = 0; _CS.clear(); _LIQ.clear()
    rows = []
    if JOURNAL.exists():
        for ln in JOURNAL.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(ln))
            except ValueError:
                pass
    lines = _new_lines(st)
    pulse = _read(BASE / "pulse.json", {}) if (lines or any(len(r.get("out", {})) < len(HOURS) * 1 for r in rows[-400:])) else {}
    bg = _bg() if lines else {}
    last = {}
    for r in rows[-600:]:
        last[(r["sym"], r["kind"])] = r
    added = 0
    for t, book, body in lines:
        for sym, kind, bot, text in _parse(body):
            r = last.get((sym, kind))
            if r and t - r["t"] < SAME_MIN * 60:
                if bot in ("лонг", "шорт") and r["bot"] not in ("лонг", "шорт"):
                    r["bot"] = bot; r["bot_t"] = t
                    m = re.match(r"вход ([0-9.eE+-]+)", text)
                    if m:
                        r["px_bot"] = float(m.group(1))
                if text and text[:60] not in " | ".join(r["why"])[:2000]:
                    r["why"].append(text[:220])
                    r["why"] = r["why"][-6:]
                r["n"] = r.get("n", 1) + 1
                continue
            r = dict(id=f"{sym}|{kind}|{int(t)}", sym=sym, kind=kind, t=t, at=datetime.fromtimestamp(t, L).strftime("%d.%m %H:%M"), book=book, bot=bot,
                     why=[text[:220]] if text else [], n=1, ctx=_ctx(sym, t, pulse, bg), out={}, read=None)
            m = re.match(r"вход ([0-9.eE+-]+)", text)
            if m:
                r["px0"] = float(m.group(1)); r["px0_src"] = "бот"; r["px_bot"] = r["px0"]
            else:
                _age = r["ctx"].get("pulse_age_min")
                if r["ctx"].get("px") and _age is not None and 0 <= _age <= 12:
                    r["px0"] = r["ctx"]["px"]; r["px0_src"] = "прогон"
                else:
                    d = _bx(f"https://open-api.bingx.com/openApi/swap/v2/quote/price?symbol={_bx_sym(sym)}") if now - t < 600 else None   # цена «сейчас» годится только для свежей строки
                    if d and d.get("price"):
                        r["px0"] = float(d["price"]); r["px0_src"] = "BingX"
                    elif r["ctx"].get("px") and _age is not None and 0 <= _age <= 45:
                        r["px0"] = r["ctx"]["px"]; r["px0_src"] = f"прогон ({_age} мин до)"
            rows.append(r); last[(sym, kind)] = r; added += 1
    filled = sum(1 for r in rows[-1500:] if len([k for k in r.get("out", {}) if k in {f"h{h}" for h in HOURS}]) < len(HOURS) and _outcomes(r, pulse, now))
    if added or filled or lines:
        tmp = JOURNAL.with_suffix(".tmp")
        tmp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + ("\n" if rows else ""), encoding="utf-8"); tmp.replace(JOURNAL)
        STATE.write_text(json.dumps(st), encoding="utf-8")
    return f"журнал всплесков: записей {len(rows)}, новых {added}, исходов дописано {filled}, запросов BingX {_BXN['n']}"


def report() -> None:
    rows = [json.loads(x) for x in JOURNAL.read_text(encoding="utf-8").splitlines()] if JOURNAL.exists() else []
    print(f"записей {len(rows)}" + (f" · с {rows[0]['at']} по {rows[-1]['at']}" if rows else ""))
    import collections
    by = collections.Counter((r["kind"], r["bot"]) for r in rows)
    for (k, b), n in by.most_common():
        g = [r for r in rows if r["kind"] == k and r["bot"] == b]
        s = f"  {k:6} · {b:14} {n:4}"
        for h in HOURS:
            v = [r["out"].get(f"h{h}") for r in g if r.get("out", {}).get(f"h{h}") is not None]
            if v:
                s += f" · через {h} ч: {sum(v) / len(v):+.2f}% (n={len(v)}, вверх {sum(1 for x in v if x > 0)})"
        print(s)
    print("с моим чтением графика:", sum(1 for r in rows if r.get("read")))


if __name__ == "__main__":
    if "--report" in sys.argv:
        report()
    else:
        print(update())
