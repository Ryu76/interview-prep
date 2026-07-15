import sqlite3

import pytest

from app import app


@pytest.fixture()
def client(tmp_path):
    app.config.update(TESTING=True, INTERVIEW_DATABASE=str(tmp_path / "interviews.sqlite3"))
    with app.test_client() as client:
        yield client


def valid_settings(**overrides):
    data = {
        "company": "누스리서치",
        "role": "백엔드 개발자",
        "experienceLevel": "경력",
        "interviewType": "직무",
        "difficulty": "보통",
        "questionCount": 3,
        "jobPosting": "Python API와 SQLite 설계 역량",
        "resume": "결제 API 개선 경험",
    }
    data.update(overrides)
    return data


def access_headers(started):
    return {"X-Interview-Token": started["accessToken"]}


def answer_current(client, started, answer):
    session = client.get(f'/api/interviews/{started["id"]}', headers=access_headers(started)).get_json()
    return client.post(
        f'/api/interviews/{started["id"]}/answers',
        headers=access_headers(started),
        json={"questionId": session["currentQuestion"]["id"], "answer": answer},
    )


def test_start_validates_settings_and_question_count(client):
    response = client.post("/api/interviews", json=valid_settings(questionCount=2))
    assert response.status_code == 400
    assert "3~10" in response.get_json()["error"]

    response = client.post("/api/interviews", json=valid_settings(interviewType="코딩"))
    assert response.status_code == 400
    assert "면접 유형" in response.get_json()["error"]


def test_start_persists_session_and_returns_first_contextual_question(client):
    response = client.post("/api/interviews", json=valid_settings())
    assert response.status_code == 201
    body = response.get_json()
    assert body["status"] == "in_progress"
    assert len(body["accessToken"]) >= 32
    assert body["settings"]["company"] == "누스리서치"
    assert body["currentQuestion"]["sequence"] == 1
    assert "백엔드 개발자" in body["currentQuestion"]["text"]

    fetched = client.get(f'/api/interviews/{body["id"]}', headers=access_headers(body))
    assert fetched.status_code == 200
    assert fetched.get_json()["currentQuestion"] == body["currentQuestion"]


