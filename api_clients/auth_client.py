"""Client for the account and authentication endpoints.

Covers verifyLogin, createAccount, updateAccount, deleteAccount and
getUserDetailByEmail. Tests never build these requests themselves.

Two shapes of method are offered on purpose. ``verify_login(email, password)``
sends a well-formed request, which is what a positive test wants. The ``_raw``
variants take an arbitrary payload so a negative test can omit a required
field or send garbage - without that, testing "what happens when email is
missing" would force a test to reach past this layer and call requests
directly, which the project's rules forbid.
"""

from __future__ import annotations

from typing import Any

from api_clients.base_client import ApiResponse, BaseClient


class AuthClient(BaseClient):
    """Account lifecycle and login verification."""

    # Messages the API returns, kept here so tests assert against one source.
    USER_EXISTS = "User exists!"
    USER_NOT_FOUND = "User not found!"
    USER_CREATED = "User created!"
    USER_UPDATED = "User updated!"
    ACCOUNT_DELETED = "Account deleted!"
    METHOD_NOT_SUPPORTED = "This request method is not supported."

    # ------------------------------------------------------------------
    # login
    # ------------------------------------------------------------------
    def verify_login(self, email: str, password: str) -> ApiResponse:
        """Check a credential pair. 200 when it is valid, 404 when it is not."""
        return self.post("verifyLogin", data={"email": email, "password": password})

    def verify_login_raw(self, payload: dict[str, Any]) -> ApiResponse:
        """Send an arbitrary verifyLogin payload, for negative cases."""
        return self.post("verifyLogin", data=payload)

    def verify_login_with_method(self, method: str) -> ApiResponse:
        """Call verifyLogin with the wrong HTTP verb, for method-guard tests."""
        return self.request(method, "verifyLogin")

    # ------------------------------------------------------------------
    # account lifecycle
    # ------------------------------------------------------------------
    def create_account(self, account: dict[str, Any]) -> ApiResponse:
        """Register an account. 201 on success."""
        return self.post("createAccount", data=account)

    def update_account(self, account: dict[str, Any]) -> ApiResponse:
        """Update an existing account. 200 on success."""
        return self.put("updateAccount", data=account)

    def delete_account(self, email: str, password: str) -> ApiResponse:
        """Remove an account. 200 on success."""
        return self.delete("deleteAccount", data={"email": email, "password": password})

    # ------------------------------------------------------------------
    # lookup
    # ------------------------------------------------------------------
    def get_user_by_email(self, email: str) -> ApiResponse:
        """Fetch a user's details. 200 when found, 404 when not."""
        return self.get("getUserDetailByEmail", params={"email": email})

    def get_user_raw(self, params: dict[str, Any]) -> ApiResponse:
        """Send an arbitrary getUserDetailByEmail query, for negative cases."""
        return self.get("getUserDetailByEmail", params=params)
