import research
from app import app


def test_parse_topics_accepts_commas_newlines_and_removes_duplicates():
    topics = research.parse_topics("웹 개발, 스프링 백엔드\n장고 백엔드, React, React, 정보처리기사")

    assert topics == ["웹 개발", "스프링 백엔드", "장고 백엔드", "React", "정보처리기사"]


def test_build_report_uses_selected_topics_for_research_questions_and_ai(monkeypatch):
    queries = []
    generated = {}

    def fake_search(query):
        queries.append(query)
        return []

    def fake_brief(company, role, job_text, sources, topics):
        generated["topics"] = topics
        return {"executive_summary": "맞춤 브리핑"}

    monkeypatch.setattr(research, "search_public_sources", fake_search)
    monkeypatch.setattr(research, "generate_interview_brief", fake_brief)

    report = research.build_report(
        "테스트회사",
        "개발자",
        topics_text="스프링 백엔드, React, 정보처리기사",
        generate_brief=True,
    )

    assert report["selected_topics"] == ["스프링 백엔드", "React", "정보처리기사"]
    assert generated["topics"] == ["스프링 백엔드", "React", "정보처리기사"]
    assert any("스프링 백엔드" in query for query in queries)
    assert any("React" in question for question in report["questions"])


def test_api_passes_optional_topics_to_report_builder(monkeypatch):
    captured = {}

    def fake_report(company, role, url, uploaded_text="", topics_text="", generate_brief=False):
        captured["topics"] = topics_text
        return {"company": company, "role": role}

    monkeypatch.setattr("app.build_report", fake_report)
    response = app.test_client().post(
        "/api/research",
        data={"company": "카카오", "role": "개발자", "topics": "장고 백엔드, Vue, 정보처리기사"},
    )

    assert response.status_code == 200
    assert captured["topics"] == "장고 백엔드, Vue, 정보처리기사"


def test_page_contains_free_form_topics_input():
    response = app.test_client().get("/")

    assert response.status_code == 200
    assert b'name="topics"' in response.data
    page = response.get_data(as_text=True)
    assert "정보처리기사" in page
    assert 'name="company" value="서울물재생시설공단"' in page
    assert 'placeholder="예: 카카오"' not in page
    assert 'name="role" value="전산직"' in page
    assert page.count("(필수)") == 2
