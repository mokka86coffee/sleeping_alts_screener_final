import json, collections, datetime as dt, sys
LOG='output/queue_log.jsonl'
runs=[]  # (at, first list)
for l in open(LOG):
    if '"sym": "_BG"' not in l[:120]: continue
    try: e=json.loads(l)
    except: continue
    runs.append((e['at'], e.get('first') or []))
runs.sort()
hits=collections.defaultdict(list); prev=set(); inrun=collections.Counter()
for at,first in runs:
    cur=set(first)
    for s in cur:
        inrun[s]+=1
        if s not in prev: hits[s].append(at)
    prev=cur
need={(at,s) for s,v in hits.items() for at in v}
px={}
for l in open(LOG):
    if '"sym": "_BG"' in l[:120]: continue
    a=l[8:28]
    i=l.find('"sym": "'); s=l[i+8:l.find('"',i+8)]
    if (a,s) in need:
        try: e=json.loads(l)
        except: continue
        px[(a,s)]=e.get('px')
json.dump({'runs':len(runs),'first_at':runs[0][0],'last_at':runs[-1][0],'hits':hits,'inrun':inrun,'px':{f'{a}|{s}':v for (a,s),v in px.items()}},open(sys.argv[1],'w'),ensure_ascii=False)
print(len(runs),runs[0][0],runs[-1][0],'монет в первых:',len(hits),'≥3 попаданий:',sum(1 for v in hits.values() if len(v)>=3),'>3:',sum(1 for v in hits.values() if len(v)>3))
