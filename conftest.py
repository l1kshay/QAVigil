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

from typing import Iterator

import pytest
import requests
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from config.settings import REPORTS_DIR, settings

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
