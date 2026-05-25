"""
API tests for /api/auth.

Test coverage:

    TestRegistration
        - Valid registration returns 201 with token and user object
        - Returned user object has all required fields
        - Returned role is 'customer' (not 'admin')
        - Token is a non-empty string
        - Duplicate email returns 400
        - Invalid email format returns 400
        - Password shorter than 6 characters returns 400
        - Empty name returns 400
        - Missing email field returns 400
        - Missing password field returns 400
        - Missing name field returns 400

    TestLogin
        - Valid credentials return 200 with token and user object
        - Returned user object has all required fields
        - Wrong password returns 401
        - Non-existent email returns 401
        - Invalid email format returns 400
        - Missing password returns 400
        - Token obtained via login can authenticate a protected endpoint

    TestGetCurrentUser
        - Valid token returns the correct user object
        - Request without token returns 401
        - Request with a malformed token returns 401

    TestLogout
        - Logout endpoint returns 200 with a message
        - Logout succeeds without a token (endpoint is public)

Fixture strategy:
    sterile_database  — session-scoped, ensures seeded users exist for
                        login tests that target SeedData users.

    registered_user   — session-scoped dynamic user. Used for /me tests
                        where we need a known user whose token we hold.

    No isolated_user needed here — registration tests create their own
    users inline so each test controls its own email and can verify the
    exact payload it sent.

Design note — why tests create users inline instead of using a fixture:
    Registration tests need to control the exact payload — testing a
    short password means sending a specific password, testing a bad email
    means sending a specific email. A fixture cannot parameterise these
    variations. Inline creation keeps each test self-contained and its
    intent readable without jumping to fixture definitions.
"""

import pytest

from api.auth_client import AuthAPIClient
from helpers.factories import SeedData, UserFactory


# ---------------------------------------------------------------------------
# Module-level helper fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_client(test_config, sterile_database):
    """
    AuthAPIClient shared across the module.

    sterile_database is a dependency because login tests target seeded
    users (SeedData.user_email(1), SeedData.ADMIN_EMAIL). Without a
    seeded database those users don't exist and login tests would 401.
    """
    return AuthAPIClient(api_url=test_config.api_url)


# ---------------------------------------------------------------------------
# TestRegistration
# ---------------------------------------------------------------------------

class TestRegistration:
    """Tests for POST /api/auth/register"""

    def test_valid_registration_returns_201(self, auth_client):
        """Happy path — valid payload returns 201 with token and user."""
        user   = UserFactory.create()
        result = auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        assert "token" in result
        assert "user"  in result

    def test_registration_response_has_required_user_fields(self, auth_client):
        """Returned user object contains id, email, name, and role."""
        user   = UserFactory.create()
        result = auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        for field in ("id", "email", "name", "role"):
            assert field in result["user"], (
                f"Registration response missing user field '{field}'"
            )

    def test_registration_returns_customer_role(self, auth_client):
        """
        Newly registered users always get role='customer'.
        Admin role can only be assigned directly in the database.
        """
        user   = UserFactory.create()
        result = auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        assert result["user"]["role"] == "customer", (
            f"Expected role 'customer', got '{result['user']['role']}'"
        )

    def test_registration_returns_non_empty_token(self, auth_client):
        """The token in the registration response is a non-empty string."""
        user   = UserFactory.create()
        result = auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        assert isinstance(result["token"], str)
        assert len(result["token"]) > 0

    def test_registration_returns_correct_email(self, auth_client):
        """The user object reflects the email that was sent in the request."""
        user   = UserFactory.create()
        result = auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        # Backend normalises email via express-validator normalizeEmail()
        # which lowercases the local part — compare in lowercase
        assert result["user"]["email"] == user["email"].lower()

    def test_duplicate_email_returns_400(self, auth_client):
        """
        Registering with an already-taken email returns 400.
        The backend checks uniqueness before inserting.
        """
        user = UserFactory.create()
        auth_client.register_user(
            email=user["email"],
            name=user["name"],
            password=user["password"],
        )

        with pytest.raises(RuntimeError) as exc_info:
            auth_client.register_user(
                email=user["email"],
                name="Different Name",
                password=user["password"],
            )

        assert "400" in str(exc_info.value)

    def test_invalid_email_format_returns_400(self, auth_client):
        """
        An email address that fails format validation returns 400.
        express-validator's isEmail() rejects strings without an @ sign.
        """
        with pytest.raises(RuntimeError) as exc_info:
            auth_client.register_user(
                email="not-an-email",
                name="Test User",
                password="ValidPass1!",
            )

        assert "400" in str(exc_info.value)

    def test_short_password_returns_400(self, auth_client):
        """
        A password shorter than 6 characters fails the isLength({min:6})
        validator and returns 400.
        """
        user = UserFactory.create()

        with pytest.raises(RuntimeError) as exc_info:
            auth_client.register_user(
                email=user["email"],
                name=user["name"],
                password="abc",           # 3 chars — below minimum
            )

        assert "400" in str(exc_info.value)

    def test_empty_name_returns_400(self, auth_client):
        """
        A name that is empty after trimming fails the isLength({min:1})
        validator and returns 400.
        """
        user = UserFactory.create()

        with pytest.raises(RuntimeError) as exc_info:
            auth_client.register_user(
                email=user["email"],
                name="   ",              # whitespace only — trims to empty
                password=user["password"],
            )

        assert "400" in str(exc_info.value)

    def test_missing_email_returns_400(self, auth_client):
        """
        Omitting the email field entirely fails validation and returns 400.

        Calls the endpoint directly via the session to send a partial payload
        that UserFactory.create() cannot produce — missing a required field.
        """
        import requests
        response = requests.post(
            f"{auth_client.api_url}/api/auth/register",
            json={"name": "Test User", "password": "ValidPass1!"},
        )
        assert response.status_code == 400

    def test_missing_password_returns_400(self, auth_client):
        """Omitting password entirely returns 400."""
        import requests
        response = requests.post(
            f"{auth_client.api_url}/api/auth/register",
            json={"email": "test@test.com", "name": "Test User"},
        )
        assert response.status_code == 400

    def test_missing_name_returns_400(self, auth_client):
        """Omitting name entirely returns 400."""
        import requests
        response = requests.post(
            f"{auth_client.api_url}/api/auth/register",
            json={"email": "test@test.com", "password": "ValidPass1!"},
        )
        assert response.status_code == 400


