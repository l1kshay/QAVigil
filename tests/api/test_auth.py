"""API tests for authentication and the account lifecycle.

Every request goes through AuthClient - no test here builds a URL or touches
requests directly.

Remember that this API reports its real status in the response body, so the
assertions below read ``response.status``, which ApiResponse resolves from
``responseCode``. See api_clients/base_client.py for why.
"""

from __future__ import annotations

import pytest

from api_clients.auth_client import AuthClient
from api_clients.schemas import MESSAGE_SCHEMA, USER_DETAIL_SCHEMA
from test_data import loader as test_data

INVALID_CREDENTIALS = test_data.users()["api_invalid_credentials"]


@pytest.mark.smoke
def test_verify_login_accepts_valid_credentials(auth_client, registered_account) -> None:
    """A real account's credentials are recognised."""
    response = auth_client.verify_login(
        registered_account["email"], registered_account["password"]
    )

    response.assert_status(200)
    assert response.message == AuthClient.USER_EXISTS


@pytest.mark.regression
def test_verify_login_rejects_a_wrong_password(auth_client, registered_account) -> None:
    """A real account with the wrong password is refused."""
    response = auth_client.verify_login(registered_account["email"], "wrong-password")

    response.assert_status(404)
    assert response.message == AuthClient.USER_NOT_FOUND


@pytest.mark.regression
@pytest.mark.parametrize(
    "case", INVALID_CREDENTIALS, ids=test_data.case_ids(INVALID_CREDENTIALS)
)
def test_verify_login_rejects_unknown_accounts(auth_client, case) -> None:
    """A well-formed request for an account that does not exist is refused."""
    response = auth_client.verify_login(case["email"], case["password"])

    response.assert_status(case["expected_status"])
    assert response.message == case["expected_message"], f"case {case['id']}"


@pytest.mark.smoke
def test_create_account_registers_a_new_user(auth_client, account_payload) -> None:
    """Registration succeeds and reports 201.

    This test owns the account it creates, so it deletes it itself rather than
    leaning on a fixture - the deletion is part of what is being verified.
    """
    try:
        response = auth_client.create_account(account_payload)

        response.assert_status(201)
        assert response.message == AuthClient.USER_CREATED
    finally:
        auth_client.delete_account(
            account_payload["email"], account_payload["password"]
        )


@pytest.mark.regression
def test_created_account_can_immediately_log_in(auth_client, account_payload) -> None:
    """Registration produces credentials that actually work."""
    try:
        auth_client.create_account(account_payload).assert_status(201)

        login = auth_client.verify_login(
            account_payload["email"], account_payload["password"]
        )

        login.assert_status(200)
    finally:
        auth_client.delete_account(
            account_payload["email"], account_payload["password"]
        )


@pytest.mark.regression
def test_creating_a_duplicate_account_is_rejected(auth_client, registered_account) -> None:
    """The same address cannot be registered twice."""
    response = auth_client.create_account(registered_account)

    assert response.status != 201, (
        "the API accepted a duplicate registration; "
        f"responseCode={response.status}, message={response.message!r}"
    )


@pytest.mark.regression
def test_update_account_changes_stored_details(auth_client, registered_account) -> None:
    """An update is persisted and visible on the next read."""
    updated = dict(registered_account, firstname="Renamed")

    auth_client.update_account(updated).assert_status(200)

    user = auth_client.get_user_by_email(registered_account["email"])
    assert user.body["user"]["first_name"] == "Renamed"


@pytest.mark.smoke
def test_get_user_by_email_returns_the_account(auth_client, registered_account) -> None:
    """A registered address resolves to its account details."""
    response = auth_client.get_user_by_email(registered_account["email"])

    response.assert_status(200)
    assert response.body["user"]["email"] == registered_account["email"]


@pytest.mark.regression
def test_user_details_match_the_documented_schema(auth_client, registered_account) -> None:
    """The user payload honours its contract, field types included."""
    response = auth_client.get_user_by_email(registered_account["email"])

    response.validate_schema(USER_DETAIL_SCHEMA)


@pytest.mark.regression
def test_delete_account_removes_the_user(auth_client, account_payload) -> None:
    """A deleted account is genuinely gone, not merely reported as deleted.

    Asserting the 200 alone would pass even if the row survived, so the real
    assertion is the 404 on the follow-up lookup.
    """
    auth_client.create_account(account_payload).assert_status(201)

    auth_client.delete_account(
        account_payload["email"], account_payload["password"]
    ).assert_status(200)

    lookup = auth_client.get_user_by_email(account_payload["email"])
    assert lookup.status == 404, (
        "the account still resolves after deletion; "
        f"responseCode={lookup.status}"
    )


@pytest.mark.regression
def test_login_responses_carry_a_message(auth_client, registered_account) -> None:
    """Auth responses always include a usable status and message."""
    response = auth_client.verify_login(
        registered_account["email"], registered_account["password"]
    )

    response.validate_schema(MESSAGE_SCHEMA)
