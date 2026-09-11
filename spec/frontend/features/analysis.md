# analysis

상태: 초안 — frontend/md/features/analysis.md에서 이관.

## 목표 + 화면 구성

채용 공고와 첨부 문서를 받아 GitHub 레포를 분석하고, 면접에 쓸 레포를 사용자가 확정한다. 면접 생성까지가 이 기능의 범위다.

| 화면 | 코드 | 구성 |
| --- | --- | --- |
| 공고·문서 입력 | — | 공고 URL 입력폼(필수) + 자기소개서 업로더 + 포트폴리오 업로더 + `분석 시작` |
| 분석 진행 | 4-2-v2 | 7단계 체크리스트 + 진행률 |
| 분석 실패 | 4-3-v2 | 실패 사유 배너 + 재시도/안내 액션 |
| 레포 확정 | 5a-v2 | 좌측 레포 카드 리스트(체크박스) + 우측 공고 요구사항 리스트 + `내 레포 더 보기` + 확정 버튼 |

### 공고 입력 규칙

| 항목 | 필수 | 형식 | 상한 |
| --- | --- | --- | --- |
| 공고 URL | ✅ | URL | — |
| 자기소개서 | ❌ | PDF, DOCX | 10MB |
| 포트폴리오 | ❌ | PDF 또는 링크 | 20MB |

- 라벨에 `* 필수` 배지, 나머지는 `(선택)`
- URL이 비었거나 URL 형식이 아니면 `분석 시작` 버튼 비활성 (회색). 눌러도 진행되지 않고 입력창 아래 안내 문구
- 공고 URL은 Sprint 1에서 Wanted만 허용한다 (BE `POST /analysis-runs` 고정 사양)
- "공고 없이 진행 (GitHub 기반)" 경로는 없다
- 스텝 인디케이터 `1 / 3`

### 문서 Preview (BE 설계에 맞춤)

파일 업로더는 `POST /analysis-runs`에 파일을 직접 실어 보내지 않는다. BE는 2단계 구조다.

1. 파일 선택 즉시 `POST /documents/preview`로 업로드 → 텍스트·GitHub URL 추출 → `documentId` + `status`(`succeeded`/`partial`/`failed`) 반환
2. `분석 시작` 클릭 시 `POST /analysis-runs`에 `documentId`(선택)만 실어 보낸다

지원 형식: `.pdf`(텍스트 레이어 있는 PDF만, 스캔 이미지 PDF는 추출 실패), `.docx`, `.txt`, `.md`. 최대 10MB. `.hwp`·이미지·`.ppt/.pptx`는 미지원.

응답 필드(`spec/shared/contracts/openapi.yaml` `DocumentPreviewResponse` 기준):

| 필드 | 타입 | 비고 |
| --- | --- | --- |
| `documentId` | string | — |
| `status` | `succeeded`\|`partial`\|`failed` | — |
| `fileName` | string | — |
| `sizeBytes` | number | — |
| `extractedGithubUrls` | string[] | — |
| `truncated` | boolean (선택) | 길이 초과로 축약됐는지 |
| `failureReason` | string \| null (선택) | `status: 'failed'`일 때만 |

요청에는 선택 필드 `postingUrl`(공고 URL)도 있다 — JD 키워드 기반 축약에 쓰인다. 공고 URL을 먼저 입력받은 뒤 파일을 업로드하면 이 값을 함께 보내는 편이 축약 품질에 유리하다. 파일이 공고 URL보다 먼저 선택되면 이 필드 없이 호출해도 된다(선택 필드).

`status === 'failed'`는 hard blocker가 아니다 — "문서 없이 계속 진행" 선택 시 `documentId`를 `analysis-runs` 요청에서 뺀다.

**`PENDING_TEAM`**: BE 계약의 `documentId`는 단수다. 공고 입력 화면은 자기소개서·포트폴리오 업로더가 2개인데 이걸 어떻게 매핑할지(각각 별도 preview 호출 후 한쪽만 채택할지, 병합할지) 미정 — 팀 확인 필요.

### 4-2-v2 체크리스트 7단계

`doc_extract` → `repo_select` → `repo_detail` → `jd_fetch` → `jd_extract` → `repo_analyze` → `match_score`

각 단계 `status`: `pending` | `running` | `completed` | `failed`

### 5a-v2 레포 카드

| 요소 | 필드 |
| --- | --- |
| 이름 | `name` |
| 별·포크 | `stars` · `forks` |
| 설명 | `description` |
| 언어 그래프 | `languages[]` (`name`, `ratio`) |
| 토픽 태그 | `topics[]` |
| 최신성·커밋 | `pushedAt` · `commitCount` (내 커밋 `userCommitCount`) |
| 추천 근거 | `recommendReason` |
| 링크 | `fullName` 조립 |
| 배지 | `candidateSource`(📎 포트폴리오) · `recommended`(AI 추천) |

- `recommended: true`인 레포는 기본 체크 상태. 최대 5개
- `status === 'failed'`면 카드 회색 + `errorCode` 문구, `matchScore`·`recommendReason`은 `null`
- `status === 'partial'`은 카드 표시, 별도 문구 없음
- 선택 상한 5개