def test_vague_answer_creates_adaptive_follow_up_and_evaluation(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    response = answer_current(client, started, "프로젝트를 열심히 해서 개선했습니다.")
    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "in_progress"
    assert body["nextQuestion"]["kind"] == "follow_up"
    assert any(word in body["nextQuestion"]["text"] for word in ("수치", "근거", "역할"))
    evaluation = body["evaluation"]
    assert set(evaluation["scores"]) == {"questionUnderstanding", "specificity", "structure", "jobRelevance", "companyFit"}
    assert all(1 <= score <= 5 for score in evaluation["scores"].values())
    assert "프로젝트를 열심히" in evaluation["evidenceQuote"]
    assert evaluation["strengths"] and evaluation["improvements"]
    assert "[본인의 실제" in evaluation["improvedExample"]
    assert "결제 API" not in evaluation["improvedExample"]


def test_specific_answer_advances_to_base_question(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    response = answer_current(client, started, "제가 API 담당자로서 로그를 분석했고 캐시를 적용해 응답 시간을 30% 줄였습니다.")
    body = response.get_json()
    assert body["nextQuestion"]["kind"] == "base"
    assert body["nextQuestion"]["sequence"] == 2


def test_completes_at_requested_count_and_result_is_persistent(client):
    started = client.post("/api/interviews", json=valid_settings(questionCount=3)).get_json()
    for _ in range(3):
        response = answer_current(client, started, "제가 담당자로서 고객 로그를 분석해 API 오류를 20% 줄였습니다.")
        assert response.status_code == 200
    completed = response.get_json()
    assert completed["status"] == "completed"
    assert completed["nextQuestion"] is None

    result = client.get(f'/api/interviews/{started["id"]}/result', headers=access_headers(started))
    assert result.status_code == 200
    report = result.get_json()
    assert report["status"] == "completed"
    assert len(report["questions"]) == 3
    assert len(report["answers"]) == 3
    assert set(report["overallScores"]) == {"questionUnderstanding", "specificity", "structure", "jobRelevance", "companyFit"}

    rejected = client.post(
        f'/api/interviews/{started["id"]}/answers', headers=access_headers(started),
        json={"questionId": completed.get("questionId", 1), "answer": "추가 답변"},
    )
    assert rejected.status_code == 409


def test_rejects_blank_answer_and_unknown_session(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    current = started["currentQuestion"]["id"]
    response = client.post(
        f'/api/interviews/{started["id"]}/answers', headers=access_headers(started),
        json={"questionId": current, "answer": "   "},
    )
    assert response.status_code == 400
    assert client.get("/api/interviews/not-found", headers={"X-Interview-Token": "x" * 32}).status_code == 404


def test_sqlite_schema_contains_session_question_answer_and_evaluation(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    answer_current(client, started, "제가 담당자로 API 장애를 분석해 오류를 20% 줄였습니다.")
    connection = sqlite3.connect(app.config["INTERVIEW_DATABASE"])
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    connection.close()
    assert {"interview_sessions", "interview_questions", "interview_answers", "interview_evaluations"} <= tables


def test_page_has_interview_setup_progress_result_and_safe_rendering(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="interview-form"' in html
    assert 'id="interview-progress"' in html
    assert 'id="interview-result"' in html
    assert "textContent" in html
    assert "innerHTML=answer" not in html
    assert "localStorage" in html
    css = client.get("/static/style.css").get_data(as_text=True)
    assert "[hidden]" in css and "!important" in css


def test_result_is_unavailable_until_interview_is_completed(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    response = client.get(f'/api/interviews/{started["id"]}/result', headers=access_headers(started))
    assert response.status_code == 409
    assert "완료" in response.get_json()["error"]


def test_rejects_overlong_company_and_role(client):
    assert client.post("/api/interviews", json=valid_settings(company="가" * 101)).status_code == 400
    assert client.post("/api/interviews", json=valid_settings(role="나" * 101)).status_code == 400


def test_difficulty_changes_the_questioning_style(client):
    easy = client.post("/api/interviews", json=valid_settings(difficulty="쉬움")).get_json()
    hard = client.post("/api/interviews", json=valid_settings(difficulty="어려움")).get_json()
    assert easy["currentQuestion"]["text"] != hard["currentQuestion"]["text"]
    assert any(word in hard["currentQuestion"]["text"] for word in ("대안", "한계", "반론", "위험"))


def test_experience_level_changes_the_questioning_context(client):
    junior = client.post("/api/interviews", json=valid_settings(experienceLevel="신입")).get_json()
    senior = client.post("/api/interviews", json=valid_settings(experienceLevel="경력")).get_json()
    assert junior["currentQuestion"]["text"] != senior["currentQuestion"]["text"]
    assert "신입" in junior["currentQuestion"]["text"]
    assert "경력" in senior["currentQuestion"]["text"]


def test_rejects_non_object_non_finite_and_fractional_json(client):
    assert client.post("/api/interviews", json=[1]).status_code == 400
    assert client.post("/api/interviews", data='{"questionCount": Infinity}', content_type="application/json").status_code == 400
    assert client.post("/api/interviews", json=valid_settings(questionCount=3.9)).status_code == 400

    started = client.post("/api/interviews", json=valid_settings()).get_json()
    response = client.post(
        f'/api/interviews/{started["id"]}/answers', headers=access_headers(started), json=["answer"]
    )
    assert response.status_code == 400


def test_other_client_cannot_read_or_answer_session(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    assert client.get(f'/api/interviews/{started["id"]}', headers={"X-Interview-Token": "z" * 64}).status_code == 403
    assert client.post(
        f'/api/interviews/{started["id"]}/answers', headers={"X-Interview-Token": "z" * 64},
        json={"questionId": started["currentQuestion"]["id"], "answer": "다른 사용자의 답변"},
    ).status_code == 403


def test_replayed_question_id_is_rejected_without_consuming_next_question(client):
    started = client.post("/api/interviews", json=valid_settings()).get_json()
    question_id = started["currentQuestion"]["id"]
    payload = {"questionId": question_id, "answer": "제가 담당자로 로그를 분석해 오류를 20% 줄였습니다."}
    first = client.post(f'/api/interviews/{started["id"]}/answers', headers=access_headers(started), json=payload)
    second = client.post(f'/api/interviews/{started["id"]}/answers', headers=access_headers(started), json=payload)
    assert first.status_code == 200
    assert second.status_code == 409
    fetched = client.get(f'/api/interviews/{started["id"]}', headers=access_headers(started)).get_json()
    assert fetched["answeredCount"] == 1
    assert fetched["currentQuestion"]["sequence"] == 2
