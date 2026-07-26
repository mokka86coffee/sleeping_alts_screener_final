import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

from squeeze_detector import analyze_squeeze

for sym in ["DEXEUSDT", "KAITOUSDT", "DIAUSDT", "ACEUSDT", "PENDLEUSDT", "GMXUSDT"]:
    s = analyze_squeeze(sym)
    print(f"\n{sym} — {s.risk_level.upper()} ({s.risk_score}/100)")
    print(f"  price 14d: {s.price_change_14d_pct:+.1f}%  |  OI 14d: {s.oi_change_14d_pct:+.1f}%")
    print(f"  funding peak: {s.funding_peak_14d:.3f}%  |  spot/fut: {s.spot_futures_ratio:.2f}")
    print(f"  RSI: {s.rsi_14:.0f}  |  parabolic: {s.parabolic}")
    for reason in s.reasons:
        print(f"  ▸ {reason}")
    print(f"  → {s.verdict}")
