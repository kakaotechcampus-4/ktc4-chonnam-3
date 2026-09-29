# Task 11 구현·게시 기록

최종 확인: 2026-09-30. 목표와 완료 기준은 [Task 11](../../backend/docs/task-11-analysis-api.md), 실행 정책은 [BE ADR 0004](decisions/0004-task11-run-execution.md), 결과 계약은 [공통 ADR 0006](../shared/decisions/0006-task11-analysis-result-contract.md)를 따른다. 최초 게시 검증과 아래 #68·#70 보완 검증을 구분한다.

## 게시 상태와 범위

최초에는 `develop`의 `e53d28b3f82032a3ae3be206a95cb66f19caf9b4`에서 `feature/be-task11-draft`에 신규 변경만 분리했다. 2026-09-30에는 PR #81을 유지하면서 인증 #57이 병합된 `fbd46eb12a56f43dc306365a2e9f3846b924680a`로 rebase했다. 원본 통합 작업·정리 전 커밋은 별도 백업에 보존한다. 미병합 선행 구현과 아래 후속 보완이 필요하므로 단독 실행·병합 완료 상태는 아니다.

| 게시 영역 | 코드와 동작 |
| --- | --- |
| 분석 REST | `analysis/router.py`, `service.py`, `run_queries.py`: 생성·상태·결과·후보 조회, 소유권·TTL, 동일 fingerprint 동시 생성 409, 후보 분석 중 202 |
| 응답 계약 | `run_schemas.py`, 공통 OpenAPI: 성공/실패 저장소 수와 실패 식별자·코드. 기존 `RepositoryCard`는 #80에서 import. FE 타입·mock·API 문서는 후속 범위 |
| 실행 | `pipeline/run.py`, `run_state.py`: 실제 7단계 실행, 문서가 없을 때 skip, partial·실패·취소·timeout 상태와 실행 시간 저장 |
| 큐·복구 | `queue.py`, 신규 작업 3개: DB commit 뒤 enqueue, 결정적 ARQ ID, queued run/pending page 재등록. running 강제 종료 작업은 자동 재실행하지 않음 |
| 워커 진입점 | `workers/analysis_app.py`: #57의 자원 초기화·해제를 상속하고 신규 작업·reaper만 추가. Compose·README 명령도 이 진입점을 사용하며 선행 `arq_app.py`는 복사하지 않음 |
| SSE | `stream.py`: #71 이벤트를 FE `data/type/key` 형식으로 변환. 기반 이벤트 복구 보완은 후속 범위 |
| DB | 모델·`0003_analysis_runs`: active fingerprint 제약과 page 실행 지표. `0002_posting_versions`가 선행하며 충돌하는 active 작업이 있으면 downgrade 거절 |
| 검증 | 신규 API·워커·복구·SSE 변환·계약·migration 테스트. 선행 테스트 fixture는 import하며 본문은 복사하지 않음 |

인증·GitHub 수집·문서 추출·공고 저장·후보 점수·L1·SSE 기반 구현, 기존 테스트와 의존성 파일은 게시하지 않는다. 이미 develop에 있는 `config.py`, `errors.py`, `main.py`에는 Task 11에 필요한 최소 변경만 포함한다. 초기 설계 문서의 Redis NX 락·워커 예시는 보존하며 현행 선택과 대체 관계는 ADR 0004에서 관리한다.

## 최초 게시의 선행 구현과 후속 보완 (2026-09-28)

로컬 통합 검증에 사용한 소스는 아래와 같다. PR 상태는 확인 시점의 스냅샷이며 이후 변경 시 재검증해야 한다.

