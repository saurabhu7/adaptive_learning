from __future__ import annotations

import base64
import binascii
import random
from datetime import datetime
from typing import Any

from emotion_model import predict_emotion_from_data_url
from gemini_client import generate_emotion_guidance

try:
    import cv2
    import numpy as np
    from deepface import DeepFace
except Exception:
    cv2 = None
    np = None
    DeepFace = None


def realtime_supported(model_info: dict[str, Any] | None) -> bool:
    return model_info is not None or (DeepFace is not None and cv2 is not None and np is not None)


def strategy_for_emotion(emotion: str) -> dict[str, str]:
    strategies = {
        "sleepy": {
            "title": "Wake-up intervention now",
            "text": "The student appears drowsy. Pause lecture, ask them to sit upright, splash water, and restart with a 1-minute recap.",
        },
        "happy": {
            "title": "Keep going and add one challenge",
            "text": "The student looks comfortable, so continue the lecture and give one quick practice task to deepen understanding.",
        },
        "neutral": {
            "title": "Give a simple recap",
            "text": "Pause briefly and explain the last point again in two or three short lines before moving on.",
        },
        "focused": {
            "title": "Stay in the same mode",
            "text": "The student looks engaged. Continue the lecture and add one short self-check question after the next topic.",
        },
        "sad": {
            "title": "Slow down and simplify",
            "text": "Replay the concept more slowly, use simpler words, and explain it with one everyday example.",
        },
        "stressed": {
            "title": "Break the topic into smaller steps",
            "text": "Pause the lecture and split the concept into micro-steps so the student can understand one piece at a time.",
        },
        "fear": {
            "title": "Reduce the pressure",
            "text": "Move from theory to a guided example and reassure the student with one easy question before continuing.",
        },
        "angry": {
            "title": "Reset the session",
            "text": "Take a short reset break and restart from the last stable point with fewer ideas shown at once.",
        },
        "frustration": {
            "title": "Reduce pressure and reteach",
            "text": "The student may be frustrated, so pause, simplify the concept, and restart with one guided example.",
        },
        "surprise": {
            "title": "Anchor the idea with context",
            "text": "Explain why this new idea matters and connect it to the previous topic with one visual example.",
        },
        "disgust": {
            "title": "Change the learning style",
            "text": "Switch from plain lecture to diagram, example, or hands-on practice so the session feels less boring.",
        },
        "bored": {
            "title": "Make the lecture active",
            "text": "The student may be losing interest, so switch from passive watching to one question, one example, and one short activity.",
        },
        "confused": {
            "title": "Use another strategy now",
            "text": "Stop the lecture for a moment and reteach the same concept with a simpler explanation and one solved example.",
        },
    }
    return strategies.get(
        emotion,
        {
            "title": "Simplify the next explanation",
            "text": "Repeat the topic with simpler words and confirm understanding with one short question.",
        },
    )


def emotion_risk_level(emotion: str) -> int:
    levels = {
        "sleepy": 4,
        "happy": 0,
        "focused": 0,
        "neutral": 1,
        "bored": 2,
        "disgust": 2,
        "confused": 3,
        "stressed": 3,
        "sad": 3,
        "fear": 3,
        "angry": 4,
        "frustration": 4,
    }
    return levels.get((emotion or "neutral").lower(), 2)


def _parse_timestamp(raw_value: Any) -> datetime | None:
    if isinstance(raw_value, datetime):
        return raw_value
    if not raw_value:
        return None
    try:
        return datetime.fromisoformat(str(raw_value).replace("Z", ""))
    except ValueError:
        return None


