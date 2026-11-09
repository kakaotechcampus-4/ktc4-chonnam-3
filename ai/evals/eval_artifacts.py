"""서비스 평가의 검증된 내부 Claim 관찰 형식. 공개 응답과 정답은 포함하지 않는다."""

from __future__ import annotations

import copy
from typing import Any

ARTIFACT_VERSION = "validated-report-claims.v1"
_SUMMARY = {"summary.strengths", "summary.gaps", "summary.follow_ups", "summary.practice_actions"}
_PERSONA = {"strengths", "improvements", "practice_actions"}
_KEYS = {"section", "persona", "claim_index", "text", "turn_refs", "evidence_refs"}


def validate_artifacts(value: object) -> dict[str, Any]:
    """파일 해시는 서명이 아니다. 알려진 형식과 원본 생성기 경계를 함께 확인한다."""
    if (
        type(value) is not dict
        or set(value) != {"schema_version", "claims"}
        or value.get("schema_version") != ARTIFACT_VERSION
        or type(value.get("claims")) is not list
    ):
        raise ValueError("invalid evaluation artifacts schema")
    identities = set()
    for claim in value["claims"]:
        if (
            type(claim) is not dict
            or set(claim) != _KEYS
            or type(claim["section"]) is not str
            or type(claim["text"]) is not str
            or not claim["text"].strip()
            or type(claim["claim_index"]) is not int
            or claim["claim_index"] < 0
        ):
            raise ValueError("invalid evaluation artifacts claim")
        if not (
            claim["section"] in _SUMMARY
            and claim["persona"] is None
            or claim["section"] in _PERSONA
            and claim["persona"] in {"hr_manager", "tech_lead", "domain_lead"}
        ):
            raise ValueError("invalid evaluation artifacts section")
        for key in ("turn_refs", "evidence_refs"):
            refs = claim[key]
            if (
                type(refs) is not list
                or any(type(ref) is not str or not ref.strip() for ref in refs)
                or len(set(refs)) != len(refs)
            ):
                raise ValueError("invalid evaluation artifacts references")
        if not claim["turn_refs"] and not claim["evidence_refs"]:
            raise ValueError("unreferenced evaluation artifacts claim")
        identity = (claim["section"], claim["persona"], claim["claim_index"])
        if identity in identities:
            raise ValueError("duplicate evaluation artifacts claim")
        identities.add(identity)
    return copy.deepcopy(value)
