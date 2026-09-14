# 작업 04 — API 타입 정의

> 선행: `docs/api-spec.md` 확정 (토요일 회의 후)
> 산출물: `src/types/api.ts`

## 목표

명세의 요청·응답 구조를 TypeScript 타입으로 옮긴다. **이 파일이 FE·BE 계약서 역할을 한다.**

## 규칙

- 필드명은 명세 그대로 **camelCase**
- 명세에 없는 필드를 임의로 추가하지 않는다
- null 가능 필드는 반드시 `| null` 표기
- **배열은 `| null` 을 붙이지 않는다** (빈 배열 규약 — 값이 없으면 `[]`)
- enum은 union 타입으로 정의
- 파일 확장자는 `.ts` (JSX 없음)

## 1. enum 타입

```ts
export type AnalysisStatus = 'no_repository' | 'no_interview' | 'completed';
export type InterviewStatus = 'in_progress' | 'completed' | 'abandoned';
export type RunStatus = 'running' | 'completed' | 'failed';
export type StepKey = 'fetch_repos' | 'extract_jd' | 'match_score' | 'prepare_result';
export type PrepareStepKey =
  | 'analyze_repo'
  | 'build_persona'
  | 'compose_question'
  | 'set_criteria';
export type StepStatus = 'pending' | 'running' | 'completed';
export type AgentRole = 'tech_lead' | 'senior_developer' | 'manager';
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
export type ApiError = {
  error: {
    reason: string;
    message: string;
    retryAfter?: number;
  };
};
```

`reason`은 종류가 많고 늘어날 수 있으므로 union으로 고정하지 않는다. 프론트는 특정 값만 분기하고 나머지는 `message`를 그대로 노출한다.

## 3. 작성할 타입 목록

`docs/api-spec.md`의 응답 예시를 기준으로 아래를 정의한다.

| 엔드포인트 | 타입명 |
| --- | --- |
| `GET /me` | `MeResponse` |
| `GET /me/home` | `HomeResponse` · `AnalysisPanel` · `LanguageRatio` · `RecentInterview` |
| `GET /me/interviews` | `InterviewListResponse` · `InterviewSummary` |
| `POST /analysis-runs` | `CreateAnalysisRunRequest`(FormData) · `CreateAnalysisRunResponse` |
| `GET /analysis-runs/{runId}` | `AnalysisRunResponse` · `AnalysisStep` |
| `GET /analysis-runs/{runId}/events` | `SseStepEvent` · `SseCompletedEvent` · `SseFailedEvent` |
| `GET /analysis-runs/{runId}/result` | `AnalysisResultResponse` · `RepositoryItem` |
| `POST /interviews` | `CreateInterviewRequest` · `CreateInterviewResponse` |
| `GET /interviews/{id}` | `InterviewDetailResponse` · `InterviewTurn` |
| WS 메시지 | `WsClientMessage` · `WsServerMessage` (아래 4번 참조) |
| `GET /interviews/{id}/report` | `ReportResponse` · `ScoreItem` · `AgentFeedback` |
| `POST /interviews/{id}/retry` | `CreateInterviewResponse` 재사용 |
| `POST /reports/{id}/feedback-disagreements` | `FeedbackDisagreementRequest` |

리다이렉트 엔드포인트(`/auth/github/*`)는 응답 body가 없으므로 타입이 없다.

## 4. WebSocket 메시지 타입

`type` 필드로 판별하는 union으로 정의한다.

```ts
export type WsClientMessage =
  | { type: 'answerStart' }
  | { type: 'answerEnd' };

export type WsServerMessage =
  | { type: 'prepareStep'; key: PrepareStepKey; status: StepStatus }
  | { type: 'prepareCompleted' }
  | { type: 'transcript'; text: string }
  | { type: 'thinking' }
  | { type: 'evidenceCheck'; repository: string; file: string }
  | { type: 'question'; role: AgentRole; text: string; turn: number }
  | { type: 'questionEnd' }
  | { type: 'interviewEnd' }
  | { type: 'error'; reason: string };
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