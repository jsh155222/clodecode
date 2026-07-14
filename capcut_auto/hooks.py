"""영상 도입부 훅(hook) 문구 생성기.

주의: 이것은 실제 생성형 AI(LLM)가 아니라, 카테고리별 키워드(categories.py)와
고정 문장 템플릿을 조합하는 규칙 기반 휴리스틱이다. LLM API 키 인프라가
프로젝트에 아직 없어서(환경변수/키 관리 전무) 이번 단계에서는 이 방식으로
"실제로 동작하는" 훅 제안 기능을 제공하고, 추후 실제 LLM을 연결할 때는
이 모듈의 generate_hook_suggestions() 시그니처만 유지한 채 내부 구현을
교체하면 된다.
"""

from __future__ import annotations

from typing import List

from .categories import ContentCategory, get_rule

_TEMPLATES = [
    "{topic}, {keyword}",
    "{keyword}: {topic}",
    "{topic} 편 — {keyword}",
    "{keyword}! {topic} 지금 확인하세요",
]


def generate_hook_suggestions(topic: str, category: ContentCategory, max_suggestions: int = 3) -> List[str]:
    """주제와 카테고리를 바탕으로 훅 문구 후보 리스트를 만든다.

    같은 (topic, category) 입력에는 항상 같은 결과를 반환하는 순수 함수다.
    """
    clean_topic = topic.strip()
    if not clean_topic:
        raise ValueError("topic은 비어 있을 수 없습니다.")
    if max_suggestions <= 0:
        return []

    rule = get_rule(category)
    suggestions: List[str] = []
    for i, keyword in enumerate(rule.hook_keywords):
        template = _TEMPLATES[i % len(_TEMPLATES)]
        suggestions.append(template.format(topic=clean_topic, keyword=keyword))
        if len(suggestions) >= max_suggestions:
            break
    return suggestions
