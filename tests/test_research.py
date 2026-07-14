from research import _parse_bing_results, _parse_naver_results, build_questions, build_report, extract_job_sections


def test_extract_job_sections_finds_text_under_headings():
    text = """담당 업무\n데이터 파이프라인을 운영합니다.\n자격 요건\nPython과 SQL 경험\n우대 사항\n클라우드 경험"""
    sections = extract_job_sections(text)
    assert "데이터 파이프라인" in sections["responsibilities"]
    assert "Python" in sections["requirements"]


def test_build_questions_uses_role_keywords_without_empty_questions():
    questions = build_questions("데이터 분석가", "Python SQL 데이터 분석 A/B 테스트")
    assert any("SQL" in question for question in questions)


def test_build_report_without_url_uses_role_as_research_context():
    report = build_report("테스트회사", "데이터 분석가", "")
    assert report["company"] == "테스트회사"
    assert report["job_sections"]["responsibilities"]
    assert report["questions"]


def test_parse_bing_results_returns_clean_result_links():
    html = """
    <li class="b_algo"><h2><a href="https://example.com/history">회사 연혁</a></h2><p>공식 회사 소개 자료</p></li>
    <li class="b_algo"><h2><a href="https://example.com/careers">채용 정보</a></h2><div class="b_caption"><p>지원 직무 안내</p></div></li>
    """

    results = _parse_bing_results(html, limit=3)

    assert results == [
        {"title": "회사 연혁", "url": "https://example.com/history", "snippet": "공식 회사 소개 자료"},
        {"title": "채용 정보", "url": "https://example.com/careers", "snippet": "지원 직무 안내"},
    ]


def test_parse_naver_results_uses_result_title_and_description():
    html = """
    <a href="https://jobs.example.com/123">Example Corp www.example.com 새 창 열림</a>
    <a href="https://jobs.example.com/123">데이터 분석가 채용 공고 새 창 열림</a>
    <a href="https://jobs.example.com/123">Python과 SQL 기반 지표 분석 및 실험 설계 업무를 담당합니다. 새 창 열림</a>
    <a href="https://help.naver.com/ignore">제외할 도움말</a>
    <a href="https://linkareer.com/123">링커리어 linkareer.com › activity 새 창 열림</a>
    """

    results = _parse_naver_results(html, limit=3)

    assert results == [{
        "title": "데이터 분석가 채용 공고",
        "url": "https://jobs.example.com/123",
        "snippet": "Python과 SQL 기반 지표 분석 및 실험 설계 업무를 담당합니다.",
    }]
