from tests.api.conftest import wait_until_terminal


def test_export_pdf_for_unknown_session_returns_404(client):
    resp = client.get("/export/does-not-exist/pdf")
    assert resp.status_code == 404


def test_export_map_for_unknown_session_returns_404(client):
    resp = client.get("/export/does-not-exist/map")
    assert resp.status_code == 404


def test_export_pdf_returns_the_generated_file(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    resp = client.get(f"/export/{session_id}/pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content[:5] == b"%PDF-"


def test_export_map_returns_html(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    resp = client.get(f"/export/{session_id}/map")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "leaflet" in resp.text.lower()


def test_export_calendar_for_unknown_session_returns_404(client):
    resp = client.get("/export/does-not-exist/calendar")
    assert resp.status_code == 404


def test_export_calendar_returns_a_valid_ics_file(client):
    session_id = client.post("/plan", json={"raw_text": "5 days in Paris"}).json()["session_id"]
    wait_until_terminal(client, session_id)

    resp = client.get(f"/export/{session_id}/calendar")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/calendar; charset=utf-8"
    assert resp.text.startswith("BEGIN:VCALENDAR")
    assert f'filename="itinerary-{session_id}.ics"' in resp.headers["content-disposition"]
