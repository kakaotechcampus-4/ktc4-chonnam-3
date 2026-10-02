# 0004 Task 11 분석 실행과 복구

- 상태: Accepted — 사용자 승인 구현 범위의 내부 선택. 팀 전체 의결이나 게시본의 구현 완료를 뜻하지 않는다.
- 날짜: 2026-09-28
- 관련 PR: `develop` 대상 Task 11 Draft 게시 범위. PR 번호와 선행 상태는 [구현 기록](../implementation-task-11.md)에서 관리한다.
- 검토자: 별도 팀 승인 기록 없음.

## 맥락

분석 API는 미병합 인증·문서·후보 분석·SSE 구현과 연결해야 한다. 기존 사용자별 active UNIQUE는 다른 공고의 동시 분석까지 막고, 큐 등록 실패·분석 참조 저장과 추천 재계산 사이의 틈은 진행 중단과 일시적인 `not_ready`를 만든다.

## 결정과 이유

- fingerprint는 `[user_id, normalized Wanted URL, document_id 또는 null]`의 JSON을 SHA-256으로 계산한다. active `analysis_run`만 `(user_id, fingerprint)` UNIQUE로 막고 다른 job의 기존 사용자별 제약은 유지한다. 기존 NULL fingerprint 행은 보존하며 사용자별 NULL active 중복도 제한한다.
- 중복 생성의 원자성은 PostgreSQL 제약, 실행 claim은 행 잠금, 큐 중복은 결정적 ARQ ID로 보장한다. 기존 문서의 별도 Redis NX run/page lock은 도입하지 않는다. 같은 권한을 가진 락 둘의 만료·해제 경합을 추가하지 않고 Redis 장애 때 DB에 남은 queued 작업을 복구하기 위한 선택이다.
- INSERT commit 뒤 enqueue한다. 202는 작업 접수이며 완료 보장이 아니다. Redis 장애로 미등록된 queued run/pending page는 30초 주기 reaper가 재등록한다. 큐와 실행 표식이 모두 없는 ARQ payload/result/retry 잔여물만 원자적으로 제거해 복구한다.
- `max_tries=1`, `keep_result=0`으로 실행 중 작업을 자동 재시도하지 않는다. 중복 delivery는 DB claim에서 끝난다. 초기 저장소 수집이 진행 중이면 분석을 시작하지 않고 queued로 남겨 reaper를 통해 후속 실행한다.
- 작업 시간 제한은 기존 600초다. 정상 timeout/취소는 실패 상태로 닫는다. 프로세스 강제 종료로 남은 running 행은 자동 재실행하지 않는다. 운영자가 이전 워커 종료를 확인한 뒤 실패로 닫아 새 요청을 허용해야 한다. Redis 키 유실만으로 워커 사망을 판정하지 않는다.
- preview 문서의 소유권과 portfolio 종류를 확인하고 저장된 URL을 사용한다. 상세 수집/L1 및 공고 fetch/extract를 분리해 실제 7단계에 대응한다. 문서가 없으면 doc_extract만 skipped다.
- 작업마다 짧은 DB transaction을 사용한다. 외부 HTTP/LLM 대기 동안 DB transaction을 붙잡지 않는다. 진행·종료 commit 이후에만 Redis mirror/pubsub에 알리며 알림 실패는 성공 데이터를 되돌리지 않는다.
- 추가 page 상태 원본은 `analysis_repo_candidate_pages`다. 별도 연결 없는 analysis_jobs 행을 중복 생성하지 않는다. requested_at을 queued 시각으로 쓰고 started_at/completed_at/duration_ms/queue_wait_ms를 저장한다. 원래 run 상태·종료 시각은 바꾸지 않는다.
- L1 snapshot 저장과 전체 후보 추천 재계산을 같은 transaction에서 확정한다. autoflush=False 환경에서 재조회하기 전에 flush한다. 완료 page 조회는 DB를 다시 쓰지 않는다.
- SSE는 기존 구독 → DB snapshot 순서를 유지하고 FE `onmessage`가 읽는 data/type/key로 변환한다. DB polling으로 유실된 단계와 종료 원인을 복원하며 늦게 도착한 running 메시지가 완료 단계를 되돌리지 않는다.

## 영향

`0003_analysis_runs`는 `0002_posting_versions`를 전제로 한다. initial_sync ON CONFLICT 조건도 새 인덱스와 함께 맞춘다. downgrade는 기존 사용자/job_type 제약을 위반하는 active 행이 남아 있으면 자료를 삭제하지 않고 거절한다.

공통 결과·조회 정책은 [공통 0006](../../shared/decisions/0006-task11-analysis-result-contract.md)에 기록한다. 원본 통합 환경을 보존하고 `develop` 기준 Draft에는 Task 11 신규 변경만 분리한다. 선행 구현을 복사하거나 합쳐진 함수를 실행한 뒤 나머지 단계를 완료 처리하는 대체 구현은 두지 않는다.

다음 보완은 선행 구현 내부를 변경하므로 별도 후속 범위다. 선행 PR 병합만으로 충족되지 않으며, Task 11 병합 전에 함께 적용하고 통합 검증해야 한다.

| 선행 영역 | 필수 후속 보완 | 없을 때의 영향 |
| --- | --- | --- |
| 공고 서비스 #79 | `fetch_posting` / `complete_posting` 분리. 기존 캐시·버전 저장·잠금 유지 | `jd_fetch` / `jd_extract`의 실제 단계 경계를 실행할 수 없음 |
| 후보 분석 #80 | `collect_candidate_batch` / `analyze_collected_batch` 분리. snapshot 연결 후 flush와 추천 갱신을 같은 transaction에서 수행 | 상세 수집/L1 단계 경계를 실행할 수 없고 완료 page의 추천 일관성을 보장할 수 없음 |
| 초기 수집 #57 | 새 active 인덱스와 일치하도록 `ON CONFLICT` predicate에 `analysis_run` 제외 조건 추가 | 새 마이그레이션 적용 뒤 초기 수집의 충돌 처리가 인덱스를 찾지 못함 |
| SSE 이벤트 #71 | DB polling 시 유실된 단계 복원과 늦은 running 메시지의 상태 역행 방지 | FE 형식 변환만으로 유실 복구·상태 역행 방지를 보장할 수 없음 |

로컬 통합 원본에는 위 보완을 결합하지만, 이를 제외한 Draft 게시본은 단독 실행·전체 구현 완료 상태가 아니다. 통합 원본의 완료·검증 결과와 Draft의 미완료 범위·병합 조건은 [Task 11 구현 기록](../implementation-task-11.md)에서 구분한다. 원본의 검증 결과를 게시본의 검증 결과로 사용하지 않는다.

## 검증

실제 PostgreSQL 15와 Redis 7에서 API·ARQ·마이그레이션을 검증하며 GitHub/Wanted/OpenAI HTTP는 mock한다. 게시본 단독 검증과 선행 구현·후속 보완을 결합한 통합 검증을 나누어 실행한다. 실행 결과와 한계는 [Task 11 구현 기록](../implementation-task-11.md) 한 곳에 기록한다. 실제 외부 계정·LLM 품질·운영 배포 검증이나 FE 후속 화면 완료를 뜻하지 않는다.
