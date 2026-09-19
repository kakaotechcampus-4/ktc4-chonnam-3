import ast
from pathlib import Path

import pytest

FORBIDDEN_IMPORT_ROOTS = {
    "anthropic",
    "app",
    "arq",
    "backend",
    "fastapi",
    "openai",
    "redis",
    "sqlalchemy",
}


def _direct_forbidden_imports(source):
    forbidden = set()

    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots = (alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = (node.module.split(".", 1)[0],)
        else:
            continue

        forbidden.update(root for root in roots if root in FORBIDDEN_IMPORT_ROOTS)

    return tuple(sorted(forbidden))


@pytest.mark.parametrize(
    ("source", "expected"),
    (
        ("import pathlib", ()),
        ("from collections.abc import Iterable", ()),
        ("from .backend import local_helper", ()),
        ("from .. import app", ()),
        ("import anthropic", ("anthropic",)),
        ("from arq import cron", ("arq",)),
        ("import backend", ("backend",)),
        ("import os, redis as cache", ("redis",)),
        ("import pathlib, app.services", ("app",)),
        ("from fastapi import FastAPI", ("fastapi",)),
        ("from sqlalchemy.orm import Session", ("sqlalchemy",)),
        ("from openai.resources import Responses", ("openai",)),
    ),
)
def test_direct_import_checker_distinguishes_dependency_boundaries(source, expected):
    assert _direct_forbidden_imports(source) == expected


def test_installed_ai_source_has_no_forbidden_direct_imports():
    import devon_ai

    package_root = Path(devon_ai.__file__).parent
    violations = {
        str(path.relative_to(package_root)): imports
        for path in package_root.rglob("*.py")
        if (imports := _direct_forbidden_imports(path.read_text(encoding="utf-8")))
    }

    assert violations == {}
