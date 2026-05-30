"""
API tests for /api/users.

Test coverage:

    TestGetProfile
        - Returns the authenticated user's profile with required fields
        - Returned email matches the registered email
        - Returned role is 'customer' for a dynamically registered user
        - Unauthenticated request returns 401

    TestUpdateProfile
        - Updating name only changes name, leaves email unchanged
        - Updating email only changes email, leaves name unchanged
        - Updating both name and email changes both
        - Updated values are reflected in subsequent GET /profile
        - Duplicate email (taken by another user) returns 400
        - Sending neither name nor email returns 400
        - Empty string name is ignored (backend uses if(name) check)
        - Unauthenticated request returns 401

    TestChangePassword
        - Valid current password + new password returns success message
        - New password can be used to log in immediately
        - Old password no longer works after change
        - Wrong current password returns 401
        - New password shorter than 6 characters returns 400
        - Missing currentPassword returns 400
        - Missing newPassword returns 400
        - Unauthenticated request returns 401

Fixture strategy:
    isolated_user — every test gets a function-scoped fresh user.
                    Profile and password tests mutate user-owned state,
                    so test isolation requires separate accounts.
                    No sterile_database needed — user data is self-contained.

Design note on empty string name test:
    The backend checks `if (name)` which treats an empty string as falsy.
    Sending name="" produces no update — the field is silently ignored.
    This documents intentional backend behaviour rather than treating it
    as a bug. If a future version rejects empty name with 400, update this
    test and the docstring in UsersClient.update_profile().
"""

import pytest

from api.auth_client import AuthAPIClient
from api.users_client import UsersClient
from helpers.factories import UserFactory, SeedData


# ---------------------------------------------------------------------------
# Module-level helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_client(test_config):
    """Shared AuthAPIClient for login calls within this module."""
    return AuthAPIClient(api_url=test_config.api_url)


def _make_users_client(test_config, user: dict) -> UsersClient:
    """Build an authenticated UsersClient for a user."""
    return UsersClient(api_url=test_config.api_url, token=user["token"])


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
        "name":     user_data["name"],
        "password": user_data["password"],
    }


# ---------------------------------------------------------------------------
# TestGetProfile
# ---------------------------------------------------------------------------

class TestGetProfile:
    """Tests for GET /api/users/profile"""

    def test_get_profile_returns_required_fields(
        self, test_config, isolated_user
    ):
        """Profile response contains id, email, name, and role."""
        client = _make_users_client(test_config, isolated_user)
        result = client.get_profile()

        assert "user" in result
        for field in ("id", "email", "name", "role"):
            assert field in result["user"], (
                f"Profile response missing field '{field}'"
            )

    def test_get_profile_returns_correct_email(
        self, test_config, isolated_user
    ):
        """Returned email matches the email used during registration."""
        client = _make_users_client(test_config, isolated_user)
        result = client.get_profile()

        assert result["user"]["email"] == isolated_user["email"].lower()

    def test_get_profile_returns_customer_role(
        self, test_config, isolated_user
    ):
        """
        Dynamically registered users always get role='customer'.
        Admin role can only be assigned directly in the database.
        """
        client = _make_users_client(test_config, isolated_user)
        result = client.get_profile()

        assert result["user"]["role"] == "customer", (
            f"Expected role 'customer', got '{result['user']['role']}'"
        )

    def test_get_profile_unauthenticated_returns_401(self, test_config):
        """GET /api/users/profile without a token returns 401."""
        client = UsersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            client.get_profile()

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestUpdateProfile
# ---------------------------------------------------------------------------

