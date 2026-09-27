# AI 작업 Context

상태: Sprint 1 FIX 경계. [0015 결정](../decisions/0015-existing-contracts-and-tool-results.md)에 따라 기존 Context 필드 구성과 다섯 작업의 식별자 인수·전달 책임은 Accepted. 상세 내부 형식은 기존 구조 안에서 구현·검증하며 실행 상한은 운영 조건과 실측으로 정한다.

이 문서는 ARQ 작업, 분석 pipeline, 단일 Director와 단발 LLM task가 어떤 context를 받을 수 있는지 정의한다. 공통 AI 경계는 [계약](../contracts.md), [아키텍처](../architecture.md), [검증](../verification.md), [기준 결정](../decisions/0001-ai-baseline.md)을 함께 따른다.

## 목적

Context는 현재 작업에 필요한 자료와 상태를 선별한 입력 묶음이다. 데이터베이스 전체를 모델 입력으로 직렬화하거나 Redis 값을 영구 원본으로 취급하는 편의 객체가 아니다.

다음 원칙을 동시에 만족해야 한다.

- 현재 사용자와 작업이 접근할 수 있는 자료만 포함한다.
- 작업 결과를 재현하고 오래된 결과를 차단할 최소 식별정보를 포함한다.
- 비밀키, GitHub access token, 불필요한 개인정보와 무관한 과거 문답은 제외한다.
- 원문, 분석 요약, 사용자 주장, 모델 판단을 서로 다른 출처로 표시한다.
- 모델이 권한, 세션 상태, turn 번호, 종료 여부를 직접 확정하지 못하게 한다.

