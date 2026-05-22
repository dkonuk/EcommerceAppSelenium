"""
Database fixtures.

Provides two fixtures at different scopes, each suited to a different
class of test:

    sterile_database  (session)  — reset + seed once per run.
                                   Right choice for tests that only read
                                   data: browsing products, checking
                                   categories, viewing seed orders.

    isolated_database (function) — reset + seed before every individual
                                   test. Right choice for tests that write
                                   shared state: product stock changes,
                                   reviews (unique per user+product pair),
                                   or anything that would leave the DB in
                                   a state that breaks the next test.

Note on cart and order tests:
    Tests that create their own user via the `registered_user` fixture
    (see auth_fixtures.py) do NOT need either fixture here. User-owned
    data (cart items, orders) is naturally isolated because each test
    owns a unique user. Only reach for isolated_database when a test
    touches state that is shared across users (product stock, reviews).
"""

import logging

import pytest

from api.admin_client import AdminAPIClient

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def sterile_database(test_config):
    """
    Reset and seed the database exactly once for the whole test session.

    Runs before the first test that requests it. All subsequent tests
    in the session share the same seeded state, so tests using this
    fixture must not modify shared data (products, categories, stock).

    Teardown:
        The database is intentionally left seeded after the session.
        This lets you inspect the final state after a run — useful when
        diagnosing failures locally. Re-seeding at the start of the next
        run replaces any leftover state anyway.

    Scope: session
    """
    admin = AdminAPIClient(api_url=test_config.api_url)

    logger.info("sterile_database: resetting database")
    admin.reset_database()

    logger.info("sterile_database: seeding database")
    result = admin.seed_database()

    counts = result.get("counts", {})
    logger.info(
        f"sterile_database: seeded "
        f"{counts.get('users', '?')} users, "
        f"{counts.get('products', '?')} products, "
        f"{counts.get('categories', '?')} categories"
    )

    yield

    # Teardown is disabled by default — see docstring above.
    # Uncomment to reset after the session (e.g. in a shared CI database):
    # logger.info("sterile_database: teardown — resetting database")
    # admin.reset_database()


@pytest.fixture(scope="function")
def isolated_database(test_config):
    """
    Reset and seed the database before every individual test.

    More expensive than sterile_database (two API calls per test) but
    gives each test a guaranteed identical starting state regardless of
    what previous tests did to shared data.

    Use this fixture when the test:
        - Reduces product stock (buying or reserving items)
        - Submits a review (unique constraint: one review per user+product)
        - Modifies a category or product record directly
        - Relies on an exact product count or specific stock level

    Do NOT use this fixture when:
        - The test only reads data  →  use sterile_database (faster)
        - The test creates its own user and only touches that user's cart
          or orders  →  no database fixture needed at all; dynamic user
          creation already provides the isolation

    Scope: function
    """
    admin = AdminAPIClient(api_url=test_config.api_url)

    logger.info("isolated_database: resetting and seeding for this test")
    admin.reset_database()
    result = admin.seed_database()

    counts = result.get("counts", {})
    logger.info(
        f"isolated_database: ready — "
        f"{counts.get('products', '?')} products, "
        f"{counts.get('categories', '?')} categories"
    )

    yield

    # No teardown: the next test's setup call handles cleanup.
    # Resetting here would add a redundant API call before every test.