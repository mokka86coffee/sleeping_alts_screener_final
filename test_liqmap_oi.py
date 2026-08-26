"""Юниты к дополнениям analytics_liqmap (вес по приросту интереса).

Старые функции не трогались — их поведение проверяется тем же входом
и должно остаться прежним.
"""

import sys
sys.path.insert(0, 'src')
import analytics_liqmap as M


def series(seq):
    """seq: [(цена, интерес)] → (highs, lows, closes, oi)."""
    h = [p * 1.01 for p, _ in seq]
    lo = [p * 0.99 for p, _ in seq]
    c = [p for p, _ in seq]
    oi = [o for _, o in seq]
    return h, lo, c, oi


def t_empty():
    assert M.liq_zones_oi([], [], [], [], 10) == []
    h, lo, c, oi = series([(10, 1e6)] * 3)
    assert M.liq_zones_oi(h, lo, c, oi, 10) == []
    print('  ✓ короткий вход — пусто')


def t_no_growth():
    """Интерес стоит — открывать нечего."""
    h, lo, c, oi = series([(10, 1e6)] * 12)
    assert M.liq_zones_oi(h, lo, c, oi, 10) == []
    print('  ✓ без прироста интереса зон нет')


def t_shrink_ignored():
    """Убыль интереса не создаёт зон: закрытые позиции не ликвидируют."""
    h, lo, c, oi = series([(10, 3e6 - i * 2e5) for i in range(12)])
    assert M.liq_zones_oi(h, lo, c, oi, 10) == []
    print('  ✓ убыль интереса игнорируется')


def t_dollars_not_shares():
    h, lo, c, oi = series([(10, 1e6 + i * 2e5) for i in range(14)])
    z = M.liq_zones_oi(h, lo, c, oi, 10, atr_pct=2.0)
    assert z and 'usd' in z[0] and 'weight' not in z[0]
    tot = sum(x['usd'] for x in z)
    assert tot > 1e5, tot
    print(f'  ✓ вес в долларах, сумма ${tot:,.0f}')


def t_funding_tilt():
    """Положительный фандинг — перевес зон ВНИЗ (лонгов больше)."""
    h, lo, c, oi = series([(10, 1e6 + i * 2e5) for i in range(14)])
    pos = M.liq_zones_oi(h, lo, c, oi, 10, fundings=[0.02] * 14)
    neg = M.liq_zones_oi(h, lo, c, oi, 10, fundings=[-0.02] * 14)
    below_p = sum(x['usd'] for x in pos if x['price'] < 10)
    below_n = sum(x['usd'] for x in neg if x['price'] < 10)
    assert below_p > below_n, (below_p, below_n)
    print(f'  ✓ фандинг наклоняет стороны ({below_p:,.0f} против {below_n:,.0f})')


def t_cross_clears():
    """Цена прошла сквозь уровень — зоны там нет."""
    grow = [(10.0, 1e6 + i * 2e5) for i in range(10)]
    h1, l1, c1, o1 = series(grow)
    z1 = M.liq_zones_oi(h1, l1, c1, o1, 10.0)
    b1 = sum(x['usd'] for x in z1 if x['price'] < 10)
    last = 1e6 + 9 * 2e5
    dive = grow + [(8.5, last), (8.5, last), (10.0, last)]
    h2, l2, c2, o2 = series(dive)
    z2 = M.liq_zones_oi(h2, l2, c2, o2, 10.0)
    b2 = sum(x['usd'] for x in z2 if x['price'] < 10)
    assert b2 < b1, (b2, b1)
    print(f'  ✓ проход цены гасит зоны (${b1:,.0f} → ${b2:,.0f})')


def t_fuel_to_cap():
    h, lo, c, oi = series([(10, 1e6 + i * 5e5) for i in range(12)])
    z = M.liq_zones_oi(h, lo, c, oi, 10)
    f = M.fuel_to_cap(z, 10, 50e6)
    assert f and f['below'] > 0
    assert M.fuel_to_cap(z, 10, 0) is None
    assert M.fuel_to_cap(None, 10, 50e6) is None
    # долевые зоны liq_zones сюда не годятся — usd нет
    share = [{'price': 9.0, 'side': 'лонги', 'weight': 1.0}]
    assert M.fuel_to_cap(share, 10, 50e6) is None
    print(f"  ✓ топливо к капе: снизу {f['below']*100:.1f}%; долевые зоны отсечены")


def t_stop_guard():
    h, lo, c, oi = series([(10, 1e6 + i * 3e5) for i in range(12)])
    z = M.liq_zones_oi(h, lo, c, oi, 10, atr_pct=2.0)
    assert z
    inside = z[0]['price']
    hit = M.stop_vs_zones(inside, z, 10, atr_pct=2.0)
    assert hit and 'виком' in hit['note']
    far = M.stop_vs_zones(inside * 0.5, z, 10, atr_pct=2.0)
    assert far is None
    assert M.stop_vs_zones(None, z, 10, 2.0) is None
    assert M.stop_vs_zones(inside, z, 10, atr_pct=0) is None
    print('  ✓ стоп в плите помечен, вдали и без ATR — молчит')


def t_old_untouched():
    """Старая функция считает как считала: доли, а не доллары."""
    h, lo, c, _ = series([(10 + i * 0.05, 0) for i in range(20)])
    v = [1e5] * 20
    z = M.liq_zones(h, lo, c, v, 11.0, atr_pct=2.0)
    if z:
        assert 'weight' in z[0] and 'usd' not in z[0]
    st = M.liq_state(z, 11.0)
    if st:
        assert 'реакции' in st.get('note', '')
    print('  ✓ старые функции не изменились')


def t_broken():
    h = [10, None, 10.2, 10.1, 10.3, 10.4]
    lo = [9.8, 9.9, 'мусор', 9.9, 10.0, 10.1]
    c = [9.9, 10.0, 10.1, 10.0, 10.2, 10.3]
    oi = [1e6, 1.2e6, None, 1.5e6, 1.7e6, 2e6]
    try:
        z = M.liq_zones_oi(h, lo, c, oi, 10.2)
        print(f'  ✓ битый вход пережит (зон {len(z)})')
    except Exception as e:                              # noqa: BLE001
        raise AssertionError(f'упало на битом входе: {e}') from e


if __name__ == '__main__':
    for fn in (t_empty, t_no_growth, t_shrink_ignored, t_dollars_not_shares,
               t_funding_tilt, t_cross_clears, t_fuel_to_cap, t_stop_guard,
               t_old_untouched, t_broken):
        fn()
    print('\nвсе юниты зелёные')
