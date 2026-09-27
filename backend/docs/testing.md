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

## LLM 실패

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
