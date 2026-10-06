# Task 11 구현·게시 기록

최종 확인: 2026-10-06. 목표와 완료 기준은 [Task 11](../../backend/docs/task-11-analysis-api.md), 실행 정책은 [BE ADR 0004](decisions/0004-task11-run-execution.md), 결과 계약은 [공통 ADR 0006](../shared/decisions/0006-task11-analysis-result-contract.md)를 따른다. 과거 게시·검증 기록은 보존하며 현행 범위는 마지막 **세 PR 분리** 절을 따른다. 이전 분리 절의 PR별 범위·병합 순서·검증 수치는 당시 이력이다.

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

## 이전 파일 유형별 분리 (2026-10-06, 아래 기능별 분리로 대체)

사용자 요청에 따라 PR #81에서 문서 변경을 분리한다. 두 게시본은 모두 최신 develop
`ef1a48d1531b43f382b69dee163419afb5709c6b`를 기준으로 하며 선행 미병합 코드를 포함하지 않는다.
원본 `08115fdf6339a9f9bc71be965461ff6632d680d2`와 로컬 통합 환경은 보존한다.

| 게시본 | 범위 |
| --- | --- |
| [구현 PR #81](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/81) | `feature/be-task11-draft` → develop. 코드·설정·migration·테스트 28개 파일, 14개 커밋. 각 파일의 Git blob은 원본과 동일하며 문서 추가·취소 이력은 제외한다. |
| 명세·설계 PR | `docs/task11-contract-design` → develop. OpenAPI, BE ADR 0004, 공통 ADR 0006, 두 결정 색인, 오류 문서, README, 이 구현 기록의 8개 파일. 계약·결정 내용은 원본을 옮기고 분리 상태·실행 조건을 보충한다. |

문서만 반영한 develop에는 Task 11 실행 코드가 생기지 않는다. README는 현재
`arq_app.WorkerSettings` 명령을 유지하고 #81 및 선행 코드 반영 후에만
`analysis_app.WorkerSettings`를 사용하도록 구분한다. DB migration은 실행 코드이므로 #81에 남긴다.

`test_analysis_api_contract.py`는 #81에 보존하며 OpenAPI 비교를 삭제·완화·skip하지 않는다.
명세 PR 선행 병합 → #81에 해당 develop 반영 → 선행 코드와 함께 재검증 순서가 필요하다.
문서 분리는 결과 필드·오류 응답 계약을 취소하거나 이전 API 동작으로 되돌리는 작업이 아니다.

### 이번 분리에서 새로 검증한 범위

Windows / Python 3.12 환경이며 게시 디렉터리의 BE·AI import 경로를 지정했다.
이번에는 DB·Redis 서버를 기동하지 않았고 실제 외부 연동을 실행하지 않았다.
이전 758·802개 통합 통과는 위 날짜의 이력이며 이번 게시본의 통과 수치로 사용하지 않는다.

| 대상 | 실행·조건 | 이번 결과 |
| --- | --- | --- |
| #81 게시본 | 원본과 비문서 파일 blob 비교, 커밋 경로·줄 수 확인 | 통과: 28개 파일 동일, 문서 경로 없음, 14개 커밋 최대 279줄 |
| #81 게시본 BE | `ruff check .`, `ruff format --check .` | 통과: 227개 파일 형식 확인 |
| #81 게시본 BE | `mypy app` | 실패: 5개 파일 15개 오류. 공고·후보·SSE 선행 정의 부재, 검사 대상 128개 파일 |
| #81 게시본 BE | `pytest -q -p no:cacheprovider -ra` | 실패: 선행 카드·SSE·테스트 helper 부재로 수집 오류 8개. 실행 통과가 아님 |
| 명세 게시본 | `python .claude/scripts/check_contracts.py` | 통과: schema 2개·부분 OpenAPI·정상/오류 fixture 7개. 전체 호환성 검사는 아님 |
| 별도 계약 검증본 | #81 + #80 `8206cec`의 카드 스키마 한 파일, 기존 develop OpenAPI | 4 failed, 9 passed. 분리된 명세가 없을 때 불일치 재현 |
| 같은 계약 검증본 | 위 상태에 명세 게시본 적용 후 `pytest -q tests/contract/test_analysis_api_contract.py` | 13 passed. BE 응답 스키마·OpenAPI 일치만 검증하며 전체 런타임 통합은 아님 |
| DB·Redis·ARQ 통합, AI 전체, FE, 실제 외부 계정·LLM·브라우저·Docker | 이번 문서 분리 후 전체 재실행 | 미실행. 코드 동일성·부분 계약 검증으로 전체 실행 완료를 주장하지 않음 |

계약 검증용 카드 스키마는 별도 로컬 환경에만 결합했다. #81이나 명세 PR에 복사하지 않는다.

### 현재 의존성과 병합 조건

- #44 문서 추출, #57 인증, #75 L1 어댑터(#73 포함)는 기준 develop에 병합됐다.
- #79(`9cd8189`) 공고·문서와 `0002_posting_versions`, #80(`8206cec`) 후보·카드는 미병합이다.
  공고 fetch/extract·후보 상세 수집/L1 단계 분리는 현재 각 PR에 반영됐다. 위 9월 기록의
  "해당 함수가 아직 없다"는 설명은 당시 상태이며, 최신 선행 코드와의 전체 통합은 재검증해야 한다.
- #71(`1a68e90`) SSE는 미병합이며 유실 단계 polling 복원·늦은 이벤트 역행 방지 후속 보완이 남는다.
- `initial_sync.py` 인덱스 충돌 조건 보완은 #81 구현에 포함돼 있다. ADR 0004의 초기 후속 목록과
  현재 포함 상태를 구분한다. `0003_analysis_runs`는 #79의 `0002_posting_versions`에 의존한다.
- #69 seed·활성 prompt, 실제 외부 연동 및 FE 결과 요약·타입·mock 반영은 후속이다.
  선행 코드·명세·SSE 보완을 결합한 최종 대상에서 통합 검사 후 #81의 Draft 해제와 병합을 판단한다.
  이번 문서 분리만으로 #68·#70을 자동 종료하지 않는다.

백업 브랜치는 `backup/task11-before-docs-split-20261006`, Git bundle과 분리 구성 기록은
`.claude/scratch/task11-docs-split-20261006/`에 보존한다. #81은 확인한 원격 HEAD에 대한
명시적 `--force-with-lease`로 갱신하며 이전 통합 원본과 다른 PR 브랜치는 변경하지 않는다.

## 기능별 재분리 (2026-10-06, 아래 추가 축소로 대체)

사용자는 문서/코드 구분 대신 **기존 명세대로 구현한 기능**과 **명세·설계 변경을 동반한 구현**으로
PR을 나누도록 요청했다. 두 PR은 develop `ef1a48d` 기준을 유지하며 이전 #81 `b9cb84d`,
#100 `fe6d0c7`와 통합 원본을 백업했다. 두 게시본의 파일 소유 범위는 겹치지 않는다.

| PR | 현재 포함 | 제외·의존 |
| --- | --- | --- |
| [#81](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/81) | 기존 상태 응답·7단계 초기값·진행률·partial 매핑, commit 후 Redis 전체 mirror·TTL·알림, SSE 응답 변환, 설정 양수 검증과 독립 회귀. 보조 문서 포함 13파일 | 공개 API·새 worker·migration·결과/후보 정책은 #100. SSE 변환에는 #71 필요 |
| [#100](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/100) | 분석 API·결과 집계·후보 조회, DB 중복/claim·ARQ 복구·실행, 종료 원자성·지표·migration 및 관련 테스트. OpenAPI와 analysis-run 현행 실행 설계를 함께 포함한 28파일 | #81 모듈을 import하며 복사하지 않음. #79·#80·#71 및 SSE 후속 보완도 필요 |

`decisions`·색인·README·이 구현 기록은 실명세 파일로 분류하지 않고 Task 11 공통 보조 기록으로
#81에 보존한다. ADR 본문은 초기 선택의 이력이며 #81에 해당 API·실행 기능이 모두 있다는 뜻이 아니다.
새 API·worker 명령은 #81과 #100, 선행 코드를 함께 반영한 환경에서만 사용할 수 있다.

상태 클래스는 `status_schemas.py`, 상태 계산은 `run_status.py`로 옮겼다. `run_schemas.py`는
상태 클래스를 재사용한다. `run_state.py`에는 기존 DB 컬럼만 쓰는 단계/알림 기능을 두고,
새 page 지표와 종료 transaction은 #100의 `run_completion.py`가 담당한다. run과 page 1의 동일
transaction 완료, commit 이후 notify 순서는 보존했다. 원본 Python 정의 112개는 이동 전후 AST가 같다.
기존 API·worker·계약·알림·SSE 통합 테스트는 삭제하지 않았으며 종료 함수 import 경로만 조정했다.

새 `test_analysis_progress.py`는 API·새 migration 없이 상태 계약과 commit/rollback/Redis 실패,
실제 SSE adapter를 검증한다. #71의 대체 이벤트 구현이나 테스트 skip으로 선행 의존성을 감추지 않는다.
결과 요약 3개 필드도 제거하지 않는다. 결과·후보 조회와 그 계약·검증은 #100의 완전한 기능 단위다.

### 이번 재분리 검증

Windows / Python 3.12.14 / PostgreSQL 15.19 / Redis 7.4.11. 새 전용 서버·DB·Redis DB 13~15를 사용했다.
GitHub·Wanted·LLM HTTP는 fixture이며 이전 통합 통과 수치를 재사용하지 않는다.

| 대상 | 새 실행 결과 |
| --- | --- |
| #81 게시본 Ruff·format | 통과, 212개 파일 |
| #81 게시본 mypy | 실패: #71의 SSE 정의 부재, 1개 파일 4개 오류(122개 검사) |
| #81 게시본 전체 pytest | 666 passed, 1 failed, skip 0. 실패는 #71 없는 SSE adapter import |
| #81 + #71의 원본 events.py·bus.py만 결합한 별도 환경 | 독립 회귀 14 passed, mypy 122개 파일 통과. #100·공고·후보 구현 없이 실제 DB·Redis 검증 |
| #100 게시본 Ruff·format | 통과, 226개 파일 |
| #100 게시본 mypy·pytest | 실패: 선행 정의 부재로 5개 파일 16개 타입 오류(127개 검사), 테스트 수집 오류 8개 |
| 두 게시본 부분 계약 검사 | 각각 통과: schema 2개·부분 OpenAPI·fixture 7개 |
| #81 + #100 + 선행 통합본 Ruff·format·mypy | 통과: format 264개·mypy 144개 파일 |
| 같은 통합본 전체 BE pytest | 890 passed, skip 0 (392.09초). 실제 DB·Redis·ARQ, migration 왕복·SSE 유실 복구 포함 |
| 같은 통합본 AI pytest | 193 passed |
| FE·실제 외부 계정/LLM·브라우저·Docker 배포 | 미실행. 계약 형식·HTTP fixture 시험으로 완료 처리하지 않음 |

통합본의 선행은 #79 `9cd8189`, #80 `8206cec`, #71 `1a68e90`이다. #71에는 기존 보존 patch의
유실 단계 복원·늦은 상태 역행 방지와 회귀 2개를 로컬에서만 더했다. 공유 config/main 결합 시
#79 문서 길이 설정·문서 라우터와 Task 11 검증·분석 라우터를 함께 보존했다. 이 선행 소스는 게시하지 않는다.
원본 source·검증·구성은 `.claude/scratch/task11-function-split-20261006/`와 별도 worktree에 보존한다.

병합 순서는 필요한 #71 기반 및 #81 → #100이며 #79·#80의 선행과 SSE 후속 보완도 함께 충족해야 한다.
두 base는 develop으로 유지하고, 선행이 아직 없으므로 실제 게시본은 Draft로 둔다. 선행 병합 후 후속 PR에
develop을 반영하고 최종 통합 검사를 다시 실행한다. #69 seed·활성 prompt·실제 외부 연동·FE 정합화는
별도 후속이며 이 재분리만으로 Task 11 전체 완료나 #68·#70 종료를 선언하지 않는다.

## #100 추가 축소 (2026-10-06, 아래 구현과 명세·설계 재분리로 대체)

기존 #81 `96266f3`와 #100 `48413a1`, 전체 개발 source `ecc78f3`를 백업한 뒤 두 PR 번호를 유지한다.
기준 develop은 `ef1a48d`다. 기존 설계의 공통 실행 처리를 #81로 더 옮겼으며 공개 동작·DB 정책은 유지한다.

| PR | 현재 범위 |
| --- | --- |
| #81 | 상태·알림·SSE, 기존 큐 등록, queued run 복구, 계정/수집/부분 실패 공통 처리와 독립 검증. 보조 문서를 포함해 18파일 |
| #100 | 변경 계약·DB 제약·claim·page 지표·종료 원자성·후보 정책과 최종 API/worker 연결·통합 검증, 실제 명세 2개. 26파일 |

`queue.py`와 복구 테스트를 #81로 옮기고 `recovery.py`, `pipeline/run_support.py`로 기존 처리를 추출했다.
후자의 클래스/함수 5개는 본문 AST가 동일하다. `analysis_reaper.py`는 공통 queued run 복구를 호출한 뒤
pending page를 조회·재등록한다. 원래 읽기 전용이던 두 조회를 분리했으며 DB claim·종료 transaction은 바꾸지 않았다.
API 장애→DB 보존→큐 정상화→reaper 재등록 연결은 #100 테스트에서 계속 검증한다. 페이지/부모 run 상태 7조합도 추가했다.

복구 테스트는 #100 생성 API 대신 실제 DB fixture를 준비한다. queued/running·잔여 ARQ 키 시나리오를 보존하고,
종료 run·초기 수집 작업을 재등록하지 않는 회귀를 더했다. 인증·내부 오류 코드·부분 성공 판정도 독립 검증한다.
나머지 기존 테스트는 유지한다. 명세 자체는 변경하지 않았고 decisions·색인·README·구현 기록은 계속 #81의 보조 문서다.

### 이번 추가 축소의 검증

Python 3.12.14 / 전용 PostgreSQL 15.19(:55444) / Redis 7.4.11(:56392). HTTP는 fixture이며 DB·큐는 실제 실행한다.
분리 테스트를 먼저 작성해 두 신규 모듈 부재를 확인한 뒤 구현했다. 아래 수치는 이번 변경에서 새로 실행한 결과다.

| 대상 | 결과 |
| --- | --- |
| #81 게시본 Ruff·format·부분 계약 검사 | 통과: format 217파일, schema 2개·부분 OpenAPI·fixture 7개 |
| #81 게시본 mypy·전체 pytest | 실패: #80·#71 부재, 타입 2파일 6오류(125개 검사), pytest 수집 오류 1개 |
| #100 게시본 Ruff·format·부분 계약 검사 | 통과: format 224파일, schema 2개·부분 OpenAPI·fixture 7개 |
| #100 게시본 mypy·전체 pytest | 실패: #81·선행 부재, 타입 6파일 18오류(126개 검사), pytest 수집 오류 8개 |
| #81 + 선행만 결합(#100 코드·migration 제외) | 독립 진행/복구/공통처리 회귀 35 passed, Ruff·format·mypy 통과 |
| #81+#100+선행 통합 | Ruff·format 267파일·mypy 146파일 통과. 최종 BE 전체 915 passed, skip 0(310.56초) |
| 같은 통합본 AI 전체 | 193 passed |
| 실제 외부 계정/LLM·FE·브라우저·Docker 배포 | 미실행 |

계약 검사는 기존 별도 검사 venv를 사용했다. BE venv에는 계약 검사 패키지가 없어 최초 실행은 미실행이었으며,
소스·의존성 파일 변경 없이 준비된 검사 환경으로 다시 실행해 통과했다. 형식 검사에서 발견한 줄바꿈도 정규화 후 재확인했다.

#81은 이제 수집 공통 처리를 통해 #80에도 의존한다. 검증 선행은 #79 `9cd8189`, #80 `8206cec`, #71 `1a68e90`과
로컬 SSE 유실 복원/상태 역행 후속 patch다. 지원 환경에만 결합했으며 게시본에 복사하지 않는다. #100→#81 방향을 유지한다.
두 PR은 develop 대상 Draft이며 선행·SSE 후속을 최종 대상에 반영한 뒤 재검증해야 한다. #82 동시 반영 시 migration
`0002_agent_storage`와 `0003_analysis_runs` 두 head의 조정도 필요하다. 이 통합 검증에 #82는 포함하지 않았다.
원본·구성·로그는 `.claude/scratch/task11-narrow-20261006/`와 source/게시/통합 worktree에 보존한다.

최종 #100은 28→26파일, 추가+삭제 합계 2,624→2,498줄이다. 실행 코드(`backend/app`)는 973→851줄로 122줄 줄었다.
파일 수만 줄이기 위해 테스트를 제거하지 않았으며, 분리 경계 보강 테스트를 포함한 수치다.

## 구현과 명세·설계 재분리 (2026-10-06, 아래 세 PR 분리로 대체)

사용자의 최종 요청으로 기능별 분리를 취소하고 파일 역할에 따라 기존 PR #81·#100의 이력을 재구성한다.
기준은 `develop@ef1a48d`이며 직전 #81 `a334562`, #100 `fa04a8b`, 전체 source `399ec6a`를 백업했다.
앞 절들의 PR별 파일 수·의존 방향·검증 결과는 당시 이력이며 현재 범위는 아래 표를 따른다.

| PR | 현행 범위 |
| --- | --- |
| [#81 구현](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/81) | 코드·설정·마이그레이션·테스트 35개와 보조 문서 7개, 총 42파일. API·워커·복구·공통 처리·모든 회귀 검증 포함 |
| [#100 명세·설계](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/100) | `spec/shared/contracts/openapi.yaml`, `spec/backend/features/analysis-run.md` 2파일만 포함 |

결정 기록과 색인·README·오류 목록·이 구현 기록은 명세 자체로 분류하지 않고 #81에 둔다.
두 PR의 변경 경로 교집합은 0개다. 최신 코드 35파일과 명세 2파일은 source `399ec6a`와 Git blob이 동일하다.
공통 처리 추출, 큐 장애 복구와 페이지/부모 상태 회귀 보강도 그대로 보존한다. 동작을 과거 버전으로 되돌리지 않는다.
선행 구현·테스트·의존성 파일과 FE·AI 제품 소스는 추가하지 않는다.

### 이번 재분리에서 새로 확인한 결과

Python 3.12.14에서 실제 게시본과 별도 계약 검증본을 구분했다. DB·Redis 서버는 이번에 기동하지 않았다.

| 대상 | 실행·조건 | 결과 |
| --- | --- | --- |
| #81 BE | Ruff check·format | 통과: 234파일 형식 확인 |
| #81 BE | `mypy app` | 실패: 미병합 공고·후보·SSE 정의 부재, 6파일 15오류(133파일 검사) |
| #81 BE | `pytest -q -p no:cacheprovider -ra` | 실패: 선행 부재로 수집 오류 9개. 테스트 실행 통과가 아님 |
| 두 게시본 각각 | `python .claude/scripts/check_contracts.py` | 통과: schema 2개·부분 OpenAPI·fixture 7개. 전용 검사 venv 사용; 전체 API 호환 검사 아님 |
| #81 + #80 실제 카드 schema만 로컬 결합, 기존 OpenAPI | 계약 pytest | 4 failed, 9 passed: 새 결과 필드·후보 오류 계약 부재 확인 |
| 동일 검증본 + #100 명세 2파일 | 같은 계약 pytest | 13 passed. 테스트 수정·skip·assert 완화 없음 |
| 두 게시본 | 원본 blob·경로 교집합·상대 문서 링크·커밋 범위 확인 | 코드 35개와 명세 2개 동일, 경로 중복 없음. 각 커밋 추가+삭제 300줄 이하로 구성 |
| DB·Redis 통합 전체 / AI 전체 / FE·외부 연동·브라우저·Docker | 이번 파일 배정 변경 | 미실행. 앞 절의 BE 915개·AI 193개는 동일 코드의 이전 통합 결과이며 이번 실행 수치가 아님 |

두 PR 모두 develop 대상이며 기존 Draft를 유지한다. #100은 실행 코드가 없는 명세 검토 PR이다.
**#100 검토·병합 → #81에 해당 develop과 필요한 선행·후속을 반영 → 최종 통합 재검증** 순서를 따른다.
#81의 API·워커는 #100의 Python 코드를 import하지 않지만 계약 테스트는 새 명세를 요구한다.

#79 `9cd8189`의 공고 단계 분리, #80 `8206cec`의 후보 단계 분리는 해당 열린 PR에 이미 반영되었다.
#71 `1a68e90`의 SSE 기반과 원격에 없는 유실 단계 복원·상태 역행 방지 후속 patch는 여전히 필요하다.
초기 수집 predicate 수정은 이미 #81에 포함되어 별도 미완료 항목이 아니다. #82까지 함께 반영하면
`0002_agent_storage`와 `0003_analysis_runs`의 migration 두 head를 조정하고 왕복 검증해야 한다.
#69 seed·활성 prompt·실제 외부 연동과 FE 타입·mock·화면 정합화도 남아 있다.

확인 시 열린 develop 대상 PR 18개의 HEAD/base와 실제 변경 목록을 비교했다. #81은 #79의 config·main,
#82의 config, #79·#80·#82·#97의 BE 결정 색인, #97·#98의 공통 결정 색인과 겹친다.
#100은 다른 열린 PR과 직접 변경 경로가 겹치지 않았다. 팀원 로컬 변경이나 이후 갱신까지 검증한 것은 아니다.
원본 bundle·게시 구성·검증 로그는 `.claude/scratch/task11-code-spec-20261006/`와 별도 worktree에 보존한다.

## 세 PR 분리 (2026-10-06, 현행)

사용자의 최종 요청으로 이전 기능별 분리의 공통 구현을 #81에 남기고, 명세 대응 구현만 새 PR #108으로 분리한다.
#100의 head `e02ab13`과 명세 2파일·1커밋은 유지하며 본문의 연결 안내만 갱신한다.
분리 전 #81 `45367c6`, #100 `e02ab13`, 전체 source `7e0118b`를 백업했다. 세 base는 모두 `develop@ef1a48d`다.

| PR | 현행 소유 범위 |
| --- | --- |
| [공통 구현 #81](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/81) | 이전 기능별 분리의 공통 코드·독립 테스트 11파일과 보조 문서 7파일, 총 18파일. 상태·알림·SSE 변환·큐·복구·실행 helper |
| [명세·설계 #100](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/100) | OpenAPI, `analysis-run.md` 2파일만 유지 |
| [명세 대응 구현 #108](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/108) | 결과 schema·조회·서비스·API·최종 파이프라인/워커 연결·DB 모델·migration·실행/계약 테스트 24파일 |

세 PR의 변경 경로 교집합은 모두 0개이고 합집합은 종전과 같은 44파일이다.
코드·설정·migration·테스트 35파일과 명세 2파일은 source `7e0118b`와 Git blob이 동일하다.
README·두 ADR·이 기록은 소유 PR과 적용 조건만 고쳤다. 결정 색인·오류 목록은 #81에 보존한다.
새 명세·기능을 만들거나 테스트를 제거하지 않으며 미병합 선행 파일·FE·AI 제품 소스도 복사하지 않는다.

### 이번 세 PR 분리의 새 검증

Python 3.12.14, 별도 게시 worktree와 계약 검증 worktree를 사용했다. DB·Redis 서버는 기동하지 않았다.

| 대상 | 실행·조건 | 결과 |
| --- | --- | --- |
| #81 BE | Ruff check·format | 통과: 217파일 |
| #81 BE | mypy / 전체 pytest | 실패: 선행 #80·#71 부재, 2파일 6타입 오류(125파일 검사), pytest 수집 오류 1개 |
| #108 BE | Ruff check·format | 통과: 224파일 |
| #108 BE | mypy / 전체 pytest | 실패: #81·공고·후보·SSE 부재, 6파일 18타입 오류(126파일 검사), pytest 수집 오류 8개 |
| 세 게시본 각각 | 부분 계약 형식 검사 | 통과: schema 2개·부분 OpenAPI·fixture 7개. 기존 전용 venv 사용 |
| #81+#108+#80 실제 카드 schema만 로컬 결합 | 기존 OpenAPI로 계약 pytest | 4 failed, 9 passed |
| 동일 검증본+#100 명세 | 같은 계약 pytest | 13 passed. 테스트 수정·skip·assert 완화 없음 |
| Git blob·경로·이력 검사 | 원본과 대조 | 코드35·명세2 동일, 변경 파일 중복·누락 없음, 커밋별 추가+삭제 300줄 이하 |
| DB·Redis 전체 통합 / AI 전체 / FE·외부 연동·브라우저·Docker | 파일 배정 변경 범위 | 이번에는 미실행. 앞 절의 BE915·AI193 통과는 과거 결과 |

#108은 #81의 공통 모듈을 import하지만 #81은 #108의 새 모듈을 import하지 않는다.
#81과 #100은 서로 순서와 무관하게 검토할 수 있다. **#108 병합 전에는 #81·#100과 필요한 선행·후속을 모두 반영하고 재검증**한다.
#81만으로 전체 기능이 연결되지 않으며 #100만으로는 실행 코드가 추가되지 않는다. 세 PR은 Draft로 유지한다.

미병합 #79 `9cd8189`의 공고 단계 분리, #80 `8206cec`의 후보 단계 분리·카드, #71 `1a68e90`의 SSE 기반이 필요하다.
원격 #71에 없는 SSE 유실 단계 복원·상태 역행 방지 후속 patch도 따로 반영해야 한다.
초기 수집 predicate 보정과 `0003_analysis_runs`는 이제 #108에 있다. #82 동시 반영 시 migration 두 head 조정,
#69 seed·활성 prompt·실제 외부 연동, FE 타입·mock·화면 정합화는 여전히 후속 범위다.

분리 착수 시 열린 develop 대상 PR18개의 HEAD/base와 실제 변경 목록을 확인했다. #81은 #79·#82 config와
#79·#80·#82·#97 BE 색인, #97·#98 공통 색인에 겹친다. #108은 #79 main에 겹치며 #100은 직접 경로 중복이 없다.
#100 설계 문서에 남은 #81·#100 참조는 기존 2개 PR 시점의 안내다. 파일·커밋을 유지하라는 요청에 따라 보존하고
현행 세 PR 소유 관계는 각 PR 본문과 이 절에서 관리한다. 팀원 로컬 변경까지 확인했다는 의미는 아니다.
원본 bundle·구성·로그는 `.claude/scratch/task11-three-pr-20261006/`와 별도 source·게시·계약 검증 worktree에 보존한다.
