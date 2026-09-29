from pathlib import Path
import logging

from main import _safe_log_level


def test_container_disables_access_logs_that_would_include_location_query_strings():
    dockerfile = Path(__file__).with_name("Dockerfile").read_text(encoding="utf-8")
    assert "--no-access-log" in dockerfile


def test_backend_never_enables_verbose_application_logs_from_environment():
    assert _safe_log_level("DEBUG") == logging.WARNING
    assert _safe_log_level("INFO") == logging.WARNING
    assert _safe_log_level("ERROR") == logging.ERROR
