from typing import Tuple, List, Optional, Union, Any
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException,
    StaleElementReferenceException,
    NoSuchElementException,
    ElementNotInteractableException,
    ElementClickInterceptedException
)

from config.settings import TestConfig


class BasePage:
    """
    Base page class providing common functionality for all page objects.

    All page objects should inherit from this class to get shared utilities
    and maintain consistent interaction patterns across the test suite.

    Attributes:
        driver: Selenium WebDriver instance
        base_url: Application base URL from configuration
        default_timeout: Default wait timeout in seconds
        poll_frequency: Wait poll frequency in seconds
    """
    def __init__(self, driver: WebDriver, config: TestConfig):
        """
        Initialize the BasePage with driver and configuration.
        Args:
            driver: Selenium WebDriver instance
            config: TestConfig instance containing settings
        """

        self.driver = driver
        self.config = config
        self.base_url = config.base_url.rstrip('/')
        self.default_timeout = config.explicit_wait
        self.poll_frequency = 0.5
    # NAVIGATION METHODS

    def open(self, path: str = "") -> 'BasePage':
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url
        self.driver.get(url)
        return self

    def refresh(self) -> 'BasePage':
        """Refresh the current page."""
        self.driver.refresh()
        return self

    def go_back(self) -> 'BasePage':
        """Navigate back in the browser history."""
        self.driver.back()
        return self

    def go_forward(self) -> 'BasePage':
        """"Navigate forward in the browser history."""
        self.driver.forward()
        return self

    #  ELEMENT FINDING METHODS (WITH RETRY LOGIC)

    def find_element(
        self,
        locator: Tuple[str, str],
        timeout: Optional[int] = None,
        retries: int = 2
        ) -> WebElement:
        """Find element with explicit wait and retry logic for stale elements.

        Args:
            locator: Tuple of (By.TYPE, "value")
            timeout: Wait timeout(uses default if None)
            retries: Number of retry attempts for stale elements

        Returns:
            WebElement: Found element

        Raises:
            TimeoutException: If the element is not found after retries
        """
        timeout = self.default_timeout if timeout is None else timeout

        for attempt in range(retries):
            try:
                wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
                element = wait.until(EC.presence_of_element_located(locator), message=f"Element not found: {locator}")
                return element
            except StaleElementReferenceException:
                if attempt < retries - 1:
                    continue
                raise
        raise TimeoutException(f"Element not found after {retries} retries: {locator}")

    def find_elements(
            self,
            locator: Tuple[str, str],
            timeout: Optional[int] = None,
            retries: int = 2
    ) -> List[WebElement]:
        """
        Find multiple elements with explicit wait and retry logic for stale elements.

        Args:
            locator: Tuple of (By.TYPE, "value")
            timeout: Wait timeout (uses default if None)
            retries: Number of retry attempts for stale elements

        Returns:
            List[WebElement]: List of found elements (empty list if none found)

        Example:
            products = page.find_elements((By.CLASS_NAME, "product-item"))
            if products:
                print(f"Found {len(products)} products")
            else:
                print("No products found")
        """
        timeout = self.default_timeout if timeout is None else timeout

        for attempt in range(retries):
            try:
                wait = WebDriverWait(
                    self.driver,
                    timeout,
                    poll_frequency=self.poll_frequency
                )
                wait.until(EC.presence_of_all_elements_located(locator))
                elements = self.driver.find_elements(*locator)
                return elements

            except TimeoutException:
                # No elements found - return an empty list (standard Selenium behavior)
                return []

            except StaleElementReferenceException:
                if attempt < retries - 1:
                    continue  # Retry
                # Last attempt failed - return an empty list
                return []

        # Fallback (should never reach here, but satisfies type checker)
        return []
    # ELEMENT INTERACTION METHODS

    def click(self, locator: Tuple[str, str], timeout: Optional[int] = None, use_js: bool = False) -> 'BasePage':
        """Click on an element with explicit wait and retry logic for stale elements."""
        timeout = self.default_timeout if timeout is None else timeout

        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            element = wait.until(EC.element_to_be_clickable(locator))

            self.scroll_to_element(element)

            if use_js:
                self._js_click(element)
            else:
                element.click()

            return self

        except (ElementClickInterceptedException, ElementNotInteractableException):
            # Fallback to JS if element is physically blocked
            try:
                element = self.find_element(locator, timeout)
                self._js_click(element)
            except TimeoutException:
                raise TimeoutException(
                    f"Element not clickable after JS fallback: {locator}"
                )
        return self

    def enter_text(
        self,
        locator: Tuple[str, str],
        text: str,
        clear_first: bool = True,
        press_enter: bool = False,
        timeout: Optional[int] = None,
        ) -> 'BasePage':
        """Enter text into the input field with proper waits"""
        timeout = self.default_timeout if timeout is None else timeout
        wait = WebDriverWait(
            self.driver,
            timeout,
            poll_frequency=self.poll_frequency
        )
        element = wait.until(
            EC.element_to_be_clickable(locator),
            message = f"Element not interactable: {locator}"
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
        timeout: Optional[int] = None, ) -> str:
        """Get visible text from an element"""

        element = self.find_element(locator, timeout)
        text = element.text.strip()
        return text

    def get_attribute(
            self,
            locator: Tuple[str, str],
            attribute: str,
            timeout: Optional[int] = None) -> str:
        """Get attribute value from an element"""
        element = self.find_element(locator, timeout)
        value = element.get_attribute(attribute)
        return value

    def select_dropdown_by_text(
        self,
        locator: Tuple[str, str],
        text: str,
        timeout: Optional[int] = None,
        ) ->'BasePage':
        """Select a dropdown option by visible text"""
        from selenium.webdriver.support.select import Select

        element = self.find_element(locator)
        select = Select(element)
        select.select_by_visible_text(text)
        return self

    def select_dropdown_by_value(
            self,
            locator: Tuple[str, str],
            value: str,
            ) -> 'BasePage':
        """Select a dropdown option by value"""
        from selenium.webdriver.support.select import Select

        element = self.find_element(locator)
        select = Select(element)
        select.select_by_value(value)
        return self

    # ELEMENT STATE CHECKING METHODS

    def is_element_visible(
        self,
        locator: Tuple[str, str],
        timeout: int = 5
        ) -> bool:
        """Check if an element is visible on the page"""
        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            wait.until(EC.visibility_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    def is_element_present(
        self,
        locator: Tuple[str, str],
        timeout: int = 2
        ) -> bool:
        """Check if an element exists in DOM (may not be visible)

        Args:
            locator: Tuple of (By.TYPE, "value")
            timeout: Wait timeout in seconds (default: 2 seconds)

        Returns:
            bool: True if element is present, False otherwise
        """

        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            wait.until(EC.presence_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    def is_element_clickable(
        self,
        locator: Tuple[str, str],
        timeout: int = 2
        ) -> bool:
        """Check if an element is clickable (visible and enabled).

        Args:
            locator: Tuple of (By.TYPE, "value")
            timeout: Wait timeout in seconds (default: 5 seconds)

        Returns:
            bool: True if element is clickable, False otherwise

        """
        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            wait.until(EC.element_to_be_clickable(locator))
            return True
        except TimeoutException:
            return False

    def wait_for_element_to_disappear(
        self,
        locator: Tuple[str, str],
        timeout: int = 10
        ) -> bool:
        """Wait for an element to disappear from the page.

        Useful for waiting for loading spinners, modals, etc.

        Args:
            locator: Tuple of (By.TYPE, "value")
            timeout: Wait timeout in seconds (default: 10 seconds)

        Returns:
            bool: True if the element disappears, False if timeout occurs

        Example:
            page.wait_for_element_to_disappear((By.ID, "loading_spinner"))
        """

        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            wait.until_not(EC.presence_of_element_located(locator))
            return True
        except TimeoutException:
            return False

    def wait_for_url_contains(
        self,
        text: str,
        timeout: Optional[int] = None,
        ) -> 'BasePage':
        """Wait for URL to contain specific text.

        Args:
            text: Text that should be in URL
            timeout: Wait timeout in seconds (uses default if None)

        Returns:
            self: For method chaining

        Raises
            TimeoutException: If text is not found in URL after timeout
        """

        timeout = self.default_timeout if timeout is None else timeout
        wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
        wait.until(EC.url_contains(text),
            message=f"URL doesn't contain '{text}' after {timeout} seconds")
        return self

    def wait_for_url_to_be(
        self,
        url: str,
        timeout: Optional[int] = None,
        ) -> 'BasePage':
        """Wait for URL to match a specific pattern.

        Args:
            url: Pattern to match URL against
            timeout: Wait timeout in seconds (uses default if None)

        Returns:
            self: For method chaining
        """
        timeout = self.default_timeout if timeout is None else timeout
        wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
        wait.until(EC.url_to_be(url),
            message=f"URL '{self.driver.current_url}' does not match '{url}' after {timeout} seconds")
        return self

    def wait_for_title_contains(
        self,
        text: str,
        timeout: Optional[int] = None,
        ) -> 'BasePage':
        """Wait for the page title to contain specific text.

        Args:
            text: Text to search for in the title
            timeout: Wait timeout in seconds (uses default if None)

        Returns:
            self: For method chaining
        """
        timeout = self.default_timeout if timeout is None else timeout
        wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
        wait.until(EC.title_contains(text),
            message=f"Title does not contain '{text}' after {timeout} seconds")
        return self

    # SCROLLING METHODS

    def scroll_to_element(
            self,
            locator_or_element: Union[Tuple[str, str], WebElement],
            timeout: Optional[int] = None
    ) -> 'BasePage':
        """Scroll element into view using JavaScript.

        Can accept either a locator (finds element first) or an existing WebElement.

        Args:
            locator_or_element: Either a tuple (By.TYPE, "value") or WebElement
            timeout: Wait timeout in seconds (used if a locator is provided)

        Returns:
            self: For method chaining
        """
        if isinstance(locator_or_element, tuple):
            element = self.find_element(locator_or_element, timeout)
        else:
            element = locator_or_element

        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});",
            element
        )
        return self

    def scroll_to_top(self) -> 'BasePage':
        """Scroll to the top of the page."""
        self.driver.execute_script("window.scrollTo(0, 0);")
        return self

    def scroll_to_bottom(self) -> 'BasePage':
        """Scroll to the bottom of the page."""
        self.driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);"
        )
        return self

    def scroll_by_amount(self, x: int = 0, y: int = 0) -> 'BasePage':
        """
        Scroll by specific pixel amount.

        Args:
            x: Horizontal scroll amount (pixels)
            y: Vertical scroll amount (pixels)

        Returns:
            self: For method chaining

        Example:
            page.scroll_by_amount(y=500)  # Scroll down 500px
        """
        self.driver.execute_script(f"window.scrollBy({x}, {y});")
        return self

    # JAVASCRIPT EXECUTİON METHODS

    def execute_script(self, script: str, *args) -> Any:
        """
        Execute JavaScript code.

        Args:
            script: Javascript code to execute
            *args: Arguments to pass to the script

        Return:
            any: Return value from Javascript code

        Example:
            page.execute_script("return document.title;")
        """
        return self.driver.execute_script(script, *args)

    def _js_click(self, element: WebElement) -> None:
        """
        Click element using Javascript (internal method)

        Args:
            element: WebElement to click
        """
        self.driver.execute_script("arguments[0].click();", element)

    # ALERT / POPUP HANDLING METHODS

    def accept_alert(self, timeout: int = 5) -> 'BasePage':
        """
        Accept JavaScript alert.

        Args:
            timeout: Wait for timeout for alert to appear

        Returns:
            self: For method chaining
        """
        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            alert = wait.until(EC.alert_is_present())
            alert.accept()

        except TimeoutException:
            pass
        return self

    def dismiss_alert(self, timeout: int = 5) -> 'BasePage':
        """
        Dismiss JavaScript alert.

        Args:
            timeout: Wait for timeout for the alert to appear

        Returns:
            self: For method chaining
        """
        try:
            wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
            alert = wait.until(EC.alert_is_present())
            alert.dismiss()
        except TimeoutException:
            pass
        return self

    def get_alert_text(self, timeout: int = 5) -> Optional[str]:
        """
        Get text from JavaScript alert.

        Args:
            timeout: Wait timeout for the alert to appear

        Returns:
            str: Alert text, Or None if no alert is present
        """
        try:
            wait = WebDriverWait(self.driver, timeout)
            alert = wait.until(EC.alert_is_present())
            return alert.text
        except TimeoutException:
            return None

    # WINDOW / TAB METHODS

    def switch_to_window(self, window_handle: str) -> 'BasePage':
        """
        Switch to a specific window or tab.

        Args:
            window_handle: Window handle to switch to

        Returns: self: For method chaining
        """
        self.driver.switch_to.window(window_handle)
        return self

    def get_window_handles(self) -> List[str]:
        """
        Get all window handles.

        Returns:
             List[str]: List of window handles
        """
        return self.driver.window_handles

    def switch_to_new_window(self) -> 'BasePage':
        """
        Switch to the most recently opened window/tab.

        Returns:
             self: For method chaining
        """
        windows = self.get_window_handles()
        self.driver.switch_to.window(windows[-1])
        return self

    # FRAME HANDLING METHODS

    def switch_to_frame(self, locator: Union[Tuple[str, str], int, str]) -> 'BasePage':
        """
        Switch to iframe or frame

        Args:
             locator: Frame locator (tuple), index(int), or name/id(str)

        Returns:
              self: For method chaining

        Example:
            page.switch_to_frame((By.ID, "payment-frame"))
            page.switch_to_frame(0)  # First frame
            page.switch_to_frame("payment")  # Frame with name="payment"
        """
        if isinstance(locator, tuple):
            frame = self.find_element(locator)
            self.driver.switch_to.frame(frame)
        else:
            self.driver.switch_to.frame(locator)

        return self

    def switch_to_default_content(self) -> 'BasePage':
        """
        Switch back to the main document (exit any iframe/frame context).

        Returns:
            self: For method chaining

        Example:
            page.switch_to_frame((By.ID, "payment-frame"))
            # ... interact inside frame ...
            page.switch_to_default_content()  # Back to main page
        """
        self.driver.switch_to.default_content()
        return self

