"""Клингер (KVO) по свечам — Г-16, поле знания.

ЗАЧЕМ. Связка вихрь+дельта+Клингер на графике владельца дала сигнал
за пять дней до хода BTC (29.08). Вихрь в пульсе уже есть (vi_p/vi_m),
дельта бара считается по спеке §10 — не хватало Клингера: он взвешивает
ОБЪЁМ направлением и размахом бара, то есть отвечает «куда идут деньги»,
а не «куда сходила цена».

ГРАНИЦЫ. В скор не входит и не войдёт — Г-16 прямо говорит: сначала
проверка ЗАДНИМ ЧИСЛОМ (klinger_retro.py), и только при подтверждении —
в ПОКАЗ. Модуль без сети и без зависимостей проекта: на вход — свечи в
формате Binance (списки, числа могут приходить СТРОКАМИ — приводим сами,
урок сборщика Coinglass).

ФОРМУЛА — классический Klinger Volume Oscillator:
    trend_i = +1, если (h+l+c)_i > (h+l+c)_{i-1}, иначе −1
    dm_i    = h_i − l_i                      (размах бара)
    cm_i    = cm_{i-1} + dm_i, если тренд не сменился,
              иначе dm_{i-1} + dm_i          (накопленный размах)
    vf_i    = vol_i · |2·dm_i/cm_i − 1| · trend_i · 100
    KVO     = EMA34(vf) − EMA55(vf);  сигнал = EMA13(KVO)

ЧТЕНИЕ. KVO выше сигнала и растёт — деньги заходят; пересечение снизу
вверх у дна — тот самый ранний признак. Пороги «на глаз» не заводим:
модуль отдаёт числа, читает их ретро и (после подтверждения) карточка.
"""

from __future__ import annotations

# Индексы свечи Binance: [t, open, high, low, close, vol, closeT,
# quoteVol, trades, takerBuyBase, takerBuyQuote, ...]. Объём берём
# КОТИРОВОЧНЫЙ (деньги, idx 7): проект меряет деньгами, а базовый
# объём между монетами несравним.
IDX_HIGH, IDX_LOW, IDX_CLOSE = 2, 3, 4
IDX_QUOTE_VOL = 7

EMA_FAST, EMA_SLOW, EMA_SIG = 34, 55, 13


def _num(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None          # NaN → None


def _ema(values: list[float], period: int) -> list[float]:
    """EMA без затравки SMA: первый элемент — сам ряд. На длинах,
    которые требует kvo_series (≥ EMA_SLOW+EMA_SIG), разница с
    SMA-затравкой растворяется задолго до хвоста, который мы читаем."""
    k = 2.0 / (period + 1.0)
    out, e = [], None
    for v in values:
        e = v if e is None else v * k + e * (1.0 - k)
        out.append(e)
    return out


def volume_force(klines: list[list]) -> list[float] | None:
    """Ряд vf Клингера по свечам; None — если ряда не собрать.

    Бары с нечисловыми полями рвут накопление честно: cm начинается
    заново, а не тянется через дыру. Бар без размаха (h == l, бывает
    у мёртвых монет) даёт cm без прибавки; cm == 0 → vf = 0, деления
    нет."""
    if not klines or len(klines) < 2:
        return None
    rows = []
    for k in klines:
        try:
            h, l, c = _num(k[IDX_HIGH]), _num(k[IDX_LOW]), _num(k[IDX_CLOSE])
            v = _num(k[IDX_QUOTE_VOL])
        except (IndexError, TypeError):
            h = l = c = v = None
        rows.append(None if None in (h, l, c, v) else (h, l, c, v))

    vf: list[float] = []
    prev = None                 # (hlc, dm, trend, cm)
    for row in rows:
        if row is None:
            vf.append(0.0)
            prev = None
            continue
        h, l, c, v = row
        hlc, dm = h + l + c, h - l
        if prev is None:
            vf.append(0.0)
            prev = (hlc, dm, 0, dm)
            continue
        p_hlc, p_dm, p_trend, p_cm = prev
        trend = 1 if hlc > p_hlc else -1
        cm = p_cm + dm if trend == p_trend else p_dm + dm
        vf.append(v * abs(2.0 * dm / cm - 1.0) * trend * 100.0 if cm else 0.0)
        prev = (hlc, dm, trend, cm)
    return vf


def kvo_series(klines: list[list]) -> dict | None:
    """KVO и сигнальная по свечам: {"kvo": [...], "sig": [...]}.

    None — если баров меньше EMA_SLOW + EMA_SIG (68): хвост более
    коротких рядов ещё помнит затравку EMA, и число врало бы."""
    if not klines or len(klines) < EMA_SLOW + EMA_SIG:
        return None
    vf = volume_force(klines)
    if vf is None:
        return None
    kvo = [a - b for a, b in zip(_ema(vf, EMA_FAST), _ema(vf, EMA_SLOW))]
    return {"kvo": kvo, "sig": _ema(kvo, EMA_SIG)}


def klinger_state(klines: list[list]) -> dict | None:
    """Хвост ряда одним словарём — под точку пульса и карточку.

    {"kvo": последний, "sig": последний, "above": kvo > sig,
     "crossUp": пересечение снизу вверх на ПОСЛЕДНЕМ баре,
     "crossDn": обратное}. Всё поле знания; порогов нет."""
    ks = kvo_series(klines)
    if ks is None:
        return None
    kvo, sig = ks["kvo"], ks["sig"]
    above = kvo[-1] > sig[-1]
    was_above = kvo[-2] > sig[-2]
    return {
        "kvo": round(kvo[-1], 1),
        "sig": round(sig[-1], 1),
        "above": above,
        "crossUp": above and not was_above,
        "crossDn": (not above) and was_above,
    }
