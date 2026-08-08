"""Regression coverage for the real /refine bug found via live use this
session: clicking a refinement chip whose text has no destination in it
("more outdoor activities") used to either crash ("Load failed" in the UI)
or silently replace the trip's real destination. Formalizes that manual
repro as a permanent E2E test.
"""

from __future__ import annotations

from playwright.sync_api import expect


def test_refinement_chip_does_not_crash_and_keeps_destination(page, app_url):
    page.goto(app_url)
    page.get_by_placeholder("Describe your trip…").fill("5 days in Paris, I love art and museums")
    page.get_by_placeholder("Describe your trip…").press("Enter")

    expect(page.get_by_text("Day 1")).to_be_visible(timeout=30000)
    expect(page.get_by_text("Paris", exact=False).first).to_be_visible()

    page.get_by_role("button", name="More outdoor activities").click()

    # The bug this covers: this used to render "Load failed" here instead.
    expect(page.get_by_text("Load failed")).not_to_be_visible()
    expect(page.get_by_text("Something went wrong", exact=False)).not_to_be_visible()

    # New turn completes and the trip is still Paris, not clobbered by a
    # destination-less refinement parse.
    expect(page.get_by_text("Day 1")).to_be_visible(timeout=30000)
    expect(page.get_by_text("Paris", exact=False).first).to_be_visible()
