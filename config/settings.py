"""
Configuration management for the test framework

Priority: CLI > Environment Variables > Config File > Defaults
"""
import os
import logging
from dataclasses import dataclass
from typing import Optional
logger = logging.getLogger(__name__)

@dataclass
class TestConfig:
    """Central configuration for test execution with built-in validation.

    Validates configuration values immediately upon creation to fail fast.

    Examples:
        >>> config = TestConfig(browser="chrome", headless=True)
        >>> config.implicit_wait
        10

        >>> # Invalid config fails immediately:
        >>> config = TestConfig(implicit_wait=-5)
        ValueError: implicit_wait must be positive, got -5

    Raises:
        ValueError: If any timeout value is not positive
        TypeError: If browser is not a string or headless is not boolean
     """

    # Test user credentials
    test_user_email: str = "user1@test.com"
    test_user_password: str = "password123"

    # Browser settings
    browser: str = "chrome"
    headless: bool = False

    # URL settings
    base_url: str = "http://localhost:3000/"
    api_url: str = "http://localhost:3001"

    # Timeout settings
    implicit_wait: int = 10
    explicit_wait: int = 10
    page_load_timeout: int = 60

    # Screenshot settings
    screenshot_on_failure: bool = True
    save_screenshots: bool = False
    screenshot_path: str = "screenshots"

    # Logging settings
    log_level: str = "DEBUG"
    log_file: str = "logs/test_execution.log"

    # Remote execution settings
    remote_execution: bool = False
    remote_url: Optional[str] = None

    def __post_init__(self):
        """Validate configuration values after initialization.

        This runs automatically after __init__ completes.
        Ensures the test session fails fast with clear error messages
        """
        # Validate types
        self._validate_types()

        # Validate browser is supported
        self._validate_browser()

        # Validate timeouts are positive
        self._validate_timeouts()

        # Validate paths exist or can be created
        self._validate_paths()

    def _validate_browser(self):
        """Validate browser is supported by checking against browser_config."""
        from config.browser_config import get_supported_browsers

        # Normalize browser name to lowercase
        browser_lower = self.browser.lower()

        # Get a list of supported browsers
        supported_browsers = get_supported_browsers()

        # Check if the browser is in the supported list
        if browser_lower not in supported_browsers:
            raise ValueError(
                f"Invalid browser '{self.browser}' in configuration. "
                f"Supported browsers: {supported_browsers}"
            )

    def _validate_timeouts(self):
        """Validate all timeout values are positive"""
        timeout_fields = {
            'implicit_wait': self.implicit_wait,
            'explicit_wait': self.explicit_wait,
            'page_load_timeout': self.page_load_timeout,
        }
        for field_name, value in timeout_fields.items():
            if value <= 0:
                raise ValueError(
                    f"{field_name} must be positive, got {value}"
                )

    def _validate_types(self):
        """Validate field types are correct"""
        if not isinstance(self.browser, str):
            raise TypeError(
                f"Browser must be string, got {type(self.browser).__name__}"
            )
        if not isinstance(self.headless, bool):
            raise TypeError(
                f"Headless must be boolean, got {type(self.headless).__name__}"
            )
        if not isinstance(self.base_url, str):
            raise TypeError(
                f"Base URL must be string, got {type(self.base_url).__name__}"
            )

    def _validate_paths(self):
        """Validate screenshot and log paths can be created"""
        for path_name, path_value in [
            ('screenshot_path', self.screenshot_path),
            ('log_file', os.path.dirname(self.log_file))
        ]:
            if path_value and not os.path.exists(path_value):
                try:
                    os.makedirs(path_value, exist_ok=True)
                    logger.debug(f"Created directory {path_value}")
                except OSError as e:
                    raise ValueError(
                        f"Cannot create {path_name} directory '{path_value}: {e}"
                    ) from None

    @classmethod
    def from_pytest_config(cls, config):
        """ Create a TestConfig object from pytest config """
        hub_url = os.getenv("SELENIUM_HUB_URL")
        # Priority 1: CLI Argument (--url)
        cli_url = config.getoption("--url")

        # Priority 2: Environment Variable (Docker Compose)
        env_url = os.getenv("TEST_BASE_URL")

        #Fallback chain
        final_url = cli_url or env_url or cls.base_url
        return cls(
            browser=config.getoption("--browser", default=cls.browser),
            headless=config.getoption("--headless", default=cls.headless),
            base_url=final_url,
            save_screenshots=config.getoption("save_screenshots", default=cls.save_screenshots),
            screenshot_path=config.getoption("screenshot_path", default=cls.screenshot_path),
            remote_url=hub_url,
            remote_execution=bool(hub_url)
        )

    @classmethod
    def from_env(cls):
        """ Create a TestConfig object from environment variables """

        hub_url = os.getenv("SELENIUM_HUB_URL")

        return cls(
            test_user_email=os.getenv("TEST_USER_EMAIL", cls.test_user_email),
            test_user_password=os.getenv("TEST_USER_PASSWORD", cls.test_user_password),
            browser=os.getenv("TEST_BROWSER", cls.browser),
            headless=os.getenv("TEST_HEADLESS", "false").lower() == "true",
            base_url=os.getenv("TEST_BASE_URL", cls.base_url),
            implicit_wait=int(os.getenv("TEST_IMPLICIT_WAIT", str(cls.implicit_wait))),
            explicit_wait=int(os.getenv("TEST_EXPLICIT_WAIT", str(cls.explicit_wait))),
            remote_url = hub_url,
            remote_execution=bool(hub_url)
        )


