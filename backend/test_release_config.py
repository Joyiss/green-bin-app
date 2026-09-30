from pathlib import Path
import logging

from main import _configured_log_level


def test_container_disables_access_logs_that_would_include_location_query_strings():
    dockerfile = Path(__file__).with_name("Dockerfile").read_text(encoding="utf-8")
    assert "--no-access-log" in dockerfile


def test_backend_honors_configured_root_log_level_without_suppressing_info():
    assert _configured_log_level("DEBUG") == logging.DEBUG
    assert _configured_log_level("INFO") == logging.INFO
    assert _configured_log_level("ERROR") == logging.ERROR
    assert _configured_log_level("invalid") == logging.WARNING


def test_sensitive_namespaces_stay_redacted_while_operations_remain_visible():
    assert logging.getLogger("services").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("routes").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("httpx").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("uvicorn.access").getEffectiveLevel() == logging.WARNING
    assert logging.getLogger("greenbin.operations").isEnabledFor(logging.INFO)
