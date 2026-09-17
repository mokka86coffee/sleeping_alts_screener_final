#!/usr/bin/env python3
"""БУМАЖНЫЙ БОТ «ПРОТИВ ТОЛПЫ ПО ФОНУ» (16.09; правила пересмотрены после 30 дней лаборатории — 134 монеты,
197 тыс. получасовок). Короткие сделки, до 3 часов. Что держится на 30 днях, а не на одной неделе:
  • шорты убивает растущий интерес и отрицательный фандинг (35–36% попаданий) — в вынос не шортим;
  • шорт «против толпы» — три бара «лонги открывают» при ФАНДИНГЕ ≥ 0 и интересе не ↑ → цель −1.5%:
    при фандинге «+» 62% / +0.81% (n=52), при 0 — 50% / +0.04%;
  • шорт по перекупленности z(20) > +2 при интересе ровно/↓ и фандинге ≥ 0 → z < 0: 50–57% / +0.1–0.2%;
  • лонг «прокол дна 8 баров −1.5%» при интересе ровно → цель +1.5%: 65% / +0.56% (n=99);
  • «за толпой» (3×лонги закрывают → лонг) на 30 днях −0.16% везде — убран;
  • ФАНДИНГ РЕШАЕТ ВТРОЕ (16.09, lab_scan --archive --days 14: 135 монет, 87 345 баров, интерес и фандинг
    по барам — то, чего в одной цене нет). «Рост сильный · фандинг −» — край −3.93% к контролю, обе
    половины одного знака, через 6 ч шорт +3.99%, через 12 ч +7.42%, ≥+2% в 55%. Те же по смыслу:
    «монета 6ч сильно ↑ · фандинг −» −2.74% (n=468), «12ч сильно ↑ · фандинг −» −2.74% (n=651).
    Смысл: монета летит, а платят ШОРТЫ — рост идёт не на покупках, а на выносе, и после выноса отдаётся.
    Поэтому шорт-правила берутся ТОЛЬКО при фандинге ≤ SPIKE_FUND_MAX; при плюсовом фандинге растёт
    на покупках — не трогаем. Рядом: «сильно ↑ · оборот бара ×1.5+» −3.16%, «сильно ↑ · тип бара
    short_close» −3.04% — рост на закрытии шортов, а не на новых деньгах;
  • СПАЙК ГАСЯТ (16.09, lab_scan на 30 днях, 134 монеты, 190 тыс. баров, самая устойчивая строка): монета +8% за
    два часа → следующие шесть часов отдаёт: край −2.0…−2.9% к контролю во ВСЕХ сочетаниях (будни n=1268, половины
    −1.99/−2.00; при биткоине ↑ и ↓, при доске ↑, в Токио, в пн/чт/пт), ≥2% в 50–55%; при сутках ≤ −8% (спайк
    внутри падения) край −3.19%, 55%, через 12 ч +6.4%. Шорт на баре спайка, цель PAPER_SPIKE_TARGET, стоп
    PAPER_SPIKE_STOP, срок PAPER_SPIKE_HOLD; размер ×2, если сутки ≤ −8%;
  • ПРОВАЛ ОТКУПАЮТ (16.09, lab_scan на полугоде часовиков, 116 монет, 495 тыс. баров): зеркало спайка — монета
    −8% за два часа → следующие шесть часов возврат +1.5…+2.0% (при «6ч сильно ↓» +1.83%, n=2558; при z<−2 +1.63%;
    в Токио +1.71%). Лонг на баре провала, цель PAPER_SPIKE_TARGET, стоп PAPER_SPIKE_STOP, срок PAPER_SPIKE_HOLD,
    размер ×2, если и за шесть часов ≤ −12%;
  • первый час Лондона (16.09, по 16 архивам: час после открытия 07:00 UTC — 64% вниз, медиана −0.42%, n=108;
    час ДО открытий сессий не падает — 36% вниз, шортить «за час до» не по данным) → шорт на баре открытия,
    крыть через LONDON_HOLD баров, стоп LONDON_STOP.
Данные: cq_v2/intraday/<монета>.jsonl (px, h, l, oi_type, oi_chg_pct, funding) по всем монетам с ≥25 барами.
Стоп PAPER_CROWD_STOP по размаху, удержание ≤ PAPER_CROWD_HOLD баров, комиссия PAPER_CROWD_FEE, размер 1.0.
Состояние output/paper_crowd.json, журнал output/paper_crowd.jsonl. Запуск из прогона; руками --only / --write.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
try:
    from core_config import PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_CROWD_FEE, PAPER_CROWD_TARGET
except ImportError:
    PAPER_CROWD_STOP, PAPER_CROWD_HOLD, PAPER_CROWD_FEE, PAPER_CROWD_TARGET = 0.02, 6, 0.001, 0.015
try:
    from core_config import PAPER_SPIKE_PCT, PAPER_SPIKE_TARGET, PAPER_SPIKE_STOP, PAPER_SPIKE_HOLD
except ImportError:
    PAPER_SPIKE_PCT, PAPER_SPIKE_TARGET, PAPER_SPIKE_STOP, PAPER_SPIKE_HOLD = 0.08, 0.025, 0.03, 12
try:
    from core_config import SPIKE_FUND_MAX, SPIKE_FUND_NEG, PAPER_SPIKE_HOLD_LONG
except ImportError:
    SPIKE_FUND_MAX, SPIKE_FUND_NEG, PAPER_SPIKE_HOLD_LONG = 0.0, -0.01, 24
try:
    from core_config import PAPER_CROWD_BOARD_N, PAPER_CROWD_MAX_PER_RUN
except ImportError:
    PAPER_CROWD_BOARD_N, PAPER_CROWD_MAX_PER_RUN = 5, 5

# СОБЫТИЕ ДОСКИ (16.09, владелец: «делай»). Первый прогон после нового старта открыл 11 шортов «перекуплен»
# на одной свече 19:00 UTC — рынок подрос одним баром, и z перешёл за +2 у всей доски разом: это одна ставка
# на откат, разложенная на одиннадцать монет, а не одиннадцать сделок. Как у paper_end: если кандидатов за
# прогон ≥ PAPER_CROWD_BOARD_N — берём PAPER_CROWD_MAX_PER_RUN лучших, остальным пишем last_sig (второй раз
# на той же свече не откроются), в журнал — строку события со взятыми и пропущенными (факты не отсекаются:
# исход пропущенных потом считается по архиву так же, как у взятых).
# Порядок: сначала сила правила, внутри правила — величина сигнала.
RULE_ORDER = ("спайк", "рост на выносе", "против толпы", "перекуплен", "прокол дна", "провал", "первый час Лондона")


def _rule_key(sig: dict) -> tuple:
    rule = str(sig.get("rule") or "")
    pri = next((i for i, r in enumerate(RULE_ORDER) if rule.startswith(r)), len(RULE_ORDER))
    z = float(sig.get("z") or 0)
    if rule.startswith("спайк"):
        mag = float(sig.get("r2") or 0)                 # ход за два часа
    elif rule.startswith("рост на выносе"):
        mag = float(sig.get("r6") or 0)                 # ход за шесть часов
    elif rule.startswith(("против толпы", "перекуплен")):
        mag = z                                         # насколько цена выше средней
    elif rule.startswith("прокол дна"):
        mag = -z                                        # насколько ниже средней
    elif rule.startswith("провал"):
        mag = -float(sig.get("r2") or 0)                # глубина провала за два часа
    elif rule.startswith("первый час Лондона"):
        mag = float(sig.get("px12") or 0)               # рост за 12 часов до открытия
    else:
        mag = 0.0
    return pri, -mag


def _brief(sym: str, sig: dict) -> dict:
    """кандидат для строки события доски: чтобы исход пропущенных можно было посчитать по архиву"""
    return {"sym": sym, "rule": str(sig.get("rule") or "").split(":")[0], "side": sig.get("side"),
            "t": sig.get("t"), "px": sig.get("px"), "z": sig.get("z"), "fund": sig.get("fund"),
            "r2": sig.get("r2"), "r6": sig.get("r6"), "px12": sig.get("px12")}

ARCH = BASE_DIR / "cq_v2" / "intraday"
STATE = BASE_DIR / "output" / "paper_crowd.json"
LOG = BASE_DIR / "output" / "paper_crowd.jsonl"


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def rows_of(sym: str) -> list[dict]:
    """получасовки архива ПО ПОРЯДКУ СВЕЧЕЙ (17.09): раньше брались по порядку строк файла — дозабор пропусков
    дописывает старые свечи в конец, и «последний бар» мог оказаться старым; повтор свечи — последняя запись"""
    p = ARCH / f"{sym.replace('USDT', '').lower()}.jsonl"
    by: dict = {}
    if not p.exists():
        return []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get("px") and r.get("h") and r.get("l") and r.get("candle"):
            try:
                r["t"] = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            except ValueError:
                continue
            by[r["t"]] = r
    now_ms = int(time.time() * 1000)
    return [by[t] for t in sorted(by) if t <= now_ms]       # свечи из будущего — не бары


def zs(C, i, N=20):
    w = C[i - N:i]
    m = sum(w) / N
    sd = (sum((x - m) ** 2 for x in w) / N) ** .5 or 1e-9
    return (C[i] - m) / sd


def signal(rows: list[dict]) -> dict | None:
    """Сигнал на последнем закрытом баре по трём правилам; None — тихо."""
    if len(rows) < 25:
        return None
    C = [r["px"] for r in rows]
    i = len(rows) - 1
    px12 = C[i - 1] / C[i - 24] - 1 if i >= 24 else 0.0
    bg = "↓" if px12 < -0.02 else "↑" if px12 > 0.02 else "ровно"
    fund = rows[i].get("funding")
    fund0 = fund is not None and -0.01 <= fund <= 0.02
    ot = [r.get("oi_type") for r in rows[i - 2:i + 1]]
    z = zs(C, i)
    base = {"t": rows[i]["t"], "px": C[i], "bg12": bg, "px12": round(px12 * 100, 2), "fund": fund, "z": round(z, 2)}
    # СПАЙК: +8% за два часа (4 бара) — первым, он сильнее остальных. ФАНДИНГ — ВОРОТА (16.09): при
    # плюсовом фандинге рост идёт на покупках, шорт туда не ставим вовсе; при отрицательном — рост на
    # выносе, там край втрое выше, и держим дольше (через 12 ч +7.4% против +4.0% через 6 ч).
    if i >= 48 and C[i] / C[i - 4] - 1 >= PAPER_SPIKE_PCT:
        if fund is None or fund > SPIKE_FUND_MAX:
            return None                          # платят лонги — рост на покупках, не шортим
        r24 = C[i] / C[i - 48] - 1
        size = 1.0
        if r24 <= -0.08:
            size = 2.0
        if fund <= SPIKE_FUND_NEG:
            size = max(size, 2.0)                # платят шорты — вынос, край −3.93% вместо −1.4
        d = datetime.fromtimestamp(rows[i]["t"] / 1000, timezone.utc)
        since = min(((d.hour - o) % 24) + d.minute / 60 for o in (21, 0, 7, 13))
        if since < 1:
            size = 0.5
        bg6 = rows[i].get("board6")            # медиана доски за 6 ч, если прогон её положил в строку
        if bg6 is not None and bg6 > 1:
            size = max(size, 1.5)
        _hold = PAPER_SPIKE_HOLD_LONG if fund <= SPIKE_FUND_NEG else PAPER_SPIKE_HOLD
        _tgt = PAPER_SPIKE_TARGET * (2.0 if fund <= SPIKE_FUND_NEG else 1.0)
        return dict(base, side=-1, rule=("спайк на выносе: +8% за 2 ч при фандинге −" if fund <= SPIKE_FUND_NEG
                                         else "спайк: +8% за 2 ч → гасят"),
                    target=_tgt, stop=PAPER_SPIKE_STOP, hold=_hold,
                    size=size, r2=round((C[i] / C[i - 4] - 1) * 100, 1), r24=round(r24 * 100, 1), since_open_h=round(since, 1))
    # РОСТ НА ВЫНОСЕ (16.09, lab_scan: «монета 6ч сильно ↑ · фандинг −» край −2.74%, n=468, 54% дают ≥2%;
    # при типе бара short_close −3.04%). Не спайк — более медленный ход, но та же машина: платят шорты.
    if i >= 48 and fund is not None and fund <= SPIKE_FUND_NEG:
        r6 = C[i] / C[i - 12] - 1
        if r6 >= 0.12:
            _st = rows[i].get("oi_type")
            return dict(base, side=-1, rule="рост на выносе: 6 ч +12% при фандинге −" + (" · шорты крылись" if _st == "short_close" else ""),
                        target=0.04, stop=PAPER_SPIKE_STOP, hold=24,
                        size=2.0 if _st == "short_close" else 1.5, r6=round(r6 * 100, 1))
    # ПРОВАЛ: −8% за два часа. Первый прогон полугодия (116 монет) — откупают (+1.7); второй (78 монет) — в Токио
    # продолжается вниз (−1.6). Не держится → только наблюдение, размер 0.5, в отбор не идёт.
    if i >= 48 and C[i] / C[i - 4] - 1 <= -PAPER_SPIKE_PCT:
        r6 = C[i] / C[i - 12] - 1
        return dict(base, side=1, rule="провал: −8% за 2 ч (наблюдение)", target=PAPER_SPIKE_TARGET, stop=PAPER_SPIKE_STOP, hold=PAPER_SPIKE_HOLD,
                    size=0.5, r2=round((C[i] / C[i - 4] - 1) * 100, 1), r6=round(r6 * 100, 1))
    oi24 = rows[i].get("oi_chg_pct")
    oi_flat_or_down = oi24 is not None and oi24 <= 5
    fund_nonneg = fund is not None and fund >= 0
    base.update(oi24=oi24)
    if ot == ["long_open"] * 3 and fund_nonneg and oi_flat_or_down:
        return dict(base, side=-1, rule="против толпы: 3×лонги открывают, фандинг ≥0, интерес не ↑", target=PAPER_CROWD_TARGET)
    if z > 2 and fund_nonneg and oi_flat_or_down:
        return dict(base, side=-1, rule="перекуплен: z>+2 при интересе не ↑ и фандинге ≥0", target=None)
    L = [r["l"] for r in rows]
    if oi24 is not None and -5 <= oi24 <= 5 and C[i] < min(L[i - 8:i]) * 0.985:
        return dict(base, side=1, rule="прокол дна 8 баров при ровном интересе", target=PAPER_CROWD_TARGET)
    d = datetime.fromtimestamp(rows[i]["t"] / 1000, timezone.utc)
    if d.hour == 7 and d.minute == 0:
        return dict(base, side=-1, rule="первый час Лондона", target=None, hold=2, stop=0.015)
    return None


def check_exit(pos: dict, rows: list[dict]) -> tuple[float, str] | None:
    """Выход по барам, закрытым после входа: стоп по размаху, цель по закрытию (или z<0 для z-правила), срок."""
    after = [r for r in rows if r["t"] > pos["t"]]
    if not after:
        return None
    e, side = pos["px"], pos["side"]
    stop = pos.get("stop") or PAPER_CROWD_STOP
    hold = pos.get("hold") or PAPER_CROWD_HOLD
    C = [r["px"] for r in rows]
    for k, r in enumerate(after, 1):
        stopped = (r["l"] / e - 1) <= -stop if side > 0 else (r["h"] / e - 1) >= stop
        if stopped:
            return -stop - PAPER_CROWD_FEE, f"стоп на баре {k}"
        res = side * (r["px"] / e - 1)
        if pos.get("target") is not None and res >= pos["target"]:
            return res - PAPER_CROWD_FEE, f"цель на баре {k}"
        if pos.get("target") is None:
            idx = rows.index(r)
            if idx >= 20 and side < 0 and zs(C, idx) < 0:
                return res - PAPER_CROWD_FEE, f"z<0 на баре {k}"
        if k >= hold:
            return res - PAPER_CROWD_FEE, f"срок {hold} баров"
    return None


BOOK_NAME = "paper_crowd"

# ЗАЩИТА ШОРТОВ (17.09, случай AVA: 18 сделок, 9 стопов подряд, −61.8% с весом): лидера и лестницу не шортим,
# после стопа — пауза; пропуски пишутся в журнал строкой skip. Логика — в paper_guard.py, пороги в core_config.
try:
    import paper_guard as _pg
except ImportError:
    _pg = None


def _opposite_open(sym: str, side: int) -> str | None:
    """ВСТРЕЧНЫЕ ПОЗИЦИИ (16.09: AKE — crowd взял лонг, end в ту же цену шорт ×2; сумма ноль, комиссия
    дважды). Смотрим состояния соседних книг: если там уже открыта противоположная сторона по этой
    монете — вход не делаем и пишем, из-за кого."""
    for _nm in ("paper_end", "paper_crowd", "paper_fast", "paper_bottom"):     # «дно» — с 17.09
        if _nm == BOOK_NAME:
            continue
        _d = _read(BASE_DIR / "output" / f"{_nm}.json") or {}
        _p = (_d.get("open") or {}).get(sym)
        if not _p:
            continue
        _s = _p.get("side")
        if _s is None:
            _s = -1 if (_nm == "paper_end" or str(_p.get("state")) == "short") else 1
        if int(_s) != int(side):
            return _nm
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    if a.only:
        syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")]
    else:
        syms = sorted(p.stem.upper() + "USDT" for p in ARCH.glob("*.jsonl"))
    state = _read(STATE) or {"open": {}}
    now = int(time.time())
    opened, closed = [], []
    cands = []
    for sym in syms:
        rows = rows_of(sym)
        if len(rows) < 25:
            continue
        pos = state["open"].get(sym)
        if pos:
            ex = check_exit(pos, rows)
            if ex:
                res, why = ex
                closed.append(dict(pos, sym=sym, kind="exit", result_pct=round(res * 100, 2), result_sized_pct=round(res * pos.get("size", 1.0) * 100, 2), why_exit=why, at=now))
                if _pg and why.startswith("стоп"):
                    _pg.note_stop(state, sym, int(pos.get("side") or -1), rows[-1]["t"])
                del state["open"][sym]
                print(f"paper_crowd: {sym} · выход · {why} · {res * 100:+.2f}% · {pos['rule']}")
                pos = None
        sig = signal(rows)
        if sig and not pos and _pg and sig["t"] > (state.get("last_sig", {}).get(sym) or 0):
            _why = (_pg.short_blocked(sym, rows) if int(sig.get("side") or -1) < 0 else None) \
                or _pg.cooldown(state, sym, int(sig.get("side") or -1), sig["t"])
            if _why:
                print(f"paper_crowd: {sym} · пропуск — {_why} · {str(sig.get('rule') or '').split(':')[0]}")
                opened.append(_pg.skip_row(sym, sig, _why, now, BOOK_NAME))
                state.setdefault("last_sig", {})[sym] = sig["t"]
                sig = None
        if sig and not pos:
            _opp = _opposite_open(sym, int(sig.get("side") or -1))
            if _opp:
                print(f"paper_crowd: {sym} · пропуск — встречная позиция в {_opp}")
                sig = None
        if sig and not pos and sig["t"] > (state.get("last_sig", {}).get(sym) or 0):
            cands.append((sym, sig))
    cands.sort(key=lambda x: _rule_key(x[1]))
    if len(cands) >= PAPER_CROWD_BOARD_N:
        skipped = cands[PAPER_CROWD_MAX_PER_RUN:]
        cands = cands[:PAPER_CROWD_MAX_PER_RUN]
        for sym, sig in skipped:
            state.setdefault("last_sig", {})[sym] = sig["t"]
        opened.append({"kind": "board", "at": now, "n": len(cands) + len(skipped),
                       "taken": [_brief(s_, g_) for s_, g_ in cands],
                       "skipped": [_brief(s_, g_) for s_, g_ in skipped]})
        _rules = {}
        for _, g_ in cands + skipped:
            _k = str(g_.get("rule") or "").split(":")[0]
            _rules[_k] = _rules.get(_k, 0) + 1
        print(f"paper_crowd: событие доски — кандидатов {len(cands) + len(skipped)} ("
              + ", ".join(f"{k} {v}" for k, v in _rules.items()) + f"), беру {len(cands)}: "
              + ", ".join(s_[:-4] for s_, _ in cands) + " · пропускаю: " + ", ".join(s_[:-4] for s_, _ in skipped))
    for sym, sig in cands:
        state["open"][sym] = dict(sig, opened_at=now)
        state.setdefault("last_sig", {})[sym] = sig["t"]
        opened.append(dict(sig, sym=sym, kind="entry", at=now))
        print(f"paper_crowd: {sym} · вход {'шорт' if sig['side'] < 0 else 'лонг'} {sig['px']:.6g} · {sig['rule']} · фон 12ч {sig['bg12']} · фандинг {sig['fund']}")
    if a.write:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            for r in opened + closed:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp = STATE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        tmp.replace(STATE)
    print(f"paper_crowd: открыто {sum(1 for r in opened if r.get('kind') == 'entry')}, закрыто {len(closed)}, в позиции {len(state['open'])}" + ("" if a.write else " (без записи)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
