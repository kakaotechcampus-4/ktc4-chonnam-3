"""Read-only lint after Claude Edit/Write; no installation or auto-fix."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def lint_command(root, file_path):
    root = Path(root).resolve()
    file = Path(file_path)
    if not file.is_absolute():
        file = root / file
    file = file.resolve()
    try:
        relative = file.relative_to(root)
    except ValueError:
        return None, None, 'SKIP: 프로젝트 밖 파일'
    if not file.is_file():
        return None, None, 'SKIP: 삭제되었거나 없는 파일'
    path = relative.as_posix()
    if path.startswith('frontend/src/') and file.suffix in ('.js', '.jsx', '.ts', '.tsx'):
        eslint = root / 'frontend/node_modules/eslint/bin/eslint.js'
        node = shutil.which('node')
        if not eslint.is_file() or not node:
            return None, None, '미실행: FE node 또는 로컬 ESLint 없음. frontend에서 npm ci 필요.'
        return [node, str(eslint), '--', str(file)], root / 'frontend', None
    if path.startswith('backend/') and file.suffix == '.py':
        uv = shutil.which('uv')
        if not uv or not (root / 'backend/.venv').is_dir():
            return None, None, '미실행: BE uv 또는 .venv 없음. backend 의존성 준비 필요.'
        return [uv, '--offline', 'run', '--no-sync', 'ruff', 'check', '--', str(file)], root / 'backend', None
    if path.startswith('ai/') and file.suffix == '.py':
        return None, None, '미실행: ai 전용 lint 설정 미확정. 현재 AI 런타임은 backend 아래.'
    return None, None, None


def emit(message):
    print(json.dumps({'hookSpecificOutput': {
        'hookEventName': 'PostToolUse', 'additionalContext': message
    }}, ensure_ascii=False))


def main():
    try:
        event = json.load(sys.stdin)
        if event.get('tool_name') not in ('Edit', 'Write'):
            return 0
        file_path = event.get('tool_input', {}).get('file_path')
        root = os.environ.get('CLAUDE_PROJECT_DIR') or event.get('cwd')
        if not file_path or not root:
            emit('미실행: lint Hook의 프로젝트 경로 또는 file_path 없음')
            return 0
        command, cwd, note = lint_command(root, file_path)
        if note:
            emit(note)
        if command:
            result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=35)
            if result.returncode:
                emit('변경 파일 lint 실패. 완료 처리 전에 확인하세요.\n' +
                     (result.stdout + result.stderr)[-5000:])
    except subprocess.TimeoutExpired:
        emit('미실행: 변경 파일 lint가 35초를 초과했습니다. 팀 검증 명령을 직접 실행하세요.')
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        emit(f'미실행: lint Hook 오류 ({type(exc).__name__}). 팀 검증 명령을 직접 실행하세요.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
