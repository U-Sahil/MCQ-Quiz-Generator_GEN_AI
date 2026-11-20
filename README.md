# MCQ Quiz Generator

An AI-powered web app that turns a pasted chapter or topic into a ready-to-take multiple-choice quiz, scores it automatically and explains every answer.

**Roll No:** 21 · **Category:** Education & Learning · **Type:** GenAI Mini Project

---

## 1. Introduction

Teachers spend a lot of time preparing quizzes. This application uses a Large Language Model (Google Gemini) to generate MCQs, with the correct answer and a short explanation, directly from study material that the teacher or student pastes in. The quiz can be taken immediately in the browser and is evaluated automatically.

## 2. Problem Statement

> Teachers spend considerable time preparing quizzes. Build an application that generates multiple-choice questions (MCQs) with answers from a pasted chapter or topic using a Large Language Model (LLM).

## 3. Features

| # | Feature | What it does |
|---|---------|--------------|
| 1 | Input section | Topic name, pasted study material, 5/10/15/20 questions, Easy/Medium/Hard, **Generate Quiz** button, one-click sample chapter |
| 2 | AI generation | Gemini creates questions with 4 options, exactly one correct answer and an explanation, returned as JSON |
| 3 | Interactive quiz | One question at a time, radio buttons, Previous/Next, jump-to-question, progress bar, Submit |
| 4 | Automatic evaluation | Score, correct/incorrect count, percentage, correct answer and explanation for every question |
| 5 | Results dashboard | Stat cards, performance message, detailed review, retake or create a new quiz |

Quality and safety features:

- Prompt tells the model to use **only the supplied material** (no invented facts).
- Every question is **validated** (4 options, one valid answer letter, explanation present); invalid or duplicate questions are skipped and the missing ones are re-requested.
- Handles malformed JSON, markdown fences, empty answers, rate limits, bad API key and retired model names with friendly messages.
- Quiz state lives in `st.session_state`, so moving between questions **never calls the API again**.
- API key comes from `.env` only, never from the source code.

## 4. Technology Stack

| Technology | Used for |
|------------|----------|
| Python 3.10+ | Application logic |
| Streamlit | Web interface |
| Gemini API (`google-genai` SDK) | Question generation |
| JSON | Structured LLM output |
| python-dotenv | Secure API key loading |
| pytest | Automated tests |

## 5. Project Architecture

```
mcq-quiz-generator/
├── app.py                      # Streamlit UI (3 screens: setup, quiz, results)
├── config.py                   # Settings: model name, limits, options
├── requirements.txt            # Python dependencies
├── .env.example                # Template for your API key (copy to .env)
├── .gitignore                  # Keeps .env and venv out of GitHub
├── pytest.ini                  # Test configuration
├── README.md
├── services/
│   ├── gemini_service.py       # Talks to Gemini (retries, error handling)
│   └── quiz_service.py         # Prompt, validation, generation, scoring
├── utils/
│   └── json_parser.py          # Cleans / parses the LLM's JSON text
├── tests/
│   ├── test_quiz_service.py    # Parsing, validation, generation, scoring tests
│   └── test_gemini_service.py  # API error-handling tests (no internet needed)
├── sample_data/
│   └── sample_chapter.txt      # Demo chapter: Photosynthesis
├── screenshots/                # Put your screenshots here
└── docs/
    └── VIVA_GUIDE.md           # Workflow explanation + viva Q&A
```

### Data flow

```
User input ─► app.py ─► quiz_service.build_prompt ─► gemini_service ─► Gemini API
                                                                          │
Results ◄─ app.py ◄─ quiz_service.evaluate_quiz ◄─ validate ◄─ json_parser ◄┘
```

### Purpose of each important file

| File | Purpose |
|------|---------|
| `app.py` | Only UI code. Builds the three screens, stores state in `st.session_state`, calls the services. |
| `config.py` | One place for the model name, retry counts, question options, input limits. |
| `services/gemini_service.py` | The only file that calls Gemini. Sends the prompt, asks for JSON, retries on 429/503, converts errors to readable messages. |
| `services/quiz_service.py` | Prompt design, question validation, duplicate removal, retry for missing questions, scoring and performance message. No Streamlit code, so it is easy to test. |
| `utils/json_parser.py` | Removes ```json fences, finds JSON inside extra text, accepts a list or `{"questions": [...]}`, raises a clear error otherwise. |
| `tests/` | 65 automated tests that run without internet or an API key. |

## 6. Installation (Windows, VS Code)

1. Install **Python 3.10 or newer** from python.org (tick *Add Python to PATH*).
2. Open the `mcq-quiz-generator` folder in VS Code (`File → Open Folder`).
3. Open the VS Code terminal (`Ctrl + ~`) and run:

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

> If PowerShell blocks activation, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, or use **Command Prompt** instead.

In VS Code press `Ctrl+Shift+P → Python: Select Interpreter` and choose the `venv` one.

## 7. API Key Configuration

1. Get a free key at <https://aistudio.google.com/apikey>.
2. Copy the template:

```powershell
copy .env.example .env
```

3. Open `.env` and replace the placeholder:

```
GEMINI_API_KEY=AIza...your real key...
GEMINI_MODEL=gemini-3.5-flash
```

`.env` is listed in `.gitignore`, so your key is never uploaded to GitHub.

If you ever see *"model not found"*, Google has retired that model: set `GEMINI_MODEL` in `.env` to a current one from <https://ai.google.dev/gemini-api/docs/models>.

## 8. How to Run

```powershell
streamlit run app.py
```

The browser opens at <http://localhost:8501>. Click **Load sample chapter**, choose the number of questions and difficulty, then **Generate Quiz**.

## 9. Sample Screenshots

Take screenshots during your demo and save them in `screenshots/`:

| Screen | File name |
|--------|-----------|
| Input form | `screenshots/01_input.png` |
| Quiz question | `screenshots/02_quiz.png` |
| Results dashboard | `screenshots/03_results.png` |
| Answer review | `screenshots/04_review.png` |

Then add them here:

```markdown
![Input](screenshots/01_input.png)
![Quiz](screenshots/02_quiz.png)
![Results](screenshots/03_results.png)
![Review](screenshots/04_review.png)
```

## 10. Testing

```powershell
pytest -v
```

No API key or internet is needed; the Gemini service is replaced by a fake.

### Sample test scenarios

| # | Scenario | Expected result |
|---|----------|-----------------|
| 1 | Valid LLM response with 5 questions | 5 questions, no warnings, one API call |
| 2 | JSON wrapped in ```json fences | Parsed correctly |
| 3 | Malformed JSON first, valid JSON second | Automatic retry succeeds |
| 4 | Only 3 valid questions returned of 5 | Missing 2 are requested again |
| 5 | Model never returns usable output | Friendly `QuizGenerationError`, no crash |

Test groups (65 tests in total): JSON parsing (9), question validation (15), input checks and prompt (6), generation with a fake LLM (11), scoring including the 8/10 = 80% example plus missing and invalid answers (15), Gemini error handling: rate limit, bad key, wrong model, empty answer (9).
