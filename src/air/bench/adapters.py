"""Opt-in provider adapters isolated from AIR Core and deterministic tests."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ..ir import JsonInput
from .live_models import ModelRequest, ModelResponse


class ModelAdapterError(RuntimeError):
    """Typed provider failure without retaining credentials or prompt content."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_count: int = 0,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_count = retry_count


@dataclass(frozen=True, slots=True)
class TransportResponse:
    """Minimal HTTP response shape required by the OpenAI adapter."""

    status_code: int
    headers: Mapping[str, str]
    body: bytes


class HttpTransport(Protocol):
    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        """Send one HTTP POST request."""


class UrllibTransport:
    """Standard-library HTTPS transport for the OpenAI Responses endpoint."""

    def post(
        self,
        url: str,
        headers: Mapping[str, str],
        body: bytes,
        timeout_seconds: float,
    ) -> TransportResponse:
        request = Request(url, data=body, headers=dict(headers), method="POST")
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                return TransportResponse(
                    status_code=response.status,
                    headers=_headers_to_mapping(response.headers),
                    body=response.read(),
                )
        except HTTPError as exc:
            return TransportResponse(
                status_code=exc.code,
                headers=_headers_to_mapping(exc.headers),
                body=exc.read(),
            )
        except URLError as exc:
            raise ModelAdapterError(f"provider transport failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise ModelAdapterError("provider request timed out") from exc


class OpenAIResponsesAdapter:
    """One real provider implementation using OpenAI's Responses API.

    The adapter accepts an injectable HTTP transport so all unit tests remain
    offline. Credentials are read only from ``OPENAI_API_KEY`` or an explicit
    constructor argument and never enter request/result models.
    """

    provider = "openai"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1/responses",
        max_retries: int = 0,
        transport: HttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("OpenAI API key must not be empty")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self._api_key = api_key
        self._base_url = base_url
        self._max_retries = max_retries
        self._transport = transport or UrllibTransport()
        self._sleep = sleep

    @classmethod
    def from_env(
        cls,
        *,
        base_url: str = "https://api.openai.com/v1/responses",
        max_retries: int = 0,
        transport: HttpTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> OpenAIResponsesAdapter:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ModelAdapterError(
                "OPENAI_API_KEY is required for live execution; "
                "set it explicitly or use an offline fake adapter"
            )
        return cls(
            api_key,
            base_url=base_url,
            max_retries=max_retries,
            transport=transport,
            sleep=sleep,
        )

    def invoke(self, request: ModelRequest) -> ModelResponse:
        payload = self._request_payload(request)
        body = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        retry_count = 0
        response: TransportResponse | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._transport.post(
                    self._base_url,
                    headers,
                    body,
                    request.timeout_seconds,
                )
            except ModelAdapterError as exc:
                if attempt >= self._max_retries:
                    raise ModelAdapterError(
                        str(exc),
                        status_code=exc.status_code,
                        retry_count=retry_count,
                    ) from exc
                retry_count += 1
                self._sleep(min(2.0, 0.25 * (2**attempt)))
                continue
            if response.status_code not in {408, 409, 429, 500, 502, 503, 504}:
                break
            if attempt >= self._max_retries:
                break
            retry_count += 1
            self._sleep(min(2.0, 0.25 * (2**attempt)))
        if response is None:
            raise ModelAdapterError("provider returned no response")
        elapsed = time.perf_counter() - started
        if response.status_code < 200 or response.status_code >= 300:
            raise ModelAdapterError(
                f"OpenAI Responses request failed with status {response.status_code}",
                status_code=response.status_code,
                retry_count=retry_count,
            )
        try:
            data = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ModelAdapterError("provider returned invalid JSON") from exc
        if not isinstance(data, Mapping):
            raise ModelAdapterError("provider response must be a JSON object")
        usage = _mapping(data.get("usage"))
        input_details = _mapping(usage.get("input_tokens_details"))
        output_details = _mapping(usage.get("output_tokens_details"))
        response_headers = {key.lower(): value for key, value in response.headers.items()}
        request_id = response_headers.get("x-request-id") or _string(data.get("id"))
        return ModelResponse(
            output=_response_text(data),
            input_tokens=_nonnegative_int(usage.get("input_tokens")),
            output_tokens=_nonnegative_int(usage.get("output_tokens")),
            cached_input_tokens=_nonnegative_int(input_details.get("cached_tokens")),
            reasoning_tokens=_nonnegative_int(output_details.get("reasoning_tokens")),
            model=_string(data.get("model")) or request.model,
            provider=self.provider,
            request_id=request_id,
            latency_seconds=elapsed,
            finish_reason=_string(data.get("status")),
            provider_metadata=_provider_metadata(data),
            retry_count=retry_count,
        )

    @staticmethod
    def _request_payload(request: ModelRequest) -> dict[str, object]:
        payload: dict[str, object] = {
            "input": [message.to_json_obj() for message in request.messages],
            "model": request.model,
            "store": False,
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        return payload


def _headers_to_mapping(headers: object | None) -> dict[str, str]:
    if headers is None:
        return {}
    items = getattr(headers, "items", None)
    if not callable(items):
        return {}
    return {str(key): str(value) for key, value in items()}


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _nonnegative_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _response_text(data: Mapping[str, object]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str):
        return direct
    chunks: list[str] = []
    output = data.get("output")
    if isinstance(output, list):
        for item in output:
            item_mapping = _mapping(item)
            content = item_mapping.get("content")
            if isinstance(content, list):
                for part in content:
                    part_mapping = _mapping(part)
                    text = part_mapping.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            elif isinstance(content, str):
                chunks.append(content)
    return "".join(chunks)


def _provider_metadata(data: Mapping[str, object]) -> dict[str, JsonInput]:
    result: dict[str, JsonInput] = {}
    for name in ("status", "service_tier", "incomplete_details", "usage"):
        value = data.get(name)
        if value is not None:
            result[name] = cast(JsonInput, value)
    return result
