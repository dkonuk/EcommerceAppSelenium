"""
API tests for /api/cart.

Test coverage:

    TestGetCart
        - Empty cart returns correct structure with zero total and itemCount
        - Cart with items returns correct itemCount (sum of quantities)
        - Total is calculated correctly (price × quantity per item, summed)
        - Each cart item has the required fields
        - Unauthenticated request returns 401

    TestAddItem
        - Adding a new product returns 201 with an itemId
        - Adding the same product again increments quantity (not a duplicate)
        - Adding with explicit quantity stores that quantity
        - Omitting quantity defaults to 1
        - Adding a non-existent product returns 404
        - quantity=0 returns 400
        - Negative quantity returns 400
        - Quantity exceeding available stock returns 400
        - Incrementing beyond available stock returns 400
        - Unauthenticated request returns 401

    TestUpdateItem
        - Updating quantity replaces the stored value (absolute, not increment)
        - Updated quantity is reflected in subsequent GET
        - quantity=0 returns 400
        - Non-existent item id returns 404
        - Another user's cart item returns 404
        - Quantity exceeding stock returns 400
        - Unauthenticated request returns 401

    TestRemoveItem
        - Removing an item deletes it from the cart
        - Removing one item leaves other items intact
        - Non-existent item id returns 404
        - Another user's cart item returns 404
        - Unauthenticated request returns 401

    TestClearCart
        - Clearing a populated cart empties it completely
        - Clearing an already-empty cart succeeds (idempotent)
        - Unauthenticated request returns 401

Fixture strategy:
    isolated_user — every test gets a function-scoped fresh user with
                    an empty cart. Cart state is user-owned, so a fresh
                    user provides complete isolation without needing
                    isolated_database.

    product_ids   — module-scoped, fetches two real product ids from the
                    seed. Two products enable multi-item cart tests.
                    Depends on sterile_database to ensure products exist.

    sterile_database — only needed indirectly via product_ids. Tests
                       themselves do not need to reset shared state
                       because they only touch user-owned cart data.
"""

import pytest

from api.cart_client import CartClient
from api.auth_client import AuthAPIClient
from helpers.factories import UserFactory


# ---------------------------------------------------------------------------
# Module-level helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def product_ids(test_config, sterile_database):
    """
    Return a list of two real product ids from the seeded database.

    Sorted by stock descending so we always get products with enough
    stock for quantity tests without hitting the stock ceiling.
    """
    from api.products_client import ProductsClient

    client   = ProductsClient(api_url=test_config.api_url)
    result   = client.get_products(limit=2, sort_by="stock", order="desc")
    products = result["products"]

    assert len(products) >= 2, (
        "Need at least 2 seeded products for cart tests — "
        "check sterile_database"
    )
    return [p["id"] for p in products]


def _make_cart(test_config, user: dict) -> CartClient:
    """Build an authenticated CartClient for a user."""
    return CartClient(api_url=test_config.api_url, token=user["token"])


def _register_fresh_user(test_config) -> dict:
    """
    Register and return a brand-new user inline.

    Used in cross-user tests that need a second user without declaring
    another fixture — keeps the test self-contained.
    """
    auth      = AuthAPIClient(api_url=test_config.api_url)
    user_data = UserFactory.create()
    response  = auth.register_user(
        email=user_data["email"],
        name=user_data["name"],
        password=user_data["password"],
    )
    return {"token": response["token"], **user_data}


# ---------------------------------------------------------------------------
# TestGetCart
# ---------------------------------------------------------------------------

