#!/usr/bin/env python3
"""ЛАБОРАТОРИЯ ВНУТРИДНЕВНЫХ ПРАВИЛ (16.09; владелец: «раз в полчаса-час открывать и закрывать, до 2–3 часов на
сделку — искать закономерности»). По архивам 11–16.09 (16 монет, одна неделя вниз) вышло: шорт против толпы при
нулевом фандинге 68% / +0.61%, шорт по z>+2 +0.36%, лонги в минус — но это ОДИН фон. Здесь то же самое на 30 днях
по всей доске, чтобы увидеть, как правила переворачиваются с фоном.

Данные:
  • цена — получасовки биржи через core_binance.get_klines(sym, "30m", limit=LAB_BARS) по монетам сводки
    (near_move.json), плюс BTCUSDT как фон;
  • интерес и тип бара — из cq_v2/intraday/<монета>.jsonl там, где есть (правила «против толпы» считаются
    только на этих барах — по ним меньше дней, это честно отмечается).
Правила (лонг и шорт, удержание ≤ LAB_HOLD баров, стоп LAB_STOP, комиссия LAB_FEE за оборот):
  z-score(20) ±1.5/±2 → возврат к нулю; RSI14 30/70 → 50; прокол N-барного дна/вершины → цель ±1.5%;
  против толпы: 3 бара «лонги открывают» → шорт −1.5%, 3 бара «лонги закрывают» → лонг +1.5%.
Фон на бар: ход монеты за 12 ч (24 бара), ход биткоина за 12 ч, интерес за сутки (где есть), фандинг (где есть).
Печатает: всё вместе; лучшие и худшие срезы «правило × фон»; равновзвешенный портфель по дням для лучших.
Ничего не пишет. Запуск: `python3 lab_intraday.py`, `--only ARK,LAB`, `--days 30`.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

LAB_BARS = 1500
LAB_HOLD = 6
LAB_STOP = 0.02
LAB_FEE = 0.001
MIN_N = 12


def _read(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def coins() -> list[str]:
    nm = _read(BASE_DIR / "output" / "near_move.json") or {}
    out = [str(s).upper() for s in (nm.get("coins") or {}).keys()]
    for name in ("leaders.json", "pump_leaders.json"):
        for k in (_read(BASE_DIR / "output" / name) or {}).keys():
            if not str(k).startswith("_"):
                out.append(str(k).upper())
    return sorted(set(s if s.endswith("USDT") else s + "USDT" for s in out))


def klines(sym: str, limit: int):
    import core_binance as cb
    from core_binance import K_HIGH, K_LOW, K_OPEN_TIME, get_klines
    KC = getattr(cb, "K_CLOSE", 4)
    ks = get_klines(sym, "30m", limit=limit) or []
    return sorted((int(k[K_OPEN_TIME]), float(k[K_HIGH]), float(k[K_LOW]), float(k[KC])) for k in ks)


def archive(sym: str) -> dict:
    """t → (oi_type, oi_chg_pct, funding) из внутридневного архива."""
    p = BASE_DIR / "cq_v2" / "intraday" / f"{sym.replace('USDT', '').lower()}.jsonl"
    out = {}
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
            t = int(datetime.strptime(r["candle"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)
            out[t] = (r.get("oi_type"), r.get("oi_chg_pct"), r.get("funding"))
        except (ValueError, KeyError):
            continue
    return out


def zs(C, i, N=20):
    w = C[i - N:i]
    m = sum(w) / N
    sd = (sum((x - m) ** 2 for x in w) / N) ** .5 or 1e-9
    return (C[i] - m) / sd


def rsi(c, N=14):
    out = [None] * len(c)
    g = l = 0.0
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        up, dn = max(ch, 0), max(-ch, 0)
        if i <= N:
            g += up / N
            l += dn / N
        else:
            g = (g * (N - 1) + up) / N
            l = (l * (N - 1) + dn) / N
        if i >= N:
            out[i] = 100 - 100 / (1 + (g / l if l else 1e9))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--days", type=int, default=30)
    a = ap.parse_args()
    syms = [x.strip().upper() + ("" if x.strip().upper().endswith("USDT") else "USDT") for x in a.only.split(",")] if a.only else coins()
    bars = min(LAB_BARS, a.days * 48 + 30)
    btc = klines("BTCUSDT", bars)
    btc_c = {t: c for t, _, _, c in btc}
    btc_t = [t for t, *_ in btc]

    def btc12(t):
        # ход биткоина за 12 ч до бара t
        import bisect
        i = bisect.bisect_left(btc_t, t)
        if i < 24 or i >= len(btc_t):
            return None
        return btc_c[btc_t[i - 1]] / btc_c[btc_t[i - 24]] - 1

    RULES = []

    def add(name, side, entry, exit_):
        RULES.append((name, side, entry, exit_))
    add("лонг z<−1.5→z>0", 1, lambda i, C, H, L, X: zs(C, i) < -1.5, lambda j, C, H, L, e, X: zs(C, j) > 0)
    add("лонг z<−2→z>0", 1, lambda i, C, H, L, X: zs(C, i) < -2, lambda j, C, H, L, e, X: zs(C, j) > 0)
    add("шорт z>+1.5→z<0", -1, lambda i, C, H, L, X: zs(C, i) > 1.5, lambda j, C, H, L, e, X: zs(C, j) < 0)
    add("шорт z>+2→z<0", -1, lambda i, C, H, L, X: zs(C, i) > 2, lambda j, C, H, L, e, X: zs(C, j) < 0)
    add("лонг RSI<30→50", 1, lambda i, C, H, L, X: X["rsi"][i] is not None and X["rsi"][i] < 30, lambda j, C, H, L, e, X: X["rsi"][j] is not None and X["rsi"][j] > 50)
    add("шорт RSI>70→50", -1, lambda i, C, H, L, X: X["rsi"][i] is not None and X["rsi"][i] > 70, lambda j, C, H, L, e, X: X["rsi"][j] is not None and X["rsi"][j] < 50)
    add("лонг прокол дна 8 баров −1.5%→+1.5%", 1, lambda i, C, H, L, X: C[i] < min(L[i - 8:i]) * .985, lambda j, C, H, L, e, X: C[j] / e - 1 >= .015)
    add("шорт прокол верха 8 баров +1.5%→−1.5%", -1, lambda i, C, H, L, X: C[i] > max(H[i - 8:i]) * 1.015, lambda j, C, H, L, e, X: C[j] / e - 1 <= -.015)
    add("шорт против толпы: 3×лонги открывают→−1.5%", -1, lambda i, C, H, L, X: all(X["ot"].get(X["T"][k]) == "long_open" for k in range(i - 2, i + 1)), lambda j, C, H, L, e, X: C[j] / e - 1 <= -.015)
    add("лонг за толпой: 3×лонги закрывают→+1.5%", 1, lambda i, C, H, L, X: all(X["ot"].get(X["T"][k]) == "long_close" for k in range(i - 2, i + 1)), lambda j, C, H, L, e, X: C[j] / e - 1 >= .015)

    pool = defaultdict(list)
    n_bars = 0
    n_arch = 0
    for sym in syms:
        try:
            ks = klines(sym, bars)
        except Exception as ex:  # noqa: BLE001
            print(f"{sym}: клайны не получены — {type(ex).__name__}")
            continue
        if len(ks) < 100:
            continue
        T = [t for t, *_ in ks]
        H = [h for _, h, _, _ in ks]
        L = [l for _, _, l, _ in ks]
        C = [c for *_, c in ks]
        arc = archive(sym)
        ot = {t: v[0] for t, v in arc.items()}
        X = {"rsi": rsi(C), "T": T, "ot": ot}
        n_bars += len(C)
        n_arch += sum(1 for t in T if t in arc)
        for name, side, entry, exit_ in RULES:
            i = 25
            while i < len(C) - 1:
                try:
                    hit = entry(i, C, H, L, X)
                except Exception:  # noqa: BLE001
                    hit = False
                if hit:
                    e = C[i]
                    j = i + 1
                    out = None
                    while j < len(C) and j <= i + LAB_HOLD:
                        stopped = (L[j] / e - 1) <= -LAB_STOP if side > 0 else (H[j] / e - 1) >= LAB_STOP
                        if stopped:
                            out = -LAB_STOP
                            break
                        if exit_(j, C, H, L, e, X):
                            out = side * (C[j] / e - 1)
                            break
                        j += 1
                    if out is None:
                        j = min(j, len(C) - 1)
                        out = side * (C[j] / e - 1)
                    px12 = C[i - 1] / C[i - 24] - 1
                    b12 = btc12(T[i])
                    ar = arc.get(T[i])
                    fon = {
                        "монета 12ч": "↓" if px12 < -0.02 else "↑" if px12 > 0.02 else "ровно",
                        "биткоин 12ч": None if b12 is None else ("↓" if b12 < -0.005 else "↑" if b12 > 0.005 else "ровно"),
                        "интерес 24ч": None if not ar or ar[1] is None else ("↑" if ar[1] > 5 else "↓" if ar[1] < -5 else "ровно"),
                        "фандинг": None if not ar or ar[2] is None else ("−" if ar[2] < -0.01 else "+" if ar[2] > 0.02 else "0"),
                    }
                    pool[name].append((out - LAB_FEE, fon, T[i] // 86400000, sym))
                    i = j + 1
                else:
                    i += 1

    def line(name, tr):
        v = [t for t, *_ in tr]
        if len(v) < MIN_N:
            return f"{name:<46} сделок {len(v):>4} — мало"
        tot = 1.0
        for t in v:
            tot *= 1 + t
        return (f"{name:<46} сделок {len(v):>4} · попаданий {100 * sum(1 for t in v if t > 0) / len(v):3.0f}% · "
                f"средняя {100 * st.mean(v):+5.2f}% · медиана {100 * st.median(v):+5.2f}% · худшая {100 * min(v):+5.1f}% · итог {100 * (tot - 1):+7.1f}%")

    print(f"монет {len(syms)} · получасовок {n_bars} ({n_bars / 48:.0f} монето-дней) · из них с архивом интереса {n_arch} · удержание ≤{LAB_HOLD} баров · стоп {LAB_STOP * 100:.0f}% · комиссия {LAB_FEE * 100:.1f}%\n")
    print("── всё вместе:")
    for name, *_ in RULES:
        print(" ", line(name, pool[name]))
    for key in ("монета 12ч", "биткоин 12ч", "интерес 24ч", "фандинг"):
        print(f"\n── по фону «{key}»:")
        for name, *_ in RULES:
            g = defaultdict(list)
            for t, fon, d, s in pool[name]:
                if fon.get(key) is not None:
                    g[fon[key]].append((t, fon, d, s))
            for k in ("↓", "ровно", "↑", "−", "0", "+"):
                if len(g.get(k, [])) >= MIN_N:
                    print(f"  {k:<6}", line(name, g[k]))
    # равновзвешенный портфель по дням для правил с положительной средней
    print("\n── портфель по дням (сумма сделок дня / число монет с сигналами), правила со средней > 0:")
    for name, *_ in RULES:
        tr = pool[name]
        v = [t for t, *_ in tr]
        if len(v) < MIN_N or st.mean(v) <= 0:
            continue
        byday = defaultdict(list)
        for t, fon, d, s in tr:
            byday[d].append(t)
        daily = [st.mean(x) for _, x in sorted(byday.items())]
        eq = 1.0
        peak = 1.0
        dd = 0.0
        for d in daily:
            eq *= 1 + d
            peak = max(peak, eq)
            dd = min(dd, eq / peak - 1)
        print(f"  {name:<46} дней {len(daily):>3} · {100 * st.mean(daily):+5.2f}%/день · итог {100 * (eq - 1):+6.1f}% · просадка {100 * dd:5.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
