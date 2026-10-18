"""ЦЕНА ИЗБРАННЫХ РАЗ В 3 МИНУТЫ, ПОКА НЕТ НОВОЙ ПОЛНОЙ СБОРКИ (18.10 01:10 UTC владелец: «давай тем что идут все таки цену
обновлять раз в 3 минуты… только цену пока»).

Полную сборку output/fast_state.json делает fast_state.py, которого бот зовёт после каждого цикла. На время прогона скринера
по Binance бот стоит на паузе до ~25 мин, сборок нет, и цена на свечах избранного («на ходу» / «скоро» / «шевелятся») стынет.
Этот процесс запускается в конце каждой сборки fast_state и живёт, пока не появится следующая: каждые PX_EVERY с один запрос
цен Binance (ticker/price, вес 2 — тот же, что у сборки) и правка только полей now / now_t у favorites (×N от дна на странице
считается от now). Ничего другого в состоянии не трогает; mtime файла ставится на секунду позже прежнего, чтобы для бота
(R82/R84 — возраст меток очереди по mtime) состояние не молодело, а сервер fast_server.py (рассылка по смене mtime) увидел правку.
Выходит сам: появилась новая полная сборка (meta.t изменился) или прошло PX_MAX_MIN. Второй экземпляр не запускается (замок).
"""
from __future__ import annotations

import fcntl
import json
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from core_http import get_json  # noqa: E402

OUT = BASE_DIR / "output" / "fast_state.json"
PX_EVERY = 180        # с: раз в 3 мин — как полная сборка
PX_MAX_MIN = 40       # дольше одного прогона скринера не живём


def patch_once() -> str:
    try:
        s = json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return f"состояние не прочитано: {type(e).__name__}"
    fav = s.get("favorites") or []
    if not fav:
        return "избранных нет"
    tk = get_json("https://fapi.binance.com/fapi/v1/ticker/price", weight=2) or []
    px = {x["symbol"]: float(x["price"]) for x in tk if str(x.get("symbol", "")).endswith("USDT") and float(x.get("price") or 0) > 0}
    if len(px) < 100:
        return "цены не пришли"
    t = round(time.time(), 1); n = 0
    for f in fav:
        p = px.get(f.get("sym"))
        if p:
            f["now"], f["now_t"] = p, t; n += 1
            lo = f.get("atl")
            if lo:
                f["from_atl_pct"] = round((p / float(lo) - 1) * 100, 1)
    s.setdefault("meta", {})["px_t"] = t
    try:
        m0 = OUT.stat().st_mtime
        tmp = OUT.with_suffix(".px.tmp")
        tmp.write_text(json.dumps(s, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(OUT)
        os.utime(OUT, (m0 + 1, m0 + 1))
    except OSError as e:
        return f"не записано: {type(e).__name__}"
    return f"цена обновлена у {n} из {len(fav)}"


def main() -> None:
    lk = open(OUT.with_suffix(".px.lock"), "w")
    try:
        fcntl.flock(lk, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return
    if "--once" in sys.argv:
        print(f"{time.strftime('%H:%M:%S', time.gmtime())} fast_px: {patch_once()}", flush=True); return
    try:
        t0 = float((json.loads(OUT.read_text(encoding="utf-8")).get("meta") or {}).get("t") or 0)
    except (OSError, ValueError):
        t0 = 0.0
    start = time.time()
    while time.time() - start < PX_MAX_MIN * 60:
        time.sleep(PX_EVERY)
        try:
            t1 = float((json.loads(OUT.read_text(encoding="utf-8")).get("meta") or {}).get("t") or 0)
        except (OSError, ValueError):
            t1 = t0
        if t1 != t0:                                                     # пришла новая полная сборка — она запустила своего fast_px
            return
        print(f"{time.strftime('%H:%M:%S', time.gmtime())} fast_px: {patch_once()}", flush=True)


if __name__ == "__main__":
    main()
