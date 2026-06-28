from __future__ import annotations

import json
import html
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from gemini_client import generate_course_learning_assets, generate_topic_summary
from project_settings import BASE_DIR

try:
    from youtube_transcript_api import YouTubeTranscriptApi
except Exception:
    YouTubeTranscriptApi = None

try:
    from fpdf import FPDF
    from fpdf.errors import FPDFException
except Exception:
    FPDF = None
    FPDFException = Exception


NOTES_DIR = BASE_DIR / "static" / "uploads" / "notes"
NOTES_DIR.mkdir(parents=True, exist_ok=True)
MAX_NOTES_PAGES = 20


class _BasicPdfWriter:
    def __init__(self) -> None:
        self.pages: list[list[str]] = [[]]
        self.max_lines = 46
        self.font_size = 11

    def _current_page(self) -> list[str]:
        return self.pages[-1]

    def add_page(self) -> None:
        self.pages.append([])

    def _push_line(self, text: str) -> None:
        page = self._current_page()
        if len(page) >= self.max_lines:
            self.add_page()
            page = self._current_page()
        page.append(_safe_pdf_text(text, max_token=35))

    def add_heading(self, text: str) -> None:
        self._push_line("")
        self._push_line(text.upper())
        self._push_line("")

    def add_paragraph(self, text: str, width: int = 95) -> None:
        words = _safe_pdf_text(text, max_token=35).split()
        if not words:
            self._push_line("")
            return
        line = []
        current = 0
        for word in words:
            extra = len(word) + (1 if line else 0)
            if current + extra > width:
                self._push_line(" ".join(line))
                line = [word]
                current = len(word)
            else:
                line.append(word)
                current += extra
        if line:
            self._push_line(" ".join(line))

    def add_bullets(self, lines: list[str]) -> None:
        if not lines:
            self._push_line("- Content will be generated from lecture transcript after next sync.")
            return
        for line in lines:
            self.add_paragraph(f"- {line}")

    @staticmethod
    def _escape_pdf_text(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    def save(self, path: Path) -> None:
        if not self.pages:
            self.pages = [["Course Notes"]]

        objects: list[bytes] = []
        page_count = len(self.pages)
        page_obj_ids = []
        content_obj_ids = []

        for idx in range(page_count):
            page_obj_ids.append(3 + idx * 2)
            content_obj_ids.append(4 + idx * 2)
        font_obj_id = 3 + page_count * 2

        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        kids = " ".join(f"{obj_id} 0 R" for obj_id in page_obj_ids)
        objects.append(f"<< /Type /Pages /Count {page_count} /Kids [ {kids} ] >>".encode("latin-1"))

        for idx, page_lines in enumerate(self.pages):
            page_obj = (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> "
                f"/Contents {content_obj_ids[idx]} 0 R >>"
            ).encode("latin-1")
            objects.append(page_obj)
            content_lines = ["BT", f"/F1 {self.font_size} Tf", "50 800 Td", "14 TL"]
            for line in page_lines:
                escaped = self._escape_pdf_text(line)
                content_lines.append(f"({escaped}) Tj")
                content_lines.append("T*")
            content_lines.append("ET")
            stream_data = "\n".join(content_lines).encode("latin-1", errors="ignore")
            content_obj = (
                f"<< /Length {len(stream_data)} >>\nstream\n".encode("latin-1")
                + stream_data
                + b"\nendstream"
            )
            objects.append(content_obj)

        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

        with path.open("wb") as f:
            f.write(b"%PDF-1.4\n")
            offsets = [0]
            for idx, obj in enumerate(objects, start=1):
                offsets.append(f.tell())
                f.write(f"{idx} 0 obj\n".encode("latin-1"))
                f.write(obj)
                f.write(b"\nendobj\n")
            xref_pos = f.tell()
            f.write(f"xref\n0 {len(objects) + 1}\n".encode("latin-1"))
            f.write(b"0000000000 65535 f \n")
            for off in offsets[1:]:
                f.write(f"{off:010d} 00000 n \n".encode("latin-1"))
            f.write(
                (
                    f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
                    f"startxref\n{xref_pos}\n%%EOF\n"
                ).encode("latin-1")
            )


def extract_youtube_video_id(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.hostname in {"youtu.be"}:
        return parsed.path.lstrip("/")
    if "youtube.com" in (parsed.hostname or ""):
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [""])[0]
        if parsed.path == "/playlist":
            return ""
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts"}:
            if parts[1] == "videoseries":
                return ""
            return parts[1]
    match = re.search(r"(?:v=|/)([0-9A-Za-z_-]{11})(?:[?&]|$)", value)
    return match.group(1) if match else ""


def fetch_transcript_from_youtube(youtube_url: str) -> dict[str, Any]:
    video_id = extract_youtube_video_id(youtube_url)
    if not video_id:
        return {"ok": False, "error": "Invalid YouTube URL."}
    if YouTubeTranscriptApi is None:
        return {"ok": False, "error": "youtube-transcript-api is not installed."}
    try:
        transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-IN", "en-US"])
    except Exception:
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            best = None
            for lang in ("en", "en-US", "en-IN", "hi", "mr"):
                try:
                    best = transcript_list.find_transcript([lang])
                    if best:
                        break
                except Exception:
                    continue
            if best is None:
                best = transcript_list.find_generated_transcript(["en", "hi"])
            transcript = best.fetch() if best is not None else []
        except Exception:
            return {"ok": False, "error": "Transcript unavailable for this video."}
    text = " ".join(segment.get("text", "").strip() for segment in transcript if isinstance(segment, dict)).strip()
    if not text:
        return {"ok": False, "error": "Transcript was empty."}
    return {"ok": True, "video_id": video_id, "transcript_text": text}


def _markdown_to_lines(markdown: str) -> list[str]:
    lines: list[str] = []
    for raw in (markdown or "").splitlines():
        text = raw.strip()
        if not text:
            lines.append("")
            continue
        text = re.sub(r"^#+\s*", "", text)
        text = text.replace("**", "").replace("__", "")
        lines.append(text)
    return lines


def _strip_markdown_tokens(text: str) -> str:
    value = text or ""
    value = re.sub(r"`{1,3}", "", value)
    value = value.replace("**", "").replace("__", "")
    value = re.sub(r"^\s*[|•.\-]+\s*", "", value)
    value = value.replace("->", " to ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_sections(markdown: str) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {
        "learning_strategy": [],
        "contents_index": [],
        "theory_notes": [],
        "flow_chart": [],
        "point_wise_notes": [],
        "mistakes_and_fixes": [],
        "important_terms": [],
        "interview_questions": [],
        "revision_plan": [],
    }
    current_key = "point_wise_notes"
    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        lowered = stripped.lower()
        if lowered.startswith("#"):
            header = re.sub(r"^#+\s*", "", lowered).strip()
            if "learning strategy" in header:
                current_key = "learning_strategy"
            elif "contents" in header or "index" in header:
                current_key = "contents_index"
            elif "theory notes" in header or "chapter-wise" in header or "unit-wise" in header:
                current_key = "theory_notes"
            elif "flow chart" in header or "flowchart" in header:
                current_key = "flow_chart"
            elif "point" in header and "note" in header:
                current_key = "point_wise_notes"
            elif "mistake" in header or "fix" in header:
                current_key = "mistakes_and_fixes"
            elif "important terms" in header or "definitions" in header:
                current_key = "important_terms"
            elif "interview" in header or "viva" in header:
                current_key = "interview_questions"
            elif "revision" in header or "plan" in header:
                current_key = "revision_plan"
            continue
        if stripped:
            mapping[current_key].append(_strip_markdown_tokens(stripped))
    return mapping


def _safe_pdf_text(value: str, max_token: int = 40) -> str:
    cleaned = " ".join((value or "").replace("\t", " ").split())
    cleaned = cleaned.encode("latin-1", "ignore").decode("latin-1")
    tokens = cleaned.split(" ")
    normalized_tokens: list[str] = []
    for token in tokens:
        if len(token) <= max_token:
            normalized_tokens.append(token)
            continue
        parts = [token[idx : idx + max_token] for idx in range(0, len(token), max_token)]
        normalized_tokens.extend(parts)
    return " ".join(part for part in normalized_tokens if part)


def _build_notes_html(
    *,
    title: str,
    summary: str,
    notes_markdown: str,
    quiz: list[dict[str, str]],
    transcript_text: str,
) -> str:
    sections = _extract_sections(notes_markdown)
    transcript_excerpt = " ".join((transcript_text or "").split())[:5000]

    def list_html(lines: list[str], *, allow_flow: bool = False) -> str:
        cleaned: list[str] = []
        for raw in lines:
            text = _strip_markdown_tokens(raw)
            if not text:
                continue
            lower = text.lower()
            if not allow_flow and ("mermaid" in lower or "flowchart" in lower):
                continue
            cleaned.append(text)
        if not cleaned:
            return "<li>Content will be generated from lecture transcript sync.</li>"
        return "".join(f"<li>{html.escape(line)}</li>" for line in cleaned)

    quiz_items = []
    for idx, item in enumerate((quiz or [])[:20], start=1):
        q = html.escape(_strip_markdown_tokens(str(item.get("question", ""))))
        a = html.escape(_strip_markdown_tokens(str(item.get("answer", ""))))
        if not q:
            continue
        options = item.get("options") if isinstance(item.get("options"), list) else []
        option_html = "".join(f"<li>{html.escape(_strip_markdown_tokens(str(opt)))}</li>" for opt in options[:4])
        quiz_items.append(
            f"<article class='quiz-item'><h4>Q{idx}. {q}</h4><ol>{option_html}</ol><p><strong>Answer:</strong> {a}</p></article>"
        )

    theory_lines = sections["theory_notes"] or sections["point_wise_notes"] or _markdown_to_lines(notes_markdown)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#eef2ff;color:#0f172a}}
.page{{max-width:980px;margin:18px auto;background:#fff;border-radius:14px;padding:24px 30px;box-shadow:0 8px 24px rgba(15,23,42,.08)}}
h1,h2,h3{{margin:0 0 10px}} h1{{font-size:30px}} h2{{margin-top:22px;font-size:21px;border-left:4px solid #2563eb;padding-left:8px}}
p,li{{line-height:1.6;font-size:15px}} ul,ol{{padding-left:22px}}
.summary{{background:#eff6ff;border:1px solid #bfdbfe;border-radius:10px;padding:14px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} .quiz-item{{border:1px solid #e2e8f0;border-radius:10px;padding:12px}}
@media (max-width:900px){{.grid{{grid-template-columns:1fr}} .page{{padding:16px}}}}
</style>
</head>
<body>
<main class="page">
<h1>{html.escape(title)}</h1>
<section class="summary"><h2>Summary</h2><p>{html.escape(summary or "Summary unavailable.")}</p></section>
<h2>1) Learning Strategy</h2><ul>{list_html(sections["learning_strategy"])}</ul>
<h2>2) Contents / Chapter Index</h2><ul>{list_html(sections["contents_index"])}</ul>
<h2>3) Theory Notes (Unit-wise)</h2><ul>{list_html(theory_lines)}</ul>
<h2>4) Flow Chart / Learning Flow</h2><ul>{list_html(sections["flow_chart"], allow_flow=True)}</ul>
<h2>4) Common Mistakes and Fixes</h2><ul>{list_html(sections["mistakes_and_fixes"])}</ul>
<h2>5) Important Terms and Definitions</h2><ul>{list_html(sections["important_terms"])}</ul>
<h2>6) Interview / Viva Questions</h2><ul>{list_html(sections["interview_questions"])}</ul>
<h2>7) Revision Plan</h2><ul>{list_html(sections["revision_plan"])}</ul>
<h2>8) Practice Questions (20)</h2><div class="grid">{''.join(quiz_items) or '<p>No quiz available.</p>'}</div>
<h2>Transcript-Based Recap</h2><p>{html.escape(transcript_excerpt or "Transcript unavailable.")}</p>
</main>
</body>
</html>"""


def _pdf_write_text(pdf: Any, text: str, line_height: int = 7) -> None:
    safe_text = _safe_pdf_text(text)
    if not safe_text:
        return
    try:
        pdf.multi_cell(190, line_height, safe_text)
        return
    except FPDFException:
        fallback = re.sub(r"[^A-Za-z0-9 .,;:!?()_\\-/#]", " ", safe_text)
        fallback = " ".join(fallback.split())
        if not fallback:
            return
        pdf.multi_cell(190, line_height, fallback)


def create_notes_pdf(
    *,
    title: str,
    summary: str,
    notes_markdown: str,
    quiz: list[dict[str, str]],
    transcript_text: str,
    target_path: Path,
) -> dict[str, Any]:
    if FPDF is None:
        writer = _BasicPdfWriter()
        sections = _extract_sections(notes_markdown)
        writer.add_heading(title or "Course Notes")
        writer.add_heading("Summary")
        writer.add_paragraph(summary or "Summary unavailable.")
        writer.add_heading("1) Learning Strategy to Study This Course")
        writer.add_bullets(sections["learning_strategy"])
        writer.add_heading("2) Flow Chart (Learning Flow)")
        writer.add_bullets(
            sections["flow_chart"]
            or [
                "Understand fundamentals -> Identify core logic -> Watch one practical example",
                "Write key points -> Solve mini practice -> Self-check with quiz",
                "Revise weak topic -> Attempt exam -> Repeat until confident",
            ]
        )
        writer.add_heading("3) Point-wise Notes")
        writer.add_bullets(sections["point_wise_notes"] or _markdown_to_lines(notes_markdown)[:120])
        writer.add_heading("4) Common Mistakes and Fixes")
        writer.add_bullets(sections["mistakes_and_fixes"])
        writer.add_heading("5) Interview / Viva Questions")
        writer.add_bullets(sections["interview_questions"])
        writer.add_heading("6) Revision Plan")
        writer.add_bullets(sections["revision_plan"])
        writer.add_heading("7) Practice Questions and Answers (20)")
        for idx, item in enumerate((quiz or [])[:20], start=1):
            question = _strip_markdown_tokens(str(item.get("question", "")))
            answer = _strip_markdown_tokens(str(item.get("answer", "")))
            if question:
                writer.add_paragraph(f"Q{idx}. {question}")
            options = item.get("options")
            if isinstance(options, list):
                for option_idx, option in enumerate(options[:4], start=1):
                    writer.add_paragraph(f"   Option {option_idx}: {_strip_markdown_tokens(str(option))}")
            if answer:
                writer.add_paragraph(f"   Answer: {answer}")
        while len(writer.pages) < 10:
            writer.add_page()
            writer.add_heading(f"Transcript Recap (Page {len(writer.pages)})")
            writer.add_paragraph(transcript_text[:4000] or "Recap content will be enriched from transcript.")
        writer.save(target_path)
        return {"ok": True, "path": str(target_path)}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    sections = _extract_sections(notes_markdown)

    def section_heading(text: str) -> None:
        pdf.set_font("Helvetica", "B", 13)
        _pdf_write_text(pdf, text, line_height=8)
        pdf.ln(1)

    def write_list(lines: list[str], *, bullet: bool = False) -> None:
        pdf.set_font("Helvetica", "", 11)
        if not lines:
            _pdf_write_text(pdf, "Content will be generated from lecture transcript after next sync.", line_height=7)
            pdf.ln(1)
            return
        for item in lines:
            text = _strip_markdown_tokens(item)
            if not text:
                continue
            prefix = "- " if bullet else ""
            _pdf_write_text(pdf, f"{prefix}{text}", line_height=7)
            pdf.ln(1)

    # Page 1: Cover + Summary
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 17)
    _pdf_write_text(pdf, title or "Course Notes", line_height=10)
    pdf.ln(2)
    section_heading("Summary")
    write_list([summary or "Summary unavailable."])

    # Page 2: Learning strategy
    pdf.add_page()
    section_heading("1) Learning Strategy to Study This Course")
    write_list(sections["learning_strategy"], bullet=True)

    # Page 3: Flow chart
    pdf.add_page()
    section_heading("2) Flow Chart (Learning Flow)")
    flow_lines = sections["flow_chart"]
    if not flow_lines:
        flow_lines = [
            "Understand fundamentals -> Identify core formula / logic -> Watch one example",
            "Pause and write key points -> Solve one mini practice -> Self-check with MCQ",
            "Revise weak topic -> Attempt course exam -> Repeat until confidence improves",
        ]
    write_list(flow_lines)

    # Pages 4-6: Point-wise notes
    point_lines = sections["point_wise_notes"] or _markdown_to_lines(notes_markdown)
    chunks = [point_lines[i : i + 32] for i in range(0, max(len(point_lines), 1), 32)]
    while len(chunks) < 3:
        chunks.append(point_lines[:32] if point_lines else ["Topic points will appear after transcript sync."])
    for page_idx, chunk in enumerate(chunks[:3], start=1):
        pdf.add_page()
        section_heading(f"3) Point-wise Notes (Part {page_idx})")
        write_list(chunk, bullet=True)

    # Page 7: Mistakes and fixes
    pdf.add_page()
    section_heading("4) Common Mistakes and Fixes")
    write_list(sections["mistakes_and_fixes"], bullet=True)

    # Page 8: Interview / viva questions
    pdf.add_page()
    section_heading("5) Interview / Viva Questions")
    interview_lines = sections["interview_questions"]
    if not interview_lines:
        interview_lines = [
            "Explain the core concept in simple words.",
            "Where is this concept used in real projects?",
            "What common mistakes happen and how to avoid them?",
            "How would you optimize this approach in production?",
            "How does this topic connect with previous concepts?",
        ]
    write_list(interview_lines, bullet=True)

    # Page 9: Revision plan
    pdf.add_page()
    section_heading("6) Revision Plan")
    write_list(sections["revision_plan"], bullet=True)

    # Page 10+: 20 Q/A
    quiz_items = quiz or []
    pdf.add_page()
    section_heading("7) Practice Questions and Answers (20)")
    pdf.set_font("Helvetica", "", 11)
    for idx, item in enumerate(quiz_items[:20], start=1):
        question = _strip_markdown_tokens(str(item.get("question", "")))
        answer = _strip_markdown_tokens(str(item.get("answer", "")))
        if not question:
            continue
        _pdf_write_text(pdf, f"Q{idx}. {question}", line_height=7)
        options = item.get("options")
        if isinstance(options, list) and options:
            for option_idx, option in enumerate(options[:4], start=1):
                option_text = _strip_markdown_tokens(str(option))
                if option_text:
                    _pdf_write_text(pdf, f"   Option {option_idx}: {option_text}", line_height=7)
        if answer:
            _pdf_write_text(pdf, f"   Answer: {answer}", line_height=7)
        pdf.ln(1)

    # Add transcript recap pages while keeping PDF length controlled.
    transcript_words = (transcript_text or "").split()
    recap_pointer = 0
    while pdf.page_no() < MAX_NOTES_PAGES:
        pdf.add_page()
        section_heading(f"Transcript Recap (Page {pdf.page_no()})")
        if transcript_words:
            block = transcript_words[recap_pointer : recap_pointer + 600]
            if not block:
                recap_pointer = 0
                block = transcript_words[:600]
            recap_pointer += 600
            write_list([" ".join(block)])
        else:
            write_list(
                [
                    "Revise the lecture by replaying difficult segments and writing one-line summaries.",
                    "Practice one question after each key concept and verify your answer.",
                    "Focus on definitions, workflow, and one practical real-world use case.",
                ]
            )

        if pdf.page_no() >= 12 and recap_pointer >= len(transcript_words):
            break

    pdf.output(str(target_path))
    return {"ok": True, "path": str(target_path)}


def create_topic_pdf(
    *,
    course_title: str,
    topic: str,
    summary_markdown: str,
    target_path: Path,
) -> dict[str, Any]:
    if FPDF is None:
        writer = _BasicPdfWriter()
        writer.add_heading(f"{course_title} - Topic Summary")
        writer.add_heading(f"Topic: {topic}")
        for line in _markdown_to_lines(summary_markdown):
            writer.add_paragraph(line)
        writer.save(target_path)
        return {"ok": True, "path": str(target_path)}
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    _pdf_write_text(pdf, f"{course_title} - Topic Summary", line_height=10)
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 12)
    _pdf_write_text(pdf, f"Topic: {topic}", line_height=8)
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 11)
    for line in _markdown_to_lines(summary_markdown):
        if not line:
            pdf.ln(2)
            continue
        _pdf_write_text(pdf, line, line_height=7)
    pdf.output(str(target_path))
    return {"ok": True, "path": str(target_path)}


def build_course_assets(course: dict[str, Any]) -> dict[str, Any]:
    transcript_text = ""
    transcript_source = "none"
    if course.get("youtube_url"):
        transcript_payload = fetch_transcript_from_youtube(course["youtube_url"])
        if transcript_payload.get("ok"):
            transcript_text = str(transcript_payload.get("transcript_text", ""))
            transcript_source = "youtube"
    ai_payload = generate_course_learning_assets(
        course=course,
        transcript_text=transcript_text or str(course.get("description", "")),
    )
    quiz = ai_payload.get("quiz") or []
    summary = str(ai_payload.get("summary", "")).strip()
    notes_markdown = str(ai_payload.get("notes_markdown", "")).strip()

    safe_title = re.sub(r"[^A-Za-z0-9_-]+", "-", str(course.get("title", "course")).strip()).strip("-") or "course"
    html_file_name = f"{safe_title}-notes.html"
    html_file_path = NOTES_DIR / html_file_name
    html_content = _build_notes_html(
        title=f"{course.get('title', 'Course')} Notes",
        summary=summary,
        notes_markdown=notes_markdown,
        quiz=quiz,
        transcript_text=transcript_text,
    )
    html_file_path.write_text(html_content, encoding="utf-8")

    return {
        "ok": True,
        "summary": summary,
        "notes_markdown": notes_markdown,
        "quiz_json": json.dumps(quiz, ensure_ascii=True),
        "provider": str(ai_payload.get("provider", "rule-based")),
        "transcript_source": transcript_source,
        "pdf_file": html_file_name,
        "html_file": html_file_name,
    }


def build_topic_summary_asset(
    *,
    course: dict[str, Any],
    topic: str,
    lecture_title: str,
    lecture_url: str,
) -> dict[str, Any]:
    transcript_text = ""
    if lecture_url:
        transcript_payload = fetch_transcript_from_youtube(lecture_url)
        if transcript_payload.get("ok"):
            transcript_text = str(transcript_payload.get("transcript_text", ""))
    payload = generate_topic_summary(
        course=course,
        lecture_title=lecture_title,
        topic=topic,
        transcript_text=transcript_text or str(course.get("description", "")),
    )
    safe_course = re.sub(r"[^A-Za-z0-9_-]+", "-", str(course.get("title", "course")).strip()).strip("-") or "course"
    safe_topic = re.sub(r"[^A-Za-z0-9_-]+", "-", topic.strip()).strip("-") or "topic"
    file_name = f"{safe_course}-{safe_topic}-summary.html"
    file_path = NOTES_DIR / file_name
    html_content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(str(payload.get("topic", topic)))}</title>
<style>body{{font-family:Segoe UI,Arial,sans-serif;margin:0;background:#eff6ff;color:#0f172a}}main{{max-width:900px;margin:16px auto;background:#fff;border-radius:12px;padding:22px;box-shadow:0 8px 24px rgba(15,23,42,.08)}}h1{{margin:0 0 8px}}h2{{margin-top:18px}}p,li{{line-height:1.6}}</style></head>
<body><main><h1>{html.escape(str(course.get("title", "Course")))}</h1><h2>Topic: {html.escape(str(payload.get("topic", topic)))}</h2><pre style="white-space:pre-wrap;font-family:inherit;">{html.escape(str(payload.get("summary_markdown", "")))}</pre></main></body></html>"""
    file_path.write_text(html_content, encoding="utf-8")
    return {
        "ok": True,
        "topic": str(payload.get("topic", topic)),
        "summary_markdown": str(payload.get("summary_markdown", "")),
        "provider": str(payload.get("provider", "rule-based")),
        "pdf_file": file_name,
    }
