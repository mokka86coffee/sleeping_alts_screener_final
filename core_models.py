"""Модели данных. Единственный источник правды о структуре кандидата."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from core_config import MIN_RR_TRADABLE


@dataclass
class ScorePart:
    """Один слагаемый вклад в общий скор."""
    code: str
    label: str
    points: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VetoReason:
    """Причина, по которой монета не идёт в работу."""
    code: str
    label: str
    detail: str
    severity: str = "mid"   # high | mid | low

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Levels:
    """Числовые уровни сделки."""
    entry: float = 0.0
    stop: float = 0.0
    target1: float = 0.0
    target2: float = 0.0
    target3: float = 0.0

    @property
    def valid(self) -> bool:
        return self.entry > 0 and 0 < self.stop < self.entry and self.target1 > self.entry

    @property
    def risk(self) -> float:
        return max(self.entry - self.stop, 0.0)

    @property
    def reward(self) -> float:
        return max(self.target1 - self.entry, 0.0)

    @property
    def rr(self) -> float:
        r = self.risk
        return self.reward / r if r > 0 else 0.0

    @property
    def rr_full(self) -> float:
        """Соотношение по дальней цели: потенциал при полном отработке плана."""
        r = self.risk
        if r <= 0 or self.target3 <= self.entry:
            return 0.0
        return (self.target3 - self.entry) / r

    @property
    def stop_pct(self) -> float:
        return ((self.stop / self.entry) - 1) * 100 if self.entry > 0 else 0.0

    @property
    def target_pct(self) -> float:
        return ((self.target1 / self.entry) - 1) * 100 if self.entry > 0 else 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d.update({
            "rr": round(self.rr, 2),
            "rr_full": round(self.rr_full, 2),
            "stop_pct": round(self.stop_pct, 2),
            "target_pct": round(self.target_pct, 2),
            "valid": self.valid,
        })
        return d


@dataclass
class Strategy:
    """Торговый план по монете."""
    text: str = ""
    size_hint: str = ""
    kind: str = "none"          # taiko | dexe | trend | momentum | base | none
    levels: Levels = field(default_factory=Levels)

    @property
    def actionable(self) -> bool:
        """План предполагает вход, а не наблюдение."""
        return self.kind != "none" and self.size_hint != "БЕЗ ВХОДА"

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "size_hint": self.size_hint,
            "kind": self.kind,
            "actionable": self.actionable,
            "levels": self.levels.to_dict(),
        }


@dataclass
class Candidate:
    """Полный результат анализа одной монеты."""
    symbol: str
    bucket: str = "watch"
    rank: str = ""
    score: int = 0

    tags: list[dict] = field(default_factory=list)
    phase: dict = field(default_factory=dict)
    metrics: list[dict] = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    dexe: dict | None = None
    surge: dict | None = None
    squeeze: dict | None = None
    taiko: dict | None = None
    flow: dict | None = None
    analysis: str = ""

    buzz: dict | None = None
    strategy: Strategy = field(default_factory=Strategy)
    links: list[dict] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    sector: str = ""

    is_viral: bool = False
    score_parts: list[ScorePart] = field(default_factory=list)
    veto: list[VetoReason] = field(default_factory=list)
    vetoed: bool = False

    quote_volume_24h: float = 0.0

    # ── удобные свойства ──
    @property
    def base(self) -> str:
        return self.symbol[:-4] if self.symbol.endswith("USDT") else self.symbol

    @property
    def rr(self) -> float:
        return self.strategy.levels.rr

    @property
    def rr_ok(self) -> bool:
        """Соотношение риска к прибыли проходит порог."""
        return self.rr >= MIN_RR_TRADABLE

    @property
    def tradable(self) -> bool:
        """Монета готова к работе.

        Единственное определение на весь проект: план предполагает вход,
        уровни валидны, соотношение риска приемлемо, блокирующего вето нет.
        """
        return (
            self.strategy.actionable
            and self.strategy.levels.valid
            and self.rr_ok
            and not self.vetoed
        )

    def metric(self, key: str, default: str = "—") -> str:
        for m in self.metrics:
            if m.get("key") == key:
                return str(m.get("val", default))
        return default

    def metric_num(self, key: str, default: float = 0.0) -> float:
        """Числовое значение метрики из сырых данных, а не из строки."""
        return float(self.raw.get(key, default) or default)

    def has_tag(self, needle: str) -> bool:
        return any(needle in t.get("text", "") for t in self.tags)

    def to_dict(self, include_raw: bool = False) -> dict:
        """Сериализация. Тяжёлые ряды свечей по умолчанию не включаются."""
        d = {
            "symbol": self.symbol,
            "bucket": self.bucket,
            "rank": self.rank,
            "score": self.score,
            "tags": self.tags,
            "phase": self.phase,
            "metrics": self.metrics,
            "dexe": self.dexe,
            "surge": self.surge,
            "squeeze": self.squeeze,
            "taiko": self.taiko,
            "flow": self.flow,
            "analysis": self.analysis,
            "buzz": self.buzz,
            "strategy": self.strategy.to_dict(),
            "links": self.links,
            "categories": self.categories,
            "sector": self.sector,
            "is_viral": self.is_viral,
            "score_parts": [p.to_dict() for p in self.score_parts],
            "veto": [v.to_dict() for v in self.veto],
            "vetoed": self.vetoed,
            "quote_volume_24h": self.quote_volume_24h,
            "rr": round(self.rr, 2),
            "tradable": self.tradable,
        }
        if include_raw:
            d["raw"] = self.raw
        return d


@dataclass
class FunnelStage:
    """Один узел воронки отбора."""
    code: str
    label: str
    count: int
    dropped: int = 0
    pass_pct: float = 0.0       # доля прошедших от предыдущего шага
    share_pct: float = 0.0      # доля от исходной выборки

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RunSnapshot:
    """Итог одного прогона скринера."""
    timestamp: str = ""
    total_scanned: int = 0
    duration_sec: float = 0.0
    errors: int = 0

    funnel: list[FunnelStage] = field(default_factory=list)
    sectors: list[dict] = field(default_factory=list)
    market_regime: dict = field(default_factory=dict)
    veto_stats: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)

    counts: dict = field(default_factory=dict)

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_scanned": self.total_scanned,
            "duration_sec": round(self.duration_sec, 1),
            "errors": self.errors,
            "counts": self.counts,
            "funnel": [f.to_dict() for f in self.funnel],
            "sectors": self.sectors,
            "market_regime": self.market_regime,
            "veto_stats": self.veto_stats,
            "candidates": self.candidates,
        }
