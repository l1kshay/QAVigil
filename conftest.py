"""Shared pytest fixtures for QAVigil.

Scope choices here exist to serve one rule above all: **every test must be
independent and order-agnostic** (ARCHITECTURE.md section 6).

* The browser process is session-scoped, because launching a browser is
  expensive and the process itself carries no test state.
* The browser *context* is function-scoped. A fresh context per test means
  fresh cookies, storage and cache, so a logged-in test cannot leak a session
  into the next one.
* The ``requests`` session is likewise function-scoped, so a cookie set by one
  API test cannot influence another. Connection pooling still applies within a
  test, which is where nearly all of the benefit is.

Failure artifacts (screenshots and traces) are wired into the Allure report in
Phase 5; this module deliberately stops at the fixtures Phase 1 calls for.
"""

from __future__ import annotations

import uuid
from typing import Any, Iterator

import pytest
import requests
from faker import Faker
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from api_clients.auth_client import AuthClient
from api_clients.base_client import BaseClient
from api_clients.product_client import ProductClient
from config.settings import REPORTS_DIR, settings
from pages.login_page import LoginPage

# Identifies our traffic to the target site rather than sending a bare
# python-requests default, which some hosts reject outright.
USER_AGENT = "QAVigil/1.0 (+https://github.com/l1kshay/QAVigil) automated-tests"


def pytest_configure(config: pytest.Config) -> None:
    """Ensure the reports tree exists before anything tries to write to it."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------
# UI fixtures
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture(scope="session")
def browser(playwright_instance: Playwright) -> Iterator[Browser]:
    """One browser process for the whole session, chosen by BROWSER in .env."""
    browser_type = getattr(playwright_instance, settings.browser)
    launched = browser_type.launch(
        headless=settings.headless,
        slow_mo=settings.slow_mo_ms,
    )
    yield launched
    launched.close()


@pytest.fixture
def browser_context(browser: Browser) -> Iterator[BrowserContext]:
    """A clean, isolated browser context per test."""
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        ignore_https_errors=True,
    )
    context.set_default_timeout(settings.timeout_ms)
    context.set_default_navigation_timeout(settings.timeout_ms)
    yield context
    context.close()


@pytest.fixture
def page(browser_context: BrowserContext) -> Iterator[Page]:
    """A fresh page for a single test."""
    new_page = browser_context.new_page()
    yield new_page
    new_page.close()


# ----------------------------------------------------------------------
# API fixtures
# ----------------------------------------------------------------------
@pytest.fixture
def api_session() -> Iterator[requests.Session]:
    """A fresh HTTP session per test, so no cookie outlives its test."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    yield session
    session.close()


@pytest.fixture
def auth_client(api_session: requests.Session) -> AuthClient:
    """Account and login endpoints, sharing the test's HTTP session."""
    return AuthClient(api_session)


@pytest.fixture
def product_client(api_session: requests.Session) -> ProductClient:
    """Catalogue endpoints, sharing the test's HTTP session."""
    return ProductClient(api_session)


# ----------------------------------------------------------------------
# test accounts
# ----------------------------------------------------------------------
@pytest.fixture(scope="session")
def faker_instance() -> Faker:
    """One Faker for the session. Seeded per-call, never globally, so tests
    stay independent rather than depending on a shared sequence."""
    return Faker()


@pytest.fixture
def account_payload(faker_instance: Faker) -> dict[str, Any]:
    """Registration details for a unique account that has *not* been created.

    Separate from ``ephemeral_account`` because the account-lifecycle tests
    need to perform the registration themselves - that is the thing they are
    testing - while every other test just wants an account that already exists.
    """
    return {
        "name": faker_instance.name(),
        # example.com is reserved for documentation and cannot receive mail,
        # so no real inbox can ever be hit by these registrations.
        "email": f"qavigil.{uuid.uuid4().hex[:12]}@example.com",
        "password": faker_instance.password(length=12),
        "title": "Mr",
        "birth_date": "1",
        "birth_month": "1",
        "birth_year": "1990",
        "firstname": faker_instance.first_name(),
        "lastname": faker_instance.last_name(),
        "company": faker_instance.company(),
        "address1": faker_instance.street_address(),
        "address2": "",
        "country": "India",
        "zipcode": faker_instance.postcode(),
        "state": faker_instance.city(),
        "city": faker_instance.city(),
        "mobile_number": faker_instance.numerify("##########"),
    }


@pytest.fixture
def registered_account(
    account_payload: dict[str, Any],
) -> Iterator[dict[str, Any]]:
    """An account created through the API and removed afterwards.

    Teardown is best-effort: a lifecycle test may already have deleted the
    account itself, and that must not fail the test.
    """
    client = AuthClient()
    created = client.create_account(account_payload)
    if created.status != 201:
        pytest.fail(
            "could not create the test account this test depends on: "
            f"responseCode={created.status}, message={created.message!r}"
        )

    yield account_payload

    client.delete_account(account_payload["email"], account_payload["password"])


@pytest.fixture
def ephemeral_account(registered_account: dict[str, Any]) -> dict[str, Any]:
    """An existing account for tests that need one but do not manage it.

    Registration happens through the site's own API rather than the signup
    form. That is deliberate: the account is *setup*, not the thing under test,
    and driving a fifteen-field form through the browser for every checkout
    test would be slow, and would make a checkout failure indistinguishable
    from a signup failure.

    The address is unique per test, so tests can run in parallel and in any
    order without colliding, and teardown removes the account even when the
    test fails - runs do not litter a site other people share.
    """
    return registered_account


@pytest.fixture
def logged_in_page(page: Page, ephemeral_account: dict[str, Any]) -> Page:
    """A browser page already signed in as a freshly created account."""
    login = LoginPage(page)
    login.open()
    login.login_as(ephemeral_account["email"], ephemeral_account["password"])
    login.wait_for_visible(login.header.LOGOUT)
    return page
