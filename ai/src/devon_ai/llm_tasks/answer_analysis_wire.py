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
