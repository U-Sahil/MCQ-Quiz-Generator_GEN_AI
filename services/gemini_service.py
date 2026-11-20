"""
gemini_service.py - The only file that talks to the Gemini API.

It uses the official, current Google Gen AI SDK (`pip install google-genai`,
imported as `from google import genai`). The old `google-generativeai`
package is deprecated and is NOT used here.

Responsibilities:
  * create the Gemini client from the API key in .env
  * send a prompt and ask for a JSON answer
  * retry when the API is busy or rate limited
  * convert SDK errors into simple, friendly error messages
"""

import time

from google import genai
from google.genai import errors, types

import config

class GeminiServiceError(Exception):
    """Base class for all problems while calling Gemini."""


class MissingAPIKeyError(GeminiServiceError):
    """The GEMINI_API_KEY is not configured."""


class InvalidAPIKeyError(GeminiServiceError):
    """Gemini rejected the API key."""


class RateLimitError(GeminiServiceError):
    """Too many requests / quota exhausted."""


class ModelNotFoundError(GeminiServiceError):
    """The configured model name does not exist (or was retired)."""


class GeminiService:
    """Small wrapper around the Gemini client."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = (api_key if api_key is not None else config.GEMINI_API_KEY).strip()
        self.model = model or config.GEMINI_MODEL
        self._client = None  # created lazily on the first request

    # ------------------------------------------------------------------
    def _get_client(self):
        if not self.api_key or self.api_key.startswith("your_"):
            raise MissingAPIKeyError(
                "Gemini API key not found. Create a .env file (copy .env.example) "
                "and set GEMINI_API_KEY=your real key."
            )
        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    # ------------------------------------------------------------------
    def generate_json(self, prompt: str) -> str:
        """
        Send `prompt` to Gemini and return the raw text of the answer.
        The model is asked to reply in JSON (response_mime_type).
        """
        client = self._get_client()
        generation_config = types.GenerateContentConfig(
            temperature=config.GEMINI_TEMPERATURE,
            response_mime_type="application/json",
        )

        delay = config.API_RETRY_DELAY_SECONDS
        last_error = None

        for attempt in range(1, config.API_MAX_RETRIES + 1):
            try:
                response = client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=generation_config,
                )
                text = response.text
                if not text:
                    raise GeminiServiceError(
                        "Gemini returned an empty answer (it may have been blocked "
                        "by a safety filter). Try different study material."
                    )
                return text

            except errors.APIError as exc:
                code = getattr(exc, "code", None)

                # Problems that retrying will not fix -> fail immediately.
                if code in (401, 403) or "API key" in str(exc):
                    raise InvalidAPIKeyError(
                        "Gemini rejected the API key. Check GEMINI_API_KEY in your .env file."
                    ) from exc
                if code == 404:
                    raise ModelNotFoundError(
                        f"The model '{self.model}' was not found. Set GEMINI_MODEL in "
                        "your .env file to a currently available Gemini model."
                    ) from exc
                if code == 400:
                    raise GeminiServiceError(f"Gemini could not process the request: {exc}") from exc

                # Rate limit (429) or server busy (500/503): wait and retry.
                last_error = exc
                if attempt < config.API_MAX_RETRIES:
                    time.sleep(delay)
                    delay *= 2

        # All retries used up.
        if getattr(last_error, "code", None) == 429:
            raise RateLimitError(
                "Gemini rate limit / quota reached. Please wait a minute and try again."
            ) from last_error
        raise GeminiServiceError(
            "Gemini is temporarily unavailable. Please try again in a moment."
        ) from last_error
