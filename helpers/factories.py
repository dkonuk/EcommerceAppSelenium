"""
Test data factories for the ecommerce test suite.

Each factory generates input data for a specific API endpoint or UI form.
They answer one question: "what valid data does this endpoint/form accept?"

Design rules:
    - All generated values satisfy the backend's validation constraints.
      Those constraints are documented inline so that if they change in
      backend/src/routes/*.js, the factory is the obvious place to update.
    - Fields the caller cares about can be overridden via **kwargs.
    - Factories never talk to the database or the API — they only produce
      plain Python dicts.
    - Uniqueness is handled with uuid4 hex fragments, not counters.
      Counters break under parallel execution (pytest-xdist); UUIDs don't.

Note on faker:
    faker is used for realistic names, addresses, and review text.
    It is listed in requirements-dev.txt but should be in requirements.txt
    because it is needed at test execution time, not just during development.
    Move it when requirements.txt is next updated.

Contents:
    SeedData             — constants mirroring the running app's seed data
    UserFactory          — registration and login payloads
    OrderFactory         — checkout / order creation payloads
    ReviewFactory        — product review payloads
    ProductSearchFactory — query parameters for GET /api/products
"""

import random
from uuid import uuid4

from faker import Faker

_fake = Faker()


# ---------------------------------------------------------------------------
# Seed data constants
# ---------------------------------------------------------------------------

class SeedData:
    """
    Known values produced by the running application's seed endpoint.

    These constants reflect what GET /api/products/categories/all and
    the admin seed endpoint actually produce — NOT what seed.js says on
    disk. If the two ever differ, the running app wins.

    If the seed data changes, update this class first. A single diff here
    is better than a grep across the whole suite.
    """

    # --- Credentials ---
    ADMIN_EMAIL    = "user1@test.com"
    ADMIN_PASSWORD = "password123"

    # Users user1@test.com .. user20@test.com, all with password123
    USER_PASSWORD  = "password123"
    USER_COUNT     = 20

    @staticmethod
    def user_email(n: int) -> str:
        """Return the seeded email for user n (1-based, 1..20).
        Note: user 1 (user1@test.com) has role='admin'.
          Use n >= 2 for tests that require a non-admin user.
          """
        if not 1 <= n <= SeedData.USER_COUNT:
            raise ValueError(
                f"Seeded user index must be 1–{SeedData.USER_COUNT}, got {n}"
            )
        return f"user{n}@test.com"

    # --- Categories ---
    # 10 flat (no parent-child hierarchy) categories as returned by the
    # running seed. Verified against GET /api/products/categories/all.
    CATEGORIES = [
        "Automotive",
        "Beauty",
        "Books",
        "Clothing",
        "Electronics",
        "Food",
        "Health",
        "Home & Garden",
        "Sports",
        "Toys",
    ]

    # --- Search terms ---
    # Category names are the safest search terms — guaranteed to appear in
    # product names or descriptions since products are seeded per category.
    SEARCH_TERMS = [
        "Electronics",
        "Clothing",
        "Books",
        "Sports",
        "Toys",
        "Automotive",
        "Beauty",
        "Food",
        "Health",
        "Home",
    ]

    # --- Shipping address used in seeded orders ---
    SEED_SHIPPING_ADDRESS = "123 Test St, Test City, TC 12345"


# ---------------------------------------------------------------------------
# UserFactory
# ---------------------------------------------------------------------------

class UserFactory:
    """
    Generates payloads for POST /api/auth/register and POST /api/auth/login.

    Backend validation rules (from backend/src/routes/auth.js):
        email    — must be a valid email address
        password — minimum 6 characters
        name     — at least 1 non-whitespace character after trimming

    Example:
        user = UserFactory.create()
        # {"email": "user_a1b2c3d4@testmail.com", "name": "Emma Johnson",
        #  "password": "Secure_c3d4!9"}

        # Override email for a duplicate-registration test:
        user = UserFactory.create(email="already_taken@test.com")
    """

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Return a valid registration payload with random defaults.

        Any field can be overridden via keyword argument.

        Returns:
            dict with keys: email, name, password
        """
        uid = uuid4().hex[:8]

        defaults = {
            # UUID fragment guarantees uniqueness even under parallel execution
            "email": f"user_{uid}@testmail.com",

            # Faker provides realistic names; better than hard-coded lists
            # for tests that display the name back in the UI
            "name": _fake.name(),

            # Meets the min-6-char rule; includes mixed case and a digit
            # so it passes any future stricter validation without changes here
            "password": f"Test_{uid[:4]}!9",
        }

        return {**defaults, **kwargs}

    @classmethod
    def create_login_payload(cls, email: str, password: str) -> dict:
        """
        Return a login payload dict.

        Thin wrapper that makes test code self-documenting:
            payload = UserFactory.create_login_payload(user["email"], user["password"])
        instead of:
            payload = {"email": user["email"], "password": user["password"]}
        """
        return {"email": email, "password": password}


# ---------------------------------------------------------------------------
# OrderFactory
# ---------------------------------------------------------------------------

class OrderFactory:
    """
    Generates payloads for POST /api/orders.

    Backend validation rules (from backend/src/routes/orders.js):
        shipping_address — required, non-empty string

    Example:
        order = OrderFactory.create()
        # {"shipping_address": "742 Evergreen Terrace, Springfield, IL 62701"}

        order = OrderFactory.create(shipping_address="1 Infinite Loop, Cupertino, CA")
    """

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Return a valid order creation payload with a random shipping address.

        Returns:
            dict with key: shipping_address
        """
        defaults = {
            # Faker builds realistic street addresses
            "shipping_address": _fake.address().replace("\n", ", "),
        }

        return {**defaults, **kwargs}


