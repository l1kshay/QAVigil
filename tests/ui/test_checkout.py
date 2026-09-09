"""UI tests for the checkout and payment journey.

These are the most expensive tests in the suite - each one registers an
account, fills a cart and places an order - so there are few of them and each
targets a distinct failure. The account comes from a fixture that cleans up
after itself, so a failed run does not leave orders behind.

Card and order inputs come from test_data/checkout.yaml.
"""

from __future__ import annotations

import pytest

from pages.cart_page import CartPage
from pages.checkout_page import CheckoutPage
from pages.search_page import SearchPage
from test_data import loader as test_data

CHECKOUT_DATA = test_data.checkout()
CARD = CHECKOUT_DATA["payment_card"]
ORDER = CHECKOUT_DATA["order"]


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


def _pay(checkout: CheckoutPage):
    """Complete payment with the card from test data."""
    return checkout.place_order().pay_with(
        name_on_card=CARD["name_on_card"],
        card_number=CARD["card_number"],
        cvc=CARD["cvc"],
        expiry_month=CARD["expiry_month"],
        expiry_year=CARD["expiry_year"],
    )


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

    assert checkout.review_item_count == ORDER["expected_item_count"], (
        f"expected {ORDER['expected_item_count']} item(s) in the order review, "
        f"found {checkout.review_item_count}"
    )


@pytest.mark.smoke
def test_placing_an_order_confirms_it(logged_in_page) -> None:
    """The full journey ends in a confirmed order."""
    checkout = _fill_cart_and_check_out(logged_in_page)
    checkout.add_order_comment(ORDER["comment"])

    payment = _pay(checkout)

    assert payment.is_order_confirmed, (
        f"expected an order confirmation, page said: {payment.confirmation_message!r}"
    )


@pytest.mark.regression
def test_confirmed_order_offers_an_invoice(logged_in_page) -> None:
    """A completed order exposes its invoice for download."""
    checkout = _fill_cart_and_check_out(logged_in_page)

    payment = _pay(checkout)

    assert payment.has_invoice_link
