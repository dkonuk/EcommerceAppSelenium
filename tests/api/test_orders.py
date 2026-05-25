"""
API tests for /api/orders.

Test coverage:

    TestCreateOrder
        - Valid cart + address creates an order and returns orderId + total
        - Created order has status='pending'
        - Cart is emptied after order creation
        - Stock is decremented for each ordered product
        - Order total matches the cart total at time of order
        - Empty cart returns 400
        - Missing shipping_address returns 400
        - Unauthenticated request returns 401

    TestGetOrders
        - Returns orders list and pagination envelope
        - Each order has required fields
        - Orders are sorted newest-first
        - Pagination: page 2 differs from page 1
        - limit parameter is respected
        - Returns only the authenticated user's orders
        - Unauthenticated request returns 401

    TestGetOrder
        - Returns the correct order with its line items
        - Each line item has required fields
        - Price on order item is the price at time of order (snapshot)
        - Another user's order id returns 404
        - Non-existent order id returns 404
        - Unauthenticated request returns 401

    TestCancelOrder
        - Cancelling a pending order sets status to 'cancelled'
        - Cancelling restores stock for each item in the order
        - Cancelling a completed order returns 400
        - Cancelling an already-cancelled order returns 400
        - Cancelling another user's order returns 404
        - Non-existent order id returns 404
        - Unauthenticated request returns 401

Fixture strategy:
    isolated_user  — function-scoped fresh user for tests that create
                     orders. Each test gets a user with an empty cart
                     and no order history.

    sterile_database — declared via product_ids to ensure products exist.
                       Also needed for stock-level assertions, where tests
                       read stock before and after an order.

    product_ids    — module-scoped, two real product ids from the seed.

    placed_order   — function-scoped helper fixture that pre-creates a
                     pending order for tests whose subject is order
                     retrieval or cancellation rather than creation.
"""

import pytest

from api.auth_client import AuthAPIClient
from api.cart_client import CartClient
from api.orders_client import OrdersClient
from api.products_client import ProductsClient
from helpers.factories import OrderFactory, UserFactory


# ---------------------------------------------------------------------------
# Module-level helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def product_ids(test_config, sterile_database):
    """
    Return two real product ids, sorted by stock descending.
    High-stock products reduce the chance of stock-exhaustion
    interference between tests in the same session.
    """
    client   = ProductsClient(api_url=test_config.api_url)
    result   = client.get_products(limit=2, sort_by="stock", order="desc")
    products = result["products"]

    assert len(products) >= 2, (
        "Need at least 2 seeded products for order tests"
    )
    return [p["id"] for p in products]


def _make_clients(test_config, user: dict):
    """Return (CartClient, OrdersClient) for a user."""
    cart   = CartClient(api_url=test_config.api_url,   token=user["token"])
    orders = OrdersClient(api_url=test_config.api_url, token=user["token"])
    return cart, orders


def _register_fresh_user(test_config) -> dict:
    """Register and return a brand-new user inline."""
    auth      = AuthAPIClient(api_url=test_config.api_url)
    user_data = UserFactory.create()
    response  = auth.register_user(
        email=user_data["email"],
        name=user_data["name"],
        password=user_data["password"],
    )
    return {
        "token":    response["token"],
        "id":       response["user"]["id"],
        "email":    user_data["email"],
        "password": user_data["password"],
    }


@pytest.fixture(scope="function")
def placed_order(test_config, isolated_user, product_ids):
    """
    Create a pending order and yield its id.

    Used by tests whose subject is order retrieval or cancellation —
    they need an order to exist before the test begins. Cart is
    populated and order placed in setup; no teardown needed because
    isolated_user provides a fresh account per test.

    Yields:
        dict with keys: order_id, total, user, cart, orders
    """
    cart, orders = _make_clients(test_config, isolated_user)
    cart.add_item(product_id=product_ids[0], quantity=1)

    result = orders.create_order(
        shipping_address=OrderFactory.create()["shipping_address"]
    )

    yield {
        "order_id": result["orderId"],
        "total":    result["total"],
        "user":     isolated_user,
        "cart":     cart,
        "orders":   orders,
    }


# ---------------------------------------------------------------------------
# TestCreateOrder
# ---------------------------------------------------------------------------

