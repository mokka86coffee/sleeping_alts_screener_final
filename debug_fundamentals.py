"""
debug_fundamentals.py — быстрая проверка external_data.py:
что резолвится, где падает, что реально приходит с CoinGecko/DefiLlama.
"""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s:%(name)s:%(message)s",
)

from external_data import (
    resolve_coingecko_id,
    get_fundamentals,
    build_fundamental_take_live,
    _load_coins_map,
    _load_protocols_map,
)


def main() -> None:
    # 1. Проверяем карты
    coins = _load_coins_map()
    protos = _load_protocols_map()
    print(f"\nCoinGecko map:      {len(coins)} символов")
    print(f"DefiLlama protocols: {len(protos)}\n")

    if protos:
        # Покажем несколько записей с TVL — для проверки что структура ок
        top = sorted(protos.items(), key=lambda kv: kv[1].get("tvl", 0), reverse=True)[:5]
        print("Топ-5 DefiLlama по TVL:")
        for sym, d in top:
            tvl_m = d["tvl"] / 1e6
            print(f"  {sym:<10} TVL=${tvl_m:>10.1f}M  slug={d.get('slug'):<30} cat={d.get('category')}")
        print()

    # 2. Тестовые тикеры из реального отчёта
    test = [
        "METUSDT", "GMXUSDT", "JTOUSDT", "ORDIUSDT", "VIRTUALUSDT",
        "HMSTRUSDT", "AEROUSDT", "INJUSDT", "PENDLEUSDT", "COAIUSDT",
        "RAVEUSDT", "POWERUSDT", "BROCCOLI714USDT", "USTCUSDT", "XANUSDT",
    ]

    print(f"{'Symbol':<18} {'cg_id':<28} {'has_data':<10} {'rank':<6} {'TVL':<12} {'Twitter'}")
    print("─" * 100)

    for sym in test:
        cid = resolve_coingecko_id(sym)
        f = get_fundamentals(sym)
        tvl_str = f"${f.tvl_usd/1e6:.1f}M" if f.tvl_usd > 0 else "—"
        tw_str = f"{f.twitter_followers:,}" if f.twitter_followers > 0 else "—"
        rank_str = str(f.mcap_rank) if f.mcap_rank else "—"

        print(
            f"{sym:<18} "
            f"{(cid or '—'):<28} "
            f"{str(f.has_data()):<10} "
            f"{rank_str:<6} "
            f"{tvl_str:<12} "
            f"{tw_str}"
        )

    # 3. Показываем текстовые вердикты для первых трёх
    print("\n" + "=" * 100)
    print("FUNDAMENTAL TAKES (примеры):")
    print("=" * 100)
    for sym in test[:5]:
        f = get_fundamentals(sym)
        take = build_fundamental_take_live(f) if f.has_data() else "— нет данных —"
        print(f"\n{sym}:")
        print(f"  {take}")


if __name__ == "__main__":
    main()
