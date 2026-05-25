"""
HTTP client for the /api/orders endpoint group.

All order endpoints require authentication — always initialise this
client with a token.

Endpoints covered:
    POST /api/orders            → create_order()
    GET  /api/orders            → get_orders()
    GET  /api/orders/:id        → get_order()
    PUT  /api/orders/:id/cancel → cancel_order()

Critical backend behaviours to understand before writing tests:

    create_order() consumes the entire cart.
        The order is built from whatever is in the user's cart at the time
        of the call. After a successful call:
            - Every cart item is deleted
            - Product stock is decremented for each item
            - The order is created with status "pending"

        This has two test implications:
            1. The cart MUST be non-empty before calling create_order().
               An empty cart returns 400. Always populate the cart first
               using CartClient.add_item() or CartClient.add_items().
            2. Stock is permanently reduced until the order is cancelled
               or the database is reset. Tests that check stock levels
               after placing an order must account for this.

    cancel_order() restores stock via a transaction.
        Cancelling an order runs a transaction that restores the stock
        for every item in the order. This is the only way to return stock
        without resetting the database, which makes cancel_order() useful
        in test teardown when you need stock to be intact for the next test.

    Status transitions:
        pending   → can be cancelled
        completed → cannot be cancelled (400)
        cancelled → cannot be cancelled again (400)

        There is no endpoint to move an order to "completed" — that
        would be an admin operation. Tests that need to verify the
        "cannot cancel completed order" behaviour must either use
        the admin client to update the order status directly or update
        the database through the admin reset/seed cycle.
"""

import logging
from typing import Optional

from api.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class OrdersClient(BaseAPIClient):
    """
    Client for /api/orders.

    Requires a token — all order routes enforce authentication.

    Typical test setup pattern:
        # 1. Create a user with an empty cart
        user = isolated_user   # from auth_fixtures

        # 2. Populate the cart
        cart = CartClient(api_url=test_config.api_url, token=user["token"])
        cart.add_items([{"product_id": 1}, {"product_id": 2, "quantity": 3}])

        # 3. Place the order
        orders = OrdersClient(api_url=test_config.api_url, token=user["token"])
        result = orders.create_order(shipping_address="123 Test St, City, 00000")

        # result["orderId"] is the id to use for get_order() and cancel_order()
    """

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def create_order(self, shipping_address: str) -> dict:
        """
        POST /api/orders — place an order from the current cart contents.

        Reads the cart, validates stock, creates the order record and
        order_items rows, decrements product stock, and clears the cart —
        all in a single database transaction.

        Args:
            shipping_address: Delivery address string. Required — the
                              backend returns 400 if missing or empty.
                              Use OrderFactory.create()["shipping_address"]
                              for a realistic random address.

        Returns:
            {
                "message": "Order created successfully",
                "orderId": int,
                "total":   float
            }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if the cart is empty.
            RuntimeError: 400 if any cart item has insufficient stock.
            RuntimeError: 400 if shipping_address is missing.
        """
        logger.debug(f"create_order: shipping_address='{shipping_address}'")
        return self._post("/api/orders", json={
            "shipping_address": shipping_address,
        })

    def cancel_order(self, order_id: int) -> dict:
        """
        PUT /api/orders/:id/cancel — cancel a pending order.

        Runs a transaction that restores stock for every item in the order
        and sets the order status to "cancelled".

        Args:
            order_id: The order's integer id.

        Returns:
            { "message": "Order cancelled successfully" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if the order status is "completed".
            RuntimeError: 400 if the order is already "cancelled".
            RuntimeError: 404 if the order does not exist or belongs to
                          a different user.
        """
        logger.debug(f"cancel_order: order_id={order_id}")
        return self._put(f"/api/orders/{order_id}/cancel")

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_orders(
        self,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        GET /api/orders — list the authenticated user's orders.

        Results are sorted newest-first by the backend (ORDER BY
        created_at DESC). Pagination defaults to page=1, limit=10.

        Args:
            page:  Page number, 1-based.
            limit: Results per page.

        Returns:
            {
                "orders": [
                    {
                        "id":               int,
                        "total":            float,
                        "status":           "pending" | "completed" | "cancelled",
                        "shipping_address": str,
                        "item_count":       int,
                        "created_at":       str,
                        "updated_at":       str
                    },
                    ...
                ],
                "pagination": { "page", "limit", "total", "totalPages" }
            }

        Raises:
            RuntimeError: 401 if not authenticated.
        """
        return self._get("/api/orders", params={"page": page, "limit": limit})

    def get_order(self, order_id: int) -> dict:
        """
        GET /api/orders/:id — fetch a single order with its line items.

        Args:
            order_id: The order's integer id.

        Returns:
            {
                "order": {
                    "id":               int,
                    "total":            float,
                    "status":           "pending" | "completed" | "cancelled",
                    "shipping_address": str,
                    "created_at":       str,
                    "updated_at":       str,
                    "items": [
                        {
                            "product_id": int,
                            "quantity":   int,
                            "price":      float,  # price at time of order
                            "name":       str,    # product name (joined)
                            "image_url":  str
                        },
                        ...
                    ]
                }
            }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 404 if the order does not exist or belongs to
                          a different user.
        """
        return self._get(f"/api/orders/{order_id}")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def place_order_from_cart(
        self,
        cart_client,
        products: list,
        shipping_address: str,
    ) -> dict:
        """
        Populate the cart and place an order in a single call.

        Combines CartClient.add_items() and create_order() into one
        helper for tests whose subject is order state (order history,
        order detail page, cancellation flow) rather than the checkout
        process itself.

        Args:
            cart_client:      An authenticated CartClient for the same user.
            products:         List of dicts passed directly to CartClient.add_items().
                              Each dict needs "product_id" and optional "quantity".
            shipping_address: Passed directly to create_order().

        Returns:
            The create_order() response dict:
            { "message": "Order created successfully", "orderId": int, "total": float }

        Example:
            orders = OrdersClient(api_url=test_config.api_url, token=user["token"])
            cart   = CartClient(api_url=test_config.api_url,   token=user["token"])

            result = orders.place_order_from_cart(
                cart_client=cart,
                products=[{"product_id": 1}, {"product_id": 2, "quantity": 2}],
                shipping_address=OrderFactory.create()["shipping_address"],
            )
            order_id = result["orderId"]
        """
        cart_client.add_items(products)
        return self.create_order(shipping_address=shipping_address)