from importlib import import_module, metadata
from pathlib import Path

BOUNDARY_MODULES = (
    "app.agents.contracts",
    "app.agents.director.agent",
    "app.agents.director.tools",
    "app.llm_tasks.repo_shallow",
    "app.llm_tasks.repo_deep",
    "app.llm_tasks.answer_analysis",
    "app.llm_tasks.report",
)


def test_backend_can_import_ai_distribution() -> None:
    package = import_module("devon_ai")

    assert package.__file__ is not None
    expected_package = (
        Path(__file__).resolve().parents[3] / "ai" / "src" / "devon_ai" / "__init__.py"
    )
    assert Path(package.__file__).resolve() == expected_package.resolve()
    assert metadata.version("devon-ai") == "0.1.0"

    for module_name in BOUNDARY_MODULES:
        import_module(module_name)
