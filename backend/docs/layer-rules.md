# 레이어 규칙 · 네이밍 · 직렬화

## 폴더 경계

```text
router -> service -> {queries | agents | llm_tasks | integrations | realtime}
workers -> features/*/pipeline
backend AI 연결 -> devon_ai
```

| 계층 | 책임 |
| --- | --- |
| `features/*/router.py` | 요청 검증, dependency, response model |
| `features/*/service.py` | 비즈니스 로직, 트랜잭션, commit |
| `features/*/queries.py` | DB 쿼리 |
| `features/*/pipeline/` | ARQ에서 호출할 긴 흐름 |
| `agents/director/` | AI 패키지 Director의 BE 연결·실제 도구 adapter 경계 |
| `llm_tasks/` | AI task 연결, prompt 로드, BE 소유 규칙 변환·집계 |
| `integrations/` | 외부 API/파일/LLM client |
| `realtime/` | SSE, WS, Redis bus |
| `workers/` | ARQ adapter |

`repository.py` 파일명은 쓰지 않는다. GitHub repository 도메인과 혼동되므로 DB 접근 모듈은 `queries.py`로 둔다.

위 표는 `backend/app/` 기준이다. [승인된 패키지 설계](../../spec/ai/designs/2026-09-12-ai-package-structure.md)에 따라 Director와 네 LLM task의 AI 원본은 `ai/src/devon_ai/`에 둔다. 기존 BE 경로는 삭제하지 않고 향후 연결 계층으로 유지하며, 양쪽에 같은 로직을 구현하지 않는다. 현재 두 영역 모두 기능 함수가 없는 골격이다. AI 패키지는 BE·ORM·Redis·ARQ·구체 provider를 역으로 import하지 않는다.

## 금지

- router에서 `db.execute()` 직접 호출.
- integrations에서 DB model import.
- agents/director에 `AsyncSession` 주입.
- 프롬프트, 루브릭, persona, domain frame을 코드에 하드코딩.
- 모델명을 코드 상수로 고정. Sprint 1 기본값은 seed/config에서 `5.5 Luna`로 읽는다.
- `os.environ`을 `core/config.py` 밖에서 직접 읽기.
- `HTTPException` 직접 raise.
- 깨진 LLM JSON을 downstream에 전달.
- Redis를 영구 원본으로 사용.

## 네이밍

| 대상 | 규칙 |
| --- | --- |
| DB table/column | snake_case |
| SQLAlchemy model | PascalCase 단수 |
| Python 함수/변수 | snake_case |
| Pydantic 필드 | 내부 snake_case, API alias camelCase |
| API path | kebab-case 복수 |
| enum/check 값 | snake_case 문자열 |

## 직렬화

`app/shared/schema.py`에 `CamelModel`을 두고 API schema는 이를 상속한다.

요구사항:

- response에 snake_case key가 새지 않는다.
- request body는 camelCase를 기준으로 받는다.
- DB column 이름을 그대로 API에 노출하지 않는다.

## Evidence 규칙

`turn_evidences`는 usage로 의미를 나눈다.

- `question_basis`: 질문 생성 근거.
- `evaluation_basis`: 답변 평가, 리포트, conflict 판정 근거.

모든 persona 질문에 `question_basis`를 강제하지 않는다. Sprint 1 첫 `hr_manager` 질문은 evidence 없이 허용한다. 답변 분석에서 검증 가능한 주장이 나오면 Evidence Retriever가 후속 evidence를 찾아 `evaluation_basis`로 연결한다.

## LLM 규칙

- 작업별 prompt version을 사용한다.
- Sprint 1 model은 `5.5 Luna`.
- timeout/provider 오류/JSON parsing 실패는 자동 1회 재시도.
- 2회 실패 시 error_code를 남기고 중단한다.
- raw output, model, prompt version, token, latency를 가능한 범위에서 저장한다.
