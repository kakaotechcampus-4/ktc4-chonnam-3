# 분석 Run

상태: Sprint 1 FIX.

## 입력

`POST /analysis-runs`

- `postingUrl`: 필수. Sprint 1은 Wanted URL만 허용한다.
- `documentId`: 선택. `POST /documents/preview`에서 생성한 문서만 허용한다.

문서 없이 공고 URL만으로 분석할 수 있다. 공고는 필수이고, Wanted fetch/extract 실패 또는 unsupported site는 hard blocker다.

## Wanted 공고 수집·분류

공고는 면접 분석의 원문으로 사용한다. 채용이 마감되었더라도 본문을 가져올 수 있으면 분석한다. Wanted의 `status`, `due_time`만으로 수집을 실패 처리하지 않는다. HTTP·네트워크 오류, 잘못된 응답, 빈 본문은 `jd_fetch_failed`, 본문은 있지만 추출 가능한 구조화 항목이 없으면 `jd_extraction_failed`로 처리한다.

API `category`는 화면의 항목 구분이고, DB·AI의 `requirement_type`은 필수·우대 여부다. 기존 [API enum](../../shared/contracts/openapi.yaml)과 [DB enum](../../../backend/docs/db-schema.md)을 각각 유지하며 다음과 같이 변환한다.

| Wanted 원문 필드 (`source_field`) | DB·AI `requirement_type` | API `category` |
| --- | --- | --- |
| `requirements` | `required` | `required` |
| `preferred_points` | `preferred` | `preferred` |
| `main_tasks` | `unknown` | `responsibility` |

주요 업무만으로 필수·우대 여부를 추측하지 않는다. `unknown`은 `responsibility`의 별칭이 아니며, 원문 출처가 `main_tasks`일 때만 API에서 주요 업무로 표시한다. 다른 출처의 `unknown`을 주요 업무로 바꾸지 않는다.

`JdRequirementDraft`는 API `category`와 함께 계산 속성 `requirement_type`, `source_field`를 제공한다. 저장 호출부는 두 속성을 명시적으로 읽고 원문 출처도 보존해야 재조회 후 같은 화면 분류를 복원할 수 있다. `category`를 DB `requirement_type`에 그대로 저장하지 않는다. 이 변환은 기존 enum을 연결하는 규칙이며 새 DB enum이나 컬럼을 추가하지 않는다.

## 단계

분석 step key는 7개로 고정한다.

1. `doc_extract`: Sprint 1에서는 포트폴리오 preview 문서에서 추출한 GitHub URL을 analysis context에 반영한다. claim 추출은 하지 않는다.
2. `repo_select`: 전체 public repo에 대해 L0-a lightweight ranking과 filter를 계산한다.
3. `repo_detail`: 분석 batch repo의 README, languages, head SHA, commit count, user commit count를 수집한다.
4. `jd_fetch`: Wanted 공개 JSON을 수집한다.
5. `jd_extract`: Wanted 구조화 필드에서 JD requirement와 tech tag를 만든다.
6. `repo_analyze`: batch repo에 대해 L1 shallow LLM 분석을 수행한다.
7. `match_score`: JD와 repo analysis를 매칭해 추천 카드 정보를 만든다.

## Candidate Ranking

`analysis_repo_candidates`에 run 종속 후보 순위를 저장한다. Redis를 원본으로 쓰지 않는다.

- 전체 public repo에 대해 `base_rank`와 `ranking_score`를 계산한다.
- 첫 batch 10개는 단순 상위 10개가 아니라 혼합 전략으로 구성한다.
- 첫 batch는 JD 수집·추출보다 먼저 확정되므로 JD signal을 사용하지 않는다.
- 첫 batch는 포트폴리오 GitHub URL 언급 repo 최대 3개, base rank top 최대 5개, high contribution 최대 2개를 중복 제거해 최대 10개로 만든다.
- JD 기반 score와 추천 이유는 `match_score` 단계와 후속 candidate page/ranking에서만 사용한다.
- 제외 repo도 `filter_status='excluded'`, `filter_reason`으로 저장한다. 기본 응답에는 `eligible`만 노출한다.

주요 필드:

- `analysis_job_id`
- `repository_id`
- `base_rank`
- `batch_no`
- `batch_rank`
- `selection_reason`: `portfolio_mentioned`, `base_rank_top`, `high_contribution`, `other`. `jd_signal`은 첫 batch에는 사용하지 않고, JD 확보 뒤 후속 ranking 신호로만 사용할 수 있다.
- `ranking_score`
- `ranking_signals JSONB`
- `filter_status`: `eligible`, `excluded`
- `filter_reason`: `private`, `fork`, `archived`, `no_language`, `too_small`, `inaccessible`

## 더 보기

`GET /analysis-runs/{runId}/candidates?page=N`

- 후보 page가 L0-b/L1 분석 완료면 `200`으로 repo card page를 반환한다.
- 미분석이면 ARQ page 분석 job을 enqueue하고 `202 { "status": "analyzing", "retryAfter": 3 }`를 반환한다.
- page 분석 상태는 `analysis_repo_candidate_pages`에 저장한다.
- 전체 `analysis_jobs.status`는 page 추가 분석 때문에 다시 `running`으로 되돌리지 않는다.

## 부분 실패

DB 상태:

- 일부 성공 + 일부 repo 실패: `analysis_jobs.status='partial'`
- 전부 실패: `analysis_jobs.status='failed'`

FE 상태 매핑:

- `queued`, `running` -> `running`
- `succeeded` -> `completed`
- `partial`, `failed`, `canceled` -> `failed`

`partial`이어도 `/analysis-runs/{runId}/result`는 조회 가능하다. 결과에는 `analyzedCount`, `failedCount`, `failedRepositories[]`를 포함한다.

## 중복 요청

중복 요청 재사용은 `POST /analysis-runs`에만 적용한다.

- fingerprint: `user_id`, normalized `posting_url`, `document_id` 또는 문서 해시/추출 GitHub URL 목록.
- 같은 fingerprint의 `queued/running` job이 있으면 기존 `runId`를 반환한다.
- 종료 상태(`succeeded`, `partial`, `failed`, `canceled`)면 새 run 생성을 허용한다.

## 선택 가능 조건

`POST /interviews`는 선택 repo가 모두 다음 조건을 만족해야 한다.

- 현재 run에 속함
- public, accessible
- candidate `eligible`
- L1 analysis `succeeded`
- 최소 1개, 최대 5개

불만족 시 `invalid_repository`, 0개면 `no_repository_selected`, 6개 이상이면 `too_many_repositories`.
