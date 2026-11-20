"""
quiz_service.py - The "brain" of the application (no Streamlit code here).

It does four things:
  1. build_prompt()      - prompt design for the LLM
  2. validate_questions()- checks and cleans every generated question
  3. generate_quiz()     - calls Gemini, parses, validates, retries if needed
  4. evaluate_quiz()     - scores the user's answers

Keeping this separate from the UI makes it easy to unit-test.
"""

import re

import config
from utils.json_parser import JSONParseError, extract_question_list, parse_llm_json


class QuizGenerationError(Exception):
    """Raised when we could not obtain a usable quiz from the model."""


class InvalidInputError(Exception):
    """Raised when the user's input (topic / material) is not acceptable."""


# ---------------------------------------------------------------------------
# 1. Input checking and prompt design
# ---------------------------------------------------------------------------
def prepare_inputs(topic: str, material: str):
    """
    Clean the user's input. Returns (topic, material, warning_or_None).
    Raises InvalidInputError when nothing usable was given.
    """
    topic = (topic or "").strip()
    material = (material or "").strip()
    warning = None

    if not topic and not material:
        raise InvalidInputError("Please enter a topic or paste some study material.")

    if material and len(material) < config.MIN_MATERIAL_CHARS:
        raise InvalidInputError(
            f"The study material is too short ({len(material)} characters). "
            f"Paste at least {config.MIN_MATERIAL_CHARS} characters, or clear the box "
            "and enter only a topic."
        )

    if len(material) > config.MAX_MATERIAL_CHARS:
        material = material[: config.MAX_MATERIAL_CHARS]
        warning = (
            f"The study material was very long, so only the first "
            f"{config.MAX_MATERIAL_CHARS:,} characters were used."
        )
    return topic, material, warning


def build_prompt(topic: str, material: str, num_questions: int, difficulty: str,
                 avoid_questions=None) -> str:
    """Create the instruction text that is sent to Gemini."""
    difficulty_guide = {
        "Easy": "Test basic recall of key facts and definitions. Distractors should be clearly different.",
        "Medium": "Test understanding and application of the ideas. Distractors should be plausible.",
        "Hard": "Test deeper reasoning, comparison and application. Distractors must be very plausible.",
    }.get(difficulty, "")

    if material:
        source_rule = (
            "Use ONLY the study material below. Do NOT add facts, numbers or names that "
            "are not stated in it. Every question must be answerable from the material."
        )
        source_block = f"STUDY MATERIAL:\n\"\"\"\n{material}\n\"\"\""
        if topic:
            source_block = f"TOPIC: {topic}\n\n" + source_block
    else:
        source_rule = (
            "Use well-established, accurate textbook knowledge about the topic. "
            "Do not include controversial or uncertain facts."
        )
        source_block = f"TOPIC: {topic}"

    avoid_block = ""
    if avoid_questions:
        listed = "\n".join(f"- {q}" for q in avoid_questions)
        avoid_block = f"\nDo NOT repeat or rephrase these questions that already exist:\n{listed}\n"

    return f"""You are an experienced teacher who writes high-quality multiple-choice questions.

TASK: Create exactly {num_questions} multiple-choice questions at {difficulty.upper()} difficulty.
Difficulty guide: {difficulty_guide}

RULES:
1. {source_rule}
2. Each question has exactly 4 options and exactly ONE correct option.
3. All questions must be different - no duplicates or near-duplicates.
4. Spread the correct answers across A, B, C and D (do not always use the same letter).
5. Options must not contain the letters "A.", "B." etc. - only the option text.
6. Avoid "All of the above" and "None of the above".
7. The explanation must be 1-2 sentences saying why the correct answer is right.
{avoid_block}
OUTPUT FORMAT: Reply with ONLY a valid JSON array, no extra text and no markdown fences.
Each item must look exactly like this:
{{
  "question": "Question text?",
  "options": {{"A": "option text", "B": "option text", "C": "option text", "D": "option text"}},
  "correct_answer": "B",
  "explanation": "Short explanation."
}}

{source_block}
"""


# ---------------------------------------------------------------------------
# 2. Validation
# ---------------------------------------------------------------------------
def _normalize_text(text: str) -> str:
    """Lower-case and strip punctuation so duplicates can be detected."""
    return re.sub(r"[^a-z0-9 ]", "", str(text).lower()).strip()


def _clean_option(text: str) -> str:
    """Remove a leading 'A.' / 'B)' / '(C)' label if the model added one."""
    return re.sub(r"^\s*\(?[A-Da-d][\.\):]\s+", "", str(text)).strip()


def validate_question(raw):
    """
    Check ONE question dictionary.
    Returns a clean question dict:
        {"question", "options": {"A".."D"}, "correct_answer", "explanation"}
    Raises ValueError (with a reason) if the question is not acceptable.
    """
    if not isinstance(raw, dict):
        raise ValueError("question is not an object")

    # --- question text ---
    question = str(raw.get("question", "")).strip()
    if len(question) < 5:
        raise ValueError("missing or too short question text")

    # --- options: accept {"A": ...} or a list of 4 strings ---
    raw_options = raw.get("options")
    if isinstance(raw_options, list):
        if len(raw_options) != 4:
            raise ValueError("options list must have exactly 4 items")
        raw_options = dict(zip(config.OPTION_LETTERS, raw_options))
    if not isinstance(raw_options, dict):
        raise ValueError("options are missing")

    options = {}
    for letter in config.OPTION_LETTERS:
        value = raw_options.get(letter)
        if value is None or not str(value).strip():
            raise ValueError(f"option {letter} is missing or empty")
        options[letter] = _clean_option(value)
        if not options[letter]:
            raise ValueError(f"option {letter} is empty")

    if len(raw_options) != 4:
        raise ValueError("there must be exactly four options")

    if len({_normalize_text(v) for v in options.values()}) < 4:
        raise ValueError("two options are identical")

    # --- correct answer: must be one letter A-D ---
    answer = str(raw.get("correct_answer", "")).strip().upper().rstrip(".)")
    if answer not in config.OPTION_LETTERS:
        raise ValueError(f"correct_answer '{answer}' is not one of A, B, C, D")

    # --- explanation ---
    explanation = str(raw.get("explanation", "")).strip()
    if not explanation:
        raise ValueError("explanation is missing")

    return {
        "question": question,
        "options": options,
        "correct_answer": answer,
        "explanation": explanation,
    }


