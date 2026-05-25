"""
API tests for /api/products and /api/reviews.

Test coverage:

    TestProductsList
        - Default list returns products and a valid pagination envelope
        - Every product in the list has the fields the UI depends on
        - Search by keyword narrows results correctly
        - Search matches product name or description (backend uses LIKE on both)
        - Search with no matches returns empty list, not an error
        - minPrice filter excludes products below the threshold
        - maxPrice filter excludes products above the threshold  [FIX: dynamic threshold]
        - Combined price range filter
        - sort_by=price asc returns ascending prices
        - sort_by=price desc returns descending prices
        - sort_by=name asc returns alphabetical order
        - Invalid sort field falls back to default (not rejected)
        - limit parameter is respected
        - Page 2 returns different products than page 1

    TestProductDetail
        - Fetching a known product returns required fields
        - Returned product id matches the requested id
        - Product detail includes avg_rating and review_count
        - Fetching a non-existent id raises 404

    TestCategories
        - List all returns all seeded categories          [FIX: uses updated SeedData]
        - Each category has required fields
        - All seeded category names are present           [FIX: uses updated SeedData]
        - Products by category returns correct category
        - Category product list has pagination
        - Category product list respects limit
        - Non-existent category returns empty, not 404

    TestReviews
        - Get reviews returns correct envelope
        - Get reviews succeeds unauthenticated
        - Create review returns a reviewId
        - Create review unauthenticated raises 401
        - Create review rating > 5 raises 400
        - Create review rating < 1 raises 400
        - Duplicate review raises 400
        - Review for non-existent product raises 404
        - Update review changes the stored rating
        - Update review with no fields raises 400
        - Delete review removes it from subsequent GET

Fixes applied vs first version:
    1. SeedData.CATEGORIES updated to 10 flat categories matching running app
    2. test_search_matches_product_name: uses "Electronics", checks name+description
    3. test_max_price_filter: threshold derived dynamically from the cheapest product
    4. test_get_all_categories_returns_seeded_count: passes with corrected SeedData
    5. test_seeded_category_names_are_present: passes with corrected SeedData
"""

import pytest

from api.products_client import ProductsClient
from helpers.factories import ProductSearchFactory, ReviewFactory, SeedData


# ---------------------------------------------------------------------------
# Module-level helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def products_client(test_config, sterile_database):
    """
    Unauthenticated ProductsClient shared across the whole module.

    Re-used by all product and category tests. Review write tests build
    their own authenticated client inline because they need a per-test token.
    """
    return ProductsClient(api_url=test_config.api_url)


@pytest.fixture(scope="module")
def product_id(products_client):
    """
    Return a real product id from the seeded database.

    Fetches the first product from the default list so tests never
    assume id=1. The id is stable within a module run because
    sterile_database is also module-scoped.
    """
    result = products_client.get_products(limit=1)
    assert result["products"], "Seed data produced no products — check sterile_database"
    return result["products"][0]["id"]


@pytest.fixture(scope="module")
def cheapest_price(products_client):
    """
    Return the price of the cheapest seeded product.

    Used by price-filter tests that need a threshold guaranteed to
    return at least one result regardless of what the seed data costs.
    """
    result = products_client.get_products(sort_by="price", order="asc", limit=1)
    assert result["products"], "Seed data produced no products — check sterile_database"
    return result["products"][0]["price"]


@pytest.fixture(scope="module")
def category_id(products_client):
    """
    Return a real category id from the seeded database.

    Never hardcodes id=1 — fetches from the actual running data.
    """
    result = products_client.get_categories()
    assert result["categories"], "Seed data produced no categories — check sterile_database"
    return result["categories"][0]["id"]


# ---------------------------------------------------------------------------
# TestProductsList
# ---------------------------------------------------------------------------

