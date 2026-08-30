#!/usr/bin/env python3
"""Репутация усилий по архиву CryptoQuant v2 (Р-2, 30.08.2026).

Смысл: смена презумпции — всплеск объёма в альте по умолчанию
раздача, пока не доказал обратное деньгами и удержанием. Скрипт
проходит cq_v2/, находит у каждой монеты ОБЪЁМНЫЕ ЭПИЗОДЫ
(оборот кратно выше своей нормы), выписывает каждому паспорт по
дискриминатору «чек — дельта — фандинг» и меряет ИСХОД: где цена
через три и семь дней после пика. Итог — output/reputation.json:

  у монеты: счёт «усилий было M, решённых R, раздали D» + строка
  для карточки + СЕГОДНЯШНИЙ отпечаток покупателя словами
  («мелочь льёт: чек 0.4 нормы, дельта −2.1M, третий день»).

Пороги ниже — первичная калибровка ночного разбора BTR/PROM/ONG;
уточнятся измерением по журналу (В-3). Запуск:
    python3 reputation_cq.py                 # cq_v2 → output/reputation.json
    python3 reputation_cq.py --verbose       # + сводка в консоль
"""
import argparse
import json
import statistics
from pathlib import Path

# ── пороги (первичные, помечены к калибровке) ──
EPISODE_MULT = 4.0     # день входит в эпизод: оборот ≥ 4× медианы-30
GLUE_DAYS = 2          # склейка соседних всплесков в один эпизод
NORM_WIN = 30          # окно нормы (медиана оборота/чека ДО дня)
HELD_RET7 = -0.10      # исход ≥ −10% от пика через 7 дн — удержали
DIST_RET7 = -0.25      # исход ≤ −25% — раздали (между — частично)
SMALL_CHK = 0.6        # чек ниже 0.6 нормы — «мелочь»
BIG_CHK = 1.3          # выше 1.3 — «крупный»
HOT_FUND = 0.05        # |фандинг| выше — сторона платит заметно
QUIET_DELTA = 0.02     # |дельта| < 2% оборота — стакан ровный


def _series(coin: dict, key: str) -> list:
    return list(reversed(coin.get(key) or []))   # старые → новые


def _median(vals: list) -> float:
    vals = [v for v in vals if v]
    return statistics.median(vals) if vals else 0.0