| 선행 PR | 확인한 head | 사용하는 영역 |
| --- | --- | --- |
| #57 (열림, Draft) | `cffad038ebd2d5eccd95a7983dc51bf9658b3be3` | 세션 인증, DB fixture, 초기 수집과 ARQ 자원 관리 |
| #44 (열림) | `a0c1ba75d74562d4b3b0aa0a17fc0f28984ef8a4` | 문서 추출 및 의존성 |
| #79 (열림) | `3d55a34fed6c75e2ea3292069ba862c1843bba3d` | Task 9 공고·문서, migration 0002 |
| #80 (열림) | `cbaa7738b13afa98ef6de8f133e5b75c185840b0` | Task 10 후보·추천·저장소 카드와 테스트 helper |
| #75 (열림, base `feature/repo-shallow`) | `f1ab89729d1bf7c388b751425788fd812e0dffd0` | #73을 포함한 L1 AI 계약·BE 어댑터 |
| #71 (열림) | `1a68e9089f4715830f3a80beb769862d0aa70216` | SSE 구독·snapshot·인증 기반 |

#45는 develop에 이미 병합되어 재게시하지 않는다. 위 PR들을 병합하는 것만으로 아래 후속 보완이 자동 적용되지는 않는다.

| 제외한 선행 파일 | Task 11 원본에 보존한 필수 후속 변경 |
| --- | --- |
| `analysis/posting_service.py` | 공고 fetch/extract를 `fetch_posting`·`complete_posting`으로 분리하고 캐시·버전·잠금 유지 |
| `pipeline/steps/repo_analyze.py` | 상세 수집/L1을 `collect_candidate_batch`·`analyze_collected_batch`로 분리. snapshot 연결 뒤 flush하고 추천을 같은 transaction에서 갱신 |
| `pipeline/initial_sync.py` | 새 partial UNIQUE 인덱스와 맞도록 `ON CONFLICT` predicate에 `analysis_run` 제외 조건 추가 |
| `analysis/events.py` | DB polling의 유실 단계 복원과 늦은 running 이벤트의 상태 역행 방지 |

위 네 파일과 단계 경계·SSE 복구 검증은 원본 통합 작업에 보존하고 이번 diff에서는 제외했다. 게시 워커가 호출하는 분리 함수는 현재 #79/#80 head에 아직 없다. 이를 숨기기 위한 임시 어댑터나 가짜 완료 단계는 만들지 않았다.

통합 환경에는 #57 정리 전 보존본 `0bd0ccd2df47fe08a3503912878dd7d2d0402f3d`의 GitHub 클라이언트 보완(`integrations/github/base.py`, `client.py` 및 대응 테스트 2개)도 포함한다. 현재 #57과 동일한 상태로 간주하면 안 되며 이 보완도 선행 영역에서 별도로 검토·반영해야 한다. 이번 PR에는 포함하지 않는다.

## 최초 게시 시 검증

아래는 FE 변경 제외 전 최초 게시본의 검증 이력이다. Python 3.12, PostgreSQL 15.19, Redis 7.4.11, Node 24 환경에서 실시했다. 통합 결과는 **당시 게시 코드 + 명시한 선행 구현 + 제외한 필수 보완을 새 검증 worktree에 결합한 결과**다. 원본 작업의 이전 테스트 수치를 재사용하지 않았다. GitHub·Wanted·OpenAI HTTP는 mock하고 DB·Redis·ARQ는 실제 실행했다.

