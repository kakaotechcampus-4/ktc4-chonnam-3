# 테스트 전략

상태: Sprint 1 검증 기준 FIX. 아래는 구현 시 충족할 체크리스트이며, 테스트 구현·실행·통과를 보고하는 문서가 아니다.

## 원칙

- GitHub, Wanted, LLM은 mock한다.
- DB는 PostgreSQL 기준으로 검증한다. SQLite로 대체하지 않는다.
- ARQ는 job 함수 단위와 enqueue 검증을 분리한다.
- WebSocket은 텍스트 프로토콜만 Sprint 1에서 테스트한다.

## 필수 테스트

| 영역 | 테스트 |
| --- | --- |
| 계약 | Pydantic 응답이 camelCase이며 snake_case가 새지 않음 |
| 에러 | 모든 AppError가 error envelope로 반환됨 |
| DB | CHECK/UNIQUE/INDEX 핵심 제약 검증 |
| 문서 preview | 포트폴리오 PDF/DOCX/TXT/MD 성공, 미지원 형식, 20MB 상한·초과 거부, GitHub URL 정규화 |
| Wanted | Wanted URL 성공, unsupported site 차단, fetch/extract 실패 구분, 성공 자료의 7일 재사용 기준 |
| GitHub | public만 수집, private/fork/archived/no_language/too_small excluded 저장 |
| Candidate | base_rank, batch_no, batch_rank, selection_reason 저장 |
| Candidate page | 미분석 page 202, 완료 page 200, 중복 enqueue 방지 |
| Analysis | 7 step 상태 전이, partial->FE failed 매핑, result 조회 가능 |
| Interview create | repo 1~5개, L1 succeeded만 허용, 활성 면접 1개 제한 |
| Prep | primary repo 1~2개, notable_areas 필수, preparing_failed 분리 |
| WS | `{type:"answer", turn, text}` 수신, turn mismatch 차단, answerReceived/thinking/question/interviewEnd/error 송신 |
| Turn | 첫 turn hr_manager, tech_lead 목표 6턴·최소 5턴, domain_lead+hr_manager 합산 최소 3턴, 개별 배분 비고정·HR 재선택, 9턴 종료 |
| Evidence | evaluation_basis 보강, answer_vs_code conflict 생성 |
| Redis | `iv:ctx` 만료 시 Postgres에서 재구성 |
| Report | lazy generation 202/200/409, `feedback_json`, profile summary enqueue |
| Events | 고정 10개 외 event_name 거부 |

## 실제 PostgreSQL 프롬프트 검증

`tests/llm_tasks/test_prompt_postgres.py`는 실제 PostgreSQL에서 prompt loader와 초기 seed를 검사한다.
LLM이나 운영 prompt는 필요하지 않다. 테스트 전용 DB를 준비한 뒤 backend 디렉터리에서 실행한다.

```powershell
# 테스트 전용 접속 URL을 설정한다. 실제 비밀번호를 문서/로그에 남기지 않는다.
$env:TEST_POSTGRES_URL = 'postgresql+asyncpg://TEST_USER:TEST_PASSWORD@127.0.0.1:TEST_PORT/TEST_DATABASE'
uv run pytest -q tests/llm_tasks/test_prompt_postgres.py
# 같은 DB 설정을 포함한 전체 BE 검사
uv run pytest -q
```

이 검사는 `.env`나 `DATABASE_URL`을 자동으로 사용하지 않는다. `TEST_POSTGRES_URL`이 없으면
13개 검사는 skip되며, 명시한 URL이 연결되지 않으면 실패한다. 접속 계정은 테스트 DB에서 schema를
생성·삭제할 수 있어야 한다. 각 검사가 UUID 기반 전용 schema를 만들고 끝나면 해당 schema만 삭제한다.
Docker가 있으면 기존 `docker-compose.yml`의 PostgreSQL 15를 사용할 수 있다. Windows에서는
PostgreSQL 공식 [Windows 다운로드 안내](https://www.postgresql.org/download/windows/)의
설치 없는 바이너리로도 임시 인스턴스를 실행할 수 있다.

현재 브랜치에는 실행 가능한 DB migration이 없으므로 테스트 fixture는 DB branch의 고정 커밋
`c731c5b87d8811885bf5f2edb07ec54569e1a7eb`, `backend/migrations/versions/0001_initial.py`에 있는
prompt_versions 테이블과 두 UNIQUE 제약만 사용한다. 전체 migration 검증으로 보고하지 않는다.
DB 구현 병합 후에는 fixture를 실제 migration과 계속 일치시킨다.

검증 범위는 7개 prompt 등록·재실행, 기존 버전 보존·활성 전환, 조회 없음/중복, model/template 충돌,
commit 전 타 세션 가시성, 호출자 rollback, task/version UNIQUE 및 활성 버전 부분 UNIQUE다.
동시 seed는 독립 세션에서 `pg_blocking_pids`로 실제 transaction lock 대기를 확인하고,
동일 입력 성공·다른 본문 충돌을 검사한다.

2026-09-23 로컬 PostgreSQL **15.19**에서 해당 **13개 통과**, 같은 설정의 전체 BE **133개 통과**.
이후 임시 인스턴스는 종료했으며, 프로젝트 `.env`와 기존 서비스 DB 설정은 변경하지 않았다.

## LLM 실패 처리

- timeout/provider 오류/parsing 실패는 자동 1회 재시도.
- schema 실패도 공통 호출 계층에서 자동 1회 재시도할 수 있다.
- semantic 실패는 재호출하지 않는다.
- 2회 실패 시 `llm_timeout`, `llm_parse_failed`, `llm_failed`.
- raw output을 저장하고 깨진 JSON은 downstream에 넘기지 않는다.

## 리포트 점수

Sprint 1 리포트는 0~100 score 6개와 단순 평균 `totalScore`를 반환한다. 항목별 세부 기준 seed 문구는 추후 보강될 수 있으나, 공개 응답에는 null/status/가중치를 사용하지 않는다.

## Sprint 1에서 테스트하지 않는 테이블 기능

- `document_claims`: Sprint 1 테이블 생성 대상이지만 row 생성/claim 추출은 Sprint 2. 실제 migration 적용은 별도 검증한다.
- `report_disagreements`: Sprint 1 테이블 생성 대상이지만 API/row 생성은 Sprint 2. 실제 migration 적용은 별도 검증한다.
- `feedback_signals`, `eval_cases`, `eval_runs`: Sprint 1 DB에서 제외.