def episodes_of(tr: list, oh: list, fu: list, oi: list, lq: list) -> list:
    """Эпизоды усилий с паспортами и исходами."""
    closes = {r["datetime"]: r["close"] for r in oh}
    days = [t["datetime"] for t in tr]
    vols = [t["quote_volume"] for t in tr]
    marks = []
    for i, t in enumerate(tr):
        norm = _median(vols[max(0, i - NORM_WIN):i])
        if norm and vols[i] >= EPISODE_MULT * norm:
            marks.append(i)
    # склейка соседних всплесков
    groups, cur = [], []
    for i in marks:
        if cur and i - cur[-1] > GLUE_DAYS:
            groups.append(cur)
            cur = []
        cur.append(i)
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        i0, i1 = g[0], g[-1]
        peak = max(range(i0, i1 + 1), key=lambda i: vols[i])
        norm = _median(vols[max(0, i0 - NORM_WIN):i0]) or 1.0
        chks = [tr[i]["quote_volume"] / max(1, tr[i]["trade_count"])
                for i in range(max(0, i0 - NORM_WIN), i0)]
        chk_norm = _median(chks) or 1.0
        t = tr[peak]
        chk_peak = t["quote_volume"] / max(1, t["trade_count"])
        delta_ep = sum(tr[i]["quote_buy_volume"] - tr[i]["quote_sell_volume"]
                       for i in range(i0, i1 + 1))
        base_close = closes.get(days[i0 - 1]) if i0 else None
        peak_close = closes.get(days[peak])

        def _ret(shift: int):
            j = peak + shift
            if j >= len(days):
                return None
            c = closes.get(days[j])
            return (c / peak_close - 1) if (c and peak_close) else None

        r3, r7 = _ret(3), _ret(7)
        if r7 is None:
            verdict = "рано судить"
        elif r7 >= HELD_RET7:
            verdict = "удержали"
        elif r7 <= DIST_RET7:
            verdict = "раздали"
        else:
            verdict = "частично отдали"

        fu_map = {r["datetime"]: r["funding_rate"] for r in fu}
        f_ep = [fu_map.get(days[i]) for i in range(i0, i1 + 1)]
        f_ep = [x for x in f_ep if x is not None]
        lq_map = {r["datetime"]: r for r in lq}
        l_ep = [lq_map.get(days[i]) for i in range(i0, i1 + 1)]
        l_ep = [x for x in l_ep if x]
        oi_map = {r["datetime"]: r["open_interest"] for r in oi}
        oi0 = oi_map.get(days[max(0, i0 - 1)])
        oi1 = oi_map.get(days[min(len(days) - 1, i1)])

        out.append({
            "start": days[i0][:10], "peak": days[peak][:10],
            "end": days[i1][:10],
            "peak_mult": round(vols[peak] / norm, 1),
            "move_pct": (round((peak_close / base_close - 1) * 100, 1)
                         if base_close and peak_close else None),
            "chk_ratio": round(chk_peak / chk_norm, 2),
            "delta_usd": round(delta_ep),
            "funding_min": round(min(f_ep), 3) if f_ep else None,
            "funding_max": round(max(f_ep), 3) if f_ep else None,
            "oi_change_pct": (round((oi1 / oi0 - 1) * 100, 1)
                              if oi0 and oi1 else None),
            "liq_long_usd": round(sum(x["long_liquidations_usd"]
                                      for x in l_ep)),
            "liq_short_usd": round(sum(x["short_liquidations_usd"]
                                       for x in l_ep)),
            "ret3_pct": round(r3 * 100, 1) if r3 is not None else None,
            "ret7_pct": round(r7 * 100, 1) if r7 is not None else None,
            "verdict": verdict,
        })
    return out


def today_print(tr: list, oh: list, fu: list) -> dict:
    """Сегодняшний отпечаток покупателя — для строки карточки."""
    if not tr:
        return {}
    vols = [t["quote_volume"] for t in tr]
    i = len(tr) - 1
    t = tr[i]
    norm_v = _median(vols[max(0, i - NORM_WIN):i]) or 1.0
    chks = [tr[j]["quote_volume"] / max(1, tr[j]["trade_count"])
            for j in range(max(0, i - NORM_WIN), i)]
    chk_norm = _median(chks) or 1.0
    chk = t["quote_volume"] / max(1, t["trade_count"])
    delta = t["quote_buy_volume"] - t["quote_sell_volume"]
    streak = 0
    for j in range(i, -1, -1):
        d = tr[j]["quote_buy_volume"] - tr[j]["quote_sell_volume"]
        if (d < 0) == (delta < 0) and d != 0:
            streak += 1
        else:
            break
    closes = [r["close"] for r in oh]
    px_up = len(closes) >= 2 and closes[-1] > closes[-2]
    f = fu[-1]["funding_rate"] if fu else 0.0

    quiet = abs(delta) < QUIET_DELTA * t["quote_volume"]

    def _usd(x: float) -> str:
        x = abs(x)
        return (f"${x/1e6:.1f}M" if x >= 1e6 else f"${x/1e3:.0f}K")

    # кто в сделках: по размеру среднего чека против своей нормы
    who = ("сделки мелкие (чек втрое ниже обычного)"
           if chk < SMALL_CHK * chk_norm else
           "сделки крупные (чек выше обычного)"
           if chk > BIG_CHK * chk_norm else "сделки обычного размера")
    dayword = (f" — {streak}-й день подряд" if streak > 1 else " за сутки")
    if quiet:
        phrase = "покупки и продажи вровень, перекоса нет"
    elif delta < 0:
        phrase = (f"продают на {_usd(delta)} больше, чем покупают"
                  f"{dayword} · {who}")
        if px_up:
            phrase += (" · цена при этом не падает — кто-то крупный "
                       "скупает всё лимитными заявками")
    else:
        phrase = (f"покупают на {_usd(delta)} больше, чем продают"
                  f"{dayword} · {who}")
    if f >= HOT_FUND:
        phrase += f" · лонги платят за плечо {f:.2f}% — перегрев"
    elif f <= -HOT_FUND:
        phrase += f" · шорты платят за перекос {abs(f):.2f}%"

    return {"phrase": phrase,
            "vol_mult": round(vols[i] / norm_v, 1),
            "chk_ratio": round(chk / chk_norm, 2),
            "delta_usd": round(delta),
            "delta_streak": streak,
            "funding": round(f, 3),
            "date": t["datetime"][:10]}


