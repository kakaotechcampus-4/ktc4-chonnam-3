# 0006 Task 11 분석 결과의 부분 실패 계약

- 상태: Accepted — 현재 사용자가 승인한 Task 11 구현 범위의 계약 구체화. 구현·통합 검증 완료를 뜻하지 않는다.
- 날짜: 2026-09-28
- 결정 근거: 사용자가 Task 11 구현 진행을 승인했다. 아래 원소 구조는 누락된 계약을 일관되게 연결하기 위한 구현 선택이며, 사용자가 각 필드 형태를 직접 선택했거나 팀 전체가 의결했다는 기록은 아니다.
- 검토자: 별도 팀 검토 기록 없음
- 관련 PR: 선행 후보 분석 #80과 `develop` 대상 Task 11 Draft의 연결 범위다. PR 번호와 선행 상태는 [Task 11 구현 기록](../../backend/implementation-task-11.md)에서 관리한다.

## 맥락

[분석 Run 명세](../../backend/features/analysis-run.md)는 partial run의 결과 조회와 `analyzedCount`, `failedCount`, `failedRepositories[]`를 요구한다. 공통 OpenAPI·FE 타입에는 세 필드가 없고 실패 배열 원소 형태도 없었다. 카드에는 필터 탈락 저장소가 나타나지 않으므로 카드만 세면 실제 배치 실패가 누락된다.

## 결정과 이유

기존 결과 필드는 유지하고 다음 세 필드를 필수로 추가한다.

| 필드 | 형태 | 의미 |
| --- | --- | --- |
| `analyzedCount` | 0 이상의 정수 | 배정 당시 eligible이었던 저장소의 run별 L1 snapshot 중 `succeeded` + `partial` 수 |
| `failedCount` | 0 이상의 정수 | 같은 집합의 `failed` 수. 실패 배열 길이와 같음 |
| `failedRepositories` | `{repositoryId: string, errorCode: string}[]` | 실패한 저장소의 식별자와 내부 오류 코드. 실패가 없으면 빈 배열 |

현재 run의 배치 배정과 연결된 분석 snapshot을 집계한다. 이후 private·inaccessible 등으로 카드에서 제외된 저장소도 집계·실패 목록에는 포함하며 메타데이터나 인증 토큰을 덧붙이지 않는다. 아직 L1 결과가 없는 저장소를 성공이나 실패로 추정하지 않는다. `partial` 저장소는 분석 수에는 포함되지만 기존 면접 선택 조건인 L1 `succeeded`를 만족하지 않는다.

`failureReason`은 기존 BE 내부 `analysis_jobs.error_code`를 그대로 사용한다. `token_invalid`·`llm_parse_failed`를 다른 표시 코드로 변환하지 않으며, HTTP envelope의 기존 `github_token_invalid` reason과 구분한다. 새 오류 reason은 만들지 않는다.

후보 page는 기존 오류 레지스트리와 동일하게 `400 invalid_request`(필수 양의 정수 page 검증), `409 not_ready`, `409 candidate_page_failed`, `410 run_expired`를 명세에 반영한다. 기존 정상 `200`과 분석 중 `202 {status: analyzing, retryAfter: 3}`은 유지한다.

## 영향과 검증

### 조회·페이지 정책의 구현 선택

- `ANALYSIS_RUN_TTL_SECONDS` 기본값 7200초는 run의 created_at부터 계산한다. 소유자에게도 만료한 run 조회는 410이며, 다른 사용자·없는 run도 같은 410을 반환한다. 영구 분석 자료를 삭제하는 TTL이 아니다. 실행 전 만료 작업은 실패로 닫는다.
- 결과는 succeeded/partial만 200, queued/running/failed/canceled는 409 not_ready다. 상태 조회의 DB partial → FE failed 매핑은 유지한다.
- 첫 page는 기존 혼합 batch 그대로다. 나머지 eligible 후보는 고정 base_rank 순서, `REPO_CANDIDATE_LIMIT` 기본 10개로 page 2부터 배정한다. 범위 밖은 200 빈 배열, 실패 page는 409 candidate_page_failed이며 조회로 자동 재시도하지 않는다.
- mentionedRepoCount는 문서의 정규화 URL 중복 제거 수, matchedRepoCount는 모든 run 후보 중 포트폴리오 언급과 연결된 수다. 페이지를 열었다는 이유로 연결 수가 달라지지 않는다.

이 항목은 기존에 명시되지 않은 경계의 구현 선택이며 별도의 팀 전체 합의로 기록하지 않는다.

- 최종적으로 OpenAPI, FE 타입, REST 참조 문서, BE 응답 스키마를 같은 형태로 연결한다. BE·OpenAPI 계약은 유지하며 FE 타입·문서 반영은 별도 후속 작업이다. schema 계약 검증과 실제 run 집계 검증을 구분한다.
- FE 타입을 반영할 때 MSW 결과 fixture에도 세 요약 필드를 함께 추가해야 한다. 실제 더 보기 호출·오류 UX, partial 카드 선택 제한, 부분 실패 후 결과 이동 및 나머지 MSW 동작 정합화도 FE 후속 범위다. 이 문서가 FE 런타임 동작 완료를 뜻하지 않는다.
- 계약 테스트는 필수 필드, camelCase, 음수 거절, 실패 원소 구조와 인증 토큰 등 미정의 필드 거절을 확인한다. 실행 결과는 [Task 11 구현 기록](../../backend/implementation-task-11.md)에서 관리한다.

### 게시 범위와 적용 조건

Accepted는 현재 사용자가 승인한 범위에서 이 계약을 채택한다는 뜻이다. 로컬 통합 원본의 구현·검증 완료와 선행 구현을 제외한 Draft 게시본의 미완료 상태는 구분한다. 통합 원본의 테스트 결과로 게시본의 단독 실행이나 전체 기능 완료를 주장하지 않는다.

2026-09-28 사용자 요청으로 PR #81의 FE 변경을 제외한다. 계약 결정 자체는 유지하며, 제외 파일·재검증·후속 적용 범위는 [구현 기록](../../backend/implementation-task-11.md#fe-변경-제외와-재검증-2026-09-28)에 기록한다.

실제 run 실행에는 선행 인증·문서·후보 분석·SSE 구현 외에 공고 fetch/extract 분리, repo 상세 수집/L1 분리와 snapshot flush·추천 갱신의 원자성, 초기 수집의 새 인덱스용 `ON CONFLICT` predicate, SSE 단계 polling 복원·상태 역행 방지 보완이 필요하다. 이 후속 범위는 선행 PR 병합만으로 충족되지 않는다. 적용 조건은 [BE 0004](../../backend/decisions/0004-task11-run-execution.md)를 따르며, 보존한 통합 원본과 Draft의 검증 결과·제외 범위·병합 조건은 [구현 기록](../../backend/implementation-task-11.md) 한 곳에서 관리한다.

## 대체 관계

기존 partial run → FE failed 매핑과 결과 조회 허용 정책을 변경하지 않는다. 누락된 배열 원소 형태를 BE·OpenAPI에서 보완한다. FE REST 참조 문서의 내부 오류 코드 별칭·후보 오류 설명을 현행 BE 레지스트리에 맞추는 작업은 후속 FE 반영에 포함한다. 기존 설계 원문과 미완료 화면 작업은 보존한다.
