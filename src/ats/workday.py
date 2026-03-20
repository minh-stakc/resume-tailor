"""Workday ATS adapter — *.myworkdayjobs.com / *.wd*.myworkdaysite.com."""

import re
import time
from playwright.sync_api import Page

from src.ats.base import ATSAdapter


class WorkdayAdapter(ATSAdapter):

    @staticmethod
    def matches(url: str) -> bool:
        return bool(re.search(r"(myworkdayjobs|myworkdaysite|workday)\.com", url, re.IGNORECASE))

    def extract_jd(self, page: Page) -> str:
        # Workday renders JD in data-automation-id containers
        for sel in [
            '[data-automation-id="jobPostingDescription"]',
            '.job-description',
            '[class*="jobDescription"]',
            'main',
        ]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text
        return page.inner_text("body")

    def navigate_to_apply(self, page: Page) -> None:
        # Workday has an "Apply" button with data-automation-id
        apply_selectors = [
            '[data-automation-id="jobPostingApplyButton"]',
            'a[href*="apply"]',
            'button:has-text("Apply")',
        ]
        for sel in apply_selectors:
            btn = page.query_selector(sel)
            if btn:
                btn.click()
                page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(2)  # Workday is slow to render forms

                # Workday often requires login/account creation
                if page.query_selector('[data-automation-id="signInLink"], [data-automation-id="createAccountLink"]'):
                    print("  [WARN] Workday requires account creation/login.")
                    print("  Please complete the login step manually, then press Enter.")
                    input("  Press Enter when ready to continue filling the form...")
                    page.wait_for_load_state("networkidle", timeout=20000)
                return

    def fill_form(self, page: Page, info: dict) -> dict:
        status = {}
        time.sleep(2)  # Wait for Workday's JS to finish rendering

        # Workday uses data-automation-id for field identification
        wd_fields = {
            "first_name": ('[data-automation-id="legalNameSection_firstName"], '
                           'input[aria-label*="First Name" i]'),
            "last_name": ('[data-automation-id="legalNameSection_lastName"], '
                          'input[aria-label*="Last Name" i]'),
            "email": ('[data-automation-id="email"], '
                      'input[aria-label*="Email" i], '
                      'input[type="email"]'),
            "phone": ('[data-automation-id="phone-number"], '
                      'input[aria-label*="Phone" i], '
                      'input[type="tel"]'),
        }

        for field, selector in wd_fields.items():
            value = info.get(field, "")
            status[field] = self._try_selectors(page, selector, value, field)

        # Workday dropdowns for country/state
        self._try_workday_dropdown(page, "country", info.get("country", ""), status)

        # Source (How did you hear)
        self._try_workday_dropdown(page, "source", info.get("how_did_you_hear", ""), status)

        return status

    def upload_resume(self, page: Page, pdf_path: str) -> bool:
        selectors = [
            '[data-automation-id="file-upload-input-ref"]',
            'input[type="file"][data-automation-id*="resume" i]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self._safe_upload(page, sel, pdf_path):
                print(f"  [UPLOAD] Resume uploaded via {sel}")
                return True
        print("  [WARN] Could not find resume upload field")
        return False

    def _try_selectors(self, page: Page, combined_selector: str, value: str, field_name: str) -> str:
        if not value:
            return "skipped"
        for sel in combined_selector.split(", "):
            result = self._safe_fill(page, sel.strip(), str(value), field_name)
            if result == "filled":
                return "filled"
        return "not_found"

    def _try_workday_dropdown(self, page: Page, keyword: str, value: str, status: dict) -> None:
        """Workday dropdowns are custom widgets, not <select> elements."""
        if not value:
            return
        try:
            # Find the dropdown button by automation-id or aria-label
            dropdown = page.query_selector(
                f'[data-automation-id*="{keyword}" i], '
                f'button[aria-label*="{keyword}" i]'
            )
            if dropdown:
                dropdown.click()
                time.sleep(1)
                # Type to filter options
                page.keyboard.type(value)
                time.sleep(0.5)
                # Select first matching option
                option = page.query_selector(f'[data-automation-id="promptOption"]:has-text("{value}")')
                if option:
                    option.click()
                    status[keyword] = "filled"
                    return
                page.keyboard.press("Escape")
            status[keyword] = "not_found"
        except Exception:
            status[keyword] = "not_found"
