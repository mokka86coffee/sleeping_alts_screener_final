"""Ретро Г-16: были ли вихрь+дельта+Клингер ДО хода. Руками, с сетью.

Запуск из каталога проекта (сеть нужна, ключей не надо):
    python klinger_retro.py                  # BTR ONG TAC + BTC контролем
    python klinger_retro.py MYX PROM --days 150

ЧТО ДЕЛАЕТ. Для каждой монеты тянет дневные свечи Binance Futures,
САМ находит её ход (сильнейший разбег закрытий: минимум +25% за две
недели — порог ручкой --min-gain) и смотрит, что говорили три
независимых измерения НАКАНУНЕ первого дня разбега:
    Клингер  — KVO выше сигнала / пересечение вверх за 5 дней до;
    вихрь    — VI+ выше VI− / пересечение вверх за 5 дней до;
    дельта   — знак дневной дельты (§10: 2·takerBuyQuote − quoteVol)
               по последним 5 дням до хода.
Вердикт: сколько из трёх смотрели вверх. Это ПРОВЕРКА ЗАДНИМ ЧИСЛОМ,
не сигнал: пороги на глаз, ход найден по факту. Если признаки
подтвердятся на BTR/ONG/TAC — величины поедут в ПОКАЗ (не в скор),
как записано в Г-16.

Вихрь здесь СВОЙ, четырнадцатидневный, а не пульсовый vi_p/vi_m:
пульс хранит хвост, а ретро нужен весь ряд. Это инструмент, не второй
источник для экранов — экраны читают пульс.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from analytics_klinger import kvo_series

FAPI = "https://fapi.binance.com/fapi/v1/klines"
IDX_T, IDX_HIGH, IDX_LOW, IDX_CLOSE = 0, 2, 3, 4
IDX_QUOTE_VOL, IDX_TAKER_QUOTE = 7, 10
VORTEX_N = 14

# Баров в дне по интервалам. Второй заход ретро (29.08): дневки
# связку не подтвердили (1–2 из трёх), а график владельца и вихрь
# пульса — четырёхчасовые; проверяем на родном масштабе, прежде чем
# записывать «не подтвердилось».
BARS_PER_DAY = {"1d": 1, "4h": 6, "1h": 24}


def fetch_klines(symbol: str, days: int, interval: str = "1d") -> list[list]:
    bpd = BARS_PER_DAY.get(interval, 1)
    q = urllib.parse.urlencode({"symbol": symbol.upper(), "interval": interval,
                                "limit": min(days * bpd + 40, 1000)})
    req = urllib.request.Request(FAPI + "?" + q,
                                 headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        rows = json.loads(r.read().decode())
    return rows[:-1] if rows else []      # последний бар не закрыт — прочь


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def vortex(klines: list[list], n: int = VORTEX_N) -> tuple[list, list]:
    """VI+ и VI− классические: суммы за n к сумме TR за n."""
    vmp, vmm, tr = [0.0], [0.0], [0.0]
    for i in range(1, len(klines)):
        h, l = _f(klines[i][IDX_HIGH]), _f(klines[i][IDX_LOW])
        ph, pl = _f(klines[i - 1][IDX_HIGH]), _f(klines[i - 1][IDX_LOW])
        pc = _f(klines[i - 1][IDX_CLOSE])
        vmp.append(abs(h - pl))
        vmm.append(abs(l - ph))
        tr.append(max(h - l, abs(h - pc), abs(l - pc)))
    vip, vim = [], []
    for i in range(len(klines)):
        a, b = max(0, i - n + 1), i + 1
        t = sum(tr[a:b]) or 1e-12
        vip.append(sum(vmp[a:b]) / t)
        vim.append(sum(vmm[a:b]) / t)
    return vip, vim


def bar_delta(k: list) -> float:
    """§10 спеки: дельта бара из готовых полей свечи, aggTrades не нужен."""
    return 2.0 * _f(k[IDX_TAKER_QUOTE]) - _f(k[IDX_QUOTE_VOL])


def find_move(klines: list[list], min_gain: float, hold: int) -> dict | None:
    """Сильнейший разбег: старт i, от закрытия i−1 к максимуму закрытий
    в ближайшие hold дней. Берётся МАКСИМАЛЬНЫЙ выигрыш ≥ порога."""
    best = None
    closes = [_f(k[IDX_CLOSE]) for k in klines]
    for i in range(1, len(closes) - 1):
        base = closes[i - 1]
        if base <= 0:
            continue
        top = max(closes[i:min(i + hold, len(closes))])
        gain = top / base - 1.0
        if gain >= min_gain and (best is None or gain > best["gain"]):
            best = {"i": i, "gain": gain}
    return best


def _d(ts_ms) -> str:
    return datetime.fromtimestamp(_f(ts_ms) / 1000,
                                  tz=timezone.utc).strftime("%d.%m")


def retro(symbol: str, days: int, min_gain: float, hold: int,
          interval: str = "1d", lookback: int = 5) -> str:
    bpd = BARS_PER_DAY.get(interval, 1)
    pair = symbol.upper()
    if not pair.endswith("USDT"):
        pair += "USDT"
    try:
        rows = fetch_klines(pair, days, interval)
    except Exception as e:
        return f"{symbol:<7} ✗ свечи не пришли: {type(e).__name__}: {e}"
    rows = rows[-days * bpd:]
    if len(rows) < 80:
        return (f"{symbol:<7} ✗ баров {len(rows)} — мало и для хода, "
                f"и для Клингера (нужно 68+)")
    mv = find_move(rows, min_gain, hold * bpd)
    if not mv:
        return (f"{symbol:<7} — хода ≥ {min_gain * 100:.0f}% за {hold} дн "
                f"в окне нет; признаки мерить не от чего")
    i = mv["i"]
    pre = rows[:i]                       # всё ДО первого дня разбега
    if len(pre) < 68:
        return (f"{symbol:<7} — ход {mv['gain'] * 100:+.0f}% от {_d(rows[i][IDX_T])} "
                f"слишком рано в окне: до него {len(pre)} баров, Клингеру мало")

    ks = kvo_series(pre)
    kvo, sig = ks["kvo"], ks["sig"]
    k_above = kvo[-1] > sig[-1]
    k_cross = any(kvo[j] > sig[j] and kvo[j - 1] <= sig[j - 1]
                  for j in range(len(kvo) - lookback, len(kvo)))

    vip, vim = vortex(pre)
    v_above = vip[-1] > vim[-1]
    v_cross = any(vip[j] > vim[j] and vip[j - 1] <= vim[j - 1]
                  for j in range(len(vip) - lookback, len(vip)))

    deltas = [bar_delta(k) for k in pre[-lookback:]]
    d_pos = sum(1 for d in deltas if d > 0)

    score = sum([k_above or k_cross, v_above or v_cross, d_pos >= 3])
    mark = {3: "✓✓✓ все три", 2: "✓✓ два из трёх",
            1: "✓ один", 0: "— ни один"}[score]
    return (f"{symbol:<7} ход {mv['gain'] * 100:+.0f}% от {_d(rows[i][IDX_T])} · "
            f"накануне: Клингер {'выше' if k_above else 'ниже'}"
            f"{' (крест↑)' if k_cross else ''} · "
            f"вихрь {'плюс' if v_above else 'минус'}"
            f"{' (крест↑)' if v_cross else ''} · "
            f"дельта {d_pos}/{lookback} бар в плюс → {mark}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ретро Г-16: признаки до хода")
    ap.add_argument("symbols", nargs="*",
                    default=["BTR", "ONG", "TAC", "BTC"],
                    help="монеты; по умолчанию BTR ONG TAC + BTC контролем")
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument("--min-gain", type=float, default=0.25,
                    help="порог хода долей: 0.25 = +25%%")
    ap.add_argument("--hold", type=int, default=14,
                    help="за сколько дней ход должен набраться")
    ap.add_argument("--interval", choices=sorted(BARS_PER_DAY), default="1d",
                    help="масштаб свечей; 4h — родной масштаб вихря пульса")
    ap.add_argument("--lookback", type=int, default=None,
                    help="окно признака В БАРАХ; по умолчанию 5 дневных "
                         "или 30 четырёхчасовых (те же 5 дней)")
    a = ap.parse_args()
    lb = a.lookback or 5 * BARS_PER_DAY.get(a.interval, 1)
    # потолок API — 1000 свечей: на 4h это ~160 дней, на 1h ~40
    ceil = 960 // BARS_PER_DAY.get(a.interval, 1)
    days = min(a.days, ceil)
    if days < a.days:
        print(f"(окно срезано до {days} дн — потолок API 1000 свечей "
              f"на {a.interval})")
    print(f"ретро {a.interval} за {days} дн · ход ≥ {a.min_gain * 100:.0f}% "
          f"за {a.hold} дн · признаки за {lb} бар до\n")
    for sym in (a.symbols or ["BTR", "ONG", "TAC", "BTC"]):
        print(retro(sym, days, a.min_gain, a.hold, a.interval, lb))
    print("\nзадним числом, пороги на глаз: это проверка ценности связки, "
          "не сигнал. Исход — в Г-16.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
