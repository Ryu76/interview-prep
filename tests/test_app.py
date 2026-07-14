from app import app


def test_health_page_loads():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_api_accepts_form_without_url(monkeypatch):
    monkeypatch.setattr("app.build_report", lambda company, role, url, uploaded_text="": {"company": company, "role": role})
    client = app.test_client()
    response = client.post("/api/research", data={"company": "카카오", "role": "기획"})
    assert response.status_code == 200
    assert response.get_json()["company"] == "카카오"
