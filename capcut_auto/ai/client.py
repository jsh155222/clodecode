"""공통 AI 모듈 호출 레이어.

- 시스템 프롬프트와 입력 데이터를 분리해서 보낸다.
- 가능한 경우 Claude Structured Outputs(output_config.format)로 JSON Schema를 강제한다.
- 응답을 다시 한 번 코드에서 JSON Schema로 검증한다 (모델이 스키마를 어겼을 가능성 대비).
- 네트워크 오류(연결 오류/429/5xx)는 최대 2회 재시도한다.
- JSON 파싱/스키마 검증에 실패하면 오류 내용을 알려주고 1회만 수정을 요청한다.
- 그래도 실패하면 AiModuleError를 던진다 - 호출자는 이 예외를 잡아 해당 기능만 폴백해야 한다.
- 입력 데이터(영상 내용/자막 등 사용자 데이터)는 로그에 남기지 않는다. 모듈 이름과 오류 종류만 남긴다.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Generic, Optional, TypeVar

import anthropic
import jsonschema

logger = logging.getLogger("capcut_auto.ai")

DEFAULT_MODEL = "claude-opus-4-8"
MAX_NETWORK_RETRIES = 2
MAX_REPAIR_ATTEMPTS = 1

TInput = TypeVar("TInput")


class AiModuleError(Exception):
    """AI 모듈 호출이 재시도/수정 요청까지 실패했을 때 발생한다.

    호출자는 이 예외를 잡아 해당 기능만 비-AI 폴백 로직으로 전환해야 한다
    (다른 기능까지 함께 죽이면 안 됨).
    """

    def __init__(self, module_name: str, reason: str):
        self.module_name = module_name
        self.reason = reason
        super().__init__(f"[{module_name}] AI 모듈 호출 실패: {reason}")


@dataclass
class AiModuleRequest(Generic[TInput]):
    module_name: str
    system_prompt: str
    input_data: TInput
    output_schema: dict


def _get_client() -> anthropic.Anthropic:
    # ANTHROPIC_API_KEY 환경변수에서 읽는다. 프론트엔드에는 절대 노출되지 않는다
    # (이 함수는 서버 프로세스 안에서만 호출됨).
    return anthropic.Anthropic()


def _validate_schema(data: Any, schema: dict) -> Optional[str]:
    """스키마를 위반하면 오류 메시지 문자열을, 통과하면 None을 반환한다."""
    try:
        jsonschema.validate(instance=data, schema=schema)
        return None
    except jsonschema.ValidationError as exc:
        return exc.message


def call_ai_module(
    request: AiModuleRequest[TInput],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 8000,
    client: Optional[anthropic.Anthropic] = None,
    sleep_fn=time.sleep,
) -> Any:
    """AI 모듈을 호출하고 output_schema를 만족하는 파싱된 JSON(dict/list)을 반환한다.

    실패(네트워크 재시도 초과, 스키마 오류 수정 요청까지 실패, 안전 거부)하면
    AiModuleError를 던진다.
    """
    cc = client or _get_client()
    user_content = json.dumps(request.input_data, ensure_ascii=False)

    messages: list = [{"role": "user", "content": user_content}]
    output_format = {"type": "json_schema", "schema": request.output_schema}

    repair_used = False
    network_attempt = 0

    while True:
        try:
            response = cc.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=request.system_prompt,
                messages=messages,
                output_config={"format": output_format},
            )
        except (anthropic.APIConnectionError, anthropic.RateLimitError) as exc:
            network_attempt += 1
            logger.warning(
                "[%s] network error (attempt %d/%d): %s",
                request.module_name,
                network_attempt,
                MAX_NETWORK_RETRIES,
                type(exc).__name__,
            )
            if network_attempt > MAX_NETWORK_RETRIES:
                raise AiModuleError(
                    request.module_name, f"네트워크 오류 재시도 초과: {type(exc).__name__}"
                ) from exc
            sleep_fn(min(2**network_attempt, 8))
            continue
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                network_attempt += 1
                logger.warning(
                    "[%s] server error (attempt %d/%d): %s",
                    request.module_name,
                    network_attempt,
                    MAX_NETWORK_RETRIES,
                    exc.status_code,
                )
                if network_attempt > MAX_NETWORK_RETRIES:
                    raise AiModuleError(
                        request.module_name, f"서버 오류 재시도 초과: {exc.status_code}"
                    ) from exc
                sleep_fn(min(2**network_attempt, 8))
                continue
            raise AiModuleError(request.module_name, f"요청 오류: {exc.status_code}") from exc

        if response.stop_reason == "refusal":
            raise AiModuleError(request.module_name, "모델이 안전 정책으로 응답을 거부했습니다")

        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise AiModuleError(request.module_name, "텍스트 응답을 받지 못했습니다")

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            error_summary = f"JSON 파싱 실패: {exc}"
            logger.warning("[%s] %s", request.module_name, error_summary)
            if repair_used:
                raise AiModuleError(request.module_name, error_summary) from exc
            repair_used = True
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"응답이 올바른 JSON이 아닙니다 ({exc}). "
                        "지정된 JSON Schema에 맞는 유효한 JSON만 다시 반환하세요."
                    ),
                }
            )
            continue

        schema_error = _validate_schema(parsed, request.output_schema)
        if schema_error is not None:
            error_summary = f"스키마 검증 실패: {schema_error}"
            logger.warning("[%s] %s", request.module_name, error_summary)
            if repair_used:
                raise AiModuleError(request.module_name, error_summary)
            repair_used = True
            messages.append({"role": "assistant", "content": text})
            messages.append(
                {
                    "role": "user",
                    "content": f"응답이 JSON Schema를 위반했습니다: {schema_error}. 스키마에 맞게 다시 반환하세요.",
                }
            )
            continue

        return parsed
