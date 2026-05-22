"""
Browser fixtures.

Provides:
    driver — a function-scoped WebDriver instance, created fresh for every
             test and guaranteed to be quit afterwards regardless of outcome.

This is intentionally the simplest fixture module. All browser configuration
logic (options, arguments, Grid vs local routing) lives in:

    utilities/driver_factory.py  — creates the driver from a TestConfig
    config/browser_config.py     — per-browser options and arguments

This fixture is only responsible for the pytest lifecycle: create before
the test, quit after the test, warn if quitting fails.

Design decisions:

    Function scope (not session):
        Each test gets a clean browser with no cookies, no localStorage,
        no navigation history from a previous test. A session-scoped driver
        would share all of that state and turn test-ordering into a hidden
        dependency. The cost is one browser launch per test — acceptable
        for a UI suite, and eliminated entirely for API-only tests that
        don't request this fixture.

    No implicit wait:
        TestConfig has an implicit_wait field but it is deliberately not
        applied here. Mixing implicit and explicit waits produces
        unpredictable timing: Selenium waits up to implicit_wait for an
        element to appear, and WebDriverWait then waits on top of that.
        BasePage uses explicit waits everywhere, so implicit_wait stays
        at zero (Selenium's default). page_load_timeout is set inside
        driver_factory.py where it belongs.

    Try/except on quit:
        The browser can crash or be killed externally between the test
        ending and teardown running — particularly common in headless CI
        environments under memory pressure. A failed quit must not mark
        a passing test as failed. We warn and move on.
"""

import logging

import pytest

from utilities.driver_factory import create_driver

logger = logging.getLogger(__name__)


@pytest.fixture(scope="function")
def driver(test_config):
    """
    Create and yield a WebDriver instance for a single test.

    Automatically routes to a local browser (via Selenium Manager) or
    a remote Selenium Grid node depending on whether SELENIUM_HUB_URL
    is set in the environment. See utilities/driver_factory.py for the
    routing logic.

    Teardown:
        driver.quit() is called after every test — pass, fail, or error.
        If quit raises (browser crashed, process already gone), a warning
        is logged but the exception is suppressed so the test result is
        not affected.

    Scope: function
        A new browser instance for every test. See module docstring for
        why session scope is the wrong choice here.

    Example:
        def test_homepage_loads(driver, test_config):
            driver.get(test_config.base_url)
            assert "Ecommerce" in driver.title
    """
    logger.info(
        f"driver: launching {test_config.browser} "
        f"({'headless' if test_config.headless else 'headed'}) "
        f"{'[Grid]' if test_config.remote_execution else '[local]'}"
    )

    web_driver = create_driver(test_config)

    yield web_driver

    logger.info("driver: test complete, quitting browser")
    try:
        web_driver.quit()
    except Exception as e:
        logger.warning(f"driver: quit failed (browser may have crashed): {e}")