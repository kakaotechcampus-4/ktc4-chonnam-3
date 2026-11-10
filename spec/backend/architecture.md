# BE 아키텍처

상태: 현재 코드 기준([공통 0014](../shared/decisions/0014-current-state-docs.md)). 변경 근거는 `spec/backend/decisions/`에 남기며 공통 계약에 영향이 있으면 `spec/shared/decisions/`에서 관리한다. 과거 `report.md`를 현재 기록 위치로 사용하지 않는다.

## 문서 경계

- `spec/backend/*`: 팀 합의가 필요한 백엔드 설계 원본.
- `spec/shared/contracts/openapi.yaml`: FE/BE 공통 API 계약 원본.
- `backend/docs/*`: Claude 구현용 task 체크리스트와 운영 가이드.
- `context/*`: 회의 기록. 구현 기준이 아니다.

## 기술 스택

- API: FastAPI, Pydantic v2.
- DB: PostgreSQL, SQLAlchemy 2.0 async, Alembic.
- Queue/short-lived state: Redis + ARQ.
- LLM: 기본 모델은 OpenAI `gpt-5.6-luna`이며 설정(`LLM_DEFAULT_MODEL`)에서 읽는다. [모델 선택 결정](../ai/decisions/0011-sprint1-model-selection.md)을 따르며 실제 모델 문자열과 prompt version을 DB에 저장하고, 저장소 분석과 면접 중 호출은 시도별 token·latency도 기록한다. 인증·client·호출 경로는 BE가 소유한다.
- 음성: STT는 OpenAI 호환 전사 API(기본 `whisper-large-v3`, [공통 0011](../shared/decisions/0011-stt-provider-mlapi-whisper.md)), TTS는 Google Cloud TTS를 선택적으로 사용한다.

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
| `ai/src/devon_ai/agents/director/` | 단일 Director와 주입된 Evidence 도구 사용 |
| `ai/src/devon_ai/llm_tasks/` | repo shallow/deep, answer analysis, report 등 AI 작업 원본 |
| `backend/app/agents/director/` | 향후 Director 연결과 실제 도구 adapter 경계; 권한·I/O는 BE |
| `backend/app/llm_tasks/` | AI task 연결, DB prompt loader, Wanted 규칙 변환·프로필 확정 집계의 BE 경계 |
| `backend/app/integrations/` | GitHub, Wanted, 문서 추출, LLM client 등 외부 I/O |
| `backend/app/realtime/` | SSE, WebSocket, Redis bus/registry |
| `backend/app/workers/` | ARQ task adapter. 실제 로직은 pipeline/service에 둔다 |

## 서비스 범위

- GitHub OAuth 로그인. GitHub access token은 FE에 노출하지 않고 BE가 암호화 저장한다.
- GitHub OAuth App long-lived access token을 전제로 하며 refresh token/expiry 컬럼은 두지 않는다.
- DEVON 인증은 [공통 0003 결정](../shared/decisions/0003-sprint1-session-auth.md)에 따라 Redis `auth:sess:{sid}`와 `devon_session` 쿠키의 서버 세션을 사용한다. 기존 14일(1,209,600초) sliding TTL을 유지한다.
- REST 요청·SSE 연결·WS handshake는 같은 HttpOnly `devon_session` 쿠키를 사용한다. `Path=/`, `SameSite=Lax`, 운영 환경의 `Secure`를 적용한다. 로그인 세션 식별자와 면접의 realtime `sessionId`는 별개다.
- 로그인 세션이 유실·만료되면 Postgres에서 복구하지 않고 재로그인한다. 로그아웃은 현재 세션 삭제와 쿠키 만료로 처리하며 이미 만료된 경우에도 `204`로 응답한다.
- GitHub token은 DB에 암호화 저장하며 DEVON 로그인 세션과 분리한다. GitHub access token은 로그인 쿠키에 넣지 않는다.
- public GitHub repository만 지원한다. private repository는 지원하지 않고 필드만 둔다.
- Wanted 공고만 지원한다. 다른 공고 사이트와 공고 없는 면접은 차단한다.
- 문서 preview는 포트폴리오·자기소개서 파일에서 텍스트와 GitHub URL을 추출한다. PDF, DOCX, TXT, MD는 직접 추출하고 이미지·PPT는 Vision 공급자가 설정된 경우에만 처리한다. 화면은 포트폴리오 PDF, 자기소개서 PDF·DOCX를 받는다.
- 면접 준비 단계에서 선택한 문서의 Claim을 추출해 `document_claims`에 저장하고, 코드와 대조한 결과를 `document_claim_comparisons`에 저장한다.
- 분석 run은 repo candidate ranking, page 단위 L0-b/L1 분석, repo recommendation을 제공한다.
- 면접은 WebSocket으로 진행하며 새 면접의 답변은 음성이다. 서버가 STT로 전사하고 질문 음성은 TTS로 제공한다. 음성 전환 이전의 텍스트 면접도 계속 진행할 수 있다.
- 첫 질문은 `hr_manager`가 긴장 완화 목적으로 한다. 2턴부터 Director가 persona를 선택한다.
- 기본 면접은 9턴이다. Director가 조기 종료하지 않으며, 명시적 이탈·재연결은 [0010](../ai/decisions/0010-sprint1-interface-runtime-decisions.md) 정책을 따른다.
- 리포트는 lazy generation이다. 리포트 생성 후 profile summary 갱신 job을 후속 enqueue한다.
- 이벤트는 10종을 기록한다.
- 피드백 이의 제기는 `report_disagreements`에 저장하고, 명시 재평가 결과는 `report_revisions`에 보존한다.
- `topic_taxonomy`, `interview_personas`, `probe_patterns`, `report_persona_feedbacks`, `feedback_signals`, `eval_cases`, `eval_runs`, `answer_analyses`, `director_decisions`, `auth_sessions`는 DB에 만들지 않는다.

## 미지원·향후 과제

- DEVON JWT와 refresh token은 사용하지 않는다. 도입하면 저장 구조·회전·재사용 탐지와 세션에서의 전환을 함께 검토한다.
- profile summary는 완료 면접의 누적 repo 기반으로 고도화한다.
- domain question frame은 팀 검수 후 seed/prompt version으로 수정 가능하게 유지한다.

## 후속 검토와 반영 확인

| 항목 | 상태 | 이유 |
| --- | --- | --- |
| 포트폴리오 unmatched GitHub URL 노출 | 현재 개수 안내 유지 | [기존 화면 명세](../frontend/features/analysis.md#포트폴리오-매칭-안내)에 따라 언급·매칭 개수만 안내. 상세 URL 공개는 현재 범위에 추가하지 않음 |
| `pgvector` extension | 미도입 | [0002](../ai/decisions/0002-sprint1-vector-search.md)에 따라 도입하지 않았고 migration에도 extension이 없음. 도입 여부는 필요할 때 검토 |
