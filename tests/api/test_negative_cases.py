"""API tests for error handling: bad input, missing resources, wrong verbs.

These are the tests that would pass vacuously if the suite asserted on HTTP
status codes. Every request here comes back as HTTP 200; the real status is
in the body, and ``ApiResponse.status`` reads it from there. The first test
below guards that assumption explicitly so the rest cannot quietly stop
testing anything.
"""

from __future__ import annotations

import pytest

from api_clients.auth_client import AuthClient
from api_clients.product_client import ProductClient
from api_clients.schemas import MESSAGE_SCHEMA


@pytest.mark.smoke
def test_errors_are_reported_in_the_body_not_the_http_status(product_client) -> None:
    """The premise every other negative test depends on.

    If this site ever starts returning real HTTP status codes, this test fails
    first and tells us to revisit ApiResponse - rather than the whole negative
    suite silently passing against a changed contract.
    """
    response = product_client.search_raw({})

    assert response.http_status == 200, (
        "the API now returns real HTTP status codes; the responseCode-based "
        "design in api_clients/base_client.py needs revisiting "
        f"(got HTTP {response.http_status})"
    )
    assert response.status == 400


# ----------------------------------------------------------------------
# missing or malformed parameters -> 400
# ----------------------------------------------------------------------
@pytest.mark.regression
def test_search_without_a_term_is_a_bad_request(product_client) -> None:
    """searchProduct requires its search_product parameter."""
    response = product_client.search_raw({})

    response.assert_status(400)
    assert response.message == ProductClient.SEARCH_PARAM_MISSING


@pytest.mark.regression
@pytest.mark.parametrize(
    "payload, case",
    [
        ({"password": "some-password"}, "email missing"),
        ({"email": "someone@example.com"}, "password missing"),
        ({}, "both missing"),
    ],
    ids=["email-missing", "password-missing", "both-missing"],
)
def test_verify_login_requires_both_credentials(auth_client, payload, case) -> None:
    """verifyLogin rejects an incomplete credential pair."""
    response = auth_client.verify_login_raw(payload)

    assert response.status == 400, (
        f"expected 400 when {case}, got {response.status} "
        f"({response.message!r})"
    )


@pytest.mark.regression
def test_get_user_without_an_email_is_a_bad_request(auth_client) -> None:
    """getUserDetailByEmail requires its email parameter."""
    response = auth_client.get_user_raw({})

    response.assert_status(400)


@pytest.mark.regression
def test_error_responses_explain_themselves(product_client) -> None:
    """A rejection carries a message a human can act on, not just a code."""
    response = product_client.search_raw({})

    response.validate_schema(MESSAGE_SCHEMA)


# ----------------------------------------------------------------------
# unknown resources -> 404
# ----------------------------------------------------------------------
@pytest.mark.regression
def test_unknown_account_lookup_is_not_found(auth_client) -> None:
    """An address with no account behind it reports 404, not an empty user."""
    response = auth_client.get_user_by_email("no-such-user@qavigil.invalid")

    response.assert_status(404)
    assert "user" not in response.body, (
        f"expected no user payload on a 404, got {response.body!r}"
    )


@pytest.mark.regression
def test_deleting_an_unknown_account_is_not_found(auth_client) -> None:
    """Deleting an account that never existed is refused."""
    response = auth_client.delete_account(
        "no-such-user@qavigil.invalid", "irrelevant-password"
    )

    assert response.status == 404, (
        f"expected 404 deleting a non-existent account, got {response.status}"
    )


# ----------------------------------------------------------------------
# unsupported HTTP verbs -> 405
# ----------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_products_list_rejects_write_methods(product_client, method) -> None:
    """The catalogue is read-only; write verbs are refused."""
    response = product_client.products_list_with_method(method)

    assert response.status == 405, (
        f"{method} on productsList returned {response.status}, expected 405"
    )
    assert response.message == ProductClient.METHOD_NOT_SUPPORTED


@pytest.mark.regression
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_brands_list_rejects_write_methods(product_client, method) -> None:
    """The brands list is read-only; write verbs are refused."""
    response = product_client.brands_list_with_method(method)

    assert response.status == 405, (
        f"{method} on brandsList returned {response.status}, expected 405"
    )


@pytest.mark.regression
def test_search_rejects_get(product_client) -> None:
    """searchProduct is POST-only."""
    response = product_client.search_with_method("GET")

    response.assert_status(405)


@pytest.mark.regression
def test_verify_login_rejects_delete(auth_client) -> None:
    """verifyLogin does not accept DELETE."""
    response = auth_client.verify_login_with_method("DELETE")

    response.assert_status(405)
    assert response.message == AuthClient.METHOD_NOT_SUPPORTED
