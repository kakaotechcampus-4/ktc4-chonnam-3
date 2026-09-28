# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

## 2026-09-28 — Task 14 BE Director·Evidence 연결

구현 원본: develop `e53d28b`에서 시작한 `feature/be-agents`의 로컬 worktree와 작업 파일을 보존했다.
게시본: 같은 최신 develop에서 별도로 만든 `feature/be-task14-draft`에 이번 변경만 옮겼다.
미병합 PR의 코드·의존성·마이그레이션을 복사하지 않았으며
FE·AI 제품 소스·OpenAPI는 변경하지 않았다. 현재 호출 가능한 BE 연결부를 구현한 상태이고,
자동 면접 흐름이나 Task 14 전체 완료를 의미하지 않는다.
저장 경계의 근거는 [0005](decisions/0005-director-storage-boundary.md)에 기록한다.

### 구현 범위

- `agents/director/agent.py`: 기존 AI `generate_question`과 BE LLM gateway를 연결한다.
  prompt/model/version은 DB loader와 설정에서 읽고 `QuestionReviewer`는 필수 주입한다.
  gateway의 총 2회 예산·기존 실패 분류를 유지한다. 공통 client에는 선택적 `attempt_sink`만
  추가하여 재시도·reviewer 중 취소되어도 이미 완료된 호출 기록을 수집한다.
- `features/interview/agent_context.py`: DB의 활성 사용자·면접 소유권·답변 이력·선택 저장소의
  공개 접근·고정 SHA를 검사한다. 정상 9턴, 첫 HR, 기술 최소 5회·HR/도메인 합산 최소 3회의
  완주 가능성을 유지한다. 사용 가능한 frame이 없으면 domain persona를 제공하지 않는다.
  같은 SHA의 분석 ID·근거만 전달하고 불완전한 과거 자료를 새 값으로 꾸미지 않는다.
- `features/interview/agent_service.py`: `generate_prepared_question`이 준비 계약을 생성기로
  전달하고 질문·계약·근거 연결·turn 증가·호출 기록을 한 transaction에 저장한다. 외부 호출
  중에는 transaction이 열려 있지 않다. 동일 call ID 재전달은 기존 결과를 반환하고 진행 중인
  같은 턴의 중복 호출은 거절한다. 저장 전 Context가 달라지면 질문을 폐기하고 시도 기록은 남긴다.
- `agents/director/tools.py`, `integrations/github/evidence.py`: 기존 `VerificationRequest`와
  DB가 승인한 `EvidenceScope`, 명시적인 `EvidenceLimits`로 정확한 파일을 조회한다.
  고정 commit→경로의 부모 tree→일반 파일→Contents의 path/blob SHA/hash를 검증한다.
  public repo의 ID를 확인하고 실제 원문은 무인증으로 읽으며 redirect·client 기본 인증/쿠키를
  상속하지 않는다. 심볼릭 링크·submodule·경로 확장·임의 URL을 허용하지 않는다.
  파일 수·HTTP 횟수·응답/누적 byte·전체 시간 상한을 적용한다. 실제 부재와 조회 실패를 구분하고
  후속 실패 전 확보한 유효 자료는 `tool_error.items`에 보존한다.
- `features/interview/agent_queries.py`: 같은 SHA의 L2 경로와 기존 파일 근거에서 범위를 구성한다.
  조회 후 짧은 저장 transaction에서 권한·상태·SHA·경로를 재검증한다. 원문·줄 위치·출처를 보존한
  durable Evidence ID를 반환하며 commit은 호출자가 맡는다. 기존 ID 재저장은 전체 출처가 같아야 한다.
- `0002_agent_storage`: 선택 SHA, 질문 계약, Evidence의 metadata key·요약·줄 범위와 내부
  `llm_call_records`를 추가한다. `0001_initial`은 수정하지 않는다. 기존 자료는 그대로 두고
  새 nullable 컬럼은 NULL로 유지한다. raw output/model/prompt/schema/token/latency/attempt와
  실패·폐기 사유를 내부 DB에 저장하며 반환값·공개 API·일반 로그에 원문을 포함하지 않는다.

### 호출·복구 조건과 남은 연결

1. Task 13은 검증된 선택 분석의 SHA를 `snapshot_head_sha`에 고정하고 실제 prompt·준비된
   `QuestionContract`·독립 reviewer를 공급해야 한다. 현재 HEAD로 빈 SHA를 보충하지 않는다.
   이 구현은 준비 완료 상태 전환·첫 질문 WS 발행을 대신하지 않는다.
