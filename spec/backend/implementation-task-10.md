# Task 10 구현 기록

기준: `develop@7e54047`, 작업 브랜치 `feature/be-repo-match`.
범위의 원본은 [Task 10](../../backend/docs/task-10-match.md)과
[분석 run](features/analysis-run.md)이며 내부 저장 결정은
[0003](decisions/0003-task10-ranking-and-analysis-reference.md)에 기록한다.

## 신규 구현

- `backend/app/features/analysis/candidates.py`: #45의 선택 규칙을 호출해 사용자 소유 후보,
  제외 사유, 순위·첫 배치를 저장한다. 기존 후보 snapshot을 보존하며 commit은 호출자가 맡는다.
- `pipeline/steps/repo_analyze.py`, `repo_analysis_queries.py`: 배치만 상세 수집하고 활성
  프롬프트·정확한 L1 캐시를 조회한 뒤 #75를 호출한다. 외부 I/O 동안 DB transaction을 유지하지 않는다.
  실패 키의 재시도, 성공 캐시 보존, run별 실패·부분 결과, 접근 불가 재분류를 처리한다.
- `analysis_results.py`: 후보에 고정된 L1 참조를 검증한다. 다른 저장소·SHA·프롬프트·L2를 섞지 않는다.
- `pipeline/steps/match_score.py`, `matching.py`: 기술의 직접 일치와 요구사항 문장의 근거를
  확인하고 모든 페이지 합산 최대 5개를 원자적으로 추천한다. DB score는 null이다.
- `queries.py`, `cards.py`, `schemas.py`: 같은 run의 분석·추천을 일관되게 읽어 공통
  RepositoryCard를 만든다. 미분석은 NOT_READY이며 성공·부분·실패 모두 matchScore=null이다.
- `backend/tests/features/analysis/`: PostgreSQL fixture, 후보·L1·추천·동시성·계약 검증.

후보 기본 순위와 카드의 배치 순서를 구분한다. 추천은 저장된 `base_rank`, 배치 실행과 카드
표시는 `batch_rank`를 사용한다. `candidateSource`는 포트폴리오 언급과 기본 필터 근거로 결정한다.
기술 정보가 없거나 불일치하는 성공 L1은 정상 미추천이다. 별도의 selected 필드나 선택 변경은 없다.

## 선행 PR과 게시 범위

