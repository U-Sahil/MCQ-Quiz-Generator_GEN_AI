"""
app.py - Streamlit user interface for the MCQ Quiz Generator.

Run with:   streamlit run app.py

The app has three screens ("stages") stored in st.session_state:
    "setup"   -> user enters topic / material and clicks Generate
    "quiz"    -> user answers questions one at a time
    "results" -> score dashboard + detailed review

Because Streamlit re-runs this whole file on every click, everything that
must survive (questions, answers, current question number, stage) is kept in
st.session_state. Questions are generated ONLY when the Generate button is
pressed, so moving between questions never calls the API again.
"""

import streamlit as st

import config
from services.gemini_service import GeminiService, GeminiServiceError
from services.quiz_service import (
    InvalidInputError,
    QuizGenerationError,
    evaluate_quiz,
    generate_quiz,
)

# ---------------------------------------------------------------------------
# Page setup and styling
# ---------------------------------------------------------------------------
st.set_page_config(page_title="MCQ Quiz Generator", page_icon="", layout="centered")

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.block-container { padding-top: 2rem; max-width: 820px; }

.hero {
    background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%);
    color: white; padding: 1.6rem 1.8rem; border-radius: 16px; margin-bottom: 1.4rem;
    box-shadow: 0 8px 24px rgba(79, 70, 229, 0.25);
}
.hero h1 { margin: 0; font-size: 1.9rem; font-weight: 700; color: white; }
.hero p  { margin: 0.3rem 0 0 0; opacity: 0.92; font-size: 1rem; }

