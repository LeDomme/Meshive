from fastapi.testclient import TestClient

from meshive.main import app


def test_health() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["version"] == "1.3.0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_cross_site_state_changing_api_request_is_rejected() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Cross-site state-changing requests are not allowed"
    )
    assert response.headers["x-content-type-options"] == "nosniff"

    fetch_metadata_response = client.post(
        "/api/auth/logout",
        headers={"Sec-Fetch-Site": "cross-site"},
    )
    assert fetch_metadata_response.status_code == 403


def test_same_origin_and_non_browser_requests_remain_allowed() -> None:
    client = TestClient(app, base_url="https://meshive.example")

    same_origin = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://meshive.example"},
    )
    no_browser_headers = client.post("/api/auth/logout")

    assert same_origin.status_code == 204
    assert no_browser_headers.status_code == 204


def test_unknown_api_route_returns_json_404() -> None:
    response = TestClient(app).get("/api/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "API endpoint not found"}
    assert response.headers["x-content-type-options"] == "nosniff"
