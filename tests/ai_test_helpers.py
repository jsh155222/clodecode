"""AI 모듈 테스트에서 공유하는 가짜(fake) Anthropic 클라이언트/응답 헬퍼.

실제 네트워크 호출 없이 client.py의 재시도/스키마 검증/폴백 로직을 검증하기 위한 것.
"""

from __future__ import annotations

import anthropic
import httpx


class FakeTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class FakeResponse:
    def __init__(self, text: str, stop_reason: str = "end_turn"):
        self.content = [FakeTextBlock(text)]
        self.stop_reason = stop_reason


class FakeMessages:
    def __init__(self, items):
        # items: FakeResponse 또는 Exception 인스턴스의 리스트. create() 호출마다 하나씩 소비됨.
        self._items = list(items)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._items:
            raise AssertionError("fake client에 준비된 응답보다 더 많이 호출됨")
        item = self._items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeAnthropicClient:
    def __init__(self, items):
        self.messages = FakeMessages(items)


def fake_request() -> httpx.Request:
    return httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def fake_httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code, request=fake_request())


def make_connection_error() -> anthropic.APIConnectionError:
    return anthropic.APIConnectionError(request=fake_request())


def make_rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError("rate limited", response=fake_httpx_response(429), body=None)


def make_server_error(status_code: int = 500) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(f"server error {status_code}", response=fake_httpx_response(status_code), body=None)


def make_client_error(status_code: int = 400) -> anthropic.APIStatusError:
    return anthropic.APIStatusError(f"client error {status_code}", response=fake_httpx_response(status_code), body=None)


def noop_sleep(_seconds: float) -> None:
    return None
