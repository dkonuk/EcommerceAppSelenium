"""
Pytest configuration and fixtures

Provides:
    - CLI arguments (--browser, --headless, etc.)
    - Fixtures (driver, test_config, base_url)
    - Hooks (logging setup, screenshot capture on failure)

"""
import pytest
import logging
from dotenv import load_dotenv
import shutil
from pathlib import Path

from api.auth_client import AuthAPIClient
from config.settings import TestConfig
from config.logging_config import setup_logging
from config.browser_config import get_supported_browsers
from utilities.driver_factory import create_driver
from utilities.screenshot_manager import capture_failure_artifacts
from api.admin_client import AdminAPIClient

load_dotenv()

logger = logging.getLogger(__name__)

def pytest_sessionstart(session):
    """
        Pytest Hook: Runs exactly once before the test suite begins.
        Vaporizes all old screenshots so we start with a clean slate.
    """

    screenshot_dir = Path("screenshots")
    if screenshot_dir.exists():
        print(f"Deleting old screenshots in {screenshot_dir}")

        # Iterate through everything inside the folder and delete it
        for item in screenshot_dir.iterdir():
            try:
                if item.is_file():
                    item.unlink() #Delete files
                elif item.is_dir():
                    shutil.rmtree(item) # Delete sub-folders

            except Exception as e:
                print(f"\n[INFO] Creating missing {screenshot_dir} directory.")
            screenshot_dir.mkdir(parents=True, exist_ok=True)

def pytest_addoption(parser):
    parser.addoption(
        "--browser",
        action="store",
        default="chrome",
        help="Browser to use for tests (chrome, firefox, edge)",
    )

    parser.addoption(
        "--url",
        action="store",
        default="",
        help= "Base URL for tests"
    )

    parser.addoption(
        "--headless",
        action="store_true",
        default=False,
        help= "Run browser in headless mode"
    )

    parser.addoption(
        "--no-screenshots",
        action="store_false",
        dest="save_screenshots",
        default=True,
        help= "Disable screenshot capture"
    )

    parser.addoption(
        "--screenshot-path",
        dest="screenshot_path",
        action="store",
        default="screenshots",
        help="Directory to ave screenshots in"
    )

def pytest_configure(config):
    """
    Hook called after command line options are parsed.

    Sets up logging before any test run.
    """
    # Get log level from pytest's -v flags
    verbose= config.option.verbose

    if verbose >= 2: # pytest -vv
        log_level = "DEBUG"
    elif verbose >= 1: # pytest -v
        log_level = "INFO"
    else: # pytest (no -v)
        log_level = "INFO"

    logging.getLogger("faker").setLevel(logging.INFO)
    logging.getLogger("urllib3").setLevel(logging.INFO)  # Mutes Selenium network spam
    logging.getLogger("selenium").setLevel(logging.INFO)

    # Setup logging
    setup_logging(
        log_level=log_level,
        log_file="logs/test_execution.log",
        console_output=True
    )

    logger.info("=" * 80)
    logger.info("Test session started")
    logger.info(f"Browser: {config.option.browser}")
    logger.info(f"Headless: {getattr(config.option, 'headless', False)}")
    logger.info(f"Base URL: {config.option.url}")
    logger.info("=" * 80)

@pytest.fixture
def authenticated_browser(driver, test_config, sterile_database):
    """
    Provides a Selenium WebDriver instance pre-authenticated as a test user.
    Requires the 'sterile_database' fixture to ensure seed data exists.
    """
    auth_client = AuthAPIClient(api_url=test_config.api_url)
    jwt_token = auth_client.get_jwt_token(
        email=test_config.test_user_email,
        password=test_config.test_user_password
    )


    # 2. Navigate to the frontend domain to satisfy Selenium security constraints
    # Hitting a 404 route or the base URL is usually fastest
    driver.get(test_config.base_url)

    # 3. Inject the token into localStorage
    # Note: 'token' is the standard key, but verify in your React app's source
    # if it uses something else like 'authToken' or 'jwt'.
    injection_script = f"window.localStorage.setItem('token', '{jwt_token}');"
    driver.execute_script(injection_script)

    # 4. Refresh the page so React picks up the new localStorage state
    driver.refresh()

    # Yield the pre-authenticated driver to the test
    yield driver

    # Optional Teardown: Clear localStorage after the test if you aren't already
    # destroying the browser session completely.
    # driver.execute_script("window.localStorage.clear();")

@pytest.fixture(scope="session")
def sterile_database(test_config):
    """
    Guarantees a clean, predictable database state before a test starts.
    """
    logger.info("Setting up sterile database for test...")
    admin_api = AdminAPIClient(test_config.api_url)

    admin_api.reset_database()
    admin_api.seed_database()  # Removed the arguments here

    yield

@pytest.fixture(scope="session")
def test_config(request):
    """
    Provide a TestConfig object created from CLI arguments

    Scope: session (created once per test session)
    """

    config = TestConfig.from_pytest_config(request.config)
    logger.debug(f"TestConfig created: {config}")
    return config

@pytest.fixture(scope="function")
def driver(test_config):
    """
    Provide a WebDriver instance for tests

    Scope: function (new driver for each test)

    Automatically:
        - Creates the driver before test
        - Quits the driver after test
        - Captures screenshot if the test fails (via pytest hook)
    """

    logger.info(f"Creating {test_config.browser} driver")

    # Create driver
    driver = create_driver(test_config)

    # Provide to test
    yield driver

    # Cleanup (runs after a test completes)
    logger.info("Test completed, cleaning up driver")
    try:
        driver.quit()
    except Exception as e:
        logger.warning(f"Driver cleanup failed: {e}")




@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """
    Hook called after each test phase (steup, call, teardown).

    Captures screenshot, page source and logs when test fails.

    """
    outcome = yield

    # Get the test report
    report = outcome.get_result()

    # Only capture on test failure (not setup/teardown failure)
    if report.when == "call" and report.failed:
        # Get driver from test fixtures
        driver = item.funcargs.get("driver")

        if driver:
            # Generate an artifact name from test name
            test_name = item.nodeid

            # Capture artifacts
            logger.info(f"Test failed: {test_name}, capturing artifacts")
            artifacts = capture_failure_artifacts(
                driver=driver,
                test_name=test_name,
                screenshot_path="screenshots"
            )

            if artifacts:
                logger.info(f"Artifacts saved: {artifacts['screenshot']}")
                logger.info(f" Page source: {artifacts['page_source']}")
                logger.info(f"Browser logs: {artifacts['logs']}")
            else:
                logger.warning(f"Failed to capture artifacts for {test_name}"
                "(browser may have crashed)")