# HOVER/MOUSE ACTIONS METHODS

    def hover_over(self, locator: Tuple[str, str]) -> 'BasePage':
        """
        Hover mouse over an element

        Args:
             locator: Tuple of (By.TYPE, "value")

        Returns:
            self: For method chaining

        Example:
            page.hover_over((By.ID, "dropdown-menu"))
        """
        element = self.find_element(locator)
        ActionChains(self.driver).move_to_element(element).perform()
        return self

    def double_click(self, locator: Tuple[str, str]) -> 'BasePage':
        """
        Double click element

        Args:
            locator: Tuple of (By.TYPE, "value")

        Returns:
            self: For method chaining
        """
        element = self.find_element(locator)
        ActionChains(self.driver).double_click(element).perform()
        return self

    def right_click(self, locator: Tuple[str, str]) -> 'BasePage':
        """
        Right-click an element

        Args:
            locator: Tuple of (By.TYPE, "value")

        Returns:
            self: For method chaining
        """
        element = self.find_element(locator)
        ActionChains(self.driver).context_click(element).perform()
        return self

# PAGE INFO PROPERTIES

    @property
    def current_url(self) -> str:
        """Get current page URL"""
        return self.driver.current_url

    @property
    def page_title(self) -> str:
        """Get current page title"""
        return self.driver.title

    @property
    def page_source(self) -> str:
        """Get current page source code"""
        return self.driver.page_source