근거: [레이어 규칙](../../../backend/docs/layer-rules.md), [Redis 키](../../../backend/docs/redis-keys.md). 과거 Controller 원칙의 원본 `context/AI.md`는 현재 저장소에 없다. 현행 Controller 역할은 [면접의 역할과 입력](interviewer.md#역할과-입력)에서 확인한다.

## 저장소별 책임

| 저장소 | 책임 | 금지 |
| --- | --- | --- |
| PostgreSQL | 분석 job, candidate, JD, 저장소 분석, 면접 상태, 질문, 확정 답변, 판정, evidence, conflict, report의 원본 | 모델 호출 중 편의를 위해 검증되지 않은 결과를 완료 상태로 확정 |
| Redis/ARQ | 작업 전달, 진행 mirror, Pub/Sub, 중복 완화 lock, 면접 context snapshot | 질문·답변·분석·리포트의 유일한 원본 |
| 원문 접근 경계 | 현재 DB·GitHub에서 권한이 확인된 필요한 원문 | 공개 로그, prompt fixture 또는 평가 데이터로 무단 복제 |

면접 snapshot key는 `iv:ctx:{interviewId}`, 기본 TTL은 2시간이다. Redis 값이 없거나 만료되면 PostgreSQL 원본에서 재구성한다. snapshot이 남아 있어도 PostgreSQL의 종료 상태나 현재 turn보다 우선하지 않는다.

## ARQ 전달 계약

작업 payload에는 직렬화 가능한 식별자와 재시도 판정에 필요한 작은 값만 넣는다. `AsyncSession`, ORM 객체, access token, 원문 전체, LLM client 객체를 enqueue하지 않는다.

고정된 Sprint 1 job 이름은 다음과 같다. [0015 결정](../decisions/0015-existing-contracts-and-tool-results.md)에 따라 `initial_sync`를 제외한 다섯 작업의 기존 식별자 인수와 Worker 재조회 책임을 채택한다.

| job | 최소 payload | Worker가 다시 조회할 원본 |
| --- | --- | --- |
| `initial_sync` | 사용자 또는 GitHub account 식별자; 인증 소유권에 맞춰 구현 시 선택 | 사용자 상태, 암호화 token, 기존 저장소 rows |
| `analysis_run` | `run_id` | 소유 사용자, posting, optional document, candidate와 step 상태 |
| `candidate_page_analyze` | `run_id`, `page_no` | page row, 해당 page candidate, L0-b/L1 cache |
| `interview_prep` | `interview_id` | session, 선택 저장소, posting/JD, L1/L2 결과 |
| `report_generate` | `interview_id` | 완료 session, 확정 turns, evaluation evidence |
| `profile_summary` | `user_id` | 완료 면접에서 사용된 저장소와 생성된 report |

인자의 의미와 전달 책임은 확정하되 Python 함수 signature·인자 타입·payload 직렬화는 기존 호출 경계에 맞추는 구현 세부로 정한다. `initial_sync`의 ID 종류도 기존 사용자·GitHub account의 소유권 관계를 확인해 정하며 새 식별자나 인증 구조를 만들지 않는다.

[0018 결정](../decisions/0018-existing-baseline-bulk-resolution.md)에 따라 이 구현 세부를 사용자에게 개별 선택으로 묻지 않고 호출·소유권 fixture로 확인한다. job별 timeout은 LLM·Context·Tool·동시성 제한과 함께 운영 조건·대표 사례 실측으로 정한다. 단일 worker를 동시 작업 한 개로 간주하거나 근거 없는 수치를 채택하지 않으며, 필요한 상한을 설정·검증하기 전 무제한 외부 호출로 연결하지 않는다.

Sprint 1은 기본 queue 1개와 단일 ARQ worker 프로세스에 위 6개 job을 등록하며, ARQ `max_tries=1`을 사용한다. `deep_analysis`는 현재 고정 job 목록에 별도 등록하지 않고 `interview_prep`이 호출하는 pipeline 단계로 본다. 이를 독립 queue로 바꾸려면 backend pipeline 결정을 갱신한다.

면접 답변별 처리는 Sprint 1 WebSocket turn loop 안에서 처리한다. Sprint 1 고정 job 목록에는 전용 turn job 이름이 없으므로 구현자가 임의로 추가하지 않는다.

Sprint 1은 worker/queue를 물리적으로 분리하지 않는다. 대신 `queued_at`, `started_at`, `completed_at`, `duration_ms`, `queue_wait_ms`, `job_type`, `status`, `error_code`를 수집해 Sprint 2에서 `analysis`, `interview`, `report` queue 분리 여부를 판단한다.

근거: [비동기 pipeline](../../../backend/docs/pipeline.md), [ARQ skeleton](../../../backend/app/workers/arq_app.py).

## Context Builder 입력

상태: [0015 결정](../decisions/0015-existing-contracts-and-tool-results.md)에 따라 기존 입력 범위와 [내부 계약의 Context 필드 구성](../contracts.md)을 채택한다. Context Builder는 순수한 내부 조립 경계이며 별도 Agent가 아니다.

Context Builder는 서비스 계층에서 권한과 상태를 확인한 뒤 다음 중 현재 task에 필요한 항목만 받는다.

- `user_id`, 작업 종류와 원본 row 식별자
- analysis run, interview session, current turn의 식별자와 현재 상태
- 선택된 repository 식별자, primary 여부, 고정 `snapshot_head_sha`
- job posting과 허용된 JD requirement 식별자
- 유효한 repo analysis 식별자, level, head SHA, prompt version
- 이미 채택한 evidence 식별자와 원문 위치
- 현재 질문의 확정 사실과 제출된 최신 answer
- turn count, persona 사용 현황, 확인/미확인 주제, 반복/도구 상한
- 호출할 task의 prompt version과 실제 provider model 설정

각 reference를 역참조할 때도 사용자 접근권한과 작업 범위를 다시 확인한다. 분석 task는 현재 run의 허용 candidate를, 면접 task는 사용자가 선택한 repository를 사용한다. 면접에서는 고정 `snapshot_head_sha`와 다른 분석, 제외된 문서, 다른 사용자의 evidence를 넣지 않는다. 원격 기본 branch의 새 push를 이유로 진행 중인 면접의 ref를 바꾸지 않는다.

Context Builder 반환값은 채택한 기존 필드 구성을 유지한다. 중첩 자료의 상세 타입·참조·null은 기존 생산자와 소비자에 맞춰 구체화하고 fixture로 확인하며, Pydantic 등 구체 클래스는 그 계약을 구현한다. 운영 상한은 위 설정 기준을 따른다. 내부 입력 필드가 새 DB column을 뜻한다고 가정하거나 범용 `dict[str, Any]`를 영구 계약으로 굳히지 않는다.

## 질문의 불변 사실

질문을 사용자에게 전달할 때 다음 사실은 하나의 확정 단위로 연결되어야 한다.

- interview와 turn 식별자
- turn 번호와 parent/depth 관계
- 실제 question text
- persona
- 질문 목적과 필수 확인내용을 담은 Question Contract
- 질문 전제와 허용된 source/evidence reference
- 생성에 사용한 prompt version과 실제 model

[0014 결정](../decisions/0014-minimal-change-revision.md)에 따라 Question Contract의 기존 다섯 항목은 `interview_turns.question_contract` JSONB에 [저장 형식](../contracts.md#question-contract-저장-형식)을 따라 함께 보관하고 별도 테이블은 만들지 않는다. 질문 전달 뒤 persona, 평가 목적 또는 필수 확인내용을 답변에 맞춰 소급 변경하면 안 된다. 재작성한 질문을 전달할 때는 전달 전 후보가 아니라 최종 승인본만 현재 turn의 질문으로 확정한다.

Question Contract의 `basis_refs`에는 `{kind, id}` 연결 정보만 저장하고 원문은 면접 당시 자료에서 읽는다. 코드의 고정 ref와 Evidence 원문 보존은 유지한다. 공고 갱신으로 기존 run·면접의 자료가 바뀌지 않도록 [공고 재조회와 이전 자료 보존](../../backend/features/analysis-run.md#공고-재조회와-이전-자료-보존)을 따른다.

답변은 현재 질문에 대해 사용자가 한 번 제출해 확정한 원문이다. 전송 실패나 작성 중 초안을 평가하지 않는다. 질문과 answer의 대응, session 종료 여부, 중복 제출 여부는 모델 호출 전후에 서비스/Controller가 검사한다.

## LLM 경계

`prompt_loader`만 DB session을 받아 task별 prompt와 model 설정을 읽는다. 서비스는 필요한 prompt 문자열과 검증된 context를 Director 또는 단발 LLM task에 주입한다. Director, 나머지 `llm_tasks`, LLM integration은 DB session을 받지 않는다.

모델에는 다음을 맡길 수 있다.

- 허용된 원문의 구조화 분석 후보
- 답변 분석 후보
- 다음 행동, 질문 목적과 persona 후보
- 질문 문장 후보
- 리포트 feedback 후보

다음은 코드가 확정한다.

- 접근권한과 선택 범위
- current session/turn과 종료 상태
- 중복 실행과 stale result 여부
- DB 상태 전이와 transaction
- 최대 turn, 재시도, 도구 호출 상한
- API/WS로 전달할 최종 이벤트

모델 출력은 Pydantic 등 명시적 schema로 검증한다. JSON parse 또는 schema 검증 실패는 자동 한 번만 재시도하고, 두 번째 실패의 부분 결과나 고친 척한 JSON을 downstream에 넘기지 않는다. raw output 저장은 승인된 column과 보존 정책 안에서만 하며 답변 원문과 개인정보가 일반 application log에 노출되지 않게 한다.

## Evidence 최소화와 보호

Sprint 1 Evidence Retriever는 README, repository metadata, languages, commit metadata, L2 `notable_areas[].path` 주변의 허용 파일만 조회한다. 전체 tree scan, 전역 keyword search, Private 저장소와 vector 검색은 범위 밖이다.

Context의 evidence는 최소한 다음을 구분한다.

- source 종류와 repository 식별자
- 고정 git ref
- 실제 path와 위치
- 원문 snapshot 또는 필요한 최소 excerpt
- 원문과 분리된 요약
- 조회 상태: 발견, 허용 범위 내 미발견, 분석 부족, 도구 장애
- usage: `question_basis` 또는 `evaluation_basis`

도구 성공은 주장의 사실성 판정과 같지 않다. 미발견과 도구 장애를 사용자 주장의 거짓 증거로 쓰지 않는다. 원문을 prompt에 넣기 전 길이와 민감정보를 제한하고, report에는 필요한 turn/evidence reference만 연결한다.

## 멱등성과 stale 결과 차단

ARQ 작업은 reaper 재등록이나 비정상 종료 경계에서 중복 실행될 수 있다고 가정한다. 각 job은 시작과 결과 확정 직전에 PostgreSQL 원본을 다시 확인한다. Sprint 1에서는 ARQ 자동 retry를 사용하지 않으며, `running` worker lost 자동 재실행은 하지 않는다.

1. job 대상이 같은 사용자와 허용 범위인지 확인한다.
2. 이미 같은 identity로 성공한 결과가 있으면 재사용한다.
3. 현재 status가 해당 전이를 허용하는지 확인한다.
4. 입력 fingerprint, head SHA, prompt version, current turn이 시작 시점과 같은지 확인한다.
5. 외부 호출 뒤 조건이 바뀌었으면 결과를 현재 상태에 적용하지 않는다.
6. DB 결과를 commit한 뒤 Redis mirror와 알림을 갱신한다.

질문을 이미 저장하고 알림만 실패했다면 새 질문을 생성하지 않고 저장된 질문을 다시 전달한다. session 종료 뒤 늦게 끝난 질문, 분석 또는 후속 작업은 현재 면접을 되살리거나 turn을 늘리지 않는다.

구체 lock token, transaction isolation, outbox 도입 여부는 Proposed 구현 결정이다. 현재 Redis lock만으로 영구 중복 방지가 된다고 주장하지 않는다. 단, 면접 종료 후 실행되는 `report_generate`와 `profile_summary`는 계약상 정상 후속 작업이다. 종료를 이유로 이 작업까지 일괄 차단하지 않고, 각 job에 허용된 상태 전이를 적용한다.

## 검증

- job 함수 단위 테스트와 enqueue 테스트를 분리한다.
- payload에 ORM/DB session/token/원문 전체가 들어가지 않는지 검증한다.
- 다른 사용자와 선택하지 않은 저장소/evidence가 context에서 제외되는지 검증한다.
- Redis snapshot hit, miss, expiry, 손상 시 PostgreSQL 재구성을 검증한다.
- 동일 job 재실행, 외부 호출 중 session 종료, head SHA/prompt version/current turn 변경을 검증한다.
- 질문, Contract, persona, evidence reference가 같은 turn에 고정되고 소급 변형되지 않는지 검증한다.
- LLM timeout, 재시도 가능한 provider 오류, parse/schema 실패의 한 번 재시도와 raw output 보호를 검증한다. 영구 HTTP 오류·quota 소진 및 서버 최소 대기 초과는 재호출 없이 종료하는지도 확인한다.
- 로그와 error details에 access token, 비밀키, 불필요한 답변 원문이 없는지 검증한다.

현재 runtime과 tests는 docstring 중심 skeleton이다. 이 문서의 Proposed 형식을 이미 존재하는 callable, migration 또는 검증 결과로 보고하지 않는다.
