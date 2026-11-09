"""v6 전용 표현을 원문 인용·기존 AnswerAnalysis 값으로 복원한다."""

import re
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass

from devon_ai import contracts as c


@dataclass(frozen=True)
class AnswerUnit:
    id: str
    start_char: int
    end_char: int
    text: str


def answer_units(answer: str) -> tuple[AnswerUnit, ...]:
    """문자는 고치지 않는다. 128번째 구간에는 남은 원문 전체를 보존한다."""
    units: list[AnswerUnit] = []
    start = 0
    ends = [match.end() for match in re.finditer(r"[.!?。！？](?=\s|$)|\r?\n+", answer)]
    if not ends or ends[-1] != len(answer):
        ends.append(len(answer))
    for end in ends:
        while start < end:
            stop = len(answer) if len(units) == 127 else min(start + 1024, end)
            if answer[start:stop].strip():
                units.append(
                    AnswerUnit(f"answer:{len(units) + 1:04d}", start, stop, answer[start:stop])
                )
            start = stop
            if start == len(answer):
                return tuple(units)
    return tuple(units)


def _object(properties: dict[str, object]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def _array(item: Mapping[str, object], *, minimum: int = 0) -> dict[str, object]:
    # 공급자가 보장하지 않는 uniqueItems는 넣지 않고 실제 응답의 중복은 서버에서 거절한다.
    return {"type": "array", "items": dict(item), "minItems": minimum}


def output_schema(
    keys: tuple[str, ...],
    units: tuple[AnswerUnit, ...],
    evidence_refs: frozenset[str],
    locations: frozenset[tuple[str, str, str]],
) -> dict[str, object]:
    text = {"type": "string", "pattern": r"\S"}
    texts = _array(text)
    identifier = {"type": "string", "enum": [unit.id for unit in units]}
    quotes = {**_array(identifier), "maxItems": len(units)}
    refs = _array({"type": "string", **({"enum": sorted(evidence_refs)} if evidence_refs else {})})
    if not evidence_refs:
        refs["maxItems"] = 0
    optional = {"anyOf": [{"type": "null"}, {**quotes, "minItems": 1}]}

    def points(required: str | None = None) -> dict[str, object]:
        return _object(
            {key: {**quotes, "minItems": 1} if required in (key, "*") else optional for key in keys}
        )

    missing = {**_array({"type": "string", "enum": list(keys)}), "maxItems": len(keys)}

    def coverage(statuses: list[str], sufficiency: str | None, limits: int) -> dict[str, object]:
        covered = points("*") if sufficiency == "sufficient" else points()
        if sufficiency == "partial":
            covered = {"anyOf": [points(key) for key in keys]}
        return _object(
            {
                "evaluation_status": {"enum": statuses},
                "sufficiency": {"type": "null"} if sufficiency is None else {"enum": [sufficiency]},
                "covered_points": covered,
                "missing_points": {
                    **missing,
                    **(
                        {"maxItems": 0}
                        if sufficiency == "sufficient"
                        else {"minItems": 1}
                        if sufficiency is not None
                        else {}
                    ),
                },
                "limitations": {**texts, "minItems": limits},
            }
        )

    claim_variants = [
        _object(
            {
                "quote_id": identifier,
                "status": {"enum": ["unverified"]},
                "evidence_refs": refs,
                "limitations": {**texts, "minItems": 1},
            }
        )
    ]
    if evidence_refs:
        claim_variants.append(
            _object(
                {
                    "quote_id": identifier,
                    "status": {"enum": ["supported", "partially_supported", "conflicting"]},
                    "evidence_refs": {**refs, "minItems": 1},
                    "limitations": texts,
                }
            )
        )
    groups: dict[tuple[str, str], list[str]] = {}
    for repo, ref, path in sorted(locations):
        groups.setdefault((repo, ref), []).append(path)
    request_variants = [
        _object(
            {
                "claim_quote_id": identifier,
                "purpose": text,
                "repository_id": {"enum": [repo]},
                "git_ref": {"enum": [ref]},
                "allowed_paths": {**_array({"enum": paths}, minimum=1), "maxItems": len(paths)},
            }
        )
        for (repo, ref), paths in groups.items()
    ]
    requests = (
        _array({"anyOf": request_variants})
        if request_variants
        else {
            **_array(
                _object(
                    {
                        "claim_quote_id": identifier,
                        "purpose": text,
                        "repository_id": text,
                        "git_ref": text,
                        "allowed_paths": texts,
                    }
                )
            ),
            "maxItems": 0,
        }
    )
    return _object(
        {
            "coverage_assessment": {
                "anyOf": [
                    coverage(["evaluated"], "sufficient", 0),
                    coverage(["needs_clarification"], "sufficient", 1),
                    coverage(["evaluated", "needs_clarification"], "partial", 1),
                    coverage(["evaluated", "needs_clarification"], "insufficient", 1),
                    coverage(["evaluated", "needs_clarification", "not_evaluable"], None, 1),
                ]
            },
            "technical_assessment": _object(
                {
                    "explanation": text,
                    "quote_ids": quotes,
                    "evidence_refs": refs,
                    "limitations": texts,
                }
            ),
            "contribution_scope": {
                "anyOf": [
                    _object(
                        {
                            "scope": {"enum": ["unknown"]},
                            "quote_ids": quotes,
                            "unknown_reason": text,
                        }
                    ),
                    _object(
                        {
                            "scope": {"enum": ["self", "shared", "teammate"]},
                            "quote_ids": {**quotes, "minItems": 1},
                            "unknown_reason": {"type": "null"},
                        }
                    ),
                ]
            },
            "claim_checks": _array({"anyOf": claim_variants}),
            "verification_requests": requests,
            "external_queries": {
                **_array(
                    _object(
                        {
                            "query": text,
                            "purpose": text,
                        }
                    )
                ),
                "maxItems": 2,
            },
        }
    )


def units_payload(units: tuple[AnswerUnit, ...]) -> list[dict[str, object]]:
    return [asdict(unit) for unit in units]


def _fields(value: object, fields: Iterable[str], name: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != set(fields):
        raise c.ContractError("schema", name)
    return value


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value.strip():
        raise c.ContractError("schema", name)
    return value


def _strings(value: object, name: str) -> list[str]:
    if type(value) is not list:
        raise c.ContractError("schema", name)
    result = [_text(item, name) for item in value]
    if len(result) != len(set(result)):
        raise c.ContractError("semantic", "duplicate " + name)
    return result


def _items(value: object, name: str) -> list[object]:
    if type(value) is not list:
        raise c.ContractError("schema", name)
    if any(item in value[:index] for index, item in enumerate(value)):
        raise c.ContractError("semantic", "duplicate " + name)
    return value


def canonical_output(raw: object, *, answer: str, keys: tuple[str, ...]) -> dict[str, object]:
    """판정값을 바꾸지 않고 원문 ID·필드 배치·중복된 파생 flag만 표현 변환한다."""
    data = _fields(
        raw,
        (
            "coverage_assessment",
            "technical_assessment",
            "contribution_scope",
            "claim_checks",
            "verification_requests",
            "external_queries",
        ),
        "answer analysis wire",
    )
    source = {unit.id: unit.text for unit in answer_units(answer)}

    def quote(identifier: object) -> str:
        name = _text(identifier, "answer quote ID")
        if name not in source:
            raise c.ContractError("semantic", "answer quote ID")
        return source[name]

    def quotes(ids: object) -> list[str]:
        return [quote(identifier) for identifier in _strings(ids, "answer quote IDs")]

    coverage = _fields(
        data["coverage_assessment"],
        ("evaluation_status", "sufficiency", "covered_points", "missing_points", "limitations"),
        "coverage assessment",
    )
    covered = _fields(coverage["covered_points"], keys, "covered point keys")
    limits = _strings(coverage["limitations"], "coverage limitations")
    technical = _fields(
        data["technical_assessment"],
        ("explanation", "quote_ids", "evidence_refs", "limitations"),
        "technical assessment",
    )
    contribution = _fields(
        data["contribution_scope"], ("scope", "quote_ids", "unknown_reason"), "contribution scope"
    )
    if contribution["scope"] == "unknown":
        reason = _text(contribution["unknown_reason"], "unknown contribution reason")
        if reason not in limits:
            limits.append(reason)
    elif contribution["unknown_reason"] is not None:
        raise c.ContractError("schema", "known contribution reason")
    claims = []
    claim_ids: set[str] = set()
    for item in _items(data["claim_checks"], "claim checks"):
        claim = _fields(item, ("quote_id", "status", "evidence_refs", "limitations"), "claim check")
        identifier = _text(claim["quote_id"], "claim quote ID")
        if identifier in claim_ids:
            # 한 원문 unit의 혼합 주장은 한 partially_supported 판정과 한계로 표현한다.
            raise c.ContractError("semantic", "duplicate claim quote ID")
        claim_ids.add(identifier)
        claims.append(
            {
                "claim_text": quote(identifier),
                "status": claim["status"],
                "evidence_refs": _strings(claim["evidence_refs"], "claim evidence"),
                "limitations": _strings(claim["limitations"], "claim limitations"),
            }
        )
    requests = []
    for item in _items(data["verification_requests"], "verification requests"):
        request = _fields(
            item,
            ("claim_quote_id", "purpose", "repository_id", "git_ref", "allowed_paths"),
            "verification request",
        )
        requests.append(
            {
                "claim_text": quote(request["claim_quote_id"]),
                "purpose": _text(request["purpose"], "verification purpose"),
                "repository_id": request["repository_id"],
                "git_ref": request["git_ref"],
                "allowed_paths": _strings(request["allowed_paths"], "verification paths"),
            }
        )
    external = []
    for item in _items(data["external_queries"], "external queries"):
        query = _fields(item, ("query", "purpose"), "external query")
        external.append({key: _text(value, "external query") for key, value in query.items()})
    if len(external) > 2:
        raise c.ContractError("semantic", "external query count")
    return {
        "evaluation_status": coverage["evaluation_status"],
        "sufficiency": coverage["sufficiency"],
        "covered_points": [
            {"key": key, "answer_quotes": quotes(ids)}
            for key, ids in covered.items()
            if ids is not None
        ],
        "missing_points": _strings(coverage["missing_points"], "missing points"),
        "technical_assessment": {
            "explanation": _text(technical["explanation"], "technical explanation"),
            "answer_quotes": quotes(technical["quote_ids"]),
            "evidence_refs": _strings(technical["evidence_refs"], "technical evidence"),
            "limitations": _strings(technical["limitations"], "technical limitations"),
        },
        "contribution_scope": {
            "scope": contribution["scope"],
            "answer_quotes": quotes(contribution["quote_ids"]),
        },
        "claim_checks": claims,
        "verification_requests": requests,
        "external_queries": external,
        # 요청 유무를 중복 출력시키지 않는다. 실제 요청 배열의 존재 여부만 나타낸다.
        "needs_verification": bool(requests or external),
        "limitations": limits,
    }


def validate_wire_constraints(raw: object) -> None:
    """공용 의미 검증 뒤 v6에서 추가한 명시적 한계·nullable 조건을 확인한다."""
    assert isinstance(raw, dict)
    coverage = raw["coverage_assessment"]
    assert isinstance(coverage, dict)
    if (
        coverage["sufficiency"] != "sufficient" or coverage["evaluation_status"] != "evaluated"
    ) and not coverage["limitations"]:
        raise c.ContractError("semantic", "coverage limitations")