def derive_emotion_state(
    raw_emotion: str,
    confidence: float,
    recent_events: list[dict[str, Any]] | None = None,
    *,
    smoothing_window: int = 12,
) -> dict[str, Any]:
    history = list(recent_events or [])
    recent = history[: max(1, smoothing_window - 1)]
    weighted: dict[str, float] = {}
    total_weight = 0.0
    for idx, row in enumerate(reversed(recent)):
        label = (row.get("emotion_smoothed") or row.get("emotion_raw") or "neutral").lower()
        hist_conf = float(row.get("confidence") or 30.0)
        recency_factor = (idx + 1) / max(len(recent), 1)
        # Keep history influence moderate so new frames can override stale dominant states.
        weight = max(0.1, (hist_conf / 100.0) * recency_factor * 0.8)
        weighted[label] = weighted.get(label, 0.0) + weight
        total_weight += weight
    current_weight = max(1.8, confidence / 12.0)
    weighted[raw_emotion] = weighted.get(raw_emotion, 0.0) + current_weight
    total_weight += current_weight
    smoothed = max(weighted, key=weighted.get)
    confidence_smoothed = round((weighted[smoothed] / max(total_weight, 1.0)) * 100.0, 2)
    # If the current frame is strong and disagrees with history, switch immediately.
    if raw_emotion != smoothed and confidence >= 60.0:
        smoothed = raw_emotion
        confidence_smoothed = round(min(100.0, max(confidence, confidence_smoothed)), 2)

    previous_smoothed = (recent[0].get("emotion_smoothed") if recent else raw_emotion) or raw_emotion
    previous_risk = emotion_risk_level(previous_smoothed)
    current_risk = emotion_risk_level(smoothed)
    if current_risk > previous_risk:
        trend_label = "rising_risk"
    elif current_risk < previous_risk:
        trend_label = "recovering"
    else:
        trend_label = "steady"
    if current_risk >= 3 and trend_label == "steady":
        trend_label = "stable_confused"
    return {
        "emotion_raw": raw_emotion,
        "emotion_smoothed": smoothed,
        "smoothed_confidence": confidence_smoothed,
        "trend_label": trend_label,
        "quality_state": "valid" if confidence > 0 else "fallback",
        "risk_score": current_risk,
        "previous_emotion": previous_smoothed,
        "previous_risk": previous_risk,
    }


def calibrate_emotion_with_feedback(
    predicted_emotion: str,
    confidence: float,
    feedback_rows: list[dict[str, Any]] | None = None,
) -> tuple[str, float]:
    rows = feedback_rows or []
    if not rows:
        return predicted_emotion, confidence
    actual_counts: dict[str, int] = {}
    total = 0
    for row in rows:
        if (row.get("predicted_emotion") or "").lower() != predicted_emotion:
            continue
        actual = (row.get("actual_emotion") or "").lower()
        count = int(row.get("total") or 0)
        if not actual or count <= 0:
            continue
        actual_counts[actual] = actual_counts.get(actual, 0) + count
        total += count
    if total < 3 or not actual_counts:
        return predicted_emotion, confidence
    best_actual = max(actual_counts, key=actual_counts.get)
    agreement = actual_counts[best_actual] / total
    if best_actual != predicted_emotion and agreement >= 0.6:
        return best_actual, max(15.0, confidence * 0.9)
    return predicted_emotion, confidence


