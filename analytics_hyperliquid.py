"""Перекос китов Hyperliquid по монете — чтение готового среза.

Вторая половина Т-1: sources_hyperliquid снял позиции отслеживаемых
адресов в output/hl_state.json на этапе прогона, здесь этот файл
читается и превращается в поле знания звезды. Сети в этом модуле
нет — модуль можно звать сколько угодно раз, побочных эффектов ноль.

Смысл поля: сколько денег отслеживаемых китов стоит в лонге и в
шорте КОНКРЕТНОЙ монеты. Связка с зарядом (С-2): киты в шорте
тонкого флоата — топливо сжима; киты в лонге при нашем заряде —
подтверждение. И зашитая оговорка: киты — контекст, не сигнал на
копирование; в решения и скор поле не входит.
"""

from __future__ import annotations

import json
from pathlib import Path

from sources_hyperliquid import STATE_PATH

_CACHE: dict = {"mtime": None, "data": {}}


def _state() -> dict:
    """Срез с кешем на процесс по mtime — как пульс в детекторах."""
    try:
        mtime = Path(STATE_PATH).stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        try:
            _CACHE["data"] = json.loads(
                Path(STATE_PATH).read_text(encoding="utf-8"))
            _CACHE["mtime"] = mtime
        except (OSError, ValueError):
            return _CACHE["data"] or {}
    return _CACHE["data"]


def whale_bias(symbol: str) -> dict | None:
    """Перекос китов по монете. symbol — 'HEMIUSDT' или 'HEMI'.

    Возвращает {"long", "short", "n", "note"} в долларах позиций или
    None, когда ни один кит монету не держит (пустое поле честнее
    нулей: молчание — «китов здесь нет», нули — «киты в нуле»).
    """
    coin = symbol[:-4] if symbol.endswith("USDT") else symbol
    # Тысячные пары Binance живут на Hyperliquid с префиксом k:
    # 1000LUNC → kLUNC, 1000PEPE → kPEPE. Без маппинга кит по такой
    # монете не нашёлся бы никогда — молчание врало бы.
    if coin.startswith("1000"):
        coin = "k" + coin[4:]
    st = _state()
    long_usd = short_usd = 0.0
    n = 0
    for w in (st.get("whales") or {}).values():
        pos = (w.get("positions") or {}).get(coin)
        if not pos:
            continue
        usd = abs(pos.get("valueUsd") or 0.0)
        if not usd:
            continue
        n += 1
        if (pos.get("szi") or 0) > 0:
            long_usd += usd
        else:
            short_usd += usd
    if not n:
        return None
    side = ("в лонге" if long_usd > short_usd * 2 else
            "в шорте" if short_usd > long_usd * 2 else
            "разошлись")
    note = (f"киты HL {side}: лонг {_m(long_usd)} против "
            f"шорта {_m(short_usd)} ({n} " + _wh(n) + ")")
    return {"long": round(long_usd), "short": round(short_usd),
            "n": n, "note": note}


def _m(v: float) -> str:
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:.0f}"


def _wh(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "кит"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "кита"
    return "китов"
