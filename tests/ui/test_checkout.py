"""UI tests for the checkout and payment journey.

These are the most expensive tests in the suite - each one registers an
account, fills a cart and places an order - so there are few of them and each
targets a distinct failure. The account comes from a fixture that cleans up
after itself, so a failed run does not leave orders behind.

The card values below are placeholders on a demo site that processes nothing;
they move into test_data in Phase 4.
"""

from __future__ import annotations

import pytest

from pages.cart_page import CartPage
from pages.checkout_page import CheckoutPage
from pages.search_page import SearchPage

CARD_NAME = "QA Vigil"
CARD_NUMBER = "4111111111111111"
CARD_CVC = "311"
CARD_EXPIRY_MONTH = "12"
CARD_EXPIRY_YEAR = "2030"
ORDER_COMMENT = "Placed by the QAVigil automated suite."


def _fill_cart_and_check_out(page) -> CheckoutPage:
    """Put one product in the cart and reach the checkout page.

    Shared setup, not a test: expressed as a helper so each test below can
    open with the state it needs and still assert exactly one thing.
    """
    products = SearchPage(page)
    products.open()
    products.add_first_result_to_cart()
    products.view_cart()

    CartPage(page).proceed_to_checkout()

    checkout = CheckoutPage(page)
    checkout.wait_for_url("/checkout")
    return checkout


@pytest.mark.smoke
def test_signed_in_user_reaches_checkout(logged_in_page) -> None:
    """A signed-in shopper gets to checkout instead of the login prompt."""
    checkout = _fill_cart_and_check_out(logged_in_page)

    assert "/checkout" in checkout.current_url


@pytest.mark.regression
def test_checkout_shows_the_account_delivery_address(
    logged_in_page, ephemeral_account
) -> None:
    """The delivery address matches what the account was registered with."""
    checkout = _fill_cart_and_check_out(logged_in_page)

    assert ephemeral_account["address1"] in checkout.delivery_address, (
        f"expected {ephemeral_account['address1']!r} in the delivery address, "
        f"got {checkout.delivery_address!r}"
    )


@pytest.mark.regression
def test_checkout_reviews_the_cart_contents(logged_in_page) -> None:
    """The order review lists the single product that was added."""
    checkout = _fill_cart_and_check_out(logged_in_page)

    assert checkout.review_item_count == 1, (
        f"expected 1 item in the order review, found {checkout.review_item_count}"
    )


@pytest.mark.smoke
def test_placing_an_order_confirms_it(logged_in_page) -> None:
    """The full journey ends in a confirmed order."""
    checkout = _fill_cart_and_check_out(logged_in_page)
    checkout.add_order_comment(ORDER_COMMENT)

    payment = checkout.place_order().pay_with(
        name_on_card=CARD_NAME,
        card_number=CARD_NUMBER,
        cvc=CARD_CVC,
        expiry_month=CARD_EXPIRY_MONTH,
        expiry_year=CARD_EXPIRY_YEAR,
    )

    assert payment.is_order_confirmed, (
        f"expected an order confirmation, page said: {payment.confirmation_message!r}"
    )


@pytest.mark.regression
def test_confirmed_order_offers_an_invoice(logged_in_page) -> None:
    """A completed order exposes its invoice for download."""
    checkout = _fill_cart_and_check_out(logged_in_page)

    payment = checkout.place_order().pay_with(
        name_on_card=CARD_NAME,
        card_number=CARD_NUMBER,
        cvc=CARD_CVC,
        expiry_month=CARD_EXPIRY_MONTH,
        expiry_year=CARD_EXPIRY_YEAR,
    )

    assert payment.has_invoice_link