2. AI의 자동 목적 선정·DirectorDecision·도구 선택·L2·답변 분석·리포트·실제 reviewer 생산자는
   이번 작업에 포함하지 않는다. 가짜 승인기나 BE의 대체 추론을 추가하지 않았다.
   Task 15는 실제 T3 분석·T4 결정 저장과 WS 흐름에 연결하고, 검증된 persona/계약을 임의로
   덮어쓰지 않아야 한다. 이 서비스는 답변 분석을 자동으로 읽어 다음 행동을 결정하지 않는다.
3. Evidence 호출 순서는 짧은 transaction의 `load_evidence_scope` → transaction 밖의
   `read_files` → 새 transaction의 `store_evidence`다. tools 입력 자체는 인증 API가 아니므로
   외부 요청에서 `EvidenceScope`를 직접 신뢰하지 않는다. 요청별 예산과 토큰 공급은 호출부 책임이다.
   README도 승인된 정확한 경로가 필요하다. metadata/languages/commit의 시점별 근거 생산과
   전역 탐색은 구현하지 않았다. `evaluation_basis`·conflict 저장은 답변 분석 연결의 후속 범위다.
4. 서비스의 근거는 Context에 있는 Evidence·JD 요구사항·이전 답변이다. 면접에 고정된 공고 본문
   생산자가 아직 연결되지 않아 `job_posting` 본문 참조는 `director_input_invalid`로 호출 전에
   거절한다. adapter의 `reference_texts` 지원과 서비스의 DB 근거 연결 범위를 구분한다.
   공고 버전·원문 연결은 Task 9/11과 통합할 때 권한·고정 버전·저장 전 재검증을 함께 추가한다.
5. call ID는 같은 논리 입력의 재전달에만 재사용한다. 취소/실패한 작업을 재실행하려면 별도 ID가
   필요하다. 정상 취소·reviewer 예외·최종 저장 예외는 claim을 종료하고 완료된 attempts를 남긴다.
   강제 프로세스 종료·DB 장애는 정리도 보장하지 못하므로 worker가 실제 실행 종료를 확인한 뒤
   미완료 claim을 복구해야 한다. 자동 복구 worker·임의 TTL은 추가하지 않았다.
   응답이 끝나지 않은 시도의 원문/토큰이나 강제 종료 직전 메모리의 기록을 복원한다고 보장하지 않는다.
6. 현재 migration은 `0001_initial` 뒤다. Task 9/11의 미병합 migration과 함께 적용할 때 실제
   revision graph와 컬럼 중복을 확인하고 merge revision 및 기존 DB upgrade를 재검증해야 한다.
   이 브랜치의 단독 통과를 미병합 전체 통합의 통과로 간주하지 않는다.

### 검증

Windows·Python 3.12·PostgreSQL 15의 전용 로컬 테스트 DB/임시 schema에서 검증한다.
GitHub·LLM 응답과 독립 reviewer는 테스트 fixture이며 실제 계정·유료 모델을 호출하지 않는다.

구현 원본에서 확인한 아래 검증을 2026-09-28 게시 worktree에서도 새로 실행해 통과했다.
Python·설치 의존성은 원본 가상환경을 사용하되 작업 디렉터리와 AI import 경로를 게시본으로
지정하고 실제 경로를 확인했다. DB 테스트에는 로컬 `*_test` DB의 `TEST_POSTGRES_URL`을
명시했다. 미병합 선행 코드를 결합하거나 이전 통합본의 결과를 게시본 결과로 대체하지 않았다.

| 검증 | 결과 |
| --- | --- |
| BE 전체 pytest + 실제 PostgreSQL | **521 passed, skip 0** |
| AI 기존 pytest | **167 passed** |
| BE Ruff check / format --check | 통과, 194개 파일 형식 확인 |
| BE mypy app | 통과, 120개 소스 파일 |
| 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 실제 DB migration | 기존 자료를 넣고 0001→0002 upgrade·downgrade·재적용 통과 |
| Alembic heads | 단독 브랜치의 `0002_agent_storage` 하나 |
| 변경 범위 / git diff --check | FE·AI·OpenAPI 변경 없음, 공백 오류 없음 |

단위/DB 회귀에서 소유권·스냅샷·persona, 외부 호출 중 잠금 해제, 멱등 저장,
상태 변경 결과 폐기, 실패/취소 기록, 허용 파일 범위, 원문/hash/줄 위치를 검사했다.
리뷰 중 발견한 최종 저장 취소·reviewer 예외·재시도 도중 완료 기록 유실·줄 위치 불일치는
실패를 재현한 뒤 수정하여 동일 사례를 통과했다. 공통 계약 검사는 부분 형식 검사다.
전체 면접 E2E·실제 모델 의미 품질·배포 검증은 아직 수행하지 않았다.

