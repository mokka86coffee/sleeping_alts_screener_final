#!/usr/bin/env python3
"""Дозабор пропущенных свечей после простоя (05.09, владелец: «5–8 часов прогона
нет — берём и записываем всё, что можем, за пропущенное время»).

Что восстанавливается ИЗ ИСТОРИИ по каждой пропущенной получасовке (со штампом свечи
и пометкой backfill=true):
  · лог ликвидности (output/liq_log.jsonl) — карты «на момент»: часовые свечи и интерес
    Binance режутся по свече, дневки cq_v2 — до её даты;
  · журнал прогнозов (output/forecasts.jsonl) — шаблоны reputation_cq «на момент»:
    живой день из баров Coinglass ≤ свечи, цена дня — из 30-минутных свечей Binance.
Что НЕ восстанавливается (снимки, которых не было): пульс, своя премия Coinbase, киты —
для них остаётся отрезок в output/gaps.jsonl; читающие обязаны его видеть.

    python3 backfill_gaps.py --from 2026-09-05T08:00Z --to 2026-09-05T15:30Z --only BLESS   # одна монета, проверка
    python3 backfill_gaps.py                                                              # последний отрезок из gaps.jsonl, все монеты
    python3 backfill_gaps.py --dry                                                        # только показать свечи и монеты

Свеча уже есть в файле (штамп совпал) — пропуск, дважды не пишет.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from core_config import BASE_DIR
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

INTERVAL_MS = 30 * 60 * 1000


def _parse(ts: str) -> int:
    t = ts.strip().replace("Z", "+00:00")
    if len(t) == 10:
        t += "T00:00:00+00:00"
    if "T" in t and "+" not in t and "-" not in t[11:]:
        t += "+00:00"
    d = datetime.fromisoformat(t)
    return int((d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp() * 1000)


def candles(from_ms: int, to_ms: int) -> list[int]:
    """Начала закрытых получасовок в [from, to): свеча t закрыта, если t + 30м ≤ to."""
    a = (from_ms // INTERVAL_MS) * INTERVAL_MS
    out = []
    while a + INTERVAL_MS <= to_ms:
        out.append(a)
        a += INTERVAL_MS
    return out


def last_gap() -> tuple[int, int] | None:
    p = BASE_DIR / "output" / "gaps.jsonl"
    if not p.exists():
        return None
    last = None
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            last = json.loads(line)
        except ValueError:
            pass
    if not last or not last.get("from") or not last.get("to"):
        return None
    return _parse(last["from"]), _parse(last["to"])


def have_candles(path: Path, key: str = "candle") -> set[str]:
    """Штампы свечей, уже записанных в jsonl (чтобы не дублировать)."""
    out = set()
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if r.get(key):
            out.add((str(r.get("sym") or "").upper(), r[key]))
    return out


def stamp_of(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:00Z", time.gmtime(ms / 1000))


def px_at(sym_usdt: str, ms: int) -> dict | None:
    """Цена дня «на момент» из 30-минутных свечей Binance: open дня, high/low до свечи, close свечи."""
    try:
        from core_binance import get_klines
        kl = get_klines(sym_usdt, "30m", 500)
    except Exception:  # noqa: BLE001
        return None
    day0 = int(datetime.fromtimestamp(ms / 1000, timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000)
    rows = [k for k in kl if day0 <= int(k[0]) <= ms and int(k[6]) <= ms + INTERVAL_MS]
    if not rows:
        return None
    return {"open": float(rows[0][1]), "high": max(float(k[2]) for k in rows),
            "low": min(float(k[3]) for k in rows), "close": float(rows[-1][4])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="frm")
    ap.add_argument("--to", dest="to")
    ap.add_argument("--only", help="монеты через запятую (базы: BLESS,4)")
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--skip-liq", action="store_true", help="без лога ликвидности")
    ap.add_argument("--skip-forecasts", action="store_true", help="без журнала прогнозов")
    a = ap.parse_args()

    if a.frm and a.to:
        frm, to = _parse(a.frm), _parse(a.to)
    else:
        g = last_gap()
        if not g:
            print("нет отрезка: укажи --from/--to или дождись записи в output/gaps.jsonl")
            return 1
        frm, to = g
    cs = candles(frm, to)
    archive = BASE_DIR / "cq_v2"
    coins = ([c.strip().upper() for c in a.only.split(",")] if a.only else
             sorted(p.stem.upper() for p in archive.glob("*.json") if not p.name.startswith("_")))
    print(f"дозабор: свечей {len(cs)} ({stamp_of(cs[0]) if cs else '—'} … {stamp_of(cs[-1]) if cs else '—'}) · монет {len(coins)}")
    if a.dry or not cs:
        return 0

    out_dir = BASE_DIR / "output"
    liq_path, fc_path = out_dir / "liq_log.jsonl", out_dir / "forecasts.jsonl"
    have_liq = have_candles(liq_path)
    have_fc = set()
    if fc_path.exists():
        for line in fc_path.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
                have_fc.add((str(r.get("sym") or "").upper(), f"{r.get('at')}T{r.get('hm')}"))
            except ValueError:
                pass

    n_liq = n_fc = 0
    t0 = time.time()
    for i, ms in enumerate(cs, 1):
        st = stamp_of(ms)
        as_of = datetime.fromtimestamp((ms + INTERVAL_MS) / 1000, timezone.utc)   # момент — закрытие свечи
        # ── лог ликвидности «на момент» ──
        if not a.skip_liq:
            import liq_log
            liq_log.AS_OF_MS = ms + INTERVAL_MS          # момент — закрытие свечи
            rows = []
            for sym in coins:
                if (sym, st) in have_liq:
                    continue
                try:
                    row = liq_log.build(sym, BASE_DIR, None, {})
                    row["candle"] = st
                    rows.append(row)
                except Exception as e:  # noqa: BLE001
                    rows.append({"sym": sym, "candle": st, "backfill": True, "error": f"{type(e).__name__}: {e}"})
            if rows:
                with liq_path.open("a", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")
                n_liq += len(rows)
        # ── журнал прогнозов «на момент» ──
        if not a.skip_forecasts:
            import reputation_cq as rc
            rc.AS_OF = as_of
            rc.AS_OF_PX = {}
            for sym in coins:
                q = px_at(sym + "USDT", ms)
                if q:
                    rc.AS_OF_PX[sym + "USDT"] = q
            try:
                rep = rc.build(archive)
            except Exception as e:  # noqa: BLE001
                print(f"  {st}: репутация не собралась: {type(e).__name__}: {e}")
                rep = {}
            at, hm = as_of.strftime("%Y-%m-%d"), as_of.strftime("%H:%M")
            lines = []
            for sym in coins:
                r = rep.get(sym + "USDT") or {}
                if not r.get("plot") or (sym + "USDT", f"{at}T{hm}") in have_fc:
                    continue
                q = rc.AS_OF_PX.get(sym + "USDT") or {}
                lines.append(json.dumps({"at": at, "hm": hm, "sym": sym + "USDT", "tpl": r["plot"],
                                         "stage": r.get("stage") or "", "px": q.get("close"),
                                         "candle": st, "backfill": True}, ensure_ascii=False))
            if lines:
                with fc_path.open("a", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")
                n_fc += len(lines)
        # внутридневной архив на эту свечу — из только что записанных строк лога и репутации «на момент»
        try:
            import intraday_archive as ia
            n_ia = ia.write_rows(ia.build_rows(ms, coins))
        except Exception as e:  # noqa: BLE001
            n_ia = 0
            print(f"  {st}: внутридневной архив не записан: {type(e).__name__}: {e}")
        print(f"  [{i}/{len(cs)}] {st} · лог +{n_liq} · журнал +{n_fc} · архив +{n_ia} · {time.time() - t0:.0f} с", flush=True)
    print(f"готово: лог ликвидности +{n_liq} строк, журнал прогнозов +{n_fc} строк; пульс/премия/киты — не восстанавливаются, отрезок остаётся в gaps.jsonl")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
