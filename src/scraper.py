"""Scrape a job description from a URL using Playwright."""

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page

import config


def open_job_page(url: str) -> tuple[str, Page, BrowserContext, Browser]:
    """Open the job URL in a headful browser and extract JD text.

    Returns (jd_text, page, browser_context, browser).
    The caller is responsible for closing the browser when done.
    """
    pw = sync_playwright().start()
    browser = pw.chromium.launch(
        headless=config.PLAYWRIGHT_HEADLESS,
        slow_mo=config.PLAYWRIGHT_SLOW_MO,
    )
    context = browser.new_context(
        viewport={"width": 1280, "height": 900},
    )
    page = context.new_page()
    page.goto(url, timeout=config.BROWSER_TIMEOUT)
    page.wait_for_load_state("networkidle", timeout=config.BROWSER_TIMEOUT)

    # Extract visible text from the page body
    jd_text = page.inner_text("body")

    # Clean up: collapse whitespace runs but preserve paragraph breaks
    lines = []
    for line in jd_text.splitlines():
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    jd_text = "\n".join(lines)

    word_count = len(jd_text.split())
    print(f"[OK] Scraped JD ({word_count} words)")

    return jd_text, page, context, browser
