"""Tests ensuring operational logs do not retain sensitive health information."""

import json
import logging

from utils.app_logging import get_logger, log_event, log_exception


def test_structured_event_keeps_only_approved_operational_fields(caplog):
    logger = get_logger("tests.privacy_safe_logging")

    with caplog.at_level(logging.INFO, logger=logger.name):
        log_event(
            logger,
            "analysis_generation_started",
            component="model_manager",
            provider="groq",
            model="example-model",
            report_text="patient report must not be logged",
            email="patient@example.com",
            access_token="secret-token",
        )

    payload = json.loads(caplog.records[-1].message)
    assert payload == {
        "context": {
            "component": "model_manager",
            "model": "example-model",
            "provider": "groq",
        },
        "event": "analysis_generation_started",
    }
    assert "patient report" not in caplog.text
    assert "patient@example.com" not in caplog.text
    assert "secret-token" not in caplog.text


def test_exception_log_records_type_without_raw_exception_text(caplog):
    logger = get_logger("tests.privacy_safe_exception")
    error = RuntimeError("report: private clinical finding; token: secret")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        log_exception(logger, "analysis_generation_failed", error, component="chat")

    payload = json.loads(caplog.records[-1].message)
    assert payload["event"] == "analysis_generation_failed"
    assert payload["context"]["error_type"] == "RuntimeError"
    assert "private clinical finding" not in caplog.text
    assert "secret" not in caplog.text
