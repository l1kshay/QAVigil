"""Page object for /view_cart - cart contents and the checkout hand-off."""

from __future__ import annotations

from playwright.sync_api import Locator

from pages.base_page import BasePage


class CartPage(BasePage):
    """The shopping cart.

    Rows are addressed by the site's own ``product-<id>`` row ids, so a test
    can assert on a specific product rather than on a positional index that
    shifts when the catalogue changes.
    """

    PATH = "/view_cart"

    TABLE = "#cart_info_table"
    ROWS = "#cart_info_table tbody tr"
    EMPTY_MESSAGE = "#empty_cart"
    CHECKOUT_BUTTON = "a.check_out"

    # Per-row cells.
    NAME_CELL = ".cart_description h4 a"
    PRICE_CELL = ".cart_price p"
    QUANTITY_CELL = ".cart_quantity button"
    TOTAL_CELL = ".cart_total_price"
    DELETE_CELL = ".cart_quantity_delete"

    # Shown when an anonymous visitor tries to check out.
    CHECKOUT_MODAL = "#checkoutModal"
    MODAL_REGISTER_LOGIN = "#checkoutModal a[href='/login']"

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    @property
    def is_empty(self) -> bool:
        return self.is_visible(self.EMPTY_MESSAGE)

    @property
    def item_count(self) -> int:
        return 0 if self.is_empty else self.count(self.ROWS)

    @property
    def product_names(self) -> list[str]:
        return [n.strip() for n in self.page.locator(f"{self.ROWS} {self.NAME_CELL}")
                .all_inner_texts()]

    def row_for(self, product_id: int | str) -> Locator:
        """The cart row for a given product id."""
        return self.page.locator(f"#product-{product_id}")

    def has_product(self, product_id: int | str) -> bool:
        return self.row_for(product_id).count() > 0

    def name_of(self, product_id: int | str) -> str:
        return self.row_for(product_id).locator(self.NAME_CELL).inner_text().strip()

    def price_of(self, product_id: int | str) -> str:
        """Unit price as displayed, e.g. "Rs. 500"."""
        return self.row_for(product_id).locator(self.PRICE_CELL).inner_text().strip()

    def quantity_of(self, product_id: int | str) -> int:
        return int(self.row_for(product_id).locator(self.QUANTITY_CELL).inner_text().strip())

    def total_of(self, product_id: int | str) -> str:
        return self.row_for(product_id).locator(self.TOTAL_CELL).inner_text().strip()

    @property
    def checkout_prompt_visible(self) -> bool:
        """Whether the "Register / Login to proceed" modal is showing."""
        return self.is_visible(self.CHECKOUT_MODAL)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def remove(self, product_id: int | str) -> None:
        """Delete a row and wait until it is actually gone from the DOM."""
        row = self.row_for(product_id)
        row.locator(self.DELETE_CELL).click()
        row.wait_for(state="detached")

    def proceed_to_checkout(self) -> None:
        self.click(self.CHECKOUT_BUTTON)

    def login_from_checkout_prompt(self) -> None:
        """Follow the anonymous-checkout modal's Register / Login link."""
        self.wait_for_visible(self.CHECKOUT_MODAL)
        self.click(self.MODAL_REGISTER_LOGIN)
        self.wait_for_url("/login")
