"""In-memory log ring buffer with fan-out to WebSocket subscribers.

Captures structlog events (via a processor inserted before the renderer)
and stdlib log records (via a Handler) so the Logs page can show a
unified live stream without having to read files off disk.
"""

from __future__ import annotations

import contextlib
import logging
from collections import deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any

import anyio
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream

MAX_HISTORY = 500
SUBSCRIBER_BUFFER = 1000


class LogBuffer:
    def __init__(self, maxlen: int = MAX_HISTORY) -> None:
        self._history: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._subscribers: set[MemoryObjectSendStream[dict[str, Any]]] = set()
        self._lock = Lock()

    def push(self, entry: dict[str, Any]) -> None:
        with self._lock:
            self._history.append(entry)
            subs = list(self._subscribers)
        for send in subs:
            try:
                send.send_nowait(entry)
            except anyio.WouldBlock:
                pass
            except anyio.ClosedResourceError:
                pass
            except anyio.BrokenResourceError:
                pass

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._history)

    def subscribe(
        self,
    ) -> tuple[
        MemoryObjectSendStream[dict[str, Any]],
        MemoryObjectReceiveStream[dict[str, Any]],
    ]:
        send, receive = anyio.create_memory_object_stream[dict[str, Any]](SUBSCRIBER_BUFFER)
        with self._lock:
            self._subscribers.add(send)
        return send, receive

    def unsubscribe(self, send: MemoryObjectSendStream[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(send)
        with contextlib.suppress(Exception):
            send.close()


log_buffer = LogBuffer()


def _safe(value: Any) -> Any:
    if isinstance(value, str | int | float | bool | type(None)):
        return value
    return str(value)


def structlog_capture_processor(
    logger: Any,
    method_name: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """structlog processor: copies each event into the ring buffer.

    Must run after ``TimeStamper`` + ``add_log_level`` but before the
    console/JSON renderer so we capture the structured data rather than
    the rendered string.
    """
    entry = {k: _safe(v) for k, v in event_dict.items()}
    entry.setdefault("source", "trove")
    log_buffer.push(entry)
    return event_dict


class LogBufferHandler(logging.Handler):
    """stdlib handler that forwards uvicorn/access/etc. into the buffer."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry: dict[str, Any] = {
                "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                "level": record.levelname.lower(),
                "event": record.getMessage(),
                "logger": record.name,
                "source": "stdlib",
            }
            if record.exc_info:
                entry["exc"] = logging.Formatter().formatException(record.exc_info)
            log_buffer.push(entry)
        except Exception:  # pragma: no cover
            pass
