from app import app


def test_health_page_loads():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert "면접" in response.get_data(as_text=True)
