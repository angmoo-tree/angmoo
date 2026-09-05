"""Load packaged logging defaults without reconfiguring a host application's handlers.

App factories do not call fileConfig/dictConfig or install handlers. Uvicorn's
normal CLI startup/reloader receives the same console configuration it used
before AR-G3. The desktop sidecar continues to opt out of Uvicorn logging.
"""
from __future__ import annotations

from configparser import ConfigParser, Error as ConfigParserError
import logging
from pathlib import Path
import sys


class RuntimeLoggingConfigurationError(RuntimeError):
    pass


def logging_config_path() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = getattr(sys, "_MEIPASS", None)
        if not bundle_root:
            raise RuntimeLoggingConfigurationError("runtime_logging_configuration_missing")
        root = Path(bundle_root)
    else:
        root = Path(__file__).resolve().parents[2]
    path = root / "logging.ini"
    if not path.is_file():
        raise RuntimeLoggingConfigurationError("runtime_logging_configuration_missing")
    return path


def _level(config: ConfigParser, section: str) -> str:
    value = config[section]["level"].strip().upper()
    if not isinstance(logging.getLevelName(value), int):
        raise ValueError("invalid logging level")
    return value


def _read_logging_config() -> ConfigParser:
    config = ConfigParser(interpolation=None)
    try:
        with logging_config_path().open(encoding="utf-8") as source:
            config.read_file(source)
        for section in ("logger_root", "logger_uvicorn", "logger_uvicorn_error", "logger_uvicorn_access"):
            _level(config, section)
        for section in ("logger_uvicorn", "logger_uvicorn_access"):
            config.getboolean(section, "propagate")
        for name, formatter in (("default", "DefaultFormatter"), ("access", "AccessFormatter")):
            if config[f"formatter_{name}"]["class"] != f"uvicorn.logging.{formatter}":
                raise ValueError("unsupported logging formatter")
            if not config[f"formatter_{name}"]["format"]:
                raise ValueError("missing logging format")
            if config[f"handler_{name}"]["stream"] not in {"stdout", "stderr"}:
                raise ValueError("unsupported logging stream")
    except (OSError, ConfigParserError, KeyError, ValueError) as exc:
        raise RuntimeLoggingConfigurationError("runtime_logging_configuration_invalid") from exc
    return config


def configure_application_logging() -> None:
    """Validate deployment resources and apply only an untouched root default.

    An embedding server, test runner, or caller owns its existing handlers and
    explicit level. Repeated app creation neither replaces nor closes them.
    """
    config = _read_logging_config()
    root = logging.getLogger()
    if not root.handlers and root.level == logging.WARNING:
        root.setLevel(_level(config, "logger_root"))


def uvicorn_logging_config() -> dict:
    """Return Uvicorn's prior configuration, read from the packaged INI.

    Uvicorn consumes this at server/reloader startup, never from an app factory.
    A missing GUI-process stream has no handler rather than a formatter trying
    to call isatty() on None. Desktop launches still pass log_config=None.
    """
    config = _read_logging_config()
    formatters, handlers = {}, {}
    for name in ("default", "access"):
        formatters[name] = {
            "()": config[f"formatter_{name}"]["class"],
            "fmt": config[f"formatter_{name}"]["format"],
        }
        if name == "default" or sys.stdout is None:
            formatters[name]["use_colors"] = False if sys.stdout is None else None
        stream = config[f"handler_{name}"]["stream"]
        if getattr(sys, stream) is None:
            handlers[name] = {"class": "logging.NullHandler"}
        else:
            handlers[name] = {"formatter": name, "class": "logging.StreamHandler", "stream": f"ext://sys.{stream}"}
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": formatters,
        "handlers": handlers,
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": _level(config, "logger_uvicorn"), "propagate": config.getboolean("logger_uvicorn", "propagate")},
            "uvicorn.error": {"level": _level(config, "logger_uvicorn_error")},
            "uvicorn.access": {"handlers": ["access"], "level": _level(config, "logger_uvicorn_access"), "propagate": config.getboolean("logger_uvicorn_access", "propagate")},
        },
    }
