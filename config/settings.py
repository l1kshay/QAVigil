"""Central configuration for QAVigil.

Every environment-dependent value (target URLs, browser behaviour, test
credentials) is resolved here, once, from environment variables. Nothing else
in the suite reads ``os.environ`` directly, and no test or page object ever
hardcodes a URL or a credential.

Resolution order: real environment variables win, then values from a local
``.env`` file, then the defaults below. That ordering is what lets CI inject
GitHub Actions Secrets without a ``.env`` file existing at all.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# override=False: a variable already exported in the environment (as in CI)
# takes precedence over the local .env file.
load_dotenv(PROJECT_ROOT / ".env", override=False)

_TRUTHY = {"1", "true", "yes", "on"}


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in _TRUTHY


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Immutable, validated view of the environment."""

    base_url: str
    api_base_url: str
    browser: str
    headless: bool
    timeout_ms: int
    slow_mo_ms: int
    test_user_email: str
    test_user_password: str

    SUPPORTED_BROWSERS = ("chromium", "firefox", "webkit")

    @classmethod
    def load(cls) -> "Settings":
        base_url = os.getenv("BASE_URL", "https://automationexercise.com").rstrip("/")
        api_base_url = os.getenv("API_BASE_URL", f"{base_url}/api").rstrip("/")
        browser = os.getenv("BROWSER", "chromium").strip().lower()

        if browser not in cls.SUPPORTED_BROWSERS:
            raise ValueError(
                f"BROWSER must be one of {cls.SUPPORTED_BROWSERS}, got {browser!r}"
            )

        return cls(
            base_url=base_url,
            api_base_url=api_base_url,
            browser=browser,
            headless=_get_bool("HEADLESS", True),
            timeout_ms=_get_int("TIMEOUT_MS", 30_000),
            slow_mo_ms=_get_int("SLOW_MO_MS", 0),
            test_user_email=os.getenv("TEST_USER_EMAIL", ""),
            test_user_password=os.getenv("TEST_USER_PASSWORD", ""),
        )

    @property
    def has_test_account(self) -> bool:
        """Whether a pre-existing test account was configured.

        Tests that require a known-good account skip rather than fail when this
        is False, so a fresh clone without a .env still runs cleanly.
        """
        return bool(self.test_user_email and self.test_user_password)

    def url_for(self, path: str = "") -> str:
        """Absolute UI URL for a site-relative path."""
        return f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

    def api_url_for(self, path: str = "") -> str:
        """Absolute API URL for an endpoint name or path."""
        return f"{self.api_base_url}/{path.lstrip('/')}" if path else self.api_base_url


settings = Settings.load()

# Where UI failure artifacts land. Phase 5 wires these into the Allure report.
REPORTS_DIR = PROJECT_ROOT / "reports"
SCREENSHOTS_DIR = REPORTS_DIR / "screenshots"
TRACES_DIR = REPORTS_DIR / "traces"
TEST_DATA_DIR = PROJECT_ROOT / "test_data"
