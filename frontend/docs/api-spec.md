# DEVON API 명세

> 최종 수정: 2026-09-07
> 필드: camelCase · URL: kebab-case · 에러 reason·enum: snake_case

## 공통 규약

| 항목 | 규칙 |
| --- | --- |
| 필드 네이밍 | camelCase |
| 배열 빈 값 | `[]` — null 금지 |
| 객체 빈 값 | `null` 허용 (명시된 필드만) |
| 날짜 | ISO 8601 문자열 |
| 필드 생략 | 금지 |
| 인증 | 모든 요청에 `credentials: 'include'` (HttpOnly 쿠키) |

### enum

```
analysisStatus:   no_repository | no_interview | completed
interviewStatus:  in_progress | completed | abandoned
runStatus:        running | completed | failed
stepKey:          fetch_repos | extract_jd | match_score | prepare_result
prepareStepKey:   analyze_repo | build_persona | compose_question | set_criteria
stepStatus:       pending | running | completed
agentRole:        tech_lead | senior_developer | manager
scoreKey:         project_understanding | technical_reasoning | problem_solving
                  | communication | contribution_clarity | company_job_fit
reasonType:       factual_error | insufficient_basis | overly_harsh
                  | unclear_intent | other
```

### 에러 응답 (모든 4xx·5xx 공통)

```json
{
  "error": {
    "reason": "github_token_expired",
    "message": "GitHub 연동 권한이 만료되었어요.",
    "retryAfter": 30
  }
}
```

`reason`은 종류가 많으므로 union으로 고정하지 않고 `string`으로 둔다.
`retryAfter`는 optional.

---

## 엔드포인트 목록

| 메서드 | 경로 | 구현 방식 |
| --- | --- | --- |
| GET | `/auth/github/login` | 브라우저 이동 |
| GET | `/auth/github/callback` | 프론트 무관 |
| POST | `/auth/logout` | fetch |
| GET | `/me` | fetch |
| GET | `/auth/github/link` | 브라우저 이동 |
| GET | `/auth/github/link/callback` | 프론트 무관 |
| GET | `/me/home` | fetch |
| GET | `/me/interviews` | fetch |
| POST | `/analysis-runs` | fetch (multipart) |
| GET | `/analysis-runs/{runId}/events` | EventSource |
| GET | `/analysis-runs/{runId}` | fetch |
| GET | `/analysis-runs/{runId}/result` | fetch |
| POST | `/interviews` | fetch |
| GET | `/interviews/{id}` | fetch |
| GET *(Upgrade)* | `/ws/interviews/{sessionId}` | WebSocket |
| GET | `/interviews/{id}/report` | fetch |
| POST | `/interviews/{id}/retry` | fetch |
| POST | `/reports/{id}/feedback-disagreements` | fetch |

> 브라우저 이동 경로는 `shared/api.ts`에 넣지 않는다. `<a href>` 또는 `window.location`으로 처리한다.

---

## GET /me

Response `200 OK`
```json
{
  "name": "김개발",
  "githubLinked": true
}
```

Response `401` — `unauthenticated`

---

## POST /auth/logout

Request — 없음
Response `204 No Content`

---

## GET /me/home

Response `200 OK`
```json
{
  "name": "김개발",
  "githubLinked": true,
  "repositoryCount": 5,
  "analysisStatus": "completed",
  "analysis": {
    "basedOnRepoCount": 2,
    "languages": [
      { "name": "TypeScript", "ratio": 42 },
      { "name": "Java", "ratio": 31 }
    ],
    "projectTypes": ["백엔드 API 서버", "결제·트랜잭션"],
    "roleSummary": "2개 레포의 README와 커밋 이력을 종합하면 백엔드 API 설계와 DB·캐시 최적화를 가장 자주 맡았습니다."
  },
  "recentInterviews": [
    {
      "id": "iv_001",
      "position": "Backend Developer",
      "totalScore": 81,
      "completedAt": "2026-09-01T15:20:00Z"
    }
  ]
}
```

`analysisStatus`가 `no_repository` 또는 `no_interview`면 `analysis`는 `null`, `recentInterviews`는 `[]`.

