"""Page objects for /checkout and /payment - the order-placing flow.

Two classes live here because checkout and payment are one continuous user
journey on this site: /checkout reviews the order, and its Place Order link
leads straight to /payment. Splitting them across modules would scatter a
single flow for no gain.
"""

from __future__ import annotations

from pages.base_page import BasePage


class CheckoutPage(BasePage):
    """Address review, order comment and the hand-off to payment.

    Only reachable while logged in; an anonymous visitor is bounced to the
    "Register / Login" modal on the cart page instead.
    """

    PATH = "/checkout"

    DELIVERY_ADDRESS = "#address_delivery"
    INVOICE_ADDRESS = "#address_invoice"
    REVIEW_ROWS = "#cart_info tbody tr"
    COMMENT_BOX = "#ordermsg textarea"
    PLACE_ORDER = "a[href='/payment']"

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    @property
    def delivery_address(self) -> str:
        return self.text_of(self.DELIVERY_ADDRESS)

    @property
    def invoice_address(self) -> str:
        return self.text_of(self.INVOICE_ADDRESS)

    @property
    def review_item_count(self) -> int:
        """Order-review rows, excluding the table's header row."""
        return max(self.count(self.REVIEW_ROWS) - 1, 0)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def add_order_comment(self, comment: str) -> "CheckoutPage":
        self.fill(self.COMMENT_BOX, comment)
        return self

    def place_order(self) -> "PaymentPage":
        """Move on to payment and return the page object for it."""
        self.click(self.PLACE_ORDER)
        payment = PaymentPage(self.page)
        payment.wait_for_url("/payment")
        return payment


class PaymentPage(BasePage):
    """Card entry and the order confirmation that follows.

    The site takes any well-formed card - nothing is charged and no real
    payment processor is involved. Card values are supplied by the caller from
    test data, never held here.
    """

    PATH = "/payment"

    NAME_ON_CARD = '[data-qa="name-on-card"]'
    CARD_NUMBER = '[data-qa="card-number"]'
    CVC = '[data-qa="cvc"]'
    EXPIRY_MONTH = '[data-qa="expiry-month"]'
    EXPIRY_YEAR = '[data-qa="expiry-year"]'
    PAY_BUTTON = '[data-qa="pay-button"]'

    CONFIRMATION = "#form"
    INVOICE_LINK = "a:has-text('Download Invoice')"

    def pay_with(
        self,
        name_on_card: str,
        card_number: str,
        cvc: str,
        expiry_month: str,
        expiry_year: str,
    ) -> "PaymentPage":
        """Submit the card form and wait for the confirmation page.

        The site redirects to /payment_done/<amount> on success, so the wait is
        on that URL rather than on an arbitrary element appearing.
        """
        self.fill(self.NAME_ON_CARD, name_on_card)
        self.fill(self.CARD_NUMBER, card_number)
        self.fill(self.CVC, cvc)
        self.fill(self.EXPIRY_MONTH, expiry_month)
        self.fill(self.EXPIRY_YEAR, expiry_year)
        self.click(self.PAY_BUTTON)
        self.wait_for_url("/payment_done/")
        return self

    @property
    def confirmation_message(self) -> str:
        return self.text_of(self.CONFIRMATION)

    @property
    def is_order_confirmed(self) -> bool:
        return "ORDER PLACED!" in self.confirmation_message.upper()

    @property
    def has_invoice_link(self) -> bool:
        return self.count(self.INVOICE_LINK) > 0
