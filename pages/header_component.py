"""
Header navigation component for the ecommerce test suite.

Models the shared <Header> React component that renders on every route.
Composed into page objects rather than inherited — each page that needs
header interaction creates a HeaderComponent instance via self.header.

Header.js renders conditionally based on auth state:

    Logged OUT:                   Logged IN:
    ┌─────────────────────┐       ┌─────────────────────────────────┐
    │ 🛒 Test Shop        │       │ 🛒 Test Shop                    │
    │ Home  Products      │       │ Home  Products  Cart  Orders    │
    │ Login  Register     │       │ {user.name}  [Logout]           │
    └─────────────────────┘       └─────────────────────────────────┘

Usage:
    class ProductsPage(BasePage):
        def __init__(self, driver, config):
            super().__init__(driver, config)
            self.header = HeaderComponent(self)

    # In a test:
    products_page.header.nav_to_cart()
    assert products_page.header.is_logged_in()
    username = products_page.header.get_username()
"""

from selenium.webdriver.common.by import By


class HeaderComponent:
    """
    Encapsulates all interactions with the application's shared header.

    Args:
        page: The BasePage instance that owns this component. All DOM
              interactions are delegated to the page's interaction methods
              so HeaderComponent never touches Selenium directly.
    """

    # ------------------------------------------------------------------
    # Locators
    # All scoped to the <header> element to prevent false matches if
    # page content happens to contain similar link text or classes.
    # ------------------------------------------------------------------

    # Always-visible
    LOGO           = (By.CSS_SELECTOR, "header h1")
    NAV_HOME       = (By.CSS_SELECTOR, "header a[href='/']")
    NAV_PRODUCTS   = (By.CSS_SELECTOR, "header a[href='/products']")

    # Visible only when logged IN
    NAV_CART       = (By.CSS_SELECTOR, "header a[href='/cart']")
    NAV_ORDERS     = (By.CSS_SELECTOR, "header a[href='/orders']")
    NAV_PROFILE    = (By.CSS_SELECTOR, "header a[href='/profile']")
    LOGOUT_BUTTON  = (By.CSS_SELECTOR, "header button.btn-secondary")

    # Visible only when logged OUT
    NAV_LOGIN      = (By.CSS_SELECTOR, "header a[href='/login']")
    NAV_REGISTER   = (By.CSS_SELECTOR, "header a[href='/register']")

    def __init__(self, page):
        self._page = page

    # ------------------------------------------------------------------
    # Auth state detection
    # ------------------------------------------------------------------

    def is_logged_in(self) -> bool:
        """
        Return True if the Logout button is visible in the header.

        The Logout button only renders when React's user state is set —
        it is the most reliable logged-in indicator available in the DOM.
        No timeout argument: a short poll is sufficient since React sets
        user state synchronously from the JWT stored in localStorage.
        """
        return self._page.is_element_visible(self.LOGOUT_BUTTON, timeout=3)

    def is_logged_out(self) -> bool:
        """
        Return True if the Login link is visible in the header.

        Complement of is_logged_in(). Use whichever reads more naturally
        in the test assertion:
            assert header.is_logged_out()
            assert not header.is_logged_in()
        """
        return self._page.is_element_visible(self.NAV_LOGIN, timeout=3)

    def get_username(self) -> str:
        """
        Return the username as displayed in the header profile link.

        React renders <Link to="/profile">{user.name}</Link> when logged in.
        This is the same name returned by GET /api/users/profile.
        """
        return self._page.get_text(self.NAV_PROFILE)

    # ------------------------------------------------------------------
    # Navigation — always available
    # ------------------------------------------------------------------

    def click_logo(self) -> None:
        """Click the '🛒 Test Shop' h1 logo, which navigates to home."""
        self._page.click(self.LOGO)
        self._page.wait_for_url_to_be(self._page.base_url + "/")

    def nav_to_home(self) -> None:
        """Click the Home link in the nav."""
        self._page.click(self.NAV_HOME)
        self._page.wait_for_url_contains("/")

    def nav_to_products(self) -> None:
        """Click the Products link in the nav."""
        self._page.click(self.NAV_PRODUCTS)
        self._page.wait_for_url_contains("/products")

    # ------------------------------------------------------------------
    # Navigation — logged IN only
    # ------------------------------------------------------------------

    def nav_to_cart(self) -> None:
        """
        Click the Cart link (only rendered when logged in).

        Raises TimeoutException if called when logged out — Cart link
        is absent from the DOM in that state.
        """
        self._page.click(self.NAV_CART)
        self._page.wait_for_url_contains("/cart")

    def nav_to_orders(self) -> None:
        """
        Click the Orders link (only rendered when logged in).
        """
        self._page.click(self.NAV_ORDERS)
        self._page.wait_for_url_contains("/orders")

    def nav_to_profile(self) -> None:
        """
        Click the profile username link (only rendered when logged in).
        """
        self._page.click(self.NAV_PROFILE)
        self._page.wait_for_url_contains("/profile")

    def logout(self) -> None:
        """
        Click the Logout button (only rendered when logged in).

        After clicking, React clears user state and removes the token
        from localStorage. The header re-renders to the logged-out state
        and the router redirects to '/'.
        """
        self._page.click(self.LOGOUT_BUTTON)
        self._page.wait_for_url_contains("/")

    # ------------------------------------------------------------------
    # Navigation — logged OUT only
    # ------------------------------------------------------------------

    def nav_to_login(self) -> None:
        """
        Click the Login link (only rendered when logged out).
        """
        self._page.click(self.NAV_LOGIN)
        self._page.wait_for_url_contains("/login")

    def nav_to_register(self) -> None:
        """
        Click the Register link (only rendered when logged out).
        """
        self._page.click(self.NAV_REGISTER)
        self._page.wait_for_url_contains("/register")