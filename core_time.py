"""ВРЕМЯ ПРОЕКТА — ТОЛЬКО UTC (16.09, владелец: «никакой привязки ко времени машины и к константам: время
всегда берём в UTC, вычисляем из машинных данных, на экран выводим строго местное»).
Пояс компьютера или сервера здесь не участвует ни в чём: «сейчас» — это секунды эпохи, и они одинаковы в
любой стране; дата и час получаются из них в UTC. Местное время делает только страница в браузере.
  • utc_now(), utc_today(), utc_today_iso(), utc_hm(), utc_stamp() — «сейчас» и «сегодня» по UTC;
  • row_dt(r) — время строки журнала с полями at + hm, если строка помечена tz=UTC (или это дозабор,
    backfill, который всегда писал UTC). Строка без пометки — запись по часам машины до перехода:
    её время неизвестно, пока utc_migrate не вычислит его по данным, поэтому row_dt отдаёт None, и в
    расчёты по времени она не идёт (лучше без точки, чем с точкой не на своём месте).
    default_utc=True — для журналов, которые и раньше писали UTC (liq_log).
Экранам время отдаётся секундами или ISO с Z; в местное его переводит только скрипт страницы.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

UTC = timezone.utc


def utc_now() -> datetime:
    return datetime.now(UTC)


def utc_today() -> date:
    return utc_now().date()


def utc_today_iso() -> str:
    return utc_today().isoformat()


def utc_hm() -> str:
    return utc_now().strftime("%H:%M")


def utc_stamp(dt: datetime | None = None) -> str:
    """ISO с Z — так метку понимает и питон, и браузер"""
    d = dt or utc_now()
    if d.tzinfo is None:
        raise ValueError("метка без пояса — время машины не принимается")
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_utc_row(r: dict) -> bool:
    return str(r.get("tz") or "").upper() == "UTC" or bool(r.get("backfill"))


def row_dt(r: dict, default_utc: bool = False) -> datetime | None:
    """время строки журнала (at «ГГГГ-ММ-ДД» + hm «ЧЧ:ММ») → datetime в UTC; время неизвестно → None"""
    if not (default_utc or is_utc_row(r)):
        return None
    try:
        d = datetime.strptime(f"{r.get('at')} {r.get('hm') or '00:00'}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None
    return d.replace(tzinfo=UTC)


def row_ts(r: dict, default_utc: bool = False) -> float | None:
    d = row_dt(r, default_utc)
    return d.timestamp() if d else None
