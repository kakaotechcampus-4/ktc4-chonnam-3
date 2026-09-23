# Error Reason 레지스트리

상태: Sprint 1 FIX. 실제 HTTP 오류 레지스트리는 `app/core/errors.py`의 `Reason`과 `ERRORS`다. 값을 추가할 때 공통 계약, 소비 코드와 테스트를 함께 검토한다. 아래 전체 도메인 표에는 향후 기능의 계약값도 포함되어 있다.

현재 코드에 등록된 reason은 `unauthenticated`, `github_token_invalid`, `account_suspended`, `account_withdrawn`, `invalid_state`, `invalid_code`, `provider_unavailable`, `github_already_linked`, `not_found`, `invalid_request`, `internal_error`다. 나머지 도메인 reason을 런타임에서 이미 제공한다고 해석하지 않는다.

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
| 면접 준비 | `prep_failed` | 409 |
| 면접 준비 | `repo_unreachable` | 409 |
| 면접 조회 | `not_found` | 404 |
| 재시도 | `original_not_completed` | 409 |
| 재시도 | `repository_unavailable` | 409 |
| 리포트 | `report_unavailable` | 409 |
| 이의 제출 | `already_submitted` | 409 |
| 공통 | `internal_error` | 500 |
| 공통 요청 검증 | `invalid_request` | 400 |

`invalid_state`는 브라우저 쿠키 불일치, state 만료·재사용, 잘못된 목적 또는 재연동 사용자 불일치를 포함한다. `github_already_linked`는 기존 계정과 다른 GitHub 사용자 ID로 재연동하려는 경우다. `provider_unavailable`은 GitHub 연결/응답 오류와 지원하지 않는 만료형 토큰 응답을 포함한다. 공급자의 원문이나 토큰은 envelope에 넣지 않는다.

Redis 세션 조회·삭제 장애는 `500 internal_error`이며 `401 unauthenticated`로 바꾸지 않는다. 쿠키 없음·세션 만료·유실은 `401 unauthenticated`다. 상태 변경 요청과 WS handshake에서 다른 Origin을 거부할 때는 같은 `unauthenticated` reason을 HTTP 403으로 사용한다.

GitHub가 만료·refresh 필드를 가진 유효한 토큰을 발급하면 `502 provider_unavailable` reason을 유지하되 로그인 설정 불일치 메시지를 반환한다. 서버는 비밀값 없이 `github_oauth_token_mode_unsupported`를 기록한다. 이는 네트워크 장애가 아니며 OAuth App의 만료형 토큰 옵션과 현재 장기 토큰 설계를 맞춰야 한다.

> `github_token_invalid`는 DEVON 세션이 아니라 GitHub 연동 토큰이 무효·폐기된 상태다
> (`github_accounts.token_status`가 `invalid`·`revoked`). long-lived 토큰 모델에 `expired` 상태는 없다. 화면은 로그인이 아니라 재연동으로 유도한다.
> 2026-09-10 `token_invalid`에서 개명됐다. `frontend/docs/api-spec.md` #7·#8 및 변경 이력 참고.
> 아래 `analysis_jobs.error_code`의 `token_invalid`는 API 표면이 아닌 내부 코드라 그대로 둔다.

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

## Partial Mapping

DB `analysis_jobs.status='partial'`은 FE `RunStatus`에 `failed`로 매핑한다. 단, `/analysis-runs/{runId}/result`는 조회 가능하고 성공/실패 repo 정보를 포함한다.

## Sprint 2

`stt_failed`, `tts_failed`, 음성 길이 초과 같은 음성 reason은 Sprint 2에서 추가한다.
