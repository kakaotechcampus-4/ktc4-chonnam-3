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

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.
