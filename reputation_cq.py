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
from datetime import datetime
from pathlib import Path

# ── пороги (первичные, помечены к калибровке) ──
EPISODE_MULT = 4.0     # день входит в эпизод: оборот ≥ 4× медианы-30
GLUE_DAYS = 2          # склейка соседних всплесков в один эпизод
NORM_WIN = 30          # окно нормы (медиана оборота/чека ДО дня)
HELD_RET7 = -0.10      # исход ≥ −10% от пика через 7 дн — удержали
DIST_RET7 = -0.25      # исход ≤ −25% — раздали (между — частично)
SMALL_CHK = 0.6        # чек ниже 0.6 нормы — «мелочь»
BIG_CHK = 1.3          # выше 1.3 — «крупный»

# ── ПРАВКИ 01.09 (SKR-урок: детектор показал монету через 2 часа
#    ПОСЛЕ ×3 от дна) ─────────────────────────────────────────────
# Опоздание было не в шаблоне, а в ОКНЕ: фигура считалась неделей и
# зажигалась, когда ход состоялся на две трети. Раннее окно ловит ту
# же фигуру, пока перевес продаж уже держится, а цена ещё не ушла.
LADDER_EARLY_DAYS = 4    # окно раннего распознавания фигуры
LADDER_EARLY_MIN = 0.08  # цена тронулась — но это ещё не ход
LADDER_LATE_MIN = 0.25   # выше — ход состоялся, вход дорогой
LADDER_NEG_DAYS = 3      # сколько дней из окна должны быть с продажами

# Курок ПО СВЯЗКЕ, без ожидания недельного окна. Случай ZKC 31.08:
# оборот 635 норм при отрицательном фандинге — тот же ONG-паттерн, а в
# «Пойдёт?» монета не попала, потому что жёсткий порог требовал
# фандинга ≤ −0.5%. Связка «оборот к норме + минус фандинга» зажигает
# курок сама.
TRIGGER_VOL_X = 20.0     # оборот к норме, при котором связка сама горит
TRIGGER_FUND_MAX = 0.0   # фандинг просто отрицательный, без порога
# КУРОК СРАБОТАЛ (04.09, случай USELESS): третий исход курка помимо
# «взведён» и «осечка». Вынос состоялся, шорты сгорели, толпа перевернулась
# в лонг — состояние другое, а журнал держал «взведён» до отката.
FIRED_PX = 0.25          # цена ≥ +25% от дня взвода
FIRED_OI_X = 1.5         # плечо ≥ ×1.5 от дня взвода
FIRED_LIQ_X = 2.0        # шортов ликвидировано ≥ ×2 лонгов за дни выноса
FIRED_DAYS = 4           # взвод ищем не дальше четырёх дней назад

# Стадия сюжета: «до движения» пускают в «Пойдёт?», «в движении»
# показывают отдельной полкой с подписью «уже идёт, вход дорогой».
# Список — по КУСКАМ текста сюжета: имя шаблона живёт в первых словах,
# и держать второй реестр имён значило бы завести место, где они
# разойдутся молча.
PLOT_MOVING_MARKS = (
    "НА ХОДУ", "ИСКРА", "подтверждение пришло", "кит ушёл",
    "крупняк отпустил", "раздача после пика", "крупняк тащит вверх",
    "лонгов вынесли", "курок сработал", "у цели сбора",
)
START_PX_6H = 8.0      # старт с места: цена за 6 ч, %
START_VOL_X = 5.0      # …при обороте к норме
START_OI_6H = 15.0     # …и плече за 6 ч, %
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


TARGET_TOL = 3.0        # % — «у цели», если плотнейшая полоса сверху ближе этого
TARGET_MIN_RUN = 15.0   # % — за неделю цена прошла минимум столько (иначе это не сбор, а шум у полосы)