| 필드 | 타입 | null |
| --- | --- | --- |
| `name` | string | ❌ |
| `githubLinked` | boolean | ❌ |
| `repositoryCount` | number | ❌ |
| `analysisStatus` | AnalysisStatus | ❌ |
| `analysis` | AnalysisPanel | ✅ |
| `analysis.basedOnRepoCount` | number | ❌ |
| `analysis.languages[].name` | string | ❌ |
| `analysis.languages[].ratio` | number | ❌ |
| `analysis.projectTypes` | string[] | ❌ |
| `analysis.roleSummary` | string | ❌ |
| `recentInterviews[].id` | string | ❌ |
| `recentInterviews[].position` | string | ❌ |
| `recentInterviews[].totalScore` | number | ✅ |
| `recentInterviews[].completedAt` | string | ✅ |

Response `403` — `github_token_expired`

---

## GET /me/interviews

Request (Query)
```
?page=1&size=20
```

Response `200 OK`
```json
{
  "interviews": [
    {
      "id": "iv_001",
      "position": "Backend Developer",
      "repositoryNames": ["project-a", "payment-service"],
      "status": "completed",
      "totalScore": 81,
      "startedAt": "2026-09-01T15:00:00Z",
      "completedAt": "2026-09-01T15:20:00Z"
    }
  ],
  "total": 12,
  "page": 1,
  "size": 20
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `interviews[].id` | string | ❌ |
| `interviews[].position` | string | ❌ |
| `interviews[].repositoryNames` | string[] | ❌ |
| `interviews[].status` | InterviewStatus | ❌ |
| `interviews[].totalScore` | number | ✅ |
| `interviews[].startedAt` | string | ❌ |
| `interviews[].completedAt` | string | ✅ |
| `total` `page` `size` | number | ❌ |

기록 0건이면 `interviews: []`, `total: 0`.

---

## POST /analysis-runs

Request `multipart/form-data`

| 필드 | 타입 | 필수 |
| --- | --- | --- |
| `jobUrl` | text | ✅ |
| `coverLetter` | file (.pdf/.docx) | ❌ |
| `portfolioFile` | file | ❌ |
| `portfolioUrl` | text | ❌ |

> `Content-Type` 헤더를 직접 지정하지 않는다. 브라우저가 boundary와 함께 자동 생성해야 한다.

Response `202 Accepted`
```
Location: /analysis-runs/run_abc123
```
```json
{ "runId": "run_abc123" }
```

Response 실패

| 코드 | reason |
| --- | --- |
| 400 | `job_url_required` · `jd_parse_failed` |
| 409 | `run_in_progress` (응답에 `runId` 포함) |
| 413 | `file_too_large` |
| 415 | `unsupported_media_type` |

---

## GET /analysis-runs/{runId}/events

SSE · `text/event-stream`

```
data: {"type":"step","key":"match_score","status":"completed"}

data: {"type":"completed"}

