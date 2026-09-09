"""Client for the catalogue endpoints: productsList, brandsList, searchProduct.

This API is read-only - there is no endpoint to create, update or delete a
product - so the "CRUD" coverage in tests/api/test_products_crud.py is the
Read half of it, exercised thoroughly, plus the guards that stop the other
verbs from working.
"""

from __future__ import annotations

from typing import Any

from api_clients.base_client import ApiResponse, BaseClient


class ProductClient(BaseClient):
    """Catalogue reads and searches."""

    SEARCH_PARAM_MISSING = (
        "Bad request, search_product parameter is missing in POST request."
    )
    METHOD_NOT_SUPPORTED = "This request method is not supported."

    # ------------------------------------------------------------------
    # reads
    # ------------------------------------------------------------------
    def list_products(self) -> ApiResponse:
        """The full product catalogue."""
        return self.get("productsList")

    def list_brands(self) -> ApiResponse:
        """Every brand the catalogue carries."""
        return self.get("brandsList")

    def search(self, term: str) -> ApiResponse:
        """Search the catalogue. Matches product name *and* category."""
        return self.post("searchProduct", data={"search_product": term})

    def search_raw(self, payload: dict[str, Any]) -> ApiResponse:
        """Send an arbitrary searchProduct payload, for negative cases."""
        return self.post("searchProduct", data=payload)

    # ------------------------------------------------------------------
    # method guards
    # ------------------------------------------------------------------
    def products_list_with_method(self, method: str) -> ApiResponse:
        return self.request(method, "productsList")

    def brands_list_with_method(self, method: str) -> ApiResponse:
        return self.request(method, "brandsList")

    def search_with_method(self, method: str) -> ApiResponse:
        return self.request(method, "searchProduct")
