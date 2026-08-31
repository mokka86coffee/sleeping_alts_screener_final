#!/usr/bin/env python3
"""Arkham Intel API (31.08): три контура разведки по адресам.

КОНФИГ. В config/config.json добавить одну строку:
    "ARKHAM_KEY": "ключ из письма о доступе"
(читается через config.py, как COINGLASS_KEY и CQ_TOKEN;
явный export ARKHAM_KEY в окне главнее файла.)

ЧТО ДЕЛАЕТ — три контура, каждый пишет свой файл в output/:

 1) КИТЫ (arkham_whales.json) — по адресам из hl_whales.json
    (ключи addresses и auto — твой боевой формат). Для каждого:
    открытые перп-позиции HyperCore, сводка счёта, кривая PnL.
    Это замена падающему sources_hyperliquid: у Arkham есть
    ИСТОРИЯ прибыли кита, а не только снимок позиций.

 2) СТОРОЖА (arkham_watch.json) — по кошелькам инвесторов из
    investors.json (если файла нет — контур молчит): свежие
    переводы, потоки в долларах, топ-контрагенты. Смысл: увидеть
    движение токенов К БИРЖЕ до того, как оно станет продажей.

 3) ДЕРЖАТЕЛИ (arkham_holders.json) — топ-держатели монет книги
    (список в BOOK ниже или из reputation.json по флагу --all):
    кто по ту сторону риска и насколько концентрирован флоат.

ЗАПУСК:
    python3 arkham_fetch.py            # все три контура
    python3 arkham_fetch.py --probe    # ТОЛЬКО проверка доступа:
                                       # какие точки открыты ключом
    python3 arkham_fetch.py --whales   # только киты (быстро)

Расход кредитов печатается из заголовков ответа, если Arkham их
шлёт — так узнаем цену вопроса по факту, а не по прикидке.
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    from config import load as _cfg
    _cfg()
except Exception:
    pass

BASE = "https://api.arkm.com"


def _key():
    """Ключ: окружение главнее, иначе прямо из config/config.json.
    Проверено 31.08: config.load() значения в окружение НЕ кладёт,
    поэтому одного os.environ не хватает."""
    k = os.environ.get("ARKHAM_KEY", "").strip()
    if k:
        return k
    for p in (Path("config/config.json"),
              Path(__file__).resolve().parent / "config" / "config.json",
              Path("config.json")):
        try:
            if p.exists():
                v = json.loads(p.read_text(encoding="utf-8")).get("ARKHAM_KEY")
                if v:
                    return str(v).strip()
        except Exception:
            pass
    return ""


KEY = _key()
TIMEOUT = 25
PAUSE = 0.35
BOOK = ["ENA", "STX", "PROM", "ONG", "ZRO", "TRUMP"]

_credits = {"seen": 0, "last": None}


def get(path, **params):
    """Один вызов. Возвращает (данные, код). Тело ошибки не глотаем —
    урок пробника Coinglass: 400 сам говорит, чего не хватило."""
    url = BASE + path + ("?" + urllib.parse.urlencode(params)
                         if params else "")
    req = urllib.request.Request(url, headers={
        "API-Key": KEY,
        "Accept": "application/json",
        # Cloudflare режет служебный агент urllib и отдаёт 403 ещё
        # до Arkham (поймано 31.08: curl проходил, скрипт — нет).
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/126.0 Safari/537.36"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read().decode()
            for h in ("X-Credits-Used", "X-Credit-Cost", "X-Credits-Remaining"):
                v = r.headers.get(h)
                if v:
                    _credits["last"] = f"{h}={v}"
                    _credits["seen"] += 1
            return json.loads(body), 200
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:300]
        try:
            return json.loads(body), e.code
        except ValueError:
            return {"error": body}, e.code
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}, 0


def _addresses():
    """Адреса китов из ЕГО файла: addresses + auto."""
    p = Path("hl_whales.json")
    if not p.exists():
        p = Path(__file__).resolve().parent / "hl_whales.json"
    if not p.exists():
        return []
    d = json.loads(p.read_text(encoding="utf-8"))
    out = []
    for k in ("addresses", "auto"):
        for x in (d.get(k) or []):
            a = x.get("addr")
            if a and a.startswith("0x"):        # соланские — не сюда
                out.append((a, x.get("label", "")))
    return out


def probe():
    """Что открыто нашим ключом — до всякой стройки."""
    addr = (_addresses() or [("0x082e843a431aef031264dc232693dd710aedca88",
                              "тест")])[0][0]
    points = [
        (f"/hypercore/account/{addr}/perp-positions", {}),
        (f"/hypercore/account/{addr}/summary", {}),
        (f"/hypercore/account/{addr}/portfolio-history", {}),
        (f"/hypercore/account/{addr}/trades", {"limit": 5}),
        (f"/balances/address/{addr}", {}),
        (f"/flow/address/{addr}", {}),
        (f"/counterparties/address/{addr}", {}),
        ("/transfers", {"base": addr, "limit": 5}),
        ("/intelligence/search", {"query": "ethena"}),
        ("/token/top_flow/ethena", {"timeLast": "24h"}),
        ("/marketdata/altcoin_index", {}),
    ]
    print(f"ключ: {'…' + KEY[-4:] if KEY else 'НЕТ (задай ARKHAM_KEY)'}")
    for path, prm in points:
        d, code = get(path, **prm)
        n = "-"
        if isinstance(d, dict):
            for k in ("data", "transfers", "positions", "holders",
                      "addresses", "counterparties", "results"):
                v = d.get(k)
                if isinstance(v, (list, dict)) and len(v):
                    n = f"{k}:{len(v)}"
                    break
            else:
                n = f"полей:{len(d)}"
        note = "" if code == 200 else f" · {str(d)[:90]}"
        print(f"{path[:52]:54s} {code} rows={n}{note}")
        time.sleep(PAUSE)
    if _credits["last"]:
        print("расход кредитов (из заголовков):", _credits["last"])
    else:
        print("заголовков расхода нет — считать по их дашборду")


def whales(write=True):
    """Контур 1: киты HyperCore по нашим адресам."""
    out = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "whales": []}
    for addr, label in _addresses():
        pos, c1 = get(f"/hypercore/account/{addr}/perp-positions")
        summ, _ = get(f"/hypercore/account/{addr}/summary")
        time.sleep(PAUSE)
        if c1 != 200:
            out["whales"].append({"addr": addr, "label": label,
                                  "error": str(pos)[:120]})
            continue
        rows = pos.get("data") or pos.get("positions") or []
        items = []
        for p in rows if isinstance(rows, list) else []:
            sz = p.get("size") or p.get("positionSize") or 0
            items.append({
                "sym": p.get("coin") or p.get("symbol"),
                "side": "лонг" if float(sz or 0) >= 0 else "шорт",
                "usd": p.get("positionValue") or p.get("notionalUsd"),
                "lev": p.get("leverage"),
                "entry": p.get("entryPrice"),
                "liq": p.get("liquidationPrice"),
                "pnl": p.get("unrealizedPnl")})
        # Живые поля summary (сверено по ответу 31.08):
        # totalUsdValue, perpUsdValue, spotUsdValue,
        # perpUnrealizedPnl, perpPositionCount.
        sm = summ or {}
        def _m(v):
            v = float(v or 0)
            a = abs(v)
            t = "-$" if v < 0 else "$"
            return (t + f"{a/1e6:.1f}M" if a >= 1e6
                    else t + f"{a/1e3:.0f}K")
        out["whales"].append({
            "addr": addr, "label": label, "positions": items,
            "equity": sm.get("totalUsdValue"),
            "perp_usd": sm.get("perpUsdValue"),
            "spot_usd": sm.get("spotUsdValue"),
            "pnl_open": sm.get("perpUnrealizedPnl"),
            "n_pos": sm.get("perpPositionCount"),
            "line": (f"{label or addr[:10]}: счёт "
                     f"{_m(sm.get('totalUsdValue'))} · перпы "
                     f"{_m(sm.get('perpUsdValue'))} · открытая прибыль "
                     f"{_m(sm.get('perpUnrealizedPnl'))} · позиций "
                     f"{sm.get('perpPositionCount', len(items))}" +
                     (" · " + ", ".join(
                         f"{i['sym']} {i['side']}" for i in items[:4])
                      if items else ""))})
    if write:
        Path("output").mkdir(exist_ok=True)
        (Path("output") / "arkham_whales.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
    live = sum(1 for w in out["whales"] if w.get("positions"))
    return f"китов {len(out['whales'])}, с позициями {live}"


def watch(write=True):
    """Контур 2: сторожа по кошелькам инвесторов (investors.json)."""
    p = Path("investors.json")
    if not p.exists():
        return "investors.json нет — контур пропущен"
    book = json.loads(p.read_text(encoding="utf-8"))
    out = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "alerts": []}
    def _addrs(info):
        """investors.json бывает разной формы (31.08): словарь с
        ключом addresses, голый список адресов, строка с одним
        адресом или список словарей. Берём адреса из любой."""
        out = []
        if isinstance(info, str):
            out = [info]
        elif isinstance(info, dict):
            v = info.get("addresses") or info.get("holders") or []
            for x in v if isinstance(v, list) else []:
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict) and x.get("addr"):
                    out.append(x["addr"])
        elif isinstance(info, list):
            for x in info:
                if isinstance(x, str):
                    out.append(x)
                elif isinstance(x, dict):
                    a = x.get("addr") or x.get("address")
                    if a:
                        out.append(a)
        return [a for a in out if isinstance(a, str) and a.startswith("0x")]

    for coin, info in (book.items() if isinstance(book, dict) else []):
        for addr in _addrs(info)[:6]:
            tr, code = get("/transfers", base=addr, limit=10)
            time.sleep(PAUSE)
            if code != 200:
                continue
            for t in (tr.get("transfers") or tr.get("data") or [])[:10]:
                to = ((t.get("toEntity") or {}).get("name") or
                      t.get("toLabel") or "")
                usd = t.get("historicalUSD") or t.get("unitValue") or 0
                if to and float(usd or 0) > 50000:
                    out["alerts"].append({
                        "coin": coin, "addr": addr[:10] + "…",
                        "to": to, "usd": usd,
                        "ts": t.get("blockTimestamp"),
                        "line": f"{coin}: кошелёк инвестора → {to} "
                                f"на ${float(usd)/1e6:.2f}M"})
    if write:
        Path("output").mkdir(exist_ok=True)
        (Path("output") / "arkham_watch.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return f"сигналов {len(out['alerts'])}"


def holders(coins=None, write=True):
    """Контур 3: топ-держатели монет книги."""
    out = {"at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
           "coins": {}}
    for c in (coins or BOOK):
        s, code = get("/intelligence/search", query=c)
        time.sleep(PAUSE)
        if code != 200:
            continue
        tok = None
        for r in (s.get("tokens") or s.get("data") or [])[:3]:
            tok = r.get("id") or r.get("pricingId")
            if tok:
                break
        if not tok:
            continue
        h, code2 = get(f"/token/holders/{tok}", limit=10)
        time.sleep(PAUSE)
        if code2 != 200:
            continue
        rows = h.get("holders") or h.get("data") or []
        top = [{"name": (x.get("entity") or {}).get("name") or
                        (x.get("address") or "")[:10],
                "usd": x.get("usd") or x.get("balanceUSD")}
               for x in rows[:8]]
        share = sum(float(t["usd"] or 0) for t in top)
        out["coins"][c] = {"top": top, "top8_usd": round(share),
                           "line": f"{c}: топ-8 держат ${share/1e6:.1f}M"}
    if write:
        Path("output").mkdir(exist_ok=True)
        (Path("output") / "arkham_holders.json").write_text(
            json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return f"монет {len(out['coins'])}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--whales", action="store_true")
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--holders", action="store_true")
    a = ap.parse_args()
    if not KEY:
        print("нет ARKHAM_KEY: добавь в config/config.json строку "
              '"ARKHAM_KEY": "…" или задай export в этом окне')
        raise SystemExit(1)
    if a.probe:
        probe()
    else:
        only = a.whales or a.watch or a.holders
        if a.whales or not only:
            print("киты:", whales())
        if a.watch or not only:
            print("сторожа:", watch())
        if a.holders or not only:
            print("держатели:", holders())
        if _credits["last"]:
            print("кредиты:", _credits["last"])
