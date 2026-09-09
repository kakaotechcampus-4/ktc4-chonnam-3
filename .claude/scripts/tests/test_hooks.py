"""Test protection boundaries and safe lint dispatch without installing tools."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = load('guard_docs')
lint = load('lint_changed')


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_rules_and_traversal_protected(self):
        self.assertTrue(guard.protected_path(self.root, 'frontend/../CLAUDE.md'))
        self.assertTrue(guard.protected_path(self.root, 'backend/CLAUDE.md'))
        self.assertTrue(guard.protected_path(self.root, '.github/workflows/assign-mentor.yml'))

    def test_working_docs_and_contracts_allowed(self):
        for path in ['spec/frontend/verification.md', 'spec/frontend/designs/new.md',
                     'spec/shared/contracts/openapi.yaml', '.github/CODEOWNERS']:
            self.assertFalse(guard.protected_path(self.root, path))

    def test_hook_exit_codes(self):
        for path, expected in [('CLAUDE.md', 2), ('spec/frontend/verification.md', 0)]:
            event = {'tool_name': 'Write', 'cwd': str(self.root), 'tool_input': {'file_path': path}}
            env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root))
            result = subprocess.run([sys.executable, str(SCRIPTS/'guard_docs.py')],
                                    input=json.dumps(event), text=True, capture_output=True, env=env)
            self.assertEqual(result.returncode, expected)

    def test_symlink_resolves_to_protected_file(self):
        (self.root/'CLAUDE.md').write_text('rules')
        try:
            (self.root/'alias.md').symlink_to(self.root/'CLAUDE.md')
        except OSError:
            self.skipTest('symlinks unavailable')
        self.assertTrue(guard.protected_path(self.root, 'alias.md'))

    def test_no_install_when_linter_missing(self):
        file = self.root/'frontend/src/app.ts'
        file.parent.mkdir(parents=True)
        file.write_text('')
        with patch.object(lint.shutil, 'which', return_value=None):
            command, cwd, note = lint.lint_command(self.root, file)
        self.assertIsNone(command)
        self.assertIn('미실행', note)

    def test_fe_path_is_single_argument(self):
        file = self.root/'frontend/src/a space;echo BAD.ts'
        file.parent.mkdir(parents=True)
        file.write_text('')
        eslint = self.root/'frontend/node_modules/eslint/bin/eslint.js'
        eslint.parent.mkdir(parents=True)
        eslint.write_text('')
        with patch.object(lint.shutil, 'which', return_value='/usr/bin/node'):
            command, cwd, note = lint.lint_command(self.root, file)
        self.assertEqual(command[-1], str(file))
        self.assertEqual(command[-2], '--')
        self.assertNotIn('--fix', command)

    def test_backend_no_sync_offline(self):
        file = self.root/'backend/app/example.py'
        file.parent.mkdir(parents=True)
        file.write_text('')
        (self.root/'backend/.venv').mkdir()
        with patch.object(lint.shutil, 'which', return_value='/usr/bin/uv'):
            command, cwd, note = lint.lint_command(self.root, file)
        self.assertIn('--offline', command)
        self.assertIn('--no-sync', command)


if __name__ == '__main__':
    unittest.main()