class TestGetCart:
    """Tests for GET /api/cart"""

    def test_empty_cart_returns_correct_structure(
        self, test_config, isolated_user, product_ids
    ):
        """
        A brand-new user's cart is empty.
        items=[], total=0, itemCount=0.
        """
        cart   = _make_cart(test_config, isolated_user)
        result = cart.get_cart()

        assert result["items"]     == []
        assert result["total"]     == 0
        assert result["itemCount"] == 0

    def test_cart_item_count_sums_all_quantities(
        self, test_config, isolated_user, product_ids
    ):
        """itemCount is the sum of all quantities, not the number of rows."""
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)
        cart.add_item(product_id=product_ids[1], quantity=3)

        result = cart.get_cart()

        assert result["itemCount"] == 5

    def test_cart_total_equals_price_times_quantity(
        self, test_config, isolated_user, product_ids
    ):
        """
        total == sum(price × quantity) across all items.

        Derives the expected total from the API response itself so the
        assertion is not tied to specific seed prices.
        """
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)
        cart.add_item(product_id=product_ids[1], quantity=1)

        result         = cart.get_cart()
        expected_total = sum(
            item["price"] * item["quantity"]
            for item in result["items"]
        )

        assert abs(result["total"] - expected_total) < 0.01, (
            f"Cart total {result['total']} does not match "
            f"calculated total {expected_total}"
        )

    def test_cart_item_has_required_fields(
        self, test_config, isolated_user, product_ids
    ):
        """Each cart item contains the fields the UI depends on."""
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0])

        item = cart.get_cart()["items"][0]

        for field in ("id", "product_id", "quantity", "name", "price", "stock"):
            assert field in item, f"Cart item missing expected field '{field}'"

    def test_get_cart_unauthenticated_returns_401(self, test_config):
        """GET /api/cart without a token returns 401."""
        cart = CartClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            cart.get_cart()

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestAddItem
# ---------------------------------------------------------------------------

class TestAddItem:
    """Tests for POST /api/cart/items"""

    def test_add_new_item_returns_item_id(
        self, test_config, isolated_user, product_ids
    ):
        """Adding a new product returns an itemId integer."""
        cart   = _make_cart(test_config, isolated_user)
        result = cart.add_item(product_id=product_ids[0])

        assert "itemId"            in result
        assert isinstance(result["itemId"], int)

    def test_add_same_product_increments_quantity(
        self, test_config, isolated_user, product_ids
    ):
        """
        Adding the same product twice increments quantity on the existing
        row rather than creating a second row.

        add(qty=1) then add(qty=2) → one row with quantity=3.
        """
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)
        cart.add_item(product_id=product_ids[0], quantity=2)

        items = cart.get_cart()["items"]
        rows  = [i for i in items if i["product_id"] == product_ids[0]]

        assert len(rows) == 1, (
            "Two rows created for the same product instead of one incremented row"
        )
        assert rows[0]["quantity"] == 3, (
            f"Expected quantity 3 after two adds, got {rows[0]['quantity']}"
        )

    def test_add_item_with_explicit_quantity(
        self, test_config, isolated_user, product_ids
    ):
        """Explicit quantity=3 is stored as 3."""
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=3)

        item = cart.get_cart()["items"][0]

        assert item["quantity"] == 3

    def test_add_item_default_quantity_is_one(
        self, test_config, isolated_user, product_ids
    ):
        """Omitting quantity defaults to 1."""
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0])

        item = cart.get_cart()["items"][0]

        assert item["quantity"] == 1

    def test_add_nonexistent_product_returns_404(
        self, test_config, isolated_user, product_ids
    ):
        """Adding a product id that does not exist returns 404."""
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=999999)

        assert "404" in str(exc_info.value)

    def test_add_item_quantity_zero_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """quantity=0 is rejected — must be >= 1."""
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=product_ids[0], quantity=0)

        assert "400" in str(exc_info.value)

    def test_add_item_negative_quantity_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """Negative quantity is rejected."""
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=product_ids[0], quantity=-1)

        assert "400" in str(exc_info.value)

    def test_add_item_exceeding_stock_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """
        Requesting more units than available stock returns 400.
        Uses quantity=999999 — safely beyond any realistic stock level.
        """
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=product_ids[0], quantity=999999)

        assert "400" in str(exc_info.value)

    def test_increment_beyond_stock_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """
        The combined-quantity check also applies when incrementing.

        First add is valid. Second add pushes combined total beyond stock.
        """
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=product_ids[0], quantity=999998)

        assert "400" in str(exc_info.value)

    def test_add_item_unauthenticated_returns_401(
        self, test_config, product_ids
    ):
        """POST /api/cart/items without a token returns 401."""
        cart = CartClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            cart.add_item(product_id=product_ids[0])

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestUpdateItem
# ---------------------------------------------------------------------------

