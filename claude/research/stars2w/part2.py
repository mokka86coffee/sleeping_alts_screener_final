import json, os, bisect, collections
BASE="/Users/evgenijminko/Work/random/python"
out=json.load(open("stars.json"))
def load(sym):
    fn=f"{BASE}/cq_v2/intraday/{sym.lower()}.jsonl"
    rows=[]
    for l in open(fn):
        try: r=json.loads(l)
        except: continue
        if r.get("px"): rows.append(r)
    rows.sort(key=lambda r:r["candle"]); return rows
C={}
def race(o,up,dn):
    rows=C.get(o["sym"]) or C.setdefault(o["sym"],load(o["sym"]))
    ts=[r["candle"][:16] for r in rows]; i=bisect.bisect_right(ts,o["at"])-1
    px=rows[i]["px"]
    for r in rows[i+1:i+49]:
        h=r.get("h") or r["px"]; l=r.get("l") or r["px"]
        if h>=px*(1+up/100) and l<=px*(1-dn/100): return "оба"
        if h>=px*(1+up/100): return "up"
        if l<=px*(1-dn/100): return "dn"
    return "нет"
groups=collections.OrderedDict([("доска ≤ −3% (рынок падает)",lambda o:o["board"] is not None and o["board"]<=-3),
                               ("доска −3…+2%",lambda o:o["board"] is not None and -3<o["board"]<2),
                               ("доска ≥ +2% (рынок растёт)",lambda o:o["board"] is not None and o["board"]>=2)])
for name,fn in groups.items():
    g=[o for o in out if fn(o)]
    for up,dn in ((10,10),(15,10)):
        c=collections.Counter(race(o,up,dn) for o in g)
        print(f"{name}: звёзд {len(g)} | сначала +{up}%: {c['up']} | сначала −{dn}%: {c['dn']} | ни то ни то: {c['нет']} | оба в одной свече: {c['оба']}")
