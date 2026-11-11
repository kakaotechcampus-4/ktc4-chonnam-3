"""Codex의 저장 판정을 동일한 원문·기준·후보에만 연결한다."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from async_grader import Judgment, content_hash
from judge_context import validate_judge_context

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_JUDGMENTS = 1000
_HASHES = ("rubric_sha256", "candidate_sha256", "source_context_sha256")
_STATUSES = {"satisfied", "violated", "unclear"}


def _keys(value: object, expected: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("invalid recorded judgment fields")
    return value


def _text(value: object, maximum: int = 20000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate recorded judgment JSON key")
        result[key] = value
    return result


class RecordedGrader:
    def __init__(self, document: object) -> None:
        data = _keys(document, {"format_version", "reviewer", "judgments"})
        if type(data["format_version"]) is not int or data["format_version"] != 1:
            raise ValueError("unsupported recorded judgment version")
        reviewer = _keys(data["reviewer"], {"kind", "actor", "review_context", "model_id"})
        if (
            reviewer["kind"] != "codex_source_review"
            or not _text(reviewer["actor"], 200)
            or type(reviewer["review_context"]) is not str
            or reviewer["review_context"]
            not in {"implementation_session", "separate_review_session"}
            or reviewer["model_id"] is not None
            and not _text(reviewer["model_id"], 200)
        ):
            raise ValueError("invalid recorded reviewer")
        entries = data["judgments"]
        if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_JUDGMENTS:
            raise ValueError("invalid recorded judgment count")
        self.reviewer = copy.deepcopy(reviewer)
        self.document_sha256 = content_hash(data)
        self.records: list[dict[str, Any]] = []
        self._entries: dict[tuple[str, ...], dict[str, Any]] = {}
        for value in entries:
            item = _keys(value, {"binding", "verdict", "reason_summary", "criterion_results"})
            binding = _keys(item["binding"], set(_HASHES))
            if any(
                not isinstance(binding[key], str)
                or len(binding[key]) != 64
                or any(char not in "0123456789abcdef" for char in binding[key])
                for key in _HASHES
            ):
                raise ValueError("invalid recorded binding hash")
            results = item["criterion_results"]
            if (
                not _text(item["reason_summary"])
                or not isinstance(results, list)
                or not 1 <= len(results) <= 100
            ):
                raise ValueError("invalid recorded criteria")
            identifiers = set()
            statuses = set()
            for result in results:
                criterion = _keys(result, {"id", "status", "reason"})
                if (
                    not _text(criterion["id"], 200)
                    or criterion["id"] in identifiers
                    or type(criterion["status"]) is not str
                    or criterion["status"] not in _STATUSES
                    or not _text(criterion["reason"])
                ):
                    raise ValueError("invalid recorded criterion")
                identifiers.add(criterion["id"])
                statuses.add(criterion["status"])
            expected = (
                "reject"
                if "violated" in statuses
                else "ambiguous"
                if "unclear" in statuses
                else "accept"
            )
            if item["verdict"] != expected:
                raise ValueError("recorded verdict contradicts criteria")
            identity = tuple(binding[key] for key in _HASHES)
            if identity in self._entries:
                raise ValueError("duplicate recorded judgment binding")
            self._entries[identity] = copy.deepcopy(item)

    @classmethod
    def from_path(cls, path: Path) -> RecordedGrader:
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ValueError("recorded judgment file exceeds byte limit")
        return cls(json.loads(data.decode("utf-8-sig"), object_pairs_hook=_pairs))

    def __call__(self, rubric: dict[str, Any], output: str) -> Judgment:
        return Judgment(None, failure={"stage": "judge", "error_code": "recorded_source_required"})

    def judge_with_context(
        self, rubric: dict[str, Any], output: str, source_context: object
    ) -> Judgment:
        checked = validate_judge_context(source_context)
        visible = {key: rubric[key] for key in ("allowed", "forbidden")}
        binding = {
            "rubric_sha256": content_hash(visible),
            "candidate_sha256": content_hash(output),
            "source_context_sha256": content_hash(checked),
        }
        item = self._entries.get(tuple(binding[key] for key in _HASHES))
        metadata = {
            "kind": "recorded_source_review",
            "reviewer": copy.deepcopy(self.reviewer),
            "recorded_document_sha256": self.document_sha256,
            "provider_calls": 0,
            "original_review_usage": "not_collected",
        }
        if item is None:
            result = Judgment(
                None,
                failure={"stage": "judge", "error_code": "recorded_judgment_not_found"},
                metadata=metadata,
            )
        else:
            expected_ids = []
            for group, entries in visible.items():
                for index, criterion in enumerate(entries):
                    identifier = criterion.get("id") if isinstance(criterion, dict) else None
                    key = (
                        identifier
                        if isinstance(identifier, str) and identifier.strip()
                        else str(index)
                    )
                    expected_ids.append(f"{group}:{key}")
            supplied = {entry["id"] for entry in item["criterion_results"]}
            if len(set(expected_ids)) != len(expected_ids) or supplied != set(expected_ids):
                result = Judgment(
                    None,
                    failure={"stage": "judge", "error_code": "recorded_criteria_mismatch"},
                    metadata=metadata,
                )
            else:
                result = Judgment(
                    item["verdict"],
                    output={
                        key: copy.deepcopy(item[key])
                        for key in ("verdict", "reason_summary", "criterion_results")
                    },
                    metadata=metadata,
                )
        self.records.append(
            {"binding": binding, "verdict": result.verdict, "failure": result.failure}
        )
        return result
