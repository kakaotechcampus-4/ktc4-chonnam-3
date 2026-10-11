# Error Reason 레지스트리

상태: Sprint 1 FIX. API reason의 단일 정의는 `app/shared/enums.py`의 `Reason`이다. `app/core/errors.py`는 `STATUS_BY_REASON`·`MESSAGE_BY_REASON`과 `AppError`를 제공한다. 값을 추가할 때 공통 계약, 소비 코드와 테스트를 함께 검토한다.

OAuth와 분석·면접 등 모든 기능은 같은 레지스트리를 사용한다. 아래 표의 reason은 코드에 등록되어 있으며, 각 API의 구현 여부와는 구분한다. 브라우저 callback 표시 코드는 아래 별도 절을 따른다.

## Error Envelope

```json
{
  "error": {
    "reason": "invalid_repository",
    "message": "선택할 수 없는 레포지토리입니다.",
    "details": {}
  }
}
```

`HTTPException`을 직접 raise하지 않는다. FastAPI 기본 `detail` 응답이 새면 계약 위반이다.

## HTTP Reason

아래 HTTP 상태는 일반 API 오류의 레지스트리다. 브라우저 OAuth callback의 알려진 실패는 아래 별도 절의 `302` 표시 코드로 전달하며, 일반 REST의 reason·상태·envelope는 변경하지 않는다.

| 그룹 | reason | HTTP |
| --- | --- | --- |
| 인증 | `unauthenticated` | 401 |
| 인증 | `github_token_invalid` | 403 |
| 인증 | `account_suspended` | 403 |
| 인증 | `account_withdrawn` | 403 |
| OAuth | `invalid_state` | 400 |
| OAuth | `invalid_code` | 400 |
| OAuth·GitHub | `provider_unavailable` | 502 |
| GitHub 재연동 | `github_already_linked` | 409 |
| 문서 | `unsupported_document_type` | 415 |
| 문서 | `document_too_large` | 413 |
| 문서 | `document_extract_failed` | 200 또는 409 |
| 분석 요청 | `posting_url_required` | 400 |
| 분석 요청 | `unsupported_site` | 400 |
| 분석 요청 | `run_in_progress` | 409 |
| 분석 조회 | `not_ready` | 409 |
| 분석 조회 | `run_expired` | 410 |
| 후보 page | `candidate_page_failed` | 409 |
| 면접 생성 | `no_repository_selected` | 400 |
| 면접 생성 | `too_many_repositories` | 400 |
| 면접 생성 | `invalid_repository` | 400 |
| 면접 생성 | `session_limit_exceeded` | 409 |
| 면접 생성 | `run_expired` | 410 |
| 면접 준비 | `prep_failed` | 409 |
| 면접 준비 | `repo_unreachable` | 409 |
| 면접 준비 재시도 | `prep_in_progress` | 409 |
| 면접 준비 재시도 | `session_expired` | 410 |
| 면접 조회 | `not_found` | 404 |
| 재시도 | `original_not_completed` | 409 |
| 재시도 | `repository_unavailable` | 409 |
| 리포트 | `report_unavailable` | 409 |
| 이의 제출 | `already_submitted` | 409 |
| 공통 | `internal_error` | 500 |
| 공통 요청 검증 | `invalid_request` | 400 |

`invalid_state`는 브라우저 쿠키 불일치, state 만료·재사용, 잘못된 목적 또는 재연동 사용자 불일치를 포함한다. `github_already_linked`는 기존 계정과 다른 GitHub 사용자 ID로 재연동하려는 경우다. `provider_unavailable`은 GitHub 연결/응답 오류와 지원하지 않는 만료형 토큰 응답을 포함한다. 공급자의 원문이나 토큰은 envelope에 넣지 않는다.

Redis 세션 조회·삭제 장애는 `500 internal_error`이며 `401 unauthenticated`로 바꾸지 않는다. 쿠키 없음·세션 만료·유실은 `401 unauthenticated`다. 상태 변경 요청과 WS handshake에서 다른 Origin을 거부할 때는 같은 `unauthenticated` reason을 HTTP 403으로 사용한다.

GitHub가 만료·refresh 필드를 가진 유효한 토큰을 발급하면 `502 provider_unavailable` 오류 정의와 로그인 설정 불일치 메시지를 유지한다. 브라우저 callback에서는 아래의 `provider_configuration` 표시 코드로 변환한다. 서버는 비밀값 없이 `github_oauth_token_mode_unsupported`를 기록한다. 이는 네트워크 장애가 아니며 OAuth App의 만료형 토큰 옵션과 현재 장기 토큰 설계를 맞춰야 한다.

> `github_token_invalid`는 DEVON 세션이 아니라 GitHub 연동 토큰이 무효·폐기된 상태다
> (`github_accounts.token_status`가 `invalid`·`revoked`). long-lived 토큰 모델에 `expired` 상태는 없다. 화면은 로그인이 아니라 재연동으로 유도한다.
> 2026-09-10 `token_invalid`에서 개명됐다. `frontend/docs/api-spec.md` #7·#8 및 변경 이력 참고.
> 아래 `analysis_jobs.error_code`의 `token_invalid`는 API 표면이 아닌 내부 코드라 그대로 둔다.

## 브라우저 OAuth callback 표시 코드

