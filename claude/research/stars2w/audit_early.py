import json, os, glob, bisect, collections, math
BASE="/Users/evgenijminko/Work/random/python"
START="2026-10-07T15"; END="2026-10-20T15"   # исход нужен за 24 ч вперёд
# цены
PX={}
for fn in glob.glob(f"{BASE}/cq_v2/intraday/*.jsonl"):
    s=os.path.basename(fn)[:-6].upper()+"USDT"; rows=[]
    for l in open(fn):
        try: r=json.loads(l)
        except: continue
        if r.get("px") and r["candle"]>="2026-10-07": rows.append((r["candle"][:16], r["px"], r.get("h") or r["px"], r.get("l") or r["px"]))
    rows.sort(); PX[s]=rows
def outcome(s,t):
    rows=PX.get(s)
    if not rows: return None
    ts=[r[0] for r in rows]; i=bisect.bisect_right(ts,t)-1
    if i<0 or i+10>=len(rows): return None
    px=rows[i][1]
    for c,p,h,l in rows[i+1:i+49]:
        if h>=px*1.15: return 1
        if l<=px*0.90: return 0
    return 0
Q=f"{BASE}/output/queue_log.jsonl"; size=os.path.getsize(Q); fh=open(Q,"rb")
lo,hi=0,size
while hi-lo>500_000:
    mid=(lo+hi)//2; fh.seek(mid); fh.readline(); a=json.loads(fh.readline()).get("at","")
    if a<START: lo=mid
    else: hi=mid
fh.seek(lo); fh.readline()
stats=collections.defaultdict(lambda: collections.defaultdict(lambda:[0,0]))   # feat -> bucket -> [n, hit]
base=[0,0]; seen=set()
num_vals=collections.defaultdict(list)
recs=[]
for l in fh:
    try: r=json.loads(l)
    except: continue
    a=(r.get("at") or "")[:16]
    if a<START: continue
    if a>END: break
    s=r.get("sym") or ""
    if not s.endswith("USDT"): continue
    key=(s,a[:13])          # одна запись на монету в час
    if key in seen: continue
    seen.add(key)
    rf=r.get("run_from_low7")
    if not isinstance(rf,(int,float)) or rf>9: continue
    y=outcome(s,a)
    if y is None: continue
    recs.append((r,y)); base[0]+=1; base[1]+=y
    for k,v in r.items():
        if k in ("at","candle","sym","bubbles","obs","px","px_src"): continue
        if isinstance(v,bool) or isinstance(v,str):
            b=stats[k][str(v)]; b[0]+=1; b[1]+=y
        elif isinstance(v,(int,float)) and not isinstance(v,bool):
            num_vals[k].append(v)
    for k,v in (r.get("obs") or {}).items():
        b=stats["obs."+k][str(v)]; b[0]+=1; b[1]+=y
# числовые — по квартилям
for k,vals in num_vals.items():
    if len(vals)<300: continue
    vs=sorted(vals); qs=[vs[int(len(vs)*q)] for q in (0.25,0.5,0.75,0.9)]
    for r,y in recs:
        v=r.get(k)
        if not isinstance(v,(int,float)) or isinstance(v,bool): continue
        if v<=qs[0]: bk=f"≤{qs[0]:.3g}"
        elif v<=qs[1]: bk=f"{qs[0]:.3g}…{qs[1]:.3g}"
        elif v<=qs[2]: bk=f"{qs[1]:.3g}…{qs[2]:.3g}"
        elif v<=qs[3]: bk=f"{qs[2]:.3g}…{qs[3]:.3g}"
        else: bk=f">{qs[3]:.3g}"
        b=stats[k][bk]; b[0]+=1; b[1]+=y
br=base[1]/base[0]
print("ТОЛЬКО МОНЕТЫ, ЕЩЁ НЕ ПОШЕДШИЕ (от минимума 7 дн ≤ +9%)")
print(f"записей монета×час: {base[0]}, база: +15% раньше −10% за сутки = {100*br:.1f}%")
res=[]
for k,bk in stats.items():
    for v,(n,h) in bk.items():
        if n<150: continue
        p=h/n; lift=p/br if br else 0
        z=(p-br)/math.sqrt(br*(1-br)/n)
        res.append((z,k,v,n,round(100*p,1),round(lift,2)))
res.sort(reverse=True)
print("\nЛУЧШЕ БАЗЫ (z>3):")
for z,k,v,n,p,lift in [x for x in res if x[0]>3][:30]: print(f"  {k} = {v}: n={n}, пошло {p}% (×{lift}), z={z:.1f}")
print("\nХУЖЕ БАЗЫ (z<−3):")
for z,k,v,n,p,lift in [x for x in res if x[0]<-3][-25:]: print(f"  {k} = {v}: n={n}, пошло {p}% (×{lift}), z={z:.1f}")