class TestUpdateProfile:
    """Tests for PUT /api/users/profile"""

    def test_update_name_only_changes_name(
        self, test_config, isolated_user
    ):
        """
        Sending only name updates the name field and leaves
        email unchanged.
        """
        client   = _make_users_client(test_config, isolated_user)
        new_name = "Updated Name"

        result = client.update_profile(name=new_name)

        assert result["user"]["name"]  == new_name
        assert result["user"]["email"] == isolated_user["email"].lower()

    def test_update_email_only_changes_email(
        self, test_config, isolated_user
    ):
        """
        Sending only email updates the email field and leaves
        name unchanged.
        """
        client    = _make_users_client(test_config, isolated_user)
        new_email = UserFactory.create()["email"]

        result = client.update_profile(email=new_email)

        assert result["user"]["email"] == new_email.lower()
        assert result["user"]["name"]  == isolated_user["name"]

    def test_update_both_name_and_email(
        self, test_config, isolated_user
    ):
        """Sending both name and email updates both fields."""
        client    = _make_users_client(test_config, isolated_user)
        new_name  = "New Full Name"
        new_email = UserFactory.create()["email"]

        result = client.update_profile(name=new_name, email=new_email)

        assert result["user"]["name"]  == new_name
        assert result["user"]["email"] == new_email.lower()

    def test_update_reflected_in_get_profile(
        self, test_config, isolated_user
    ):
        """
        Updated values appear in a subsequent GET /api/users/profile.

        Verifies that the update actually persists in the database, not
        just in the PUT response body.
        """
        client   = _make_users_client(test_config, isolated_user)
        new_name = "Persisted Name"

        client.update_profile(name=new_name)

        profile = client.get_profile()
        assert profile["user"]["name"] == new_name, (
            f"Name change not reflected in subsequent GET: "
            f"expected '{new_name}', got '{profile['user']['name']}'"
        )

    def test_update_duplicate_email_returns_400(
        self, test_config, isolated_user
    ):
        """
        Updating to an email already taken by another user returns 400.

        User 2 is a seeded user — their email is known and stable.
        The isolated_user is a dynamically registered account so there
        is no risk of the two being the same user.
        """
        client        = _make_users_client(test_config, isolated_user)
        taken_email   = SeedData.user_email(2)

        with pytest.raises(RuntimeError) as exc_info:
            client.update_profile(email=taken_email)

        assert "400" in str(exc_info.value)

    def test_update_with_no_fields_returns_400(
        self, test_config, isolated_user
    ):
        """
        Calling update_profile() with neither name nor email sends an
        empty body, which the backend rejects with 400 'No updates provided'.
        """
        client = _make_users_client(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            client.update_profile()

        assert "400" in str(exc_info.value)

    def test_empty_string_name_is_ignored(
        self, test_config, isolated_user
    ):
        """
        The backend checks `if (name)` — an empty string is falsy in
        JavaScript and is silently ignored. Sending name="" produces
        no update and the name stays unchanged.

        This documents intentional backend behaviour. If the backend is
        updated to reject empty name with 400, change this test to assert
        on the 400 instead.
        """
        client       = _make_users_client(test_config, isolated_user)
        original_name = isolated_user["name"]

        # Sending name="" alongside a valid email triggers an update
        # (email changes), but name stays unchanged because "" is falsy
        new_email = UserFactory.create()["email"]
        result    = client.update_profile(name="", email=new_email)

        assert result["user"]["name"] == original_name, (
            f"Empty string name should be ignored. "
            f"Expected '{original_name}', got '{result['user']['name']}'"
        )

    def test_update_profile_unauthenticated_returns_401(self, test_config):
        """PUT /api/users/profile without a token returns 401."""
        client = UsersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            client.update_profile(name="Test")

        assert "401" in str(exc_info.value)


# ---------------------------------------------------------------------------
# TestChangePassword
# ---------------------------------------------------------------------------

class TestChangePassword:
    """Tests for PUT /api/users/password"""

    def test_valid_password_change_returns_success(
        self, test_config, isolated_user
    ):
        """
        Providing the correct current password and a valid new password
        returns a success message.
        """
        client      = _make_users_client(test_config, isolated_user)
        new_password = f"NewPass_{UserFactory.create()['password'][:4]}!7"

        result = client.change_password(
            current_password=isolated_user["password"],
            new_password=new_password,
        )

        assert "message" in result

    def test_new_password_works_for_login(
        self, test_config, isolated_user, auth_client
    ):
        """
        After a successful password change, the new password can be used
        to obtain a valid JWT token.

        This is the most important test in this class — it verifies the
        full lifecycle: change password → log in with new password → get token.
        """
        client       = _make_users_client(test_config, isolated_user)
        new_password = f"NewPass_{UserFactory.create()['password'][:4]}!7"

        client.change_password(
            current_password=isolated_user["password"],
            new_password=new_password,
        )

        # New password should produce a valid token
        new_token = auth_client.get_jwt_token(
            email=isolated_user["email"],
            password=new_password,
        )
        assert isinstance(new_token, str)
        assert len(new_token) > 0

    def test_old_password_fails_after_change(
        self, test_config, isolated_user, auth_client
    ):
        """
        After a password change, the old password no longer authenticates.
        This verifies the hash is actually replaced in the database.
        """
        client       = _make_users_client(test_config, isolated_user)
        old_password = isolated_user["password"]
        new_password = f"NewPass_{UserFactory.create()['password'][:4]}!7"

        client.change_password(
            current_password=old_password,
            new_password=new_password,
        )

        with pytest.raises(RuntimeError) as exc_info:
            auth_client.get_jwt_token(
                email=isolated_user["email"],
                password=old_password,
            )

        assert "401" in str(exc_info.value)

    def test_wrong_current_password_returns_401(
        self, test_config, isolated_user
    ):
        """
        An incorrect current password returns 401.
        The backend bcrypt-compares before applying the change.
        Note: this returns 401, not 400 — wrong password is an auth
        failure, not a validation failure.
        """
        client = _make_users_client(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            client.change_password(
                current_password="definitely_wrong_password",
                new_password="ValidNewPass1!",
            )

        assert "401" in str(exc_info.value)

    def test_short_new_password_returns_400(
        self, test_config, isolated_user
    ):
        """
        A new password shorter than 6 characters is rejected with 400.
        The backend validates length before calling bcrypt.
        """
        client = _make_users_client(test_config, isolated_user)

        with pytest.raises(RuntimeError) as exc_info:
            client.change_password(
                current_password=isolated_user["password"],
                new_password="abc",
            )

        assert "400" in str(exc_info.value)

    def test_missing_current_password_returns_400(
        self, test_config, isolated_user
    ):
        """Omitting currentPassword returns 400."""
        import requests as req

        response = req.put(
            f"{test_config.api_url}/api/users/password",
            headers={"Authorization": f"Bearer {isolated_user['token']}"},
            json={"newPassword": "ValidNewPass1!"},
        )
        assert response.status_code == 400

    def test_missing_new_password_returns_400(
        self, test_config, isolated_user
    ):
        """Omitting newPassword returns 400."""
        import requests as req

        response = req.put(
            f"{test_config.api_url}/api/users/password",
            headers={"Authorization": f"Bearer {isolated_user['token']}"},
            json={"currentPassword": isolated_user["password"]},
        )
        assert response.status_code == 400

    def test_change_password_unauthenticated_returns_401(self, test_config):
        """PUT /api/users/password without a token returns 401."""
        client = UsersClient(api_url=test_config.api_url)

        with pytest.raises(RuntimeError) as exc_info:
            client.change_password(
                current_password="anything",
                new_password="ValidNewPass1!",
            )

        assert "401" in str(exc_info.value)