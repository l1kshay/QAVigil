"""Base class for every Page Object in the suite.

Design rules this class exists to enforce (see ARCHITECTURE.md section 6):

* Tests never touch a raw Playwright locator or a URL. They call intent-named
  methods on a Page Object, and those methods delegate here.
* There is no ``sleep()`` anywhere. Playwright's locators auto-wait for an
  element to be attached, visible, stable and enabled before acting, and
  ``expect``-style waits cover the rest. If something needs waiting for, wait
  for the *condition*, never for a duration.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Locator, Page, expect

from config.settings import SCREENSHOTS_DIR, settings


class Header:
    """The site-wide navigation bar.

    Every page on automationexercise.com carries the same header, so it lives
    here as a component rather than being duplicated across five page objects.
    Which links are present is itself the site's signal of auth state: logged
    out shows "Signup / Login", logged in swaps it for Logout, Delete Account
    and a "Logged in as <name>" label.
    """

    SIGNUP_LOGIN = "a[href='/login']"
    LOGOUT = "a[href='/logout']"
    DELETE_ACCOUNT = "a[href='/delete_account']"
    HOME = "ul.nav.navbar-nav a[href='/']"
    PRODUCTS = "ul.nav.navbar-nav a[href='/products']"
    CART = "ul.nav.navbar-nav a[href='/view_cart']"
    LOGGED_IN_AS = "ul.nav.navbar-nav a:has-text('Logged in as')"

    def __init__(self, page: Page) -> None:
        self.page = page

    def go_home(self) -> None:
        self.page.locator(self.HOME).first.click()

    def go_to_products(self) -> None:
        self.page.locator(self.PRODUCTS).first.click()

    def go_to_cart(self) -> None:
        self.page.locator(self.CART).first.click()

    def go_to_login(self) -> None:
        self.page.locator(self.SIGNUP_LOGIN).first.click()

    def logout(self) -> None:
        self.page.locator(self.LOGOUT).first.click()

    @property
    def is_logged_in(self) -> bool:
        """Auth state as the site itself reports it."""
        return self.page.locator(self.LOGOUT).count() > 0

    @property
    def logged_in_username(self) -> str:
        """The name shown in "Logged in as <name>", or "" when logged out."""
        label = self.page.locator(self.LOGGED_IN_AS)
        if label.count() == 0:
            return ""
        return label.first.inner_text().replace("Logged in as", "").strip()


class BasePage:
    """Common navigation, interaction and query behaviour for all pages.

    Subclasses declare their own locators as class attributes and expose
    intent-named actions (``login_as``, ``search_for``, ...) built from the
    primitives here.
    """

    #: Site-relative path this page lives at. Subclasses override it.
    PATH: str = "/"

    def __init__(self, page: Page) -> None:
        self.page = page
        self.header = Header(page)

    # ------------------------------------------------------------------
    # navigation
    # ------------------------------------------------------------------
    def open(self, path: str | None = None) -> "BasePage":
        """Navigate to this page (or an explicit site-relative path)."""
        self.page.goto(settings.url_for(self.PATH if path is None else path))
        return self

    @property
    def current_url(self) -> str:
        return self.page.url

    @property
    def title(self) -> str:
        return self.page.title()

    def wait_for_url(self, url_substring: str) -> None:
        """Block until the address bar contains ``url_substring``."""
        self.page.wait_for_url(f"**{url_substring}**")

    # ------------------------------------------------------------------
    # interaction - each of these auto-waits for actionability
    # ------------------------------------------------------------------
    def click(self, target: str | Locator) -> None:
        self._locator(target).click()

    def fill(self, target: str | Locator, value: str) -> None:
        """Set an input's value in one step (clears any existing content)."""
        self._locator(target).fill(value)

    def type_into(self, target: str | Locator, value: str, delay_ms: int = 0) -> None:
        """Type key-by-key, for inputs that react to individual keystrokes."""
        self._locator(target).press_sequentially(value, delay=delay_ms)

    def select_option(self, target: str | Locator, value: str) -> None:
        self._locator(target).select_option(value)

    def scroll_into_view(self, target: str | Locator) -> None:
        self._locator(target).scroll_into_view_if_needed()

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    def text_of(self, target: str | Locator) -> str:
        return (self._locator(target).inner_text() or "").strip()

    def is_visible(self, target: str | Locator) -> bool:
        return self._locator(target).is_visible()

    def count(self, target: str | Locator) -> int:
        return self._locator(target).count()

    def wait_for_visible(self, target: str | Locator) -> Locator:
        """Wait for an element to be visible and return it.

        Uses ``expect`` so the failure message names the element and the
        timeout, rather than surfacing a bare TimeoutError.
        """
        locator = self._locator(target)
        expect(locator).to_be_visible(timeout=settings.timeout_ms)
        return locator

    # ------------------------------------------------------------------
    # dialogs and artifacts
    # ------------------------------------------------------------------
    def accept_next_dialog(self) -> None:
        """Auto-accept the next native dialog so it cannot block the run."""
        self.page.once("dialog", lambda dialog: dialog.accept())

    def screenshot(self, name: str) -> Path:
        """Capture a full-page screenshot into the reports directory."""
        SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
        path = SCREENSHOTS_DIR / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------
    def _locator(self, target: str | Locator) -> Locator:
        """Accept either a selector string or an already-built Locator.

        Subclasses can therefore declare locators as plain selector strings or
        as richer role/text-based Locators without callers caring which.
        """
        return self.page.locator(target) if isinstance(target, str) else target
