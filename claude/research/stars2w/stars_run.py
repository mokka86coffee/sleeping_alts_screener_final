import json, os, glob, bisect, collections, datetime as dt
BASE="/Users/evgenijminko/Work/random/python"
START="2026-10-07T15:00"
Q=f"{BASE}/output/queue_log.jsonl"
size=os.path.getsize(Q); f=open(Q,"rb")
lo,hi=0,size
while hi-lo>500_000:
    mid=(lo+hi)//2; f.seek(mid); f.readline(); a=json.loads(f.readline()).get("at","")
    if a<START: lo=mid
    else: hi=mid
f.seek(lo); f.readline()
runs=collections.OrderedDict(); bg={}
for l in f:
    try: r=json.loads(l)
    except: continue
    a=(r.get("at") or "")[:16]
    if a<START: continue
    if r.get("sym")=="_BG":
        bg[a]=r; runs.setdefault(a,{}); continue
    p=r.get("place")
    runs.setdefault(a,{})
    if isinstance(p,int): runs[a][r["sym"]]=p
keys=list(runs.keys())
print("прогонов:",len(keys), keys[0], keys[-1])
# звёзды
top=collections.Counter(); one=collections.Counter(); active=set(); ev=[]
for a in keys:
    d=runs[a]
    for s in list(top):
        if s not in d or d[s]>3: top[s]=0; one[s]=0; active.discard(s)
    for s,p in d.items():
        if p<=3: top[s]+=1
        one[s]= one[s]+1 if p==1 else 0
        if s not in active and (top[s]>=3 or one[s]>=2):
            active.add(s); ev.append((a,s,"1" if one[s]>=2 else "★"))
print("звёзд:",len(ev))
# intraday
def load(sym):
    fn=f"{BASE}/cq_v2/intraday/{sym[:-4].lower()}.jsonl"
    if not os.path.exists(fn): return None
    rows=[]
    for l in open(fn):
        try: r=json.loads(l)
        except: continue
        if r.get("px"): rows.append(r)
    rows.sort(key=lambda r:r["candle"]); return rows
cache={}
def at_idx(rows,t):
    ts=[r["candle"][:16] for r in rows]; i=bisect.bisect_right(ts,t)-1; return i
out=[]
for a,s,m in ev:
    rows=cache.get(s) or cache.setdefault(s,load(s))
    if not rows: continue
    i=at_idx(rows,a)
    if i<12: continue
    px=rows[i]["px"]; nxt=rows[i+1:i+49]
    if len(nxt)<10: continue
    hi=max((r.get("h") or r["px"]) for r in nxt); low=min((r.get("l") or r["px"]) for r in nxt)
    up=(hi/px-1)*100; dn=(low/px-1)*100
    # что раньше: +15 или -10
    first=None
    for r in nxt:
        if (r.get("h") or r["px"])>=px*1.15: first="up"; break
        if (r.get("l") or r["px"])<=px*0.90: first="dn"; break
    prev=rows[i-12]
    def coins(r): return (r.get("oi") or 0)/(r.get("px") or 1)
    oi6=(coins(rows[i])/coins(prev)-1)*100 if coins(prev) else None
    px6=(px/prev["px"]-1)*100
    fund=next((r.get("funding") for r in rows[i::-1][:6] if r.get("funding") is not None),None)
    b=bg.get(a) or {}
    out.append(dict(at=a,sym=s[:-4],m=m,px=px,up=round(up,1),dn=round(dn,1),first=first,oi6=None if oi6 is None else round(oi6,1),px6=round(px6,1),fund=fund,board=b.get("board_med_24h"),btc=b.get("btc_24h"),up_pct=b.get("board_up_pct")))
json.dump(out,open("stars.json","w"),ensure_ascii=False,indent=0)
went=[o for o in out if o["first"]=="up"]; fail=[o for o in out if o["first"]!="up"]
print("с ценой:",len(out),"пошло (+15% раньше −10%):",len(went),"не пошло:",len(fail))
import statistics as st
def med(xs): xs=[x for x in xs if x is not None]; return round(st.median(xs),3) if xs else None
for name,g in (("ПОШЛО",went),("НЕ ПОШЛО",fail)):
    print(f"{name}: n={len(g)} | доска 24ч мед {med([o['board'] for o in g])} | BTC 24ч мед {med([o['btc'] for o in g])} | фандинг<0: {sum(1 for o in g if (o['fund'] or 0)<0)}/{len(g)} | интерес в монетах 6ч мед {med([o['oi6'] for o in g])}% | цена 6ч до звезды мед {med([o['px6'] for o in g])}%")
for o in sorted(out,key=lambda o:o["at"]): print(o["at"][5:].replace("T"," "),o["sym"],o["m"],"вверх",o["up"],"вниз",o["dn"],o["first"],"| доска",o["board"],"btc",o["btc"],"фанд",o["fund"],"OI6",o["oi6"],"px6",o["px6"])
