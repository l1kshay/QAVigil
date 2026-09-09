"""API tests for the catalogue endpoints.

This API exposes no way to create, update or delete a product, so the CRUD
coverage here is Read, exercised properly: the payload's shape, its types, and
the behaviour of search. The guards that reject the write verbs live in
test_negative_cases.py.
"""

from __future__ import annotations

import pytest

from api_clients.schemas import (
    BRANDS_LIST_SCHEMA,
    PRODUCTS_LIST_SCHEMA,
    SEARCH_RESULT_SCHEMA,
)

SEARCH_TERM = "dress"
SEARCH_TERM_WITH_NO_MATCHES = "zzqqxx-no-such-product"


@pytest.mark.smoke
def test_products_list_returns_the_catalogue(product_client) -> None:
    """The catalogue endpoint answers with products."""
    response = product_client.list_products()

    response.assert_status(200)
    assert len(response.body["products"]) > 0


@pytest.mark.smoke
def test_products_list_matches_its_schema(product_client) -> None:
    """Every product honours the documented contract.

    This is the test that catches a silent contract change - a renamed field
    or a type that flips from integer to string - which a length check alone
    would sail straight past.
    """
    response = product_client.list_products()

    response.validate_schema(PRODUCTS_LIST_SCHEMA)


@pytest.mark.regression
def test_products_have_unique_ids(product_client) -> None:
    """Product ids identify a product, which means they cannot repeat."""
    products = product_client.list_products().body["products"]

    ids = [p["id"] for p in products]
    assert len(ids) == len(set(ids)), f"duplicate product ids in {ids}"


@pytest.mark.smoke
def test_brands_list_returns_brands(product_client) -> None:
    """The brands endpoint answers with brands."""
    response = product_client.list_brands()

    response.assert_status(200)
    assert len(response.body["brands"]) > 0


@pytest.mark.regression
def test_brands_list_matches_its_schema(product_client) -> None:
    """Every brand honours the documented contract."""
    response = product_client.list_brands()

    response.validate_schema(BRANDS_LIST_SCHEMA)


@pytest.mark.smoke
def test_search_returns_matching_products(product_client) -> None:
    """A search for a known term returns results."""
    response = product_client.search(SEARCH_TERM)

    response.assert_status(200)
    assert len(response.body["products"]) > 0


@pytest.mark.regression
def test_search_matches_on_category_not_only_name(product_client) -> None:
    """Search matches a product's category as well as its name.

    This is the behaviour that made an early UI test fail: searching "dress"
    returns items such as "Sleeves Top and Short - Blue & Pink" whose name does
    not contain the term but whose category is Dress. The UI grid does not show
    categories, so the assertion belongs here, where the field exists.
    """
    products = product_client.search(SEARCH_TERM).body["products"]

    unmatched = [
        p["name"] for p in products
        if SEARCH_TERM.lower() not in p["name"].lower()
        and SEARCH_TERM.lower() not in p["category"]["category"].lower()
    ]
    assert not unmatched, (
        f"results matching neither the name nor the category of "
        f"{SEARCH_TERM!r}: {unmatched}"
    )


@pytest.mark.regression
def test_search_results_match_the_product_schema(product_client) -> None:
    """Search results carry the same product shape as the catalogue."""
    response = product_client.search(SEARCH_TERM)

    response.validate_schema(SEARCH_RESULT_SCHEMA)


@pytest.mark.regression
def test_search_returns_a_subset_of_the_catalogue(product_client) -> None:
    """A search narrows the catalogue rather than returning all of it."""
    catalogue_size = len(product_client.list_products().body["products"])

    results = len(product_client.search(SEARCH_TERM).body["products"])

    assert 0 < results < catalogue_size, (
        f"search returned {results} of {catalogue_size} products; "
        "expected a non-empty subset"
    )


@pytest.mark.regression
def test_search_with_no_matches_returns_an_empty_list(product_client) -> None:
    """A nonsense term returns nothing, rather than erroring or returning all."""
    response = product_client.search(SEARCH_TERM_WITH_NO_MATCHES)

    response.assert_status(200)
    assert response.body["products"] == []
