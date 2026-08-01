from tests.api.conftest import StubParser, isolated_client, wait_until_terminal

LOW_BUDGET_PARSER = StubParser(budget_total=200)


def test_resume_unknown_session_returns_404(client):
    resp = client.post("/plan/does-not-exist/resume", json={"approved": True})
    assert resp.status_code == 404


def test_approving_resumes_and_completes_the_run(app_factory):
    with isolated_client(app_factory(parser=LOW_BUDGET_PARSER)) as client:
        session_id = client.post("/plan", json={"raw_text": "cheap trip"}).json()["session_id"]
        assert wait_until_terminal(client, session_id)["status"] == "awaiting_review"

        resp = client.post(f"/plan/{session_id}/resume", json={"approved": True})
        assert resp.status_code == 200
        assert resp.json() == {"session_id": session_id, "status": "running"}

        data = wait_until_terminal(client, session_id)
        assert data["status"] == "completed"
        assert "human_review" in data["completed_steps"]


def test_rejecting_resumes_and_records_an_error(app_factory):
    with isolated_client(app_factory(parser=LOW_BUDGET_PARSER)) as client:
        session_id = client.post("/plan", json={"raw_text": "cheap trip"}).json()["session_id"]
        assert wait_until_terminal(client, session_id)["status"] == "awaiting_review"

        client.post(f"/plan/{session_id}/resume", json={"approved": False})
        data = wait_until_terminal(client, session_id)
        assert data["status"] == "completed"
        assert any("did not approve" in e for e in data["errors"])


def test_resume_request_requires_approved_field(client):
    session_id = client.post("/plan", json={"raw_text": "trip"}).json()["session_id"]
    resp = client.post(f"/plan/{session_id}/resume", json={})
    assert resp.status_code == 422
