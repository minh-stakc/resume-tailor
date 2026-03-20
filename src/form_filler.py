"""Orchestrates browser-based application form filling."""

from playwright.sync_api import Page, BrowserContext, Browser

from src.ats.base import ATSAdapter


def fill_application(
    page: Page,
    context: BrowserContext,
    browser: Browser,
    adapter: ATSAdapter,
    applicant_info: dict,
    pdf_path: str,
) -> None:
    """Fill the application form, upload resume, and pause for review.

    The browser stays open for the user to review and manually submit.
    """
    # Step 1: Navigate to application form
    print("[*] Navigating to application form...")
    adapter.navigate_to_apply(page)

    # Step 2: Fill form fields
    print("[*] Filling form fields...")
    status = adapter.fill_form(page, applicant_info)

    # Step 3: Upload resume
    print("[*] Uploading resume...")
    uploaded = adapter.upload_resume(page, pdf_path)

    # Step 4: Print summary
    print("\n" + "=" * 50)
    print("  FORM FILL SUMMARY")
    print("=" * 50)

    filled = [k for k, v in status.items() if v == "filled"]
    skipped = [k for k, v in status.items() if v == "skipped"]
    not_found = [k for k, v in status.items() if v == "not_found"]

    if filled:
        print(f"  Filled:     {', '.join(filled)}")
    if skipped:
        print(f"  Skipped:    {', '.join(skipped)}")
    if not_found:
        print(f"  Not found:  {', '.join(not_found)}")
    print(f"  Resume:     {'uploaded' if uploaded else 'FAILED'}")
    print("=" * 50)

    # Step 5: Pause for review
    print("\nForm filled. Review in the browser and submit manually.")
    print("(Check all fields are correct before submitting.)")
    input("\nPress Enter to close the browser...")

    # Cleanup
    context.close()
    browser.close()
