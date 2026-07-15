"""Deterministic, offline text interview engine with SQLite persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import hmac
import json
import math
import re
import secrets
import sqlite3
from uuid import uuid4


SCORE_KEYS = (
    "questionUnderstanding",
    "specificity",
    "structure",
    "jobRelevance",
    "companyFit",
)
EXPERIENCE_LEVELS = {"신입", "경력"}
INTERVIEW_TYPES = {"인성", "직무", "PT", "임원"}
DIFFICULTIES = {"쉬움", "보통", "어려움"}


def connect(database: str) -> sqlite3.Connection:
    connection = sqlite3.connect(database)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS interview_sessions (
            id TEXT PRIMARY KEY, company TEXT NOT NULL, role TEXT NOT NULL,
            experience_level TEXT NOT NULL, interview_type TEXT NOT NULL,
            difficulty TEXT NOT NULL, question_count INTEGER NOT NULL,
            job_posting TEXT NOT NULL DEFAULT '', resume TEXT NOT NULL DEFAULT '',
            access_token_hash TEXT NOT NULL,
            status TEXT NOT NULL, created_at TEXT NOT NULL, completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS interview_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL, text TEXT NOT NULL, kind TEXT NOT NULL,
            focus TEXT, UNIQUE(session_id, sequence)
        );
        CREATE TABLE IF NOT EXISTS interview_answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
            question_id INTEGER NOT NULL UNIQUE REFERENCES interview_questions(id) ON DELETE CASCADE,
            text TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS interview_evaluations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            answer_id INTEGER NOT NULL UNIQUE REFERENCES interview_answers(id) ON DELETE CASCADE,
            scores_json TEXT NOT NULL, evidence_quote TEXT NOT NULL,
            strengths_json TEXT NOT NULL, improvements_json TEXT NOT NULL,
            improved_example TEXT NOT NULL
        );
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(interview_sessions)")}
    if "access_token_hash" not in columns:
        connection.execute("ALTER TABLE interview_sessions ADD COLUMN access_token_hash TEXT NOT NULL DEFAULT ''")
    return connection


def validate_settings(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ValueError("요청 본문은 JSON 객체여야 합니다.")
    aliases = {
        "company": "회사명", "role": "직무", "experienceLevel": "경력 구분",
        "interviewType": "면접 유형", "difficulty": "난이도",
    }
    cleaned = {}
    for key, label in aliases.items():
        value = str(data.get(key) or "").strip()
        if not value:
            raise ValueError(f"{label}은(는) 필수입니다.")
        if key in {"company", "role"} and len(value) > 100:
            raise ValueError(f"{label}은(는) 100자 이하여야 합니다.")
        cleaned[key] = value
    if cleaned["experienceLevel"] not in EXPERIENCE_LEVELS:
        raise ValueError("경력 구분은 신입 또는 경력이어야 합니다.")
    if cleaned["interviewType"] not in INTERVIEW_TYPES:
        raise ValueError("면접 유형은 인성, 직무, PT, 임원 중 하나여야 합니다.")
    if cleaned["difficulty"] not in DIFFICULTIES:
        raise ValueError("난이도는 쉬움, 보통, 어려움 중 하나여야 합니다.")
    count = data.get("questionCount")
    if isinstance(count, bool) or (isinstance(count, float) and (not math.isfinite(count) or not count.is_integer())):
        raise ValueError("질문 수는 3~10 사이의 정수여야 합니다.")
    try:
        count = int(count)
    except (TypeError, ValueError, OverflowError):
        raise ValueError("질문 수는 3~10 사이의 정수여야 합니다.") from None
    if count < 3 or count > 10:
        raise ValueError("질문 수는 3~10 사이여야 합니다.")
    cleaned["questionCount"] = count
    cleaned["jobPosting"] = str(data.get("jobPosting") or "").strip()[:10000]
    cleaned["resume"] = str(data.get("resume") or "").strip()[:10000]
    return cleaned


def base_question(settings: sqlite3.Row | dict, sequence: int) -> str:
    role, company = settings["role"], settings["company"]
    interview_type = settings["interview_type"] if "interview_type" in settings.keys() else settings["interviewType"]
    experience_level = settings["experience_level"] if "experience_level" in settings.keys() else settings["experienceLevel"]
    difficulty = settings["difficulty"]
    pools = {
        "인성": [
            f"{role}로서 본인의 강점이 드러난 경험을 말씀해 주세요.",
            "의견 충돌을 해결했던 경험과 본인의 역할을 설명해 주세요.",
            f"{company}에서 이루고 싶은 성장 목표는 무엇인가요?",
        ],
        "직무": [
            f"{role} 업무에서 가장 성과를 낸 경험을 구체적으로 설명해 주세요.",
            f"{role} 업무 중 어려운 문제를 분석하고 해결한 과정을 말씀해 주세요.",
            f"{company}의 업무에 본인의 역량을 어떻게 적용하겠습니까?",
        ],
        "PT": [
            f"{role} 관점에서 개선이 필요한 문제 하나와 해결안을 발표해 주세요.",
            "제안한 해결안의 우선순위와 성과 지표를 설명해 주세요.",
            "예상되는 위험과 대응 방안을 설명해 주세요.",
        ],
        "임원": [
            f"왜 {company}의 {role}에 지원했으며 어떤 기여를 할 수 있나요?",
            "중요한 판단에서 원칙을 지킨 경험을 말씀해 주세요.",
            "장기적으로 조직과 함께 만들고 싶은 성과는 무엇인가요?",
        ],
    }
    pool = pools[interview_type]
    question = pool[(sequence - 1) % len(pool)]
    if experience_level == "신입":
        question += " 신입 지원자로서 학습 과정과 본인의 기여를 구분해 주세요."
    else:
        question += " 경력 지원자로서 본인의 책임 범위와 의사결정을 밝혀 주세요."
    if difficulty == "쉬움":
        return question + " 핵심 상황과 본인의 행동을 중심으로 답해 주세요."
    if difficulty == "어려움":
        return question + " 선택한 대안의 한계와 예상 위험까지 함께 설명해 주세요."
    return question


def answer_signals(answer: str) -> dict[str, bool]:
    return {
        "number": bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|퍼센트|명|건|회|일|개월|초|분|원|배)", answer)),
        "role": bool(re.search(r"제가|저는|담당|주도|역할|책임|직접", answer)),
        "evidence": bool(re.search(r"분석|측정|로그|피드백|데이터|검증|적용|구현|결과|성과|감소|증가|개선", answer)),
    }


def follow_up(answer: str) -> tuple[str, str] | None:
    signals = answer_signals(answer)
    if not signals["role"]:
        return "역할", "그 과정에서 본인이 직접 맡은 역할과 행동을 구체적으로 말씀해 주세요."
    if not signals["number"]:
        return "수치", "성과를 확인할 수 있는 수치나 전후 비교 근거를 말씀해 주세요."
    if not signals["evidence"]:
        return "근거", "그 판단과 성과를 뒷받침한 데이터나 피드백 근거를 말씀해 주세요."
    return None


def evaluate(answer: str, session: sqlite3.Row) -> dict:
    signals = answer_signals(answer)
    length = len(answer)
    has_structure = bool(re.search(r"먼저|이후|그 결과|결과적으로|상황|과제", answer)) or length >= 80
    role_terms = [term for term in re.split(r"[^0-9A-Za-z가-힣+#.]+", session["role"]) if len(term) > 1]
    company_fit = session["company"].lower() in answer.lower()
    job_fit = any(term.lower() in answer.lower() for term in role_terms) or signals["evidence"]
    scores = {
        "questionUnderstanding": 4 if length >= 25 else 2,
        "specificity": min(5, 2 + int(signals["number"]) + int(signals["role"]) + int(signals["evidence"])),
        "structure": 4 if has_structure else 2,
        "jobRelevance": 4 if job_fit else 2,
        "companyFit": 4 if company_fit else (3 if session["job_posting"] else 2),
    }
    strengths = []
    if signals["role"]:
        strengths.append("본인의 역할을 구분해 설명했습니다.")
    if signals["number"]:
        strengths.append("수치로 성과를 뒷받침했습니다.")
    if signals["evidence"]:
        strengths.append("행동 또는 판단 근거가 포함되어 있습니다.")
    if not strengths:
        strengths.append("질문에 답하려는 핵심 경험을 제시했습니다.")
    improvements = []
    labels = {"role": "본인이 맡은 역할", "number": "검증 가능한 수치 또는 전후 비교", "evidence": "판단과 행동의 근거"}
    for key, label in labels.items():
        if not signals[key]:
            improvements.append(f"{label}을(를) 실제 사실에 근거해 보완하세요.")
    if not has_structure:
        improvements.append("상황-과제-행동-결과 순서로 답변을 구조화하세요.")
    if not company_fit:
        improvements.append("공고에 명시된 요구 역량과 연결해 지원 회사 맞춤도를 높이세요.")
    quote = answer[:140] + ("…" if len(answer) > 140 else "")
    example = (
        "상황: [본인의 실제 상황] / 과제: [달성해야 했던 실제 목표] / "
        "행동: [본인이 직접 한 행동과 판단 근거] / 결과: [실제로 확인한 수치·피드백] / "
        "직무 연결: [공고의 요구 역량과 연결]"
    )
    return {
        "scores": scores,
        "evidenceQuote": quote,
        "strengths": strengths,
        "improvements": improvements or ["현재 구체성을 유지하고 답변을 더 간결하게 정리하세요."],
        "improvedExample": example,
    }


def question_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return {"id": row["id"], "sequence": row["sequence"], "text": row["text"], "kind": row["kind"], "focus": row["focus"]}


def settings_dict(row: sqlite3.Row) -> dict:
    return {
        "company": row["company"], "role": row["role"],
        "experienceLevel": row["experience_level"], "interviewType": row["interview_type"],
        "difficulty": row["difficulty"], "questionCount": row["question_count"],
        "jobPosting": row["job_posting"], "resume": row["resume"],
    }


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def require_access(db: sqlite3.Connection, session_id: str, access_token: str) -> sqlite3.Row | None:
    session = db.execute("SELECT * FROM interview_sessions WHERE id = ?", (session_id,)).fetchone()
    if session is None:
        return None
    if not access_token or not hmac.compare_digest(session["access_token_hash"], token_hash(access_token)):
        raise PermissionError("이 면접 세션에 접근할 권한이 없습니다.")
    return session


def start(database: str, data: dict) -> dict:
    settings = validate_settings(data)
    session_id, now = uuid4().hex, datetime.now(timezone.utc).isoformat()
    access_token = secrets.token_urlsafe(32)
    with connect(database) as db:
        db.execute(
            "INSERT INTO interview_sessions "
            "(id, company, role, experience_level, interview_type, difficulty, question_count, "
            "job_posting, resume, access_token_hash, status, created_at, completed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'in_progress', ?, NULL)",
            (session_id, settings["company"], settings["role"], settings["experienceLevel"],
             settings["interviewType"], settings["difficulty"], settings["questionCount"],
             settings["jobPosting"], settings["resume"], token_hash(access_token), now),
        )
        text = base_question(settings, 1)
        cursor = db.execute(
            "INSERT INTO interview_questions(session_id, sequence, text, kind) VALUES (?, 1, ?, 'base')",
            (session_id, text),
        )
        question = {"id": cursor.lastrowid, "sequence": 1, "text": text, "kind": "base", "focus": None}
    return {"id": session_id, "accessToken": access_token, "status": "in_progress", "settings": settings,
            "currentQuestion": question, "answeredCount": 0}


def get_session(database: str, session_id: str, access_token: str) -> dict | None:
    with connect(database) as db:
        session = require_access(db, session_id, access_token)
        if not session:
            return None
        current = db.execute(
            "SELECT q.* FROM interview_questions q LEFT JOIN interview_answers a ON a.question_id=q.id "
            "WHERE q.session_id=? AND a.id IS NULL ORDER BY q.sequence LIMIT 1", (session_id,),
        ).fetchone()
        answered = db.execute("SELECT COUNT(*) FROM interview_answers WHERE session_id=?", (session_id,)).fetchone()[0]
        return {"id": session_id, "status": session["status"], "settings": settings_dict(session),
                "currentQuestion": question_dict(current), "answeredCount": answered}


def submit_answer(database: str, session_id: str, answer: str, question_id: int, access_token: str) -> dict | None:
    answer = str(answer or "").strip()
    if not answer:
        raise ValueError("답변을 입력해 주세요.")
    if len(answer) > 10000:
        raise ValueError("답변은 10,000자 이하여야 합니다.")
    if isinstance(question_id, bool) or not isinstance(question_id, int):
        raise ValueError("현재 질문 ID가 필요합니다.")
    with connect(database) as db:
        db.execute("BEGIN IMMEDIATE")
        session = require_access(db, session_id, access_token)
        if not session:
            return None
        if session["status"] == "completed":
            raise RuntimeError("이미 완료된 면접입니다.")
        question = db.execute(
            "SELECT q.* FROM interview_questions q LEFT JOIN interview_answers a ON a.question_id=q.id "
            "WHERE q.session_id=? AND a.id IS NULL ORDER BY q.sequence LIMIT 1", (session_id,),
        ).fetchone()
        if not question:
            raise RuntimeError("답변할 질문이 없습니다.")
        if question["id"] != question_id:
            raise RuntimeError("이미 처리되었거나 현재 질문과 일치하지 않는 답변입니다.")
        cursor = db.execute(
            "INSERT INTO interview_answers(session_id, question_id, text, created_at) VALUES (?, ?, ?, ?)",
            (session_id, question["id"], answer, datetime.now(timezone.utc).isoformat()),
        )
        evaluation = evaluate(answer, session)
        db.execute(
            "INSERT INTO interview_evaluations(answer_id, scores_json, evidence_quote, strengths_json, improvements_json, improved_example) VALUES (?, ?, ?, ?, ?, ?)",
            (cursor.lastrowid, json.dumps(evaluation["scores"]), evaluation["evidenceQuote"],
             json.dumps(evaluation["strengths"], ensure_ascii=False), json.dumps(evaluation["improvements"], ensure_ascii=False),
             evaluation["improvedExample"]),
        )
        sequence = question["sequence"]
        if sequence >= session["question_count"]:
            db.execute("UPDATE interview_sessions SET status='completed', completed_at=? WHERE id=?",
                       (datetime.now(timezone.utc).isoformat(), session_id))
            return {"id": session_id, "status": "completed", "evaluation": evaluation, "nextQuestion": None}
        adaptive = follow_up(answer)
        kind = "follow_up" if adaptive else "base"
        focus, text = adaptive if adaptive else (None, base_question(session, sequence + 1))
        next_cursor = db.execute(
            "INSERT INTO interview_questions(session_id, sequence, text, kind, focus) VALUES (?, ?, ?, ?, ?)",
            (session_id, sequence + 1, text, kind, focus),
        )
        next_question = {"id": next_cursor.lastrowid, "sequence": sequence + 1, "text": text, "kind": kind, "focus": focus}
        return {"id": session_id, "status": "in_progress", "evaluation": evaluation, "nextQuestion": next_question}


def get_result(database: str, session_id: str, access_token: str) -> dict | None:
    with connect(database) as db:
        session = require_access(db, session_id, access_token)
        if not session:
            return None
        rows = db.execute(
            "SELECT q.id question_id,q.sequence,q.text question_text,q.kind,q.focus,a.text answer_text,"
            "e.scores_json,e.evidence_quote,e.strengths_json,e.improvements_json,e.improved_example "
            "FROM interview_questions q LEFT JOIN interview_answers a ON a.question_id=q.id "
            "LEFT JOIN interview_evaluations e ON e.answer_id=a.id WHERE q.session_id=? ORDER BY q.sequence",
            (session_id,),
        ).fetchall()
        questions, answers, score_sets = [], [], []
        for row in rows:
            questions.append({"id": row["question_id"], "sequence": row["sequence"], "text": row["question_text"], "kind": row["kind"], "focus": row["focus"]})
            if row["answer_text"] is not None:
                scores = json.loads(row["scores_json"])
                score_sets.append(scores)
                answers.append({"questionId": row["question_id"], "text": row["answer_text"], "evaluation": {
                    "scores": scores, "evidenceQuote": row["evidence_quote"],
                    "strengths": json.loads(row["strengths_json"]), "improvements": json.loads(row["improvements_json"]),
                    "improvedExample": row["improved_example"],
                }})
        overall = {key: round(sum(scores[key] for scores in score_sets) / len(score_sets), 1) for key in SCORE_KEYS} if score_sets else {key: 0 for key in SCORE_KEYS}
        return {"id": session_id, "status": session["status"], "settings": settings_dict(session),
                "questions": questions, "answers": answers, "overallScores": overall}
