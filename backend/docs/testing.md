# 테스트 전략

상태: Sprint 1 FIX.

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
| 문서 preview | PDF/DOCX/TXT/MD 성공, 미지원 형식, 10MB 초과, GitHub URL 정규화 |
| Wanted | Wanted URL 성공, unsupported site 차단, fetch/extract 실패 구분 |
| GitHub | public만 수집, private/fork/archived/no_language/too_small excluded 저장 |
| Candidate | base_rank, batch_no, batch_rank, selection_reason 저장 |
| Candidate page | 미분석 page 202, 완료 page 200, 중복 enqueue 방지 |
| Analysis | 7 step 상태 전이, partial->FE failed 매핑, result 조회 가능 |
| Interview create | repo 1~5개, L1 succeeded만 허용, 활성 면접 1개 제한 |
| Prep | primary repo 1~2개, notable_areas 필수, preparing_failed 분리 |
| WS | `{type:"answer", text}` 수신, answerReceived/thinking/question/interviewEnd/error 송신 |
| Turn | 첫 turn hr_manager, 9턴 종료, tech_lead 최소 5턴 |
| Evidence | evaluation_basis 보강, answer_vs_code conflict 생성 |
| Redis | `iv:ctx` 만료 시 Postgres에서 재구성 |
| Report | lazy generation 202/200/409, `feedback_json`, profile summary enqueue |
| Events | 고정 10개 외 event_name 거부 |

## LLM 실패

- timeout/provider 오류/parsing 실패는 자동 1회 재시도.
- 2회 실패 시 `llm_timeout`, `llm_parse_failed`, `llm_failed`.
- raw output을 저장하고 깨진 JSON은 downstream에 넘기지 않는다.

## 리포트 점수

점수 산정 근거는 `PENDING_TEAM`이다. Sprint 1 테스트는 response shape, generation 상태, feedback/evidence 연결 중심으로 둔다.

## Sprint 1에서 테스트하지 않는 테이블 기능

- `document_claims`: 테이블은 존재하지만 row 생성/claim 추출은 Sprint 2.
- `report_disagreements`: 테이블은 존재하지만 API/row 생성은 Sprint 2.
- `feedback_signals`, `eval_cases`, `eval_runs`: Sprint 1 DB에서 제외.
