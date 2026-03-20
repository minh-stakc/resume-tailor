"""Generic ATS adapter — uses Claude vision to analyze form screenshots and fill fields."""

import base64
import json
import time

from playwright.sync_api import Page
import anthropic

import config
from src.ats.base import ATSAdapter

# Maps Claude-identified field purposes to applicant_info keys
_FIELD_KEY_MAP = {
    "first_name": "first_name",
    "first name": "first_name",
    "given_name": "first_name",
    "last_name": "last_name",
    "last name": "last_name",
    "family_name": "last_name",
    "surname": "last_name",
    "full_name": "full_name",
    "full name": "full_name",
    "name": "full_name",
    "email": "email",
    "email_address": "email",
    "phone": "phone",
    "phone_number": "phone",
    "telephone": "phone",
    "linkedin": "linkedin",
    "linkedin_url": "linkedin",
    "github": "github",
    "github_url": "github",
    "website": "github",
    "portfolio": "github",
    "school": "school",
    "university": "school",
    "college": "school",
    "institution": "school",
    "degree": "degree",
    "gpa": "gpa",
    "city": "city",
    "state": "state",
    "country": "country",
    "address": "street",
    "zip": "zip",
    "postal_code": "zip",
    "how_did_you_hear": "how_did_you_hear",
    "source": "how_did_you_hear",
    "referral": "how_did_you_hear",
}

_BOOL_FIELD_MAP = {
    "work_authorization": ("work_authorization", True),
    "authorized_to_work": ("work_authorization", True),
    "legally_authorized": ("work_authorization", True),
    "sponsorship": ("requires_sponsorship", False),
    "visa_sponsorship": ("requires_sponsorship", False),
    "require_sponsorship": ("requires_sponsorship", False),
}


class GenericAdapter(ATSAdapter):

    @staticmethod
    def matches(url: str) -> bool:
        return True  # Catch-all fallback

    def extract_jd(self, page: Page) -> str:
        return page.inner_text("body")

    def navigate_to_apply(self, page: Page) -> None:
        # Try common apply button patterns
        for sel in [
            'a[href*="apply" i]',
            'button:has-text("Apply")',
            'a:has-text("Apply")',
            'input[type="submit"][value*="Apply" i]',
        ]:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_load_state("networkidle", timeout=15000)
                return

    def fill_form(self, page: Page, info: dict) -> dict:
        """Screenshot the form, ask Claude to identify fields, then fill them."""
        status = {}

        # Take screenshot
        screenshot_bytes = page.screenshot(full_page=True)
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

        # Ask Claude to identify form fields
        fields = self._identify_fields(screenshot_b64)

        if not fields:
            print("  [WARN] Claude could not identify form fields")
            return status

        print(f"  [GENERIC] Identified {len(fields)} form fields via Claude vision")

        for field_info in fields:
            label = field_info.get("label", "").lower().strip()
            selector = field_info.get("selector", "")
            field_type = field_info.get("type", "text")

            if not selector:
                continue

            # Map label to applicant info key
            value = self._resolve_value(label, field_type, info)
            if value is None:
                status[label] = "skipped"
                continue

            if field_type == "file":
                # Skip — resume upload handled separately
                continue
            elif field_type == "select":
                status[label] = self._safe_select(page, selector, str(value), label)
            elif field_type in ("checkbox", "radio"):
                status[label] = self._safe_check(page, selector, bool(value))
            else:
                status[label] = self._safe_fill(page, selector, str(value), label)

        return status

    def upload_resume(self, page: Page, pdf_path: str) -> bool:
        # Try common file input selectors
        selectors = [
            'input[type="file"][name*="resume" i]',
            'input[type="file"][name*="cv" i]',
            'input[type="file"][accept*="pdf" i]',
            'input[type="file"]',
        ]
        for sel in selectors:
            if self._safe_upload(page, sel, pdf_path):
                print(f"  [UPLOAD] Resume uploaded via {sel}")
                return True

        # If no standard file input, try drag-drop zones
        drop_zone = page.query_selector('[class*="drop" i], [class*="upload" i]')
        if drop_zone:
            # Look for hidden file input inside
            hidden_input = drop_zone.query_selector('input[type="file"]')
            if hidden_input:
                hidden_input.set_input_files(pdf_path)
                print("  [UPLOAD] Resume uploaded via drop zone hidden input")
                return True

        print("  [WARN] Could not find resume upload field")
        return False

    def _identify_fields(self, screenshot_b64: str) -> list[dict]:
        """Ask Claude to identify form fields from a screenshot."""
        client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

        prompt = """Analyze this job application form screenshot. For each fillable form field visible, return a JSON array where each element has:
- "label": the field label or placeholder text (e.g., "First Name", "Email")
- "type": one of "text", "email", "tel", "select", "checkbox", "radio", "file", "textarea"
- "selector": the most likely CSS selector to target this field (use aria-label, name, id, placeholder, or type attributes)

Focus on: name fields, email, phone, LinkedIn, GitHub/website, school, degree, GPA, work authorization, sponsorship, how did you hear about us, and resume/CV upload.

Return ONLY the JSON array, no other text."""

        try:
            response = client.messages.create(
                model=config.MODEL,
                max_tokens=2000,
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
            text = response.content[0].text.strip()
            # Extract JSON from response (handle markdown code blocks)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except Exception as e:
            print(f"  [WARN] Claude vision field identification failed: {e}")
            return []

    def _resolve_value(self, label: str, field_type: str, info: dict):
        """Map a field label to the corresponding value from applicant info."""
        # Direct match
        for keyword, key in _FIELD_KEY_MAP.items():
            if keyword in label:
                return info.get(key, "")

        # Boolean fields
        for keyword, (key, default_yes) in _BOOL_FIELD_MAP.items():
            if keyword in label.replace(" ", "_"):
                val = info.get(key, default_yes)
                if field_type in ("checkbox", "radio"):
                    return val
                return "Yes" if val else "No"

        return None
