import research


def test_parse_brief_response_extracts_json_after_cli_metadata():
    response = 'session_id: abc123\n{"executive_summary":"핵심 요약","company_context":["사업"],"role_fit":["역량"],"must_know":["지표"],"answer_playbook":[],"story_prompts":[],"questions_for_interviewer":[],"day_before_checklist":[],"cautions":[],"sources_used":[]}'

    brief = research.parse_brief_response(response)

    assert brief["executive_summary"] == "핵심 요약"
    assert brief["company_context"] == ["사업"]


def test_build_report_includes_generated_brief_only_when_requested(monkeypatch):
    monkeypatch.setattr(research, "search_public_sources", lambda _query: [])
    monkeypatch.setattr(
        research,
        "generate_interview_brief",
        lambda company, role, job_text, sources: {"executive_summary": f"{company} {role} 브리핑"},
    )

    report = research.build_report("테스트회사", "데이터 분석가", generate_brief=True)

    assert report["interview_brief"]["executive_summary"] == "테스트회사 데이터 분석가 브리핑"


def test_build_report_does_not_call_brief_generator_by_default(monkeypatch):
    monkeypatch.setattr(research, "search_public_sources", lambda _query: [])
    monkeypatch.setattr(research, "generate_interview_brief", lambda *_args: (_ for _ in ()).throw(AssertionError("must not run")))

    report = research.build_report("테스트회사", "데이터 분석가")

    assert report["interview_brief"] is None
