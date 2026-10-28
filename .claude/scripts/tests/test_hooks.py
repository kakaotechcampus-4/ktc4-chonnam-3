"""Test protection boundaries and safe lint dispatch without installing tools."""
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
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
                                    input=json.dumps(event), text=True, capture_output=True,
                                    env=env, check=False)
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
        self.assertIsNone(cwd)
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
        self.assertEqual(cwd, self.root.resolve()/'frontend')
        self.assertIsNone(note)

    def test_backend_no_sync_offline(self):
        file = self.root/'backend/app/example.py'
        file.parent.mkdir(parents=True)
        file.write_text('')
        (self.root/'backend/.venv').mkdir()
        with patch.object(lint.shutil, 'which', return_value='/usr/bin/uv'):
            command, cwd, note = lint.lint_command(self.root, file)
        self.assertIn('--offline', command)
        self.assertIn('--no-sync', command)
        self.assertEqual(cwd, self.root.resolve()/'backend')
        self.assertIsNone(note)

    def prepare_ai(self):
        file = self.root/'ai/src/a space;echo BAD.py'
        file.parent.mkdir(parents=True)
        file.write_text('import os\n', encoding='utf-8')
        ruff = self.root/'ai/.venv'/('Scripts/ruff.exe' if os.name == 'nt' else 'bin/ruff')
        ruff.parent.mkdir(parents=True)
        ruff.touch()
        return file, ruff

    def run_lint_event(self, file, tool='Edit'):
        event = {'tool_name': tool, 'cwd': str(self.root),
                 'tool_input': {'file_path': str(file)}}
        output = io.StringIO()
        with patch.dict(os.environ, CLAUDE_PROJECT_DIR=str(self.root)), \
                patch.object(lint.sys, 'stdin', io.StringIO(json.dumps(event))), \
                redirect_stdout(output):
            self.assertEqual(lint.main(), 0)
        return output.getvalue()

    def test_ai_uses_own_environment_and_single_file(self):
        file, _ = self.prepare_ai()
        for path in (file, file.relative_to(self.root)):
            with self.subTest(path=path), \
                    patch.object(lint.shutil, 'which', return_value='/tools/uv'):
                command, cwd, note = lint.lint_command(self.root, path)
            self.assertEqual(command, ['/tools/uv', '--offline', 'run', '--no-sync',
                                       'ruff', 'check', '--', str(file.resolve())])
            self.assertEqual(cwd, self.root.resolve()/'ai')
            self.assertIsNone(note)

    def test_ai_missing_uv_or_environment_is_reported_without_execution(self):
        file, ruff = self.prepare_ai()
        for missing in ('uv', 'ruff', 'venv'):
            if missing == 'ruff':
                ruff.unlink()
            elif missing == 'venv':
                ruff.parent.rmdir()
                ruff.parent.parent.rmdir()
            with self.subTest(missing=missing), \
                    patch.object(lint.shutil, 'which',
                                 return_value=None if missing == 'uv' else '/tools/uv'), \
                    patch.object(lint.subprocess, 'run') as run:
                output = self.run_lint_event(file)
            self.assertIn('미실행', output)
            self.assertIn('AI', output)
            run.assert_not_called()

    def test_ai_lint_failure_is_returned_without_modifying_source(self):
        file, _ = self.prepare_ai()
        original = file.read_bytes()
        for tool in ('Edit', 'Write'):
            with self.subTest(tool=tool), \
                    patch.object(lint.shutil, 'which', return_value='/tools/uv'), \
                    patch.object(lint.subprocess, 'run', return_value=
                                 subprocess.CompletedProcess([], 1, 'F401 unused import', '')) as run:
                output = self.run_lint_event(file, tool)
            context = json.loads(output)['hookSpecificOutput']
            self.assertEqual(context['hookEventName'], 'PostToolUse')
            self.assertIn('F401', context['additionalContext'])
            self.assertIn('lint 실패', context['additionalContext'])
            self.assertEqual(run.call_args.kwargs['cwd'], self.root.resolve()/'ai')
            self.assertEqual(run.call_args.kwargs['timeout'], 35)
            self.assertNotIn('--fix', run.call_args.args[0])
            self.assertEqual(file.read_bytes(), original)

    def test_ai_lint_success_emits_nothing(self):
        file, _ = self.prepare_ai()
        with patch.object(lint.shutil, 'which', return_value='/tools/uv'), \
                patch.object(lint.subprocess, 'run', return_value=
                             subprocess.CompletedProcess([], 0, 'All checks passed!', '')) as run:
            self.assertEqual(self.run_lint_event(file), '')
        run.assert_called_once()

    def test_ai_lint_timeout_is_reported(self):
        file, _ = self.prepare_ai()
        with patch.object(lint.shutil, 'which', return_value='/tools/uv'), \
                patch.object(lint.subprocess, 'run',
                             side_effect=subprocess.TimeoutExpired(['/tools/uv'], 35)):
            output = self.run_lint_event(file)
        self.assertIn('미실행', output)
        self.assertIn('35초', output)

    def test_ai_unsupported_or_missing_paths_do_not_run(self):
        self.prepare_ai()
        doc = self.root/'ai/readme.md'
        doc.write_text('documentation')
        outside = self.root/'../outside.py'
        for file in (doc, self.root/'ai/deleted.py', outside):
            with self.subTest(file=file), patch.object(lint.subprocess, 'run') as run:
                self.run_lint_event(file)
            run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
