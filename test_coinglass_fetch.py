"""Юниты coinglass_fetch: сеть подменена, формы — с живого пробника 29.08.

    python test_coinglass_fetch.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import coinglass_fetch as cf

cf.time.sleep = lambda s: None          # юнитам пауза не нужна
cf.STATE_PATH = Path("/tmp/cg_test_state.json")

CALLS = []

# Живые формы: фьюч-дельта несёт и тейкер, и cvd; последний бар
# ЯДОВИТЫЙ — если его не отбросить, тейкер улетит в 100+.
FUT_CVD = {"code": "0", "msg": "success", "data": [
    {"time": 1787965400000, "agg_taker_buy_vol": 40.0,
     "agg_taker_sell_vol": 30.0, "cum_vol_delta": 10.0},
    {"time": 1787969000000, "agg_taker_buy_vol": 60.0,
     "agg_taker_sell_vol": 50.0, "cum_vol_delta": 34.0},
    {"time": 1787972600000, "agg_taker_buy_vol": 99999.0,
     "agg_taker_sell_vol": 1.0, "cum_vol_delta": 999.0},   # неполный
]}
SPOT_EMPTY = {"code": "0", "msg": "success", "data": []}
OI = {"code": "0", "data": [                               # строки!
    {"time": 1, "open": "90", "high": "101", "low": "89", "close": "100"},
    {"time": 2, "open": "100", "high": "125", "low": "99", "close": "120"},
    {"time": 3, "open": "120", "high": "121", "low": "4", "close": "5"},  # неполный
]}
FUNDING = {"code": "0", "data": [
    {"time": 1, "open": "0.010", "close": "0.0100"},
    {"time": 2, "open": "0.010", "close": "0.0250"},
    {"time": 3, "open": "0.025", "close": "0.9000"},       # неполный
]}
DENY = {"code": "401", "msg": "Upgrade plan"}
LIQ_LIST = {"code": "0", "data": [
    {"symbol": "MAGMA", "long_liquidation_usd_24h": 63000,
     "short_liquidation_usd_24h": 48000, "long_liquidation_usd_4h": 21000,
     "short_liquidation_usd_4h": 2500, "long_liquidation_usd_1h": 0,
     "short_liquidation_usd_1h": 0},
    {"symbol": "ZZZ", "long_liquidation_usd_24h": 1},
]}


def router(deny_funding=False, deny_liq=False):
    def fake_get(path, params, key):
        CALLS.append((path, dict(params)))
        if "liquidation/coin-list" in path:
            return (200, DENY) if deny_liq else (200, LIQ_LIST)
        if "futures/aggregated-cvd" in path:
            return 200, FUT_CVD
        if "spot/aggregated-cvd" in path:
            return 200, SPOT_EMPTY
        if "open-interest" in path:
            return 200, OI
        if "funding-rate" in path:
            return (200, DENY) if deny_funding else (200, FUNDING)
        raise AssertionError("неизвестный путь " + path)
    return fake_get


def т(имя, усл):
    print(("  ок " if усл else "  ПРОВАЛ ") + имя)
    assert усл, имя


print("1. разбор: закрытые бары, строки-числа, пусто ≠ ошибка")
c = cf.parse_cvd(FUT_CVD)
т("тейкер по закрытым 100/80", c["taker"] == 1.25)
т("ядовитый неполный бар отброшен", c["buyUsd"] == 100.0)
т("cvdChg = последний − первый закрытый", c["cvdChg"] == 24.0)
т("спот пустой → None", cf.parse_cvd(SPOT_EMPTY) is None)
o = cf.parse_ohlc_close(OI)
т("OI из строк: последний закрытый 120", o["last"] == 120.0)
т("OI сдвиг +20%", o["chgPct"] == 20.0)
т("_num: запятая и NaN", cf._num("1,234.5") == 1234.5
  and cf._num(float("nan")) is None and cf._num("мусор") is None)

print("2. отказ внутри кода двести")
try:
    cf._body(200, DENY)
    т("Denied поднят", False)
except cf.Denied as e:
    т("Denied с сообщением тарифа", "Upgrade plan" in str(e))
cf._body(200, {"code": "0", "data": []})        # живой — не поднимает
т("живой ответ проходит", True)

print("3. список ликвидаций: фильтр и терпимые ключи")
lm = cf.parse_liq_list(LIQ_LIST)
т("MAGMA найдена", lm["MAGMA"]["long24h"] == 63000
  and lm["MAGMA"]["short4h"] == 2500)
т("чужая монета отдельно, не мешает", "ZZZ" in lm)

print("4. сбор: срез, отказ точки записан, запись только по write")
CALLS.clear()
cf.get = router(deny_funding=True)
cf.STATE_PATH.unlink(missing_ok=True)
st = cf.collect(["MAGMAUSDT"], key="k", write=False)
m = st["coins"]["MAGMA"]
т("USDT срезан, монета в срезе", "MAGMA" in st["coins"])
т("фьюч-тейкер 1.25", m["fut"]["taker"] == 1.25)
т("спот null — данных нет", m["spot"] is None)
т("OI в поля", m["oiUsd"] == 120.0 and m["oiChgPct"] == 20.0)
т("фандинг отказан → None + ошибка с текстом",
  m["funding"] is None and "Upgrade plan" in st["errors"]["MAGMA funding"])
т("спот-пусто НЕ в ошибках", "MAGMA spot" not in st["errors"])
т("ликвидации из общего списка", m["liq"]["long24h"] == 63000)
т("запросов 5 (список + четыре точки)", st["requests"] == 5)
т("write=False не пишет", not cf.STATE_PATH.exists())
т("limit просит окно+1", all(p.get("limit") == "13"
  for _, p in CALLS if "limit" in p))

print("5. запись по флагу и живой фандинг")
cf.get = router()
st2 = cf.collect(["MAGMA"], key="k", write=True)
т("файл записан", cf.STATE_PATH.exists())
disk = json.loads(cf.STATE_PATH.read_text(encoding="utf-8"))
т("на диске фандинг последнего закрытого 0.025",
  disk["coins"]["MAGMA"]["funding"] == 0.025)
т("ошибок нет", disk["errors"] == {})

print("6. отказ общего списка не роняет монеты")
cf.get = router(deny_liq=True)
st3 = cf.collect(["MAGMA"], key="k")
т("монета собрана, liq пуст", st3["coins"]["MAGMA"]["liq"] is None)
т("отказ списка записан", "Upgrade plan" in st3["errors"]["liq-list"])

print("7. показ")
d = cf.digest(st2)
т("строка монеты с тейкером", "MAGMA" in d and "1.25" in d)
т("спот подписан «нет»", "нет" in d)
d3 = cf.digest(st3)
т("ошибка видна в показе", "liq-list" in d3)
т("без ключа — человеческий отказ",
  "нет ключа" in cf.digest(cf.collect(["X"], key="")))

print("8. журнал не прочитался — причина видна, не молчание")
cf.get = router()
st4 = cf.collect(None, key="k")          # analytics_leaders здесь нет
т("откат до BTC", list(st4["coins"]) == ["BTC"])
т("причина в ошибках, а не проглочена", "журнал" in st4["errors"]
  and "не прочитан" in st4["errors"]["журнал"])

print("9. показ не слипается на длинном минусе (живой BTC)")
live = {"at": "x", "window": "12x1h", "requests": 5, "errors": {},
        "coins": {"BTC": {
            "fut": {"taker": 0.91, "cvdChg": -431.0e6},
            "spot": {"taker": 0.90, "cvdChg": -53.1e6},
            "oiUsd": 54.3e9, "oiChgPct": -1.6, "funding": 0.0069,
            "liq": {"long24h": 132.3e6, "short24h": 22.5e6}}}}
dl = cf.digest(live)
т("минус не въехал в спот-колонку", "M0." not in dl)
т("обе стороны ликвидаций на месте", "132.3M/22.5M" in dl)

cf.STATE_PATH.unlink(missing_ok=True)
print("\nвсе юниты зелёные")
