"""
Configuration management for the test framework.

Priority chain (highest to lowest):
    1. CLI flags       --browser, --url, --headless, etc.
    2. Env variables   TEST_BASE_URL, TEST_BROWSER, TEST_USER_EMAIL, etc.
    3. Defaults        values defined on the dataclass fields below

Typical usage:
    # From within a pytest fixture (reads CLI + env):
    config = TestConfig.from_pytest_config(request.config)

    # From outside pytest (reads env only — useful for standalone scripts):
    config = TestConfig.from_env()
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TestConfig:
    """
    Central configuration object for a test session.

    Validates all values immediately on creation via __post_init__ so that
    bad config surfaces as a clear error before any test runs, not as a
    confusing mid-run failure.

    Examples:
        >>> config = TestConfig(browser="chrome", headless=True)
        >>> config.implicit_wait
        10

        >>> config = TestConfig(implicit_wait=-5)
        ValueError: implicit_wait must be positive, got -5

    Raises:
        ValueError: If any timeout value is not positive, or a path
                    cannot be created.
        TypeError:  If browser is not a string or headless is not boolean.
    """

    # --- Browser ---
    browser: str = "chrome"
    headless: bool = False

    # --- URLs ---
    base_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:3001"

    # --- Timeouts ---
    implicit_wait: int = 10
    explicit_wait: int = 10
    page_load_timeout: int = 60

    # --- Screenshots ---
    screenshot_on_failure: bool = True
    save_screenshots: bool = True
    screenshot_path: str = "screenshots"

    # --- Logging ---
    log_level: str = "INFO"
    log_file: str = "logs/test_execution.log"

    # --- Remote / Grid execution ---
    remote_execution: bool = False
    remote_url: Optional[str] = None

    # --- Test user credentials ---
    # Defaults match the seed data. Override via TEST_USER_EMAIL /
    # TEST_USER_PASSWORD env vars so no credentials live in code for
    # non-default environments.
    test_user_email: str = "user1@test.com"
    test_user_password: str = "password123"

    # ---------------------------------------------------------------------------
    # Validation
    # ---------------------------------------------------------------------------

    def __post_init__(self):
        """Runs automatically after __init__. Validates all fields eagerly."""
        self._validate_types()
        self._validate_browser()
        self._validate_timeouts()
        self._validate_paths()

    def _validate_browser(self):
        """Validate browser name against the supported list in browser_config."""
        from config.browser_config import get_supported_browsers

        supported = get_supported_browsers()
        if self.browser.lower() not in supported:
            raise ValueError(
                f"Unsupported browser '{self.browser}'. "
                f"Supported: {supported}"
            )

    def _validate_timeouts(self):
        """All timeout values must be positive integers."""
        for field_name, value in {
            "implicit_wait": self.implicit_wait,
            "explicit_wait": self.explicit_wait,
            "page_load_timeout": self.page_load_timeout,
        }.items():
            if value <= 0:
                raise ValueError(
                    f"{field_name} must be a positive integer, got {value}"
                )

    def _validate_types(self):
        """Guard against common misconfiguration from env-var parsing."""
        if not isinstance(self.browser, str):
            raise TypeError(
                f"browser must be a string, got {type(self.browser).__name__}"
            )
        if not isinstance(self.headless, bool):
            raise TypeError(
                f"headless must be a boolean, got {type(self.headless).__name__}"
            )
        if not isinstance(self.base_url, str):
            raise TypeError(
                f"base_url must be a string, got {type(self.base_url).__name__}"
            )

    def _validate_paths(self):
        """Create screenshot and log directories if they don't exist."""
        for label, path in [
            ("screenshot_path", self.screenshot_path),
            ("log_file directory", os.path.dirname(self.log_file)),
        ]:
            if path and not os.path.exists(path):
                try:
                    os.makedirs(path, exist_ok=True)
                    logger.debug(f"Created {label} directory: {path}")
                except OSError as e:
                    raise ValueError(
                        f"Cannot create {label} '{path}': {e}"
                    ) from None

    # ---------------------------------------------------------------------------
    # Factory methods
    # ---------------------------------------------------------------------------

    @classmethod
    def from_pytest_config(cls, config):
        """
        Build a TestConfig from pytest's parsed CLI options and env vars.

        Called from the test_config fixture. Uses dest= names (no dashes)
        for getoption() calls — see conftest.pytest_addoption for the mapping
        between flag names and dest names.

        Priority per field:
            URL       — --url CLI flag → TEST_BASE_URL env var → class default
            others    — CLI flag → class default (env vars via from_env() fallback)
        """
        hub_url = os.getenv("SELENIUM_HUB_URL")

        # URL gets a three-level fallback because it's the most likely value
        # to differ between local, CI, and staging environments.
        cli_url = config.getoption("url")           # dest="url" in addoption
        env_url = os.getenv("TEST_BASE_URL", "")
        final_url = cli_url or env_url or cls.base_url  # was: cli_url or cli_url

        return cls(
            browser=config.getoption("browser"),                          # dest="browser"
            headless=config.getoption("headless"),                        # dest="headless"
            base_url=final_url,
            save_screenshots=config.getoption("save_screenshots"),        # dest="save_screenshots"
            screenshot_path=config.getoption("screenshot_path"),          # dest="screenshot_path"
            remote_url=hub_url,
            remote_execution=bool(hub_url),
            test_user_email=os.getenv("TEST_USER_EMAIL", cls.test_user_email),
            test_user_password=os.getenv("TEST_USER_PASSWORD", cls.test_user_password),
        )

    @classmethod
    def from_env(cls):
        """
        Build a TestConfig purely from environment variables.

        Used outside of pytest — standalone scripts, health checks, or
        any context where request.config is not available.
        """
        hub_url = os.getenv("SELENIUM_HUB_URL")

        return cls(
            browser=os.getenv("TEST_BROWSER", cls.browser),
            headless=os.getenv("TEST_HEADLESS", "false").lower() == "true",
            base_url=os.getenv("TEST_BASE_URL", cls.base_url),
            api_url=os.getenv("TEST_API_URL", cls.api_url),
            implicit_wait=int(os.getenv("TEST_IMPLICIT_WAIT", str(cls.implicit_wait))),
            explicit_wait=int(os.getenv("TEST_EXPLICIT_WAIT", str(cls.explicit_wait))),
            remote_url=hub_url,
            remote_execution=bool(hub_url),
            test_user_email=os.getenv("TEST_USER_EMAIL", cls.test_user_email),
            test_user_password=os.getenv("TEST_USER_PASSWORD", cls.test_user_password),
        )