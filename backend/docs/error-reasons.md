# Error Reason 레지스트리

상태: Sprint 1 FIX. 값을 추가할 때 `spec/shared/contracts/openapi.yaml`, `app/shared/enums.py`, 테스트를 함께 갱신한다.

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
| 인증 | `token_invalid` | 403 |
| 인증 | `account_suspended` | 403 |
| 인증 | `account_withdrawn` | 403 |
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
