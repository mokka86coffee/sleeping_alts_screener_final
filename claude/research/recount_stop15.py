#!/usr/bin/env python3
"""ПЕРЕСЧЁТ ШОРТОВ СО СТОПОМ 15 % (13.10 UTC, владелец: «поставь у шортов стоп 15% вместо 10», «и пересчитай все сделки за последние 5 дней»).

Берёт бумажные сделки бота за DAYS суток (журналы output/paper_*.jsonl). Шорт, закрытый стопом 10 %, «доигрывается» по нашим получасовкам
(cq_v2/intraday и архив) от свечи стопа до своего срока с прежними правилами выхода и новым стопом:
  • максимум свечи дошёл до входа + NEW_SL — стоп (−15 %);
  • у шорта с целью минимум дошёл до входа − цель — цель;
  • минимум дошёл до входа − 5 % — стоп переносится в точку входа, дальше возврат к входу закрывает в ноль;
  • на шестом часу от входа: цена выше входа — закрытие по рынку (R66; у «конца пампа» — то же по его правилу), ниже — стоп в точку входа;
  • срок вышел (из правила сделки: «срок N мин», «выход ДД.ММ ЧЧ:ММ UTC», у «конца пампа» 72 ч; иначе потолок 16 ч) — закрытие по цене свечи.
В одной свече стоп проверяется раньше цели. Это счёт по получасовым свечам, а не по трёхминутным, как у бота, — выход может отличаться на свечу.
Монета без получасовок не пересчитывается. Остальные сделки (не дошедшие до стопа 10 %) новый стоп не меняет.

Пишет output/recount_stop15.json: adjust — {«книга|монета|секунда входа»: {res, usd, exit, t_out, why}}; страница бота (fast_state.positions) при
MANUAL_BY_USER_SITE_NEW_RULES показывает эти сделки с пересчитанным итогом и пометкой «пересчёт» в причине выхода. Журналы не меняются.

    .venv/bin/python claude/research/recount_stop15.py [--dry]
"""
from __future__ import annotations

import collections
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import pump_pot as pp  # noqa: E402

U = timezone.utc
OUT = ROOT / "output" / "recount_stop15.json"
DAYS, OLD_SL, NEW_SL, BE_AT = 5, 0.10, 0.15, 0.05
BOOKS = (("всплеск/вынос", "paper_fast3"), ("пробуждение", "paper_wake"))


def bingx_bars(sym: str, t_from: float) -> list:
    """получасовые свечи открытых данных BingX (без ключей) для монеты, которой нет в наших получасовках: [(начало unix, закрытие, максимум, минимум)]"""
    import urllib.request
    url = f"https://open-api.bingx.com/openApi/swap/v3/quote/klines?symbol={sym[:-4]}-USDT&interval=30m&startTime={int(t_from * 1000)}&limit=1000"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20) as r:
            d = json.loads(r.read().decode("utf-8")).get("data") or []
    except Exception as e:  # noqa: BLE001
        print(f"   BingX {sym}: {type(e).__name__}: {e}"); return []
    out = [(int(k["time"]) / 1000, float(k["close"]), float(k["high"]), float(k["low"])) for k in d if k.get("time")]
    return sorted(out)


