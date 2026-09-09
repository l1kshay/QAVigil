"""Page object for /login - the combined login and signup entry page."""

from __future__ import annotations

from pages.base_page import BasePage


class LoginPage(BasePage):
    """The "Login to your account" / "New User Signup!" page.

    Both forms live on the same URL, so this object exposes both entry points.
    Credentials are always passed in by the caller - a page object never knows
    a username or a password of its own.
    """

    PATH = "/login"

    # --- login form ---
    EMAIL = '[data-qa="login-email"]'
    PASSWORD = '[data-qa="login-password"]'
    SUBMIT = '[data-qa="login-button"]'
    LOGIN_FORM = ".login-form"
    # The site renders the failure as a red <p> inside the login form. There is
    # no id or data-qa on it, so it is matched by its inline colour style.
    ERROR = '.login-form p[style*="color"]'

    # --- signup form (same page) ---
    SIGNUP_NAME = '[data-qa="signup-name"]'
    SIGNUP_EMAIL = '[data-qa="signup-email"]'
    SIGNUP_SUBMIT = '[data-qa="signup-button"]'

    def is_loaded(self) -> bool:
        return self.is_visible(self.SUBMIT)

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    def login_as(self, email: str, password: str) -> "LoginPage":
        """Fill and submit the login form. Does not assert the outcome."""
        self.fill(self.EMAIL, email)
        self.fill(self.PASSWORD, password)
        self.click(self.SUBMIT)
        return self

    def start_signup(self, name: str, email: str) -> None:
        """Begin registration; the site then serves the full signup form."""
        self.fill(self.SIGNUP_NAME, name)
        self.fill(self.SIGNUP_EMAIL, email)
        self.click(self.SIGNUP_SUBMIT)

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------
    @property
    def has_login_error(self) -> bool:
        return self.count(self.ERROR) > 0

    @property
    def error_message(self) -> str:
        """The visible login error, or "" when the form reports none."""
        if not self.has_login_error:
            return ""
        return self.text_of(self.ERROR)

    def wait_for_error(self) -> str:
        """Wait for the failure message to appear, then return it.

        Used by the invalid-login test so the assertion waits on the condition
        rather than racing the page's re-render.
        """
        self.wait_for_visible(self.ERROR)
        return self.error_message