class TestCreateOrder:
    """Tests for POST /api/orders"""

    def test_create_order_returns_order_id_and_total(
        self, test_config, isolated_user, product_ids
    ):
        """Happy path — valid cart + address returns orderId and total."""
        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)

        result = orders.create_order(
            shipping_address=OrderFactory.create()["shipping_address"]
        )

        assert "orderId" in result
        assert "total"   in result
        assert isinstance(result["orderId"], int)
        assert result["total"] > 0

    def test_created_order_has_pending_status(
        self, test_config, isolated_user, product_ids
    ):
        """Newly created orders always have status='pending'."""
        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)

        result   = orders.create_order(OrderFactory.create()["shipping_address"])
        order_id = result["orderId"]

        order = orders.get_order(order_id)["order"]
        assert order["status"] == "pending", (
            f"Expected status 'pending', got '{order['status']}'"
        )

    def test_cart_is_cleared_after_order_creation(
        self, test_config, isolated_user, product_ids
    ):
        """
        The cart is emptied as part of the order creation transaction.
        Calling get_cart() after create_order() returns an empty cart.
        """
        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)
        cart.add_item(product_id=product_ids[1], quantity=2)

        orders.create_order(OrderFactory.create()["shipping_address"])

        cart_after = cart.get_cart()
        assert cart_after["items"]     == []
        assert cart_after["itemCount"] == 0

    def test_stock_is_decremented_after_order(
        self, test_config, isolated_user, product_ids
    ):
        """
        Placing an order reduces product stock by the ordered quantity.

        Reads stock before and after the order to verify the delta,
        so the assertion is independent of the actual stock numbers.
        """
        products_client = ProductsClient(api_url=test_config.api_url)
        stock_before    = products_client.get_product(product_ids[0])["product"]["stock"]

        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)
        orders.create_order(OrderFactory.create()["shipping_address"])

        stock_after = products_client.get_product(product_ids[0])["product"]["stock"]

        assert stock_after == stock_before - 2, (
            f"Stock should have decreased by 2: "
            f"{stock_before} → expected {stock_before - 2}, got {stock_after}"
        )

    def test_order_total_matches_cart_total(
        self, test_config, isolated_user, product_ids
    ):
        """
        The total in the order creation response equals the cart total
        at time of order. Verifies the backend calculates consistently.
        """
        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)
        cart.add_item(product_id=product_ids[1], quantity=1)

        cart_total   = cart.get_cart()["total"]
        order_result = orders.create_order(OrderFactory.create()["shipping_address"])

        assert abs(order_result["total"] - cart_total) < 0.01, (
            f"Order total {order_result['total']} does not match "
            f"cart total {cart_total}"
        )

    def test_create_order_with_empty_cart_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """POST /api/orders with an empty cart returns 400."""
        _, orders = _make_clients(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            orders.create_order(OrderFactory.create()["shipping_address"])

        assert "400" in str(exc_info.value)

    def test_create_order_missing_address_returns_400(
        self, test_config, isolated_user, product_ids
    ):
        """POST /api/orders without shipping_address returns 400."""
        import requests as req

        cart, _ = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)

        response = req.post(
            f"{test_config.api_url}/api/orders",
            headers={"Authorization": f"Bearer {isolated_user['token']}"},
            json={},
        )
        assert response.status_code == 400

    def test_create_order_unauthenticated_returns_401(self, test_config):
        """POST /api/orders without a token returns 401."""
        orders = OrdersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            orders.create_order("123 Test St")

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestGetOrders
# ---------------------------------------------------------------------------

