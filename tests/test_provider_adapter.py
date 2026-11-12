"""DeepSeek wire boundary: real HTTP client, isolated vendor transport only."""

import json
from dataclasses import replace

import httpx
import pytest
from deliveryflow_speccraft import providers
from deliveryflow_speccraft.model_boundary import ModelBoundaryError
from deliveryflow_speccraft.prd_authoring import FakePrdAuthor
from test_model_boundary import prd_task


def config(**overrides):
    return providers.DeepSeekConfig.from_environment(
        {
            "SPECCRAFT_PROVIDER": "deepseek",
            "SPECCRAFT_MODEL": "configured-model",
            "DEEPSEEK_API_KEY": "test-secret-never-disclose",
            **overrides,
        }
    )


def completion(task, **overrides):
    return {
        "id": "vendor-response",
        "object": "chat.completion",
        "created": 1,
        "model": "configured-model",
        "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {
                    "role": "assistant",
                    "content": FakePrdAuthor().author(task).model_dump_json(),
                    "reasoning_content": "discarded private reasoning",
                },
            }
        ],
        **overrides,
    }


def adapter(handler, settings=None):
    return providers.DeepSeekProvider(
        settings or config(),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_typed_json_request_returns_validated_candidate_and_frozen_nonsecret_profile():
    task = prd_task()

    def handle(request):
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer test-secret-never-disclose"
        body = json.loads(request.content)
        assert body["response_format"] == {"type": "json_object"}
        assert body["model"] == "configured-model" and body["stream"] is False
        assert body["thinking"] == {"type": "disabled"}
        assert body["max_tokens"] == 8192
        assert task.system_rules in body["messages"][0]["content"]
        assert "input_binding" in body["messages"][0]["content"]
        assert json.loads(body["messages"][1]["content"]) == task.model_dump(
            mode="json"
        )
        assert "tools" not in body
        return httpx.Response(200, json=completion(task))

    model = adapter(handle)
    output = model.author(task)
    assert output == FakePrdAuthor().author(task)
    assert "reasoning_content" not in output.model_dump_json()
    profile = model.binding
    assert "test-secret" not in profile.model_dump_json() + repr(config())
    assert profile.model == "configured-model"
    assert model.identity.startswith("deepseek:")
    assert config(DEEPSEEK_API_KEY="rotated-secret").binding == profile
    assert config(SPECCRAFT_MODEL="different-model").binding != profile


@pytest.mark.parametrize(
    "name", ["SPECCRAFT_PROVIDER", "SPECCRAFT_MODEL", "DEEPSEEK_API_KEY"]
)
def test_missing_configuration_fails_without_fake_or_secret_disclosure(name):
    with pytest.raises(providers.ProviderConfigurationError) as error:
        config(**{name: ""})
    assert name in str(error.value)
    assert "test-secret" not in str(error.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://api.deepseek.com",
        "https://untrusted.invalid",
        "https://a:b@api.deepseek.com",
        "https://[",
        "https://api.deepseek.com/other",
        "https://api.deepseek.com?key=secret",
    ],
)
def test_endpoint_cannot_redirect_credentials_to_another_origin(url):
    with pytest.raises(providers.ProviderConfigurationError):
        config(SPECCRAFT_BASE_URL=url)


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "provider_request_invalid", False),
        (401, "provider_auth_failed", False),
        (403, "provider_auth_failed", False),
        (402, "provider_balance_exhausted", False),
        (422, "provider_request_invalid", False),
        (429, "provider_rate_limited", True),
        (500, "provider_unavailable", True),
        (503, "provider_unavailable", True),
        (302, "provider_redirect_rejected", False),
    ],
)
def test_http_failures_are_classified_sanitized_and_never_retried_inside_adapter(
    status,
    code,
    retryable,
):
    calls = []

    def handle(request):
        calls.append(request)
        return httpx.Response(
            status,
            text="test-secret-never-disclose server private body",
            headers={"location": "https://untrusted.invalid"},
        )

    with pytest.raises(providers.ProviderError) as error:
        adapter(handle).author(prd_task())
    assert str(error.value) == code
    assert error.value.retryable is retryable
    assert len(calls) == 1  # Retry owner must reserve budget for every actual request.


