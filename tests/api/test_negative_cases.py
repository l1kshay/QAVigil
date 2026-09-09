"""API tests for error handling: bad input, missing resources, wrong verbs.

Every case is a record in test_data/edge_cases.yaml or users.yaml, so adding
coverage for a new failure mode is a data edit, not a code change.

These are the tests that would pass vacuously if the suite asserted on HTTP
status codes. Every request here comes back as HTTP 200; the real status is in
the body, and ``ApiResponse.status`` reads it from there. The first test below
guards that premise explicitly so the rest cannot quietly stop testing
anything.
"""

from __future__ import annotations

import pytest

from api_clients.schemas import MESSAGE_SCHEMA
from test_data import loader as test_data

EDGE_CASES = test_data.edge_cases()
MISSING_PARAMS = EDGE_CASES["missing_parameters"]
UNSUPPORTED_METHODS = EDGE_CASES["unsupported_methods"]
UNKNOWN_RESOURCES = EDGE_CASES["unknown_resources"]
API_LOGIN_PAYLOADS = test_data.users()["api_login_payloads"]


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
# required parameters omitted -> 400
# ----------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize(
    "case", MISSING_PARAMS, ids=test_data.case_ids(MISSING_PARAMS)
)
def test_omitting_a_required_parameter_is_a_bad_request(
    auth_client, product_client, case
) -> None:
    """Each endpoint rejects a request that leaves out a required field."""
    senders = {
        "searchProduct": lambda: product_client.search_raw({}),
        "getUserDetailByEmail": lambda: auth_client.get_user_raw({}),
    }
    send = senders.get(case["endpoint"])
    assert send is not None, f"no sender wired up for endpoint {case['endpoint']!r}"

    response = send()

    assert response.status == case["expected_status"], (
        f"case {case['id']}: omitting {case['input_field']!r} from "
        f"{case['endpoint']} returned {response.status}, expected "
        f"{case['expected_status']} ({case['expected_behavior'].strip()})"
    )


@pytest.mark.regression
@pytest.mark.parametrize(
    "case", API_LOGIN_PAYLOADS, ids=test_data.case_ids(API_LOGIN_PAYLOADS)
)
def test_verify_login_requires_both_credentials(auth_client, case) -> None:
    """verifyLogin rejects an incomplete credential pair."""
    response = auth_client.verify_login_raw(case["payload"])

    assert response.status == case["expected_status"], (
        f"case {case['id']}: {case['description']} - got {response.status} "
        f"({response.message!r})"
    )


@pytest.mark.regression
def test_error_responses_explain_themselves(product_client) -> None:
    """A rejection carries a message a human can act on, not just a code."""
    response = product_client.search_raw({})

    response.validate_schema(MESSAGE_SCHEMA)


# ----------------------------------------------------------------------
# resources that do not exist -> 404
# ----------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize(
    "case", UNKNOWN_RESOURCES, ids=test_data.case_ids(UNKNOWN_RESOURCES)
)
def test_unknown_resources_are_not_found(auth_client, case) -> None:
    """Operating on an account that does not exist is refused."""
    senders = {
        "getUserDetailByEmail": lambda: auth_client.get_user_by_email(
            case["input_value"]
        ),
        "deleteAccount": lambda: auth_client.delete_account(
            case["input_value"], "irrelevant-password"
        ),
    }
    send = senders.get(case["endpoint"])
    assert send is not None, f"no sender wired up for endpoint {case['endpoint']!r}"

    response = send()

    assert response.status == case["expected_status"], (
        f"case {case['id']}: {case['expected_behavior'].strip()} - got "
        f"{response.status}"
    )


@pytest.mark.regression
def test_a_not_found_lookup_returns_no_user_payload(auth_client) -> None:
    """A 404 carries no user object, rather than an empty shell of one."""
    response = auth_client.get_user_by_email("no-such-user@qavigil.invalid")

    response.assert_status(404)
    assert "user" not in response.body, (
        f"expected no user payload on a 404, got {response.body!r}"
    )


# ----------------------------------------------------------------------
# unsupported HTTP verbs -> 405
# ----------------------------------------------------------------------
@pytest.mark.regression
@pytest.mark.parametrize(
    "case", UNSUPPORTED_METHODS, ids=test_data.case_ids(UNSUPPORTED_METHODS)
)
def test_unsupported_http_methods_are_rejected(
    auth_client, product_client, case
) -> None:
    """Each endpoint refuses the verbs it does not implement."""
    senders = {
        "productsList": product_client.products_list_with_method,
        "brandsList": product_client.brands_list_with_method,
        "searchProduct": product_client.search_with_method,
        "verifyLogin": auth_client.verify_login_with_method,
    }
    send = senders.get(case["endpoint"])
    assert send is not None, f"no sender wired up for endpoint {case['endpoint']!r}"

    response = send(case["input_value"])

    assert response.status == case["expected_status"], (
        f"case {case['id']}: {case['input_value']} on {case['endpoint']} "
        f"returned {response.status}, expected {case['expected_status']}"
    )
    assert response.message == case["expected_behavior"]
