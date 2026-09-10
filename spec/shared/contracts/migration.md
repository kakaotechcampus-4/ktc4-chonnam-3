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
| WS 식별자 | `interviewId` 통일 vs 별도 `sessionId` | `PENDING_FE` |
| `questionEnd` | 텍스트 WS에서 유지 여부 | `PENDING_FE` |
| 이탈/복구 | disconnect, heartbeat, abandoned 자동 판정 | `PENDING_FE` |
| DEVON JWT 전달 | HttpOnly cookie only vs body 포함 | `PENDING_FE` |
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
| Report score | 산정 근거와 저장 스케일 | `PENDING_TEAM` |
| pgvector | 실제 vector 검색 필요 여부 | `PENDING_AI` |

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.
