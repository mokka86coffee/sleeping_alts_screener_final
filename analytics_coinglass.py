"""Чтение среза Coinglass без сети: перекос ликвидаций по монете.

Сеть отработала шагом прогона (sources_coinglass.collect), здесь —
только готовый output/coinglass_state.json. Поле liq24h — КОНТЕКСТ,
не сигнал: подтверждение стороны каскада живыми суммами («за сутки
вынесло лонгов на X»), в решения не входит, показ ждёт Э-7.
"""

from __future__ import annotations

import json
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent

STATE_PATH = BASE_DIR / "output" / "coinglass_state.json"

_CACHE: dict = {"mtime": None, "data": {}}


def _fmt_usd(v: float) -> str:
    if v >= 1e9:
        return f"${v/1e9:.1f} млрд"
    if v >= 1e6:
        return f"${v/1e6:.1f} млн"
    if v >= 1e3:
        return f"${v/1e3:.0f} тыс"
    return f"${v:.0f}"


def _load() -> dict:
    try:
        mtime = STATE_PATH.stat().st_mtime
    except OSError:
        return {}
    if _CACHE["mtime"] != mtime:
        try:
            _CACHE["data"] = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            _CACHE["mtime"] = mtime
        except (OSError, ValueError):
            return _CACHE["data"] or {}
    return _CACHE["data"] or {}


def _base_coin(sym: str) -> str:
    s = sym.upper()
    for tail in ("USDT", "USDC", "BUSD", "USD"):
        if s.endswith(tail) and len(s) > len(tail):
            return s[: -len(tail)]
    return s


def liq_bias(symbol: str) -> dict | None:
    """{long, short, side, note[, map]} за сутки или None.

    side — кого выносило больше (реактивная сторона каскада);
    note — готовая русская строка для карточки. map присутствует
    только при доступной по тарифу карте кластеров.
    """
    rec = (_load().get("coins") or {}).get(_base_coin(symbol))
    if not isinstance(rec, dict):
        return None
    long_usd = float(rec.get("long") or 0.0)
    short_usd = float(rec.get("short") or 0.0)
    if long_usd <= 0 and short_usd <= 0:
        return None
    side = "лонгам" if long_usd >= short_usd else "шортам"
    out = {
        "long": long_usd, "short": short_usd, "side": side,
        "note": (f"ликвидации за сутки: лонгов {_fmt_usd(long_usd)}, "
                 f"шортов {_fmt_usd(short_usd)} — каскад бил по {side}"),
    }
    if rec.get("map"):
        out["map"] = rec["map"]
    return out
