from io import BytesIO
from pathlib import Path
import re
from tempfile import NamedTemporaryFile
from flask import Flask, jsonify, render_template, request, send_file
from pdf_export import create_briefing_pdf
from research import build_report, extract_image_text, extract_pdf_text

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 12 * 1024 * 1024


@app.errorhandler(413)
def uploaded_file_too_large(_error):
    return jsonify({"error": "업로드 파일은 12MB 이하여야 합니다."}), 413

@app.get("/")
def index():
    return render_template("index.html")


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
        return jsonify(build_report(company, role, url, uploaded_text, generate_brief=True))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "채용공고를 불러오지 못했습니다. 공개 접근 가능한 URL인지 확인해 주세요."}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
