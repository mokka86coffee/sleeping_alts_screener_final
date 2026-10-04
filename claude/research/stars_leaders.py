"""04.10 владелец: «посмотри только историю звёзд, которые больше 3-х раз попадали в лидеры, какие пошли, какие нет и почему».
Лидеры = список «первые» очереди в output/queue_log.jsonl (строки _BG, поле first), с 16.09. Попадание = монета появилась в первых,
а в прошлом прогоне её там не было. Цена — часовые свечи Binance (кэш в scratchpad). Мерки хода — из R34: +10 % и +40 % за 48 ч.
Запуск: .venv/bin/python claude/research/stars_leaders.py"""
import json, collections, datetime, os, statistics, sys, time
import requests
BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CACHE = "/private/tmp/claude-501/-Users-evgenijminko-Work-random-python/d82eedff-7b9d-4661-aef5-52266ba7899d/scratchpad/stars_k1h.json"
UTC = datetime.timezone.utc; TZ = datetime.timezone(datetime.timedelta(hours=3))
P = lambda s: datetime.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC).timestamp()
D = lambda t: datetime.datetime.fromtimestamp(t, TZ).strftime("%d.%m %H:%M")

def load():
    bg = []; rows = collections.defaultdict(dict)
    for l in open(os.path.join(BASE, "output/queue_log.jsonl"), encoding="utf-8"):
        try: e = json.loads(l)
        except ValueError: continue
        if e["sym"] == "_BG": bg.append(e)
        else: rows[e["at"]][e["sym"]] = e
    bg.sort(key=lambda b: b["at"])
    return bg, rows

def entries(bg):
    prev = set(); out = collections.defaultdict(list); runs = collections.Counter()
    for i, b in enumerate(bg):
        cur = set(b.get("first") or [])
        for s in cur:
            runs[s] += 1
            if s not in prev: out[s].append(i)
        prev = cur
    return out, runs

def klines(syms):
    try: c = json.load(open(CACHE))
    except (OSError, ValueError): c = {}
    for s in syms:
        if s in c: continue
        r = requests.get("https://fapi.binance.com/fapi/v1/klines", params=dict(symbol=s, interval="1h", limit=500), timeout=15)
        c[s] = [[int(k[0]) // 1000, float(k[1]), float(k[2]), float(k[3]), float(k[4])] for k in r.json()] if r.status_code == 200 else []
        time.sleep(0.25)
    json.dump(c, open(CACHE, "w"))
    return c

def after(k, t, hours):
    """ход после момента t за hours часов: (цена входа, макс. рост %, макс. просадка %, через сколько часов максимум, просадка ДО максимума %)"""
    w = [x for x in k if x[0] + 3600 > t and x[0] < t + hours * 3600]
    if len(w) < 2: return None
    p0 = w[0][4]
    w = w[1:]
    hi = max(w, key=lambda x: x[2]); lo = min(x[3] for x in w)
    lo_before = min([x[3] for x in w if x[0] <= hi[0]] or [p0])
    return p0, (hi[2] / p0 - 1) * 100, (lo / p0 - 1) * 100, (hi[0] - t) / 3600, (lo_before / p0 - 1) * 100

if __name__ == "__main__":
    bg, rows = load(); ent, runs = entries(bg)
    many = {s: ix for s, ix in ent.items() if len(ix) > 3}
    K = klines(sorted(many))
    now = time.time(); E = []
    for s, ix in many.items():
        k = K.get(s) or []
        for n, i in enumerate(ix):
            t = P(bg[i]["at"]); a = after(k, t, 48)
            if not a or now - t < 48 * 3600: full = False
            else: full = True
            if not a: continue
            E.append(dict(sym=s, n=n + 1, t=t, i=i, p0=a[0], up=a[1], dn=a[2], h_hi=a[3], dn_before=a[4], full=full, row=rows[bg[i]["at"]].get(s) or {}, bg=bg[i]))
    json.dump([{k: v for k, v in e.items() if k not in ("row", "bg")} for e in E], open(CACHE.replace("k1h", "entries"), "w"))
    print(f"монет с более чем 3 попаданиями в первые: {len(many)} · попаданий с ценой: {len(E)} · из них с полными 48 ч после: {sum(e['full'] for e in E)}")
    # по монетам
    print("\nПО МОНЕТАМ (от первого попадания до сейчас):")
    coin = []
    for s, ix in many.items():
        k = K.get(s) or []
        if not k: continue
        t0 = P(bg[ix[0]]["at"]); a = after(k, t0, 24 * 60)
        if not a: continue
        es = [e for e in E if e["sym"] == s]
        coin.append(dict(sym=s, n=len(ix), runs=runs[s], t0=t0, p0=a[0], up=a[1], dn=a[2], h_hi=a[3], dn_before=a[4], now=(k[-1][4] / a[0] - 1) * 100,
                         best48=max(e["up"] for e in es), ok10=sum(1 for e in es if e["up"] >= 10), ok40=sum(1 for e in es if e["up"] >= 40), ne=len(es)))
    coin.sort(key=lambda c: -c["up"])
    for c in coin:
        print(f"  {c['sym'][:-4]:11} попаданий {c['n']:2} (прогонов {c['runs']:3}) · первое {D(c['t0'])} · до вершины {c['up']:+6.0f}% через {c['h_hi'] / 24:4.1f} дн (до неё просадка {c['dn_before']:+5.0f}%) · сейчас {c['now']:+5.0f}% · "
              f"попаданий с +10% за 48 ч: {c['ok10']}/{c['ne']}, с +40%: {c['ok40']} · лучший ход за 48 ч {c['best48']:+.0f}%")
    json.dump(coin, open(CACHE.replace("k1h", "coins"), "w"))
