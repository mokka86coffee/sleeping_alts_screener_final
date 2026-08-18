# Прогон пробы по названным монетам

Правка в `flow_probe.py`. Ключ тот же, что в `run.py`:
`python flow_probe.py --symbols MYX,ZEC`.

Работает вместе с остальными ключами: `--no-net` ускоряет, `--limit`
при именном списке игнорируется — потолок к явному списку неприменим.

---

## 1 · строка запуска в шапке — `flow_probe.py`

### Было

```python
    python flow_probe.py --limit 50   первые 50 монет по обороту
    python flow_probe.py --with-tokenized   не отсеивать акции и сырьё
    python flow_probe.py --with-excluded    не отсеивать мажоры
"""
```

### Стало

```python
    python flow_probe.py --limit 50   первые 50 монет по обороту
    python flow_probe.py --symbols MYX,ZEC   только эти монеты
    python flow_probe.py --with-tokenized   не отсеивать акции и сырьё
    python flow_probe.py --with-excluded    не отсеивать мажоры
"""
```

---

## 2 · именной список сильнее любого отсева — `flow_probe.py`

Названная монета проходит мимо отсева мажоров, мимо порога оборота и
мимо потолка выборки. Прося конкретный символ, человек уже решил, что
смотреть, и молча получить пустой прогон вместо BTC — не помощь, а
ловушка. Проба тем и отличается от боевого прогона, что ей задают
вопрос про отдельную монету, в том числе про ту, которой в боевой
выборке нет.

Разбор списка отдельной функцией: принимаем и «MYX», и «MYXUSDT», и
любой регистр. Набирать в консоли будут как придётся, а разбираться
потом с пустым прогоном из-за строчных букв — худший способ потратить
час.

### Было

```python
def load_universe(
    limit: int = 0,
    skip_tokenized: bool = True,
    skip_excluded: bool = True,
) -> list[tuple[str, float]]:
    """Символы с объёмом, отсортированные по убыванию ликвидности.

    Отсев двухступенчатый и ступени разные по смыслу. EXCLUDE_TOKENS
    из core.config режет по БАЗОВОМУ токену и повторяет боевую
    выборку: стейблы, мажоры, акции, сырьё. NON_CRYPTO режет по
    полному символу и добирает то, чего в конфиге нет.

    Потолок MAX_SYMBOLS тоже общий с боевым: без него проба могла
    бы мерить хвост, до которого скринер не доходит.
    """
    out: list[tuple[str, float]] = []
    for t in get_futures_tickers():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if skip_excluded and sym[:-4] in EXCLUDE_TOKENS:
            continue
        if skip_tokenized and sym in NON_CRYPTO:
            continue
        try:
            qv = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            continue
        if qv >= MIN_QUOTE_VOLUME_24H:
            out.append((sym, qv))
    out.sort(key=lambda x: -x[1])
    cap = limit or MAX_SYMBOLS
    return out[:cap]
```

### Стало

```python
def parse_symbols(raw: str) -> set[str]:
    """Список монет через запятую в набор полных символов.

    Принимаем и «MYX», и «MYXUSDT», и в любом регистре: набирать
    руками в консоли будут как придётся, а разбираться потом с пустым
    прогоном из-за нижнего регистра — худший способ потратить час.
    """
    out: set[str] = set()
    for part in raw.split(","):
        s = part.strip().upper()
        if not s:
            continue
        out.add(s if s.endswith("USDT") else s + "USDT")
    return out


def load_universe(
    limit: int = 0,
    skip_tokenized: bool = True,
    skip_excluded: bool = True,
    only: set[str] | None = None,
) -> list[tuple[str, float]]:
    """Символы с объёмом, отсортированные по убыванию ликвидности.

    Отсев двухступенчатый и ступени разные по смыслу. EXCLUDE_TOKENS
    из core.config режет по БАЗОВОМУ токену и повторяет боевую
    выборку: стейблы, мажоры, акции, сырьё. NON_CRYPTO режет по
    полному символу и добирает то, чего в конфиге нет.

    Потолок MAX_SYMBOLS тоже общий с боевым: без него проба могла
    бы мерить хвост, до которого скринер не доходит.

    Именной список (only) сильнее всех этих правил. Названная монета
    проходит мимо отсева мажоров, мимо порога оборота и мимо потолка:
    прося конкретный символ, человек уже принял решение, что смотреть,
    и молча получить пустой прогон вместо BTC — не помощь, а ловушка.
    Проба тем и отличается от боевого прогона, что ей задают вопрос
    про отдельную монету, в том числе про ту, которой в выборке нет.
    """
    out: list[tuple[str, float]] = []
    for t in get_futures_tickers():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        named = bool(only) and sym in only
        if not named:
            if only:
                continue
            if skip_excluded and sym[:-4] in EXCLUDE_TOKENS:
                continue
            if skip_tokenized and sym in NON_CRYPTO:
                continue
        try:
            qv = float(t.get("quoteVolume", 0))
        except (TypeError, ValueError):
            qv = 0.0
        if named or qv >= MIN_QUOTE_VOLUME_24H:
            out.append((sym, qv))
    out.sort(key=lambda x: -x[1])
    if only:
        return out
    cap = limit or MAX_SYMBOLS
    return out[:cap]
```

