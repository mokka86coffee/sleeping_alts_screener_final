"""Сборка кандидата: связывает метрики, детекторы, скоринг, вето и стратегию."""

from __future__ import annotations

from analytics_buzz import build_buzz, detect_viral, resolve_sector
from analytics_metrics import build_metric_rows, collect_metrics, strip_series
from analytics_scoring import classify_bucket, score_candidate
from analytics_strategy import build_strategy
from analytics_veto import evaluate_veto, is_blocking
from core_binance import drop_symbol_cache
from core_config import BUCKET_SCOUT
from core_models import Candidate
from detectors_dexe import DexeSignal, detect_dexe
from detectors_taiko import TaikoSignal, detect_taiko
from detectors_volume_surge import detect_volume_surge
from detectors_squeeze import detect_squeeze
from detectors_flow import detect_flow
from sources_external import build_fundamental_take_live, get_fundamentals


def _build_links(symbol: str) -> list[dict]:
    base = symbol[:-4] if symbol.endswith("USDT") else symbol
    return [
        {"text": "TradingView",
         "url": f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}.P"},
        {"text": "Binance",
         "url": f"https://www.binance.com/en/futures/{symbol}"},
        {"text": "CoinGecko",
         "url": f"https://www.coingecko.com/en/search?query={base}"},
        {"text": "Twitter",
         "url": f"https://x.com/search?q=%24{base}&f=live"},
    ]


def _needs_deep_fundamentals(score: int, has_pattern: bool, phase_num: int) -> bool:
    """Стоит ли тратить сетевой запрос к CoinGecko на эту монету.

    Запрос занимает около двух секунд в общей очереди, поэтому глубокий
    разбор получают только монеты, которые реально дошли до отбора:
    с распознанным паттерном, заметным скором или живой фазой рынка.
    Остальным достаётся DefiLlama и дисковый кэш.
    """
    return has_pattern or score >= BUCKET_SCOUT or phase_num >= 3