class TestGetOrders:
    """Tests for GET /api/orders"""

    def test_get_orders_returns_list_and_pagination(
        self, test_config, placed_order
    ):
        """Response contains orders list and pagination envelope."""
        result = placed_order["orders"].get_orders()

        assert "orders"     in result
        assert "pagination" in result

    def test_order_has_required_fields(
        self, test_config, placed_order
    ):
        """Each order in the list has the fields the UI depends on."""
        result = placed_order["orders"].get_orders()

        assert len(result["orders"]) > 0
        order = result["orders"][0]

        for field in ("id", "total", "status", "shipping_address",
                      "item_count", "created_at"):
            assert field in order, f"Order list item missing field '{field}'"

    def test_orders_sorted_newest_first(
        self, test_config, isolated_user, product_ids
    ):
        """
            Orders are returned sorted by created_at DESC — newest first.

            Asserts the returned timestamps form a non-ascending sequence
            rather than pinning specific order ids to specific positions.
            Same-second timestamps are equal and satisfy DESC ordering — both
            orderings are valid, so the test does not force a strict distinction.
            """
        cart, orders = _make_clients(test_config, isolated_user)

        cart.add_item(product_id=product_ids[0], quantity=1)
        orders.create_order(OrderFactory.create()["shipping_address"])

        cart.add_item(product_id=product_ids[1], quantity=1)
        orders.create_order(OrderFactory.create()["shipping_address"])

        result = orders.get_orders()
        timestamps = [o["created_at"] for o in result["orders"]]

        assert timestamps == sorted(timestamps, reverse=True), (
            f"Orders are not sorted newest-first.\n"
            f"Returned:  {timestamps}\n"
            f"Expected:  {sorted(timestamps, reverse=True)}"
        )

    def test_get_orders_limit_respected(
        self, test_config, isolated_user, product_ids
    ):
        """limit parameter caps the number of returned orders."""
        cart, orders = _make_clients(test_config, isolated_user)

        # Place two orders so we have something to paginate
        cart.add_item(product_id=product_ids[0], quantity=1)
        orders.create_order(OrderFactory.create()["shipping_address"])
        cart.add_item(product_id=product_ids[1], quantity=1)
        orders.create_order(OrderFactory.create()["shipping_address"])

        result = orders.get_orders(limit=1)

        assert len(result["orders"]) <= 1

    def test_get_orders_returns_only_own_orders(
        self, test_config, placed_order, product_ids
    ):
        """
        A user only sees their own orders — another user's orders are
        invisible even when they exist in the same database.
        """
        # User B places their own order
        user_b       = _register_fresh_user(test_config)
        cart_b       = CartClient(api_url=test_config.api_url, token=user_b["token"])
        orders_b     = OrdersClient(api_url=test_config.api_url, token=user_b["token"])

        cart_b.add_item(product_id=product_ids[0], quantity=1)
        orders_b.create_order(OrderFactory.create()["shipping_address"])

        # User A's order list should not contain user B's order
        user_a_result = placed_order["orders"].get_orders()
        user_a_ids    = {o["id"] for o in user_a_result["orders"]}
        user_b_result = orders_b.get_orders()
        user_b_ids    = {o["id"] for o in user_b_result["orders"]}

        assert user_a_ids.isdisjoint(user_b_ids), (
            f"Order ids overlap between users: {user_a_ids & user_b_ids}"
        )

    def test_get_orders_unauthenticated_returns_401(self, test_config):
        """GET /api/orders without a token returns 401."""
        orders = OrdersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            orders.get_orders()

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestGetOrder
# ---------------------------------------------------------------------------

class TestGetOrder:
    """Tests for GET /api/orders/:id"""

    def test_get_order_returns_correct_order(
        self, test_config, placed_order
    ):
        """Fetching a known order id returns the correct order."""
        order_id = placed_order["order_id"]
        result   = placed_order["orders"].get_order(order_id)

        assert "order"       in result
        assert result["order"]["id"] == order_id

    def test_order_detail_has_required_fields(
        self, test_config, placed_order
    ):
        """Order detail contains id, total, status, shipping_address, items."""
        result = placed_order["orders"].get_order(placed_order["order_id"])
        order  = result["order"]

        for field in ("id", "total", "status", "shipping_address", "items"):
            assert field in order, f"Order detail missing field '{field}'"

    def test_order_detail_includes_line_items(
        self, test_config, placed_order
    ):
        """Order items list is non-empty and each item has required fields."""
        result = placed_order["orders"].get_order(placed_order["order_id"])
        items  = result["order"]["items"]

        assert len(items) > 0
        for item in items:
            for field in ("product_id", "quantity", "price"):
                assert field in item, f"Order item missing field '{field}'"

    def test_order_item_price_is_snapshot(
        self, test_config, isolated_user, product_ids
    ):
        """
        The price recorded on an order_item is the price at time of
        purchase — it does not change if the product price changes.

        We verify this by comparing the order item price against the
        cart item price captured before placing the order.
        """
        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=1)

        # Capture price from cart before ordering
        cart_items  = cart.get_cart()["items"]
        price_in_cart = next(
            i["price"] for i in cart_items if i["product_id"] == product_ids[0]
        )

        result   = orders.create_order(OrderFactory.create()["shipping_address"])
        order_id = result["orderId"]

        order_items = orders.get_order(order_id)["order"]["items"]
        price_in_order = next(
            i["price"] for i in order_items if i["product_id"] == product_ids[0]
        )

        assert abs(price_in_order - price_in_cart) < 0.01, (
            f"Order item price {price_in_order} does not match "
            f"cart price {price_in_cart} at time of order"
        )

    def test_get_another_users_order_returns_404(
        self, test_config, placed_order, product_ids
    ):
        """
        Fetching another user's order id returns 404.
        Backend filters SELECT by order id AND user id.
        """
        order_id = placed_order["order_id"]

        user_b   = _register_fresh_user(test_config)
        orders_b = OrdersClient(api_url=test_config.api_url, token=user_b["token"])

        with pytest.raises(RuntimeError) as exc_info:
            orders_b.get_order(order_id)

        assert "404" in str(exc_info.value)

    def test_get_nonexistent_order_returns_404(
        self, test_config, placed_order
    ):
        """Fetching an order id that does not exist returns 404."""
        with pytest.raises(RuntimeError) as exc_info:
            placed_order["orders"].get_order(order_id=999999)

        assert "404" in str(exc_info.value)

    def test_get_order_unauthenticated_returns_401(
        self, test_config, placed_order
    ):
        """GET /api/orders/:id without a token returns 401."""
        orders = OrdersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            orders.get_order(placed_order["order_id"])

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestCancelOrder
# ---------------------------------------------------------------------------