class TestUpdateItem:
    """Tests for PUT /api/cart/items/:id"""

    def test_update_item_sets_absolute_quantity(
        self, test_config, isolated_user, product_ids
    ):
        """
        update_item() replaces quantity — it does not add to it.
        add(qty=2) then update(qty=5) → quantity=5, not 7.
        """
        cart    = _make_cart(test_config, isolated_user)
        result  = cart.add_item(product_id=product_ids[0], quantity=2)
        item_id = result["itemId"]

        cart.update_item(item_id=item_id, quantity=5)

        items   = cart.get_cart()["items"]
        updated = next(i for i in items if i["id"] == item_id)

        assert updated["quantity"] == 5, (
            f"Expected quantity 5 after update, got {updated['quantity']}"
        )

    def test_update_item_reflected_in_get_cart(
        self, test_config, isolated_user, product_ids
    ):
        """Updated quantity appears in the subsequent GET /api/cart."""
        cart    = _make_cart(test_config, isolated_user)
        result  = cart.add_item(product_id=product_ids[0], quantity=1)
        item_id = result["itemId"]

        cart.update_item(item_id=item_id, quantity=4)

        item = next(
            i for i in cart.get_cart()["items"] if i["id"] == item_id
        )
        assert item["quantity"] == 4

    def test_update_item_quantity_zero_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """quantity=0 is rejected on update as well as add."""
        cart    = _make_cart(test_config, isolated_user)
        result  = cart.add_item(product_id=product_ids[0])
        item_id = result["itemId"]

        with pytest.raises(RuntimeError) as exc_info:
            cart.update_item(item_id=item_id, quantity=0)

        assert "400" in str(exc_info.value)

    def test_update_nonexistent_item_returns_404(
        self, test_config, isolated_user, product_ids
    ):
        """Updating an item id that does not exist returns 404."""
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.update_item(item_id=999999, quantity=1)

        assert "404" in str(exc_info.value)

    def test_update_another_users_item_returns_404(
        self, test_config, isolated_user, product_ids
    ):
        """
        A user cannot update another user's cart item.

        The backend joins cart_items with user_id so another user's item
        is not found — returns 404, not 403.
        """
        cart_a  = _make_cart(test_config, isolated_user)
        result  = cart_a.add_item(product_id=product_ids[0])
        item_id = result["itemId"]

        user_b = _register_fresh_user(test_config)
        cart_b = _make_cart(test_config, user_b)

        with pytest.raises(RuntimeError) as exc_info:
            cart_b.update_item(item_id=item_id, quantity=1)

        assert "404" in str(exc_info.value)

    def test_update_item_exceeding_stock_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """Updating to a quantity beyond available stock returns 400."""
        cart    = _make_cart(test_config, isolated_user)
        result  = cart.add_item(product_id=product_ids[0], quantity=1)
        item_id = result["itemId"]

        with pytest.raises(RuntimeError) as exc_info:
            cart.update_item(item_id=item_id, quantity=999999)

        assert "400" in str(exc_info.value)

    def test_update_item_unauthenticated_returns_401(
        self, test_config, isolated_user, product_ids
    ):
        """PUT /api/cart/items/:id without a token returns 401."""
        cart_auth = _make_cart(test_config, isolated_user)
        result    = cart_auth.add_item(product_id=product_ids[0])
        item_id   = result["itemId"]

        cart_unauth = CartClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            cart_unauth.update_item(item_id=item_id, quantity=2)

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestRemoveItem
# ---------------------------------------------------------------------------

