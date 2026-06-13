"""
Browser-based end-to-end tests using Playwright.
Run with: uv run pytest tests/test_ui.py -v
Skip in CI without a browser: pytest -m "not ui"

The mock server is started once per session (live_url fixture in conftest.py).
All tests run against http://127.0.0.1:<port> with mock data (9 threads).
"""
import pytest
from playwright.sync_api import Page, expect

pytestmark = pytest.mark.ui


def _load(page: Page, live_url: str) -> None:
    """Navigate and wait until thread cards are visible."""
    page.goto(live_url)
    page.wait_for_selector(".thread-card", timeout=10_000)


# ── Page integrity ────────────────────────────────────────────────────────────

def test_page_loads_without_js_errors(page: Page, live_url: str):
    # pageerror captures uncaught JS exceptions; console "error" includes harmless
    # network failures (e.g. favicon 404) that are not JS bugs.
    errors = []
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    _load(page, live_url)
    assert errors == [], f"Uncaught JS exceptions on load: {errors}"
    expect(page).to_have_title("signalstripper")


def test_overview_stats_render(page: Page, live_url: str):
    _load(page, live_url)
    expect(page.locator(".stat-card")).to_have_count(4)
    # DB info header should contain schema version
    expect(page.locator("#db-info")).to_contain_text("schema v")


# ── Thread list ───────────────────────────────────────────────────────────────

def test_thread_cards_render(page: Page, live_url: str):
    _load(page, live_url)
    cards = page.locator(".thread-card")
    # Mock has 9 threads
    expect(cards).to_have_count(9)


def test_sort_by_name_reorders_cards(page: Page, live_url: str):
    _load(page, live_url)
    # Grab names before sort change
    names_before = page.locator(".thread-name").all_text_contents()
    page.select_option("#sort-by", "name")
    names_after = page.locator(".thread-name").all_text_contents()
    assert sorted(names_after) == names_after, "Cards should be alphabetically ordered after sort by name"
    # Sorted list should differ from size-sorted (mock data has varied sizes)
    assert names_before != names_after or names_before == sorted(names_before)


# ── Selection and tally ───────────────────────────────────────────────────────

def test_select_thread_updates_tally(page: Page, live_url: str):
    _load(page, live_url)
    assert page.locator("#tally-bytes").text_content() == "0 B"
    # Click the first thread card body to toggle its checkbox
    page.locator(".thread-card").first.click()
    tally = page.locator("#tally-bytes").text_content()
    assert tally != "0 B", f"Tally should update after selecting a thread, got {tally!r}"


def test_deselect_thread_resets_tally(page: Page, live_url: str):
    _load(page, live_url)
    card = page.locator(".thread-card").first
    card.click()                     # select
    assert page.locator("#tally-bytes").text_content() != "0 B"
    card.click()                     # deselect
    assert page.locator("#tally-bytes").text_content() == "0 B"


def test_select_all_selects_every_thread(page: Page, live_url: str):
    _load(page, live_url)
    page.click("#select-all")
    checked = page.locator(".thread-check:checked")
    total = page.locator(".thread-check")
    expect(checked).to_have_count(total.count())
    assert page.locator("#tally-bytes").text_content() != "0 B"


def test_date_range_inputs_appear_on_select(page: Page, live_url: str):
    _load(page, live_url)
    wrap = page.locator(".thread-card").first.locator(".date-range-wrap")
    # Before selection the date range is not visible
    assert not wrap.is_visible()
    page.locator(".thread-card").first.click()
    assert wrap.is_visible()


# ── Generate command ──────────────────────────────────────────────────────────

def test_generate_without_selection_shows_alert(page: Page, live_url: str):
    _load(page, live_url)
    page.once("dialog", lambda d: d.accept())
    page.click("#generate-btn")
    # Command output stays hidden
    expect(page.locator("#command-output")).to_have_class("command-output hidden")


def test_generate_command_visible_after_selection(page: Page, live_url: str):
    _load(page, live_url)
    page.locator(".thread-card").first.click()
    page.click("#generate-btn")
    output = page.locator("#command-output")
    expect(output).not_to_have_class("command-output hidden")
    text = output.text_content()
    assert "--replaceattachments" in text or "--croptothreads" in text


def test_copy_button_disabled_then_enabled(page: Page, live_url: str):
    _load(page, live_url)
    copy_btn = page.locator("#copy-btn")
    expect(copy_btn).to_be_disabled()
    page.locator(".thread-card").first.click()
    page.click("#generate-btn")
    expect(copy_btn).not_to_be_disabled()


def test_command_output_has_safety_comment(page: Page, live_url: str):
    _load(page, live_url)
    page.locator(".thread-card").first.click()
    page.click("#generate-btn")
    output = page.locator("#command-output")
    # Wait for the async fetch to complete and the hidden class to be removed
    expect(output).not_to_have_class("command-output hidden")
    assert "signalstripper never auto-runs" in output.text_content()
