"""
json_parser.py - Turns the raw text returned by the LLM into Python objects.

LLMs sometimes wrap JSON in ```json fences, add a sentence before/after it,
or return a dict like {"questions": [...]} instead of a plain list. This
module handles all of those cases and raises one clear error otherwise.
"""

import json
import re


class JSONParseError(Exception):
    """Raised when no valid JSON can be extracted from the LLM response."""


def _strip_code_fences(text: str) -> str:
    """Remove ```json ... ``` markers if the model added them."""
    text = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.DOTALL | re.IGNORECASE)
    return fence.group(1) if fence else text


def _find_json_block(text: str) -> str:
    """
    Find the first complete JSON array/object inside text that may contain
    extra words around it. Uses bracket matching, ignoring brackets that are
    inside string values.
    """
    starts = [i for i in (text.find("["), text.find("{")) if i != -1]
    if not starts:
        raise JSONParseError("No JSON found in the response.")
    start = min(starts)
    open_char = text[start]
    close_char = "]" if open_char == "[" else "}"

    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise JSONParseError("The JSON in the response is incomplete (cut off).")


def parse_llm_json(raw_text: str):
    """Parse the LLM response and return the decoded JSON (list or dict)."""
    if not raw_text or not raw_text.strip():
        raise JSONParseError("The model returned an empty response.")

    cleaned = _strip_code_fences(raw_text)

    # First try: the whole text is valid JSON.
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Second try: extract the JSON part from surrounding text.
    block = _find_json_block(cleaned)
    try:
        return json.loads(block)
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"The response contains invalid JSON: {exc}") from exc


def extract_question_list(parsed) -> list:
    """
    Accept either a plain list of questions or a dict that holds the list
    (e.g. {"questions": [...]}) and always return a list.
    """
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        for key in ("questions", "quiz", "mcqs", "items", "data"):
            if isinstance(parsed.get(key), list):
                return parsed[key]
        # A single question object returned on its own.
        if "question" in parsed:
            return [parsed]
    raise JSONParseError("The JSON does not contain a list of questions.")
