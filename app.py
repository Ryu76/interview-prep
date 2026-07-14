from flask import Flask, jsonify, render_template, request
from research import build_report

app = Flask(__name__)

@app.get("/")
def index():
    return render_template("index.html")

@app.post("/api/research")
def research():
    data = request.get_json(silent=True) or {}
    company, role, url = (data.get("company") or "").strip(), (data.get("role") or "").strip(), (data.get("jobUrl") or "").strip()
    if not all([company, role, url]):
        return jsonify({"error": "회사명, 지원 직무, 채용공고 URL을 모두 입력하세요."}), 400
    try:
        return jsonify(build_report(company, role, url))
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    except Exception:
        return jsonify({"error": "채용공고를 불러오지 못했습니다. 공개 접근 가능한 URL인지 확인해 주세요."}), 502

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=True)