`/auth/github/callback`과 호환 경로 `/auth/github/link/callback`은 알려진 실패를 `302 /login?error=<표시 코드>`로 전달한다. 브라우저 이동 계약 원본은 [FE API 명세 #2·#8](../../frontend/docs/api-spec.md#2-get-authgithubcallback)이며 OpenAPI의 일반 REST 오류를 바꾸지 않는다.

| 원인/API reason | callback 표시 코드 |
| --- | --- |
| state 검증 후 GitHub 동의 거부 | `denied` |
| `invalid_state` | `invalid_state` |
| `invalid_code` | `invalid_code` |
| GitHub 연결·응답 오류의 `provider_unavailable` | `provider_unavailable` |
| 지원하지 않는 expiry·refresh 토큰 설정의 `provider_unavailable` | `provider_configuration` |
| `github_already_linked` | `github_already_linked` |
| `account_suspended` · `account_withdrawn` | 같은 표시 코드 |

`denied`·`provider_configuration`은 화면 표시용이며 API `Reason`을 추가하지 않는다. 특히 설정 불일치의 API reason은 `provider_unavailable`을 유지한다. redirect URL과 화면에는 고정 코드·고정 안내만 사용하며 code·state·토큰·공급자 원문을 전달하지 않는다. FE는 등록되지 않은 `error` 값을 무시하고 오류 배너 없이 기본 GitHub 로그인 버튼(`/api/auth/github/login`)을 표시한다.

재연동 state를 일회용 검증하고 현재 활성 사용자가 시작 사용자와 일치한 경우에만 `denied`·`invalid_code`·`provider_unavailable`·`provider_configuration`·`github_already_linked`에 `&flow=link`를 붙인다. FE 재시도는 고정된 `/api/auth/github/link`로 이동한다. state 무효·사용자 불일치·정지·탈퇴는 일반 로그인 안내로 돌아가며 `flow=link`를 붙이지 않는다. 재연동 세션 만료·유실은 기존대로 `/login`으로 이동하고 새 로그인 세션을 만들지 않는다.

`internal_error`와 Redis·세션·DB·enqueue 등 내부 장애는 기존 `500` JSON envelope를 유지한다. callback의 state 일회 소비·PKCE 검증, state 쿠키 정리, `Cache-Control: no-store`, `Referrer-Policy: no-referrer`도 유지한다.

## Job Error Code

`analysis_jobs.error_code`:

- `no_public_repo`
- `rate_limited`
- `token_invalid`
- `jd_fetch_failed`
- `jd_extraction_failed`
- `unsupported_site`
- `doc_extract_failed`
- `llm_timeout`
- `llm_parse_failed`
- `llm_failed`

현재 `initial_sync`는 위 내부 코드 중 `rate_limited`·`token_invalid`를 사용하며 provider 통신 실패는 `provider_unavailable`, enqueue/예상 밖 실패는 `internal_error`로 기록한다. job의 내부 `error_code`와 API reason은 별도 경계다.

`repo_analyses.error_code`:

- `rate_limited`
- `repo_unreachable`
- `no_readme`
- `input_too_large`
- `llm_timeout`
- `llm_parse_failed`
- `llm_failed`

`job_postings.parse_error_code`:

- `unsupported_site`
- `jd_fetch_failed`
- `jd_extraction_failed`
- `not_a_job_posting`

## GitHub 수집 오류의 계층

GitHub 수집 실패는 세 층을 거치며, 각 층의 코드는 서로 다른 축이라 이름이 같아도 같은 값이 아니다.

```
GitHub HTTP 응답 / 응답 형식 오류
  └─ integrations/github/client.py    GithubApiError.error_code   (예외에 실리는 내부 코드)
       ├─ 목록 수집(initial_sync)      → analysis_jobs.error_code  (작업 전체 실패 원인)
       └─ 저장소 상세(repo_detail)     → repo_analyses.error_code  (저장소 단위 실패 원인)
                                          ※ API 응답 Reason(envelope)과는 별도 경계
```

| 상황 | `GithubApiError.error_code` | 비고 |
| --- | --- | --- |
| 401 | `token_invalid` | 호출부가 `token_status='revoked'`로 바꾼다 |
| 429, 또는 헤더·본문이 제한을 가리키는 403 | `rate_limited` | 429는 헤더가 없어도 제한이다. 대기 초는 Retry-After 우선, 없으면 60초 |
| 그 외 4xx/5xx, 네트워크 오류 | `repo_unreachable` | 일시 장애와 접근 불가를 이 코드만으로 구분하지 않는다 |
| 200이지만 목록이 list가 아님, 항목 필수 필드(id·name·full_name·private) 누락·타입 오류, JSON 아님 | `repo_unreachable` | 빈 목록(`[]`)과 달리 **실패**다. 일부 page만 모은 목록도 돌려주지 않는다 |
| next 주소가 API origin이 아니거나 경로가 다르거나 page가 증가하지 않음, 목록 응답이 3xx | `repo_unreachable` | 요청을 보내기 전에 중단하므로 토큰이 외부로 나가지 않는다 |

목록 수집이 실패하면 `initial_sync`는 DB 변경을 rollback하고 `analysis_jobs`만 `failed`로 기록하므로
기존 저장소를 접근 불가(`is_accessible=false`)로 바꾸지 않는다.

## Partial Mapping

DB `analysis_jobs.status='partial'`은 FE `RunStatus`에 `failed`로 매핑한다. 단, `/analysis-runs/{runId}/result`는 조회 가능하고 성공/실패 repo 정보를 포함한다.

## Sprint 2

`stt_failed`, `tts_failed`, 음성 길이 초과 같은 음성 reason은 Sprint 2에서 추가한다.