def main() -> int:
    now = datetime.now(U); t0 = (now - timedelta(days=DAYS)).timestamp()
    tr: dict = {}
    for book, stem in BOOKS:
        for ln in (ROOT / "output" / f"{stem}.jsonl").open(encoding="utf-8"):
            if '"exit_' not in ln:
                continue
            r = json.loads(ln)
            if float(r.get("opened_at") or 0) < t0:
                continue
            k = f"{book}|{r['sym']}|{int(float(r['opened_at']))}"
            t = tr.setdefault(k, dict(key=k, book=book, sym=r["sym"], side=int(r["side"]), t=float(r["opened_at"]), t_out=float(r["at"]), e=float(r["px_in"]), usd=0.0,
                                      pct=float(r.get("result_pct") or 0), rule=r.get("rule") or "", why=r.get("why_exit") or ""))
            t["usd"] += float(r.get("usd") or 0); t["t_out"] = max(t["t_out"], float(r["at"])); t["why"] = r.get("why_exit") or t["why"]; t["pct"] = float(r.get("result_pct") or t["pct"])
    T = sorted(tr.values(), key=lambda x: x["t"])
    R = pp.hist_rows((now - timedelta(days=DAYS + 1)).strftime(pp.FMT), now.strftime(pp.FMT))
    adjust = {}; nodata = []; rows_out = []; byx = []
    for x in T:
        if x["side"] != -1 or x["why"] != "стоп" or not (-OLD_SL * 100 - 0.6 <= x["pct"] <= -OLD_SL * 100 + 0.6):
            continue
        size = abs(x["usd"] / x["pct"] * 100)
        bars = [(pp._t(r[0]).timestamp(), r[1], r[2], r[3]) for r in R.get(x["sym"][:-4], [])]
        src = "наши получасовки"
        if not bars:
            bars = bingx_bars(x["sym"], x["t"] - 3600); src = "свечи BingX"
        bars = [b for b in bars if b[0] + 1800 > x["t_out"]]             # со свечи, в которой сработал стоп 10 %
        if not bars:
            nodata.append(x["sym"][:-4]); continue
        if src != "наши получасовки":
            byx.append(x["sym"][:-4])
        pe = x["rule"].startswith("R58 конец роста")
        m = re.search(r"выход (\d\d)\.(\d\d) (\d\d):(\d\d) UTC", x["rule"]); m2 = re.search(r"срок (\d+) мин", x["rule"])
        if pe:
            end = x["t"] + 72 * 3600
        elif m:
            end = datetime(now.year, int(m.group(2)), int(m.group(1)), int(m.group(3)), int(m.group(4)), tzinfo=U).timestamp()
        else:
            end = x["t"] + (int(m2.group(1)) if m2 else 960) * 60
        end = min(max(end, x["t"]), x["t"] + (72 if pe else 16) * 3600)
        tgt = None if (pe or "цели нет" in x["rule"] or "без цели" in x["rule"]) else 0.10
        e = x["e"]; be = False; res = None; why = ""; t_exit = None; px_exit = None; six = x["t"] + 6 * 3600; six_done = False
        for ts, c, h, lo in bars:
            te = ts + 1800
            if h >= (e if be else e * (1 + NEW_SL)):
                res, why = (0.0, "стоп в точке входа") if be else (-NEW_SL, "стоп 15 %"); px_exit = e if be else e * (1 + NEW_SL); t_exit = te; break
            if tgt and lo <= e * (1 - tgt):
                res, why, px_exit, t_exit = tgt, "цель", e * (1 - tgt), te; break
            if not be and lo <= e * (1 - BE_AT):
                be = True
            if not six_done and te >= six:
                six_done = True
                if c > e and not be:
                    res, why, px_exit, t_exit = 1 - c / e, "на шестом часу цена выше входа — закрытие", c, te; break
                be = True
            if te >= end:
                res, why, px_exit, t_exit = 1 - c / e, "срок", c, te; break
        if res is None:                                                    # срок ещё не вышел — по последней цене, сделка считалась бы открытой
            ts, c, h, lo = bars[-1]; res, why, px_exit, t_exit = 1 - c / e, "ещё открыта бы — по последней цене", c, ts + 1800
        usd = res * size
        rows_out.append((x, res * 100, usd, why))
        adjust[x["key"]] = dict(res=round(res * 100, 2), usd=round(usd, 2), exit=px_exit, t_out=t_exit, why=f"пересчёт со стопом 15 %: {why} (по журналу — стоп 10 %, {x['usd']:+.0f} $)")

    def agg(L: list) -> str:
        return f"{len(L)} сделок, в плюс {sum(v['usd'] > 0 for v in L)}, {sum(v['usd'] for v in L):+.0f} $"
    sh = [x for x in T if x["side"] == -1]
    print(f"сделок за {DAYS} суток: {agg(T)} | лонги {agg([x for x in T if x['side'] == 1])} | шорты {agg(sh)}")
    print(f"шортов, закрытых стопом 10 %: {len(rows_out) + len(nodata)}; пересчитано {len(rows_out)} (из них по свечам BingX: {' '.join(byx) or 'нет'}), без данных {len(nodata)} ({' '.join(nodata)})")
    was = sum(x["usd"] for x, *_ in rows_out); new = sum(u for _, _, u, _ in rows_out)
    print(f"по ним было {was:+.0f} $ → со стопом 15 % {new:+.0f} $ (разница {new - was:+.0f} $)")
    for k, n in collections.Counter(w for *_, w in rows_out).most_common():
        L = [(x, p, u) for x, p, u, w in rows_out if w == k]; print(f"   {k}: {len(L)}, итог {sum(u for _, _, u in L):+.0f} $ (было {sum(x['usd'] for x, _, _ in L):+.0f} $)")
    for x, p, u, w in rows_out:
        print(f"   {datetime.fromtimestamp(x['t'], U):%d.%m %H:%M} {x['sym'][:-4]:9s} было {x['usd']:+5.0f} $ → {p:+5.1f}% {u:+5.0f} $ · {w} · {x['rule'].split(' · ')[0][:42]}")
    print(f"шорты за {DAYS} суток: было {sum(x['usd'] for x in sh):+.0f} $ → стало бы {sum(x['usd'] for x in sh) - was + new:+.0f} $; все сделки: {sum(x['usd'] for x in T):+.0f} → {sum(x['usd'] for x in T) - was + new:+.0f} $")
    days = collections.defaultdict(lambda: [0.0, 0.0])
    adj = {x["key"]: u for x, _, u, _ in rows_out}
    for x in T:
        d = datetime.fromtimestamp(x["t"], U).strftime("%d.%m"); days[d][0] += x["usd"]; days[d][1] += adj.get(x["key"], x["usd"])
    print("по дням входа (UTC), было → стало:", " · ".join(f"{d} {a:+.0f}→{b:+.0f}" for d, (a, b) in sorted(days.items(), key=lambda kv: (kv[0][3:], kv[0][:2]))))
    if "--dry" not in sys.argv:
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(at=now.strftime(pp.FMT), days=DAYS, new_sl=NEW_SL, adjust=adjust), ensure_ascii=False), encoding="utf-8"); tmp.replace(OUT)
        print("записано:", OUT, len(adjust))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
