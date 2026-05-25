"""
HTTP client for the /api/cart endpoint group.

All cart endpoints require authentication — this client must always be
initialised with a token. Calling any method on a tokenless instance
raises RuntimeError(401).

Endpoints covered:
    GET    /api/cart            → get_cart()
    POST   /api/cart/items      → add_item()
    PUT    /api/cart/items/:id  → update_item()
    DELETE /api/cart/items/:id  → remove_item()
    DELETE /api/cart            → clear_cart()

Key backend behaviour to be aware of when writing tests:

    add_item() is not idempotent.
        If the product is already in the cart, calling add_item() again
        INCREMENTS the stored quantity by the amount you pass. It does not
        replace it. This means:

            add_item(product_id=1, quantity=2)  → cart has 2 units
            add_item(product_id=1, quantity=1)  → cart now has 3 units

        Use update_item() when you want to SET an absolute quantity.

    add_item() returns 201 for new items, 200 for quantity increments.
        BaseAPIClient._handle() treats both as success (response.ok covers
        all 2xx codes), so you don't need to handle this difference in tests
        unless you're specifically testing the status code.

    The cart is user-scoped.
        Every query is filtered by the authenticated user's id on the backend.
        One user's cart is completely invisible to another user. Tests using
        isolated_user (from auth_fixtures.py) get a naturally empty cart
        with no setup needed.
"""

import logging
from typing import Optional

from api.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class CartClient(BaseAPIClient):
    """
    Client for /api/cart.

    Requires a token — all cart routes enforce authentication.

    Example:
        cart = CartClient(api_url=test_config.api_url, token=user["token"])

        cart.add_item(product_id=1, quantity=2)
        cart.add_item(product_id=3)           # quantity defaults to 1

        result = cart.get_cart()
        assert result["itemCount"] == 3
        assert result["total"] > 0

        cart.clear_cart()
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_cart(self) -> dict:
        """
        GET /api/cart — fetch the authenticated user's cart.

        Returns:
            {
                "items": [
                    {
                        "id":         int,    # cart item id (used for update/delete)
                        "product_id": int,
                        "quantity":   int,
                        "name":       str,    # product name (joined)
                        "price":      float,  # unit price
                        "stock":      int,    # available stock
                        "image_url":  str
                    },
                    ...
                ],
                "total":     float,  # sum of (price × quantity) for all items
                "itemCount": int     # sum of all quantities
            }

        Raises:
            RuntimeError: 401 if called without a token.
        """
        return self._get("/api/cart")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_item(self, product_id: int, quantity: int = 1) -> dict:
        """
        POST /api/cart/items — add a product to the cart, or increment
        its quantity if it is already present.

        Read the module docstring before using this in state-setup code.
        If you need the cart to contain exactly N units of a product,
        start with an empty cart (isolated_user gives you one) and call
        add_item once, rather than calling it multiple times.

        Args:
            product_id: The product's integer id.
            quantity:   Units to add. Defaults to 1. Must be >= 1.

        Returns:
            New item:      { "message": "Item added to cart",  "itemId": int }
            Existing item: { "message": "Cart updated",        "itemId": int }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if quantity < 1 or insufficient stock.
            RuntimeError: 404 if the product does not exist.
        """
        return self._post("/api/cart/items", json={
            "product_id": product_id,
            "quantity":   quantity,
        })

    def update_item(self, item_id: int, quantity: int) -> dict:
        """
        PUT /api/cart/items/:id — set the quantity of a cart item.

        Unlike add_item(), this REPLACES the stored quantity rather than
        incrementing it. Use this when a test needs to bring an item to
        an exact quantity regardless of its current state.

        Args:
            item_id:  The cart item's integer id (from get_cart()["items"][n]["id"]).
            quantity: New quantity. Must be >= 1.

        Returns:
            { "message": "Cart item updated" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if quantity < 1 or exceeds available stock.
            RuntimeError: 404 if the item does not exist or belongs to
                          a different user.
        """
        return self._put(f"/api/cart/items/{item_id}", json={"quantity": quantity})

    def remove_item(self, item_id: int) -> dict:
        """
        DELETE /api/cart/items/:id — remove a single item from the cart.

        Args:
            item_id: The cart item's integer id.

        Returns:
            { "message": "Item removed from cart" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 404 if the item does not exist or belongs to
                          a different user.
        """
        return self._delete(f"/api/cart/items/{item_id}")

    def clear_cart(self) -> dict:
        """
        DELETE /api/cart — remove all items from the cart.

        Always succeeds even if the cart is already empty.

        Returns:
            { "message": "Cart cleared" }

        Raises:
            RuntimeError: 401 if not authenticated.
        """
        return self._delete("/api/cart")

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def add_items(self, items: list) -> None:
        """
        Add multiple products to the cart in a single call.

        Convenience helper for state setup in tests that need a populated
        cart before they can exercise their actual subject (checkout,
        order creation, cart UI rendering, etc.).

        Args:
            items: List of dicts, each with:
                       product_id (int, required)
                       quantity   (int, optional — defaults to 1)

        Example:
            cart.add_items([
                {"product_id": 1, "quantity": 2},
                {"product_id": 5},
                {"product_id": 7, "quantity": 3},
            ])

        Raises:
            RuntimeError: On the first item that fails (auth, stock, or
                          not-found errors). Items added before the failure
                          remain in the cart.
        """
        for item in items:
            product_id = item["product_id"]
            quantity   = item.get("quantity", 1)
            self.add_item(product_id=product_id, quantity=quantity)
            logger.debug(f"add_items: added product_id={product_id} qty={quantity}")