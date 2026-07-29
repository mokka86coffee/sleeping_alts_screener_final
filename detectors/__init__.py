"""Детекторы паттернов. Единый интерфейс: detect_xxx(symbol) -> Signal.

Каждый сигнал умеет to_dict() для сериализации в снимок прогона
и в данные страницы.
"""

from detectors.taiko import TaikoSignal, detect_taiko
from detectors.dexe import DexeSignal, detect_dexe
from detectors.volume_surge import VolumeSurgeSignal, detect_volume_surge
from detectors.squeeze import SqueezeSignal, analyze_squeeze, detect_squeeze

__all__ = [
    "TaikoSignal", "detect_taiko",
    "DexeSignal", "detect_dexe",
    "VolumeSurgeSignal", "detect_volume_surge",
    "SqueezeSignal", "analyze_squeeze", "detect_squeeze",
]