게시 전 열린 PR 14개의 원격 파일 목록을 확인했다. 직접 중복은 #79의 이 구현 기록과
#79·#80·#81의 결정 색인이다. 병합 시 각 작업의 기록과 링크를 모두 보존한다. 직접 파일 중복이
없는 #64·#65·#66의 준비·턴 연결, #69의 지식 seed와 활성 prompt, Task 9/11의 migration은
위 후속 조건대로 통합해야 한다. 팀원의 미게시 로컬 변경은 확인 범위가 아니다.

## 2026-09-27 — PR #45 GitHub 수집 리뷰 반영

관련 PR: [GitHub 수집 #45](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/45).
검토 기준은 #45 `cbd6bae`, 통합 검증 기준은 develop `aaee6a8`(#50·#67 병합 포함)이다.

### 변경 범위

- `integrations/github/client.py`: Retry-After를 우선하고 primary quota가 소진됐을 때만
  reset을 사용한다. 나머지 제한 응답에는 60초 대기를 전달한다.
- `pipeline/steps/repo_detail.py`: rate limit과 무효 토큰 모두 저장소 순회를 중단하고,
  확보한 데이터와 미호출 저장소의 중단 원인을 보존한다.
- `RepoDetail.repository_inaccessible`: 저장소 단위 languages 404를 명시적으로 전달한다.
  후속 수집에 성공하면 이를 해제한다. 503·timeout·README/브랜치 404만으로 제외하지 않는다.
- `pipeline/steps/repo_select.py`: 제외 후보와 첫 배치 밖의 정상 후보까지 모두 보존한다.
  eligible 후보에서 포트폴리오 최대 3개·기본 순위 최대 5개·기여도 최대 2개를 각각 고른 뒤
  중복 제거하며, 첫 배치의 `batch_no`·`batch_rank`·`selection_reason`을 별도로 표시한다.
  포트폴리오 언급은 필터를 우회하지 않는다. 접근 불가 재분류 시 수집 당시 배치 이력은 유지한다.
- 기여도 순서는 호출부가 근거로 제공한다. 정보가 없거나 후보가 겹쳐 비는 자리는 임의로 채우지
  않는다. 기존 pushed_at 기반 순위를 유지하며 task-10의 종합 점수·기여도 산정·DB 저장은 포함하지 않는다.
- 중복 `pipeline/initial_sync.py`·`workers/tasks/initial_sync.py`는 develop 골격으로 복원하고
  해당 구현 전용 테스트를 제외했다. 토큰 복호화·폐기 상태 영속화·초기 동기화·큐 연결은 #57에서
  통합한다. 이번 분리는 해당 경로의 롤백·부분 저장 문제를 수정 완료했다는 뜻이 아니다.
- 공개 API·DB schema·enum·의존성은 변경하지 않았다. 필요한 오류·선택 경계에 한국어 주석을 추가했다.

### 실행 결과

Windows, Python 3.12, uv locked 환경에서 실행했다. 외부 GitHub 응답은 MockTransport를 사용했다.

| 작업 디렉터리 / 기준 | 검증 | 결과 |
| --- | --- | --- |
| `backend`, 수정한 PR 브랜치 | 전체 pytest, 전용 PostgreSQL 연결 | 384 passed, skip 0 |
| `backend`, develop 통합본 | 전체 pytest, 전용 PostgreSQL 연결 | 385 passed, skip 0 |
| `ai`, develop 통합본 | 전체 pytest | 167 passed |
| `backend`, 양쪽 기준 | Ruff check·format, mypy app | 통과; format 180개, mypy 115개 파일 |
| 루트, develop 통합본 | 공통 계약 검사 | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 회귀 검증 | 수정 전 실패를 확인한 뒤 동일 사례 재실행 | 제한 대기·토큰 중단·접근 증거·후보 보존·배치 규칙 통과 |
| 독립 검토 | 코드·테스트·DB nullable 계약·중복 범위 | 추가 수정이 필요한 결함 없음 |

PostgreSQL은 전용 로컬 테스트 DB의 임시 schema만 사용했다. 새 DB 쓰기 기능을 검증한 것은 아니다.
실제 GitHub 장애·rate limit을 유발하지 않았으며 서비스 전체 연결이나 배포 검증 결과도 아니다.
공통 계약 스크립트는 부분 형식 검사다.

### 후속 연결

- [#57](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/57)은 #45의 dataclass 반환값과
  저장 직렬화를 맞추고, 인증·작업 ID 중심 worker와 수집 기능을 함께 보존해야 한다.
- 상세 수집 호출부는 전체 후보 중 `filter_status='eligible'`이고 `batch_no=1`인 항목을 사용한다.
  기여도 근거 공급·종합 ranking·후속 page 저장은 task-10에서 연결한다.
- [#68](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/issues/68)의 run partial/failed,
  Redis 제한 기록·SSE 연결은 별도 작업이다. README의 중요한 섹션 중심 축약 정책도 후속 범위다.
