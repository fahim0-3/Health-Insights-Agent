"""Privacy-safe structured logging for operational failures.

Logs deliberately omit report text, chat content, credentials, patient details,
and raw exception messages. Use only the small allow-list of operational fields.
"""

import json
import logging


SAFE_CONTEXT_FIELDS = {
    "component",
    "operation",
    "provider",
    "model",
    "status",
    "error_type",
}


def get_logger(name):
    """Return a standard logger; deployment controls its destination and retention."""
    return logging.getLogger(name)


def log_event(logger, event, level=logging.INFO, **context):
    """Write one structured event using only approved, non-sensitive fields."""
    safe_context = {
        key: str(value)
        for key, value in context.items()
        if key in SAFE_CONTEXT_FIELDS and value is not None
    }
    logger.log(level, json.dumps({"event": event, "context": safe_context}, sort_keys=True))


def log_exception(logger, event, error, **context):
    """Log an exception category without recording its potentially sensitive text."""
    log_event(
        logger,
        event,
        level=logging.ERROR,
        error_type=type(error).__name__,
        **context,
    )