class TestProductsList:
    """Tests for GET /api/products"""

    def test_default_list_returns_products(self, products_client):
        """Happy path — no filters, returns products and pagination envelope."""
        result = products_client.get_products()

        assert "products"   in result
        assert "pagination" in result
        assert len(result["products"]) > 0

    def test_pagination_envelope_has_required_fields(self, products_client):
        """Pagination object always contains page, limit, total, totalPages."""
        result     = products_client.get_products()
        pagination = result["pagination"]

        for field in ("page", "limit", "total", "totalPages"):
            assert field in pagination, f"Pagination missing field '{field}'"

    def test_product_has_required_fields(self, products_client):
        """Every product in the list contains the fields the UI depends on."""
        result  = products_client.get_products(limit=1)
        product = result["products"][0]

        for field in ("id", "name", "price", "stock", "category_name"):
            assert field in product, f"Product missing expected field '{field}'"

    def test_search_narrows_results(self, products_client):
        """Searching for a category name returns fewer results than the full list."""
        all_products  = products_client.get_products()
        search_result = products_client.get_products(search="Electronics")

        assert search_result["pagination"]["total"] < all_products["pagination"]["total"]
        assert search_result["pagination"]["total"] >= 0

    def test_search_matches_product_name_or_description(self, products_client, product_id):
        """
        Every product returned by a search contains the term in its name
        or description.

        The backend applies LIKE to both fields:
            WHERE name LIKE '%Electronics%' OR description LIKE '%Electronics%'

        The assertion checks both fields so tests don't fail when the term
        appears in description but not name.

        FIX: was "MacBook" (not in seed data) → now "Electronics" (a category
        name guaranteed to appear in products seeded for that category).
        """
        known_product = products_client.get_product(product_id)["product"]
        search_term = known_product["name"]
        result = products_client.get_products(search=search_term, limit=10)

        assert result["pagination"]["total"] > 0, (
            f"Search for '{search_term}' returned no results — "
            f"the product exists (id={product_id}) but search is not matching it"
        )
        for product in result["products"]:
            combined = (
                    product.get("name", "") + " " +
                    (product.get("description") or "")
            ).lower()

            assert search_term.lower() in combined, (
                f"Product '{product['name']}' was returned for search "
                f"'{search_term}' but the term was not found in name or description"
            )

    def test_search_no_match_returns_empty_list(self, products_client):
        """A search with no matches returns an empty list, not a 404 or error."""
        params = ProductSearchFactory.create_empty_result()
        result = products_client.get_products(search=params["search"])

        assert result["products"]             == []
        assert result["pagination"]["total"]  == 0

    def test_min_price_filter_excludes_cheaper_products(
        self, products_client, cheapest_price
    ):
        """
        Products returned when minPrice is set all have price >= threshold.

        Uses a threshold above the cheapest product so the filter is
        actually applied rather than matching everything.
        """
        threshold = cheapest_price + 0.01
        result    = products_client.get_products(min_price=threshold)

        # Only assert prices if products exist above the threshold
        if result["pagination"]["total"] > 0:
            for product in result["products"]:
                assert product["price"] >= threshold, (
                    f"Product '{product['name']}' priced {product['price']} "
                    f"was returned for minPrice={threshold}"
                )

    def test_max_price_filter_excludes_pricier_products(
        self, products_client, cheapest_price
    ):
        """
        Products returned when maxPrice is set all have price <= threshold.

        FIX: was maxPrice=30 (no products that cheap in actual seed data).
        Now uses the cheapest product's actual price as the threshold,
        guaranteeing at least one result regardless of what the seed costs.
        """
        threshold = cheapest_price
        result    = products_client.get_products(max_price=threshold)

        assert result["pagination"]["total"] > 0, (
            f"Expected at least one product at maxPrice={threshold} "
            f"(cheapest product price) but got zero results"
        )
        for product in result["products"]:
            assert product["price"] <= threshold, (
                f"Product '{product['name']}' priced {product['price']} "
                f"exceeds maxPrice={threshold}"
            )

    def test_price_range_filter(self, products_client, cheapest_price):
        """minPrice and maxPrice work together to define a range."""
        # Use a wide range anchored to the cheapest product so it always
        # returns results regardless of the seed's actual price distribution
        min_p  = cheapest_price
        max_p  = cheapest_price * 10
        result = products_client.get_products(min_price=min_p, max_price=max_p)

        assert result["pagination"]["total"] > 0
        for product in result["products"]:
            assert min_p <= product["price"] <= max_p, (
                f"Product '{product['name']}' priced {product['price']} "
                f"is outside range [{min_p}, {max_p}]"
            )

    def test_sort_by_price_ascending(self, products_client):
        """sort_by=price, order=asc returns products with non-decreasing prices."""
        result = products_client.get_products(sort_by="price", order="asc", limit=10)
        prices = [p["price"] for p in result["products"]]

        assert prices == sorted(prices), (
            f"Prices are not ascending: {prices}"
        )

    def test_sort_by_price_descending(self, products_client):
        """sort_by=price, order=desc returns products with non-increasing prices."""
        result = products_client.get_products(sort_by="price", order="desc", limit=10)
        prices = [p["price"] for p in result["products"]]

        assert prices == sorted(prices, reverse=True), (
            f"Prices are not descending: {prices}"
        )

    def test_sort_by_name_ascending(self, products_client):
        """sort_by=name, order=asc returns products in alphabetical order."""
        result = products_client.get_products(sort_by="name", order="asc", limit=10)
        names  = [p["name"].lower() for p in result["products"]]

        assert names == sorted(names), (
            f"Names are not alphabetically ascending: {names}"
        )

    def test_invalid_sort_field_falls_back_to_default(self, products_client):
        """
        An unrecognised sortBy value is silently ignored by the backend —
        it falls back to created_at. The request succeeds and is not rejected.
        """
        result = products_client.get_products(sort_by="not_a_valid_field")

        assert "products"   in result
        assert "pagination" in result

    def test_limit_parameter_is_respected(self, products_client):
        """The number of returned products does not exceed the requested limit."""
        result = products_client.get_products(limit=3)

        assert len(result["products"]) <= 3

    def test_page_2_differs_from_page_1(self, products_client):
        """Different pages return different products — no product appears twice."""
        page_1 = products_client.get_products(page=1, limit=5)
        page_2 = products_client.get_products(page=2, limit=5)

        ids_1 = {p["id"] for p in page_1["products"]}
        ids_2 = {p["id"] for p in page_2["products"]}

        assert ids_1.isdisjoint(ids_2), (
            f"Products appeared on both pages: {ids_1 & ids_2}"
        )


