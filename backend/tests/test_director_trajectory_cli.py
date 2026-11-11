"""9턴 재개 CLI가 설정·질문 바인딩을 검사하고 기본 모드에서 호출하지 않는지 확인한다."""

import hashlib
import json
from dataclasses import asdict

import pytest
from director_cases import build_cohort, content_hash

from scripts.run_director_trajectory import execute, load_seed_file, parser


def seed_file(tmp_path):
    case = build_cohort().select("pilot")[0]
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(asdict(case), ensure_ascii=False), encoding="utf-8")
    return path


def test_external_seed_preserves_exact_case_and_file_bytes_binding(tmp_path):
    path = seed_file(tmp_path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    case, metadata = load_seed_file(path, expected)
    assert case.case_id == "dq-01-partial"
    assert metadata["sha256"] == expected
    assert metadata["bytes"] == len(path.read_bytes())
    assert metadata["payload_sha256"] == content_hash(case.payload)
    assert set(asdict(case)) == {
        "case_id",
        "version",
        "kind",
        "split",
        "source_group_id",
        "payload",
        "expectation",
    }


@pytest.mark.parametrize(
    "broken",
    [
        "extra_field",
        "mismatched_version",
        "mixed_source_version",
        "duplicate",
        "too_large",
        "wrong_hash",
        "invalid_split",
        "boolean_version",
    ],
)
def test_invalid_external_seed_is_rejected_before_provider_configuration(tmp_path, broken):
    path = seed_file(tmp_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    expected = None
    if broken == "extra_field":
        data["provenance"] = {"do_not_send_to_model": True}
    elif broken == "mismatched_version":
        data["expectation"]["version"] = data["version"] + 1
    elif broken == "mixed_source_version":
        data["payload"]["service_input"]["context"]["evidence"][0]["git_ref"] = "b" * 40
    elif broken == "wrong_hash":
        expected = "0" * 64
    elif broken == "invalid_split":
        data["split"] = {}
    elif broken == "boolean_version":
        data["version"] = 1
        data["expectation"]["version"] = True
    if broken == "duplicate":
        path.write_text('{"case_id":"first","case_id":"second"}', encoding="utf-8")
    elif broken == "too_large":
        path.write_bytes(b" " * (512 * 1024 + 1))
    else:
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(ValueError):
        load_seed_file(path, expected)


def manifest(tmp_path):
    for name in ("director", "answer_analysis"):
        (tmp_path / f"{name}.md").write_text("fixture", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "prompts": [
                    {
                        "task_name": "director",
                        "version": "director_v8",
                        "model": "gpt-6-luna",
                        "template_path": "director.md",
                    },
                    {
                        "task_name": "answer_analysis",
                        "version": "answer_analysis_v2",
                        "model": "gpt-6-luna",
                        "template_path": "answer_analysis.md",
                    },
                ],
                "limits": {
                    "timeout_seconds": 30,
                    "max_output_tokens": 1000,
                    "max_input_bytes": 262144,
                    "max_response_bytes": 1048576,
                },
            }
        ),
        encoding="utf-8",
    )
    return manifest


async def test_default_trajectory_validation_does_not_load_environment(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("validation must not load provider credentials")

    monkeypatch.setattr("scripts.run_director_trajectory.get_settings", forbidden)
    prepared_manifest = manifest(tmp_path)
    output = tmp_path / "step-00.json"
    result = await execute(
        parser().parse_args(
            [
                "--manifest",
                str(prepared_manifest),
                "--session-id",
                "session",
                "--seed-case-id",
                "dq-01-partial",
                "--output",
                str(output),
            ]
        )
    )
    assert result["trajectory"]["status"] == "validated_only"
    assert result["metadata"]["model_api_calls"] == 0
    assert result["trajectory"]["normal_model_attempts"] == 27
    assert len(result["trajectory"]["turns"]) == 0


@pytest.mark.parametrize("omit_defaults", [False, True])
async def test_external_seed_cli_validates_without_calls_and_keeps_file_binding(
    tmp_path, monkeypatch, omit_defaults
):
    def forbidden(*args, **kwargs):
        raise AssertionError("validation must not load provider credentials")

    monkeypatch.setattr("scripts.run_director_trajectory.get_settings", forbidden)
    path = seed_file(tmp_path)
    if omit_defaults:
        raw = json.loads(path.read_text(encoding="utf-8"))
        for field in ("external_searches", "supplemental_sources", "supplemental_limitations"):
            raw["payload"]["service_input"]["context"].pop(field)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    result = await execute(
        parser().parse_args(
            [
                "--manifest",
                str(manifest(tmp_path)),
                "--seed-file",
                str(path),
                "--seed-sha256",
                expected,
                "--session-id",
                "file-session",
                "--output",
                str(tmp_path / "file-result.json"),
            ]
        )
    )
    assert result["trajectory"]["status"] == "validated_only"
    assert result["trajectory"]["source_case"] == "dq-01-partial.v2"
    assert result["metadata"]["seed_file"]["sha256"] == expected
    assert result["metadata"]["seed_file"]["provenance_verified"] is False
    assert result["metadata"]["model_api_calls"] == 0
    assert "expectation" not in result["trajectory"]["materials"]


async def test_resuming_cannot_replace_source_with_a_seed_file(tmp_path):
    args = parser().parse_args(
        [
            "--manifest",
            str(manifest(tmp_path)),
            "--resume",
            str(tmp_path / "unused.json"),
            "--seed-file",
            str(seed_file(tmp_path)),
            "--output",
            str(tmp_path / "output.json"),
        ]
    )
    with pytest.raises(ValueError, match="resume cannot replace"):
        await execute(args)


def test_cohort_and_file_seed_selection_is_mutually_exclusive(tmp_path):
    with pytest.raises(SystemExit):
        parser().parse_args(
            [
                "--manifest",
                "unused.json",
                "--seed-case-id",
                "dq-01-partial",
                "--seed-file",
                "seed.json",
                "--output",
                str(tmp_path / "unused.json"),
            ]
        )