# ---------------------------------------------------------------------------
# TestLogin
# ---------------------------------------------------------------------------

class TestLogin:
    """Tests for POST /api/auth/login"""

    def test_valid_credentials_return_token_and_user(self, auth_client):
        """
        Happy path — seeded user credentials return 200 with token and user.
        Uses a seeded user so no registration step is needed.
        """
        token = auth_client.get_jwt_token(
            email=SeedData.user_email(1),
            password=SeedData.USER_PASSWORD,
        )

        assert isinstance(token, str)
        assert len(token) > 0

    def test_admin_login_returns_admin_role(self, test_config, auth_client):
        """
        Logging in as the seeded admin returns role='admin'.

        Uses a fresh AuthAPIClient to access the full response rather
        than just the token returned by get_jwt_token().
        """
        import requests
        response = requests.post(
            f"{test_config.api_url}/api/auth/login",
            json={
                "email":    SeedData.ADMIN_EMAIL,
                "password": SeedData.ADMIN_PASSWORD,
            },
        )
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "admin"

    def test_login_response_has_required_user_fields(self, test_config):
        """Login response user object contains id, email, name, and role."""
        import requests
        response = requests.post(
            f"{test_config.api_url}/api/auth/login",
            json={
                "email":    SeedData.user_email(1),
                "password": SeedData.USER_PASSWORD,
            },
        )
        user = response.json()["user"]

        for field in ("id", "email", "name", "role"):
            assert field in user, f"Login response missing user field '{field}'"

    def test_wrong_password_returns_401(self, auth_client):
        """
        A valid email with the wrong password returns 401 'Invalid credentials'.
        The backend does not distinguish between wrong email and wrong password
        to avoid user enumeration.
        """
        with pytest.raises(RuntimeError) as exc_info:
            auth_client.get_jwt_token(
                email=SeedData.user_email(1),
                password="definitely_wrong_password",
            )

        assert "401" in str(exc_info.value)

    def test_nonexistent_email_returns_401(self, auth_client):
        """
        An email address not in the database returns 401.
        Same error as wrong password — prevents user enumeration.
        """
        with pytest.raises(RuntimeError) as exc_info:
            auth_client.get_jwt_token(
                email="ghost_user_does_not_exist@testmail.com",
                password="AnyPassword1!",
            )

        assert "401" in str(exc_info.value)

    def test_invalid_email_format_returns_400(self, auth_client):
        """
        An email that fails format validation returns 400 before the
        database is even queried.
        """
        with pytest.raises(RuntimeError) as exc_info:
            auth_client.get_jwt_token(
                email="not-an-email",
                password="AnyPassword1!",
            )

        assert "400" in str(exc_info.value)

    def test_missing_password_returns_400(self, auth_client):
        """Omitting password entirely returns 400."""
        import requests
        response = requests.post(
            f"{auth_client.api_url}/api/auth/login",
            json={"email": SeedData.user_email(1)},
        )
        assert response.status_code == 400

    def test_token_authenticates_protected_endpoint(self, test_config):
        """
        A token obtained via login successfully authenticates a request
        to a protected endpoint (/api/auth/me).

        This is an integration test — it verifies the full token lifecycle:
        login → receive token → use token → get authenticated response.
        """
        import requests

        # Step 1: log in and obtain a token
        login_response = requests.post(
            f"{test_config.api_url}/api/auth/login",
            json={
                "email":    SeedData.user_email(1),
                "password": SeedData.USER_PASSWORD,
            },
        )
        assert login_response.status_code == 200
        token = login_response.json()["token"]

        # Step 2: use the token on a protected endpoint
        me_response = requests.get(
            f"{test_config.api_url}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me_response.status_code == 200
        assert me_response.json()["user"]["email"] == SeedData.user_email(1)


# ---------------------------------------------------------------------------
# TestGetCurrentUser
# ---------------------------------------------------------------------------

class TestGetCurrentUser:
    """Tests for GET /api/auth/me"""

    def test_valid_token_returns_correct_user(self, test_config, registered_user):
        """
        /api/auth/me with a valid token returns the authenticated user's data.

        Uses registered_user (session-scoped dynamic user) so the test
        knows the exact email to assert against.
        """
        import requests
        response = requests.get(
            f"{test_config.api_url}/api/auth/me",
            headers={"Authorization": f"Bearer {registered_user['token']}"},
        )

        assert response.status_code == 200
        assert response.json()["user"]["email"] == registered_user["email"]

    def test_me_returns_required_user_fields(self, test_config, registered_user):
        """/api/auth/me response user object contains id, email, name, role."""
        import requests
        response = requests.get(
            f"{test_config.api_url}/api/auth/me",
            headers={"Authorization": f"Bearer {registered_user['token']}"},
        )
        user = response.json()["user"]

        for field in ("id", "email", "name", "role"):
            assert field in user, f"/me response missing user field '{field}'"

    def test_no_token_returns_401(self, test_config):
        """/api/auth/me without an Authorization header returns 401."""
        import requests
        response = requests.get(f"{test_config.api_url}/api/auth/me")

        assert response.status_code == 401

    def test_malformed_token_returns_401(self, test_config):
        """
        /api/auth/me with a syntactically invalid token returns 401.
        The JWT middleware rejects anything it cannot verify.
        """
        import requests
        response = requests.get(
            f"{test_config.api_url}/api/auth/me",
            headers={"Authorization": "Bearer this.is.not.a.valid.jwt"},
        )

        assert response.status_code == 401

    def test_token_without_bearer_prefix_returns_401(self, test_config, registered_user):
        """
        Sending the token without the 'Bearer ' prefix returns 401.
        The middleware expects the exact format: 'Bearer <token>'.
        """
        import requests
        response = requests.get(
            f"{test_config.api_url}/api/auth/me",
            headers={"Authorization": registered_user["token"]},  # no 'Bearer '
        )

        assert response.status_code == 401


# ---------------------------------------------------------------------------
# TestLogout
# ---------------------------------------------------------------------------

class TestLogout:
    """
    Tests for POST /api/auth/logout.

    The logout endpoint is intentionally thin — JWT is stateless, so the
    server cannot invalidate a token. Logout is client-side (delete the
    token from localStorage). The endpoint exists as an acknowledgement
    and for future server-side session tracking if needed.
    """

    def test_logout_returns_success_message(self, test_config):
        """POST /api/auth/logout returns 200 with a message."""
        import requests
        response = requests.post(f"{test_config.api_url}/api/auth/logout")

        assert response.status_code == 200
        assert "message" in response.json()

    def test_logout_succeeds_without_token(self, test_config):
        """
        Logout does not require authentication — the endpoint has no
        authenticate middleware. Calling it without a token still returns 200.

        This is correct behaviour: the server has nothing to invalidate,
        so it should not reject an unauthenticated logout request.
        """
        import requests
        response = requests.post(f"{test_config.api_url}/api/auth/logout")

        assert response.status_code == 200