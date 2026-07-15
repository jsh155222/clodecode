"""각 AI 모듈의 출력 JSON Schema. Claude Structured Outputs(output_config.format)와
응답 검증(client.py의 _validate_schema) 양쪽에 그대로 사용된다.
"""

from __future__ import annotations

VIDEO_SECTION_ROLES = [
    "HOOK",
    "PROBLEM",
    "CAUSE",
    "SOLUTION",
    "PROCESS",
    "PROOF",
    "RESULT",
    "CTA",
    "TRANSITION",
    "UNKNOWN",
]

VIDEO_STRUCTURE_SCHEMA = {
    "type": "object",
    "properties": {
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "role": {"type": "string", "enum": VIDEO_SECTION_ROLES},
                    "summary": {"type": "string"},
                },
                "required": ["start", "end", "role", "summary"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["sections"],
    "additionalProperties": False,
}

CUT_ACTIONS = ["AUTO_CUT", "REVIEW", "KEEP"]

CUT_CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "action": {"type": "string", "enum": CUT_ACTIONS},
                    "reasonCode": {"type": "string"},
                    "reason": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "contextRisk": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "start",
                    "end",
                    "action",
                    "reasonCode",
                    "reason",
                    "confidence",
                    "contextRisk",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["candidates"],
    "additionalProperties": False,
}

SUBTITLE_OPTIMIZE_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "text": {"type": "string"},
                },
                "required": ["id", "start", "end", "text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}

SUBTITLE_HIGHLIGHT_TYPES = [
    "NUMBER",
    "PRICE",
    "DURATION",
    "PROBLEM",
    "RISK",
    "RESULT",
    "ACTION",
    "PRODUCT",
    "COMPARISON",
]

SUBTITLE_HIGHLIGHT_SCHEMA = {
    "type": "object",
    "properties": {
        "lines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "highlights": {
                        "type": "array",
                        "maxItems": 2,
                        "items": {
                            "type": "object",
                            "properties": {
                                "word": {"type": "string"},
                                "type": {"type": "string", "enum": SUBTITLE_HIGHLIGHT_TYPES},
                            },
                            "required": ["word", "type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "highlights"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["lines"],
    "additionalProperties": False,
}

HOOK_TYPES = [
    "PROBLEM",
    "CURIOSITY",
    "BEFORE_AFTER",
    "LOSS",
    "EXPERIMENT",
    "CONFESSION",
    "RESULT_FIRST",
    "QUESTION",
]

HOOK_CANDIDATES_SCHEMA = {
    "type": "object",
    "properties": {
        "hooks": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": HOOK_TYPES},
                    "evidenceSegmentIds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                    },
                    "exaggerationRisk": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": ["text", "type", "evidenceSegmentIds", "exaggerationRisk"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hooks"],
    "additionalProperties": False,
}