def build_profile_snapshot(
    emotion_state: dict[str, Any],
    exam_average_score: float,
    recovery_rate: float,
    recent_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    recent = list(recent_events or [])[:8]
    if recent:
        stable_count = sum(
            1 for row in recent if emotion_risk_level((row.get("emotion_smoothed") or "neutral")) <= 1
        )
        stability_score = round((stable_count / len(recent)) * 100.0, 2)
    else:
        stability_score = 50.0
    engagement_score = round((0.6 * max(0.0, exam_average_score)) + (0.4 * stability_score), 2)
    risk_score = round(emotion_state.get("risk_score", 2) * 25.0, 2)
    if risk_score >= 70 or recovery_rate < 35:
        recommended_pacing = "slow"
    elif risk_score <= 25 and recovery_rate >= 60:
        recommended_pacing = "fast"
    else:
        recommended_pacing = "normal"
    return {
        "stability_score": stability_score,
        "engagement_score": engagement_score,
        "risk_score": risk_score,
        "recovery_rate": round(max(0.0, recovery_rate), 2),
        "recommended_pacing": recommended_pacing,
    }


def adaptive_strategy_for_state(
    emotion_state: dict[str, Any],
    profile_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile = profile_snapshot or {}
    emotion = emotion_state.get("emotion_smoothed", "neutral")
    trend = emotion_state.get("trend_label", "steady")
    base = strategy_for_emotion(emotion)
    risk_score = float(profile.get("risk_score", emotion_state.get("risk_score", 2) * 25.0))
    recovery_rate = float(profile.get("recovery_rate", 50.0))
    strategy_code = "maintain_flow"
    reason = "Student state is stable, so continuing the current pace is suitable."
    confidence = 0.62
    if risk_score >= 70 or emotion in {"confused", "stressed", "fear", "sad", "angry", "frustration"}:
        strategy_code = "simplify_and_slow"
        reason = "High cognitive-emotional risk detected, so content should be simplified and pace reduced."
        confidence = 0.84
    elif emotion in {"bored", "disgust"} or trend == "rising_risk":
        strategy_code = "active_reengagement"
        reason = "Disengagement pattern detected, so activity-based re-engagement is likely to help."
        confidence = 0.78
    elif recovery_rate >= 65 and emotion in {"happy", "focused"}:
        strategy_code = "challenge_boost"
        reason = "Consistent recovery and engagement suggest the learner can handle a small challenge."
        confidence = 0.73
    return {
        "code": strategy_code,
        "title": base["title"],
        "text": base["text"],
        "confidence": round(confidence, 2),
        "reason": reason,
    }


def classify_outcome(before_emotion: str | None, after_emotion: str) -> str:
    if not before_emotion:
        return "baseline"
    before_risk = emotion_risk_level(before_emotion)
    after_risk = emotion_risk_level(after_emotion)
    if after_risk < before_risk:
        return "improved"
    if after_risk > before_risk:
        return "worsened"
    return "unchanged"


def estimate_recovery_seconds(previous_created_at: Any, outcome_status: str) -> int | None:
    if outcome_status != "improved":
        return None
    previous_time = _parse_timestamp(previous_created_at)
    if previous_time is None:
        return None
    elapsed = int((datetime.now() - previous_time).total_seconds())
    return max(elapsed, 0)


def simple_explanation_for_course(course, emotion: str) -> str:
    subject = course["subject"]
    title = course["title"]
    category = course["category"]
    generic = (
        f"{title} is easier when we focus on one small idea at a time. "
        f"First understand what {subject} is used for, then see one simple example, and only after that move to the full lecture."
    )
    by_category = {
        "programming": (
            f"In {subject}, do not try to learn the whole program at once. "
            "Read one line, understand what it does, and test it with one small input."
        ),
        "ai-ml": (
            f"In {subject}, think of the model like a learner that finds patterns from examples. "
            "First understand the input, then the pattern, then the prediction."
        ),
        "datascience": (
            f"In {subject}, begin with the data itself before looking at formulas. "
            "See what each column means, then find one trend, then explain what that trend tells us."
        ),
        "webdevelopment": (
            f"In {subject}, treat the page as three parts: structure, style, and behavior. "
            "First see the HTML, then the CSS design, then the JavaScript action."
        ),
    }
    if emotion in {"confused", "stressed", "sad", "fear", "frustration"}:
        return by_category.get(category, generic)
    if emotion in {"bored", "disgust"}:
        return by_category.get(category, generic) + " To keep it interesting, connect the topic to one real project or a mini task right now."
    return generic


def project_context_for_course(course) -> dict[str, Any]:
    category = course["category"]
    domain_map = {
        "programming": "EdTech with intelligent programming support",
        "ai-ml": "AI-enabled adaptive education",
        "datascience": "Data-driven adaptive education",
        "webdevelopment": "Interactive web-based adaptive education",
    }
    domain = domain_map.get(category, "Adaptive learning and educational technology")
    return {
        "domain": domain,
        "goal": (
            "Detect student emotion during a live lecture and immediately generate a simpler explanation, "
            "better teaching strategy, and supportive intervention for the same topic."
        ),
        "requirements": [
            "Monitor student emotion during the lecture",
            "Detect confusion, stress, boredom, or engagement in real time",
            "Generate a simpler explanation for the current topic",
            "Suggest the next teaching action for the live session",
            "Store every intervention as project evidence",
        ],
        "lecture_flow": [
            "Student starts the lecture",
            "Camera captures the current facial expression",
            "Emotion analysis checks if the student is confused or stable",
            "Gemini generates a topic-specific explanation and support message",
            "The session saves the support result for dashboard review",
        ],
    }


def live_support_plan(course, emotion: str) -> dict[str, Any]:
    plan = {
        "support_state": "steady",
        "headline": "Lecture can continue",
        "coach_message": "The student looks stable enough to continue the current lecture flow.",
        "actions": [
            "Continue the lecture for the next short segment.",
            "Ask one quick self-check question after the next point.",
            "Keep the explanation short and focused.",
        ],
        "simple_explanation": simple_explanation_for_course(course, emotion),
    }
    if emotion == "sleepy":
        plan.update(
            {
                "support_state": "critical_sleep",
                "headline": "Student may be sleepy",
                "coach_message": "Pause lecture now and wake the student before continuing.",
                "actions": [
                    "Ask student to sit upright and wash face.",
                    "Take a 1-2 minute activation break.",
                    "Restart with a very short recap and one simple question.",
                ],
            }
        )
    elif emotion in {"confused", "sad", "fear", "stressed", "frustration"}:
        plan.update(
            {
                "support_state": "needs_support",
                "headline": "Student may be confused right now",
                "coach_message": "Pause the lecture and reteach the same concept with easier words during this session.",
                "actions": [
                    "Stop the video for a moment and explain only one concept.",
                    "Use one real-life example before returning to theory.",
                    "Ask the student one yes or no understanding check.",
                ],
            }
        )
    elif emotion in {"bored", "disgust"}:
        plan.update(
            {
                "support_state": "needs_switch",
                "headline": "Student may be bored with the current method",
                "coach_message": "Change the learning strategy now so the student becomes active instead of only watching.",
                "actions": [
                    "Switch from lecture to a diagram, example, or mini problem.",
                    "Ask the student to predict the next step before showing it.",
                    "Turn the next topic into one short practical task.",
                ],
            }
        )
    elif emotion in {"happy", "focused"}:
        plan.update(
            {
                "support_state": "engaged",
                "headline": "Student looks engaged",
                "coach_message": "Keep the flow going and add one small challenge to deepen understanding.",
                "actions": [
                    "Continue the lecture at the same pace.",
                    "Add one practice question after the next idea.",
                    "Use one applied example to strengthen recall.",
                ],
            }
        )
    return plan


def normalize_emotion_label(dominant: str, confidence: float) -> str:
    dominant = (dominant or "neutral").lower()
    # Allow happy at moderate confidence so smiling faces are not forced to neutral.
    if dominant == "happy" and confidence < 35:
        return "neutral"
    if dominant == "angry":
        return "frustration"
    if dominant in {"sad", "fear"} and confidence >= 25:
        return "confused"
    if dominant == "surprise":
        return "stressed"
    if dominant == "disgust" and confidence >= 20:
        return "bored"
    if dominant == "neutral" and confidence >= 55:
        return "bored"
    return dominant


def _is_sleepy_frame(frame) -> bool:
    if cv2 is None:
        return False
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(str(cv2.data.haarcascades + "haarcascade_frontalface_default.xml"))
        eye_cascade = cv2.CascadeClassifier(str(cv2.data.haarcascades + "haarcascade_eye_tree_eyeglasses.xml"))
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(80, 80))
        if len(faces) == 0:
            return False
        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        face_roi = gray[y : y + h, x : x + w]
        upper_face = face_roi[0 : max(1, int(h * 0.6)), :]
        eyes = eye_cascade.detectMultiScale(upper_face, scaleFactor=1.1, minNeighbors=5, minSize=(15, 15))
        return len(eyes) == 0
    except Exception:
        return False


def _frame_quality_state(frame) -> tuple[str, float]:
    if cv2 is None:
        return "valid", 1.0
    try:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        # Low-light or blur can degrade FER quality; mark these so pipeline can safely fallback.
        if brightness < 40 or brightness > 225:
            return "low_light", 0.45
        if sharpness < 35:
            return "blurred", 0.5
        return "valid", 1.0
    except Exception:
        return "valid", 1.0


def analyze_frame_emotion(data_url: str) -> tuple[str, float, str]:
    fallback_options = ["neutral"]
    if not data_url or "," not in data_url:
        return random.choice(fallback_options), 0.0, "fallback"
    try:
        _, encoded = data_url.split(",", 1)
        image_bytes = base64.b64decode(encoded)
    except (ValueError, binascii.Error):
        return random.choice(fallback_options), 0.0, "fallback"
    try:
        image_array = np.frombuffer(image_bytes, dtype=np.uint8) if np is not None else None
        frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR) if (cv2 is not None and image_array is not None) else None
        if frame is not None:
            quality_state, quality_factor = _frame_quality_state(frame)
            if quality_state != "valid":
                return "neutral", max(8.0, 22.0 * quality_factor), f"quality-{quality_state}"
        if frame is not None and _is_sleepy_frame(frame):
            return "sleepy", 92.0, "sleep-detector"
        trained_prediction = predict_emotion_from_data_url(data_url)
    except Exception:
        trained_prediction = None
    if trained_prediction is not None:
        detected, confidence, provider = trained_prediction
        if confidence < 18:
            return "neutral", confidence, f"{provider}-lowconf"
        return normalize_emotion_label(detected, confidence), confidence, provider
    if DeepFace is None or cv2 is None or np is None:
        return random.choice(fallback_options), 0.0, "fallback"
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    frame = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if frame is None:
        return random.choice(fallback_options), 0.0, "fallback"
    try:
        result = DeepFace.analyze(
            img_path=frame,
            actions=["emotion"],
            enforce_detection=False,
            detector_backend="opencv",
        )
        payload = result[0] if isinstance(result, list) else result
        dominant = (payload.get("dominant_emotion") or "neutral").lower()
        confidence = float(payload.get("emotion", {}).get(dominant, 0.0))
        return normalize_emotion_label(dominant, confidence), confidence, "deepface"
    except Exception:
        return random.choice(fallback_options), 0.0, "fallback"


