"""Greenhouse ATS adapter — boards.greenhouse.io / job-boards.greenhouse.io."""

import re
from playwright.sync_api import Page

from src.ats.base import ATSAdapter


class GreenhouseAdapter(ATSAdapter):

    @staticmethod
    def matches(url: str) -> bool:
        return bool(re.search(r"greenhouse\.io", url, re.IGNORECASE))

    def extract_jd(self, page: Page) -> str:
        # Greenhouse puts the JD in #content or .job-post
        for sel in ["#content", ".job-post", '[class*="job"]', "main", "body"]:
            el = page.query_selector(sel)
            if el:
                text = el.inner_text().strip()
                if len(text) > 200:
                    return text
        return page.inner_text("body")

    def navigate_to_apply(self, page: Page) -> None:
        # Greenhouse embeds the form on the same page, or has an "Apply" link
        apply_btn = page.query_selector('a[href*="apply"], a[href*="#app"], button:has-text("Apply")')
        if apply_btn:
            apply_btn.click()
            page.wait_for_load_state("networkidle", timeout=15000)

    def fill_form(self, page: Page, info: dict) -> dict:
        status = {}

        # Standard Greenhouse field names
        field_map = {
            "first_name": ('input[name="job_application[first_name]"], '
                           'input[id*="first_name"], '
                           'input[autocomplete="given-name"]'),
            "last_name": ('input[name="job_application[last_name]"], '
                          'input[id*="last_name"], '
                          'input[autocomplete="family-name"]'),
            "email": ('input[name="job_application[email]"], '
                      'input[id*="email"], '
                      'input[type="email"]'),
            "phone": ('input[name="job_application[phone]"], '
                      'input[id*="phone"], '
                      'input[type="tel"]'),
            "linkedin": ('input[name*="linkedin" i], '
                         'input[id*="linkedin" i], '
                         'input[placeholder*="linkedin" i]'),
            "github": ('input[name*="github" i], '
                       'input[id*="github" i], '
                       'input[placeholder*="github" i], '
                       'input[name*="website" i]'),
        }

        for field, selector in field_map.items():
            value = info.get(field, "")
            status[field] = self._try_selectors(page, selector, value, field)

        # School / education fields (if present)
        school_sel = 'input[name*="school" i], input[id*="school" i], input[placeholder*="school" i], input[placeholder*="university" i]'
        status["school"] = self._try_selectors(page, school_sel, info.get("school", ""), "school")

        degree_sel = 'input[name*="degree" i], input[id*="degree" i], select[name*="degree" i]'
        status["degree"] = self._try_selectors(page, degree_sel, info.get("degree", ""), "degree")

        gpa_sel = 'input[name*="gpa" i], input[id*="gpa" i], input[placeholder*="gpa" i]'
        status["gpa"] = self._try_selectors(page, gpa_sel, info.get("gpa", ""), "gpa")

        # Work authorization (look for Yes/No radio or select)
        self._handle_work_auth(page, info, status)

        # How did you hear about us
        hear_sel = ('select[name*="hear" i], select[id*="hear" i], '
                    'select[name*="source" i], select[id*="source" i]')
        status["how_did_you_hear"] = self._safe_select(
            page, hear_sel, info.get("how_did_you_hear", ""), "how_did_you_hear"
        )

        return status

    def upload_resume(self, page: Page, pdf_path: str) -> bool:
        # Greenhouse resume upload — look for file input in resume section
        selectors = [
            'input[type="file"][name*="resume" i]',
            'input[type="file"][id*="resume" i]',
            'input[type="file"][name*="cv" i]',
            'input[type="file"]',  # fallback: first file input
        ]
        for sel in selectors:
            if self._safe_upload(page, sel, pdf_path):
                print(f"  [UPLOAD] Resume uploaded via {sel}")
                return True
        print("  [WARN] Could not find resume upload field")
        return False

    # ── Internal helpers ─────────────────────────────────────

    def _try_selectors(self, page: Page, combined_selector: str, value: str, field_name: str) -> str:
        """Try a comma-separated list of selectors, return first that works."""
        if not value:
            return "skipped"
        for sel in combined_selector.split(", "):
            result = self._safe_fill(page, sel.strip(), str(value), field_name)
            if result == "filled":
                return "filled"
        return "not_found"

    def _handle_work_auth(self, page: Page, info: dict, status: dict) -> None:
        """Handle work authorization radio buttons or selects."""
        auth_value = "Yes" if info.get("work_authorization", True) else "No"
        sponsor_value = "Yes" if info.get("requires_sponsorship", False) else "No"

        # Try radio buttons
        for label_text, value in [("authorized", auth_value), ("sponsorship", sponsor_value)]:
            radios = page.query_selector_all(f'label:has-text("{label_text}")')
            for radio_label in radios:
                # Find the associated radio input
                parent = radio_label.evaluate_handle("el => el.closest('.field') || el.parentElement")
                if parent:
                    yes_radio = parent.as_element().query_selector(f'input[type="radio"][value="{value}"], input[type="radio"][value="{value.lower()}"]')
                    if yes_radio:
                        yes_radio.click()
                        status[label_text] = "filled"
                        break
