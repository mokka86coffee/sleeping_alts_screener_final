"""ПУЗЫРИ ДЛЯ БЫСТРОГО БОТА И СБОРЩИКА (30.09, владелец «заведи и проверь, что и где работает, а что нет по монетам»).
Пузырь — как в карточке монеты (render_coin._fast_events): дельта бара (покупки тейкера − продажи тейкера, $) дальше FAST_BUBBLE_SIGMA σ от нормы самой монеты;
белый (покупки) z ≥ +σ, красный (продажи) z ≤ −σ; «ясный» — интерес на баре вырос не меньше FAST_BUBBLE_OI_PCT %. Здесь бары 3 мин (Binance futures),
норма — среднее и σ дельты по 30 барам до бара. Только ЗАПИСЬ в журнал (фон), в решения бота не входит.
"""
from __future__ import annotations

import statistics as st

from core_http import get_json

try:
    from core_config import FAST_BUBBLE_SIGMA as SIGMA, FAST_BUBBLE_OI_PCT as OI_PCT
except ImportError:
    SIGMA, OI_PCT = 2.0, 1.5


def deltas(k: list) -> list[float]:
    """дельта бара, $ = 2 × покупки тейкера (котируемая) − оборот; k — закрытые 3-мин бары Binance"""
    return [2 * float(x[10]) - float(x[7]) for x in k]


def feats(k: list) -> dict | None:
    """k — ≥ 32 закрытых 3-мин баров, последний — бар всплеска. → z дельты последнего бара, доля покупок, пузыри в 20 барах до него"""
    if len(k) < 32:
        return None
    d = deltas(k)
    out = {}

    def z(i: int):
        base = d[max(0, i - 30):i]
        if len(base) < 10:
            return None
        sd = st.pstdev(base)
        return (d[i] - st.fmean(base)) / sd if sd > 0 else None

    zl = z(len(k) - 1)
    qv = float(k[-1][7])
    out["dz"] = None if zl is None else round(zl, 2)
    out["buy_share"] = round(float(k[-1][10]) / qv * 100, 1) if qv > 0 else None
    zs = [z(i) for i in range(len(k) - 21, len(k) - 1)]
    out["bub_white_20"] = sum(1 for v in zs if v is not None and v >= SIGMA)
    out["bub_red_20"] = sum(1 for v in zs if v is not None and v <= -SIGMA)
    out["bubble"] = "белый" if (zl is not None and zl >= SIGMA) else ("красный" if (zl is not None and zl <= -SIGMA) else None)
    return out


def oi_feats(sym: str) -> dict:
    """ПРИБЛИЖЕНИЕ «ВЫНОС ПО ИНТЕРЕСУ» (30.09, владелец «да»: потока ликвидаций Binance с этой машины нет — фьючерсный websocket молчит): интерес Binance по 5-мин
    барам за последний час — самое сильное падение и самый сильный рост на одном баре, %. Порога нет: непрерывные значения пишутся фоном, порог — по исходам.
    Калибровка (oi_flush_calib.py, 395 монет, 179 тыс. баров): падение ≤ −1% на баре — ликвидации ≥ 1K$ в потоке OKX+Bybit у 14% таких баров против 3% у остальных."""
    oi = get_json("https://fapi.binance.com/futures/data/openInterestHist", {"symbol": sym, "period": "5m", "limit": 13}, quiet_400=True) or []
    ov = [float(x["sumOpenInterestValue"]) for x in oi]
    ch = [(b / a - 1) * 100 for a, b in zip(ov, ov[1:]) if a > 0]
    return dict(oi5_min_1h=round(min(ch), 2), oi5_max_1h=round(max(ch), 2)) if len(ch) >= 6 else {}


def live(sym: str) -> dict | None:
    """для входа бота: свежие 3-мин бары монеты (последний закрытый — бар всплеска) + интерес по 5-мин барам"""
    k = get_json("https://fapi.binance.com/fapi/v1/klines", {"symbol": sym, "interval": "3m", "limit": 40}, quiet_400=True) or []
    out = feats(k[:-1]) or {}
    out.update(oi_feats(sym))
    return out or None
