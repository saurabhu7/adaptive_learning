from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from project_settings import AI_PROVIDER, GEMINI_API_KEY, GROK_API_KEY, GROK_MODEL


DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
DEFAULT_GROK_MODEL = GROK_MODEL or "grok-3-mini"


def get_gemini_api_key() -> str:
    return os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()


def get_grok_api_key() -> str:
    return os.getenv("GROK_API_KEY", GROK_API_KEY).strip()


def _provider_order() -> list[str]:
    configured = (os.getenv("AI_PROVIDER", AI_PROVIDER) or "auto").strip().lower()
    if configured == "grok":
        return ["grok", "gemini"]
    if configured == "gemini":
        return ["gemini", "grok"]
    return ["grok", "gemini"]


def _extract_text_from_gemini(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []
    text_segments = [part.get("text", "") for part in parts if isinstance(part, dict)]
    return "\n".join(segment for segment in text_segments if segment).strip()


def _extract_text_from_grok(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        return "\n".join(part for part in text_parts if part).strip()
    return ""


def _post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: int = 30) -> dict[str, Any] | None:
    request = urllib.request.Request(
        url=url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None


def _call_gemini(prompt: str, *, max_output_tokens: int = 320, temperature: float = 0.5) -> str:
    api_key = get_gemini_api_key()
    if not api_key:
        return ""
    payload = _post_json(
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_GEMINI_MODEL}:generateContent",
        body={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        },
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        timeout=30,
    )
    if not payload:
        return ""
    return _extract_text_from_gemini(payload)


def _call_grok(prompt: str, *, max_tokens: int = 500, temperature: float = 0.4) -> str:
    api_key = get_grok_api_key()
    if not api_key:
        return ""
    payload = _post_json(
        url="https://api.x.ai/v1/chat/completions",
        body={
            "model": DEFAULT_GROK_MODEL,
            "messages": [
                {"role": "system", "content": "You are a precise assistant for adaptive learning systems."},
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        timeout=30,
    )
    if not payload:
        return ""
    return _extract_text_from_grok(payload)


def _run_ai_prompt(prompt: str, *, max_tokens: int = 500, temperature: float = 0.4) -> tuple[str, str]:
    for provider in _provider_order():
        if provider == "grok":
            text = _call_grok(prompt, max_tokens=max_tokens, temperature=temperature)
            if text:
                return text, "grok"
        if provider == "gemini":
            text = _call_gemini(prompt, max_output_tokens=max_tokens, temperature=temperature)
            if text:
                return text, "gemini"
    return "", "rule-based"


def _parse_structured_lines(text: str) -> dict[str, str]:
    result = {
        "coach_message": "",
        "student_message": "",
        "summary": "",
        "topic_focus": "",
        "intervention_reason": "",
    }
    for line in text.splitlines():
        normalized = line.strip()
        if normalized.startswith("COACH:"):
            result["coach_message"] = normalized.removeprefix("COACH:").strip()
        elif normalized.startswith("STUDENT:"):
            result["student_message"] = normalized.removeprefix("STUDENT:").strip()
        elif normalized.startswith("SUMMARY:"):
            result["summary"] = normalized.removeprefix("SUMMARY:").strip()
        elif normalized.startswith("TOPIC:"):
            result["topic_focus"] = normalized.removeprefix("TOPIC:").strip()
        elif normalized.startswith("WHY:"):
            result["intervention_reason"] = normalized.removeprefix("WHY:").strip()
    return result


def _extract_json_object(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def generate_emotion_guidance(
    *,
    course: dict[str, Any],
    emotion: str,
    confidence: float,
    project_context: dict[str, Any],
    support_plan: dict[str, Any],
    strategy: dict[str, str],
) -> dict[str, str]:
    prompt = f"""
You are supporting a real-time adaptive learning final year project.
Write exactly five lines and do not add anything else.

Context:
- Course title: {course.get("title", "")}
- Subject: {course.get("subject", "")}
- Category: {course.get("category", "")}
- Course description: {course.get("description", "")}
- Project domain: {project_context.get("domain", "")}
- Project goal: {project_context.get("goal", "")}
- Project requirements: {", ".join(project_context.get("requirements", []))}
- Detected facial expression: {emotion}
- Confidence: {confidence:.2f}
- Existing strategy title: {strategy.get("title", "")}
- Existing strategy text: {strategy.get("text", "")}
- Existing support headline: {support_plan.get("headline", "")}
- Existing support actions: {", ".join(support_plan.get("actions", []))}

Requirements:
- COACH must guide the teacher in one or two short sentences.
- STUDENT must explain the current lecture topic simply for the student in two short sentences.
- SUMMARY must describe the live intervention briefly.
- TOPIC must name the exact topic or concept that should be re-explained now.
- WHY must say why this explanation is being generated for the project.
- Keep the answer specific to the course instead of generic advice.

Output format:
COACH: ...
STUDENT: ...
SUMMARY: ...
TOPIC: ...
WHY: ...
""".strip()

    text, provider = _run_ai_prompt(prompt, max_tokens=360, temperature=0.5)
    if not text:
        return {}
    parsed = _parse_structured_lines(text)
    if not any(parsed.values()):
        return {}
    parsed["provider"] = provider
    parsed["model"] = DEFAULT_GROK_MODEL if provider == "grok" else DEFAULT_GEMINI_MODEL
    return parsed


def generate_course_learning_assets(*, course: dict[str, Any], transcript_text: str) -> dict[str, Any]:
    safe_transcript = (transcript_text or "").strip()
    excerpt = safe_transcript[:10000] if safe_transcript else "No transcript available."
    prompt = f"""
You are generating adaptive learning content for students.
Return only JSON with these keys:
summary, notes_markdown, quiz (array of 20 objects with question, options, answer).

Course:
- title: {course.get("title", "")}
- subject: {course.get("subject", "")}
- category: {course.get("category", "")}
- description: {course.get("description", "")}

Transcript excerpt:
{excerpt}

Rules:
- Summary must be 180-260 words and simple.
- Notes markdown must be detailed and long (at least 2200 words), with headings, subheadings, and bullet points suitable for final year students.
- Every major section must include transcript-grounded details (keywords, process steps, examples, definitions) from the lecture excerpt.
- Notes must be THEORY-FIRST and classroom-ready: include definitions, core principles, conceptual explanation, and exam-oriented points.
- Follow a lecture-notes style similar to diploma/semester notes:
  - Cover page title line
  - Short contents/index section
  - Chapter-wise flow (CHAPTER-1, CHAPTER-2, ...)
  - For each chapter: Introduction, need/significance, key concepts, point-wise explanation, mini examples
  - End with revision points and viva/interview questions
- Notes must include these sections in order:
  1) Learning Strategy (how to study this topic step-by-step)
  2) Contents / Chapter Index
  3) Theory Notes (chapter-wise / unit-wise explanation)
  4) Flow Chart (in Mermaid markdown block)
  5) Common Mistakes and Fixes
  6) Important Terms and Definitions
  7) Interview / Viva Questions
  8) Revision Plan
- Quiz should have 20 MCQ questions.
- Each quiz item must have 4 options in 'options' list, and 'answer' must be exactly one option.
- Use transcript details directly (examples, terms, flow, methods) and avoid generic filler or vague textbook language.
- Keep questions practical and concept-specific; do not repeat same template question style.
- Keep content specific to the course and transcript.
""".strip()

    text, provider = _run_ai_prompt(prompt, max_tokens=1200, temperature=0.35)
    payload = _extract_json_object(text) if text else {}

    summary = str(payload.get("summary", "")).strip()
    notes_markdown = str(payload.get("notes_markdown", "")).strip()
    quiz = payload.get("quiz")
    if not isinstance(quiz, list):
        quiz = []

    clean_quiz: list[dict[str, Any]] = []
    for item in quiz[:20]:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        options = item.get("options")
        normalized_options: list[str] = []
        if isinstance(options, list):
            for opt in options:
                text = str(opt).strip()
                if text:
                    normalized_options.append(text)
        if question and answer:
            if answer not in normalized_options:
                normalized_options.insert(0, answer)
            if len(normalized_options) < 4:
                filler = [
                    "All of the above",
                    "None of the above",
                    "Only theoretical understanding is enough",
                    "Skip fundamentals and directly solve advanced problems",
                ]
                for opt in filler:
                    if opt not in normalized_options and len(normalized_options) < 4:
                        normalized_options.append(opt)
            clean_quiz.append({"question": question, "answer": answer, "options": normalized_options[:4]})

    if not summary:
        summary = (
            f"{course.get('title', 'This course')} focuses on key concepts in {course.get('subject', 'the topic')}. "
            "Use the lecture flow to understand one idea at a time, connect it to real examples, and practice each step."
        )
    if not notes_markdown:
        notes_markdown = (
            f"# {course.get('title', 'Course Notes')}\n\n"
            "## 1) Learning Strategy\n"
            "- Start from definitions and conceptual foundation.\n"
            "- Move to process flow and then examples.\n"
            "- Revise each micro-topic before attempting questions.\n\n"
            "## 2) Flow Chart\n"
            "```mermaid\nflowchart TD\nA[Understand Concept] --> B[Study Definitions]\nB --> C[Learn Workflow]\nC --> D[Review Example]\nD --> E[Practice Questions]\n```\n\n"
            "## 3) Theory Notes\n"
            "- Explain each concept in simple and formal language.\n"
            "- Cover assumptions, principles, and use-cases.\n"
            "- Add at least one lecture-based example per concept.\n\n"
            "## 4) Common Mistakes and Fixes\n"
            "- Mistake: Skipping fundamentals.\n"
            "- Fix: Start with definitions and scope of topic.\n\n"
            "## 5) Important Terms and Definitions\n"
            "- Key Term 1: Meaning and context.\n"
            "- Key Term 2: Meaning and context.\n\n"
            "## 6) Interview / Viva Questions\n"
            "- Explain the concept in your own words.\n"
            "- Give one practical application.\n\n"
            "## 7) Revision Plan\n"
            "- Day 1: Concepts and definitions\n"
            "- Day 2: Process flow and examples\n"
            "- Day 3: MCQ + viva revision\n"
        )
    if len(clean_quiz) < 20:
        title = str(course.get("title", "this course")).strip()
        subject = str(course.get("subject", "this subject")).strip()
        transcript_words = [w.strip(".,:;!?()[]{}\"'").lower() for w in safe_transcript.split()]
        stop_words = {
            "the", "and", "for", "with", "that", "this", "from", "into", "your", "their", "there", "about",
            "have", "has", "was", "were", "when", "what", "where", "which", "while", "after", "before", "using",
        }
        freq: dict[str, int] = {}
        for word in transcript_words:
            if len(word) < 5 or word in stop_words or not word.isalpha():
                continue
            freq[word] = freq.get(word, 0) + 1
        keywords = [k for k, _ in sorted(freq.items(), key=lambda item: item[1], reverse=True)[:12]]
        if not keywords:
            keywords = [subject.lower().replace(" ", ""), "concept", "workflow", "application"]

        fallback: list[dict[str, str]] = []
        for kw in keywords:
            fallback.append(
                {
                    "question": f"In {title}, how is '{kw}' used in the {subject} workflow?",
                    "answer": f"'{kw}' is used as a key step in the lecture process for {subject}.",
                }
            )
            fallback.append(
                {
                    "question": f"Which statement best matches the lecture explanation of '{kw}' in {title}?",
                    "answer": f"The lecture defines '{kw}' with practical usage and step-by-step context.",
                }
            )
        fallback.append(
            {
                "question": f"What should a student revise first in {title} before taking the {subject} exam?",
                "answer": "Revise core definitions, process flow, and practical examples from the lecture.",
            }
        )

        for item in fallback[: max(0, 20 - len(clean_quiz))]:
            answer = item["answer"]
            clean_quiz.append(
                {
                    "question": item["question"],
                    "answer": answer,
                    "options": [
                        answer,
                        f"Skip important {subject} fundamentals from the lecture.",
                        f"Memorize {title} terms without understanding their usage.",
                        "Ignore lecture workflow and guess answers from intuition.",
                    ],
                }
            )
        clean_quiz = clean_quiz[:20]

    return {
        "summary": summary,
        "notes_markdown": notes_markdown,
        "quiz": clean_quiz,
        "provider": provider,
    }


def generate_topic_summary(
    *,
    course: dict[str, Any],
    lecture_title: str,
    topic: str,
    transcript_text: str,
) -> dict[str, Any]:
    excerpt = (transcript_text or "").strip()[:7000]
    prompt = f"""
You are an adaptive learning tutor.
Generate a concise, high-quality topic note for one lecture topic.

Return only JSON with keys:
topic, summary_markdown

Course title: {course.get("title", "")}
Subject: {course.get("subject", "")}
Lecture: {lecture_title}
Requested topic: {topic}
Transcript excerpt:
{excerpt or 'No transcript available.'}

Rules:
- summary_markdown must be 450-700 words.
- Include sections exactly in this order:
  1) Topic Definition
  2) Why This Topic Matters
  3) Step-by-Step Explanation
  4) Lecture-Based Example
  5) Common Mistakes and Fixes
  6) Interview/Viva Questions
  7) Quick Revision Points
- Use transcript-grounded explanation, not generic textbook filler.
- Keep language simple, clear, and exam-ready.
""".strip()
    text, provider = _run_ai_prompt(prompt, max_tokens=700, temperature=0.3)
    payload = _extract_json_object(text) if text else {}
    summary_markdown = str(payload.get("summary_markdown", "")).strip()
    if not summary_markdown:
        summary_markdown = (
            f"## 1) Topic Definition\n{topic} is an important concept in {course.get('title', 'this course')}.\n\n"
            "## 2) Why This Topic Matters\nIt helps students connect core theory with practical workflow and problem-solving.\n\n"
            "## 3) Step-by-Step Explanation\n1. Start with the basic definition.\n2. Understand the key process.\n3. Connect process with output.\n4. Validate with one practice scenario.\n\n"
            f"## 4) Lecture-Based Example\nUse one practical classroom example around {topic} and explain each step.\n\n"
            "## 5) Common Mistakes and Fixes\n- Mistake: Memorizing without understanding flow.\n- Fix: Map concept -> step -> output clearly.\n\n"
            "## 6) Interview/Viva Questions\n- Explain the concept in simple words.\n- Where is this concept used practically?\n\n"
            "## 7) Quick Revision Points\n- Definitions\n- Process flow\n- One example\n- One common mistake and fix"
        )
    return {
        "topic": str(payload.get("topic", topic or "Lecture Topic")).strip() or (topic or "Lecture Topic"),
        "summary_markdown": summary_markdown,
        "provider": provider,
    }
