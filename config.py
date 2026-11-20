"""
config.py - Central place for all settings of the MCQ Quiz Generator.

The Gemini API key is NEVER written in the source code. It is read from a
`.env` file (see `.env.example`) using python-dotenv.
"""

import os

from dotenv import load_dotenv

# Load variables from the .env file (if it exists) into the environment.
load_dotenv()

# ---------------------------------------------------------------------------
# Gemini settings
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Model name can be changed from the .env file without touching the code.
# Google retires old models over time, so if you ever get a "model not found"
# error, just set GEMINI_MODEL in .env to a newer model.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash").strip()

# Lower temperature = more factual, less creative output.
GEMINI_TEMPERATURE = 0.4

# How many times we retry when the API is busy / rate limited.
API_MAX_RETRIES = 3
API_RETRY_DELAY_SECONDS = 4  # doubled after every failed attempt

# How many times we ask the model again when its answer is unusable.
GENERATION_MAX_ATTEMPTS = 3

# ---------------------------------------------------------------------------
# Quiz settings
# ---------------------------------------------------------------------------
QUESTION_COUNT_OPTIONS = [5, 10, 15, 20]
DIFFICULTY_LEVELS = ["Easy", "Medium", "Hard"]
OPTION_LETTERS = ["A", "B", "C", "D"]

# Study material limits (characters).
MIN_MATERIAL_CHARS = 200   # shorter text is too little to build a good quiz
MAX_MATERIAL_CHARS = 30000  # longer text is trimmed to keep the prompt small

SAMPLE_CHAPTER_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "sample_data", "sample_chapter.txt"
)
