from research import build_questions, extract_job_sections


def test_extract_job_sections_finds_text_under_headings():
    text = """담당 업무\n데이터 파이프라인을 운영합니다.\n자격 요건\nPython과 SQL 경험\n우대 사항\n클라우드 경험"""
    sections = extract_job_sections(text)
    assert "데이터 파이프라인" in sections["responsibilities"]
    assert "Python" in sections["requirements"]


def test_build_questions_uses_role_keywords_without_empty_questions():
    questions = build_questions("데이터 분석가", "Python SQL 데이터 분석 A/B 테스트")
    assert any("SQL" in question for question in questions)
    assert all(question.strip() for question in questions)
