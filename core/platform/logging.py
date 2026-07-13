import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from core.platform.paths import AppPaths

_LOGGER_NAME = "bamboo_workbench"
_HANDLER_MARKER = "_bamboo_workbench_handler"
_REDACTION = "[REDACTED]"
_SECRET_PATTERNS = (
    re.compile(
        r"(?i)(?P<prefix>(?P<quote>[\"']?)api_key(?P=quote)\s*[:=]\s*)"
        r"[^\r\n]*"
    ),
    re.compile(
        r"(?i)(?P<prefix>(?P<quote>[\"']?)authorization(?P=quote)\s*[:=]\s*)"
        r"[^\r\n]*"
    ),
    re.compile(r"(?i)\b(bearer)\b[^\r\n]*"),
)


def redact_secrets(value: object) -> str:
    redacted = str(value)
    redacted = _SECRET_PATTERNS[0].sub(rf"\g<prefix>{_REDACTION}", redacted)
    redacted = _SECRET_PATTERNS[1].sub(rf"\g<prefix>{_REDACTION}", redacted)
    redacted = _SECRET_PATTERNS[2].sub(rf"\1 {_REDACTION}", redacted)
    return redacted


class SecretRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_secrets(record.getMessage())
        record.args = ()
        if record.exc_info:
            formatter = logging.Formatter()
            record.exc_text = redact_secrets(formatter.formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = redact_secrets(record.exc_text)
        return True


def configure_logging(paths: AppPaths) -> logging.Logger:
    paths.logs.mkdir(parents=True, exist_ok=True)
    log_path = (paths.logs / "bamboo-workbench.log").resolve()
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    handler = _find_handler(logger, log_path)
    if handler is None:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=1_048_576,
            backupCount=3,
            encoding="utf-8",
        )
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        handler.addFilter(SecretRedactionFilter())
        logger.addHandler(handler)
    return logger


def close_logging(logger: logging.Logger, paths: AppPaths) -> None:
    log_path = (paths.logs / "bamboo-workbench.log").resolve()
    for handler in tuple(logger.handlers):
        if not getattr(handler, _HANDLER_MARKER, False):
            continue
        if isinstance(handler, RotatingFileHandler) and (
            Path(handler.baseFilename).resolve() == log_path
        ):
            logger.removeHandler(handler)
            handler.close()


def _find_handler(
    logger: logging.Logger,
    log_path: Path,
) -> RotatingFileHandler | None:
    matched: RotatingFileHandler | None = None
    for handler in tuple(logger.handlers):
        if not getattr(handler, _HANDLER_MARKER, False):
            continue
        if isinstance(handler, RotatingFileHandler) and (
            Path(handler.baseFilename).resolve() == log_path
        ):
            matched = handler
            continue
        logger.removeHandler(handler)
        handler.close()
    return matched