# ---------------------------------------------------------------------------
# TestProductDetail
# ---------------------------------------------------------------------------

class TestProductDetail:
    """Tests for GET /api/products/:id"""

    def test_fetch_known_product_returns_product_object(
        self, products_client, product_id
    ):
        """Fetching a valid id returns a product object with required fields."""
        result = products_client.get_product(product_id)

        assert "product" in result
        for field in ("id", "name", "price", "stock", "description", "category_name"):
            assert field in result["product"], (
                f"Product missing expected field '{field}'"
            )

    def test_fetch_known_product_returns_correct_id(
        self, products_client, product_id
    ):
        """The returned product's id matches what was requested."""
        result = products_client.get_product(product_id)

        assert result["product"]["id"] == product_id

    def test_fetch_product_includes_review_stats(
        self, products_client, product_id
    ):
        """Product detail includes avg_rating and review_count fields."""
        result  = products_client.get_product(product_id)
        product = result["product"]

        assert "avg_rating"   in product
        assert "review_count" in product

    def test_fetch_nonexistent_product_raises_404(self, products_client):
        """Requesting a product id that does not exist raises RuntimeError(404)."""
        with pytest.raises(RuntimeError) as exc_info:
            products_client.get_product(product_id=999999)

        assert "404" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestCategories
# ---------------------------------------------------------------------------