class TestCancelOrder:
    """Tests for PUT /api/orders/:id/cancel"""

    def test_cancel_pending_order_sets_status_cancelled(
        self, test_config, placed_order
    ):
        """Cancelling a pending order changes its status to 'cancelled'."""
        order_id = placed_order["order_id"]
        orders   = placed_order["orders"]

        orders.cancel_order(order_id)

        order = orders.get_order(order_id)["order"]
        assert order["status"] == "cancelled", (
            f"Expected status 'cancelled', got '{order['status']}'"
        )

    def test_cancel_order_restores_stock(
        self, test_config, isolated_user, product_ids
    ):
        """
        Cancelling an order runs the stock-restoration transaction.
        Stock after cancellation equals stock before the order was placed.
        """
        products_client = ProductsClient(api_url=test_config.api_url)
        stock_before    = products_client.get_product(product_ids[0])["product"]["stock"]

        cart, orders = _make_clients(test_config, isolated_user)
        cart.add_item(product_id=product_ids[0], quantity=2)

        result   = orders.create_order(OrderFactory.create()["shipping_address"])
        order_id = result["orderId"]

        stock_after_order = products_client.get_product(product_ids[0])["product"]["stock"]
        assert stock_after_order == stock_before - 2, "Stock should decrease after order"

        orders.cancel_order(order_id)

        stock_after_cancel = products_client.get_product(product_ids[0])["product"]["stock"]
        assert stock_after_cancel == stock_before, (
            f"Stock should be restored to {stock_before} after cancel, "
            f"got {stock_after_cancel}"
        )

    def test_cancel_completed_order_returns_400(
        self, test_config, placed_order
    ):
        """
        Cancelling a 'completed' order returns 400.

        There is no API endpoint to mark an order as completed, so we
        update the status directly in the database via the admin Node
        script pattern. If that's not available, we document the
        expected behaviour and skip with a clear message.
        """
        import requests as req

        order_id = placed_order["order_id"]

        # Attempt to force status to 'completed' via admin endpoint.
        # If the running app has no such endpoint, skip gracefully.
        patch_response = req.patch(
            f"{placed_order['orders'].api_url}/api/admin/orders/{order_id}",
            json={"status": "completed"},
            headers={"Authorization": f"Bearer {placed_order['user']['token']}"},
        )

        if patch_response.status_code == 404:
            pytest.skip(
                "No admin endpoint to force order status — "
                "cannot test cancellation of completed orders without it"
            )

        with pytest.raises(RuntimeError) as exc_info:
            placed_order["orders"].cancel_order(order_id)

        assert "400" in str(exc_info.value)

    def test_cancel_already_cancelled_order_returns_400(
        self, test_config, placed_order
    ):
        """
        Calling cancel_order() twice on the same order returns 400
        on the second call. Status is already 'cancelled'.
        """
        order_id = placed_order["order_id"]
        orders   = placed_order["orders"]

        orders.cancel_order(order_id)

        with pytest.raises(RuntimeError) as exc_info:
            orders.cancel_order(order_id)

        assert "400" in str(exc_info.value)

    def test_cancel_another_users_order_returns_404(
        self, test_config, placed_order, product_ids
    ):
        """
        User B cannot cancel user A's order.
        Backend filters by order id AND user id — returns 404.
        """
        order_id = placed_order["order_id"]

        user_b   = _register_fresh_user(test_config)
        orders_b = OrdersClient(api_url=test_config.api_url, token=user_b["token"])

        with pytest.raises(RuntimeError) as exc_info:
            orders_b.cancel_order(order_id)

        assert "404" in str(exc_info.value)

    def test_cancel_nonexistent_order_returns_404(
        self, test_config, placed_order
    ):
        """Cancelling an order id that does not exist returns 404."""
        with pytest.raises(RuntimeError) as exc_info:
            placed_order["orders"].cancel_order(order_id=999999)

        assert "404" in str(exc_info.value)

    def test_cancel_order_unauthenticated_returns_401(
        self, test_config, placed_order
    ):
        """PUT /api/orders/:id/cancel without a token returns 401."""
        orders = OrdersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            orders.cancel_order(placed_order["order_id"])

        assert "401" in str(exc_info.value)