class TestRemoveItem:
    """Tests for DELETE /api/cart/items/:id"""

    def test_remove_item_deletes_it_from_cart(
        self, test_config, isolated_user, product_ids
    ):
        """Removing an item means it is absent from the subsequent GET."""
        cart    = _make_cart(test_config, isolated_user)
        result  = cart.add_item(product_id=product_ids[0])
        item_id = result["itemId"]

        cart.remove_item(item_id=item_id)

        ids = [i["id"] for i in cart.get_cart()["items"]]

        assert item_id not in ids, (
            f"Item {item_id} still in cart after remove_item()"
        )

    def test_remove_item_leaves_other_items_intact(
        self, test_config, isolated_user, product_ids
    ):
        """Removing one item does not affect other items in the cart."""
        cart      = _make_cart(test_config, isolated_user)
        result_0  = cart.add_item(product_id=product_ids[0])
        result_1  = cart.add_item(product_id=product_ids[1])
        item_id_0 = result_0["itemId"]
        item_id_1 = result_1["itemId"]

        cart.remove_item(item_id=item_id_0)

        ids = [i["id"] for i in cart.get_cart()["items"]]

        assert item_id_0 not in ids, "Removed item still present"
        assert item_id_1 in ids,     "Unrelated item was unexpectedly removed"

    def test_remove_nonexistent_item_returns_404(
        self, test_config, isolated_user, product_ids
    ):
        """Removing an item id that does not exist returns 404."""
        cart = _make_cart(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            cart.remove_item(item_id=999999)

        assert "404" in str(exc_info.value)

    def test_remove_another_users_item_returns_404(
        self, test_config, isolated_user, product_ids
    ):
        """
        A user cannot remove another user's cart item.
        Backend DELETE filters by item id AND user id — returns 404.
        """
        cart_a  = _make_cart(test_config, isolated_user)
        result  = cart_a.add_item(product_id=product_ids[0])
        item_id = result["itemId"]

        user_b = _register_fresh_user(test_config)
        cart_b = _make_cart(test_config, user_b)

        with pytest.raises(RuntimeError) as exc_info:
            cart_b.remove_item(item_id=item_id)

        assert "404" in str(exc_info.value)

    def test_remove_item_unauthenticated_returns_401(
        self, test_config, isolated_user, product_ids
    ):
        """DELETE /api/cart/items/:id without a token returns 401."""
        cart_auth = _make_cart(test_config, isolated_user)
        result    = cart_auth.add_item(product_id=product_ids[0])
        item_id   = result["itemId"]

        cart_unauth = CartClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            cart_unauth.remove_item(item_id=item_id)

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestClearCart
# ---------------------------------------------------------------------------

class TestClearCart:
    """Tests for DELETE /api/cart"""

    def test_clear_cart_removes_all_items(
        self, test_config, isolated_user, product_ids
    ):
        """Clearing a populated cart results in items=[], total=0, itemCount=0."""
        cart = _make_cart(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)
        cart.add_item(product_id=product_ids[1], quantity=1)

        cart.clear_cart()

        result = cart.get_cart()

        assert result["items"]     == []
        assert result["total"]     == 0
        assert result["itemCount"] == 0

    def test_clear_empty_cart_is_idempotent(
        self, test_config, isolated_user, product_ids
    ):
        """
        Clearing an already-empty cart succeeds and returns a message.
        Backend runs DELETE WHERE user_id=? which affects zero rows
        but does not raise an error — correct idempotent behaviour.
        """
        cart   = _make_cart(test_config, isolated_user)
        result = cart.clear_cart()

        assert "message" in result

    def test_clear_cart_unauthenticated_returns_401(self, test_config):
        """DELETE /api/cart without a token returns 401."""
        cart = CartClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            cart.clear_cart()

        assert "401" in str(exc_info.value)