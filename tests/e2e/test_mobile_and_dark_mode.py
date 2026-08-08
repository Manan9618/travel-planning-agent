"""Mobile viewport (chat/canvas toggle) and dark mode — verified in a real
browser, not just assumed from the CSS, matching how Week 16 was originally
live-tested by hand.
"""

import re

from playwright.sync_api import expect


def test_dark_mode_toggle_changes_root_theme(page, app_url):
    page.goto(app_url)
    html = page.locator("html")
    expect(html).not_to_have_class(re.compile(r"\bdark\b"))

    page.get_by_role("button", name="Switch to dark mode").click()
    expect(html).to_have_class(re.compile(r"\bdark\b"), timeout=5000)


def test_mobile_viewport_toggles_between_chat_and_canvas(page, app_url):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(app_url)

    page.get_by_placeholder("Describe your trip…").fill("5 days in Paris, I love art and museums")
    page.get_by_placeholder("Describe your trip…").press("Enter")
    # "Day 1" itself lives in the canvas, which is hidden behind the chat
    # view by default on mobile - wait on a chat-rail-visible completion
    # signal instead of the (currently offscreen) itinerary content.
    expect(page.get_by_role("button", name="View itinerary")).to_be_visible(timeout=30000)

    # Canvas is hidden until the mobile toggle is used
    expect(page.get_by_role("tab", name="Itinerary")).to_be_hidden()

    page.get_by_role("button", name="Itinerary", exact=True).click()
    expect(page.get_by_role("tab", name="Itinerary")).to_be_visible()
    expect(page.get_by_text("Day 1")).to_be_visible()

    page.get_by_role("button", name="Chat", exact=True).click()
    expect(page.get_by_placeholder("Refine your trip…")).to_be_visible()
