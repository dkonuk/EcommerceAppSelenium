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
    SeedData           — constants mirroring backend/scripts/seed.js
    UserFactory        — registration and login payloads
    OrderFactory       — checkout / order creation payloads
    ReviewFactory      — product review payloads
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
    Known values produced by backend/scripts/seed.js.

    Use these constants when a test deliberately targets seeded data —
    for example, an API test that verifies a specific product exists, or
    an auth test that logs in as the admin.

    If seed.js changes, update this class. Having one canonical reference
    means a seed change produces a single diff, not a grep across the suite.
    """

    # --- Credentials ---
    ADMIN_EMAIL    = "admin@test.com"
    ADMIN_PASSWORD = "admin123"

    # Users user1@test.com .. user20@test.com, all with password123
    USER_PASSWORD  = "password123"
    USER_COUNT     = 20

    @staticmethod
    def user_email(n: int) -> str:
        """Return the seeded email for user n (1-based, 1..20)."""
        if not 1 <= n <= SeedData.USER_COUNT:
            raise ValueError(
                f"Seeded user index must be 1–{SeedData.USER_COUNT}, got {n}"
            )
        return f"user{n}@test.com"

    # --- Categories (matches seed.js category list exactly) ---
    CATEGORIES = [
        "Electronics",
        "Laptops",
        "Smartphones",
        "Clothing",
        "Men",
        "Women",
        "Books",
        "Fiction",
        "Non-Fiction",
        "Home & Garden",
        "Sports",
        "Toys",
    ]

    # --- Named products (the hand-crafted ones, not the generic Laptop 1…N) ---
    NAMED_PRODUCTS = [
        'MacBook Pro 16"',
        "Dell XPS 13",
        "iPhone 15 Pro",
        "Samsung Galaxy S24",
        "Sony WH-1000XM5",
        "Classic Cotton T-Shirt",
        "Slim Fit Jeans",
        "Summer Dress",
        "Yoga Pants",
        "The Great Novel",
        "Science Made Simple",
        "Cooking Mastery",
        "Ergonomic Office Chair",
        "LED Desk Lamp",
        "Plant Pot Set",
        "Yoga Mat",
        "Dumbbells Set",
        "Running Shoes",
        "Building Blocks Set",
        "Board Game Collection",
    ]

    # Prefixes used for generic products (Laptop 1..30, Phone 1..40, etc.)
    # Useful for constructing search terms that will return results.
    GENERIC_PRODUCT_PREFIXES = ["Laptop", "Phone", "T-Shirt", "Book", "Toy"]

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

    This factory generates search terms and sort options that will return
    results against the seeded database. Tests that need an empty result
    set should pass a nonsense search term explicitly:
        params = ProductSearchFactory.create(search="xyzzy_no_match_12345")

    Example:
        params = ProductSearchFactory.create()
        # {"search": "Laptop", "sortBy": "price", "order": "asc",
        #  "page": 1, "limit": 20}

        # Filter to a price range:
        params = ProductSearchFactory.create(minPrice=10.0, maxPrice=100.0)
    """

    # Valid sort fields as declared in products.js validSortFields
    _SORT_FIELDS = ["name", "price", "created_at", "stock"]

    # Search terms guaranteed to return results from the seeded database.
    # Drawn from SeedData.GENERIC_PRODUCT_PREFIXES and named product keywords.
    _SEARCH_TERMS = [
        "Laptop", "Phone", "T-Shirt", "Book", "Toy",
        "MacBook", "iPhone", "Samsung", "Sony",
        "Yoga", "Running", "Cooking",
    ]

    @classmethod
    def create(cls, **kwargs) -> dict:
        """
        Return a valid product search query parameter dict.

        Returns:
            dict with keys: search, sortBy, order, page, limit
        """
        defaults = {
            "search": random.choice(cls._SEARCH_TERMS),
            "sortBy": random.choice(cls._SORT_FIELDS),
            "order": random.choice(["asc", "desc"]),
            "page": 1,
            "limit": 20,
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
        Return params that will produce zero results from the seeded database.

        Useful for testing empty-state UI rendering and zero-result API responses.
        """
        return cls.create(
            search="xyzzy_guaranteed_no_match_00000",
            **kwargs,
        )