"""Abstract base class for ATS platform adapters."""

from abc import ABC, abstractmethod
from playwright.sync_api import Page


class ATSAdapter(ABC):
    """Each ATS adapter knows how to extract JD, navigate to the apply form,
    fill fields, and upload a resume for a specific platform."""

    @staticmethod
    @abstractmethod
    def matches(url: str) -> bool:
        """Return True if this adapter handles the given URL."""
        ...

    @abstractmethod
    def extract_jd(self, page: Page) -> str:
        """Extract job description text from the listing page."""
        ...

    @abstractmethod
    def navigate_to_apply(self, page: Page) -> None:
        """Click through to the application form."""
        ...

    @abstractmethod
    def fill_form(self, page: Page, info: dict) -> dict:
        """Fill the application form fields.

        Returns a dict of {field_name: "filled" | "skipped" | "not_found"}.
        """
        ...

    @abstractmethod
    def upload_resume(self, page: Page, pdf_path: str) -> bool:
        """Upload the resume PDF. Returns True on success."""
        ...

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _safe_fill(page: Page, selector: str, value: str, field_name: str) -> str:
        """Try to fill a text field. Returns status string."""
        if not value:
            return "skipped"
        try:
            el = page.query_selector(selector)
            if el:
                el.click()
                el.fill(value)
                return "filled"
            return "not_found"
        except Exception:
            return "not_found"

    @staticmethod
    def _safe_select(page: Page, selector: str, value: str, field_name: str) -> str:
        """Try to select a dropdown option by visible text or value. Returns status."""
        if not value:
            return "skipped"
        try:
            el = page.query_selector(selector)
            if not el:
                return "not_found"
            # Try by label first, then by value
            try:
                page.select_option(selector, label=value)
                return "filled"
            except Exception:
                try:
                    page.select_option(selector, value=value)
                    return "filled"
                except Exception:
                    return "not_found"
        except Exception:
            return "not_found"

    @staticmethod
    def _safe_upload(page: Page, selector: str, file_path: str) -> bool:
        """Try to upload a file. Returns True on success."""
        try:
            el = page.query_selector(selector)
            if el:
                el.set_input_files(file_path)
                return True
            return False
        except Exception:
            return False

    @staticmethod
    def _safe_check(page: Page, selector: str, should_check: bool) -> str:
        """Try to check/uncheck a checkbox. Returns status."""
        try:
            el = page.query_selector(selector)
            if not el:
                return "not_found"
            if should_check:
                el.check()
            else:
                el.uncheck()
            return "filled"
        except Exception:
            return "not_found"
