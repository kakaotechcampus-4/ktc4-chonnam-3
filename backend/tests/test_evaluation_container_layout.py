"""Compose와 같은 읽기 전용 자료 배치를 구성해 출처 검증의 연결을 확인한다."""

import shutil
from pathlib import Path

import pytest

from scripts import run_ai_evaluation as cli
from tests.test_ai_evaluation_cli import ROOT, args


def stage_mounts(tmp_path: Path, cohort: str) -> Path:
    evaluation = tmp_path / "srv/ai/evals"
    evaluation.mkdir(parents=True)
    source = ROOT / "ai/evals"
    # COPY *.py만으로는 제공되지 않는 자료를 실제 Compose의 형제 마운트로 재현한다.
    for sibling in ("source_snapshot_20261108", "service_regression"):
        shutil.copytree(source / sibling, evaluation / sibling)
    shutil.copytree(source / cohort, evaluation / "cases")
    shutil.copytree(ROOT / "ai/prompts", evaluation.parent / "prompts")
    return evaluation / "cases"


def forbid_provider(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("layout validation must not load provider settings or call a model")

    monkeypatch.setattr(cli, "get_settings", forbidden)
    monkeypatch.setattr(cli, "Settings", forbidden)
    monkeypatch.setattr(cli, "call_model", forbidden)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("cohort", "manifest", "total"),
    [
        ("service_regression", "runtime-manifest.json", 32),
        ("component_regression", "manifest.json", 1),
        ("report_source_binding_cohort", "manifest.json", 8),
    ],
)
async def test_compose_reference_layout_validates_each_selected_cohort_without_providers(
    monkeypatch, tmp_path, cohort, manifest, total
):
    forbid_provider(monkeypatch)
    cases = stage_mounts(tmp_path, cohort)
    result = await cli.execute(
        args(cases=cases, manifest=cases / manifest, split="all", approved_only=False)
    )
    assert result["summary"]["statuses"] == {"validated_only": total}
    assert result["summary"]["release_gate_passed"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("missing", "message"),
    [
        ("source_snapshot_20261108", "Invalid historical source snapshot"),
        ("service_regression", "Source provenance file is unavailable"),
    ],
)
async def test_missing_reference_mount_fails_before_provider_settings(
    monkeypatch, tmp_path, missing, message
):
    forbid_provider(monkeypatch)
    cases = stage_mounts(tmp_path, "report_source_binding_cohort")
    shutil.rmtree(cases.parent / missing)
    with pytest.raises(ValueError, match=message):
        await cli.execute(
            args(cases=cases, manifest=cases / "manifest.json", split="all", approved_only=False)
        )


def test_compose_keeps_reference_mounts_separate_from_executable_evaluation_modules():
    compose = (ROOT / "compose.evaluation.yaml").read_text("utf-8")
    for target in ("cases", "source_snapshot_20261108", "service_regression"):
        assert f"target: /srv/ai/evals/{target}\n" in compose
    image = (ROOT / "backend/Dockerfile.evaluation").read_text("utf-8")
    assert "COPY ai/evals/*.py /srv/ai/evals/" in image
    assert "COPY ai/evals/ /srv/ai/evals/" not in image