data: {"type":"failed","reason":"github_token_expired"}
```

| type | 필드 |
| --- | --- |
| `step` | `key` (StepKey), `status` (StepStatus) |
| `completed` | — |
| `failed` | `reason` (string) |

---

## GET /analysis-runs/{runId}

Response `200 OK`
```json
{
  "runId": "run_abc123",
  "status": "running",
  "steps": [
    { "key": "fetch_repos", "status": "completed" },
    { "key": "extract_jd", "status": "completed" },
    { "key": "match_score", "status": "running" },
    { "key": "prepare_result", "status": "pending" }
  ],
  "failureReason": null,
  "estimatedSeconds": 20
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `runId` | string | ❌ |
| `status` | RunStatus | ❌ |
| `steps[].key` | StepKey | ❌ |
| `steps[].status` | StepStatus | ❌ |
| `failureReason` | string | ✅ |
| `estimatedSeconds` | number | ✅ |

> 분석 실패도 HTTP 200이다. `status: "failed"` + `failureReason`으로 판단한다.

Response `410` — `run_expired`

---

## GET /analysis-runs/{runId}/result

Response `200 OK`
```json
{
  "runId": "run_abc123",
  "position": "Backend Developer",
  "jdRequirements": [
    "Java 또는 Kotlin으로 실서비스 백엔드를 설계·운영해본 경험이 2년 이상",
    "Redis, Kafka 같은 분산 캐시·메시징 시스템을 실제 트래픽 환경에서 다뤄본 경험"
  ],
  "repositories": [
    {
      "id": "r_001",
      "name": "project-a",
      "languages": ["Spring Boot", "Redis"],
      "recommended": true,
      "recommendReason": "JD의 Backend·캐시 요구사항과 연관도가 가장 높아요.",
      "matchScore": 92
    }
  ]
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `runId` | string | ❌ |
| `position` | string | ❌ |
| `jdRequirements` | string[] | ❌ |
| `repositories[].id` | string | ❌ |
| `repositories[].name` | string | ❌ |
| `repositories[].languages` | string[] | ❌ |
| `repositories[].recommended` | boolean | ❌ |
| `repositories[].recommendReason` | string | ❌ |
| `repositories[].matchScore` | number | ✅ |

Response 실패

| 코드 | reason |
| --- | --- |
| 409 | `not_ready` |
| 410 | `run_expired` |

---

## POST /interviews

Request
```json
{
  "runId": "run_abc123",
  "repositoryIds": ["r_001", "r_002"]
}
```

Response `201 Created`
```json
{
  "sessionId": "sess_xyz789",
  "interviewId": "iv_001"
}
```

Response 실패

| 코드 | reason |
| --- | --- |
| 400 | `no_repository_selected` · `invalid_repository` |
| 409 | `session_limit_exceeded` |
| 410 | `run_expired` |

---

## GET /interviews/{id}

5a2-v2(준비)와 5b-v2(진행)가 공유한다.

Response `200 OK`
```json
{
  "id": "iv_001",
  "sessionId": "sess_xyz789",
  "status": "in_progress",
  "position": "Backend Developer",
  "repositoryNames": ["project-a", "payment-service"],
  "currentTurn": 3,
  "totalTurns": 8,
  "remainingSeconds": 177,
  "turns": [
    {
      "turn": 1,
      "role": "tech_lead",
      "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",
      "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."
    },
    {
      "turn": 2,
      "role": "senior_developer",
      "question": "payment-service의 결제 실패 재시도는 어떻게 처리했나요?",
      "answer": null
    }
  ]
}
```

준비 단계면 `currentTurn: 0`, `turns: []`.

| 필드 | 타입 | null |
| --- | --- | --- |
| `id` | string | ❌ |
| `sessionId` | string | ❌ |
| `status` | InterviewStatus | ❌ |
| `position` | string | ❌ |
| `repositoryNames` | string[] | ❌ |
| `currentTurn` | number | ❌ |
| `totalTurns` | number | ✅ |
| `remainingSeconds` | number | ❌ |
| `turns[].turn` | number | ❌ |
| `turns[].role` | AgentRole | ❌ |
| `turns[].question` | string | ❌ |
| `turns[].answer` | string | ✅ |

Response `404` — `not_found`

---

## GET (Upgrade) /ws/interviews/{sessionId}

5a2-v2에서 연결하고 5b-v2까지 유지한다.

### 클라이언트 → 서버

```json
{ "type": "answerStart" }
```
```
(오디오 바이너리 — 일괄 1회 전송)
```
```json
{ "type": "answerEnd" }
```

### 서버 → 클라이언트

```json
{ "type": "prepareStep", "key": "compose_question", "status": "running" }
{ "type": "prepareCompleted" }
{ "type": "transcript", "text": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다." }
{ "type": "thinking" }
{ "type": "evidenceCheck", "repository": "project-a", "file": "CacheConfig.java" }
{ "type": "question", "role": "tech_lead", "text": "TTL을 600초로 설정한 근거가 있나요?", "turn": 3 }
{ "type": "questionEnd" }
{ "type": "interviewEnd" }
{ "type": "error", "reason": "stt_failed" }
```

`question` 메시지 뒤에 TTS 오디오 바이너리가 이어진다.

| type | 필드 |
| --- | --- |
| `prepareStep` | `key` (PrepareStepKey), `status` (StepStatus) |
| `prepareCompleted` | — |
| `transcript` | `text` (string) |
| `thinking` | — |
| `evidenceCheck` | `repository` (string), `file` (string) |
| `question` | `role` (AgentRole), `text` (string), `turn` (number) |
| `questionEnd` | — |
| `interviewEnd` | — |
| `error` | `reason` (string) |

`error.reason` 값: `stt_failed` · `tts_failed` · `question_failed` · `answer_too_long` · `prepare_failed`

핸드셰이크 실패

| 코드 | 상황 |
| --- | --- |
| 401 | 쿠키 없음 |
| 409 | 이미 종료된 세션 · `already_connected` |

---

## GET /interviews/{id}/report

Response `200 OK`
```json
{
  "interviewId": "iv_001",
  "position": "Backend Developer",
  "totalScore": 81,
  "headline": "김개발님은 프로젝트 이해도가 돋보이는 지원자입니다.",
  "summary": "사용자가 직접 선택한 project-a · payment-service 두 레포를 근거로 질문이 구성되었습니다.",
  "scores": [
    { "key": "project_understanding", "label": "프로젝트 이해도", "score": 88 },
    { "key": "technical_reasoning", "label": "기술적 사고력", "score": 79 },
    { "key": "problem_solving", "label": "문제 해결력", "score": 83 },
    { "key": "communication", "label": "커뮤니케이션", "score": 80 },
    { "key": "contribution_clarity", "label": "기여도 명확성", "score": 76 },
    { "key": "company_job_fit", "label": "기업·직무 적합성", "score": 82 }
  ],
  "agentFeedbacks": [
    {
      "role": "tech_lead",
      "tags": ["Architecture", "Trade-off"],
      "strengths": [
        "project-a에서 Redis를 도입한 배경과 전체 아키텍처 변화는 명확하게 설명했습니다."
      ],
      "improvements": [
        "TTL을 600초로 설정한 근거는 다른 대안과 비교해 구체적으로 제시하지 못했습니다."
      ],
      "disagreementSubmitted": false
    }
  ],
  "turns": [
    {
      "turn": 1,
      "role": "tech_lead",
      "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",
      "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."
    }
  ],
  "repositoryNames": ["project-a", "payment-service"],
  "completedAt": "2026-09-01T15:20:00Z"
}
```

`scores`는 6개, `agentFeedbacks`는 3개 고정.

| 필드 | 타입 | null |
| --- | --- | --- |
| `interviewId` | string | ❌ |
| `position` | string | ❌ |
| `totalScore` | number | ❌ |
| `headline` | string | ❌ |
| `summary` | string | ❌ |
| `scores[].key` | ScoreKey | ❌ |
| `scores[].label` | string | ❌ |
| `scores[].score` | number | ❌ |
| `agentFeedbacks[].role` | AgentRole | ❌ |
| `agentFeedbacks[].tags` | string[] | ❌ |
| `agentFeedbacks[].strengths` | string[] | ❌ |
| `agentFeedbacks[].improvements` | string[] | ❌ |
| `agentFeedbacks[].disagreementSubmitted` | boolean | ❌ |
| `turns[].turn` | number | ❌ |
| `turns[].role` | AgentRole | ❌ |
| `turns[].question` | string | ❌ |
| `turns[].answer` | string | ✅ |
| `repositoryNames` | string[] | ❌ |
| `completedAt` | string | ❌ |

Response `202 Accepted` — 생성 중
```json
{ "status": "generating", "retryAfter": 3 }
```

Response `409` — `report_unavailable` (진행된 턴 0개)

---

## POST /interviews/{id}/retry

Request — 없음

Response `201 Created`
```json
{
  "sessionId": "sess_new456",
  "interviewId": "iv_002"
}
```

Response 실패

| 코드 | reason |
| --- | --- |
| 409 | `original_not_completed` · `repository_unavailable` · `session_limit_exceeded` |
| 410 | `run_expired` |

---

## POST /reports/{id}/feedback-disagreements

Request
```json
{
  "agentRole": "tech_lead",
  "reasonType": "factual_error",
  "comment": "TTL 근거를 설명했는데 반영되지 않았습니다."
}
```

| 필드 | 타입 | 필수 |
| --- | --- | --- |
| `agentRole` | AgentRole | ✅ |
| `reasonType` | ReasonType | ✅ |
| `comment` | string (최대 500자) | ❌ |

Response `204 No Content`
Response `409` — `already_submitted`

---

## queryKey 매핑

| 경로 | queryKey |
| --- | --- |
| `GET /me` | `['me']` |
| `GET /me/home` | `['home']` |
| `GET /me/interviews?page=N` | `['interviews', { page }]` |
| `GET /analysis-runs/{runId}` | `['analysis-run', runId]` |
| `GET /analysis-runs/{runId}/result` | `['analysis-run', runId, 'result']` |
| `GET /interviews/{id}` | `['interview', id]` |
| `GET /interviews/{id}/report` | `['interview', id, 'report']` |

## 캐시 무효화

| 시점 | 무효화 |
| --- | --- |
| `POST /interviews` | `interviews` |
| `POST /interviews/{id}/retry` | `interviews` |
| 면접 완료 (리포트 생성) | `home`, `interviews` |
| 피드백 이의 제출 | `interview(id).report` |
| `POST /auth/logout` | 전체 `clear()` |