.q-card {
    background: #ffffff; border: 1px solid #e5e7eb; border-left: 6px solid #4f46e5;
    border-radius: 14px; padding: 1.2rem 1.4rem; margin: 0.8rem 0 0.4rem 0;
    box-shadow: 0 2px 10px rgba(0,0,0,0.05); color: #111827;
}
.q-number { color: #4f46e5; font-weight: 600; font-size: 0.85rem; letter-spacing: 0.04em; }
.q-text   { font-size: 1.15rem; font-weight: 600; margin-top: 0.25rem; color: #111827; }

.stat-card {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 14px;
    padding: 1rem; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.05);
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: #4f46e5; }
.stat-label { color: #6b7280; font-size: 0.85rem; }

.score-banner {
    border-radius: 16px; padding: 1.4rem; text-align: center; margin-bottom: 1rem;
    background: linear-gradient(135deg, #eef2ff 0%, #f5f3ff 100%); border: 1px solid #c7d2fe;
}
.score-big { font-size: 2.6rem; font-weight: 700; color: #4338ca; }
.score-msg { color: #374151; font-size: 1.05rem; }

.review-ok  { background:#ecfdf5; border:1px solid #6ee7b7; border-radius:12px; padding:0.9rem 1.1rem; color:#064e3b; }
.review-bad { background:#fef2f2; border:1px solid #fca5a5; border-radius:12px; padding:0.9rem 1.1rem; color:#7f1d1d; }
.review-skip{ background:#fffbeb; border:1px solid #fcd34d; border-radius:12px; padding:0.9rem 1.1rem; color:#78350f; }

div.stButton > button { border-radius: 10px; font-weight: 600; padding: 0.5rem 1.2rem; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------
def init_state():
    """Create all session-state keys once (only if they do not exist yet)."""
    defaults = {
        "stage": "setup",
        "questions": [],
        "answers": {},          # {question_index: "A"/"B"/"C"/"D"}
        "current": 0,           # index of the question being shown
        "result": None,         # evaluation dictionary after submit
        "topic_input": "",
        "material_input": "",
        "quiz_topic": "",
        "quiz_difficulty": "",
        "warnings": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def load_sample_into_form():
    """Button callback: fill the form with the demo chapter."""
    try:
        with open(config.SAMPLE_CHAPTER_PATH, "r", encoding="utf-8") as file:
            st.session_state.material_input = file.read()
        st.session_state.topic_input = "Photosynthesis"
    except OSError:
        st.session_state.sample_error = True


def go_to_question(index: int):
    """Button callback: jump to a question number."""
    st.session_state.current = index


def save_answer(index: int):
    """Radio callback: store the selected letter for question `index`."""
    choice = st.session_state.get(f"radio_{index}")
    if choice in config.OPTION_LETTERS:
        st.session_state.answers[index] = choice


def submit_quiz():
    """Button callback: evaluate answers and switch to the results screen."""
    st.session_state.result = evaluate_quiz(
        st.session_state.questions, st.session_state.answers
    )
    st.session_state.stage = "results"


def retake_same_quiz():
    """Keep the questions, clear the answers."""
    st.session_state.answers = {}
    st.session_state.current = 0
    st.session_state.result = None
    st.session_state.stage = "quiz"


def new_quiz():
    """Throw everything away and go back to the input form."""
    st.session_state.questions = []
    st.session_state.answers = {}
    st.session_state.current = 0
    st.session_state.result = None
    st.session_state.warnings = []
    st.session_state.stage = "setup"


def render_setup():
    st.markdown("#### 1. Tell us what the quiz is about")

    if not config.GEMINI_API_KEY:
        st.warning(
            "No Gemini API key found. Copy `.env.example` to `.env`, add your key "
            "and restart the app."
        )

    st.text_input(
        "Topic / chapter name",
        key="topic_input",
        placeholder="e.g. Photosynthesis",
    )
    st.text_area(
        "Study material (optional but recommended)",
        key="material_input",
        height=260,
        placeholder="Paste the chapter or notes here. If you leave this empty, "
                    "questions are created from the topic name alone.",
    )
    st.button(" Load sample chapter", on_click=load_sample_into_form)
    if st.session_state.get("sample_error"):
        st.error("Could not load the sample chapter file.")
        st.session_state.sample_error = False

    col1, col2 = st.columns(2)
    with col1:
        num_questions = st.selectbox("Number of questions", config.QUESTION_COUNT_OPTIONS, index=0)
    with col2:
        difficulty = st.selectbox("Difficulty", config.DIFFICULTY_LEVELS, index=1)

    if st.button("Generate Quiz", type="primary", use_container_width=True):
        topic = st.session_state.topic_input
        material = st.session_state.material_input
        try:
            with st.spinner("Gemini is writing your questions... this can take 10-30 seconds."):
                service = GeminiService()
                outcome = generate_quiz(service, topic, material, num_questions, difficulty)
        except InvalidInputError as exc:
            st.error(str(exc))
        except (GeminiServiceError, QuizGenerationError) as exc:
            st.error(str(exc))
        except Exception as exc:  # last safety net: never show a raw crash page
            st.error(f"Something unexpected went wrong: {exc}")
        else:
            st.session_state.questions = outcome["questions"]
            st.session_state.warnings = outcome["warnings"]
            st.session_state.quiz_topic = topic.strip() or "Pasted study material"
            st.session_state.quiz_difficulty = difficulty
            st.session_state.answers = {}
            st.session_state.current = 0
            st.session_state.stage = "quiz"
            st.rerun()


# ---------------------------------------------------------------------------
# Screen 2: quiz
# ---------------------------------------------------------------------------
def render_quiz():
    questions = st.session_state.questions
    total = len(questions)
    current = st.session_state.current
    answers = st.session_state.answers
    question = questions[current]

    st.success(
        f"Quiz ready: **{st.session_state.quiz_topic}** · {total} questions · "
        f"{st.session_state.quiz_difficulty} difficulty"
    )
    for warning in st.session_state.warnings:
        st.warning(warning)

    # Progress = how many questions have an answer.
    answered = len(answers)
    st.progress(answered / total, text=f"Answered {answered} of {total}")

    # Question card
    st.markdown(
        f"""<div class="q-card">
              <div class="q-number">QUESTION {current + 1} OF {total}</div>
              <div class="q-text">{_escape(question['question'])}</div>
            </div>""",
        unsafe_allow_html=True,
    )

    letters = config.OPTION_LETTERS
    saved = answers.get(current)
    st.radio(
        "Choose your answer",
        options=letters,
        format_func=lambda letter: f"{letter}.  {question['options'][letter]}",
        index=letters.index(saved) if saved in letters else None,
        key=f"radio_{current}",
        on_change=save_answer,
        args=(current,),
        label_visibility="collapsed",
    )

    # Previous / Next buttons
    prev_col, mid_col, next_col = st.columns([1, 2, 1])
    with prev_col:
        st.button("Previous", disabled=current == 0,
                  on_click=go_to_question, args=(current - 1,), use_container_width=True)
    with next_col:
        st.button("Next", disabled=current == total - 1,
                  on_click=go_to_question, args=(current + 1,), use_container_width=True)

    # Question navigator: numbered buttons marked by an answered suffix
    with st.expander("Jump to a question", expanded=False):
        per_row = 10
        for start in range(0, total, per_row):
            cols = st.columns(per_row)
            for offset, col in enumerate(cols):
                idx = start + offset
                if idx >= total:
                    break
                label = f"{idx + 1}{' *' if idx in answers else ''}"
                col.button(label, key=f"nav_{idx}", on_click=go_to_question, args=(idx,),
                           type="primary" if idx == current else "secondary")

    st.divider()
    unanswered = total - answered
    if unanswered:
        st.caption(f"{unanswered} question(s) still unanswered - they will count as incorrect.")
    st.button("Submit Quiz", type="primary", use_container_width=True, on_click=submit_quiz)
    st.button("Start over with a new quiz", on_click=new_quiz)


# ---------------------------------------------------------------------------
# Screen 3: results
# ---------------------------------------------------------------------------
def render_results():
    result = st.session_state.result

    st.markdown(
        f"""<div class="score-banner">
              <div class="score-big">Score: {result['correct']}/{result['total']}</div>
              <div class="score-msg">{result['percentage']}% &nbsp;·&nbsp; {result['message']}</div>
            </div>""",
        unsafe_allow_html=True,
    )

    cols = st.columns(4)
    stats = [
        ("Total Questions", result["total"]),
        ("Correct", result["correct"]),
        ("Incorrect", result["incorrect"]),
        ("Percentage", f"{result['percentage']}%"),
    ]
    for col, (label, value) in zip(cols, stats):
        col.markdown(
            f"""<div class="stat-card"><div class="stat-value">{value}</div>
                <div class="stat-label">{label}</div></div>""",
            unsafe_allow_html=True,
        )
    if result["unanswered"]:
        st.caption(f"{result['unanswered']} question(s) were left unanswered.")

    st.markdown("#### Detailed answer review")
    for item in result["review"]:
        if not item["answered"]:
            css, status = "review-skip", "Not answered"
        elif item["is_correct"]:
            css, status = "review-ok", "Correct"
        else:
            css, status = "review-bad", "Incorrect"

        with st.expander(f"Q{item['number']}. {item['question']}  —  {status}"):
            correct = item["correct_answer"]
            selected = item["selected"]
            your_text = (f"{selected}. {item['options'][selected]}" if selected
                         else "No answer selected")
            st.markdown(
                f"""<div class="{css}">
                    <b>Your answer:</b> {_escape(your_text)}<br>
                    <b>Correct answer:</b> {correct}. {_escape(item['options'][correct])}<br><br>
                    <b>Explanation:</b> {_escape(item['explanation'])}
                    </div>""",
                unsafe_allow_html=True,
            )
            st.markdown("**All options:**")
            for letter in config.OPTION_LETTERS:
                marker = " (correct)" if letter == correct else (" (your choice)" if letter == selected else "")
                st.write(f"{letter}. {item['options'][letter]}{marker}")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.button("Retake this quiz", on_click=retake_same_quiz, use_container_width=True)
    with col2:
        st.button("Create a new quiz", on_click=new_quiz, type="primary", use_container_width=True)


def _escape(text) -> str:
    """Escape HTML so quiz text can never break the page layout."""
    import html
    return html.escape(str(text))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    init_state()
    st.markdown(
        """<div class="hero"><h1>MCQ Quiz Generator</h1>
           <p>Turn any chapter or topic into a ready-to-take quiz in seconds, powered by Gemini.</p></div>""",
        unsafe_allow_html=True,
    )

    stage = st.session_state.stage
    if stage == "quiz" and st.session_state.questions:
        render_quiz()
    elif stage == "results" and st.session_state.result:
        render_results()
    else:
        st.session_state.stage = "setup"
        render_setup()


main()
