# error reason 레지스트리

> FE 와 공유하는 **유일한 원본**. 값은 `app/shared/enums.py` 에서만 정의하고 이 문서와 함께 늘린다.
> BE 가 임의로 reason 을 만들면 FE 가 문구를 붙일 수 없다.

## 봉투

```json
{ "error": { "reason": "run_expired", "message": "분석 결과가 만료되었어요.", "retryAfter": 30 } }
```

- `retryAfter` 는 optional — 에러 핸들러 안에서만 `model_dump(exclude_none=True)` 를 쓴다.
- `HTTPException` 을 직접 raise 하지 않는다. FastAPI 기본 `{"detail": ...}` 이 새어나가면 FE 파싱이 깨진다.
- 전역 핸들러 3개: `AppError`, `RequestValidationError`(→ 400), `Exception`(→ 500 `internal_error`).

---

## ★ 에러는 3계층이다

같은 이름의 에러가 층마다 다른 뜻을 갖는다. **층을 섞으면 10개 중 3개 실패 때문에 전체를 실패
처리하게 된다.**

| 계층 | 컬럼 | 단위 | 실패 시 job 상태 |
|---|---|---|---|
| 작업 전체 | `analysis_jobs.error_code` | run 1건 | `failed` |
| 레포 1개 | `repo_analyses.error_code` | 레포 1개 | job 은 `succeeded`, 해당 row 만 `failed` |
| 공고 1건 | `job_postings.parse_error_code` | 공고 1건 | job 은 `failed` (공고 필수) |

10개 중 3개가 실패하면 → **job 은 `succeeded`, 개별 row 3개가 `failed`.**

---

## ① HTTP 에러 (`AppError` → 봉투)

| 그룹 | reason | HTTP |
|---|---|---|
| 인증 | `unauthenticated` | 401 |
| | `token_invalid` | 403 |
| 분석 요청 | `job_url_required` | 400 |
| | `run_in_progress` | 409 |
| | `file_too_large` | 413 |
| | `unsupported_media_type` | 415 |
| 분석 조회 | `run_expired` | 410 |
| | `not_ready` | 409 |
| 면접 생성 | `no_repository_selected` | 400 |
| | `invalid_repository` | 400 |
| | `session_limit_exceeded` | 409 |
| 면접 조회 | `not_found` | 404 |
| 재시도 | `original_not_completed` | 409 |
| | `repository_unavailable` | 409 |
| 리포트 | `report_unavailable` | 409 |
| 이의 제출 | `already_submitted` | 409 |
| 공통 | `internal_error` | 500 |

`github_token_expired` → **`token_invalid` 로 확정** (FE 합의: BE 내부명을 그대로 쓴다).
`github_accounts.token_status` 가 `expired` / `revoked` 로 갈리지만 API 에는 `token_invalid` 하나로 낸다.

---

## ② `analysis_jobs.error_code` — 작업 전체 (HTTP 200 + `failureReason`)

⚠ **분석 실패는 HTTP 200 이다.** `GET /analysis-runs/{runId}` 는 `status:"failed"` +
`failureReason` 으로 답한다. 여기서 4xx 를 내면 FE 의 `queryCache.onError` 가 걸려 로그인 화면으로 튄다.

| 그룹 | error_code | 재시도 |
|---|---|---|
| 레포 | `no_public_repo` | X |
| | `user_not_found` | X |
| | `rate_limited` | reset 후 |
| | `token_invalid` | 재연동 |
| 공고 | `jd_fetch_failed` | 자동 1회 (우리 코드 실패) |
| | `jd_extraction_failed` | 자동 1회 (LLM 실패) |
| | `not_a_job_posting` | X |
| 문서 | `doc_extract_failed` | 자동 1회 |
| 공통 | `llm_timeout` | 자동 1회 |

**FE 합의로 확정된 개명** — 경계 매핑 레이어를 두지 않고 아래 이름을 그대로 내려보낸다.

| 구 api-spec | 확정 |
|---|---|
| `jd_unreachable` | `jd_fetch_failed` |
| `jd_parse_failed` | `jd_extraction_failed` |
| `github_token_expired` | `token_invalid` |

`jd_fetch_failed`(우리 코드)와 `jd_extraction_failed`(LLM)를 나눈 게 핵심 — **재시도 가능 여부가 다르다.**

---

## ③ `repo_analyses.error_code` — 레포 1개

`status` 는 3값이다.

| status | 상황 |
|---|---|
| `succeeded` | 필수 필드가 다 채워짐 |
| `failed` | 결과 없음. 해당 레포는 매칭 후보에서 제외 |
| `partial` | 배치 때문에 필요한 값. 예: `project_types` 는 나왔는데 `tech_stack` 이 빈 배열 → 카드는 띄우되 매칭 점수는 낮게 |