| 대상 | 명령·조건 | 최초 게시 시 결과 |
| --- | --- | --- |
| 게시본 `backend` | `uv sync --locked --group dev`, develop 의존성 유지 | 통과 |
| 게시본 `backend` | `ruff check .`, `ruff format --check .` | 통과: 197개 파일 형식 확인 |
| 게시본 `backend` | `mypy app` | 실패: 인증·후보·SSE·워커 선행 정의 부재, 6개 파일 20개 오류 |
| 게시본 `backend` | `pytest -q` | 실패: `current_user` import에서 conftest 로딩 중단. 테스트 수집 전 실패이며 테스트 통과가 아님 |
| 게시본 루트 | `python .claude/scripts/check_contracts.py` | 통과: schema 2개, 부분 OpenAPI, positive/negative fixture 7개. 런타임·전체 API 호환 검사는 아님 |
| 게시본 `frontend` | `npm ci`, `npm run lint`, `npm run build` | 통과 |
| 선행 구현 결합, 후속 4개 제외 | `python -c "import app.features.analysis.pipeline.run"` | 실패: `CollectedCandidateBatch` 없음. 단순 테스트 수집은 758개 성공했지만 실제 실행 가능 근거가 되지 않음 |
| 선행 구현·필수 보완 결합 `backend` | `ruff check .`, `ruff format --check .`, `mypy app` | 통과: 형식 245개, 타입 141개 파일 |
| 선행 구현·필수 보완 결합 `backend` | 전용 PostgreSQL·Redis 환경에서 `pytest -q` | 통과: 758개, skip 없음. migration upgrade/downgrade 포함 |
| 마지막 워커 연결 수정 후 `backend` | `pytest -q tests/features/test_analysis_worker.py` | 통과: 13개 재실행 |
| 결합본 Compose 워커 경로 | YAML의 command를 import하여 작업·cron 등록 확인 | 통과: 초기 수집·분석·후보 작업과 reaper 등록. 컨테이너 build·기동은 미실행 |
| 선행 구현 결합 `ai` | 검증 환경 Python으로 `pytest -q` | 통과: 192개 |

이번 분리에서 새 워커 등록 목록을 직접 ARQ에 전달하는 테스트로 바꿨다. 분리 직후 발견한 부모 워커 함수 목록의 좁은 타입 추론과 선행 테스트 패키지 유무에 따른 import 분류 차이는 게시 코드에서 수정 후 다시 검사했다. 별도 리뷰에서 발견한 Compose의 기존 워커 경로도 새 진입점으로 수정하고 등록 결과를 확인했다.

## FE 변경 제외와 재검증 (2026-09-28)

사용자 요청에 따라 PR #81의 기존 계약 커밋에서 `frontend/docs/api-spec.md`, `frontend/src/mocks/handlers/analysis.ts`, `frontend/src/types/api.ts` 변경을 제거했다. 현재 PR의 모든 커밋과 최종 diff에는 `frontend/`와 `spec/frontend/` 변경이 없다. 문서 정정은 기존 문서 커밋에 합치고 별도의 FE 취소 커밋은 제외했다. 재작성 전 이력은 로컬 백업에 보존하며 로컬 통합 원본도 유지한다.

BE 코드·테스트·공통 OpenAPI는 최초 게시본과 동일하다. FE 타입·mock의 결과 요약 3개 필드와 FE API 문서의 내부 오류 코드·후보 조회 오류 설명 정합화는 별도 FE 후속 작업이다. 기존 FE는 새 필드를 사용하지 않으므로 타입과 mock을 함께 복원해도 빌드할 수 있지만, 새 집계·부분 실패 정보를 화면에 반영한 상태는 아니다.

| 대상 | 재검증 | 결과 |
| --- | --- | --- |
| FE 변경 제외 게시본 `frontend` | `npm run lint`, `npm run build` | 통과. 브라우저 동작 검증은 아님 |
| FE 변경 제외 게시본 루트 | `python .claude/scripts/check_contracts.py` | 통과: schema 2개, 부분 OpenAPI, fixture 7개. TypeScript 정합성·전체 API 호환 검사는 아님 |
| 선행·필수 보완 결합 `backend` | `pytest -q tests/contract/test_analysis_api_contract.py` | 13개 통과. 게시본과 동일한 BE 응답 스키마·OpenAPI 검증 |

BE·AI 전체 테스트는 이번 FE 제외에서 재실행하지 않았다. 위 최초 게시 시 통합 결과와 이번 검증을 구분하며, 선행 구현 부재에 따른 게시본 단독 실행 제한도 그대로다.

커밋 재작성 후에는 정리 전 head와 Git tree를 비교해 이 문서의 이력 설명 외 모든 파일 내용이 동일함을 확인했다. 11개 커밋 각각의 추가·삭제 합계는 300줄 이하이며, 위 테스트 결과는 FE 제외 시 실행한 기록이다. 이력 정리에서 전체 테스트를 다시 실행한 결과로 표현하지 않는다.

