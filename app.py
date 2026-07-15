from io import BytesIO
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from flask import Flask, jsonify, render_template, request, send_file
from pdf_export import create_briefing_pdf
from research import build_report, extract_image_text, extract_pdf_text
from interview import get_result, get_session, start, submit_answer

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024
app.config.setdefault("INTERVIEW_DATABASE", str(Path(app.instance_path) / "interviews.sqlite3"))


def interview_database():
    path = Path(app.config["INTERVIEW_DATABASE"])
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


@app.errorhandler(413)
def uploaded_file_too_large(_error):
    return jsonify({"error": "업로드 파일은 12MB 이하여야 합니다."}), 413

@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/interviews")
def start_interview():
    try:
        payload = request.get_json(silent=True)
        result = start(interview_database(), payload if payload is not None else {})
        return jsonify(result), 201
    except ValueError as error:
        return jsonify({"error": str(error)}), 400


@app.get("/api/interviews/<session_id>")
def interview_session(session_id):
    try:
        result = get_session(interview_database(), session_id, request.headers.get("X-Interview-Token", ""))
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    if result is None:
        return jsonify({"error": "면접 세션을 찾을 수 없습니다."}), 404
    return jsonify(result)


@app.post("/api/interviews/<session_id>/answers")
def answer_interview(session_id):
    try:
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise ValueError("요청 본문은 JSON 객체여야 합니다.")
        result = submit_answer(
            interview_database(), session_id, payload.get("answer", ""), payload.get("questionId"),
            request.headers.get("X-Interview-Token", ""),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    except RuntimeError as error:
        return jsonify({"error": str(error)}), 409
    if result is None:
        return jsonify({"error": "면접 세션을 찾을 수 없습니다."}), 404
    return jsonify(result)


@app.get("/api/interviews/<session_id>/result")
def interview_result(session_id):
    try:
        result = get_result(interview_database(), session_id, request.headers.get("X-Interview-Token", ""))
    except PermissionError as error:
        return jsonify({"error": str(error)}), 403
    if result is None:
        return jsonify({"error": "면접 세션을 찾을 수 없습니다."}), 404
    if result["status"] != "completed":
        return jsonify({"error": "면접을 완료한 후 결과를 확인할 수 있습니다."}), 409
    return jsonify(result)


@app.post("/api/export-pdf")
def export_pdf():
    report = request.get_json(silent=True) or {}
    company = str(report.get("company") or "").strip()
    role = str(report.get("role") or "").strip()
    if not company or not role or not isinstance(report.get("interview_brief"), dict):
        return jsonify({"error": "회사명, 지원 직무, 생성된 브리핑 내용이 필요합니다."}), 400
    pdf = create_briefing_pdf(report)
    filename = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", f"{company}_{role}_면접브리핑.pdf")
    return send_file(
        BytesIO(pdf),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=filename,
    )

@app.post("/api/research")
def research():
    data = request.form if request.form else (request.get_json(silent=True) or {})
    company, role, url = (data.get("company") or "").strip(), (data.get("role") or "").strip(), (data.get("jobUrl") or "").strip()
    topics = (data.get("topics") or "").strip()
    if not company or not role:
        return jsonify({"error": "회사명과 지원 직무는 필수입니다."}), 400
    uploaded_text = ""
    upload = request.files.get("jobFile") or request.files.get("jobImage")
    if upload and upload.filename:
        suffix = Path(upload.filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".pdf"}:
            return jsonify({"error": "PNG, JPG, JPEG, WEBP 이미지 또는 PDF 파일만 업로드할 수 있습니다."}), 400
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            upload.save(temporary.name)
            path = temporary.name
        try:
            uploaded_text = extract_pdf_text(path) if suffix == ".pdf" else extract_image_text(path)
        finally:
            Path(path).unlink(missing_ok=True)
        if not uploaded_text:
            return jsonify({"error": "업로드 파일에서 읽을 수 있는 텍스트를 찾지 못했습니다. 더 선명한 이미지 또는 텍스트가 포함된 PDF를 사용해 주세요."}), 422
    try:
        return jsonify(build_report(company, role, url, uploaded_text, topics_text=topics, generate_brief=True))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "채용공고를 불러오지 못했습니다. 공개 접근 가능한 URL인지 확인해 주세요."}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
