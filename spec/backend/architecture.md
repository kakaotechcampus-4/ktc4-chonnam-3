# BE 아키텍처

상태: Sprint 1 FIX 기준. 변경하려면 관련 `spec/backend/decisions/` 또는 `report.md`에 근거를 남긴다.

## 문서 경계

- `spec/backend/*`: 팀 합의가 필요한 백엔드 설계 원본.
- `spec/shared/contracts/openapi.yaml`: FE/BE 공통 API 계약 원본.
- `backend/docs/*`: Claude 구현용 task 체크리스트와 운영 가이드.
- `context/*`: 회의 기록. 구현 기준이 아니다.

## 기술 스택

- API: FastAPI, Pydantic v2.
- DB: PostgreSQL, SQLAlchemy 2.0 async, Alembic.
- Queue/short-lived state: Redis + ARQ.
- LLM: Sprint 1은 모든 LLM 작업을 `5.5 Luna`로 고정한다. 실제 모델 문자열, prompt version, token, latency는 DB에 저장한다.

## 레이어

호출 방향은 한 방향이다.

AI 코드 배치는 사용자가 승인한 [AI 패키지 설계](../ai/designs/2026-09-12-ai-package-structure.md)를 따른다. `ai/src/devon_ai/`가 AI 구현 원본이며 기존 backend 파일은 연결 경계로 유지한다. 별도 서비스·API·DB 계약 변경은 아니다.

```text
router -> service -> {queries | agents | llm_tasks | integrations | realtime}
workers -> features/*/pipeline -> service/queries/llm_tasks/integrations
backend AI 연결 -> devon_ai (역방향 import 금지)
```

| 경로 | 책임 |
| --- | --- |
| `backend/app/features/*/router.py` | 요청 검증, dependency, 응답 직렬화 |
| `backend/app/features/*/service.py` | 비즈니스 로직과 트랜잭션 경계. commit 책임 |
| `backend/app/features/*/queries.py` | DB 읽기/쓰기 쿼리. GitHub repository와 혼동되므로 `repository.py` 금지 |
| `ai/src/devon_ai/agents/director/` | 단일 Director와 주입된 Evidence 도구 사용; 현재 골격 |
| `ai/src/devon_ai/llm_tasks/` | repo shallow/deep, answer analysis, report의 AI 원본; 현재 골격 |
| `backend/app/agents/director/` | 향후 Director 연결과 실제 도구 adapter 경계; 권한·I/O는 BE |
| `backend/app/llm_tasks/` | AI task 연결, DB prompt loader, Wanted 규칙 변환·프로필 확정 집계의 BE 경계 |
| `backend/app/integrations/` | GitHub, Wanted, 문서 추출, LLM client 등 외부 I/O |
| `backend/app/realtime/` | SSE, WebSocket, Redis bus/registry |
| `backend/app/workers/` | ARQ task adapter. 실제 로직은 pipeline/service에 둔다 |

## Sprint 1 범위

- GitHub OAuth 로그인. GitHub access token은 FE에 노출하지 않고 BE가 암호화 저장한다.
- GitHub OAuth App long-lived access token을 전제로 하며 refresh token/expiry 컬럼은 두지 않는다.
- DEVON 자체 JWT는 BE API 인증에 사용한다. 전달 방식은 `PENDING_FE`.
- DEVON JWT는 GitHub token과 분리한다. JWT payload에는 GitHub access token을 넣지 않고, `github_accounts` token field도 JWT 발급용으로 읽지 않는다.
- public GitHub repository만 지원한다. private repository는 Sprint 2에서도 지원하지 않고 필드만 둔다.
- Wanted 공고만 지원한다. 다른 공고 사이트와 공고 없는 면접은 차단한다.
- 문서 preview는 PDF, DOCX, TXT, MD 텍스트 추출과 GitHub URL 추출만 수행한다.
- `document_claims` 테이블은 만들되 자소서/포트폴리오 claim 추출과 row 생성은 하지 않는다.
- 분석 run은 repo candidate ranking, page 단위 L0-b/L1 분석, repo recommendation을 제공한다.
- 면접은 텍스트 WebSocket이다. 음성, STT, TTS는 Sprint 2.
- 첫 질문은 `hr_manager`가 긴장 완화 목적으로 한다. 2턴부터 Director가 persona를 선택한다.
- 기본 면접은 9턴이다. Sprint 1에서는 조기 종료하지 않는다.
- 리포트는 lazy generation이다. 리포트 생성 후 profile summary 갱신 job을 후속 enqueue한다.
- 이벤트는 최소 10종만 기록한다.
- `report_disagreements` 테이블은 만들되 API/row 생성은 Sprint 2로 넘긴다.
- `topic_taxonomy`, `interview_personas`, `probe_patterns`, `report_persona_feedbacks`, `feedback_signals`, `eval_cases`, `eval_runs`, `answer_analyses`, `director_decisions`, `auth_sessions`는 Sprint 1 DB에서 제외한다.
- `auth_sessions`는 Sprint 2에서도 제외한다.

## Sprint 2 방향

- 음성 입력, STT, TTS, `questionEnd` 포함 여부는 FE 결정 후 확장한다.
- 자소서/포트폴리오 claim 추출과 문서-코드 conflict를 추가한다.
- `report_disagreements` API와 row 생성을 추가한다.
- profile summary는 완료 면접의 누적 repo 기반으로 고도화한다.
- domain question frame은 팀 검수 후 seed/prompt version으로 수정 가능하게 유지한다.
- Director 조기 종료와 이탈/복구 정책은 FE와 합의 후 추가한다.

## 보류 항목

| 항목 | 상태 | 이유 |
| --- | --- | --- |
| WS 식별자 `interviewId` vs `sessionId` | `PENDING_FE` | FE 라우팅, 새로고침 복구, 상태머신 결정 필요 |
| 텍스트 WS에서 `questionEnd` 유지 여부 | `PENDING_FE` | Sprint 2 음성 스트리밍과 연결됨 |
| 이탈/복구/자동 `abandoned` 판정 | `PENDING_FE` | FE UX와 하트비트 정책 결정 필요 |
| DEVON JWT 전달 방식 | `PENDING_FE` | HttpOnly cookie only vs body 포함 |
| 포트폴리오 unmatched GitHub URL 노출 | `PENDING_FE` | 개인정보/UX 결정 필요 |
| 리포트 점수 스케일과 산정 근거 | `PENDING_TEAM` | 팀원이 자료 보충 후 확정 |
| `pgvector` extension | `PENDING_AI` | embedding/vector 검색 실제 필요 여부 확인 필요 |