| error_code | 발생 | 실제 상황 | 화면 | 재시도 |
|---|---|---|---|---|
| `llm_timeout` | M2, M4-a | 배치 응답 타임아웃 | "분석이 지연되고 있습니다" | 자동 1회 |
| `parse_failed` | M2, M4-a | LLM 이 JSON 형식을 안 지킴 | 동일 | 자동 1회 |
| `input_too_large` | M2 | README 가 수백 KB — 컨텍스트 초과 | 카드에 "정보 부족" | X (입력 잘라 1회) |
| `no_readme` | M2 | README 없음 → 판단 근거 부족 | 카드 회색 + "정보 부족" | X |
| `repo_unreachable` | M4-a | 확정 후 레포가 private 전환/삭제 | "레포에 접근할 수 없습니다" | X |
| `token_invalid` | M2, M4-a | GitHub 토큰 만료/취소 | "GitHub 재연동이 필요합니다" | 재로그인 |

`token_invalid` 는 `github_accounts.token_status` 와 연동된다 — 401 을 받으면
`token_status='revoked'` 로 UPDATE 하고 다음 요청은 GitHub 호출 전에 차단한다.

**읽기 시점**

- M2 — `COUNT(*) FILTER (WHERE status='succeeded')` → "20개 중 17개 분석 완료" 진행률
- M3 — `failed` 레포는 카드 회색 + `error_code` 별 문구 + [재시도]
- M4-a — `repo_unreachable` 이면 그 레포만 빼고 면접을 진행한다 (전체 중단 아님)

---

## ④ `job_postings.parse_error_code` — 공고 1건

| 코드 | 단계 | 상황 | 화면 |
|---|---|---|---|
| `unsupported_site` | 우리 | 어댑터 없는 사이트 | "지원하지 않는 사이트예요" |
| `url_unreachable` | 우리 | 404 · 마감 · 네트워크 | "공고를 불러올 수 없어요" |
| `content_empty` | 우리 | 텍스트 · 이미지 둘 다 없음 | 동일 |
| `not_a_job_posting` | LLM | 공고가 아니라 판정 | "채용 공고가 아닌 것 같아요" |
| `extraction_failed` | LLM | 요구사항 0건 | "공고를 분석하지 못했어요" |
| `llm_timeout` / `parse_failed` | LLM | | 자동 1회 재시도 |
| `input_too_large` | LLM | 컨텍스트 초과 (이미지 공고) | 2차 |

**단계가 나뉘는 게 핵심** — `unsupported_site` 는 재시도해도 소용없고(사이트를 지원해야 함),
`llm_timeout` 은 재시도하면 되니 화면 대응이 다르다.

---

## ⑤ WebSocket

스프린트1 은 **양방향 텍스트**다. 아래 2개는 스프린트2 에서 STT/TTS 를 붙일 때 추가한다.

| reason | 스프린트 |
|---|---|
| `question_failed` | 1 |
| `answer_too_long` | 1 |
| `prepare_failed` | 1 |
| `already_connected` | 1 |
| `stt_failed` | **2** |
| `tts_failed` | **2** |

---

## 미결 — 확정 필요

### `analysis_jobs.status='partial'` 을 FE 에 무엇으로 내려보내나 ⚠

`RunStatus` 는 `running` / `completed` / `failed` 3값인데 DB 는 6값
(`queued` / `running` / `succeeded` / `partial` / `failed` / `canceled`) 이다.

`partial` = **작업은 끝났고 결과도 있지만 후보 레포 일부가 빠진 상태** (10개 중 8개 성공).
넣은 이유는 4-3-v2 부분 실패 화면 때문이다. `completed` 로 뭉개면 "10개 중 8개 분석 완료"
문구와 실패 카드 회색 처리를 만들 수 없고, `failed` 로 내면 8개짜리 정상 결과를 버리게 된다.

**BE 권고** — `RunStatus` 에 값을 추가하지 않는다.

```
queued / running        → "running"
succeeded / partial     → "completed"
failed / canceled       → "failed"
```

대신 결과 응답에 카드 단위 정보를 싣는다 (`analyzedCount` / `failedCount` /
`failedRepositories[{repositoryId, errorCode}]`). 회색 카드와 문구는 어차피 레포 단위 정보를
필요로 하므로, union 에 값을 하나 늘리는 것보다 이쪽이 화면에 바로 쓰인다.

### `users.status` 가 `suspended` / `withdrawn` 일 때의 reason

대응 reason 이 api-spec 에 없다. `account_suspended` (403) 신설 제안 — FE 확정 필요.
