"""Render an interview briefing report as a paginated Korean PDF."""
from __future__ import annotations

from html import escape
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

import fitz


LIST_SECTIONS = (
    ("회사와 사업 맥락", "company_context"),
    ("직무 적합성 연결", "role_fit"),
    ("반드시 공부할 것", "must_know"),
    ("준비할 STAR 경험", "story_prompts"),
    ("면접관에게 할 역질문", "questions_for_interviewer"),
    ("면접 전날 최종 체크", "day_before_checklist"),
    ("과장하면 안 되는 부분", "cautions"),
)


def _text(value: object) -> str:
    return escape(str(value or ""))


def _list(items: object) -> str:
    values = items if isinstance(items, list) else []
    return "<ul>" + "".join(f"<li>{_text(item)}</li>" for item in values) + "</ul>"


def _font_settings() -> tuple[str, fitz.Archive | None]:
    candidates = (
        (Path("C:/Windows/Fonts/malgun.ttf"), "Malgun Gothic"),
        (Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"), "Noto Sans CJK KR"),
        (Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"), "NanumGothic"),
    )
    for font_path, font_name in candidates:
        if font_path.exists():
            archive = fitz.Archive(str(font_path.parent))
            return f"@font-face{{font-family:BriefFont;src:url('{font_path.name}')}}", archive
    return "", None


def build_pdf_html(report: dict) -> str:
    brief = report.get("interview_brief") or {}
    job = report.get("job_sections") or {}
    topics = report.get("selected_topics") if isinstance(report.get("selected_topics"), list) else []
    topics_html = "".join(f"<span>{_text(topic)}</span>" for topic in topics)
    playbook = brief.get("answer_playbook") if isinstance(brief.get("answer_playbook"), list) else []
    playbook_html = []
    for index, item in enumerate(playbook, 1):
        if not isinstance(item, dict):
            continue
        playbook_html.append(
            f"<section class='question'><h3>{index:02d}. {_text(item.get('question'))}</h3>"
            f"<p><b>면접관 의도</b> {_text(item.get('interviewer_intent'))}</p>"
            f"<p><b>답변 구조</b> {_text(item.get('answer_structure'))}</p>"
            f"<p><b>준비할 근거</b> {_text(item.get('evidence_to_prepare'))}</p></section>"
        )
    list_html = "".join(
        f"<section><h2>{title}</h2>{_list(brief.get(key))}</section>" for title, key in LIST_SECTIONS
    )
    source_links = []
    for url in brief.get("sources_used") or []:
        if isinstance(url, str) and urlparse(url).scheme in {"http", "https"}:
            safe_url = _text(url)
            source_links.append(f"<li><a href='{safe_url}'>{safe_url}</a></li>")
    return f"""<!doctype html><html><body>
      <header><div class='label'>INTERVIEW PREP BRIEF</div>
      <h1>{_text(report.get('company'))} · {_text(report.get('role'))}</h1>
      <div class='topics'>{topics_html}</div>
      <p class='notice'>{_text(report.get('notice'))}</p></header>
      <section class='summary'><h2>면접 완성 브리핑</h2><p>{_text(brief.get('executive_summary'))}</p></section>
      {list_html}
      <section><h2>예상 질문별 답변 설계</h2>{''.join(playbook_html)}</section>
      <section><h2>채용공고 해석</h2>
        <h3>담당 업무</h3><p>{_text(job.get('responsibilities'))}</p>
        <h3>필수 요건</h3><p>{_text(job.get('requirements'))}</p>
        <h3>우대 사항</h3><p>{_text(job.get('preferred'))}</p>
      </section>
      <section><h2>확인한 출처</h2><ol>{''.join(source_links)}</ol></section>
    </body></html>"""


def create_briefing_pdf(report: dict) -> bytes:
    font_face, archive = _font_settings()
    css = font_face + """
      @page { size: A4; margin: 18mm 16mm 18mm 16mm; }
      body { font-family: BriefFont, sans-serif; color: #18201d; font-size: 10pt; line-height: 1.65; }
      header { border-bottom: 2px solid #18201d; padding-bottom: 12pt; margin-bottom: 18pt; }
      .label { color: #71815d; font-size: 8pt; letter-spacing: 1pt; }
      h1 { font-size: 25pt; margin: 5pt 0 7pt; }
      h2 { color: #4d6c2a; font-size: 15pt; margin: 18pt 0 8pt; page-break-after: avoid; }
      h3 { font-size: 11pt; margin: 12pt 0 5pt; page-break-after: avoid; }
      p { margin: 4pt 0 8pt; }
      ul, ol { margin: 4pt 0 10pt; padding-left: 18pt; }
      li { margin-bottom: 5pt; }
      .notice { color: #68736e; font-size: 8.5pt; }
      .topics span { display: inline-block; background: #e5ebd7; color: #4d6c2a; padding: 3pt 6pt; margin: 0 4pt 5pt 0; font-size: 8.5pt; }
      .summary { background: #eef5df; padding: 12pt; }
      .summary h2 { margin-top: 0; }
      .question { border-left: 3px solid #c8ed70; padding-left: 10pt; margin-bottom: 13pt; page-break-inside: avoid; }
      .question b { display: inline-block; color: #4d6c2a; min-width: 60pt; }
      a { color: #4d6c2a; }
    """
    output = BytesIO()
    writer = fitz.DocumentWriter(output)
    story = fitz.Story(build_pdf_html(report), user_css=css, archive=archive)
    page_rect = fitz.paper_rect("a4")
    content_rect = page_rect + (45, 45, -45, -45)
    more = True
    while more:
        device = writer.begin_page(page_rect)
        more, _ = story.place(content_rect)
        story.draw(device)
        writer.end_page()
    writer.close()
    raw_pdf = output.getvalue()
    document = fitz.open(stream=raw_pdf, filetype="pdf")
    try:
        document.subset_fonts()
        return document.tobytes(garbage=4, deflate=True, clean=True)
    finally:
        document.close()