## 재현과 병합 조건

1. 선행 변경 및 위 별도 보완을 검토·반영하고 잠금 파일을 합친 환경에서 설치한다. 신규 PR만 checkout해서 실행할 수는 없다.
2. 테스트 전용 로컬 PostgreSQL에 `TEST_DATABASE_URL`과 `TEST_POSTGRES_URL`을 설정한다. Task 10 fixture는 `task10_test` 접두사를 요구한다. `TEST_REDIS_URL`은 격리된 Redis DB 13~15를 사용한다. migration 검증용 `TASK11_MIGRATION_URL`은 별도 로컬 `task11_migration_test` DB여야 한다.
3. BE의 Ruff·mypy·전체 pytest, AI pytest, FE lint·build와 계약 검사를 재실행한다. 원본·게시본·최종 병합본을 구분해 결과를 기록한다.
4. 최종 결합 환경의 워커 명령은 `uv run arq app.workers.analysis_app.WorkerSettings`다. 기존 `arq_app.WorkerSettings`만 실행하면 Task 11 작업·reaper가 등록되지 않는다. API 명령은 기존 uvicorn 진입점을 유지한다.
5. #69 seed 작업과 활성 프롬프트·모델 설정을 확인한 뒤 실제 외부 계정·LLM·브라우저 흐름을 별도로 검증한다. 현재 mock 통합 시험은 운영 프롬프트 품질이나 배포 성공을 입증하지 않는다.
6. 실제 기능 연결 및 본문의 실패·후속 항목을 해소한 다음 Draft를 해제한다. FE 문서·타입·mock 변경은 이 PR에서 제외했으며, 해당 계약 반영과 Task 13 이후 화면 연결은 별도 FE 후속 작업이다.

협업 검토: #57/#79와 공통 config·main, #80과 카드 계약, #71과 SSE 계약을 맞춰야 한다. #64의 오류·Redis 문서 작업과도 오류 코드 영역이 겹치므로 병합 때 확인한다. 면접 코드, 다른 PR의 이력, 운영진 보호 파일은 변경하지 않는다.

## #68·#70 보완과 재검증 (2026-09-30)

