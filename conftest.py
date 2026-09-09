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

import platform
import sys
import uuid
from typing import Any, Iterator

import allure
import pytest
import requests
from faker import Faker
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from api_clients.auth_client import AuthClient
from api_clients.product_client import ProductClient
from config.settings import (
    ALLURE_RESULTS_DIR,
    REPORTS_DIR,
    SCREENSHOTS_DIR,
    TRACES_DIR,
    settings,
)
from pages.login_page import LoginPage
from test_data import loader as test_data

# Identifies our traffic to the target site rather than sending a bare
# python-requests default, which some hosts reject outright.
USER_AGENT = "QAVigil/1.0 (+https://github.com/l1kshay/QAVigil) automated-tests"


def pytest_configure(config: pytest.Config) -> None:
    """Ensure the reports tree exists before anything tries to write to it."""
    for directory in (REPORTS_DIR, SCREENSHOTS_DIR, TRACES_DIR, ALLURE_RESULTS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def pytest_sessionstart(session: pytest.Session) -> None:
    """Record what this run was executed against.

    Allure renders these on the report's front page. Without them a failed run
    is ambiguous - a red suite looks the same whether it ran headless against
    production or headed against a stale local build.
    """
    environment = {
        "Browser": settings.browser,
        "Headless": str(settings.headless),
        "Base.URL": settings.base_url,
        "API.Base.URL": settings.api_base_url,
        "Python": sys.version.split()[0],
        "Platform": platform.platform(),
    }
    ALLURE_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (ALLURE_RESULTS_DIR / "environment.properties").write_text(
        "\n".join(f"{key}={value}" for key, value in environment.items()),
        encoding="utf-8",
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    """Stash each phase's result, and capture UI artifacts on failure.

    Fixture teardown has no built-in way to know whether its test passed, so
    the result is stashed here for fixtures that need it.

    Capture happens in this hook rather than in the fixtures' teardown for one
    concrete reason: attachments made during teardown are filed by Allure under
    the fixture's "Tear down" container, which puts the screenshot two clicks
    away from the failure. Attaching here files them against the test itself,
    which is where someone reading a red report will actually look. The page is
    still open at this point, which is what makes it possible.
    """
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"report_{report.when}", report)

    if report.when == "call" and report.failed:
        _capture_ui_failure(item)


def _capture_ui_failure(item: pytest.Item) -> None:
    """Attach a screenshot, URL, page HTML and Playwright trace to the report.

    Silent about its own errors on purpose: if the browser has already crashed,
    a capture failure must not replace the real test failure with a confusing
    one. It reports the problem as an attachment instead.
    """
    page = item.funcargs.get("page")
    context = item.funcargs.get("browser_context")
    if page is None:
        return  # an API test - nothing to photograph

    name = _artifact_name(item)

    try:
        screenshot_path = SCREENSHOTS_DIR / f"{name}.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        allure.attach.file(
            str(screenshot_path),
            name="screenshot-at-failure",
            attachment_type=allure.attachment_type.PNG,
        )
        allure.attach(
            page.url, name="url-at-failure", attachment_type=allure.attachment_type.TEXT
        )
        allure.attach(
            page.content(),
            name="page-html-at-failure",
            attachment_type=allure.attachment_type.HTML,
        )
    except Exception as exc:  # pragma: no cover - diagnostics must not mask the failure
        allure.attach(
            f"could not capture page artifacts: {type(exc).__name__}: {exc}",
            name="artifact-capture-error",
            attachment_type=allure.attachment_type.TEXT,
        )

    if context is not None:
        try:
            trace_path = TRACES_DIR / f"{name}.zip"
            context.tracing.stop(path=str(trace_path))
            # Tell the fixture not to stop tracing a second time.
            context.qavigil_trace_saved = True
            allure.attach.file(
                str(trace_path),
                name="playwright-trace (open at trace.playwright.dev)",
                extension="zip",
            )
        except Exception as exc:  # pragma: no cover
            allure.attach(
                f"could not save the Playwright trace: {type(exc).__name__}: {exc}",
                name="trace-capture-error",
                attachment_type=allure.attachment_type.TEXT,
            )


def _test_failed(item: pytest.Item) -> bool:
    """Whether the test body (not setup or teardown) failed."""
    report = getattr(item, "report_call", None)
    return report is not None and report.failed


def _artifact_name(item: pytest.Item) -> str:
    """A filesystem-safe, collision-free name derived from the test's node id."""
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in item.name)
    return f"{safe}_{uuid.uuid4().hex[:8]}"


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
def browser_context(browser: Browser, request: pytest.FixtureRequest) -> Iterator[BrowserContext]:
    """A clean, isolated browser context per test, recording a Playwright trace.

    Tracing runs for every test but is only ever *written* for a failing one.
    A trace is a full recording - DOM snapshots, network, console, sources -
    so it is the single most useful thing to have when a CI failure cannot be
    reproduced locally. Keeping them for passing tests would cost hundreds of
    megabytes per run and bury the one that matters.
    """
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        ignore_https_errors=True,
    )
    context.set_default_timeout(settings.timeout_ms)
    context.set_default_navigation_timeout(settings.timeout_ms)
    context.tracing.start(screenshots=True, snapshots=True, sources=True)
    context.qavigil_trace_saved = False

    yield context

    # A failing test's trace was already stopped and saved by
    # _capture_ui_failure; stopping it again would raise.
    if not getattr(context, "qavigil_trace_saved", False):
        context.tracing.stop()

    context.close()


@pytest.fixture
def page(browser_context: BrowserContext) -> Iterator[Page]:
    """A fresh page for a single test.

    Failure artifacts are captured by _capture_ui_failure during the call
    phase, while this page is still open - see pytest_runtest_makereport.
    """
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
        # Faker supplies everything that must be unique or realistic...
        "name": faker_instance.name(),
        # example.com is reserved for documentation and cannot receive mail,
        # so no real inbox can ever be hit by these registrations.
        "email": f"qavigil.{uuid.uuid4().hex[:12]}@example.com",
        "password": faker_instance.password(length=12),
        "firstname": faker_instance.first_name(),
        "lastname": faker_instance.last_name(),
        "company": faker_instance.company(),
        "address1": faker_instance.street_address(),
        "address2": "",
        "zipcode": faker_instance.postcode(),
        "state": faker_instance.city(),
        "city": faker_instance.city(),
        "mobile_number": faker_instance.numerify("##########"),
        # ...and test_data supplies the fields the site validates against its
        # own fixed lists, which Faker cannot invent valid values for.
        **test_data.users()["account_defaults"],
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
