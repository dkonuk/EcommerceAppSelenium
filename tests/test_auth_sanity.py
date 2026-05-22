from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import time


def test_browser_injection_works(authenticated_browser, test_config):
    """Sanity check to ensure the API token is injected and accepted."""

    # 1. Verify the payload exists in the browser
    injected_token = authenticated_browser.execute_script("return window.localStorage.getItem('token');")

    assert injected_token is not None, "FAIL: Token is missing from localStorage."
    assert len(injected_token) > 20, "FAIL: Token was injected, but it looks malformed."
    print(f"\nSuccess: Token found in localStorage: {injected_token[:10]}...")

    # 2. Verify the React app respects the session
    authenticated_browser.get(test_config.base_url)

    # Wait briefly to ensure React's router has time to mount and evaluate the token
    wait = WebDriverWait(authenticated_browser, 3)

    cart_link = wait.until(EC.element_to_be_clickable((By.LINK_TEXT, "Cart")))
    cart_link.click()


    # 3. Verify the client-side route changed
    wait.until(EC.url_contains("/cart"))

    print("Success: Navigated to Cart via React Router.")