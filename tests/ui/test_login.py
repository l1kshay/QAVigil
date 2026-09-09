"""UI tests for the login flow.

Happy path first, then the failure modes. Each test asserts one thing, and
each gets its own freshly created account so nothing depends on run order or
on an account someone else may have changed.

The literal credentials still present here move into test_data/users.yaml in
Phase 4; the account-derived values already come from a fixture.
"""

from __future__ import annotations

import pytest

from pages.login_page import LoginPage

INCORRECT_CREDENTIALS_MESSAGE = "Your email or password is incorrect!"


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
def test_login_with_wrong_password_is_rejected(page, ephemeral_account) -> None:
    """A real account with the wrong password does not get in."""
    login = LoginPage(page)
    login.open()

    login.login_as(ephemeral_account["email"], "definitely-not-the-password")

    assert login.wait_for_error() == INCORRECT_CREDENTIALS_MESSAGE


@pytest.mark.regression
def test_login_with_unknown_email_is_rejected(page) -> None:
    """An address with no account behind it is refused.

    The site deliberately returns the same message as a wrong password, so the
    assertion is that the two are indistinguishable - which is the correct
    security behaviour, not an accident worth asserting around.
    """
    login = LoginPage(page)
    login.open()

    login.login_as("no-such-user@qavigil.invalid", "irrelevant-password")

    assert login.wait_for_error() == INCORRECT_CREDENTIALS_MESSAGE


@pytest.mark.regression
def test_login_rejected_credentials_do_not_create_a_session(page) -> None:
    """A failed attempt leaves the visitor signed out.

    Distinct from the message assertion above: a site can show an error and
    still leak a session, and that is the failure worth catching.
    """
    login = LoginPage(page)
    login.open()

    login.login_as("no-such-user@qavigil.invalid", "irrelevant-password")

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
