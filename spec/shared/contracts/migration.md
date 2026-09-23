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
| Sprint 1 로그인 인증 | 기존 Redis 서버 세션 + HttpOnly `devon_session`, 14일 sliding; REST/SSE/WS 공통. [공통 0003](../decisions/0003-sprint1-session-auth.md) | FIX — 구현·검증 대기 |
| JWT·갱신 토큰 | `/auth/refresh`를 Sprint 1에서 제외하고 Sprint 2로 이관. 상세 저장·전환 설계는 착수 시 검토 | 후속 |
| Partial run 매핑 | DB `partial` -> FE `failed`, result 조회 가능 | FIX |
| Persona enum | `tech_lead`, `hr_manager`, `domain_lead` | FIX |
| Analysis StepKey | 7개 step 유지 | FIX |
| Document claims | Sprint 1 테이블 생성, row 생성/claim 추출은 Sprint 2 | FIX |
| Evidence conflict | Sprint 1 `answer_vs_code`, Sprint 2 doc claims 확장 | FIX |
| Report persona feedback | `interview_reports.feedback_json`으로 흡수 | FIX |
| Report disagreement | Sprint 1 테이블 생성, API/row 생성은 Sprint 2 | FIX |
| Knowledge seed tables | `score_criteria`, `prompt_versions`, `domain_question_frames`만 유지 | FIX |
| Eval/feedback tables | `feedback_signals`, `eval_cases`, `eval_runs` Sprint 1 제외 | FIX |
| SQL `auth_sessions` | 기존 DB 테이블 제외 유지. Sprint 1의 Redis 로그인 세션과 구분하며 Sprint 2 JWT 저장 설계는 후속 검토 | FIX — 현행 DB 범위 |
| Wanted-only JD | Sprint 1 Wanted만 지원 | FIX |
| Private repo | 지원하지 않음. 필드만 유지 | FIX |
| Report score | 0~100 score 6개와 단순 평균 `totalScore`; 세부 기준 seed는 보강 가능 | FIX |
| pgvector | 실제 vector 검색 필요 여부 | `PENDING_AI` |
| `answer`의 `turn` | `{ type, turn, text }`. `spec/ai/decisions/0010:30` 반영, BE 합의 2026-09-23. 불일치 시 `answer_stale_turn`(recoverable `true`)으로 거절하며 화면은 초안을 버리고 현재 질문으로 돌아간다 | FIX |
| 명시적 이탈 통지 | `abandoned`는 명시적 이탈과 레포 재선택으로만 설정한다 (`spec/frontend/features/interview.md:90`, `backend/docs/pipeline.md:241-242`). 그런데 FE가 "나가기를 눌렀다"를 서버에 알릴 수단이 계약에 없다 — REST 엔드포인트 없음, WS 클라이언트 메시지는 `answer`뿐 (`frontend/docs/api-spec.md:1152`), close code 규약도 없음. 서버가 끊김과 구분할 수 없어 Sprint 1에서 이탈 모달은 화면만 닫는다. FE 제안은 REST — 이탈 모달은 재연결 중에도 누를 수 있어 소켓이 죽은 상태에서는 close code·WS 메시지가 나가지 못한다. 덧붙여 `frontend/docs/api-spec.md:1140`·`:1604`는 아직 "재연결 실패 시 `abandoned` 확정"으로 적혀 있어 위 결정과 충돌한다 | `PENDING_BE` |
| 준비 재시도 경로 | REST `POST /interviews/{id}/prepare/retry`. `spec/ai/decisions/0010:32` 반영, BE 합의 2026-09-23. 거절 reason `prep_in_progress`(409)·`session_expired`(410) 신설 | FIX |
| 수동 재시도 상한 | 사용자가 `다시 시도`를 누를 수 있는 횟수의 상한이 없다. `analysis_jobs.retry_count`는 지표이고 차단 규칙이 아니다 (`spec/ai/decisions/0010:72`, `backend/docs/pipeline.md:13`). LLM 호출 상한(최초 1 + 자동 1)만 있어 수동 N회는 최대 2×(N+1)회 호출이 된다 (`spec/ai/contracts.md:141`) | `PENDING_BE` |
| 준비 실패 대기 시간 | `github_api_rate_limited`의 화면 처리는 "대기 후 재시도"인데 (`spec/frontend/features/interview.md:200`) 대기 시간을 담을 필드가 없다. WS `error`(`frontend/docs/api-spec.md:1183`)와 `InterviewLastError`(`openapi.yaml:866`)는 `openapi.yaml:870-871`에 따라 같은 모양을 유지해야 해 한쪽만 고칠 수 없다 | `PENDING_TEAM` |
| pgvector | [0002](../../ai/decisions/0002-sprint1-vector-search.md)에 따라 Sprint 1 미도입·선설치 없음; Sprint 2 도입 여부는 후속 검토 | AI 방향 확정, BE migration 반영 검증 대기 |

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.

## PR #15 JD 분류 정합화

API `JdCategory`와 DB·AI `requirement_type`은 서로 다른 의미이므로 기존 enum을 각각 유지한다. 이번 수정은 두 enum의 변환과 원문 출처 보존을 [분석 Run](../../backend/features/analysis-run.md#wanted-공고-수집분류)에 명시하고 추출 초안에 반영한다. 공개 API 값이나 DB enum을 변경하지 않는다.
