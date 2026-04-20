from pathlib import Path

import pytest

from repo_autodocs.config import AppConfig
from repo_autodocs.llm import (
    LLMStreamInterruptedFailure,
    LLMTransientFailure,
    OpenAICompatibleLLMClient,
    _build_effective_system_prompt,
    _build_effective_user_prompt,
    _is_json_stage,
    _timeout_attempts,
    call_llm_with_retries,
)
from repo_autodocs.models import ProjectPaths


def _config(model_name: str | None, api_key_env_var: str = "OPENAI_API_KEY") -> AppConfig:
    root = Path("/tmp/repo")
    paths = ProjectPaths(
        project_root=root,
        docs_dir=root / "docs",
        reference_dir=root / "docs/context/methodology",
        output_dir=root / "docs/generated",
        site_dir=root / "site",
    )
    return AppConfig(
        project_paths=paths,
        enable_llm=True,
        model_name=model_name,
        base_url="https://llm.example/v1",
        api_key_env_var=api_key_env_var,
    )


def _make_stream_chunk(text: str):
    delta = type("_Delta", (), {"content": text})()
    choice = type("_Choice", (), {"delta": delta})()
    return type("_Chunk", (), {"choices": [choice]})()


class _FakeStreamingCompletions:
    def __init__(self, attempts):
        self.attempts = attempts
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        factory = self.attempts[self.calls - 1]
        return factory(kwargs)


def _set_streaming_client(client: OpenAICompatibleLLMClient, attempts) -> None:
    completions = _FakeStreamingCompletions(attempts)
    client._client = type(
        "_FakeOpenAIClient",
        (),
        {"chat": type("_FakeChat", (), {"completions": completions})()},
    )()


def test_from_config_raises_when_model_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="no model name"):
        OpenAICompatibleLLMClient.from_config(_config(model_name=None))


def test_from_config_raises_when_model_is_blank(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    with pytest.raises(ValueError, match="no model name"):
        OpenAICompatibleLLMClient.from_config(_config(model_name=""))


def test_from_config_allows_missing_api_key_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)

    client = OpenAICompatibleLLMClient.from_config(
        _config(model_name="gpt-test", api_key_env_var="MISSING_KEY")
    )
    assert client.api_key is None


def test_from_config_allows_empty_api_key_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMPTY_KEY", "")

    client = OpenAICompatibleLLMClient.from_config(
        _config(model_name="gpt-test", api_key_env_var="EMPTY_KEY")
    )
    assert client.api_key is None


def test_from_config_uses_api_key_when_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOM_KEY", "top-secret")

    client = OpenAICompatibleLLMClient.from_config(
        _config(model_name="gpt-test", api_key_env_var="CUSTOM_KEY")
    )
    assert client.api_key == "top-secret"


def test_from_config_raises_when_base_url_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    config = _config(model_name="gpt-test")
    config.base_url = None

    with pytest.raises(ValueError, match="no base_url"):
        OpenAICompatibleLLMClient.from_config(config)


def test_timeout_attempt_sequence_is_geometric_and_capped() -> None:
    assert _timeout_attempts(timeout_cap_seconds=60) == (5, 10, 20, 40, 60)
    assert _timeout_attempts(timeout_cap_seconds=30) == (5, 10, 20, 30)
    assert _timeout_attempts(timeout_cap_seconds=5) == (5,)
    assert _timeout_attempts(timeout_cap_seconds=3) == (3,)


def test_call_llm_with_retries_retries_retryable_timeout_then_succeeds() -> None:
    seen_timeouts: list[int] = []
    calls = {"count": 0}

    def _invoke(timeout_seconds: int) -> str:
        calls["count"] += 1
        seen_timeouts.append(timeout_seconds)
        if calls["count"] < 3:
            raise TimeoutError("temporary timeout")
        return "ok"

    result = call_llm_with_retries(
        operation_label="overview:notes",
        timeout_cap_seconds=20,
        invoke=_invoke,
    )

    assert result == "ok"
    assert seen_timeouts == [5, 10, 20]


def test_call_llm_with_retries_does_not_retry_non_retryable_error() -> None:
    calls = {"count": 0}

    def _invoke(timeout_seconds: int) -> str:
        calls["count"] += 1
        raise RuntimeError("semantic failure")

    with pytest.raises(RuntimeError, match="semantic failure"):
        call_llm_with_retries(
            operation_label="overview:notes",
            timeout_cap_seconds=60,
            invoke=_invoke,
        )
    assert calls["count"] == 1


