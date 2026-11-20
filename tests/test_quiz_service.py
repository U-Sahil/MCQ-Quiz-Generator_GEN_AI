"""
Unit tests for the MCQ Quiz Generator.

No internet or API key is needed: the Gemini service is replaced by a small
FakeGemini class that returns pre-written answers.

Run all tests from the project folder with:   pytest -v

The five SAMPLE SCENARIOS asked for in the assignment are marked "SCENARIO n".
"""

import json

import pytest

import config
from services.quiz_service import (
    InvalidInputError,
    QuizGenerationError,
    build_prompt,
    evaluate_quiz,
    generate_quiz,
    performance_message,
    prepare_inputs,
    validate_question,
    validate_questions,
)
from utils.json_parser import JSONParseError, extract_question_list, parse_llm_json

LONG_MATERIAL = "Photosynthesis converts light energy into chemical energy in plants. " * 6


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def make_question(n=1, answer="A"):
    """Build one valid question dictionary."""
    return {
        "question": f"What is the capital number {n}?",
        "options": {"A": f"alpha {n}", "B": f"bravo {n}", "C": f"charlie {n}", "D": f"delta {n}"},
        "correct_answer": answer,
        "explanation": f"Because of reason {n}.",
    }


def make_questions(count):
    return [make_question(i + 1, config.OPTION_LETTERS[i % 4]) for i in range(count)]


