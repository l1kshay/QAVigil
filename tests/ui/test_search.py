"""UI tests for product browsing, search and the cart.

Cart tests live here rather than in a file of their own because adding to the
cart starts from the product listing; keeping the journey together keeps each
test short. Phase 4 moves the search terms below into test_data/products.json.
"""

from __future__ import annotations

import pytest

from pages.cart_page import CartPage
from pages.search_page import SearchPage

SEARCH_TERM = "dress"
SEARCH_TERM_WITH_NO_MATCHES = "zzqqxx-no-such-product"


@pytest.mark.smoke
def test_products_page_lists_the_catalogue(page) -> None:
    """The listing renders products for a visitor who has searched nothing."""
    products = SearchPage(page)
    products.open()

    assert products.result_count > 0, "expected the catalogue to list products"


@pytest.mark.smoke
def test_search_returns_matching_products(page) -> None:
    """A search returns a non-empty, narrower result set."""
    products = SearchPage(page)
    products.open()
    catalogue_size = products.result_count

    products.search_for(SEARCH_TERM)

    assert 0 < products.result_count < catalogue_size, (
        f"search for {SEARCH_TERM!r} returned {products.result_count} of "
        f"{catalogue_size} products; expected a non-empty subset"
    )


@pytest.mark.regression
def test_search_finds_a_product_by_its_exact_name(page) -> None:
    """Searching a product's own name returns that product.

    Note on what is *not* asserted here. An earlier version of this test
    required every result name to contain the search term, and it failed
    legitimately: this site matches on **category** as well as name, so
    searching "dress" correctly returns Kids items such as "Sleeves Top and
    Short - Blue & Pink" whose category is Dress. Asserting name-containment
    would encode a false assumption about the feature. Category is not shown
    on the listing grid, so category-level relevance is asserted in the API
    suite, where the category field is actually available.

    The term is taken from the live catalogue rather than hardcoded, so this
    keeps working when the demo site's inventory changes.
    """
    products = SearchPage(page)
    products.open()
    known_product = products.first_product_name

    products.search_for(known_product)

    assert known_product in products.result_names, (
        f"searching for {known_product!r} did not return it; "
        f"got {products.result_names}"
    )


@pytest.mark.regression
def test_search_switches_the_listing_heading(page) -> None:
    """The page announces that it is showing search results, not the catalogue."""
    products = SearchPage(page)
    products.open()

    products.search_for(SEARCH_TERM)

    assert "SEARCHED PRODUCTS" in products.heading.upper()


@pytest.mark.regression
def test_search_with_no_matches_returns_nothing(page) -> None:
    """A nonsense term yields an empty result set rather than the full catalogue."""
    products = SearchPage(page)
    products.open()

    products.search_for(SEARCH_TERM_WITH_NO_MATCHES)

    assert products.result_count == 0, (
        f"expected no matches for {SEARCH_TERM_WITH_NO_MATCHES!r}, "
        f"got {products.result_count}"
    )


@pytest.mark.smoke
def test_adding_a_product_puts_it_in_the_cart(page) -> None:
    """A product added from the listing appears in the cart."""
    products = SearchPage(page)
    products.open()
    expected_name = products.first_product_name

    products.add_first_result_to_cart()
    products.view_cart()

    cart = CartPage(page)
    assert expected_name in cart.product_names, (
        f"expected {expected_name!r} in the cart, found {cart.product_names}"
    )


@pytest.mark.regression
def test_cart_records_a_single_unit_for_one_add(page) -> None:
    """Adding a product once records a quantity of one, not zero or two."""
    products = SearchPage(page)
    products.open()

    products.add_first_result_to_cart()
    products.view_cart()

    cart = CartPage(page)
    assert cart.quantity_of(1) == 1


@pytest.mark.regression
def test_removing_the_last_item_empties_the_cart(page) -> None:
    """Deleting the only cart row leaves the cart genuinely empty."""
    products = SearchPage(page)
    products.open()
    products.add_first_result_to_cart()
    products.view_cart()
    cart = CartPage(page)

    cart.remove(1)

    assert cart.is_empty, f"cart still holds {cart.item_count} item(s)"


@pytest.mark.regression
def test_anonymous_checkout_is_blocked_behind_login(page) -> None:
    """A signed-out visitor is asked to register or log in before checkout."""
    products = SearchPage(page)
    products.open()
    products.add_first_result_to_cart()
    products.view_cart()
    cart = CartPage(page)

    cart.proceed_to_checkout()

    cart.wait_for_visible(cart.CHECKOUT_MODAL)
    assert cart.checkout_prompt_visible
