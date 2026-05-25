"""
Base HTTP client for the ecommerce API.

All endpoint-specific clients (ProductsClient, CartClient, etc.) inherit
from BaseAPIClient. This class owns everything that is the same across every
client:

    - Session creation and reuse
    - Bearer token attachment
    - URL construction
    - HTTP verb helpers (_get, _post, _put, _delete)
    - Consistent error raising on non-2xx responses

Keeping this logic here means:
    - Adding a new endpoint-specific client is ~10 lines of thin methods
    - Changing error message format happens in one place
    - Auth header handling is not copy-pasted across five files

Usage:
    class CartClient(BaseAPIClient):
        def get_cart(self):
            return self._get("/api/cart")
"""

import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class BaseAPIClient:
    """
    Shared HTTP session and request helpers for all API clients.

    Args:
        api_url: Base URL of the API, e.g. "http://localhost:3001".
                 Trailing slashes are stripped on init.
        token:   Optional Bearer JWT. When provided it is attached to
                 every request via the Authorization header. Pass None
                 for unauthenticated clients (public endpoints).

    Example — authenticated client:
        client = ProductsClient(api_url="http://localhost:3001", token=jwt)
        result = client.get_products(search="Laptop")

    Example — unauthenticated client (public endpoint):
        client = ProductsClient(api_url="http://localhost:3001")
        result = client.get_categories()
    """

    def __init__(self, api_url: str, token: Optional[str] = None):
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()

        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
            logger.debug(f"{self.__class__.__name__}: initialised with auth token")
        else:
            logger.debug(f"{self.__class__.__name__}: initialised without auth token")

    # ------------------------------------------------------------------
    # URL helper
    # ------------------------------------------------------------------

    def _url(self, path: str) -> str:
        """Build a full URL from a path fragment.

        Args:
            path: API path starting with /, e.g. "/api/products/1"

        Returns:
            Full URL, e.g. "http://localhost:3001/api/products/1"
        """
        return f"{self.api_url}{path}"

    # ------------------------------------------------------------------
    # HTTP verb helpers
    # ------------------------------------------------------------------

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        """
        Send a GET request and return the parsed JSON body.

        Args:
            path:   API path, e.g. "/api/products"
            params: Optional query parameters dict. None values are
                    stripped so callers can pass optional params directly:
                        self._get("/api/products", {"search": term, "page": None})
                    produces ?search=term with no page param.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            RuntimeError: If the server returns a non-2xx status.
        """
        clean_params = (
            {k: v for k, v in params.items() if v is not None}
            if params
            else None
        )
        url = self._url(path)
        logger.debug(f"GET {url} params={clean_params}")

        response = self.session.get(url, params=clean_params)
        return self._handle(response)

    def _post(self, path: str, json: Optional[dict] = None) -> dict:
        """
        Send a POST request with a JSON body and return the parsed response.

        Args:
            path: API path, e.g. "/api/cart/items"
            json: Request body as a dict. Pass None for requests with no body.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            RuntimeError: If the server returns a non-2xx status.
        """
        url = self._url(path)
        logger.debug(f"POST {url} body={json}")

        response = self.session.post(url, json=json)
        return self._handle(response)

    def _put(self, path: str, json: Optional[dict] = None) -> dict:
        """
        Send a PUT request with a JSON body and return the parsed response.

        Args:
            path: API path, e.g. "/api/cart/items/5"
            json: Request body as a dict.

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            RuntimeError: If the server returns a non-2xx status.
        """
        url = self._url(path)
        logger.debug(f"PUT {url} body={json}")

        response = self.session.put(url, json=json)
        return self._handle(response)

    def _delete(self, path: str) -> dict:
        """
        Send a DELETE request and return the parsed response.

        Args:
            path: API path, e.g. "/api/cart/items/5"

        Returns:
            Parsed JSON response body as a dict.

        Raises:
            RuntimeError: If the server returns a non-2xx status.
        """
        url = self._url(path)
        logger.debug(f"DELETE {url}")

        response = self.session.delete(url)
        return self._handle(response)

    # ------------------------------------------------------------------
    # Response handler
    # ------------------------------------------------------------------

    def _handle(self, response: requests.Response) -> dict:
        """
        Validate a response and return its parsed JSON body.

        On success (2xx): returns the parsed JSON dict.
        On failure (non-2xx): raises RuntimeError with the status code
        and response body so test failures point directly at the API
        contract that was violated.

        Args:
            response: The requests.Response object to validate.

        Returns:
            Parsed JSON body as a dict.

        Raises:
            RuntimeError: On non-2xx status codes.
        """
        if not response.ok:
            log = logger.error if response.status_code >= 500 else logger.debug
            log(
                f"{response.request.method} {response.url} "
                f"[{response.status_code}]: {response.text}"
            )
            raise RuntimeError(
                f"{response.request.method} {response.url} "
                f"failed [{response.status_code}]: {response.text}"
            )

        if not response.content:
            return {}

        return response.json()