import importlib
import importlib.metadata
import importlib.resources
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

MODULE_NAMES = (
    "devon_ai",
    "devon_ai.contracts",
    "devon_ai.agents",
    "devon_ai.agents.director",
    "devon_ai.agents.director.agent",
    "devon_ai.agents.director.tools",
    "devon_ai.llm_tasks",
    "devon_ai.llm_tasks.repo_shallow",
    "devon_ai.llm_tasks.repo_deep",
    "devon_ai.llm_tasks.answer_analysis",
    "devon_ai.llm_tasks.report",
)

FORBIDDEN_MODULE_ROOTS = {
    "anthropic",
    "app",
    "arq",
    "backend",
    "fastapi",
    "openai",
    "redis",
    "sqlalchemy",
}


@pytest.mark.parametrize("module_name", MODULE_NAMES)
def test_module_is_installable(module_name):
    module = importlib.import_module(module_name)

    assert module.__spec__ is not None
    assert module.__spec__.name == module_name


def test_installed_distribution_has_expected_metadata_and_type_marker():
    assert importlib.metadata.version("devon-ai") == "0.1.0"
    assert importlib.resources.files("devon_ai").joinpath("py.typed").is_file()


def test_imports_are_isolated_from_repository_and_external_services(tmp_path):
    script = textwrap.dedent(
        f"""
        import os
        import socket
        import sqlite3
        import subprocess
        import sys
        import urllib.request

        module_names = {MODULE_NAMES!r}
        forbidden_roots = {FORBIDDEN_MODULE_ROOTS!r}

        def blocked(*args, **kwargs):
            raise RuntimeError("forbidden import side effect")

        class GuardedEnvironment(dict):
            def _blocked(self, *args, **kwargs):
                raise RuntimeError("environment access during import")

            __contains__ = _blocked
            __delitem__ = _blocked
            __getitem__ = _blocked
            __iter__ = _blocked
            __setitem__ = _blocked
            copy = _blocked
            get = _blocked
            items = _blocked
            keys = _blocked
            pop = _blocked
            popitem = _blocked
            setdefault = _blocked
            update = _blocked
            values = _blocked

        os.environ = GuardedEnvironment()
        os.getenv = blocked
        os.putenv = blocked
        os.system = blocked
        os.popen = blocked
        sqlite3.connect = blocked
        socket.socket = blocked
        socket.create_connection = blocked
        socket.getaddrinfo = blocked
        subprocess.Popen = blocked
        subprocess.call = blocked
        subprocess.check_call = blocked
        subprocess.check_output = blocked
        subprocess.run = blocked
        urllib.request.urlopen = blocked

        for name in module_names:
            __import__(name)

        loaded_forbidden = sorted(
            name for name in sys.modules if name.split(".", 1)[0] in forbidden_roots
        )
        if loaded_forbidden:
            raise RuntimeError("forbidden modules loaded: " + ", ".join(loaded_forbidden))
        """
    )
    safe_environment = {
        key: value
        for key, value in os.environ.items()
        if key.upper() in {"COMSPEC", "PATH", "PATHEXT", "SYSTEMROOT", "TEMP", "TMP", "WINDIR"}
    }
    safe_environment.pop("PYTHONPATH", None)

    completed = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=Path(tmp_path),
        env=safe_environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr[-2000:]