def build_candidate(
    symbol: str,
    rank_idx: int = 0,
    quote_volume_24h: float = 0.0,
    release_cache: bool = True,
) -> Candidate | None:
    """Полный анализ одной монеты."""
    try:
        m = collect_metrics(symbol, quote_volume_24h)
        if not m:
            return None

        tags: list[dict] = []

        # ── Фаза рынка ──
        vp = m.get("vortex_4h") or {}
        phase = {
            "num": vp.get("phase", 0),
            "label": vp.get("label", "—"),
            "vi_plus": vp.get("vi_plus", 0),
            "vi_minus": vp.get("vi_minus", 0),
        }

        # ── Детекторы ──
        surge = detect_volume_surge(symbol)
        squeeze = detect_squeeze(symbol)
        taiko = detect_taiko(symbol)
        dexe = detect_dexe(symbol)

        # TAIKO и DEXE взаимоисключающи: побеждает более уверенный
        if taiko.detected and dexe.detected:
            if taiko.score >= dexe.score:
                dexe = DexeSignal()
            else:
                taiko = TaikoSignal()

        # ── FLOW: семейство потока ──
        # Вызывается последним и работает диспетчером: подкейсы
        # (spring, churn, fuel, hidden, taker) считаются по общему
        # кэшу дневных свечей, зоны и события — один раз на все.
        # Дорогие запросы (funding, OI, спот) берутся только после
        # срабатывания дневного ядра: без него detected всё равно ложь,
        # и двести монет × два запроса уходят впустую.
        flow = detect_flow(symbol, quote_volume_24h)

        # ── Теги сигналов ──
        if surge.detected:
            arrow = "▲" if surge.is_green else "▼"
            tags.append({
                "text": f"VOL SURGE ×{surge.surge_ratio:.1f} {arrow}",
                "class": "tag-pattern surge",
            })

        if squeeze and squeeze.get("detected"):
            lvl = str(squeeze.get("risk_level", "high")).upper()
            tags.append({
                "text": f"SQUEEZE {lvl} · {squeeze.get('risk_score', 0)}",
                "class": "tag-pattern euphoria",
            })

        if taiko.detected:
            prefix = "TAIKO CONFIRMED" if taiko.confirmed_breakout else "TAIKO REVERSAL"
            tags.append({
                "text": f"{prefix} · {taiko.score}",
                "class": "tag-pattern taiko",
            })

        if dexe.detected:
            tags.append({
                "text": f"DEXE POST-PUMP · {dexe.score}",
                "class": "tag-pattern dexe",
            })

        if flow.detected:
            text = f"FLOW {flow.case.upper()} · {flow.score}"
            if flow.horizon_readable and flow.horizon_tf:
                text += f" · {flow.horizon_tf}"
            tags.append({"text": text, "class": "tag-pattern flow"})

        # ── Скоринг ──
        sb = score_candidate(m, surge, squeeze, taiko, dexe, flow)
        score = sb.capped()
        has_pattern = taiko.detected or dexe.detected or flow.detected
        bucket = classify_bucket(score, has_pattern)

        # ── Вето ──
        protected = bool(
            taiko.detected or dexe.detected or surge.detected or flow.detected
        )
        veto = evaluate_veto(m, squeeze)
        vetoed = is_blocking(veto) and not protected

        # ── Фундаментальные данные ──
        # Глубина зависит от того, интересна ли монета: сетевой запрос
        # к CoinGecko дорог и не окупается для монет вне отбора.
        deep = _needs_deep_fundamentals(score, has_pattern, phase.get("num", 0))
        fund = get_fundamentals(symbol, deep=deep)
        # Фундаментал уже загружен выше для категорий — берём из того же
        # объекта, дополнительных запросов нет. Поля именно такие:
        # mcap_usd, mcap_rank, fdv_usd (см. CoinFundamentals).
        raw_data = strip_series(m)
        raw_data.update({
            "mcap_usd": fund.mcap_usd,
            "mcap_rank": fund.mcap_rank or 0,
            "fdv_ratio": (fund.fdv_usd / fund.mcap_usd) if fund.mcap_usd > 0 else 0.0,
        })

        categories = list(fund.categories or [])
        if fund.defillama_category and fund.defillama_category not in categories:
            categories.append(fund.defillama_category)

        if categories:
            tags.append({"text": categories[0], "class": "tag-cat"})

        sector = resolve_sector(categories)

        # ── Внимание рынка и вирусность ──
        # Считается после категорий: detect_viral смотрит на сектор монеты
        buzz = build_buzz(m)
        is_viral, viral_label = detect_viral(buzz, surge, symbol, categories)
        if is_viral:
            tags.insert(0, {"text": viral_label, "class": "tag-pattern viral"})
            vetoed = False   # четвёртый защищённый трек

        # ── Аналитический текст ──
        analysis_parts = [
            p for p in (
                taiko.verdict if taiko.detected else "",
                dexe.verdict if dexe.detected else "",
                flow.verdict if flow.detected else "",
                surge.verdict if surge.detected else "",
            ) if p
        ]
        analysis = " ".join(analysis_parts)

        fund_take = build_fundamental_take_live(fund)
        if fund_take:
            analysis = f"{analysis} {fund_take}".strip() if analysis else fund_take

        # ── Стратегия ──
        strategy = build_strategy(m, squeeze, taiko, dexe)

        return Candidate(
            symbol=symbol,
            bucket=bucket,
            rank=f"#{rank_idx:03d}" if rank_idx else "",
            score=score,
            tags=tags,
            phase=phase,
            metrics=build_metric_rows(m),
            raw=raw_data,
            dexe=dexe.to_dict() if dexe.detected else None,
            surge=surge.to_dict() if surge.detected else None,
            squeeze=squeeze,
            taiko=taiko.to_dict() if taiko.detected else None,
            flow=flow.to_dict() if flow.detected else None,
            analysis=analysis,
            buzz=buzz,
            strategy=strategy,
            links=_build_links(symbol),
            categories=categories,
            sector=sector,
            is_viral=is_viral,
            score_parts=sb.parts,
            veto=veto,
            vetoed=vetoed,
            quote_volume_24h=quote_volume_24h,
        )

    finally:
        # Часовой ряд на 1000 свечей по 200 монетам — это сотни мегабайт
        if release_cache:
            drop_symbol_cache(symbol)