@pytest.mark.parametrize(
    "failure,code",
    [
        (httpx.ReadTimeout, "provider_timeout"),
        (httpx.ConnectError, "provider_network_failure"),
    ],
)
def test_transport_failures_do_not_expose_request_or_vendor_detail(failure, code):
    def handle(request):
        raise failure("test-secret-never-disclose", request=request)

    with pytest.raises(providers.ProviderError) as error:
        adapter(handle).author(prd_task())
    assert str(error.value) == code
    assert error.value.retryable is True


@pytest.mark.parametrize(
    "content,finish,code",
    [
        ("   ", "stop", "provider_output_empty"),
        ("{", "length", "provider_output_truncated"),
        ("{}", "tool_calls", "provider_output_invalid"),
        (None, "stop", "provider_output_invalid"),
    ],
)
def test_blank_truncated_or_tool_outputs_are_never_success(content, finish, code):
    body = completion(prd_task())
    body["choices"][0]["finish_reason"] = finish
    body["choices"][0]["message"]["content"] = content
    with pytest.raises(providers.ProviderError, match=code):
        adapter(lambda _: httpx.Response(200, json=body)).author(prd_task())


@pytest.mark.parametrize(
    "update",
    [
        {"input_binding": "0" * 64},
        {"cited_ids": ["unknown"]},
        {"approval": "model-approved"},
    ],
)
def test_wrong_binding_unknown_citations_and_model_approval_are_rejected(update):
    task = prd_task()
    candidate = FakePrdAuthor().author(task).model_dump(mode="json") | update
    body = completion(task)
    body["choices"][0]["message"]["content"] = json.dumps(candidate)
    with pytest.raises(ModelBoundaryError) as error:
        adapter(lambda _: httpx.Response(200, json=body)).author(task)
    assert error.value.code == "model_output_invalid"


def test_invalid_input_is_rejected_before_network():
    def forbidden(_):
        pytest.fail("invalid task must not reach the provider")

    task = prd_task().model_copy(update={"input_binding": "0" * 64})
    with pytest.raises(ModelBoundaryError):
        adapter(forbidden).author(task)


def test_oversized_http_envelope_is_rejected_even_when_content_is_small():
    body = completion(prd_task())
    body["ignored_vendor_field"] = "x" * (512 * 1024)
    with pytest.raises(providers.ProviderError, match="provider_response_too_large"):
        adapter(lambda _: httpx.Response(200, json=body)).author(prd_task())


def test_malformed_http_json_is_sanitized():
    with pytest.raises(providers.ProviderError, match="provider_output_invalid"):
        adapter(lambda _: httpx.Response(200, content=b"private invalid json")).author(
            prd_task()
        )


def test_runtime_profile_mismatch_rejects_without_network():
    model = adapter(lambda _: pytest.fail("profile mismatch must not reach provider"))
    changed = replace(config(), model="changed")
    with pytest.raises(providers.ProviderError, match="provider_binding_conflict"):
        model.execute(prd_task(), expected_binding=changed.binding)


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    def __iter__(self):
        yield from self.chunks

    def close(self):
        self.closed = True


def test_stream_size_limit_closes_response_before_reading_remaining_chunks():
    def chunks():
        yield b"x" * (512 * 1024)
        yield b"x"
        pytest.fail("limit reached: must not read subsequent vendor data")

    stream = Chunks(chunks())
    with pytest.raises(providers.ProviderError, match="provider_response_too_large"):
        adapter(lambda _: httpx.Response(200, stream=stream)).author(prd_task())
    assert stream.closed


def test_elapsed_deadline_stops_slow_trickle_and_closes_stream(monkeypatch):
    now = iter([0.0, 91.0])
    monkeypatch.setattr(providers, "monotonic", lambda: next(now))
    stream = Chunks([b" ", b" "])
    with pytest.raises(providers.ProviderError, match="provider_timeout"):
        adapter(lambda _: httpx.Response(200, stream=stream)).author(prd_task())
    assert stream.closed


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"choices": []},
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": [],
                }
            ]
        },
    ],
)
def test_malformed_vendor_envelope_is_a_stable_protocol_error(body):
    with pytest.raises(providers.ProviderError, match="provider_output_invalid"):
        adapter(lambda _: httpx.Response(200, json=body)).author(prd_task())
