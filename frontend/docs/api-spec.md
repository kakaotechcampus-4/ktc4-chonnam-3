# DEVON API 명세

> 필드: camelCase · URL: kebab-case · 에러 reason·enum: snake_case
> 

각 엔드포인트는 **Endpoint / Request / Response / UI states / Failure** 5단 구조로 기술한다. `UI states`는 이 API가 어느 화면에서 어떻게 쓰이는지(분기·배지·버튼 노출), `Failure`는 실패 응답 코드·reason만 담는다.

일반 HTTP API의 요청·응답 원본은 [OpenAPI](../../spec/shared/contracts/openapi.yaml)다. 이 문서는 [공통 계약 안내](../../spec/shared/contracts/README.md)에 따라 WebSocket(#18), SSE(#13), 브라우저 이동(#1·#2·#7·#8)의 원본이며 나머지는 FE용 설명이다. 차이가 있으면 OpenAPI와 [이관·보류 현황](../../spec/shared/contracts/migration.md)을 먼저 확인한다. 문서의 확정 기준과 로컬 구현·mock의 반영 상태는 구분하며 과거 변경 이력은 당시 기록으로 보존한다.

## 공통 규약

| 항목 | 규칙 |
| --- | --- |
| 필드 네이밍 | camelCase |
| 배열 빈 값 | `[]` — null 금지 |
| 객체 빈 값 | `null` 허용 (명시된 필드만) |
| 날짜 | ISO 8601 문자열 |
| 필드 생략 | OpenAPI의 required·optional 정의를 따른다. nullable과 optional은 구분한다. |
| 인증 | Sprint 1: 기존 Redis 서버 세션·HttpOnly `devon_session` 쿠키. 모든 요청에 `credentials: 'include'` |
| 배포 | FE·BE 단일 DuckDNS+Caddy 배포. same-origin이므로 CORS 설정 불필요, API base URL은 상대경로 |

### 인증 구조

[0003 결정](../../spec/shared/decisions/0003-sprint1-session-auth.md)에 따라 Sprint 1은 기존 Redis의 `auth:sess:{sid}`에 로그인 세션을 저장하고 브라우저에는 식별자만 전달한다. JWT·refresh는 Sprint 2로 보류한다. 아래 명세 정리는 실제 서버·FE·MSW 인증 구현 완료를 뜻하지 않는다.

| 용도 | 쿠키명 | 만료 | Path |
| --- | --- | --- | --- |
| 로그인 세션 | `devon_session` | 14일 sliding (`1209600`초) | `/` |

운영 HTTPS 환경의 쿠키 예시:

```
Set-Cookie: devon_session=<sid>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600
```

`Secure`는 운영 HTTPS 환경에서 사용한다. 유효한 인증 요청에서 Redis TTL과 HTTP 응답의 쿠키 만료를 함께 14일로 연장하며 FE는 별도 갱신 요청을 보내지 않는다. REST·SSE·WS는 같은 쿠키로 인증한다. GitHub 토큰(`github_accounts.access_token_encrypted`)은 로그인 쿠키나 공개 응답에 담지 않고 서버가 조회한다.

<details>
<summary>이전 JWT 인증안 — Sprint 2 참고 기록, 세부 미확정</summary>

아래는 이전 설계의 보존 기록이며 Sprint 1 요구사항이 아니다. 토큰 수명·클레임·저장·로테이션·자동 갱신은 Sprint 2 착수 시 검토한다.

| 토큰 | 쿠키명 | 만료 | Path |
| --- | --- | --- | --- |
| Access Token | `accessToken` | 15분 | `/` |
| Refresh Token | `refreshToken` | 14일 | `/auth/refresh` |

```
Set-Cookie: accessToken=<jwt>;  HttpOnly; Secure; SameSite=Lax; Path=/;             Max-Age=900
Set-Cookie: refreshToken=<jwt>; HttpOnly; Secure; SameSite=Lax; Path=/auth/refresh; Max-Age=1209600
```

Access Token 클레임

```json
{ "sub": "u_001", "iat": 1757300000, "exp": 1757300900, "jti": "at_9f2c1b" }
```

리프레시 토큰은 서버 DB에 `jti`·상태·만료 시각을 저장하고, 갱신 시 로테이션한다. 폐기된 `jti`가 재사용되면 해당 사용자의 모든 리프레시 토큰을 무효화한다.

GitHub 토큰(`github_accounts.access_token_encrypted`)은 JWT에 담지 않는다. 서버가 조회한다.

</details>

### enum

```
analysisStatus:   syncing | no_repository | no_interview | completed
interviewStatus:  preparing | in_progress | completed | preparing_failed | abandoned
runStatus:        running | completed | failed
stepKey:          doc_extract | repo_select | repo_detail | jd_fetch
                  | jd_extract | repo_analyze | match_score
prepareStepKey:   analyze_repo | build_persona | compose_question | set_criteria
stepStatus:       pending | running | completed | failed | skipped
answerMode:       text            (2차에 voice 추가)
repoStatus:       succeeded | partial | failed
candidateSource:  rule_filter | portfolio | both
jdCategory:       required | preferred | responsibility
persona:          tech_lead | hr_manager | domain_lead
scoreKey:         project_understanding | technical_reasoning | problem_solving
                  | communication | contribution_clarity | company_job_fit
reasonType:       factual_error | insufficient_basis | overly_harsh
                  | unclear_intent | other
```

> `stepStatus.skipped`는 **입력이 없어 해당 단계를 실행하지 않은 정상 경로**를 뜻한다. `failed`(실행했으나 실패)와 구분한다. `stepKey`에만 적용되며, `prepareStepKey` 4단계는 모두 필수 실행이므로 `skipped`가 오지 않는다.
>

`skipped`가 발생하는 경우

| 상황 | `doc_extract` |
| --- | --- |
| `POST /analysis-runs`를 `documentId` 없이 호출 | `skipped` |
| `documentId`를 보냈으나 추출 실패 | `failed` |

### 에러 응답 (모든 4xx·5xx 공통)

```json
{
  "error": {
    "reason": "github_token_invalid",
    "message": "GitHub 재연동이 필요해요.",
    "retryAfter": 30
  }
}
```

`reason`은 종류가 많으므로 union으로 고정하지 않고 `string`으로 둔다.
`retryAfter`는 optional.

> `error.retryAfter`(4xx·5xx 공통 에러 객체)와, `202 Accepted` 응답 본문의 최상위 `retryAfter`(#19 · #22)는 위치가 다르다. 타입 정의 시 혼동하지 않는다.
>

### 인증 에러 reason (공통 참조)

`devon_session`을 쓰는 모든 엔드포인트에 적용된다. 각 엔드포인트의 `Failure`에서는 "공통 인증 에러 참고"로 링크하고 그 엔드포인트 고유 실패만 별도로 적는다.

| reason | 코드 | 의미 | 프론트 처리 |
| --- | --- | --- | --- |
| `unauthenticated` | 401 | 로그인 쿠키 없음 · Redis 세션 만료/유실/무효 | 전체 clear → `/login`, refresh 재시도 없음 |
| `account_suspended` | 403 | `users.status = 'suspended'` | 정지 안내 |
| `account_withdrawn` | 403 | `users.status = 'withdrawn'` | 재가입 불가 안내 |
| `github_token_invalid` | 403 | `github_accounts.token_status`가 `expired`·`revoked` | GitHub 재연동 유도 |

### 401 처리 정책

```
401 unauthenticated 수신
  └─ queryClient.clear() → /login
```

Query·Mutation에 같은 처리를 적용한다. 401에 refresh 호출이나 원 요청 자동 재시도를 하지 않으며 이미 로그인 화면이면 반복 이동하지 않는다. 현재 공통 처리는 미완료이며 [auth 구현 작업](task-07-auth.md)에서 연결·검증한다.

Redis 조회 장애는 세션 만료·유실과 구분한다. 정상 인증이나 `401 unauthenticated`로 처리하지 않고 기존 공통 오류 계약의 서버 오류로 처리한다.

### CSRF

`SameSite=Lax`로 방어한다. 상태 변경 요청은 모두 POST이며 `Lax`는 cross-site POST에 쿠키를 보내지 않는다. CSRF 토큰은 도입하지 않는다. `Strict`는 GitHub 콜백에서 돌아오는 top-level GET에 쿠키가 실리지 않아 쓰지 않는다.

---

## 엔드포인트 목록

| # | 메서드 | 경로 | 구현 방식 |
| --- | --- | --- | --- |
| 1 | GET | `/auth/github/login` | 브라우저 이동 |
| 2 | GET | `/auth/github/callback` | 프론트 무관 |
| 3 | POST | `/auth/refresh` | Sprint 2 예약 — Sprint 1 호출 없음 |
| 4 | POST | `/auth/logout` | fetch |
| 5 | GET | `/me` | fetch |
| 6 | GET | `/me/profile` | fetch |
| 7 | GET | `/auth/github/link` | 브라우저 이동 |
| 8 | GET | `/auth/github/link/callback` | 프론트 무관 |
| 9 | GET | `/me/home` | fetch |
| 10 | GET | `/me/interviews` | fetch |
| 11 | POST | `/documents/preview` | fetch (multipart) |
| 12 | POST | `/analysis-runs` | fetch |
| 13 | GET | `/analysis-runs/{runId}/events` | EventSource |
| 14 | GET | `/analysis-runs/{runId}` | fetch |
| 15 | GET | `/analysis-runs/{runId}/result` | fetch |
| 22 | GET | `/analysis-runs/{runId}/candidates` | fetch |
| 16 | POST | `/interviews` | fetch |
| 17 | GET | `/interviews/{id}` | fetch |
| 18 | GET *(Upgrade)* | `/ws/interviews/{sessionId}` | WebSocket |
| 19 | GET | `/interviews/{id}/report` | fetch |
| 20 | POST | `/interviews/{id}/retry` | fetch |
| 21 | POST | `/interviews/{id}/feedback-disagreements` | 계약 잔존, Sprint 1 제공·호출 제외 |

기존 번호 22개를 유지한다(기존 색인 21개 + Sprint 2 예약 #3). #21의 잔존 계약은 Sprint 1 제공·호출 대상이 아니므로 이 숫자를 실제 제공 API 수로 해석하지 않는다. 번호는 아래 "최종 엔드포인트 목록"·`shared/queryKeys.ts` 참조 번호와 같다. 22번은 `analysis-runs` 계열끼리 묶어 읽도록 15번 뒤에 배치했다.

> 브라우저 이동 경로는 `shared/api.ts`에 넣지 않는다. `<a href>` 또는 `window.location`으로 처리한다.
> 

> `sessionId`·`session_limit_exceeded`·`already_connected`의 "세션"은 면접 세션(`interview_sessions`)을 뜻한다. Redis 로그인 세션(`auth:sess:{sid}`)과는 별개이며 공개 면접 ID는 바꾸지 않는다.
> 

---

## 1. GET /auth/github/login

**Request**

없음.

**Response**

`302`

```
Location: https://github.com/login/oauth/authorize
            ?client_id=<client_id>
            &redirect_uri=<callback>
            &scope=read:user
            &state=<random>
Set-Cookie: oauthState=<random>; HttpOnly; Secure; SameSite=Lax; Path=/auth/github; Max-Age=600
```

| 항목 | 값 |
| --- | --- |
| `scope` | 로그인·연동 모두 `read:user`. 기존 BE 설정을 따르며 public 저장소 읽기에 `repo`·`public_repo` 권한은 요청하지 않음 |
| `state` | 서버 생성 랜덤값 — `oauthState` 쿠키에 저장 (CSRF 방어) |

**UI states**

로그인 화면(미인증 상태에서 보호 경로 접근 시 진입)의 `GitHub으로 로그인` 버튼 클릭 시 `window.location = '/auth/github/login'`으로 이동한다. 입력 폼은 없다.

**Failure**

해당 없음 — 항상 302로 GitHub 인증 화면으로 이동한다.

---

## 2. GET /auth/github/callback

**Request** (Query)

```
?code=abc123&state=x7f2a9
```

| 필드 | 필수 | 비고 |
| --- | --- | --- |
| `code` | ✅ | 1회용, 약 10분 유효 |
| `state` | ✅ | `oauthState` 쿠키값과 대조 |
| `error` | ❌ | 사용자 동의 거부 시 |

**Response**

`302`

```
Location: /home
Set-Cookie: devon_session=<sid>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=1209600
Set-Cookie: oauthState=; Max-Age=0; Path=/auth/github
```

서버는 Redis 로그인 세션을 생성하고 위 쿠키를 발급한다. `Secure`는 운영 HTTPS 환경 기준이며 로그인 세션은 14일 sliding 정책을 따른다.

동의 거부 시

```
Location: /login?error=denied
```

성공 시 `initial_sync` 잡을 큐에 넣고 즉시 302한다. 레포 수집 완료를 기다리지 않는다.

> 반드시 쿼리를 제거한 주소로 302한다. `?code=`가 남으면 새로고침 시 재사용이 발생하고, GitHub은 code 재사용을 탈취로 판단해 이미 발급한 토큰까지 무효화한다.
> 

**UI states**

프론트 로직 없음(서버 302만 처리). 복귀 후 홈은 `analysisStatus: 'syncing'`으로 시작한다.

**Failure**

| 코드 | reason |
| --- | --- |
| 400 | `invalid_state` · `invalid_code` |
| 403 | `account_suspended` · `account_withdrawn` |
| 502 | `provider_unavailable` |

---

## 3. POST /auth/refresh — Sprint 2 예약

기존 참조 번호만 유지한다. Sprint 1 서버 세션 인증에서는 이 API를 제공·호출하지 않는다. 현재 코드에 남은 `api.refresh`·MSW 핸들러·smoke 검사는 후속 정리 대상이다.

<details>
<summary>이전 JWT refresh안 — 과거 기록, Sprint 2 착수 시 재검토</summary>

아래 요청·응답·로테이션·실패 처리는 이전안이며 현재 구현 요구사항이나 Sprint 2 세부 확정이 아니다.

**Request**

없음 (`refreshToken` 쿠키만 사용).

**Response**

`204 No Content`

```
Set-Cookie: accessToken=<new_jwt>;  HttpOnly; Secure; SameSite=Lax; Path=/;             Max-Age=900
Set-Cookie: refreshToken=<new_jwt>; HttpOnly; Secure; SameSite=Lax; Path=/auth/refresh; Max-Age=1209600
```

갱신 시 리프레시 토큰도 새로 발급하고 이전 `jti`는 폐기한다.

**UI states**

화면에 직접 노출되지 않는다. 401 인터셉터 내부에서만 호출한다(single-flight).

**Failure**

| 코드 | reason |
| --- | --- |
| 401 | `refresh_token_invalid` |
| 403 | `account_suspended` · `account_withdrawn` |

</details>

---

## 4. POST /auth/logout

**Request**

없음.

**Response**

`204 No Content`

```
Set-Cookie: devon_session=; Max-Age=0; Path=/
```

현재 로그인 쿠키에 대응하는 Redis `auth:sess:{sid}`를 삭제하고 쿠키를 만료시킨다. 쿠키나 세션이 이미 없거나 만료된 상태여도 `204`로 응답한다(멱등). 다른 로그인 세션과 GitHub 토큰은 삭제하지 않는다.

**UI states**

마이페이지 로그아웃 버튼 → 확인 모달 → 호출 성공 시 `queryClient.clear()` → `/login`.

**Failure**

없음 (멱등, 항상 `204`).

---

## 5. GET /me

**Response**

`200 OK`

```json
{
  "name": "김개발",
  "avatarUrl": "https://avatars.githubusercontent.com/u/12345",
  "githubLinked": true
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `name` | string | ❌ |
| `avatarUrl` | string | ✅ |
| `githubLinked` | boolean | ❌ |

`name`은 `users.display_name` (GitHub `name`, 없으면 `login`).

**UI states**

전역 인증 가드용 — 보호 라우트 진입 시 호출해 인증 여부를 확인한다. 응답 필드 자체는 화면에 직접 렌더하지 않는다(프로필 표시는 `/me/home`, `/me/profile` 담당).

**Failure**

| 코드 | reason |
| --- | --- |
| 401 | `unauthenticated` |

---

## 6. GET /me/profile

**Response**

`200 OK`

```json
{
  "name": "김개발",
  "avatarUrl": "https://avatars.githubusercontent.com/u/12345",
  "loginId": "kimdev",
  "joinedAt": "2026-03-12T04:20:00Z",
  "desiredPosition": "Backend Developer",
  "github": {
    "linked": true,
    "login": "kimdev-io",
    "publicRepoCount": 5
  },
  "interviewSummary": {
    "totalCount": 3,
    "averageScore": 75
  }
}
```

| 필드 | 타입 | null | 출처 |
| --- | --- | --- | --- |
| `name` | string | ❌ | `users.display_name` |
| `avatarUrl` | string | ❌ | `users.avatar_url` |
| `loginId` | string | ✅ | `github_accounts.login` |
| `joinedAt` | string | ❌ | `users.created_at` |
| `desiredPosition` | string | ✅ | 가장 최근 완료 면접의 `position` |
| `github.linked` | boolean | ❌ | `github_accounts` 존재 여부 |
| `github.login` | string | ✅ | `github_accounts.login` |
| `github.publicRepoCount` | number | ✅ | `github_accounts.public_repo_count` |
| `interviewSummary.totalCount` | number | ❌ | `status='completed'` 세션 수 |
| `interviewSummary.averageScore` | number | ✅ | 완료 면접 `totalScore` 평균, 소수점 없이 반올림 |

`github.linked`가 `false`면 `login`·`loginId`·`publicRepoCount`는 `null`이다.
완료 면접이 0건이면 `totalCount: 0`, `averageScore: null`, `desiredPosition: null`이다.

`desiredPosition`(희망 직무)은 사용자가 직접 입력하는 값이 아니다. 가장 최근 완료 면접(`status='completed'`, `completed_at` 최신)의 `position`을 그대로 반환한다. `interviewSummary`와 같은 세션 집합을 집계하므로 별도 컬럼·수정 폼·`PATCH` 엔드포인트가 필요 없다.

> **BE 확인 필요** — `avatarUrl`·`loginId`의 null 여부는 이 문서와 `GET /me`(#5)가 어긋나 있었다. 이 표는 `feature/shared-api-mypage-support`(PR #7, develop 머지됨)의 `MeProfileResponse` 구현을 기준으로 맞춘 것이다. #5는 `avatarUrl`을 nullable로 두고 있어 같은 `users.avatar_url`을 두 엔드포인트가 다르게 취급한다. 어느 쪽이 맞는지 BE가 확정해야 한다.

**UI states**

마이페이지(1a) 내 정보 카드 — `name`·`joinedAt`·`loginId`·`desiredPosition`, GitHub 배지("연동됨 · 레포 {publicRepoCount}개"), 면접 이력 헤더(`interviewSummary.totalCount`·`averageScore`). 이력 목록 자체는 `GET /me/interviews`가 담당.

**Failure**

| 코드 | reason |
| --- | --- |
| 401 | `unauthenticated` |

---

## 7. GET /auth/github/link

GitHub 토큰 무효 시 재연동. DEVON 로그인 상태는 유지되고 GitHub 토큰만 갱신된다.

**Request**

없음.

**Response**

`302`

```
Location: https://github.com/login/oauth/authorize?...&state=<random>
Set-Cookie: oauthState=<random>; HttpOnly; Secure; SameSite=Lax; Path=/auth/github; Max-Age=600
```

`302` → `/login` — 로그인 쿠키가 없거나 Redis 세션이 만료·유실·무효인 경우.

> 이 경로는 브라우저 이동이므로 401 인터셉터가 동작하지 않는다. 만료 시 JSON 401이 아니라 `/login`으로 302한다.
> 

**UI states**

홈·분석 실패 화면의 "GitHub 재연동" 배너 클릭 시 `window.location`으로 이동한다(공용 컴포넌트).

**Failure**

JSON 에러 없음 — 실패는 `/login` 302로 표현된다.

---

## 8. GET /auth/github/link/callback

**Request** (Query) — `code`, `state` (login 콜백과 동일)

**Response**

`302`

```
Location: /home
Set-Cookie: oauthState=; Max-Age=0; Path=/auth/github
```

`github_accounts.token_status`를 `valid`로 갱신한다. 기존 DEVON 로그인 세션을 유지하며 새 JWT를 발급하지 않는다. 세션 만료 연장은 공통 sliding 정책을 따른다.

**UI states**

프론트 로직 없음. 복귀 후 `me`·`home` 쿼리를 무효화해 재연동 배너를 내린다.

**Failure**

| 코드 | reason |
| --- | --- |
| 409 | `github_already_linked` |

---

## 9. GET /me/home

**Response**

`200 OK`

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
    "roleSummary": "면접 답변에서 백엔드 API 설계와 DB·캐시 최적화를 담당했다고 설명했습니다."
  },
  "recentInterviews": [
    {
      "id": "iv_001",
      "position": "Backend Developer",
      "companyName": "토스뱅크",
      "totalScore": 81,
      "completedAt": "2026-09-01T15:20:00Z"
    }
  ]
}
```

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
| `recentInterviews[].companyName` | string | ✅ |
| `recentInterviews[].totalScore` | number | ✅ |
| `recentInterviews[].completedAt` | string | ✅ |

`analysis`는 `user_profile_summaries` 1행을 그대로 매핑한다.

**UI states**

| `analysisStatus` | 화면 | `analysis` | `recentInterviews` |
| --- | --- | --- | --- |
| `syncing` | 레포 수집 중 안내(스피너), 폴링 | `null` | `[]` |
| `no_repository` | 공개 레포 없음 안내 | `null` | `[]` |
| `no_interview` | 첫 면접 유도 CTA 강조 | `null` | `[]` |
| `completed` | 언어 비율 그래프 + 프로젝트 유형 태그 + 역할 요약문 + 최근 면접 리스트 | 객체 | 배열 |

헤더 GitHub 배지는 `githubLinked`, 새 면접 시작 CTA는 상시 노출. `syncing`이면 폴링으로 재조회한다(간격은 팀 확정 필요).

**Failure**

| 코드 | reason | 처리 |
| --- | --- | --- |
| 403 | `github_token_invalid` | 재연동 배너 노출, 패널은 마지막 캐시 유지 |

---

## 10. GET /me/interviews

**Request** (Query)

```
?page=1&size=20
```

| 필드 | 타입 | 필수 | 기본값 |
| --- | --- | --- | --- |
| `page` | number | ❌ | 1 |
| `size` | number | ❌ | 20 |

**Response**

`200 OK`

```json
{
  "interviews": [
    {
      "id": "iv_001",
      "position": "Backend Developer",
      "companyName": "토스뱅크",
      "repositoryNames": ["project-a", "payment-service"],
      "status": "completed",
      "totalScore": 81,
      "startedAt": "2026-09-01T15:00:00Z",
      "completedAt": "2026-09-01T15:20:00Z"
    }
  ],
  "total": 12,
  "averageScore": 75,
  "page": 1,
  "size": 20
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `averageScore` | number | ✅ |
| `interviews[].id` | string | ❌ |
| `interviews[].position` | string | ❌ |
| `interviews[].companyName` | string | ✅ |
| `interviews[].repositoryNames` | string[] | ❌ |
| `interviews[].status` | InterviewStatus | ❌ |
| `interviews[].totalScore` | number | ✅ |
| `interviews[].startedAt` | string | ✅ |
| `interviews[].completedAt` | string | ✅ |
| `total` `page` `size` | number | ❌ |

`startedAt`은 첫 질문 시각이므로 `preparing` 상태에서는 `null`이다.
`averageScore`는 완료 면접의 `totalScore` 평균이며 페이지와 무관하게 전체 기준이다.
기록 0건이면 `interviews: []`, `total: 0`, `averageScore: null`.

**UI states**

마이페이지(1a) 면접 이력 테이블 — `status === 'completed'`만 표시. 행 클릭 시 리포트(5c-v2)로 이동. 페이지네이션은 이 쿼리로 처리.

**Failure**

공통 인증 에러 참고.

---

## 11. POST /documents/preview

BE `spec/backend/features/documents.md`와 [0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md) 기준이다. Sprint 1은 포트폴리오를 `analysis-runs`에 직접 싣지 않고 이 엔드포인트로 먼저 업로드해 `documentId`를 발급받는다. 자소서는 preview 대상이 아니며 claim 추출은 Sprint 2다. 아래 응답 명세와 실제 추출·저장 구현 완료는 구분한다.

**Request** `multipart/form-data`

| 필드 | 타입 | 필수 | 상한 |
| --- | --- | --- | --- |
| `file` | file (.pdf/.docx/.txt/.md) | ✅ | 20MB |

> `.pdf`는 텍스트 레이어가 있는 파일만 지원한다(스캔 이미지 PDF는 추출 실패). `.hwp`·이미지·`.ppt/.pptx`는 미지원.
`Content-Type` 헤더를 직접 지정하지 않는다. 브라우저가 boundary와 함께 자동 생성해야 한다.
> 

**Response**

`200 OK`

```json
{
  "documentId": "doc_abc123",
  "extractStatus": "succeeded"
}
```

`extractStatus`: `succeeded` / `partial`(일부 추출 또는 길이 초과 축약) / `failed`.

**UI states**

공고입력 화면에서 파일 선택 즉시(백그라운드) 호출한다. `extractStatus: 'failed'`여도 hard blocker가 아니다 — 사용자가 계속 진행을 선택하면 `POST /analysis-runs`를 `documentId` 없이 호출한다. 이 경우 `doc_extract`는 `skipped`로 응답된다.

**확정**: [0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 Sprint 1의 preview는 포트폴리오 전용이다. `documentId`는 단일 portfolio preview ID를 유지하며 자소서는 preview POST 대상이 아니다. 화면·호출 코드의 반영 여부는 별도로 검증한다.

**Failure**

| 코드 | reason |
| --- | --- |
| 413 | `file_too_large` |
| 415 | `unsupported_media_type` |

---

## 12. POST /analysis-runs

`analysis_jobs` 1행(`job_type='interview_prep'`)을 생성한다.

**Request** `application/json`

| 필드 | 타입 | 필수 |
| --- | --- | --- |
| `postingUrl` | text | ✅ |
| `documentId` | string | ❌ |

`postingUrl`은 Sprint 1에서 Wanted URL만 허용한다. `documentId`는 `POST /documents/preview`에서 발급된 값만 허용한다. 자기소개서·포트폴리오는 선택 입력이므로 `documentId`를 생략할 수 있고, 이때 `doc_extract` 단계는 실행되지 않는다(`skipped`).

**Response**

`202 Accepted`

```
Location: /analysis-runs/run_abc123
```

```json
{ "runId": "run_abc123" }
```

> 동일 `postingUrl`이 7일 이내에 `success`로 파싱된 이력이 있으면 `job_postings` 행을 재사용한다. 프론트에서 구분할 필요는 없다.
> 

**UI states**

공고입력 화면 `분석 시작` 클릭 시 호출 → `202` 수신 시 4-2-v2로 이동. 공고 URL 미입력/형식 오류면 클라이언트에서 버튼을 비활성해 아예 호출하지 않는다. "공고 없이 진행" 경로는 없다.

**Failure**

| 코드 | reason | 처리 |
| --- | --- | --- |
| 400 | `job_url_required` | 입력창 에러 |
| 400 | `unsupported_site` | "지원하지 않는 사이트예요" |
| 400 | `url_unreachable` | "공고를 불러올 수 없어요" |
| 409 | `run_in_progress` | `error.details.runId`로 기존 분석 진행 화면(4-2-v2) 이동 |

> 공고 수집·추출 실패는 잡 생성 후 발생하므로 `202`로 응답하고 `failureReason`으로 전달한다(`GET /analysis-runs/{runId}` 참고). `unsupported_site`·`url_unreachable`만 잡 생성 전에 판별 가능하므로 `400`이다.
> 

---

## 13. GET /analysis-runs/{runId}/events

SSE · `text/event-stream`

**Request**

```jsx
new EventSource(`/analysis-runs/${runId}/events`, { withCredentials: true })
```

> 구독 전에 `GET /analysis-runs/{runId}`를 1회 호출해 `steps` 스냅샷을 확보한다. 이 스트림은 구독 시점 이후의 변화만 전달하므로, 새로고침·재진입 시 이전 `step` 이벤트를 받을 수 없다. REST로 부트스트랩하고 SSE로 델타를 받는 구조다(#17 · #18과 동일).
>

**Response**

```
data: {"type":"step","key":"jd_extract","status":"completed"}

data: {"type":"step","key":"doc_extract","status":"skipped"}

data: {"type":"progress","value":57}

data: {"type":"completed"}

data: {"type":"failed","reason":"github_token_invalid"}
```

| type | 필드 |
| --- | --- |
| `step` | `key` (StepKey), `status` (StepStatus) |
| `progress` | `value` (number, 0~100) |
| `completed` | — |
| `failed` | `reason` (string) |

`skipped`도 `step` 이벤트로 1회 전송한다. 전송하지 않으면 SSE만 구독한 화면은 해당 스텝을 초기값 `pending`인 채로 유지하게 되어 `GET /analysis-runs/{runId}` 결과와 어긋난다.

`devon_session` 인증은 연결 수립 시 1회 검증한다. 연결 유지 중 로그인 세션 만료를 이유로 기존 스트림을 끊는 정책은 추가하지 않는다. 새 연결은 세션을 다시 확인한다.

**UI states**

4-2-v2 체크리스트 갱신(각 단계가 완료되면 회전 아이콘이 체크로 바뀌는 방식). `completed` 수신 시 5a-v2, `failed` 수신 시 4-3-v2로 전환. `status: 'skipped'`인 스텝은 체크리스트에서 숨긴다(✕로 표시하지 않는다 — 미첨부는 정상 경로다).

> `progress` 이벤트(0~100)는 계약에는 존재하지만, 4-2-v2는 퍼센트·진행률 바 대신 단계별 상태(`step` 이벤트)만으로 진행 상황을 표시하기로 해 현재 어떤 화면에서도 소비하지 않는다. 다른 화면에서 필요해지면 그때 UI states를 갱신한다.
>

**Failure**

`EventSource`는 응답 바디를 읽을 수 없어 `onerror`에서 상태 코드를 알 수 없다. 401 등 판별이 필요하면 `GET /analysis-runs/{runId}`를 1회 호출해 확인한다.

---

## 14. GET /analysis-runs/{runId}

**Response**

`200 OK`

```json
{
  "runId": "run_abc123",
  "status": "running",
  "steps": [
    { "key": "doc_extract",  "status": "completed" },
    { "key": "repo_select",  "status": "completed" },
    { "key": "repo_detail",  "status": "completed" },
    { "key": "jd_fetch",     "status": "completed" },
    { "key": "jd_extract",   "status": "running" },
    { "key": "repo_analyze", "status": "pending" },
    { "key": "match_score",  "status": "pending" }
  ],
  "progress": 57,
  "failureReason": null,
  "estimatedSeconds": 20
}
```

`documentId` 없이 생성된 run (포트폴리오 미첨부)

```json
{
  "runId": "run_def456",
  "status": "running",
  "steps": [
    { "key": "doc_extract",  "status": "skipped" },
    { "key": "repo_select",  "status": "completed" },
    { "key": "repo_detail",  "status": "running" },
    { "key": "jd_fetch",     "status": "pending" },
    { "key": "jd_extract",   "status": "pending" },
    { "key": "repo_analyze", "status": "pending" },
    { "key": "match_score",  "status": "pending" }
  ],
  "progress": 22,
  "failureReason": null,
  "estimatedSeconds": 35
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `runId` | string | ❌ |
| `status` | RunStatus | ❌ |
| `steps[].key` | StepKey | ❌ |
| `steps[].status` | StepStatus | ❌ |
| `progress` | number | ❌ |
| `failureReason` | string | ✅ |
| `estimatedSeconds` | number | ✅ |

`steps[]`는 항상 `stepKey` 7개를 모두 포함한다. 실행하지 않은 단계도 키를 생략하지 않고 `skipped`로 표기한다(공통 규약 "필드 생략 금지"). `skipped`인 스텝은 `progress` 계산에서 제외한다.

> 분석 실패도 HTTP 200이다. `status: "failed"` + `failureReason`으로 판단한다.
DB run의 `partial`은 FE `status: "failed"`로 매핑한다. 성공한 저장소의 결과는 `GET /analysis-runs/{runId}/result`로 조회할 수 있다([부분 실패 기준](../../spec/backend/features/analysis-run.md#부분-실패)). 개별 저장소의 `status: 'partial'`과는 다른 범위다. 실패 화면에서 성공 결과로 이동하는 경로는 [task-09](task-09-analysis.md)에 제안만 기록했으며 화면 수정은 보류 중이다.
> 

**UI states**

4-2-v2·4-3-v2 상태 판단, SSE 구독 전 스냅샷 확보, SSE `onerror` 시 폴백 조회.

`status: 'skipped'`인 스텝은 체크리스트 렌더에서 제외한다. 스텝을 그룹으로 묶어 표시하는 경우, 그룹 내 스텝이 전부 `skipped`면 그룹 행 자체를 숨긴다.

**Failure**

`failureReason` 값 (`analysis_jobs.error_code`)

| 값 | 화면 처리 | 재시도 |
| --- | --- | --- |
| `no_public_repo` | 안내만 — 재시도 버튼 숨김 | ❌ |
| `user_not_found` | 안내만 | ❌ |
| `rate_limited` | 대기 시간 안내 (`retryAfter`) | 시간 후 |
| `github_token_invalid` | GitHub 재연동 강조 | 재연동 후 |
| `jd_fetch_failed` | 공고 URL 입력창 강조 | ✅ |
| `jd_extraction_failed` | 공고 URL 입력창 강조 | ✅ |
| `not_a_job_posting` | "채용 공고가 아닌 것 같아요" | ✅ |
| `doc_extract_failed` | 첨부 파일 안내 | ✅ |
| `llm_timeout` | "분석이 지연되고 있어요" | ✅ |

> `jd_fetch_failed`는 페이지 수집 실패, `jd_extraction_failed`는 LLM 추출 실패다. 재시도 성공률이 다르므로 구분한다.
`doc_extract_failed`는 첨부한 문서의 추출에 실패한 경우다. 미첨부는 실패가 아니라 `skipped`이며 `failureReason`을 만들지 않는다.
> 

`410` — `run_expired`

---

## 15. GET /analysis-runs/{runId}/result

**Response**

`200 OK`

```json
{
  "runId": "run_abc123",
  "position": "Backend Developer",
  "companyName": "토스뱅크",
  "jdRequirements": [
    {
      "id": "req_003",
      "category": "required",
      "text": "Redis 등 캐시 시스템 운영 경험",
      "displayOrder": 3
    },
    {
      "id": "req_007",
      "category": "preferred",
      "text": "대용량 트래픽 처리 경험",
      "displayOrder": 7
    }
  ],
  "mentionedRepoCount": 3,
  "matchedRepoCount": 2,
  "repositories": [
    {
      "id": "r_001",
      "name": "project-a",
      "fullName": "kim/project-a",
      "description": "Spring Boot 기반 결제 API 서버",
      "languages": [
        { "name": "Java", "ratio": 68 },
        { "name": "TypeScript", "ratio": 21 }
      ],
      "topics": ["spring-boot", "redis"],
      "stars": 12,
      "forks": 3,
      "commitCount": 142,
      "userCommitCount": 138,
      "pushedAt": "2026-06-14T09:12:00Z",
      "status": "succeeded",
      "errorCode": null,
      "recommended": true,
      "candidateSource": "both",
      "recommendReason": "공고의 Redis 캐싱 경험과 직접 연관돼요.",
      "matchScore": null,
      "matchedRequirementIds": ["req_003", "req_007"]
    }
  ]
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `runId` | string | ❌ |
| `position` | string | ❌ |
| `companyName` | string | ✅ |
| `jdRequirements[].id` | string | ❌ |
| `jdRequirements[].category` | JdCategory | ❌ |
| `jdRequirements[].text` | string | ❌ |
| `jdRequirements[].displayOrder` | number | ❌ |
| `mentionedRepoCount` | number | ❌ |
| `matchedRepoCount` | number | ❌ |
| `repositories[].id` | string | ❌ |
| `repositories[].name` | string | ❌ |
| `repositories[].fullName` | string | ❌ |
| `repositories[].description` | string | ✅ |
| `repositories[].languages[].name` | string | ❌ |
| `repositories[].languages[].ratio` | number | ❌ |
| `repositories[].topics` | string[] | ❌ |
| `repositories[].stars` | number | ❌ |
| `repositories[].forks` | number | ❌ |
| `repositories[].commitCount` | number | ✅ |
| `repositories[].userCommitCount` | number | ✅ |
| `repositories[].pushedAt` | string | ✅ |
| `repositories[].status` | RepoStatus | ❌ |
| `repositories[].errorCode` | string | ✅ |
| `repositories[].recommended` | boolean | ❌ |
| `repositories[].candidateSource` | CandidateSource | ❌ |
| `repositories[].recommendReason` | string | ✅ |
| `repositories[].matchScore` | number | ✅ |
| `repositories[].matchedRequirementIds` | string[] | ❌ |

`doc_extract`가 `skipped`인 run에서는 `candidateSource`가 `portfolio`·`both`인 레포가 없고, `mentionedRepoCount`·`matchedRepoCount`는 `0`이다.

[0017 결정](../../spec/ai/decisions/0017-recommendation-score-deferral.md)에 따라 Sprint 1은 `matchScore` 필드를 생략하지 않고 null을 반환한다. 숫자 계산·표시·점수 정렬은 보류하며 null만으로 실패나 추천 제외를 판단하지 않는다. 기존 mock의 숫자 예시는 후속 반영 대상이다.

**UI states**

5a-v2 레포 확정 화면.

- `jdRequirements[]`는 `category`로 그룹핑해 `displayOrder` 순으로 우측에 표시(읽기 전용). 상한 20개.
- 선택 가능한 `succeeded` 레포 중 `recommended: true`(최대 5개)인 레포는 기본 체크 상태. 로컬 화면의 선택 조건 보완은 task-09에서 보류 중이다.
- `candidateSource` 배지: `rule_filter` 없음 / `portfolio`·`both` → 📎 포트폴리오.
- `mentionedRepoCount ≠ matchedRepoCount`면 "포트폴리오에 언급된 3개 중 2개를 찾았어요" 안내. 매칭 실패는 정상 상황이며 오류로 처리하지 않는다. 두 값이 모두 `0`이면(미첨부) 이 안내를 표시하지 않는다.
- `repositories[].status === 'failed'`면 카드를 회색 처리하고 `errorCode`별 문구를 띄운다. `matchScore`·`recommendReason`은 `null`이다.
- `status: 'partial'`은 카드를 표시하되 기존 서버 기준상 선택 대상은 아니다. 낮은 숫자 점수로 표현하지 않는다. 선택 조건·안내의 화면 반영은 task-09의 보류 상태를 유지한다.

| `errorCode` | 문구 | 재시도 |
| --- | --- | --- |
| `llm_timeout` | "분석이 지연되고 있어요" | 자동 1회 |
| `parse_failed` | "분석이 지연되고 있어요" | 자동 1회 |
| `input_too_large` | "정보가 부족해요" | ❌ |
| `no_readme` | "정보가 부족해요" | ❌ |
| `github_token_invalid` | "GitHub 재연동이 필요해요" | 재연동 후 |

**Failure**

| 코드 | reason |
| --- | --- |
| 409 | `not_ready` |
| 410 | `run_expired` |

---

## 22. GET /analysis-runs/{runId}/candidates

5a-v2의 "내 레포 더 보기". BE `spec/backend/features/analysis-run.md` 기준(Sprint 1 FIX) — 해당 run에 종속된 랭킹 후보를 페이지 단위로 반환한다. 필터 탈락(`private`·`fork`·`archived`·`no_language`·`too_small`·`inaccessible`) 레포는 기본 응답에 노출하지 않는다.

**Request** (Query)

```
?page=2
```

**Response**

`200 OK` — 해당 page가 이미 분석 완료된 경우. 필드는 `/analysis-runs/{runId}/result`의 `repositories[]`와 동일한 카드 스키마.

`202 Accepted` — 해당 page가 아직 미분석인 경우

```json
{ "status": "analyzing", "retryAfter": 3 }
```

`retryAfter` 간격으로 재조회해 완료되면 카드를 추가한다. 이 `retryAfter`는 본문 최상위 필드이며, 공통 에러 객체의 `error.retryAfter`와 위치가 다르다.

> 2026-09-11 이전에는 이 화면을 `GET /me/repositories`(전체 공개 레포 목록, 필터 탈락분 포함)로 설계했으나 BE 계약과 맞지 않아 폐기했다. "더보기"는 전체 레포 열람이 아니라 같은 run 안에서 다음 랭킹 배치를 분석·노출하는 것이다.
> 

**UI states**

5a-v2 `내 레포 더 보기` 클릭 시 호출. `202`면 로딩 상태 유지 후 폴링, `200`이면 카드를 기존 목록에 추가한다.

**Failure**

공통 인증 에러 참고. 그 외 고유 실패 코드 없음(상태는 `200`/`202`로 표현).

---

## 16. POST /interviews

`interview_sessions`(`status='preparing'`)와 `session_repositories`를 생성한다.

**Request**

```json
{
  "runId": "run_abc123",
  "repositoryIds": ["r_001", "r_002"]
}
```

| 필드 | 타입 | 필수 | 상한 |
| --- | --- | --- | --- |
| `runId` | string | ✅ | — |
| `repositoryIds` | string[] | ✅ | 5개 |

**Response**

`201 Created`

```json
{
  "sessionId": "sess_xyz789",
  "interviewId": "iv_001"
}
```

**UI states**

5a-v2 `확정` 버튼 클릭 시 호출. 성공 시 `interviews` 캐시 무효화 후 5a2-v2(면접 준비)로 이동.

**Failure**

| 코드 | reason |
| --- | --- |
| 400 | `no_repository_selected` · `invalid_repository` · `too_many_repositories` |
| 409 | `session_limit_exceeded` |
| 410 | `run_expired` |

---

## 17. GET /interviews/{id}

5a2-v2(준비)와 5b-v2(진행)가 공유한다. 인터뷰가 존재하는 한 상태와 무관하게 `200`이다 — "인터뷰 시작 조건"이 아니라 상태 조회용 단일 엔드포인트다.

**Response**

`200 OK`

```json
{
  "id": "iv_001",
  "sessionId": "sess_xyz789",
  "runId": "run_abc123",
  "status": "in_progress",
  "answerMode": "text",
  "position": "Backend Developer",
  "companyName": "토스뱅크",
  "repositoryNames": ["project-a", "payment-service"],
  "currentTurn": 3,
  "totalTurns": 9,
  "remainingSeconds": 177,
  "turns": [
    {
      "turn": 1,
      "persona": "tech_lead",
      "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",
      "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."
    },
    {
      "turn": 2,
      "persona": "domain_lead",
      "question": "금융권이라 캐시에 개인정보가 담기면 규제 대상이 됩니다. 데이터 민감도를 고려해보신 적 있나요?",
      "answer": null
    }
  ],
  "lastError": null
}
```

`status === "preparing_failed"`일 때 `lastError` 예시:

```json
{
  "status": "preparing_failed",
  "lastError": {
    "reason": "question_gen_timeout",
    "code": "ERR_QUESTION_GEN_TIMEOUT",
    "step": "compose_question",
    "recoverable": true,
    "occurredAt": "2026-09-07T14:22:10Z"
  }
}
```

| 필드 | 타입 | null |
| --- | --- | --- |
| `id` | string | ❌ |
| `sessionId` | string | ❌ |
| `runId` | string | ❌ |
| `status` | InterviewStatus | ❌ |
| `answerMode` | AnswerMode | ❌ |
| `position` | string | ❌ |
| `companyName` | string | ✅ |
| `repositoryNames` | string[] | ❌ |
| `currentTurn` | number | ❌ |
| `totalTurns` | number | ❌ |
| `remainingSeconds` | number | ❌ |
| `turns[].turn` | number | ❌ |
| `turns[].persona` | Persona | ❌ |
| `turns[].question` | string | ❌ |
| `turns[].answer` | string | ✅ |
| `lastError` | object | ✅ |
| `lastError.reason` | string | ❌ |
| `lastError.code` | string | ❌ |
| `lastError.step` | PrepareStepKey | ✅ |
| `lastError.recoverable` | boolean | ❌ |
| `lastError.occurredAt` | string | ❌ |

`runId`는 이 면접을 만든 `analysis_jobs` 행의 id다. `POST /interviews`가 `runId` 필수로 세션을 만들므로 모든 면접이 반드시 값을 갖는다(null 불가). 1b(준비 실패) 화면에서 "레포 다시 선택"으로 5a-v2에 돌아가려면 `GET /analysis-runs/{runId}/result`가 필요한데, 새로고침 시 FE는 `runId`를 들고 있지 않으므로 이 응답으로 복구한다.

`totalTurns`는 `max_turns`, `remainingSeconds`는 `planned_duration_sec - elapsed_sec`다. 서버 시각 기준이므로 재연결 시 클라이언트 타이머를 이 값으로 덮어쓴다.

`lastError`는 `status === 'preparing_failed'`일 때만 값이 있고 그 외에는 `null`이다. WS `error` 이벤트와 필드 구성이 같다 — 새로고침으로 WS가 끊긴 상태에서도 REST 스냅샷만으로 1b 배너를 완성하기 위함이다.

**UI states**

새로고침·재진입 시 이 응답의 `status`로 도달 화면을 결정한다.

| `status` | `currentTurn` | 화면 |
| --- | --- | --- |
| `preparing` | `0` | 5a2-v2 준비 화면 — `turns: []` |
| `in_progress` | `1+` | 5b-v2 — `turns`로 복구 |
| `completed` | — | 5c-v2 리포트로 이동 |
| `preparing_failed` | `0` | 1b — `lastError`로 배너 렌더 (WS 재연결 불필요) |
| `abandoned` | — | "중단된 면접이에요" 안내 후 `/home` |

`abandoned`여도 이미 저장한 답변 원문은 보존한다. 마지막 턴이 미답변일 때만 `answer: null`로 남으며, 답변 저장 후 분석·질문 생성 중 명시적으로 나간 경우 저장된 답변을 지우지 않는다.

1b에서 "레포 다시 선택"은 이 응답의 `runId`로 `/interview/repos/{runId}`(5a-v2)에 진입한다.

**Failure**

| 코드 | reason |
| --- | --- |
| 404 | `not_found` |

---

## 18. GET (Upgrade) /ws/interviews/{sessionId}

5a2-v2에서 연결하고 5b-v2까지 유지한다.

**Request**

핸드셰이크

```
GET /ws/interviews/sess_xyz789 HTTP/1.1
Upgrade: websocket
Connection: Upgrade
Cookie: devon_session=<sid>
```

Redis 로그인 세션 인증은 핸드셰이크 시 1회 검증한다. 연결 유지 중 로그인 세션 만료를 이유로 기존 연결을 끊는 정책은 추가하지 않는다. `onclose` 후 `GET /interviews/{id}`로 세션 유효성을 확인하고 `turns`를 확보한 다음 재연결한다. 세션 만료·유실로 `401 unauthenticated`이면 refresh 없이 캐시를 비우고 `/login`으로 이동한다. 로그인 세션 식별자와 면접 `sessionId`는 별개다.

`abandoned`는 명시적 이탈 확인 또는 레포 재선택으로 새 면접을 만들 때만 설정한다([0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md)). 연결 끊김·재연결 실패·로그인 세션 만료만으로 면접 상태를 바꾸지 않는다.

클라이언트 → 서버

```json
{ "type": "answer", "turn": 3, "text": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다." }
```

| type | 필드 |
| --- | --- |
| `answer` | `turn` (number), `text` (string, 최대 2000자) |

[0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 준비 실패 후 "다시 시도"는 WS `prepareRetry`가 아니라 REST `POST /interviews/{id}/prepare/retry`를 호출한다. 실패한 `prepareStepKey`부터 다시 실행하고 성공한 단계·면접 식별자·레포 조합을 유지한다. 기존 번호는 추가하지 않으며 상세 흐름은 [면접 명세](../../spec/frontend/features/interview.md)를 따른다. 이 REST 경로의 공통 계약 파일 반영과 실제 구현·연결은 별도 검증 대상이다.

`answer`는 현재 답변 가능한 `turn`과 함께 제출 버튼 클릭 시 1회 전송한다. 초안 저장은 없다. 2000자 초과 시 `answer_too_long`.

**Response**

`101 Switching Protocols`

서버 → 클라이언트

```json
{ "type": "prepareStep", "key": "compose_question", "status": "running" }
{ "type": "prepareCompleted" }
{ "type": "answerReceived" }
{ "type": "thinking" }
{ "type": "evidenceCheck", "repository": "project-a", "file": "CacheConfig.java" }
{ "type": "question", "persona": "tech_lead", "text": "TTL을 600초로 설정한 근거가 있나요?", "turn": 3 }
{ "type": "interviewEnd" }
{ "type": "error", "reason": "answer_too_long", "recoverable": true,
  "code": "ERR_ANSWER_TOO_LONG", "step": null,
  "occurredAt": "2026-09-07T14:22:10Z" }
```

| type | 필드 |
| --- | --- |
| `prepareStep` | `key` (PrepareStepKey), `status` (StepStatus) |
| `prepareCompleted` | — |
| `answerReceived` | — |
| `thinking` | — |
| `evidenceCheck` | `repository` (string), `file` (string) |
| `question` | `persona` (Persona), `text` (string), `turn` (number) |
| `interviewEnd` | — |
| `error` | `reason` (string), `recoverable` (boolean), `code` (string), `step` (PrepareStepKey 또는 null), `occurredAt` (string) |

`prepareStep.status`는 `pending`·`running`·`completed`·`failed` 4개만 사용한다. `prepareStepKey` 4단계는 모두 필수 실행이므로 `skipped`가 오지 않는다 — `skipped`는 `stepKey`(#13 · #14) 전용이다.

`answerReceived`는 서버가 답변 수신·저장을 완료했다는 신호다. 수신하면 제출 중 상태는 해제하지만 다음 `question`까지 새 답변 입력은 잠근다. Sprint 1은 `question` 수신 자체가 질문 전달 완료이므로 `questionEnd`를 기다리지 않는다.

준비 단계가 실패하면 해당 단계에 `prepareStep`을 `status: "failed"`로 보낸 뒤 `error`를 보낸다. 이후 단계는 `pending`으로 남는다.

```
{ "type": "prepareStep", "key": "analyze_repo",      "status": "completed" }
{ "type": "prepareStep", "key": "build_persona",     "status": "completed" }
{ "type": "prepareStep", "key": "compose_question",  "status": "failed" }
{ "type": "error", "reason": "question_gen_timeout", "recoverable": true,
  "code": "ERR_QUESTION_GEN_TIMEOUT", "step": "compose_question",
  "occurredAt": "2026-09-07T14:22:10Z" }
```

**UI states**

- 5a2-v2: 체크리스트를 유지한 상태에서 실패 단계만 ✕로 바꾸고 배너를 띄운다. `prepareCompleted` 수신 시 5b-v2로 전환.
- 5b-v2: `question`으로 질문 표시, `answer` 제출 → `answerReceived`까지 제출 중 상태 → 다음 `question`까지 입력 잠금 유지. `thinking`/`evidenceCheck` 인디케이터, `interviewEnd` 시 5c-v2로 이동.
- `evidenceCheck` 배너는 다른 서버 메시지 수신 시 해제, 30초간 메시지 없으면 타임아웃 해제.
- `error`는 `reason`과 `recoverable`을 함께 보고 아래 원인별 처리로 분기한다. `true`만으로 해당 턴이나 LLM 작업을 다시 실행하지 않으며, `false`이면 오류 안내와 해당 복구 경로를 표시한다.

`error.reason` 값

| reason | `code` | `recoverable` | 화면 처리 |
| --- | --- | --- | --- |
| `answer_too_long` | `ERR_ANSWER_TOO_LONG` | `true` | 같은 턴 재제출 |
| `answer_rejected` | `ERR_ANSWER_REJECTED` | `true` | 같은 턴 재제출 (저장 실패) |
| `question_failed` | `ERR_QUESTION_FAILED` | `true` | 허용된 시도 후 실패 안내·기록 보존·명시적 나가기 (아래 재시도 책임 참고) |
| `question_gen_timeout` | `ERR_QUESTION_GEN_TIMEOUT` | `true` | 준비 실패 화면 — REST `POST /interviews/{id}/prepare/retry` |
| `persona_build_failed` | `ERR_PERSONA_BUILD_FAILED` | `true` | 준비 실패 화면 — REST `POST /interviews/{id}/prepare/retry` |
| `criteria_set_failed` | `ERR_CRITERIA_SET_FAILED` | `true` | 준비 실패 화면 — REST `POST /interviews/{id}/prepare/retry` |
| `repo_analyze_failed` | `ERR_REPO_ANALYZE_FAILED` | `true` | 준비 실패 화면 — REST `POST /interviews/{id}/prepare/retry` |
| `github_api_rate_limited` | `ERR_GITHUB_RATE_LIMITED` | `true` | 준비 실패 화면 — 대기 후 REST `POST /interviews/{id}/prepare/retry` |
| `repo_unreachable` | `ERR_REPO_UNREACHABLE` | `false` | "레포에 접근할 수 없어요" — 레포 재선택 |
| `github_token_invalid` | `ERR_GITHUB_TOKEN_INVALID` | `false` | GitHub 재연동 유도 |

[0010 결정](../../spec/ai/decisions/0010-sprint1-interface-runtime-decisions.md)에 따라 LLM의 timeout/provider 오류·parse/schema 실패는 공통 호출 계층에서만 자동 1회 재시도한다(최초 호출 포함 최대 2회). semantic 실패는 재호출하지 않는다. `question_failed`의 기존 `recoverable: true`는 FE의 추가 재시도나 재연결을 통한 LLM 재호출을 허용한다는 뜻이 아니다. 허용된 시도 후에도 질문 생성에 실패하면 [기존 면접 실패 정책](../../spec/ai/features/interviewer.md#공개-메시지와-보류-항목)에 따라 오류 안내·기록 보존·명시적 나가기와 새 면접 흐름을 유지하며, 진행 중 면접의 새 수동 이어가기를 추가하지 않는다.

`recoverable: false`면 서버가 WS 연결을 닫는다. 오류 안내나 연결 종료만으로 DB 상태를 `completed` 또는 `abandoned`로 바꾸지 않는다. 정상 완료는 9번째 답변 처리 완료, `abandoned`는 명시적 나가기 확인·레포 재선택에 따른다. 오류 전달·종료 요청·실패 기록 복원의 실제 연결은 구현·검증 대상이다.

`code`는 화면에 그대로 노출하는 표시용 식별자로, `occurredAt`과 함께 배너 하단에 표기한다. `step`은 준비 단계 오류일 때만 값이 있고 진행 중 오류에서는 `null`이다.

`repo_unreachable`의 "레포 재선택"은 `GET /interviews/{id}`의 `runId`로 5a-v2에 진입한다.

### 2차 스프린트 — 음성 전환 (지금 구현 대상 아님)

1차는 텍스트 답변 전용이다 (`answerMode: "text"`). 2차에 음성이 추가되면 다음이 달라진다.

| 항목 | 1차 (text) | 2차 (voice) |
| --- | --- | --- |
| 답변 전송 | `answer` 1회 (JSON) | `answerStart` → 오디오 바이너리 → `answerEnd` |
| 전사 | 없음 | `transcript` 메시지 추가 |
| 질문 출력 | `question` 텍스트만 | `question` 뒤 TTS 오디오 + `questionEnd` |
| 답변 상한 | 2000자 | 초 단위 |
| 신규 error reason | — | `stt_failed` · `tts_failed` |

`answerMode`로 분기하므로 1차 구현 시 이 값을 무시하지 않는다.

**Failure**

핸드셰이크 실패

| 코드 | 상황 |
| --- | --- |
| 401 | `unauthenticated` — 로그인 쿠키 없음 · 세션 만료/유실/무효 |
| 409 | 이미 종료된 면접 세션 · `already_connected` |

> `already_connected`는 이전 연결이 살아 있는 경우다. 새로고침 재연결을 막지 않도록 서버는 기존 연결을 종료한 뒤 신규 연결을 허용한다.
> 

---

## 19. GET /interviews/{id}/report

**Response**

`200 OK`

```json
{
  "interviewId": "iv_001",
  "position": "Backend Developer",
  "positionLabel": "토스뱅크 백엔드 개발자",
  "totalScore": 74.5,
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
      "persona": "tech_lead",
      "tags": ["Architecture", "Trade-off"],
      "strengths": [
        "project-a에서 Redis를 도입한 배경과 전체 아키텍처 변화는 명확하게 설명했습니다."
      ],
      "improvements": [
        "TTL을 600초로 설정한 근거는 다른 대안과 비교해 구체적으로 제시하지 못했습니다."
      ],
      "disagreementSubmitted": false
    },
    {
      "persona": "hr_manager",
      "tags": ["협업", "기여도"],
      "strengths": [
        "결제 모듈에서 본인이 담당한 범위를 구체적으로 설명했습니다."
      ],
      "improvements": [
        "팀원과의 의사결정 과정은 충분히 드러나지 않았습니다."
      ],
      "disagreementSubmitted": false
    },
    {
      "persona": "domain_lead",
      "tags": ["도메인", "기업 적합성"],
      "strengths": [
        "결제 도메인의 정합성 요구를 이해하고 있었습니다."
      ],
      "improvements": [
        "금융권 규제 관점의 고려가 부족했습니다."
      ],
      "disagreementSubmitted": false
    }
  ],
  "coverage": {
    "totalRequirements": 8,
    "coveredRequirements": 5,
    "uncoveredRequirements": ["Kafka 운영 경험", "Kubernetes 기반 배포 경험"]
  },
  "turns": [
    {
      "turn": 1,
      "persona": "tech_lead",
      "question": "project-a에서 Redis를 캐시로 도입한 이유를 설명해주세요.",
      "answer": "상품 조회 성능을 높이기 위해 캐시로 사용했습니다."
    }
  ],
  "repositoryNames": ["project-a", "payment-service"],
  "completedAt": "2026-09-01T15:20:00Z"
}
```

`202 Accepted` — 리포트 생성 중 (실패가 아니다)

```json
{ "status": "generating", "retryAfter": 3 }
```

`retryAfter` 간격으로 폴링한다. 이 `retryAfter`는 본문 최상위 필드이며, 공통 에러 객체의 `error.retryAfter`와 위치가 다르다.

`scores`는 6개, `agentFeedbacks`는 3개 고정.

| 필드 | 타입 | null |
| --- | --- | --- |
| `interviewId` | string | ❌ |
| `position` | string | ❌ |
| `positionLabel` | string | ❌ |
| `totalScore` | number | ❌ |
| `headline` | string | ❌ |
| `summary` | string | ❌ |
| `scores[].key` | ScoreKey | ❌ |
| `scores[].label` | string | ❌ |
| `scores[].score` | number | ❌ |
| `agentFeedbacks[].persona` | Persona | ❌ |
| `agentFeedbacks[].tags` | string[] | ❌ |
| `agentFeedbacks[].strengths` | string[] | ❌ |
| `agentFeedbacks[].improvements` | string[] | ❌ |
| `agentFeedbacks[].disagreementSubmitted` | boolean | ❌ |
| `coverage.totalRequirements` | number | ❌ |
| `coverage.coveredRequirements` | number | ❌ |
| `coverage.uncoveredRequirements` | string[] | ❌ |
| `turns[].turn` | number | ❌ |
| `turns[].persona` | Persona | ❌ |
| `turns[].question` | string | ❌ |
| `turns[].answer` | string | ✅ |
| `repositoryNames` | string[] | ❌ |
| `completedAt` | string | ❌ |

`positionLabel`은 회사명이 포함된 표시용 문구다. `coverage`는 `company_job_fit` 점수의 근거로 함께 표시한다.

> 리포트는 면접당 1개이며 별도 `reportId`를 발급하지 않는다. 이의 제기(#21)도 `interviewId`를 식별자로 사용한다.
>

**UI states**

5c-v2 탭 구조.

| 탭 | 필드 |
| --- | --- |
| 종합리포트 | `headline` · `totalScore` · `summary` · `scores` · `coverage` |
| 면접관별 피드백 | `agentFeedbacks` — Sprint 1 이의 제기 버튼은 비활성. `disagreementSubmitted` 연동은 #21의 후속 범위 |
| 면접 기록 | `turns` |

**Failure**

`409` — `report_unavailable` (진행된 턴 0개, 리포트 없이 안내)

---

## 20. POST /interviews/{id}/retry

원본 면접 세션의 `runId`·레포 조합을 복사해 새 세션을 만든다.

허용 상태는 FE의 기존 `original_not_completed` 설명과 BE 명세의 `completed`·`abandoned` 허용이 다르며 OpenAPI는 409만 정의한다. 이번 문서 정리에서는 세부 조건을 임의 확정하지 않는다([report의 계약 차이](../../spec/frontend/features/report.md#계약-차이와-구현-범위)).

**Request**

없음.

**Response**

`201 Created`

```json
{
  "sessionId": "sess_new456",
  "interviewId": "iv_002"
}
```

새 `interviewId`가 발급되므로 하나의 면접에 리포트가 여러 개 생기지 않는다.

**UI states**

5c-v2 `재도전` 버튼 클릭 시 호출. 성공 시 `interviews` 캐시 무효화 후 `/interview/iv_002/prepare`(5a2-v2)로 이동.

**Failure**

| 코드 | reason |
| --- | --- |
| 409 | `original_not_completed` · `repository_unavailable` · `session_limit_exceeded` |
| 410 | `run_expired` |

`repository_unavailable`은 원본 레포가 삭제·private 전환된 경우다.

---

## 21. POST /interviews/{id}/feedback-disagreements

**범위 주의:** [이관 현황](../../spec/shared/contracts/migration.md)의 기존 결정에 따라 Sprint 1은 API 제공·호출 대상이 아니며 버튼은 비활성이다. OpenAPI·FE 타입·mock에 계약이 남아 있어 아래 구조와 번호를 보존하지만, 이를 Sprint 1 기능 활성화로 해석하지 않는다. 계약 파일 잔존 내용의 정합화와 실제 구현은 후속 작업이다.

`{id}`는 `interviewId`다. 리포트는 면접당 1개이고 `GET /interviews/{id}/report` 응답에 `reportId`가 없으므로, FE가 보유한 식별자는 `interviewId`뿐이다. 서버가 내부적으로 `reports` 행을 따로 관리하더라도 경로 파라미터는 `interviewId`를 받는다.

**Request**

```json
{
  "persona": "tech_lead",
  "reasonType": "factual_error",
  "comment": "TTL 근거를 설명했는데 반영되지 않았습니다."
}
```

| 필드 | 타입 | 필수 |
| --- | --- | --- |
| `persona` | Persona | ✅ |
| `reasonType` | ReasonType | ✅ |
| `comment` | string (최대 500자) | ❌ |

`reasonType` 화면 표기

| 값 | 표기 |
| --- | --- |
| `factual_error` | 사실과 다름 |
| `insufficient_basis` | 근거 부족 |
| `overly_harsh` | 과도한 평가 |
| `unclear_intent` | 질문 의도 불명확 |
| `other` | 기타 |

**Response**

`204 No Content`

**UI states**

Sprint 2 참고 흐름: 5c-v2 이의 제기 모달 제출 → 성공 시 `disagreementSubmitted: true`로 버튼 비활성(재조회 기반, 로컬 플래그 아님) → `interview(id).report` 캐시 무효화. 제출 단위는 `(interviewId, persona)`, persona당 1회. Sprint 1 호출·모달 구현 지시가 아니다.

**Failure**

| 코드 | reason |
| --- | --- |
| 404 | `not_found` |
| 409 | `already_submitted` |

---

## queryKey 매핑

| 경로 | queryKey |
| --- | --- |
| `GET /me` | `['me']` |
| `GET /me/home` | `['home']` |
| `GET /me/interviews?page=N` | `['interviews', { page }]` |
| `GET /analysis-runs/{runId}` | `['analysis-run', runId]` |
| `GET /analysis-runs/{runId}/result` | `['analysis-run', runId, 'result']` |
| `GET /analysis-runs/{runId}/candidates?page=N` | `['analysis-run', runId, 'candidates', { page }]` |
| `GET /interviews/{id}` | `['interview', id]` |
| `GET /interviews/{id}/report` | `['interview', id, 'report']` |

계층 구조라 `['interview', id]`를 무효화하면 하위 `report`까지 함께 무효화된다. `POST /interviews/{id}/feedback-disagreements`도 같은 `interviewId`를 쓰므로 무효화 대상이 그대로 대응된다.

`POST /auth/refresh`(#3)는 Sprint 2 예약이다. Sprint 1에는 queryKey도 호출부도 두지 않는다.

## 캐시 무효화

| 시점 | 무효화 |
| --- | --- |
| `POST /interviews` | `interviews` |
| `POST /interviews/{id}/retry` | `interviews` |
| 면접 완료 (리포트 생성) | `home`, `interviews` |
| 피드백 이의 제출 | `interview(id).report` |
| `GET /auth/github/link/callback` 복귀 | `me`, `home` |
| `POST /auth/logout` | 전체 `clear()` |
| `401 unauthenticated` | 전체 `clear()` 후 `/login` |

---

## 최종 엔드포인트 목록

| # | 메서드 | 경로 | 구현 방식 | 인증 |
| --- | --- | --- | --- | --- |
| 1 | GET | `/auth/github/login` | 브라우저 이동 | 불필요 |
| 2 | GET | `/auth/github/callback` | 프론트 무관 | 불필요 |
| 3 | POST | `/auth/refresh` | Sprint 2 예약 | Sprint 1 해당 없음 |
| 4 | POST | `/auth/logout` | fetch | `devon_session` (만료·없음도 204) |
| 5 | GET | `/me` | fetch | `devon_session` |
| 6 | GET | `/me/profile` | fetch | `devon_session` |
| 7 | GET | `/auth/github/link` | 브라우저 이동 | `devon_session` |
| 8 | GET | `/auth/github/link/callback` | 프론트 무관 | `devon_session` |
| 9 | GET | `/me/home` | fetch | `devon_session` |
| 10 | GET | `/me/interviews` | fetch | `devon_session` |
| 11 | POST | `/documents/preview` | fetch (multipart) | `devon_session` |
| 12 | POST | `/analysis-runs` | fetch | `devon_session` |
| 13 | GET | `/analysis-runs/{runId}/events` | EventSource | `devon_session` |
| 14 | GET | `/analysis-runs/{runId}` | fetch | `devon_session` |
| 15 | GET | `/analysis-runs/{runId}/result` | fetch | `devon_session` |
| 16 | POST | `/interviews` | fetch | `devon_session` |
| 17 | GET | `/interviews/{id}` | fetch | `devon_session` |
| 18 | GET *(Upgrade)* | `/ws/interviews/{sessionId}` | WebSocket | `devon_session` |
| 19 | GET | `/interviews/{id}/report` | fetch | `devon_session` |
| 20 | POST | `/interviews/{id}/retry` | fetch | `devon_session` |
| 21 | POST | `/interviews/{id}/feedback-disagreements` | 계약 잔존, Sprint 1 제공·호출 제외 | `devon_session` |
| 22 | GET | `/analysis-runs/{runId}/candidates` | fetch | `devon_session` |

기존 번호 22개를 유지한다(기존 색인 21개 + Sprint 2 예약 #3). #21은 계약이 잔존하지만 Sprint 1 제공·호출 대상에서 제외한다. 이 숫자는 실제 제공 API 수나 구현 완료 수가 아니며, 준비 재시도 등 별도 명세의 추가 경로도 전체 개수에 섞어 세지 않는다.

`shared/api.ts`에 넣지 않는 것: 1, 2, 7, 8(브라우저 이동 또는 프론트 무관). 3은 Sprint 2 예약이므로 Sprint 1에서는 호출하지 않는다.

### 구현 방식별 분류

| 방식 | 엔드포인트 |
| --- | --- |
| 브라우저 이동 | 1, 7 |
| 프론트 무관 (서버 302) | 2, 8 |
| `fetch` GET | 5, 6, 9, 10, 14, 15, 17, 19, 22 |
| `fetch` POST | 4, 12, 16, 20 |
| 계약 잔존, Sprint 1 제공·호출 제외 | 21 (이의 제기, 기존 Sprint 2 범위) |
| Sprint 2 예약 | 3 (`POST /auth/refresh`) |
| `fetch` POST (multipart) | 11 |
| `EventSource` | 13 |
| `WebSocket` | 18 |

---

## 화면별 API 사용표

`R` = 조회, `W` = 호출(상태 변경), `S` = 스트리밍 구독

| 화면 | 코드 | 사용 API |
| --- | --- | --- |
| 로그인 | — | `/auth/github/login` (이동) |
| 홈 | `/home` | `/me/home` R |
| 마이페이지 | 1a | `/me/profile` R · `/me/interviews` R · `/auth/logout` W |
| 공고·문서 입력 | 1c / 4-1-v2 | `/documents/preview` W (파일 선택 시) · `/analysis-runs` W |
| 분석 진행 | 4-2-v2 | `/analysis-runs/{runId}` R (스냅샷) · `/analysis-runs/{runId}/events` S |
| 분석 실패 | 4-3-v2 | `/analysis-runs/{runId}` R · `/analysis-runs` W (재시도) · `/auth/github/link` (이동) |
| 레포 확정 | 5a-v2 | `/analysis-runs/{runId}/result` R · `/analysis-runs/{runId}/candidates` R (더보기) · `/interviews` W |
| 면접 준비 | 5a2-v2 | `/interviews/{id}` R · `/ws/interviews/{sessionId}` S |
| 면접 준비 실패 | 1b | `/interviews/{id}` R (`lastError`·`runId`) · `/interviews/{id}/prepare/retry` W · `/analysis-runs/{runId}/result` R (레포 재선택) |
| 면접 진행 | 5b-v2 | `/ws/interviews/{sessionId}` S · `/interviews/{id}` R (재연결 복구) |
| 리포트 | 5c-v2 | `/interviews/{id}/report` R · `/interviews/{id}/retry` W. 이의 제기는 Sprint 1 호출 제외(#21 범위 주의) |
| 전역 | — | `/me` R (인증 가드) · `/auth/logout` W · 401 시 캐시 정리와 로그인 이동 |

> 화면별 상세 설명은 각 엔드포인트의 `UI states`를 참고한다. 이 표는 화면 하나가 여러 엔드포인트를 조합하는 지점만 빠르게 훑기 위한 색인이다.
> 

---

## 화면 전이

```
/login
  └─ /auth/github/login → GitHub → /auth/github/callback → /home

/home
  ├─ 아바타 클릭 → 1a 마이페이지
  │    ├─ 리포트 보기 → 5c-v2
  │    └─ 로그아웃 → /login
  └─ 새 면접 시작 → 1c

1c      공고·문서 입력 (공고 URL 필수, 문서 선택)
  ├─ 파일 선택 → POST /documents/preview → documentId
  └─ POST /analysis-runs { postingUrl, documentId? } → 202 → 4-2-v2
       └─ documentId 생략 시 doc_extract = skipped

4-2-v2  분석 진행
  ├─ completed → 5a-v2
  └─ failed    → 4-3-v2 ─(재시도)→ 4-2-v2

5a-v2   레포 확정
  └─ POST /interviews → 201 → 5a2-v2

5a2-v2  면접 준비 (WS 연결)
  ├─ prepareCompleted → 5b-v2
  └─ error            → 1b ─(POST /interviews/{id}/prepare/retry)→ 5a2-v2
                           └─(레포 다시 선택 · runId)→ 5a-v2

5b-v2   면접 진행 (WS 유지)
  ├─ interviewEnd → 5c-v2
  └─ 명시적 이탈 확인·레포 재선택 → status='abandoned' (연결 끊김·인증 만료만으로 전환하지 않음)

5c-v2   리포트
  └─ POST /interviews/{id}/retry → 201 → 5a2-v2
```

`GET /interviews/{id}`의 `status`로 새로고침·재진입 시 도달할 화면을 결정한다.

| `status` | 화면 |
| --- | --- |
| `preparing` | 5a2-v2 |
| `in_progress` | 5b-v2 (`turns` 복구) |
| `completed` | 5c-v2 |
| `preparing_failed` | 1b (`lastError`로 배너 렌더, `runId`로 레포 재선택 경로 확보) |
| `abandoned` | 안내 후 `/home` |

---

## 변경 이력

| 일자 | 변경 |
| --- | --- |
| 2026-09-08 | `stepKey` 4개 → **7개** (`doc_extract` · `repo_select` · `repo_detail` · `jd_fetch` · `jd_extract` · `repo_analyze` · `match_score`) |
| 2026-09-08 | `agentRole` → **`persona`**, 값 `senior_developer`/`manager` → **`hr_manager`/`domain_lead`** |
| 2026-09-08 | 에러 reason `jd_parse_failed` → **`jd_fetch_failed`/`jd_extraction_failed`** |
| 2026-09-10 | **인증 방식 Redis 세션 + 쿠키 → JWT + HttpOnly 쿠키** (Access 15분 / Refresh 14일) |
| 2026-09-10 | **`POST /auth/refresh` 신규 추가**, 리프레시 토큰 로테이션·재사용 감지 |
| 2026-09-10 | **쿠키명 `session` → `accessToken` / `refreshToken`**, OAuth `state` 저장 위치 세션 → `oauthState` 쿠키 |
| 2026-09-10 | **인증 에러 reason 신설**: `access_token_expired` · `access_token_invalid` · `refresh_token_invalid` · `account_suspended` · `account_withdrawn` |
| 2026-09-10 | 에러 reason `token_invalid` → **`github_token_invalid`** (DEVON JWT와 구분) |
| 2026-09-10 | **배포 CloudFront 통합** — same-origin이므로 CORS 불필요, API base URL 상대경로 |
| 2026-09-10 | `interviewStatus`에 **`preparing`** 추가, `abandonedQ` 오타 수정 → `abandoned` |
| 2026-09-10 | `analysisStatus`에 **`syncing`** 추가 (`initial_sync` 진행 중) |
| 2026-09-10 | `jdRequirements` `string[]` → **객체 배열** (`id`·`category`·`text`·`displayOrder`) — `category` 그룹핑·커버리지 계산에 필요 |
| 2026-09-10 | `/analysis-runs/{runId}/result`의 `repositories`에 **`fullName`·`description`·`topics`·`stars`·`forks`·`commitCount`·`userCommitCount`·`pushedAt`·`status`·`errorCode`·`candidateSource`·`matchedRequirementIds` 추가**, `languages` `string[]` → 비율 객체 배열 |
| 2026-09-10 | **`mentionedRepoCount`·`matchedRepoCount` 추가** (포트폴리오 레포 매칭 안내) |
| 2026-09-10 | **`GET /me/repositories` 신규 추가** ("내 레포 더 보기") |
| 2026-09-10 | `POST /interviews` `repositoryIds` **상한 5개**, `too_many_repositories` reason 추가 |
| 2026-09-10 | WS **`answerReceived` 메시지 추가**, `error`에 **`recoverable`** 필드 추가, 오디오 포맷 명시 |
| 2026-09-10 | WS `error.reason`에 **`repo_unreachable`** 추가 |
| 2026-09-10 | 리포트에 **`positionLabel`·`coverage` 추가** |
| 2026-09-10 | SSE에 **`progress`** 이벤트, `GET /analysis-runs/{runId}`에 **`progress`** 필드 추가 |
| 2026-09-10 | **최종 엔드포인트 목록·화면별 API 사용표·화면 전이도 추가** |
| 2026-09-10 | **`GET /me/profile` 신규 추가** (마이페이지 1a) — `loginId`·`joinedAt`·`github.publicRepoCount`·`interviewSummary` |
| 2026-09-10 | `/me/interviews`에 **`averageScore` 추가** (마이페이지 이력 헤더) |
| 2026-09-10 | `stepStatus`에 **`failed`** 추가 — 준비 단계 실패를 체크리스트에 표시 (1b) |
| 2026-09-11 | BE Sprint 1 FIX 계약 정합화 — **`POST /documents/preview` 신규 추가** (파일 업로드는 `analysis-runs`가 아닌 이 엔드포인트로 먼저 보내 `documentId` 발급) |
| 2026-09-11 | `POST /analysis-runs` **`multipart/form-data` → `application/json`**, 필드 `jobUrl`→**`postingUrl`** + `documentId`(선택). `coverLetter`·`portfolioFile`·`portfolioUrl` 필드 제거 |
| 2026-09-11 | **`GET /me/repositories` 폐기 → `GET /analysis-runs/{runId}/candidates?page=N`로 대체** — "더보기"는 전체 공개 레포 목록이 아니라 같은 run의 다음 랭킹 배치임이 BE 계약(`spec/backend/features/analysis-run.md`)으로 확인됨 |
| 2026-09-11 | `ForFE.md` FE 결정 회신 — WS는 `sessionId` 유지, 라우트 `:id`는 `interviewId`, `questionEnd`는 Sprint 1에서 제거, abandoned는 즉시 판정 안 하고 재연결 실패 시에만, CSRF는 SameSite=Lax만(토큰 없음), 포트폴리오 매칭은 개수만 노출 |
| 2026-09-11 | `interviewStatus`에 **`preparing_failed`** 추가, `GET /interviews/{id}` 응답에 **`lastError`** 필드 신규 추가 (새로고침 시 WS 없이 1b 배너 렌더용) |
| 2026-09-10 | WS **`prepareRetry`** 클라이언트 메시지 추가 — 실패 단계부터 재실행, 세션·레포 유지 |
| 2026-09-10 | WS `error`에 **`code`·`step`·`occurredAt` 추가**, `reason` 세분화 (`question_gen_timeout` · `persona_build_failed` · `criteria_set_failed` · `repo_analyze_failed` · `github_api_rate_limited`), `prepare_failed` 제거 |
| 2026-09-10 | 공고 URL 필수 명시 — "공고 없이 진행" 경로 없음 |
| 2026-09-10 | 화면 코드 정정: 공고 입력 `1c`, 마이페이지 `1a`, 면접 준비 실패 `1b` |
| 2026-09-10 | **1차 스프린트 답변 방식 텍스트로 확정** — `answerMode: text`. WS 답변 전송을 `answerStart`→오디오→`answerEnd`에서 **`answer` 단일 메시지**로 변경, 상한 2000자 |
| 2026-09-10 | WS `transcript`·`questionEnd` 메시지 **제거**, `error.reason`에서 `stt_failed`·`tts_failed` **제거**, `answer_rejected` 추가 (모두 2차 음성 전환 시 복원) |
| 2026-09-10 | `enum`에 **`answerMode`** 추가, `GET /interviews/{id}` 응답에 **`answerMode`** 필드 추가 |
| 2026-09-10 | 5a2-v2 마이크·스피커 점검 섹션 1차 미표시 |
| 2026-09-11 | 문서 구조 전면 개편 — 엔드포인트별 **Endpoint/Request/Response/UI states/Failure** 5단 구조로 재구성. 내용 변경 없음(재배치만) |
| 2026-09-17 | `stepStatus`에 **`skipped`** 추가 — 자기소개서·포트폴리오는 선택 입력이므로 `documentId` 없이 생성된 run에서 `doc_extract`가 실행되지 않는다. `pending`으로 두면 체크리스트에 영구히 채워지지 않는 행이 남고, `failed`(✕)로 두면 정상 경로를 오류로 오인한다. #13 SSE `step` 이벤트로도 동일하게 전송하며, `prepareStepKey`에는 적용하지 않는다 |
| 2026-09-17 | `GET /interviews/{id}` 응답에 **`runId`** 필드 추가 — 1b(준비 실패)·`repo_unreachable`에서 "레포 다시 선택"으로 5a-v2에 진입하려면 `/analysis-runs/{runId}/result`가 필요한데, 새로고침 시 FE가 `runId`를 보유하지 않아 경로가 끊겼다 |
| 2026-09-17 | **`POST /reports/{id}/feedback-disagreements` → `POST /interviews/{id}/feedback-disagreements`** — `{id}`는 `interviewId`다. 리포트는 면접당 1개이고 #19 응답에 `reportId`가 없어 FE가 보유한 식별자는 `interviewId`뿐이다. 제출 단위 표기도 `(reportId, persona)` → `(interviewId, persona)`로 정정, `404 not_found` 추가 |
| 2026-09-17 | #13 SSE에 **구독 전 `GET /analysis-runs/{runId}` 스냅샷 호출 명시** — 스트림은 구독 시점 이후 델타만 전달하므로 새로고침 시 이전 `step` 이벤트를 복구할 수 없다 |
| 2026-09-17 | #19의 **`202 Accepted`를 Failure → Response로 이동** (생성 중은 실패가 아님), `error.retryAfter`와 본문 최상위 `retryAfter`의 위치 차이 명시 |
| 2026-09-22 | [공통 0003](../../spec/shared/decisions/0003-sprint1-session-auth.md): Sprint 1은 기존 Redis·HttpOnly `devon_session`·14일 sliding 세션으로 확정. JWT·refresh 및 #3은 Sprint 2로 이관. 기존 번호와 과거안은 보존하며 실제 인증 구현·검증은 후속 작업으로 구분 |