### 5a-v2 우측 공고 리스트

`jdRequirements[]`를 `type`으로 그룹핑(`required` / `preferred`). 응답 배열 순서 그대로 표시(`displayOrder` 없음). 읽기 전용, 편집 불가.

BE 협의(2026-09-11)로 필드명 `category`→`type`, `responsibility` 카테고리·`displayOrder` 필드는 제거했다 — 화면 요구사항 표시에 필요 없다고 판단.

### 포트폴리오 매칭 안내

`mentionedRepoCount !== matchedRepoCount`일 때 "포트폴리오에 언급된 3개 중 2개를 찾았어요" 안내. 매칭 실패는 정상 상황이므로 오류로 처리하지 않는다.

## 화면 이동 순서

```
/home [새 면접 시작] → 공고 입력

공고 입력 (공고·문서 입력)
  ├─ 파일 선택 → POST /documents/preview → documentId (즉시, 백그라운드)
  └─ [분석 시작] → POST /analysis-runs { postingUrl, documentId? } → 202 { runId } → 4-2-v2

4-2-v2  분석 진행 (EventSource 구독)
  ├─ completed 수신 → 5a-v2
  └─ failed 수신    → 4-3-v2

4-3-v2  분석 실패
  ├─ [다시 시도]        → 공고 입력 화면 값 유지 후 재호출 → 4-2-v2
  ├─ [GitHub 재연동]    → /auth/github/link   (github_token_invalid)
  └─ 재시도 불가 사유    → 안내만, 버튼 숨김   (no_public_repo, user_not_found)

5a-v2  레포 확정
  ├─ [내 레포 더 보기] → GET /analysis-runs/{runId}/candidates?page=N
  │      ├─ 200 → 다음 배치 카드 추가
  │      └─ 202 { status: "analyzing", retryAfter } → 안내 후 폴링
  └─ [확정]                  → POST /interviews → 201 → 5a2-v2
```

## API 연동

| # | 엔드포인트 | 화면 | queryKey |
| --- | --- | --- | --- |
| — | `POST /documents/preview` | 공고 입력 | — (multipart) |
| 12 | `POST /analysis-runs` | 공고 입력, 4-3-v2 | — (JSON) |
| 13 | `GET /analysis-runs/{runId}/events` | 4-2-v2 | — (EventSource) |
| 14 | `GET /analysis-runs/{runId}` | 4-2-v2, 4-3-v2 | `['analysis-run', runId]` |
| 15 | `GET /analysis-runs/{runId}/result` | 5a-v2 | `['analysis-run', runId, 'result']` |
| — | `GET /analysis-runs/{runId}/candidates?page=N` | 5a-v2 더 보기 | `['analysis-run', runId, 'candidates', { page }]` |
| 16 | `POST /interviews` | 5a-v2 확정 | — |

기존 `GET /me/repositories`(`frontend/docs/api-spec.md` 2026-09-10 추가분, `['repositories', { page }]`)는 BE `spec/backend/features/analysis-run.md`(Sprint 1 FIX)와 맞지 않아 이 문서에서는 채택하지 않는다. BE는 run에 종속된 candidate 배치 방식이고, 기존 안은 필터 탈락분을 포함한 전체 공개 레포 목록이라 동작이 다르다 — `frontend/docs/api-spec.md` 쪽 갱신은 팀 확인 필요.

### POST /documents/preview

`multipart/form-data`. **`Content-Type` 헤더를 직접 지정하지 않는다** — 브라우저가 boundary와 함께 자동 생성해야 한다.

| 코드 | reason | 처리 |
| --- | --- | --- |
| 413 | `file_too_large` | 업로더 에러 |
| 415 | `unsupported_media_type` | 업로더 에러 |

401 재시도 시 `FormData`를 재전송해야 한다. 인터셉터가 요청 바디를 복제해 보관하도록 구현한다(`fetch`의 body는 1회 소비된다).

### POST /analysis-runs

일반 JSON 요청. 파일을 직접 싣지 않는다.

```json
{ "postingUrl": "https://www.wanted.co.kr/wd/123456", "documentId": "doc_abc123" }
```

`documentId`는 선택이며 `POST /documents/preview`에서 발급된 값만 허용한다.

응답 `202`:
```json
{ "runId": "run_abc123", "status": "running", "reused": false }
```

`status`는 `RunStatus`(`running`/`completed`/`failed`), `reused: true`면 동일 fingerprint의 진행 중인 run을 재사용한 것이다(새 job을 만들지 않음).

| 코드 | reason | 처리 |
| --- | --- | --- |
| 400 | `job_url_required` | 입력창 에러 |
| 400 | `unsupported_site` | "지원하지 않는 사이트예요" |
| 400 | `url_unreachable` | "공고를 불러올 수 없어요" |
| 409 | `run_in_progress` | 응답의 `runId`로 4-2-v2 이동 |

### SSE 구독

```javascript
new EventSource(`/api/analysis-runs/${runId}/events`, { withCredentials: true })
```

