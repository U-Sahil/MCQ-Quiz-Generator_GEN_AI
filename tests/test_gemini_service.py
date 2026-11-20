"""
Tests for gemini_service.py error handling.
The real Gemini client is replaced with a fake one, so no internet or API key
is needed and no quota is used.
"""

from types import SimpleNamespace

import pytest
from google.genai import errors

import config
from services import gemini_service
from services.gemini_service import (
    GeminiService,
    GeminiServiceError,
    InvalidAPIKeyError,
    MissingAPIKeyError,
    ModelNotFoundError,
    RateLimitError,
)


def api_error(code):
    return errors.APIError(code, {"error": {"message": f"fake error {code}", "status": "X"}})


class FakeClient:
    """Raises the given errors in order, then returns a good response."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0
        self.models = SimpleNamespace(generate_content=self._generate)

    def _generate(self, **kwargs):
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(text=outcome)


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    """Do not really wait between retries during tests."""
    monkeypatch.setattr(gemini_service.time, "sleep", lambda seconds: None)


def service_with(client):
    service = GeminiService(api_key="test-key", model="test-model")
    service._client = client
    return service


def test_missing_api_key_raises_friendly_error():
    with pytest.raises(MissingAPIKeyError):
        GeminiService(api_key="").generate_json("hi")


def test_placeholder_api_key_is_treated_as_missing():
    with pytest.raises(MissingAPIKeyError):
        GeminiService(api_key="your_api_key_here").generate_json("hi")


def test_successful_call_returns_text():
    assert service_with(FakeClient("[]")).generate_json("hi") == "[]"


def test_rate_limit_retries_then_succeeds():
    client = FakeClient(api_error(429), "[]")
    assert service_with(client).generate_json("hi") == "[]"
    assert client.calls == 2


def test_rate_limit_forever_raises_rate_limit_error():
    client = FakeClient(api_error(429))
    with pytest.raises(RateLimitError):
        service_with(client).generate_json("hi")
    assert client.calls == config.API_MAX_RETRIES


def test_server_busy_forever_raises_service_error():
    with pytest.raises(GeminiServiceError):
        service_with(FakeClient(api_error(503))).generate_json("hi")


def test_invalid_key_fails_immediately_without_retry():
    client = FakeClient(api_error(403))
    with pytest.raises(InvalidAPIKeyError):
        service_with(client).generate_json("hi")
    assert client.calls == 1


def test_model_not_found_fails_immediately():
    client = FakeClient(api_error(404))
    with pytest.raises(ModelNotFoundError):
        service_with(client).generate_json("hi")
    assert client.calls == 1


def test_empty_answer_raises_service_error():
    with pytest.raises(GeminiServiceError):
        service_with(FakeClient("")).generate_json("hi")
