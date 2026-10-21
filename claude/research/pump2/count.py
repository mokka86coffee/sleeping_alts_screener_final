"""21.10 владелец: «после падения первый памп всегда возвращается, идёт минимум второй»; «памп идёт до первого уровня флэта»; «макс немного выше, зависит от толпы».
Счёт на дневках TradingView (claude/research/tvd/*_1D.json, собраны 03–06.10). Пороги — Claude:
  долгое падение: минимум дня — минимум 60 дн и ниже максимума 90 дн на 60 %+;
  памп: максимум ≥ +30 % от самого низкого минимума после дна (база), в пределах 30 дн от дна;
  флэт: 10+ дней подряд, размах (макс/мин) ≤ 20 %; «первый флэт сверху» — последний флэт до дна, чей низ выше базы на 5 %+;
  вернулся: за 30 дн после вершины пампа минимум ≤ база × 1,10;  второй памп: после возврата за 60 дн максимум ≥ база × 1,30.
Фон: медиана хода всех монет за 30 дн на день пампа."""
import json, glob, os, statistics as st, collections
FILES = glob.glob(os.path.join(os.path.dirname(__file__), "..", "tvd", "*_1D.json"))
D = {}
for f in FILES:
    try: b = json.load(open(f))["bars"]
    except Exception: continue
    if len(b) > 120: D[os.path.basename(f).split(".P_")[0]] = b
# фон: медиана хода за 30 дн по дням
ch = collections.defaultdict(list)
for b in D.values():
    for i in range(30, len(b)):
        if b[i - 30][4]: ch[b[i][0]].append(b[i][4] / b[i - 30][4] - 1)
BG = {t: st.median(v) * 100 for t, v in ch.items() if len(v) >= 30}
ev = []
for s, b in D.items():
    H = [x[2] for x in b]; L = [x[3] for x in b]; T = [x[0] for x in b]; n = len(b)
    flats = []; i = 0
    while i + 10 <= n:
        if max(H[i:i + 10]) / min(L[i:i + 10]) <= 1.20:
            j = i + 10
            while j < n and max(H[i:j + 1]) / min(L[i:j + 1]) <= 1.20: j += 1
            flats.append((i, j - 1, min(L[i:j]), max(H[i:j]))); i = j
        else: i += 1
    k = 90; skip = -1
    while k < n - 35:
        if k <= skip or L[k] > min(L[k - 60:k + 1]) or L[k] > max(H[k - 90:k]) * 0.40:
            k += 1; continue
        base = L[k]; jp = None
        for j in range(k + 1, min(n, k + 31)):
            base = min(base, L[j])
            if H[j] >= base * 1.30: jp = j; break
        if jp is None: k += 1; continue
        pk_i = max(range(jp, min(n, jp + 6)), key=lambda x: H[x]); peak = H[pk_i]
        fl = [f for f in flats if f[1] < k and f[2] > base * 1.05]
        fz = fl[-1] if fl else None
        ret_i = next((x for x in range(pk_i + 1, min(n, pk_i + 31)) if L[x] <= base * 1.10), None)
        sec = None
        if ret_i is not None:
            sec_i = next((x for x in range(ret_i + 1, min(n, ret_i + 61)) if H[x] >= base * 1.30), None)
            if sec_i is not None:
                sp = max(H[sec_i:min(n, sec_i + 6)]); sec = dict(higher=sp > peak, x=sp / base)
        ev.append(dict(sym=s, t=T[jp], bg=BG.get(T[jp]), pump=peak / base, flat_lo=(fz[2] / base) if fz else None, flat_hi=(fz[3] / base) if fz else None,
                       reach=(peak >= fz[2]) if fz else None, over=(peak / fz[2]) if fz else None, ret=ret_i is not None, sec=sec,
                       ret_days=(ret_i - pk_i) if ret_i is not None else None, tail=n - pk_i))
        skip = pk_i + 60; k = skip + 1
json.dump(ev, open(os.path.join(os.path.dirname(__file__), "events.json"), "w"))
ok = [e for e in ev if e["tail"] >= 91]          # хвост после вершины ≥ 90 дн — исход виден
print("монет", len(D), "событий", len(ev), "с хвостом ≥90 дн", len(ok))
r = sum(e["ret"] for e in ok); print(f"первый памп вернулся к базе (≤ +10 %) за 30 дн: {r} из {len(ok)}")
rr = [e for e in ok if e["ret"]]; s2 = [e for e in rr if e["sec"]]
print(f"после возврата второй памп ≥ +30 % за 60 дн: {len(s2)} из {len(rr)}; выше первого: {sum(e['sec']['higher'] for e in s2)}")
wf = [e for e in ok if e["flat_lo"]]
print(f"есть флэт сверху: {len(wf)} из {len(ok)}; памп дошёл до низа флэта: {sum(e['reach'] for e in wf)}")
ov = sorted(e["over"] for e in wf if e["reach"])
if ov: print("насколько выше низа флэта вершина (медиана, четверти):", round(st.median(ov), 2), round(ov[len(ov)//4], 2), round(ov[3*len(ov)//4], 2))
nr = [e for e in wf if not e["reach"]]; print("не дошли — вершина к низу флэта, медиана:", round(st.median([e['over'] for e in nr]), 2) if nr else None)
for nm, f in (("фон ≤ −15 %", lambda x: x <= -15), ("фон −15…0", lambda x: -15 < x <= 0), ("фон > 0", lambda x: x > 0)):
    g = [e for e in ok if e["bg"] is not None and f(e["bg"])]
    if g: print(f"{nm}: событий {len(g)}, вернулся {sum(e['ret'] for e in g)}, второй после возврата {sum(1 for e in g if e['sec'])}")
