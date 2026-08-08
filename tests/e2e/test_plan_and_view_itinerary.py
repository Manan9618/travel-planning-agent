"""Golden path: type a trip request, watch it plan, see a real itinerary
render across all four canvas tabs. Runs against the stub-tool-backed
backend (see stub_backend.py) so it's fast, free, and deterministic.
"""

from __future__ import annotations

from playwright.sync_api import expect


def test_full_planning_journey_renders_itinerary_across_all_tabs(page, app_url):
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    failed_requests = []
    page.on("requestfailed", lambda req: failed_requests.append(req.url))

    page.goto(app_url)
    expect(page.get_by_placeholder("Describe your trip…")).to_be_visible()

    page.get_by_placeholder("Describe your trip…").fill("5 days in Paris, I love art and museums")
    page.get_by_placeholder("Describe your trip…").press("Enter")

    expect(page.get_by_text("Day 1")).to_be_visible(timeout=30000)
    expect(page.get_by_role("button", name="Export PDF")).to_be_enabled(timeout=15000)

    # Itinerary tab: real day cards from the stub itinerary
    expect(page.get_by_text("Louvre Museum")).to_be_visible()

    # Map tab
    page.get_by_role("tab", name="Map").click()
    expect(page.locator(".leaflet-container")).to_be_visible(timeout=10000)

    # Budget tab
    page.get_by_role("tab", name="Budget").click()
    expect(page.get_by_text("Budget", exact=False).first).to_be_visible()

    # PDF preview tab
    page.get_by_role("tab", name="PDF preview").click()
    expect(page.get_by_title("Itinerary PDF preview")).to_be_visible(timeout=10000)

    # Third-party map tiles (no internet access in this sandbox) and the PDF
    # iframe's blob: URL (a known Playwright false-positive on blob
    # navigations, not a real failure) are expected noise, not app bugs —
    # only requests to our own backend/frontend indicate a real problem.
    real_failures = [
        url
        for url in failed_requests
        if "tile.openstreetmap.org" not in url and not url.startswith("blob:")
    ]
    assert console_errors == [], f"console errors: {console_errors}"
    assert real_failures == [], f"failed requests: {real_failures}"
