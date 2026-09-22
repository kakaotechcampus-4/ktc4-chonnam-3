# 계약 이관 현황

작성일: 2026-09-10

이 문서는 기존 FE 문서, backend docs, context 기록에서 Sprint 1 FIX 계약으로 옮긴 항목과 보류 항목을 추적한다.

| 항목 | 결정 | 상태 |
| --- | --- | --- |
| 계약 원본 | `spec/shared/contracts/openapi.yaml` | FIX |
| API field casing | API camelCase, Python/DB snake_case | FIX |
| Error envelope | `{ error: { reason, message, details } }` | FIX |
| Sprint 1 면접 입력 | 텍스트-only | FIX |
| Sprint 2 면접 입력 | 음성/STT/TTS 확장 | FIX |
| WS 식별자 | REST/route는 `interviewId`, WS는 `/api/ws/interviews/{sessionId}` | FIX |
| `questionEnd` | Sprint 1 텍스트 WS에서 제거, `question`이 전달 완료를 의미 | FIX |
| 이탈/복구 | Sprint 1은 명시적 이탈·레포 재선택만 `abandoned`; 자동 heartbeat 판정은 Sprint 2 | FIX |
| DEVON JWT 전달 | HttpOnly `accessToken` cookie handshake | FIX |
| Partial run 매핑 | DB `partial` -> FE `failed`, result 조회 가능 | FIX |
| Persona enum | `tech_lead`, `hr_manager`, `domain_lead` | FIX |
| Analysis StepKey | 7개 step 유지 | FIX |
| Document claims | Sprint 1 테이블 생성, row 생성/claim 추출은 Sprint 2 | FIX |
| Evidence conflict | Sprint 1 `answer_vs_code`, Sprint 2 doc claims 확장 | FIX |
| Report persona feedback | `interview_reports.feedback_json`으로 흡수 | FIX |
| Report disagreement | Sprint 1 테이블 생성, API/row 생성은 Sprint 2 | FIX |
| Knowledge seed tables | `score_criteria`, `prompt_versions`, `domain_question_frames`만 유지 | FIX |
| Eval/feedback tables | `feedback_signals`, `eval_cases`, `eval_runs` Sprint 1 제외 | FIX |
| Auth sessions | Sprint 1, Sprint 2 모두 제외 | FIX |
| Wanted-only JD | Sprint 1 Wanted만 지원 | FIX |
| Private repo | 지원하지 않음. 필드만 유지 | FIX |
| Report score | 0~100 score 6개와 단순 평균 `totalScore`; 세부 기준 seed는 보강 가능 | FIX |
| pgvector | 실제 vector 검색 필요 여부 | `PENDING_AI` |
| 준비 재시도 경로 | WS `prepareRetry`(`frontend/docs/api-spec.md:1142`, WS 계약 원본) vs REST `POST /interviews/{id}/prepare/retry`(`spec/ai/decisions/0010:32` Accepted, FE/BE features) | `PENDING_BE` — FE 제안: `spec/frontend/designs/2026-09-22-prepare-retry-transport.md` |
| 수동 재시도 상한 | 사용자가 `다시 시도`를 누를 수 있는 횟수의 상한이 없다. `analysis_jobs.retry_count`는 지표이고 차단 규칙이 아니다 (`spec/ai/decisions/0010:72`, `backend/docs/pipeline.md:13`). LLM 호출 상한(최초 1 + 자동 1)만 있어 수동 N회는 최대 2×(N+1)회 호출이 된다 (`spec/ai/contracts.md:141`) | `PENDING_BE` |
| 준비 실패 대기 시간 | `github_api_rate_limited`의 화면 처리는 "대기 후 재시도"인데 (`spec/frontend/features/interview.md:200`) 대기 시간을 담을 필드가 없다. WS `error`(`frontend/docs/api-spec.md:1183`)와 `InterviewLastError`(`openapi.yaml:866`)는 `openapi.yaml:870-871`에 따라 같은 모양을 유지해야 해 한쪽만 고칠 수 없다 | `PENDING_TEAM` |

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.
