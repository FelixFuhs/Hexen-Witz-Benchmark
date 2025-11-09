from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, Optional


_processors: Iterable[Callable[[logging.Logger, str, Dict[str, Any]], Dict[str, Any]]] = []
_wrapper_factory: Optional[Callable[[logging.Logger], "BoundLogger"]] = None


class BoundLogger:
    def __init__(self, logger: logging.Logger, processors: Iterable[Callable[[logging.Logger, str, Dict[str, Any]], Dict[str, Any]]]):
        self._logger = logger
        self._processors = list(processors)
        self._context: Dict[str, Any] = {}

    def bind(self, **kwargs: Any) -> "BoundLogger":
        self._context.update(kwargs)
        return self

    def _log(self, level: str, event: str, **kwargs: Any) -> None:
        record: Dict[str, Any] = {"event": event, **self._context, **kwargs}
        for processor in self._processors:
            record = processor(self._logger, level, record)
        message = record.pop("event", "")
        self._logger.log(getattr(logging, level.upper(), logging.INFO), message, extra={"structlog": record})

    def info(self, event: str, **kwargs: Any) -> None:
        self._log("info", event, **kwargs)

    def warning(self, event: str, **kwargs: Any) -> None:
        self._log("warning", event, **kwargs)

    def error(self, event: str, **kwargs: Any) -> None:
        self._log("error", event, **kwargs)

    def debug(self, event: str, **kwargs: Any) -> None:
        self._log("debug", event, **kwargs)


class _TimeStamper:
    def __init__(self, fmt: str = "iso") -> None:
        self._fmt = fmt

    def __call__(self, logger: logging.Logger, level: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        if self._fmt == "iso":
            event_dict.setdefault("timestamp", datetime.utcnow().isoformat() + "Z")
        return event_dict


class _AddLogLevel:
    def __call__(self, logger: logging.Logger, level: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        event_dict.setdefault("level", level.lower())
        return event_dict


class _KeyValueRenderer:
    def __init__(self, sort_keys: bool = False) -> None:
        self._sort_keys = sort_keys

    def __call__(self, logger: logging.Logger, level: str, event_dict: Dict[str, Any]) -> Dict[str, Any]:
        items = sorted(event_dict.items()) if self._sort_keys else event_dict.items()
        rendered = " ".join(f"{key}={value}" for key, value in items)
        return {"event": rendered}


class processors:  # type: ignore[override]
    TimeStamper = _TimeStamper
    add_log_level = _AddLogLevel()
    KeyValueRenderer = _KeyValueRenderer


def configure(*, wrapper_class: Optional[Callable[[logging.Logger], BoundLogger]] = None, processors: Optional[Iterable[Callable[[logging.Logger, str, Dict[str, Any]], Dict[str, Any]]]] = None) -> None:
    global _wrapper_factory, _processors
    _wrapper_factory = wrapper_class
    _processors = processors or []


def make_filtering_bound_logger(level: int) -> Callable[[logging.Logger], BoundLogger]:
    def factory(logger: logging.Logger) -> BoundLogger:
        logger.setLevel(level)
        return BoundLogger(logger, _processors)

    return factory


def get_logger(name: Optional[str] = None) -> BoundLogger:
    logger = logging.getLogger(name)
    if _wrapper_factory is not None:
        return _wrapper_factory(logger)
    return BoundLogger(logger, _processors)