# ---------------------------------------------------------------------------
# ReviewFactory
# ---------------------------------------------------------------------------

class ReviewFactory:
    """
    Generates payloads for POST /api/reviews/:productId.

    Backend validation rules (from backend/src/config/database.js schema):
        rating  — integer, 1–5 (CHECK constraint)
        comment — text, optional

    The unique constraint (product_id, user_id) means one user can only
    review each product once. Tests using ReviewFactory with a shared
    user against the same product must use isolated_database to reset
    between tests.

    Example:
        review = ReviewFactory.create()
        # {"rating": 4, "comment": "Great product! Highly recommend."}

        review = ReviewFactory.create(rating=1, comment="Terrible quality.")
    """

    _COMMENTS = [
        "Great product! Exactly as described.",
        "Good value for the price. Would buy again.",
        "Fast shipping and solid build quality.",
        "Decent quality but sizing runs a bit small.",
        "Exceeded my expectations. Very happy with this.",
        "Solid product. Does exactly what it says.",
        "Average quality for the price point.",
        "Would recommend to a friend.",
    ]

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Return a valid review payload with random defaults.

        Returns:
            dict with keys: rating, comment
        """
        defaults = {
            # Weighted toward positive reviews to reflect realistic data;
            # use create(rating=1) to test negative review scenarios
            "rating": random.choices(
                population=[1, 2, 3, 4, 5],
                weights=[5, 5, 15, 35, 40],
            )[0],
            "comment": random.choice(cls._COMMENTS),
        }

        return {**defaults, **kwargs}


# ---------------------------------------------------------------------------
# ProductSearchFactory
# ---------------------------------------------------------------------------

class ProductSearchFactory:
    """
    Generates query parameter dicts for GET /api/products.

    Valid query parameters (from backend/src/routes/products.js):
        search    — string, matched against name and description (LIKE)
        category  — integer category id
        sortBy    — "name" | "price" | "created_at" | "stock"
        order     — "asc" | "desc"
        minPrice  — float
        maxPrice  — float
        page      — integer >= 1
        limit     — integer >= 1

    Search terms are drawn from SeedData.SEARCH_TERMS — category names
    guaranteed to appear in product names or descriptions.

    Example:
        params = ProductSearchFactory.create()
        # {"search": "Electronics", "sortBy": "price", "order": "asc",
        #  "page": 1, "limit": 20}

        # Filter to a price range:
        params = ProductSearchFactory.create_price_range(min_price=10.0, max_price=100.0)
    """

    _SORT_FIELDS = ["name", "price", "created_at", "stock"]

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Return a valid product search query parameter dict.

        Returns:
            dict with keys: search, sortBy, order, page, limit
        """
        defaults = {
            "search": random.choice(SeedData.SEARCH_TERMS),
            "sortBy": random.choice(cls._SORT_FIELDS),
            "order":  random.choice(["asc", "desc"]),
            "page":   1,
            "limit":  20,
        }

        return {**defaults, **kwargs}

    @classmethod
    def create_price_range(
        cls,
        min_price: float = 10.0,
        max_price: float = 500.0,
        **kwargs,
    ) -> dict:
        """
        Convenience method for price-range filter tests.

        Example:
            params = ProductSearchFactory.create_price_range(min_price=50, max_price=200)
        """
        return cls.create(minPrice=min_price, maxPrice=max_price, **kwargs)

    @classmethod
    def create_empty_result(cls, **kwargs) -> dict:
        """
        Return params that produce zero results from the seeded database.

        Useful for testing empty-state UI rendering and zero-result API responses.
        """
        return cls.create(
            search="xyzzy_guaranteed_no_match_00000",
            **kwargs,
        )