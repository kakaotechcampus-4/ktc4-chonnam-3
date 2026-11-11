"""서비스가 실제로 읽은 레포 원문을 해시로 묶어 공통 Judge 문맥에 투영한다."""

import json
from typing import Any

from async_grader import content_hash
from judge_context import build_judge_context


def source_context(snapshot: dict[str, Any]) -> dict[str, Any]:
    if (
        set(snapshot) != {"schema_version", "task", "repository", "selection"}
        or snapshot["schema_version"] != "repository-sources.v1"
        or snapshot["task"] not in {"repo_shallow", "repo_deep"}
        or not isinstance(snapshot["repository"], dict)
        or not isinstance(snapshot["selection"], dict)
    ):
        raise ValueError("invalid repository source snapshot")
    repository = snapshot["repository"]
    evidence = []
    if snapshot["task"] == "repo_shallow":
        # README 확장자·경로를 수집하지 않았다면 README.md라고 추정하지 않는다.
        evidence.append(
            {
                "id": "readme",
                "source_field": "readme_text",
                "content": repository.get("readme_text") or "",
            }
        )
        evidence.extend(repository.get("supporting_files", []))
        metadata = {
            key: repository[key]
            for key in (
                "description",
                "languages",
                "structure",
                "collection_errors",
                "source_limitations",
            )
            if key in repository
        }
        evidence.append(
            {
                "id": "collection-metadata",
                "source_field": "collection_metadata",
                "content": json.dumps(metadata, ensure_ascii=False),
            }
        )
        evidence.append(
            {
                "id": "collection-scope",
                "source_field": "collection_scope",
                "content": json.dumps(
                    {
                        "readme_truncated": repository.get("readme_truncated"),
                        "readme_selection": snapshot["selection"].get("model_view"),
                        "collection_errors": repository.get("collection_errors", []),
                        "metadata_scope": (
                            "languages/commit counts are collection-time metadata, "
                            "not SHA-pinned code or authorship proof"
                        ),
                    },
                    ensure_ascii=False,
                ),
            }
        )
    else:
        evidence.extend(repository.get("sources", []))
    return build_judge_context(
        {
            "task": snapshot["task"],
            "text_hash": content_hash(snapshot),
            "repositories": [
                {
                    "repository_id": repository["repository_id"],
                    "git_ref": repository["head_sha"],
                    "evidence": evidence,
                }
            ],
            "limitations": snapshot["selection"].get("limitations", []),
        }
    )
