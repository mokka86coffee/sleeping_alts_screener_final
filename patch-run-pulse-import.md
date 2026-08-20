# Патч: импорт pulse в run.py

Старый импорт `from analytics import pulse` остался закомментированным
после переноса пакета `analytics/` в плоские `analytics_*.py` — модуль
стал называться `analytics_pulse`, а вызов `pulse.record(...)` внизу
файла тоже остался мёртвым текстом под комментарием.

## файл: `run.py`

### было
```python
from analytics_leaders import update_leaders
# import pulse
from analytics_candidate import build_candidate
```

### стало
```python
from analytics_leaders import update_leaders
from analytics_pulse import record as record_pulse
from analytics_candidate import build_candidate
```

### было
```python
    #     log(f"→ Пульс: {pulse.record(candidates)}")
```

### стало
```python
    log(f"→ Пульс: {record_pulse(candidates)}")
```
