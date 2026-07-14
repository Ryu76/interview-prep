from pathlib import Path
from tempfile import NamedTemporaryFile
from flask import Flask, jsonify, render_template, request
from research import build_report, extract_image_text

app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/research")
def research():
    data = request.form if request.form else (request.get_json(silent=True) or {})
    company, role, url = (data.get("company") or "").strip(), (data.get("role") or "").strip(), (data.get("jobUrl") or "").strip()
    if not company or not role:
        return jsonify({"error": "회사명과 지원 직무는 필수입니다."}), 400
    uploaded_text = ""
    image = request.files.get("jobImage")
    if image and image.filename:
        suffix = Path(image.filename).suffix.lower()
        if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
            return jsonify({"error": "PNG, JPG, JPEG, WEBP 이미지 파일만 업로드할 수 있습니다."}), 400
        with NamedTemporaryFile(suffix=suffix, delete=False) as temporary:
            image.save(temporary.name)
            path = temporary.name
        try:
            uploaded_text = extract_image_text(path)
        finally:
            Path(path).unlink(missing_ok=True)
        if not uploaded_text:
            return jsonify({"error": "이미지에서 읽을 수 있는 텍스트를 찾지 못했습니다. 더 선명한 이미지를 사용해 주세요."}), 422
    try:
        return jsonify(build_report(company, role, url, uploaded_text))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "채용공고를 불러오지 못했습니다. 공개 접근 가능한 URL인지 확인해 주세요."}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
