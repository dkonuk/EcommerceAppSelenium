"""
HTTP client for the /api/products and /api/reviews endpoint groups.

Both are included here because reviews are always accessed in the context
of a specific product — every review endpoint takes a product id. Keeping
them together avoids a two-import pattern in tests that read a product and
then read or write its reviews.

Endpoints covered:

    Products (all use optionalAuth — work without a token):
        GET  /api/products                          → get_products()
        GET  /api/products/:id                      → get_product()
        GET  /api/products/categories/all           → get_categories()
        GET  /api/products/categories/:id/products  → get_products_by_category()

    Reviews:
        GET  /api/reviews/products/:id   → get_reviews()       (optionalAuth)
        POST /api/reviews/products/:id   → create_review()     (requires token)
        PUT  /api/reviews/:id            → update_review()     (requires token)
        DELETE /api/reviews/:id          → delete_review()     (requires token)

Auth note:
    Products endpoints use optionalAuth on the backend — they return the
    same data with or without a token. Pass a token only if the test needs
    to verify authenticated vs unauthenticated behaviour.

    Review write endpoints (POST/PUT/DELETE) require authentication.
    Calling them on an unauthenticated client will raise a RuntimeError
    with a 401 status — which is the correct test outcome for auth tests.
"""

import logging
from typing import Optional

from api.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class ProductsClient(BaseAPIClient):
    """
    Client for /api/products and /api/reviews.

    Example — unauthenticated product browsing:
        client = ProductsClient(api_url=test_config.api_url)
        result = client.get_products(search="Laptop", sort_by="price")

    Example — authenticated review creation:
        client = ProductsClient(
            api_url=test_config.api_url,
            token=registered_user["token"]
        )
        client.create_review(product_id=1, rating=5, comment="Great!")
    """

    # ------------------------------------------------------------------
    # Products
    # ------------------------------------------------------------------

    def get_products(
        self,
        search: Optional[str] = None,
        category: Optional[int] = None,
        sort_by: Optional[str] = None,
        order: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        GET /api/products — list products with optional filtering and sorting.

        All parameters are optional. Omitting a parameter uses the backend
        default (page=1, limit=20, sortBy=created_at, order=DESC).

        Args:
            search:    Substring to match against product name and description.
            category:  Category id to filter by.
            sort_by:   Sort field — "name", "price", "created_at", or "stock".
            order:     Sort direction — "asc" or "desc".
            min_price: Minimum price (inclusive).
            max_price: Maximum price (inclusive).
            page:      Page number, 1-based.
            limit:     Results per page.

        Returns:
            {
                "products":   [ { id, name, price, stock, category_name,
                                  avg_rating, review_count, ... } ],
                "pagination": { "page", "limit", "total", "totalPages" }
            }
        """
        return self._get("/api/products", params={
            "search":   search,
            "category": category,
            "sortBy":   sort_by,
            "order":    order,
            "minPrice": min_price,
            "maxPrice": max_price,
            "page":     page,
            "limit":    limit,
        })

    def get_product(self, product_id: int) -> dict:
        """
        GET /api/products/:id — fetch a single product by id.

        Args:
            product_id: The product's integer id.

        Returns:
            { "product": { id, name, price, stock, category_name,
                           avg_rating, review_count, ... } }

        Raises:
            RuntimeError: 404 if the product does not exist.
        """
        return self._get(f"/api/products/{product_id}")

    def get_categories(self) -> dict:
        """
        GET /api/products/categories/all — list all categories.

        No auth required. Returns every category regardless of whether
        it has products.

        Returns:
            { "categories": [ { id, name, parent_id, product_count } ] }
        """
        return self._get("/api/products/categories/all")

    def get_products_by_category(
        self,
        category_id: int,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        GET /api/products/categories/:id/products — list products in a category.

        Args:
            category_id: The category's integer id.
            page:        Page number, 1-based.
            limit:       Results per page.

        Returns:
            {
                "products":   [ { id, name, price, stock, avg_rating,
                                  review_count, ... } ],
                "pagination": { "page", "limit", "total", "totalPages" }
            }

        Raises:
            RuntimeError: 404 if the category does not exist.
        """
        return self._get(
            f"/api/products/categories/{category_id}/products",
            params={"page": page, "limit": limit},
        )

    # ------------------------------------------------------------------
    # Reviews
    # ------------------------------------------------------------------

    def get_reviews(
        self,
        product_id: int,
        page: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> dict:
        """
        GET /api/reviews/products/:productId — fetch reviews for a product.

        No auth required.

        Args:
            product_id: The product's integer id.
            page:       Page number, 1-based.
            limit:      Results per page.

        Returns:
            {
                "reviews":    [ { id, rating, comment, user_name,
                                  created_at, ... } ],
                "avgRating":  float,
                "pagination": { "page", "limit", "total", "totalPages" }
            }
        """
        return self._get(
            f"/api/reviews/products/{product_id}",
            params={"page": page, "limit": limit},
        )

    def create_review(
        self,
        product_id: int,
        rating: int,
        comment: Optional[str] = None,
    ) -> dict:
        """
        POST /api/reviews/products/:productId — submit a review.

        Requires authentication. Each user may only review a product once —
        a second call for the same product_id raises RuntimeError(400).

        Args:
            product_id: The product's integer id.
            rating:     Integer from 1 to 5 (backend enforces CHECK constraint).
            comment:    Optional review text.

        Returns:
            { "message": "Review created successfully", "reviewId": int }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if the user already reviewed this product,
                          or if rating is outside 1–5.
            RuntimeError: 404 if the product does not exist.
        """
        body = {"rating": rating}
        if comment is not None:
            body["comment"] = comment

        return self._post(f"/api/reviews/products/{product_id}", json=body)

    def update_review(
        self,
        review_id: int,
        rating: Optional[int] = None,
        comment: Optional[str] = None,
    ) -> dict:
        """
        PUT /api/reviews/:id — update an existing review.

        Requires authentication. The user can only update their own reviews.
        At least one of rating or comment must be provided — the backend
        returns 400 if both are absent.

        Args:
            review_id: The review's integer id.
            rating:    New rating (1–5), or None to leave unchanged.
            comment:   New comment text, or None to leave unchanged.

        Returns:
            { "message": "Review updated successfully" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if neither rating nor comment is provided,
                          or if rating is outside 1–5.
            RuntimeError: 404 if the review does not exist or belongs to
                          a different user.
        """
        body = {}
        if rating is not None:
            body["rating"] = rating
        if comment is not None:
            body["comment"] = comment

        return self._put(f"/api/reviews/{review_id}", json=body)

    def delete_review(self, review_id: int) -> dict:
        """
        DELETE /api/reviews/:id — delete a review.

        Requires authentication. Users can only delete their own reviews.

        Args:
            review_id: The review's integer id.

        Returns:
            { "message": "Review deleted successfully" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 404 if the review does not exist or belongs to
                          a different user.
        """
        return self._delete(f"/api/reviews/{review_id}")