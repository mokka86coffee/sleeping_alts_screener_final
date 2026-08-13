# Патч · свежий пик снимает подкейс с роли победителя

Три файла. `flow_signal.py` и `flow_fuel.py` меньше пятисот строк, но
правка в каждом — одна вставка, поэтому блоками; `flow.py` — 572
строки.

**Что случилось.** TUT получил `flow_fuel` со скором 94 и подписью
«экстремальный», а в обоснованиях самого подкейса стояло: «свежий пик:
рост x42.6 4 дней назад». Монета сделала сорокадвухкратку и сложилась
на 84% от вершины. `growth_load` при этом отработал — множитель 0.85.
Просто множителя мало: он снял пятнадцать процентов там, где надо было
снять монету с доски.

**Почему не вето.** Фигура настоящая: предложение действительно снято,
уровни пройдены. Выбрасывать сигнал значит терять верное наблюдение.
Неверно другое — что он представляет монету на экране. Поэтому не
«не считать», а «не побеждать»: подкейс остаётся в списке сработавших,
но уступает роль любому другому, если тот собрался.

---

## 1 · `detectors/flow_signal.py` — признак у сигнала

### было

```python
    # Базовый скор до множителей. Нужен при калибровке: без него
    # непонятно, слабая фигура или сильная, но зарезанная.
    base_score: float = 0.0
```

### стало

```python
    # Базовый скор до множителей. Нужен при калибровке: без него
    # непонятно, слабая фигура или сильная, но зарезанная.
    base_score: float = 0.0

    # Фигура собралась, но описывает уже состоявшееся движение.
    #
    # Отдельный признак, а не множитель и не вето. Множитель уже был
    # и не помогал: он снимает проценты, а проблема не в величине
    # вклада — сигнал верен. Вето тоже неправильно: выбросив его, мы
    # потеряли бы верное наблюдение о том, что предложение снято.
    #
    # Ложно ровно одно утверждение — что такой фигурой стоит
    # ПРЕДСТАВЛЯТЬ монету. Поэтому признак влияет только на выбор
    # победителя в диспетчере и больше ни на что.
    late: bool = False
```

### было

```python
    def to_dict(self) -> dict:
        return {
            "subcase": self.subcase,
            "score": round(self.score, 1),
            "base_score": round(self.base_score, 1),
            "cut": round(self.cut, 3),
```

### стало

```python
    def to_dict(self) -> dict:
        return {
            "subcase": self.subcase,
            "score": round(self.score, 1),
            "base_score": round(self.base_score, 1),
            "cut": round(self.cut, 3),
            "late": self.late,
```

---

## 2 · `detectors/flow_fuel.py` — свежий пик ставит признак

### было

```python
    fresh_peak = ctx.drop.peak_age_days <= GROWTH_LOAD_PEAK_DAYS
    if fresh_peak and ctx.growth_x >= GROWTH_LOAD_X:
        sig.apply("growth_load", 0.85)
        sig.add(
            f"свежий пик: рост x{ctx.growth_x:.1f} "
            f"{ctx.drop.peak_age_days} дней назад, выше могут быть "
            f"зоны за горизонтом карты",
            growth_x=ctx.growth_x,
            peak_age_days=float(ctx.drop.peak_age_days),
        )
```

### стало

```python
    fresh_peak = ctx.drop.peak_age_days <= GROWTH_LOAD_PEAK_DAYS
    if fresh_peak and ctx.growth_x >= GROWTH_LOAD_X:
        sig.apply("growth_load", 0.85)
        # Множитель остаётся, но решает не он.
        #
        # Замер 13 августа: TUT сделал x42.6 за четыре дня до прогона,
        # сложился на 84% от вершины — и получил от семейства 94 балла
        # с подписью «экстремальный». Обоснование подкейса при этом
        # честно сообщало про свежий пик. Пятнадцать процентов штрафа
        # на такой картине ничего не решают: снимать надо не проценты,
        # а право представлять монету.
        #
        # Смысл fuel от этого не меняется — предложение действительно
        # снято. Меняется только то, чем монета подписана на экране,
        # если рядом собралась фигура входа.
        sig.late = True
        sig.add(
            f"свежий пик: рост x{ctx.growth_x:.1f} "
            f"{ctx.drop.peak_age_days} дней назад, выше могут быть "
            f"зоны за горизонтом карты",
            growth_x=ctx.growth_x,
            peak_age_days=float(ctx.drop.peak_age_days),
        )
```

---

## 3 · `detectors/flow.py` — победитель выбирается из не-поздних

### было

```python
    top_score = max(s.score for _, s in results)
    contenders = [(n, s) for n, s in results if s.score >= top_score - TIE_MARGIN]
    best_name, best_sig = max(
        contenders,
        key=lambda x: (CASE_PRIORITY.get(x[0], 0), x[1].score),
    )
```

### стало

```python
    # Поздние фигуры не участвуют в выборе, пока есть хоть одна не
    # поздняя. Отсечка стоит ДО расчёта top_score намеренно: иначе
    # поздний лидер задирал бы планку и утаскивал за собой окно
    # TIE_MARGIN, оставляя ранние фигуры за его пределами.
    #
    # Если поздние все — выбираем из них, ничего не пряча. Фигура
    # верна, монета просто уже поехала, и это надо показать, а не
    # заменить пустотой.
    early = [(n, s) for n, s in results if not getattr(s, "late", False)]
    pool = early or results

    top_score = max(s.score for _, s in pool)
    contenders = [(n, s) for n, s in pool if s.score >= top_score - TIE_MARGIN]
    best_name, best_sig = max(
        contenders,
        key=lambda x: (CASE_PRIORITY.get(x[0], 0), x[1].score),
    )
```

### было

```python
    others = [
        (n, s) for n, s in results
        if n != best_name and s.score >= CONFIRM_MIN_RAW
    ]
```

### стало

```python
    # Подтверждать победителя поздняя фигура вправе: «предложение
    # снято» остаётся верным доводом рядом с фигурой входа. Здесь
    # берётся весь results, а не pool.
    others = [
        (n, s) for n, s in results
        if n != best_name and s.score >= CONFIRM_MIN_RAW
    ]
```
