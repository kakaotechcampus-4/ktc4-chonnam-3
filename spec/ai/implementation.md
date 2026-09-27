# AI 구현·검증 기록

AI 작업의 구현·수정 내역, 코드 위치, 실행 결과와 남은 작업을 관리하는 원본이다.
기능 요구사항·초기 설계·검증 방법은 각 명세에, 지속할 결정의 맥락·이유·영향은
[decisions](decisions/README.md)에 보존한다. 문서 역할은
[ADR 0020](decisions/0020-implementation-record-policy.md)을 따른다.

## PR #56의 현재 범위

관련 PR: [AI task-01~03 기반 및 Director 기본 질문 생성 구현](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/56)

| 영역 | 구현 위치와 범위 | 후속 범위 |
| --- | --- | --- |
| task-01 | `ai/pyproject.toml`, `ai/uv.lock`, `backend/pyproject.toml`: 독립 AI 패키지와 BE editable 설치 | 기능별 서비스 연결 |
| task-02 | `ai/src/devon_ai/contracts.py`: 내부 값 계약, 순수 검증, 저장 값 변환 | DB 존재·소유권·transaction 검증은 BE |
| task-03 | `backend/app/core/config.py`, `backend/app/integrations/llm/client.py`: 단일 환경 진입점, 지연 LLM 설정 검증, HTTP 호출·실패 분류·공유 호출 상한·metadata | 실제 계정 접근, 운영 상한·품질·비용 검증, metadata 영구 저장 |
| prompt | `backend/app/llm_tasks/prompt_loader.py`, `backend/scripts/seed_prompt_versions.py`: 활성 prompt 조회, 7종 seed의 멱등성·불변성·동시성 | 검수된 운영 prompt 등록 |
| Director | `ai/src/devon_ai/agents/director/agent.py`: 준비된 질문 계약을 받아 질문 생성·독립 검토·검증 | 목적 자동 선정, 도구 실행, 실제 검토기, DB·worker·API·WS 연결 |

레포 분석과 JD 분석의 본체를 이 PR에서 완성한 것은 아니다. 위 기반을 소비하는 각 기능 구현과
실제 서비스 연결은 해당 담당 작업에서 이어간다. Director도 준비된 목적의 질문 생성 경로까지다.

## 2026-09-27 — 최신 develop 통합

### 기준과 변경

- 작업 브랜치: `feature/ai-director-define`.
- 통합 전 feature: `b5f8a8ece3a34d807098a803c3557ad186751caf`.
- 통합한 develop: `ec38943722b5fb87132a14b29368a799813f28e9`.
- 기존 공통 조상 `b444c64` 이후의 DB 모델·초기 migration, 공통 오류 처리, API schema·검사,
  CORS 제거 및 develop의 면접 화면 변경을 병합했다.
- 유일한 Git 충돌인 `backend/uv.lock`은 양쪽 `pyproject.toml` 선언을 유지하고 `uv lock`으로
  재생성했다. 기존 패키지 버전은 모두 보존했고 `types-pyyaml`만 새로 추가했다.
  `pyyaml`의 명시적 개발 의존성과 `devon-ai` editable 설치도 유지한다.
- `backend/tests/llm_tasks/test_prompt_postgres.py`는 과거 migration에서 복사한 DDL 대신
  현재 `PromptVersion.__table__.create`로 테이블·제약·인덱스를 생성한다. 테스트별 임시
  schema와 정리 방식은 유지한다. 이 테스트와 전체 migration 검증은 별개다.
- 새 DB session/migration의 `get_settings().database_url` 소비, 일반 앱 기동과 LLM 지연
  설정 검증, CORS 설정·소비자의 동시 제거를 확인했다. AI의 호출 정책·Director 출력 계약은 유지한다.

### 실행 결과

환경: Windows, Python 3.12, uv 0.12.13, 로컬 PostgreSQL 15.19.
아래 결과는 통합한 코드에서 실제 실행한 결과다. 프롬프트 테스트 변경 후 BE 검사를 다시 수행했다.

| 작업 디렉터리 | 명령 / 시나리오 | 결과 |
| --- | --- | --- |
| `ai`, `backend` | `uv sync --locked --python 3.12` | 양쪽 성공 |
| `ai` | `ruff check .`, `ruff format --check .`, `mypy src` | 통과; format 37개, mypy 11개 파일 |
| `ai` | `python -m pytest -q` | 138 passed |
| `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과; format 173개, mypy 114개 파일 |
| `backend` | 명시적 `TEST_POSTGRES_URL`로 `python -m pytest -q` | 285 passed; 실제 PostgreSQL prompt 검사 13개 포함 |
| 저장소 루트 | 검사 의존성을 별도 uv 환경에 주입해 `python .claude/scripts/check_contracts.py` | schema 2개, 부분 OpenAPI, 정상·오류 fixture 7개 통과 |
| `backend` | 격리 DB에 `python -m alembic upgrade head`, `current`, `check` | revision `0001_initial`, 26개 업무 테이블, ORM 대비 추가 변경 없음 |
| `backend` | 실제 migration 테이블에서 테스트 prompt 7종 seed → load → 같은 seed 재실행 | 7종 일치; UUID·시간·본문·활성 상태 보존 |
| `backend` | 격리 DB에서 `downgrade base` → `upgrade head` → `check` → seed/load 재검사 | 업무 테이블 제거·재생성, ORM 일치, 7종 재검사 통과 |

전체 migration 검증은 전용 로컬 클러스터의 새 임시 DB에서만 실행했다. `DATABASE_URL`은 검증
자식 프로세스에만 지정했고 `.env`를 수정하지 않았다. 테스트 prompt는 합성 본문과 `test-model`을
사용했다. 검증 후 임시 DB와 테스트 schema가 남지 않은 것을 확인하고 전용 PostgreSQL을 종료했다.
실제 서비스 DB 적용이나 운영 prompt 등록 결과는 아니다.

### 검증 한계와 후속 작업

- 외부 모델 호출은 mock으로 검증했다. 실제 OpenAI 호출·자연어 품질·비용은 미검증이다.
- 이번 실행에서 FE lint/build는 미실행이다. 현재 실행 셸에서 Node/npm을 찾을 수 없었다.
  develop의 FE 변경을 그대로 수용했으며 별도 FE 구현은 추가하지 않았다.
- 공통 계약 스크립트는 부분 형식 검사다. 전체 API·TypeScript 대응·실서비스 호환성 검증을 대신하지 않는다.
- 기존 설계와 `testing.md`의 과거 기록을 이번 통합에서 일괄 재작성하지 않는다.
  이후 구현 현황과 실행 결과는 이 파일을 갱신한다.
