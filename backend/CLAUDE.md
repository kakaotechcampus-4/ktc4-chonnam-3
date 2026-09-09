# BE 코딩 AI 작업 지침

루트 CLAUDE.md를 따른다. 모든 spec 경로는 저장소 루트 기준이다.
서비스 명세는 spec/backend/architecture.md, spec/backend/features/, spec/backend/verification.md를 읽는다.
공통 인터페이스는 spec/shared/contracts/README.md와 migration.md를 함께 확인한다.
명세 내용을 이 파일에 복제하지 않고 관련 spec 문서를 갱신한다.

## 실행 환경
작업 디렉터리: backend
```text
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## 실행할 검증
```text
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```
현재 main.py는 docstring 스켈레톤이다. 실행 명령은 구현 후 확인할 목표이며 DB·Redis·환경값 준비는 backend/README.md를 참고한다.
미구현·도구 미설치·테스트 없음은 미실행으로 보고한다.

## 산출물 위치
- 기능·설계·결정: spec/backend/ 하위의 해당 문서.
- AI 실행 계획: .claude/scratch/plans/. 인계 메모: .claude/scratch/.
- 코딩 AI 작업 규칙: 이 파일 또는 .claude/skills/.
