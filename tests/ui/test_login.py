"""UI tests for the login flow.

Happy path first, then the failure modes. Each test asserts one thing, and
each gets its own freshly created account so nothing depends on run order or
on an account someone else may have changed.

All inputs come from test_data/users.yaml, except the valid credentials, which
are generated per test - see that file for why a working credential is never
committed.
"""

from __future__ import annotations

import pytest

from pages.login_page import LoginPage
from test_data import loader as test_data

USERS = test_data.users()
INVALID_LOGINS = USERS["invalid_logins"]
CLIENT_BLOCKED = USERS["client_validation_rejections"]
LOGIN_ERROR = USERS["login_error_message"]


@pytest.mark.smoke
def test_login_with_valid_credentials_signs_the_user_in(page, ephemeral_account) -> None:
    """A known-good account reaches a signed-in session."""
    login = LoginPage(page)
    login.open()

    login.login_as(ephemeral_account["email"], ephemeral_account["password"])

    login.wait_for_visible(login.header.LOGOUT)
    assert login.header.is_logged_in, "expected the header to show a signed-in session"


@pytest.mark.regression
def test_logged_in_header_shows_the_account_name(page, ephemeral_account) -> None:
    """The header greets the user by the name the account was created with."""
    login = LoginPage(page)
    login.open()

    login.login_as(ephemeral_account["email"], ephemeral_account["password"])

    login.wait_for_visible(login.header.LOGGED_IN_AS)
    assert login.header.logged_in_username == ephemeral_account["name"]


@pytest.mark.regression
@pytest.mark.parametrize("case", INVALID_LOGINS, ids=test_data.case_ids(INVALID_LOGINS))
def test_invalid_credentials_are_rejected(page, case) -> None:
    """Every bad-credential case is refused with the same message.

    The site returns one message for all of them, which is correct: telling an
    attacker whether an address exists is a disclosure, so the test asserts the
    cases are indistinguishable rather than asserting per-case wording.
    """
    login = LoginPage(page)
    login.open()

    login.login_as(case["email"], case["password"])

    assert login.wait_for_error() == case["expected_message"], (
        f"case {case['id']}: {case['description']}"
    )


@pytest.mark.regression
@pytest.mark.parametrize("case", CLIENT_BLOCKED, ids=test_data.case_ids(CLIENT_BLOCKED))
def test_malformed_email_is_blocked_before_submission(page, case) -> None:
    """The browser refuses to submit an invalid email, so nothing reaches the server.

    Worth its own test rather than folding into the cases above: the outcome is
    genuinely different. There is no error message to assert on, because the
    form never submitted. Asserting the *absence* of a session here is what
    distinguishes "the browser stopped it" from "the server accepted it".
    """
    login = LoginPage(page)
    login.open()

    login.login_as(case["email"], case["password"])

    assert not login.has_login_error, (
        f"case {case['id']}: expected no server error, the form should not have "
        f"submitted; got {login.error_message!r}"
    )
    assert not login.header.is_logged_in, f"case {case['id']}: a session was created"


@pytest.mark.regression
def test_login_with_wrong_password_is_rejected(page, ephemeral_account) -> None:
    """A *real* account with the wrong password is refused.

    Distinct from the parametrized cases above, which use addresses that do not
    exist: this proves the password itself is actually checked, not merely that
    unknown addresses are turned away.
    """
    login = LoginPage(page)
    login.open()

    login.login_as(ephemeral_account["email"], "definitely-not-the-password")

    assert login.wait_for_error() == LOGIN_ERROR


@pytest.mark.regression
def test_rejected_credentials_do_not_create_a_session(page) -> None:
    """A failed attempt leaves the visitor signed out.

    Separate from the message assertion: a site can show an error and still
    leak a session, and that is the failure worth catching.
    """
    case = INVALID_LOGINS[0]
    login = LoginPage(page)
    login.open()

    login.login_as(case["email"], case["password"])

    login.wait_for_error()
    assert not login.header.is_logged_in


@pytest.mark.regression
def test_logout_ends_the_session(page, ephemeral_account) -> None:
    """Signing out returns the header to its logged-out state."""
    login = LoginPage(page)
    login.open()
    login.login_as(ephemeral_account["email"], ephemeral_account["password"])
    login.wait_for_visible(login.header.LOGOUT)

    login.header.logout()

    login.wait_for_visible(login.header.SIGNUP_LOGIN)
    assert not login.header.is_logged_in
