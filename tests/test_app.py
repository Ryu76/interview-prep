from io import BytesIO

import fitz

from app import app


def test_health_page_loads():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200


def test_api_accepts_form_without_url(monkeypatch):
    captured = {}

    def fake_report(company, role, url, uploaded_text="", generate_brief=False):
        captured["generate_brief"] = generate_brief
        return {"company": company, "role": role}

    monkeypatch.setattr("app.build_report", fake_report)
    client = app.test_client()
    response = client.post("/api/research", data={"company": "카카오", "role": "기획"})
    assert response.status_code == 200
    assert response.get_json()["company"] == "카카오"
    assert captured["generate_brief"] is True


def test_api_extracts_text_from_optional_pdf(monkeypatch):
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Python SQL required for data analysis")
    pdf_bytes = document.tobytes()
    document.close()

    captured = {}

    def fake_report(company, role, url, uploaded_text="", generate_brief=False):
        captured["uploaded_text"] = uploaded_text
        return {"company": company, "role": role}

    monkeypatch.setattr("app.build_report", fake_report)
    client = app.test_client()
    response = client.post(
        "/api/research",
        data={
            "company": "카카오",
            "role": "데이터 분석가",
            "jobFile": (BytesIO(pdf_bytes), "job-posting.pdf"),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert "Python SQL" in captured["uploaded_text"]


def test_api_rejects_unsupported_upload(monkeypatch):
    monkeypatch.setattr("app.build_report", lambda *args: {})
    client = app.test_client()
    response = client.post(
        "/api/research",
        data={
            "company": "카카오",
            "role": "기획",
            "jobFile": (BytesIO(b"not a document"), "posting.txt"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "PDF" in response.get_json()["error"]
