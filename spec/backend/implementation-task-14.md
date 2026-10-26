# BE 구현·검증 기록

구현 범위와 실제 실행 결과를 기록한다. 기능 요구사항은 각 features 문서와 task 문서를 따른다.

## 2026-10-06 — Task 14 Director·Evidence 연결과 고정 질문 배분

게시 대상은 [PR #82](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/pull/82)이며 기준 브랜치는 develop이다.
정상 면접의 배분은 [#97의 공통 ADR 0007](https://github.com/kakaotechcampus-4/ktc4-chonnam-3/blob/f2f1011af2aa72c7034948c2c71699cf25e47a18/spec/shared/decisions/0007-fixed-persona-allocation.md)을 따른다.
현재 BE 연결부의 구현·검증 기록이며 자동 면접이나 Task 14 전체 완료를 의미하지 않는다.
저장 경계의 초기 설계는 [ADR 0005](decisions/0005-director-storage-boundary.md)에 보존한다.

### 구현 범위

- `core/config.py`는 총 9문항·기술 6·도메인 2·HR 1만 허용한다. 잘못된 역할·횟수·중복 환경 입력과
  bool/float의 암묵 변환을 거절하고 기존 설정값을 Context 구성에 전달한다.
- `agent_context.py`는 활성 사용자·소유권·면접 상태·답변 이력·선택 저장소의 공개 접근·고정 SHA를 확인한다.
  첫 질문은 HR이며 이후에는 할당이 남은 기술·도메인만 허용한다. 순서와 교대를 강제하지 않는다.
  할당 초과·잘못된 과거 이력·10번째 질문 생성을 거절하며 이미 제시한 Persona를 바꾸지 않는다.
- 미분류 공고에는 [기존 도메인 정책](../ai/decisions/0005-domain-question-policy.md)에 따라 Context에만 활성
  `etc` 프레임을 사용한다. 공고의 `domain_category=NULL`은 보존하고 확인된 category를 임의로 대체하지 않는다.
  도메인 할당이 남았는데 활성 프레임이 없으면 첫 HR 생성 전부터 내부 `domain_frames_unavailable`로 중단한다.
  이때 모델 호출·호출 기록·질문·턴 증가가 발생하지 않는다. 도메인 2회가 끝났다면 프레임 부재만으로
  남은 기술 질문을 막지 않는다. 질문 횟수 외에 프레임 수·축별 할당 규칙을 추가하지 않는다.
- `agents/director/agent.py`는 기존 AI 생성기와 BE LLM gateway를 연결한다. DB prompt loader가 실제
  prompt/model/version을 공급하고 호출자가 독립 `QuestionReviewer`와 준비 계약을 전달한다.
- `agent_service.py`는 동일한 설정 배분으로 생성 전·저장 직전 Context를 검사한다. 질문·계약·근거 연결·턴 증가·
  호출 기록을 같은 transaction에 저장하며 외부 모델 호출 동안에는 DB 잠금을 유지하지 않는다.
  동일 call ID 재전달은 기존 결과를 반환하고 진행 중인 같은 턴의 중복 호출은 거절한다.
  늦은 응답이나 프레임 변경으로 Context가 달라지면 질문을 폐기하고 호출 시도 기록을 남긴다.
- `attempt_sink`는 기존 gateway의 완료된 시도를 보존한다. 재시도·reviewer·최종 저장 중 취소/예외가 나도
  확보한 원문·토큰·모델·prompt version을 기록하며 모델 실패와 적용 폐기를 구분한다.
- `agents/director/tools.py`, `integrations/github/evidence.py`는 DB 승인 경로와 고정 SHA의 일반 UTF-8 파일만 읽는다.
  commit/tree/blob·경로·원문 hash·줄 위치를 검사하고 원문 요청에 인증을 상속하지 않는다.
  redirect·심볼릭 링크·submodule·전역 탐색을 허용하지 않으며 유한 파일/요청/시간/byte 상한과 부분 결과를 보존한다.
- `agent_queries.py`는 소유권·면접 상태·접근·선택 SHA·경로를 재검사하고 근거 원문과 출처를 저장한다.
  같은 SHA의 분석·Evidence만 Context에 넣으며 불완전한 과거 자료는 추측해 복구하지 않는다.
- `0002_agent_storage`는 이 Task에서 필요한 질문 계약·선택 SHA·Evidence 출처 컬럼 및 `llm_call_records`를 추가한다.
  `0001_initial`은 유지하고 과거 자료를 추측해 backfill하지 않는다. 이번 배분 변경 때문에 추가 migration을 만들지 않았다.

### 게시 이력과 변경 범위

사용자가 기존 PR 번호를 유지하고 유동 배분 커밋을 고정 구현으로 교체하도록 요청했다.
기존 게시 HEAD `b262f29`는 `backup/be-task14-flexible-20261006`, 수정본 `8aee453`은
`fix/be-task14-fixed-allocation`에 보존했으며 별도 Git bundle도 만들었다. 최초 개발 원본 `feature/be-agents`도 보존했다.
최신 develop `ef1a48d`에서 별도 게시 이력을 재구성했으며 Context·service·배분 테스트는 최초 추가부터 고정 구현이다.
이전 PR의 14개 커밋은 새 게시 HEAD의 조상이 아니다. 수정본의 runtime/test 24개 파일은 검증 통합본과 동일하다.
설정 파일의 최신 인증 변경을 보존했고, #97 문서·hook이나 다른 미병합 PR의 코드·테스트·의존성을 복사하지 않았다.
공개 REST·WS 계약·Persona enum·FE·AI 제품 소스·의존성은 변경하지 않았다.

### 실제 게시본 검증

2026-10-06, Windows / Python 3.12 / PostgreSQL 15.19 / Redis 7.4.
작업 디렉터리와 BE·AI import 경로를 새 게시 worktree로 지정해 실행했다. 의존성 환경은 기존 locked venv를 사용했다.
`TEST_POSTGRES_URL`은 로컬 `task14_test`의 임시 schema, `TEST_DATABASE_URL`은 별도 `task14_rewrite_publish_test`,
`TEST_REDIS_URL`은 검증 전용 Redis DB 15를 지정했다. 외부 GitHub·LLM·reviewer는 fixture다.
이전 수정본의 557건·통합본의 825건을 이번 게시본 실행 결과로 재사용하지 않는다.

| 작업 디렉터리 | 검증 | 결과 |
| --- | --- | --- |
| `backend` | 전체 `pytest -q -p no:cacheprovider -ra`, 위 세 테스트 환경 변수 지정 | 825 passed, skip 0, 194.55초 |
| `backend` | Ruff check·format·mypy app | 통과, format 222개·mypy 123개 파일 |
| `ai` | 전체 `pytest -q -p no:cacheprovider` | 193 passed |
| 루트 | `check_contracts.py` | schema 2개·부분 OpenAPI·정상/오류 fixture 7개 통과 |
| 게시 이력 | 원본 보존·runtime/test 비교·모든 중간 커밋의 고정 구현·커밋별 줄 수 | 독립 검토 통과 |
| 실제 서비스 | 자동 면접 E2E·실제 모델 의미 품질·운영 seed 설치·배포 | 미실행, 준비·턴 실행·실제 생산자 연결 필요 |

단위 테스트는 첫 HR 이후 가능한 28가지 순서 모두 6/2/1로 완주하는지 확인한다. DB 테스트는 실제 9문항 저장,
중복 재전달·초과 질문·허용 밖 Persona·프레임 부재와 상태 변경을 검증한다. 답변은 fixture에서 직접 저장하므로
실제 답변 처리·정상 종료 검증은 아니다. 공통 계약 스크립트도 부분 형식 검사이며 전체 API 호환성을 증명하지 않는다.

### 후속 연결과 협업 조건

- Task 13의 생성 서비스 #64는 병합됐지만 준비 worker 연결은 남아 있다. 검증된 선택 분석 SHA를 `snapshot_head_sha`에
  고정하고 준비 계약·독립 reviewer를 공급해야 한다. 프레임 부재는 기존 `prep_failed`·`preparing_failed`·재시도에 연결한다.
- Task 15 #65·#66은 질문 저장 책임을 이 서비스와 하나로 통합해야 한다. `compose → save_question`에 그대로 연결하면
  저장이 겹치므로 검증된 Persona·QuestionContract를 덮어쓰거나 턴을 다시 증가시키지 않아야 한다.
  T3/T4·WS 및 9번째 답변 처리 완료 후 정상 종료·`interviewEnd` 검증이 남는다.
- #69 도메인 프레임의 팀 검수와 실제 공급, 별도의 활성 prompt 공급, 실제 reviewer·자동 목적 선정·L2·답변 분석·리포트 연결이 남는다.
  개발 후보를 운영 seed로 자동 활성화하거나 임시 분류기·대체 질문·가짜 승인기를 추가하지 않았다.
  실행 프롬프트와 FE mock의 이전 정책 정합화도 별도 범위다.
- #79·#81의 migration과 합치면 `0002_agent_storage` 및 `0003_analysis_runs` 두 head가 생긴다.
  확인한 migration 사이에 직접 중복 컬럼은 없으며 실제 graph 연결과 기존 DB upgrade·downgrade·재적용을 재검증해야 한다.
  현재 단독 migration 검증은 이 통합 검증을 대신하지 않는다.
- 고정 공고 본문·버전·권한 연결 전에는 `job_posting` 본문 참조를 `director_input_invalid`로 거절한다.
  metadata·languages·commit의 시점별 근거, 전역 탐색, `evaluation_basis`·conflict 저장은 후속 범위다.
- call ID는 같은 논리 요청 재전달에만 재사용한다. 강제 프로세스 종료·DB 장애 뒤 미완료 호출 복구는 worker가
  실제 실행 종료를 확인한 뒤 처리해야 하며 완료되지 않은 원문·토큰을 추측하지 않는다.

### 2026-10-27 리뷰 후속 검증

원본 `0e973f3`과 기존 migration을 보존하고 후속 커밋으로 수정했다. 위 과거 검증과 선행 조건은
당시의 기록이며, 아래 결과는 `develop@d063d8d`에 이번 게시본을 결합한 별도 worktree에서 새로 확인했다.
Task 14 고유 절은 이 파일로 이동하고 공용 `implementation.md`의 다른 기록은 그대로 보존했다.

- Director adapter가 검증된 `settings.llm_base_url`을 공통 gateway에 전달한다. direct/proxy 두 경우의
  실제 adapter→AI Director→gateway 경로를 HTTP mock으로 검증하며 URL·인증 토큰·prompt 모델을 구분한다.
  수정 전 두 경우 모두 필수 `base_url` 누락으로 실패했고 수정 후 통과했다.
- `0002_agent_storage`의 ID·부모·DDL은 변경하지 않았다. 신규 DDL 없는
  `0003_agent_storage_merge`가 `0002_agent_storage`와 `0002_posting_versions`를 합친다.
  두 부모 각각이 이미 적용된 DB에서 기존 공고 자료를 보존하며 전진·합류 해제·재적용을 검증했다.
  합류 해제는 부모 DDL을 되돌리는 동작과 구분한다. 배포 DB의 실제 적용 이력은 확인하지 않았다.
- 현행 고정 6/2/1 근거는 공통 ADR 0008로 연결하며 당시 ADR 0007 링크는 이력으로 남겼다.
  gateway의 기존 `base_url`, deadline 처리와 `attempt_sink`를 모두 보존했다.

| 검사 시점·대상 | 검증 | 결과 |
| --- | --- | --- |
| 2026-10-26, 최신 develop 결합본 BE | 전체 `pytest -q -p no:cacheprovider -ra` | 1291 passed, skip 0, 663.20초 |
| 같은 결합본 AI | 전체 `pytest -q -p no:cacheprovider` | 309 passed |
| 같은 결합본 BE | Ruff check·format·mypy app | 통과, format 294개·mypy 141개 파일 |
| 같은 결합본 루트, 기존 계약 전용 venv | `check_contracts.py` | schema 2개·부분 OpenAPI·fixture 7개 통과 |
| 2026-10-27, 최종 코드 재확인 | 실제 PostgreSQL migration 3건·adapter·revision graph | 22 passed, 3.47초 |
| 최종 게시 head와 `develop@d063d8d` | merge-tree·기존 migration 보존 | 충돌 없음, 원본 migration 변경 없음 |
| 실제 외부 서비스·운영 환경 | GitHub·LLM·자동 면접 E2E·운영 seed·배포 | 미실행 |

전용 PostgreSQL `127.0.0.1:56526/task10_test_pr82_test`와 Redis `127.0.0.1:64526/13`만 사용했다.
migration 검사는 매번 독립 임시 schema를 만들고 제거했다. BE venv의 첫 계약 검사는 `jsonschema`
부재로 미실행됐으며, 기존 계약 전용 venv에서 다시 실행해 통과했다. 최종 재확인에서 import 경로도
결합 worktree의 adapter·gateway·AI 계약을 가리키는지 확인했다. 원격 CI는 push 후 별도 확인한다.

위 단일 head 결과는 현재 develop와 #82의 조합에 한정한다. #108·#127 등 후속 migration은 기존 ID와
부모를 보존한 추가 합류 revision으로 연결하고 실제 최종 graph·기존 자료·왕복을 다시 검증해야 한다.
준비 worker·턴 처리·정상 종료·실제 reviewer 공급은 위 후속 범위를 유지하며 이번 통과 수치로 완료를
대신하지 않는다. 공개 REST·WS·AI 계약은 바꾸지 않았다.