def _crowd(sym_usdt: str | None) -> dict:
    """Доля счетов в лонге (толпа, топы) из output/coinglass_crowd.json; пусто — {}."""
    if not sym_usdt:
        return {}
    try:
        from core_config import BASE_DIR as _B
    except ImportError:
        _B = Path(__file__).resolve().parent
    try:
        raw = json.loads((_B / "output" / "coinglass_crowd.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    c = raw.get(sym_usdt) or raw.get(sym_usdt.replace("USDT", "")) or {}
    crowd = ((c.get("crowd") or {}).get("longPct")); top = ((c.get("top") or {}).get("longPct"))
    return {"crowd": crowd, "top": top}


def _at_target(oh: list, oi: list, fu: list, tr: list, px: list, sym: str | None = None) -> str:
    try:
        from analytics_liqmap import liq_zones
    except Exception:  # noqa: BLE001
        return ""
    if len(oh) < 20:
        return ""
    h = [r.get("high") or r["close"] for r in oh]; l = [r.get("low") or r["close"] for r in oh]
    c = [r["close"] for r in oh]; v = [r.get("quote_volume") or 0.0 for r in oh]
    med = _median(v[-60:]) or 0.0
    vv = [min(x, 3 * med) for x in v] if med else v
    price = c[-1]
    if not price or not px[-8]:
        return ""
    if price / px[-8] - 1 < TARGET_MIN_RUN / 100:
        return ""
    allz = liq_zones(h, l, c, vv, price)
    zones = [z for z in allz if z["price"] > price]
    if not zones:
        return ""
    top = max(zones, key=lambda z: z["weight"])
    # топливо по сторонам — сумма весов полос под и над ценой (модель), отношение снизу к сверху
    f_above = sum(z["weight"] for z in allz if z["price"] > price) or 0.0
    f_below = sum(z["weight"] for z in allz if z["price"] < price) or 0.0
    fuel_ratio = (f_below / f_above) if f_above else (9.9 if f_below else 1.0)
    cw = _crowd(sym); cl = cw.get("crowd"); tl = cw.get("top")
    crowd_long = max([x for x in (cl, tl) if x is not None] or [0.0])
    dist = (top["price"] / price - 1) * 100
    if dist > TARGET_TOL:
        return ""
    # кто двигает
    t = tr[-1]
    tk = t.get("buy_sell_ratio") or 0.0
    d = (t.get("quote_buy_volume") or 0.0) - (t.get("quote_sell_volume") or 0.0)
    oi_now = (oi[-1].get("open_interest") if oi else None) or 0.0
    oi_prev = (oi[-2].get("open_interest") if len(oi) > 1 else None) or 0.0
    oi_g = (oi_now / oi_prev - 1) if oi_prev else 0.0
    px_g = (c[-1] / c[-2] - 1) if len(c) > 1 and c[-2] else 0.0
    f = fu[-1]["funding_rate"] if fu else 0.0
    f_prev = fu[-2]["funding_rate"] if len(fu) > 1 else f
    head = (f"у цели сбора: цена в {dist:.1f}% от плотнейшей полосы стопов "
            f"{top['price']:.4g} сверху, выше полос нет — ")
    if tk > 1.0 and d > 0 and oi_g <= max(px_g, 0) + 0.10:
        return (head + f"ведёт покупатель: тейкер {tk:.2f}, дельта в плюс, плечо "
                f"{oi_g * 100:+.0f}% при цене {px_g * 100:+.0f}% — держать со стопом под полосой, "
                "выход в день, когда дельта уйдёт в минус")
    crowd_txt = (f"толпа в лонге {cl:.0f}%" if cl is not None else "") + (f", топы {tl:.0f}%" if tl is not None else "")
    fuel_txt = f"топлива снизу в {fuel_ratio:.1f} раза больше, чем сверху" if f_above and f_below else ""
    if ((px_g <= 0.02 and (oi_g > 0.15 or f > max(f_prev, 0) * 1.5 + 0.01)) or f >= 0.05
            or (crowd_long >= 60 and fuel_ratio >= 2 and oi_g > 0.10)):
        return (head + f"толпа набивается в лонг: плечо {oi_g * 100:+.0f}% при цене {px_g * 100:+.0f}%, "
                f"фандинг {f:.3f}%" + (f", {crowd_txt}" if crowd_txt else "") + (f", {fuel_txt}" if fuel_txt else "")
                + " — следующий ход вниз, к ближайшей полосе лонгов; снять часть в полосе")
    return (head + f"кто двигает — неясно: тейкер {tk:.2f}, дельта {d / 1e3:+.0f}K, плечо {oi_g * 100:+.0f}% "
            "— половину снять, остаток со стопом под полосой")


def plot_line(tr: list, oh: list, fu: list, oi: list, lq: list | None = None,
              sym: str | None = None, src: dict | None = None) -> str:
    """Сюжет: узнанный шаблон истории с человеческим прогнозом.
    Шаблоны калиброваны ночными разборами 30.08 (ONG/SKR — курок
    шортов; BTR — кит до взрыва; BLESS/TRUMP — кит поглощает слив;
    PROM/STX — крупняк тащит вверх; NIL — дёрг без подтверждения)."""
    if len(tr) < 10 or len(oh) < 10:
        return ""
    closes = {r["datetime"][:10]: r["close"] for r in oh}
    days = [t["datetime"][:10] for t in tr]
    px = [closes.get(d) for d in days]
    if not all(px[-8:]):
        return ""
    vols = [t["quote_volume"] for t in tr]
    med = _median(vols[-37:-7]) or 1.0
    dl = [t["quote_buy_volume"] - t["quote_sell_volume"] for t in tr]
    fu_last = fu[-1]["funding_rate"] if fu else 0.0
    fu_min7 = min((r["funding_rate"] for r in fu[-7:]), default=0.0)
    chk = tr[-1]["quote_volume"] / max(1, tr[-1]["trade_count"])
    chks = [tr[j]["quote_volume"] / max(1, tr[j]["trade_count"])
            for j in range(max(0, len(tr)-37), len(tr)-7)]
    chk_norm = _median(chks) or 1.0
    d_now, d_prev = dl[-1], dl[-2]
    px_wk = px[-1] / px[-8] - 1 if px[-8] else 0
    vol_now = vols[-1] / med

    # 0. У ЦЕЛИ СБОРА (05.09, случай «4»): цена в TARGET_TOL от плотнейшей
    # полосы стопов НАД ценой по своей карте (analytics_liqmap на дневках
    # со срезом оборота ×3 медианы). Дальше два ответа на «кто двигает»:
    #   ведёт покупатель — тейкер > 1 и дельта в плюс, плечо растёт не
    #     быстрее цены → держать со стопом под полосой;
    #   толпа набивается — цена стоит или ниже, а плечо/фандинг растут →
    #     следующий ход вниз, к ближайшей полосе лонгов.
    _at = _at_target(oh, oi, fu, tr, px, sym)
    if _at:
        return _at

    # 1. Курок второго акта (ONG/SKR): шорты платят жирно + мясорубка
    if fu_min7 <= -0.5 and vol_now >= 8:
        if d_now > 0:
            return ("второй акт НА ХОДУ: шорты платят "
                    f"{abs(fu_last):.1f}% — их выкуп и толкает цену; "
                    "по шаблону ONG/SKR акт ярок и короток: выход — "
                    "чек мельчает, фандинг к нулю или первый день "
                    "продаж")
        return ("курок взведён на шорты, второй акт (шаблон ONG/SKR): шорты "
                f"платят до {abs(fu_min7):.1f}%, оборот-мясорубка ×"
                f"{vol_now:.0f} — день покупок выше недавнего верха "
                "может дать резкий вынос; продолжение продаж — отбой")
    # 1б. Тот же курок ПО СВЯЗКЕ (правка 01.09, случай ZKC): жёсткий
    #     порог требовал фандинга ≤ −0.5%, и монета с оборотом в 635
    #     норм при фандинге в сотые доли мимо него проходила. Связка
    #     «оборот к норме + минус фандинга» достаточна сама: платят
    #     шорты, а не толпа, и оборот уже не рядовой.
    # ОСЕЧКА (03.09, случай ONG): курок висел три дня подряд, а монета
    # шла вниз — шаблон обещал «продолжение продаж — отбой», но отбой
    # никто не считал. Считаем: сколько дней подряд связка горит, где
    # цена относительно дня взвода, продают ли. Три дня, цена ниже,
    # продажи — осечка, из «Пойдёт?» снять. Шорты, которые платили,
    # уже вынесены раньше (ONG 26.08), топлива нет.
    fu_by_day = {r["datetime"][:10]: r["funding_rate"] for r in fu}
    # КУРОК СРАБОТАЛ (04.09, случай USELESS): за FIRED_DAYS назад был день
    # взвода (оборот ≥ ×20 при минус-фандинге), а сегодня фандинг ПЛЮС —
    # платят уже лонги, цена от дня взвода ≥ +25%, плечо ≥ ×1.5, шортов
    # ликвидировано вдвое больше лонгов. Это не «взведён» (шорты сгорели)
    # и не «осечка» (ход был). Топливо теперь ПОД ценой — следующий сбор
    # вниз; выход из состояния: продажи с падением — «раздача после пика».
    oi_by_day = {r["datetime"][:10]: r.get("open_interest") for r in oi}
    armed_j = None
    for j in range(len(tr) - 2, max(-1, len(tr) - 2 - FIRED_DAYS), -1):
        f_j = fu_by_day.get(days[j])
        if vols[j] / med >= TRIGGER_VOL_X and f_j is not None and f_j < TRIGGER_FUND_MAX:
            armed_j = j
            break
    if armed_j is not None and fu_last > 0 and px[-1] and px[armed_j] \
            and px[-1] / px[armed_j] - 1 >= FIRED_PX:
        oi_a, oi_n = oi_by_day.get(days[armed_j]), oi_by_day.get(days[-1])
        oi_ok = bool(oi_a and oi_n and oi_n / oi_a >= FIRED_OI_X)
        liq_ok = True
        if lq:
            lq_by = {r["datetime"][:10]: r for r in lq}
            sh = sum((lq_by.get(days[j]) or {}).get("short_liquidations_usd") or 0
                     for j in range(armed_j, len(tr)))
            lo_ = sum((lq_by.get(days[j]) or {}).get("long_liquidations_usd") or 0
                      for j in range(armed_j, len(tr)))
            liq_ok = sh >= FIRED_LIQ_X * max(1.0, lo_)
        if oi_ok and liq_ok:
            return (f"курок сработал (шаблон USELESS): с дня взвода цена "
                    f"+{(px[-1] / px[armed_j] - 1) * 100:.0f}%, плечо ×"
                    f"{oi_n / oi_a:.1f}, фандинг перешёл в плюс {fu_last:.3f}% — "
                    "шорты сгорели, платят уже лонги, топливо под ценой; "
                    "держат — крупняк тащит, первый день продаж с падением — "
                    "раздача после пика")
    armed = 0
    for j in range(len(tr) - 1, -1, -1):
        f_j = fu_by_day.get(days[j])
        if vols[j] / med >= TRIGGER_VOL_X and f_j is not None and f_j < TRIGGER_FUND_MAX:
            armed += 1
        else:
            break
    if armed >= 3 and px[-1] and px[-armed] and px[-1] < px[-armed] \
            and sum(dl[-3:]) < 0:
        return (f"курок — осечка: взведён {armed} дн подряд, а цена ниже "
                f"дня взвода на {(1 - px[-1] / px[-armed]) * 100:.0f}% при "
                "продажах — шорты, что платили, вынесены раньше, топлива "
                "нет; по правилу «продолжение продаж — отбой»")
    if vol_now >= TRIGGER_VOL_X and fu_last < TRIGGER_FUND_MAX:
        return ("курок взведён на шорты (оборот и фандинг): оборот ×"
                f"{vol_now:.0f} к норме при фандинге {fu_last:.3f}% — "
                "платят шорты, а не толпа; день покупок выше недавнего "
                "верха даёт вынос, продолжение продаж — отбой")
    # 2. Рука над сливом (BLESS/TRUMP): дни продаж, а цена не падает
    neg_streak = 0
    for j in range(len(dl)-1, -1, -1):
        if dl[j] < 0:
            neg_streak += 1
        else:
            break
    # Потолок по цене (правка 01.09): условие принимало ЛЮБОЙ рост, и
    # «кит поглощает слив» перехватывал фигуру целиком — она почти
    # никогда не зажигалась. Рука над сливом — это когда цена ДЕРЖИТСЯ
    # под продажами; когда она при тех же продажах РАСТЁТ, это уже
    # «крупняк тащит вверх», и разбирать её должен следующий шаблон.
    if neg_streak >= 3 and -0.05 < px_wk < LADDER_EARLY_MIN:
        return (f"кит поглощает слив (шаблон BLESS/TRUMP): продают "
                f"{neg_streak} дней подряд, а цена держится — крупный "
                "собирает лимитками; развязку выбирает он: рост "
                "возможен резкий, но первый день, когда продажи "
                "продавили цену на 7%+, — кит ушёл, выходить без "
                "иллюзий")
    # 3. Лестница руки (PROM/STX): цена растёт при перевесе продаж.
    #    ДВЕ СТАДИИ (правка 01.09). Недельное окно зажигалось, когда
    #    ход состоялся на две трети — так SKR попала в список на
    #    третьем иксе. Ранняя стадия смотрит окно в четыре дня: перевес
    #    продаж уже держится, цена ещё не ушла. Поздняя осталась, но
    #    названа честно — «на ходу», ей в «Пойдёт?» не место.
    wk_delta = sum(dl[-7:])
    if px_wk > LADDER_LATE_MIN and wk_delta < 0 and fu_last < 0.05:
        return ("крупняк тащит вверх (шаблон PROM/STX): за неделю цена +"
                f"{px_wk*100:.0f}% при перевесе продаж — лимитный "
                "покупатель ведёт, плечо толпы холодное; ход уже "
                "состоялся, вход дорогой — жив до дня, когда продажи "
                "совпадут с падением 7%+, это крупняк отпустил")
    E = LADDER_EARLY_DAYS
    if len(px) > E and px[-(E + 1)]:
        px_e = px[-1] / px[-(E + 1)] - 1
        e_neg = sum(1 for x in dl[-E:] if x < 0)
        if (LADDER_EARLY_MIN <= px_e <= LADDER_LATE_MIN
                and sum(dl[-E:]) < 0 and e_neg >= LADDER_NEG_DAYS
                and fu_last < 0.05):
            return ("крупняк начал тащить вверх (шаблон PROM/STX): "
                    f"за {E} дня цена +{px_e*100:.0f}% при продажах "
                    f"{e_neg} дней из {E} — лимитный покупатель ведёт, "
                    "плечо толпы холодное; ход ещё не состоялся — "
                    "отбой, если продажи совпадут с падением 7%+")
    # 4. Кит до взрыва (BTR): тихо, чек крупный, дельта ≈0
    if (vol_now >= 1.5 and chk > 1.4 * chk_norm
            and abs(d_now) < 0.03 * vols[-1] and abs(fu_last) < 0.05):
        return ("кит набирает тихо (шаблон BTR-до-взрыва): оборот "
                f"×{vol_now:.1f} при крупном чеке и ровной кассе — "
                "кто-то собирает лимитками; искрой обычно служит "
                "вынос шортов, дальше возможен розничный шторм")
    # 5. Дёрг без подтверждения (NIL): вчера импульс+, сегодня минус
    if d_prev > 0 and d_now < 0 and px[-2] and px[-2] / px[-3] - 1 > 0.08             and px[-1] < px[-2]:
        return ("дёрг без подтверждения (шаблон NIL): вчерашний "
                "импульс сегодня продают — старта не случилось; "
                "интерес вернёт только новый день покупок с "
                "удержанием выше вчерашнего верха")
    # 6. Раздача вторым днём после пика
    if len(dl) >= 3 and dl[-1] < 0 and dl[-2] < 0 and             max(vols[-5:]) / med >= 8 and px[-1] < max(p for p in px[-5:] if p) * 0.85:
        return ("раздача после пика (шаблон ONG-финал): второй день "
                "продаж после мясорубки, от вершины уже −15%+; по "
                "шаблону дальше тяжело — возврат интереса только "
                "через новый цикл набора")
    return ""


def plot_stage(plot: str) -> str:
    """Стадия сюжета: 'before' — ход ещё не состоялся, 'moving' — идёт.

    Нужна для правки 01.09: в «Пойдёт?» пускать только 'before'
    (курок, кит набирает тихо, ранняя стадия), а 'moving' показывать
    отдельной полкой с подписью «уже идёт, вход дорогой». Без этого
    список соблазняет тем, что выросло вчетверо вчера.

    Пустой сюжет — 'before' по умолчанию НЕ ставим: нечего показывать,
    значит и стадии нет.
    """
    p = str(plot or "")
    if not p:
        return ""
    # ТОЛЬКО ГОЛОВА, до первого двоеточия. Хвост сюжета — это сторож,
    # и в нём законно стоят слова другой стадии: «кит поглощает слив …
    # первый день, когда продажи продавили цену, — кит ушёл». Поиск
    # по всему тексту зачислял такую монету в «уже идёт», хотя она
    # только взводится (поймано тестом 01.09).
    head = p.split(":")[0]
    if "осечка" in head or "отбой" in head:
        return ""                     # снято: ни «Пойдёт?», ни «уже идёт»
    for m in PLOT_MOVING_MARKS:
        if m in head:
            return "moving"
    return "before"


def live_refresh(entry: dict, live: dict) -> dict:
    """Живой пересчёт «сегодня» и сюжета внутри дня (30.08, зазор
    свежести). Вчерашняя дневка кванта даёт историю и шаблон;
    свежие числа часового прогона Coinglass — сегодняшний факт.
    live: {delta_usd, px_chg_pct, funding, vol_mult, taker}.
    Возвращает копию entry с обновлёнными today.phrase / plot —
    сюжет «взведён» умеет выстреливать, «рука» — уходить, не
    дожидаясь завтрашней дневки (урок SKR)."""
    import copy
    e = copy.deepcopy(entry)
    t = e.get("today") or {}
    # Плечо (01.09): живому пересчёту оно не передавалось вовсе, и
    # самый сильный внутридневной сигнал — обвал открытого интереса —
    # был ему не виден. Поля нет — переход просто не сработает.
    oi = live.get("oi_chg_pct")
    d = live.get("delta_usd")
    px = live.get("px_chg_pct") or 0.0
    f = live.get("funding")
    vm = live.get("vol_mult")
    if d is None:
        return e

    def _usd(x):
        x = abs(x)
        return (f"${x/1e6:.1f}M" if x >= 1e6 else f"${x/1e3:.0f}K")

    # преемственность серии: знак совпал со вчерашним — день N+1
    streak = t.get("delta_streak") or 0
    prev_neg = (t.get("delta_usd") or 0) < 0
    streak = streak + 1 if (d < 0) == prev_neg and d != 0 else 1
    dayw = f" — {streak}-й день подряд" if streak > 1 else " за сутки"
    if d < 0:
        ph = f"продают на {_usd(d)} больше, чем покупают{dayw}"
        if px > 1:
            ph += (" · цена при этом растёт — кто-то крупный "
                   "скупает всё лимитными заявками")
    else:
        ph = f"покупают на {_usd(d)} больше, чем продают{dayw}"
    if f is not None and f >= 0.05:
        ph += f" · лонги платят за плечо {f:.2f}% — перегрев"
    elif f is not None and f <= -0.05:
        ph += f" · шорты платят за перекос {abs(f):.2f}%"
    t.update({"phrase": ph, "delta_usd": round(d),
              "delta_streak": streak, "live": True})
    e["today"] = t

    # горячие переходы сюжета по свежему факту
    pl = e.get("plot") or ""
    # ЛОНГОВ ВЫНЕСЛИ (01.09, случай BLESS). Единственный переход, где
    # решает ПЛЕЧО, а не дельта: цена вниз, открытый интерес вниз и
    # оборот выше нормы в один час — это ликвидация длинных, а не
    # раздача. Отличается от «кит ушёл» тем, что там уходит лимитный
    # покупатель при живом плече, здесь наоборот — уходит само плечо.
    # Стоит РАНЬШЕ прочих: вынос перебивает любую прежнюю фигуру,
    # какой бы она ни была.
    # Ход и плечо берём ЧАСОВЫЕ, если пульс их дал: вынос случается за
    # час, и в суточных числах он размывается втрое. Часовых нет —
    # падаем на суточные, тогда переход просто сработает позже.
    _oi_h = live.get("oi_chg_1h")
    _px_h = live.get("px_chg_1h")
    oi_v = _oi_h if _oi_h is not None else oi
    px_v = _px_h if _px_h is not None else px
    _span = "за час" if _oi_h is not None else "за сутки"
    if (oi_v is not None and oi_v <= -6 and px_v < -4
            and (vm or 0) >= 1.5):
        e["plot"] = (f"лонгов вынесли (сегодня): {_span} цена "
                     f"{px_v:.0f}% при плече {oi_v:.0f}% и обороте "
                     f"×{vm:.1f} — длинных ликвидировали, а не раздали; "
                     "интерес вернётся только новым набором")
    elif "курок взведён на шорты" in pl and d > 0 and px > 8:
        # Ловит ОБА курка (01.09): и связку, и второй акт. Прежний
        # прежний маркер видел только один курок из двух, и курок по
        # связке никогда не переходил в «акт НА ХОДУ».
        e["plot"] = ("второй акт НА ХОДУ (курок выстрелил сегодня): "
                     f"день покупок и цена +{px:.0f}% — выкуп шортов "
                     "толкает; по шаблону ONG/SKR акт ярок и короток: "
                     "выход — чек мельчает, фандинг к нулю или первый "
                     "день продаж")
    elif "курок сработал" in pl and d < 0 and px < -7:
        e["plot"] = ("раздача после пика (сегодня): после сработавшего курка "
                     f"продажи и цена {px:.0f}% — лонги, набранные на выносе, "
                     "отдают; по шаблону ONG-финал ход отдают быстро")
    elif "кит поглощает слив" in pl and d < 0 and px < -7:
        e["plot"] = ("кит ушёл (развязка сегодня): продажи продавили "
                     f"цену на {abs(px):.0f}% — шаблон BLESS/TRUMP "
                     "предупреждал: выходить без иллюзий, возврат "
                     "интереса только новым циклом набора")
    elif "крупняк" in pl and d < 0 and px < -7:
        # Корень сменился вместе с именем (01.09): «лестниц» больше не
        # встречается ни в одном сюжете, и переход молча перестал бы
        # срабатывать. Ловит обе стадии — «тащит вверх» и «начал».
        # Корень «крупняк» ловит ОБЕ стадии (правка 01.09): после
        # переименования поздней в «крупняк тащит вверх» проверка по
        # «крупняк тащит вверх» тихо перестала бы её видеть, а финал у них
        # общий — продажи совпали с падением.
        e["plot"] = ("крупняк отпустил (сегодня): продажи совпали с "
                     f"падением {abs(px):.0f}% — покупатель отпустил; "
                     "по шаблону PROM дальше перезарядка, не разгон")
    elif "кит набирает тихо" in pl and d > 0 and (vm or 0) >= 8:
        e["plot"] = ("похоже, ИСКРА (сегодня): на наборе кита пришли "
                     f"покупки при обороте ×{vm:.0f} — по шаблону BTR "
                     "дальше возможен розничный шторм; сторожа: чек "
                     "мельчает и фандинг греется — поздняя стадия")
    elif "дёрг без подтверждения" in pl and d > 0 and px > 5:
        e["plot"] = ("подтверждение пришло (сегодня): новый день "
                     f"покупок и цена +{px:.0f}% — дёрг становится "
                     "стартом; интерес законен, пока покупки держатся")
    # СТАРТ С МЕСТА (03.09, случай MUBARAK): часовой слой умел только
    # ПОВЫШАТЬ стоящий шаблон, а у монеты без шаблона +32% за день с
    # оборотом ×17 и удвоением плеча проходили мимо до завтрашней
    # дневки. Теперь монете без сюжета ставим часовой: за 6 ч цена
    # ≥ +8% при обороте ≥ ×5 к норме и плече ≥ +15%. Дневка завтра
    # подтвердит шаблоном или снимет.
    if not e.get("plot"):
        _p6 = live.get("px_chg_6h"); _o6 = live.get("oi_chg_6h")
        _vm = live.get("vol_mult")
        if (_p6 is not None and _p6 >= START_PX_6H
                and (_vm or 0) >= START_VOL_X
                and (_o6 is not None and _o6 >= START_OI_6H)):
            e["plot"] = (f"старт с места (часы): за 6 ч цена +{_p6:.0f}% при "
                         f"обороте ×{_vm:.0f} к норме и плече +{_o6:.0f}% — ход "
                         "начался без дневного шаблона; подтверждение — "
                         "дневка с покупками, отбой — отдача половины хода "
                         "за сутки")
            t["phrase"] = (f"часы: +{_p6:.0f}% за 6 ч, плечо +{_o6:.0f}% — "
                           "старт с места")

    # ВИХРЬ КАК СТОРОЖ (02.09). Не переход и не смена шаблона — только
    # предупреждение в хвосте текста. Проверено на архиве (7 монет,
    # 14 событий): сжатие разрыва после пика даёт ВЫБРОС, а не
    # направление — 10 из 14 вниз, но 4 вверх это +18, +34, +52,
    # самые большие ходы выборки. Куда пойдёт — решает фундамент.
    _vx = live.get("vx") or {}
    _vs = _vx.get("state")
    if _vs in ("shrinking", "converged") and e.get("plot") \
            and "вихрь" not in str(e["plot"]):
        if _vs == "converged":
            _msg = "вихрь сошёлся, направления нет — любая свеча выброс"
        else:
            _msg = (f"вихрь сжался с {abs(_vx.get('peak', 0)):.2f} до "
                    f"{abs(_vx.get('spread', 0)):.2f} — импульс выдохся, "
                    "ждать выброс; куда — по фундаменту")
        e["plot"] = str(e["plot"]).rstrip(" .") + "; сторож: " + _msg
    # Стадию пересчитываем ПОСЛЕ горячих переходов (01.09): курок,
    # выстреливший в течение дня, становится «на ходу», и список
    # «Пойдёт?» обязан узнать об этом в тот же прогон, а не завтра.
    e["stage"] = plot_stage(e.get("plot"))
    return e


# ── ЖИВОЙ ДЕНЬ (05.09) ──────────────────────────────────────────
# Шаблоны считались только по дневкам cq_v2, которые приходят раз в
# сутки (~08:00 SGT): между ними при прогонах каждые полчаса смен не
# было в принципе — Coinglass и пульс качались, но в детектор не шли.
# Теперь текущий (незакрытый) день собирается из своих рядов и
# дописывается к дневкам как ещё одна строка:
#   оборот   — сумма ног b+s баров Coinglass с полуночи UTC,
#              приведённая к темпу полных суток (делим на долю дня);
#   тейкер   — Σb/Σs тех же баров; дельта — Σb−Σs (в темпе суток);
#   цена     — последняя из пульса (high/low — экстремумы пульса за день);
#   интерес, фандинг — последние из пульса.
# Дневка, когда придёт, эту строку заменит (ключ — дата).
LIVE_MIN_FRACTION = 0.15      # раньше ~3:40 UTC темп суток слишком шумный — день не дописываем
LIVE_MIN_BARS = 4             # и минимум четыре бара Coinglass за день


def _live_sources():
    try:
        from core_config import BASE_DIR as _B
    except ImportError:
        _B = Path(__file__).resolve().parent
    out = {"cg": {}, "pulse": {}}
    try:
        cg = json.loads((_B / "output" / "coinglass_fetch.json").read_text(encoding="utf-8"))
        out["cg"] = cg.get("coins") or {}
    except (OSError, ValueError):
        pass
    for pp in (_B / "pulse.json", _B / "output" / "pulse.json"):
        try:
            out["pulse"] = json.loads(pp.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            continue
    return out


def live_day(sym_usdt: str, src: dict, last_daily: str | None):
    """Строка текущего дня в формате cq_v2 (tr, oh, fu, oi) или None."""
    from datetime import timezone as _tz
    now = datetime.now(_tz.utc)
    today = now.strftime("%Y-%m-%d")
    if last_daily and last_daily[:10] >= today:
        return None                                   # дневка за сегодня уже есть
    frac = (now.hour * 60 + now.minute) / 1440.0
    if frac < LIVE_MIN_FRACTION:
        return None
    c = (src["cg"].get(sym_usdt) or src["cg"].get(sym_usdt.replace("USDT", "")) or {})
    ser = ((c.get("fut") or {}).get("series")) or []
    mid = int(datetime(now.year, now.month, now.day, tzinfo=_tz.utc).timestamp() * 1000)
    bars = [b for b in ser if b.get("t") and b["t"] >= mid and b.get("b") is not None and b.get("s") is not None]
    if len(bars) < LIVE_MIN_BARS:
        return None
    b = sum(x["b"] for x in bars); s_ = sum(x["s"] for x in bars)
    pace = 1.0 / max(frac, LIVE_MIN_FRACTION)
    pr = src["pulse"].get(sym_usdt) or []
    pr = [r for r in pr if r.get("price")]
    if not pr:
        return None
    pr.sort(key=lambda r: r.get("t") or 0)
    day_rows = [r for r in pr if (r.get("t") or 0) * 1000 >= mid] or pr[-1:]
    px = float(pr[-1]["price"]); hi = max(float(r["price"]) for r in day_rows); lo = min(float(r["price"]) for r in day_rows)
    oi_v = pr[-1].get("oi_usd"); fu_v = pr[-1].get("funding")
    dt = today + " 00:00:00"
    return {
        "tr": {"datetime": dt, "quote_buy_volume": b * pace, "quote_sell_volume": s_ * pace,
               "quote_volume": (b + s_) * pace, "buy_sell_ratio": (b / s_) if s_ else None, "live": True},
        "oh": {"datetime": dt, "open": float(day_rows[0]["price"]), "high": hi, "low": lo, "close": px,
               "quote_volume": (b + s_) * pace, "live": True},
        "fu": {"datetime": dt, "funding_rate": float(fu_v) if fu_v is not None else 0.0, "live": True},
        "oi": {"datetime": dt, "open_interest": float(oi_v) if oi_v is not None else None, "live": True},
    }


def build(archive: Path) -> dict:
    rep = {"_meta": {"source": "cq_v2", "thresholds": {
        "episode_mult": EPISODE_MULT, "held_ret7": HELD_RET7,
        "dist_ret7": DIST_RET7}}}
    _LIVE_SRC = _live_sources()
    _LIVE_DUMP: dict = {}
    for fp in sorted(archive.glob("*.json")):
        if fp.name.startswith("_"):
            continue
        coin = json.loads(fp.read_text())
        tr, oh = _series(coin, "trade"), _series(coin, "ohlcv")
        fu, oi = _series(coin, "funding"), _series(coin, "oi")
        lq = _series(coin, "liq")
        if not tr or not oh:
            continue
        # живой день поверх дневок (05.09) — только для шаблона; эпизоды
        # считаются по закрытым дневкам, как и раньше
        _live = live_day(fp.stem.upper() + "USDT", _LIVE_SRC, oh[-1]["datetime"]) if _LIVE_SRC else None
        if _live:
            # число сделок живого дня — по среднему чеку последней недели (Coinglass сделок не даёт)
            chk = [t["quote_volume"] / t["trade_count"] for t in tr[-7:] if t.get("trade_count") and t.get("quote_volume")]
            med_chk = statistics.median(chk) if chk else None
            _live["tr"]["trade_count"] = max(1, int(_live["tr"]["quote_volume"] / med_chk)) if med_chk else 1
        tr_l, oh_l = (tr + [_live["tr"]], oh + [_live["oh"]]) if _live else (tr, oh)
        fu_l, oi_l = (fu + [_live["fu"]], oi + [_live["oi"]]) if _live else (fu, oi)
        eps = episodes_of(tr, oh, fu, oi, lq)
        resolved = [e for e in eps if e["verdict"] != "рано судить"]
        dist = sum(e["verdict"] == "раздали" for e in resolved)
        part = sum(e["verdict"] == "частично отдали" for e in resolved)
        held = sum(e["verdict"] == "удержали" for e in resolved)
        # Числа обязаны сходиться (правка 31.08). Было: «всплесков
        # было 8: после 0 цену слили, 2 устояли, 3 отдали наполовину»
        # — восемь в заголовке, пять в разборе, три пропали молча.
        # Пропали неразрешённые: их не судят, но и не прятать же.
        ripe = len(eps) - len(resolved)
        line = (f"всплесков объёма было {len(eps)}, разрешились "
                f"{len(resolved)}: после {dist} цену слили, {held} устояли, "
                f"{part} отдали наполовину"
                + (f" · {ripe} ещё зреют" if ripe else "")
                if resolved else
                (f"всплесков объёма {len(eps)}, исходы ещё зреют" if eps
                 else "всплесков объёма не было"))
        _pl = plot_line(tr_l, oh_l, fu_l, oi_l, lq, sym=fp.stem.upper() + "USDT", src=_LIVE_SRC)
        if _live:
            _LIVE_DUMP[fp.stem.upper() + "USDT"] = _live
        rep[fp.stem.upper() + "USDT"] = {
            "episodes": len(eps), "resolved": len(resolved),
            "distributed": dist, "partial": part, "held": held,
            "line": line,
            "today": today_print(tr, oh, fu),
            "plot": _pl,
            # живой день (05.09): что подмешали к дневкам, чтобы было видно глазами
            "live_day": ({"date": _live["oh"]["datetime"][:10], "px": round(_live["oh"]["close"], 8),
                          "vol_pace_usd": round(_live["oh"]["quote_volume"], 0),
                          "taker": round(_live["tr"]["buy_sell_ratio"], 3) if _live["tr"]["buy_sell_ratio"] else None,
                          "delta_usd": round(_live["tr"]["quote_buy_volume"] - _live["tr"]["quote_sell_volume"], 0),
                          "oi_usd": _live["oi"]["open_interest"], "funding": _live["fu"]["funding_rate"]} if _live else None),
            # Стадия рядом с сюжетом (01.09): потребителям не нужно
            # знать список имён шаблонов, чтобы отличить «взводится»
            # от «уже идёт».
            "stage": plot_stage(_pl),
            "last_episode": eps[-1] if eps else None,
        }
    try:
        _out = archive.parent / "output" / "live_day.json"
        _out.parent.mkdir(exist_ok=True)
        _out.write_text(json.dumps({"at": datetime.now().strftime("%Y-%m-%d %H:%M"), "coins": _LIVE_DUMP},
                                   ensure_ascii=False, indent=1), encoding="utf-8")
    except OSError:
        pass
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
