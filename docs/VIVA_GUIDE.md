# Viva Guide - MCQ Quiz Generator (Roll No. 21)

## 1. The 30-second explanation

"My project is an MCQ Quiz Generator. A teacher pastes a chapter, chooses the number of questions and the difficulty, and the app sends a carefully designed prompt to the Gemini LLM. Gemini returns the questions as JSON. My code parses and validates that JSON, shows the quiz in a Streamlit interface, evaluates the answers automatically and shows a results dashboard with explanations."

## 2. Complete workflow (step by step)

1. **Start** - `streamlit run app.py` runs `app.py`. `init_state()` creates the session-state keys (stage, questions, answers, current question).
2. **Input** - User enters topic, pastes material (or clicks *Load sample chapter*), selects 5/10/15/20 questions and a difficulty.
3. **Generate click** - `generate_quiz()` in `quiz_service.py` starts:
   1. `prepare_inputs()` checks the input (not empty, material not too short, trimmed if too long).
   2. `build_prompt()` creates the prompt: role (teacher), task, difficulty guide, rules (only use the material, 4 options, one correct answer, no duplicates, explanation) and the exact JSON format.
   3. `GeminiService.generate_json()` sends the prompt with the `google-genai` SDK, asking for `application/json`. It retries on 429/503 with waiting time.
   4. `parse_llm_json()` converts the text to Python objects (handles ```json fences and extra text).
   5. `validate_questions()` checks each question and removes invalid or duplicate ones.
   6. If fewer questions than requested are valid, it asks Gemini again only for the missing ones (maximum 3 attempts).
4. **Quiz** - Questions are stored in `st.session_state`. The UI shows one question per page with radio buttons. The `save_answer` callback stores each choice in `session_state.answers`. Navigation only changes `session_state.current`, so **no API call happens again**.
5. **Submit** - `evaluate_quiz()` compares answers with correct answers, counts correct/incorrect/unanswered, calculates the percentage and picks a performance message.
6. **Results** - Dashboard shows score (e.g. 8/10), stat cards, message and a review of every question with the correct answer and explanation.
7. **Restart** - *Retake this quiz* keeps the questions and clears answers. *Create a new quiz* returns to the input screen.

## 3. Prompt design (2 marks)

Show these points from `build_prompt()`:

- **Role prompting** - "You are an experienced teacher".
- **Clear task** - exact number of questions and difficulty, with a guide for what Easy/Medium/Hard means.
- **Grounding** - "Use ONLY the study material", which reduces hallucination.
- **Constraints** - four options, exactly one correct answer, no duplicates, mixed answer positions, no "All of the above".
- **Output format** - strict JSON schema with an example, so the output is machine-readable.
- **Low temperature (0.4)** - more factual and consistent.
- **Re-prompt with an avoid-list** - when questions are missing, the already created questions are listed so the model does not repeat them.

## 4. Why these design decisions?

| Decision | Reason |
|----------|--------|
| Separate `services/`, `utils/`, `app.py` | Separation of concerns: UI, logic and API code can be changed and tested independently |
| `session_state` | Streamlit re-runs the script on every click; session state remembers the quiz |
| Validation of every question | LLM output cannot be trusted blindly |
| JSON mode + parser | Reliable structure; the parser still guards against fences/extra text |
| Retry with delay | Rate limits (429) and busy servers (503) are temporary |
| `.env` + `python-dotenv` | Secrets must never be in the source code or on GitHub |
| Model name in `.env` | Google retires models; changing one line fixes it |
| Fake Gemini in tests | Tests are fast, free, repeatable and need no internet |
| `google-genai` SDK | It is the current official SDK; the older `google-generativeai` package is deprecated |

## 5. Likely viva questions and answers

**Q: What is an LLM and which one did you use?**
A: A Large Language Model is a neural network trained on huge text data to understand and generate text. I used Google's Gemini through the official Python SDK.

**Q: How do you make sure the output is valid JSON?**
A: Three layers: the prompt specifies the exact format, the API is called with JSON response mode, and my parser plus validator check the result. If it still fails, the app retries and finally shows a friendly error instead of crashing.

**Q: How do you stop the model from inventing facts?**
A: The prompt says to use only the supplied material and every question must be answerable from it. Temperature is low. (I can't make hallucination impossible, which is why the explanation is shown for review.)

**Q: What if the LLM returns fewer questions or duplicates?**
A: `validate_questions()` removes invalid and duplicate questions; `generate_quiz()` asks again for the missing number and finally trims extras.

**Q: Why does the app not regenerate the quiz when you press Next?**
A: Generation is triggered only by the Generate button. Questions and answers live in `st.session_state`, so reruns just read them.

**Q: How is the score calculated?**
A: For each question, the stored letter is compared with `correct_answer`. Percentage = correct / total x 100. Unanswered questions count as incorrect.

**Q: How do you handle API errors?**
A: In `gemini_service.py`: 429/503 are retried with doubling delay; wrong key (401/403), wrong model (404) and bad requests (400) fail immediately with a clear message. The UI catches these exceptions and shows `st.error`.

**Q: Where is the API key stored? Is it safe?**
A: In a local `.env` file read by python-dotenv. `.env` is in `.gitignore`, and `.env.example` contains only a placeholder.

**Q: How did you test it?**
A: 65 pytest tests (run `pytest -v`): JSON parsing, validation, prompt content, generation using a fake LLM (valid, fenced, malformed, incomplete, always-invalid), scoring (including missing/invalid answers) and API error handling. I also tested the UI flow manually with the checklist in the README.

**Q: What are the limitations and future work?**
A: Quality depends on the model; very long chapters are trimmed to 30,000 characters; no user login or quiz history. Future work: PDF upload, PDF export of the quiz, timer, saving results.

## 6. Demo script (about 3 minutes)

1. Show the folder structure in VS Code and say what each folder does (30 s).
2. Run `streamlit run app.py`.
3. Click **Load sample chapter**, choose 5 questions, Medium, click **Generate Quiz**.
4. Answer a few questions, press Previous/Next to show answers are preserved.
5. Submit; show score, percentage, message and the detailed review with explanations.
6. Click **Create a new quiz**, enter only a topic, generate again.
7. In the terminal run `pytest -v` to show the passing tests.
8. Show `.env.example` and `.gitignore` to explain key safety.
