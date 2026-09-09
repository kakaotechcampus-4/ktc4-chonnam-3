"""Direct-edit guard for governance files; not an access-control boundary."""
import json
import os
import sys
from pathlib import Path

PROTECTED = {
    'CLAUDE.md', 'frontend/CLAUDE.md', 'backend/CLAUDE.md', 'ai/CLAUDE.md',
    '.github/workflows/assign-mentor.yml',
    '.github/workflows/notify-discord.yml',
    '.github/workflows/convention-check.yml',
}


def protected_path(root, file_path):
    root = Path(root).resolve()
    target = Path(file_path)
    if not target.is_absolute():
        target = root / target
    try:
        relative = target.resolve().relative_to(root).as_posix()
    except ValueError:
        return False
    return relative in PROTECTED


def main():
    try:
        event = json.load(sys.stdin)
        if event.get('tool_name') not in ('Edit', 'Write'):
            return 0
        file_path = event.get('tool_input', {}).get('file_path')
        root = os.environ.get('CLAUDE_PROJECT_DIR') or event.get('cwd')
        if not file_path or not root:
            raise ValueError('project root or file_path is missing')
        if protected_path(root, file_path):
            print('보호된 규칙 문서 또는 운영진 워크플로입니다. 직접 수정 대신 변경안을 보고하세요. '
                  '승인된 규칙 갱신은 담당자가 편집기로 적용합니다. Bash 등으로 우회하지 마세요.', file=sys.stderr)
            return 2
        return 0
    except (ValueError, TypeError, AttributeError, OSError) as exc:
        print(f'문서 보호 Hook 입력을 확인할 수 없습니다: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
