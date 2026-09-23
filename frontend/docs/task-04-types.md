# 작업 04 — API 타입 정의

> 기준: [공통 계약의 원본·예외 범위](../../spec/shared/contracts/README.md), [이관·보류 현황](../../spec/shared/contracts/migration.md)
> 산출물: `src/types/api.ts`

## 목표

일반 HTTP API는 `spec/shared/contracts/openapi.yaml`, WebSocket·SSE·브라우저 이동 경로는 `docs/api-spec.md`를 기준으로 요청·응답 구조를 TypeScript 타입으로 옮긴다. `src/types/api.ts`는 계약을 사용하는 FE 타입이며 별도의 계약 원본이 아니다. 아래 예시는 구현 기준이며 현재 코드의 일치·완료를 보증하지 않는다.

## 규칙

- 필드명은 명세 그대로 **camelCase**
- 명세에 없는 필드를 임의로 추가하지 않는다
- null 가능 필드는 반드시 `| null` 표기
- **배열은 `| null` 을 붙이지 않는다** (빈 배열 규약 — 값이 없으면 `[]`)
- enum은 union 타입으로 정의
- 파일 확장자는 `.ts` (JSX 없음)

## 1. enum 타입

```ts
export type AnalysisStatus = 'syncing' | 'no_repository' | 'no_interview' | 'completed';
export type InterviewStatus =
  | 'preparing'
  | 'preparing_failed'
  | 'in_progress'
  | 'completed'
  | 'abandoned';
export type RunStatus = 'running' | 'completed' | 'failed';
export type StepKey =
  | 'doc_extract'
  | 'repo_select'
  | 'repo_detail'
  | 'jd_fetch'
  | 'jd_extract'
  | 'repo_analyze'
  | 'match_score';
export type PrepareStepKey =
  | 'analyze_repo'
  | 'build_persona'
  | 'set_criteria'
  | 'compose_question';
export type StepStatus = 'pending' | 'running' | 'completed' | 'failed' | 'skipped';
export type Persona = 'tech_lead' | 'hr_manager' | 'domain_lead';
export type ScoreKey =
  | 'project_understanding'
  | 'technical_reasoning'
  | 'problem_solving'
  | 'communication'
  | 'contribution_clarity'
  | 'company_job_fit';
export type ReasonType =
  | 'factual_error'
  | 'insufficient_basis'
  | 'overly_harsh'
  | 'unclear_intent'
  | 'other';
```

## 2. 공통 에러 타입

```ts
export type ApiErrorBody = {
  error: {
    reason: string;
    message: string;
    retryAfter?: number;
    details?: Record<string, unknown>;
  };
};

// HTTP 상태코드는 클라이언트에서 덧붙이며 응답 본문에는 없다.
export type ApiError = ApiErrorBody & { status: number };
```

`reason`은 종류가 많고 늘어날 수 있으므로 union으로 고정하지 않는다. 프론트는 특정 값만 분기하고 나머지는 `message`를 그대로 노출한다.

## 3. 작성할 타입 목록

위 원본 구분에 따라 아래 타입을 정의한다. 일반 HTTP API는 예시 JSON만 복사하지 않고 OpenAPI의 required·nullable·enum을 대조한다.

| 엔드포인트 | 타입명 |
| --- | --- |
| `GET /me` | `MeResponse` |
| `GET /me/home` | `HomeResponse` · `AnalysisPanel` · `LanguageRatio` · `RecentInterview` |
| `GET /me/interviews` | `InterviewListResponse` · `InterviewSummary` |
| `POST /documents/preview` | `DocumentPreviewResponse` |
| `POST /analysis-runs` | `CreateAnalysisRunRequest` · `CreateAnalysisRunResponse` |
| `GET /analysis-runs/{runId}` | `AnalysisRunResponse` · `AnalysisStep` |
| `GET /analysis-runs/{runId}/events` | `SseStepEvent` · `SseCompletedEvent` · `SseFailedEvent` |
| `GET /analysis-runs/{runId}/result` | `AnalysisResultResponse` · `RepositoryItem` |
| `POST /interviews` | `CreateInterviewRequest` · `CreateInterviewResponse` |
| `GET /interviews/{id}` | `InterviewDetailResponse` · `InterviewTurn` |
| WS 메시지 | `WsClientMessage` · `WsServerMessage` (아래 4번 참조) |
| `GET /interviews/{id}/report` | `ReportResponse` · `ScoreItem` · `AgentFeedback` |
| `POST /interviews/{id}/retry` | `CreateInterviewResponse` 재사용 |
| `POST /interviews/{id}/feedback-disagreements` | `FeedbackDisagreementRequest` — 잔존 계약상 경로. Sprint 1 제공·호출 제외 |

리다이렉트 엔드포인트(`/auth/github/*`)는 응답 body가 없으므로 타입이 없다.

이의 제기는 OpenAPI에 경로가 남아 있지만 `migration.md`의 기존 결정대로 Sprint 2 범위다. 이 문서가 Sprint 1 호출 구현을 승인하는 것은 아니며, [report의 계약 차이](../../spec/frontend/features/report.md#계약-차이와-구현-범위)를 먼저 확인한다.

## 4. WebSocket 메시지 타입

`type` 필드로 판별하는 union으로 정의한다.

[0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 Sprint 1은 `answer`에 `turn`·`text`를 전달한다. `prepareRetry`는 WS 메시지가 아니며 준비 재시도는 REST로 호출한다. 아래 타입과 다른 로컬 WS 타입은 화면 연결 시 수정·검증할 대상이다.

```ts
export type WsClientMessage =
  | { type: 'answer'; turn: number; text: string };

export type WsServerMessage =
  | { type: 'prepareStep'; key: PrepareStepKey; status: StepStatus }
  | { type: 'prepareCompleted' }
  | { type: 'answerReceived' }
  | { type: 'thinking' }
  | { type: 'evidenceCheck'; repository: string; file: string }
  | { type: 'question'; persona: Persona; text: string; turn: number }
  | { type: 'interviewEnd' }
  | { type: 'error'; reason: string; recoverable: boolean; code: string; step: PrepareStepKey | null; occurredAt: string };
```

이렇게 정의하면 `switch (msg.type)` 에서 각 분기의 필드가 자동으로 좁혀진다.

## 5. 진행 방식

**한 번에 3~4개 타입씩 만들고 확인받는다.** 18개를 한꺼번에 생성하지 않는다.

명세의 예시 JSON과 필드를 1:1 대조하며 작성한다.

## 완료 조건

- [ ] 위 목록의 모든 타입이 정의됨
- [ ] 명세와 필드명이 1:1 일치
- [ ] null 가능 필드가 모두 `| null` 표기됨
- [ ] 배열 필드에 `| null` 이 없음
- [ ] `npm run build` 통과

## 커밋

```
feat: add api types
```
