"""
HTTP client for the /api/auth endpoints.

Responsibilities:
    - Know the shape of the auth API (endpoints, payloads, response fields)
    - Return data the caller asked for
    - Raise on non-2xx responses with a clear message

Non-responsibilities:
    - Deciding which user to authenticate as   (caller's job)
    - Storing or caching tokens                (fixture's job)
    - Knowing anything about seed data         (database_fixtures' job)
"""

import logging

import requests

logger = logging.getLogger(__name__)


class AuthAPIClient:
    """Client for the /api/auth endpoint group."""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def register_user(self, email: str, name: str, password: str) -> dict:
        """
        POST /api/auth/register — create a new user account.

        Args:
            email:    Unique email address for the new account.
            name:     Display name.
            password: Must be at least 6 characters (backend rule).

        Returns:
            dict with keys:
                token  (str)  — JWT for immediate use
                user   (dict) — {id, email, name, role}

        Raises:
            RuntimeError: If the server returns a non-201 status.
        """
        endpoint = f"{self.api_url}/api/auth/register"
        payload = {"email": email, "name": name, "password": password}

        logger.debug(f"Registering user: {email}")
        response = self.session.post(endpoint, json=payload)

        if response.status_code != 201:
            logger.error(
                f"Registration failed for {email} | "
                f"status={response.status_code} | "
                f"body={response.text}"
            )
            raise RuntimeError(
                f"POST /api/auth/register failed [{response.status_code}]: "
                f"{response.text}"
            )

        data = response.json()
        logger.debug(f"Registered user id={data['user']['id']} email={email}")
        return data

    def get_jwt_token(self, email: str, password: str) -> str:
        """
        POST /api/auth/login — authenticate and return a JWT.

        No default arguments: the caller decides which user to log in as.
        Credentials belong in TestConfig or a fixture, not in this client.

        Args:
            email:    Account email address.
            password: Account password.

        Returns:
            JWT token string.

        Raises:
            RuntimeError: If the server returns a non-200 status.
            ValueError:   If the response body contains no token field.
        """
        endpoint = f"{self.api_url}/api/auth/login"
        payload = {"email": email, "password": password}

        logger.debug(f"Authenticating: {email}")
        response = self.session.post(endpoint, json=payload)

        if response.status_code != 200:
            logger.error(
                f"Login failed for {email} | "
                f"status={response.status_code} | "
                f"body={response.text}"
            )
            raise RuntimeError(
                f"POST /api/auth/login failed [{response.status_code}]: "
                f"{response.text}"
            )

        data = response.json()
        token = data.get("token")

        if not token:
            raise ValueError(
                f"Login response for {email} contained no 'token' field. "
                f"Response: {data}"
            )

        logger.debug(f"Token obtained for {email}")
        return token