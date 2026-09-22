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
| `answer`의 `turn` | `{ type, turn, text }`. `spec/ai/decisions/0010:30` 반영, BE 합의 2026-09-23. 불일치 시 `answer_stale_turn`(recoverable `true`)으로 거절하며 화면은 초안을 버리고 현재 질문으로 돌아간다 | FIX |
| 명시적 이탈 통지 | `abandoned`는 명시적 이탈과 레포 재선택으로만 설정한다 (`spec/frontend/features/interview.md:90`, `backend/docs/pipeline.md:241-242`). 그런데 FE가 "나가기를 눌렀다"를 서버에 알릴 수단이 계약에 없다 — REST 엔드포인트 없음, WS 클라이언트 메시지는 `answer`뿐 (`frontend/docs/api-spec.md:1152`), close code 규약도 없음. 서버가 끊김과 구분할 수 없어 Sprint 1에서 이탈 모달은 화면만 닫는다. FE 제안은 REST — 이탈 모달은 재연결 중에도 누를 수 있어 소켓이 죽은 상태에서는 close code·WS 메시지가 나가지 못한다. 덧붙여 `frontend/docs/api-spec.md:1140`·`:1604`는 아직 "재연결 실패 시 `abandoned` 확정"으로 적혀 있어 위 결정과 충돌한다 | `PENDING_BE` |

기존 자료는 참고 기록으로 남긴다. 구현자는 이 문서의 FIX/PENDING 상태를 보고 범위를 판단한다.