| PR | 확인한 HEAD | 의존성 |
| --- | --- | --- |
| [#45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45) | `e3cc0c7` | 후보 선택·GitHub 상세 수집 |
| [#73](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/73) | `b76b7f4` | AI L1 분석·검증 |
| [#75](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/75) | `f1ab897` | BE L1 호출·저장 행 변환 |
| [#79](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/79) | `3d55a34` | 실제 run의 문서·공고 입력 준비 |

Task 10 브랜치에는 위 PR의 구현·테스트·의존성·커밋을 복사하지 않는다. #45/#73/#75의 feature
delta는 검증용 detached worktree에서만 결합한다. #75의 base가 #73이라는 점을 반영하며,
오래된 PR 전체 트리로 develop의 `JDRequirement.category`를 되돌리지 않는다.
#79의 실제 문서·공고 경로는 이번 결합 검증에 포함하지 않고 현재 DB 모델의 자료를 fixture로 준비한다.

새 마이그레이션·의존성·lockfile 변경은 없다. 선행 PR 미병합 상태이므로 develop 대상
Draft로 게시하며, 단독 실행 가능한 완성 PR로 표시하지 않는다.

열린 PR 13개의 변경 파일을 대조한 결과 직접 중복은 #79의 BE 결정 문서 색인이다.
Task 10은 ADR 0003을 사용해 #79의 0002와 구분하며, 통합 시 양쪽 색인 항목을 보존한다.
#57(`0bd0ccd`)에는 이전 후보 선택 코드가 포함되어 있어 통합 시 #45의 최신 선택 정책을 유지해야 한다.
#64(`85c6a5d`)의 면접 선택은 저장소의 임의 성공 L1 존재를 검사한다. 후속 통합에서는
Task 10의 run별 분석 ID·SHA·프롬프트·상태 검증과 정합화해야 한다. 해당 선행 코드는 이 PR에 포함하지 않는다.

## Task 11 호출 계약과 남은 범위

1. API/worker가 사용자 소유권·run 유형·만료·페이지 상태·중복 실행을 검사한다.
2. 후보 준비는 `prepare_candidates(session, run_id, portfolio_full_names=..., min_size_kb=...)`
   호출 후 commit한다. 신뢰할 수 있는 현재 상세 자료가 있을 때만 `contribution_details`를 넘긴다.
   빈 결과는 run 종료 마커를 만들지 않으며 이후 수집 자료가 생기면 다시 평가할 수 있다.
3. 배치 분석은 `analyze_candidate_batch(session_factory, run_id, batch_no, ...)`를 호출한다.
   GitHub client와 `github_token_encrypted`는 같은 계정 조회에서 준비해야 한다. 암호문은 응답·로그에
   노출하지 않는다. 활성 repo_shallow 프롬프트와 LLM 설정은 실제 환경에 준비되어 있어야 한다.
4. 분석 후 `refresh_matches(session, run_id)`와 commit을 마친 뒤 해당 페이지를 완료 처리한다.
   이 함수는 모든 페이지를 다시 계산한다. 새 snapshot으로 무효화된 추천을 건너뛰지 않는다.
5. `get_repository_cards(session, run_id, batch_no=...)`로 조립한 뒤 읽기 transaction을 끝낸다.
   NOT_READY의 202 변환·enqueue, 없는 페이지의 처리, run 최종 상태 집계는 Task 11 책임이다.

Task 11은 후속 페이지 후보 배정, ARQ·7단계 실행 배선, run API, 부분 실패 집계를 연결해야 한다.
현재 BE 명세의 `analyzedCount/failedCount/failedRepositories`와 OpenAPI 차이도 그때 정리한다.
FE의 더 보기 호출·partial 선택 제한·기존 페이지 추천 정보 갱신은 별도 연결 사항이다.
추천이 바뀌어도 사용자가 직접 선택·해제한 ID는 유지해야 한다.

## 검증

PostgreSQL 15의 전용 `task10_test` DB에서 테스트마다 독립 schema를 생성한다.
`TEST_DATABASE_URL`이 없거나 전용 DB 이름이 아니면 DB 테스트는 실패하며 실제 앱 DB로 대체하지 않는다.
GitHub·LLM 요청은 HTTP mock이며 SQLite·실제 유료 모델·실제 사용자 토큰을 사용하지 않는다.

2026-09-28 실행 결과:

| 검증 | 실제 Task 10 브랜치 | #45/#73/#75 결합 검증본 |
| --- | --- | --- |
| BE `ruff check .` | 통과 | 통과 |
| BE `ruff format --check .` | 184파일 통과 | 192파일 통과 |
| BE `mypy app` | 선행 선언 부재로 3파일 10오류 | 120파일 통과 |
| BE 전체 `pytest -q` | 322통과·39실패·skip 0 | 469통과·실패 0·skip 0 |
| AI 전체 `pytest -q` | 이번 변경 없음, 별도 미실행 | 192통과·실패 0·skip 0 |
| 공통 계약 검사 | 2스키마·부분 OpenAPI·fixture 7개 통과 | 공통 계약 변경 없음 |

단독 실패는 `select_candidates`, `app.integrations.github.base` 등 선행 구현 부재이며,
일부 비동기 회귀 테스트는 같은 import 실패로 mock 도달 이벤트도 기다리지 못한다.
누락을 임시 구현이나 skip으로 숨기지 않았다. 단독에서 선행 의존 테스트 두 파일을 제외한
명시적 부분 실행도 309개 통과했다. 결합본의 Task 10 신규 검증은 총 75개이며 전체 469개에 포함된다.
계약 검사는 런타임·TypeScript 대조·전체 API 호환성 검증을 대신하지 않는다.

주요 재현·회귀 검증:

- 후보 중복·제외·대소문자·동률·기여도 근거·동시 준비·rollback.
- SHA/프롬프트/단계가 다른 캐시 제외, 실패 키 재시도, 늦은 실패가 성공을 덮지 않음,
  과거 run 실패 상태 보존, cache miss의 원래 배치 위치 유지.
- 분석 참조 변경 시 이전 추천 무효화, 페이지 완료 순서와 무관한 전체 5개 상한,
  카드 읽기 도중 다른 트랜잭션의 추천 교체 차단.
- 요청 중 재로그인으로 토큰이 교체된 뒤 늦은 401이 와도 새 토큰은 유지.
- README·언어명·모델 결과의 NUL/잘못된 Unicode를 해당 저장소에서 격리.
- 후보 준비 → GitHub 상세 HTTP mock → 모델 HTTP mock → L1 저장 → 추천 → 카드의 통합 흐름.

같은 L1 캐시 키의 실패가 성공으로 갱신되면 과거 raw 출력 전체의 별도 이력까지 복제하지는 않는다.
후보 snapshot이 보존하는 범위는 당시 상태·오류·분석 식별자다.

재현 시 전용 PostgreSQL DB를 마련하고 `TEST_DATABASE_URL`을 명시한 뒤 `backend`에서
`uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy app`, `uv run pytest -q`를 실행한다.
Task 10만 확인하려면 `uv run pytest tests/features/analysis -q`를 사용한다.
선행 통합 전후 결과를 구분하며, 활성 prompt 조회의 기존 PostgreSQL 테스트에는
`TEST_POSTGRES_URL`도 같은 전용 DB로 지정한다.

운영 프롬프트 품질, 실제 LLM 응답 품질, Task 9의 실제 입력 경로와 Task 11/FE 전체 화면 흐름은
이번 검증 범위 밖이다. 사용자 수동 선택 보존은 기존 FE 상태 로직과 서버의 selected 미수정 경계를
대조했으며, 브라우저에서의 전체 흐름을 새로 검증한 것은 아니다.

## 2026-09-30 — 수집·L1 분리와 추천 저장 일관성 보완

기존 PR #80을 유지하고 최신 develop `fbd46eb` 위로 재배치했다. 원본은
`backup/task10-before-followup-20260930`(`cbaa773`)에 보존했다. #45·#57은 이제 develop에 있다.

- `collect_candidate_batch()`는 L0-b 상세 수집·토큰 폐기 결과를 commit하고
  `CollectedCandidateBatch`를 반환한다. 이 값에 토큰을 보관하지 않는다.
- `analyze_collected_batch()`는 수집 자료만 사용해 프롬프트·캐시·L1을 처리하며 GitHub를 다시
  호출하지 않는다. 기존 `analyze_candidate_batch()` 호출은 wrapper로 유지한다.
- Task 11은 최초 run과 후속 페이지 모두 `refresh_recommendations=True`로 L1·후보 snapshot·전체
  페이지 추천을 같은 transaction에서 확정한다. 최초 run은 고정 7단계의 별도 `match_score`에서
  추천을 다시 확인·재계산한다.
- `autoflush=False`에서도 snapshot을 명시적으로 flush한 뒤 추천을 재조회한다. 누락 시 snapshot이
  사라져 NOT_READY/KeyError가 되는 2건을 재현한 뒤 해결했다. 실패 시 함께 rollback하며 완료 페이지의
  추천은 보존한다. 동시 카드 조회는 run 잠금으로 완성된 상태만 읽는다.
- 새 PostgreSQL 검증 7건과 기존 75건, 총 82건이 통과했다. 공개 계약·schema·migration·의존성·FE 변경은 없다.

검증 기준은 `origin/develop fbd46eb`이며, 선행 구현을 로컬 검증 환경에만 결합했다.
전용 PostgreSQL 15·Redis와 HTTP mock을 사용했다. 실제 GitHub·Wanted·유료 LLM·브라우저·운영 배포는 미실행이다.
Task 11 보존 통합본에는 미게시 Task 8 GitHub 보완과 Task 12 SSE 보완도 포함되어 있으므로,
해당 전체 결과를 게시본의 단독 성공으로 해석하지 않는다.

최소 결합본의 GitHub 관련 20건 실패는 수정 없는 develop `fbd46eb`에서 동일한 20건을 실행해
모두 재현했다. 관련 테스트 2개 파일·GitHub 구현 2개 파일의 내용도 양쪽 최소 결합본과 일치한다.
Task 8 후속 범위이며 이번 변경에 가져오지 않았다. Task 12 SSE 후속도 이번 게시 범위 밖이다.

| 환경 | 실행 | 결과 |
| --- | --- | --- |
| 게시본 | `uv sync --locked --group dev` | 통과; 선행 패키지·잠금 파일 복사 없음 |
| 게시본 | `python -m ruff check .`, `python -m ruff format --check .` | 통과; 형식 209파일 |
| 게시본 | `python -m mypy app` | 실패: #75 L1 호출 함수 부재, 1파일 2오류 |
| 게시본 | `python -m pytest -q` | 실패: #75 L1 함수 부재로 수집 오류 2건 |
| 최소 결합본: 게시본 + #75 `0778a60`(#73 포함)의 L1 코드·테스트 | `python -m pytest -q` | 20 failed, 598 passed in 349.11s (0:05:49) |
| 같은 최소 결합본 | Ruff·format·mypy | 통과; 형식 210파일·타입 121파일 |
| Task 11 보존 통합본 + 이번 Task 9·10 변경 | `python -m pytest -q` | 816 passed in 576.90s (0:09:36) |
| 같은 통합본 | Ruff·format·mypy | 통과; 형식 253파일·타입 141파일 |
| 게시본 | 공통 계약 검사 | 2스키마·부분 OpenAPI·fixture 7개 통과 |

최소 결합본의 GitHub `base.py`·`client.py`는 develop 그대로이며 Task 8 미게시 보완을 쓰지 않는다.
#75(#73 포함) 미병합 의존성 때문에 Draft로 표시한다. Task 11 #81은 이번 분리 함수와 원자 저장
옵션을 이미 호출하고 있다. Task 8·12 후속과 선행 병합 뒤 최종 통합 검증은 별도로 필요하다.