# UTILITY METHODS

    def take_screenshot(self, filename: str) -> bool:
        """Take screenshot and save it to a file

        Args:
            filename: path to save screenshot

        Returns:
            bool: True if the screenshot saved successfully, False otherwise
        """
        try:
            self.driver.save_screenshot(filename)
            return True
        except Exception as e:
            print(f"Error saving screenshot: {e}")
            return False

    def get_element_count(self, locator: Tuple[str, str]) -> int:
        """Get the number of elements found by a locator

        Args:
            locator: Tuple of (By.TYPE, "value")

        Returns:
            int: Number of elements found
        """
        elements = self.find_elements(locator, timeout=2)
        count = len(elements)
        return count

    def wait_for_page_load(self, timeout: Optional[int] = None) -> 'BasePage':
        """
        Wait for page to fully load (document.readyState === 'complete').

        Args:
            timeout: Wait for timeout for page load (Uses default if None)

        Returns:
            self: For method chaining
        """
        timeout = self.default_timeout if timeout is None else timeout

        wait = WebDriverWait(self.driver, timeout, poll_frequency=self.poll_frequency)
        wait.until(
            lambda driver: driver.execute_script("return document.readyState") == "complete",
            message=f"Page load timed out after {timeout} seconds."
        )
        return self

    def is_page_loaded(self) -> bool:
        """
        Check if page is fully loaded

        Returns:
             bool: True if the page is fully loaded, False otherwise
        """
        return self.driver.execute_script("return document.readyState") == "complete"


    def __repr__(self) -> str:
        """String representation of the page object"""
        return f"{self.__class__.__name__}(url={self.current_url})"







