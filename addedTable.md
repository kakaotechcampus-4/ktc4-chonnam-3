# 브레인스토밍 후 테이블 판정

작성일: 2026-09-10

기준: 기존 제공 테이블은 `context/DB.md`의 `[TABLE]` 항목으로 본다. 이 문서는 브레인스토밍 과정에서 새로 추가됐거나 필요성이 재검토된 테이블의 최종 판정을 정리한다.

## 신규 추가 후 KEEP

| 그룹 | 테이블 | Sprint 1 판정 | 이유 |
| --- | --- | --- | --- |
| 분석 후보 | `analysis_repo_candidates` | 생성/사용 | 전체 public repo의 run별 추천 후보 순서, 필터 결과, 추천 사유를 재현 가능하게 저장 |
| 분석 후보 | `analysis_repo_candidate_pages` | 생성/사용 | 후보를 10개 단위 page로 분석/조회하고, 미분석 page 요청 시 ARQ job 상태 추적 |
| 지식/Seed | `score_criteria` | 생성/사용 | 리포트 score key/label/criteria를 코드에 박지 않기 위해 유지. 세부 기준은 `PENDING_TEAM` |
| 지식/Seed | `prompt_versions` | 생성/사용 | 작업별 prompt version, 모델명, 활성 여부를 기록하고 LLM 결과 재현성 확보 |
| 지식/Seed | `domain_question_frames` | 생성/사용 | `domain_lead` 질문을 도메인별 frame 기반으로 생성 |
| 지표 | `events` | 생성/사용 | 분석/추천/면접/리포트의 핵심 funnel event 저장 |

## 신규 추가 후 DROP/MERGE

| 그룹 | 테이블 | 판정 | 이유 |
| --- | --- | --- | --- |
| 리포트 | `report_persona_feedbacks` | MERGE | persona별 피드백은 리포트 스냅샷 성격이 강하므로 `interview_reports.feedback_json`에 저장 |
| 지식/Seed | `topic_taxonomy` | DROP/MERGE | Sprint 1에서 `interview_turns.topic_code`에 FK를 걸지 않으므로 별도 테이블 실익이 낮음 |
| 지식/Seed | `interview_personas` | DROP/MERGE | persona는 `tech_lead`, `hr_manager`, `domain_lead` 3개 CHECK 값으로 충분 |
| 지식/Seed | `probe_patterns` | DROP/MERGE | Sprint 1에서는 prompt/Director 로직으로 흡수하고 운영 테이블로 관리하지 않음 |
| 지표/평가 | `feedback_signals` | DEFER/DROP | 범용 피드백 signal은 `report_disagreements`와 중복 가능성이 있어 Sprint 2에서도 필요성 재검토 |
| 지표/평가 | `eval_cases` | DEFER | 서비스 런타임 DB보다 AI 평가/CI fixture 성격이 강하므로 Sprint 2로 미룸 |
| 지표/평가 | `eval_runs` | DEFER | prompt/model 평가 결과 저장은 Sprint 2로 미룸 |

## 기존 제공 테이블 중 판정 변경

| 테이블 | 판정 | 변경된 내용 |
| --- | --- | --- |
| `document_claims` | KEEP, Sprint 1 생성만 | 기존 “Sprint 1 제외”에서 변경. 테이블은 만들지만 row 생성/claim 추출은 Sprint 2 |
| `evidence_conflicts` | KEEP, Sprint 1 사용 | 기존 “빈 테이블”에서 변경. Sprint 1부터 `answer_vs_code` 충돌 row를 생성 |
| `report_disagreements` | KEEP, Sprint 1 생성만 | 테이블은 만들지만 API/row 생성은 Sprint 2 |
| `user_documents` | KEEP | Sprint 1에서 파일 바이너리 없이 metadata, extracted_text, extracted_github_urls, extract_status, truncation 여부만 저장 |
| `user_profile_summaries` | KEEP | report 생성 성공 후 profile summary job으로 갱신 |
| `repo_analyses` | KEEP | `batch_position`을 Sprint 1부터 추가하고, UNIQUE 기준에서 `model`은 제외 |
| `interview_sessions` | KEEP | `preparing_failed` 상태를 추가하고, `answer_mode='text'`를 Sprint 1 고정 |
| `auth_sessions` | DROP | Sprint 1과 Sprint 2 모두 만들지 않음 |

## Sprint 1 최종 생성 테이블

| 그룹 | 테이블 |
| --- | --- |
| 계정 | `users`, `github_accounts` |
| GitHub | `repositories`, `repo_analyses`, `user_profile_summaries` |
| 공고 | `job_postings`, `jd_requirements` |
| 문서 | `user_documents`, `document_claims` |
| 분석 | `analysis_jobs`, `analysis_repo_candidates`, `analysis_repo_candidate_pages`, `repo_match_scores` |
| 면접 | `interview_sessions`, `session_repositories`, `interview_turns` |
| 근거 | `evidences`, `turn_evidences`, `evidence_conflicts` |
| 리포트 | `interview_reports`, `report_scores`, `report_disagreements` |
| 지식 | `score_criteria`, `prompt_versions`, `domain_question_frames` |
| 지표 | `events` |

## Sprint 1에서 만들지 않는 테이블

| 테이블 | 이유 |
| --- | --- |
| `auth_sessions` | Sprint 2에서도 제외 |
| `tool_calls` | Tool 계약과 상세 기록은 Sprint 2 이후 재검토 |
| `topic_taxonomy` | `topic_code` FK 없이 문자열로 운용 |
| `interview_personas` | persona CHECK 값으로 충분 |
| `probe_patterns` | prompt/Director 로직으로 흡수 |
| `report_persona_feedbacks` | `interview_reports.feedback_json`으로 흡수 |
| `feedback_signals` | 범위가 넓고 중복 가능성이 있어 Sprint 2 재검토 |
| `eval_cases` | 평가/CI 영역으로 Sprint 2 재검토 |
| `eval_runs` | 평가/CI 영역으로 Sprint 2 재검토 |
| `answer_analyses` | `interview_turns.analysis JSONB` 유지 |
| `director_decisions` | `interview_turns.decision JSONB` 유지 |
