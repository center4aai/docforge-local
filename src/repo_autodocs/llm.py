"""LLM client abstractions for markdown section generation."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from hashlib import sha1
from typing import Protocol

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    PermissionDeniedError,
)

from repo_autodocs.config import AppConfig
from repo_autodocs.rendering import get_section_contract
from repo_autodocs.secrets import resolve_api_key

logger = logging.getLogger(__name__)

STANDARD_LLM_REQUEST_TIMEOUT_SECONDS = 60
INITIAL_LLM_REQUEST_TIMEOUT_SECONDS = 5
LLM_STREAM_CONNECT_TIMEOUT_SECONDS = 5
LLM_STREAM_FIRST_CHUNK_TIMEOUT_SECONDS = 30
LLM_STREAM_INACTIVITY_TIMEOUT_SECONDS = 60

_JSON_STAGE_SUFFIXES = (
    ":notes",
    ":notes-repair",
    ":mapping",
    ":final",
    ":final-repair",
    ":language-repair",
)


class LLMClient(Protocol):
    """Interface for stage-oriented LLM text generation."""

    def generate_text(
        self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
    ) -> str:
        """Generate text for a specific orchestration stage."""

    def generate_markdown(self, prompt: str) -> str:
        """Backward-compatible single-call helper for older code/tests."""


class LLMServiceError(RuntimeError):
    """User-facing LLM runtime failure with actionable guidance."""


@dataclass(slots=True)
class LLMTransientFailure(LLMServiceError):
    """Structured transport-level failure after retry exhaustion."""

    operation_label: str
    attempt_count: int
    attempt_timeouts_seconds: tuple[int, ...]
    final_exception_type: str
    final_error_message: str

    def __str__(self) -> str:
        return (
            "LLM transport request failed after retries "
            f"(operation={self.operation_label}, attempts={self.attempt_count}, "
            f"timeouts={list(self.attempt_timeouts_seconds)}, "
            f"final_error={self.final_exception_type}: {self.final_error_message})."
        )


@dataclass(slots=True)
class LLMStreamInterruptedFailure(LLMServiceError):
    """Structured mid-stream failure after meaningful streamed content has started."""

    operation_label: str
    meaningful_response_started: bool
    attempt_count: int
    final_exception_type: str
    final_error_message: str
    content_received_chars: int

    def __str__(self) -> str:
        return (
            "LLM stream interrupted after meaningful response started "
            f"(operation={self.operation_label}, attempts={self.attempt_count}, "
            f"content_received_chars={self.content_received_chars}, "
            f"final_error={self.final_exception_type}: {self.final_error_message})."
        )


@dataclass(slots=True)
class _LLMPreResponseTransportFailure(RuntimeError):
    operation_label: str
    attempt_count: int
    cause: Exception


def _timeout_attempts(*, timeout_cap_seconds: int) -> tuple[int, ...]:
    cap = max(1, int(timeout_cap_seconds))
    if cap <= INITIAL_LLM_REQUEST_TIMEOUT_SECONDS:
        return (cap,)
    attempts: list[int] = []
    attempt_index = 0
    while True:
        timeout = min(INITIAL_LLM_REQUEST_TIMEOUT_SECONDS * (2**attempt_index), cap)
        attempts.append(timeout)
        if timeout >= cap:
            break
        attempt_index += 1
    return tuple(attempts)


def _is_retryable_transport_error(exc: Exception) -> bool:
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(
        exc,
        (
            httpx.TimeoutException,
            httpx.NetworkError,
            TimeoutError,
            ConnectionError,
            ConnectionResetError,
            ConnectionAbortedError,
        ),
    ):
        return True
    cause = getattr(exc, "__cause__", None)
    return isinstance(cause, Exception) and _is_retryable_transport_error(cause)


def _is_json_stage(operation_label: str, user_prompt: str) -> bool:
    if any(operation_label.endswith(suffix) for suffix in _JSON_STAGE_SUFFIXES):
        return True
    lowered = user_prompt.lower()
    return (
        "return json" in lowered
        or "return only one valid json object" in lowered
        or "[json output discipline" in lowered
        or "[notes json schema]" in lowered
        or "[mapping json schema]" in lowered
        or "[final section json schema]" in lowered
        or "[language repair json schema]" in lowered
    )


def _json_stage_system_guard(operation_label: str) -> str:
    return "\n".join(
        [
            f"[NON-NEGOTIABLE OUTPUT RULES FOR {operation_label}]",
            "You must return exactly one valid JSON object.",
            "You must follow the schema and example provided in the user prompt exactly.",
            "You must not output markdown fences, prose, commentary, apologies, or explanations.",
            "You must not add text before or after the JSON object.",
            "You must not rename keys, translate keys, or add extra top-level keys.",
            "If the user prompt defines allowed enums, required headings, required block kinds, or required keys, obey them exactly.",
            "If any instruction conflicts with the required JSON schema, the schema wins.",
        ]
    )


def _markdown_stage_system_guard(operation_label: str) -> str:
    return "\n".join(
        [
            f"[OUTPUT RULES FOR {operation_label}]",
            "Return only the requested markdown content.",
            "Do not switch to JSON unless the user prompt explicitly requests JSON.",
            "Do not add meta-explanations about the prompt or your formatting choices.",
        ]
    )


def _build_effective_system_prompt(
    *, system_prompt: str, user_prompt: str, operation_label: str
) -> str:
    guard = (
        _json_stage_system_guard(operation_label)
        if _is_json_stage(operation_label, user_prompt)
        else _markdown_stage_system_guard(operation_label)
    )
    return "\n\n".join([system_prompt.strip(), guard]).strip()


def _build_effective_user_prompt(*, user_prompt: str, operation_label: str) -> str:
    if not _is_json_stage(operation_label, user_prompt):
        return user_prompt

    prelude = "\n".join(
        [
            f"[FINAL REMINDER: {operation_label}]",
            "Return ONLY one valid JSON object and nothing else.",
            "The JSON object must match the provided schema exactly.",
            "Do not wrap the JSON in code fences.",
        ]
    )
    return "\n\n".join([prelude, user_prompt])


def call_llm_with_retries(
    *,
    operation_label: str,
    timeout_cap_seconds: int,
    invoke: Callable[[int], str],
) -> str:
    """Run one outbound LLM API call with retry-on-transport failure semantics."""

    attempt_timeouts = _timeout_attempts(timeout_cap_seconds=timeout_cap_seconds)
    last_exception: Exception | None = None

    for attempt_index, timeout_seconds in enumerate(attempt_timeouts, start=1):
        try:
            return invoke(timeout_seconds)
        except Exception as exc:  # noqa: BLE001
            if not _is_retryable_transport_error(exc):
                raise
            last_exception = exc
            final_attempt = attempt_index == len(attempt_timeouts)
            if final_attempt:
                break
            logger.warning(
                "LLM transport failure (operation=%s, attempt=%s/%s, timeout=%ss, "
                "error_type=%s, message=%s). Retrying.",
                operation_label,
                attempt_index,
                len(attempt_timeouts),
                timeout_seconds,
                type(exc).__name__,
                str(exc).strip() or "<empty>",
            )

    assert last_exception is not None
    logger.warning(
        "LLM transport retries exhausted (operation=%s, attempts=%s, timeouts=%s, "
        "final_error_type=%s, message=%s).",
        operation_label,
        len(attempt_timeouts),
        list(attempt_timeouts),
        type(last_exception).__name__,
        str(last_exception).strip() or "<empty>",
    )
    raise LLMTransientFailure(
        operation_label=operation_label,
        attempt_count=len(attempt_timeouts),
        attempt_timeouts_seconds=attempt_timeouts,
        final_exception_type=type(last_exception).__name__,
        final_error_message=str(last_exception).strip() or "<empty>",
    ) from last_exception


@dataclass(slots=True)
class OpenAICompatibleLLMClient:
    """Minimal OpenAI-compatible client backed by the OpenAI SDK."""

    model_name: str
    api_key: str | None
    temperature: float = 0.2
    base_url: str | None = None
    _client: OpenAI = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.api_key or "", base_url=self.base_url)

    @classmethod
    def from_config(cls, config: AppConfig) -> OpenAICompatibleLLMClient:
        """Build client from app config and process environment."""

        if not config.model_name:
            raise ValueError("LLM is enabled but no model name is configured.")
        if not config.base_url:
            raise ValueError("LLM is enabled but no base_url is configured.")

        api_key = resolve_api_key(config)

        return cls(
            model_name=config.model_name,
            api_key=api_key,
            temperature=config.temperature,
            base_url=config.base_url,
        )

    def generate_text(
        self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
    ) -> str:
        operation = operation_label or "unknown"
        effective_system_prompt = _build_effective_system_prompt(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            operation_label=operation,
        )
        effective_user_prompt = _build_effective_user_prompt(
            user_prompt=user_prompt,
            operation_label=operation,
        )

        attempt_timeouts = _timeout_attempts(
            timeout_cap_seconds=STANDARD_LLM_REQUEST_TIMEOUT_SECONDS
        )
        last_pre_response_failure: _LLMPreResponseTransportFailure | None = None
        try:
            for attempt_index, startup_timeout in enumerate(attempt_timeouts, start=1):
                logger.info(
                    "LLM stream attempt started "
                    "(operation=%s, attempt=%s/%s, startup_timeout=%ss).",
                    operation,
                    attempt_index,
                    len(attempt_timeouts),
                    startup_timeout,
                )
                try:
                    stream = self._client.chat.completions.create(
                        model=self.model_name,
                        temperature=self.temperature,
                        stream=True,
                        timeout=httpx.Timeout(
                            timeout=LLM_STREAM_INACTIVITY_TIMEOUT_SECONDS,
                            connect=min(startup_timeout, LLM_STREAM_CONNECT_TIMEOUT_SECONDS),
                            read=max(
                                LLM_STREAM_FIRST_CHUNK_TIMEOUT_SECONDS,
                                LLM_STREAM_INACTIVITY_TIMEOUT_SECONDS,
                            ),
                            write=startup_timeout,
                        ),
                        messages=[
                            {"role": "system", "content": effective_system_prompt},
                            {"role": "user", "content": effective_user_prompt},
                        ],
                    )
                    return self._consume_text_stream(
                        stream=stream,
                        operation_label=operation,
                        attempt_count=attempt_index,
                    )
                except _LLMPreResponseTransportFailure as exc:
                    last_pre_response_failure = exc
                except LLMStreamInterruptedFailure:
                    raise
                except Exception as exc:  # noqa: BLE001
                    if not _is_retryable_transport_error(exc):
                        raise
                    last_pre_response_failure = _LLMPreResponseTransportFailure(
                        operation_label=operation,
                        attempt_count=attempt_index,
                        cause=exc,
                    )
                if last_pre_response_failure is not None:
                    final_attempt = attempt_index == len(attempt_timeouts)
                    if final_attempt:
                        break
                    logger.warning(
                        "LLM pre-response transport failure (operation=%s, attempt=%s/%s, "
                        "error_type=%s, message=%s). Retrying.",
                        operation,
                        attempt_index,
                        len(attempt_timeouts),
                        type(last_pre_response_failure.cause).__name__,
                        str(last_pre_response_failure.cause).strip() or "<empty>",
                    )
        except AuthenticationError as exc:
            raise LLMServiceError(
                "LLM endpoint authentication failed: the configured endpoint rejected the request. "
                "If your endpoint requires authentication, set "
                "REPO_AUTODOCS_API_KEY_ENV_VAR and export the actual key in that environment "
                "variable."
            ) from exc
        except PermissionDeniedError as exc:
            raise LLMServiceError(
                "LLM endpoint permission denied: the configured credentials do not have access "
                f"to {self.base_url or '<missing-base-url>'}."
            ) from exc
        except LLMTransientFailure:
            raise
        except LLMStreamInterruptedFailure:
            raise
        except APIStatusError as exc:
            raise LLMServiceError(
                f"LLM endpoint returned an unexpected error status (HTTP {exc.status_code})."
            ) from exc
        assert last_pre_response_failure is not None
        final_exc = last_pre_response_failure.cause
        raise LLMTransientFailure(
            operation_label=operation,
            attempt_count=len(attempt_timeouts),
            attempt_timeouts_seconds=attempt_timeouts,
            final_exception_type=type(final_exc).__name__,
            final_error_message=str(final_exc).strip() or "<empty>",
        ) from final_exc

    def _consume_text_stream(self, *, stream, operation_label: str, attempt_count: int) -> str:
        meaningful_response_started = False
        fragments: list[str] = []
        stream_closed = False
        try:
            for chunk in stream:
                text_parts = self._extract_text_parts_from_chunk(chunk)
                if not text_parts:
                    continue
                if not meaningful_response_started:
                    meaningful_response_started = True
                    logger.info(
                        "LLM first meaningful stream chunk received (operation=%s, attempt=%s).",
                        operation_label,
                        attempt_count,
                    )
                fragments.extend(text_parts)
            logger.info(
                "LLM stream completed successfully (operation=%s, attempt=%s, content_chars=%s).",
                operation_label,
                attempt_count,
                len("".join(fragments)),
            )
        except Exception as exc:  # noqa: BLE001
            if _is_retryable_transport_error(exc):
                if meaningful_response_started:
                    logger.warning(
                        "LLM stream interrupted mid-response (operation=%s, attempt=%s, "
                        "error_type=%s, message=%s).",
                        operation_label,
                        attempt_count,
                        type(exc).__name__,
                        str(exc).strip() or "<empty>",
                    )
                    raise LLMStreamInterruptedFailure(
                        operation_label=operation_label,
                        meaningful_response_started=True,
                        attempt_count=attempt_count,
                        final_exception_type=type(exc).__name__,
                        final_error_message=str(exc).strip() or "<empty>",
                        content_received_chars=len("".join(fragments)),
                    ) from exc
                raise _LLMPreResponseTransportFailure(
                    operation_label=operation_label,
                    attempt_count=attempt_count,
                    cause=exc,
                ) from exc
            raise
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
                stream_closed = True
            if not stream_closed:
                exit_fn = getattr(stream, "__exit__", None)
                if callable(exit_fn):
                    exit_fn(None, None, None)
        return "".join(fragments).strip()

    def _extract_text_parts_from_chunk(self, chunk: object) -> tuple[str, ...]:
        choices = getattr(chunk, "choices", None)
        if not choices:
            return ()

        parts: list[str] = []
        for choice in choices:
            delta = getattr(choice, "delta", None)
            content = getattr(delta, "content", None) if delta is not None else None
            if isinstance(content, str):
                if content != "":
                    parts.append(content)
                continue
            if isinstance(content, list):
                for item in content:
                    text_value = ""
                    if isinstance(item, dict):
                        text_value = str(item.get("text") or "")
                    else:
                        text_value = str(getattr(item, "text", "") or "")
                    if text_value.strip():
                        parts.append(text_value)
        return tuple(parts)

    def generate_markdown(self, prompt: str) -> str:
        return self.generate_text(
            system_prompt=(
                "You are a technical analysis writer. "
                "Return only markdown. "
                "Produce evidence-backed markdown that clearly separates observed repository "
                "evidence from inference, states uncertainty explicitly, and surfaces mismatches "
                "when relevant. "
                "Do not switch to JSON unless the user prompt explicitly requires JSON."
            ),
            user_prompt=prompt,
        )


@dataclass(slots=True)
class StubLLMClient:
    """Deterministic offline stub used for tests and local default mode."""

    marker: str = "stub"

    def generate_text(
        self, *, system_prompt: str, user_prompt: str, operation_label: str | None = None
    ) -> str:
        section_name = "overview"
        for candidate in (
            "overview",
            "architecture",
            "code_structure",
            "runtime_entrypoints",
            "reference_alignment",
            "agent_instruction_alignment",
            "readme_claim_alignment",
            "theory_alignment",
        ):
            if f"[STAGE: {candidate}:" in user_prompt or f"[TASK: {candidate}]" in user_prompt:
                section_name = candidate
                break

        contract = get_section_contract(section_name)
        digest = sha1(user_prompt.encode("utf-8")).hexdigest()[:12]

        if f"[STAGE: {section_name}:notes" in user_prompt:
            return json.dumps(
                {
                    "notes_markdown": (
                        f"- OBS: Stub observations for {section_name}\n"
                        f"- UNCERTAINTY: Stub uncertainty for {section_name}"
                    ),
                    "observations": [f"Stub observation digest {digest}"],
                    "uncertainty_flags": ["Stub mode does not use external LLM evidence."],
                }
            )

        if ":mapping]" in user_prompt and "[STAGE:" in user_prompt:
            return json.dumps(
                {
                    "entries": [
                        {
                            "reference_claim": "Stub reference claim",
                            "code_anchor": "Stub code anchor",
                            "status": "missing_evidence",
                            "evidence_note": "Stub mode cannot validate semantic alignment.",
                            "uncertainty_note": "No real model inference in stub mode.",
                        }
                    ]
                }
            )

        if f"[STAGE: {section_name}:final" in user_prompt:
            return json.dumps(
                {
                    "title": contract.title,
                    "section_blocks": {
                        heading: (
                            [
                                {
                                    "kind": "bullet",
                                    "text": f"Stub synthesis for `{section_name}` / `{heading}`.",
                                },
                                {"kind": "bullet", "text": f"Prompt digest: `{digest}`."},
                                {
                                    "kind": "paragraph",
                                    "text": (
                                        "Deterministic repository and code facts remain "
                                        "authoritative."
                                    ),
                                },
                            ]
                        )
                        for heading in contract.headings
                    },
                }
            )

        return json.dumps({"text": f"stub-stage:{section_name}"})

    def generate_markdown(self, prompt: str) -> str:
        return self.generate_text(system_prompt="stub", user_prompt=prompt)
