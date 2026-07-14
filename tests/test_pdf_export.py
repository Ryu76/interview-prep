from io import BytesIO

import fitz

from app import app


def sample_report():
    return {
        "company": "카카오",
        "role": "데이터 분석가",
        "notice": "중요한 사실은 원문에서 확인하세요.",
        "job_sections": {
            "responsibilities": "사용자 행동 데이터를 분석합니다.",
            "requirements": "SQL과 데이터 분석 역량",
            "preferred": "실험 설계 경험",
        },
        "interview_brief": {
            "executive_summary": "문제 정의부터 의사결정까지 연결하는 역량을 보여주세요.",
            "company_context": ["다양한 서비스를 운영합니다."],
            "role_fit": ["SQL 경험을 실제 성과와 연결합니다."],
            "must_know": ["리텐션과 전환율"],
            "answer_playbook": [{
                "question": "어려운 분석 문제를 해결한 경험은?",
                "interviewer_intent": "문제 해결 과정을 확인합니다.",
                "answer_structure": "상황, 행동, 결과 순으로 답합니다.",
                "evidence_to_prepare": "본인의 기여도와 성과 수치",
            }],
            "story_prompts": ["실패를 학습으로 전환한 경험"],
            "questions_for_interviewer": ["입사 후 첫 과제는 무엇인가요?"],
            "day_before_checklist": ["공고 원문 다시 확인"],
            "cautions": ["계열사 자료를 본사 정보로 단정하지 않습니다."],
            "sources_used": ["https://www.kakaocorp.com/"],
        },
        "sources": {},
    }


def test_pdf_export_returns_openable_pdf_with_korean_text():
    client = app.test_client()

    response = client.post("/api/export-pdf", json=sample_report())

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data.startswith(b"%PDF")
    assert len(response.data) < 5 * 1024 * 1024
    assert "attachment" in response.headers["Content-Disposition"]
    document = fitz.open(stream=BytesIO(response.data), filetype="pdf")
    text = "\n".join(page.get_text() for page in document)
    document.close()
    assert "카카오" in text
    assert "면접 완성 브리핑" in text
    assert "어려운 분석 문제" in text


def test_pdf_export_rejects_missing_report_fields():
    client = app.test_client()

    response = client.post("/api/export-pdf", json={"company": "카카오"})

    assert response.status_code == 400
    assert "회사명" in response.get_json()["error"]


def test_result_page_contains_pdf_download_control():
    client = app.test_client()

    response = client.get("/")

    assert response.status_code == 200
    assert b'id="pdf-download"' in response.data
    assert b"/api/export-pdf" in response.data
