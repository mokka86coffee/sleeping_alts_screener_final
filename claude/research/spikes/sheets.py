from pathlib import Path
from playwright.sync_api import sync_playwright
H = Path(__file__).resolve().parent; S = H / "shots"; M = H / "sheets"; M.mkdir(exist_ok=True)
tids = sorted({p.name.rsplit("_", 1)[0] for p in S.glob("*_1D.png")})
new = [t for t in tids if not (M / f"{t}.jpg").exists() and all((S / f"{t}_{tf}.png").exists() for tf in ("1D", "360", "60", "30"))]
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1700, "height": 1500})
    for t in new:
        html = "<body style='margin:0;background:#000;display:grid;grid-template-columns:850px 850px'>" + "".join(
            f"<div style='position:relative'><img src='file://{S}/{t}_{tf}.png' style='width:850px;height:750px;display:block'><b style='position:absolute;top:4px;right:8px;color:#ff0;font:bold 22px sans-serif'>{lab}</b></div>"
            for tf, lab in (("1D", "1D"), ("360", "6h"), ("60", "1h"), ("30", "30m"))) + "</body>"
        (M / "tmp.html").write_text(html); pg.goto(f"file://{M}/tmp.html"); pg.wait_for_timeout(250)
        pg.screenshot(path=str(M / f"{t}.jpg"), type="jpeg", quality=78)
    b.close()
print(new)
