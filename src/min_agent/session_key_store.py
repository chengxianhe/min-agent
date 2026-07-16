from __future__ import annotations

import threading


class InvalidSessionKey(ValueError):
    pass


class SessionKeyNotConfigured(RuntimeError):
    pass


class SessionKeyStore:
    def __init__(self) -> None:
        self._key: str | None = None
        self._lock = threading.Lock()

    def configure(self, raw_key: str) -> None:
        if not isinstance(raw_key, str):
            raise InvalidSessionKey("DeepSeek Key must be a string")
        key = raw_key.strip()
        if not key or len(key) > 4096:
            raise InvalidSessionKey("DeepSeek Key must be non-empty and at most 4096 characters")
        with self._lock:
            self._key = key

    def is_configured(self) -> bool:
        with self._lock:
            return self._key is not None

    def require(self) -> str:
        with self._lock:
            if self._key is None:
                raise SessionKeyNotConfigured("DeepSeek Key is not configured for this Web service")
            return self._key

    def clear(self) -> None:
        with self._lock:
            self._key = None
