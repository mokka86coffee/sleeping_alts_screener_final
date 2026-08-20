"""HTTP-слой: единая сессия, токен-бакет по весам, ретраи, кэш ответов.

Все сетевые запросы проекта проходят через get_json. Модули выше по стеку
не знают ни про Retry-After, ни про X-MBX-USED-WEIGHT.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

from core_config import (
    HTTP_BACKOFF_BASE,
    HTTP_RETRIES,
    MAX_WORKERS,
    REQUEST_TIMEOUT,
    USER_AGENT,
    WEIGHT_CAPACITY,
    WEIGHT_PENALTY_SEC,
    WEIGHT_REFILL_PER_SEC,
    WEIGHT_SOFT_LIMIT,
)

_PRINT_LOCK = threading.Lock()


def log(msg: str) -> None:
    """Потокобезопасный вывод."""
    with _PRINT_LOCK:
        print(msg, flush=True)


# ─────────────────────────────────────────────────────────────
# Токен-бакет
# ─────────────────────────────────────────────────────────────
class WeightLimiter:
    """Потокобезопасный токен-бакет. Единица — вес запроса Binance."""

    def __init__(self, capacity: float, refill_per_sec: float) -> None:
        self.capacity = float(capacity)
        self.refill = float(refill_per_sec)
        self._tokens = float(capacity)
        self._ts = time.monotonic()
        self._lock = threading.Lock()
        self._pause_until = 0.0

    def _refill_locked(self) -> None:
        now = time.monotonic()
        elapsed = now - self._ts
        if elapsed > 0:
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill)
            self._ts = now

    def acquire(self, weight: float = 1.0) -> None:
        """Блокирует поток, пока не наберётся нужный вес."""
        while True:
            with self._lock:
                now = time.monotonic()
                if now < self._pause_until:
                    wait = self._pause_until - now
                else:
                    self._refill_locked()
                    if self._tokens >= weight:
                        self._tokens -= weight
                        return
                    deficit = weight - self._tokens
                    wait = deficit / self.refill if self.refill > 0 else 1.0
            time.sleep(min(max(wait, 0.01), 5.0))

    def penalize(self, seconds: float) -> None:
        """Глобальная пауза для всех потоков после 429 или 418."""
        with self._lock:
            target = time.monotonic() + max(seconds, 0.0)
            if target > self._pause_until:
                self._pause_until = target

    def observe_used_weight(self, used: float) -> None:
        """Мягкое торможение при приближении к лимиту биржи."""
        if used >= WEIGHT_SOFT_LIMIT:
            self.penalize(WEIGHT_PENALTY_SEC)


LIMITER = WeightLimiter(WEIGHT_CAPACITY, WEIGHT_REFILL_PER_SEC)


# ─────────────────────────────────────────────────────────────
# Сессия
# ─────────────────────────────────────────────────────────────
def _build_session() -> requests.Session:
    s = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=MAX_WORKERS * 2,
        pool_maxsize=MAX_WORKERS * 4,
        max_retries=0,
    )
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    return s


SESSION = _build_session()


# ─────────────────────────────────────────────────────────────
# Основной запрос
# ─────────────────────────────────────────────────────────────
def get_json(
    url: str,
    params: dict | None = None,
    quiet_400: bool = False,
    weight: int = 1,
    timeout: tuple = REQUEST_TIMEOUT,
) -> Any:
    """GET с токен-бакетом, ретраями и уважением Retry-After.

    Возвращает разобранный JSON или None. Никогда не бросает исключение.
    """
    last_err = ""

    for attempt in range(HTTP_RETRIES):
        LIMITER.acquire(weight)
        try:
            r = SESSION.get(url, params=params, timeout=timeout)

            used = r.headers.get("X-MBX-USED-WEIGHT-1M")
            if used:
                try:
                    LIMITER.observe_used_weight(float(used))
                except (TypeError, ValueError):
                    pass

            if r.status_code == 400 and quiet_400:
                return None

            if r.status_code in (418, 429):
                retry_after = r.headers.get("Retry-After")
                try:
                    delay = float(retry_after) if retry_after else 5.0 * (attempt + 1)
                except (TypeError, ValueError):
                    delay = 5.0 * (attempt + 1)
                LIMITER.penalize(delay)
                last_err = f"HTTP {r.status_code}, пауза {delay:.0f}с"
                continue

            if r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                time.sleep(HTTP_BACKOFF_BASE * (2 ** attempt))
                continue

            r.raise_for_status()
            return r.json()

        except requests.exceptions.RequestException as e:
            last_err = f"{type(e).__name__}: {e}"
            time.sleep(HTTP_BACKOFF_BASE * (2 ** attempt))
        except ValueError as e:
            last_err = f"Некорректный JSON: {e}"
            break

    log(f"[HTTP] {url} — {last_err}")
    return None


# ─────────────────────────────────────────────────────────────
# Универсальный кэш на время прогона
# ─────────────────────────────────────────────────────────────
class RunCache:
    """Потокобезопасный кэш ключ-значение, живёт один прогон."""

    def __init__(self) -> None:
        self._data: dict[Any, Any] = {}
        self._lock = threading.Lock()

    def get(self, key: Any) -> Any:
        with self._lock:
            return self._data.get(key)

    def set(self, key: Any, value: Any) -> None:
        with self._lock:
            self._data[key] = value

    def get_or_call(self, key: Any, producer) -> Any:
        """Возвращает значение из кэша либо вычисляет и сохраняет."""
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value)
        return value

    def drop_prefix(self, prefix: Any) -> None:
        """Удаляет все записи, чей ключ — кортеж с данным первым элементом."""
        with self._lock:
            doomed = [
                k for k in self._data
                if isinstance(k, tuple) and k and k[0] == prefix
            ]
            for k in doomed:
                self._data.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()

    def size(self) -> int:
        with self._lock:
            return len(self._data)
