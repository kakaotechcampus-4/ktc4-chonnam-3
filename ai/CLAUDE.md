# AI 코딩 AI 작업 지침

루트 CLAUDE.md를 따른다. 모든 spec 경로는 저장소 루트 기준이다.
서비스 명세는 spec/ai/architecture.md, spec/ai/features/, spec/ai/verification.md를 읽는다.
공통 인터페이스는 spec/shared/contracts/README.md와 migration.md를 함께 확인한다.
명세 내용을 이 파일에 복제하지 않고 관련 spec 문서를 갱신한다.

## 실행 환경
AI 소스와 단독 검증의 작업 디렉터리는 `ai`이며 소스 원본은 `ai/src/devon_ai/`다. 기존 API·ARQ worker가 이 패키지를 import한다. 서비스 실행·통합 연결은 `backend`가 맡으며 별도 AI 서버는 없다.

현재 구조·설치 상태와 명령은 `ai/README.md`, `ai/docs/testing.md`, `spec/ai/verification.md`를 따른다. 패키지 import 성공을 Director·분석·평가 기능 구현 완료로 취급하지 않는다.

## 실행할 검증
```text
ai: uv run --locked ruff check .
ai: uv run --locked ruff format --check .
ai: uv run --locked mypy
ai: uv run --locked pytest
backend: uv run --locked pytest tests/agents/test_ai_package_imports.py
모델 기반 평가는 데이터셋·모델 버전·비용·지표를 지정한 뒤 수행.
```
`backend/app/agents/`와 `backend/app/llm_tasks/`의 연결 계층을 수정할 때는 `backend/CLAUDE.md`도 읽는다. BE import 검사는 패키지 연결 범위만 검증한다. 실제 모델·저장·작업 실행은 해당 구현과 테스트가 준비된 범위에서 확인한다. 의존성 선언만으로 모델·provider·RAG 저장소 선정을 확정하지 않는다.
미구현·도구 미설치·테스트 없음은 미실행으로 보고한다.

## 산출물 위치
- 기능·설계·결정: spec/ai/ 하위의 해당 문서.
- AI 실행 계획: .claude/scratch/plans/. 인계 메모: .claude/scratch/.
- 코딩 AI 작업 규칙: 이 파일 또는 .claude/skills/.
