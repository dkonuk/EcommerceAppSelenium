"""
Pytest configuration — hooks and plugin declarations only.

Fixtures live in their own modules under fixtures/ and are loaded
via pytest_plugins below. This file is intentionally lean: if you
are adding a fixture here, it belongs in a fixtures/ module instead.

Hook responsibilities:
    pytest_plugins       — declares fixture modules for auto-discovery
    pytest_sessionstart  — cleans up stale screenshots before the run
    pytest_addoption     — registers CLI flags (--browser, --headless, etc.)
    pytest_configure     — suppresses noisy loggers, prints session banner
    pytest_runtest_makereport — captures screenshot/source/logs on failure
"""

import logging
import shutil
from pathlib import Path

import pytest
from dotenv import load_dotenv

from utilities.screenshot_manager import capture_failure_artifacts

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fixture module declarations
# pytest loads these modules and makes their fixtures available everywhere.
# Order does not imply dependency — pytest resolves that itself.
# ---------------------------------------------------------------------------
pytest_plugins = [
    "fixtures.config_fixtures",
    "fixtures.database_fixtures",
    "fixtures.auth_fixtures",
    "fixtures.browser_fixtures",
]


# ---------------------------------------------------------------------------
# Session lifecycle hooks
# ---------------------------------------------------------------------------

def pytest_sessionstart(session):
    """
    Runs once before any test is collected or executed.
    Clears the screenshots directory so each run starts with a clean slate.
    """
    screenshot_dir = Path("screenshots")

    if not screenshot_dir.exists():
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created screenshots directory: {screenshot_dir}")
        return

    deleted, failed = 0, 0
    for item in screenshot_dir.iterdir():
        try:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
            deleted += 1
        except Exception as e:
            logger.warning(f"Could not delete {item}: {e}")
            failed += 1

    logger.info(
        f"Screenshots cleared: {deleted} removed"
        + (f", {failed} failed" if failed else "")
    )


def pytest_addoption(parser):
    """Registers custom CLI flags for the test suite."""

    parser.addoption(
        "--browser",
        action="store",
        default="chrome",
        dest="browser",
        help="Browser to run tests in: chrome (default), firefox, edge",
    )
    parser.addoption(
        "--url",
        action="store",
        default="",
        dest="url",
        help="Override the base URL for the frontend (e.g. http://staging:3000)",
    )
    parser.addoption(
        "--headless",
        action="store_true",
        default=False,
        dest="headless",
        help="Run the browser in headless mode (no visible window)",
    )
    parser.addoption(
        "--no-screenshots",
        action="store_false",
        default=True,
        dest="save_screenshots",  # retrieved as: config.getoption("save_screenshots")
        help="Disable screenshot capture on test failure",
    )
    parser.addoption(
        "--screenshot-path",
        action="store",
        default="screenshots",
        dest="screenshot_path",  # retrieved as: config.getoption("screenshot_path")
        help="Directory to save failure screenshots in",
    )


def pytest_configure(config):
    """
    Runs after CLI options are parsed, before fixtures or tests execute.

    Responsibilities:
        - Suppresses noisy third-party loggers (logging is owned by pytest.ini)
        - Prints the session banner so the run is easy to identify in logs

    Note: do NOT call setup_logging() here. pytest.ini owns all log
    handler configuration (log_cli, log_file). Calling setup_logging()
    here clears pytest's handlers and causes duplicate output.
    """
    # Suppress third-party noise regardless of the active log level
    logging.getLogger("faker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("selenium.webdriver.remote.remote_connection").setLevel(logging.WARNING)

    # Session banner — written after pytest's handlers are attached
    logger.info("=" * 70)
    logger.info("Test session started")
    logger.info(f"  Browser  : {config.getoption('browser')}")
    logger.info(f"  Headless : {config.getoption('headless')}")
    logger.info(f"  Base URL : {config.getoption('url') or '(default from config)'}")
    logger.info("=" * 70)


# ---------------------------------------------------------------------------
# Test result hooks
# ---------------------------------------------------------------------------

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Runs after each test phase (setup / call / teardown).

    On failure during the call phase, captures three artifacts:
        - screenshot (.png)
        - page source (.html)
        - browser console logs (.log)

    Only fires when a 'driver' fixture is active in the test, so API-only
    tests that have no browser are silently skipped.
    """
    outcome = yield
    report = outcome.get_result()

    if report.when != "call" or not report.failed:
        return

    driver = item.funcargs.get("driver")
    if not driver:
        return

    test_name = item.nodeid
    logger.info(f"Test failed: {test_name} — capturing artifacts")

    artifacts = capture_failure_artifacts(
        driver=driver,
        test_name=test_name,
        screenshot_path="screenshots",
    )

    if artifacts:
        logger.info(f"  Screenshot : {artifacts['screenshot']}")
        logger.info(f"  Page source: {artifacts['page_source']}")
        logger.info(f"  Browser log: {artifacts['logs']}")
    else:
        logger.warning(
            f"Artifact capture failed for {test_name} — browser may have crashed"
        )