class FakeGemini:
    """Pretends to be GeminiService. Returns the given responses one by one."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_json(self, prompt):
        self.calls += 1
        index = min(self.calls - 1, len(self.responses) - 1)
        return self.responses[index]


# ---------------------------------------------------------------------------
# JSON parsing
# ---------------------------------------------------------------------------
class TestJsonParser:
    def test_plain_json_list(self):
        assert parse_llm_json('[{"a": 1}]') == [{"a": 1}]

    def test_json_inside_markdown_fence(self):
        text = '```json\n[{"a": 1}]\n```'
        assert parse_llm_json(text) == [{"a": 1}]

    def test_json_with_extra_words_around_it(self):
        text = 'Sure! Here is your quiz: [{"a": "x ] y"}] Hope it helps.'
        assert parse_llm_json(text) == [{"a": "x ] y"}]

    def test_empty_response_raises(self):
        with pytest.raises(JSONParseError):
            parse_llm_json("   ")

    def test_text_without_json_raises(self):
        with pytest.raises(JSONParseError):
            parse_llm_json("I am sorry, I cannot do that.")

    def test_truncated_json_raises(self):
        with pytest.raises(JSONParseError):
            parse_llm_json('[{"question": "Cut off here')

    def test_extract_list_from_wrapper_dict(self):
        assert extract_question_list({"questions": [1, 2]}) == [1, 2]

    def test_extract_single_question_object(self):
        assert extract_question_list({"question": "Q?"}) == [{"question": "Q?"}]

    def test_extract_list_rejects_other_json(self):
        with pytest.raises(JSONParseError):
            extract_question_list({"hello": "world"})


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class TestValidation:
    def test_valid_question_passes(self):
        clean = validate_question(make_question(1, "C"))
        assert clean["correct_answer"] == "C"
        assert set(clean["options"]) == {"A", "B", "C", "D"}

    def test_options_as_list_are_accepted(self):
        raw = make_question()
        raw["options"] = ["one", "two", "three", "four"]
        assert validate_question(raw)["options"]["D"] == "four"

    def test_option_labels_are_removed(self):
        raw = make_question()
        raw["options"]["A"] = "A. Chlorophyll"
        assert validate_question(raw)["options"]["A"] == "Chlorophyll"

    def test_lowercase_answer_is_normalised(self):
        raw = make_question()
        raw["correct_answer"] = "b"
        assert validate_question(raw)["correct_answer"] == "B"

    @pytest.mark.parametrize("field", ["question", "options", "correct_answer", "explanation"])
    def test_missing_field_is_rejected(self, field):
        raw = make_question()
        del raw[field]
        with pytest.raises(ValueError):
            validate_question(raw)

    def test_wrong_answer_letter_rejected(self):
        raw = make_question()
        raw["correct_answer"] = "E"
        with pytest.raises(ValueError):
            validate_question(raw)

    def test_only_three_options_rejected(self):
        raw = make_question()
        del raw["options"]["D"]
        with pytest.raises(ValueError):
            validate_question(raw)

    def test_five_options_rejected(self):
        raw = make_question()
        raw["options"]["E"] = "extra"
        with pytest.raises(ValueError):
            validate_question(raw)

    def test_identical_options_rejected(self):
        raw = make_question()
        raw["options"]["B"] = raw["options"]["A"]
        with pytest.raises(ValueError):
            validate_question(raw)

    def test_non_dict_rejected(self):
        with pytest.raises(ValueError):
            validate_question("just a string")

    def test_duplicates_and_invalid_are_filtered(self):
        raw = [make_question(1), make_question(1), {"question": "bad"}, make_question(2)]
        valid, problems = validate_questions(raw)
        assert len(valid) == 2
        assert len(problems) == 2

    def test_duplicates_against_existing_questions(self):
        existing = [validate_question(make_question(1))]
        valid, problems = validate_questions([make_question(1)], existing=existing)
        assert valid == [] and len(problems) == 1


# ---------------------------------------------------------------------------
# Input checking and prompt design
# ---------------------------------------------------------------------------
class TestInputsAndPrompt:
    def test_empty_input_rejected(self):
        with pytest.raises(InvalidInputError):
            prepare_inputs("", "")

    def test_topic_only_is_allowed(self):
        topic, material, warning = prepare_inputs("Photosynthesis", "")
        assert topic == "Photosynthesis" and material == "" and warning is None

    def test_very_short_material_rejected(self):
        with pytest.raises(InvalidInputError):
            prepare_inputs("Bio", "too short")

    def test_very_long_material_is_trimmed(self):
        _, material, warning = prepare_inputs("", "x" * (config.MAX_MATERIAL_CHARS + 500))
        assert len(material) == config.MAX_MATERIAL_CHARS and warning

    def test_prompt_with_material_forbids_outside_facts(self):
        prompt = build_prompt("Bio", LONG_MATERIAL, 5, "Hard")
        assert "ONLY the study material" in prompt
        assert LONG_MATERIAL.strip() in prompt
        assert "exactly 5" in prompt and "HARD" in prompt

    def test_prompt_topic_only(self):
        prompt = build_prompt("Photosynthesis", "", 5, "Easy")
        assert "TOPIC: Photosynthesis" in prompt and "STUDY MATERIAL" not in prompt


# ---------------------------------------------------------------------------
# Generation (with a fake LLM)
# ---------------------------------------------------------------------------
class TestGeneration:
    def test_scenario_1_valid_response_5_questions(self):
        """SCENARIO 1: normal, valid LLM response."""
        fake = FakeGemini(json.dumps(make_questions(5)))
        result = generate_quiz(fake, "Biology", LONG_MATERIAL, 5, "Easy")
        assert len(result["questions"]) == 5
        assert result["warnings"] == []
        assert fake.calls == 1

    def test_scenario_2_response_in_markdown_fence(self):
        """SCENARIO 2: LLM wraps the JSON in ```json fences."""
        fake = FakeGemini("```json\n" + json.dumps(make_questions(5)) + "\n```")
        assert len(generate_quiz(fake, "Biology", LONG_MATERIAL, 5, "Medium")["questions"]) == 5

    def test_scenario_3_malformed_json_then_retry_succeeds(self):
        """SCENARIO 3: first answer is broken JSON, second answer is fine."""
        fake = FakeGemini("[{ this is not json", json.dumps(make_questions(5)))
        result = generate_quiz(fake, "Biology", LONG_MATERIAL, 5, "Hard")
        assert len(result["questions"]) == 5 and fake.calls == 2

    def test_scenario_4_incomplete_response_is_topped_up(self):
        """SCENARIO 4: model returns only 3 valid questions, we ask for the rest."""
        first = make_questions(3)
        second = [make_question(10), make_question(11)]
        fake = FakeGemini(json.dumps(first), json.dumps(second))
        result = generate_quiz(fake, "Biology", LONG_MATERIAL, 5, "Medium")
        assert len(result["questions"]) == 5 and fake.calls == 2

    def test_scenario_5_always_invalid_raises_friendly_error(self):
        """SCENARIO 5: model never returns usable output."""
        fake = FakeGemini("Sorry, I can't help with that.")
        with pytest.raises(QuizGenerationError):
            generate_quiz(fake, "Biology", LONG_MATERIAL, 5, "Easy")
        assert fake.calls == config.GENERATION_MAX_ATTEMPTS

    def test_extra_questions_are_trimmed(self):
        fake = FakeGemini(json.dumps(make_questions(8)))
        assert len(generate_quiz(fake, "Bio", LONG_MATERIAL, 5, "Easy")["questions"]) == 5

    def test_partial_result_gives_warning(self):
        fake = FakeGemini(json.dumps(make_questions(3)))
        result = generate_quiz(fake, "Bio", LONG_MATERIAL, 5, "Easy")
        assert len(result["questions"]) == 3
        assert any("Only 3 of 5" in w for w in result["warnings"])

    def test_invalid_questions_inside_response_are_skipped(self):
        data = make_questions(5) + [{"question": "broken"}]
        fake = FakeGemini(json.dumps(data))
        result = generate_quiz(fake, "Bio", LONG_MATERIAL, 5, "Easy")
        assert len(result["questions"]) == 5

    def test_wrapper_dict_response(self):
        fake = FakeGemini(json.dumps({"questions": make_questions(5)}))
        assert len(generate_quiz(fake, "Bio", LONG_MATERIAL, 5, "Easy")["questions"]) == 5

    def test_invalid_question_count_rejected(self):
        with pytest.raises(InvalidInputError):
            generate_quiz(FakeGemini("[]"), "Bio", LONG_MATERIAL, 7, "Easy")

    def test_invalid_difficulty_rejected(self):
        with pytest.raises(InvalidInputError):
            generate_quiz(FakeGemini("[]"), "Bio", LONG_MATERIAL, 5, "Impossible")


# ---------------------------------------------------------------------------
# Evaluation / scoring
# ---------------------------------------------------------------------------
class TestEvaluation:
    def setup_method(self):
        # correct answers: A, B, C, D, A
        self.questions = [validate_question(q) for q in make_questions(5)]

    def test_all_correct(self):
        answers = {0: "A", 1: "B", 2: "C", 3: "D", 4: "A"}
        result = evaluate_quiz(self.questions, answers)
        assert (result["correct"], result["incorrect"], result["percentage"]) == (5, 0, 100.0)

    def test_assignment_example_8_out_of_10(self):
        questions = [validate_question(q) for q in make_questions(10)]
        answers = {i: q["correct_answer"] for i, q in enumerate(questions)}
        answers[0] = "D" if questions[0]["correct_answer"] != "D" else "A"
        answers[1] = "D" if questions[1]["correct_answer"] != "D" else "A"
        result = evaluate_quiz(questions, answers)
        assert (result["correct"], result["incorrect"], result["percentage"]) == (8, 2, 80.0)

    def test_all_wrong(self):
        answers = {0: "D", 1: "A", 2: "A", 3: "A", 4: "B"}
        result = evaluate_quiz(self.questions, answers)
        assert result["correct"] == 0 and result["percentage"] == 0.0

    def test_missing_answers_count_as_incorrect(self):
        result = evaluate_quiz(self.questions, {0: "A"})
        assert result["correct"] == 1
        assert result["incorrect"] == 4
        assert result["unanswered"] == 4
        assert result["review"][1]["selected"] is None

    def test_no_answers_at_all(self):
        result = evaluate_quiz(self.questions, {})
        assert result["correct"] == 0 and result["unanswered"] == 5

    def test_none_answers_dict(self):
        assert evaluate_quiz(self.questions, None)["correct"] == 0

    def test_invalid_answer_values_are_ignored(self):
        result = evaluate_quiz(self.questions, {0: "Z", 1: 5, 2: "", 3: None, 4: "A"})
        assert result["correct"] == 1 and result["unanswered"] == 4

    def test_lowercase_answer_accepted(self):
        assert evaluate_quiz(self.questions, {0: "a"})["correct"] == 1

    def test_review_contains_explanation_and_correct_answer(self):
        review = evaluate_quiz(self.questions, {0: "B"})["review"][0]
        assert review["correct_answer"] == "A"
        assert review["is_correct"] is False
        assert review["explanation"]

    def test_empty_quiz_does_not_crash(self):
        result = evaluate_quiz([], {})
        assert result["total"] == 0 and result["percentage"] == 0.0

    @pytest.mark.parametrize("percent,word", [
        (100, "Outstanding"), (80, "Great"), (65, "Good effort"),
        (45, "Fair"), (10, "Needs improvement"),
    ])
    def test_performance_messages(self, percent, word):
        assert word in performance_message(percent)
