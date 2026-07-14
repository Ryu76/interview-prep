"""Public-source collection and transparent rule-based interview research."""
from __future__ import annotations
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup

MAX_PDF_PAGES = 12
MAX_EXTRACTED_TEXT = 24000

HEADERS = {"User-Agent": "Mozilla/5.0 (InterviewPrepBot/1.0; public research)"}


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def extract_job_sections(text: str) -> dict[str, str]:
    lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
    groups = {"responsibilities": [], "requirements": [], "preferred": []}
    current = "responsibilities"
    for line in lines:
        lower = line.lower()
        if any(key in lower for key in ["자격 요건", "자격요건", "필수", "requirements"]):
            current = "requirements"; continue
        if any(key in lower for key in ["우대", "preferred", "plus"]):
            current = "preferred"; continue
        if any(key in lower for key in ["담당 업무", "주요 업무", "직무", "responsibil"]):
            current = "responsibilities"; continue
        groups[current].append(line)
    return {key: " ".join(value[:12]) for key, value in groups.items()}


def build_questions(role: str, job_text: str) -> list[str]:
    questions = [
        f"{role} 직무에서 가장 중요한 문제를 무엇이라 정의하며, 입사 후 90일 동안 무엇을 검증하겠습니까?",
        "공고의 핵심 요구사항 중 본인이 가장 강하게 증명할 수 있는 경험을 STAR 방식으로 설명해 주세요.",
        "기대와 다른 결과가 나왔던 프로젝트에서 원인을 어떻게 파악하고 의사결정을 바꿨습니까?",
    ]
    keyword_map = {
        "python": "Python으로 성능 또는 안정성 문제를 해결한 사례와 검증 방법을 설명해 주세요.",
        "sql": "SQL로 복잡한 분석 질문을 해결한 사례에서 데이터 품질을 어떻게 검증했습니까?",
        "분석": "분석 결과를 이해관계자의 실제 의사결정으로 연결한 사례를 설명해 주세요.",
        "a/b": "A/B 테스트의 성공 지표·가드레일 지표·표본 수를 어떻게 설계하겠습니까?",
        "cloud": "클라우드 환경에서 비용·보안·신뢰성의 균형을 맞춘 경험이 있습니까?",
        "react": "React 컴포넌트의 상태 관리와 성능 문제를 해결한 경험을 설명해 주세요.",
    }
    normalized = job_text.lower()
    for keyword, question in keyword_map.items():
        if keyword in normalized:
            questions.append(question)
    return questions[:7]


def fetch_job_posting(url: str) -> tuple[str, str | None]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("채용공고 URL은 http 또는 https 주소여야 합니다.")
    response = requests.get(url, headers=HEADERS, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]): tag.decompose()
    title = clean_text(soup.title.get_text(" ", strip=True)) if soup.title else None
    return soup.get_text("\n", strip=True)[:24000], title


def search_public_sources(query: str, limit: int = 3) -> list[dict[str, str]]:
    try:
        response = requests.get("https://html.duckduckgo.com/html/", params={"q": query}, headers=HEADERS, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = []
        for result in soup.select(".result")[:limit]:
            anchor = result.select_one(".result__a")
            snippet = result.select_one(".result__snippet")
            if anchor:
                items.append({"title": clean_text(anchor.get_text(" ", strip=True)), "url": anchor.get("href", ""), "snippet": clean_text(snippet.get_text(" ", strip=True)) if snippet else ""})
        return items
    except requests.RequestException:
        return []


def extract_image_text(image_path: str) -> str:
    """Extract Korean/English text from a locally uploaded job-posting image."""
    from rapidocr_onnxruntime import RapidOCR
    result, _ = RapidOCR()(image_path)
    return "\n".join(str(row[1]) for row in result or [])


def extract_pdf_text(pdf_path: str) -> str:
    """Extract a job posting from a PDF; OCR image-only pages as a fallback."""
    import fitz

    try:
        document = fitz.open(pdf_path)
    except Exception as error:
        raise ValueError("열 수 없는 PDF 파일입니다. 손상되지 않은 PDF인지 확인해 주세요.") from error
    try:
        if document.needs_pass:
            raise ValueError("암호로 보호된 PDF는 업로드할 수 없습니다.")
        if not document.page_count:
            raise ValueError("페이지가 없는 PDF 파일입니다.")

        pages = [document.load_page(index) for index in range(min(document.page_count, MAX_PDF_PAGES))]
        text = "\n".join(page.get_text("text") for page in pages).strip()
        if len(clean_text(text)) >= 80:
            return text[:MAX_EXTRACTED_TEXT]

        ocr_text = []
        for page in pages:
            with NamedTemporaryFile(suffix=".png", delete=False) as temporary:
                image_path = temporary.name
            try:
                page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(image_path)
                ocr_text.append(extract_image_text(image_path))
            finally:
                Path(image_path).unlink(missing_ok=True)
        return "\n".join(ocr_text).strip()[:MAX_EXTRACTED_TEXT]
    finally:
        document.close()


def build_report(company: str, role: str, job_url: str = "", uploaded_text: str = "") -> dict:
    if job_url:
        job_text, job_title = fetch_job_posting(job_url)
        if uploaded_text.strip():
            job_text = f"{job_text}\n\n[업로드한 공고 파일]\n{uploaded_text.strip()}"
    else:
        job_title = None
        job_text = uploaded_text.strip() or f"담당 업무\n{role} 직무의 핵심 문제를 해결하고, 필요 역량과 협업 경험을 조사합니다."
    sections = extract_job_sections(job_text)
    if not sections["responsibilities"]:
        sections["responsibilities"] = clean_text(job_text)
    searches = {
        "history": search_public_sources(f"{company} 회사 연혁"),
        "values": search_public_sources(f"{company} 인재상 핵심가치"),
        "business": search_public_sources(f"{company} 사업 소개"),
        "reviews": search_public_sources(f"{company} {role} 면접 후기"),
    }
    return {"company": company, "role": role, "job_title": job_title, "job_sections": sections, "questions": build_questions(role, job_text), "sources": searches, "notice": "공개 웹페이지에서 수집한 자료입니다. 출처를 열어 사실관계와 최신성을 직접 확인하세요."}
