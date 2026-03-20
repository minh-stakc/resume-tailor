"""Lever ATS adapter — jobs.lever.co."""

import re
from playwright.sync_api import Page

from src.ats.base import ATSAdapter


class LeverAdapter(ATSAdapter):

    @staticmethod
    def matches(url: str) -> bool:
        return bool(re.search(r"lever\.co", url, re.IGNORECASE))

    def extract_jd(self, page: Page) -> str:
        for sel in [".posting-page", ".section-wrapper", '[class*="posting"]', "main"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text
        return page.inner_text("body")

    def navigate_to_apply(self, page: Page) -> None:
        # Lever often has "Apply for this job" button on the posting page
        apply_btn = page.query_selector(
            'a.postings-btn[href*="apply"], '
            'a[class*="apply"], '
            'button:has-text("Apply")'
        )
        if apply_btn:
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)

    def fill_form(self, page: Page, info: dict) -> dict:
        status = {}

        # Lever uses simple input names
        field_map = {
            "full_name": ('input[name="name"], input[placeholder*="name" i]', info.get("full_name", "")),
            "email": ('input[name="email"], input[type="email"]', info.get("email", "")),
            "phone": ('input[name="phone"], input[type="tel"]', info.get("phone", "")),
            "linkedin": ('input[name*="linkedin" i], input[name="urls[LinkedIn]"], input[placeholder*="linkedin" i]', info.get("linkedin", "")),
            "github": ('input[name*="github" i], input[name="urls[GitHub]"], input[placeholder*="github" i]', info.get("github", "")),
            "school": ('input[name*="school" i], input[name*="university" i]', info.get("school", "")),
        }

        for field, (selector, value) in field_map.items():
            status[field] = self._try_selectors(page, selector, value, field)

        # Additional custom questions — Lever shows them as labeled inputs
        self._fill_labeled_inputs(page, info, status)

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

    def _try_selectors(self, page: Page, combined_selector: str, value: str, field_name: str) -> str:
        if not value:
            return "skipped"
        for sel in combined_selector.split(", "):
            result = self._safe_fill(page, sel.strip(), str(value), field_name)
            if result == "filled":
                return "filled"
        return "not_found"

    def _fill_labeled_inputs(self, page: Page, info: dict, status: dict) -> None:
        """Try to fill Lever's custom question fields by label text matching."""
        label_map = {
            "authorization": "Yes" if info.get("work_authorization") else "No",
            "sponsorship": "No" if not info.get("requires_sponsorship") else "Yes",
            "gender": info.get("gender", ""),
            "race": info.get("race_ethnicity", ""),
            "ethnicity": info.get("race_ethnicity", ""),
            "veteran": "No" if not info.get("veteran_status") else "Yes",
            "disability": "No" if not info.get("disability_status") else "Yes",
        }
        for keyword, value in label_map.items():
            if not value:
                continue
            labels = page.query_selector_all(f'label:has-text("{keyword}")')
            for label in labels:
                input_id = label.get_attribute("for")
                if input_id:
                    el = page.query_selector(f"#{input_id}")
                    if el:
                        tag = el.evaluate("el => el.tagName.toLowerCase()")
                        if tag == "select":
                            self._safe_select(page, f"#{input_id}", value, keyword)
                        else:
                            self._safe_fill(page, f"#{input_id}", value, keyword)
                        status[keyword] = "filled"
                        break