| type | 필드 | 처리 |
| --- | --- | --- |
| `step` | `key`, `status` | 체크리스트 갱신 |
| `progress` | `value` (0~100) | 진행률 바 |
| `completed` | — | 5a-v2 이동 |
| `failed` | `reason` | 4-3-v2 전환 |

`withCredentials: true`가 없으면 쿠키가 안 실려 401이다. `EventSource`는 응답 바디를 못 읽어 `onerror`에서 상태 코드를 알 수 없으므로, `onerror` 시 `GET /analysis-runs/{runId}`를 1회 호출해 확인한다.

**`/api` 프리픽스 직접 붙여야 함**: `EventSource`는 `shared/api.ts` 래퍼를 거치지 않아 `/api`를 자동으로 붙여주지 않는다. 위 예시처럼 URL에 직접 포함해야 CloudFront rewrite(`/api/:path*` → BE)를 탄다.

인증은 연결 수립 시 1회 검증. 연결 유지 중 토큰 만료로 스트림이 끊기지 않는다.

### failureReason 분기 (4-3-v2)

| 값 | 문구 방향 | 재시도 |
| --- | --- | --- |
| `no_public_repo` | 안내만 | ❌ 버튼 숨김 |
| `user_not_found` | 안내만 | ❌ |
| `rate_limited` | 대기 시간 안내 (`retryAfter`) | 시간 후 |
| `github_token_invalid` | 재연동 강조 | 재연동 후 |
| `jd_fetch_failed` | 공고 URL 입력창 강조 | ✅ |
| `jd_extraction_failed` | 공고 URL 입력창 강조 | ✅ |
| `not_a_job_posting` | "채용 공고가 아닌 것 같아요" | ✅ |
| `doc_extract_failed` | 첨부 파일 안내 | ✅ |
| `llm_timeout` | "분석이 지연되고 있어요" | ✅ |

**분석 실패도 HTTP 200이다.** `status: "failed"` + `failureReason`으로 판단한다. 레포 일부만 실패한 경우는 잡 실패가 아니며 `status: "completed"`로 온다.

### 레포별 errorCode (5a-v2 카드)

| `errorCode` | 문구 | 재시도 |
| --- | --- | --- |
| `llm_timeout` | "분석이 지연되고 있어요" | 자동 1회 |
| `parse_failed` | "분석이 지연되고 있어요" | 자동 1회 |
| `input_too_large` | "정보가 부족해요" | ❌ |
| `no_readme` | "정보가 부족해요" | ❌ |
| `github_token_invalid` | "GitHub 재연동이 필요해요" | 재연동 후 |

### POST /interviews

```json
{ "runId": "run_abc123", "repositoryIds": ["r_001", "r_002"] }
```

| 코드 | reason |
| --- | --- |
| 400 | `no_repository_selected` · `invalid_repository` · `too_many_repositories` |
| 409 | `session_limit_exceeded` |
| 410 | `run_expired` |

성공 시 `interviews` 캐시 무효화.

## 상태 요구사항

### 공고 입력

| 상태 | 용도 |
| --- | --- |
| `jobUrl` | 입력 중인 URL 텍스트 |
| `coverLetterFile` | 선택된 파일 객체 |
| `portfolioFile` / `portfolioUrl` | 선택된 파일 또는 링크 |
| `isDragging` | 드래그 오버 하이라이트 (업로더별) |
| `isUrlValid` | `분석 시작` 버튼 활성 여부 (파생값) |
| `isSubmitting` | 중복 제출 방지 |

### 4-2-v2

| 상태 | 용도 |
| --- | --- |
| `steps` | SSE로 누적한 단계별 status |
| `progress` | SSE `progress.value` |

SSE 스트림 상태는 TanStack Query로 관리하지 않는다. 컴포넌트 로컬 또는 별도 store에 둔다.

### 5a-v2

| 상태 | 용도 |
| --- | --- |
| `selectedRepoIds` | 체크된 레포 (초기값 = `recommended: true`). 상한 5개 |
| `isMoreExpanded` | `내 레포 더 보기` 확장 여부 |
| `morePage` | 더 보기 목록 페이지 |
| `morePageStatus` | 페이지별 `idle` / `analyzing`(202 대기 중) |

`selectedRepoIds` 초기화 타이밍에 주의한다. `result` 쿼리 응답이 도착한 뒤 1회만 세팅해야 하며, 리렌더마다 재설정하면 사용자 선택이 덮어써진다.

## 검증 시나리오

- 공고 URL 미입력/형식 오류 시 `분석 시작` 비활성
- 파일 용량·형식 초과 시 업로더 에러 노출
- 409 `run_in_progress` → 기존 `runId`로 이동
- SSE 체크리스트 갱신 + `onerror` 폴백 조회
- `failureReason` 9종 분기 문구 확인
- 레포 카드 실패 상태(회색 + `errorCode`) 노출
- 레포 선택 5개 상한 처리
- 문서 추출 실패(`status: 'failed'`) 시 계속 진행 여부 확인 동작
- 더보기 202 `analyzing` 폴링 후 카드 추가 확인
- 확정 → 면접 생성 후 이동
