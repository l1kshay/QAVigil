"""Page object for /products - browsing, searching and adding to cart."""

from __future__ import annotations

from pages.base_page import BasePage


class SearchPage(BasePage):
    """The All Products / Searched Products listing.

    The same grid renders both the full catalogue and search results; the
    heading is what distinguishes them, so it is exposed for assertions.
    """

    PATH = "/products"

    SEARCH_INPUT = "#search_product"
    SEARCH_BUTTON = "#submit_search"
    HEADING = ".features_items .title"

    PRODUCT_CARD = ".features_items .product-image-wrapper"
    PRODUCT_NAME = ".features_items .product-image-wrapper .productinfo p"
    PRODUCT_PRICE = ".features_items .product-image-wrapper .productinfo h2"
    ADD_TO_CART = ".features_items .product-image-wrapper .productinfo .add-to-cart"

    # Modal shown after adding an item.
    CART_MODAL = "#cartModal"
    MODAL_VIEW_CART = "#cartModal a[href='/view_cart']"
    MODAL_CONTINUE = "#cartModal .close-modal"

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def search_for(self, term: str) -> "SearchPage":
        """Run a product search and wait for the results grid to settle."""
        self.fill(self.SEARCH_INPUT, term)
        self.click(self.SEARCH_BUTTON)
        self.wait_for_visible(self.HEADING)
        return self

    def add_to_cart_by_index(self, index: int = 0) -> "SearchPage":
        """Add the nth listed product, then wait for the confirmation modal.

        Hovering is not required: the ``.productinfo`` copy of the button is
        always in the DOM, and Playwright scrolls it into view before clicking.
        """
        self.page.locator(self.ADD_TO_CART).nth(index).click()
        self.wait_for_cart_modal()
        return self

    def add_first_result_to_cart(self) -> "SearchPage":
        return self.add_to_cart_by_index(0)

    def wait_for_cart_modal(self) -> None:
        self.wait_for_visible(self.CART_MODAL)

    def continue_shopping(self) -> None:
        """Dismiss the confirmation modal and wait for it to disappear.

        Waiting for the hidden state matters: the modal's fade-out otherwise
        intercepts the next click.
        """
        self.click(self.MODAL_CONTINUE)
        self.page.locator(self.CART_MODAL).wait_for(state="hidden")

    def view_cart(self) -> None:
        """Follow the modal's View Cart link."""
        self.click(self.MODAL_VIEW_CART)
        self.wait_for_url("/view_cart")

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    @property
    def heading(self) -> str:
        """"ALL PRODUCTS" when browsing, "SEARCHED PRODUCTS" after a search."""
        return self.text_of(self.HEADING)

    @property
    def result_count(self) -> int:
        return self.count(self.PRODUCT_CARD)

    @property
    def result_names(self) -> list[str]:
        return [n.strip() for n in self.page.locator(self.PRODUCT_NAME).all_inner_texts()]

    @property
    def first_product_name(self) -> str:
        return self.page.locator(self.PRODUCT_NAME).first.inner_text().strip()

    @property
    def first_product_price(self) -> str:
        return self.page.locator(self.PRODUCT_PRICE).first.inner_text().strip()
