"""
Configuration fixtures.

Provides:
    test_config — the single session-scoped TestConfig instance that all
                  other fixtures and tests pull settings from.

This module intentionally contains only one fixture. TestConfig carries
the full priority chain (CLI → env → defaults) inside its factory method,
so the fixture itself is just the construction call.
"""

import logging
import pytest

from config.settings import TestConfig

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def test_config(request):
    """
    Build and return the TestConfig for the entire test session.

    Reads CLI flags registered in conftest.pytest_addoption, then falls
    back to environment variables, then to class-level defaults. The full
    priority chain is documented in config/settings.py.

    Scope: session
        Created exactly once per run and shared by every fixture and test.
        Changing CLI flags mid-session has no effect — config is frozen
        at collection time.

    Example:
        def test_something(test_config):
            assert "localhost" in test_config.base_url
    """
    config = TestConfig.from_pytest_config(request.config)
    logger.debug(
        f"TestConfig initialised | "
        f"browser={config.browser} "
        f"headless={config.headless} "
        f"base_url={config.base_url} "
        f"api_url={config.api_url} "
        f"remote={config.remote_execution}"
    )
    return config