---

## 3 · разбор ключа и громкий отчёт о ненайденном — `flow_probe.py`

Опечатка в тикере даёт ровно тот же пустой прогон, что и монета без
фьючерса. Без отдельной строки эти два случая неразличимы, поэтому
ненайденное называется вслух, а полностью пустой список останавливает
прогон сразу, а не после сбора нулевого CSV.

### Было

```python
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            limit = 0

    _check_cases()
    symbols = load_universe(
        limit, skip_tokenized=skip_tokenized, skip_excluded=skip_excluded,
    )
    net = "включена" if allow_network else "выключена"
    filt = "как в боевом прогоне" if skip_excluded else "включая мажоры"
    if not skip_tokenized:
        filt += ", с акциями и сырьём"
    print(f"Монет к прогону: {len(symbols)}, сеть для leverage: {net}")
    print(f"Состав выборки: {filt}")
```

### Стало

```python
    limit = 0
    if "--limit" in sys.argv:
        try:
            limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError):
            limit = 0
    only: set[str] = set()
    if "--symbols" in sys.argv:
        try:
            only = parse_symbols(sys.argv[sys.argv.index("--symbols") + 1])
        except IndexError:
            only = set()

    _check_cases()
    symbols = load_universe(
        limit, skip_tokenized=skip_tokenized, skip_excluded=skip_excluded,
        only=only,
    )
    net = "включена" if allow_network else "выключена"
    filt = "как в боевом прогоне" if skip_excluded else "включая мажоры"
    if not skip_tokenized:
        filt += ", с акциями и сырьём"
    if only:
        filt = "именной список, отсев и потолок не применяются"
        # Ненайденное называем вслух. Опечатка в тикере даёт ровно тот
        # же пустой прогон, что и монета без фьючерса, и без этой
        # строки они неразличимы.
        missing = sorted(s for s in only if s not in {x for x, _ in symbols})
        if missing:
            print(f"⚠ нет среди фьючерсов: {', '.join(missing)}")
        if not symbols:
            print("Прогон пуст: ни одна из названных монет не найдена")
            return
    print(f"Монет к прогону: {len(symbols)}, сеть для leverage: {net}")
    print(f"Состав выборки: {filt}")
```

---

## 4 · названная монета всегда попадает в JSON — `flow_probe.py`

Её и просили ради разбора причины, а не ради строки в CSV. Раньше
полный контекст сохранялся только для сработавших и для WATCH —
то есть именно в интересном случае «назвал монету, она молчит»
разбора бы не было.

### Было

```python
            if (d.get("detected") or symbol in WATCH) and len(deep) < DEEP_DUMP_LIMIT:
```

### Стало

```python
            # Названная монета попадает в JSON всегда, как и WATCH:
            # её и просили ради разбора причины, а не ради строки CSV.
            if ((d.get("detected") or symbol in WATCH or symbol in only)
                    and len(deep) < DEEP_DUMP_LIMIT):
```