관련 이슈는 [#68](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/68)과 [#70](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/70)이다. 이슈 자동 종료 문구를 사용하지 않는다. 아래 통합 검증 통과와 게시본의 선행 미반영 상태는 별개다.

- `pipeline/run_state.py`: 단계 변경·종료 transaction 안에서 전체 단계 상태를 복사하고, commit 성공 후 Redis `HSET(mapping)` → `EXPIRE` → `PUBLISH`를 실행한다. 문서 미첨부의 skipped와 중단된 단계의 failed/skipped도 기록한다. commit 실패 시 알림을 보내지 않으며 Redis execute 실패는 DB 결과를 되돌리지 않는다. 이벤트 payload와 외부 API 계약은 유지한다.
- `test_analysis_rate_limit.py`: 429/403 × 부분 성공/전체 실패 4개. 실제 수집 호출 중단, 미호출 후보 snapshot 보존, `gh:rl:501` TTL, partial/failed·결과 집계, Redis 발행 및 재접속 SSE를 확인한다. 제한된 저장소는 접근 불가로 간주하지 않으므로 실패 카드를 보존하고 추천에서 제외한다.
- `test_analysis_notifications.py`: 8개. 문서 skip·실패·성공·partial의 전체 mirror, Redis 실행 직전 별도 PostgreSQL session에서 commit 가시성, HSET/EXPIRE/PUBLISH 순서, commit 실패와 Redis execute 장애를 확인한다. 수정 전 4 실패/3 통과로 누락을 재현했고, 수정 후 추가 시나리오까지 8개 통과했다.
- `test_analysis_live_stream.py`: 정상/실패 × 알림 정상/유실 4개. 실제 인증·SSE 라우터·ASGI 프레임·ARQ를 함께 실행하고 종료 프레임 전송 시점에 상태/결과 API와 별도 DB session을 조회한다. 정상 경우 running 단계 수신, 유실 경우 최종 7단계 복원도 확인한다.
- #57은 현재 develop에 병합됐다. 새 migration과 초기 수집의 충돌 조건을 맞추는 `initial_sync.py` 한 줄과 주석은 이제 기존 파일에 대한 신규 변경으로 포함한다. main은 develop의 인증 수명 관리를 보존하고 분석 라우터 등록 2줄만 추가하며 README·Compose 워커 명령을 유지했다. FE·추가 migration·의존성 변경은 없다.

검증 환경은 기존 `e53d28b` 로컬 통합본에 위 표의 고정 선행 소스·보존 보완, 최신 develop의 Origin 검증과 해당 테스트, 이번 변경을 결합했다. #75 최신 `0778a60`은 기존 고정 소스 대비 문서만 변경됐다. 최신 develop 전체를 결합해 모든 미병합 PR 간 호환성이 검증됐다는 의미는 아니다. GitHub/Wanted/LLM HTTP는 mock하고 PostgreSQL 15·Redis 7·ARQ·SSE 경로는 실제 실행했다.

| 대상 | 실행 | 이번 결과 |
| --- | --- | --- |
| 선행·보완 결합 BE | `ruff check .`, `ruff format --check .`, `mypy app` | 통과: 형식 250개·타입 141개 파일 |
| 선행·보완 결합 BE | `pytest -q` | **802 passed, skip 없음**, migration 왕복과 최신 Origin 회귀 포함 |
| 위 전체 테스트 내 이번 회귀 | 게시할 신규 16개 + SSE 선행 후속 2개 | **18개 통과**. 후속 2개는 게시 diff에 포함하지 않음 |
| 게시본 BE | `uv sync --locked --group dev`, Ruff check·format | 통과: develop 의존성 유지, 형식 216개 파일 |
| 게시본 BE | `mypy app` | **실패: 5개 파일 15개 오류**, 후보/공고/SSE 선행 정의 부재 |
| 게시본 BE | `pytest -q` | **실패: 수집 오류 8개**, 후보 카드·SSE·선행 테스트 helper 부재. 테스트 통과가 아님 |
| 게시본 루트 | `python .claude/scripts/check_contracts.py` | 통과: schema 2개·부분 OpenAPI·positive/negative fixture 7개. 전체 런타임 호환 검사는 아님 |
| AI 전체·FE·외부 계정/LLM·브라우저/Docker | 이번 BE 상태 보완에서 새 실행 | **미실행**. BE 연결 테스트의 mock 검증으로 대체 완료 처리하지 않음 |

알림 유실 시험에서 실제 5초 polling으로 워커 종료 후 약 4.6~4.8초에 성공·실패 상태를 복구했다. 같은 시험의 mock 워커는 약 0.2~0.7초에 종료됐으므로 5초를 유지하되 실서비스의 단계별 LLM 지연·동시 SSE 수·DB 부하에 대한 최적값으로 확정하지 않는다. 운영 조건에서 복구 지연과 조회량을 측정해 조정한다.

게시본에 없는 `posting_service.py`, `repo_analyze.py`, `events.py` 보완은 계속 선행 영역 후속으로 남긴다. SSE의 유실 단계 복원·늦은 running 역행 방지와 전용 회귀 2개는 별도 로컬 `pr71-sse-followup.patch`에 보존했다. 선행 소스·GitHub 보안 보완까지 최종 대상 브랜치에 반영한 뒤 재검증해야 #68·#70의 전체 연결과 PR 병합 조건을 완료로 판단할 수 있다.

이번 원본·로그·구성 기록은 `.claude/scratch/task11-issues-68-70-20260930/`, 통합 환경은 `.claude/scratch/task11-publish-verify/`에 보존한다. 재작성 전 PR head `3a61798`은 `backup/task11-before-issues-6870-20260930`으로 백업했다. 커밋별 300줄 이하와 원격 HEAD를 확인한 뒤 명시적 lease로 같은 PR #81을 갱신한다.