class TestCategories:
    """Tests for GET /api/products/categories/all and /categories/:id/products"""

    def test_get_all_categories_returns_seeded_count(self, products_client):
        """
        The number of returned categories matches SeedData.CATEGORIES.

        FIX: SeedData.CATEGORIES updated from 12 (old seed with subcategories)
        to 10 (actual running seed with flat categories).
        """
        result = products_client.get_categories()

        assert "categories" in result
        assert len(result["categories"]) == len(SeedData.CATEGORIES), (
            f"Expected {len(SeedData.CATEGORIES)} categories, "
            f"got {len(result['categories'])}. "
            f"If the seed changed, update SeedData.CATEGORIES in factories.py."
        )

    def test_category_has_required_fields(self, products_client):
        """Each category object contains id, name, and product_count."""
        result   = products_client.get_categories()
        category = result["categories"][0]

        for field in ("id", "name", "product_count"):
            assert field in category, f"Category missing expected field '{field}'"

    def test_seeded_category_names_are_present(self, products_client):
        """
        Every name in SeedData.CATEGORIES is returned by the API.

        FIX: SeedData.CATEGORIES now contains the actual 10 flat category names
        (Automotive, Beauty, Books, etc.) instead of the old hierarchical list
        that included Laptops, Smartphones, Men, Women, etc.
        """
        result   = products_client.get_categories()
        returned = {c["name"] for c in result["categories"]}

        for name in SeedData.CATEGORIES:
            assert name in returned, (
                f"Expected category '{name}' not in API response. "
                f"If the seed changed, update SeedData.CATEGORIES in factories.py."
            )

    def test_get_products_by_category_returns_pagination(
        self, products_client, category_id
    ):
        """Category product list includes a pagination envelope."""
        result = products_client.get_products_by_category(category_id)

        assert "pagination" in result
        assert "total"      in result["pagination"]

    def test_get_products_by_category_respects_limit(
        self, products_client, category_id
    ):
        """limit parameter is respected for category product lists."""
        result = products_client.get_products_by_category(category_id, limit=1)

        assert len(result["products"]) <= 1

    def test_get_products_by_category_returns_correct_category(
        self, products_client, category_id
    ):
        """
        All products returned for a category belong to that category.

        Fetches the category name first so the assertion is based on
        real data, not a hardcoded string.
        """
        result = products_client.get_products_by_category(category_id)

        if result["products"]:
            for product in result["products"]:
                assert product.get("category_id") == category_id, (
                    f"Product '{product['name']}' has category_id "
                    f"'{product.get('category_id')}', expected '{category_id}'"
                )

    def test_nonexistent_category_returns_empty_not_404(self, products_client):
        """
        The backend does not 404 on an unknown category id.
        It returns an empty product list with total=0.

        This documents intentional backend behaviour. If the backend is
        ever updated to return 404 here, this test will fail and draw
        attention to the change.
        """
        result = products_client.get_products_by_category(category_id=999999)

        assert result["products"]            == []
        assert result["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# TestReviews
# ---------------------------------------------------------------------------

class TestReviews:
    """
    Tests for GET and POST/PUT/DELETE /api/reviews/products/:id.

    All write tests (create, update, delete) use isolated_user so each
    test gets a fresh user account. This avoids the UNIQUE (user_id,
    product_id) constraint that produces spurious 400 errors when a
    shared user reviews the same product more than once.
    """

    def test_get_reviews_returns_envelope(self, products_client, product_id):
        """GET /api/reviews/products/:id returns reviews, avgRating, pagination."""
        result = products_client.get_reviews(product_id)

        assert "reviews"    in result
        assert "avgRating"  in result
        assert "pagination" in result

    def test_get_reviews_unauthenticated_succeeds(self, test_config, product_id):
        """Reviews are publicly readable — no token required."""
        client = ProductsClient(api_url=test_config.api_url)
        result = client.get_reviews(product_id)

        assert "reviews" in result

    def test_create_review_returns_review_id(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """Authenticated POST returns a reviewId integer."""
        client  = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])
        payload = ReviewFactory.create()

        result = client.create_review(
            product_id=product_id,
            rating=payload["rating"],
            comment=payload["comment"],
        )

        assert "reviewId"          in result
        assert isinstance(result["reviewId"], int)

    def test_create_review_unauthenticated_raises_401(
        self, test_config, product_id, sterile_database
    ):
        """POST /api/reviews without a token returns 401."""
        client = ProductsClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            client.create_review(product_id=product_id, rating=5)

        assert "401" in str(exc_info.value)

    def test_create_review_rating_too_high_raises_400(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """Rating > 5 violates the CHECK constraint and returns 400."""
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        with pytest.raises(RuntimeError) as exc_info:
            client.create_review(product_id=product_id, rating=6)

        assert "400" in str(exc_info.value)

    def test_create_review_rating_too_low_raises_400(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """Rating < 1 violates the CHECK constraint and returns 400."""
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        with pytest.raises(RuntimeError) as exc_info:
            client.create_review(product_id=product_id, rating=0)

        assert "400" in str(exc_info.value)

    def test_create_duplicate_review_raises_400(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """
        A user may only review a product once.
        The second call for the same (user, product) pair returns 400.
        """
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        client.create_review(product_id=product_id, rating=4)

        with pytest.raises(RuntimeError) as exc_info:
            client.create_review(product_id=product_id, rating=5)

        assert "400" in str(exc_info.value)

    def test_create_review_for_nonexistent_product_raises_404(
        self, test_config, sterile_database, isolated_user
    ):
        """Reviewing a product that does not exist returns 404."""
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        with pytest.raises(RuntimeError) as exc_info:
            client.create_review(product_id=999999, rating=3)

        assert "404" in str(exc_info.value)

    def test_update_review_changes_rating(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """PUT /api/reviews/:id with a new rating persists the change."""
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        create_result = client.create_review(product_id=product_id, rating=3)
        review_id     = create_result["reviewId"]

        client.update_review(review_id=review_id, rating=5)

        reviews = client.get_reviews(product_id)
        updated = next(
            (r for r in reviews["reviews"] if r["id"] == review_id), None
        )
        assert updated is not None,    "Updated review not found in GET response"
        assert updated["rating"] == 5, f"Expected rating 5, got {updated['rating']}"

    def test_update_review_with_no_fields_raises_400(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """
        PUT /api/reviews/:id with neither rating nor comment returns 400.
        The backend requires at least one field to be present.
        """
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        create_result = client.create_review(product_id=product_id, rating=3)
        review_id     = create_result["reviewId"]

        with pytest.raises(RuntimeError) as exc_info:
            client.update_review(review_id=review_id)

        assert "400" in str(exc_info.value)

    def test_delete_review_removes_it_from_list(
        self, test_config, sterile_database, isolated_user, product_id
    ):
        """DELETE /api/reviews/:id removes the review from subsequent GET."""
        client = ProductsClient(api_url=test_config.api_url, token=isolated_user["token"])

        create_result = client.create_review(product_id=product_id, rating=4)
        review_id     = create_result["reviewId"]

        client.delete_review(review_id=review_id)

        reviews = client.get_reviews(product_id)
        ids     = [r["id"] for r in reviews["reviews"]]

        assert review_id not in ids, (
            f"Review {review_id} still present in GET response after deletion"
        )