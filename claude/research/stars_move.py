import json, datetime as dt, os, sys
S=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(S+'/stars_first.json'))
ts=lambda a: dt.datetime.strptime(a,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=dt.timezone.utc).timestamp()
loc=lambda t: dt.datetime.fromtimestamp(t).strftime('%d.%m %H:%M')
out=[]
for s,v in d['hits'].items():
    if len(v)<=3: continue
    c=s[:-4]; t0=ts(v[0])
    try:
        H=json.load(open(f'claude/research/tvd/{s}.P_60.json')); D=json.load(open(f'claude/research/tvd/{s}.P_1D.json'))
    except Exception as e:
        out.append(dict(c=c,err=str(e)[:60])); continue
    hb=[b for b in H['bars'] if b[0]+3600>t0]
    if not hb: out.append(dict(c=c,err='нет часов после')); continue
    px0=d['px'].get(v[0]+'|'+s) or hb[0][4]
    last_t=H['bars'][-1][0]; last=H['bars'][-1][4]
    mx=max(hb,key=lambda b:b[2]); mult=mx[2]/px0
    pre=[b for b in hb if b[0]<=mx[0]]; dd=min(b[3] for b in pre)/px0-1
    after=[b for b in hb if b[0]>=mx[0]]; fall=min(b[3] for b in after)/mx[2]-1
    db=[b for b in D['bars'] if t0-30*86400<=b[0]<t0-86400]
    low30=min(b[3] for b in db) if db else None; hi30=max(b[2] for b in db) if db else None
    oi=[o for o in H.get('oi',[]) if o[1]]
    oi0=next((o[1] for o in oi if o[0]+3600>t0),None); oimx=next((o[1] for o in oi if o[0]>=mx[0]),None); oil=oi[-1][1] if oi else None
    out.append(dict(c=c,n=len(v),runs=d['inrun'][s],t0=loc(t0),px0=px0,mult=round(mult,2),days_to_max=round((mx[0]-t0)/86400,1),tmax=loc(mx[0]),dd=round(dd*100,1),
        fall=round(fall*100,1),now=round(last/px0,2),from_low30=round(px0/low30,2) if low30 else None,total=round(mx[2]/low30,2) if low30 else None,
        vs_hi30=round((px0/hi30-1)*100,1) if hi30 else None, oi0=oi0, oi_at_max=oimx, oi_now=oil, last=loc(last_t), days=round((last_t-t0)/86400,1)))
json.dump(out,open(S+'/stars_move.json','w'),ensure_ascii=False,indent=0)
ok=[o for o in out if 'err' not in o]
for o in sorted(ok,key=lambda o:-o['mult']):
    oi=f"интерес {o['oi_at_max']/o['oi0']:.2f}→{o['oi_now']/o['oi0']:.2f}" if o['oi0'] and o['oi_at_max'] and o['oi_now'] else ''
    print(f"{o['c']:11} в первых {o['n']:2} раз · впервые {o['t0']} · уже ×{o['from_low30']} от низа 30д ({o['vs_hi30']:+}% к макс 30д) · потом макс ×{o['mult']} за {o['days_to_max']} дн (до него просадка {o['dd']}%) · от макс {o['fall']}% · сейчас ×{o['now']} · всего от низа ×{o['total']} · {oi} · дней {o['days']}")
for o in out:
    if 'err' in o: print('НЕТ ДАННЫХ',o)
