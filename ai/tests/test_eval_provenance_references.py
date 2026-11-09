"""보고서 코호트가 선언한 이전 입력·기대값·template 지문을 모두 검사한다."""

import json
import shutil
from pathlib import Path

import pytest
from source_snapshot import validate_bound_sources

EVALS = Path(__file__).parents[1] / "evals"


@pytest.fixture
def cohort(tmp_path):
    for name in ("source_snapshot_20261108", "service_regression", "report_source_binding_cohort"):
        shutil.copytree(EVALS / name, tmp_path / name)
    return tmp_path / "report_source_binding_cohort"


@pytest.mark.parametrize(
    "relative",
    [
        "service_regression/inputs/r-0001.v2.json",
        "service_regression/expectations/r-0001.v2.json",
        "service_regression/inputs/r-0009.v2.json",
    ],
)
def test_prior_source_mutation_is_rejected_before_case_execution(cohort, relative):
    validate_bound_sources(cohort)
    source = cohort.parent / relative
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="fingerprint"):
        validate_bound_sources(cohort)


@pytest.mark.parametrize(
    "field",
    ["prior_binding_sha256", "prior_expectation_sha256", "snapshot_template_sha256"],
)
def test_every_declared_prior_hash_is_checked(cohort, field):
    path = cohort / "binding-manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["cases"][0][field] = "0" * 64
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        validate_bound_sources(cohort)


def test_prior_reference_cannot_escape_the_named_cohort(cohort):
    path = cohort / "binding-manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    manifest["cases"][0]["prior_binding"] = "../outside"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="reference"):
        validate_bound_sources(cohort)