def validate_questions(raw_questions, existing=None):
    """
    Validate a list of raw questions.
    * invalid questions are skipped (reasons are returned)
    * duplicates (also against `existing`) are skipped
    Returns (valid_questions, problems) where problems is a list of strings.
    """
    valid = []
    problems = []
    seen = {_normalize_text(q["question"]) for q in (existing or [])}

    for number, raw in enumerate(raw_questions, start=1):
        try:
            clean = validate_question(raw)
        except ValueError as exc:
            problems.append(f"Question {number} skipped: {exc}")
            continue

        key = _normalize_text(clean["question"])
        if key in seen:
            problems.append(f"Question {number} skipped: duplicate question")
            continue
        seen.add(key)
        valid.append(clean)

    return valid, problems


# ---------------------------------------------------------------------------
# 3. Generation (calls Gemini through the service object)
# ---------------------------------------------------------------------------
def generate_quiz(gemini_service, topic: str, material: str, num_questions: int,
                  difficulty: str):
    """
    Generate `num_questions` validated MCQs.

    `gemini_service` is any object with a `generate_json(prompt) -> str` method
    (the real GeminiService, or a fake one in the tests).

    If the model returns fewer valid questions than requested, we ask again
    for the missing ones (up to GENERATION_MAX_ATTEMPTS times).
    Returns a dict: {"questions": [...], "warnings": [...]}
    """
    if num_questions not in config.QUESTION_COUNT_OPTIONS:
        raise InvalidInputError(f"Number of questions must be one of {config.QUESTION_COUNT_OPTIONS}.")
    if difficulty not in config.DIFFICULTY_LEVELS:
        raise InvalidInputError(f"Difficulty must be one of {config.DIFFICULTY_LEVELS}.")

    topic, material, input_warning = prepare_inputs(topic, material)
    warnings = [input_warning] if input_warning else []

    questions = []
    last_problem = "The model did not return usable questions."

    for _attempt in range(config.GENERATION_MAX_ATTEMPTS):
        still_needed = num_questions - len(questions)
        if still_needed <= 0:
            break

        prompt = build_prompt(
            topic, material, still_needed, difficulty,
            avoid_questions=[q["question"] for q in questions],
        )
        raw_text = gemini_service.generate_json(prompt)

        try:
            raw_questions = extract_question_list(parse_llm_json(raw_text))
        except JSONParseError as exc:
            last_problem = str(exc)
            continue  # ask the model again

        new_valid, problems = validate_questions(raw_questions, existing=questions)
        warnings.extend(problems)
        if not new_valid:
            last_problem = "None of the returned questions passed validation."
        questions.extend(new_valid)

    if not questions:
        raise QuizGenerationError(
            f"Could not generate a valid quiz. {last_problem} Please try again."
        )

    # Never return more than requested.
    questions = questions[:num_questions]

    if len(questions) < num_questions:
        warnings.append(
            f"Only {len(questions)} of {num_questions} questions could be generated "
            "with valid format. You can still take this quiz or click Generate again."
        )

    return {"questions": questions, "warnings": warnings}


# ---------------------------------------------------------------------------
# 4. Evaluation
# ---------------------------------------------------------------------------
def performance_message(percentage: float) -> str:
    """Friendly message based on the score."""
    if percentage >= 90:
        return "Outstanding! You have mastered this topic."
    if percentage >= 75:
        return "Great job! You have a strong understanding."
    if percentage >= 60:
        return "Good effort! Review the explanations to improve further."
    if percentage >= 40:
        return "Fair attempt. Revise the material and try again."
    return "Needs improvement. Read the chapter again and retake the quiz."


def evaluate_quiz(questions, answers):
    """
    Compare the user's answers with the correct answers.

    questions: list of validated question dicts
    answers  : dict {question_index: "A"/"B"/"C"/"D"}  (may be incomplete/invalid)

    Missing or invalid answers simply count as incorrect (and are marked
    "not answered"). Returns a dict with totals and a per-question review.
    """
    answers = answers or {}
    total = len(questions)
    correct_count = 0
    review = []

    for index, question in enumerate(questions):
        selected = answers.get(index)
        if isinstance(selected, str):
            selected = selected.strip().upper()
        if selected not in config.OPTION_LETTERS:
            selected = None  # missing or invalid answer

        is_correct = selected == question["correct_answer"]
        if is_correct:
            correct_count += 1

        review.append({
            "number": index + 1,
            "question": question["question"],
            "options": question["options"],
            "selected": selected,
            "correct_answer": question["correct_answer"],
            "is_correct": is_correct,
            "answered": selected is not None,
            "explanation": question["explanation"],
        })

    percentage = round((correct_count / total) * 100, 1) if total else 0.0
    return {
        "total": total,
        "correct": correct_count,
        "incorrect": total - correct_count,
        "unanswered": sum(1 for item in review if not item["answered"]),
        "percentage": percentage,
        "message": performance_message(percentage),
        "review": review,
    }
