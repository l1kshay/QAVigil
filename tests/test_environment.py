"""Phase 1 environment checks.

These are not feature tests. They answer a narrower question: is the target
application reachable, and is the framework itself wired up correctly? When a
CI run goes red, this file is what tells you whether the suite found a real
regression or simply could not reach automationexercise.com.

Kept deliberately thin, and marked ``smoke`` so it runs on every push.
"""

from __future__ import annotations

import pytest

from api_clients.base_client import BaseClient
from config.settings import settings
from pages.base_page import BasePage


@pytest.mark.smoke
def test_ui_home_page_loads(page) -> None:
    """The site under test serves its home page to a real browser."""
    home = BasePage(page).open()

    assert settings.base_url in home.current_url, (
        f"expected to land on {settings.base_url}, ended up at {home.current_url}"
    )


@pytest.mark.smoke
def test_api_products_endpoint_is_reachable(api_session) -> None:
    """The API answers, and returns a non-empty product catalogue."""
    response = BaseClient(api_session).get("productsList")

    response.assert_status(200)
    assert response.body.get("products"), (
        f"productsList returned no products; body={response.body!r}"
    )


@pytest.mark.smoke
def test_api_reports_status_in_response_body(api_session) -> None:
    """Guards the assumption the whole API client layer rests on.

    This target answers every request with HTTP 200 and puts the real status in
    the body's ``responseCode``. If the site ever starts using real HTTP status
    codes, ``ApiResponse.status`` would silently change meaning and negative
    tests could pass vacuously - so that assumption is asserted explicitly,
    once, here rather than left implicit everywhere.
    """
    # A request with no search term: documented as a 400-equivalent.
    response = BaseClient(api_session).post("searchProduct", data={})

    assert response.http_status == 200, (
        "the target no longer answers errors with HTTP 200 - the "
        "responseCode-based design in api_clients/base_client.py needs revisiting "
        f"(got HTTP {response.http_status})"
    )
    response.assert_status(400)
