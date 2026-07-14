"""공통 AI 모듈 호출 레이어(capcut_auto/ai/client.py) 테스트.

테스트 시나리오 1~4: 정상 AI 응답 / JSON 오류 / 스키마 오류 / API 타임아웃(네트워크 오류).
"""

import json
import unittest

from capcut_auto.ai.client import AiModuleError, AiModuleRequest, call_ai_module
from tests.ai_test_helpers import (
    FakeAnthropicClient,
    FakeResponse,
    make_connection_error,
    make_rate_limit_error,
    make_server_error,
    make_client_error,
    noop_sleep,
)

SCHEMA = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}


def make_request(input_data=None) -> AiModuleRequest:
    return AiModuleRequest(
        module_name="test_module",
        system_prompt="시스템 프롬프트",
        input_data=input_data or {"foo": "bar"},
        output_schema=SCHEMA,
    )


class TestNormalResponse(unittest.TestCase):
    """1. 정상 AI 응답"""

    def test_valid_response_returns_parsed_json(self):
        client = FakeAnthropicClient([FakeResponse(json.dumps({"value": 42}))])
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 42})
        self.assertEqual(len(client.messages.calls), 1)

    def test_system_prompt_and_input_data_are_sent_separately(self):
        client = FakeAnthropicClient([FakeResponse(json.dumps({"value": 1}))])
        call_ai_module(make_request({"secret": "data"}), client=client, sleep_fn=noop_sleep)
        call_kwargs = client.messages.calls[0]
        self.assertEqual(call_kwargs["system"], "시스템 프롬프트")
        self.assertIn("secret", call_kwargs["messages"][0]["content"])

    def test_refusal_raises_ai_module_error(self):
        client = FakeAnthropicClient([FakeResponse(json.dumps({"value": 1}), stop_reason="refusal")])
        with self.assertRaises(AiModuleError):
            call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)


class TestJsonError(unittest.TestCase):
    """2. JSON 오류"""

    def test_invalid_json_triggers_one_repair_then_succeeds(self):
        client = FakeAnthropicClient(
            [FakeResponse("이건 JSON이 아님"), FakeResponse(json.dumps({"value": 7}))]
        )
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 7})
        self.assertEqual(len(client.messages.calls), 2)
        # 수정 요청 메시지가 실제로 대화에 추가되었는지 확인
        second_call_messages = client.messages.calls[1]["messages"]
        self.assertGreaterEqual(len(second_call_messages), 3)

    def test_invalid_json_twice_raises_ai_module_error(self):
        client = FakeAnthropicClient([FakeResponse("깨진 JSON 1"), FakeResponse("깨진 JSON 2")])
        with self.assertRaises(AiModuleError):
            call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)


class TestSchemaError(unittest.TestCase):
    """3. 스키마 오류"""

    def test_schema_violation_triggers_one_repair_then_succeeds(self):
        client = FakeAnthropicClient(
            [
                FakeResponse(json.dumps({"value": "not-an-integer"})),
                FakeResponse(json.dumps({"value": 5})),
            ]
        )
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 5})
        self.assertEqual(len(client.messages.calls), 2)

    def test_schema_violation_twice_raises_ai_module_error(self):
        client = FakeAnthropicClient(
            [
                FakeResponse(json.dumps({"value": "bad"})),
                FakeResponse(json.dumps({"wrong_key": 1})),
            ]
        )
        with self.assertRaises(AiModuleError):
            call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)


class TestNetworkTimeout(unittest.TestCase):
    """4. API 타임아웃(네트워크 오류) - 최대 2회 재시도"""

    def test_connection_error_retries_then_succeeds(self):
        client = FakeAnthropicClient(
            [make_connection_error(), make_connection_error(), FakeResponse(json.dumps({"value": 1}))]
        )
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 1})
        self.assertEqual(len(client.messages.calls), 3)

    def test_connection_error_exceeds_retries_raises(self):
        client = FakeAnthropicClient(
            [make_connection_error(), make_connection_error(), make_connection_error()]
        )
        with self.assertRaises(AiModuleError):
            call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)

    def test_rate_limit_error_is_retried(self):
        client = FakeAnthropicClient([make_rate_limit_error(), FakeResponse(json.dumps({"value": 9}))])
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 9})

    def test_server_5xx_is_retried(self):
        client = FakeAnthropicClient([make_server_error(500), FakeResponse(json.dumps({"value": 9}))])
        result = call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(result, {"value": 9})

    def test_client_4xx_is_not_retried(self):
        client = FakeAnthropicClient([make_client_error(400)])
        with self.assertRaises(AiModuleError):
            call_ai_module(make_request(), client=client, sleep_fn=noop_sleep)
        self.assertEqual(len(client.messages.calls), 1)


if __name__ == "__main__":
    unittest.main()