def build(archive: Path) -> dict:
    rep = {"_meta": {"source": "cq_v2", "thresholds": {
        "episode_mult": EPISODE_MULT, "held_ret7": HELD_RET7,
        "dist_ret7": DIST_RET7}}}
    for fp in sorted(archive.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        coin = json.loads(fp.read_text())
        tr, oh = _series(coin, "trade"), _series(coin, "ohlcv")
        fu, oi = _series(coin, "funding"), _series(coin, "oi")
        lq = _series(coin, "liq")
        if not tr or not oh:
            continue
        eps = episodes_of(tr, oh, fu, oi, lq)
        resolved = [e for e in eps if e["verdict"] != "рано судить"]
        dist = sum(e["verdict"] == "раздали" for e in resolved)
        part = sum(e["verdict"] == "частично отдали" for e in resolved)
        held = sum(e["verdict"] == "удержали" for e in resolved)
        line = (f"всплесков объёма было {len(eps)}: после {dist} цену "
                f"слили, {held} устояли, {part} отдали наполовину"
                if resolved else
                (f"всплесков объёма {len(eps)}, исходы ещё зреют" if eps
                 else "всплесков объёма не было"))
        rep[fp.stem.upper() + "USDT"] = {
            "episodes": len(eps), "resolved": len(resolved),
            "distributed": dist, "partial": part, "held": held,
            "line": line,
            "today": today_print(tr, oh, fu),
            "last_episode": eps[-1] if eps else None,
        }
    return rep


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archive", default="cq_v2")
    ap.add_argument("--out", default="output/reputation.json")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    rep = build(Path(a.archive))
    out = Path(a.out)
    out.parent.mkdir(exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(rep, ensure_ascii=False, indent=1))
    tmp.replace(out)
    coins = {k: v for k, v in rep.items() if k != "_meta"}
    n_ep = sum(v["episodes"] for v in coins.values())
    n_d = sum(v["distributed"] for v in coins.values())
    n_h = sum(v["held"] for v in coins.values())
    print(f"репутации: монет {len(coins)} · эпизодов {n_ep} · "
          f"раздали {n_d} · удержали {n_h} → {out}")
    if a.verbose:
        worst = sorted(coins.items(),
                       key=lambda kv: -kv[1]["distributed"])[:10]
        print("\nчаще всех раздают:")
        for k, v in worst:
            if v["distributed"]:
                print(f"  {k[:-4]:9s} {v['line']}")
        print("\nгромкие отпечатки сегодня:")
        loud = sorted(coins.items(),
                      key=lambda kv: -abs(kv[1]["today"].get("delta_usd", 0)))
        for k, v in loud[:10]:
            t = v["today"]
            print(f"  {k[:-4]:9s} {t.get('phrase','')} "
                  f"(дельта {t.get('delta_usd',0)/1e6:+.1f}M)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
