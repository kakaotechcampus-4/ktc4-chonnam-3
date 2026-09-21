# 계약 이관 현황

작성일: 2026-09-10
갱신일: 2026-09-15

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
| Auth API | login, callback, refresh, logout, `/me`만 현재 범위 | FIX |
| DEVON JWT 전달 | `accessToken`, `refreshToken` HttpOnly cookie only; WS는 `accessToken` cookie handshake | FIX |
| OAuth state | Redis 10분 single-use + `oauthState` cookie + S256 PKCE | FIX |
| Refresh 상태 | PostgreSQL `users.refresh_generation` + `auth_sessions`; Redis 이중 기록/fallback 없음 | FIX |
| 초기 GitHub 동기화·재연동 | 로그인 callback에서 enqueue하지 않음; link API는 후속 | FIX |
| Partial run 매핑 | DB `partial` -> FE `failed`, result 조회 가능 | FIX |
| Persona enum | `tech_lead`, `hr_manager`, `domain_lead` | FIX |
| Analysis StepKey | 7개 step 유지 | FIX |
| Document claims | Sprint 1 테이블 생성, row 생성/claim 추출은 Sprint 2 | FIX |
| Evidence conflict | Sprint 1 `answer_vs_code`, Sprint 2 doc claims 확장 | FIX |
| Report persona feedback | `interview_reports.feedback_json`으로 흡수 | FIX |
| Report disagreement | Sprint 1 테이블 생성, API/row 생성은 Sprint 2 | FIX |
| Knowledge seed tables | `score_criteria`, `prompt_versions`, `domain_question_frames`만 유지 | FIX |
| Eval/feedback tables | `feedback_signals`, `eval_cases`, `eval_runs` Sprint 1 제외 | FIX |
| Auth sessions | Sprint 1 인증에 포함; migration `0002`로 추가, 만료 session 정기 삭제 | FIX |
| Wanted-only JD | Sprint 1 Wanted만 지원 | FIX |
| Private repo | 지원하지 않음. 필드만 유지 | FIX |
| Report score | 0~100 score 6개와 단순 평균 `totalScore`; 세부 기준 seed는 보강 가능 | FIX |
| pgvector | 실제 vector 검색 필요 여부 | `PENDING_AI` |

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.

## PR #15 JD 분류 정합화

API `JdCategory`와 DB·AI `requirement_type`은 서로 다른 의미이므로 기존 enum을 각각 유지한다. 이번 수정은 두 enum의 변환과 원문 출처 보존을 [분석 Run](../../backend/features/analysis-run.md#wanted-공고-수집분류)에 명시하고 추출 초안에 반영한다. 공개 API 값이나 DB enum을 변경하지 않는다.
