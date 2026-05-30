"""
Base page class for the ecommerce test suite.

All page objects inherit from this class. It provides:
    - Element finding with explicit waits and stale-element retry
    - Interaction helpers (click, enter_text, get_text, etc.)
    - State checking (is_visible, is_present, is_clickable)
    - Wait helpers (URL, title, element disappear)
    - Scrolling utilities
    - JavaScript execution
    - Mouse action helpers
    - React-aware page load detection

React loading note:
    This app is a React SPA. On first load, App.js calls checkAuth()
    which shows a <div class="loading">Loading...</div> while it
    verifies the JWT. All page objects call wait_for_app_ready() after
    navigating to ensure the app has finished mounting before any
    interaction happens.
"""

import logging
from typing import Any, List, Optional, Tuple, Union

from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from config.settings import TestConfig

logger = logging.getLogger(__name__)


class BasePage:
    """
    Base page class providing shared utilities for all page objects.

    Args:
        driver: Selenium WebDriver instance.
        config: TestConfig holding base_url, timeouts, etc.
    """

    def __init__(self, driver: WebDriver, config: TestConfig):
        self.driver           = driver
        self.config           = config
        self.base_url         = config.base_url.rstrip("/")
        self.default_timeout  = config.explicit_wait
        self.poll_frequency   = 0.5

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def open(self, path: str = "") -> "BasePage":
        """
        Navigate to base_url + path and wait for the app to be ready.

        Args:
            path: URL path relative to base_url, e.g. "/products".
                  Leading slash is normalised automatically.

        Returns:
            self for method chaining.
        """
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url
        logger.debug(f"{self.__class__.__name__}: navigating to {url}")
        self.driver.get(url)
        self.wait_for_app_ready()
        return self

    def refresh(self) -> "BasePage":
        """Refresh the current page and wait for the app to be ready."""
        self.driver.refresh()
        self.wait_for_app_ready()
        return self

    def go_back(self) -> "BasePage":
        """Navigate back in browser history."""
        self.driver.back()
        return self


    # ------------------------------------------------------------------
    # React-aware load detection
    # ------------------------------------------------------------------

    def wait_for_app_ready(self, timeout: Optional[int] = None) -> "BasePage":
        """
        Wait until the React app has finished its initial mount.

        The app renders <div class="loading">Loading...</div> while
        App.checkAuth() runs. This method waits for that element to
        disappear AND for document.readyState to be 'complete'.

        This is called automatically by open() and refresh(). Call it
        manually if you navigate via JavaScript or inject a token and
        refresh the page in a fixture.

        Args:
            timeout: Seconds to wait. Uses default_timeout if None.

        Returns:
            self for method chaining.
        """
        timeout = self.default_timeout if timeout is None else timeout

        # Step 1: document ready
        WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
            lambda d: d.execute_script("return document.readyState") == "complete",
            message=f"Page load timed out after {timeout}s",
        )

        # Step 2: React loading spinner gone
        # The spinner may not appear at all (e.g. when already authenticated),
        # so we only wait if it is currently present.
        try:
            spinner = self.driver.find_element(By.CSS_SELECTOR, ".loading")
            if spinner.is_displayed():
                WebDriverWait(
                    self.driver, timeout, poll_frequency=self.poll_frequency
                ).until_not(
                    EC.visibility_of_element_located((By.CSS_SELECTOR, ".loading")),
                    message="React loading spinner did not disappear",
                )
        except NoSuchElementException:
            pass  # Spinner is not present — app is already ready

        return self

    # ------------------------------------------------------------------
    # Element finding (with stale-element retry)
    # ------------------------------------------------------------------

    def find_element(
        self,
        locator: Tuple[str, str],
        timeout: Optional[int] = None,
        retries: int = 2,
    ) -> WebElement:
        """
        Find a single element with explicit wait and stale-element retry.

        Args:
            locator:  (By.TYPE, "value") tuple.
            timeout:  Seconds to wait. Uses default_timeout if None.
            retries:  Retry attempts on StaleElementReferenceException.

        Returns:
            The found WebElement.

        Raises:
            TimeoutException: If element not found after all retries.
        """
        timeout = self.default_timeout if timeout is None else timeout

        for attempt in range(retries):
            try:
                wait = WebDriverWait(
                    self.driver, timeout, poll_frequency=self.poll_frequency
                )
                return wait.until(
                    EC.presence_of_element_located(locator),
                    message=f"Element not found: {locator}",
                )
            except StaleElementReferenceException:
                if attempt < retries - 1:
                    continue
                raise

        raise TimeoutException(
            f"Element not found after {retries} retries: {locator}"
        )

    def find_elements(
        self,
        locator: Tuple[str, str],
        timeout: Optional[int] = None,
        retries: int = 2,
    ) -> List[WebElement]:
        """
        Find multiple elements with explicit wait and stale-element retry.

        Returns an empty list if no elements are found (never raises).

        Args:
            locator:  (By.TYPE, "value") tuple.
            timeout:  Seconds to wait. Uses default_timeout if None.
            retries:  Retry attempts on StaleElementReferenceException.

        Returns:
            List of WebElements, or [] if none found.
        """
        timeout = self.default_timeout if timeout is None else timeout

        for attempt in range(retries):
            try:
                wait = WebDriverWait(
                    self.driver, timeout, poll_frequency=self.poll_frequency
                )
                wait.until(EC.presence_of_all_elements_located(locator))
                return self.driver.find_elements(*locator)
            except TimeoutException:
                return []
            except StaleElementReferenceException:
                if attempt < retries - 1:
                    continue
                return []

        return []

    # ------------------------------------------------------------------
    # Element interaction
    # ------------------------------------------------------------------

    def click(
        self,
        locator: Tuple[str, str],
        timeout: Optional[int] = None,
        use_js: bool = False,
    ) -> "BasePage":
        """
        Click an element. Falls back to JavaScript click if intercepted.

        Args:
            locator:  (By.TYPE, "value") tuple.
            timeout:  Seconds to wait for clickability.
            use_js:   Force JavaScript click without trying native first.

        Returns:
            self for method chaining.
        """
        timeout = self.default_timeout if timeout is None else timeout

        try:
            wait    = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            element = wait.until(EC.element_to_be_clickable(locator))
            self.scroll_to_element(element)

            if use_js:
                self._js_click(element)
            else:
                element.click()

        except (ElementClickInterceptedException, ElementNotInteractableException):
            element = self.find_element(locator, timeout)
            self._js_click(element)

        return self

    def enter_text(
        self,
        locator: Tuple[str, str],
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """
        Type text into an input field.

        Args:
            locator:     (By.TYPE, "value") tuple.
            text:        Text to type.
            clear_first: Clear the field before typing (default True).
            press_enter: Send ENTER key after typing (default False).
            timeout:     Seconds to wait for interactability.

        Returns:
            self for method chaining.
        """
        timeout = self.default_timeout if timeout is None else timeout
        wait    = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
        element = wait.until(
            EC.element_to_be_clickable(locator),
            message=f"Input not interactable: {locator}",
        )

        if clear_first:
            element.clear()

        element.send_keys(text)

        if press_enter:
            element.send_keys(Keys.ENTER)

        return self

    def get_text(
        self,
        locator: Tuple[str, str],
        timeout: Optional[int] = None,
    ) -> str:
        """Get visible text from an element."""
        return self.find_element(locator, timeout).text.strip()

    def get_attribute(
        self,
        locator: Tuple[str, str],
        attribute: str,
        timeout: Optional[int] = None,
    ) -> str:
        """Get attribute value from an element."""
        return self.find_element(locator, timeout).get_attribute(attribute)

    def select_dropdown_by_text(
        self,
        locator: Tuple[str, str],
        text: str,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Select a <select> dropdown option by visible text."""
        from selenium.webdriver.support.select import Select

        element = self.find_element(locator, timeout)
        Select(element).select_by_visible_text(text)
        return self

    def select_dropdown_by_value(
        self,
        locator: Tuple[str, str],
        value: str,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Select a <select> dropdown option by value attribute."""
        from selenium.webdriver.support.select import Select

        element = self.find_element(locator, timeout)
        Select(element).select_by_value(value)
        return self

    # ------------------------------------------------------------------
    # Element state checking
    # ------------------------------------------------------------------

    def is_element_visible(
        self,
        locator: Tuple[str, str],
        timeout: int = 5,
    ) -> bool:
        """Return True if the element is visible within timeout seconds."""
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
                EC.visibility_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    def is_element_present(
        self,
        locator: Tuple[str, str],
        timeout: int = 2,
    ) -> bool:
        """Return True if the element exists in the DOM (may not be visible)."""
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
                EC.presence_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    def is_element_clickable(
        self,
        locator: Tuple[str, str],
        timeout: int = 2,
    ) -> bool:
        """Return True if the element is visible and enabled."""
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
                EC.element_to_be_clickable(locator)
            )
            return True
        except TimeoutException:
            return False

    def wait_for_element_to_disappear(
        self,
        locator: Tuple[str, str],
        timeout: int = 10,
    ) -> bool:
        """
        Wait for an element to leave the DOM or become invisible.

        Useful for loading spinners, toast notifications, and modals.

        Returns:
            True if it disappeared, False if timeout was reached.
        """
        try:
            WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until_not(
                EC.presence_of_element_located(locator)
            )
            return True
        except TimeoutException:
            return False

    # ------------------------------------------------------------------
    # URL and title waits
    # ------------------------------------------------------------------

    def wait_for_url_contains(
        self,
        text: str,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Wait until the current URL contains text."""
        timeout = self.default_timeout if timeout is None else timeout
        WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
            EC.url_contains(text),
            message=f"URL does not contain '{text}' after {timeout}s",
        )
        return self

    def wait_for_url_to_be(
        self,
        url: str,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Wait until the current URL exactly matches url."""
        timeout = self.default_timeout if timeout is None else timeout
        WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
            EC.url_to_be(url),
            message=f"URL '{self.driver.current_url}' does not match '{url}'",
        )
        return self

    def wait_for_title_contains(
        self,
        text: str,
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Wait until the page title contains text."""
        timeout = self.default_timeout if timeout is None else timeout
        WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency).until(
            EC.title_contains(text),
            message=f"Title does not contain '{text}' after {timeout}s",
        )
        return self

    # ------------------------------------------------------------------
    # Scrolling
    # ------------------------------------------------------------------

    def scroll_to_element(
        self,
        locator_or_element: Union[Tuple[str, str], WebElement],
        timeout: Optional[int] = None,
    ) -> "BasePage":
        """Scroll an element into the viewport centre."""
        if isinstance(locator_or_element, tuple):
            element = self.find_element(locator_or_element, timeout)
        else:
            element = locator_or_element

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        return self

    def scroll_to_top(self) -> "BasePage":
        """Scroll to the top of the page."""
        self.driver.execute_script("window.scrollTo(0, 0);")
        return self

    def scroll_to_bottom(self) -> "BasePage":
        """Scroll to the bottom of the page."""
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        return self


    # ------------------------------------------------------------------
    # JavaScript execution
    # ------------------------------------------------------------------

    def execute_script(self, script: str, *args) -> Any:
        """Execute JavaScript and return the result."""
        return self.driver.execute_script(script, *args)

    def _js_click(self, element: WebElement) -> None:
        """Click element using JavaScript (internal fallback)."""
        self.driver.execute_script("arguments[0].click();", element)


    # ------------------------------------------------------------------
    # Mouse actions
    # ------------------------------------------------------------------

    def hover_over(self, locator: Tuple[str, str]) -> "BasePage":
        """Move the mouse over an element."""
        element = self.find_element(locator)
        ActionChains(self.driver).move_to_element(element).perform()
        return self

    def double_click(self, locator: Tuple[str, str]) -> "BasePage":
        """Double-click an element."""
        element = self.find_element(locator)
        ActionChains(self.driver).double_click(element).perform()
        return self

    def right_click(self, locator: Tuple[str, str]) -> "BasePage":
        """Right-click (context menu) an element."""
        element = self.find_element(locator)
        ActionChains(self.driver).context_click(element).perform()
        return self
    # ------------------------------------------------------------------
    # Page info properties
    # ------------------------------------------------------------------

    @property
    def current_url(self) -> str:
        """Current page URL."""
        return self.driver.current_url

    @property
    def page_title(self) -> str:
        """Current browser tab title."""
        return self.driver.title

    @property
    def page_source(self) -> str:
        """Current page HTML source."""
        return self.driver.page_source

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def take_screenshot(self, filename: str) -> bool:
        """Save a screenshot to filename. Returns True on success."""
        try:
            self.driver.save_screenshot(filename)
            return True
        except Exception as e:
            logger.warning(f"Screenshot failed: {e}")
            return False

    def get_element_count(self, locator: Tuple[str, str]) -> int:
        """Return the number of elements matching locator."""
        return len(self.find_elements(locator, timeout=2))

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(url={self.current_url})"