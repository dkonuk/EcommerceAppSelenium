"""
HTTP client for the /api/users endpoint group.

All user endpoints require authentication — always initialise this
client with a token.

Endpoints covered:
    GET /api/users/profile          → get_profile()
    PUT /api/users/profile          → update_profile()
    PUT /api/users/password         → change_password()

Backend behaviours to understand before writing tests:

    update_profile() is partial — both fields are optional.
        Sending only "name" updates only the name. Sending only "email"
        updates only the email. Sending neither returns 400 "No updates
        provided". There is no way to clear a field by sending an empty
        string — the backend ignores falsy values entirely (if (name) {...}).

    Email uniqueness is enforced across all users.
        If you try to update a user's email to one that another user
        already owns, the backend returns 400 "Email already in use".
        This is a useful negative test case — use SeedData.user_email(2)
        as the conflicting email when the test user was registered
        independently.

    change_password() requires the current password to be correct.
        The backend bcrypt-compares the provided currentPassword against
        the stored hash. A wrong current password returns 401, not 400.
        This is a deliberate security design — 401 signals an auth
        failure, not a validation failure.

    get_profile() returns the user object attached to the JWT.
        The backend returns req.user directly, which is the decoded JWT
        payload joined against the users table. Fields returned:
        id, email, name, role. Password hash is never included.
"""

import logging
from typing import Optional

from api.base_client import BaseAPIClient

logger = logging.getLogger(__name__)


class UsersClient(BaseAPIClient):
    """
    Client for /api/users.

    Requires a token — all user routes enforce authentication.

    Example:
        client = UsersClient(api_url=test_config.api_url, token=user["token"])

        profile = client.get_profile()
        assert profile["user"]["email"] == user["email"]

        client.update_profile(name="New Name")
        client.change_password(
            current_password=user["password"],
            new_password="NewPass_x9!"
        )
    """

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_profile(self) -> dict:
        """
        GET /api/users/profile — fetch the authenticated user's profile.

        Returns the user object from the JWT payload — no additional
        database query is made by the backend beyond what authenticate()
        middleware already performed.

        Returns:
            {
                "user": {
                    "id":    int,
                    "email": str,
                    "name":  str,
                    "role":  "user" | "admin"
                }
            }

        Raises:
            RuntimeError: 401 if not authenticated.
        """
        return self._get("/api/users/profile")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_profile(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> dict:
        """
        PUT /api/users/profile — update name, email, or both.

        Both fields are optional — send only the ones you want to change.
        Sending neither raises RuntimeError(400).

        Args:
            name:  New display name. None means leave unchanged.
            email: New email address. None means leave unchanged.
                   Must not be in use by another account.

        Returns:
            {
                "message": "Profile updated successfully",
                "user": {
                    "id":    int,
                    "email": str,   # updated value
                    "name":  str,   # updated value
                    "role":  str
                }
            }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 400 if neither name nor email is provided.
            RuntimeError: 400 if the new email is already taken by
                          another user.
        """
        body = {}
        if name is not None:
            body["name"] = name
        if email is not None:
            body["email"] = email

        logger.debug(f"update_profile: fields={list(body.keys())}")
        return self._put("/api/users/profile", json=body)

    def change_password(
        self,
        current_password: str,
        new_password: str,
    ) -> dict:
        """
        PUT /api/users/password — change the account password.

        The backend verifies current_password against the stored bcrypt
        hash before applying the change. A wrong current password returns
        401, not 400 — see module docstring for the reasoning.

        After a successful call, the old token remains valid until it
        expires (JWT expiry is set on the backend). The user must log in
        again with the new password to get a fresh token.

        Args:
            current_password: The user's existing password. Must match
                              the stored hash exactly.
            new_password:     The replacement password. Must be at least
                              6 characters (backend enforces this).

        Returns:
            { "message": "Password updated successfully" }

        Raises:
            RuntimeError: 401 if not authenticated.
            RuntimeError: 401 if current_password is incorrect.
            RuntimeError: 400 if current_password or new_password is
                          missing, or if new_password is under 6 chars.
        """
        logger.debug("change_password: sending password change request")
        return self._put("/api/users/password", json={
            "currentPassword": current_password,
            "newPassword":     new_password,
        })