def test_call_llm_with_retries_raises_structured_failure_after_exhaustion() -> None:
    with pytest.raises(LLMTransientFailure) as exc_info:
        call_llm_with_retries(
            operation_label="architecture:final",
            timeout_cap_seconds=30,
            invoke=lambda timeout_seconds: (_ for _ in ()).throw(ConnectionResetError("reset")),
        )

    failure = exc_info.value
    assert failure.operation_label == "architecture:final"
    assert failure.attempt_count == 4
    assert failure.attempt_timeouts_seconds == (5, 10, 20, 30)
    assert failure.final_exception_type == "ConnectionResetError"
    assert "reset" in failure.final_error_message


def test_generate_text_streaming_success_assembles_chunks_without_retry() -> None:
    client = OpenAICompatibleLLMClient(
        model_name="gpt-test",
        api_key="test-key",
        base_url="https://llm.example/v1",
    )

    _set_streaming_client(
        client,
        attempts=[
            lambda kwargs: iter(
                [
                    _make_stream_chunk("Hello"),
                    _make_stream_chunk(" "),
                    _make_stream_chunk("world"),
                ]
            )
        ],
    )

    result = client.generate_text(system_prompt="system", user_prompt="user", operation_label="op")

    assert result == "Hello world"


def test_generate_text_retries_when_failure_happens_before_meaningful_chunk() -> None:
    client = OpenAICompatibleLLMClient(
        model_name="gpt-test",
        api_key="test-key",
        base_url="https://llm.example/v1",
    )

    _set_streaming_client(
        client,
        attempts=[
            lambda kwargs: (_ for _ in ()).throw(TimeoutError("connect timeout")),
            lambda kwargs: (_ for _ in ()).throw(ConnectionResetError("reset before data")),
            lambda kwargs: iter([_make_stream_chunk("ok")]),
        ],
    )

    result = client.generate_text(system_prompt="system", user_prompt="user", operation_label="op")

    assert result == "ok"


def test_generate_text_does_not_retry_when_stream_interrupts_after_meaningful_chunk() -> None:
    client = OpenAICompatibleLLMClient(
        model_name="gpt-test",
        api_key="test-key",
        base_url="https://llm.example/v1",
    )

    def _broken_stream():
        yield _make_stream_chunk("partial")
        raise ConnectionResetError("stream broke")

    _set_streaming_client(client, attempts=[lambda kwargs: _broken_stream()])

    with pytest.raises(LLMStreamInterruptedFailure) as exc_info:
        client.generate_text(system_prompt="system", user_prompt="user", operation_label="op")

    failure = exc_info.value
    assert failure.meaningful_response_started is True
    assert failure.attempt_count == 1
    assert failure.content_received_chars == len("partial")
    assert failure.final_exception_type == "ConnectionResetError"


def test_generate_text_non_retryable_semantic_failure_still_does_not_retry() -> None:
    client = OpenAICompatibleLLMClient(
        model_name="gpt-test",
        api_key="test-key",
        base_url="https://llm.example/v1",
    )

    calls = {"count": 0}

    def _raise_semantic(kwargs):
        calls["count"] += 1
        raise RuntimeError("semantic parse failure")

    _set_streaming_client(client, attempts=[_raise_semantic])

    with pytest.raises(RuntimeError, match="semantic parse failure"):
        client.generate_text(system_prompt="system", user_prompt="user", operation_label="op")

    assert calls["count"] == 1


def test_json_stage_detection_uses_operation_label_and_prompt_content() -> None:
    assert _is_json_stage("overview:final", "plain prompt")
    assert _is_json_stage("overview:any", "[FINAL SECTION JSON SCHEMA] Return JSON")
    assert not _is_json_stage("overview:markdown", "Write markdown summary only.")


def test_effective_prompt_guards_harden_json_stages_without_touching_markdown_stages() -> None:
    json_system = _build_effective_system_prompt(
        system_prompt="base",
        user_prompt="[NOTES JSON SCHEMA] Return JSON",
        operation_label="overview:notes",
    )
    json_user = _build_effective_user_prompt(
        user_prompt="[NOTES JSON SCHEMA] Return JSON",
        operation_label="overview:notes",
    )
    markdown_system = _build_effective_system_prompt(
        system_prompt="base",
        user_prompt="Write markdown section body",
        operation_label="overview:markdown",
    )
    markdown_user = _build_effective_user_prompt(
        user_prompt="Write markdown section body",
        operation_label="overview:markdown",
    )

    assert "[NON-NEGOTIABLE OUTPUT RULES FOR overview:notes]" in json_system
    assert "[FINAL REMINDER: overview:notes]" in json_user
    assert "[OUTPUT RULES FOR overview:markdown]" in markdown_system
    assert (
        "Do not switch to JSON unless the user prompt explicitly requests JSON." in markdown_system
    )
    assert markdown_user == "Write markdown section body"