def quiz_for_course(course, emotion: str) -> dict[str, str]:
    title = course["title"]
    subject = course["subject"]
    category = course["category"]
    if category == "programming":
        return {
            "question": f"In {title}, what should you understand first before writing a full {subject} program?",
            "answer": "Understand one line or one step at a time before building the full program.",
        }
    if category == "ai-ml":
        return {
            "question": f"In {title}, what comes before prediction in {subject}?",
            "answer": "First understand the input data and the pattern the model learns from it.",
        }
    if category == "datascience":
        return {
            "question": f"In {title}, what should you check before using formulas in {subject}?",
            "answer": "Check what the data columns mean and look for one clear trend first.",
        }
    if category == "webdevelopment":
        return {
            "question": f"In {title}, what are the three core parts of {subject}?",
            "answer": "Structure, style, and behavior.",
        }
    if emotion in {"confused", "sad", "stressed", "fear", "frustration"}:
        return {
            "question": f"What is the one main idea from {title} that you need to understand before moving on?",
            "answer": "The core concept of the current topic in one simple step.",
        }
    return {
        "question": f"What is the most important concept from {title} so far?",
        "answer": "The main concept currently being explained in the lecture.",
    }


def build_guidance_payload(
    course,
    emotion: str,
    confidence: float,
    *,
    emotion_state: dict[str, Any] | None = None,
    profile_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = emotion_state or {"emotion_smoothed": emotion, "trend_label": "steady", "risk_score": emotion_risk_level(emotion)}
    strategy = adaptive_strategy_for_state(state, profile_snapshot)
    support_plan = live_support_plan(course, emotion)
    project_context = project_context_for_course(course)
    quiz = quiz_for_course(course, emotion)
    gemini_guidance = generate_emotion_guidance(
        course=dict(course),
        emotion=emotion,
        confidence=confidence,
        project_context=project_context,
        support_plan=support_plan,
        strategy=strategy,
    )
    coach_message = gemini_guidance.get("coach_message") or support_plan["coach_message"]
    student_message = gemini_guidance.get("student_message") or support_plan["simple_explanation"]
    summary = gemini_guidance.get("summary") or strategy["text"]
    topic_focus = gemini_guidance.get("topic_focus") or f"{course['title']} fundamentals"
    intervention_reason = (
        gemini_guidance.get("intervention_reason")
        or "This explanation is generated because the project detected that the student may need support during the live lecture."
    )
    return {
        "strategy": strategy,
        "support_plan": support_plan,
        "coach_message": coach_message,
        "student_message": student_message,
        "summary": summary,
        "topic_focus": topic_focus,
        "intervention_reason": intervention_reason,
        "project_context": project_context,
        "quiz": quiz,
        "generator_provider": gemini_guidance.get("provider", "rule-based"),
        "trend_label": state.get("trend_label", "steady"),
        "strategy_code": strategy.get("code", "maintain_flow"),
        "strategy_confidence": strategy.get("confidence", 0.6),
        "strategy_reason": strategy.get("reason", "Strategy selected from current learner state."),
    }
