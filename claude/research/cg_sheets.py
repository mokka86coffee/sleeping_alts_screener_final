#!/usr/bin/env python3
"""Склейка снимков сделки 1D / 6h / 1h / 15m (01.10 владелец) в один лист (cgr → cgm/<сделка>.jpg) для разбора; только готовые и ещё не склеенные."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
H = Path(__file__).resolve().parent
M = H / "cgm"; M.mkdir(exist_ok=True)
F = {f["tid"]: f for f in json.load(open(H / "trade_facts.json"))}
todo = [t for t in F if all((H / f"cgr/{t}_{tf}.png").exists() for tf in ("1D", "360", "60", "15")) and not (M / f"{t}.jpg").exists()]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1700, "height": 1500})
    for t in todo:
        html = "<body style='margin:0;background:#000;display:grid;grid-template-columns:850px 850px'>" + "".join(
            f"<div style='position:relative'><img src='file://{H}/cgr/{t}_{tf}.png' style='width:850px;height:750px;display:block'>"
            f"<b style='position:absolute;top:4px;right:8px;color:#ff0;font:bold 22px sans-serif'>{lab}</b></div>"
            for tf, lab in (("1D", "1D"), ("360", "6h"), ("60", "1h"), ("15", "15m"))) + "</body>"
        (M / "tmp.html").write_text(html); pg.goto(f"file://{M}/tmp.html"); pg.wait_for_timeout(250)
        pg.screenshot(path=str(M / f"{t}.jpg"), type="jpeg", quality=78)
    b.close()
print(len(todo), "листов")
