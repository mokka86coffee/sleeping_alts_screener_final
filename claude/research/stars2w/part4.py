import json, os, collections, datetime as dt, statistics as st
BASE="/Users/evgenijminko/Work/random/python"
movers=json.load(open("movers.json"))
def iso(t): return dt.datetime.fromtimestamp(float(t),dt.UTC).strftime("%Y-%m-%dT%H:%M")
# сделки бота
ent=collections.defaultdict(list)
for f in ("paper_fast3.jsonl","paper_wake.jsonl","paper_queue.jsonl"):
    opened={}
    for l in open(f"{BASE}/output/{f}"):
        try: r=json.loads(l)
        except: continue
        k=r.get("kind"); s=(r.get("sym") or "")[:-4]
        if k=="entry": opened[(s,r.get("side"))]=dict(book=r.get("book"),side=r.get("side"),t_in=iso(r["at"]),px_in=r.get("px"))
        elif k in ("exit_long","exit_short","exit"):
            side=1 if k=="exit_long" else (-1 if k=="exit_short" else r.get("side"))
            e=opened.pop((s,side),None)
            if e: e["t_out"]=iso(r.get("at") or r.get("t") or 0); e["res"]=r.get("res"); ent[s].append(e)
    for (s,side),e in opened.items(): e["t_out"]=None; ent[s].append(e)
# очередь: лучшее место монеты в окне хода
import bisect
Q=f"{BASE}/output/queue_log.jsonl"; size=os.path.getsize(Q); fh=open(Q,"rb")
lo,hi=0,size
while hi-lo>500_000:
    mid=(lo+hi)//2; fh.seek(mid); fh.readline(); a=json.loads(fh.readline()).get("at","")
    if a<"2026-10-07T00": lo=mid
    else: hi=mid
fh.seek(lo); fh.readline()
qp=collections.defaultdict(list)
for l in fh:
    try: r=json.loads(l)
    except: continue
    s=(r.get("sym") or "")
    if s.endswith("USDT"): qp[s[:-4]].append(((r.get("at") or "")[:16], r.get("place"), r.get("in_queue")))
res=collections.Counter(); rows=[]
for m in movers:
    s=m["sym"]; a=m["lo_t"]; b=m["pk_t"]
    pre=(dt.datetime.fromisoformat(a)-dt.timedelta(hours=6)).isoformat()[:16]
    tr=[e for e in ent.get(s,[]) if pre<=e["t_in"]<=b]
    pl=[p for (t,p,iq) in qp.get(s,[]) if pre<=t<=b and isinstance(p,int)]
    seen=sum(1 for (t,p,iq) in qp.get(s,[]) if pre<=t<=b)
    best=min(pl) if pl else None
    longs=[e for e in tr if e["side"]==1]; shorts=[e for e in tr if e["side"]==-1]
    if longs: res["бот брал лонг"]+=1
    elif shorts: res["бот брал только шорт"]+=1
    else: res["бот не брал"]+=1
    if m["star"]: res["звезда"]+=1
    elif best is not None: res[f"в очереди, лучшее место ≤3"]+= best<=3; res["в очереди, но ниже тройки"]+= best>3
    elif seen: res["в выборке, но не в очереди"]+=1
    else: res["не было в выборке прогона"]+=1
    hold=[ (dt.datetime.fromisoformat(e["t_out"])-dt.datetime.fromisoformat(e["t_in"])).total_seconds()/3600 for e in longs if e.get("t_out")]
    rows.append((m, longs, shorts, best, seen, hold))
for k,v in res.items(): print(k, v)
lh=[h for r in rows for h in r[5]]
if lh: print("лонги бота на этих ходах: сколько держал, медиана", round(st.median(lh),1), "ч; сделок", len(lh))
print()
for m,longs,shorts,best,seen,hold in rows[-40:]:
    t=" ".join(f"{'Л' if e['side']==1 else 'Ш'} {e['t_in'][5:].replace('T',' ')}→{(e['t_out'] or '—')[11:]} {e.get('res')}" for e in (longs+shorts)[:3])
    print(m["lo_t"][5:].replace("T"," "), m["sym"], f"+{m['move']}%", "звезда" if m["star"] else (f"очередь #{best}" if best else ("выборка без очереди" if seen else "нет в выборке")), "|", t or "бот не брал")
