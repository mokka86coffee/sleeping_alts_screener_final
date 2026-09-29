import json, glob
from pathlib import Path
from datetime import datetime, timezone, timedelta
H = Path(__file__).parent; CGX = H.parent / "cgx"; L = timezone(timedelta(hours=3))
def cl(v): return v if isinstance(v, (int, float)) and v == v else 0.0
B = []
for f in sorted(H.glob("sig_[0-9]*.json")): B += json.load(open(f))
out = []
for x in B:
    fp = CGX / f"{x['sym']}_15.json"
    if not fp.exists(): continue
    R = [r for r in json.load(open(fp))["rows"] if r.get("c")]
    t0, e = x["t_in"], x["px_in"]
    W = [r for r in R if t0 < r["t"] <= t0 + 4 * 3600]
    if len(W) < 4: continue
    up = (max(r["h"] for r in W) / e - 1) * 100; dn = (min(r["l"] for r in W) / e - 1) * 100
    first = next(("+5" if r["h"] >= e * 1.05 else "-5" for r in W if r["h"] >= e * 1.05 or r["l"] <= e * 0.95), "нет")
    hs = {}
    for r in R:
        h = int(r["t"] // 3600 * 3600); hs.setdefault(h, [0, 0]); hs[h][0] += cl(r.get("liq_long")); hs[h][1] += cl(r.get("liq_short"))
    h0 = int(t0 // 3600 * 3600); past = [v for h, v in hs.items() if h < h0]
    tl = max((v[0] for v in past), default=0); ts = max((v[1] for v in past), default=0)
    pre_s = hs.get(h0, [0, 0])[1]; post_l = sum(hs.get(h0 + k * 3600, [0, 0])[0] for k in range(1, 5)); post_s = sum(hs.get(h0 + k * 3600, [0, 0])[1] for k in range(1, 5))
    day = [r for r in R if t0 - 86400 <= r["t"] < t0]
    fund = [r["fund"] for r in day if isinstance(r.get("fund"), (int, float)) and r["fund"] == r["fund"]]
    oi = [r["oi"] for r in R if r["t"] < t0 and isinstance(r.get("oi"), (int, float)) and r["oi"] == r["oi"]]
    oi_ch = (oi[-1] / oi[-5] - 1) * 100 if len(oi) > 5 and oi[-5] else None
    out.append(dict(tid=f"{x['sym'][:-4]}_{datetime.fromtimestamp(t0, L):%m%d_%H%M}", lab=x["label"], px=e, up4=up, dn4=dn, c4=(W[-1]["c"] / e - 1) * 100, first=first,
                    liq_s_now=pre_s, liq_s_top=ts, liq_l_after=post_l, liq_l_top=tl, fund=(sum(fund) / len(fund) if fund else None), oi1h=oi_ch))
json.dump(out, open(H / "sig_facts.json", "w"), ensure_ascii=False, indent=0)
for o in out:
    print(f"{o['tid']:16} {o['lab'][:26]:26} 4ч: вверх {o['up4']:+.1f} вниз {o['dn4']:+.1f} закр {o['c4']:+.1f} первым {o['first']:>3} | OI1ч {o['oi1h'] if o['oi1h'] is None else round(o['oi1h'],1)} фанд {o['fund'] if o['fund'] is None else round(o['fund'],4)} | вынос шортов на баре {o['liq_s_now']/1e3:.0f}K (макс. до {o['liq_s_top']/1e3:.0f}K) лонгов после {o['liq_l_after']/1e3:.0f}K")
