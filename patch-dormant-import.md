# Патч · импорт CAP_DORMANT

Один блок в `detectors/flow.py`. Чинит `NameError: name 'CAP_DORMANT'
is not defined` при импорте пакета.

Моя ошибка в `patch-dormant.md`: константа добавлена в `CASE_CAP`, а в
список импорта из `flow_config` — нет. Проверка не поймала, потому что
я гонял только `ast.parse`: синтаксис проходит, имена он не разрешает.

---

## `detectors/flow.py`

### было

```python
from detectors.flow_config import (
    AGG_SCALES,
    CAP_CHURN,
    CAP_FUEL,
    CAP_HIDDEN,
    CAP_LEVERAGE,
    CAP_SPRING,
    CAP_TAKER,
```

### стало

```python
from detectors.flow_config import (
    AGG_SCALES,
    CAP_CHURN,
    CAP_DORMANT,
    CAP_FUEL,
    CAP_HIDDEN,
    CAP_LEVERAGE,
    CAP_SPRING,
    CAP_TAKER,
```
