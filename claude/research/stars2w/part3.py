import json, os, glob, collections, statistics as st
BASE="/Users/evgenijminko/Work/random/python"
START="2026-10-07T15"
stars=json.load(open("stars.json"))
bys=collections.defaultdict(list)
for o in stars: bys[o["sym"]].append(o["at"])
movers=[]
for fn in glob.glob(f"{BASE}/cq_v2/intraday/*.jsonl"):
    sym=os.path.basename(fn)[:-6].upper()
    rows=[]
    for l in open(fn):
        try: r=json.loads(l)
        except: continue
        if r.get("px") and r["candle"]>=START: rows.append(r)
    rows.sort(key=lambda r:r["candle"])
    i=0; n=len(rows)
    while i<n:
        lo=rows[i]["l"] or rows[i]["px"]; li=i
        # пик в 24 ч после
        win=rows[i:i+48]
        if not win: break
        pk=max(range(len(win)),key=lambda k:(win[k].get("h") or win[k]["px"])); hi=win[pk].get("h") or win[pk]["px"]
        # лоу должен быть минимумом окна до пика
        mlo=min(range(pk+1),key=lambda k:(win[k].get("l") or win[k]["px"]))
        lo=win[mlo].get("l") or win[mlo]["px"]
        if hi/lo-1>=0.30:
            t_lo=win[mlo]["candle"][:16]; t_pk=win[pk]["candle"][:16]
            st_before=[a for a in bys.get(sym,[]) if a<=t_pk and a>= (rows[max(0,i+mlo-24)]["candle"][:16])]
            done=None
            if st_before:
                a=st_before[0]
                rr=[r for r in rows if r["candle"][:16]<=a]
                pxs=rr[-1]["px"]; done=round((pxs/lo-1)/(hi/lo-1)*100)
            r0=win[mlo]
            fu=r0.get("funding")
            movers.append(dict(sym=sym,lo_t=t_lo,pk_t=t_pk,move=round((hi/lo-1)*100),star=st_before[0] if st_before else None,done=done))
            i=i+pk+1
        else:
            i+=12
movers.sort(key=lambda m:m["lo_t"])
print("ходов ≥ +30% за 24 ч от низа (мой порог):", len(movers))
with_star=[m for m in movers if m["star"]]; no=[m for m in movers if not m["star"]]
print("со звездой до пика:", len(with_star), "| без звезды:", len(no))
if with_star:
    print("сколько хода уже было сделано к звезде, медиана:", st.median([m["done"] for m in with_star]),"%")
for m in movers: print(m["lo_t"][5:].replace("T"," "),"→",m["pk_t"][11:],m["sym"],f"+{m['move']}%", ("звезда "+m["star"][5:].replace("T"," ")+f", сделано {m['done']}%") if m["star"] else "НЕ ЗВЕЗДА")
json.dump(movers,open("movers.json","w"),ensure_ascii=False)
