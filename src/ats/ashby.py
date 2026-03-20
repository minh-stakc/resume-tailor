"""Ashby ATS adapter — jobs.ashbyhq.com."""

import re
from playwright.sync_api import Page

from src.ats.base import ATSAdapter


class AshbyAdapter(ATSAdapter):

    @staticmethod
    def matches(url: str) -> bool:
        return bool(re.search(r"ashbyhq\.com", url, re.IGNORECASE))

    def extract_jd(self, page: Page) -> str:
        for sel in ['[class*="job-description"]', '[class*="posting"]', "main"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text
        return page.inner_text("body")

    def navigate_to_apply(self, page: Page) -> None:
        apply_btn = page.query_selector(
            'a[href*="apply"], button:has-text("Apply")'
        )
        if apply_btn:
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)

    def fill_form(self, page: Page, info: dict) -> dict:
        status = {}

        # Ashby uses standard form inputs with label associations
        label_field_map = {
            "First Name": info.get("first_name", ""),
            "Last Name": info.get("last_name", ""),
            "Email": info.get("email", ""),
            "Phone": info.get("phone", ""),
            "LinkedIn": info.get("linkedin", ""),
            "GitHub": info.get("github", ""),
            "Website": info.get("github", ""),
            "School": info.get("school", ""),
            "University": info.get("school", ""),
        }

        for label_text, value in label_field_map.items():
            if not value:
                status[label_text.lower()] = "skipped"
                continue
            status[label_text.lower()] = self._fill_by_label(page, label_text, value)

        # Work auth / sponsorship
        self._fill_by_label_select(page, "authorized", "Yes" if info.get("work_authorization") else "No", status)
        self._fill_by_label_select(page, "sponsorship", "No" if not info.get("requires_sponsorship") else "Yes", status)

        return status

    def upload_resume(self, page: Page, pdf_path: str) -> bool:
        selectors = [
            'input[type="file"][name*="resume" i]',
            'input[type="file"][name*="cv" i]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self._safe_upload(page, sel, pdf_path):
                print(f"  [UPLOAD] Resume uploaded via {sel}")
                return True
        print("  [WARN] Could not find resume upload field")
        return False

    def _fill_by_label(self, page: Page, label_text: str, value: str) -> str:
        """Find an input by its label text and fill it."""
        try:
            labels = page.query_selector_all(f'label:has-text("{label_text}")')
            for label in labels:
                input_id = label.get_attribute("for")
                if input_id:
                    el = page.query_selector(f"#{input_id}")
                    if el:
                        el.click()
                        el.fill(value)
                        return "filled"
                # Try sibling/child input
                inp = label.query_selector("input, textarea")
                if inp:
                    inp.click()
                    inp.fill(value)
                    return "filled"
            # Fallback: aria-label
            el = page.query_selector(f'input[aria-label*="{label_text}" i]')
            if el:
                el.click()
                el.fill(value)
                return "filled"
            return "not_found"
        except Exception:
            return "not_found"

    def _fill_by_label_select(self, page: Page, keyword: str, value: str, status: dict) -> None:
        """Find a select by label keyword and choose an option."""
        if not value:
            return
        try:
            labels = page.query_selector_all(f'label:has-text("{keyword}")')
            for label in labels:
                input_id = label.get_attribute("for")
                if input_id:
                    result = self._safe_select(page, f"#{input_id}", value, keyword)
                    if result == "filled":
                        status[keyword] = "filled"
                        return
            status[keyword] = "not_found"
        except Exception:
            status[keyword] = "not_found"
