"""
Authentication fixtures.

Provides:
    registered_user      (session)  — creates one user via the registration
                                      API for the whole run. Use this for any
                                      test that needs an authenticated user but
                                      doesn't modify user-specific state.

    isolated_user        (function) — creates a fresh user per test. Use this
                                      when the test modifies user-owned data
                                      (cart items, orders, profile) and you
                                      need a clean slate each time.

    authenticated_browser (function) — a WebDriver with the registered_user's
                                       token already in localStorage. React
                                       treats the session as logged in from the
                                       first page load.

Scope decisions explained:
    registered_user is session-scoped because most UI tests just need *an*
    authenticated user — they don't care which one. Creating the user once and
    reusing the token across the session avoids N registration calls for N tests.

    isolated_user is function-scoped because cart and order tests mutate state
    that lives under a specific user account. Two tests sharing a user would see
    each other's cart items, orders, and profile changes.

    authenticated_browser is function-scoped because driver is function-scoped.
    A fixture cannot be broader in scope than its dependencies.

No sterile_database dependency here:
    These fixtures create users dynamically — they do not rely on seed data.
    If a test also needs products or categories to exist, it should declare
    sterile_database separately. Keeping auth and data state independent means
    you can compose them freely:

        # Needs auth only (profile page):
        def test_view_profile(authenticated_browser, test_config): ...

        # Needs auth + seed data (browse products while logged in):
        def test_browse_products(authenticated_browser, sterile_database, test_config): ...

        # Needs a fresh user + seed data (add product to cart):
        def test_add_to_cart(driver, isolated_user, sterile_database, test_config): ...
"""

import logging

import pytest
import requests

from api.auth_client import AuthAPIClient
from helpers.factories import UserFactory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _inject_token(driver, base_url: str, token: str) -> None:
    """
    Write a JWT into the browser's localStorage so React picks it up.

    This is not a fixture — it is a plain function called by any fixture
    that needs to establish an authenticated browser session. Centralising
    the injection logic here means a change to the localStorage key name
    ('token') only needs to happen in one place.

    Why navigate first:
        localStorage is origin-scoped. Selenium can only write to
        localStorage for the domain currently loaded in the browser.
        Navigating to base_url before injecting ensures we are on the
        correct origin.

    Why refresh after:
        React reads localStorage on mount. If the app is already loaded
        when we inject the token, it won't re-evaluate auth state until
        the next render cycle. A full refresh guarantees the app starts
        with the token already present.
    """
    driver.get(base_url)
    driver.execute_script(f"window.localStorage.setItem('token', '{token}');")
    driver.refresh()
    logger.debug("JWT injected into localStorage and page refreshed")


# ---------------------------------------------------------------------------
# User fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def registered_user(test_config):
    """
    Create one test user for the entire session via POST /api/auth/register.

    Returns a dict with everything a test or fixture might need:
        email    (str) — login credential
        password (str) — login credential
        name     (str) — display name
        token    (str) — JWT for immediate use without a separate login call
        id       (int) — user id in the database

    Note on UserFactory:
        UserFactory.create() currently generates extra fields inherited from
        a previous project. The fixture only extracts the three fields the
        registration endpoint requires (email, name, password). The factory
        will be rebuilt to match this app's schema in helpers/factories.py.

    Scope: session
    """
    auth_client = AuthAPIClient(api_url=test_config.api_url)
    user_data = UserFactory.create()

    logger.info(f"registered_user: registering {user_data['email']}")
    response_data = auth_client.register_user(
        email=user_data["email"],
        name=user_data["name"],
        password=user_data["password"],
    )

    user = {
        "email": user_data["email"],
        "password": user_data["password"],
        "name": user_data["name"],
        "token": response_data["token"],
        "id": response_data["user"]["id"],
    }

    logger.info(
        f"registered_user: ready — "
        f"id={user['id']} email={user['email']}"
    )
    return user


@pytest.fixture(scope="function")
def isolated_user(test_config):
    """
    Create a fresh user for a single test via POST /api/auth/register.

    Identical structure to registered_user but function-scoped, so each
    test that requests it gets a brand-new account with an empty cart,
    no orders, and no reviews.

    Use this instead of registered_user when the test:
        - Adds items to the cart
        - Places an order
        - Updates the user profile
        - Does anything that would leave user-owned state behind for the
          next test to stumble over

    Scope: function
    """
    auth_client = AuthAPIClient(api_url=test_config.api_url)
    user_data = UserFactory.create()

    logger.info(f"isolated_user: registering {user_data['email']}")
    response_data = auth_client.register_user(
        email=user_data["email"],
        name=user_data["name"],
        password=user_data["password"],
    )

    user = {
        "email": user_data["email"],
        "password": user_data["password"],
        "name": user_data["name"],
        "token": response_data["token"],
        "id": response_data["user"]["id"],
    }

    logger.info(
        f"isolated_user: ready — "
        f"id={user['id']} email={user['email']}"
    )
    return user


# ---------------------------------------------------------------------------
# Browser + auth fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def authenticated_browser(driver, test_config, registered_user):
    """
    A WebDriver instance pre-authenticated as the session's registered user.

    The JWT is injected into localStorage before yielding, so the React app
    treats the browser as logged in from the very first page load in the test.

    Depends on:
        driver           — the raw browser instance (from browser_fixtures)
        test_config      — for base_url
        registered_user  — for the token to inject

    Does NOT depend on sterile_database. If a test needs products or
    categories to exist, declare sterile_database explicitly alongside
    this fixture.

    Scope: function (inherits from driver)
    """
    logger.info(
        f"authenticated_browser: injecting token for "
        f"user id={registered_user['id']}"
    )
    _inject_token(
        driver=driver,
        base_url=test_config.base_url,
        token=registered_user["token"],
    )
    yield driver
    # No teardown needed — driver fixture handles browser shutdown,
    # and localStorage is cleared when the browser session ends.